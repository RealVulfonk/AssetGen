import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import process_pbr_seams as seams


class SeamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for kind, color in [('base_color', (20, 40, 60)), ('normal', (128, 128, 255)), ('roughness', (90, 91, 92))]:
            im = Image.new('RGB', (12, 10), color)
            if kind == 'base_color':
                for y in range(10):
                    im.putpixel((11, y), (200, 30, 50))
            im.save(self.root / f'test_{kind}.png')

    def test_candidate_masks_data_and_refuses_overwrite(self):
        out = seams.run(self.root, self.root, 'test', 2)
        report = json.loads((out / 'report.json').read_text())
        self.assertEqual(report['status'], 'needs_review')
        for kind in seams.PANELS:
            before = Image.open(self.root / f'test_{kind}.png').convert('RGB')
            after = Image.open(out / f'test_{kind}.png').convert('RGB')
            self.assertEqual(after.size, before.size)
            for y in range(2, 8):
                for x in range(2, 10):
                    expected = before.getpixel((x, y))
                    if kind == 'roughness': expected = (expected[1],) * 3
                    self.assertEqual(after.getpixel((x, y)), expected)
            if kind == 'normal':
                for p in [after.getpixel((x, y)) for y in range(after.height) for x in range(after.width)]:
                    self.assertAlmostEqual(sum((v / 127.5 - 1)**2 for v in p), 1, delta=.03)
                    self.assertGreater(p[1], 126)
            if kind == 'roughness':
                self.assertTrue(all(r == g == b for r, g, b in [after.getpixel((x, y)) for y in range(after.height) for x in range(after.width)]))
        with self.assertRaises(ValueError): seams.run(self.root, self.root, 'test', 2)
        self.assertFalse((self.root / '.test_seam.split.lock').exists())

    def test_failure_rolls_back_and_unlocks(self):
        with patch.object(seams, 'process', side_effect=ValueError('injected')):
            with self.assertRaises(ValueError): seams.run(self.root, self.root, 'test', 2)
        self.assertFalse((self.root / 'test_seam_candidate').exists())
        self.assertFalse((self.root / '.test_seam.split.lock').exists())
        self.assertFalse(list(self.root.glob('.seam-*')))

    def test_deterministic_distinct_destinations(self):
        a = self.root / 'a'; b = self.root / 'b'; a.mkdir(); b.mkdir()
        first = seams.run(self.root, a, 'test', 2)
        second = seams.run(self.root, b, 'test', 2)
        for path in first.iterdir():
            self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())

    def test_invalid_dimensions_are_rejected(self):
        Image.new('RGB', (5, 5)).save(self.root / 'test_normal.png')
        with self.assertRaises(ValueError): seams.run(self.root, self.root, 'test', 2)
        self.assertFalse((self.root / 'test_seam_candidate').exists())

    def test_zero_normal_rejected_without_publication(self):
        image = Image.open(self.root / 'test_normal.png').copy()
        image.putpixel((5, 5), (128, 128, 128))
        image.save(self.root / 'test_normal.png')
        with self.assertRaisesRegex(ValueError, 'near-zero'):
            seams.run(self.root, self.root, 'test', 2)
        self.assertFalse((self.root / 'test_seam_candidate').exists())
        self.assertFalse((self.root / '.test_seam.split.lock').exists())

if __name__ == '__main__': unittest.main()



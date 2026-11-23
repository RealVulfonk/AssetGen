"""CLI and pixel-preservation tests for the PBR sheet splitter."""

import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "split_pbr_sheet.py"
KINDS = ("base_color", "normal", "roughness")


class SplitPbrSheetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.source = self.root / "sheet.png"
        self.colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255))
        sheet = Image.new("RGB", (12, 5))
        for panel, color in enumerate(self.colors):
            for y in range(5):
                for x in range(4):
                    sheet.putpixel((panel * 4 + x, y), (color[0], (x * 31 + y) % 256, color[2]))
        sheet.save(self.source)

    def tearDown(self):
        self.temporary.cleanup()

    def run_split(self, *extra, source=None, name="wall_stone", output=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(source or self.source),
             "--out", str(output or self.output), "--name", name, *extra],
            capture_output=True, text=True, encoding="utf-8",
        )

    def outputs(self):
        return [self.output / f"wall_stone_{kind}.png" for kind in KINDS]

    def test_splits_three_equal_panels_without_resampling(self):
        result = self.run_split()
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in self.outputs():
            self.assertTrue(path.is_file())
            self.assertIn("4x5", result.stdout)
            self.assertIn(str(path), result.stdout)
        with Image.open(self.source) as sheet:
            for index, path in enumerate(self.outputs()):
                with Image.open(path) as panel:
                    self.assertEqual(panel.size, (4, 5))
                    self.assertEqual(panel.mode, "RGB")
                    expected = sheet.convert("RGB").crop((index * 4, 0, (index + 1) * 4, 5))
                    self.assertEqual(panel.tobytes(), expected.tobytes())

    def test_rejects_width_not_divisible_by_three(self):
        Image.new("RGB", (10, 5), "white").save(self.source)
        result = self.run_split()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("divisible by 3", result.stderr)
        self.assertFalse(any(path.exists() for path in self.outputs()))

    def test_rejects_damaged_image_without_outputs(self):
        self.source.write_bytes(b"not a png")
        result = self.run_split()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot read image", result.stderr)
        self.assertFalse(any(path.exists() for path in self.outputs()))

    def test_repeat_requires_force_and_force_replaces_all_outputs(self):
        self.assertEqual(self.run_split().returncode, 0)
        before = [path.read_bytes() for path in self.outputs()]
        repeat = self.run_split()
        self.assertNotEqual(repeat.returncode, 0)
        self.assertIn("--force", repeat.stderr)
        self.assertEqual([path.read_bytes() for path in self.outputs()], before)

        Image.new("RGB", (6, 2), (17, 33, 65)).save(self.source)
        forced = self.run_split("--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        for path in self.outputs():
            with Image.open(path) as panel:
                self.assertEqual(panel.size, (2, 2))
                self.assertEqual(panel.tobytes(), bytes((17, 33, 65)) * 4)

    def test_concurrent_split_without_force_has_one_complete_publisher(self):
        colors = {"first": (17, 33, 65), "second": (101, 67, 35)}
        sources = []
        for label, color in colors.items():
            source = self.root / f"{label}.png"
            Image.new("RGB", (6, 2), color).save(source)
            sources.append(source)
        start = Barrier(2)

        def invoke(source):
            start.wait(timeout=10)
            return source, self.run_split(source=source)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(invoke, sources))
        successful = [(source, result) for source, result in results if result.returncode == 0]
        self.assertEqual(len(successful), 1, [(result.stdout, result.stderr) for _, result in results])
        failed = next(result for _, result in results if result.returncode != 0)
        self.assertTrue("another split" in failed.stderr or "--force" in failed.stderr, failed.stderr)
        winner = successful[0][0].stem
        for path in self.outputs():
            with Image.open(path) as panel:
                self.assertEqual(panel.tobytes(), bytes(colors[winner]) * 4)
        self.assertFalse((self.output / ".wall_stone.split.lock").exists())

    def test_rejects_unsafe_name_and_missing_output_directory(self):
        for name, output in (("../bad", self.output), ("Bad Name", self.output),
                             ("wall_stone", self.root / "missing")):
            with self.subTest(name=name, output=output):
                result = self.run_split(name=name, output=output)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(path.exists() for path in self.outputs()))


if __name__ == "__main__":
    unittest.main()

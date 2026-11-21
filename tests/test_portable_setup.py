"""Configuration precedence and model viewing with no local Blender outputs."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assetgen_config as config
import workbench as wb


class PortableSetupTests(unittest.TestCase):
    def test_local_configuration_does_not_change_shared_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assetgen.config.json").write_text(json.dumps({"blender": "blender", "out": "out"}))
            (root / "assetgen.local.json").write_text(json.dumps({"blender": "local-blender", "out": "local-out"}))
            loaded = config.load_config(root)
            self.assertEqual(loaded, {"blender": "local-blender", "out": "local-out"})
            with patch.dict(os.environ, {"BLENDER": "explicit-missing-blender"}), patch.object(config.shutil, "which", return_value=None):
                self.assertEqual(config.find_blender(loaded), "explicit-missing-blender")

    def test_library_is_viewable_without_out_and_local_build_takes_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "specs/models").mkdir(parents=True)
            model = root / "specs/models/example.json"
            model.write_text(json.dumps({"name": "example", "category": "props"}))
            output = root / "out/interiors/example"
            library = root / "library/interiors/example"
            library.mkdir(parents=True)
            (library / "example.glb").write_bytes(b"library")
            with patch.object(wb, "ROOT", root), patch.object(wb.ag, "OUT", root / "out"):
                self.assertEqual(wb.display_dir("example"), library)
                output.mkdir(parents=True)
                (output / "example.glb").write_bytes(b"local")
                self.assertEqual(wb.display_dir("example"), output)


if __name__ == "__main__":
    unittest.main()

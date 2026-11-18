"""Schema contract for local geometry operations and UV projections."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "schemas/model.schema.json").read_text("utf-8")))


class ModelSchemaTests(unittest.TestCase):
    def test_cylindrical_projection_is_limited_to_uncut_lathes(self):
        part = {
            "type": "lathe", "material": "wood", "uv_projection": "cylindrical",
            "profile": [[0, 0], [1, 0], [1, 2], [0, 2]],
        }
        for changes, valid in (
            ({}, True),
            ({"uv_projection": "planar"}, False),
            ({"type": "box", "size": [2, 2, 2]}, False),
            ({"cutouts": [{"type": "box", "size": [1, 1, 1]}]}, False),
        ):
            with self.subTest(changes=changes):
                self.assertEqual(VALIDATOR.is_valid({"name": "fixture", "parts": [{**part, **changes}]}), valid)

"""Schema contract for local geometry operations and UV projections."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = Draft202012Validator(json.loads((ROOT / "schemas/model.schema.json").read_text("utf-8")))


class ModelSchemaTests(unittest.TestCase):
    def test_plane_requires_an_outline_and_rejects_solid_operations(self):
        plane = {"type": "plane", "material": "glass"}
        outline = {"points": [[-1, -1], [1, -1], [1, 1], [-1, 1]]}
        for fields, valid in (
            (outline, True),
            ({}, False),
            ({"points": [[0, 0], [1, 0]]}, False),
            ({**outline, "depth": 0.01}, False),
            ({**outline, "bevel": {"width": 0.01}}, False),
            ({**outline, "cutouts": [{"type": "box", "size": [1, 1, 1]}]}, False),
        ):
            with self.subTest(fields=fields):
                self.assertEqual(VALIDATOR.is_valid({"name": "fixture", "parts": [{**plane, **fields}]}), valid)

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

    def test_cutouts_require_closed_supported_shapes_and_dimensions(self):
        for cutout, valid in (
            ({"type": "box", "size": [1, 2, 3]}, True),
            ({"type": "cylinder", "radius": 0.5, "height": 2, "rotation": [90, 0, 0]}, True),
            ({"type": "box"}, False),
            ({"type": "box", "size": [1, 2, -3]}, False),
            ({"type": "cylinder", "radius": 1}, False),
            ({"type": "sphere", "radius": 1}, False),
            ({"type": "box", "size": [1, 1, 1], "material": "dark"}, False),
        ):
            with self.subTest(cutout=cutout):
                part = {"type": "box", "size": [2, 2, 2], "material": "stone", "cutouts": [cutout]}
                self.assertEqual(VALIDATOR.is_valid({"name": "fixture", "parts": [part]}), valid)

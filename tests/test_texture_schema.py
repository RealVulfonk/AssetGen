"""Schema and palette contract tests for texture specs."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import jsonschema

import assetgen

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/texture.schema.json").read_text(encoding="utf-8"))
PALETTES = json.loads((ROOT / "presets/palettes.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def texture_document(material):
    return {"asset": "test_asset", "materials": {"default": material}}


class TextureSchemaTests(unittest.TestCase):
    def test_explicit_surface_sources_and_legacy_compatibility(self):
        detail = {"image": "fine_grained_wood.jpg", "tile_size": 1, "strength": 0.6}
        base = {"palette": "wood_dark", "preset": "wood"}
        self.assert_material_valid(base)
        self.assert_material_valid({**base, "source_detail": detail})
        for mode in ("procedural", "image", "mixed"):
            self.assert_material_valid({**base, "source_mode": mode, "source_detail": detail})
            self.assert_material_valid({**base, "source_mode": mode}, mode == "procedural")
        self.assert_material_valid({**base, "source_mode": "unknown"}, False)
        document = texture_document({**base, "source_mode": "image", "source_detail": detail})
        document["quantize"] = True
        self.assertFalse(VALIDATOR.is_valid(document))

    def assert_material_valid(self, material, expected=True):
        document = texture_document(material)
        self.assertEqual(VALIDATOR.is_valid(document), expected, VALIDATOR.iter_errors(document))

    def test_production_specs_and_named_palettes(self):
        paths = sorted((ROOT / "specs/textures").glob("*.json"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(spec=path.name):
                spec = json.loads(path.read_text(encoding="utf-8"))
                errors = list(VALIDATOR.iter_errors(spec))
                self.assertFalse(errors, errors)
                self.assertEqual(spec["asset"], path.stem)
                for material in spec["materials"].values():
                    palette = material["palette"]
                    if isinstance(palette, str):
                        self.assertIn(palette, PALETTES)

    def test_soft_defaults_are_declared(self):
        properties = SCHEMA["properties"]
        self.assertFalse(properties["pixel"]["default"])
        self.assertFalse(properties["quantize"]["default"])
        self.assertFalse(properties["pack_uv"]["default"])
        self.assertEqual(properties["samples"]["default"], 64)
        self.assertEqual(properties["margin"]["default"], 4)
        common = SCHEMA["$defs"]["material_common"]["properties"]
        self.assertEqual(common["gradient"]["default"], "ease")
        self.assertEqual(common["contrast_pivot"]["default"], 0.5)
        self.assertEqual(common["ao"]["default"], 0.25)

    def test_custom_layers_accepted(self):
        material = {
            "palette": "stone_grey_soft",
            "layers": [
                {"type": "noise", "scale": 3, "detail": 4, "weight": 2},
                {"type": "wave", "direction": "Z", "distortion": 0.5},
                {"type": "voronoi", "invert": True},
                {"type": "constant", "value": 0.25, "weight": 0.5},
            ],
        }
        self.assert_material_valid(material)

    def test_opacity_on_presets_and_custom_layers(self):
        for recipe in ({"preset": "flat"}, {"layers": [{"type": "constant", "value": 0.5}]}):
            material = {"palette": "stone_grey", **recipe}
            self.assert_material_valid(material)
            for opacity in (0, 0.35, 1, -0.01, 1.01, "0.35", True, False):
                with self.subTest(recipe=recipe, opacity=opacity):
                    valid = type(opacity) in (int, float) and 0 <= opacity <= 1
                    self.assert_material_valid({**material, "opacity": opacity}, valid)

    def test_preset_and_layers_are_mutually_exclusive(self):
        material = {
            "palette": "stone_grey",
            "preset": "stone",
            "layers": [{"type": "noise"}],
        }
        self.assert_material_valid(material, False)

    def test_preset_controls_rejected_with_layers(self):
        for field, value in (
            ("scale", 4),
            ("direction", "X"),
            ("distortion", 2),
            ("detail", 3),
            ("value", 0.5),
        ):
            with self.subTest(field=field):
                material = {"palette": "stone_grey", "layers": [{"type": "noise"}], field: value}
                self.assert_material_valid(material, False)

    def test_coopered_wood_controls(self):
        material = {
            "palette": "wood_dark_soft",
            "preset": "coopered_wood",
            "staves": 10,
            "seam_width": 0.05,
            "lid_board_width": 0.11,
            "grain_strength": 0.45,
        }
        self.assert_material_valid(material)
        self.assert_material_valid({**material, "preset": "wood"}, False)
        self.assert_material_valid({**material, "staves": 0}, False)
        self.assert_material_valid({**material, "seam_width": 0}, False)
        self.assert_material_valid({**material, "direction": "X"}, False)

    def test_source_detail_requires_a_local_image_and_valid_scale(self):
        detail = {"image": "fine_grained_wood.jpg", "tile_size": 0.6, "strength": 0.5}
        material = {"palette": "wood_dark", "source_detail": detail}
        self.assert_material_valid(material)
        for field, value in (("image", "../wood.png"), ("tile_size", 0), ("strength", 1.1)):
            with self.subTest(field=field):
                self.assert_material_valid({**material, "source_detail": {**detail, field: value}}, False)

    def test_irrelevant_layer_fields_rejected(self):
        cases = (
            ("noise", "direction", "X"),
            ("noise", "value", 0.5),
            ("wave", "detail", 2),
            ("voronoi", "distortion", 2),
            ("constant", "scale", 2),
        )
        for kind, field, value in cases:
            with self.subTest(kind=kind, field=field):
                material = {"palette": "stone_grey", "layers": [{"type": kind, field: value}]}
                self.assert_material_valid(material, False)

    def test_invalid_layer_collections_and_weights(self):
        layers = [
            [],
            [{"type": "noise"}] * 5,
            [{"type": "noise", "weight": 0}],
            [{"type": "noise", "weight": -1}],
            [{"type": "unknown"}],
        ]
        for value in layers:
            with self.subTest(layers=value):
                self.assert_material_valid({"palette": "stone_grey", "layers": value}, False)

    def test_gradient_pivot_and_unknown_fields(self):
        for gradient in ("constant", "linear", "ease"):
            with self.subTest(gradient=gradient):
                self.assert_material_valid({"palette": "stone_grey", "gradient": gradient})
        for pivot in (-0.01, 1.01):
            with self.subTest(pivot=pivot):
                self.assert_material_valid({"palette": "stone_grey", "contrast_pivot": pivot}, False)
        self.assert_material_valid({"palette": "stone_grey", "gradient": "smooth"}, False)
        self.assert_material_valid({"palette": "stone_grey", "unknown": True}, False)
        document = texture_document({"palette": "stone_grey"})
        document["unknown"] = True
        self.assertFalse(VALIDATOR.is_valid(document))
    def test_pbr_detail_requires_complete_aligned_image_sources(self):
        detail = {"image": "wall_base_color.png", "tile_size": 2, "strength": 1}
        pbr = {"normal": "wall_normal.png", "roughness": "wall_roughness.png"}
        base = {"palette": "stone_grey_soft", "source_mode": "image", "source_detail": detail}
        self.assert_material_valid({**base, "pbr_detail": pbr})
        self.assert_material_valid({**base, "pbr_detail": {**pbr, "normal_strength": 0.5}})
        for mode in (None, "procedural", "mixed"):
            with self.subTest(mode=mode):
                material = {**base, "pbr_detail": pbr}
                if mode is None:
                    material.pop("source_mode")
                else:
                    material["source_mode"] = mode
                self.assert_material_valid(material, False)
        for incomplete in ({"normal": "wall_normal.png"}, {"roughness": "wall_roughness.png"}, {}):
            with self.subTest(incomplete=incomplete):
                self.assert_material_valid({**base, "pbr_detail": incomplete}, False)
        for field, value in (("normal", "../wall_normal.png"), ("roughness", "wall.jpg"),
                             ("normal_strength", -0.1), ("normal_strength", 2.1)):
            with self.subTest(field=field, value=value):
                self.assert_material_valid({**base, "pbr_detail": {**pbr, field: value}}, False)
        self.assert_material_valid({"palette": "stone_grey_soft", "preset": "stone"})

    def test_pbr_source_files_are_checked_by_cli_validation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "schemas").mkdir(parents=True)
            (root / "specs/textures").mkdir(parents=True)
            (root / "presets/textures").mkdir(parents=True)
            (root / "schemas/texture.schema.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
            (root / "presets/palettes.json").write_text('{"stone_grey_soft": ["#808080"]}', encoding="utf-8")
            document = texture_document({
                "palette": "stone_grey_soft", "source_mode": "image",
                "source_detail": {"image": "wall_base_color.png", "tile_size": 2, "strength": 1},
                "pbr_detail": {"normal": "wall_normal.png", "roughness": "wall_roughness.png"},
            })
            (root / "specs/textures/test_asset.json").write_text(json.dumps(document), encoding="utf-8")
            with patch.object(assetgen, "ROOT", root):
                for filename in ("wall_base_color.png", "wall_normal.png"):
                    (root / "presets/textures" / filename).write_bytes(b"placeholder")
                with self.assertRaisesRegex(assetgen.AssetGenError, "pbr_detail.roughness"):
                    assetgen.load_texture_spec("test_asset")
                (root / "presets/textures/wall_roughness.png").write_bytes(b"placeholder")
                (root / "presets/textures/wall_normal.png").unlink()
                with self.assertRaisesRegex(assetgen.AssetGenError, "pbr_detail.normal"):
                    assetgen.load_texture_spec("test_asset")
                (root / "presets/textures/wall_normal.png").write_bytes(b"placeholder")
                self.assertEqual(assetgen.load_texture_spec("test_asset"), document)

    def test_pbr_normal_strength_default_is_declared(self):
        common = SCHEMA["$defs"]["material_common"]["properties"]
        self.assertEqual(common["pbr_detail"]["properties"]["normal_strength"]["default"], 1)


if __name__ == "__main__":
    unittest.main()

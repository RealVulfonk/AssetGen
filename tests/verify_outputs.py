"""Integration checks for generated reports, previews and GLB files (system Python)."""

import argparse
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assetgen_paths import output_dir


def read_glb(path):
    data = path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", data)
    assert magic == b"glTF", f"{path}: invalid GLB signature"
    assert version == 2, f"{path}: unsupported GLB version {version}"
    assert declared_length == len(data), f"{path}: incorrect declared length"
    chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
    assert chunk_type == 0x4E4F534A, f"{path}: first chunk is not JSON"
    document = json.loads(data[20 : 20 + chunk_length])
    assert document.get("meshes"), f"{path}: no meshes"
    assert document.get("buffers"), f"{path}: no buffers"
    return document


def assert_lighting_preview(output):
    path = output / "preview_lighting.png"
    with path.open("rb") as handle:
        header = handle.read(24)
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"{path}: invalid PNG"
    assert struct.unpack_from(">II", header, 16) == (1024, 512), f"{path}: expected two 512 px frames"


def assert_texture_samplers(document, texture_spec, asset_name, variant):
    expected_mag = 9728 if texture_spec.get("pixel", False) else 9729
    expected_min = (9984, 9986) if texture_spec.get("pixel", False) else (9985, 9987)
    checked = 0
    for material in document.get("materials", []):
        pbr = material.get("pbrMetallicRoughness", {})
        for info in (pbr.get("baseColorTexture"), material.get("normalTexture"),
                     pbr.get("metallicRoughnessTexture")):
            if info is None:
                continue
            texture = document["textures"][info["index"]]
            sampler = document["samplers"][texture["sampler"]]
            assert sampler.get("magFilter") == expected_mag, (
                f"{asset_name}{variant}: unexpected magnification filter {sampler.get('magFilter')}"
            )
            assert sampler.get("minFilter") in expected_min, (
                f"{asset_name}{variant}: unexpected mipmapped minification filter {sampler.get('minFilter')}"
            )
            image = document["images"][texture["source"]]
            assert "bufferView" in image and "uri" not in image, (
                f"{asset_name}{variant}: texture image is not embedded"
            )
            assert image.get("mimeType") == "image/png", f"{asset_name}{variant}: expected an embedded PNG"
            checked += 1
    assert checked, f"{asset_name}{variant}: no textured samplers checked"


def assert_pbr_materials(document, texture_spec, model_tags, label):
    configs = texture_spec["materials"]
    materials = {material.get("name"): (index, material)
                 for index, material in enumerate(document.get("materials", []))}
    for tag in model_tags:
        index, material = materials[tag]
        config = configs.get(tag, configs["default"])
        pbr = config.get("pbr_detail")
        surface = material.get("pbrMetallicRoughness", {})
        if not pbr:
            assert "normalTexture" not in material, f"{label}/{tag}: unexpected legacy normal texture"
            assert "metallicRoughnessTexture" not in surface, f"{label}/{tag}: unexpected legacy ORM texture"
            continue
        normal = material.get("normalTexture")
        assert normal is not None, f"{label}/{tag}: normalTexture missing"
        assert abs(normal.get("scale", 1) - pbr.get("normal_strength", 1)) < 1e-6, (
            f"{label}/{tag}: normal scale differs from pbr_detail"
        )
        metallic_roughness = surface.get("metallicRoughnessTexture")
        assert metallic_roughness is not None, f"{label}/{tag}: metallicRoughnessTexture missing"
        assert abs(surface.get("roughnessFactor", 1) - config.get("roughness", 0.9)) < 1e-6, (
            f"{label}/{tag}: roughness factor is not the scalar multiplier"
        )
        assert abs(surface.get("metallicFactor", 1) - config.get("metallic", 0)) < 1e-6, (
            f"{label}/{tag}: metallic scalar changed during ORM packing"
        )
        texcoords = {
            info.get("texCoord", 0)
            for info in (surface.get("baseColorTexture"), normal, metallic_roughness)
        }
        assert len(texcoords) == 1, f"{label}/{tag}: PBR channels use different UV sets"
        primitives = [primitive for mesh in document["meshes"] for primitive in mesh["primitives"]
                      if primitive.get("material") == index]
        assert primitives and all("TANGENT" in primitive["attributes"] for primitive in primitives), (
            f"{label}/{tag}: exported tangent basis missing"
        )
        uv_attributes = {
            attribute
            for primitive in primitives
            for attribute in primitive["attributes"]
            if attribute.startswith("TEXCOORD_")
        }
        assert uv_attributes == {"TEXCOORD_0"}, (
            f"{label}/{tag}: temporary PBR projection leaked into exported UV sets: {uv_attributes}"
        )


def assert_material_opacity(document, texture_spec, expected_tags, label):
    materials = {
        material["name"]: material
        for material in document.get("materials", [])
        if "baseColorTexture" in material.get("pbrMetallicRoughness", {})
    }
    assert set(materials) == set(expected_tags), f"{label}: exported material tags differ from the model"
    configs = texture_spec["materials"]
    for tag, material in materials.items():
        opacity = configs.get(tag, configs.get("default", {})).get("opacity", 1)
        alpha = material["pbrMetallicRoughness"].get("baseColorFactor", [1, 1, 1, 1])[3]
        assert abs(alpha - opacity) < 1e-6, f"{label}/{tag}: alpha {alpha} differs from opacity {opacity}"
        mode = material.get("alphaMode", "OPAQUE")
        if opacity == 1:
            assert mode == "OPAQUE", f"{label}/{tag}: expected an opaque material"
        else:
            # Blender may export exactly zero as a mask that discards every fragment.
            invisible_mask = opacity == 0 and mode == "MASK" and material.get("alphaCutoff", 0.5) > 0
            assert mode == "BLEND" or invisible_mask, f"{label}/{tag}: unexpected alpha mode {mode}"
            assert material.get("doubleSided") is True, f"{label}/{tag}: transparent material is one-sided"


def verify(out_root, assets=()):
    model_count = 0
    texture_count = 0
    missing = []
    found = set()
    for spec_path in sorted((ROOT / "specs/models").glob("*.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        name = spec["name"]
        if assets and name not in assets:
            continue
        found.add(name)
        output = output_dir(out_root, name, spec.get("category"))
        if not (output / "report.json").is_file():
            assert not assets, f"{name}: model report missing in {output}"
            # Specs are committed; builds are not. Iterating on a few assets at a
            # time is normal, so skip what was never built instead of failing.
            missing.append(name)
            continue
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        assert report["status"] == "OK", f"{name}: model warnings: {report['warnings']}"
        assert report["tris"] <= report["tri_budget"], f"{name}: triangle budget exceeded"
        for view in ("front", "side", "iso", "top"):
            preview = output / f"preview_{view}.png"
            assert preview.stat().st_size > 100, f"{name}: missing or empty {preview.name}"
        document = read_glb(output / f"{name}.glb")
        node_names = {node.get("name") for node in document.get("nodes", [])}
        collision_names = {f"{name}-colonly", f"{name}-convcolonly"}
        assert not collision_names.intersection(node_names), f"{name}: collision leaked into visual GLB"
        collision_type = spec.get("collision", "none")
        if collision_type != "none":
            godot_document = read_glb(output / f"{name}_godot.glb")
            godot_node_names = {node.get("name") for node in godot_document.get("nodes", [])}
            collision_name = f"{name}-convcolonly" if collision_type == "convex" else f"{name}-colonly"
            assert collision_name in godot_node_names, f"{name}: collision node missing in Godot GLB"
            assert name in godot_node_names, f"{name}: visual node missing in Godot GLB"
            if collision_type == "mesh":
                def position_count(node_name):
                    node = next(item for item in godot_document["nodes"] if item.get("name") == node_name)
                    mesh = godot_document["meshes"][node["mesh"]]
                    return sum(
                        godot_document["accessors"][primitive["attributes"]["POSITION"]]["count"]
                        for primitive in mesh["primitives"]
                    )

                assert position_count(collision_name) == position_count(name), f"{name}: collision geometry differs"
        model_count += 1

        texture_spec_path = ROOT / "specs/textures" / f"{name}.json"
        if not texture_spec_path.exists():
            if report.get("lighting_preview"):
                assert_lighting_preview(output)
            continue
        if not (output / "report_texture.json").is_file():
            assert not assets, f"{name}: texture report missing in {output}"
            if report.get("lighting_preview"):
                assert_lighting_preview(output)
            continue
        texture_report = json.loads((output / "report_texture.json").read_text(encoding="utf-8"))
        if texture_report.get("lighting_preview"):
            assert_lighting_preview(output)
        assert texture_report["status"] == "OK", f"{name}: texture warnings"
        assert (output / f"{name}_albedo.png").is_file(), f"{name}: albedo missing"
        assert document.get("images"), f"{name}: no embedded GLB image"
        textured_materials = [
            material
            for material in document.get("materials", [])
            if "baseColorTexture" in material.get("pbrMetallicRoughness", {})
        ]
        assert textured_materials, f"{name}: no textured material in GLB"
        texture_spec = json.loads(texture_spec_path.read_text(encoding="utf-8"))
        configs = texture_spec["materials"]
        has_pbr = any(configs.get(tag, configs["default"]).get("pbr_detail")
                      for tag in report["materials"])
        for key, suffix in (("normal_texture", "normal"), ("orm_texture", "orm")):
            filename = f"{name}_{suffix}.png"
            if has_pbr:
                assert texture_report.get(key), f"{name}: report {key} missing"
                assert Path(texture_report[key]).name == filename, f"{name}: report {key} has wrong path"
                assert (output / filename).is_file(), f"{name}: {filename} missing"
            else:
                assert key not in texture_report, f"{name}: stale report {key}"
                assert not (output / filename).exists(), f"{name}: stale {filename}"
        assert_texture_samplers(document, texture_spec, name, "")
        assert_material_opacity(document, texture_spec, report["materials"], name)
        assert_pbr_materials(document, texture_spec, report["materials"], name)
        godot_glb = output / f"{name}_godot.glb"
        if godot_glb.is_file():
            godot_document = read_glb(godot_glb)
            assert_texture_samplers(godot_document, texture_spec, name, "_godot")
            assert_material_opacity(godot_document, texture_spec, report["materials"], f"{name}_godot")
            assert_pbr_materials(godot_document, texture_spec, report["materials"], f"{name}_godot")
        if "material_settings" in texture_report:
            packed = texture_report.get("pack_uv", False)
            if "pack_uv" in texture_report:
                assert packed == texture_spec.get("pack_uv", False), f"{name}: pack_uv differs from spec"
            margin_default = min(4, texture_report["size"] // 64) if packed else 4
            for key, default in (
                ("seed", 1),
                ("pixel", False),
                ("quantize", False),
                ("samples", 64),
                ("margin", margin_default),
            ):
                assert texture_report[key] == texture_spec.get(key, default), f"{name}: report {key} differs from spec"
            assert texture_report["margin_type"] == "EXTEND", f"{name}: unexpected bake margin type"
            assert texture_report["unique_colors"] > 0, f"{name}: invalid unique color count"
            assert set(texture_report["material_settings"]) == set(texture_report["materials"]), (
                f"{name}: material settings do not match material slots"
            )
            configs = texture_spec["materials"]
            for tag, settings in texture_report["material_settings"].items():
                opacity = configs.get(tag, configs.get("default", {})).get("opacity", 1)
                assert settings.get("opacity", 1) == opacity, f"{name}/{tag}: report opacity differs from spec"
        texture_count += 1

    assert not (set(assets) - found), f"Unknown assets: {sorted(set(assets) - found)}"
    print(f"Verified {model_count} models and {texture_count} textured GLBs")
    if missing:
        print(f"Skipped {len(missing)} specs that are not built in out/: {', '.join(missing[:8])}"
              + (" ..." if len(missing) > 8 else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", nargs="*", help="asset names to require; omit to scan built assets")
    parser.add_argument("--out", type=Path, default=ROOT / "out")
    args = parser.parse_args()
    verify(args.out, args.assets)

"""Integration checks for generated reports, previews and GLB files (system Python)."""

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def main():
    model_count = 0
    texture_count = 0
    for spec_path in sorted((ROOT / "specs/models").glob("*.json")):
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        name = spec["name"]
        output = ROOT / "out" / name
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
            continue
        texture_report = json.loads((output / "report_texture.json").read_text(encoding="utf-8"))
        assert texture_report["status"] == "OK", f"{name}: texture warnings"
        assert (output / f"{name}_albedo.png").is_file(), f"{name}: albedo missing"
        assert document.get("images"), f"{name}: no embedded GLB image"
        textured_materials = [
            material
            for material in document.get("materials", [])
            if "baseColorTexture" in material.get("pbrMetallicRoughness", {})
        ]
        assert textured_materials, f"{name}: no textured material in GLB"
        texture_count += 1

    print(f"Verified {model_count} models and {texture_count} textured GLBs")


if __name__ == "__main__":
    main()

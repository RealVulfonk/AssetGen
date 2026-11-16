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
        assert f"{name}-colonly" not in node_names, f"{name}: collision leaked into visual GLB"
        if spec.get("collision") == "box":
            godot_document = read_glb(output / f"{name}_godot.glb")
            godot_node_names = {node.get("name") for node in godot_document.get("nodes", [])}
            assert f"{name}-colonly" in godot_node_names, f"{name}: collision node missing in Godot GLB"
            assert name in godot_node_names, f"{name}: visual node missing in Godot GLB"
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

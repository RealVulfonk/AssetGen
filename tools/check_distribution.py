"""Validate all sources and verify every file in the shareable model library."""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import assetgen as ag


def check():
    models = sorted((ROOT / "specs/models").glob("*.json"))
    for model in models:
        data = ag.validate(model, "model.schema.json")
        assert data["name"] == model.stem, f"Model name mismatch: {model}"
    textures = sorted((ROOT / "specs/textures").glob("*.json"))
    for texture in textures:
        ag.load_texture_spec(texture.stem)
    library = ROOT / "library"
    manifest = json.loads((library / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["assets"], "Library must contain built assets"
    seen = set()
    for asset in manifest["assets"]:
        assert asset["name"] not in seen, f"Duplicate asset {asset['name']}"
        seen.add(asset["name"])
        assert (ROOT / "specs/models" / f"{asset['name']}.json").is_file()
        glbs = 0
        for entry in asset["files"]:
            path = (library / entry["path"]).resolve()
            assert path.is_relative_to(library.resolve()), f"Invalid library path: {entry['path']}"
            data = path.read_bytes()
            assert len(data) == entry["bytes"], f"Size mismatch: {path}"
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], f"SHA256 mismatch: {path}"
            assert len(data) < 50 * 1024 * 1024, f"Large Git blob: {path}"
            if path.suffix == ".glb":
                magic, version, size = struct.unpack_from("<4sII", data)
                assert (magic, version, size) == (b"glTF", 2, len(data)), f"Invalid GLB: {path}"
                length, kind = struct.unpack_from("<II", data, 12)
                assert kind == 0x4E4F534A
                document = json.loads(data[20:20 + length])
                assert document.get("meshes"), f"No meshes: {path}"
                for block in (*document.get("buffers", []), *document.get("images", [])):
                    assert "uri" not in block or block["uri"].startswith("data:"), f"External GLB dependency: {path}"
                glbs += 1
        assert glbs, f"Missing GLB for {asset['name']}"
    print(f"Verified {len(models)} model specs, {len(textures)} texture specs, {len(seen)} bundled assets", flush=True)


if __name__ == "__main__":
    check()

"""Exercise old and new source modes through the normal CLI in an isolated repo."""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix="assetgen-sources-") as directory:
        root = Path(directory)
        for name in ("assetgen.py", "assetgen_paths.py", "assetgen_config.py", "assetgen.config.json"):
            shutil.copy2(ROOT / name, root / name)
        for name in ("blender", "schemas", "presets"):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
        (root / "tests").mkdir()
        shutil.copy2(ROOT / "tests/verify_outputs.py", root / "tests/verify_outputs.py")
        for kind in ("models", "textures"):
            (root / "specs" / kind).mkdir(parents=True)
            shutil.copy2(ROOT / "specs" / kind / "barrel_01.json", root / "specs" / kind / "barrel_01.json")
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(bytes([0, 200, 100, 50]))) + chunk(b"IEND", b"")
        (root / "presets/textures/source_probe.png").write_bytes(png)
        model = {"name": "source_probe", "category": "props", "collision": "box",
                 "parts": [{"type": "box", "size": [0.3, 0.3, 0.3], "location": [x, 0, 0.15], "material": tag}
                           for x, tag in ((-0.4, "rgb"), (0, "procedural"), (0.4, "mixed"))]}
        material = {"preset": "flat", "palette": "glass_blue", "ao": 0, "edge": 0,
                    "source_detail": {"image": "source_probe.png", "tile_size": 1, "strength": 0.6}}
        texture = {"asset": "source_probe", "size": 64, "samples": 1, "materials": {
            "rgb": {**material, "source_mode": "image", "opacity": 0.35},
            "procedural": {**material, "source_mode": "procedural"},
            "mixed": {**material, "source_mode": "mixed"},
            "default": {"preset": "flat", "palette": "stone_grey"}}}
        for kind, data in (("models", model), ("textures", texture)):
            (root / "specs" / kind / "source_probe.json").write_text(json.dumps(data), encoding="utf-8")
        env = {**os.environ, "ASSETGEN_OUT": str(root / "out")}
        def run(*args):
            result = subprocess.run([sys.executable, *args], cwd=root, env=env,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
        for name in ("barrel_01", "source_probe"):
            for stage in ("validate", "validate-texture", "model", "texture"):
                run("assetgen.py", stage, name, "--no-copy")
            run("tests/verify_outputs.py", name)
            print(f"CLI and GLB verification passed: {name}", flush=True)
        report = json.loads((root / "out/interiors/source_probe/report_texture.json").read_text())
        assert report["material_settings"]["rgb"]["source_mode"] == "image"
        assert "resolved_layers" not in report["material_settings"]["rgb"]
        assert report["material_settings"]["procedural"]["source_mode"] == "procedural"
        print("Verified legacy bake and explicit RGB/procedural/mixed modes with transparent GLB", flush=True)


if __name__ == "__main__":
    main()

"""Real multi-tag queue bake using isolated specs and outputs, never production files."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import workbench as wb
from verify_outputs import verify


def main():
    original_model, original_texture, _ = wb.asset_paths("barrel_01")
    original_bytes = original_texture.read_bytes()
    with tempfile.TemporaryDirectory(prefix="assetgen-tags-") as directory:
        root = Path(directory)
        model, texture = root / "model.json", root / "texture.json"
        model.write_bytes(original_model.read_bytes())
        texture.write_bytes(original_bytes)
        output = root / "out/interiors/barrel_01"
        with patch.object(wb, "STATE", root / "state"), patch.object(wb, "asset_paths", return_value=(model, texture, output)):
            jobs = wb.Jobs()
            jobs.submit({"assets": ["barrel_01"], "tags": ["wood", "metal"], "patch": {
                "source_mode": "image", "brightness": 0, "contrast": 1,
                "source_detail": {"image": "fine_grained_wood.jpg"}}})
            jobs.pending.join()
            result = jobs.snapshot()[0]
            assert result["status"] == "done", result
            assert len(result["items"]) == 1 and result["items"][0]["tags"] == ["wood", "metal"]
        candidate = wb.read_json(texture)
        report = wb.read_json(output / "report_texture.json")
        before = wb.read_json(original_texture)
        for tag in ("wood", "metal"):
            assert candidate["materials"][tag]["source_mode"] == "image"
            assert report["material_settings"][tag]["source_mode"] == "image"
            assert candidate["materials"][tag]["source_detail"]["tile_size"] == before["materials"][tag]["source_detail"]["tile_size"]
        verify(root / "out", ["barrel_01"])
    assert original_texture.read_bytes() == original_bytes
    print("Verified one real queue bake updating two tags and preserving individual scales", flush=True)


if __name__ == "__main__":
    main()

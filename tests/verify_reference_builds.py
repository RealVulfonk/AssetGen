"""Build and verify the reference assets through the CLI in a clean directory."""

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from verify_outputs import ROOT, output_dir, verify
from assetgen import asset_lock, BLENDER

ASSETS = ("barrel_01", "pillar", "skull_01", "urn", "window_01", "window_02", "window_glass_01")
PACKED_ASSETS = ("barrel_01", "pillar")


def run_cli(stage, name, env):
    return subprocess.run(
        [sys.executable, "assetgen.py", stage, name, "--no-copy"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
    )


def check_rebuild(out, env):
    barrel = output_dir(out, "barrel_01", "props")
    model_report = barrel / "report.json"
    texture_report = barrel / "report_texture.json"
    original_report = model_report.read_bytes()
    original_texture = texture_report.read_bytes()

    with asset_lock(barrel):
        result = run_cli("model", "barrel_01", env)
        assert result.returncode == 1 and "Another build is using" in result.stderr, result.stderr
    result = run_cli("model", "barrel_01", {**env, "BLENDER": str(out / "missing-blender")})
    assert result.returncode == 1, result.stderr
    assert model_report.read_bytes() == original_report
    assert texture_report.read_bytes() == original_texture

    stale = json.loads(original_report)
    stale["model_digest"] = "old input"
    model_report.write_text(json.dumps(stale), encoding="utf-8")
    result = run_cli("texture", "barrel_01", env)
    assert result.returncode == 1 and "Build the current model first" in result.stderr, result.stderr
    assert texture_report.read_bytes() == original_texture

    (barrel / "barrel_01_normal.png").write_bytes(b"stale normal")
    (barrel / "barrel_01_orm.png").write_bytes(b"stale orm")
    result = run_cli("model", "barrel_01", env)
    assert result.returncode == 0, result.stderr
    assert not texture_report.exists()
    assert not (barrel / "barrel_01_albedo.png").exists()
    assert not (barrel / "barrel_01_normal.png").exists()
    assert not (barrel / "barrel_01_orm.png").exists()
    print("Verified build lock, failure recovery, stale input guard and rebake invalidation", flush=True)


def check_uv(out, blender):
    for name in PACKED_ASSETS:
        asset = output_dir(out, name, "props")
        bake = json.loads((asset / "report_texture.json").read_text(encoding="utf-8"))
        assert bake["pack_uv"], f"{name}: atlas was not repacked"
        audit = asset / "uv.json"
        result = subprocess.run(
            [blender, "-b", str(asset / f"{name}_tex.blend"), "--python-exit-code", "1",
             "-P", str(ROOT / "tools" / "inspect_uv.py"), "--", name, str(audit), str(bake["margin"])],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        metrics = json.loads(audit.read_text(encoding="utf-8"))
        padding = metrics["resolutions"][str(bake["size"])]
        assert metrics["atlas_overlap_percent"] == 0, f"{name}: overlapping UVs"
        assert padding["room_for_two_margins"], f"{name}: bake margins touch"
        assert padding["min_atlas_border_px"] >= bake["margin"], f"{name}: bake margin clips atlas edge"
        print(f"Verified {name} UV atlas and bake margins", flush=True)


def main():
    blender = BLENDER
    with TemporaryDirectory(prefix="assetgen-reference-") as directory:
        out = Path(directory)
        env = {**os.environ, "ASSETGEN_OUT": str(out)}
        for name in ASSETS:
            stages = ["model"]
            if (ROOT / "specs" / "textures" / f"{name}.json").is_file():
                stages.append("texture")
            for stage in stages:
                result = run_cli(stage, name, env)
                if result.returncode:
                    raise SystemExit(result.stderr or result.stdout)
                print(f"Built {name}/{stage}", flush=True)
        verify(out, ASSETS)
        check_uv(out, blender)
        barrel = output_dir(out, "barrel_01", "props") / "barrel_01_tex.blend"
        subprocess.run(
            [blender, "-b", str(barrel), "--python-exit-code", "1",
             "-P", str(ROOT / "tests" / "verify_barrel_caps.py")],
            cwd=ROOT, check=True,
        )
        skull = output_dir(out, "skull_01", "remains") / "skull_01.blend"
        subprocess.run(
            [blender, "-b", "--factory-startup", "--python-exit-code", "1",
             "-P", str(ROOT / "tests" / "verify_cutouts.py"), "--", str(skull)],
            cwd=ROOT, check=True,
        )
        check_rebuild(out, env)


if __name__ == "__main__":
    main()

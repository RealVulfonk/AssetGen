"""Snapshot built GLBs/previews into the tracked, portable library for fresh clones."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import assetgen as ag


def export():
    library = ROOT / "library"
    library.mkdir(exist_ok=True)
    assets = []
    for model in sorted((ROOT / "specs/models").glob("*.json")):
        spec = json.loads(model.read_text(encoding="utf-8"))
        name = model.stem
        output = ag.output_dir(ag.OUT, name, spec.get("category"))
        destination = ag.output_dir(library, name, spec.get("category"))
        if not (output / f"{name}.glb").is_file():
            # Keep a previously published asset when this machine has not built it.
            if not (destination / f"{name}.glb").is_file():
                continue
        else:
            with ag.asset_lock(output):
                destination.mkdir(parents=True, exist_ok=True)
                filenames = [f"{name}.glb", f"{name}_godot.glb", f"{name}_albedo.png",
                             f"{name}_normal.png", f"{name}_orm.png",
                             "preview_front.png", "preview_side.png", "preview_iso.png", "preview_top.png",
                             "preview_lighting.png", "report.json", "report_texture.json"]
                for filename in filenames:
                    source = output / filename
                    target = destination / filename
                    if not source.is_file():
                        # Remove only known obsolete exported artifacts; never local builds.
                        target.unlink(missing_ok=True)
                        continue
                    if filename.startswith("report"):
                        data = json.loads(source.read_text(encoding="utf-8"))
                        for key in ("blend", "glb", "godot_glb", "texture", "normal_texture", "orm_texture",
                                    "lighting_preview"):
                            if data.get(key):
                                data[key] = Path(data[key]).name
                        data["previews"] = [Path(path).name for path in data.get("previews", [])]
                        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
                    else:
                        shutil.copy2(source, target)
        files = [{"path": path.relative_to(library).as_posix(), "bytes": path.stat().st_size,
                  "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                 for path in sorted(destination.iterdir()) if path.is_file()]
        assets.append({"name": name, "category": spec.get("category"), "files": files})
    manifest = {"format": 1, "assets": assets}
    (library / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Exported {len(assets)} built assets; {sum(f['bytes'] for a in assets for f in a['files']) / 1048576:.1f} MiB", flush=True)


if __name__ == "__main__":
    export()

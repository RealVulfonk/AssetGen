#!/usr/bin/env python3
"""Command-line entry point for the JSON-driven asset generator.

python assetgen.py new <template> <name>
python assetgen.py validate <name>
python assetgen.py validate-texture <name>
python assetgen.py model <name>
python assetgen.py texture <name>
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from assetgen_paths import asset_group, output_dir
from assetgen_config import load_config, find_blender

ROOT = Path(__file__).resolve().parent
CFG = load_config(ROOT)
BLENDER = find_blender(CFG)
OUT = ROOT / os.environ.get("ASSETGEN_OUT", CFG.get("out", "out"))


class AssetGenError(RuntimeError):
    pass


def validate(path, schema_name):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AssetGenError(f"Spec not found: {path}") from error
    except json.JSONDecodeError as error:
        raise AssetGenError(f"Invalid JSON in {path}: {error}") from error

    try:
        import jsonschema
    except ImportError as error:
        raise AssetGenError("Install the validator first: python -m pip install -r requirements.txt") from error

    schema = json.loads((ROOT / "schemas" / schema_name).read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))
    if errors:
        messages = []
        for error in errors:
            location = ".".join(str(item) for item in error.absolute_path) or "<root>"
            messages.append(f"  {location}: {error.message}")
        raise AssetGenError(f"Schema validation failed for {path}:\n" + "\n".join(messages))
    return data


def load_texture_spec(name):
    path = ROOT / "specs" / "textures" / f"{name}.json"
    data = validate(path, "texture.schema.json")
    if data["asset"] != name:
        raise AssetGenError(f"Texture asset {data['asset']!r} must match file name {name!r}")
    palettes = json.loads((ROOT / "presets" / "palettes.json").read_text(encoding="utf-8"))
    for tag, material in data["materials"].items():
        palette = material["palette"]
        if isinstance(palette, str) and palette not in palettes:
            raise AssetGenError(f"{path}: materials.{tag}.palette: unknown palette {palette!r}")
        detail = material.get("source_detail")
        if detail and not (ROOT / "presets" / "textures" / detail["image"]).is_file():
            raise AssetGenError(f"{path}: materials.{tag}.source_detail.image: missing {detail['image']!r}")
        for channel in ("normal", "roughness"):
            filename = material.get("pbr_detail", {}).get(channel)
            if filename and not (ROOT / "presets" / "textures" / filename).is_file():
                raise AssetGenError(f"{path}: materials.{tag}.pbr_detail.{channel}: missing {filename!r}")
    return data


def run_blender(script, args, blend=None):
    blender = Path(BLENDER)
    if not blender.is_file():
        raise AssetGenError(
            f"Blender executable not found: {blender}. Set assetgen.local.json or the BLENDER environment variable."
        )
    command = [str(blender), "-b"]
    command += [str(blend)] if blend else ["--factory-startup"]
    command += ["--python-exit-code", "1", "-P", str(ROOT / "blender" / script), "--", *map(str, args)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = result.stdout + result.stderr
    if result.returncode != 0 or "Traceback" in log:
        raise AssetGenError("Blender failed. Last log lines:\n" + "\n".join(log.splitlines()[-40:]))


def copy_to_godot(name, category, report):
    configured = CFG.get("godot_assets", "").strip()
    if not configured:
        print("Godot copy: disabled (set godot_assets in assetgen.config.json to enable)")
        return
    destination = (ROOT / configured / category / name).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for key in ("glb", "godot_glb", "texture", "normal_texture", "orm_texture"):
        if report.get(key):
            source = Path(report[key])
            shutil.copy2(source, destination / source.name)
            copied.append(source.name)
    print(f"Godot copy: {destination} ({', '.join(sorted(copied))})")


def read_report(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AssetGenError(f"Blender exited without creating the expected report: {path}") from error


@contextmanager
def asset_lock(output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".build.lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt

                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise AssetGenError(f"Another build is using {output}") from error
        yield


def render_lighting_preview(glb, destination):
    configured = os.environ.get("GODOT_BIN")
    executable = Path(configured) if configured else None
    if executable is None:
        on_path = shutil.which("godot")
        executable = Path(on_path) if on_path else None
    if executable is None or not executable.is_file():
        raise AssetGenError("Godot executable not found. Set GODOT_BIN to render the lighting preview.")
    executable = executable.resolve()
    if os.name == "nt":
        console = executable.with_name(executable.stem + "_console.exe")
        if console.is_file():
            executable = console

    project = destination.parent / "_lighting_project"
    shutil.copytree(ROOT / "godot" / "lighting_preview", project)
    command = [
        str(executable), "--path", str(project), "--script", "res://preview.gd",
        "--", str(glb), str(destination),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except subprocess.TimeoutExpired as error:
        raise AssetGenError("Godot timed out while rendering the lighting preview") from error
    if result.returncode != 0 or not destination.is_file():
        log = result.stdout + result.stderr
        raise AssetGenError("Godot failed to render the lighting preview:\n" + "\n".join(log.splitlines()[-20:]))


def build_stage(stage, spec, output, *, blend=None, model_digest=None, lighting_preview=False):
    report_name = "report.json" if stage == "model" else "report_texture.json"
    script = "build_model.py" if stage == "model" else "bake_texture.py"
    with TemporaryDirectory(prefix=f".{stage}-", dir=output) as directory:
        staging = Path(directory)
        spec_bytes = spec.read_bytes()
        snapshot = staging / spec.name
        snapshot.write_bytes(spec_bytes)
        if stage == "model":
            model_digest = hashlib.sha256(spec_bytes).hexdigest()
        run_blender(script, [snapshot, staging], blend=blend)
        report = read_report(staging / report_name)
        paths = {
            key: Path(report[key])
            for key in ("blend", "glb", "godot_glb", "texture", "normal_texture", "orm_texture")
            if report.get(key)
        }
        previews = [Path(path) for path in report["previews"]]
        files = [*paths.values(), *previews]
        for source in files:
            if not source.is_file():
                raise AssetGenError(f"Blender did not produce {source.name}")
        if lighting_preview:
            preview = staging / "preview_lighting.png"
            render_lighting_preview(paths["glb"], preview)
            paths["lighting_preview"] = preview
            files.append(preview)

        # Reports certify complete stages. Publish them after all stage files.
        reports = [output / report_name]
        if stage == "model":
            reports.append(output / "report_texture.json")
        for old_report in reports:
            old_report.unlink(missing_ok=True)
        if not lighting_preview:
            (output / "preview_lighting.png").unlink(missing_ok=True)
        if stage == "model":
            asset = report["name"]
            for filename in (f"{asset}_albedo.png", f"{asset}_normal.png", f"{asset}_orm.png",
                             f"{asset}_tex.blend"):
                (output / filename).unlink(missing_ok=True)
            if not report.get("godot_glb"):
                (output / f"{asset}_godot.glb").unlink(missing_ok=True)
        else:
            asset = report["name"]
            for key, filename in (("normal_texture", f"{asset}_normal.png"),
                                  ("orm_texture", f"{asset}_orm.png")):
                if key not in paths:
                    (output / filename).unlink(missing_ok=True)
        for source in files:
            source.replace(output / source.name)
        for key, source in paths.items():
            report[key] = str((output / source.name).resolve())
        report["previews"] = [str((output / source.name).resolve()) for source in previews]
        if model_digest is not None:
            report["model_digest"] = model_digest
        completed = staging / report_name
        completed.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        completed.replace(output / report_name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cmd", choices=["new", "validate", "validate-texture", "model", "texture"])
    parser.add_argument("a", help="template for 'new', asset name otherwise")
    parser.add_argument("b", nargs="?", help="new asset name for 'new'")
    parser.add_argument("--no-copy", action="store_true", help="do not copy generated files into Godot")
    parser.add_argument("--lighting-preview", action="store_true", help="render the GLB in two lighting setups in Godot")
    args = parser.parse_args()
    if args.lighting_preview and args.cmd not in ("model", "texture"):
        parser.error("--lighting-preview applies to model and texture")

    try:
        if args.cmd == "new":
            if not args.b:
                raise AssetGenError("Usage: python assetgen.py new <template> <name>")
            template = ROOT / "templates" / f"{args.a}.json"
            destination = ROOT / "specs/models" / f"{args.b}.json"
            data = validate(template, "model.schema.json")
            if destination.exists():
                raise AssetGenError(f"Refusing to overwrite existing spec: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            data["name"] = args.b
            serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            destination.write_text(serialized, encoding="utf-8")
            validate(destination, "model.schema.json")
            print(f"Created {destination}")
            return

        if args.b:
            raise AssetGenError(f"Command {args.cmd!r} accepts exactly one asset name")
        model_spec = ROOT / "specs/models" / f"{args.a}.json"
        if args.cmd == "validate-texture":
            load_texture_spec(args.a)
            print(f"OK: {ROOT / 'specs/textures' / f'{args.a}.json'}")
            return
        data = validate(model_spec, "model.schema.json")
        if data["name"] != args.a:
            raise AssetGenError(f"Spec name {data['name']!r} must match file name {args.a!r}")
        if args.cmd == "validate":
            print(f"OK: {model_spec}")
            return
        if args.cmd == "texture":
            load_texture_spec(args.a)
        output = output_dir(OUT, args.a, data.get("category"))
        with asset_lock(output):
            if args.cmd == "model":
                report = build_stage("model", model_spec, output, lighting_preview=args.lighting_preview)
            else:
                texture_spec = ROOT / "specs/textures" / f"{args.a}.json"
                blend = output / f"{args.a}.blend"
                model_report = output / "report.json"
                digest = hashlib.sha256(model_spec.read_bytes()).hexdigest()
                if (
                    not blend.is_file()
                    or not model_report.is_file()
                    or read_report(model_report).get("model_digest") != digest
                ):
                    raise AssetGenError(f"Build the current model first: python assetgen.py model {args.a}")
                report = build_stage(
                    "texture", texture_spec, output, blend=blend, model_digest=digest,
                    lighting_preview=args.lighting_preview,
                )
            print(json.dumps(report, indent=2, ensure_ascii=False))
            if not args.no_copy:
                copy_to_godot(args.a, data.get("category", "props"), report)
    except (AssetGenError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

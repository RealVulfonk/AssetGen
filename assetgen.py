#!/usr/bin/env python3
"""Command-line entry point for the JSON-driven asset generator.

python assetgen.py new <template> <name>
python assetgen.py validate <name>
python assetgen.py validate-texture <name>
python assetgen.py model <name>
python assetgen.py texture <name>
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from assetgen_paths import asset_group, output_dir

ROOT = Path(__file__).resolve().parent
CFG = json.loads((ROOT / "assetgen.config.json").read_text(encoding="utf-8"))
BLENDER = os.environ.get("BLENDER", CFG["blender"])
OUT = ROOT / CFG.get("out", "out")


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
    return data


def run_blender(script, args, blend=None):
    blender = Path(BLENDER)
    if not blender.is_file():
        raise AssetGenError(
            f"Blender executable not found: {blender}. Set assetgen.config.json or the BLENDER environment variable."
        )
    command = [str(blender), "-b"]
    command += [str(blend)] if blend else ["--factory-startup"]
    command += ["--python-exit-code", "1", "-P", str(ROOT / "blender" / script), "--", *map(str, args)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = result.stdout + result.stderr
    if result.returncode != 0 or "Traceback" in log:
        raise AssetGenError("Blender failed. Last log lines:\n" + "\n".join(log.splitlines()[-40:]))


def copy_to_godot(name, category):
    configured = CFG.get("godot_assets", "").strip()
    if not configured:
        print("Godot copy: disabled (set godot_assets in assetgen.config.json to enable)")
        return
    destination = (ROOT / configured / category / name).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in output_dir(OUT, name, category).iterdir():
        if source.suffix.lower() in (".glb", ".png") and not source.name.startswith("preview_"):
            shutil.copy2(source, destination / source.name)
            copied.append(source.name)
    print(f"Godot copy: {destination} ({', '.join(sorted(copied))})")


def read_report(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise AssetGenError(f"Blender exited without creating the expected report: {path}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cmd", choices=["new", "validate", "validate-texture", "model", "texture"])
    parser.add_argument("a", help="template for 'new', asset name otherwise")
    parser.add_argument("b", nargs="?", help="new asset name for 'new'")
    args = parser.parse_args()

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
        if args.cmd in ("validate", "model"):
            data = validate(model_spec, "model.schema.json")
            if data["name"] != args.a:
                raise AssetGenError(f"Spec name {data['name']!r} must match file name {args.a!r}")
            if args.cmd == "validate":
                print(f"OK: {model_spec}")
                return
            output = output_dir(OUT, args.a, data.get("category"))
            output.mkdir(parents=True, exist_ok=True)
            run_blender("build_model.py", [model_spec, output])
            report = read_report(output / "report.json")
        else:
            texture_spec = ROOT / "specs/textures" / f"{args.a}.json"
            load_texture_spec(args.a)
            data = validate(model_spec, "model.schema.json")
            output = output_dir(OUT, args.a, data.get("category"))
            blend = output / f"{args.a}.blend"
            if not blend.is_file():
                raise AssetGenError(f"Build the model first: python assetgen.py model {args.a}")
            run_blender("bake_texture.py", [texture_spec, output], blend=blend)
            report = read_report(output / "report_texture.json")

        print(json.dumps(report, indent=2, ensure_ascii=False))
        copy_to_godot(args.a, data.get("category", "props"))
    except AssetGenError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

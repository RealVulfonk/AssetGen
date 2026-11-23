#!/usr/bin/env python3
"""Split a horizontal Base Color / Normal / Roughness sheet into three PNGs."""

import argparse
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, UnidentifiedImageError

NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
PANELS = ("base_color", "normal", "roughness")


@contextmanager
def publication_lock(output, name):
    """Serialize the existence check and publication for one output prefix."""
    path = output / f".{name}.split.lock"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise ValueError(f"another split is publishing {name}; stale lock can be removed: {path}") from error
    os.close(descriptor)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def split_sheet(source, output, name, force=False):
    if not NAME.fullmatch(name):
        raise ValueError("name must be safe snake_case, for example wall_stone")
    if not output.is_dir():
        raise ValueError(f"output directory does not exist: {output}")

    try:
        with Image.open(source) as image:
            image.load()
            rgb = image.convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError(f"cannot read image {source}: {error}") from error

    width, height = rgb.size
    if width == 0 or height == 0 or width % 3:
        raise ValueError(f"image width must be positive and divisible by 3, got {width}x{height}")
    panel_width = width // 3
    destinations = {kind: output / f"{name}_{kind}.png" for kind in PANELS}

    with publication_lock(output, name):
        existing = [path for path in destinations.values() if path.exists()]
        if existing and not force:
            raise ValueError("refusing to overwrite existing files without --force: "
                             + ", ".join(str(path) for path in existing))

        panels = {
            kind: rgb.crop((index * panel_width, 0, (index + 1) * panel_width, height))
            for index, kind in enumerate(PANELS)
        }
        with tempfile.TemporaryDirectory(prefix=".split-pbr-", dir=output) as directory:
            staging = Path(directory)
            for kind, panel in panels.items():
                panel.save(staging / destinations[kind].name, format="PNG")
            for kind, path in destinations.items():
                if force and path.is_file():
                    shutil.copy2(path, staging / f"backup_{path.name}")

            published = []
            try:
                for path in destinations.values():
                    os.replace(staging / path.name, path)
                    published.append(path)
            except OSError:
                for path in reversed(published):
                    backup = staging / f"backup_{path.name}"
                    if backup.is_file():
                        os.replace(backup, path)
                    else:
                        path.unlink(missing_ok=True)
                raise

    for path in destinations.values():
        print(f"{path} ({panel_width}x{height})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="horizontal three-panel image")
    parser.add_argument("--out", type=Path, required=True, help="existing output directory")
    parser.add_argument("--name", required=True, help="safe snake_case output prefix")
    parser.add_argument("--force", action="store_true", help="replace all three existing outputs")
    args = parser.parse_args()
    try:
        split_sheet(args.source, args.out, args.name, args.force)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

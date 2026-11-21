"""Portable config shared by the CLI and output-directory tools."""
import json
import os
import shutil
from pathlib import Path


def load_config(root):
    config = json.loads((root / "assetgen.config.json").read_text(encoding="utf-8"))
    local = root / "assetgen.local.json"
    if local.is_file():
        config.update(json.loads(local.read_text(encoding="utf-8")))
    return config


def find_blender(config):
    configured = os.environ.get("BLENDER") or config.get("blender", "blender")
    expanded = os.path.expandvars(os.path.expanduser(configured))
    found = shutil.which(expanded)
    if found:
        return found
    if configured in ("blender", "blender.exe") and os.name == "nt":
        installations = sorted((Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Blender Foundation").glob("Blender */blender.exe"))
        if installations:
            return str(installations[-1])
    return expanded

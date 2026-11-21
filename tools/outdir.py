#!/usr/bin/env python3
"""Print the resolved output directory for an asset name.

    python tools/outdir.py conifer_01     -> out/exteriors/conifer_01

Lets shell scripts (build_flora.ps1) find generated files without duplicating
the category-to-group mapping from assetgen_paths.py.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assetgen_paths import output_dir
from assetgen_config import load_config
import os

CFG = load_config(ROOT)
OUT = ROOT / os.environ.get("ASSETGEN_OUT", CFG.get("out", "out"))

for name in sys.argv[1:]:
    spec = json.loads((ROOT / "specs" / "models" / f"{name}.json").read_text(encoding="utf-8"))
    print(output_dir(OUT, name, spec.get("category")).as_posix())

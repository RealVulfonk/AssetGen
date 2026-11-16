#!/usr/bin/env python3
"""Move already-built assets from flat out/<name> into out/<group>/<name>.

    python tools/regroup_out.py --dry-run
    python tools/regroup_out.py

Safe to re-run: assets already in their group are skipped, and unknown
directories (out/verification, out/*.log, out/*.png) are left alone.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from assetgen_paths import GROUPS, asset_group

CFG = json.loads((ROOT / "assetgen.config.json").read_text(encoding="utf-8"))
OUT = ROOT / CFG.get("out", "out")
MODELS = ROOT / "specs" / "models"


def category_of(name):
    spec = MODELS / f"{name}.json"
    if not spec.is_file():
        return None
    return json.loads(spec.read_text(encoding="utf-8")).get("category")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    moves, skipped, unknown = [], [], []
    for entry in sorted(OUT.iterdir()):
        if not entry.is_dir() or entry.name in GROUPS:
            continue
        category = category_of(entry.name)
        if category is None:
            unknown.append(entry.name)
            continue
        group = asset_group(category)
        destination = OUT / group / entry.name
        if destination.exists():
            skipped.append((entry.name, group))
            continue
        moves.append((entry, destination, group, category))

    for entry, destination, group, category in moves:
        print(f"{'would move' if args.dry_run else 'move'} "
              f"{entry.name:20s} {category:18s} -> {group}/")
        if not args.dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(entry), str(destination))

    print(f"\n{'planned' if args.dry_run else 'moved'} {len(moves)} assets")
    if skipped:
        print(f"already in place: {len(skipped)}")
    if unknown:
        print(f"left untouched (no spec): {', '.join(unknown)}")


if __name__ == "__main__":
    main()

"""Bake one asset twice and compare pixels and normalized reports inside Blender."""

import hashlib
import importlib.util
import json
import os
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1 :]
ROOT = os.path.abspath(argv[0])
NAME = argv[1] if len(argv) > 1 else "pillar"
BASE_BLEND = os.path.join(ROOT, "out", NAME, f"{NAME}.blend")
SPEC_PATH = os.path.join(ROOT, "specs", "textures", f"{NAME}.json")
MODULE_PATH = os.path.join(ROOT, "blender", "bake_texture.py")

spec = importlib.util.spec_from_file_location("assetgen_bake_texture_determinism", MODULE_PATH)
texture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(texture)

outputs = []
for run in ("run_a", "run_b"):
    output = os.path.join(ROOT, "out", "verification", NAME + "_determinism", run)
    bpy.ops.wm.open_mainfile(filepath=BASE_BLEND)
    sys.argv = ["blender", "--", SPEC_PATH, output]
    texture.main()
    outputs.append(output)


def read_pixels(path):
    image = bpy.data.images.load(path, check_existing=False)
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    bpy.data.images.remove(image)
    return pixels


pixel_hashes = []
reports = []
for output in outputs:
    png = os.path.join(output, f"{NAME}_albedo.png")
    pixels = read_pixels(png)
    pixel_hashes.append(hashlib.sha256(pixels.tobytes()).hexdigest())
    with open(os.path.join(output, "report_texture.json"), encoding="utf-8") as handle:
        report = json.load(handle)
    for key in ("texture", "blend", "glb", "godot_glb", "previews"):
        report.pop(key, None)
    reports.append(report)

assert pixel_hashes[0] == pixel_hashes[1], f"{NAME}: repeated bake produced different pixels"
assert reports[0] == reports[1], f"{NAME}: repeated bake produced different settings"
print(f"Verified deterministic bake for {NAME}: {pixel_hashes[0]}")

"""Verify saved PNG colors against their texture palettes inside Blender."""

import json
import os
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1 :]
ROOT = os.path.abspath(argv[0])
names = argv[1:]


def hex2rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


with open(os.path.join(ROOT, "presets", "palettes.json"), encoding="utf-8") as handle:
    palettes = json.load(handle)

for name in names:
    with open(os.path.join(ROOT, "specs", "textures", f"{name}.json"), encoding="utf-8") as handle:
        spec = json.load(handle)
    colors = []
    for config in spec["materials"].values():
        value = config["palette"]
        colors.extend(palettes[value] if isinstance(value, str) else value)
    expected = np.array([hex2rgb(value) for value in set(colors)], dtype=np.float32)

    path = os.path.join(ROOT, "out", name, f"{name}_albedo.png")
    image = bpy.data.images.load(path, check_existing=False)
    width, height = image.size
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(-1, 4)[:, :3]
    distances = np.sqrt(((pixels[:, None, :] - expected[None]) ** 2).sum(-1))
    max_error = float(distances.min(1).max())
    unique_colors = len(np.unique(np.round(pixels * 255), axis=0))
    print(f"{name}: {unique_colors} colors, maximum palette error {max_error:.6f}")
    assert max_error < 0.011, f"{name}: pixels outside the configured palette"
    bpy.data.images.remove(image)

print(f"Verified palette quantization for {len(names)} textures")

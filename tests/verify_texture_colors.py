"""Verify generated PNGs for quantized and soft texture modes inside Blender."""

import json
import os
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1 :]
ROOT = os.path.abspath(argv[0])
sys.path.insert(0, ROOT)
from assetgen_paths import output_dir
names = argv[1:]
if not names:
    names = sorted(
        os.path.splitext(filename)[0]
        for filename in os.listdir(os.path.join(ROOT, "specs", "textures"))
        if filename.endswith(".json")
    )


def hex2rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def is_non_flat(config):
    if "layers" in config:
        return any(layer["type"] != "constant" for layer in config["layers"])
    return config.get("preset", "noise") != "flat"


with open(os.path.join(ROOT, "presets", "palettes.json"), encoding="utf-8") as handle:
    palettes = json.load(handle)

skipped = []
for name in names:
    with open(os.path.join(ROOT, "specs", "textures", f"{name}.json"), encoding="utf-8") as handle:
        spec = json.load(handle)
    with open(os.path.join(ROOT, "specs", "models", f"{name}.json"), encoding="utf-8") as handle:
        category = json.load(handle).get("category")
    output = str(output_dir(Path(ROOT) / "out", name, category))
    colors = []
    palette_stop_count = 0
    for config in spec["materials"].values():
        value = config["palette"]
        resolved = palettes[value] if isinstance(value, str) else value
        colors.extend(resolved)
        palette_stop_count += len(resolved)
    expected = np.array([hex2rgb(value) for value in set(colors)], dtype=np.float32)

    path = os.path.join(output, f"{name}_albedo.png")
    if not os.path.isfile(path):
        # Specs are committed; bakes are not, so an unbaked asset is skipped.
        skipped.append(name)
        continue
    image = bpy.data.images.load(path, check_existing=False)
    width, height = image.size
    assert width == spec.get("size", 128) and height == width, f"{name}: unexpected texture dimensions"
    pixels = np.empty(width * height * 4, dtype=np.float32)
    image.pixels.foreach_get(pixels)
    rgba = pixels.reshape(-1, 4)
    assert np.isfinite(rgba).all(), f"{name}: non-finite image values"
    assert np.allclose(rgba[:, 3], 1.0), f"{name}: albedo alpha is not opaque"
    rgb = rgba[:, :3]
    unique_colors = len(np.unique(np.round(rgb * 255), axis=0))

    if spec.get("quantize", False):
        distances = np.sqrt(((rgb[:, None, :] - expected[None]) ** 2).sum(-1))
        max_error = float(distances.min(1).max())
        assert max_error < 0.011, f"{name}: pixels outside the configured palette"
        print(f"{name}: quantized, {unique_colors} colors, maximum palette error {max_error:.6f}")
    else:
        assert unique_colors > 1, f"{name}: soft texture is unexpectedly uniform"
        if any(is_non_flat(config) for config in spec["materials"].values()):
            assert unique_colors > palette_stop_count, (
                f"{name}: expected intermediate soft colors, got {unique_colors} colors "
                f"for {palette_stop_count} palette stops"
            )
        print(f"{name}: soft, {unique_colors} colors")

    report_path = os.path.join(output, "report_texture.json")
    with open(report_path, encoding="utf-8") as handle:
        report = json.load(handle)
    if "unique_colors" in report:
        assert report["unique_colors"] == unique_colors, f"{name}: report color count differs from PNG"
    bpy.data.images.remove(image)

print(f"Verified {len(names) - len(skipped)} texture images")
if skipped:
    print(f"Skipped {len(skipped)} unbaked: {', '.join(skipped[:8])}"
          + (" ..." if len(skipped) > 8 else ""))

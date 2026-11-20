"""Measure how solid an asset silhouette is, from its preview PNGs.

    blender -b --factory-startup -P tools/silhouette_stats.py -- <root> <png> [<png> ...]

Two numbers per image, over the tight bounding box of the opaque pixels:

- ``solidity``   — доля заполненных пикселей. Низкая значит «сквозь модель
  видно фон», то есть крона собрана из отдельных плоских лопастей.
- ``split_rows`` — доля строк, разорванных на 2+ отрезка. Высокая значит
  «решето»: даже там, где модель есть, она не образует цельного силуэта.

Для плотных пропов (бочка, колонна) solidity 60–90% и split_rows около нуля.
Крона дерева ниже ~40% при split_rows выше ~20% читается как решето.
"""

import os
import sys

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.path.abspath(argv[0])
PATHS = argv[1:]

for path in PATHS:
    image = bpy.data.images.load(path, check_existing=False)
    w, h = image.size
    px = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(px)
    alpha = px.reshape(h, w, 4)[:, :, 3]
    ys, xs = np.nonzero(alpha > 0.5)
    if len(xs) == 0:
        print(f"MEASURE {os.path.basename(path)} EMPTY")
        continue
    box = alpha[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    solidity = float((box > 0.5).mean())
    # Horizontal scanline gaps: how many rows are split into 2+ runs.
    split = 0
    for row in (box > 0.5):
        runs = np.count_nonzero(np.diff(row.astype(np.int8)) == 1)
        if runs >= 2:
            split += 1
    print(f"MEASURE {os.path.basename(path):28s} solidity {solidity:5.1%}  "
          f"split_rows {split / box.shape[0]:5.1%}")
    bpy.data.images.remove(image)

"""Render one orthographic view per asset into out/sheet_<name>.png.

blender -b --factory-startup -P tools/render_sheet.py -- <root> <name> [<name> ...]
"""

import json
import math
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = os.path.abspath(argv[0])
NAMES = argv[1:]
sys.path.insert(0, ROOT)
from assetgen_paths import output_dir

# factory-startup leaves a default cube in the scene; it would be rendered too.
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "MATERIAL"
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = False
scene.render.resolution_x = 420
scene.render.resolution_y = 560
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "Standard"
scene.world = bpy.data.worlds.new("sheet_world")
scene.world.color = (0.16, 0.17, 0.20)

camera_data = bpy.data.cameras.new("sheet_cam")
camera_data.type = "ORTHO"
camera = bpy.data.objects.new("sheet_cam", camera_data)
scene.collection.objects.link(camera)
scene.camera = camera

for name in NAMES:
    with open(os.path.join(ROOT, "specs", "models", f"{name}.json"), encoding="utf-8") as handle:
        category = json.load(handle).get("category")
    folder = output_dir(ROOT, name, category)
    blend = os.path.join(folder, f"{name}.blend")
    with bpy.data.libraries.load(blend) as (source, target):
        # A collision mesh is stored as "<name>-colonly" and would match the
        # prefix, so exclude the suffixes Godot uses for collision-only nodes.
        target.objects = [item for item in source.objects
                          if item == name
                          or (item.startswith(name + "_") and not item.endswith(("-colonly", "-convcolonly")))]
    obj = next(item for item in target.objects if not item.name.endswith(("-colonly", "-convcolonly")))
    scene.collection.objects.link(obj)
    # The blend stores the mesh already shifted by its pivot, so the bbox is local.
    low = [min(vertex.co[i] for vertex in obj.data.vertices) for i in range(3)]
    high = [max(vertex.co[i] for vertex in obj.data.vertices) for i in range(3)]
    center = [(low[i] + high[i]) / 2 for i in range(3)]
    span = max(high[i] - low[i] for i in range(3)) * 1.18
    camera_data.ortho_scale = span
    camera.location = (center[0] + span * 0.5, center[1] - span * 0.9, center[2] + span * 0.28)
    camera.rotation_euler = (math.radians(72), 0.0, math.radians(30))
    scene.render.filepath = os.path.join(ROOT, "out", f"sheet_{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(obj, do_unlink=True)
    print(f"SHEET {name} span {span:.2f}")

"""Check exported door GLBs: solid seams, clear frame, matching parts and hinge.

blender -b --factory-startup --python-exit-code 1 -P tests/verify_door_assembly.py -- <root>
"""

import json
import math
import sys
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(sys.argv[sys.argv.index("--") + 1])
OUT = ROOT / "out/interiors"
PIVOT = Vector((-.43, -.065, 0))


def load(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(OUT / name / (name + ".glb")))
    vertices, faces, wood_faces = [], [], []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        offset = len(vertices)
        vertices.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
        for poly in obj.data.polygons:
            face = tuple(offset + i for i in poly.vertices)
            faces.append(face)
            if obj.data.materials[poly.material_index].name == "wood":
                wood_faces.append(face)
    return vertices, faces, wood_faces


def tree(data, wood=False, transform=None):
    vertices, faces, wood_faces = data
    return BVHTree.FromPolygons(
        [transform(v) if transform else v for v in vertices],
        wood_faces if wood else faces,
    )


combined = load("door_arch_heavy_01")
frame = load("door_arch_heavy_frame_01")
leaf = load("door_arch_heavy_leaf_01")
frame_tree, leaf_tree = tree(frame), tree(leaf)
checks = 0
# Densely cover every joint and the full rectangular lower region, both ways.
for x in [-.28, -.14, 0, .14, .28] + [i / 1000 for i in range(-410, 411, 10)]:
    for z in [i / 100 for i in range(2, 143)]:
        for y, direction in [(-1, (0, 1, 0)), (1, (0, -1, 0))]:
            origin = Vector((x, y, z)) - PIVOT
            assert leaf_tree.ray_cast(origin, Vector(direction), 2)[0] is not None, (x, z)
            checks += 1
# The opening must remain empty, in both visual and static collision geometry.
for name in ["door_arch_heavy_frame_01.glb", "door_arch_heavy_frame_01_godot.glb"]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(OUT / "door_arch_heavy_frame_01" / name))
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        bvh = BVHTree.FromPolygons(
            [obj.matrix_world @ v.co for v in obj.data.vertices],
            [tuple(p.vertices) for p in obj.data.polygons],
        )
        for x in [-.40, -.2, 0, .2, .40]:
            for z in [.02, .5, 1, 1.4]:
                assert bvh.ray_cast(Vector((x, -1, z)), Vector((0, 1, 0)), 2)[0] is None


def face_positions(data, offset=Vector((0, 0, 0))):
    vertices, faces, _ = data
    return Counter(tuple(sorted(tuple(round(c, 5) for c in vertices[i] + offset)
                                for i in face)) for face in faces)


assert face_positions(combined) == face_positions(frame) + face_positions(leaf, PIVOT), "Split parts differ from assembly"
for angle in [0, 5, 15, 30, 45, 60, 90]:
    rotation = Matrix.Rotation(math.radians(-angle), 3, "Z")
    moving_wood = tree(leaf, wood=True, transform=lambda v: rotation @ v + PIVOT)
    assert not moving_wood.overlap(frame_tree), f"Wood intersects frame at {angle} degrees"

result = dict(status="OK", seam_rays=checks, split_geometry_matches=True,
              frame_and_collision_open=True, opening_angles_degrees=[0, 5, 15, 30, 45, 60, 90],
              leaf_position_blender=list(PIVOT), leaf_position_godot=[-.43, 0, .065])
(OUT / "door_arch_heavy_01/assembly_verification.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))

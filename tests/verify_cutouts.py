"""Check real recesses against render geometry inside Blender."""

import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "blender"))
from build_model import build_part


def check_fixture(height, center, through):
    part = {
        "type": "box",
        "size": [1, 1, 1],
        "cutouts": [{"type": "cylinder", "radius": 0.2, "height": height, "location": [0, 0, center]}],
    }
    geometry = build_part(part, random.Random(1), "fixture")
    try:
        tree = BVHTree.FromBMesh(geometry)
        center_hit, *_ = tree.ray_cast(Vector((0, 0, 1)), Vector((0, 0, -1)))
        rim, *_ = tree.ray_cast(Vector((0.3, 0, 1)), Vector((0, 0, -1)))
        assert rim is not None and abs(rim.z - 0.5) < 1e-5, "fixture lost its exterior"
        if through:
            assert center_hit is None, f"through hole stopped at {center_hit}"
        else:
            assert center_hit is not None and abs(center_hit.z - 0.25) < 1e-5, center_hit
    finally:
        geometry.free()


bpy.ops.wm.read_factory_settings(use_empty=True)
check_fixture(height=0.5, center=0.5, through=False)
check_fixture(height=1.5, center=0, through=True)
invalid = {"type": "box", "size": [1, 1, 1], "cutouts": [{"type": "box", "size": [0.1] * 3, "location": [2, 0, 0]}]}
try:
    build_part(invalid, random.Random(1), "fixture")
except ValueError as error:
    assert "fixture.cutouts[0] does not remove volume" in str(error), error
else:
    raise AssertionError("A cutter without intersection was accepted")
assert not bpy.data.objects, "temporary boolean objects survived"

bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
skull = bpy.data.objects["skull_01"]
assert [material.name for material in skull.data.materials] == ["bone"]
direction = Vector((0, 1, 0))
rim_hit, rim, _, _ = skull.ray_cast(Vector((0, -1, 0.119)), direction)
assert rim_hit, "the bridge between the eye sockets is missing"
for x in (-0.035, 0.035):
    hit, floor, normal, _ = skull.ray_cast(Vector((x, -1, 0.119)), direction)
    assert hit and normal.dot(direction) < -0.99, "the eye ray did not hit the socket floor"
    depth = floor.y - rim.y
    assert 0.020 < depth < 0.040, f"socket at {x:+.3f}: {depth:.4f} m"
    print(f"skull_01 socket at {x:+.3f}: {depth * 1000:.1f} mm behind rim")

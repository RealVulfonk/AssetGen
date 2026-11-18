"""Build a low-poly asset from JSON.

blender -b --factory-startup --python-exit-code 1 -P blender/build_model.py -- spec.json out_dir
"""

import copy
import json
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Euler, Vector

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from common import export_glb, hex2rgb, render_previews
from uv_layout import PROJECTION_LAYER, pack_uv_islands, project_capped_lathe, restore_part_projections

argv = sys.argv[sys.argv.index("--") + 1 :]
SPEC_PATH, OUT = argv[0], os.path.abspath(argv[1])
os.makedirs(OUT, exist_ok=True)
with open(SPEC_PATH, encoding="utf-8") as handle:
    spec = json.load(handle)
rng = random.Random(spec.get("seed", 1))
warnings = []


def p_box(part):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(part["size"]), verts=bm.verts)
    return bm


def p_cylinder(part):
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        segments=part.get("segments", 8),
        radius1=part["radius"],
        radius2=part.get("radius_top", part["radius"]),
        depth=part["height"],
    )
    return bm


def p_sphere(part):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=part.get("segments", 8),
        v_segments=part.get("rings", 6),
        radius=part["radius"],
    )
    return bm


def p_lathe(part):
    bm = bmesh.new()
    vertices = [bm.verts.new((radius, 0.0, z)) for radius, z in part["profile"]]
    edges = [bm.edges.new((vertices[i], vertices[i + 1])) for i in range(len(vertices) - 1)]
    bmesh.ops.spin(
        bm,
        geom=vertices + edges,
        cent=(0, 0, 0),
        axis=(0, 0, 1),
        angle=2 * math.pi,
        steps=part.get("segments", 10),
        use_merge=True,
    )
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def p_extrude(part):
    bm = bmesh.new()
    vertices = [bm.verts.new((x, y, 0.0)) for x, y in part["points"]]
    face = bm.faces.new(vertices)
    result = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [item for item in result["geom"] if isinstance(item, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, part["depth"]), verts=top)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


PRIMITIVES = {
    "box": p_box,
    "cylinder": p_cylinder,
    "sphere": p_sphere,
    "lathe": p_lathe,
    "extrude": p_extrude,
}


def build_part(part, label, use_projections):
    bm = PRIMITIVES[part["type"]](part)
    if use_projections:
        bm.loops.layers.uv.new("UVMap")
        bm.loops.layers.uv.new(PROJECTION_LAYER)
        if part.get("uv_projection") == "cylindrical":
            project_capped_lathe(bm, part["profile"], label)
    if "scale" in part:
        bmesh.ops.scale(bm, vec=Vector(part["scale"]), verts=bm.verts)
    if "bevel" in part and part["type"] in ("box", "extrude"):
        bevel = part["bevel"]
        bmesh.ops.bevel(
            bm,
            geom=list(bm.edges),
            offset=bevel.get("width", 0.01),
            segments=bevel.get("segments", 1),
            profile=0.5,
            affect="EDGES",
            clamp_overlap=True,
        )
    if part.get("jitter", 0) > 0:
        amount = part["jitter"]
        for vertex in bm.verts:
            vertex.co += Vector([rng.uniform(-amount, amount) for _ in range(3)])
    if "rotation" in part:
        matrix = Euler([math.radians(value) for value in part["rotation"]], "XYZ").to_matrix()
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=matrix, verts=bm.verts)
    if "location" in part:
        bmesh.ops.translate(bm, vec=Vector(part["location"]), verts=bm.verts)
    if part.get("_mirror"):
        bmesh.ops.scale(bm, vec=(-1, 1, 1), verts=bm.verts)
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    return bm


def expand(parts):
    expanded = []
    for part in parts:
        array = part.get("array", {"count": 1, "offset": [0, 0, 0]})
        for index in range(array["count"]):
            item = copy.deepcopy(part)
            location = Vector(item.get("location", [0, 0, 0])) + Vector(array["offset"]) * index
            item["location"] = list(location)
            expanded.append(item)
            if part.get("mirror_x"):
                mirrored = copy.deepcopy(item)
                mirrored["_mirror"] = True
                expanded.append(mirrored)
    return expanded


def get_material(tag):
    material = bpy.data.materials.get(tag)
    if material:
        return material
    material = bpy.data.materials.new(tag)
    color = hex2rgb(spec.get("materials", {}).get(tag, "#888888"))
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1.0)
    material.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    return material


def mesh_bounds(obj):
    vertices = obj.data.vertices
    minimum = Vector(tuple(min(vertex.co[i] for vertex in vertices) for i in range(3)))
    maximum = Vector(tuple(max(vertex.co[i] for vertex in vertices) for i in range(3)))
    return minimum, maximum


def apply_pivot(obj, pivot):
    minimum, maximum = mesh_bounds(obj)
    center = (minimum + maximum) / 2
    if isinstance(pivot, list):
        offset = Vector(pivot)
    elif pivot == "center":
        offset = center
    elif pivot == "hinge_left":
        offset = Vector((minimum.x, center.y, minimum.z))
    else:
        offset = Vector((center.x, center.y, minimum.z))
    for vertex in obj.data.vertices:
        vertex.co -= offset
    obj.data.update()
    return offset


def make_collision_box(obj):
    minimum, maximum = mesh_bounds(obj)
    dimensions = maximum - minimum
    center = (minimum + maximum) / 2
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=dimensions, verts=bm.verts)
    bmesh.ops.translate(bm, vec=center, verts=bm.verts)
    mesh = bpy.data.meshes.new("collision")
    bm.to_mesh(mesh)
    bm.free()
    collision = bpy.data.objects.new(spec["name"] + "-colonly", mesh)
    bpy.context.scene.collection.objects.link(collision)
    collision.display_type = "WIRE"
    collision.hide_render = True
    return collision


def make_mesh_collision(obj, convex=False):
    """Reuse the visible geometry so Godot builds a matching trimesh or convex hull."""
    suffix = "-convcolonly" if convex else "-colonly"
    mesh = obj.data.copy()
    mesh.name = spec["name"] + "_collision"
    mesh.materials.clear()
    collision = bpy.data.objects.new(spec["name"] + suffix, mesh)
    collision.matrix_world = obj.matrix_world.copy()
    bpy.context.scene.collection.objects.link(collision)
    collision.display_type = "WIRE"
    collision.hide_render = True
    return collision


bpy.ops.wm.read_factory_settings(use_empty=True)
objects = []
use_projections = any(part.get("uv_projection") for part in spec["parts"])
for index, part in enumerate(expand(spec["parts"])):
    bm = build_part(part, f"parts[{index}]", use_projections)
    mesh = bpy.data.meshes.new(f"part_{index}")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(get_material(part.get("material", "default")))
    obj = bpy.data.objects.new(f"part_{index}", mesh)
    bpy.context.scene.collection.objects.link(obj)
    objects.append(obj)

bpy.ops.object.select_all(action="DESELECT")
for obj in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0]
if len(objects) > 1:
    bpy.ops.object.join()
obj = bpy.context.view_layer.objects.active
obj.name = obj.data.name = spec["name"]
apply_pivot(obj, spec.get("pivot", "bottom_center"))
for polygon in obj.data.polygons:
    polygon.use_smooth = False

if use_projections:
    obj.data.uv_layers.active = obj.data.uv_layers["UVMap"]
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.03)
bpy.ops.object.mode_set(mode="OBJECT")

if use_projections:
    restore_part_projections(obj.data)
    bpy.ops.object.mode_set(mode="EDIT")
    pack_uv_islands(0.03)
    bpy.ops.object.mode_set(mode="OBJECT")

export_objects = [obj]
collision_type = spec.get("collision", "none")
if collision_type == "box":
    export_objects.append(make_collision_box(obj))
elif collision_type in ("mesh", "convex"):
    export_objects.append(make_mesh_collision(obj, convex=collision_type == "convex"))

bpy.context.view_layer.update()
triangles = sum(len(polygon.vertices) - 2 for polygon in obj.data.polygons)
budget = spec.get("tri_budget", 500)
if triangles > budget:
    warnings.append(f"tris {triangles} > budget {budget}")
dimensions = [round(value, 3) for value in obj.dimensions]
if "expected_size" in spec:
    for axis, actual, expected in zip("XYZ", dimensions, spec["expected_size"]):
        if expected > 0 and abs(actual - expected) / expected > 0.15:
            warnings.append(f"size {axis}: got {actual}, expected {expected}")

blend_path = os.path.join(OUT, spec["name"] + ".blend")
glb_path = os.path.join(OUT, spec["name"] + ".glb")
godot_path = None
bpy.ops.wm.save_as_mainfile(filepath=blend_path, check_existing=False)
export_glb(glb_path, [obj], obj)
if len(export_objects) > 1:
    godot_path = os.path.join(OUT, spec["name"] + "_godot.glb")
    export_glb(godot_path, export_objects, obj)
preview_paths = render_previews(obj, OUT, "MATERIAL")

report = {
    "name": spec["name"],
    "stage": "model",
    "tris": triangles,
    "tri_budget": budget,
    "dimensions": dimensions,
    "materials": [material.name for material in obj.data.materials],
    "blend": blend_path,
    "glb": glb_path,
    "godot_glb": godot_path,
    "previews": preview_paths,
    "warnings": warnings,
    "status": "WARN" if warnings else "OK",
}
with open(os.path.join(OUT, "report.json"), "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, ensure_ascii=False)

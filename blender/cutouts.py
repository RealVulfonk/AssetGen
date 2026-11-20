"""Boolean differences on closed render parts."""

import bmesh
import bpy


def temporary_object(name, geometry):
    mesh = bpy.data.meshes.new(name)
    geometry.to_mesh(mesh)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def validate_shell(geometry, label):
    if not geometry.faces or any(not edge.is_contiguous for edge in geometry.edges):
        raise ValueError(f"{label} must have closed, consistently oriented faces")
    remaining = set(geometry.faces)
    pending = [remaining.pop()]
    while pending:
        for edge in pending.pop().edges:
            for face in edge.link_faces:
                if face in remaining:
                    remaining.remove(face)
                    pending.append(face)
    if remaining:
        raise ValueError(f"{label} must have one connected surface")


def difference(base, cutter, label):
    """Return a new BMesh. The caller retains ownership of both operands."""
    validate_shell(base, f"{label} base")
    validate_shell(cutter, f"{label} cutter")
    volume = base.calc_volume()
    result = bmesh.new()
    objects = []
    try:
        target = temporary_object("cutout_base", base)
        objects.append(target)
        tool = temporary_object("cutout_cutter", cutter)
        objects.append(tool)
        modifier = target.modifiers.new("Cutout", "BOOLEAN")
        modifier.operation = "DIFFERENCE"
        modifier.solver = "EXACT"
        modifier.object = tool
        depsgraph = bpy.context.evaluated_depsgraph_get()
        result.from_mesh(target.evaluated_get(depsgraph).data)
        validate_shell(result, f"{label} result")
        if result.calc_volume() >= volume * (1 - 1e-6):
            raise ValueError(f"{label} does not remove volume from the base")
        return result
    except Exception:
        result.free()
        raise
    finally:
        for obj in objects:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)

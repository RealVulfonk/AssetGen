"""Shared Blender helpers. This module runs inside Blender, not system Python."""

import math
import os

import bpy
from mathutils import Vector


def hex2rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb2lin(value):
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def hex2lin(value):
    return tuple(srgb2lin(channel) for channel in hex2rgb(value))


def bbox_world(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    minimum = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    maximum = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    return minimum, maximum


def export_glb(filepath, objects, active, *, tangents=False):
    """Export exactly the requested objects; glTF has no standard hidden-node flag."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_tangents=tangents,
    )


def render_previews(obj, outdir, color_type="MATERIAL"):
    """Render four deterministic Workbench views and return their paths."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = color_type
    scene.display.shading.show_cavity = False
    scene.display.shading.show_shadows = True
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"

    bpy.context.view_layer.update()
    minimum, maximum = bbox_world(obj)
    center = (minimum + maximum) / 2
    radius = max((maximum - minimum).length, 0.1) * 1.6

    camera_data = bpy.data.cameras.new("preview_cam")
    camera = bpy.data.objects.new("preview_cam", camera_data)
    target = bpy.data.objects.new("preview_tgt", None)
    scene.collection.objects.link(camera)
    scene.collection.objects.link(target)
    target.location = center
    constraint = camera.constraints.new("TRACK_TO")
    constraint.target = target
    constraint.track_axis = "TRACK_NEGATIVE_Z"
    constraint.up_axis = "UP_Y"
    scene.camera = camera

    paths = []
    views = {"front": (0, 8), "side": (90, 8), "iso": (35, 30), "top": (0, 89)}
    for name, (azimuth, elevation) in views.items():
        az = math.radians(azimuth)
        el = math.radians(elevation)
        camera.location = center + Vector(
            (
                radius * math.sin(az) * math.cos(el),
                -radius * math.cos(az) * math.cos(el),
                radius * math.sin(el),
            )
        )
        path = os.path.abspath(os.path.join(outdir, f"preview_{name}.png"))
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        paths.append(path)

    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.objects.remove(target, do_unlink=True)
    bpy.data.cameras.remove(camera_data)
    scene.camera = None
    return paths

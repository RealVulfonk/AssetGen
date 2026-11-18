"""UV projections and packing for the generated render mesh."""

import math

import bpy


PROJECTION_LAYER = "PartProjection"


def project_capped_lathe(bm, profile, label):
    """Keep one continuous side strip and one planar island per cap."""
    radii, heights = zip(*profile)
    if (len(profile) < 4 or radii[0] != 0 or radii[-1] != 0
            or min(radii[1:-1]) <= 0 or heights[0] != heights[1]
            or heights[-2] != heights[-1]
            or any(a >= b for a, b in zip(heights[1:-2], heights[2:-1]))):
        raise ValueError(f"{label}.uv_projection: needs an ascending lathe profile with flat end caps")

    layer = bm.loops.layers.uv[PROJECTION_LAYER]
    outer_radius = max(radii)
    radius = (min(radii[1:-1]) + outer_radius) / 2
    for face in bm.faces:
        points = [loop.vert.co for loop in face.loops]
        # The two flat caps get disjoint planar charts. The side unwraps around -X.
        bottom = all(abs(point.z - heights[0]) < 1e-6 for point in points)
        top = all(abs(point.z - heights[-1]) < 1e-6 for point in points)
        if bottom or top:
            offset = outer_radius * (5 if top else 2)
            for loop, point in zip(face.loops, points):
                loop[layer].uv = (2 + point.x + offset, point.y)
        else:
            angles = [math.atan2(point.y, point.x) for point in points]
            if max(angles) - min(angles) > math.pi:
                angles = [angle + math.tau if angle < 0 else angle for angle in angles]
            for loop, point, angle in zip(face.loops, points, angles):
                loop[layer].uv = (2 + angle * radius, point.z - heights[0])


def restore_part_projections(mesh):
    projected = mesh.uv_layers[PROJECTION_LAYER]
    uv = mesh.uv_layers.active.uv
    for index, coordinate in enumerate(projected.uv):
        # Scratch UVs are zero on parts left to Smart UV.
        if coordinate.vector.length_squared > 0:
            uv[index].vector = coordinate.vector
    mesh.uv_layers.remove(projected)


def pack_uv_islands(margin_fraction):
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(udim_source="ACTIVE_UDIM", margin_method="FRACTION", margin=margin_fraction)

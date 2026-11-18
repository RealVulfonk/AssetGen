"""Measure the active UV map of an AssetGen mesh inside Blender."""

import json
import math
import sys
from collections import defaultdict
from itertools import combinations

import bpy
import numpy as np
from mathutils import Vector, geometry


SIZES = (64, 128, 256, 512)
SAMPLE_GRID = 1024


def find_islands(mesh, uv):
    parents = list(range(len(mesh.polygons)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    edges = defaultdict(list)
    mesh_edges = defaultdict(list)
    for face in mesh.polygons:
        loops = list(face.loop_indices)
        for first, second in zip(loops, loops[1:] + loops[:1]):
            edge = mesh.loops[first].edge_index
            corners = (first, second)
            if mesh.loops[first].vertex_index > mesh.loops[second].vertex_index:
                corners = (second, first)
            start, end = (tuple(uv[index].vector) for index in corners)
            key = (edge, start, end)
            edges[key].append(face.index)
            mesh_edges[edge].append(key)
    for faces in edges.values():
        for face in faces[1:]:
            parents[root(face)] = root(faces[0])

    islands = [root(face.index) for face in mesh.polygons]
    borders = defaultdict(list)
    for (_, start, end), faces in edges.items():
        if len(faces) == 1:
            borders[islands[faces[0]]].append((Vector(start), Vector(end)))
    seams = [
        mesh.edges[index] for index, keys in mesh_edges.items()
        if len(keys) == 2 and keys[0] != keys[1]
    ]
    return islands, borders, seams


def point_segment_distance(point, start, end):
    segment = end - start
    if segment.length_squared == 0:
        return (point - start).length
    fraction = (point - start).dot(segment) / segment.length_squared
    closest = start + segment * max(0.0, min(1.0, fraction))
    return (point - closest).length


def island_gap(borders):
    closest = math.inf
    for first, second in combinations(borders.values(), 2):
        for a, b in first:
            for c, d in second:
                if geometry.intersect_line_line_2d(a, b, c, d) is not None:
                    return 0.0
                closest = min(closest, point_segment_distance(a, c, d),
                              point_segment_distance(b, c, d),
                              point_segment_distance(c, a, b),
                              point_segment_distance(d, a, b))
    return closest if math.isfinite(closest) else None


def rasterize(samples, corners):
    # Interior samples exclude shared edges, which have zero area.
    triangle = np.array(corners, dtype=np.float64) * SAMPLE_GRID
    low = np.clip(np.floor(triangle.min(axis=0)).astype(int), 0, SAMPLE_GRID)
    high = np.clip(np.ceil(triangle.max(axis=0)).astype(int), 0, SAMPLE_GRID)
    x = np.arange(low[0], high[0])[None, :] + 0.5
    y = np.arange(low[1], high[1])[:, None] + 0.5
    sides = [(end[0] - start[0]) * (y - start[1]) - (end[1] - start[1]) * (x - start[0])
             for start, end in zip(triangle, np.roll(triangle, -1, axis=0))]
    region = samples[low[1]:high[1], low[0]:high[0]]
    region += np.logical_or(np.logical_and.reduce([side > 0 for side in sides]),
                            np.logical_and.reduce([side < 0 for side in sides]))


def measure(obj, margin):
    mesh = obj.data
    layer = mesh.uv_layers.active
    if layer is None or not mesh.polygons:
        raise ValueError(f"{obj.name!r} has no UV-mapped faces")
    uv = layer.uv
    islands, borders, seams = find_islands(mesh, uv)
    gap = island_gap(borders)
    world = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    coordinates = np.array([tuple(loop.vector) for loop in uv])
    edge_gap = float(min(coordinates.min(), 1 - coordinates.max()))
    mesh.calc_loop_triangles()
    areas = defaultdict(lambda: [0.0, 0.0])
    samples = np.zeros((SAMPLE_GRID, SAMPLE_GRID), dtype=np.int32)
    for triangle in mesh.loop_triangles:
        a, b, c = (uv[index].vector for index in triangle.loops)
        corners = (tuple(a), tuple(b), tuple(c))
        x, y, z = (world[index] for index in triangle.vertices)
        island = areas[islands[triangle.polygon_index]]
        island[0] += abs((b - a).cross(c - a)) / 2
        island[1] += (y - x).cross(z - x).length / 2
        rasterize(samples, corners)

    density = [math.sqrt(uv_area / world_area) for uv_area, world_area in areas.values()
               if world_area > 0]
    return {
        "blender": bpy.app.version_string,
        "asset": obj.name,
        "triangles": len(mesh.loop_triangles),
        "islands": len(areas),
        "uv_seam_edges": len(seams),
        "uv_seam_length_m": round(sum((world[e.vertices[0]] - world[e.vertices[1]]).length
                                      for e in seams), 4),
        "sample_grid": SAMPLE_GRID,
        "atlas_coverage_percent": round(100 * np.count_nonzero(samples) / samples.size, 4),
        "atlas_overlap_percent": round(100 * np.count_nonzero(samples > 1) / samples.size, 4),
        "resolutions": {
            size: {
                "min_island_gap_px": round(gap * size, 3) if gap is not None else None,
                "min_atlas_border_px": round(edge_gap * size, 3),
                "island_density_px_per_m": [round(min(density) * size, 2),
                                            round(max(density) * size, 2)],
                "bake_margin_px": margin,
                "room_for_two_margins": gap is None or gap * size >= 2 * margin,
            }
            for size in SIZES
        },
    }


def main():
    asset, output, *args = sys.argv[sys.argv.index("--") + 1:]
    margin = int(args[0]) if args else 4
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(measure(bpy.data.objects[asset], margin), handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()

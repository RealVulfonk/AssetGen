"""Verify that each wooden end cap survives UV packing as one planar chart."""

import math
from collections import defaultdict

import bpy

mesh = bpy.data.objects["barrel_01"].data
uv = mesh.uv_layers.active.uv
for height in (min(vertex.co.z for vertex in mesh.vertices), max(vertex.co.z for vertex in mesh.vertices)):
    chart = defaultdict(list)
    scales = []
    for face in mesh.polygons:
        if not all(math.isclose(mesh.vertices[index].co.z, height, abs_tol=1e-6) for index in face.vertices):
            continue
        corners = [uv[index].vector for index in face.loop_indices]
        for vertex, corner in zip(face.vertices, corners):
            chart[vertex].append(corner)
        twice_area = abs(sum(a.cross(b) for a, b in zip(corners, corners[1:] + corners[:1])))
        scales.append(twice_area / (2 * face.area))
    assert len(scales) == 10, f"expected ten triangles in the cap at Z={height}"
    assert min(scales) > 1e-6, f"collapsed UV triangle in cap at Z={height}: {scales}"
    assert math.isclose(min(scales), max(scales), rel_tol=1e-5), f"stretched UV triangle at Z={height}"
    for vertex, corners in chart.items():
        assert all((corner - corners[0]).length < 1e-6 for corner in corners), f"UV seam at cap vertex {vertex}"
print("Verified both barrel UV caps")

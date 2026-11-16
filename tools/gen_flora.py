#!/usr/bin/env python3
"""Procedural forest generator: writes AssetGen JSON specs into specs/.

    python tools/gen_flora.py --list
    python tools/gen_flora.py --family conifer --count 14 --seed 700
    python tools/gen_flora.py --all --seed 700

Trees are radial by nature and the DSL has no radial array (only linear
``array`` and ``mirror_x``), so this script does the trigonometry itself and
emits one explicit part per branch with its own ``rotation``.
"""

import argparse
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "specs" / "models"
TEXTURES = ROOT / "specs" / "textures"

CATEGORY_TREE = "flora/trees"
CATEGORY_GROUND = "flora/understory"


def orient(p0, p1):
    """Length, azimuth and elevation (degrees) of the p0 -> p1 segment."""
    dx, dy, dz = (p1[i] - p0[i] for i in range(3))
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-6:
        return 0.0, 0.0, 0.0
    azimuth = math.degrees(math.atan2(dy, dx))
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, dz / length))))
    return length, azimuth, elevation


def euler_xyz(rx, ry, rz):
    """Rotation matrix for Blender's XYZ Euler order (degrees)."""
    cx, sx = math.cos(math.radians(rx)), math.sin(math.radians(rx))
    cy, sy = math.cos(math.radians(ry)), math.sin(math.radians(ry))
    cz, sz = math.cos(math.radians(rz)), math.sin(math.radians(rz))
    return (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )


def apply(matrix, vector):
    return [sum(matrix[i][j] * vector[j] for j in range(3)) for i in range(3)]


class Builder:
    """Collects parts and tracks the exact bounding box while placing them."""

    def __init__(self, rng):
        self.rng = rng
        self.parts = []
        self.lo = [1e9, 1e9, 1e9]
        self.hi = [-1e9, -1e9, -1e9]

    def _track(self, point, pad):
        """Grow the bbox around ``point``; ``pad`` is a scalar or per-axis."""
        if isinstance(pad, (int, float)):
            pad = (pad, pad, pad)
        for i in range(3):
            self.lo[i] = min(self.lo[i], point[i] - pad[i])
            self.hi[i] = max(self.hi[i], point[i] + pad[i])

    def _track_box(self, center, half, rotation):
        """Track an axis-aligned box rotated about its own centre."""
        matrix = euler_xyz(*rotation)
        reach = [sum(abs(matrix[i][j]) * half[j] for j in range(3)) for i in range(3)]
        self._track(center, reach)

    def ground(self):
        """Lift the whole asset so its lowest point sits exactly on z=0.

        Нижние комки листвы и отросшие корни могут уйти ниже нуля. Pivot
        bottom_center считается по фактическому bbox Blender, поэтому
        утопленная в пол геометрия сдвинула бы точку опоры.
        """
        if not self.parts or self.lo[2] >= -1e-4:
            return
        lift = -self.lo[2]
        for part in self.parts:
            location = part.get("location")
            if location:
                part["location"] = [round(location[0], 4),
                                    round(location[1], 4),
                                    round(location[2] + lift, 4)]
        self.lo[2] += lift
        self.hi[2] += lift

    def blade(self, material, p0, p1, width0, width1, thickness, comment, jitter=0.003,
              roll=0.0):
        """Flat tapered spray: long axis along the segment, thickness across it.

        ``roll`` поворачивает плоскость лопасти вокруг её длинной оси. Без него
        все перья вайи лежали бы в одной плоскости и папоротник выглядел бы
        плоским; при roll=90 лопасть встаёт «на ребро».
        """
        length, azimuth, elevation = orient(p0, p1)
        if length < 1e-3:
            return
        rotation = [roll, -elevation, azimuth]
        self.parts.append({
            "comment": comment,
            "type": "extrude",
            "material": material,
            "points": [[0.0, -width0], [length, -width1], [length, width1], [0.0, width0]],
            "depth": thickness,
            "rotation": rotation,
            "location": list(p0),
            "jitter": jitter,
        })
        # Лопасть — вытянутый бокс вдоль луча: считаем её повёрнутый bbox точно.
        center = [(p0[i] + p1[i]) / 2 for i in range(3)]
        self._track_box(center, [length / 2, max(width0, width1), thickness / 2], rotation)

    def limb(self, material, p0, p1, radius0, radius1, comment, segments=6, jitter=0.002):
        """Tapered cylinder between two points; radius1 == 0 makes a spike."""
        length, azimuth, elevation = orient(p0, p1)
        if length < 1e-3:
            return
        rotation = [0.0, round(90.0 - elevation, 3), round(azimuth, 3)]
        part = {
            "comment": comment,
            "type": "cylinder",
            "material": material,
            "radius": round(radius0, 4),
            "height": round(length, 4),
            "segments": segments,
            "rotation": rotation,
            "location": [round((p0[i] + p1[i]) / 2, 4) for i in range(3)],
        }
        # radius_top: 0 допустим схемой и даёт настоящий шип; без него
        # build_model.py берёт radius, и конус вырождается в цилиндр.
        part["radius_top"] = round(max(radius1, 0.0), 4)
        if jitter:
            part["jitter"] = jitter
        self.parts.append(part)
        # Усечённый конус: границы задают два торцевых диска с разными радиусами.
        # Диск радиуса r, перпендикулярный оси a, проецируется на ось i как
        # r*sqrt(1-a_i^2); берём объединение обоих торцов, а не максимум радиуса.
        axis = [(p1[i] - p0[i]) / length for i in range(3)]
        r0, r1 = radius0, max(radius1, 0.0)
        for i in range(3):
            spread = math.sqrt(max(0.0, 1.0 - axis[i] ** 2))
            self.lo[i] = min(self.lo[i], p0[i] - r0 * spread, p1[i] - r1 * spread)
            self.hi[i] = max(self.hi[i], p0[i] + r0 * spread, p1[i] + r1 * spread)

    def box(self, material, size, location, comment, rotation=None, jitter=0.0,
            bevel=None, mirror_x=False):
        part = {
            "comment": comment,
            "type": "box",
            "material": material,
            "size": [round(value, 4) for value in size],
            "location": [round(value, 4) for value in location],
        }
        if rotation:
            part["rotation"] = [round(value, 3) for value in rotation]
        if bevel:
            part["bevel"] = bevel
        if jitter:
            part["jitter"] = jitter
        if mirror_x:
            part["mirror_x"] = True
        self.parts.append(part)
        half = [value / 2 for value in size]
        if rotation:
            self._track_box(location, half, rotation)
        else:
            self._track(location, half)

    def blob(self, material, center, radius, comment, scale=None, segments=8,
             rings=5, jitter=0.004):
        part = {
            "comment": comment,
            "type": "sphere",
            "material": material,
            "radius": round(radius, 4),
            "segments": segments,
            "rings": rings,
            "location": [round(value, 4) for value in center],
            "jitter": jitter,
        }
        if scale:
            part["scale"] = [round(value, 4) for value in scale]
        self.parts.append(part)
        # UV-сфера: вершины лежат на широтах i*pi/rings. При нечётном rings
        # экваториального пояса нет, и фактическая ширина меньше радиуса —
        # учитываем это, иначе expected_size врёт относительно Blender.
        max_sin = max(math.sin(math.pi * i / max(rings, 2)) for i in range(max(rings, 2) + 1))
        pad = [radius * max_sin, radius * max_sin, radius]
        if scale:
            pad = [pad[i] * abs(scale[i]) for i in range(3)]
        if jitter:
            pad = [value + jitter for value in pad]
        self._track(center, pad)

    def size(self):
        return [round(max(self.hi[i] - self.lo[i], 0.01), 3) for i in range(3)]


def droop_point(origin, azimuth_deg, droop_deg, length):
    """End point of a branch leaving ``origin`` at the given angles.

    ``droop_deg`` is measured from the horizontal plane: 0 is straight out,
    90 is straight down, negative points upward.
    """
    az = math.radians(azimuth_deg)
    dr = math.radians(droop_deg)
    reach = length * math.cos(dr)
    return [
        origin[0] + reach * math.cos(az),
        origin[1] + reach * math.sin(az),
        origin[2] - length * math.sin(dr),
    ]


def sprout_point(origin, azimuth_deg, tilt_deg, length):
    """End point of an upright shoot; ``tilt_deg`` is measured from vertical."""
    return droop_point(origin, azimuth_deg, 90.0 - tilt_deg, length)


def trunk_axis(z0, z1, lean, bend):
    """Trunk centreline: quadratic drift, so trees can lean and curve."""
    def axis(z):
        t = 0.0 if z1 <= z0 else (z - z0) / (z1 - z0)
        t = max(0.0, min(1.0, t))
        curve = t * t + bend * math.sin(math.pi * t)
        return (lean[0] * curve, lean[1] * curve, z)
    return axis


# --------------------------------------------------------------------------
# Trees
# --------------------------------------------------------------------------

CONIFER_SHAPES = [
    # height, bare, whorls, per_whorl, reach, falloff, droop_lo, droop_hi, taper
    ((6.5, 11.0), 0.10, (7, 10), (5, 7), (1.5, 2.4), (0.85, 1.05), (16, 26), (-6, 4), (0.62, 0.78)),
    ((4.5, 8.0), 0.06, (8, 11), (6, 8), (1.8, 2.9), (0.70, 0.90), (20, 34), (-4, 6), (0.55, 0.70)),
    ((3.5, 6.5), 0.14, (6, 9), (5, 8), (1.2, 2.0), (0.80, 1.00), (10, 22), (0, 10), (0.60, 0.75)),
    ((1.4, 3.0), 0.05, (5, 8), (7, 10), (0.9, 1.6), (0.55, 0.75), (22, 40), (4, 14), (0.45, 0.62)),
    ((0.8, 2.2), 0.20, (4, 7), (6, 9), (0.7, 1.3), (0.60, 0.85), (26, 46), (8, 18), (0.40, 0.58)),
]


def conifer(rng, shape):
    height_r, bare, whorls_r, per_r, reach_r, falloff_r, droop_lo_r, droop_hi_r, taper_r = shape
    height = rng.uniform(*height_r)
    bare = bare * rng.uniform(0.7, 1.35)
    n_whorls = rng.randint(*whorls_r)
    per_whorl = rng.randint(*per_r)
    max_reach = rng.uniform(*reach_r)
    falloff = rng.uniform(*falloff_r)
    droop_lo = rng.uniform(*droop_lo_r)
    droop_hi = rng.uniform(*droop_hi_r)
    taper = rng.uniform(*taper_r)
    lean = (rng.uniform(-0.35, 0.35) * height * 0.06, rng.uniform(-0.35, 0.35) * height * 0.06)
    bend = rng.uniform(-0.6, 0.6)
    dead_whorls = rng.choice([0, 0, 1, 1, 2, 3])
    dry_palette = rng.choice(["bark_brown_soft", "dry_wood_soft", "bark_red_soft"])

    b = Builder(rng)
    z_bare = height * bare
    axis = trunk_axis(0.0, height, lean, bend)
    base_radius = height * rng.uniform(0.014, 0.026)

    segments = rng.randint(4, 6)
    points = [axis(z_bare + (height - z_bare) * (i / segments)) for i in range(segments + 1)]
    points[0] = axis(0.0)
    for i in range(segments):
        t0, t1 = i / segments, (i + 1) / segments
        r0 = base_radius * (1.0 - taper * t0)
        r1 = base_radius * (1.0 - taper * t1)
        label = "ствол" if i == 0 else f"ствол сегмент {i + 1}"
        b.limb("bark", points[i], points[i + 1], r0, r1, label,
               segments=7 if i == 0 else 6, jitter=0.0025)

    # Корневой наплыв, чтобы ствол не выглядел воткнутым в пол.
    for index in range(rng.randint(3, 5)):
        az = 360.0 * index / 4 + rng.uniform(-20, 20)
        tip = droop_point([0.0, 0.0, 0.0], az, -70.0, base_radius * rng.uniform(2.0, 3.2))
        tip[2] = 0.0
        b.limb("bark", [0.0, 0.0, base_radius * 0.9], tip,
               base_radius * 0.55, base_radius * 0.18, f"корневой наплыв {index + 1}")

    top_whorl = height * rng.uniform(0.93, 0.985)
    for w in range(n_whorls):
        # Степень < 1 сгущает ярусы к вершине, как у настоящей ели.
        t = ((w + 1) / (n_whorls + 1)) ** rng.uniform(0.75, 0.9)
        z = z_bare + (top_whorl - z_bare) * t
        origin = list(axis(z))
        reach = max_reach * (1.0 - 0.88 * t) ** falloff
        if reach < 0.08:
            continue
        dry = w < dead_whorls
        material = "bark_dry" if dry else "needles"
        if dry:
            reach *= rng.uniform(0.35, 0.6)
        count = max(3, int(round(per_whorl * (1.0 - 0.25 * t))))
        phase = w * (137.5 + rng.uniform(-22, 22)) + rng.uniform(0, 360)
        droop = droop_lo + (droop_hi - droop_lo) * t
        thickness = max(0.03, reach * rng.uniform(0.15, 0.26))
        for index in range(count):
            az = phase + 360.0 * index / count
            jitter_len = reach * rng.uniform(0.82, 1.15)
            jitter_droop = droop + rng.uniform(-7, 7)
            tip = droop_point(origin, az, jitter_droop, jitter_len)
            tag = f"ярус {w + 1} ветка {index + 1}/{count}"
            if dry:
                tag = f"сухая ветка ярус {w + 1} {index + 1}/{count}"
                b.limb(material, origin, tip, thickness * 0.28, thickness * 0.08, tag)
            else:
                b.blade(material, origin, tip, thickness, thickness * 0.22,
                        thickness * rng.uniform(0.35, 0.55), tag)
        # Промежуточный ярус для густой «лапчатой» кроны.
        if rng.random() < 0.85:
            z_sub = min(z + (top_whorl - z_bare) / (n_whorls + 1) * 0.42, top_whorl)
            origin_sub = list(axis(z_sub))
            reach_sub = reach * rng.uniform(0.55, 0.8)
            count_sub = max(3, count - rng.randint(0, 2))
            phase_sub = phase + 180.0 / max(count_sub, 1)
            thickness_sub = max(0.024, reach_sub * 0.17)
            for index in range(count_sub):
                az = phase_sub + 360.0 * index / count_sub
                tip = droop_point(origin_sub, az, droop - rng.uniform(2, 10),
                                  reach_sub * rng.uniform(0.8, 1.1))
                b.blade(material if not dry else "needles", origin_sub, tip,
                        thickness_sub, thickness_sub * 0.22,
                        thickness_sub * rng.uniform(0.35, 0.55),
                        f"подъярус {w + 1} ветка {index + 1}/{count_sub}")

    # Макушка: короткий лидерный побег чуть выше последнего яруса.
    apex = list(axis(height))
    spike_base = list(axis(top_whorl))
    b.limb("bark", spike_base, apex, base_radius * (1.0 - taper) * 0.8, 0.0,
           "макушка", segments=5)
    for index in range(rng.randint(3, 5)):
        az = 360.0 * index / 4 + rng.uniform(-25, 25)
        tip = droop_point(spike_base, az, rng.uniform(-30, 5), max_reach * 0.22)
        tip[2] = max(tip[2], spike_base[2] * 0.9)
        b.blade("needles", spike_base, tip, max_reach * 0.09, max_reach * 0.02,
                max_reach * 0.05, f"верхушечная лапа {index + 1}")

    b.ground()
    return {
        "parts": b.parts,
        "size": b.size(),
        "budget": 2400,
        "category": CATEGORY_TREE,
        "bark_palette": rng.choice(["bark_brown_soft", "bark_red_soft", "wood_dark_soft"]),
        "bark_dry_palette": dry_palette,
        "needle_palette": rng.choice(["needle_green_soft", "needle_bright_soft",
                                      "needle_dark_soft"]),
        "collision": "mesh",
        "size_px": 256 if height > 5.0 else 128,
        "height": height,
    }


def snag(rng):
    """Голый сухостой: обломанная верхушка, торчащие сучья, ни хвои."""
    height = rng.uniform(3.0, 10.0)
    lean = (rng.uniform(-0.6, 0.6) * height * 0.10, rng.uniform(-0.6, 0.6) * height * 0.10)
    bend = rng.uniform(-1.0, 1.0)
    base_radius = height * rng.uniform(0.022, 0.036)
    taper = rng.uniform(0.62, 0.86)
    axis = trunk_axis(0.0, height, lean, bend)

    b = Builder(rng)
    segments = rng.randint(7, 10)
    points = [axis(height * i / segments) for i in range(segments + 1)]
    for i in range(segments):
        t0, t1 = i / segments, (i + 1) / segments
        b.limb("bark", points[i], points[i + 1],
               base_radius * (1.0 - taper * t0), base_radius * (1.0 - taper * t1),
               f"ствол сегмент {i + 1}", segments=6 if i else 7, jitter=0.006)

    # Обломанный верх: несколько рваных шипов разной длины вместо макушки.
    crown = list(axis(height))
    for index in range(rng.randint(3, 5)):
        tip = droop_point(crown, rng.uniform(0, 360), rng.uniform(20, 75),
                          height * rng.uniform(0.04, 0.14))
        b.limb("bark", crown, tip, base_radius * (1.0 - taper) * 0.9, 0.0,
               f"обломок верхушки {index + 1}", segments=5)

    # Сучья: длинные жерди с отростками, короткие пеньки и пара загнутых вниз.
    limb_ends = []
    for index in range(rng.randint(7, 12)):
        az = rng.uniform(0, 360)
        z = rng.uniform(height * 0.22, height * 0.94)
        origin = list(axis(z))
        kind = rng.random()
        if kind < 0.45:
            length = height * rng.uniform(0.24, 0.42)
        elif kind < 0.75:
            length = height * rng.uniform(0.10, 0.22)
        else:
            length = height * rng.uniform(0.05, 0.10)
        # Толщина сука зависит от высоты: внизу толще, у вершины тоньше.
        thickness = base_radius * rng.uniform(0.30, 0.55) * (1.0 - 0.5 * z / height)
        tip = droop_point(origin, az, rng.uniform(-15, 40), length)
        b.limb("bark", origin, tip, thickness, thickness * 0.18,
               f"сук {index + 1}", segments=5, jitter=0.005)
        limb_ends.append((tip, thickness, az, length))
        # Отросток на длинном суку — сухостой перестаёт быть «палкой с гвоздями».
        if length > height * 0.20 and rng.random() < 0.7:
            fork = [origin[i] + (tip[i] - origin[i]) * rng.uniform(0.45, 0.75)
                    for i in range(3)]
            sub_tip = droop_point(fork, az + rng.uniform(-75, 75), rng.uniform(-10, 40),
                                  length * rng.uniform(0.35, 0.6))
            b.limb("bark", fork, sub_tip, thickness * 0.55, thickness * 0.12,
                   f"отросток сука {index + 1}", segments=5, jitter=0.004)

    # Коряга, упавшая к земле.
    if rng.random() < 0.55:
        az = rng.uniform(0, 360)
        origin = list(axis(height * rng.uniform(0.30, 0.55)))
        tip = droop_point(origin, az, rng.uniform(48, 76), height * rng.uniform(0.30, 0.50))
        tip[2] = max(tip[2], 0.0)
        b.limb("bark", origin, tip, base_radius * 0.55, 0.0,
               "упавшая коряга", segments=6, jitter=0.006)

    # Торчащие корни у комля.
    for index in range(rng.randint(4, 6)):
        az = 360.0 * index / 5 + rng.uniform(-25, 25)
        tip = droop_point([0.0, 0.0, 0.0], az, -72.0, base_radius * rng.uniform(2.4, 4.0))
        tip[2] = 0.0
        b.limb("bark", [0.0, 0.0, base_radius * 0.8], tip,
               base_radius * 0.55, base_radius * 0.15, f"корень {index + 1}",
               jitter=0.006)

    # Мох у основания — связывает сухостой с землёй.
    if rng.random() < 0.6:
        for index in range(rng.randint(2, 4)):
            az = rng.uniform(0, 360)
            spot = droop_point([0.0, 0.0, 0.0], az, -80.0, base_radius * rng.uniform(1.5, 2.6))
            spot[2] = base_radius * rng.uniform(0.1, 0.35)
            b.blob("moss", spot, base_radius * rng.uniform(0.5, 0.9),
                   f"мох у комля {index + 1}", scale=[1.0, 1.0, 0.55],
                   segments=7, rings=4, jitter=0.006)

    b.ground()
    return {
        "parts": b.parts,
        "size": b.size(),
        "budget": 2000,
        "category": CATEGORY_TREE,
        "bark_palette": rng.choice(["dry_wood_soft", "bark_brown_soft", "wood_dark_soft"]),
        "bark_dry_palette": rng.choice(["dry_wood_soft", "bark_brown_soft"]),
        "needle_palette": rng.choice(["needle_dark_soft", "moss_green_soft"]),
        "collision": "mesh",
        "size_px": 256 if height > 5.0 else 128,
        "height": height,
    }


BROADLEAF_SHAPES = [
    # height, limbs, leaf_size, crown_wide, crown_ratio
    ((5.0, 9.0), (13, 17), (0.30, 0.42), (0.85, 1.15), (0.55, 0.72)),
    ((3.0, 6.0), (12, 16), (0.28, 0.40), (0.95, 1.25), (0.58, 0.78)),
    ((1.8, 3.6), (10, 14), (0.26, 0.36), (1.05, 1.35), (0.62, 0.85)),
    ((4.0, 7.5), (12, 16), (0.30, 0.42), (0.65, 0.90), (0.50, 0.68)),
]


def broadleaf(rng, shape):
    height_r, limbs_r, leaf_r, wide_r, ratio_r = shape
    height = rng.uniform(*height_r)
    n_limbs = rng.randint(*limbs_r)
    leaf_size = rng.uniform(*leaf_r)
    crown_wide = rng.uniform(*wide_r)
    crown_ratio = rng.uniform(*ratio_r)
    lean = (rng.uniform(-0.3, 0.3) * height * 0.06, rng.uniform(-0.3, 0.3) * height * 0.06)
    bend = rng.uniform(-0.5, 0.5)
    base_radius = height * rng.uniform(0.018, 0.032)
    taper = rng.uniform(0.50, 0.70)
    trunk_top = height * rng.uniform(0.48, 0.62)
    axis = trunk_axis(0.0, trunk_top, lean, bend)

    b = Builder(rng)
    segments = rng.randint(3, 5)
    points = [axis(trunk_top * i / segments) for i in range(segments + 1)]
    for i in range(segments):
        t0, t1 = i / segments, (i + 1) / segments
        b.limb("bark", points[i], points[i + 1],
               base_radius * (1.0 - taper * t0), base_radius * (1.0 - taper * t1),
               f"ствол сегмент {i + 1}", segments=7 if i == 0 else 6, jitter=0.003)

    for index in range(rng.randint(3, 5)):
        az = 360.0 * index / 4 + rng.uniform(-30, 30)
        tip = droop_point([0.0, 0.0, 0.0], az, -70.0, base_radius * rng.uniform(2.4, 3.8))
        tip[2] = 0.0
        b.limb("bark", [0.0, 0.0, base_radius * 0.9], tip,
               base_radius * 0.55, base_radius * 0.16, f"корневой наплыв {index + 1}")

    # Крона-купол: ветви отходят от ствола на разной высоте, а их концы
    # распределены по эллипсоиду спиралью Фибоначчи — это убирает «пальму».
    crown_center = [axis(trunk_top)[0], axis(trunk_top)[1],
                    trunk_top + (height - trunk_top) * 0.42]
    radius_h = height * 0.30 * crown_wide
    radius_v = radius_h * crown_ratio
    crown_base = list(axis(trunk_top * rng.uniform(0.55, 0.75)))
    limb_tips = []
    foliage_spots = []
    for index in range(n_limbs):
        t = (index + 0.5) / n_limbs
        cos_theta = 1.0 - t * rng.uniform(1.0, 1.15)
        theta = math.acos(max(-1.0, min(1.0, cos_theta)))
        az = index * 137.508 + rng.uniform(-14, 14)
        jitter = rng.uniform(0.85, 1.12)
        tip = [
            crown_center[0] + radius_h * math.sin(theta) * math.cos(math.radians(az)) * jitter,
            crown_center[1] + radius_h * math.sin(theta) * math.sin(math.radians(az)) * jitter,
            crown_center[2] + radius_v * cos_theta * jitter,
        ]
        # Ветви растут из ствола на разной высоте, а не веером из одной точки.
        origin_z = crown_base[2] + (trunk_top - crown_base[2]) * (index / max(n_limbs - 1, 1))
        origin = list(axis(origin_z * rng.uniform(0.92, 1.0)))
        mid = [origin[i] + (tip[i] - origin[i]) * 0.55 for i in range(3)]
        radius = base_radius * rng.uniform(0.34, 0.48) * (1.0 - 0.35 * index / n_limbs)
        b.limb("bark", origin, mid, radius, radius * 0.65,
               f"ветвь кроны {index + 1}", segments=6, jitter=0.003)
        b.limb("bark", mid, tip, radius * 0.65, radius * 0.22,
               f"ветвь кроны {index + 1}.1", segments=5, jitter=0.003)
        # Листва идёт и вдоль ветви, но не на каждой — крона остаётся воздушной.
        if rng.random() < 0.55:
            foliage_spots.append((mid, rng.uniform(0.7, 0.9)))
        limb_tips.append(tip)
        # Часть ветвей несёт второй побег — крона гуще без роста числа ветвей.
        if rng.random() < 0.5:
            sub_tip = droop_point(mid, az + rng.uniform(-70, 70), rng.uniform(-10, 35),
                                  height * rng.uniform(0.10, 0.18))
            b.limb("bark", mid, sub_tip, radius * 0.5, radius * 0.16,
                   f"ветвь кроны {index + 1}.2", segments=5, jitter=0.003)
            limb_tips.append(sub_tip)
        limb_tips.append(tip)

    # Листва: гранёные комки дают массу, торчащие листья — рваный силуэт.
    # Одни комки читаются как «брокколи», одни листья оставляют крону дырявой.
    # Комок держим чуть меньше листа, иначе лепестки тонут в шаре.
    leaf_palette = rng.choice(["leaf_green_soft", "moss_green_soft",
                               "needle_bright_soft", "leaf_yellow_soft"])
    for index, (tip, scale) in enumerate(foliage_spots + [(tip, 1.0) for tip in limb_tips]):
        b.blob("leaves", tip, leaf_size * scale * rng.uniform(0.42, 0.58),
               f"крона комок {index + 1}",
               scale=[rng.uniform(1.0, 1.3), rng.uniform(1.0, 1.3),
                      rng.uniform(0.72, 0.92)],
               segments=6, rings=4, jitter=0.03)
        count = rng.randint(3, 5)
        for leaf in range(count):
            az = 360.0 * leaf / count + rng.uniform(-25, 25)
            end = droop_point(tip, az, rng.uniform(-25, 35),
                              leaf_size * scale * rng.uniform(0.75, 1.2))
            b.blade("leaves", tip, end, leaf_size * 0.17, leaf_size * 0.03,
                    leaf_size * 0.04, f"крона лист {index + 1}.{leaf + 1}")

    b.ground()
    return {
        "parts": b.parts,
        "size": b.size(),
        "budget": 6000,
        "category": CATEGORY_TREE,
        "bark_palette": rng.choice(["bark_brown_soft", "bark_red_soft", "wood_dark_soft"]),
        "bark_dry_palette": "dry_wood_soft",
        "needle_palette": leaf_palette,
        "collision": "mesh",
        "size_px": 256 if height > 4.0 else 128,
        "height": height,
    }


def shrub(rng):
    """Низкий густой куст: пучок стеблей из одной точки плюс шапка листвы."""
    height = rng.uniform(0.45, 1.7)
    stems = rng.randint(5, 9)
    base_radius = height * rng.uniform(0.012, 0.022)
    spread = rng.uniform(38, 68)
    leaf_palette = rng.choice(["leaf_green_soft", "moss_green_soft",
                               "fern_green_soft", "needle_dark_soft"])
    flowering = rng.random() < 0.35

    b = Builder(rng)
    tips = []
    for index in range(stems):
        az = 360.0 * index / stems + rng.uniform(-22, 22)
        # Наклон от вертикали ограничен сверху: при 90° стебель ложится
        # горизонтально и комок висит в воздухе.
        length = height * rng.uniform(0.45, 1.15)
        tilt = rng.uniform(6, min(spread, 55))
        origin = [rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0.0]
        tip = sprout_point(origin, az, tilt, length)
        b.limb("twig", origin, tip, base_radius, base_radius * 0.35,
               f"стебель {index + 1}", segments=5, jitter=0.003)
        tips.append(tip)
        # Комки сидят не лесенкой по оси, а вокруг стебля: смещение в стороны
        # по азимуту делает куст объёмным, а не «башней из шаров».
        side = height * rng.uniform(0.10, 0.16)
        for step in range(rng.randint(2, 3)):
            t = 0.35 + 0.3 * step
            spot = [origin[i] + (tip[i] - origin[i]) * t for i in range(3)]
            offset_az = az + rng.uniform(0, 360)
            spread_out = rng.uniform(0.4, 1.0)
            spot[0] += math.cos(math.radians(offset_az)) * side * spread_out
            spot[1] += math.sin(math.radians(offset_az)) * side * spread_out
            b.blob("leaves", spot, height * rng.uniform(0.11, 0.17),
                   f"листва стебля {index + 1}.{step + 1}",
                   scale=[rng.uniform(1.0, 1.3), rng.uniform(1.0, 1.3), 0.85],
                   segments=6, rings=4, jitter=0.014)

    for index, tip in enumerate(tips):
        # Верхушечный комок меньше шага между стеблями, иначе соседние
        # слипаются в сплошную массу и куст читается как груда камней.
        radius = height * rng.uniform(0.11, 0.16)
        b.blob("leaves", tip, radius, f"листва {index + 1}",
               scale=[rng.uniform(1.0, 1.4), rng.uniform(1.0, 1.4),
                      rng.uniform(0.72, 0.95)],
               segments=7, rings=4, jitter=0.012)
        # Несколько торчащих листьев дают рваный край вместо гладкого шара.
        for leaf in range(rng.randint(2, 4)):
            az = 360.0 * leaf / 3 + rng.uniform(-30, 30)
            end = droop_point(tip, az, rng.uniform(-20, 40), radius * rng.uniform(1.1, 1.7))
            b.blade("leaves", tip, end, radius * 0.22, radius * 0.05,
                    radius * 0.07, f"лист куста {index + 1}.{leaf + 1}")
    # Один-два внутренних комка ниже — заполняют середину, не склеивая куст.
    for index in range(rng.randint(1, 2)):
        tip = rng.choice(tips)
        spot = [tip[0] * rng.uniform(0.2, 0.5), tip[1] * rng.uniform(0.2, 0.5),
                tip[2] * rng.uniform(0.3, 0.6)]
        b.blob("leaves", spot, height * rng.uniform(0.14, 0.20),
               f"листва внутренняя {index + 1}",
               scale=[rng.uniform(1.0, 1.3), rng.uniform(1.0, 1.3), 0.7],
               segments=7, rings=4, jitter=0.012)

    if flowering:
        for index in range(rng.randint(3, 6)):
            tip = rng.choice(tips)
            spot = [tip[0] + rng.uniform(-0.1, 0.1), tip[1] + rng.uniform(-0.1, 0.1),
                    tip[2] + rng.uniform(0.0, 0.12)]
            b.blob("petal", spot, height * rng.uniform(0.05, 0.09),
                   f"цветок {index + 1}", segments=6, rings=4, jitter=0.006)

    b.ground()
    return {
        "parts": b.parts,
        "size": b.size(),
        "budget": 1900,
        "category": CATEGORY_GROUND,
        "bark_palette": rng.choice(["wood_dark_soft", "bark_brown_soft"]),
        "bark_dry_palette": "dry_wood_soft",
        "needle_palette": leaf_palette,
        "collision": "box",
        "size_px": 128,
        "height": height,
    }


# --------------------------------------------------------------------------
# Understory
# --------------------------------------------------------------------------

def stump(rng):
    height = rng.uniform(0.20, 0.85)
    radius = rng.uniform(0.16, 0.42)
    lean = (rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05))
    top = [lean[0], lean[1], height]
    b = Builder(rng)
    b.limb("bark", [0.0, 0.0, 0.0], top, radius, radius * rng.uniform(0.82, 0.95),
           "пень", segments=rng.randint(7, 9), jitter=0.006)
    # Рваный срез: несколько шипов вверх.
    for index in range(rng.randint(3, 6)):
        az = rng.uniform(0, 360)
        origin = droop_point(top, az, rng.uniform(-8, 8), radius * rng.uniform(0.25, 0.85))
        origin[2] = height
        tip = [origin[0], origin[1], height + rng.uniform(0.03, 0.12) * (1.0 + height)]
        b.limb("bark_dry", origin, tip, radius * 0.22, 0.0,
               f"задир среза {index + 1}", segments=5)
    for index in range(rng.randint(3, 5)):
        az = 360.0 * index / 4 + rng.uniform(-25, 25)
        tip = droop_point([0.0, 0.0, 0.0], az, -72.0, radius * rng.uniform(1.6, 2.6))
        tip[2] = 0.0
        b.limb("bark", [0.0, 0.0, radius * 0.5], tip, radius * 0.4, radius * 0.12,
               f"корень пня {index + 1}")
    for index in range(rng.randint(1, 3)):
        az = rng.uniform(0, 360)
        spot = droop_point([0.0, 0.0, 0.0], az, -80.0, radius * rng.uniform(0.9, 1.5))
        spot[2] = height * rng.uniform(0.5, 0.95)
        b.blob("moss", spot, radius * rng.uniform(0.35, 0.6), f"мох на пне {index + 1}",
               scale=[1.0, 1.0, 0.5], segments=7, rings=4, jitter=0.008)
    b.ground()
    return {
        "parts": b.parts, "size": b.size(), "budget": 500,
        "category": CATEGORY_GROUND,
        "bark_palette": rng.choice(["bark_brown_soft", "bark_red_soft", "wood_dark_soft"]),
        "bark_dry_palette": "dry_wood_soft",
        "needle_palette": "moss_green_soft",
        "collision": "mesh", "size_px": 128, "height": height,
    }


def fallen_log(rng):
    length = rng.uniform(1.4, 3.4)
    radius = rng.uniform(0.13, 0.30)
    taper = rng.uniform(0.05, 0.22)
    b = Builder(rng)
    axis_y = rng.uniform(-0.25, 0.25)
    p0 = [-length / 2, axis_y, radius * rng.uniform(0.9, 1.05)]
    p1 = [length / 2, axis_y + rng.uniform(-0.2, 0.2), radius * rng.uniform(0.75, 1.0)]
    b.limb("bark", p0, p1, radius, radius * (1.0 - taper), "бревно",
           segments=rng.randint(7, 9), jitter=0.006)
    # Рваные торцы.
    for side, base in ((0, p0), (1, p1)):
        for index in range(rng.randint(3, 5)):
            az = rng.uniform(0, 360)
            tip = droop_point(base, az, rng.uniform(-70, 70), radius * rng.uniform(0.2, 0.55))
            direction = -1 if side == 0 else 1
            tip[0] = base[0] + direction * rng.uniform(0.02, 0.10)
            b.limb("bark_dry", base, tip, radius * 0.28, 0.0,
                   f"задир торца {side + 1}.{index + 1}", segments=5)
    # Обломанные сучья и мох сверху.
    for index in range(rng.randint(2, 5)):
        t = rng.uniform(0.15, 0.85)
        origin = [p0[i] + (p1[i] - p0[i]) * t for i in range(3)]
        origin[2] = radius * 0.9
        az = rng.uniform(0, 360)
        tip = droop_point(origin, az, rng.uniform(10, 55), radius * rng.uniform(1.0, 2.2))
        b.limb("bark", origin, tip, radius * 0.22, 0.0, f"сук бревна {index + 1}",
               segments=5, jitter=0.004)
    for index in range(rng.randint(2, 4)):
        t = rng.uniform(0.2, 0.8)
        spot = [p0[0] + (p1[0] - p0[0]) * t + rng.uniform(-0.1, 0.1),
                p0[1] + (p1[1] - p0[1]) * t + rng.uniform(-0.08, 0.08),
                radius * rng.uniform(0.85, 1.15)]
        b.blob("moss", spot, radius * rng.uniform(0.3, 0.55), f"мох на бревне {index + 1}",
               scale=[1.5, 1.0, 0.45], segments=7, rings=4, jitter=0.008)
    b.ground()
    return {
        "parts": b.parts, "size": b.size(), "budget": 700,
        "category": CATEGORY_GROUND,
        "bark_palette": rng.choice(["bark_brown_soft", "dry_wood_soft", "bark_red_soft"]),
        "bark_dry_palette": "dry_wood_soft",
        "needle_palette": "moss_green_soft",
        "collision": "mesh", "size_px": 256 if length > 2.4 else 128, "height": radius * 2,
    }


def fern(rng):
    """Папоротник: дуговидные вайи с перьями по обе стороны стержня."""
    height = rng.uniform(0.40, 1.15)
    fronds = rng.randint(6, 10)
    b = Builder(rng)
    palette = rng.choice(["fern_green_soft", "leaf_green_soft", "moss_green_soft"])
    for index in range(fronds):
        az = 360.0 * index / fronds + rng.uniform(-18, 18)
        # Вайя встаёт вверх и лишь к концу поникает, поэтому крона объёмная.
        rise = rng.uniform(18, 38)
        length = height * rng.uniform(0.85, 1.15)
        base = [rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03), 0.0]
        mid = sprout_point(base, az, rise, length * 0.62)
        tip = droop_point(mid, az, rng.uniform(35, 65), length * 0.45)
        width = height * rng.uniform(0.055, 0.085)
        b.blade("needles", base, mid, width, width * 0.65, width * 0.45,
                f"вайя {index + 1} стержень 1")
        b.blade("needles", mid, tip, width * 0.65, width * 0.14, width * 0.38,
                f"вайя {index + 1} стержень 2")
        # Перья: лопасти по обе стороны от стержня, вдоль всей вайи.
        pinnae = rng.randint(7, 10)
        for p in range(pinnae):
            t = (p + 1) / (pinnae + 1)
            if t < 0.62:
                anchor = [base[i] + (mid[i] - base[i]) * (t / 0.62) for i in range(3)]
            else:
                u = (t - 0.62) / 0.38
                anchor = [mid[i] + (tip[i] - mid[i]) * u for i in range(3)]
            # Перья длиннее у основания вайи и короче к концу — как у настоящего.
            span = length * rng.uniform(0.26, 0.40) * (1.0 - 0.45 * t)
            for side in (-1, 1):
                side_az = az + side * rng.uniform(72, 104)
                # Лопасть встаёт боком: перья торчат вбок от стержня, а не
                # лежат в одной плоскости с ним.
                leaf_tip = droop_point(anchor, side_az, rng.uniform(-28, 6), span)
                b.blade("needles", anchor, leaf_tip, width * 0.46, width * 0.08,
                        width * 0.24, f"вайя {index + 1} перо {p + 1}.{side}",
                        roll=rng.uniform(55, 90))
    b.ground()
    return {
        "parts": b.parts, "size": b.size(), "budget": 2800,
        "category": CATEGORY_GROUND,
        "bark_palette": "wood_dark_soft", "bark_dry_palette": "dry_wood_soft",
        "needle_palette": palette,
        "collision": "none", "size_px": 128, "height": height,
    }


def grass_tuft(rng):
    height = rng.uniform(0.16, 0.65)
    blades = rng.randint(8, 18)
    b = Builder(rng)
    palette = rng.choice(["grass_green_soft", "reed_green_soft", "moss_green_soft"])
    dry = rng.random() < 0.3
    for index in range(blades):
        az = rng.uniform(0, 360)
        length = height * rng.uniform(0.6, 1.1)
        spread = rng.uniform(6, 42)
        origin = [rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), 0.0]
        tip = sprout_point(origin, az, spread, length)
        width = height * rng.uniform(0.022, 0.045)
        material = "grass_dry" if dry and rng.random() < 0.5 else "grass"
        b.blade(material, origin, tip, width, width * 0.15, width * 0.3,
                f"травина {index + 1}", jitter=0.004)
    b.ground()
    return {
        "parts": b.parts, "size": b.size(), "budget": 300,
        "category": CATEGORY_GROUND,
        "bark_palette": "wood_dark_soft",
        "bark_dry_palette": rng.choice(["leaf_yellow_soft", "dry_wood_soft"]),
        "needle_palette": palette,
        "collision": "none", "size_px": 64, "height": height,
    }


def reeds(rng):
    """Камыш: узкие листья плюс коричневые початки на верхушках."""
    height = rng.uniform(0.7, 1.9)
    stalks = rng.randint(4, 9)
    heads = rng.randint(1, 4)
    b = Builder(rng)
    palette = rng.choice(["reed_green_soft", "grass_green_soft"])
    tips = []
    for index in range(stalks):
        az = rng.uniform(0, 360)
        length = height * rng.uniform(0.7, 1.0)
        origin = [rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), 0.0]
        tip = sprout_point(origin, az, rng.uniform(4, 26), length)
        width = height * rng.uniform(0.014, 0.026)
        b.blade("grass", origin, tip, width, width * 0.4, width * 0.35,
                f"лист камыша {index + 1}", jitter=0.003)
        tips.append(tip)
    for index in range(heads):
        tip = tips[index % len(tips)]
        head_h = height * rng.uniform(0.10, 0.17)
        b.limb("reed_head", [tip[0], tip[1], tip[2]],
               [tip[0], tip[1], tip[2] + head_h],
               height * rng.uniform(0.016, 0.024), height * rng.uniform(0.012, 0.018),
               f"початок {index + 1}", segments=6, jitter=0.002)
    b.ground()
    return {
        "parts": b.parts, "size": b.size(), "budget": 300,
        "category": CATEGORY_GROUND,
        "bark_palette": "wood_dark_soft", "bark_dry_palette": "dry_wood_soft",
        "needle_palette": palette, "head_palette": "cattail_brown_soft",
        "collision": "none", "size_px": 128, "height": height,
    }


def mushroom(rng):
    """Грибная семейка: 1–4 шляпки разного размера на общем пятне."""
    b = Builder(rng)
    count = rng.randint(1, 4)
    scale = rng.uniform(0.04, 0.12)
    palette = rng.choice(["cap_red_soft", "cap_brown_soft", "leaf_yellow_soft"])
    for index in range(count):
        r = scale * rng.uniform(0.6, 1.3)
        az = rng.uniform(0, 360)
        dist = scale * rng.uniform(0.0, 1.6)
        cx, cy = dist * math.cos(math.radians(az)), dist * math.sin(math.radians(az))
        stem_h = r * rng.uniform(1.2, 2.0)
        b.limb("stem", [cx, cy, 0.0], [cx, cy, stem_h], r * 0.20, r * 0.16,
               f"ножка {index + 1}", segments=8, jitter=0.002)
        # scale — множитель радиуса, а не метры: 0.7 даёт купол высотой 0.7r.
        cap_ratio = rng.uniform(0.65, 0.95)
        b.blob("cap", [cx, cy, stem_h + r * cap_ratio * 0.55], r,
               f"шляпка {index + 1}",
               scale=[1.0, 1.0, cap_ratio], segments=rng.randint(9, 12), rings=6,
               jitter=0.004)
    b.ground()
    return {
        "parts": b.parts, "size": b.size(), "budget": 750,
        "category": CATEGORY_GROUND,
        "bark_palette": "wood_dark_soft", "bark_dry_palette": "dry_wood_soft",
        "needle_palette": palette, "stem_palette": "stem_cream_soft",
        "collision": "none", "size_px": 64, "height": scale * 2.4,
    }


def flower(rng):
    height = rng.uniform(0.14, 0.5)
    count = rng.randint(1, 4)
    b = Builder(rng)
    palette = rng.choice(["flower_purple_soft", "flower_white_soft",
                          "flower_yellow_soft", "berry_red_soft"])
    for index in range(count):
        az = rng.uniform(0, 360)
        dist = height * rng.uniform(0.0, 0.9)
        cx, cy = dist * math.cos(math.radians(az)), dist * math.sin(math.radians(az))
        stem_h = height * rng.uniform(0.7, 1.1)
        b.limb("stem", [cx, cy, 0.0], [cx, cy, stem_h], height * 0.018,
               height * 0.012, f"стебель {index + 1}", segments=5, jitter=0.002)
        b.blob("petal", [cx, cy, stem_h], height * rng.uniform(0.10, 0.18),
               f"венчик {index + 1}", scale=[1.0, 1.0, 0.7],
               segments=7, rings=4, jitter=0.005)
        for leaf in range(2):
            leaf_az = az + 120 + leaf * 120
            tip = droop_point([cx, cy, stem_h * rng.uniform(0.25, 0.45)], leaf_az,
                              rng.uniform(20, 55), height * rng.uniform(0.2, 0.35))
            b.blade("leaves", [cx, cy, stem_h * 0.35], tip, height * 0.05,
                    height * 0.015, height * 0.03, f"лист {index + 1}.{leaf + 1}")
    b.ground()
    return {
        "parts": b.parts, "size": b.size(), "budget": 200,
        "category": CATEGORY_GROUND,
        "bark_palette": "wood_dark_soft", "bark_dry_palette": "dry_wood_soft",
        "needle_palette": "leaf_green_soft", "petal_palette": palette,
        "collision": "none", "size_px": 64, "height": height,
    }


def berry_bush(rng):
    height = rng.uniform(0.30, 0.70)
    b = Builder(rng)
    stems = rng.randint(4, 7)
    tips = []
    for index in range(stems):
        az = 360.0 * index / stems + rng.uniform(-25, 25)
        length = height * rng.uniform(0.7, 1.0)
        tip = droop_point([0.0, 0.0, 0.0], az, rng.uniform(8, 40), length)
        b.limb("twig", [0.0, 0.0, 0.0], tip, height * 0.02, height * 0.008,
               f"побег {index + 1}", segments=5, jitter=0.003)
        tips.append(tip)
    for index, tip in enumerate(tips):
        b.blob("leaves", tip, height * rng.uniform(0.16, 0.26), f"листва {index + 1}",
               scale=[1.1, 1.1, 0.7], segments=7, rings=4, jitter=0.007)
    for index in range(rng.randint(6, 14)):
        tip = rng.choice(tips)
        spot = [tip[0] + rng.uniform(-0.12, 0.12), tip[1] + rng.uniform(-0.12, 0.12),
                tip[2] + rng.uniform(-0.10, 0.08)]
        b.blob("berry", spot, height * rng.uniform(0.035, 0.06),
               f"ягода {index + 1}", segments=6, rings=4, jitter=0.003)
    b.ground()
    return {
        "parts": b.parts, "size": b.size(), "budget": 700,
        "category": CATEGORY_GROUND,
        "bark_palette": "wood_dark_soft", "bark_dry_palette": "dry_wood_soft",
        "needle_palette": "leaf_green_soft", "berry_palette": "berry_red_soft",
        "collision": "none", "size_px": 128, "height": height,
    }


def rock(rng):
    """Валун: два-три наложенных сфероида с сильным jitter."""
    b = Builder(rng)
    size = rng.uniform(0.18, 0.85)
    count = rng.randint(1, 3)
    mossy = rng.random() < 0.5
    for index in range(count):
        r = size * rng.uniform(0.55, 1.0)
        az = rng.uniform(0, 360)
        dist = size * rng.uniform(0.0, 0.6) if count > 1 else 0.0
        center = [dist * math.cos(math.radians(az)), dist * math.sin(math.radians(az)),
                  r * rng.uniform(0.45, 0.65)]
        # Мало сегментов и крупный jitter дают читаемые плоские грани валуна.
        b.blob("stone", center, r, f"валун {index + 1}",
               scale=[rng.uniform(0.85, 1.25), rng.uniform(0.85, 1.25),
                      rng.uniform(0.45, 0.70)],
               segments=rng.randint(5, 7), rings=rng.randint(3, 4), jitter=0.045)
    if mossy:
        for index in range(rng.randint(2, 4)):
            az = rng.uniform(0, 360)
            r = size * rng.uniform(0.25, 0.5)
            spot = [r * math.cos(math.radians(az)) * rng.uniform(0.4, 1.0),
                    r * math.sin(math.radians(az)) * rng.uniform(0.4, 1.0),
                    size * rng.uniform(0.55, 0.95)]
            b.blob("moss", spot, r, f"мох на валуне {index + 1}",
                   scale=[1.2, 1.2, 0.35], segments=7, rings=4, jitter=0.015)
    b.ground()
    return {
        "parts": b.parts, "size": None, "budget": 400,
        "category": CATEGORY_GROUND,
        "bark_palette": "wood_dark_soft", "bark_dry_palette": "dry_wood_soft",
        "needle_palette": "moss_green_soft", "stone_palette": "stone_grey_soft",
        "collision": "convex", "size_px": 128, "height": size,
    }


FAMILIES = {
    "conifer": {
        "count": 16, "prefix": "conifer",
        "make": lambda rng: conifer(rng, rng.choice(CONIFER_SHAPES)),
    },
    "snag": {"count": 8, "prefix": "snag", "make": snag},
    "broadleaf": {
        "count": 10, "prefix": "broadleaf",
        "make": lambda rng: broadleaf(rng, rng.choice(BROADLEAF_SHAPES)),
    },
    "shrub": {"count": 6, "prefix": "shrub", "make": shrub},
    "stump": {"count": 3, "prefix": "stump", "make": stump},
    "log": {"count": 3, "prefix": "log", "make": fallen_log},
    "fern": {"count": 4, "prefix": "fern", "make": fern},
    "grass": {"count": 4, "prefix": "grass", "make": grass_tuft},
    "reed": {"count": 2, "prefix": "reed", "make": reeds},
    "mushroom": {"count": 4, "prefix": "mushroom", "make": mushroom},
    "flower": {"count": 4, "prefix": "flower", "make": flower},
    "berry": {"count": 2, "prefix": "berry", "make": berry_bush},
    "rock": {"count": 4, "prefix": "rock", "make": rock},
}

# Теги материалов -> (пресет, палитра, переопределения)
MATERIAL_RECIPES = {
    "bark": ("wood", {"scale": 5, "direction": "Z", "distortion": 2.0,
                      "contrast": 0.95, "brightness": 0.05, "ao": 0.35,
                      "ao_distance": 0.06, "edge": 0.16, "roughness": 0.95}),
    "bark_dry": ("wood", {"scale": 6, "direction": "Z", "distortion": 2.4,
                          "contrast": 0.85, "brightness": 0.04, "ao": 0.35,
                          "ao_distance": 0.05, "edge": 0.18, "roughness": 0.97}),
    "needles": ("noise", {"scale": 16, "detail": 5, "contrast": 1.15,
                          "brightness": 0.06, "ao": 0.3, "ao_distance": 0.04,
                          "edge": 0.18, "roughness": 0.92}),
    "leaves": ("noise", {"scale": 11, "detail": 4, "contrast": 1.1,
                         "brightness": 0.05, "ao": 0.32, "ao_distance": 0.05,
                         "edge": 0.15, "roughness": 0.92}),
    "twig": ("wood", {"scale": 9, "direction": "Z", "distortion": 1.6,
                      "contrast": 0.9, "ao": 0.35, "ao_distance": 0.03,
                      "edge": 0.14, "roughness": 0.96}),
    "moss": ("noise", {"scale": 22, "detail": 5, "contrast": 1.0,
                       "brightness": 0.05, "ao": 0.4, "ao_distance": 0.03,
                       "edge": 0.12, "roughness": 0.98}),
    "grass": ("noise", {"scale": 14, "detail": 3, "contrast": 1.05,
                        "brightness": 0.06, "ao": 0.3, "ao_distance": 0.03,
                        "edge": 0.16, "roughness": 0.94}),
    "grass_dry": ("noise", {"scale": 14, "detail": 3, "contrast": 0.95,
                            "brightness": 0.08, "ao": 0.3, "ao_distance": 0.03,
                            "edge": 0.16, "roughness": 0.95}),
    "reed_head": ("noise", {"scale": 20, "detail": 3, "contrast": 0.85,
                            "ao": 0.35, "ao_distance": 0.02, "roughness": 0.95}),
    "cap": ("noise", {"scale": 18, "detail": 3, "contrast": 1.0,
                      "brightness": 0.05, "ao": 0.3, "ao_distance": 0.02,
                      "edge": 0.14, "roughness": 0.85}),
    "stem": ("flat", {"value": 0.62, "contrast": 0.5, "brightness": 0.05,
                      "ao": 0.3, "ao_distance": 0.02, "roughness": 0.9}),
    "petal": ("noise", {"scale": 24, "detail": 2, "contrast": 0.9,
                        "brightness": 0.08, "ao": 0.28, "ao_distance": 0.02,
                        "roughness": 0.85}),
    "berry": ("noise", {"scale": 26, "detail": 2, "contrast": 1.0,
                        "brightness": 0.06, "ao": 0.3, "ao_distance": 0.02,
                        "roughness": 0.7}),
    "stone": ("stone", {"scale": 7, "contrast": 0.9, "ao": 0.4,
                        "ao_distance": 0.08, "edge": 0.18, "roughness": 0.96}),
}

PALETTE_KEYS = {
    "bark": "bark_palette",
    "bark_dry": "bark_dry_palette",
    "needles": "needle_palette",
    "leaves": "needle_palette",
    "twig": "bark_palette",
    "moss": "needle_palette",
    "grass": "needle_palette",
    "grass_dry": "bark_dry_palette",
    "reed_head": "head_palette",
    "cap": "needle_palette",
    "stem": "stem_palette",
    "petal": "petal_palette",
    "berry": "berry_palette",
    "stone": "stone_palette",
}


def texture_spec(name, recipe, seed):
    """Retro pixel filtering with soft palettes, matching recent dungeon props."""
    materials = {}
    for tag, (preset, overrides) in MATERIAL_RECIPES.items():
        if tag not in recipe["used_materials"]:
            continue
        key = PALETTE_KEYS.get(tag)
        palette = recipe.get(key) or "moss_green_soft"
        entry = {"preset": preset, "palette": palette}
        entry.update(overrides)
        materials[tag] = entry
    materials["default"] = {"preset": "flat", "palette": recipe["bark_palette"]}
    return {
        "asset": name,
        "size": recipe["size_px"],
        "seed": seed % 10000,
        "pixel": True,
        "quantize": True,
        "samples": 32,
        "margin": 3,
        "materials": materials,
    }


def build_spec(name, recipe, seed):
    used = []
    for part in recipe["parts"]:
        tag = part["material"]
        if tag not in used:
            used.append(tag)
    recipe["used_materials"] = used

    material_colors = {tag: MATERIAL_COLORS[tag] for tag in used}
    spec = {
        "name": name,
        "category": recipe["category"],
        "seed": seed % 100000,
        "pivot": "bottom_center",
        "tri_budget": recipe["budget"],
        "collision": recipe["collision"],
        "materials": material_colors,
        "parts": recipe["parts"],
    }
    # Габарит не заявляем, когда он заведомо неточен: у камней это несколько
    # перекрывающихся сфер с крупным jitter, и Blender даёт другой bbox.
    if recipe["size"]:
        spec["expected_size"] = recipe["size"]
    return spec, texture_spec(name, recipe, seed)


MATERIAL_COLORS = {
    "bark": "#463525",
    "bark_dry": "#514537",
    "needles": "#2f4d33",
    "leaves": "#3f652e",
    "twig": "#3a2c1e",
    "moss": "#374f29",
    "grass": "#3f612d",
    "grass_dry": "#816a1d",
    "reed_head": "#452f1e",
    "cap": "#852e1f",
    "stem": "#908773",
    "petal": "#553773",
    "berry": "#6f2521",
    "stone": "#505158",
}


def generate(family, count, seed, start_index):
    """Yield (spec, texture, path) for ``count`` variants of one family."""
    config = FAMILIES[family]
    rng = random.Random(seed)
    made = []
    for index in range(count):
        recipe = config["make"](rng)
        name = f"{config['prefix']}_{start_index + index + 1:02d}"
        spec, texture = build_spec(name, recipe, seed + index * 977)
        made.append((name, spec, texture))
    return made


def write_specs(entries, force):
    written, skipped = [], []
    for name, spec, texture in entries:
        model_path = MODELS / f"{name}.json"
        texture_path = TEXTURES / f"{name}.json"
        if model_path.exists() and not force:
            skipped.append(name)
            continue
        model_path.parent.mkdir(parents=True, exist_ok=True)
        texture_path.parent.mkdir(parents=True, exist_ok=True)
        model_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
        texture_path.write_text(json.dumps(texture, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
        written.append(name)
    return written, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--family", action="append", choices=sorted(FAMILIES),
                        help="family to generate; repeatable")
    parser.add_argument("--all", action="store_true", help="generate every family")
    parser.add_argument("--count", type=int, help="override the variant count per family")
    parser.add_argument("--seed", type=int, default=20261116)
    parser.add_argument("--force", action="store_true", help="overwrite existing specs")
    parser.add_argument("--dry-run", action="store_true", help="print names only")
    parser.add_argument("--list", action="store_true", help="list families and exit")
    args = parser.parse_args()

    if args.list:
        for family, config in sorted(FAMILIES.items()):
            print(f"{family:10s} default count {config['count']:2d}  prefix {config['prefix']}")
        return

    families = sorted(FAMILIES) if args.all else (args.family or [])
    if not families:
        parser.error("pass --family <name>, several times, or --all (see --list)")

    entries = []
    for family in families:
        count = args.count or FAMILIES[family]["count"]
        start = FAMILIES[family].get("start_index", 0)
        entries += generate(family, count, args.seed, start)

    if args.dry_run:
        for name, spec, _ in entries:
            print(f"{name:18s} parts {len(spec['parts']):3d}  size {spec['expected_size']}")
        print(f"total {len(entries)} assets")
        return

    written, skipped = write_specs(entries, args.force)
    print(f"wrote {len(written)} model+texture spec pairs")
    if skipped:
        print(f"skipped {len(skipped)} existing (use --force): {', '.join(skipped)}")


if __name__ == "__main__":
    main()

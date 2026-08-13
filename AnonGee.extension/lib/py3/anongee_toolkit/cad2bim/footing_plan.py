# -*- coding: utf-8 -*-
"""Work out WHERE the foundation pads go and how deep, before Revit is touched.

Two things the builder cannot decide on its own:

  * COMBINED PADS. Two columns close together get two pads that overlap, and
    Revit will happily place one floor on top of another. Real practice is a
    single COMBINED footing spanning both, so overlapping pads are merged into
    one rectangle covering the group.

  * DEPTH FROM AREA. A pad's thickness follows its plan area -- a small pad
    under one column does not need the depth of a big combined one. The depth on
    the dialog is the depth at one square metre and it scales with the square
    root of the area (the same way a pad's bending demand does), clamped so it
    never runs away in either direction, and rounded to a buildable 50mm.

Revit-free, so both can be unit-tested and replayed offline.
"""

import math

from . import config

_MM = config.MM_PER_FT

_DEPTH_STEP_MM = 50.0       # pads are cast in 50mm steps, not to the millimetre
_DEPTH_MIN_FACTOR = 0.5     # never thinner than half the nominal depth
_DEPTH_MAX_FACTOR = 2.0     # ... nor more than twice it
_MERGE_TOL_FT = 1.0 / _MM   # pads touching within a millimetre are one pad


class Pad(object):
    """One foundation pad: an oriented rectangle and the columns under it."""

    def __init__(self, cx, cy, half_long, half_short, angle_deg, marks=None):
        self.cx = cx
        self.cy = cy
        self.half_long = half_long
        self.half_short = half_short
        self.angle_deg = angle_deg
        self.marks = list(marks or [])

    @property
    def area_m2(self):
        return (2.0 * self.half_long * _MM / 1000.0) * (2.0 * self.half_short
                                                        * _MM / 1000.0)

    def ring(self):
        """The pad's four corners, counterclockwise, in internal feet."""
        angle = math.radians(self.angle_deg)
        ux, uy = math.cos(angle), math.sin(angle)
        nx, ny = -uy, ux
        return [(self.cx + ux * self.half_long + nx * self.half_short,
                 self.cy + uy * self.half_long + ny * self.half_short),
                (self.cx - ux * self.half_long + nx * self.half_short,
                 self.cy - uy * self.half_long + ny * self.half_short),
                (self.cx - ux * self.half_long - nx * self.half_short,
                 self.cy - uy * self.half_long - ny * self.half_short),
                (self.cx + ux * self.half_long - nx * self.half_short,
                 self.cy + uy * self.half_long - ny * self.half_short)]

    def bounds(self):
        xs = [p[0] for p in self.ring()]
        ys = [p[1] for p in self.ring()]
        return min(xs), min(ys), max(xs), max(ys)

    def mark(self):
        """"F-C1" for one column, "F-C1+C2" for a combined pad."""
        named = [m for m in self.marks if m]
        if not named:
            return None
        return "F-{0}".format("+".join(named[:4]))

    def __repr__(self):
        return "<Pad {0:.0f}x{1:.0f}mm at ({2:.0f}, {3:.0f}) {4}>".format(
            2 * self.half_long * _MM, 2 * self.half_short * _MM,
            self.cx * _MM, self.cy * _MM, self.mark() or "")


def pads_for(sections, projection_mm, region_max_side_mm, oversized=None):
    """One Pad per column footprint, before any merging.

    `oversized` collects the footprints the size filter rejects. The filter
    itself is right for this path -- a lift or stair region grown by a
    projection is not a pad -- but it used to reject in silence, so a raft-sized
    region drawn on the column layer produced no foundation and no explanation.
    A drawing that carries its own foundation layer never reaches here at all;
    one that does not now at least says what it declined to invent.
    """
    projection_ft = float(projection_mm or 0.0) / _MM
    pads = []
    for entry in (sections.get("entries") or []):
        for rectangle in (entry.get("rectangles") or []):
            width_mm = rectangle["width_mm"]
            height_mm = rectangle["height_mm"]
            if min(width_mm, height_mm) > region_max_side_mm:
                if oversized is not None:
                    oversized.append(
                        "{0:.0f} x {1:.0f} mm region is wider than a column "
                        "({2:.0f} mm): no pad invented for it".format(
                            max(width_mm, height_mm), min(width_mm, height_mm),
                            region_max_side_mm))
                continue                 # a lift/stair region, not a column
            angle = rectangle.get("long_axis_deg")
            if angle is None:
                angle = 0.0 if width_mm >= height_mm else 90.0
            pads.append(Pad(rectangle["center"][0], rectangle["center"][1],
                            (max(width_mm, height_mm) / _MM) / 2.0 + projection_ft,
                            (min(width_mm, height_mm) / _MM) / 2.0 + projection_ft,
                            angle, [rectangle.get("mark")]))
    for circle in (sections.get("circles") or []):
        half = (circle["diameter_mm"] / _MM) / 2.0 + projection_ft
        pads.append(Pad(circle["center"][0], circle["center"][1], half, half,
                        0.0, [circle.get("mark")]))
    return pads


def _overlap(a, b):
    """True when two pads' footprints intersect (bounding boxes, with slop).

    Bounding boxes rather than exact oriented rectangles: a pad whose box
    overlaps another's is close enough that one combined footing is what an
    engineer would draw, and the merged pad is a box anyway.
    """
    ax0, ay0, ax1, ay1 = a.bounds()
    bx0, by0, bx1, by1 = b.bounds()
    return not (ax1 < bx0 - _MERGE_TOL_FT or bx1 < ax0 - _MERGE_TOL_FT
                or ay1 < by0 - _MERGE_TOL_FT or by1 < ay0 - _MERGE_TOL_FT)


def merge_overlapping(pads):
    """Fuse every group of overlapping pads into ONE combined pad.

    Merging is transitive -- three columns in a row give one pad, not two --
    and repeats until nothing more overlaps, because a merged pad is bigger
    than its parts and can reach a pad neither parent touched.

    A group whose members share an orientation keeps it; a mixed group falls
    back to an axis-aligned box, which is what a combined footing under
    differently-turned columns is drawn as anyway.
    """
    pads = list(pads)
    changed = True
    while changed:
        changed = False
        parent = list(range(len(pads)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(pads)):
            for j in range(i + 1, len(pads)):
                if find(i) != find(j) and _overlap(pads[i], pads[j]):
                    parent[find(i)] = find(j)
                    changed = True
        if not changed:
            break
        groups = {}
        for i in range(len(pads)):
            groups.setdefault(find(i), []).append(pads[i])
        pads = [_combine(group) for group in groups.values()]
    return pads


def _combine(group):
    """One pad covering `group`; the group itself when it holds a single pad."""
    if len(group) == 1:
        return group[0]
    angles = set(round((p.angle_deg % 180.0) / 5.0) for p in group)
    marks = []
    for pad in group:
        marks.extend(pad.marks)
    if len(angles) == 1:
        # all turned the same way: measure the union IN that frame, so a pair of
        # rotated columns gets a rotated combined pad rather than a bigger box
        angle = group[0].angle_deg
        radians = math.radians(angle)
        ux, uy = math.cos(radians), math.sin(radians)
        nx, ny = -uy, ux
        us, vs = [], []
        for pad in group:
            for x, y in pad.ring():
                us.append(x * ux + y * uy)
                vs.append(x * nx + y * ny)
        cu, cv = (min(us) + max(us)) / 2.0, (min(vs) + max(vs)) / 2.0
        return Pad(cu * ux + cv * nx, cu * uy + cv * ny,
                   (max(us) - min(us)) / 2.0, (max(vs) - min(vs)) / 2.0,
                   angle, marks)
    xs, ys = [], []
    for pad in group:
        x0, y0, x1, y1 = pad.bounds()
        xs += [x0, x1]
        ys += [y0, y1]
    return Pad((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0,
               (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0, 0.0, marks)


def depth_for(area_m2, nominal_mm):
    """The pad thickness for a plan area, in millimetres.

    `nominal_mm` is the depth at one square metre; a bigger pad spans further
    and gets deeper, following the square root of the area, clamped to half and
    twice the nominal and rounded to a buildable 50mm step.
    """
    nominal = float(nominal_mm or 0.0)
    if nominal <= 0:
        return 0.0
    raw = nominal * math.sqrt(max(area_m2, 0.0))
    low, high = nominal * _DEPTH_MIN_FACTOR, nominal * _DEPTH_MAX_FACTOR
    clamped = min(max(raw, low), high)
    return round(clamped / _DEPTH_STEP_MM) * _DEPTH_STEP_MM


def plan_pads(sections, projection_mm, depth_mm, region_max_side_mm,
              oversized=None):
    """[(ring, thickness_mm, mark)] -- every pad, merged and sized, ready to place."""
    pads = merge_overlapping(pads_for(sections, projection_mm,
                                      region_max_side_mm, oversized))
    out = []
    for pad in pads:
        out.append((pad.ring(), depth_for(pad.area_m2, depth_mm), pad.mark()))
    return out

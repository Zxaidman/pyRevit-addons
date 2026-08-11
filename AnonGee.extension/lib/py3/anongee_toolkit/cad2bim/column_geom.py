# -*- coding: utf-8 -*-
"""Column primitives shared by detection, recovery and the beam passes.

Small, dependency-light helpers that all three ends of the column pipeline
need: is this ring closed, where does this rectangle sit as a FOOTPRINT, what
size does this label claim. They live here so the bigger modules can import
them without importing each other.

Two footprint conventions meet in this file and both are load-bearing:

  * a PLAIN rectangle has no `long_axis_deg`, and its width/height are the x/y
    extents as drawn;
  * an ORIENTED one carries its SMALL side as the width and its long side along
    the angle -- which is how the column builder places it.

`_column_footprints` normalises both into ("rect", cx, cy, cos, sin, half_long,
half_short), the form every overlap test in the package expects.
"""

import math

from . import config
from .classify.layers import CATEGORY_COLUMN

_MM = config.MM_PER_FT

_CLOSE_TOL_FT = 1.0e-3       # ~0.3 mm: ring is closed when its ends meet this close

def _ring_closed(points):
    """True if a polyline's first and last vertices coincide (a closed ring).

    Both readers mark closure this way: the DXF reader appends the start point to
    a closed LWPOLYLINE/POLYLINE, and Revit's PolyLine repeats the start for a
    closed loop. A polyline whose ends do NOT meet is an open path -- at a
    beam-column junction that means a partial outline (an L/U/-shaped fragment),
    NOT a column to be auto-closed into a (wrong, undersized) rectangle.
    """
    if len(points) < 4:
        return False
    a, b = points[0], points[-1]
    return abs(a[0] - b[0]) <= _CLOSE_TOL_FT and abs(a[1] - b[1]) <= _CLOSE_TOL_FT


def _inside_rectangles(cx, cy, rectangles):
    """True if (cx, cy) falls within any rectangle's axis-aligned bbox."""
    for rect in rectangles:
        if rect.x_min <= cx <= rect.x_max and rect.y_min <= cy <= rect.y_max:
            return True
    return False


def _bbox_half(rect):
    """Axis-aligned half-extents (hx, hy) in feet of a possibly-rotated column rect."""
    theta = math.radians(rect.get("long_axis_deg", 90.0))
    long_ft, short_ft = rect["height_ft"], rect["width_ft"]
    hx = (abs(math.cos(theta)) * long_ft + abs(math.sin(theta)) * short_ft) / 2.0
    hy = (abs(math.sin(theta)) * long_ft + abs(math.cos(theta)) * short_ft) / 2.0
    return hx, hy


def _label_size(text, schedule):
    """(small, big) mm for a label, or None.

    Precedence: the inline size ("B1 300x600") first, then schedule[mark], then
    the label's parenthesised SCHEDULE KEY -- "B20(c)" is sized by the (c) row
    of a MARK/SIZE table. Every element type resolves through here, so columns,
    beams and slabs all understand the keyed convention.
    """
    if text.b_mm is not None and text.h_mm is not None:
        return (min(text.b_mm, text.h_mm), max(text.b_mm, text.h_mm))
    if text.mark and text.mark in schedule:
        b, h = schedule[text.mark]
        return (min(b, h), max(b, h))
    key = getattr(text, "size_key", None)
    if key and key in schedule:
        b, h = schedule[key]
        return (min(b, h), max(b, h))
    return None


# Column-LAYER outline rectangles used as obstacles even when no column got placed
# (blade columns like test8's 250x3250 slanted rects exceed the column limits and are
# dropped -- but a beam still must not be drawn over them).
_OBSTACLE_SHORT_MIN_MM = 100.0     # a closed rect thinner than this is stray linework


_OBSTACLE_SHORT_MAX_MM = 1000.0    # ...wider than this is a room/void outline, not a column


_OBSTACLE_LONG_MAX_MM = 6000.0     # ...longer than this is a core wall, not a blade column


def _distinct_ring_corners(points, tol_ft):
    """First-visit distinct vertices of a (possibly retraced) closed polyline."""
    corners = []
    for p in points:
        for q in corners:
            if abs(p[0] - q[0]) <= tol_ft and abs(p[1] - q[1]) <= tol_ft:
                break
        else:
            corners.append((p[0], p[1]))
    return corners


def column_outline_footprints(records, placed_footprints=None):
    """Obstacle footprints from CLOSED RECTANGULAR column-layer outlines.

    Column detection enforces schedule-plausible size limits, so a blade column
    (test8: 250x3250, slanted, drawn with a diagonal marker stroke) is dropped and
    never placed -- yet the beam layer re-traces its outline and the derived beams
    would be DRAWN ON TOP of the (real, just unplaced) column. Every column-layer
    polyline whose distinct vertices form one clean rectangle (opposite sides equal,
    corners square) within blade-column bounds becomes a ("rect", ...) footprint for
    split_beams_at_columns, whether or not a column got placed there. Fragmented or
    L/C-shaped core outlines never qualify -- deliberately conservative.
    """
    tol_ft = config.mm_to_ft(1.0)
    short_min = config.mm_to_ft(_OBSTACLE_SHORT_MIN_MM)
    short_max = config.mm_to_ft(_OBSTACLE_SHORT_MAX_MM)
    long_max = config.mm_to_ft(_OBSTACLE_LONG_MAX_MM)
    side_tol = config.mm_to_ft(20.0)
    out = []
    for record in records:
        if record.category != CATEGORY_COLUMN or record.kind != "polyline":
            continue
        if len(record.points) < 4:
            continue
        corners = _distinct_ring_corners(record.points, tol_ft)
        if len(corners) != 4:
            continue
        (ax, ay), (bx, by), (cx2, cy2), (dx2, dy2) = corners
        e1 = (bx - ax, by - ay)
        e2 = (cx2 - bx, cy2 - by)
        e3 = (dx2 - cx2, dy2 - cy2)
        e4 = (ax - dx2, ay - dy2)
        l1 = (e1[0] ** 2 + e1[1] ** 2) ** 0.5
        l2 = (e2[0] ** 2 + e2[1] ** 2) ** 0.5
        l3 = (e3[0] ** 2 + e3[1] ** 2) ** 0.5
        l4 = (e4[0] ** 2 + e4[1] ** 2) ** 0.5
        if min(l1, l2, l3, l4) <= 0:
            continue
        if abs(l1 - l3) > side_tol or abs(l2 - l4) > side_tol:
            continue
        if abs(e1[0] * e2[0] + e1[1] * e2[1]) / (l1 * l2) > 0.035:   # ~2 deg off square
            continue
        short, long_ = min(l1, l2), max(l1, l2)
        if not (short_min <= short <= short_max) or long_ > long_max:
            continue
        cx = (ax + cx2) / 2.0
        cy = (ay + cy2) / 2.0
        if l1 >= l2:
            ca, sa = e1[0] / l1, e1[1] / l1
        else:
            ca, sa = e2[0] / l2, e2[1] / l2
        out.append(("rect", cx, cy, ca, sa, long_ / 2.0, short / 2.0))
    return out


def _column_footprints(sections, circles):
    """Every column footprint, as ("circle", cx, cy, r) or
    ("rect", cx, cy, cos, sin, half_long, half_short) with the LONG half-extent
    along `long_axis_deg` -- the same convention the column builder places by
    (small side b across, big side h along the long axis)."""
    out = []
    for circle in (circles or []):
        cx, cy, _cz = circle["center"]
        out.append(("circle", cx, cy, circle["diameter_ft"] / 2.0))
    for entry in sections.get("entries", []):
        for rect in entry["rectangles"]:
            w = rect["width_mm"] / _MM
            h = rect["height_mm"] / _MM
            deg = rect.get("long_axis_deg")
            if deg is None:
                deg = 0.0 if w >= h else 90.0   # placement default (builders/columns)
            cx, cy, _cz = rect["center"]
            theta = math.radians(deg)
            out.append(("rect", cx, cy, math.cos(theta), math.sin(theta),
                        max(w, h) / 2.0, min(w, h) / 2.0))
    return out


def column_trim_footprints(sections):
    """PLACED columns -- rects AND round -- as footprint tuples.

    The slab member-edge source uses these to replace raw column-layer linework
    with exact rings (columns become TRIM geometry for the beam-outline graph);
    round columns especially arrive as dozens of tiny drawn arc fragments."""
    return _column_footprints(sections, sections.get("circles"))

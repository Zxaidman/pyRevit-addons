# -*- coding: utf-8 -*-
"""Plan STAIRCASES from the CAD plan -- both of the user's two source modes.

Option 2, STAIR LINEWORK (preferred when the plan has a stair layer): the
S-STRS riser lines say exactly where the runs are. Riser lines cluster into
stairs, group into RUNS (parallel, equidistant, overlapping spans); the tread
is the drawn spacing, the run width the drawn riser length, the riser count
per run the drawn line count, and the riser height storey / total drawn
risers. The landing is the drawn leftover space next to the riser extent.
The user's dialog numbers back-fill anything the linework cannot say.

Option 1, TEXT ONLY (fallback, plans like test1-3 whose stair layer is off or
missing): a STAIRCASE / ST-1 text marks WHERE a stair lives; the bay that
contains the text -- a bounded face of the placed beams + walls, from the same
machinery the slabs use -- is the stair's area. Inside that area a generic
DOG-LEG (two parallel runs + one half landing) is laid out from the user's
numbers: target riser height, tread depth, run width and landing depth. The
storey height (base to top level) fixes the riser count; the actual riser is
storey / count (never above the target).

Revit-free (no Revit imports) so the layout can be unit-tested and replayed
against the JSON exports offline; builders/stairs.py turns the plans into
Revit stairs inside a StairsEditScope.
"""

import math
import re
from collections import defaultdict

from . import config
from . import slab_outlines
from .classify.layers import CATEGORY_STAIR

_MM = config.MM_PER_FT
_dist = slab_outlines._dist

# "STAIRCASE" / "STAIR" / "STAIRS" / "ST-1" / "ST1" / "ST 2" -- the note that sits
# inside the stair bay on the plan (any text layer; content decides, like slabs).
_STAIR_TEXT = re.compile(r"^\s*(?:STAIRS?CASE|STAIRS?|ST[-_ ]?(\d+))\s*$", re.IGNORECASE)
# "DN" / "DN." / "UP" -- the run direction note; DN sits at the TOP of the flight.
_DIR_TEXT = re.compile(r"^\s*(DN|UP)\.?\s*$", re.IGNORECASE)


def apply_tolerances(tolerances):
    """Override the module's tunables from the dialog's Tolerances tab.

    Called once per run by the pushbutton; anything absent keeps its default so
    the offline tests and replays are unaffected.
    """
    global _CLUSTER_GAP_MM, _TREAD_MIN_MM, _TREAD_MAX_MM, _ARRIVAL_MERGE_GAP_MM
    if not tolerances:
        return
    _CLUSTER_GAP_MM = float(tolerances.get("stair_cluster_mm", _CLUSTER_GAP_MM))
    _TREAD_MIN_MM = float(tolerances.get("stair_tread_min_mm", _TREAD_MIN_MM))
    _TREAD_MAX_MM = float(tolerances.get("stair_tread_max_mm", _TREAD_MAX_MM))
    _ARRIVAL_MERGE_GAP_MM = float(tolerances.get("stair_arrival_merge_mm",
                                                 _ARRIVAL_MERGE_GAP_MM))


_MIN_STAIR_AREA_M2 = 4.0     # a bay smaller than this cannot hold a real stair
_MAX_STAIR_AREA_M2 = 60.0    # bigger than this is a floor plate, not a stair bay


def stair_label(text):
    """The stair mark for a stair note ("ST-1" -> "ST-1", "STAIRCASE" -> "ST"),
    or None when the text is not a stair note."""
    match = _STAIR_TEXT.match(text or "")
    if not match:
        return None
    number = match.group(1)
    return "ST-{0}".format(number) if number else "ST"


def direction_label(text):
    """"DN" / "UP" for a run-direction note, or None."""
    match = _DIR_TEXT.match(text or "")
    return match.group(1).upper() if match else None


def find_stair_texts(texts):
    """[(x_ft, y_ft, mark)] for every stair note with an internal point."""
    out = []
    for t in texts:
        mark = stair_label(getattr(t, "text", None))
        p = getattr(t, "point_internal", None)
        if mark and p is not None:
            out.append((p[0], p[1], mark))
    return out


def find_direction_texts(texts):
    """[(x_ft, y_ft, "DN"|"UP")] for every run-direction note."""
    out = []
    for t in texts:
        label = direction_label(getattr(t, "text", None))
        p = getattr(t, "point_internal", None)
        if label and p is not None:
            out.append((p[0], p[1], label))
    return out


def stair_areas_from_texts(records, beam_segments, column_rects, texts):
    """[(ring, z, mark)] -- the bounded face under each stair note.

    The faces come from the placed-members machinery with `keep_points` so the
    wall-bounded stair bay is not discarded as a shaft. A note whose face cannot
    be found (or is implausibly small/large) is reported in `notes` instead of
    silently dropped: returns (areas, notes).
    """
    stair_pts = find_stair_texts(texts)
    if not stair_pts:
        return [], ["no STAIRCASE/ST-n text on the plan"]
    loops = slab_outlines.slab_loops_from_placed_members(
        records, beam_segments, column_rects=column_rects,
        keep_points=[(x, y) for x, y, _m in stair_pts])
    areas = []
    notes = []
    min_ft2 = _MIN_STAIR_AREA_M2 * (1000.0 / _MM) ** 2
    max_ft2 = _MAX_STAIR_AREA_M2 * (1000.0 / _MM) ** 2
    for x, y, mark in stair_pts:
        hit = None
        for ring, z, _arcs in loops:
            if slab_outlines._point_in_ring((x, y), ring):
                hit = (ring, z)
                break
        if hit is None:
            notes.append("{0}: no closed bay found around the text".format(mark))
            continue
        area = abs(slab_outlines._signed_area(hit[0]))
        if area < min_ft2 or area > max_ft2:
            notes.append("{0}: bay area {1:.1f} m2 outside {2}-{3} m2".format(
                mark, area * (_MM / 1000.0) ** 2,
                int(_MIN_STAIR_AREA_M2), int(_MAX_STAIR_AREA_M2)))
            continue
        areas.append((hit[0], hit[1], mark))
    return areas, notes


def _oriented_extents(ring):
    """((cx, cy), (ux, uy), long_extent, short_extent) of the ring's best box.

    The box axis follows the ring's LONGEST edge (stair bays are rectangles or
    near-rectangles; the dominant wall direction is the run direction).
    """
    best_len = -1.0
    ux, uy = 1.0, 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        length = math.hypot(x2 - x1, y2 - y1)
        if length > best_len:
            best_len = length
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
    us = [p[0] * ux + p[1] * uy for p in ring]
    vs = [-p[0] * uy + p[1] * ux for p in ring]
    u0, u1 = min(us), max(us)
    v0, v1 = min(vs), max(vs)
    cu, cv = (u0 + u1) / 2.0, (v0 + v1) / 2.0
    cx = cu * ux - cv * uy
    cy = cu * uy + cv * ux
    if (u1 - u0) >= (v1 - v0):
        return (cx, cy), (ux, uy), (u1 - u0), (v1 - v0)
    return (cx, cy), (-uy, ux), (v1 - v0), (u1 - u0)


# The generic shapes the dialog offers when the CAD has no stair linework.
SHAPE_U = "u"                 # two parallel flights, half landing (dog-leg)
SHAPE_STRAIGHT = "straight"   # one flight end to end
SHAPE_L = "l"                 # two flights at 90 degrees, corner landing
SHAPE_C = "c"                 # three flights around three sides of the bay
SHAPE_CIRCULAR = "circular"   # one spiral flight around the bay's centre
STAIR_SHAPES = (SHAPE_U, SHAPE_STRAIGHT, SHAPE_L, SHAPE_C, SHAPE_CIRCULAR)


def plan_shaped_stair(ring, z, mark, params, storey_mm, direction_texts=None,
                      shape=SHAPE_U):
    """A generic stair of the requested SHAPE inside `ring` -> (plan, note).

    `shape` is one of STAIR_SHAPES; it is what the Staircase tab's shape picker
    sends when the drawing carries no stair linework to measure. Every shape
    shares the dialog numbers (riser height/count, tread, run width, landing,
    waist) and differs only in how the flights are laid inside the bay.
    """
    if shape == SHAPE_CIRCULAR:
        return _plan_circular_stair(ring, z, mark, params, storey_mm)
    if shape in (SHAPE_L, SHAPE_C):
        return _plan_cornered_stair(ring, z, mark, params, storey_mm, shape,
                                    direction_texts=direction_texts)
    return plan_dogleg_stair(ring, z, mark, params, storey_mm,
                             direction_texts=direction_texts,
                             single_flight=(shape == SHAPE_STRAIGHT))


def _riser_split(params, storey_mm, flights):
    """(risers_total, riser_mm, [per-flight riser counts]) for the dialog numbers."""
    riser_target = float(params.get("riser_mm") or 150.0)
    riser_count = int(params.get("riser_count") or 0)
    if riser_count > 0:
        total = riser_count
    else:
        total = int(math.ceil(storey_mm / riser_target - 1e-9))
    total = max(total, flights)
    base = total // flights
    extra = total - base * flights
    counts = [base + (1 if i < extra else 0) for i in range(flights)]
    return total, storey_mm / total, counts


def _plan_circular_stair(ring, z, mark, params, storey_mm):
    """One spiral flight around the bay's centre, sized by the dialog numbers."""
    tread = float(params.get("tread_mm") or 300.0)
    width = float(params.get("run_width_mm") or 1250.0)
    if storey_mm <= 0 or tread <= 0 or width <= 0:
        return None, "{0}: invalid inputs for a circular stair".format(mark)
    (cx, cy), _axis, long_mm, short_mm = _oriented_extents(ring)
    outer_mm = min(long_mm, short_mm) * _MM / 2.0
    if outer_mm <= width:
        return None, ("{0}: bay {1} mm across cannot hold a {2} mm wide spiral"
                      .format(mark, int(min(long_mm, short_mm) * _MM),
                              int(width)))
    risers_total, riser_mm, _counts = _riser_split(params, storey_mm, 1)
    inner_mm = outer_mm - width
    walk_mm = inner_mm + 300.0                    # tread measured on the walk line
    included = (risers_total * tread) / walk_mm   # radians
    if included > 2.0 * math.pi * 0.95:
        included = 2.0 * math.pi * 0.95
    spiral = {"center": (cx, cy), "radius": config.mm_to_ft(inner_mm + width / 2.0),
              "width_mm": width, "start_angle": 0.0,
              "included_angle": included, "clockwise": False,
              "risers": risers_total, "tread_mm": tread}
    plan = {"mark": mark, "z": z, "runs": [], "spiral": spiral,
            "landing": None, "top_landing": None,
            "risers_total": risers_total, "riser_mm": riser_mm,
            "tread_mm": tread, "run_width_mm": width,
            "landing_mm": float(params.get("landing_mm") or 0.0) or width,
            "waist_mm": float(params.get("waist_mm") or 0.0),
            "shape": SHAPE_CIRCULAR}
    return plan, None


def _plan_cornered_stair(ring, z, mark, params, storey_mm, shape,
                         direction_texts=None):
    """An L (two flights, one corner) or C (three flights, two corners) stair.

    The flights hug the bay's sides counterclockwise from its lower-left
    corner, each inset half a run width so the runs sit inside the boundary.
    """
    tread = float(params.get("tread_mm") or 300.0)
    width = float(params.get("run_width_mm") or 1250.0)
    landing = float(params.get("landing_mm") or 0.0) or width
    if storey_mm <= 0 or tread <= 0 or width <= 0:
        return None, "{0}: invalid inputs for an {1} stair".format(
            mark, shape.upper())
    flights = 2 if shape == SHAPE_L else 3
    risers_total, riser_mm, counts = _riser_split(params, storey_mm, flights)
    (cx, cy), (ux, uy), long_mm, short_mm = _oriented_extents(ring)
    nx, ny = -uy, ux
    half_long = long_mm / 2.0
    half_short = short_mm / 2.0
    inset = config.mm_to_ft(width / 2.0)

    def at(along_ft, across_ft):
        return (cx + ux * along_ft + nx * across_ft,
                cy + uy * along_ft + ny * across_ft)

    # flight 1 runs along the long axis on the near side, flight 2 up the far
    # short side, flight 3 (C only) back along the long axis on the far side
    corner_a = half_long - config.mm_to_ft(landing)
    corner_b = half_short - config.mm_to_ft(landing)
    legs = [
        (at(-half_long + inset, -half_short + inset), at(corner_a, -half_short + inset)),
        (at(half_long - inset, -half_short + inset), at(half_long - inset, corner_b)),
        (at(half_long - inset, half_short - inset), at(-corner_a, half_short - inset)),
    ][:flights]
    runs = []
    note = None
    for (start, end), risers in zip(legs, counts):
        span_mm = math.hypot(end[0] - start[0], end[1] - start[1]) * _MM
        needed = risers * tread
        if needed > span_mm + 1.0:
            note = ("{0}: {1} stair needs {2} mm per flight but the bay gives "
                    "{3} mm -- flights trimmed".format(mark, shape.upper(),
                                                       int(needed),
                                                       int(span_mm)))
            scale = span_mm / needed if needed else 1.0
            end = (start[0] + (end[0] - start[0]) * scale,
                   start[1] + (end[1] - start[1]) * scale)
        else:
            length_ft = config.mm_to_ft(needed)
            dx, dy = end[0] - start[0], end[1] - start[1]
            total = math.hypot(dx, dy)
            if total > 0:
                end = (start[0] + dx / total * length_ft,
                       start[1] + dy / total * length_ft)
        runs.append({"start": start, "end": end, "risers": risers,
                     "width_mm": width})
    plan = {"mark": mark, "z": z, "runs": runs, "landing": None,
            "top_landing": _arrival_landing(runs, landing),
            "risers_total": risers_total, "riser_mm": riser_mm,
            "tread_mm": tread, "run_width_mm": width, "landing_mm": landing,
            "waist_mm": float(params.get("waist_mm") or 0.0),
            "shape": shape}
    return plan, note


def plan_dogleg_stair(ring, z, mark, params, storey_mm, direction_texts=None,
                      single_flight=False):
    """One dog-leg stair plan inside `ring`, or (None, note) when it cannot fit.

    params (mm): riser_mm (target MAX riser height), tread_mm (tread depth),
    run_width_mm, landing_mm (landing depth along the run axis; 0/None -> run
    width). Returns (plan, note); `note` carries a warning even on success.

    Layout, in the ring's own oriented box (long axis = run axis):
        landing at the end NEAREST a DN/UP note (else the long-axis low end),
        two parallel runs side by side across the width, climbing FROM the far
        end TOWARD the landing, turning 180 degrees on it.
    Both run centrelines are what the builder feeds to Revit; riser counts per
    run and the exact riser height ride along.
    """
    riser_target = float(params.get("riser_mm") or 150.0)
    tread = float(params.get("tread_mm") or 300.0)
    width = float(params.get("run_width_mm") or 1250.0)
    landing = float(params.get("landing_mm") or 0.0) or width
    riser_count = int(params.get("riser_count") or 0)

    if storey_mm <= 0 or riser_target <= 0 or tread <= 0 or width <= 0:
        return None, "{0}: invalid inputs (storey {1} mm)".format(mark, int(storey_mm))
    # an explicit riser count is ABSOLUTE (the dialog syncs riser height to it);
    # otherwise the count comes from the target max riser height
    if riser_count > 0:
        risers_total = riser_count
    else:
        risers_total = int(math.ceil(storey_mm / riser_target - 1e-9))
    if risers_total < 2:
        risers_total = 2
    riser_actual = storey_mm / risers_total
    if single_flight:
        run1_risers, run2_risers = risers_total, 0
    else:
        run1_risers = int(math.ceil(risers_total / 2.0))
        run2_risers = risers_total - run1_risers

    (cx, cy), (ux, uy), long_mm, short_mm = _oriented_extents(ring)
    long_mm *= _MM
    short_mm *= _MM
    note = None
    if short_mm < 2.0 * width:
        note = "{0}: bay {1} mm across < 2 x run width {2} mm (runs squeezed)".format(
            mark, int(short_mm), int(width))
        width = short_mm / 2.0
    # a run with R risers spans R treads along the axis (Revit measures the same)
    run_len = max(run1_risers, run2_risers) * tread
    if run_len + landing > long_mm + 1.0:
        return None, ("{0}: needs {1} mm run + {2} mm landing but the bay is "
                      "{3} mm long".format(mark, int(run_len), int(landing),
                                           int(long_mm)))

    # landing end: nearest DN/UP note, else the low end of the long axis
    end_a = (cx - ux * long_mm / 2.0 / _MM, cy - uy * long_mm / 2.0 / _MM)
    end_b = (cx + ux * long_mm / 2.0 / _MM, cy + uy * long_mm / 2.0 / _MM)
    landing_end = end_a
    best = None
    for tx, ty, _lbl in (direction_texts or []):
        if not slab_outlines._point_in_ring((tx, ty), ring):
            continue
        for end in (end_a, end_b):
            d = math.hypot(tx - end[0], ty - end[1])
            if best is None or d < best:
                best = d
                landing_end = end
    sign = 1.0 if landing_end == end_a else -1.0
    # axis pointing FROM the far (start) end TOWARD the landing
    ax, ay = -ux * sign, -uy * sign
    nx, ny = -ay, ax                                  # across the bay
    lu = landing / _MM                                # landing depth, ft
    wu = width / _MM                                  # run width, ft
    far_u = long_mm / _MM / 2.0                       # centre -> either end
    # The two flights sit SIDE BY SIDE and centred across the bay, so both keep
    # the run width the dialog asked for and the landing spans exactly the pair.
    # (Pushing them out to the bay's edges instead stretched the stair to
    # whatever the drawn outline happened to be and left the landing adrift.)
    off1, off2 = wu / 2.0, -wu / 2.0
    if single_flight:
        off1 = off2 = 0.0
    # both runs anchor at the landing edge (axis coordinate far_u - lu from the
    # centre): run1 climbs INTO it, run2 leaves it climbing back -- a 180 turn
    def _at(s, off):
        return (cx + ax * s + nx * off, cy + ay * s + ny * off)

    turn_u = far_u - lu
    runs = []
    for risers, off, along in ((run1_risers, off1, 1.0), (run2_risers, off2, -1.0)):
        if risers <= 0:
            continue
        length_u = risers * tread / _MM
        if along > 0:
            start, end = _at(turn_u - length_u, off), _at(turn_u, off)
        else:
            start, end = _at(turn_u, off), _at(turn_u - length_u, off)
        runs.append({"start": start, "end": end, "risers": risers,
                     "width_mm": width})
    # the HALF landing fills the turn: from the last riser to the bay end,
    # spanning both flights (their outer edges), never the whole drawn bay
    half_span = (wu if not single_flight else wu / 2.0)
    landing_ring = None
    if not single_flight:
        landing_ring = [
            (_at(turn_u, 0.0)[0] + nx * half_span,
             _at(turn_u, 0.0)[1] + ny * half_span),
            (_at(turn_u + lu, 0.0)[0] + nx * half_span,
             _at(turn_u + lu, 0.0)[1] + ny * half_span),
            (_at(turn_u + lu, 0.0)[0] - nx * half_span,
             _at(turn_u + lu, 0.0)[1] - ny * half_span),
            (_at(turn_u, 0.0)[0] - nx * half_span,
             _at(turn_u, 0.0)[1] - ny * half_span)]
    plan = {"mark": mark, "z": z, "runs": runs, "landing": landing_ring,
            "top_landing": _arrival_landing(runs, landing),
            "risers_total": risers_total, "riser_mm": riser_actual,
            "tread_mm": tread, "run_width_mm": width, "landing_mm": landing,
            "waist_mm": float(params.get("waist_mm") or 0.0),
            "shape": SHAPE_STRAIGHT if single_flight else SHAPE_U}
    return plan, note


_ARRIVAL_MERGE_GAP_MM = 800.0   # runs this close across = one shared arrival slab


def _bridge_landings(run_dicts):
    """{after_run: ring} -- landings that BRIDGE two flights exactly.

    Revit's automatic landing squares itself to the run ends, which leaves a
    wedge of daylight against a FANNED flight whose outermost riser is angled
    (StaircasePlan-Test2's winder stairs: the tread and the landing did not
    meet). A bridge landing is the quadrilateral through the four ends of the
    two drawn risers it joins, so it shares an edge with each flight exactly.

    Only emitted where a fan is involved -- a pair of square flights is served
    perfectly well by the automatic landing, and this must not disturb them.
    """
    out = {}
    for index in range(len(run_dicts) - 1):
        first, second = run_dicts[index], run_dicts[index + 1]
        if not (first.get("fanned") or second.get("fanned")):
            continue
        top = _run_edge(first, "end")
        bottom = _run_edge(second, "start")
        if top is None or bottom is None:
            continue
        ring = _simple_quad(top + bottom)
        if ring is not None and abs(slab_outlines._signed_area(ring)) > 0:
            out[index] = ring
    return out


def _run_edge(run, which):
    """The two endpoints of the drawn riser at one end of a run, or None.

    Falls back to a square edge across the run for a flight with no drawn
    lines, so a fan can bridge to an ordinary straight flight.
    """
    lines = run.get("riser_lines")
    if lines:
        a, b = lines[-1] if which == "end" else lines[0]
        return [tuple(a), tuple(b)]
    sx, sy = run["start"]
    ex, ey = run["end"]
    length = math.hypot(ex - sx, ey - sy)
    if length <= 0:
        return None
    ax, ay = (ex - sx) / length, (ey - sy) / length
    nx, ny = -ay, ax
    half = (run["width_mm"] / _MM) / 2.0
    px, py = (ex, ey) if which == "end" else (sx, sy)
    return [(px + nx * half, py + ny * half), (px - nx * half, py - ny * half)]


def _simple_quad(points):
    """Order four points into a non-self-crossing ring, or None."""
    if len(points) != 4:
        return None
    cx = sum(p[0] for p in points) / 4.0
    cy = sum(p[1] for p in points) / 4.0
    ring = sorted(points, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    for i in range(4):
        if _dist(ring[i], ring[(i + 1) % 4]) < 1e-9:
            return None                  # degenerate: the two risers coincide
    return ring


def _arrival_landing(runs, depth_mm):
    """The ARRIVAL landing: a rectangle continuing past the last run's top end
    (the drawn plans show it; Revit's automatic landing only fills the turn).

    Width: in a U stair the arrival platform spans BOTH flights like the half
    landing does, so every run parallel to the last one and lying within
    _ARRIVAL_MERGE_GAP_MM across joins the slab's width. A winding stair's
    opposite flight sits across the WELL (a bigger gap), so there the slab
    stays one run wide."""
    if not runs:
        return None
    last = runs[-1]
    (sx, sy), (ex, ey) = last["start"], last["end"]
    length = math.hypot(ex - sx, ey - sy)
    if length <= 0:
        return None
    ax, ay = (ex - sx) / length, (ey - sy) / length
    nx, ny = -ay, ax
    gap_ft = config.mm_to_ft(_ARRIVAL_MERGE_GAP_MM)
    intervals = []
    for run in runs:
        (qsx, qsy), (qex, qey) = run["start"], run["end"]
        qlen = math.hypot(qex - qsx, qey - qsy)
        if qlen <= 0:
            continue
        qax, qay = (qex - qsx) / qlen, (qey - qsy) / qlen
        if abs(qax * ay - qay * ax) > 0.17:
            continue                    # not parallel to the last run
        mid_off = ((qsx + qex) / 2.0) * nx + ((qsy + qey) / 2.0) * ny
        hw = (run["width_mm"] / _MM) / 2.0
        intervals.append((mid_off - hw, mid_off + hw))
    last_off = ((sx + ex) / 2.0) * nx + ((sy + ey) / 2.0) * ny
    hw_last = (last["width_mm"] / _MM) / 2.0
    lo, hi = last_off - hw_last, last_off + hw_last
    changed = True
    while changed:
        changed = False
        for a, b in intervals:
            if a - gap_ft <= hi and lo - gap_ft <= b and (a < lo or b > hi):
                lo, hi = min(lo, a), max(hi, b)
                changed = True
    du = depth_mm / _MM
    near = _run_top_edge(last, (ex, ey), (ax, ay), (nx, ny),
                         lo - last_off, hi - last_off)
    return [near[0],
            (near[0][0] + ax * du, near[0][1] + ay * du),
            (near[1][0] + ax * du, near[1][1] + ay * du),
            near[1]]


def _run_top_edge(run, end, axis, normal, lo_off, hi_off):
    """The two points a landing must start from at the top of `run`.

    A straight flight ends on a riser square to its axis, so the landing's near
    edge is just the line through `end`. A FANNED flight ends on an ANGLED
    riser, and a square edge there leaves a wedge of daylight between the last
    tread and the landing -- so the drawn riser IS the near edge, extended to
    the landing's width.
    """
    ax, ay = axis
    nx, ny = normal
    lines = run.get("riser_lines") if run.get("fanned") else None
    if lines:
        a, b = lines[-1]
        # order the drawn ends across the run, then extend each to the landing
        if (a[0] * nx + a[1] * ny) > (b[0] * nx + b[1] * ny):
            a, b = b, a
        return (_extend_to_offset(a, b, axis, normal, lo_off, end),
                _extend_to_offset(b, a, axis, normal, hi_off, end))
    return ((end[0] + nx * lo_off, end[1] + ny * lo_off),
            (end[0] + nx * hi_off, end[1] + ny * hi_off))


def _extend_to_offset(point, other, axis, normal, offset, end):
    """`point` slid along the riser line until it sits `offset` across the run."""
    ax, ay = axis
    nx, ny = normal
    want = (end[0] * nx + end[1] * ny) + offset
    dx, dy = other[0] - point[0], other[1] - point[1]
    across = dx * nx + dy * ny
    if abs(across) < 1e-9:
        return (point[0] + nx * offset, point[1] + ny * offset)
    t = (want - (point[0] * nx + point[1] * ny)) / across
    return (point[0] + dx * t, point[1] + dy * t)


# ------------------------------------------------------- option 2: stair linework
_RISER_ANGLE_TOL = math.radians(3.0)
_RISER_MIN_LINES = 3          # fewer parallel lines than this is not a flight
_TREAD_MIN_MM = 150.0         # drawn riser spacing accepted as a tread
_TREAD_MAX_MM = 500.0
_CLUSTER_GAP_MM = 2000.0      # stair pieces closer than this belong together
_POSITION_DEDUPE_MM = 10.0    # the same riser drawn per-run appears twice
_MIN_STAIR_SPAN_MM = 1500.0   # a smaller cluster is an arrow/annotation glyph


def _stair_lines(records):
    """Straight (a, b) segments from the stair-layer records, with their z."""
    lines = []
    z = 0.0
    for record in records:
        if record.category != CATEGORY_STAIR or record.kind == "arc":
            continue
        pts = record.points
        z = pts[0][2] if pts else z
        for i in range(len(pts) - 1):
            a = (pts[i][0], pts[i][1])
            b = (pts[i + 1][0], pts[i + 1][1])
            if _dist(a, b) > config.mm_to_ft(50.0):
                lines.append((a, b))
    return lines, z


def _cluster_lines(lines, gap_ft):
    """Union-find the lines into stairs: bounding boxes closer than `gap_ft`."""
    boxes = []
    for a, b in lines:
        boxes.append((min(a[0], b[0]), min(a[1], b[1]),
                      max(a[0], b[0]), max(a[1], b[1])))
    parent = list(range(len(lines)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            bi, bj = boxes[i], boxes[j]
            if (bi[0] - gap_ft <= bj[2] and bj[0] - gap_ft <= bi[2] and
                    bi[1] - gap_ft <= bj[3] and bj[1] - gap_ft <= bi[3]):
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(len(lines)):
        groups[find(i)].append(lines[i])
    return list(groups.values())


def _riser_runs(lines):
    """RUNS from one stair's linework, EVERY direction considered.

    Riser lines bucket by direction; within a bucket, same-length lines whose
    ACROSS spans overlap belong to the same run; each run's riser positions
    (deduped -- the shared riser between adjacent panels is drawn once per
    panel) must be >= 3 and equidistant within tread limits. A dog-leg keeps
    one direction; a SQUARE stair (four flights around a well, Project1)
    contributes runs from two perpendicular directions.

    Returns [{"axis", "normal", "positions", "span_lo", "span_hi", "center"}]
    -- axis is the unit vector positions are measured along, normal the riser
    direction spans are measured along.
    """
    buckets = defaultdict(list)
    # a line's direction is unsigned, so the bucket key WRAPS: an angle just
    # under pi is the same direction as one just over zero. Without the wrap a
    # flight drawn with some risers "backwards" split into two buckets and lost
    # most of its lines (StaircasePlan-Test2's stairs).
    bucket_count = max(1, int(round(math.pi / _RISER_ANGLE_TOL)))
    for a, b in lines:
        ang = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        key = int(round(ang / _RISER_ANGLE_TOL)) % bucket_count
        buckets[key].append((a, b))
    runs = []
    dedupe_ft = config.mm_to_ft(_POSITION_DEDUPE_MM)
    for _key, bucket in sorted(buckets.items()):
        if len(bucket) < _RISER_MIN_LINES:
            continue
        # risers are same-length; a boundary line in the same direction (the
        # drawn landing edge, twice their length) would BRIDGE the run groups
        lengths = sorted(_dist(a, b) for a, b in bucket)
        median_len = lengths[len(lengths) // 2]
        bucket = [(a, b) for a, b in bucket
                  if 0.6 * median_len <= _dist(a, b) <= 1.4 * median_len]
        if len(bucket) < _RISER_MIN_LINES:
            continue
        a0, b0 = bucket[0]
        ang = math.atan2(b0[1] - a0[1], b0[0] - a0[0]) % math.pi
        dx, dy = math.cos(ang), math.sin(ang)      # along a riser line
        px, py = -dy, dx                           # the run axis
        items = []
        for a, b in bucket:
            pos = ((a[0] + b[0]) / 2.0) * px + ((a[1] + b[1]) / 2.0) * py
            lo = min(a[0] * dx + a[1] * dy, b[0] * dx + b[1] * dy)
            hi = max(a[0] * dx + a[1] * dy, b[0] * dx + b[1] * dy)
            items.append((pos, lo, hi))
        parent = list(range(len(items)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                lo = max(items[i][1], items[j][1])
                hi = min(items[i][2], items[j][2])
                shorter = min(items[i][2] - items[i][1],
                              items[j][2] - items[j][1])
                if shorter > 0 and (hi - lo) > 0.3 * shorter:
                    parent[find(i)] = find(j)
        grouped = defaultdict(list)
        for i in range(len(items)):
            grouped[find(i)].append(items[i])
        stray_ft = config.mm_to_ft(_TREAD_MIN_MM * 0.9)
        for group in grouped.values():
            merged = []
            for pos, lo, hi in sorted(group):
                # closer than a tread = the per-panel duplicate of the same
                # riser, or a stray near-parallel line -- one position only
                if merged and pos - merged[-1][0] <= stray_ft:
                    prev = merged[-1]
                    merged[-1] = (prev[0], min(prev[1], lo), max(prev[2], hi))
                else:
                    merged.append((pos, lo, hi))
            for chain in _equidistant_chains(merged):
                positions = [p for p, _lo, _hi in chain]
                # the flight's width is the TYPICAL riser span, not the union:
                # one line often runs past the flight (a U's bottom landing edge
                # crosses the well), and taking the extremes stretched the run
                # over that well and threw its centreline off (Test2 stair 1).
                lo, hi = _modal_span(chain)
                mid_pos = (positions[0] + positions[-1]) / 2.0
                mid_off = (lo + hi) / 2.0
                runs.append({"axis": (px, py), "normal": (dx, dy),
                             "positions": positions, "span_lo": lo,
                             "span_hi": hi,
                             "center": (px * mid_pos + dx * mid_off,
                                        py * mid_pos + dy * mid_off)})
    return runs + _fan_runs(lines, runs)


_FAN_MID_TOL_MM = 60.0        # a fan's midpoints stay this close to one line
_FAN_LENGTH_TOL = 0.30        # winder risers grow along the turn, but not wildly
_FAN_MIN_RISERS = 4           # fewer than this is noise, not a winder flight
_FAN_MIN_TURN = math.radians(12.0)   # a fan TURNS; a straight flight does not


def _fan_runs(lines, runs):
    """Runs whose risers FAN instead of staying parallel (a winder flight).

    A balanced winder keeps the going constant on the WALK LINE, so its risers
    rotate and their ends spread unevenly along the two sides -- the parallel
    detector sees a different direction per riser and finds nothing (three of
    StaircasePlan-Test2's six stairs). Two things stay true and identify it:

      * the riser MIDPOINTS sit on one straight line, one tread apart;
      * the risers TURN, monotonically, by a real angle across the flight.

    That second test is what keeps this off ordinary geometry -- a straight
    flight turns by nothing and is already the parallel detector's job.
    """
    seen = set()
    pool = []
    for a, b in lines:
        length = _dist(a, b)
        if length <= 0:
            continue
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        key = (round(mid[0] * _MM), round(mid[1] * _MM), round(length * _MM))
        if key in seen:
            continue                     # the same riser drawn twice
        seen.add(key)
        pool.append((mid, a, b, length,
                     math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi))
    if len(pool) < _FAN_MIN_RISERS:
        return []
    tol = config.mm_to_ft(_FAN_MID_TOL_MM)
    found = []
    for band in _length_bands(pool):
        found += _fans_in_band(band, tol)
    return _best_fans(found, runs)


def _length_bands(pool):
    """The distinct groups of similar-length lines, biggest group first.

    Length bands, not one median: a stair's linework is mostly short nosing and
    outline marks, so the median length of the whole cluster is nowhere near the
    flight width and a single band misses the winder entirely. Riser lines of
    one flight DO share a length (the flight width), so a band is a candidate.
    """
    bands = {}
    for item in pool:
        length = item[3]
        if length <= 0:
            continue
        band = tuple(sorted(
            i for i, other in enumerate(pool)
            if abs(other[3] - length) <= _FAN_LENGTH_TOL * length))
        if len(band) >= _FAN_MIN_RISERS:
            bands[band] = [pool[i] for i in band]
    return sorted(bands.values(), key=len, reverse=True)


def _fans_in_band(band, tol):
    """Fan runs among one length band, over every walk direction."""
    found = []
    # try every walk direction on the same angular grid the parallel pass uses
    steps = max(1, int(round(math.pi / _RISER_ANGLE_TOL)))
    for step in range(steps):
        angle = step * _RISER_ANGLE_TOL
        ux, uy = math.cos(angle), math.sin(angle)
        # the normal follows the parallel pass's handedness -- axis is the
        # normal turned +90 degrees -- or the rebuilt centreline mirrors
        nx, ny = uy, -ux
        rows = defaultdict(list)
        for item in band:
            mid = item[0]
            across = mid[0] * nx + mid[1] * ny
            rows[int(round(across / tol))].append(
                (mid[0] * ux + mid[1] * uy, item))
        for row in rows.values():
            if len(row) < _FAN_MIN_RISERS:
                continue
            row.sort()
            across = sum(item[0][0] * nx + item[0][1] * ny
                         for _p, item in row) / len(row)
            for chain in _equidistant_chains([(p, 0.0, 0.0) for p, _i in row]):
                if len(chain) < _FAN_MIN_RISERS:
                    continue
                wanted = set(round(p * _MM) for p, _lo, _hi in chain)
                members = [(p, item) for p, item in row
                           if round(p * _MM) in wanted]
                if len(members) < _FAN_MIN_RISERS:
                    continue
                turn = _monotone_turn([item[4] for _p, item in members])
                if turn is None or abs(turn) < _FAN_MIN_TURN:
                    continue             # parallel risers: not a winder
                widths = sorted(item[3] for _p, item in members)
                width = widths[len(widths) // 2]
                positions = [p for p, _item in members]
                mid_pos = (positions[0] + positions[-1]) / 2.0
                found.append({
                    "axis": (ux, uy), "normal": (nx, ny),
                    "positions": positions,
                    # span_lo/hi are ABSOLUTE projections on the normal, exactly
                    # as the parallel runs report them: the run dicts rebuild
                    # the centreline from them, and centred values would put it
                    # on the axis instead of on the flight
                    "span_lo": across - width / 2.0,
                    "span_hi": across + width / 2.0,
                    "fanned": True, "turn": turn,
                    "riser_lines": [(item[1], item[2]) for _p, item in members],
                    "center": (ux * mid_pos + nx * across,
                               uy * mid_pos + ny * across)})
    return found


def _monotone_turn(angles):
    """Total signed rotation across a fan, or None when it does not turn evenly.

    Riser directions are unsigned (mod pi), so each step is taken as the SHORT
    way round; the steps must all lean the same way for the flight to be a fan
    rather than a scatter of near-parallel strays.
    """
    if len(angles) < 3:
        return None
    total = 0.0
    sign = 0
    for i in range(len(angles) - 1):
        step = (angles[i + 1] - angles[i]) % math.pi
        if step > math.pi / 2.0:
            step -= math.pi              # the short way round
        if abs(step) < 1e-9:
            continue
        if sign and (step > 0) != (sign > 0):
            return None                  # turns back on itself
        sign = 1 if step > 0 else -1
        total += step
    return total if sign else None


def _best_fans(fans, runs):
    """Keep the longest fans that share no risers with each other or a run.

    The direction sweep finds the same flight from several nearby angles and
    also finds its sub-chains, so the raw list over-counts; a fan survives only
    when most of its risers are still unclaimed.
    """
    def keys(fan):
        return set((round(a[0] * _MM), round(a[1] * _MM),
                    round(b[0] * _MM), round(b[1] * _MM))
                   for a, b in fan["riser_lines"])

    claimed = set()
    for run in runs:
        for pos in run["positions"]:
            claimed.add(round(pos * _MM / 15.0))
    kept = []
    used = set()
    for fan in sorted(fans, key=lambda f: (-len(f["positions"]),
                                           -abs(f.get("turn") or 0.0))):
        mine = keys(fan)
        if len(mine - used) < _FAN_MIN_RISERS:
            continue                     # already covered by a longer fan
        on_a_run = sum(1 for pos in fan["positions"]
                       if round(pos * _MM / 15.0) in claimed)
        if on_a_run > len(fan["positions"]) / 2:
            continue                     # a parallel run already has these
        used |= mine
        kept.append(fan)
    return kept


_SPAN_BUCKET_MM = 5.0        # riser ends within this are the same drawn span


def _modal_span(chain):
    """The (lo, hi) span MOST of the chain's riser lines actually have.

    Always a real drawn extent, unlike a per-end median, which can pair the low
    end of one line with the high end of another and invent a width no riser
    has.
    """
    bucket = config.mm_to_ft(_SPAN_BUCKET_MM)
    tally = defaultdict(list)
    for _pos, lo, hi in chain:
        tally[(round(lo / bucket), round(hi / bucket))].append((lo, hi))
    best = max(tally.values(), key=lambda group: (len(group),
                                                  group[0][1] - group[0][0]))
    return (sum(g[0] for g in best) / len(best),
            sum(g[1] for g in best) / len(best))


def _equidistant_chains(merged):
    """Split riser positions into maximal EQUIDISTANT chains (one per flight).

    A drawn flight is a run of positions one tread apart; the landing and the
    boundary lines past the last riser sit further away. Rejecting the whole
    group when its gaps are not uniform threw away real flights (test9's stairs
    lose 11 risers at 300 mm to two trailing 800 mm gaps), so the gaps that are
    not a tread SEGMENT the group instead of disqualifying it.
    """
    step = _tread_step(merged)
    chains = []
    current = []
    for item in merged:
        if not current:
            current = [item]
            continue
        gap = (item[0] - current[-1][0]) * _MM
        multiple = _tread_multiple(gap, step)
        if multiple:
            # a gap of exactly k treads means k-1 riser lines were not drawn
            # (a break line, a landing edge drawn over them): rebuild them so
            # the flight stays whole and its riser count stays right
            previous = current[-1]
            for missing in range(1, multiple):
                fraction = float(missing) / multiple
                current.append((previous[0] + (item[0] - previous[0]) * fraction,
                                previous[1], previous[2]))
            current.append(item)
        else:
            if len(current) >= _RISER_MIN_LINES:
                chains.append(current)
            current = [item]
    if len(current) >= _RISER_MIN_LINES:
        chains.append(current)
    return chains


def _tread_step(merged):
    """The flight's tread: the median gap that falls inside the tread range."""
    gaps = sorted((merged[i + 1][0] - merged[i][0]) * _MM
                  for i in range(len(merged) - 1))
    inside = [g for g in gaps if _TREAD_MIN_MM <= g <= _TREAD_MAX_MM]
    if not inside:
        return None
    return inside[len(inside) // 2]


_MAX_MISSING_RISERS = 3      # a bigger jump is a landing, not a gap in a flight


def _tread_multiple(gap, step):
    """How many treads this gap spans (1 = the next riser), or 0 if it is not
    a whole multiple of the tread -- that is where the flight really ends."""
    if step is None or step <= 0:
        return 0
    for multiple in range(1, _MAX_MISSING_RISERS + 1):
        if abs(gap - step * multiple) <= 60.0:
            return multiple
    return 0


def _dogleg_run_dicts(runs, cluster, params):
    """Start/end run dicts for a one-direction stair (one or two flights).

    The landing sits in the drawn leftover next to the riser extent; the first
    run climbs INTO its edge, the second climbs OUT (the 180-degree turn).
    Returns (run_dicts, landing_mm)."""
    runs = sorted(runs, key=lambda r: r["span_lo"])[:2]
    px, py = runs[0]["axis"]
    projections = [x * px + y * py
                   for a, b in cluster for x, y in (a, b)]
    cluster_lo, cluster_hi = min(projections), max(projections)
    pos_lo = min(r["positions"][0] for r in runs)
    pos_hi = max(r["positions"][-1] for r in runs)
    left_over_lo = (pos_lo - cluster_lo) * _MM
    left_over_hi = (cluster_hi - pos_hi) * _MM
    landing_at_lo = left_over_lo >= left_over_hi
    landing_mm = max(left_over_lo, left_over_hi)
    width_mm = min((r["span_hi"] - r["span_lo"]) * _MM for r in runs)
    if landing_mm < width_mm * 0.5:
        landing_mm = float(params.get("landing_mm") or 0.0) or width_mm
    dxn, dyn = py, -px                          # unit normal to the run axis
    run_dicts = []
    for number, run in enumerate(runs):
        off = (run["span_lo"] + run["span_hi"]) / 2.0
        s0, s1 = run["positions"][0], run["positions"][-1]
        near_s, far_s = (s0, s1) if landing_at_lo else (s1, s0)
        if number == 0:
            start_s, end_s = far_s, near_s      # climbs INTO the landing
        else:
            start_s, end_s = near_s, far_s      # climbs OUT of it
        run_dicts.append(_with_drawn_risers({
            "start": (px * start_s + dxn * off, py * start_s + dyn * off),
            "end": (px * end_s + dxn * off, py * end_s + dyn * off),
            "risers": len(run["positions"]),
            "width_mm": (run["span_hi"] - run["span_lo"]) * _MM}, run))
    return run_dicts, landing_mm


def _with_drawn_risers(run_dict, run):
    """Carry a FANNED run's drawn riser lines onto its run dict.

    A winder's risers are not perpendicular to the walk line, so the builder
    cannot rebuild them from start/end -- it sketches the run from these exact
    lines instead. Ordered along the climb and oriented consistently (first
    point on the same side of the walk line throughout) so the two boundary
    chains come straight off them.
    """
    if not run.get("fanned") or not run.get("riser_lines"):
        return run_dict
    sx, sy = run_dict["start"]
    ex, ey = run_dict["end"]
    length = math.hypot(ex - sx, ey - sy)
    if length <= 0:
        return run_dict
    ux, uy = (ex - sx) / length, (ey - sy) / length
    ordered = []
    for a, b in run["riser_lines"]:
        # first point to the LEFT of the climb direction, always the same side
        if (-(a[0] - sx) * uy + (a[1] - sy) * ux) < (-(b[0] - sx) * uy
                                                     + (b[1] - sy) * ux):
            a, b = b, a
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        ordered.append(((mid[0] - sx) * ux + (mid[1] - sy) * uy, a, b))
    ordered.sort()
    run_dict["riser_lines"] = [(a, b) for _t, a, b in ordered]
    run_dict["fanned"] = True
    return run_dict


def _winding_run_dicts(runs, params):
    """Start/end run dicts for a MULTI-DIRECTION stair (flights around a well,
    e.g. Project1's square stairs). Runs are ordered counterclockwise around
    the well centre and each climbs in the counterclockwise direction, so
    consecutive ends meet at the corner landings. Returns (run_dicts,
    landing_mm) -- the corner landing is one run width unless the dialog says
    otherwise."""
    ox = sum(r["center"][0] for r in runs) / len(runs)
    oy = sum(r["center"][1] for r in runs) / len(runs)
    runs = sorted(runs, key=lambda r: math.atan2(r["center"][1] - oy,
                                                 r["center"][0] - ox))
    # start at the bottom-most flight; the rest follow counterclockwise
    start_index = min(range(len(runs)), key=lambda i: runs[i]["center"][1])
    runs = runs[start_index:] + runs[:start_index]
    run_dicts = []
    for run in runs:
        apx, apy = run["axis"]
        nx, ny = run["normal"]
        cx, cy = run["center"]
        off = (run["span_lo"] + run["span_hi"]) / 2.0
        # climb along the counterclockwise tangent at this flight's position
        tx, ty = -(cy - oy), (cx - ox)
        s0, s1 = run["positions"][0], run["positions"][-1]
        if apx * tx + apy * ty >= 0:
            start_s, end_s = s0, s1
        else:
            start_s, end_s = s1, s0
        run_dicts.append(_with_drawn_risers({
            "start": (apx * start_s + nx * off, apy * start_s + ny * off),
            "end": (apx * end_s + nx * off, apy * end_s + ny * off),
            "risers": len(run["positions"]),
            "width_mm": (run["span_hi"] - run["span_lo"]) * _MM}, run))
    width_mm = min(r["width_mm"] for r in run_dicts)
    landing_mm = float(params.get("landing_mm") or 0.0) or width_mm
    return run_dicts, landing_mm


_SPIRAL_MIN_LINES = 5          # radial risers needed to call a stair circular
_SPIRAL_CENTER_TOL = 0.20      # extension must pass within 20% of riser length
_SPIRAL_DOMINANCE = 0.60       # radial lines must be most of the cluster
_SPIRAL_STEP_TOL = 0.60        # one flight turns at an even angular pitch
_SPIRAL_SAME_RISER = 0.40      # angles this much closer than the pitch are one riser
_SPIRAL_DUP_RAD = math.radians(0.5)   # below this two lines are the SAME riser
_SPIRAL_MIN_TURN = math.radians(90.0)  # less turn than this is a winder corner
_WINDER_REACH = 1.6            # corner leftovers within reach x width join it


def _spiral_run(cluster):
    """A CIRCULAR stair: riser lines RADIATE from a common centre.

    Every line's extension must pass near one point and the endpoint distances
    must form a consistent radial band. Returns {"center", "radius" (mid),
    "width_mm", "start_angle", "included_angle", "clockwise", "risers",
    "tread_mm"} or None.
    """
    if len(cluster) < _SPIRAL_MIN_LINES:
        return None
    # candidate centre: intersect the first line with the most-perpendicular one
    inter = []
    n = len(cluster)
    for i in range(n):
        a1, b1 = cluster[i]
        d1 = (b1[0] - a1[0], b1[1] - a1[1])
        for j in range(i + 1, n):
            a2, b2 = cluster[j]
            d2 = (b2[0] - a2[0], b2[1] - a2[1])
            den = d1[0] * d2[1] - d1[1] * d2[0]
            L1 = math.hypot(*d1)
            L2 = math.hypot(*d2)
            if L1 <= 0 or L2 <= 0 or abs(den) < 0.3 * L1 * L2:
                continue                     # near-parallel: unstable crossing
            t = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
            inter.append((a1[0] + d1[0] * t, a1[1] + d1[1] * t))
    if len(inter) < 3:
        return None
    cx = sorted(p[0] for p in inter)[len(inter) // 2]
    cy = sorted(p[1] for p in inter)[len(inter) // 2]
    lengths = sorted(_dist(a, b) for a, b in cluster)
    median_len = lengths[len(lengths) // 2]
    # SELECT the radial lines, do not demand them: a drawn spiral carries its
    # stairwell walls and nosing marks on the same layer, and bailing on the
    # first non-radial line is why Test2's spiral produced nothing.
    radial = []
    for a, b in cluster:
        dxl, dyl = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dxl, dyl)
        if L <= 0:
            continue
        # distance from the centre to the infinite line
        off = abs((a[0] - cx) * dyl - (a[1] - cy) * dxl) / L
        if off <= _SPIRAL_CENTER_TOL * median_len:
            radial.append((a, b))
    if len(radial) < _SPIRAL_MIN_LINES:
        return None
    if float(len(radial)) / len(cluster) < _SPIRAL_DOMINANCE:
        return None                          # a fan in a corner, not a spiral
    angles = []
    r_in = []
    r_out = []
    for a, b in radial:
        ra = math.hypot(a[0] - cx, a[1] - cy)
        rb = math.hypot(b[0] - cx, b[1] - cy)
        r_in.append(min(ra, rb))
        r_out.append(max(ra, rb))
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        angles.append(math.atan2(my - cy, mx - cx))
    r_lo = sorted(r_in)[len(r_in) // 2]
    r_hi = sorted(r_out)[len(r_out) // 2]
    if (r_hi - r_lo) < 0.5 * median_len:
        return None
    # order angularly; the largest gap separates the flight from empty air
    order = sorted(range(len(angles)), key=lambda i: angles[i])
    sorted_angles = [angles[i] for i in order]
    gaps = [(sorted_angles[(i + 1) % len(sorted_angles)] - sorted_angles[i])
            % (2.0 * math.pi) for i in range(len(sorted_angles))]
    cut = max(range(len(gaps)), key=lambda i: gaps[i])
    seq = [sorted_angles[(cut + 1 + i) % len(sorted_angles)]
           for i in range(len(sorted_angles))]
    unwrapped = [seq[0]]
    for ang in seq[1:]:
        step = (ang - unwrapped[-1]) % (2.0 * math.pi)
        unwrapped.append(unwrapped[-1] + step)
    unwrapped = _merge_close_angles(unwrapped)
    if len(unwrapped) < _SPIRAL_MIN_LINES:
        return None
    included = unwrapped[-1] - unwrapped[0]
    if included <= 0 or included > 2.0 * math.pi * 0.999:
        return None
    if included < _SPIRAL_MIN_TURN:
        return None                          # a winder corner, not a spiral
    steps = [unwrapped[i + 1] - unwrapped[i] for i in range(len(unwrapped) - 1)]
    even = sorted(steps)[len(steps) // 2]
    if even <= 0 or max(abs(s - even) for s in steps) > _SPIRAL_STEP_TOL * even:
        return None                          # uneven pitch: not one spiral flight
    mid_r = (r_lo + r_hi) / 2.0
    # A spiral's going can be read on the WALK LINE (300mm off the inner edge,
    # the code measure) or across the MIDDLE of the flight. Neither suits every
    # stair: Test2's spiral is 2000 wide on a 300 inner radius, where the walk
    # line reads 139mm and would reject treads that are exactly 300 across the
    # middle. Take whichever reading is a plausible going, walk line first.
    pitch = included / len(steps)
    walk_mm = pitch * (r_lo + config.mm_to_ft(300.0)) * _MM
    mid_mm = pitch * mid_r * _MM
    tread_mm = None
    for value in (walk_mm, mid_mm):
        if _TREAD_MIN_MM <= value <= _TREAD_MAX_MM:
            tread_mm = value
            break
    if tread_mm is None:
        return None
    return {"center": (cx, cy), "radius": mid_r,
            "width_mm": (r_hi - r_lo) * _MM,
            "start_angle": unwrapped[0], "included_angle": included,
            "clockwise": False, "risers": len(unwrapped),
            "tread_mm": tread_mm}


_SPIRAL_LANDING_CHORDS = 8     # arc tessellation for the arrival landing


def _spiral_top_landing(spiral, landing_mm):
    """The arrival landing ring at the top of a spiral flight.

    A spiral run ends on its last riser with nothing to step onto, so the stair
    arrived at the storey with no landing. The ring is the annular sector that
    continues the flight: same inner and outer radius, one landing depth of
    turn past the last riser (a tread's worth when the dialog says nothing).
    """
    mid_r = spiral["radius"]
    half_w = (spiral["width_mm"] / _MM) / 2.0
    r_lo, r_hi = mid_r - half_w, mid_r + half_w
    if r_lo <= 0 or mid_r <= 0:
        return None
    depth = config.mm_to_ft(landing_mm or spiral["tread_mm"])
    sweep = depth / mid_r
    if sweep <= 0:
        return None
    cx, cy = spiral["center"]
    end = spiral["start_angle"] + spiral["included_angle"]
    if spiral.get("clockwise"):
        sweep = -sweep
    steps = _SPIRAL_LANDING_CHORDS
    ring = []
    for i in range(steps + 1):              # along the OUTER edge
        angle = end + sweep * (float(i) / steps)
        ring.append((cx + r_hi * math.cos(angle), cy + r_hi * math.sin(angle)))
    for i in range(steps, -1, -1):          # back along the INNER edge
        angle = end + sweep * (float(i) / steps)
        ring.append((cx + r_lo * math.cos(angle), cy + r_lo * math.sin(angle)))
    return ring


def _merge_close_angles(unwrapped):
    """Collapse risers drawn twice: angles far closer than the typical step.

    Test2's spiral carries every riser as two collinear lines, so 24 treads
    arrived as 48 and the going came out half of what is drawn. Duplicates sit
    at a step of ~0, so they must be kept OUT of the median -- with half the
    steps zero the median is zero and nothing merges at all.
    """
    if len(unwrapped) < 3:
        return unwrapped
    steps = sorted(step for step in (unwrapped[i + 1] - unwrapped[i]
                                     for i in range(len(unwrapped) - 1))
                   if step > _SPIRAL_DUP_RAD)
    if not steps:
        return unwrapped
    typical = steps[len(steps) // 2]
    merged = [unwrapped[0]]
    for angle in unwrapped[1:]:
        if angle - merged[-1] < _SPIRAL_SAME_RISER * typical:
            continue                         # the same riser drawn again
        merged.append(angle)
    return merged


def _winder_corners(cluster, runs, run_dicts):
    """ANGLED risers in a turn (a winder corner instead of a flat landing).

    Leftover riser-length lines that sit in the corner between two consecutive
    flights and point BETWEEN their riser directions are the drawn winders.
    Returns [{"after_run": i, "riser_lines": [((x1,y1),(x2,y2)), ...]}].
    """
    if len(run_dicts) < 2 or not runs:
        return []
    lengths = sorted((r["span_hi"] - r["span_lo"]) for r in runs)
    median_w = lengths[len(lengths) // 2]
    used = []
    for run in runs:
        px, py = run["axis"]
        for pos in run["positions"]:
            used.append((run, pos))

    def in_a_run(a, b):
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        ang_line = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        for run in runs:
            nx, ny = run["normal"]
            ang_norm = math.atan2(ny, nx) % math.pi
            dang = abs(ang_line - ang_norm) % math.pi
            if min(dang, math.pi - dang) > 0.1:
                continue
            px, py = run["axis"]
            pos = mx * px + my * py
            if any(abs(pos - q) * _MM < 15.0 for q in run["positions"]):
                return True
        return False

    def angled(a, b):
        # a WINDER riser points BETWEEN the flights: a leftover parallel to a
        # flight's risers (a stray) or to its axis (a landing boundary) is not
        ang_line = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        for run in runs:
            for vx, vy in (run["normal"], run["axis"]):
                ang_v = math.atan2(vy, vx) % math.pi
                dang = abs(ang_line - ang_v) % math.pi
                if min(dang, math.pi - dang) < 0.12:
                    return False
        return True

    # a FANNED run is already made of angled risers -- counting them again here
    # would place the same winder twice and double the stair's riser total
    fanned = set()
    for run in runs:
        for a, b in run.get("riser_lines") or []:
            fanned.add((round(a[0] * _MM), round(a[1] * _MM),
                        round(b[0] * _MM), round(b[1] * _MM)))

    def in_a_fan(a, b):
        return (round(a[0] * _MM), round(a[1] * _MM),
                round(b[0] * _MM), round(b[1] * _MM)) in fanned

    leftovers = [(a, b) for a, b in cluster
                 if 0.6 * median_w <= _dist(a, b) <= 1.4 * median_w
                 and not in_a_run(a, b) and not in_a_fan(a, b)
                 and angled(a, b)]
    if not leftovers:
        return []
    out = []
    reach = median_w * _WINDER_REACH
    inside = median_w * 1.1        # a winder stays IN the corner square; a
    #                                break-line diagonal shoots past it
    for i in range(len(run_dicts) - 1):
        ex, ey = run_dicts[i]["end"]
        sx, sy = run_dicts[i + 1]["start"]
        cx, cy = (ex + sx) / 2.0, (ey + sy) / 2.0
        fan = [(a, b) for a, b in leftovers
               if math.hypot((a[0] + b[0]) / 2.0 - cx,
                             (a[1] + b[1]) / 2.0 - cy) <= reach
               and math.hypot(a[0] - cx, a[1] - cy) <= inside
               and math.hypot(b[0] - cx, b[1] - cy) <= inside]
        if fan:
            out.append({"after_run": i, "riser_lines": fan})
    return out


def stair_plans_from_linework(records, params, storey_mm, texts=None):
    """Option 2: stair plans measured from the drawn stair-layer riser lines.

    Every drawn quantity wins over the dialog: tread = drawn spacing, run width
    = drawn riser length, riser count = drawn line count, landing = the drawn
    leftover next to the riser extent. One drawn direction = a dog-leg (or a
    single flight); two directions = a winding stair around a well, every
    flight kept. Returns (plans, notes).
    """
    lines, z = _stair_lines(records)
    if not lines:
        return [], []
    stair_texts = find_stair_texts(texts or [])
    plans = []
    notes = []
    for index, cluster in enumerate(
            _cluster_lines(lines, config.mm_to_ft(_CLUSTER_GAP_MM)), start=1):
        spiral = _spiral_run(cluster)
        if spiral:
            risers_total = spiral["risers"]
            plans.append({
                "mark": "ST-{0}".format(index), "z": z, "runs": [],
                "spiral": spiral, "landing": None,
                "top_landing": _spiral_top_landing(
                    spiral, float(params.get("landing_mm") or 0.0)),
                "risers_total": risers_total,
                "riser_mm": (storey_mm / risers_total if storey_mm > 0
                             else 0.0),
                "tread_mm": spiral["tread_mm"],
                "run_width_mm": spiral["width_mm"],
                "landing_mm": float(params.get("landing_mm") or 0.0)
                or spiral["width_mm"],
                "waist_mm": float(params.get("waist_mm") or 0.0),
                "source": "stair_linework"})
            continue
        runs = _riser_runs(cluster)
        if not runs:
            xs = [q[0] for a, b in cluster for q in (a, b)]
            ys = [q[1] for a, b in cluster for q in (a, b)]
            span_mm = max(max(xs) - min(xs), max(ys) - min(ys)) * _MM
            if span_mm >= _MIN_STAIR_SPAN_MM:
                notes.append("stair linework cluster {0} at ({1:.0f}, {2:.0f}) mm: "
                             "no riser lines (need >= {3} parallel equidistant "
                             "lines)".format(index, min(xs) * _MM, min(ys) * _MM,
                                             _RISER_MIN_LINES))
            continue
        axes_differ = any(
            abs(r["axis"][0] * runs[0]["axis"][1] -
                r["axis"][1] * runs[0]["axis"][0]) > 0.17 for r in runs)
        if axes_differ and len(runs) >= 2:
            # L (two flights), three-flight U or a four-flight square: every
            # multi-direction stair walks around its corner(s)
            run_dicts, landing_mm = _winding_run_dicts(runs, params)
        else:
            same_axis = [r for r in runs
                         if abs(r["axis"][0] * runs[0]["axis"][1] -
                                r["axis"][1] * runs[0]["axis"][0]) <= 0.17]
            run_dicts, landing_mm = _dogleg_run_dicts(same_axis, cluster,
                                                      params)
        winders = _winder_corners(cluster, runs, run_dicts)
        gaps = [(r["positions"][i + 1] - r["positions"][i]) * _MM
                for r in runs for i in range(len(r["positions"]) - 1)]
        gaps.sort()
        tread_mm = gaps[len(gaps) // 2] if gaps else 300.0
        width_mm = min(r["width_mm"] for r in run_dicts)
        risers_total = sum(r["risers"] for r in run_dicts)
        winder_risers = sum(len(w["riser_lines"]) + 1 for w in winders)
        risers_total += winder_risers
        riser_mm = storey_mm / risers_total if storey_mm > 0 else 0.0
        # nearest stair text names the stair
        xs = [q for a, b in cluster for q in (a[0], b[0])]
        ys = [q for a, b in cluster for q in (a[1], b[1])]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        mark = "ST-{0}".format(index)
        best_d = None
        for tx, ty, tmark in stair_texts:
            d = math.hypot(tx - cx, ty - cy)
            if best_d is None or d < best_d:
                best_d, mark = d, tmark
        plans.append({"mark": mark, "z": z, "runs": run_dicts,
                      "landing": None, "winders": winders,
                      "bridge_landings": _bridge_landings(run_dicts),
                      "top_landing": _arrival_landing(run_dicts, landing_mm),
                      "risers_total": risers_total,
                      "riser_mm": riser_mm, "tread_mm": tread_mm,
                      "run_width_mm": width_mm, "landing_mm": landing_mm,
                      "waist_mm": float(params.get("waist_mm") or 0.0),
                      "source": "stair_linework"})
    return plans, notes


def plan_stairs(records, beam_segments, column_rects, texts, params, storey_mm,
                source="auto", regions=None):
    """The staircase chain (drawn linework, plan text, or a picked region):

    source="auto"     -- drawn stair LINEWORK when the plan has any, else the
                         TEXT + dialog-numbers layout (the default chain);
    source="linework" -- drawn riser lines drive the layout, nothing else;
    source="text"     -- the generic SHAPE from the dialog, laid inside the bay
                         holding a STAIRCASE / ST-n note;
    source="region"   -- the generic SHAPE laid inside `regions`, the
                         rectangles the user drew in the Revit view.

    `params["shape"]` picks the generic shape (STAIR_SHAPES); it is ignored
    when the layout comes from drawn linework. Returns (plans, notes) -- every
    skipped stair leaves a human-readable note so the console says WHY.
    """
    plans = []
    notes = []
    shape = (params.get("shape") or SHAPE_U).lower()
    if shape not in STAIR_SHAPES:
        notes.append("unknown stair shape '{0}' -- using U".format(shape))
        shape = SHAPE_U
    direction_texts = find_direction_texts(texts or [])

    if source == "region":
        if not regions:
            return [], ["no region picked in the Revit view"]
        for index, ring in enumerate(regions, start=1):
            plan, note = plan_shaped_stair(ring, 0.0, "ST-{0}".format(index),
                                           params, storey_mm,
                                           direction_texts=direction_texts,
                                           shape=shape)
            if note:
                notes.append(note)
            if plan:
                plan["source"] = "picked_region"
                plans.append(plan)
        return notch_landings(plans, column_rects), notes

    if source in ("auto", "linework"):
        plans, notes = stair_plans_from_linework(records, params, storey_mm,
                                                 texts=texts)
        if plans or source == "linework":
            return notch_landings(plans, column_rects), notes
    areas, area_notes = stair_areas_from_texts(records, beam_segments,
                                               column_rects, texts)
    notes += area_notes
    for ring, z, mark in areas:
        plan, note = plan_shaped_stair(ring, z, mark, params, storey_mm,
                                       direction_texts=direction_texts,
                                       shape=shape)
        if note:
            notes.append(note)
        if plan:
            plan["source"] = "stair_text"
            plans.append(plan)
    return notch_landings(plans, column_rects), notes


# ------------------------------------------------------- landings vs columns
_NOTCH_MIN_BITE_MM = 20.0     # an overlap smaller than this is not worth cutting


def notch_landings(plans, column_rects):
    """Step every landing ring around the columns it runs into.

    A landing laid out from the flights alone can push its corner through a
    column -- Test2's stair 1 mid landing runs into C38 and C40 -- and Revit
    happily builds the overlap. The corner is CUT OUT instead, leaving the step
    the drawing shows. Rings that a cut would break apart are left alone, so a
    landing is never silently turned into something disconnected.
    """
    boxes = _column_boxes(column_rects)
    if not boxes:
        return plans
    for plan in plans or []:
        for key in ("landing", "top_landing"):
            ring = plan.get(key)
            if ring:
                plan[key] = _notch_ring(ring, boxes)
        bridges = plan.get("bridge_landings") or {}
        for index, ring in list(bridges.items()):
            bridges[index] = _notch_ring(ring, boxes)
    return plans


def _column_boxes(column_rects):
    """[(x0, y0, x1, y1)] -- the axis-aligned footprint of each column."""
    boxes = []
    for rect in column_rects or []:
        kind = rect[0]
        if kind == "circle":
            _k, cx, cy, radius = rect
            boxes.append((cx - radius, cy - radius, cx + radius, cy + radius))
        elif kind == "rect":
            _k, cx, cy, ux, uy, half_long, half_short = rect
            nx, ny = -uy, ux
            xs, ys = [], []
            for su, sv in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
                xs.append(cx + ux * half_long * su + nx * half_short * sv)
                ys.append(cy + uy * half_long * su + ny * half_short * sv)
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
    return boxes


def _notch_ring(ring, boxes):
    """`ring` with every overlapping column box cut out, or unchanged.

    Rectilinear boolean by cell grid: the ring's own bounding box is split at
    every edge coordinate of the ring and the boxes, each cell is kept when it
    is inside the ring and outside every box, and the kept cells' outline is
    traced back into one ring. The cut is only accepted when it leaves ONE
    piece with no hole -- Revit's landing sketch takes a single loop.
    """
    bite = config.mm_to_ft(_NOTCH_MIN_BITE_MM)
    xs = sorted(set([p[0] for p in ring]))
    ys = sorted(set([p[1] for p in ring]))
    if len(xs) < 2 or len(ys) < 2:
        return ring
    hits = [b for b in boxes
            if b[0] < xs[-1] - bite and b[2] > xs[0] + bite
            and b[1] < ys[-1] - bite and b[3] > ys[0] + bite]
    if not hits:
        return ring
    for box in hits:
        xs += [box[0], box[2]]
        ys += [box[1], box[3]]
    xs = _unique_sorted(xs, xs[0], max(p[0] for p in ring), bite)
    ys = _unique_sorted(ys, ys[0], max(p[1] for p in ring), bite)
    if len(xs) < 2 or len(ys) < 2:
        return ring
    keep = set()
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx = (xs[i] + xs[i + 1]) / 2.0
            cy = (ys[j] + ys[j + 1]) / 2.0
            if not slab_outlines._point_in_ring((cx, cy), ring):
                continue
            if any(b[0] < cx < b[2] and b[1] < cy < b[3] for b in hits):
                continue
            keep.add((i, j))
    if not keep or not _one_piece(keep):
        return ring
    traced = _trace_cells(keep, xs, ys)
    if traced is None or len(traced) < 4:
        return ring
    if abs(slab_outlines._signed_area(traced)) < 0.5 * abs(
            slab_outlines._signed_area(ring)):
        return ring                     # the cut took most of the landing away
    return traced


def _unique_sorted(values, low, high, tol):
    """Sorted values inside [low, high], merged when closer than `tol`."""
    out = []
    for value in sorted(values):
        if value < low - tol or value > high + tol:
            continue
        value = min(max(value, low), high)
        if not out or value - out[-1] > tol:
            out.append(value)
    return out


def _one_piece(cells):
    """True when the kept cells form ONE 4-connected region with no hole."""
    start = next(iter(cells))
    seen = set([start])
    stack = [start]
    while stack:
        i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = (i + di, j + dj)
            if neighbour in cells and neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    if len(seen) != len(cells):
        return False
    # a hole shows up as an interior gap: every missing cell inside the bounding
    # range must be reachable from outside it
    i0 = min(i for i, _j in cells)
    i1 = max(i for i, _j in cells)
    j0 = min(j for _i, j in cells)
    j1 = max(j for _i, j in cells)
    outside = set()
    stack = [(i, j) for i in range(i0 - 1, i1 + 2)
             for j in (j0 - 1, j1 + 1) if (i, j) not in cells]
    stack += [(i, j) for j in range(j0 - 1, j1 + 2)
              for i in (i0 - 1, i1 + 1) if (i, j) not in cells]
    outside.update(stack)
    while stack:
        i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = (i + di, j + dj)
            if (i0 - 1 <= neighbour[0] <= i1 + 1
                    and j0 - 1 <= neighbour[1] <= j1 + 1
                    and neighbour not in cells and neighbour not in outside):
                outside.add(neighbour)
                stack.append(neighbour)
    empty = [(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)
             if (i, j) not in cells]
    return all(cell in outside for cell in empty)


def _trace_cells(cells, xs, ys):
    """The outline of a set of grid cells as one ring, collinear points dropped."""
    edges = {}
    for i, j in cells:
        corners = [(xs[i], ys[j]), (xs[i + 1], ys[j]),
                   (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])]
        for step, (di, dj) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
            if (i + di, j + dj) in cells:
                continue                # shared with a kept cell: interior
            a = corners[step]
            b = corners[(step + 1) % 4]
            edges.setdefault(a, []).append(b)
    if not edges:
        return None
    start = min(edges)
    ring = [start]
    current = start
    while True:
        options = edges.get(current)
        if not options:
            return None
        nxt = options.pop()
        if not options:
            del edges[current]
        if nxt == start:
            break
        if len(ring) > 4 * len(cells) + 8:
            return None                 # not closing: give up rather than spin
        ring.append(nxt)
        current = nxt
    if edges:
        return None                     # more than one loop: not a single ring
    return _drop_collinear(ring)


def _drop_collinear(ring):
    out = []
    n = len(ring)
    for i in range(n):
        a, b, c = ring[i - 1], ring[i], ring[(i + 1) % n]
        if abs((b[0] - a[0]) * (c[1] - a[1])
               - (b[1] - a[1]) * (c[0] - a[0])) > 1e-12:
            out.append(b)
    return out

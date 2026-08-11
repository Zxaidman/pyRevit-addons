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
from . import stair_tolerances as tol
from .stair_landings import (_arrival_landing, _bridge_landings,
                             _spiral_top_landing, notch_landings)  # noqa: F401
from .stair_runs import (_riser_runs, _spiral_run, _winder_corners,
                         _fan_runs, _RISER_MIN_LINES)   # noqa: F401
from .stair_text import (find_stair_texts, stair_label, find_direction_texts,
                        direction_label, stair_areas_from_texts)  # noqa: F401
from . import slab_outlines
from .classify.layers import CATEGORY_STAIR

_MM = config.MM_PER_FT
_dist = slab_outlines._dist
















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
            _cluster_lines(lines, config.mm_to_ft(tol._CLUSTER_GAP_MM)), start=1):
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


















# The tunables live in stair_tolerances so every module that reads them sees the
# same values; re-exported here because the pushbutton has always called
# stair_layout.apply_tolerances().
from .stair_tolerances import apply_tolerances          # noqa: E402,F401

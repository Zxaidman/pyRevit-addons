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


def plan_dogleg_stair(ring, z, mark, params, storey_mm, direction_texts=None):
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

    if storey_mm <= 0 or riser_target <= 0 or tread <= 0 or width <= 0:
        return None, "{0}: invalid inputs (storey {1} mm)".format(mark, int(storey_mm))
    risers_total = int(math.ceil(storey_mm / riser_target - 1e-9))
    if risers_total < 2:
        risers_total = 2
    riser_actual = storey_mm / risers_total
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
    # run centrelines sit half a width off the bay's centreline, each side
    off1, off2 = wu / 2.0 + (short_mm / _MM - 2.0 * wu) / 2.0, -(
        wu / 2.0 + (short_mm / _MM - 2.0 * wu) / 2.0)
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
    lc = (cx + ax * (far_u - lu / 2.0), cy + ay * (far_u - lu / 2.0))
    landing_ring = [
        (lc[0] - ax * lu / 2.0 + nx * short_mm / _MM / 2.0,
         lc[1] - ay * lu / 2.0 + ny * short_mm / _MM / 2.0),
        (lc[0] + ax * lu / 2.0 + nx * short_mm / _MM / 2.0,
         lc[1] + ay * lu / 2.0 + ny * short_mm / _MM / 2.0),
        (lc[0] + ax * lu / 2.0 - nx * short_mm / _MM / 2.0,
         lc[1] + ay * lu / 2.0 - ny * short_mm / _MM / 2.0),
        (lc[0] - ax * lu / 2.0 - nx * short_mm / _MM / 2.0,
         lc[1] - ay * lu / 2.0 - ny * short_mm / _MM / 2.0)]
    plan = {"mark": mark, "z": z, "runs": runs, "landing": landing_ring,
            "risers_total": risers_total, "riser_mm": riser_actual,
            "tread_mm": tread, "run_width_mm": width, "landing_mm": landing}
    return plan, note


# ------------------------------------------------------- option 2: stair linework
_RISER_ANGLE_TOL = math.radians(3.0)
_RISER_MIN_LINES = 3          # fewer parallel lines than this is not a flight
_TREAD_MIN_MM = 150.0         # drawn riser spacing accepted as a tread
_TREAD_MAX_MM = 500.0
_CLUSTER_GAP_MM = 2000.0      # stair pieces closer than this belong together
_POSITION_DEDUPE_MM = 10.0    # the same riser drawn per-run appears twice


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
    """RUNS from one stair's linework: (run_axis, runs) or (None, []).

    Riser lines = the dominant parallel direction. Lines whose ACROSS spans
    overlap belong to the same run; each run's riser positions (deduped -- the
    shared riser between adjacent panels is drawn once per panel) must be >= 3
    and equidistant within tread limits. `runs` come back as
    [(positions_ft_sorted, span_lo_ft, span_hi_ft)], run_axis the unit vector
    the positions are measured along.
    """
    buckets = defaultdict(list)
    for a, b in lines:
        ang = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        key = int(round(ang / _RISER_ANGLE_TOL))
        buckets[key].append((a, b))
    best = None
    for key, bucket in buckets.items():
        if len(bucket) < _RISER_MIN_LINES:
            continue
        if best is None or len(bucket) > len(best):
            best = bucket
    if best is None:
        return None, []
    # risers are same-length; a boundary line in the same direction (the drawn
    # landing edge, twice their length) would BRIDGE the two run groups
    lengths = sorted(_dist(a, b) for a, b in best)
    median_len = lengths[len(lengths) // 2]
    best = [(a, b) for a, b in best
            if 0.6 * median_len <= _dist(a, b) <= 1.4 * median_len]
    if len(best) < _RISER_MIN_LINES:
        return None, []
    a0, b0 = best[0]
    ang = math.atan2(b0[1] - a0[1], b0[0] - a0[0]) % math.pi
    dx, dy = math.cos(ang), math.sin(ang)          # along a riser line
    px, py = -dy, dx                               # the run axis
    items = []
    for a, b in best:
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
            shorter = min(items[i][2] - items[i][1], items[j][2] - items[j][1])
            if shorter > 0 and (hi - lo) > 0.3 * shorter:
                parent[find(i)] = find(j)
    grouped = defaultdict(list)
    for i in range(len(items)):
        grouped[find(i)].append(items[i])
    dedupe_ft = config.mm_to_ft(_POSITION_DEDUPE_MM)
    runs = []
    for group in grouped.values():
        positions = []
        for pos, _lo, _hi in sorted(group):
            if not positions or pos - positions[-1] > dedupe_ft:
                positions.append(pos)
        if len(positions) < _RISER_MIN_LINES:
            continue
        gaps = [(positions[i + 1] - positions[i]) * _MM
                for i in range(len(positions) - 1)]
        if min(gaps) < _TREAD_MIN_MM or max(gaps) > _TREAD_MAX_MM:
            continue
        if max(gaps) - min(gaps) > 60.0:
            continue                    # not equidistant: boundary lines, not risers
        lo = min(g[1] for g in group)
        hi = max(g[2] for g in group)
        runs.append((positions, lo, hi))
    return (px, py), runs


def stair_plans_from_linework(records, params, storey_mm, texts=None):
    """Option 2: dog-leg plans measured from the drawn stair-layer riser lines.

    Every drawn quantity wins over the dialog: tread = drawn spacing, run width
    = drawn riser length, riser count = drawn line count, landing = the drawn
    leftover next to the riser extent. The dialog still contributes the riser
    height limit only through storey / drawn-riser-count (reported per plan).
    Returns (plans, notes).
    """
    lines, z = _stair_lines(records)
    if not lines:
        return [], []
    stair_texts = find_stair_texts(texts or [])
    plans = []
    notes = []
    for index, cluster in enumerate(
            _cluster_lines(lines, config.mm_to_ft(_CLUSTER_GAP_MM)), start=1):
        axis, runs = _riser_runs(cluster)
        if not runs:
            notes.append("stair linework cluster {0}: no riser lines "
                         "(need >= {1} parallel equidistant lines)".format(
                             index, _RISER_MIN_LINES))
            continue
        runs = sorted(runs, key=lambda r: r[1])[:2]      # dog-leg: two runs max
        px, py = axis
        xs = [q for a, b in cluster for q in (a[0], b[0])]
        ys = [q for a, b in cluster for q in (a[1], b[1])]
        cluster_lo = min(x * px + y * py for x, y in zip(xs, ys))
        cluster_hi = max(x * px + y * py for x, y in zip(xs, ys))
        pos_lo = min(r[0][0] for r in runs)
        pos_hi = max(r[0][-1] for r in runs)
        left_over_lo = (pos_lo - cluster_lo) * _MM
        left_over_hi = (cluster_hi - pos_hi) * _MM
        landing_at_lo = left_over_lo >= left_over_hi
        landing_mm = max(left_over_lo, left_over_hi)
        gaps = [(r[0][i + 1] - r[0][i]) * _MM
                for r in runs for i in range(len(r[0]) - 1)]
        gaps.sort()
        tread_mm = gaps[len(gaps) // 2]
        widths = [(r[2] - r[1]) * _MM for r in runs]
        width_mm = min(widths)
        if landing_mm < width_mm * 0.5:
            landing_mm = float(params.get("landing_mm") or 0.0) or width_mm
        risers_total = sum(len(r[0]) for r in runs)
        riser_mm = storey_mm / risers_total if storey_mm > 0 else 0.0
        # nearest stair text names the stair
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        mark = "ST-{0}".format(index)
        best_d = None
        for tx, ty, tmark in stair_texts:
            d = math.hypot(tx - cx, ty - cy)
            if best_d is None or d < best_d:
                best_d, mark = d, tmark
        # (px, py) is the run axis and `off` the across offset: a point is
        # p = axis * s + normal * off, with normal = the riser-line direction.
        # The FIRST run climbs INTO the landing edge, the second climbs OUT of
        # it back the other way (the 180-degree dog-leg turn).
        dxn, dyn = py, -px                              # unit normal to the axis
        run_dicts = []
        for number, (positions, span_lo, span_hi) in enumerate(runs):
            off = (span_lo + span_hi) / 2.0
            s0, s1 = positions[0], positions[-1]
            near_s, far_s = (s0, s1) if landing_at_lo else (s1, s0)
            if number == 0:
                start_s, end_s = far_s, near_s
            else:
                start_s, end_s = near_s, far_s
            run_dicts.append({
                "start": (px * start_s + dxn * off, py * start_s + dyn * off),
                "end": (px * end_s + dxn * off, py * end_s + dyn * off),
                "risers": len(positions),
                "width_mm": (span_hi - span_lo) * _MM})
        plans.append({"mark": mark, "z": z, "runs": run_dicts,
                      "landing": None, "risers_total": risers_total,
                      "riser_mm": riser_mm, "tread_mm": tread_mm,
                      "run_width_mm": width_mm, "landing_mm": landing_mm,
                      "source": "stair_linework"})
    return plans, notes


def plan_stairs(records, beam_segments, column_rects, texts, params, storey_mm):
    """The staircase chain (user's two options, drawn linework preferred):

    (2) stair-layer LINEWORK -- runs measured from the drawn riser lines;
    (1) TEXT + dialog numbers -- a generic dog-leg inside the bay that holds a
        STAIRCASE / ST-n note (used when the plan has no usable stair layer).

    Returns (plans, notes). Every skipped stair leaves a human-readable note so
    the console says WHY a source produced no stair.
    """
    plans, notes = stair_plans_from_linework(records, params, storey_mm,
                                             texts=texts)
    if plans:
        return plans, notes
    areas, area_notes = stair_areas_from_texts(records, beam_segments,
                                               column_rects, texts)
    notes += area_notes
    direction_texts = find_direction_texts(texts)
    for ring, z, mark in areas:
        plan, note = plan_dogleg_stair(ring, z, mark, params, storey_mm,
                                       direction_texts=direction_texts)
        if note:
            notes.append(note)
        if plan:
            plan["source"] = "stair_text"
            plans.append(plan)
    return plans, notes

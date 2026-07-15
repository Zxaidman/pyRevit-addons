# -*- coding: utf-8 -*-
"""Plan STAIRCASES from the CAD plan -- location from text, geometry from inputs.

Option 1 of the user's two staircase modes (this module): NO stair linework is
read. A STAIRCASE / ST-1 text marks WHERE a stair lives; the bay that contains
the text -- a bounded face of the placed beams + walls, from the same machinery
the slabs use -- is the stair's area. Inside that area a generic DOG-LEG (two
parallel runs + one half landing) is laid out from the user's numbers in the
dialog's Staircase tab: target riser height, tread depth, run width and landing
depth. The storey height (base to top level) fixes the riser count; the actual
riser is storey / count (never above the target).

Option 2 (planned): the same user inputs, but the run/landing positions come
from the stair-layer linework (S-STRS riser lines) instead of a generic layout.

Revit-free (no Revit imports) so the layout can be unit-tested and replayed
against the JSON exports offline; builders/stairs.py turns the plans into
Revit stairs inside a StairsEditScope.
"""

import math
import re

from . import config
from . import slab_outlines

_MM = config.MM_PER_FT

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


def plan_stairs(records, beam_segments, column_rects, texts, params, storey_mm):
    """The full option-1 pipeline: texts -> areas -> dog-leg plans.

    Returns (plans, notes). Every skipped stair leaves a human-readable note so
    the console says WHY a text produced no stair.
    """
    areas, notes = stair_areas_from_texts(records, beam_segments, column_rects,
                                          texts)
    direction_texts = find_direction_texts(texts)
    plans = []
    for ring, z, mark in areas:
        plan, note = plan_dogleg_stair(ring, z, mark, params, storey_mm,
                                       direction_texts=direction_texts)
        if note:
            notes.append(note)
        if plan:
            plans.append(plan)
    return plans, notes

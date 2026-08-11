# -*- coding: utf-8 -*-
"""Landings: the slabs BETWEEN the runs, and the shapes they have to avoid.

A drawing rarely outlines a landing -- it is whatever is left between one flight
and the next -- so these build it:

    _arrival_landing     the slab at the top or bottom of a flight
    _bridge_landings     the mid-landing two runs share, spanned between them
    _spiral_top_landing  the wedge a spiral arrives on
    notch_landings       and the correction that matters in a real building: a
                         landing overlapping a COLUMN is notched around it,
                         because Revit will happily build a landing straight
                         through a 400x900 column and nobody notices until the
                         model is opened

Revit-free: rings in, rings out.
"""

import math

from . import config
from . import slab_outlines
from . import stair_tolerances as tol

_MM = config.MM_PER_FT


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


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
    tol._ARRIVAL_MERGE_GAP_MM across joins the slab's width. A winding stair's
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
    gap_ft = config.mm_to_ft(tol._ARRIVAL_MERGE_GAP_MM)
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

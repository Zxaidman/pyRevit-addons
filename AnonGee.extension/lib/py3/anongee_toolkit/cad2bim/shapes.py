# -*- coding: utf-8 -*-
"""Rectilinear shape parsing: simplify a CAD column outline and split composite
(C / L / E / U) lift-core shapes into their rectangular sections.

This module is deliberately Revit-free and 2D so it can be unit-tested outside
Revit. All coordinates are in Revit internal feet (the reader never rescales).

Pipeline per closed column polyline:
  1. simplify_ring  -- drop duplicate and collinear vertices the DWG inserts
                       along straight edges (these inflate the corner count).
  2. is_rectilinear -- are all edges axis-aligned? (rotated columns are not.)
  3. decompose_to_rectangles -- partition a rectilinear ring into a clean,
     gap-free, non-overlapping set of axis-aligned rectangles. A plain rectangle
     yields one; an L yields two; the U/channel lift core yields two legs; an E
     yields its bars.

Decomposition method: grid-partition + greedy maximal-rectangle merge.
  + Pro: correct for ANY rectilinear polygon (exact cover, no overlaps/gaps) and
    fully deterministic with no external geometry library.
  - Con: not guaranteed *minimal* — a shape with horizontal bars may split into a
    few more rectangles than a human would draw. The merge heuristic can be
    tuned later if a specific wall-leg convention is preferred.
"""

import math

from . import config as _cfg

_TOL = 1.0e-4   # feet (~0.03 mm): collinear / axis-alignment tolerance (numerical)


class Rectangle(object):
    """An axis-aligned rectangle in feet (centre + size), with mm convenience."""

    def __init__(self, x_min, y_min, x_max, y_max, z=0.0):
        self.x_min = x_min
        self.y_min = y_min
        self.x_max = x_max
        self.y_max = y_max
        self.z = z

    @property
    def width_ft(self):
        return self.x_max - self.x_min

    @property
    def height_ft(self):
        return self.y_max - self.y_min

    @property
    def center(self):
        return ((self.x_min + self.x_max) / 2.0,
                (self.y_min + self.y_max) / 2.0, self.z)

    def to_dict(self):
        cx, cy, cz = self.center
        return {
            "center": [cx, cy, cz],
            "width_ft": self.width_ft,
            "height_ft": self.height_ft,
            "width_mm": self.width_ft * 304.8,
            "height_mm": self.height_ft * 304.8,
        }


class OrientedRect(object):
    """A rotated rectangle: centre, two side lengths, and long-axis angle (degrees).

    Reports its SHORT side as width and LONG side as height so the small-x-big
    type-naming convention falls out directly; carries an axis-aligned bbox so it
    stays compatible with code that inspects x_min/x_max (e.g. spine detection).
    """

    def __init__(self, cx, cy, long_len, short_len, long_axis_deg,
                 x_min, y_min, x_max, y_max, z=0.0):
        self.cx = cx
        self.cy = cy
        self.long_len = long_len
        self.short_len = short_len
        self.long_axis_deg = long_axis_deg
        self.x_min = x_min
        self.y_min = y_min
        self.x_max = x_max
        self.y_max = y_max
        self.z = z

    @property
    def width_ft(self):
        return self.short_len

    @property
    def height_ft(self):
        return self.long_len

    @property
    def center(self):
        return (self.cx, self.cy, self.z)

    def to_dict(self):
        return {
            "center": [self.cx, self.cy, self.z],
            "width_ft": self.short_len,
            "height_ft": self.long_len,
            "width_mm": self.short_len * 304.8,
            "height_mm": self.long_len * 304.8,
            "long_axis_deg": self.long_axis_deg,
        }


def _convex_hull(points):
    """Andrew's monotone-chain convex hull; returns hull vertices CCW."""
    pts = sorted(set((p[0], p[1]) for p in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def min_area_rect(ring, z=0.0):
    """Minimum-area oriented bounding rectangle of a ring (rotating calipers).

    Returns an OrientedRect. Recovers a rotated rectangle's true size+angle even
    when its outline carries an extra near-collinear vertex, and gives a tight
    oriented box for genuinely non-rectangular shapes.
    """
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    hull = _convex_hull(ring)
    if len(hull) < 3:
        cx = (bbox[0] + bbox[2]) / 2.0
        cy = (bbox[1] + bbox[3]) / 2.0
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        long_len, short_len = max(w, h), min(w, h)
        ang = 0.0 if w >= h else 90.0
        return OrientedRect(cx, cy, long_len, short_len, ang, *bbox, z=z)

    best = None
    count = len(hull)
    for i in range(count):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % count]
        ex, ey = bx - ax, by - ay
        edge_len = (ex * ex + ey * ey) ** 0.5
        if edge_len < 1e-12:
            continue
        ux, uy = ex / edge_len, ey / edge_len   # edge direction
        vx, vy = -uy, ux                         # perpendicular
        us = [px * ux + py * uy for px, py in hull]
        vs = [px * vx + py * vy for px, py in hull]
        min_u, max_u = min(us), max(us)
        min_v, max_v = min(vs), max(vs)
        width = max_u - min_u
        height = max_v - min_v
        area = width * height
        if best is None or area < best[0]:
            cu = (min_u + max_u) / 2.0
            cv = (min_v + max_v) / 2.0
            cx = cu * ux + cv * vx
            cy = cu * uy + cv * vy
            best = (area, cx, cy, width, height, ux, uy)

    _area, cx, cy, width, height, ux, uy = best
    edge_angle = math.degrees(math.atan2(uy, ux))
    if width >= height:
        long_len, short_len = width, height
        long_axis_deg = edge_angle % 180.0
    else:
        long_len, short_len = height, width
        long_axis_deg = (edge_angle + 90.0) % 180.0
    return OrientedRect(cx, cy, long_len, short_len, long_axis_deg, *bbox, z=z)


def _min_dist2(a, b):
    """Smallest squared distance between any point of a and any point of b."""
    best = float("inf")
    for px, py in a:
        for qx, qy in b:
            d = (px - qx) ** 2 + (py - qy) ** 2
            if d < best:
                best = d
    return best


def recover_oriented_columns(fragments, gap_ft, min_fragments=2):
    """Recover oriented columns from clipped/fragmented outlines.

    Revit's CAD import sometimes breaks an angled column's outline into several
    disconnected pieces at a beam junction, so no single piece forms a closed ring
    and the column is lost. This clusters nearby fragments (any two within gap_ft)
    and fits a minimum-area oriented rectangle to each cluster's combined points.

    `fragments`: list of 2D-or-3D point-lists (feet). Returns [OrientedRect]. Only
    clusters built from >= min_fragments pieces are returned (a lone stray fragment
    never becomes a column); size filtering is left to the caller.
    """
    frags = []
    for points in fragments:
        xy = [(p[0], p[1]) for p in points]
        if len(xy) >= 2:
            frags.append(xy)
    count = len(frags)
    if count == 0:
        return []

    parent = list(range(count))

    def find(i):
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    gap2 = gap_ft * gap_ft
    for i in range(count):
        for j in range(i + 1, count):
            ri, rj = find(i), find(j)
            if ri != rj and _min_dist2(frags[i], frags[j]) <= gap2:
                parent[ri] = rj

    groups = {}
    for i in range(count):
        root = find(i)
        bucket = groups.setdefault(root, {"pts": [], "n": 0})
        bucket["pts"].extend(frags[i])
        bucket["n"] += 1

    rects = []
    for bucket in groups.values():
        if bucket["n"] < min_fragments:
            continue
        distinct = set((round(x, 6), round(y, 6)) for x, y in bucket["pts"])
        if len(distinct) < 3:
            continue
        rects.append(min_area_rect(bucket["pts"]))
    return rects


def snap_to_standard(value_ft, standards_ft, tol_ft):
    """Snap a measurement to the nearest standard size if within tolerance."""
    if not standards_ft:
        return value_ft
    nearest = min(standards_ft, key=lambda s: abs(s - value_ft))
    return nearest if abs(nearest - value_ft) <= tol_ft else value_ft


def to_xy(points):
    """Project (x, y, z) tuples to 2D (x, y), returning (xy_list, z)."""
    z = points[0][2] if points else 0.0
    return [(p[0], p[1]) for p in points], z


def simplify_ring(xy):
    """Return a closed ring as a vertex list with duplicates/collinear removed.

    Input may or may not repeat the first point at the end; output never does.
    Returns [] if the result is degenerate (fewer than 3 real corners).
    """
    pts = _dedup(xy)
    if len(pts) >= 2 and _close(pts[0], pts[-1]):
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        return []
    ring = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        if not _collinear(a, b, c):
            ring.append(b)
    return ring if len(ring) >= 3 else []


def is_rectilinear(ring):
    """True if every edge of the ring is axis-aligned (horizontal or vertical)."""
    n = len(ring)
    if n < 4:
        return False
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        if abs(a[0] - b[0]) > _TOL and abs(a[1] - b[1]) > _TOL:
            return False
    return True


def decompose_to_rectangles(ring, z=0.0):
    """Partition a rectilinear ring into axis-aligned Rectangles (exact cover).

    Caller must pass a ring that passed is_rectilinear(). Returns [] for a
    degenerate ring.
    """
    if len(ring) < 4:
        return []

    xs = _sorted_unique(p[0] for p in ring)
    ys = _sorted_unique(p[1] for p in ring)
    if len(xs) < 2 or len(ys) < 2:
        return []

    cols = len(xs) - 1
    rows = len(ys) - 1

    # inside[r][c] == True when the cell centre lies inside the polygon.
    inside = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        cy = (ys[r] + ys[r + 1]) / 2.0
        for c in range(cols):
            cx = (xs[c] + xs[c + 1]) / 2.0
            inside[r][c] = _point_in_polygon(cx, cy, ring)

    rectangles = []
    consumed = [[False] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if not inside[r][c] or consumed[r][c]:
                continue
            c_end = _extend_columns(inside, consumed, r, c, cols)
            r_end = _extend_rows(inside, consumed, r, c, c_end, rows)
            for rr in range(r, r_end + 1):
                for cc in range(c, c_end + 1):
                    consumed[rr][cc] = True
            rectangles.append(
                Rectangle(xs[c], ys[r], xs[c_end + 1], ys[r_end + 1], z))
    return rectangles


def parse_column_polyline(points):
    """High-level: turn one column polyline into a parse result dict.

    Returns:
      {'status': 'rectangle'|'composite'|'non_rectilinear'|'degenerate',
       'rectangles': [Rectangle, ...]}

    Column outlines are treated as implicitly closed rings: DWG polylines with the
    'closed' flag set often arrive without a duplicated start point (first != last),
    so closure is inferred from the ring rather than from a repeated endpoint.
    Genuine open paths (e.g. 2-point leaders) collapse to < 4 corners and report
    'degenerate'.
    """
    if not points or len(points) < 4:
        return {"status": "degenerate", "rectangles": []}

    xy, z = to_xy(points)
    ring = simplify_ring(xy)
    if len(ring) < 4:
        return {"status": "degenerate", "rectangles": []}

    if not is_rectilinear(ring):
        # Not axis-aligned: a rotated rectangular column (or a genuinely irregular
        # shape). A minimum-area oriented box recovers a rotated rectangle's true
        # size+angle (even with a stray vertex) and stays tight for odd shapes,
        # so we no longer oversize these with an axis-aligned bbox.
        return {"status": "oriented_rect",
                "rectangles": [min_area_rect(ring, z)],
                "approx": True}

    rects = decompose_to_rectangles(ring, z)
    status = "rectangle" if len(rects) <= 1 else "composite"
    return {"status": status, "rectangles": rects, "approx": False}


def bounding_rectangle(ring, z=0.0):
    """Axis-aligned bounding Rectangle of a ring (used as a non-rectilinear fallback)."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return Rectangle(min(xs), min(ys), max(xs), max(ys), z)


# Line-spine detection tolerances (feet).
_SPINE_MAX_GAP_FT = 1000.0 / 304.8   # a line/leg pair closer than ~1 m can form a spine
_SPINE_CLUSTER_FT = 60.0 / 304.8     # leg edges within ~60 mm count as the same edge


def build_line_spines(line_points_list, leg_rectangles):
    """Turn bare lines on the column layer into spine Rectangles.

    A line becomes a spine only when at least two legs (column rectangles) present
    a near edge at a consistent offset on the SAME side of the line, within
    _SPINE_MAX_GAP_FT. The spine width is that measured gap -- no assumed width --
    and its length is the line's own extent. A line coincident with a single leg
    edge (e.g. an outline segment) gathers fewer than two legs and is skipped.
    """
    spines = []
    for points in line_points_list:
        if not points or len(points) < 2:
            continue
        p0, p1 = points[0], points[-1]
        d_x = abs(p1[0] - p0[0])
        d_y = abs(p1[1] - p0[1])
        if d_x < _TOL and d_y < _TOL:
            continue
        horizontal = d_x >= d_y
        if horizontal:
            line_coord = (p0[1] + p1[1]) / 2.0
            lo_ext, hi_ext = sorted((p0[0], p1[0]))
            edges = _near_edges(leg_rectangles, line_coord, lo_ext, hi_ext, axis="x")
        else:
            line_coord = (p0[0] + p1[0]) / 2.0
            lo_ext, hi_ext = sorted((p0[1], p1[1]))
            edges = _near_edges(leg_rectangles, line_coord, lo_ext, hi_ext, axis="y")

        edge_coord = _consistent_edge(edges, line_coord)
        if edge_coord is None:
            continue
        lo, hi = min(line_coord, edge_coord), max(line_coord, edge_coord)
        if horizontal:
            spines.append(Rectangle(lo_ext, lo, hi_ext, hi))
        else:
            spines.append(Rectangle(lo, lo_ext, hi, hi_ext))
    return spines


def _near_edges(leg_rectangles, line_coord, lo_ext, hi_ext, axis):
    """Collect leg edges (perpendicular coord) that lie within the gap band and
    overlap the line's extent. Returns a list of edge coordinates."""
    found = []
    for rect in leg_rectangles:
        if axis == "x":   # horizontal line: legs must overlap in x, edges are y
            if rect.x_max <= lo_ext + _TOL or rect.x_min >= hi_ext - _TOL:
                continue
            candidate_edges = (rect.y_min, rect.y_max)
        else:             # vertical line: legs must overlap in y, edges are x
            if rect.y_max <= lo_ext + _TOL or rect.y_min >= hi_ext - _TOL:
                continue
            candidate_edges = (rect.x_min, rect.x_max)
        for edge in candidate_edges:
            gap = abs(edge - line_coord)
            if _TOL < gap <= _SPINE_MAX_GAP_FT:
                found.append(edge)
    return found


def _consistent_edge(edges, line_coord):
    """Return the leg-edge coordinate shared by >= 2 legs nearest the line, else None."""
    if len(edges) < 2:
        return None
    nearest = min(edges, key=lambda e: abs(e - line_coord))
    cluster = [e for e in edges if abs(e - nearest) <= _SPINE_CLUSTER_FT]
    if len(cluster) < 2:
        return None
    return sum(cluster) / len(cluster)


# Circular-column detection tolerances (feet). Min/max diameter are user knobs
# (config); the cluster epsilon is numerical and stays here.
_CIRCLE_TOL_FT = 2.0 / 304.8         # arcs within ~2 mm centre+radius are one circle
_CIRCLE_MIN_DIA_FT = _cfg.mm_to_ft(_cfg.DEFAULTS["circle_min_dia_mm"])
_CIRCLE_MAX_DIA_FT = _cfg.mm_to_ft(_cfg.DEFAULTS["circle_max_dia_mm"])


class Circle(object):
    """A circular column footprint: centre + diameter, in feet."""

    def __init__(self, cx, cy, diameter, z=0.0):
        self.cx = cx
        self.cy = cy
        self.diameter = diameter
        self.z = z

    @property
    def center(self):
        return (self.cx, self.cy, self.z)

    def to_dict(self):
        return {
            "center": [self.cx, self.cy, self.z],
            "diameter_ft": self.diameter,
            "diameter_mm": self.diameter * 304.8,
        }


def circle_from_three_points(p1, p2, p3):
    """Exact circumcircle (cx, cy, r) of three 2D points, or None if collinear."""
    ax, ay = p1
    bx, by = p2
    cx, cy = p3
    denom = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(denom) < 1.0e-12:
        return None
    a_sq = ax * ax + ay * ay
    b_sq = bx * bx + by * by
    c_sq = cx * cx + cy * cy
    ux = (a_sq * (by - cy) + b_sq * (cy - ay) + c_sq * (ay - by)) / denom
    uy = (a_sq * (cx - bx) + b_sq * (ax - cx) + c_sq * (bx - ax)) / denom
    radius = ((ax - ux) ** 2 + (ay - uy) ** 2) ** 0.5
    return ux, uy, radius


def build_circular_columns(arc_records, min_dia_ft=None, max_dia_ft=None):
    """Recover circular columns from arc records on the column layer.

    Each arc stores start/mid/end, so a 3-point circumcircle gives its exact
    centre+radius; arcs sharing a centre+radius (a circle drawn as several
    segments) collapse to one Circle. Diameters outside the plausible column
    range (config, overridable) are dropped as annotation/noise.
    """
    min_dia_ft = _CIRCLE_MIN_DIA_FT if min_dia_ft is None else min_dia_ft
    max_dia_ft = _CIRCLE_MAX_DIA_FT if max_dia_ft is None else max_dia_ft
    clusters = []   # [cx, cy, r, count]
    z_value = 0.0
    for record in arc_records:
        points = record.points
        if len(points) < 3:
            continue
        z_value = points[0][2]
        mid = points[len(points) // 2]
        fit = circle_from_three_points(
            (points[0][0], points[0][1]), (mid[0], mid[1]),
            (points[-1][0], points[-1][1]))
        if fit is None:
            continue
        cx, cy, radius = fit
        matched = False
        for cluster in clusters:
            if (abs(cluster[0] - cx) <= _CIRCLE_TOL_FT
                    and abs(cluster[1] - cy) <= _CIRCLE_TOL_FT
                    and abs(cluster[2] - radius) <= _CIRCLE_TOL_FT):
                cluster[3] += 1
                matched = True
                break
        if not matched:
            clusters.append([cx, cy, radius, 1])

    circles = []
    for cx, cy, radius, _count in clusters:
        diameter = 2.0 * radius
        if min_dia_ft <= diameter <= max_dia_ft:
            circles.append(Circle(cx, cy, diameter, z_value))
    return circles


def _distance(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _midpoint(a, b):
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)


def beam_centerline_from_quad(ring):
    """Centerline of a 4-corner (possibly rotated) thin quad.

    Returns (start, end, width_ft) along the long axis -- the line joining the
    midpoints of the two SHORT edges. Works at any orientation, so diagonal beams
    are handled, not just axis-aligned ones.
    """
    if len(ring) != 4:
        return None
    p0, p1, p2, p3 = ring
    side_a = _distance(p0, p1)   # edges p0-p1 and p2-p3
    side_b = _distance(p1, p2)   # edges p1-p2 and p3-p0
    if side_a >= side_b:
        return _midpoint(p1, p2), _midpoint(p3, p0), side_b
    return _midpoint(p0, p1), _midpoint(p2, p3), side_a


def beam_centerline_from_rect(rect):
    """Centerline of an axis-aligned Rectangle along its long axis (start, end, width_ft)."""
    cx, cy, _z = rect.center
    if rect.width_ft >= rect.height_ft:
        return (rect.x_min, cy), (rect.x_max, cy), rect.height_ft
    return (cx, rect.y_min), (cx, rect.y_max), rect.width_ft


# Parallel-pair tolerances (a beam/member drawn as its two long edges).
# All four are user knobs (config), overridable per run.
_PARALLEL_SIN_TOL = math.sin(math.radians(_cfg.DEFAULTS["parallel_angle_deg"]))
_PAIR_MIN_WIDTH_FT = _cfg.mm_to_ft(_cfg.DEFAULTS["pair_min_width_mm"])
_PAIR_MAX_WIDTH_FT = _cfg.mm_to_ft(_cfg.DEFAULTS["pair_max_width_mm"])
_PAIR_MIN_OVERLAP_FT = _cfg.mm_to_ft(_cfg.DEFAULTS["pair_min_overlap_mm"])


def _vsub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _vdot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _vcross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _vunit(v):
    length = (v[0] * v[0] + v[1] * v[1]) ** 0.5
    return (v[0] / length, v[1] / length) if length > 1e-12 else (0.0, 0.0)


def pair_parallel_lines(lines, min_width_ft=None, max_width_ft=None,
                        min_overlap_ft=None, sin_tol=None):
    """Pair near-parallel lines ~one width apart into straight members.

    `lines`: list of (p0, p1, z) with p0/p1 = (x, y) in feet. Returns
    (segments, leftover): each segment is dict(start, end, width_ft) whose
    centerline lies on the midline over the shared overlap and whose width is the
    measured perpendicular gap. Greedy and order-independent: each line is used at
    most once, paired with the partner giving the largest genuine overlap. Lines
    with no parallel partner (junction fragments) are returned as leftover. The
    width band / overlap / parallel-angle tolerances default to config but can be
    overridden per run.
    """
    min_width_ft = _PAIR_MIN_WIDTH_FT if min_width_ft is None else min_width_ft
    max_width_ft = _PAIR_MAX_WIDTH_FT if max_width_ft is None else max_width_ft
    min_overlap_ft = _PAIR_MIN_OVERLAP_FT if min_overlap_ft is None else min_overlap_ft
    sin_tol = _PARALLEL_SIN_TOL if sin_tol is None else sin_tol
    count = len(lines)
    used = [False] * count
    segments = []
    for i in range(count):
        if used[i]:
            continue
        a0, a1, az = lines[i]
        direction = _vunit(_vsub(a1, a0))
        if direction == (0.0, 0.0):
            continue
        normal = (-direction[1], direction[0])
        best = None
        for j in range(count):
            if j == i or used[j]:
                continue
            b0, b1, _bz = lines[j]
            other = _vunit(_vsub(b1, b0))
            if abs(_vcross(direction, other)) > sin_tol:
                continue
            signed_gap = _vdot(_vsub(b0, a0), normal)
            gap = abs(signed_gap)
            if gap < min_width_ft or gap > max_width_ft:
                continue
            ta = sorted([0.0, _vdot(_vsub(a1, a0), direction)])
            tb = sorted([_vdot(_vsub(b0, a0), direction),
                         _vdot(_vsub(b1, a0), direction)])
            lo = max(ta[0], tb[0])
            hi = min(ta[1], tb[1])
            overlap = hi - lo
            if overlap < min_overlap_ft:
                continue
            if best is None or overlap > best["overlap"]:
                best = {"j": j, "signed_gap": signed_gap, "lo": lo, "hi": hi,
                        "overlap": overlap, "gap": gap}
        if best:
            used[i] = True
            used[best["j"]] = True
            offset = best["signed_gap"] / 2.0
            lo, hi = best["lo"], best["hi"]
            start = (a0[0] + direction[0] * lo + normal[0] * offset,
                     a0[1] + direction[1] * lo + normal[1] * offset)
            end = (a0[0] + direction[0] * hi + normal[0] * offset,
                   a0[1] + direction[1] * hi + normal[1] * offset)
            segments.append({"start": (start[0], start[1], az),
                             "end": (end[0], end[1], az),
                             "width_ft": best["gap"]})
    leftover = [lines[k] for k in range(count) if not used[k]]
    return segments, leftover


# --- internal helpers -------------------------------------------------------

def _dedup(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if not _close(p, out[-1]):
            out.append(p)
    return out


def _close(a, b):
    return abs(a[0] - b[0]) <= _TOL and abs(a[1] - b[1]) <= _TOL


def _collinear(a, b, c):
    cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
    len1 = math.hypot(b[0] - a[0], b[1] - a[1])
    len2 = math.hypot(c[0] - b[0], c[1] - b[1])
    if len1 < 1.0e-9 or len2 < 1.0e-9:
        return True
    return abs(cross) / (len1 * len2) <= _TOL


def _sorted_unique(values):
    out = []
    for v in sorted(values):
        if not out or abs(v - out[-1]) > _TOL:
            out.append(v)
    return out


def _point_in_polygon(x, y, ring):
    """Ray-casting test; ring is a list of (x, y) with no closing duplicate."""
    n = len(ring)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > y) != (yj > y)) and \
                (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _extend_columns(inside, consumed, r, c, cols):
    """Greedily extend a run rightward along row r; return the last column index."""
    c_end = c
    while c_end + 1 < cols and inside[r][c_end + 1] and not consumed[r][c_end + 1]:
        c_end += 1
    return c_end


def _extend_rows(inside, consumed, r, c, c_end, rows):
    """Greedily extend the [c..c_end] band upward; return the last row index."""
    r_end = r
    while r_end + 1 < rows:
        row = r_end + 1
        if all(inside[row][cc] and not consumed[row][cc]
               for cc in range(c, c_end + 1)):
            r_end = row
        else:
            break
    return r_end

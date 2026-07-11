# -*- coding: utf-8 -*-
"""PROTOTYPE: derive floor SLABS from the plan -- outline, thickness and mark.

Status: prototype, NOT wired into the pushbutton. Beams are the active workstream;
this module proves out the slab pipeline so it can be lifted in when beams are done.
It is Revit-free (imports no Revit assemblies) so it can be unit-tested and replayed
against the JSON raw-geometry exports like the beam logic.

Three outline sources, in order of preference:

(1) SLAB-EDGE LAYER (A-FLOR): each closed polyline on the slab-edge layer IS a slab
    boundary -- take it directly (loose edge lines are chained end-to-end into rings
    first). This is the normal path when the DWG carries a floor layer.

(2) MEMBER EDGES (no slab layer): the beams' and columns' DRAWN outlines bound each
    panel with true face lines; the bounded faces of that edge graph are the slab
    panels at their exact boundary (member-body strips are filtered by mean width).

(3) BEAM PERIMETER GRAPH (last resort): the placed beam CENTERLINES form a planar
    graph whose bounded faces are the panels; each face edge is then offset INWARD
    by that beam's half width so the slab meets the beam FACE instead of
    overlapping to its centreline.

Sizing and naming mirror columns/beams exactly:
    - a slab label ("S1 150 THK", "S3", "150 thk") sitting INSIDE a loop names it and
      gives its thickness;
    - a mark-only label ("S3") resolves its thickness through the schedule
      (mark -> thickness), exactly as B20 resolves through the beam schedule;
    - a loop with no label keeps thickness None (the builder falls back to the
      user-picked floor type's default thickness).
"""

import math
import re
from collections import defaultdict

from . import config
from .classify.layers import CATEGORY_SLAB_EDGE, CATEGORY_BEAM, CATEGORY_COLUMN

_MM = config.MM_PER_FT

_SNAP_MM = 50.0          # endpoint snap grid for the beam graph (junction slop)
_HEAL_MM = 600.0         # extend a beam end up to this far to meet the junction
_MIN_FACE_AREA_M2 = 1.0  # a bounded face smaller than this is a junction sliver
_CHAIN_TOL_MM = 150.0    # loose slab-edge lines chain when ends are this close
_EDGE_HEAL_MM = 350.0    # drawn member edges: close small junction gaps only
_MIN_PANEL_WIDTH_MM = 500.0   # a face slimmer than this (2A/P) is a member body, not a panel

# "S1 150 THK" / "S7_150 THK." / "S12 125" / "150 THK" / "S3" (mark-only; thickness
# via schedule). The mark joins its thickness by SPACE or UNDERSCORE -- the same
# convention the beam labels use ("B1_300 X 600").
_SLAB_LABEL = re.compile(
    r"^\s*(?:(S\d+))?[\s_]*(?:(\d{2,4})\s*(?:MM\s*)?(?:THK|THICK)?\.?)?\s*$",
    re.IGNORECASE)


# ---------------------------------------------------------------- outline source 1
def slab_loops_from_edges(records):
    """Slab boundary rings straight from the slab-edge layer, [(ring, z), ...].

    A CLOSED polyline is a ring as drawn. Open polylines and loose lines are chained
    end-to-end (within _CHAIN_TOL_MM) and kept only if they close into a ring.
    """
    tol_ft = config.mm_to_ft(_CHAIN_TOL_MM)
    rings = []
    chains = []                       # open pieces awaiting chaining
    for record in records:
        if record.category != CATEGORY_SLAB_EDGE:
            continue
        pts = [(p[0], p[1]) for p in record.points]
        if len(pts) < 2:
            continue
        z = record.points[0][2]
        if len(pts) >= 4 and _dist(pts[0], pts[-1]) <= tol_ft:
            rings.append((_dedup_ring(pts), z))
        else:
            chains.append((pts, z))
    for ring, z in _chain_into_rings(chains, tol_ft):
        rings.append((_dedup_ring(ring), z))
    return [(r, z) for r, z in rings if len(r) >= 3]


def _chain_into_rings(chains, tol_ft):
    """Greedily join open polylines end-to-end; yield the ones that close."""
    pool = [list(pts) for pts, _z in chains]
    zs = [z for _pts, z in chains]
    used = [False] * len(pool)
    out = []
    for i in range(len(pool)):
        if used[i]:
            continue
        used[i] = True
        ring = list(pool[i])
        z = zs[i]
        grown = True
        while grown:
            grown = False
            for j in range(len(pool)):
                if used[j]:
                    continue
                piece = pool[j]
                if _dist(ring[-1], piece[0]) <= tol_ft:
                    ring += piece[1:]
                elif _dist(ring[-1], piece[-1]) <= tol_ft:
                    ring += list(reversed(piece))[1:]
                elif _dist(ring[0], piece[-1]) <= tol_ft:
                    ring = piece[:-1] + ring
                elif _dist(ring[0], piece[0]) <= tol_ft:
                    ring = list(reversed(piece))[:-1] + ring
                else:
                    continue
                used[j] = True
                grown = True
        if len(ring) >= 4 and _dist(ring[0], ring[-1]) <= tol_ft:
            out.append((ring, z))
    return out


# ---------------------------------------------------------------- outline source 2
def slab_loops_from_beam_graph(beam_segments):
    """Bounded faces of the beam-centerline graph, INSET to the beam faces.

    beam_segments: the "segments" list build_beam_segments returns (start/end in
    internal feet, width_mm). Segments are split at mutual crossings, endpoints
    snapped to a _SNAP_MM grid so a T-junction meets exactly, then the planar
    faces are walked half-edge style. The unbounded outer face is dropped, as are
    junction slivers. Each face edge lies on a beam CENTRELINE, so the raw face
    would overlap half of every bounding beam -- each edge is therefore offset
    INWARD by that beam's half width and the ring rebuilt from the offset carriers
    (the slab meets the beam FACE). Returns [(ring, z), ...].
    """
    segs = []
    for s in beam_segments:
        hw = config.mm_to_ft(float(s.get("width_mm") or 0.0)) / 2.0
        segs.append(((s["start"][0], s["start"][1]),
                     (s["end"][0], s["end"][1]), hw))
    z = beam_segments[0]["start"][2] if beam_segments else 0.0
    plain = [(a, b) for a, b, _hw in segs]
    healed = _heal_endpoints(plain, config.mm_to_ft(_HEAL_MM))
    healed_hw = [(a, b, segs[i][2]) for i, (a, b) in enumerate(healed)]
    pieces = _split_at_crossings_w(healed_hw)
    snap_ft = config.mm_to_ft(_SNAP_MM)

    def key(p):
        return (round(p[0] / snap_ft), round(p[1] / snap_ft))

    nodes = {}
    edge_hw = {}
    for a, b, hw in pieces:
        for p in (a, b):
            nodes.setdefault(key(p), p)
        ka, kb = key(a), key(b)
        if ka != kb:
            edge_hw[(ka, kb)] = max(hw, edge_hw.get((ka, kb), 0.0))
            edge_hw[(kb, ka)] = edge_hw[(ka, kb)]
    adjacency = defaultdict(set)
    for (ka, kb) in edge_hw:
        adjacency[ka].add(kb)

    faces = _walk_faces(nodes, adjacency)
    min_area_ft2 = _MIN_FACE_AREA_M2 * (1000.0 / _MM) ** 2
    out = []
    for ring in faces:
        area = _signed_area(ring)
        if area <= 0 or area < min_area_ft2:
            continue
        keys = [key(p) for p in ring]
        hws = [edge_hw.get((keys[i], keys[(i + 1) % len(keys)]), 0.0)
               for i in range(len(keys))]
        inset = _inset_ring(ring, hws)
        if inset and _signed_area(inset) >= min_area_ft2 * 0.25:
            out.append((inset, z))
    return out


def _split_at_crossings_w(segs_hw):
    """_split_at_crossings, but every split piece inherits its parent's half-width."""
    plain = [(a, b) for a, b, _hw in segs_hw]
    pieces = _split_at_crossings(plain)
    out = []
    for a, b in pieces:
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        best_hw, best_d = 0.0, None
        for pa, pb, hw in segs_hw:
            d = _pt_seg_dist(mx, my, pa, pb)
            if best_d is None or d < best_d:
                best_d, best_hw = d, hw
        out.append((a, b, best_hw))
    return out


def _pt_seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2)) if l2 else 0.0
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def _inset_ring(ring, halfwidths):
    """Offset each edge of a CCW ring INWARD by its own half-width; rebuild corners.

    Edge i runs ring[i] -> ring[i+1]; the interior of a CCW ring lies to its LEFT,
    so each edge's carrier shifts along its left normal by halfwidths[i]. Each new
    vertex is the intersection of consecutive offset carriers (parallel/degenerate
    corners fall back to the plain offset point)."""
    n = len(ring)
    carriers = []
    for i in range(n):
        ax, ay = ring[i]
        bx, by = ring[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return None
        nx, ny = -dy / length, dx / length          # left normal (interior side)
        off = halfwidths[i]
        carriers.append(((ax + nx * off, ay + ny * off),
                         (bx + nx * off, by + ny * off)))
    out = []
    for i in range(n):
        p = _line_x_line(carriers[i - 1], carriers[i])
        out.append(p if p is not None else carriers[i][0])
    return out


def _line_x_line(s1, s2):
    (x1, y1), (x2, y2) = s1
    (x3, y3), (x4, y4) = s2
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


# ------------------------------------------------------- outline source 2 (middle)
def slab_loops_from_member_edges(records):
    """Bounded faces of the DRAWN beam + column edge lines, [(ring, z), ...].

    The middle outline source: no slab layer, but the beams' and columns' drawn
    outlines bound each panel with TRUE face lines -- so the faces of that edge
    graph are the slab panels at their exact boundary, no offset needed. Member
    BODIES also appear as faces (the thin strip between a beam's two edges): any
    face slimmer than _MIN_PANEL_WIDTH_MM (by mean width 2A/P) is dropped, as are
    junction slivers below the area floor.
    """
    segs = []
    z = 0.0
    for record in records:
        if record.category not in (CATEGORY_BEAM, CATEGORY_COLUMN):
            continue
        pts = record.points
        if len(pts) >= 2:
            z = pts[0][2]
        for i in range(len(pts) - 1):
            a = (pts[i][0], pts[i][1])
            b = (pts[i + 1][0], pts[i + 1][1])
            if _dist(a, b) > 1e-9:
                segs.append((a, b))
    if len(segs) < 4:
        return []
    segs = _heal_endpoints(segs, config.mm_to_ft(_EDGE_HEAL_MM))
    segs = _split_at_crossings(segs)
    snap_ft = config.mm_to_ft(_SNAP_MM)

    def key(p):
        return (round(p[0] / snap_ft), round(p[1] / snap_ft))

    nodes = {}
    for a, b in segs:
        for p in (a, b):
            nodes.setdefault(key(p), p)
    adjacency = defaultdict(set)
    for a, b in segs:
        ka, kb = key(a), key(b)
        if ka != kb:
            adjacency[ka].add(kb)
            adjacency[kb].add(ka)

    faces = _walk_faces(nodes, adjacency)
    min_area_ft2 = _MIN_FACE_AREA_M2 * (1000.0 / _MM) ** 2
    min_width_ft = config.mm_to_ft(_MIN_PANEL_WIDTH_MM)
    out = []
    for ring in faces:
        area = _signed_area(ring)
        if area <= 0 or area < min_area_ft2:
            continue
        perimeter = sum(_dist(ring[i], ring[(i + 1) % len(ring)])
                        for i in range(len(ring)))
        if perimeter <= 0 or 2.0 * area / perimeter < min_width_ft:
            continue                   # a member body (thin strip), not a panel
        out.append((ring, z))
    return out


def _heal_endpoints(segs, heal_ft):
    """Extend each segment endpoint (up to heal_ft) to the nearest carrier crossing.

    A placed beam's centerline stops at the COLUMN FACE, so at a junction the members'
    centerlines miss each other by half a column each and the graph never closes. Each
    endpoint is pushed OUTWARD along its own carrier to the closest intersection with
    another segment's carrier, provided both sit within heal_ft of their spans -- i.e.
    to the shared junction point (the column centre). Ends with no nearby partner stay
    put (a genuinely open beam end never fabricates a junction).
    """
    healed = []
    for i, (a, b) in enumerate(segs):
        new_ends = []
        for tip, other in ((a, b), (b, a)):
            dx, dy = tip[0] - other[0], tip[1] - other[1]
            length = (dx * dx + dy * dy) ** 0.5
            if length == 0:
                new_ends.append(tip)
                continue
            ux, uy = dx / length, dy / length          # outward direction at this tip
            best_s, best_p = None, None
            for j, sj in enumerate(segs):
                if j == i:
                    continue
                hit = _line_intersection((tip, (tip[0] + ux, tip[1] + uy)), sj)
                if hit is None:
                    continue
                p, s, u = hit                          # s: feet beyond the tip (param on unit dir)
                lj = _dist(*sj)
                slop = heal_ft / max(lj, 1e-9)
                if -1e-9 <= s <= heal_ft and -slop <= u <= 1.0 + slop:
                    if best_s is None or s < best_s:
                        best_s, best_p = s, p
            new_ends.append(best_p if best_p is not None else tip)
        healed.append((new_ends[0], new_ends[1]))
    return healed


def _split_at_crossings(segs):
    """Split segments where they cross or touch: X crossings AND T-junctions.

    A T-junction (one beam ending ON another's span, the usual bay layout) puts the
    cut on the RUN-THROUGH segment only; an X crossing cuts both. Without the T cut
    the run-through edge skips the junction node and the faces merge.
    """
    tol_ft = config.mm_to_ft(_SNAP_MM)
    cuts = [[] for _ in segs]
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            hit = _line_intersection(segs[i], segs[j])
            if hit is None:
                continue
            p, ti, tj = hit
            ei = tol_ft / max(_dist(*segs[i]), 1e-9)   # param-space slop, per segment
            ej = tol_ft / max(_dist(*segs[j]), 1e-9)
            if -ei <= ti <= 1.0 + ei and -ej <= tj <= 1.0 + ej:
                if ei < ti < 1.0 - ei:
                    cuts[i].append(p)
                if ej < tj < 1.0 - ej:
                    cuts[j].append(p)
    out = []
    for (a, b), pts in zip(segs, cuts):
        if not pts:
            out.append((a, b))
            continue
        along = sorted(set([0.0, 1.0] + [_param_along(a, b, p) for p in pts]))
        for t0, t1 in zip(along, along[1:]):
            if t1 - t0 < 1e-9:
                continue
            p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            out.append((p0, p1))
    return out


def _line_intersection(s1, s2):
    """((x, y), t, u) where the two segments' carrier LINES meet, or None if parallel.

    t and u are the parametric positions along s1 and s2; the caller decides how much
    endpoint slop to accept (X crossing vs T-junction).
    """
    (x1, y1), (x2, y2) = s1
    (x3, y3), (x4, y4) = s2
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return None
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1)), t, u


def _param_along(a, b, p):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) >= abs(dy):
        return (p[0] - a[0]) / dx if dx else 0.0
    return (p[1] - a[1]) / dy if dy else 0.0


def _walk_faces(nodes, adjacency):
    """All faces of the planar graph via the half-edge 'turn most CCW' walk."""
    visited = set()                    # directed edges already consumed by a face
    faces = []
    for a in adjacency:
        for b in adjacency[a]:
            if (a, b) in visited:
                continue
            ring_keys = []
            edge = (a, b)
            while edge not in visited:
                visited.add(edge)
                ring_keys.append(edge[0])
                edge = (edge[1], _next_ccw(nodes, adjacency, edge))
            faces.append([nodes[k] for k in ring_keys])
    return faces


def _next_ccw(nodes, adjacency, edge):
    """From directed edge u->v, pick the neighbour of v with the LARGEST CCW turn
    from the reversed edge (turn as far left as possible). This traces every bounded
    face counter-clockwise (positive signed area) and the one unbounded outer face
    clockwise, which is what slab_loops_from_beam_graph filters on."""
    u, v = edge
    ux, uy = nodes[u]
    vx, vy = nodes[v]
    back = math.atan2(uy - vy, ux - vx)
    best, best_turn = None, None
    for w in adjacency[v]:
        if w == u and len(adjacency[v]) > 1:
            continue
        wx, wy = nodes[w]
        ang = math.atan2(wy - vy, wx - vx)
        turn = (ang - back) % (2.0 * math.pi)   # CCW turn from the reversed edge
        if turn < 1e-12:
            turn = 2.0 * math.pi
        if best_turn is None or turn > best_turn:
            best, best_turn = w, turn
    return best if best is not None else u


# ------------------------------------------------------------------- label / sizing
def parse_slab_label(text):
    """(mark, thickness_mm) from a slab label; either may be None."""
    m = _SLAB_LABEL.match(text or "")
    if not m or (m.group(1) is None and m.group(2) is None):
        return None, None
    mark = m.group(1).upper() if m.group(1) else None
    thk = float(m.group(2)) if m.group(2) else None
    return mark, thk


def apply_slab_labels(loops, texts, schedule=None):
    """[{ring, z, mark, thickness_mm}] -- name/size each loop like columns/beams.

    A label INSIDE the loop wins (nearest to the loop centroid when several);
    a mark-only label resolves thickness via schedule[mark]. Unlabelled loops
    keep thickness None (builder falls back to the picked floor type).
    """
    schedule = schedule or {}
    out = []
    for ring, z in loops:
        cx, cy = _centroid(ring)
        best = None                     # (dist, mark, thk)
        for t in (texts or []):
            mark, thk = parse_slab_label(getattr(t, "text", "") or "")
            if mark is None and thk is None:
                continue
            p = t.point_internal
            if p is None or not _point_in_ring((p[0], p[1]), ring):
                continue
            d = (p[0] - cx) ** 2 + (p[1] - cy) ** 2
            if best is None or d < best[0]:
                best = (d, mark, thk)
        mark = best[1] if best else None
        thk = best[2] if best else None
        if thk is None and mark is not None and mark in schedule:
            entry = schedule[mark]
            thk = entry[0] if isinstance(entry, (tuple, list)) else entry
        out.append({"ring": ring, "z": z, "mark": mark, "thickness_mm": thk})
    return out


# --------------------------------------------------------------------------- utils
def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _dedup_ring(pts):
    out = []
    for p in pts:
        if not out or _dist(out[-1], p) > 1e-9:
            out.append((p[0], p[1]))
    if len(out) > 1 and _dist(out[0], out[-1]) < 1e-9:
        out.pop()
    return out


def _signed_area(ring):
    s = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _centroid(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _point_in_ring(pt, ring):
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside

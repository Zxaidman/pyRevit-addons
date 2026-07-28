# -*- coding: utf-8 -*-
"""Derive floor SLAB outlines from the plan -- outline, thickness and mark.

Wired into the CAD-to-BIM pushbutton (builders/slabs.py places the floors).
It is Revit-free (imports no Revit assemblies) so it can be unit-tested and replayed
against the JSON raw-geometry exports like the beam logic.

Two outline sources, in order of preference (the production chain):

(1) SLAB-EDGE LAYER (A-FLOR): each closed polyline on the slab-edge layer IS a slab
    boundary -- take it directly (loose edge lines are chained end-to-end into rings
    first). This is the normal path when the DWG carries a floor layer.

(2) PLACED MEMBERS (no slab layer): synthesize edge lines from the PLACED beams
    (centreline +/- half width) and the PLACED column footprint rings; the bounded
    faces of that graph are the slab panels, every vertex re-derived exactly onto
    its carrier lines by the exactness pass.

Two further sources survive for tests and offline replays only:
slab_loops_from_member_edges (drawn member linework) and
slab_loops_from_beam_graph (centreline graph, faces inset by half width).

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
from .geom import shapes

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


_ARC_CHORDS = 16   # tessellation density for a boundary arc (geometry tests only)


def apply_tolerances(tolerances):
    """Override the module's tunables from the dialog's Tolerances tab.

    The pushbutton calls this once per run; anything absent keeps its default,
    so the offline tests and replays are unaffected.
    """
    global _SNAP_MM, _EDGE_HEAL_MM, _CHAIN_TOL_MM, _MIN_PANEL_WIDTH_MM
    if not tolerances:
        return
    _SNAP_MM = float(tolerances.get("slab_snap_mm", _SNAP_MM))
    _EDGE_HEAL_MM = float(tolerances.get("slab_heal_mm", _EDGE_HEAL_MM))
    _CHAIN_TOL_MM = float(tolerances.get("slab_chain_mm", _CHAIN_TOL_MM))
    _MIN_PANEL_WIDTH_MM = float(tolerances.get("slab_min_width_mm",
                                               _MIN_PANEL_WIDTH_MM))


def _tessellate_arc(pts):
    """3-point arc record -> (chord_points, (start, mid, end)) or (pts_2d, None).

    The readers return an ARC as exactly three points (start, on-arc, end) from a
    circle fit. For ring GEOMETRY (labels, nesting, areas) the arc is sampled into
    chords; the true (start, mid, end) triple rides along so the builder can emit a
    genuine Revit Arc instead of the chords.
    """
    p2 = [(p[0], p[1]) for p in pts]
    if len(p2) != 3:
        return p2, None
    a, m, b = p2
    fit = shapes.circle_from_three_points(a, m, b)
    if not fit:
        return p2, None
    cx, cy, r = fit
    a0 = math.atan2(a[1] - cy, a[0] - cx)
    am = math.atan2(m[1] - cy, m[0] - cx)
    a1 = math.atan2(b[1] - cy, b[0] - cx)
    sweep = (a1 - a0) % (2.0 * math.pi)
    if (am - a0) % (2.0 * math.pi) > sweep:      # mid not inside CCW span: go CW
        sweep = sweep - 2.0 * math.pi
    # Adaptive chord count: a small junction fillet sampled at 16 chords puts its
    # vertices ~25 mm apart -- INSIDE the node-snap distance, so the graph pass
    # would chain-merge them and collapse the arc. Chords stay >= ~2x the snap.
    min_chord_ft = config.mm_to_ft(_SNAP_MM * 2.0)
    n_chords = max(2, min(_ARC_CHORDS, int(abs(sweep) * r / min_chord_ft)))
    chords = [(cx + r * math.cos(a0 + sweep * i / n_chords),
               cy + r * math.sin(a0 + sweep * i / n_chords))
              for i in range(n_chords + 1)]
    return chords, (a, m, b)


def _ring_arcs(ring, arc_triples, tol_ft):
    """The arc triples this ring actually TRAVERSES (order preserved).

    Endpoint membership is not enough: an arc's endpoints are junction corners
    SHARED with the neighbouring panel, whose ring runs STRAIGHT between them --
    attaching the arc there would bulge the neighbour's edge. The ring must also
    pass through the arc's MID point (i.e. it walked the arc's chords)."""
    out = []
    n = len(ring)
    for a, m, b in arc_triples:
        on_a = any(_dist(a, p) <= tol_ft for p in ring)
        on_b = any(_dist(b, p) <= tol_ft for p in ring)
        if not (on_a and on_b):
            continue
        on_m = False
        for i in range(n):
            if _pt_seg_dist(m[0], m[1], ring[i], ring[(i + 1) % n]) <= tol_ft:
                on_m = True
                break
        if on_m:
            out.append((a, m, b))
    return out


# ---------------------------------------------------------------- outline source 1
def slab_loops_from_edges(records):
    """Slab boundary rings straight from the slab-edge layer, [(ring, z, arcs), ...].

    A CLOSED polyline is a ring as drawn. Open polylines, loose lines AND boundary
    ARCS (tessellated into chords, with the true start/mid/end triple carried in
    `arcs` so the builder can rebuild a genuine curved edge) are chained end-to-end
    (within _CHAIN_TOL_MM) and kept only if they close into a ring.
    """
    tol_ft = config.mm_to_ft(_CHAIN_TOL_MM)
    rings = []
    chains = []                       # open pieces awaiting chaining
    arc_triples = []
    seen_pieces = set()               # adjacent panels re-draw shared edges: ONE copy
    for record in records:
        if record.category != CATEGORY_SLAB_EDGE:
            continue
        fp = _piece_fingerprint(record.points)
        if fp in seen_pieces:
            # the SAME edge drawn twice (each panel outlines it): chaining both
            # copies stitches an out-and-back SPUR into one ring -- a pinch that
            # Floor.Create rejects (this is what kept the curved S8 slab out).
            continue
        seen_pieces.add(fp)
        if record.kind == "arc":
            chords, triple = _tessellate_arc(record.points)
            if triple:
                arc_triples.append(triple)
            if len(chords) >= 2:
                chains.append((chords, record.points[0][2]))
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
    return [(r, z, _ring_arcs(r, arc_triples, tol_ft))
            for r, z in rings if len(r) >= 3]


def _piece_fingerprint(points):
    """Orientation-free identity of a drawn piece (10 mm grid, endpoint-sorted)."""
    def grid(p):
        return (round(p[0] * 30.48), round(p[1] * 30.48))    # ~10 mm cells
    a, b = grid(points[0]), grid(points[-1])
    mid = grid(points[len(points) // 2])
    return (min(a, b), max(a, b), mid)


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
            # take the globally CLOSEST attachment, not the first within tolerance:
            # a junction fillet arc can be SHORTER than the tolerance, so both its
            # ends "match" -- first-match then glues the wrong end and the ring
            # walks the fillet out-and-back (the pinch that kept S8 out of Revit)
            best = None                # (distance, j, mode)
            for j in range(len(pool)):
                if used[j]:
                    continue
                piece = pool[j]
                for mode, dist in (("tail_fwd", _dist(ring[-1], piece[0])),
                                   ("tail_rev", _dist(ring[-1], piece[-1])),
                                   ("head_fwd", _dist(ring[0], piece[-1])),
                                   ("head_rev", _dist(ring[0], piece[0]))):
                    if dist <= tol_ft and (best is None or dist < best[0]):
                        best = (dist, j, mode)
            if best is not None:
                _d, j, mode = best
                piece = pool[j]
                if mode == "tail_fwd":
                    ring += piece[1:]
                elif mode == "tail_rev":
                    ring += list(reversed(piece))[1:]
                elif mode == "head_fwd":
                    ring = piece[:-1] + ring
                else:
                    ring = list(reversed(piece))[:-1] + ring
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
            out.append((inset, z, []))
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
_COLUMN_RECT_PAD_MM = 80.0   # drawn linework this close inside a column rect is that column's


def _in_rect_footprint(px, py, fp, pad_ft):
    """Point inside a ("rect", cx, cy, cos, sin, half_long, half_short) + pad."""
    _kind, cx, cy, ca, sa, hl, hs = fp
    dx, dy = px - cx, py - cy
    u = dx * ca + dy * sa
    v = dy * ca - dx * sa
    return abs(u) <= hl + pad_ft and abs(v) <= hs + pad_ft


def slab_loops_from_member_edges(records, column_rects=None, beam_segments=None):
    """Bounded faces of the DRAWN beam + column edge lines, [(ring, z), ...].

    The middle outline source: no slab layer, but the beams' and columns' drawn
    outlines bound each panel with TRUE face lines -- so the faces of that edge
    graph are the slab panels at their exact boundary, no offset needed. Member
    BODIES also appear as faces (the thin strip between a beam's two edges): any
    face slimmer than _MIN_PANEL_WIDTH_MM (by mean width 2A/P) is dropped, as are
    junction slivers below the area floor.

    `column_rects` (("rect", cx, cy, cos, sin, half_long, half_short) and
    ("circle", cx, cy, r) footprints from the column pass) makes the BEAM outlines
    the primary graph and reduces columns to TRIM geometry: raw column-layer
    linework lying inside a footprint (fragmented outlines, rotated corners,
    diagonal marker strokes -- and ROUND columns drawn as dozens of tiny arc
    fragments) is REPLACED by that footprint's exact ring (4 edges for a rect, a
    fine polygon for a circle). Broken drawn rings let the face walk flood THROUGH
    the column and fuse a bay with the beam-body corridors, or notch the boundary
    (test1-3's round-column mess); an exact ring is airtight. Core WALLS --
    column-layer linework not inside any footprint -- stay in the graph so shafts
    remain bounded.

    `beam_segments` (placed centreline dicts, pre-split) lets faces that are
    mostly BEAM BODY by area be dropped: a 900-wide beam's body strip out-sizes
    the mean-width floor, and fused corridor crosses pass every perimeter test --
    but no real panel has half its AREA under beams (test6's B21/B20 strips and
    the B22/B4/B5 cross).
    """
    pad_ft = config.mm_to_ft(_COLUMN_RECT_PAD_MM)
    rects = [fp for fp in (column_rects or []) if fp[0] == "rect"]
    circles = [fp for fp in (column_rects or []) if fp[0] == "circle"]

    def _swallowed(pts):
        for fp in rects:
            if all(_in_rect_footprint(p[0], p[1], fp, pad_ft) for p in pts):
                return True
        for _kind, cx, cy, r in circles:
            reach = (r + pad_ft) ** 2
            if all((p[0] - cx) ** 2 + (p[1] - cy) ** 2 <= reach for p in pts):
                return True
        return False

    segs = []
    src = []                          # per segment: True when it is a BEAM edge
    carriers = []                     # straight input lines (never arc chords)
    z = 0.0
    arc_triples = []
    for record in records:
        if record.category not in (CATEGORY_BEAM, CATEGORY_COLUMN):
            continue
        is_beam = record.category == CATEGORY_BEAM
        if not is_beam and (rects or circles) and _swallowed(record.points):
            continue                  # replaced by the clean footprint ring below;
            # swallowed arcs must not register triples either, or the fragments a
            # round column is drawn from become phantom micro-arcs on the boundary
        is_arc = record.kind == "arc"
        if is_arc:
            # a 3-point arc record (round column, junction fillet, curved beam edge)
            # contributes two long CHORDS if used raw -- junk faces and phantom
            # crossings. Sample it; keep the triple so a face running the WHOLE arc
            # gets a genuine curved edge (a partial run falls back to its chords).
            pts2, triple = _tessellate_arc(record.points)
            if triple:
                arc_triples.append(triple)
            pts = [(x, y, record.points[0][2]) for x, y in pts2]
        else:
            pts = record.points
        if len(pts) >= 2:
            z = pts[0][2]
        for i in range(len(pts) - 1):
            a = (pts[i][0], pts[i][1])
            b = (pts[i + 1][0], pts[i + 1][1])
            if _dist(a, b) > 1e-9:
                segs.append((a, b))
                src.append(is_beam)
                if not is_arc:
                    carriers.append((a, b))
    _append_footprint_rings(segs, src, rects, circles, carriers=carriers)
    return _faces_from_edge_graph(segs, src, arc_triples, z, circles, beam_segments,
                                  carriers=carriers)


def slab_loops_from_placed_members(records, beam_segments, column_rects=None,
                                   trim_columns=True, keep_points=None):
    """Bounded faces of the PLACED geometry, [(ring, z, arcs), ...].

    `keep_points` (staircase location): faces containing any of these (x, y)
    points bypass the beam-fraction and body-coverage filters -- a stair bay is
    bounded by WALLS and would otherwise be dropped as a shaft. The stair layout
    asks for the face under its STAIRCASE/ST-n text this way.

    `trim_columns=False` is the v0.45.1 DIAGNOSTIC mode (isolating the test4/5
    misalignment): the graph is built from the placed BEAM edges alone -- no
    column footprint rings, no round-column wraps, and no column-layer linework
    (walls included) -- so any misalignment that remains cannot come from the
    column trimming. Slab corners run square through the column corners and
    shaft faces are not wall-bounded in this mode; that is expected.

    The user-proposed source: slabs are created AFTER beams and columns, so their
    outlines can come from what was actually placed instead of the raw drawn
    linework -- each straight beam contributes its two long edge lines
    (centreline offset by half its width) plus end caps, every column its exact
    footprint ring. Alignment with the placed members is then exact BY
    CONSTRUCTION. From the drawn records only two things are kept: BEAM-layer
    ARCS (curved beam edges and junction fillets, with their true triples) and
    column-layer WALL linework outside every footprint (so shafts stay bounded).
    """
    pad_ft = config.mm_to_ft(_COLUMN_RECT_PAD_MM)
    junction_fps = column_rects            # caps still suppress at column junctions
    if not trim_columns:
        column_rects = None                # beam edges ONLY: no rings, no wraps
    rects = [fp for fp in (column_rects or []) if fp[0] == "rect"]
    circles = [fp for fp in (column_rects or []) if fp[0] == "circle"]
    jrects = [fp for fp in (junction_fps or []) if fp[0] == "rect"]
    jcircles = [fp for fp in (junction_fps or []) if fp[0] == "circle"]

    def _swallowed(pts):
        for fp in rects:
            if all(_in_rect_footprint(p[0], p[1], fp, pad_ft) for p in pts):
                return True
        for _kind, cx, cy, r in circles:
            reach = (r + pad_ft) ** 2
            if all((p[0] - cx) ** 2 + (p[1] - cy) ** 2 <= reach for p in pts):
                return True
        return False

    beams_xy = []
    for seg in (beam_segments or []):
        x1, y1 = seg["start"][0], seg["start"][1]
        x2, y2 = seg["end"][0], seg["end"][1]
        length = _dist((x1, y1), (x2, y2))
        half_w = (seg.get("width_mm") or 0.0) / _MM / 2.0
        if length > 0 and half_w > 0:
            beams_xy.append((x1, y1, x2, y2, length, half_w, seg["start"][2]))

    def _junction_end(px, py, self_idx):
        # a beam end meeting a column or another beam gets its boundary from THAT
        # member; a cap there only adds jog material at the corner (columns keep
        # suppressing caps even in the trim_columns=False diagnostic mode)
        for fp in jrects:
            if _in_rect_footprint(px, py, fp, pad_ft):
                return True
        for _kind, cx, cy, r in jcircles:
            if (px - cx) ** 2 + (py - cy) ** 2 <= (r + pad_ft) ** 2:
                return True
        for k, (x1, y1, x2, y2, length, half_w, _bz) in enumerate(beams_xy):
            if k == self_idx:
                continue
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            dx, dy = px - (x1 + x2) / 2.0, py - (y1 + y2) / 2.0
            if (abs(dx * ux + dy * uy) <= length / 2.0 + pad_ft and
                    abs(dy * ux - dx * uy) <= half_w + pad_ft):
                return True
        return False

    segs = []
    src = []
    carriers = []                     # straight input lines (never arc chords)
    z = 0.0
    arc_triples = []
    for idx, (x1, y1, x2, y2, length, half_w, bz) in enumerate(beams_xy):
        z = bz
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        nx, ny = -uy * half_w, ux * half_w
        e1a, e1b = (x1 + nx, y1 + ny), (x2 + nx, y2 + ny)
        e2a, e2b = (x1 - nx, y1 - ny), (x2 - nx, y2 - ny)
        segs += [(e1a, e1b), (e2a, e2b)]
        src += [True, True]
        carriers += [(e1a, e1b), (e2a, e2b)]
        if not _junction_end(x1, y1, idx):
            segs.append((e1a, e2a))               # cap only a FREE end
            src.append(True)
            carriers.append((e1a, e2a))
        if not _junction_end(x2, y2, idx):
            segs.append((e1b, e2b))
            src.append(True)
            carriers.append((e1b, e2b))
    for record in records:
        is_beam = record.category == CATEGORY_BEAM
        if is_beam:
            if record.kind != "arc":
                continue               # straight linework replaced by placed edges
        elif record.category == CATEGORY_COLUMN:
            if not trim_columns:
                continue               # diagnostic mode: beam edges ONLY
            if _swallowed(record.points):
                continue               # replaced by the footprint ring
        else:
            continue
        is_arc = record.kind == "arc"
        if is_arc:
            pts2, triple = _tessellate_arc(record.points)
            if triple:
                arc_triples.append(triple)
            pts = [(x, y, record.points[0][2]) for x, y in pts2]
        else:
            pts = record.points
        for i in range(len(pts) - 1):
            a = (pts[i][0], pts[i][1])
            b = (pts[i + 1][0], pts[i + 1][1])
            if _dist(a, b) > 1e-9:
                segs.append((a, b))
                src.append(is_beam)
                if not is_arc:
                    carriers.append((a, b))
    _append_footprint_rings(segs, src, rects, circles, carriers=carriers)
    return _faces_from_edge_graph(segs, src, arc_triples, z, circles, beam_segments,
                                  carriers=carriers, keep_points=keep_points)


def _append_footprint_rings(segs, src, rects, circles, carriers=None):
    """The clean column TRIM rings: 4 edges per rect, a fine polygon per circle.

    Rect ring edges are CARRIERS for the exactness pass; circle chords are not
    (a circle's true carrier is the circle itself)."""
    for fp in rects:
        _kind, cx, cy, ca, sa, hl, hs = fp
        corners = [(cx + su * hl * ca - sv * hs * sa, cy + su * hl * sa + sv * hs * ca)
                   for su, sv in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
        for i in range(4):
            segs.append((corners[i], corners[(i + 1) % 4]))
            src.append(False)
            if carriers is not None:
                carriers.append((corners[i], corners[(i + 1) % 4]))
    min_chord = config.mm_to_ft(_SNAP_MM * 2.0)   # chords must outsize the node snap
    for _kind, cx, cy, r in circles:
        n = max(8, min(48, int(2.0 * math.pi * r / min_chord)))
        ring = [(cx + r * math.cos(2.0 * math.pi * i / n),
                 cy + r * math.sin(2.0 * math.pi * i / n)) for i in range(n)]
        for i in range(n):
            segs.append((ring[i], ring[(i + 1) % n]))
            src.append(False)


def _faces_from_edge_graph(segs, src, arc_triples, z, circles, beam_segments,
                           carriers=None, keep_points=None):
    """Shared face machinery: heal -> split -> cluster -> prune -> walk -> filter.

    A face containing one of `keep_points` skips the beam-fraction and body-
    coverage filters (a wall-bounded stair bay is a REAL area to the stair
    layout, not a shaft to discard); area/width/simple checks still apply.

    Returns [(ring, z, arcs)]; `arcs` carries the drawn triples the ring traverses
    PLUS synthesized wrap arcs where the boundary runs along a circle footprint.
    `carriers` (input lines excluding circle-polygon chords) drive the EXACTNESS
    pass: every output vertex is snapped to the intersection of its two nearest
    carriers (line x line at corners, line x circle at round-column wraps) --
    cluster centroids otherwise drift junction vertices up to snap/2 off the beam
    edge (the reported 14 mm slab/beam misalignment).
    """
    if len(segs) < 4:
        return []
    beam_lines = [segs[i] for i in range(len(segs)) if src[i]]
    segs = _heal_endpoints(segs, config.mm_to_ft(_EDGE_HEAL_MM))   # order-preserving
    segs, src = _split_at_crossings(segs, flags=src)
    snap_ft = config.mm_to_ft(_SNAP_MM)

    # Node identity by NEIGHBOUR-CELL clustering, not same-cell rounding: two
    # endpoints 44 mm apart can round into ADJACENT 50 mm cells (a beam edge tip
    # landing just shy of a column ring corner), stay two nodes, dangle, get
    # pruned -- and the bay face floods over the beam body (test4/5's overlap).
    # Clustering merges every endpoint pair within snap_ft regardless of grid
    # alignment; a node with any BEAM-edge member sits ON the beam edge (the beam
    # outline is the alignment authority, column rings are trim).
    key, nodes = _cluster_nodes(
        [p for seg in segs for p in seg], snap_ft,
        prefer=[f for flag in src for f in (flag, flag)])
    adjacency = defaultdict(set)
    for a, b in segs:
        ka, kb = key(a), key(b)
        if ka != kb:
            adjacency[ka].add(kb)
            adjacency[kb].add(ka)

    # PRUNE dangling stubs: an edge chain ending mid-air (a clipped edge, an opening
    # jamb) makes every face that meets it walk out-and-back through the stub -- a
    # PINCHED ring Floor.Create rejects. 96 of test4/5's bays were dropped this way.
    changed = True
    while changed:
        changed = False
        for node in list(adjacency.keys()):
            if len(adjacency[node]) == 1:
                other = next(iter(adjacency[node]))
                adjacency[other].discard(node)
                del adjacency[node]
                changed = True

    faces = _walk_faces(nodes, adjacency)
    bodies = []
    for seg in (beam_segments or []):
        x1, y1 = seg["start"][0], seg["start"][1]
        x2, y2 = seg["end"][0], seg["end"][1]
        length = _dist((x1, y1), (x2, y2))
        if length <= 0:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        half_w = (seg.get("width_mm") or 0.0) / _MM / 2.0
        if half_w > 0:
            bodies.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0, ux, uy,
                           length / 2.0 + half_w, half_w))
    min_area_ft2 = _MIN_FACE_AREA_M2 * (1000.0 / _MM) ** 2
    min_width_ft = config.mm_to_ft(_MIN_PANEL_WIDTH_MM)
    arc_tol_ft = config.mm_to_ft(_SNAP_MM * 2.0)
    carrier_idx = None
    out = []
    for ring in faces:
        area = _signed_area(ring)
        if area <= 0 or area < min_area_ft2:
            continue
        perimeter = sum(_dist(ring[i], ring[(i + 1) % len(ring)])
                        for i in range(len(ring)))
        if perimeter <= 0 or 2.0 * area / perimeter < min_width_ft:
            continue                   # a member body (thin strip), not a panel
        if not _is_simple_ring(ring):
            continue                   # bow-tie / self-crossing face: never a panel
        kept = any(_point_in_ring(kp, ring) for kp in (keep_points or []))
        if not kept and _beam_fraction(ring, beam_lines) < _MIN_BEAM_FRACTION:
            continue                   # bounded by WALLS, not beams: a lift/stair shaft
        if not kept and _body_coverage(ring, bodies) > _MAX_BODY_COVERAGE:
            continue                   # mostly under beam bodies: a member, not a panel
        if carriers:
            if carrier_idx is None:
                carrier_idx = _carrier_index(carriers, snap_ft)
            ring = _snap_ring_to_carriers(ring, carriers, circles, snap_ft,
                                          index=carrier_idx)
            ring = _square_off_chamfers(ring, carriers)
            if len(ring) < 3:
                continue
        arcs = _ring_arcs(ring, arc_triples, arc_tol_ft)
        arcs += _circle_wrap_arcs(ring, circles, arc_tol_ft)
        out.append((ring, z, arcs))
    return out


_CHAMFER_MAX_MM = 150.0     # a boundary stub shorter than this may be a false chamfer
_CHAMFER_PARALLEL = 0.17    # ~10 degrees: "this stub lies along a real edge"


def _square_off_chamfers(ring, carriers):
    """Replace false CHAMFERS at a corner with the corner itself.

    Where two boundary edges meet at a column, the face walk can leave a short
    stub across the corner instead of a clean step, and the exactness pass keeps
    it because each of its ends is legitimately on a carrier. The result is a
    SLOPED trim where the slab should turn square.

    A stub is false only when it lies along NO carrier -- a genuinely chamfered
    column edge is drawn, so it has one. For a false stub the two neighbouring
    edges are extended to their own crossing and the stub's two vertices are
    replaced by that single point, which is exactly the corner they both came
    from.
    """
    if not carriers or len(ring) < 4:
        return ring
    max_len = config.mm_to_ft(_CHAMFER_MAX_MM)
    directions = []
    for (ax, ay), (bx, by) in carriers:
        length = _dist((ax, ay), (bx, by))
        if length > 1e-9:
            directions.append(((bx - ax) / length, (by - ay) / length,
                               (ax, ay)))
    out = list(ring)
    n = len(out)
    replaced = {}
    for i in range(n):
        a, b = out[i], out[(i + 1) % n]
        length = _dist(a, b)
        if length < 1e-9 or length > max_len:
            continue
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        on_carrier = False
        for dx, dy, origin in directions:
            if abs(ux * dy - uy * dx) > _CHAMFER_PARALLEL:
                continue
            # same direction AND the stub sits on that carrier's line
            if abs((a[0] - origin[0]) * dy - (a[1] - origin[1]) * dx) <= max_len / 3.0:
                on_carrier = True
                break
        if on_carrier:
            continue
        prev_pt = out[(i - 1) % n]
        next_pt = out[(i + 2) % n]
        if _dist(prev_pt, a) < 2.0 * length or _dist(b, next_pt) < 2.0 * length:
            continue                       # neighbours too short to trust
        crossing = _line_x_line((prev_pt, a), (b, next_pt))
        if crossing is None:
            continue                       # near-parallel: not a corner
        if _dist(crossing, a) > 4.0 * length or _dist(crossing, b) > 4.0 * length:
            continue                       # the crossing is not this corner
        replaced[i] = crossing
        replaced[(i + 1) % n] = crossing
    if not replaced:
        return ring
    squared = [replaced.get(i, point) for i, point in enumerate(out)]
    return _dedup_ring(squared)


def _carrier_index(carriers, snap_ft):
    """Precomputed spatial lookup for the exactness pass (shared per source run)."""
    reach = snap_ft * 1.2
    cell_ft = config.mm_to_ft(_GRAPH_CELL_MM)
    grid, _boxes = _seg_grid(carriers, cell_ft, pad_ft=reach)
    return grid, cell_ft


def _snap_ring_to_carriers(ring, carriers, circles, snap_ft, index=None):
    """Snap every ring vertex onto its authoritative geometry (the EXACTNESS pass).

    A vertex is a walk node -- the centroid of a weld cluster, which can sit up to
    snap/2 off the true junction. The true position is fully determined by the
    input geometry: the crossing of the two nearest CARRIER lines (beam edge x
    beam edge, beam edge x column ring edge), the nearest line's intersection
    with a circle footprint at a round-column wrap, or the foot on a single
    carrier along a plain edge. Vertices with no carrier within reach stay put.
    """
    reach = snap_ft * 1.2
    slop = config.mm_to_ft(_EDGE_HEAL_MM) + snap_ft   # heal may extend past spans
    grid, cell_ft = index if index is not None else _carrier_index(carriers, snap_ft)
    n = len(ring)
    out = []
    for i, (vx, vy) in enumerate(ring):
        near = []                     # (distance, ux, uy, ax, ay) per carrier line
        for k in grid.get((int(math.floor(vx / cell_ft)),
                           int(math.floor(vy / cell_ft))), ()):
            a, b = carriers[k]
            ax, ay = a
            dx, dy = b[0] - ax, b[1] - ay
            length = (dx * dx + dy * dy) ** 0.5
            if length <= 0:
                continue
            ux, uy = dx / length, dy / length
            t = (vx - ax) * ux + (vy - ay) * uy
            if t < -slop or t > length + slop:
                continue
            perp = abs((vx - ax) * uy - (vy - ay) * ux)
            if perp <= reach:
                near.append((perp, ux, uy, ax, ay))
        near.sort(key=lambda c: c[0])

        # TOPOLOGY-AWARE carrier choice: the vertex belongs to its two ring edges,
        # so its true position is the crossing of the carriers PARALLEL to them.
        # Nearest-two would grab a diamond column's two ring edges at a junction
        # and weld the beam edge onto the column APEX (test4/5's 24-60mm tilts of
        # long boundaries -- the diamonds' 45-degree edges out-crowd the beam edge).
        def _edge_dir(p, q):
            dx, dy = q[0] - p[0], q[1] - p[1]
            length = (dx * dx + dy * dy) ** 0.5
            return (dx / length, dy / length) if length > 1e-9 else None

        def _match(direction):
            if direction is None:
                return None
            for cand in near:         # nearest carrier parallel to this ring edge
                if abs(direction[0] * cand[2] - direction[1] * cand[1]) <= 0.17:
                    return cand
            return None

        d_in = _edge_dir(ring[i - 1], (vx, vy))
        d_out = _edge_dir((vx, vy), ring[(i + 1) % n])
        c_in = _match(d_in)
        c_out = _match(d_out)
        on_circle = None
        for _kind, cx, cy, r in circles:
            d = abs(_dist((vx, vy), (cx, cy)) - r)
            if d <= reach and (on_circle is None or d < on_circle[0]):
                on_circle = (d, cx, cy, r)
        lines = []
        for cand in (c_in, c_out):
            if cand is not None and all(
                    abs(cand[1] * o[2] - cand[2] * o[1]) > 0.15 for o in lines):
                lines.append(cand)
        nx, ny = vx, vy
        if len(lines) == 2:           # corner: exact crossing of ITS two carriers
            _d1, u1x, u1y, a1x, a1y = lines[0]
            _d2, u2x, u2y, a2x, a2y = lines[1]
            det = u1x * u2y - u1y * u2x
            if abs(det) > 1e-9:
                s = ((a2x - a1x) * u2y - (a2y - a1y) * u2x) / det
                px, py = a1x + s * u1x, a1y + s * u1y
                if _dist((px, py), (vx, vy)) <= reach * 2.0:
                    nx, ny = px, py
        elif len(lines) == 1:
            _d, ux, uy, ax, ay = lines[0]
            hit = None
            if on_circle is not None:        # wrap end: exact line x circle point
                _dc, cx, cy, r = on_circle   # (the other ring edge is a chord, so
                fx, fy = ax - cx, ay - cy    # no line carrier matches it)
                bq = fx * ux + fy * uy
                disc = bq * bq - (fx * fx + fy * fy - r * r)
                if disc >= 0:
                    root = disc ** 0.5
                    cands = [(ax + t * ux, ay + t * uy) for t in (-bq - root, -bq + root)]
                    px, py = min(cands, key=lambda p: _dist(p, (vx, vy)))
                    if _dist((px, py), (vx, vy)) <= reach * 2.0:
                        hit = (px, py)
            if hit is None:                  # plain edge: foot on the carrier
                t = (vx - ax) * ux + (vy - ay) * uy
                hit = (ax + t * ux, ay + t * uy)
            nx, ny = hit
        elif on_circle is not None:
            _dc, cx, cy, r = on_circle       # mid-wrap chord vertex: radial
            fx, fy = vx - cx, vy - cy
            d = (fx * fx + fy * fy) ** 0.5 or 1.0
            nx, ny = cx + fx / d * r, cy + fy / d * r
        if not out or _dist((nx, ny), out[-1]) > 1e-9:
            out.append((nx, ny))
    while len(out) > 1 and _dist(out[0], out[-1]) <= 1e-9:
        out.pop()
    return out


def _circle_wrap_arcs(ring, circles, tol_ft):
    """Synthesized (start, mid, end) triples where the ring WRAPS a round column.

    The clean circle ring is pure chords, so without this every round-column trim
    came out as line strings (the 0.42.0 regression). Each maximal run of >= 3
    consecutive ring vertices lying ON a circle footprint becomes one triple with
    its endpoints PROJECTED onto the circle -- the builder welds the ring to the
    triple and emits a genuine Arc."""
    if not circles:
        return []
    n = len(ring)
    out = []
    for _kind, cx, cy, r in circles:
        on = [abs(_dist(p, (cx, cy)) - r) <= tol_ft for p in ring]
        if not any(on) or all(on):
            continue                   # no wrap, or the ring IS the column face
        i = 0
        while i < n:
            if not (on[i] and not on[i - 1]):
                i += 1
                continue
            j = i                      # run start: walk to its end (circular)
            length = 1
            while on[(j + 1) % n] and length < n:
                j = (j + 1) % n
                length += 1
            if length >= 3:
                def _proj(p):
                    dx, dy = p[0] - cx, p[1] - cy
                    d = (dx * dx + dy * dy) ** 0.5 or 1.0
                    return (cx + dx / d * r, cy + dy / d * r)
                mid = ring[(i + length // 2) % n]
                out.append((_proj(ring[i]), _proj(mid), _proj(ring[j])))
            i = i + length if j >= i else n
    return out


# A panel is framed by beams; a shaft is framed by walls. Measured on test1-3:
# lift shafts < 0.3, STAIR WELLS 0.33 (one flight-side beam, walls elsewhere),
# real panels >= 0.44 -- 0.35 drops both shafts and stair wells with margin.
# (A wall-fraction ceiling was tried instead and dropped REAL bays that nestle
# into an L of the core: wall-adjacency does not separate wells from bays.)
_MIN_BEAM_FRACTION = 0.35

# A face mostly UNDER the placed beams is a member body / fused corridor, never a
# panel (corridors of 900-wide beams beat the mean-width floor; a real bay's area
# under beams is just the trim slivers, well below 0.2).
_MAX_BODY_COVERAGE = 0.5
_COVERAGE_STEP_MM = 150.0     # sample grid pitch for the area-coverage estimate


def _body_coverage(ring, bodies):
    """Approximate fraction of the ring's area lying inside beam BODY rectangles.

    Grid point-sampling (pitch _COVERAGE_STEP_MM, widened on large faces to keep
    the sample count bounded): robust against the polygon-clip corner cases of
    long thin fused corridors. `bodies` are (cx, cy, ux, uy, half_len, half_w)."""
    if not bodies:
        return 0.0
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    step = config.mm_to_ft(_COVERAGE_STEP_MM)
    span = max(x1 - x0, y1 - y0)
    if span / step > 120.0:
        step = span / 120.0
    near = [b for b in bodies
            if b[0] + b[4] >= x0 and b[0] - b[4] <= x1 and
            b[1] + b[4] >= y0 and b[1] - b[4] <= y1]
    if not near:
        return 0.0
    inside_n = 0
    covered = 0
    yy = y0 + step / 2.0
    while yy < y1:
        xx = x0 + step / 2.0
        while xx < x1:
            if _point_in_ring((xx, yy), ring):
                inside_n += 1
                for cx, cy, ux, uy, hl, hw in near:
                    dx, dy = xx - cx, yy - cy
                    if abs(dx * ux + dy * uy) <= hl and abs(dy * ux - dx * uy) <= hw:
                        covered += 1
                        break
            xx += step
        yy += step
    return (covered / float(inside_n)) if inside_n else 0.0


def _beam_fraction(ring, beam_lines, tol_mm=60.0):
    """Fraction of the ring's perimeter that runs along a BEAM-layer edge.

    A lift or stair shaft is enclosed by core WALLS (column-layer edges), so its
    face has almost no beam-edge boundary -- a real floor panel is framed by beams
    on most sides. Sampled at edge midpoints, weighted by edge length."""
    tol_ft = config.mm_to_ft(tol_mm)
    n = len(ring)
    total = 0.0
    on_beam = 0.0
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        length = _dist(a, b)
        if length <= 0:
            continue
        total += length
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        for ls, le in beam_lines:
            if _pt_seg_dist(mx, my, ls, le) <= tol_ft:
                on_beam += length
                break
    return (on_beam / total) if total else 0.0


def _is_simple_ring(ring):
    """True when the ring neither crosses NOR touches itself (valid floor boundary).

    Floor.Create also rejects a PINCH -- the same vertex visited twice (a figure-8
    through a junction node): no two edges cross, but the loop is not simple."""
    n = len(ring)
    seen = set()
    for x, y in ring:
        key = (round(x * 3048.0), round(y * 3048.0))    # 0.1 mm grid
        if key in seen:
            return False
        seen.add(key)
    for i in range(n):
        a1, b1 = ring[i], ring[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            a2, b2 = ring[j], ring[(j + 1) % n]
            if _segments_cross(a1, b1, a2, b2):
                return False
    return True


def _segments_cross(a1, b1, a2, b2):
    (x1, y1), (x2, y2) = a1, b1
    (x3, y3), (x4, y4) = a2, b2
    d = (x2 - x1) * (y4 - y3) - (y2 - y1) * (x4 - x3)
    if abs(d) < 1e-12:
        return False
    t = ((x3 - x1) * (y4 - y3) - (y3 - y1) * (x4 - x3)) / d
    u = ((x3 - x1) * (y2 - y1) - (y3 - y1) * (x2 - x1)) / d
    eps = 1e-9
    return eps < t < 1.0 - eps and eps < u < 1.0 - eps


def _cluster_nodes(points, snap_ft, prefer=None):
    """(key_fn, positions): endpoint identity by proximity clustering.

    Union-find over grid buckets: every pair of points within snap_ft merges
    (checked across the 3x3 neighbouring cells, so the cell-boundary blind spot
    of plain rounding is gone -- two endpoints 44 mm apart ALWAYS unify). A
    cluster's total spread stays under ~1.5x snap: transitive chains would
    otherwise swallow whole runs of closely-spaced vertices (an arc's chords, a
    short jog) into one node and collapse real geometry. A cluster's position is
    the centroid of its PREFERRED members when `prefer` flags any (a beam edge
    tip merging with a column ring vertex must land ON the beam edge -- the
    centroid of both tilted long straight boundaries by up to snap/2), else the
    centroid of all. key_fn maps a coordinate pair to its cluster id.
    """
    pts = []
    seen = {}
    pref = []
    for idx, p in enumerate(points):
        q = (p[0], p[1])
        flag = bool(prefer[idx]) if prefer is not None else False
        if q not in seen:
            seen[q] = len(pts)
            pts.append(q)
            pref.append(flag)
        elif flag:
            pref[seen[q]] = True
    parent = list(range(len(pts)))
    bbox = [[x, y, x, y] for (x, y) in pts]     # per-root min/max extent

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    max_span = snap_ft * 1.5
    cells = defaultdict(list)
    for i, (x, y) in enumerate(pts):
        cells[(int(math.floor(x / snap_ft)), int(math.floor(y / snap_ft)))].append(i)
    snap2 = snap_ft * snap_ft
    for (cx, cy), members in cells.items():
        for dx in (0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy < 0:
                    continue           # each unordered cell pair once
                other = cells.get((cx + dx, cy + dy))
                if not other:
                    continue
                for i in members:
                    xi, yi = pts[i]
                    for j in other:
                        if i >= j and (dx, dy) == (0, 0):
                            continue
                        xj, yj = pts[j]
                        if (xi - xj) ** 2 + (yi - yj) ** 2 <= snap2:
                            ri, rj = find(i), find(j)
                            if ri == rj:
                                continue
                            bi, bj = bbox[ri], bbox[rj]
                            x0 = min(bi[0], bj[0])
                            y0 = min(bi[1], bj[1])
                            x1 = max(bi[2], bj[2])
                            y1 = max(bi[3], bj[3])
                            if x1 - x0 > max_span or y1 - y0 > max_span:
                                continue          # would swallow real geometry
                            parent[rj] = ri
                            bbox[ri] = [x0, y0, x1, y1]
    sums = defaultdict(lambda: [0.0, 0.0, 0, 0.0, 0.0, 0])
    for i, (x, y) in enumerate(pts):
        r = find(i)
        s = sums[r]
        s[0] += x
        s[1] += y
        s[2] += 1
        if pref[i]:
            s[3] += x
            s[4] += y
            s[5] += 1
    positions = {}
    for r, s in sums.items():
        if s[5]:
            positions[r] = (s[3] / s[5], s[4] / s[5])
        else:
            positions[r] = (s[0] / s[2], s[1] / s[2])
    index = seen

    def key(p):
        return find(index[(p[0], p[1])])

    return key, positions


_GRAPH_CELL_MM = 3000.0   # spatial-bucket size for the O(n^2)->O(n*k) graph passes


def _seg_grid(segs, cell_ft, pad_ft=0.0):
    """(grid, boxes): cell -> segment indices whose padded bbox covers the cell."""
    grid = defaultdict(list)
    boxes = []
    for i, (a, b) in enumerate(segs):
        x0, x1 = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
        y0, y1 = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
        box = (x0 - pad_ft, y0 - pad_ft, x1 + pad_ft, y1 + pad_ft)
        boxes.append(box)
        for cx in range(int(math.floor(box[0] / cell_ft)),
                        int(math.floor(box[2] / cell_ft)) + 1):
            for cy in range(int(math.floor(box[1] / cell_ft)),
                            int(math.floor(box[3] / cell_ft)) + 1):
                grid[(cx, cy)].append(i)
    return grid, boxes


def _heal_endpoints(segs, heal_ft):
    """Extend each segment endpoint (up to heal_ft) to the nearest carrier crossing.

    A placed beam's centerline stops at the COLUMN FACE, so at a junction the members'
    centerlines miss each other by half a column each and the graph never closes. Each
    endpoint is pushed OUTWARD along its own carrier to the closest intersection with
    another segment's carrier, provided both sit within heal_ft of their spans -- i.e.
    to the shared junction point (the column centre). Ends with no nearby partner stay
    put (a genuinely open beam end never fabricates a junction). Candidate partners
    come from a spatial grid (a hit must lie within heal_ft of the tip AND near the
    partner's span), so the pass is O(n*k) instead of all-pairs.
    """
    cell_ft = config.mm_to_ft(_GRAPH_CELL_MM)
    grid, _boxes = _seg_grid(segs, cell_ft, pad_ft=2.0 * heal_ft)
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
            candidates = set()
            for cx in range(int(math.floor((tip[0] - heal_ft) / cell_ft)),
                            int(math.floor((tip[0] + heal_ft) / cell_ft)) + 1):
                for cy in range(int(math.floor((tip[1] - heal_ft) / cell_ft)),
                                int(math.floor((tip[1] + heal_ft) / cell_ft)) + 1):
                    candidates.update(grid.get((cx, cy), ()))
            best_s, best_p = None, None
            for j in sorted(candidates):
                if j == i:
                    continue
                sj = segs[j]
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


def _split_at_crossings(segs, flags=None):
    """Split segments where they cross or touch: X crossings AND T-junctions.

    A T-junction (one beam ending ON another's span, the usual bay layout) puts the
    cut on the RUN-THROUGH segment only; an X crossing cuts both. Without the T cut
    the run-through edge skips the junction node and the faces merge. Candidate
    pairs come from a spatial grid + bbox overlap, so the pass is O(n*k) instead
    of all-pairs (test4's ~4k edges took tens of seconds otherwise). When `flags`
    (one per segment) is given, pieces inherit their parent's flag and the return
    is (segments, flags).
    """
    tol_ft = config.mm_to_ft(_SNAP_MM)
    cell_ft = config.mm_to_ft(_GRAPH_CELL_MM)
    grid, boxes = _seg_grid(segs, cell_ft, pad_ft=tol_ft)
    cuts = [[] for _ in segs]
    checked = set()
    for members in grid.values():
        for ii in range(len(members)):
            for jj in range(ii + 1, len(members)):
                i, j = members[ii], members[jj]
                if i > j:
                    i, j = j, i
                pair = i * len(segs) + j
                if pair in checked:
                    continue
                checked.add(pair)
                bi, bj = boxes[i], boxes[j]
                if bi[2] < bj[0] or bj[2] < bi[0] or bi[3] < bj[1] or bj[3] < bi[1]:
                    continue
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
    out_flags = []
    for idx, ((a, b), pts) in enumerate(zip(segs, cuts)):
        flag = flags[idx] if flags is not None else False
        if not pts:
            out.append((a, b))
            out_flags.append(flag)
            continue
        along = sorted(set([0.0, 1.0] + [_param_along(a, b, p) for p in pts]))
        for t0, t1 in zip(along, along[1:]):
            if t1 - t0 < 1e-9:
                continue
            p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            out.append((p0, p1))
            out_flags.append(flag)
    if flags is None:
        return out
    return out, out_flags


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
    for loop in loops:
        ring, z = loop[0], loop[1]
        arcs = loop[2] if len(loop) > 2 else []
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
        out.append({"ring": ring, "z": z, "mark": mark, "thickness_mm": thk,
                    "arcs": arcs})
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

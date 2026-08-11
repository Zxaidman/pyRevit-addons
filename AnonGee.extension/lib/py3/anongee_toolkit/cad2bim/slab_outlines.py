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
from . import slab_graph
from .classify.layers import CATEGORY_SLAB_EDGE, CATEGORY_BEAM, CATEGORY_COLUMN
from .geom import shapes
from .slab_graph import (apply_tolerances, _tessellate_arc, _ring_arcs,
                         _append_footprint_rings, _faces_from_edge_graph,
                         _walk_faces, _heal_endpoints, _split_at_crossings_w,
                         _inset_ring, _in_rect_footprint, _dedup_ring, _dist,
                         _signed_area, _centroid, _point_in_ring,
                         _COLUMN_RECT_PAD_MM)          # noqa: F401

_MM = config.MM_PER_FT












# ---------------------------------------------------------------- outline source 1
def slab_loops_from_edges(records):
    """Slab boundary rings straight from the slab-edge layer, [(ring, z, arcs), ...].

    A CLOSED polyline is a ring as drawn. Open polylines, loose lines AND boundary
    ARCS (tessellated into chords, with the true start/mid/end triple carried in
    `arcs` so the builder can rebuild a genuine curved edge) are chained end-to-end
    (within _CHAIN_TOL_MM) and kept only if they close into a ring.
    """
    tol_ft = config.mm_to_ft(slab_graph._CHAIN_TOL_MM)
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
    healed = _heal_endpoints(plain, config.mm_to_ft(slab_graph._HEAL_MM))
    healed_hw = [(a, b, segs[i][2]) for i, (a, b) in enumerate(healed)]
    pieces = _split_at_crossings_w(healed_hw)
    snap_ft = config.mm_to_ft(slab_graph._SNAP_MM)

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
    min_area_ft2 = slab_graph._MIN_FACE_AREA_M2 * (1000.0 / _MM) ** 2
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


# The labelling half moved to slab_labels.py -- imported at the END because that
# module reads outlines back from this one, and re-exported so every caller keeps
# the import it has always used.
from .slab_labels import (parse_slab_label, apply_slab_labels,          # noqa: E402,F401
                          loops_for_unclaimed_notes)

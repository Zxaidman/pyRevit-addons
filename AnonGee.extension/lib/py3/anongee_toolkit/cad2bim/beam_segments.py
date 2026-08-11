# -*- coding: utf-8 -*-
"""Turning beam-layer linework into placeable CENTRELINES.

A beam is drawn as its two long edges, so the member itself is the space
between them: this module pairs those edges, reads a centreline and a width off
each pair, and sizes the result from the plan's labels ("B1 300x600") or the
schedule. Depth cannot be measured from a 2D plan at all -- only the label
knows it -- which is why the labelling passes live here too.

The awkward cases each have their own pass, and each earns its place from a
real drawing:

    quad / rect        one closed outline that IS the beam
    explode-to-pairs   an outline too wide, tapered or skewed to be one member,
                       broken back into edges and re-paired
    curved             concentric arc pairs -> an arc centreline
    edge pairs         a beam edge paired with a slab edge, where only one side
                       was drawn on the beam layer
    continuation       one beam crossing another, drawn as two collinear pieces

Everything here is Revit-free and works in internal feet; sizes come back in
millimetres because that is what the labels, the schedule and the user speak.
"""

import math
from collections import defaultdict, Counter

from . import config
from .geom import shapes
from .classify import marks
from .classify.layers import CATEGORY_BEAM, CATEGORY_SLAB_EDGE
from .limits import DEFAULT_LIMITS, _standard_dims_mm
from .column_geom import _label_size

_MM = config.MM_PER_FT

_ARC_EDGE_CENTER_TOL_MM = 250.0   # arc fragments share an edge if their centres agree this far
_ARC_EDGE_RADIUS_TOL_MM = 60.0    # ...and their radii agree this far (< any real beam width)
_EDGE_DUP_TOL_MM = 250.0          # an edge-pair beam this close to a placed beam is a re-trace
_SKEW_OUTLINE_MAX_DEG = 2.0   # bbox a non-rectilinear ring only when this close to the axes


def _ring_longest_edge_skew_deg(ring):
    """Angle (deg) of the ring's LONGEST edge off the nearest axis.

    The longest edge of a beam outline runs along the beam, so its skew tells whether
    an axis-aligned bounding box can stand in for the outline (near 0) or would flatten
    a sloped beam onto the wrong axis (several degrees).
    """
    best_len2, best_deg = -1.0, 0.0
    n = len(ring)
    for i in range(n):
        ax, ay = ring[i]
        bx, by = ring[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        len2 = dx * dx + dy * dy
        if len2 > best_len2:
            deg = abs(math.degrees(math.atan2(dy, dx))) % 90.0
            best_len2, best_deg = len2, min(deg, 90.0 - deg)
    return best_deg


def _ring_keeps_all_points(xy, ring, tol_ft):
    """True if every original polyline vertex sits on the simplified ring's boundary.

    simplify_ring closes the vertex list implicitly, so an OPEN polyline gains a fabricated
    closing edge -- and any real leg collinear with it is removed as "redundant". A removed
    vertex that does NOT lie on the resulting ring means actual drawn geometry was lost, so
    the ring cannot be trusted as this record's outline.
    """
    n = len(ring)
    for px, py in xy:
        on_ring = False
        for i in range(n):
            if _point_to_segment_dist(px, py, ring[i], ring[(i + 1) % n]) <= tol_ft:
                on_ring = True
                break
        if not on_ring:
            return False
    return True


def build_beam_segments(records, circles=None, limits=None, standards=None,
                        texts=None, tolerances=None, schedule=None):
    """Derive straight beam centerlines from beam-category geometry.

    When `texts` (sized DXF marks, internal feet) are given, each segment is
    refined from the nearest mark (e.g. "B1 230x500"): width = the smaller value,
    DEPTH = the larger -- the depth a 2D outline cannot provide on its own.
    `tolerances` (config.DEFAULTS overrides) tunes the parallel-pair band, the
    arc junction/concentric tolerances, snap and mark radius.

    Three sources: (1) closed thin outlines -> one centerline along the long axis;
    multi-segment rectilinear outlines decompose into straight beams. (2) PAIRS of
    parallel lines ~one width apart -> a beam on their midline (this is how the
    perimeter / grid-line beams are drawn). (3) arcs: those centred on a detected
    round column are junction fillets and ignored; genuine curved beams (concentric
    arc pairs) are detected and surfaced (placement to follow).
    """
    tol = config.merged(tolerances)
    junction_tol_ft = config.mm_to_ft(tol["junction_tol_mm"])
    concentric_tol_ft = config.mm_to_ft(tol["concentric_tol_mm"])
    pair_min_ft = config.mm_to_ft(tol["pair_min_width_mm"])
    pair_max_ft = config.mm_to_ft(tol["pair_max_width_mm"])
    beam_width_max_mm = (limits or DEFAULT_LIMITS)["beam_width_max_mm"]
    quad_width_max_ft = config.mm_to_ft(beam_width_max_mm + tol["snap_tol_mm"])
    circles = circles or []
    status = defaultdict(int)
    segments = []
    review = []
    bare_lines = []
    floor_lines = []     # slab/floor edges -- the clipped partner edge of a perimeter beam
    arc_fits = []
    for record in records:
        if record.category == CATEGORY_SLAB_EDGE:
            # A slab/floor outline often arrives as ONE polyline (the Revit link reader
            # returns connected edges as a single polyline, not loose lines), so explode it
            # into its straight segments -- each becomes a candidate partner edge for a beam.
            if record.kind in ("line", "polyline"):
                pts = record.points
                for i in range(len(pts) - 1):
                    floor_lines.append(((pts[i][0], pts[i][1]),
                                        (pts[i + 1][0], pts[i + 1][1]), pts[i][2]))
            continue
        if record.category != CATEGORY_BEAM:
            continue
        if record.kind == "line":
            pts = record.points
            if len(pts) >= 2:
                bare_lines.append(((pts[0][0], pts[0][1]),
                                   (pts[-1][0], pts[-1][1]), pts[0][2]))
            continue
        if record.kind == "arc":
            pts = record.points
            if len(pts) >= 3:
                mid = pts[len(pts) // 2]
                fit = shapes.circle_from_three_points(
                    (pts[0][0], pts[0][1]), (mid[0], mid[1]),
                    (pts[-1][0], pts[-1][1]))
                if fit:
                    cx, cy, r = fit
                    a0 = math.degrees(math.atan2(pts[0][1] - cy, pts[0][0] - cx)) % 360.0
                    a1 = math.degrees(math.atan2(pts[-1][1] - cy, pts[-1][0] - cx)) % 360.0
                    arc_fits.append((cx, cy, r, a0, a1, pts[0][2]))
            continue
        xy, z = shapes.to_xy(record.points)
        ring = shapes.simplify_ring(xy)
        if ring and len(ring) >= 4 and not _ring_keeps_all_points(xy, ring, junction_tol_ft):
            # simplify_ring treats every polyline as CLOSED (it wraps the vertex list), so an
            # OPEN snake -- e.g. a horizontal beam edge that turns up into a vertical beam's
            # edge -- gets a fabricated closing edge, and any leg collinear with that edge is
            # silently deleted (Test10 lost the grid-6 vertical beam this way: its right edge
            # was the polyline's last leg). If an ORIGINAL vertex lies off the simplified ring,
            # the ring dropped real geometry: explode the polyline into the pair pool instead.
            pts = record.points
            for i in range(len(pts) - 1):
                bare_lines.append(((pts[i][0], pts[i][1]),
                                   (pts[i + 1][0], pts[i + 1][1]), pts[i][2]))
            status["open_explode"] += 1
            continue
        if not ring or len(ring) < 4:
            # An OPEN beam outline (the link reader gives a beam's surviving edge as a short
            # polyline, not a closed quad) is not degenerate -- explode its segments into the
            # line pool so they pair like any other beam edge, instead of being dropped.
            pts = record.points
            for i in range(len(pts) - 1):
                bare_lines.append(((pts[i][0], pts[i][1]),
                                   (pts[i + 1][0], pts[i + 1][1]), pts[i][2]))
            status["degenerate"] += 1
            continue
        # An outline WIDER than any beam is never one member's outline: it is either an
        # open U-polyline chaining the facing edges of TWO grid beams that simplify_ring
        # closed across the void (Test15's phantom midline beams between J/K, S/T), or a
        # whole BAY traced as one nearly-closed snake whose slightly-skew closing edge
        # defeats is_rectilinear (Test15's undrawn perimeter rows: the bay bbox segment
        # was emitted 2950 wide, silently dropped by the width filter, and the real beam
        # edges inside it were CONSUMED). In every such case the polyline's legs are real
        # beam edges -- explode them into the pair pool so the actual beams re-pair.
        def _explode_too_wide(status_key):
            pts = record.points
            for i in range(len(pts) - 1):
                bare_lines.append(((pts[i][0], pts[i][1]),
                                   (pts[i + 1][0], pts[i + 1][1]), pts[i][2]))
            status[status_key] += 1

        if len(ring) == 4:
            result = shapes.beam_centerline_from_quad(ring)
            if not result:
                # a TAPERING quad is two members' edges closed into one ring by
                # the link reader; its legs are real beam edges, so let them
                # re-pair rather than reading a skewed beam off the trapezoid
                _explode_too_wide("tapered_quad_explode")
                continue
            start, end, width = result
            if width > quad_width_max_ft:
                _explode_too_wide("quad_too_wide_explode")
                continue
            segments.append(_beam_segment(start, end, width, z, record.layer, "rect"))
            status["rect"] += 1
        elif shapes.is_rectilinear(ring):
            pieces = [shapes.beam_centerline_from_rect(rect)
                      for rect in shapes.decompose_to_rectangles(ring)]
            if any(width > quad_width_max_ft for _s, _e, width in pieces):
                _explode_too_wide("composite_too_wide_explode")
                continue
            for start, end, width in pieces:
                segments.append(_beam_segment(start, end, width, z, record.layer, "segment"))
            status["composite"] += 1
        else:
            bbox = shapes.bounding_rectangle(ring, z)
            start, end, width = shapes.beam_centerline_from_rect(bbox)
            if width > quad_width_max_ft:
                _explode_too_wide("outline_too_wide_explode")
                continue
            if _ring_longest_edge_skew_deg(ring) > _SKEW_OUTLINE_MAX_DEG:
                # The bbox fallback assumes a near-axis-aligned outline. A SLOPED beam
                # (Test11's 4-degree grid-I bays between rotated columns) arrives as a
                # non-rectilinear snake, and its axis-aligned bbox flattens the beam
                # onto the wrong axis (an angled beam placed horizontal). Explode it:
                # the two angled edges are parallel one width apart and pair correctly.
                _explode_too_wide("skew_outline_explode")
                continue
            segments.append(_beam_segment(start, end, width, z, record.layer, "non_rectilinear"))
            status["non_rectilinear"] += 1

    # (2) Beams drawn as two parallel edge lines.
    line_segments, leftover = shapes.pair_parallel_lines(
        bare_lines, min_width_ft=pair_min_ft, max_width_ft=pair_max_ft,
        min_overlap_ft=config.mm_to_ft(tol["pair_min_overlap_mm"]),
        sin_tol=math.sin(math.radians(tol["parallel_angle_deg"])))
    for seg in line_segments:
        segments.append(_beam_segment(seg["start"], seg["end"], seg["width_ft"],
                                      seg["start"][2], "S-BEAM", "line_pair"))
        status["line_pair"] += 1
    if leftover:
        status["bare_line_unpaired"] += len(leftover)
        review.append("{0} bare lines without a parallel partner".format(len(leftover)))

    # (3) Arcs: drop round-column junction fillets; build concentric pairs into CURVED
    # beams. A curved beam is drawn as two concentric edges, each a chain of many short
    # arc fragments, so the fragments are first clustered into edges (by shared centre +
    # radius), then an inner/outer edge pair (radius gap = the beam width) becomes one
    # curved member spanning the chain's swept angle.
    def _is_junction(fit):
        cx, cy = fit[0], fit[1]
        for circle in circles:
            ccx, ccy, _cz = circle["center"]
            if ((cx - ccx) ** 2 + (cy - ccy) ** 2) ** 0.5 < junction_tol_ft:
                return True
        return False

    free_arcs = [f for f in arc_fits if not _is_junction(f)]
    status["arc_junction"] += (len(arc_fits) - len(free_arcs))
    edges = _group_arc_edges(free_arcs,
                             config.mm_to_ft(_ARC_EDGE_CENTER_TOL_MM),
                             config.mm_to_ft(_ARC_EDGE_RADIUS_TOL_MM))
    curved_segments, lone = _curved_beams_from_edges(
        edges, pair_min_ft, pair_max_ft, concentric_tol_ft)
    if curved_segments:
        status["curved_pair"] += len(curved_segments)
    if lone:
        status["arc_lone"] += lone

    # A beam's DEPTH (and, for a mark-only label, its width) comes from the label: an inline
    # "B1 300x600" or the schedule[mark] -- exactly as columns are sized. Resolve every beam
    # label to a size once, then size segments / curved beams / edge pairs from it.
    radius_ft = config.mm_to_ft(tol["mark_radius_mm"])
    sized_labels = _sized_beam_labels(texts, schedule)
    refined = _apply_beam_marks(segments, sized_labels, radius_ft,
                                width_max_mm=beam_width_max_mm + tol["snap_tol_mm"])
    refined += _apply_curved_marks(curved_segments, sized_labels, radius_ft)

    # (4) Perimeter / floor-clipped beams: a beam whose inner edge was clipped against the
    # slab outline survives as a LONE beam line; pair the leftover beam lines and the slab
    # edges, then keep a candidate only where a beam LABEL of matching width sits across it.
    placed = set(s.get("mark") for s in segments if s.get("mark"))
    placed |= set(s.get("mark") for s in curved_segments if s.get("mark"))
    # The edge pass is label-confirmed (each pair must match a label's width + sit under it),
    # so it can pair WIDER than the geometric line_pair pass without inviting false beams --
    # admit up to the full beam-width limit so a wide member (e.g. a 900-wide B22) is found.
    edge_max_ft = config.mm_to_ft(max(tol["pair_max_width_mm"],
                                      (limits or DEFAULT_LIMITS)["beam_width_max_mm"]))
    edge_beams = _edge_pair_beams(
        leftover, floor_lines, sized_labels, placed, segments,
        pair_min_ft, edge_max_ft, config.mm_to_ft(tol["pair_min_overlap_mm"]),
        math.sin(math.radians(tol["parallel_angle_deg"])),
        config.mm_to_ft(tol["snap_tol_mm"]), radius_ft,
        config.mm_to_ft(_EDGE_DUP_TOL_MM))
    if edge_beams:
        segments.extend(edge_beams)
        status["edge_pair"] += len(edge_beams)
        refined += len(edge_beams)
    if refined:
        status["text_sized"] = refined

    # (5) Continuations: the far piece of a beam interrupted by a crossing member (its one
    # label sits over the near piece), e.g. B22 continuing past B4/B5 to the C12 core.
    continuation = _continuation_beams(
        leftover, floor_lines, segments, pair_min_ft, edge_max_ft,
        config.mm_to_ft(tol["pair_min_overlap_mm"]),
        math.sin(math.radians(tol["parallel_angle_deg"])),
        config.mm_to_ft(tol["snap_tol_mm"]), config.mm_to_ft(_EDGE_DUP_TOL_MM))
    if continuation:
        status["continuation"] += continuation   # beams EXTENDED in place, none added

    segments, dropped = _filter_beam_segments(segments, limits or DEFAULT_LIMITS,
                                              standards or {}, tol["snap_tol_mm"])
    curved_segments, cdropped = _filter_beam_segments(
        curved_segments, limits or DEFAULT_LIMITS, standards or {}, tol["snap_tol_mm"])
    dropped += cdropped
    if dropped:
        status["width_out_of_range"] = dropped
    if curved_segments:
        review.append("{0} curved beam(s) detected".format(len(curved_segments)))

    return {"segments": segments, "curved_segments": curved_segments,
            "status_counts": dict(status), "review": review}


def _group_arc_edges(arcs, center_tol_ft, radius_tol_ft):
    """Cluster concentric, equal-radius arc fragments into edges.

    `arcs` are (cx, cy, r, a0, a1, z) circle fits with the fragment's two endpoint
    angles. Returns edge dicts {cx, cy, r, z, angles:[...], n} carrying the running-mean
    centre/radius and every fragment's endpoint angles (for the swept-angle span).
    """
    edges = []
    for cx, cy, r, a0, a1, z in arcs:
        hit = None
        for e in edges:
            ecx, ecy, er = e["cx"] / e["n"], e["cy"] / e["n"], e["r"] / e["n"]
            if (((cx - ecx) ** 2 + (cy - ecy) ** 2) ** 0.5 <= center_tol_ft
                    and abs(r - er) <= radius_tol_ft):
                hit = e
                break
        if hit is None:
            edges.append({"cx": cx, "cy": cy, "r": r, "z": z,
                          "angles": [a0, a1], "n": 1})
        else:
            hit["cx"] += cx
            hit["cy"] += cy
            hit["r"] += r
            hit["n"] += 1
            hit["angles"] += [a0, a1]
    return edges


def _curved_beams_from_edges(edges, pair_min_ft, pair_max_ft, center_tol_ft):
    """Pair concentric inner/outer edges into curved beam segments.

    Two edges sharing a centre whose radii differ by a real beam width (pair band) form
    one curved member: centreline radius = mean of the two, width = the gap, swept angle =
    the chain's populated arc. Returns (curved_segments, lone_fragment_count). Largest
    edges (most fragments) pair first, so a long beam edge is not stolen by a stray arc.
    """
    order = sorted(range(len(edges)), key=lambda i: -edges[i]["n"])
    paired = [False] * len(edges)
    segs = []
    for a_pos in range(len(order)):
        i = order[a_pos]
        if paired[i]:
            continue
        ei = edges[i]
        cix, ciy, rin = ei["cx"] / ei["n"], ei["cy"] / ei["n"], ei["r"] / ei["n"]
        for b_pos in range(a_pos + 1, len(order)):
            j = order[b_pos]
            if paired[j]:
                continue
            ej = edges[j]
            cjx, cjy, rjn = ej["cx"] / ej["n"], ej["cy"] / ej["n"], ej["r"] / ej["n"]
            if ((cix - cjx) ** 2 + (ciy - cjy) ** 2) ** 0.5 > center_tol_ft:
                continue
            gap = abs(rin - rjn)
            if not (pair_min_ft < gap < pair_max_ft):
                continue
            cx, cy = (cix + cjx) / 2.0, (ciy + cjy) / 2.0
            r_center = (rin + rjn) / 2.0
            start_deg, end_deg = _arc_span(ei["angles"] + ej["angles"])
            segs.append(_curved_segment(cx, cy, ei["z"], r_center, gap,
                                        start_deg, end_deg))
            paired[i] = paired[j] = True
            break
    lone = sum(edges[k]["n"] for k in range(len(edges)) if not paired[k])
    return segs, lone


def _arc_span(angles):
    """(start_deg, end_deg) of the populated arc, sweeping CCW across the LARGEST gap.

    The chain's fragment endpoint angles leave one big empty wedge (the un-drawn side);
    the beam spans everything else. end_deg may exceed 360 so end > start (a CCW sweep).
    """
    pts = sorted(a % 360.0 for a in angles)
    n = len(pts)
    gi, gmax = 0, -1.0
    for k in range(n):
        gap = (pts[(k + 1) % n] - pts[k]) % 360.0
        if gap > gmax:
            gmax, gi = gap, k
    start = pts[(gi + 1) % n]
    end = pts[gi]
    if end <= start:
        end += 360.0
    return start, end


def _curved_segment(cx, cy, z, r_center_ft, width_ft, start_deg, end_deg):
    """A placeable curved beam: centre, centreline radius, swept angle, width (mm/ft)."""
    length_ft = math.radians(end_deg - start_deg) * r_center_ft
    return {"kind": "curved",
            "center": [cx, cy, z],
            "radius_mm": r_center_ft * _MM, "radius_ft": r_center_ft,
            "start_deg": start_deg, "end_deg": end_deg,
            "width_mm": width_ft * _MM, "length_mm": length_ft * _MM,
            "layer": "S-BEAM", "status": "curved"}


def _apply_curved_marks(curved, sized_labels, radius_ft):
    """Size each curved beam from the nearest beam label to its mid-arc point.

    Depth (the larger label value) and mark are taken from the label; the WIDTH stays the
    geometric gap between the two edges (the 2D plan does carry a curved beam's width).
    """
    if not sized_labels:
        return 0
    count = 0
    for seg in curved:
        cx, cy, _z = seg["center"]
        mid = math.radians((seg["start_deg"] + seg["end_deg"]) / 2.0)
        r = seg["radius_ft"]
        hit = _nearest_sized_label(cx + r * math.cos(mid), cy + r * math.sin(mid),
                                   sized_labels, radius_ft)
        if hit is None:
            continue
        text, _small, big = hit
        seg["depth_mm"] = big
        seg["mark"] = text.mark
        count += 1
    return count


def _edge_pair_beams(beam_leftover, floor_lines, sized_labels, placed_marks, existing,
                     pair_min_ft, pair_max_ft, min_overlap_ft, sin_tol,
                     width_tol_ft, radius_ft, dup_tol_ft):
    """Recover perimeter/floor-clipped beams: a lone beam line + the parallel slab edge.

    Revit clips a perimeter beam's inner edge against the floor outline, so only one beam
    edge survives on the beam layer and the other is on the slab/floor layer. Pair the
    leftover beam lines AND the slab edges into width-band candidates, then KEEP one only
    where a beam label (still unplaced) of matching width sits across it -- a slab edge on
    its own (a real floor boundary) never becomes a beam. A candidate that lands on top of
    an already-placed beam is dropped (where the floor outline simply re-traces a beam whose
    two edges were both on the beam layer, that beam is already placed). Each candidate and
    each label is used at most once. Returns the new (sized + marked) beam segments.
    """
    candidates = [(t, small, big) for (t, small, big) in sized_labels
                  if t.mark not in placed_marks]
    if not candidates or len(beam_leftover) + len(floor_lines) < 2:
        return []
    pairs, _lo = shapes.pair_parallel_lines(
        list(beam_leftover) + list(floor_lines), min_width_ft=pair_min_ft,
        max_width_ft=pair_max_ft, min_overlap_ft=min_overlap_ft, sin_tol=sin_tol)
    placed_lines = [(s["start"], s["end"]) for s in existing]
    # OWNERSHIP: each candidate pair is owned by its NEAREST matching-width label (within
    # radius), so two same-width labels (e.g. B4 and B5, both 300x600) can't have the first
    # one claim the other's nearer beam. Then each label takes only its single nearest owned
    # candidate -- one beam per label, assigned to whichever label is genuinely closest.
    owners = {}                              # label index -> [(dist, pair index), ...]
    for k, seg in enumerate(pairs):
        sx = (seg["start"][0] + seg["end"][0]) / 2.0
        sy = (seg["start"][1] + seg["end"][1]) / 2.0
        best_i, best_d = None, None
        for i, (text, small, _big) in enumerate(candidates):
            if abs(seg["width_ft"] - small / _MM) > width_tol_ft:
                continue
            if not _label_matches_orientation(text, seg):
                continue                     # a label always runs ALONG its beam
            d = _point_to_segment_dist(text.point_internal[0], text.point_internal[1],
                                       seg["start"], seg["end"])
            if d > radius_ft:
                continue
            if best_d is None or d < best_d:
                best_d, best_i = d, i
        if best_i is not None:
            owners.setdefault(best_i, []).append((best_d, k))
    out = []
    for i, owned in owners.items():
        text, small, big = candidates[i]
        for _d, k in sorted(owned):
            seg = pairs[k]
            if _coincides_with_a_beam(seg["start"], seg["end"], placed_lines, dup_tol_ft):
                continue                     # floor outline re-traced an existing beam
            beam = _beam_segment(seg["start"], seg["end"], small / _MM,
                                 seg["start"][2], "S-BEAM", "edge_pair")
            beam["depth_mm"] = big
            beam["mark"] = text.mark
            placed_lines.append((seg["start"], seg["end"]))
            out.append(beam)
            break                            # one beam per label (its nearest)
    return out


_CONTINUATION_GAP_MAX_MM = 1200.0   # widest crossing member a beam may continue past


def _continuation_beams(beam_leftover, floor_lines, existing, pair_min_ft, pair_max_ft,
                        min_overlap_ft, sin_tol, width_tol_ft, dup_tol_ft):
    """Recover the far piece of a beam interrupted by a crossing member, label-free.

    A wide beam drawn across a junction is broken there (B22, 900 wide, stops at the
    B4/B5 crossing), and the far piece often has no label of its own -- the one label
    sits over the near piece -- so neither the geometric pair pass (width-capped) nor
    the label-confirmed edge pass will place it. Pair the leftover beam lines AND the
    slab edges (the far piece's inner edge may survive only as the floor outline, as
    Test19's B22 does) up to the full beam width, and keep a candidate only when
    (a) at least one of its edges is on the BEAM layer -- slab edges alone never make
    a beam -- and (b) it collinearly CONTINUES an already-detected beam: same width,
    same centreline, separated along the axis by no more than a crossing member's
    width. The continued beam is the evidence.

    The matched beam is EXTENDED in place over the candidate's span (returns the
    number of extensions): the drawing merely breaks the member's linework at the
    crossing, but it is ONE beam -- placing two pieces left a phantom gap in the
    model that read like a column that isn't there. Mark, size and depth stay.
    """
    if not existing or len(beam_leftover) < 1 or len(beam_leftover) + len(floor_lines) < 2:
        return 0
    pairs, _lo = shapes.pair_parallel_lines(
        list(beam_leftover) + list(floor_lines), min_width_ft=pair_min_ft,
        max_width_ft=pair_max_ft, min_overlap_ft=min_overlap_ft, sin_tol=sin_tol)
    placed_lines = [(s["start"], s["end"]) for s in existing]
    gap_max_ft = config.mm_to_ft(_CONTINUATION_GAP_MAX_MM)
    extended = 0
    for seg in pairs:
        if _coincides_with_a_beam(seg["start"], seg["end"], placed_lines, dup_tol_ft):
            continue                         # re-pairing of an already-placed beam
        if not _pair_has_beam_edge(seg, beam_leftover, sin_tol, width_tol_ft):
            continue                         # both edges are floor outline: not a beam
        hit = None
        for ex in existing:
            if abs(seg["width_ft"] - ex["width_mm"] / _MM) > width_tol_ft:
                continue
            if _collinear_continuation(seg, ex, sin_tol, width_tol_ft, gap_max_ft):
                hit = ex
                break
        if hit is None:
            continue
        _extend_segment_over(hit, seg)
        placed_lines.append((seg["start"], seg["end"]))
        extended += 1
    return extended


def _extend_segment_over(existing, seg):
    """Stretch `existing` along its own axis so its span also covers `seg`'s."""
    p, q = existing["start"], existing["end"]
    vx, vy = q[0] - p[0], q[1] - p[1]
    length = (vx * vx + vy * vy) ** 0.5
    if length == 0:
        return
    ux, uy = vx / length, vy / length
    ts = [0.0, length]
    for cx, cy in ((seg["start"][0], seg["start"][1]), (seg["end"][0], seg["end"][1])):
        ts.append((cx - p[0]) * ux + (cy - p[1]) * uy)
    t_lo, t_hi = min(ts), max(ts)
    z = p[2]
    existing["start"] = [p[0] + ux * t_lo, p[1] + uy * t_lo, z]
    existing["end"] = [p[0] + ux * t_hi, p[1] + uy * t_hi, z]
    existing["length_mm"] = (t_hi - t_lo) * _MM


def _pair_has_beam_edge(seg, beam_lines, sin_tol, tol_ft):
    """True if one of the pair's two edges lies along a BEAM-layer line.

    An edge sits half the pair's width from the centreline: accept a beam line that is
    parallel to the candidate and whose midpoint sits within width/2 + tol of the
    candidate centreline (and not beyond half width -- i.e. actually along an edge).
    """
    half_w = seg["width_ft"] / 2.0
    ax, ay = seg["start"][0], seg["start"][1]
    bx, by = seg["end"][0], seg["end"][1]
    vx, vy = bx - ax, by - ay
    lv = (vx * vx + vy * vy) ** 0.5
    if lv == 0:
        return False
    for (ls, le, _z) in beam_lines:
        dx, dy = le[0] - ls[0], le[1] - ls[1]
        ld = (dx * dx + dy * dy) ** 0.5
        if ld == 0 or abs(vx * dy - vy * dx) / (lv * ld) > sin_tol:
            continue
        mx, my = (ls[0] + le[0]) / 2.0, (ls[1] + le[1]) / 2.0
        d = _point_to_segment_dist(mx, my, (ax, ay), (bx, by))
        if abs(d - half_w) <= tol_ft:
            return True
    return False


def _collinear_continuation(seg, existing, sin_tol, lat_tol_ft, gap_max_ft):
    """True when candidate `seg` continues `existing` along the SAME centreline.

    Parallel within sin_tol, BOTH candidate endpoints within lat_tol of the existing
    centreline extended (an offset parallel neighbour never qualifies), and the two
    axial spans disjoint by 0..gap_max (the crossing member's width). Touching or a
    hair of overlap is tolerated; a large overlap is a duplicate, not a continuation.
    """
    px, py = existing["start"][0], existing["start"][1]
    qx, qy = existing["end"][0], existing["end"][1]
    vx, vy = qx - px, qy - py
    length = (vx * vx + vy * vy) ** 0.5
    if length == 0:
        return False
    ux, uy = vx / length, vy / length
    ax, ay = seg["start"][0], seg["start"][1]
    bx, by = seg["end"][0], seg["end"][1]
    wx, wy = bx - ax, by - ay
    lw = (wx * wx + wy * wy) ** 0.5
    if lw == 0 or abs(wx * uy - wy * ux) / lw > sin_tol:
        return False
    for cx, cy in ((ax, ay), (bx, by)):
        if abs((cx - px) * uy - (cy - py) * ux) > lat_tol_ft:
            return False
    t0 = (ax - px) * ux + (ay - py) * uy
    t1 = (bx - px) * ux + (by - py) * uy
    lo, hi = min(t0, t1), max(t0, t1)
    gap = max(lo - length, 0.0 - hi)         # positive when spans are disjoint
    return -lat_tol_ft <= gap <= gap_max_ft


def _coincides_with_a_beam(start, end, placed_lines, perp_tol_ft):
    """True when centreline start->end runs along an already-placed beam centreline.

    Parallel (within ~5 deg) and the candidate's mid-point lies within perp_tol of the
    placed centreline (clamped to its span) -- i.e. they are the same beam, drawn once on
    the beam layer and again as the coincident floor edge.
    """
    mx, my = (start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0
    adx, ady = end[0] - start[0], end[1] - start[1]
    la = (adx * adx + ady * ady) ** 0.5
    if la == 0:
        return False
    for ps, pe in placed_lines:
        bdx, bdy = pe[0] - ps[0], pe[1] - ps[1]
        lb = (bdx * bdx + bdy * bdy) ** 0.5
        if lb == 0:
            continue
        if abs(adx * bdy - ady * bdx) / (la * lb) > 0.087:   # not parallel (~5 deg)
            continue
        if _point_to_segment_dist(mx, my, ps, pe) <= perp_tol_ft:
            return True
    return False


def _point_to_segment_dist(px, py, start, end):
    """Planar distance from (px, py) to segment start->end (clamped to the segment)."""
    ax, ay = start[0], start[1]
    bx, by = end[0], end[1]
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / length2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def _sized_beam_labels(texts, schedule):
    """[(text, small_mm, big_mm)] for beam labels with a resolvable size.

    Size comes from the inline label ("B1 300x600") OR, for a mark-only label, from
    schedule[mark] (a tabular beam schedule) -- the same precedence columns use. A label
    with no size anywhere is dropped (a 2D outline cannot supply a beam's depth).
    """
    out = []
    for text in (texts or []):
        if not text.point_internal:
            continue
        size = _label_size(text, schedule or {})
        if size is not None:
            out.append((text, size[0], size[1]))
    return out


def _nearest_sized_label(cx, cy, sized_labels, radius_ft):
    """Nearest (text, small, big) within radius_ft of (cx, cy), or None."""
    best, best_d2 = None, radius_ft * radius_ft
    for text, small, big in sized_labels:
        px, py = text.point_internal[0], text.point_internal[1]
        d2 = (px - cx) ** 2 + (py - cy) ** 2
        if d2 <= best_d2:
            best, best_d2 = (text, small, big), d2
    return best


def _apply_beam_marks(segments, sized_labels, radius_ft, width_max_mm=None):
    """Size each beam segment from its beam label (inline or schedule), in place.

    width = smaller value, depth = larger, plus the mark. Returns the count sized.

    Assignment is label-OWNS-segment first (the same cure the edge-pair pass uses for
    the B4/B5 swap): each label claims the one segment whose CENTERLINE it sits nearest
    (point-to-segment distance), and a claimed segment is sized by its nearest owning
    label. Segment-picks-nearest-label by MIDPOINT let a stacked neighbour's label win
    -- B23's label (drawn between B20 and B23) was nearer B20's midpoint than B20's own
    off-midspan label, so B20 took B23's 300-wide size and, after the duplicate-mark
    sweep, lost its name. Unclaimed segments still fall back to the nearest label by
    midpoint, so a bay whose label was claimed elsewhere keeps its size/depth.

    A segment whose DRAWN width already exceeds `width_max_mm` is never sized: it is
    not one beam's outline (e.g. a ring closed across the void between two grid beams),
    and letting a label rewrite its width would launder it past the width filter -- and
    steal that label's mark from the real member.
    """
    if not sized_labels:
        return 0
    owners = {}
    for text, small, big in sized_labels:
        px, py = text.point_internal[0], text.point_internal[1]
        best_i, best_d = None, radius_ft
        for i, segment in enumerate(segments):
            if width_max_mm is not None and segment["width_mm"] > width_max_mm:
                continue
            if not _label_matches_orientation(text, segment):
                continue
            s, e = segment["start"], segment["end"]
            d = _point_to_segment_dist(px, py, (s[0], s[1]), (e[0], e[1]))
            if d <= best_d:
                best_i, best_d = i, d
        if best_i is not None:
            owners.setdefault(best_i, []).append((best_d, text, small, big))
    count = 0
    for i, segment in enumerate(segments):
        if width_max_mm is not None and segment["width_mm"] > width_max_mm:
            continue
        if i in owners:
            _d, text, small, big = min(owners[i], key=lambda o: o[0])
        else:
            hit = _nearest_fallback_label(segment, sized_labels, radius_ft)
            if hit is None:
                continue
            text, small, big = hit
        segment["width_mm"] = small
        segment["depth_mm"] = big
        segment["mark"] = text.mark
        count += 1
    _dedupe_marks(segments, sized_labels)
    return count


def _nearest_fallback_label(segment, sized_labels, radius_ft):
    """Midpoint-nearest label for a segment no label claimed, orientation-gated."""
    cx = (segment["start"][0] + segment["end"][0]) / 2.0
    cy = (segment["start"][1] + segment["end"][1]) / 2.0
    best, best_d2 = None, radius_ft * radius_ft
    for text, small, big in sized_labels:
        if not _label_matches_orientation(text, segment):
            continue
        px, py = text.point_internal[0], text.point_internal[1]
        d2 = (px - cx) ** 2 + (py - cy) ** 2
        if d2 <= best_d2:
            best, best_d2 = (text, small, big), d2
    return best


_LABEL_ANGLE_TOL_DEG = 20.0


def _label_matches_orientation(text, segment):
    """True when the label's text runs ALONG the segment (drafting convention).

    A beam's label is always written parallel to its beam, so a rotated (vertical)
    label can never belong to a horizontal beam. This matters because a rotated
    label's INSERTION point sits at one end of its text run -- often just past the
    beam's end, closer to the crossing row's centreline than to its own beam --
    which let vertical labels claim horizontal beams (Test15: wrong marks across
    whole rows). Labels without a rotation (non-DXF sources) match everything.
    """
    rot = getattr(text, "rotation_deg", None)
    if rot is None:
        return True
    sx, sy = segment["start"][0], segment["start"][1]
    ex, ey = segment["end"][0], segment["end"][1]
    seg_deg = math.degrees(math.atan2(ey - sy, ex - sx))
    diff = abs((seg_deg - rot) % 180.0)
    diff = min(diff, 180.0 - diff)
    return diff <= _LABEL_ANGLE_TOL_DEG


def _dedupe_marks(segments, sized_labels):
    """A mark names ONE beam: when two segments both took the same label (it sits between
    them), keep the mark on the segment nearest that label and clear it on the others.

    The de-named segment keeps its size (a real member, just unnamed) -- placing two beams
    with the same Mark would otherwise trip Revit's duplicate-mark warning.
    """
    label_pt = {}
    for text, _small, _big in sized_labels:
        if text.mark and text.mark not in label_pt:
            label_pt[text.mark] = text.point_internal
    by_mark = {}
    for seg in segments:
        m = seg.get("mark")
        if m:
            by_mark.setdefault(m, []).append(seg)
    for mark, group in by_mark.items():
        if len(group) < 2 or mark not in label_pt:
            continue
        px, py = label_pt[mark][0], label_pt[mark][1]

        def _d(seg):
            # centreline distance, matching the ownership metric -- a midpoint
            # metric here could overturn a correct ownership assignment
            return _point_to_segment_dist(px, py, seg["start"], seg["end"])

        group.sort(key=_d)
        for seg in group[1:]:
            seg["mark"] = None


def _filter_beam_segments(segments, limits, standards, snap_tol_mm):
    """Snap each beam width to a standard and drop widths outside the limit band.

    This is what rejects junction-clipped 'beams' (e.g. a 1064 mm-wide blob) while
    keeping real 300 mm members. Returns (kept_segments, dropped_count).
    """
    widths = [w / _MM for w in standards.get("beam_widths", [])]
    tol = snap_tol_mm / _MM
    w_min, w_max = limits["beam_width_min_mm"], limits["beam_width_max_mm"]
    kept = []
    dropped = 0
    for segment in segments:
        snapped = shapes.snap_to_standard(segment["width_mm"] / _MM, widths, tol) * _MM
        segment["width_mm"] = snapped
        if w_min <= snapped <= w_max:
            kept.append(segment)
        else:
            dropped += 1
    return kept, dropped


def _beam_segment(start, end, width_ft, z, layer, status):
    length_ft = ((start[0] - end[0]) ** 2 + (start[1] - end[1]) ** 2) ** 0.5
    return {
        "start": [start[0], start[1], z],
        "end": [end[0], end[1], z],
        "length_mm": length_ft * 304.8,
        "width_mm": width_ft * 304.8,
        "layer": layer,
        "status": status,
    }

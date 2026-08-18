# -*- coding: utf-8 -*-
"""Plan wall CENTRELINES from the wall-layer linework, before Revit is touched.

A wall arrives three ways in this corpus, and all three appear in one drawing
(test8):

  * A CLOSED THIN OUTLINE -- a quad (150 x 12490, sometimes rotated 10.3
    degrees off axis) or a rectilinear L/U ring one thickness wide all the way
    round (Project1's parapet). The outline IS the wall: a quad reads straight
    off `beam_centerline_from_quad`, a rectilinear ring decomposes into thin
    rectangles exactly as composite columns do.

  * AN ALMOST-CLOSED OUTLINE -- a U open by exactly one wall width, where the
    drafter never drew the far end cap (test8's `[4310, 150, 4310]` runs, open
    150). Closed across that gap it is the outline it was meant to be, so a
    polyline whose ends sit within `_WALL_MAX_MM` is read as a ring FIRST --
    and only kept when the ring proves thin. The fabricated closing edge is
    never emitted as geometry: when the ring is not a wall outline, what
    explodes into the pair pool is the DRAWN segments only (the lesson
    beam_segments' `_ring_keeps_all_points` records).

  * TWO PARALLEL FACES -- loose lines and open snakes, one face per record or
    the outer and inner face of an L-shaped core as sibling records (test8's
    S-RCC-WALL `[800, 8990, 3660]` / `[650, 8690, 3510]`). These pair the way
    `geom.shapes.recover_core_walls` pairs a fragmented lift core, generalised
    to ARBITRARY angles because the corpus is not axis-aligned (Project1 and
    test8 both carry 10.3-degree wall runs):

      - collinear faces MERGE across gaps up to `_COLLINEAR_BRIDGE_MM` first,
        so a door punched through a wall does not split it into two members
        (and a tee'd wall's end cap, which lies exactly on the crossing face's
        line, fills the very gap the tee cut);
      - candidate pairs bind SMALLEST-GAP-FIRST, so a thin wall claims its
        outer face before a far face reaches across a notch;
      - each pair spans the UNION of its two faces, so a face notched short on
        one side still lands the wall on its true extent.

A CUTOUT layer's linework is never a wall. test9's `PI_SHEAR WALL CUTOUT`
carries ten closed quads 240..500 wide -- indistinguishable from real wall
outlines by any width rule -- and its own legend says what they are: "HATCH
INDICATE CUTOUT FOR DOOR ABOVE". Planning them would wall up every doorway,
so a record whose layer name carries the cutout token (the same token the
hatch convention trusts) goes to `skipped`, loudly, and the override dialog
still owns the final word on the layer.

Units follow the package convention: records arrive in INTERNAL FEET (the
sweep and the pushbutton both scale the reader's millimetres by 1/304.8 before
any planner sees them -- compare foundation_plan), and sizes come back in
MILLIMETRES because that is what the user speaks. Revit-free, so all of it is
unit-testable and replayable offline.
"""

import math
import re
from collections import Counter

from . import config
from .classify.layers import CATEGORY_ARCH_WALL, CATEGORY_STRUCT_WALL
from .geom import shapes

_MM = config.MM_PER_FT

_WALL_KIND = {CATEGORY_STRUCT_WALL: "structural", CATEGORY_ARCH_WALL: "arch"}

# The width band, measured across the three wall-bearing fixtures (Project1,
# test8, test9). Real widths observed: 100 (test8's partitions), 150/160/175/
# 200/230/240/250/300/350 and a thin tail to 495; drawn outlines never exceed
# 250. Below 100 the candidate histogram is EMPTY down to the ~5 mm re-traced
# duplicates, and above 495 it is empty until 565, where the door artifacts
# begin (37 candidates at exactly 750 -- jamb strokes across 750 doorways --
# then 840/850/900). 90 and 520 sit inside those two deserts.
_WALL_MIN_MM = 90.0
_WALL_MAX_MM = 520.0

# How far apart two collinear faces may sit and still be one wall. test8's
# collinear-gap histogram has the crossing-wall interruptions at 150..200 (a
# tee'd wall cuts its host's face by its own width) and the door openings at
# 750..1310 (27 at 750, 10 at 1000, 12 at 1150, 12 at 1200); from 1350 up the
# values blur into room-scale separations. 1300 spans every measured door and
# stops before that blur. Wider than report.py's `_CORE_WALL_DOOR_MM` (700)
# on purpose: an architectural door is wider than a lift-core access.
_COLLINEAR_BRIDGE_MM = 1300.0

# Two parallel segments this close laterally are the SAME face drawn twice
# (or in pieces). Drafting noise measured in the corpus is under 3 mm, and
# the nearest genuinely distinct parallel line is a wall width away (>= 100),
# so 10 forgives a sloppy snap without ever welding a wall's two faces.
_COLLINEAR_LATERAL_MM = 10.0

# A pair whose gap changes along the overlap is two different walls
# converging, not one wall's faces -- the same refusal, with the same
# numbers, as shapes.pair_parallel_lines' taper rule.
_TAPER_TOL_MM = 15.0
_TAPER_FRACTION = 0.05

# The cutout token, matching the HATCH convention's (classify/layers.py):
# linework is deliberately never ROUTED by it, but a wall planner may still
# decline to build what the layer's own name calls a hole.
_CUTOUT_TOKEN = re.compile(r"cut[\s_-]*out", re.IGNORECASE)


def plan_walls(records, texts=None, tolerances=None):
    """{"segments": [...], "skipped": [...]} for the wall-category linework.

    Each segment carries `start`/`end` (the centreline, internal feet),
    `width_mm`, `length_mm`, `kind` ("structural" | "arch"), `layer`, and
    `source` ("outline" for a wall read off a closed ring, "pair" for one
    built from two faces). Everything consumed that plans nothing lands in
    `skipped` with a reason -- nothing is dropped in silence.

    `texts` is accepted for parity with the other planners and RESERVED: no
    fixture carries a wall-sizing note today (test9's wall texts are legend
    rows, already consumed by legend.py), so nothing reads it yet. Widths are
    measured off the drawing instead. `tolerances` overrides config's
    `pair_min_overlap_mm` / `parallel_angle_deg`, the same two knobs the beam
    pair pass takes them from.
    """
    tol = config.merged(tolerances)
    overlap_ft = config.mm_to_ft(tol["pair_min_overlap_mm"])
    sin_tol = math.sin(math.radians(tol["parallel_angle_deg"]))
    min_ft = config.mm_to_ft(_WALL_MIN_MM)
    max_ft = config.mm_to_ft(_WALL_MAX_MM)

    segments = []
    skipped = []
    pools = {CATEGORY_STRUCT_WALL: [], CATEGORY_ARCH_WALL: []}
    for record in records:
        category = getattr(record, "category", None)
        if category not in pools:
            continue
        kind = _WALL_KIND[category]
        if getattr(record, "kind", None) not in ("line", "polyline"):
            skipped.append({"reason": "unsupported kind ({0})".format(
                getattr(record, "kind", None)),
                "layer": record.layer_key, "kind": kind})
            continue
        if _CUTOUT_TOKEN.search(record.layer_key or ""):
            skipped.append({"reason": "cutout layer -- the drawing calls "
                                      "this a hole, not a wall",
                            "layer": record.layer_key, "kind": kind})
            continue
        points = [(p[0], p[1]) for p in record.points]
        z = record.points[0][2] if record.points else 0.0
        drawn = [(points[i], points[i + 1]) for i in range(len(points) - 1)
                 if _dist(points[i], points[i + 1]) > 1e-9]
        if not drawn:
            skipped.append({"reason": "degenerate (zero length)",
                            "layer": record.layer_key, "kind": kind})
            continue
        planned = None
        if len(points) >= 4 and _dist(points[0], points[-1]) <= max_ft:
            planned = _outline_walls(points, z, kind, record.layer_key,
                                     min_ft, max_ft)
        if planned is not None:
            outline_segments, slivers = planned
            segments.extend(outline_segments)
            skipped.extend(slivers)
            continue
        for a, b in drawn:
            pools[category].append((a, b, z, record.layer_key))

    for category, lines in pools.items():
        kind = _WALL_KIND[category]
        faces = _merge_collinear(lines, sin_tol)
        paired, leftover = _pair_faces(faces, min_ft, max_ft, overlap_ft,
                                       sin_tol)
        for start, end, width_ft, z, layer in paired:
            segments.append(_wall_segment(start, end, width_ft, z, layer,
                                          kind, "pair"))
        for face in leftover:
            length_mm = (face["hi"] - face["lo"]) * _MM
            a, b = _face_endpoints(face)
            # A leftover no longer than a wall is wide is an end cap or a
            # door jamb stroke -- drawn geometry, but the closure of a wall,
            # not a wall. Longer than that it is a face whose partner the
            # drawing never supplied (test9's single-line boundary walls).
            reason = ("end cap / jamb stroke -- closes a wall, is not one"
                      if length_mm <= _WALL_MAX_MM
                      else "no parallel partner within the wall width band")
            skipped.append({"reason": reason, "layer": face["layer"],
                            "kind": kind, "length_mm": length_mm,
                            "start": [a[0], a[1], face["z"]],
                            "end": [b[0], b[1], face["z"]]})
    return {"segments": segments, "skipped": skipped}


def _outline_walls(points, z, kind, layer, min_ft, max_ft):
    """The wall segments a closed (or one-cap-short) ring yields, or None.

    None means "this ring is not a thin wall outline" -- the caller explodes
    the DRAWN segments into the pair pool instead, and the closing edge the
    tolerance fabricated is forgotten. Returns (segments, sliver skips): the
    exact-cover decomposition of an L or U leaves jog slivers behind (test8's
    25x150 and 80x150), which are corners of the cover, not lost walls -- but
    they are reported all the same.
    """
    ring = shapes.simplify_ring(points)
    if len(ring) < 3:
        return None
    if len(ring) == 4:
        result = shapes.beam_centerline_from_quad(ring)
        if not result:
            return None                 # tapers: two members' edges, not one
        start, end, width_ft = result
        if not (min_ft <= width_ft <= max_ft):
            return None                 # a room traced closed, not a wall
        return [_wall_segment(start, end, width_ft, z, layer, kind,
                              "outline")], []
    if not shapes.is_rectilinear(ring):
        return None                     # an angled L arrives as loose faces
    rects = shapes.decompose_to_rectangles(ring, z)
    if not rects:
        return None
    widths = [min(rect.width_ft, rect.height_ft) for rect in rects]
    if any(width > max_ft for width in widths):
        return None                     # one fat cell: a room ring after all
    segments = []
    slivers = []
    for rect, width_ft in zip(rects, widths):
        if width_ft < min_ft:
            slivers.append({"reason": "ring sliver below the minimum wall "
                                      "width", "layer": layer, "kind": kind,
                            "length_mm": max(rect.width_ft, rect.height_ft)
                            * _MM})
            continue
        start, end, width_ft = shapes.beam_centerline_from_rect(rect)
        segments.append(_wall_segment(start, end, width_ft, z, layer, kind,
                                      "outline"))
    return segments, slivers


def _merge_collinear(lines, sin_tol):
    """Merge the pool's segments into FACES: maximal collinear runs.

    Two stages, exactly the donor's shape (recover_core_walls) with the axis
    generalised: first every segment is assigned to a LINE -- parallel within
    `sin_tol`, laterally within `_COLLINEAR_LATERAL_MM` -- longest segments
    first, so the longest run defines each line's axis; then each line's runs
    are sorted and chained across gaps up to `_COLLINEAR_BRIDGE_MM`, which is
    what carries a face across its door openings. Assigning to lines WITHOUT
    an axial condition first is what makes the chaining order-independent.

    A face is {"origin", "u", "n", "lo", "hi", "c", "z", "layer"} -- an axis
    frame, the run's interval along it, and `c`, the run's length-weighted
    mean lateral offset off the axis (the donor's `csum / cn`), so a face
    merged from slightly staggered re-traces sits at their mean rather than
    snapping onto whichever was longest. The layer kept is the one that
    contributed the most length, for the segment record.
    """
    lat_ft = config.mm_to_ft(_COLLINEAR_LATERAL_MM)
    bridge_ft = config.mm_to_ft(_COLLINEAR_BRIDGE_MM)
    order = sorted(lines, key=lambda l: -_dist(l[0], l[1]))
    axes = []                        # {"origin", "u", "n", "runs": [...]}
    for a, b, z, layer in order:
        length = _dist(a, b)
        u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        hit = None
        for axis in axes:
            au, an, ao = axis["u"], axis["n"], axis["origin"]
            if abs(u[0] * au[1] - u[1] * au[0]) > sin_tol:
                continue
            off_a = (a[0] - ao[0]) * an[0] + (a[1] - ao[1]) * an[1]
            off_b = (b[0] - ao[0]) * an[0] + (b[1] - ao[1]) * an[1]
            if max(abs(off_a), abs(off_b)) > lat_ft:
                continue
            hit = axis
            break
        if hit is None:
            hit = {"origin": a, "u": u, "n": (-u[1], u[0]), "runs": []}
            axes.append(hit)
        au, an, ao = hit["u"], hit["n"], hit["origin"]
        t0 = (a[0] - ao[0]) * au[0] + (a[1] - ao[1]) * au[1]
        t1 = (b[0] - ao[0]) * au[0] + (b[1] - ao[1]) * au[1]
        off = (((a[0] - ao[0]) * an[0] + (a[1] - ao[1]) * an[1])
               + ((b[0] - ao[0]) * an[0] + (b[1] - ao[1]) * an[1])) / 2.0
        hit["runs"].append((min(t0, t1), max(t0, t1), off, z, layer))

    faces = []
    for axis in axes:
        runs = sorted(axis["runs"])
        lo, hi, z, layers = runs[0][0], runs[0][1], runs[0][3], Counter()
        weight = runs[0][1] - runs[0][0]
        csum = runs[0][2] * weight
        layers[runs[0][4]] += weight
        for r_lo, r_hi, r_off, r_z, r_layer in runs[1:]:
            if r_lo - hi <= bridge_ft:
                hi = max(hi, r_hi)
                csum += r_off * (r_hi - r_lo)
                weight += r_hi - r_lo
                layers[r_layer] += r_hi - r_lo
            else:
                faces.append(_face(axis, lo, hi, csum / weight, z, layers))
                lo, hi, z, layers = r_lo, r_hi, r_z, Counter()
                weight = r_hi - r_lo
                csum = r_off * weight
                layers[r_layer] += weight
        faces.append(_face(axis, lo, hi, csum / weight, z, layers))
    return faces


def _face(axis, lo, hi, c, z, layers):
    return {"origin": axis["origin"], "u": axis["u"], "n": axis["n"],
            "lo": lo, "hi": hi, "c": c, "z": z,
            "layer": layers.most_common(1)[0][0]}


def _face_endpoints(face):
    ox = face["origin"][0] + face["n"][0] * face["c"]
    oy = face["origin"][1] + face["n"][1] * face["c"]
    ux, uy = face["u"]
    return ((ox + ux * face["lo"], oy + uy * face["lo"]),
            (ox + ux * face["hi"], oy + uy * face["hi"]))


def _pair_faces(faces, min_ft, max_ft, overlap_ft, sin_tol):
    """Bind opposing faces into wall segments, smallest gap first.

    Returns ([(start, end, width_ft, z, layer)], leftover faces). Candidates
    are every near-parallel pair whose lateral gap sits in the wall band and
    whose axial overlap reaches `overlap_ft`; the gap is read at BOTH ends of
    the overlap so a tapering pair is refused, and a pair whose faces sit on
    opposite sides of each other's axis (a shallow crossing) is refused with
    it. Each face binds at most once, and every segment spans the UNION of
    its two faces along the wall.
    """
    taper_tol_ft = config.mm_to_ft(_TAPER_TOL_MM)
    candidates = []
    for i in range(len(faces)):
        for j in range(i + 1, len(faces)):
            fit = _pair_geometry(faces[i], faces[j], min_ft, max_ft,
                                 overlap_ft, sin_tol, taper_tol_ft)
            if fit is not None:
                candidates.append((fit["gap"], i, j, fit))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    used = [False] * len(faces)
    paired = []
    for _gap, i, j, fit in candidates:
        if used[i] or used[j]:
            continue
        used[i] = used[j] = True
        paired.append(fit["segment"])
    leftover = [face for k, face in enumerate(faces) if not used[k]]
    return paired, leftover


def _pair_geometry(face_a, face_b, min_ft, max_ft, overlap_ft, sin_tol,
                   taper_tol_ft):
    """The candidate a face pair makes, or None. Measured in face_a's frame."""
    ua, ub = face_a["u"], face_b["u"]
    if abs(ua[0] * ub[1] - ua[1] * ub[0]) > sin_tol:
        return None
    an = face_a["n"]
    a0, _a1 = _face_endpoints(face_a)
    length_a = face_a["hi"] - face_a["lo"]
    (b0, b1) = _face_endpoints(face_b)
    # face_b's ends, in face_a's own frame (its start endpoint at t = 0)
    t_b0 = (b0[0] - a0[0]) * ua[0] + (b0[1] - a0[1]) * ua[1]
    t_b1 = (b1[0] - a0[0]) * ua[0] + (b1[1] - a0[1]) * ua[1]
    off_b0 = (b0[0] - a0[0]) * an[0] + (b0[1] - a0[1]) * an[1]
    off_b1 = (b1[0] - a0[0]) * an[0] + (b1[1] - a0[1]) * an[1]
    lo = max(0.0, min(t_b0, t_b1))
    hi = min(length_a, max(t_b0, t_b1))
    if hi - lo < overlap_ft:
        return None
    # the offset at both ends of the shared overlap, by interpolation along b
    span = t_b1 - t_b0
    if abs(span) < 1e-12:
        return None
    off_lo = off_b0 + (lo - t_b0) / span * (off_b1 - off_b0)
    off_hi = off_b0 + (hi - t_b0) / span * (off_b1 - off_b0)
    if off_lo * off_hi <= 0:
        return None                     # crosses the axis: never a wall pair
    gap = (abs(off_lo) + abs(off_hi)) / 2.0
    taper = abs(abs(off_lo) - abs(off_hi))
    if taper > max(taper_tol_ft, _TAPER_FRACTION * gap):
        return None
    if not (min_ft <= gap <= max_ft):
        return None
    union_lo = min(0.0, t_b0, t_b1)
    union_hi = max(length_a, t_b0, t_b1)
    offset = (off_lo + off_hi) / 4.0    # signed mid-gap, half the mean offset
    start = (a0[0] + ua[0] * union_lo + an[0] * offset,
             a0[1] + ua[1] * union_lo + an[1] * offset)
    end = (a0[0] + ua[0] * union_hi + an[0] * offset,
           a0[1] + ua[1] * union_hi + an[1] * offset)
    layer = max((face_a, face_b), key=lambda f: f["hi"] - f["lo"])["layer"]
    return {"gap": gap,
            "segment": (start, end, gap, face_a["z"], layer)}


def _wall_segment(start, end, width_ft, z, layer, kind, source):
    length_ft = _dist(start, end)
    return {"start": [start[0], start[1], z],
            "end": [end[0], end[1], z],
            "width_mm": width_ft * _MM,
            "length_mm": length_ft * _MM,
            "kind": kind, "layer": layer, "source": source}


def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])

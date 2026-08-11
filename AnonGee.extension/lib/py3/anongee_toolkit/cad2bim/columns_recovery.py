# -*- coding: utf-8 -*-
"""Getting a column back when the drawing did not hand one over cleanly.

Detection (columns_sections, still in report.py) places what is unambiguous: a
closed outline of a plausible size. Real drawings are messier, and each of these
passes answers one specific way a member goes missing:

    recover_core_walls_from_labels   a fused lift/stair core, re-tiled from the
                                     mark+size labels that name its walls
    recover_unplaced_labeled_columns a column so fragmented that recovery folded
                                     it into a neighbour, rebuilt from its label
    recover_outline_columns          a blade/wall column the SIZE LIMITS refused,
                                     placed at its drawn size because its outline
                                     is closed and unambiguous
    recover_face_columns             a COMBINED member -- a wall carrying several
                                     columns, exploded to bare lines -- walked out
                                     of the planar graph its linework forms
    drop_nested_columns              the other direction: a member placed twice,
                                     once whole and once in pieces

Every pass takes the `sections` dict detection produced and edits it in place,
returning how many rectangles it changed, so the console can say which pass did
what. All are label-gated or geometry-gated: none of them invents a column that
the drawing does not evidence, because a wrong column is worse than a missing
one -- it has to be found and deleted by hand.

Revit-free, like the rest of report: it reads plain dicts and returns counts.
"""

import math

from . import config
from .geom import shapes
from .classify.layers import CATEGORY_COLUMN
from .limits import DEFAULT_LIMITS
from .column_geom import (_bbox_half, _column_footprints, _distinct_ring_corners,
                          _inside_rectangles, _label_size, _ring_closed,
                          column_outline_footprints)

_MM = config.MM_PER_FT

_CORE_LABEL_MARGIN_MM = 1100.0  # a wall's label may sit this far outside the blob
#                                 (bottom-row columns carry their text well below them)
_CORE_DIM_TOL_MM = 80.0         # a cell-rectangle must match the label size this closely
_CORE_EDGE_EPS_MM = 2.0         # merge cell grid edges closer than this (float noise)
_ABSORB_RADIUS_MM = 2000.0   # the orphaned label and its leftover pieces lie within this
_ABSORB_PAD_MM = 60.0        # a fragment point this far inside a placed column is "its"
_ABSORB_MIN_PTS = 3          # need at least this much leftover geometry as evidence

def recover_core_walls_from_labels(sections, column_texts, schedule=None):
    """Re-place fused-outline columns from their size labels, before text-correction.

    When abutting members share an outline -- a lift/stair core drawn as loose wall
    lines, or one column cast hard against another (Test19's C16 under C15) -- the
    pieces are assembled into one blob and decomposed greedily. The greedy cut
    mis-assigns the shared corners/edges, so each member keeps its THICKNESS but is
    clipped/extended along its length and offset by the stolen cell (a 5300 wall
    placed as 4700, 600 mm low; or C16's whole footprint swallowed into C15).
    text-correction would then resize/merge to the labels but keep that wrong split.

    Here each fused blob is re-tiled from the labels instead: the blob's exact-cover
    pieces define a cell grid, and members are carved LONGEST first, each claiming
    the label-sized run of still-unclaimed cells nearest its label. Applied only to a
    blob that holds at least one MARKED label (so a working markless-only core is never
    touched) and only when the labels -- marked and markless alike -- tile the WHOLE
    blob cleanly; otherwise the blob is left exactly as decomposed. A markless-but-sized
    stub packed into such a blob (Test19's "300x600" under C17) is placed unnamed.
    Returns the number of blobs re-tiled.
    """
    entries = sections.get("entries", [])
    # Every sized label (inline size or schedule[mark]) is a tiling candidate, INCLUDING
    # markless ones -- a fused outline can pack a marked column over an unlabelled-but-
    # sized stub (Test19's C17 over a "300x600"), and both need a cell. Each label is
    # paired with its (small, big) mm size; a blob is only re-tiled when it holds at
    # least one MARKED label (below), so a working markless-only core is never touched.
    labels = []
    for text in (column_texts or []):
        if not text.point_internal:
            continue
        size = _label_size(text, schedule or {})
        if size is not None:
            labels.append((text, size))
    if not labels:
        return 0
    # Only the greedy decompositions that can mis-cut a fused outline are candidates.
    cand_status = ("composite", "recovered_strip")
    pieces = [rect for entry in entries if entry.get("status") in cand_status
              for rect in entry["rectangles"]]
    if not pieces:
        return 0
    consumed = set()
    carved = []
    retiled = 0
    for comp in _connected_blobs(pieces):
        if len(comp) < 2:
            continue                       # a lone strip: nothing fused to re-cut
        blob_labels = _labels_for_blob(comp, labels)
        if not any(lbl[0] for lbl in blob_labels):
            continue                       # only markless labels here: a working core
        walls = _carve_blob_from_labels(comp, blob_labels)
        if walls is None:
            continue                       # not a clean label tiling: leave as-is
        for rect in comp:
            consumed.add(id(rect))
        carved.extend(walls)
        retiled += 1
    if not retiled:
        return 0
    for entry in entries:
        if entry.get("status") in cand_status:
            entry["rectangles"] = [r for r in entry["rectangles"]
                                   if id(r) not in consumed]
    entries.append({"layer": "(label core)", "status": "label_core_wall",
                    "approx": True, "rectangles": carved})
    sections["entries"] = [e for e in entries if e["rectangles"]]
    counts = sections.setdefault("status_counts", {})
    counts["label_core_wall"] = counts.get("label_core_wall", 0) + len(carved)
    return retiled


def _rect_bounds_mm(rect):
    """(x_min, y_min, x_max, y_max) of an axis-aligned rect dict, in mm."""
    cx, cy = rect["center"][0] * _MM, rect["center"][1] * _MM
    return (cx - rect["width_mm"] / 2.0, cy - rect["height_mm"] / 2.0,
            cx + rect["width_mm"] / 2.0, cy + rect["height_mm"] / 2.0)


def _connected_blobs(rects):
    """Group rectangles into edge-adjacent components (a fused outline = one blob)."""
    n = len(rects)
    bounds = [_rect_bounds_mm(r) for r in rects]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    eps = 1.0
    for i in range(n):
        ax0, ay0, ax1, ay1 = bounds[i]
        for j in range(i + 1, n):
            bx0, by0, bx1, by1 = bounds[j]
            if (ax0 - eps <= bx1 and bx0 - eps <= ax1 and
                    ay0 - eps <= by1 and by0 - eps <= ay1):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(rects[i])
    return list(groups.values())


def _labels_for_blob(comp, labels):
    """(mark, small, big, lx, ly) for each sized label inside the blob's grown bbox.

    `labels` are (TextRecord, (small, big) mm) pairs; the bbox is grown by
    _CORE_LABEL_MARGIN_MM so a wall's label that sits just outside the outline counts.
    """
    bounds = [_rect_bounds_mm(r) for r in comp]
    x0 = min(b[0] for b in bounds) - _CORE_LABEL_MARGIN_MM
    y0 = min(b[1] for b in bounds) - _CORE_LABEL_MARGIN_MM
    x1 = max(b[2] for b in bounds) + _CORE_LABEL_MARGIN_MM
    y1 = max(b[3] for b in bounds) + _CORE_LABEL_MARGIN_MM
    out = []
    for text, (small, big) in labels:
        lx, ly = text.point_internal[0] * _MM, text.point_internal[1] * _MM
        if x0 <= lx <= x1 and y0 <= ly <= y1:
            out.append((text.mark, small, big, lx, ly))
    return out


def _unique_edges(values):
    """Sorted grid edges with near-duplicates (float noise) merged."""
    out = []
    for v in sorted(values):
        if not out or v - out[-1] > _CORE_EDGE_EPS_MM:
            out.append(v)
    return out


def _dims_match(w, h, b_mm, h_mm):
    """True when a w x h cell-rectangle matches the (b, h) label in either orientation."""
    t = _CORE_DIM_TOL_MM
    return ((abs(w - b_mm) <= t and abs(h - h_mm) <= t) or
            (abs(w - h_mm) <= t and abs(h - b_mm) <= t))


def _carve_blob_from_labels(comp, comp_labels):
    """Re-tile one fused blob into label-sized walls, or None if labels can't tile it.

    The blob's exact-cover pieces give a cell grid; each label carves the nearest
    matching run of unclaimed inside-cells, longest wall first. Returns the carved
    wall rects only when EVERY inside cell is claimed (a clean tiling), so an
    ambiguous or partially labelled blob falls back to the original decomposition.
    """
    if not comp_labels:
        return None
    bounds = [_rect_bounds_mm(r) for r in comp]
    xs = _unique_edges([b[0] for b in bounds] + [b[2] for b in bounds])
    ys = _unique_edges([b[1] for b in bounds] + [b[3] for b in bounds])
    nc, nr = len(xs) - 1, len(ys) - 1
    if nc < 1 or nr < 1:
        return None
    inside = [[False] * nc for _ in range(nr)]
    for r in range(nr):
        cy = (ys[r] + ys[r + 1]) / 2.0
        for c in range(nc):
            cx = (xs[c] + xs[c + 1]) / 2.0
            inside[r][c] = any(b[0] < cx < b[2] and b[1] < cy < b[3] for b in bounds)
    claimed = [[False] * nc for _ in range(nr)]
    z = comp[0]["center"][2]
    walls = []
    for mark, b_mm, h_mm, lx, ly in sorted(comp_labels,
                                           key=lambda L: -max(L[1], L[2])):
        best, best_d = None, None
        for c0 in range(nc):
            for c1 in range(c0, nc):
                w = xs[c1 + 1] - xs[c0]
                for r0 in range(nr):
                    for r1 in range(r0, nr):
                        ht = ys[r1 + 1] - ys[r0]
                        if not _dims_match(w, ht, b_mm, h_mm):
                            continue
                        if not _cells_free(inside, claimed, r0, r1, c0, c1):
                            continue
                        mx = (xs[c0] + xs[c1 + 1]) / 2.0
                        my = (ys[r0] + ys[r1 + 1]) / 2.0
                        d = (mx - lx) ** 2 + (my - ly) ** 2
                        if best_d is None or d < best_d:
                            best, best_d = (r0, r1, c0, c1), d
        if best is None:
            return None
        r0, r1, c0, c1 = best
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                claimed[r][c] = True
        walls.append(_wall_rect(xs[c0], ys[r0], xs[c1 + 1], ys[r1 + 1], z, mark))
    for r in range(nr):
        for c in range(nc):
            if inside[r][c] and not claimed[r][c]:
                return None                # an unlabelled cell left over: not confident
    return walls


def _cells_free(inside, claimed, r0, r1, c0, c1):
    """True when every cell in the range is inside the blob and not yet claimed."""
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            if not inside[r][c] or claimed[r][c]:
                return False
    return True


def _wall_rect(x0, y0, x1, y1, z, mark):
    """A wall rect dict (mm bounds -> internal-feet centre + mm size), long axis set."""
    w_mm, h_mm = x1 - x0, y1 - y0
    return {"center": [((x0 + x1) / 2.0) / _MM, ((y0 + y1) / 2.0) / _MM, z],
            "width_mm": w_mm, "height_mm": h_mm,
            "width_ft": w_mm / _MM, "height_ft": h_mm / _MM,
            "long_axis_deg": 90.0 if h_mm >= w_mm else 0.0, "mark": mark}


def _aabb_overlaps(cx, cy, hx, hy, rects, margin_ft):
    """True if the box with half-extents (hx, hy) at (cx, cy) overlaps any rect."""
    for r in rects:
        rhx, rhy = _bbox_half(r)
        if (abs(cx - r["center"][0]) < hx + rhx - margin_ft and
                abs(cy - r["center"][1]) < hy + rhy - margin_ft):
            return True
    return False


def recover_unplaced_labeled_columns(sections, column_texts, schedule, limits=None):
    """Place a labelled column that geometry recovery ABSORBED into a larger neighbour.

    A small column cast against a bigger one (e.g. a 300x600 beside a 600x900) can
    fragment so badly that recovery merges its pieces into the neighbour and drops
    the rest, orphaning its plan label. For a mark that has a schedule size but no
    placed column, the leftover fragments NOT already inside a placed column are
    clustered; the schedule-sized column is then placed ABUTTING its nearest placed
    neighbour edge-to-edge -- the side, and the centre on the shared face, come from
    the leftover bits. The abutment fixes the coordinate across the shared face
    exactly; the other coordinate comes from the leftover centroid, clamped so the
    column still meets the neighbour. These columns sit deliberately off-axis against
    their partner, so they are NOT snapped to the structural grid.

    Conservative by construction, so a stray label can never fabricate a column:
      * the mark must be unplaced AND carry a schedule size,
      * a placed neighbour must sit within _ABSORB_RADIUS (a real column region),
      * >= _ABSORB_MIN_PTS leftover points outside every placed footprint must remain
        (hard geometry evidence the column was really drawn there),
      * the result must land in range and overlap nothing already placed.
    Returns the count placed.
    """
    entries = sections.get("entries", [])
    placed = [r for e in entries for r in e["rectangles"]]
    if not placed:
        return 0
    placed_marks = set(r.get("mark") for r in placed if r.get("mark"))
    placed_marks |= set(c.get("mark") for c in (sections.get("circles") or [])
                        if c.get("mark"))
    limits = limits or DEFAULT_LIMITS
    absorb = config.mm_to_ft(_ABSORB_RADIUS_MM)
    pad = config.mm_to_ft(_ABSORB_PAD_MM)
    frag_pts = [(config.mm_to_ft(p[0]), config.mm_to_ft(p[1]))
                for g in (sections.get("dropped_raw") or []) for p in g.get("pts", [])]

    def inside_placed(px, py):
        for r in placed:
            rhx, rhy = _bbox_half(r)
            if abs(px - r["center"][0]) <= rhx + pad and abs(py - r["center"][1]) <= rhy + pad:
                return True
        return False

    new_rects = []
    for text in column_texts or []:
        if not text.mark or text.mark in placed_marks:
            continue
        if text.mark not in schedule or not text.point_internal:
            continue
        lx, ly = text.point_internal[0], text.point_internal[1]
        if not any((r["center"][0] - lx) ** 2 + (r["center"][1] - ly) ** 2 <= absorb * absorb
                   for r in placed):
            continue   # no placed neighbour: not a known column region, skip
        iso = [(px, py) for (px, py) in frag_pts
               if (px - lx) ** 2 + (py - ly) ** 2 <= absorb * absorb
               and not inside_placed(px, py)]
        if len(iso) < _ABSORB_MIN_PTS:
            continue   # no leftover geometry as evidence -> never fabricate a column
        b_mm, h_mm = schedule[text.mark]
        small, big = min(b_mm, h_mm), max(b_mm, h_mm)
        if not (limits["col_b_min_mm"] <= small <= limits["col_b_max_mm"] and
                limits["col_h_min_mm"] <= big <= limits["col_h_max_mm"]):
            continue
        big_ft, small_ft = big / _MM, small / _MM
        ccx = sum(p[0] for p in iso) / len(iso)
        ccy = sum(p[1] for p in iso) / len(iso)
        # The neighbour these leftover bits abut: the placed column nearest the cluster.
        nb = min(placed, key=lambda r: (r["center"][0] - ccx) ** 2
                 + (r["center"][1] - ccy) ** 2)
        nbx, nby, nbz = nb["center"]
        nb_hx, nb_hy = _bbox_half(nb)
        if abs(ccy - nby) >= abs(ccx - nbx):
            # abut below/above: long side spans away from the shared horizontal face.
            # y is fixed by the abutment (edge-to-edge); x is the leftover centroid,
            # clamped so the column still meets the neighbour's face.
            sgn = 1.0 if ccy >= nby else -1.0
            cy = nby + sgn * (nb_hy + big_ft / 2.0)
            lim = nb_hx + small_ft / 2.0
            cx = min(max(ccx, nbx - lim), nbx + lim)
            hx, hy, deg = small_ft / 2.0, big_ft / 2.0, 90.0
        else:
            # abut left/right: long side spans away from the shared vertical face.
            sgn = 1.0 if ccx >= nbx else -1.0
            cx = nbx + sgn * (nb_hx + big_ft / 2.0)
            lim = nb_hy + small_ft / 2.0
            cy = min(max(ccy, nby - lim), nby + lim)
            hx, hy, deg = big_ft / 2.0, small_ft / 2.0, 0.0
        if _aabb_overlaps(cx, cy, hx, hy, placed, config.mm_to_ft(_ABSORB_PAD_MM)):
            continue   # would sit on top of an existing column -> skip, never duplicate
        rect = {"center": [cx, cy, nbz],
                "width_ft": small_ft, "height_ft": big_ft,
                "width_mm": small, "height_mm": big,
                "long_axis_deg": deg, "mark": text.mark}
        new_rects.append(rect)
        placed.append(rect)
        placed_marks.add(text.mark)

    if not new_rects:
        return 0
    entries.append({"layer": "(label-recovered)", "status": "label_recovered",
                    "approx": True, "rectangles": new_rects})
    counts = sections.setdefault("status_counts", {})
    counts["label_recovered"] = counts.get("label_recovered", 0) + len(new_rects)
    sections["total_rectangles"] = sections.get("total_rectangles", 0) + len(new_rects)
    return len(new_rects)


def recover_outline_columns(sections, records, column_texts=None,
                            mark_reach_mm=700.0):
    """Place columns from CLOSED rectangular column-layer outlines the size
    limits rejected.

    Blade / wall-columns (test8's 250x3250 slanted strips, labelled AC19..BC28)
    exceed the schedule-plausible size band, so detection drops them -- yet their
    outlines are drawn CLOSED and unambiguous, and the beam layer even re-traces
    them. Every closed 4-corner column-layer outline that does not overlap an
    already placed column becomes a column at its drawn size, position and angle;
    the nearest unclaimed column mark within reach names it. These columns are
    NOT grid-snapped or size-snapped -- the drawn outline is the authority.
    Returns the count placed.
    """
    candidates = column_outline_footprints(records)
    if not candidates:
        return 0
    reach_ft = config.mm_to_ft(mark_reach_mm)
    placed = _column_footprints(sections, sections.get("circles"))
    new_rects = []
    for fp in candidates:
        _kind, cx, cy, ca, sa, hl, hs = fp
        dup = False
        for pfp in placed:
            if pfp[0] == "circle":
                _k, px, py, pr = pfp
                if (cx - px) ** 2 + (cy - py) ** 2 <= (pr + hs) ** 2:
                    dup = True
                    break
            else:
                _k, px, py, pca, psa, phl, phs = pfp
                dx, dy = cx - px, cy - py
                u = dx * pca + dy * psa
                v = dy * pca - dx * psa
                if abs(u) <= phl + hs and abs(v) <= phs + hs:
                    dup = True
                    break
        if dup:
            continue
        small = hs * 2.0 * _MM
        big = hl * 2.0 * _MM
        new_rects.append({"center": [cx, cy, 0.0],
                          "width_mm": small, "height_mm": big,
                          "width_ft": small / _MM, "height_ft": big / _MM,
                          "long_axis_deg": math.degrees(math.atan2(sa, ca)) % 180.0,
                          "mark": None, "_fp": fp})
        placed.append(fp)             # two outlines can never stack
    if not new_rects:
        return 0
    entries = sections.get("entries", [])
    claimed = set(r.get("mark") for e in entries for r in e.get("rectangles", [])
                  if r.get("mark"))
    claimed |= set(c.get("mark") for c in (sections.get("circles") or [])
                   if c.get("mark"))
    for text in (column_texts or []):
        mark = getattr(text, "mark", None)
        point = getattr(text, "point_internal", None)
        if not mark or mark in claimed or point is None:
            continue
        best = None
        for rect in new_rects:
            if rect["mark"]:
                continue
            _kind, cx, cy, ca, sa, hl, hs = rect["_fp"]
            dx, dy = point[0] - cx, point[1] - cy
            u = dx * ca + dy * sa
            v = dy * ca - dx * sa
            outside = (max(abs(u) - hl, 0.0) ** 2 + max(abs(v) - hs, 0.0) ** 2) ** 0.5
            if outside <= reach_ft and (best is None or outside < best[0]):
                best = (outside, rect)
        if best is not None:
            best[1]["mark"] = mark
            claimed.add(mark)
    for rect in new_rects:
        del rect["_fp"]
    entries.append({"layer": "COLUMN (closed outline)", "status": "outline_recovered",
                    "rectangles": new_rects})
    sections["entries"] = entries
    counts = sections.setdefault("status_counts", {})
    counts["outline_recovered"] = counts.get("outline_recovered", 0) + len(new_rects)
    sections["total_rectangles"] = sections.get("total_rectangles", 0) + len(new_rects)
    return len(new_rects)


_FACE_LABEL_REACH_MM = 900.0      # a size label sits just off the member it names


_FACE_SIZE_TOL_MM = 60.0          # drawn vs labelled dimension


_FACE_LIKENESS = 0.6              # a guess this much of the face is the same member


def recover_face_columns(sections, records, column_texts=None,
                         mark_reach_mm=_FACE_LABEL_REACH_MM,
                         size_tol_mm=_FACE_SIZE_TOL_MM):
    """Place COMBINED columns whose outline exists only as a graph face.

    A merged member -- test10's roof: a 12300x300 perimeter wall carrying four
    300x3300 columns, every piece exploded to bare lines -- closes into no ring
    at all, because the wall's own edge runs THROUGH each column root. Walking
    the faces of that line soup recovers each drawn member exactly (see
    shapes.recover_face_columns).

    Deliberately gated, because a face is otherwise easy to invent: a recovered
    rectangle is kept only when the plan's own SIZE LABEL agrees with it -- a
    "300 X 12300" text within reach whose dimensions match what was walked. No
    label, no column; a rectangle already covered by a placed column is a
    duplicate and is dropped. In exchange the size limits do not apply: the
    drawing and its label agree, which is better evidence than a size band.

    Any earlier APPROXIMATE rectangle (the leftover-fragment passes) that falls
    inside a recovered face is removed: the same member, guessed badly.

    Returns the count placed.
    """
    labels = [text for text in (column_texts or [])
              if getattr(text, "b_mm", None) and getattr(text, "h_mm", None)]
    if not labels:
        return 0
    paths = _open_column_paths(records)
    if not paths:
        return 0
    z = next((p[0][2] for p in paths if p and len(p[0]) > 2), 0.0)
    candidates = shapes.recover_face_columns(paths, z=z)
    if not candidates:
        return 0
    # A placed column blocks a face only while it is a fair LIKENESS of it: a
    # 212x424 blob standing in for a 300x2000 column, or a 2700-long piece of a
    # 12300 wall read as an outline of its own, is part of the member rather
    # than the member, and must not veto the one the label agrees with.
    placed = _column_footprints(sections, sections.get("circles"))
    reach_ft = config.mm_to_ft(mark_reach_mm)
    new_rects = []
    kept_fps = []
    for rect in candidates:
        cx, cy, _cz = rect.center
        width_mm = rect.width_ft * _MM
        height_mm = rect.height_ft * _MM
        small, big = min(width_mm, height_mm), max(width_mm, height_mm)
        likeness = _FACE_LIKENESS * rect.width_ft * rect.height_ft
        if _covered_by(cx, cy, kept_fps):
            continue
        if _covered_by(cx, cy, placed, min_area_ft2=likeness):
            continue
        label = _matching_size_label(labels, rect, reach_ft, size_tol_mm)
        if label is None:
            continue
        deg = 0.0 if width_mm >= height_mm else 90.0
        new_rects.append({"center": [cx, cy, z],
                          "width_mm": small, "height_mm": big,
                          "width_ft": small / _MM, "height_ft": big / _MM,
                          "long_axis_deg": deg,
                          "mark": getattr(label, "mark", None)})
        kept_fps.append(("rect", cx, cy, math.cos(math.radians(deg)),
                         math.sin(math.radians(deg)),
                         big / _MM / 2.0, small / _MM / 2.0))
    if not new_rects:
        return 0
    dropped = _drop_approximate_inside(sections, new_rects)
    entries = sections.get("entries", [])
    entries.append({"layer": "COLUMN (graph face)", "status": "face_recovered",
                    "approx": False, "rectangles": new_rects})
    sections["entries"] = entries
    counts = sections.setdefault("status_counts", {})
    counts["face_recovered"] = counts.get("face_recovered", 0) + len(new_rects)
    sections["total_rectangles"] = (sections.get("total_rectangles", 0)
                                    + len(new_rects) - dropped)
    return len(new_rects)


def _open_column_paths(records):
    """Column-layer geometry that closes into no ring of its own."""
    paths = []
    for record in (records or []):
        if record.category != CATEGORY_COLUMN:
            continue
        points = record.points or []
        if len(points) < 2:
            continue
        if len(points) > 3 and _ring_closed(points):
            continue                      # a closed outline is already a column
        paths.append(points)
    return paths


def _covered_by(cx, cy, footprints, min_area_ft2=0.0):
    """True when (cx, cy) lies inside any footprint of at least `min_area_ft2`."""
    for fp in footprints or []:
        if fp[0] == "circle":
            _k, px, py, pr = fp
            if math.pi * pr * pr < min_area_ft2:
                continue
            if (cx - px) ** 2 + (cy - py) ** 2 <= pr ** 2:
                return True
            continue
        _k, px, py, ca, sa, hl, hs = fp
        if 4.0 * hl * hs < min_area_ft2:
            continue
        dx, dy = cx - px, cy - py
        u = dx * ca + dy * sa
        v = dy * ca - dx * sa
        if abs(u) <= hl and abs(v) <= hs:
            return True
    return False


def _matching_size_label(labels, rect, reach_ft, size_tol_mm):
    """The nearest size label that AGREES with this rectangle, or None."""
    cx, cy, _cz = rect.center
    half_w = rect.width_ft / 2.0
    half_h = rect.height_ft / 2.0
    width_mm = rect.width_ft * _MM
    height_mm = rect.height_ft * _MM
    best = None
    for text in labels:
        point = getattr(text, "point_internal", None)
        if point is None:
            continue
        outside = ((max(abs(point[0] - cx) - half_w, 0.0) ** 2
                    + max(abs(point[1] - cy) - half_h, 0.0) ** 2) ** 0.5)
        if outside > reach_ft:
            continue
        if not _dims_match_tol(width_mm, height_mm, text.b_mm, text.h_mm,
                               size_tol_mm):
            continue
        if best is None or outside < best[0]:
            best = (outside, text)
    return best[1] if best else None


def _dims_match_tol(width_mm, height_mm, b_mm, h_mm, tol_mm):
    small, big = min(width_mm, height_mm), max(width_mm, height_mm)
    label_small, label_big = min(b_mm, h_mm), max(b_mm, h_mm)
    return (abs(small - label_small) <= tol_mm
            and abs(big - label_big) <= tol_mm)


def drop_nested_columns(sections, pad_mm=2.0, thickness_tol_mm=20.0):
    """Remove a column that is a LENGTH of another column, read twice.

    Test10's roof placed its 12300x300 perimeter wall AND two 2700x300 lengths
    of that same wall, which arrived as closed outlines of their own and so
    passed every earlier check. Two solids cannot share ground.

    Kept deliberately narrow, because "inside a bigger rectangle" alone is not
    evidence of a duplicate: a 400x660 column can sit inside the bounding box of
    a 5630x400 wall it merely abuts, and dropping that would lose a real member.
    All three must hold:

      * the small one lies WHOLLY inside the big one;
      * they are the same THICKNESS (short side), within `thickness_tol_mm`;
      * their long axes are PARALLEL.

    which is the signature of one wall drawn as a whole and again in pieces.
    Returns the count removed.
    """
    boxes = []
    for entry in sections.get("entries", []):
        for rect in entry.get("rectangles", []):
            half_w, half_h = _rect_half_box(rect)
            cx, cy, _cz = rect["center"]
            width = rect["width_mm"]
            height = rect["height_mm"]
            boxes.append({"entry": entry, "rect": rect, "cx": cx, "cy": cy,
                          "hw": half_w, "hh": half_h,
                          "thickness": min(width, height),
                          "axis": _long_axis_deg(rect),
                          "area": 4.0 * half_w * half_h})
    if len(boxes) < 2:
        return 0
    pad = config.mm_to_ft(pad_mm)
    boxes.sort(key=lambda box: box["area"])          # smallest first
    doomed = []
    for index, small in enumerate(boxes):
        for big in boxes[index + 1:]:                # only larger ones
            if abs(small["cx"] - big["cx"]) + small["hw"] > big["hw"] + pad:
                continue
            if abs(small["cy"] - big["cy"]) + small["hh"] > big["hh"] + pad:
                continue
            if abs(small["thickness"] - big["thickness"]) > thickness_tol_mm:
                continue                             # a different member
            turn = abs(small["axis"] - big["axis"]) % 180.0
            if min(turn, 180.0 - turn) > 3.0:
                continue                             # crossing, not colinear
            doomed.append(small)
            break
    if not doomed:
        return 0
    for box in doomed:
        try:
            box["entry"]["rectangles"].remove(box["rect"])
        except ValueError:
            continue
    sections["entries"] = [entry for entry in sections.get("entries", [])
                           if entry.get("rectangles")]
    sections["total_rectangles"] = max(
        sections.get("total_rectangles", 0) - len(doomed), 0)
    counts = sections.setdefault("status_counts", {})
    counts["nested_dropped"] = counts.get("nested_dropped", 0) + len(doomed)
    return len(doomed)


def _long_axis_deg(rect):
    """The angle the rectangle's LONG side runs at, in degrees."""
    deg = rect.get("long_axis_deg")
    if deg is not None:
        return float(deg)
    return 0.0 if rect["width_mm"] >= rect["height_mm"] else 90.0


def _rect_half_box(rect):
    """A rectangle's AXIS-ALIGNED half extents (half width, half height).

    Two conventions live in these dicts: a plain rect has no `long_axis_deg`
    and its width/height are the x/y extents as drawn, while an oriented one
    carries its SMALL side as the width and its long side along the angle.
    Both come out right here, and a rotated rect gives its true bounding box.
    """
    w = rect["width_mm"] / _MM
    h = rect["height_mm"] / _MM
    deg = rect.get("long_axis_deg")
    if deg is None:
        return w / 2.0, h / 2.0
    long_half, short_half = max(w, h) / 2.0, min(w, h) / 2.0
    theta = math.radians(deg)
    cos, sin = abs(math.cos(theta)), abs(math.sin(theta))
    return (long_half * cos + short_half * sin,
            long_half * sin + short_half * cos)


def _drop_approximate_inside(sections, new_rects):
    """Remove the rectangles a recovered face now covers properly.

    Two kinds go: a GUESS whose centre the face contains (the 45-degree blob a
    comb corner leaves behind), and ANY rectangle -- however it was found --
    that lies WHOLLY inside the face. Test10's roof placed its 12300 wall as
    well as two 2700-long pieces of that same wall, read as closed outlines of
    their own: two solids in one place is always wrong, and the face, agreeing
    with the plan's own label, is the one to keep.
    """
    boxes = [(rect["center"][0], rect["center"][1]) + _rect_half_box(rect)
             for rect in new_rects]
    pad = config.mm_to_ft(2.0)
    dropped = 0
    for entry in sections.get("entries", []):
        approx = bool(entry.get("approx"))
        kept = []
        for rect in entry.get("rectangles", []):
            cx, cy, _cz = rect["center"]
            own_w, own_h = _rect_half_box(rect)
            covered = False
            for bx, by, hw, hh in boxes:
                if approx and abs(cx - bx) <= hw and abs(cy - by) <= hh:
                    covered = True                  # a guess at this member
                    break
                if (abs(cx - bx) + own_w <= hw + pad
                        and abs(cy - by) + own_h <= hh + pad):
                    covered = True                  # a piece of this member
                    break
            if covered:
                dropped += 1
            else:
                kept.append(rect)
        entry["rectangles"] = kept
    sections["entries"] = [e for e in sections.get("entries", [])
                           if e.get("rectangles")]
    return dropped

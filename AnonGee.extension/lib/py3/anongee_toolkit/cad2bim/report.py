# -*- coding: utf-8 -*-
"""Reporting: a human summary for the pyRevit output window and a JSON export.

The JSON schema is deliberately the intermediate format the future external
CPython 3 + ezdxf validator will consume, so writing it now is not throwaway --
it is the contract between the in-Revit reader and the out-of-Revit checker.
"""

import json
import math
from collections import defaultdict, Counter

from .geom import shapes
from .classify import marks
from . import config
from .classify.layers import CATEGORY_COLUMN, CATEGORY_BEAM, CATEGORY_SLAB_EDGE

_MM = config.MM_PER_FT

# Acceptance limits (mm) -- the subset of config used as the UI's defaults.
DEFAULT_LIMITS = dict((key, config.DEFAULTS[key]) for key in (
    "beam_width_min_mm", "beam_width_max_mm",
    "col_b_min_mm", "col_b_max_mm", "col_h_min_mm", "col_h_max_mm"))

_FRAG_MAX_LINE_MM = 2000.0   # column-layer lines shorter than this are junction bits
_FRAG_GAP_MM = 600.0         # fragments within this gap belong to the same column
#                              (a beam cut across an angled column can leave its two
#                              halves ~450 mm apart; still well under the ~1500 mm
#                              spacing of separate columns, so they do not fuse)
_FRAG_CLOSE_GAP_MM = 900.0   # a LONE outline left open this wide at a junction cut is
#                              still one column (rotated corner columns clip to ~600-800);
#                              recovered rects are deduped so this cannot double a column
_CLOSE_TOL_FT = 1.0e-3       # ~0.3 mm: ring is closed when its ends meet this close


def _ring_closed(points):
    """True if a polyline's first and last vertices coincide (a closed ring).

    Both readers mark closure this way: the DXF reader appends the start point to
    a closed LWPOLYLINE/POLYLINE, and Revit's PolyLine repeats the start for a
    closed loop. A polyline whose ends do NOT meet is an open path -- at a
    beam-column junction that means a partial outline (an L/U/-shaped fragment),
    NOT a column to be auto-closed into a (wrong, undersized) rectangle.
    """
    if len(points) < 4:
        return False
    a, b = points[0], points[-1]
    return abs(a[0] - b[0]) <= _CLOSE_TOL_FT and abs(a[1] - b[1]) <= _CLOSE_TOL_FT


def _inside_rectangles(cx, cy, rectangles):
    """True if (cx, cy) falls within any rectangle's axis-aligned bbox."""
    for rect in rectangles:
        if rect.x_min <= cx <= rect.x_max and rect.y_min <= cy <= rect.y_max:
            return True
    return False


def parse_standard_sizes(text):
    """Parse '300x600, 300x750' -> [(300.0, 600.0), ...] (b<=h). Tolerant of junk."""
    pairs = []
    if not text:
        return pairs
    for token in text.replace(";", ",").split(","):
        token = token.strip().lower().replace("X", "x")
        if "x" not in token:
            continue
        a, _, b = token.partition("x")
        try:
            va, vb = float(a.strip()), float(b.strip())
        except ValueError:
            continue
        pairs.append((min(va, vb), max(va, vb)))
    return pairs


def parse_standard_widths(text):
    """Parse '300, 450, 600' -> [300.0, 450.0, 600.0]. Tolerant of junk."""
    widths = []
    if not text:
        return widths
    for token in text.replace(";", ",").split(","):
        token = token.strip()
        try:
            widths.append(float(token))
        except ValueError:
            continue
    return widths


def _standard_dims_mm(pairs):
    """Flatten standard (b, h) pairs into the set of distinct dimensions."""
    dims = set()
    for b, h in pairs:
        dims.add(b)
        dims.add(h)
    return sorted(dims)


def build_layer_counts(records):
    """{layer_key: {'count': int, 'kinds': {kind: int}}} for the summary table."""
    summary = {}
    for record in records:
        bucket = summary.setdefault(record.layer_key, {"count": 0, "kinds": defaultdict(int)})
        bucket["count"] += 1
        bucket["kinds"][record.kind] += 1
    return summary


def build_category_counts(records):
    """{category: count}, including unmapped, so nothing is silently dropped."""
    counts = defaultdict(int)
    for record in records:
        counts[record.category] += 1
    return dict(counts)


def format_summary(result, mapping):
    """Return a list of plain-text lines describing the read (no markup)."""
    lines = []
    lines.append("Source link : {0}".format(result.source_name))
    lines.append("Curves read : {0}".format(len(result.records)))
    lines.append("")

    lines.append("By layer -> category:")
    layer_counts = build_layer_counts(result.records)
    for layer in sorted(layer_counts.keys()):
        info = layer_counts[layer]
        category = mapping.get(layer, "unmapped")
        kinds = ", ".join("{0}x {1}".format(n, k)
                          for k, n in sorted(info["kinds"].items()))
        lines.append("  {0:<24} -> {1:<10} ({2} curves: {3})".format(
            layer, category, info["count"], kinds))

    lines.append("")
    lines.append("By category:")
    for category, count in sorted(build_category_counts(result.records).items()):
        lines.append("  {0:<12} {1}".format(category, count))

    return lines


# Fragmented lift/stair-core detection + recovery.
# A core drawn as a proper closed polyline becomes a column and leaves NO open path;
# one drawn as disconnected segments comes through (in Revit the inner wall faces fuse
# into a single open polyline) as a big UNCLOSED ring that never places. The gate below
# separates that ring (~19 m^2, 4700x4400) from the thin edge strips a working plan
# leaves behind (<= ~3 m^2, one bbox side ~300 mm) with a wide margin.
_CORE_MIN_BBOX_MM = 1800.0     # smaller side of the outline's bbox; thin strips fall out
_CORE_MIN_AREA_MM2 = 3.0e6     # enclosed area (>= 3 m^2) of a real shaft outline
_CORE_WALL_MAX_MM = 1200.0     # pair faces up to this far apart (a member's depth); below
#                                the ~1500 mm stair opening, so a real opening stays open
_CORE_WALL_OVERLAP_MM = 500.0  # paired faces must share at least this much run
_CORE_WALL_DOOR_MM = 700.0     # merge collinear faces split by a gap this small (a door):
#                                a doorway punched through a wall must not split the member
_CORE_WALL_PAD_MM = 1200.0     # grow the core bbox by one depth so a deep member's outer
#                                face (one column-depth beyond the inner ring) is included


def _find_core_outlines(unplaced_raw):
    """Locate large UNCLOSED outlines (likely fragmented lift/stair cores) among the
    unplaced column-layer geometry. Returns a list of
    {"center_mm": [x, y], "area_m2": a, "bbox_mm": [x0, y0, x1, y1]} -- one per open-path
    polyline whose enclosed area >= _CORE_MIN_AREA_MM2 and whose smaller bbox side
    >= _CORE_MIN_BBOX_MM (a real shaft vs. the thin strips a working plan leaves behind).
    """
    cores = []
    for geom in unplaced_raw:
        if geom.get("kind") != "polyline" or geom.get("status") != "open_path":
            continue
        pts = geom.get("pts") or []
        if len(pts) < 4:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if min(max(xs) - min(xs), max(ys) - min(ys)) < _CORE_MIN_BBOX_MM:
            continue
        area = 0.0   # shoelace, auto-closing the open ring back to its first point
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            area += x0 * y1 - x1 * y0
        area = abs(area) / 2.0
        if area < _CORE_MIN_AREA_MM2:
            continue
        cores.append({
            "center_mm": [int(round(sum(xs) / len(xs))), int(round(sum(ys) / len(ys)))],
            "area_m2": round(area / 1e6, 1),
            "bbox_mm": [min(xs), min(ys), max(xs), max(ys)],
        })
    return cores


def detect_fragmented_cores(unplaced_raw, placed_rects=None):
    """Flag a likely fragmented lift/stair core: a large UNCLOSED outline left on the
    column layer that never placed -- redraw it as a closed polyline so it places.

    Detection only -- returns advisory warnings, never geometry. `unplaced_raw`: the
    column-layer geometry that produced no rectangle ({kind, status, pts} in mm, exactly
    the JSON's dropped_raw). `placed_rects`: already-placed columns (feet); an outline
    whose centroid sits on one is part of a column that DID place and is skipped. Returns
    a list of {"center_mm": [x, y], "area_m2": a}.
    """
    placed_rects = placed_rects or []
    warnings = []
    for core in _find_core_outlines(unplaced_raw):
        cx, cy = core["center_mm"]
        if _inside_rectangles(cx / _MM, cy / _MM, placed_rects):
            continue   # outline sits on a column that actually placed
        warnings.append({"center_mm": core["center_mm"], "area_m2": core["area_m2"]})
    return warnings


def build_column_sections(records, limits=None, standards=None, texts=None,
                          tolerances=None):
    """Decompose every column-category polyline into rectangular sections, and
    derive spine rectangles from bare column-layer lines.

    When `texts` (sized DXF marks, internal feet) are given, each rectangle is
    refined to the size of the nearest mark (e.g. "C1 400x400"), overriding the
    geometry-derived dimensions before limit/standard filtering. `tolerances`
    (config.DEFAULTS overrides) tunes circle diameter range, snap and mark radius.

    Line-drawn members (e.g. a lift spine) carry no width on their own; where two
    or more legs meet such a line, a spine rectangle is derived (width = measured
    gap to the legs) and added as a placeable 'line_spine' entry. Lines that do
    not resolve to a spine are reported as leftover line_members.
    """
    tol = config.merged(tolerances)
    status_counts = defaultdict(int)
    total_rectangles = 0
    entries = []
    leg_rectangles = []
    line_points = []
    line_members = []
    arc_records = []
    polyline_records = []
    open_paths = []     # unclosed column-layer polylines (a core's inner ring lives here)
    unplaced_raw = []   # debug: column-layer geometry that produced no rectangle
    fragments = []      # small leftover pieces to reassemble into clipped columns
    for record in records:
        if record.category != CATEGORY_COLUMN:
            continue
        if record.kind == "line":
            line_points.append(record.points)
            length_mm = _polyline_length_ft(record.points) * 304.8
            line_members.append({"layer": record.layer, "length_mm": length_mm})
            unplaced_raw.append({"kind": "line", "layer": record.layer,
                                 "pts": _pts_mm(record.points)})
            if length_mm < _FRAG_MAX_LINE_MM:   # short = junction fragment, not a spine
                fragments.append(record.points)
        elif record.kind == "arc":
            arc_records.append(record)
        else:
            polyline_records.append(record)

    # Circles first, so polyline fragments of a circle (arcs captured as polylines)
    # can be discarded instead of becoming spurious little rectangles.
    circles = shapes.build_circular_columns(
        arc_records,
        min_dia_ft=config.mm_to_ft(tol["circle_min_dia_mm"]),
        max_dia_ft=config.mm_to_ft(tol["circle_max_dia_mm"]))

    def _inside_a_circle(rect):
        cx, cy, _z = rect.center
        for circle in circles:
            radius = circle.diameter / 2.0
            if (cx - circle.cx) ** 2 + (cy - circle.cy) ** 2 <= radius * radius:
                return True
        return False

    for record in polyline_records:
        # An OPEN polyline on the column layer is a junction fragment (a partial
        # L/U/-outline left when beams sliced the column), not a closed column.
        # Auto-closing it would forge a wrong, undersized sliver AND steal its
        # segments from recovery; route it to the fragment pool to be reassembled.
        if not _ring_closed(record.points):
            unplaced_raw.append({"kind": record.kind, "layer": record.layer,
                                 "status": "open_path",
                                 "pts": _pts_mm(record.points)})
            open_paths.append(record.points)
            fragments.append(record.points)
            status_counts["open_fragment"] += 1
            continue
        result = shapes.parse_column_polyline(record.points)
        kept = [rect for rect in result["rectangles"] if not _inside_a_circle(rect)]
        dropped = len(result["rectangles"]) - len(kept)
        if dropped:
            status_counts["circle_artifact"] += dropped
        if not kept:
            if result["status"] != "rectangle":   # genuinely lost, not a circle bit
                unplaced_raw.append({"kind": record.kind, "layer": record.layer,
                                     "status": result["status"],
                                     "pts": _pts_mm(record.points)})
                fragments.append(record.points)
            continue   # whole shape was a circle-drawing artifact
        status_counts[result["status"]] += 1
        total_rectangles += len(kept)
        leg_rectangles.extend(kept)
        entries.append({
            "layer": record.layer,
            "status": result["status"],
            "approx": result.get("approx", False),
            "rectangles": [rect.to_dict() for rect in kept],
        })

    spines = shapes.build_line_spines(line_points, leg_rectangles)
    if spines:
        status_counts["line_spine"] += len(spines)
        total_rectangles += len(spines)
        entries.append({
            "layer": "(line spine)",
            "status": "line_spine",
            "approx": False,
            "rectangles": [spine.to_dict() for spine in spines],
        })
    status_counts["line_member"] += len(line_members)
    status_counts["circle"] += len(circles)

    # Recover columns from fused/unclosed AXIS-ALIGNED wall outlines first: a long
    # wall drawn as one comb with its perpendicular legs (e.g. a 12300 base + four
    # 300x3300 teeth) never closes into a ring, so each piece would otherwise blob
    # into one oversized oriented rect. Assemble the pieces into closed rectilinear
    # rings and decompose them into their real columns. Feed both the open-path
    # fragments and the bare column lines (the long wall edges live in line_points).
    recl_paths = list(fragments) + list(line_points)
    recl_z = next((p[0][2] for p in recl_paths if p and len(p[0]) > 2), 0.0)
    strip_rects_raw, recl_consumed = shapes.recover_rectilinear_columns(
        recl_paths, z=recl_z)
    strip_rects = []
    for rect in strip_rects_raw:
        cx, cy, _cz = rect.center
        if _inside_a_circle(rect) or _inside_rectangles(cx, cy, leg_rectangles):
            continue
        strip_rects.append(rect)
    if strip_rects:
        status_counts["recovered_strip"] += len(strip_rects)
        total_rectangles += len(strip_rects)
        leg_rectangles.extend(strip_rects)
        entries.append({
            "layer": "(recovered)",
            "status": "recovered_strip",
            "approx": True,
            "rectangles": [rect.to_dict() for rect in strip_rects],
        })
    # Drop fragments consumed by the rectilinear assembly so the oriented pass below
    # cannot re-cluster them into a duplicate blob (fragment ids index recl_paths,
    # whose first len(fragments) entries are the fragments themselves).
    fragments = [frag for i, frag in enumerate(fragments) if i not in recl_consumed]

    # Recover columns whose Revit outline was clipped into disconnected fragments
    # at a junction (e.g. angled F9): cluster the leftover pieces and fit an
    # oriented rectangle. Skip any that land inside an already-placed column.
    recovered = shapes.recover_oriented_columns(
        fragments, gap_ft=config.mm_to_ft(_FRAG_GAP_MM),
        close_gap_ft=config.mm_to_ft(_FRAG_CLOSE_GAP_MM))
    recovered_rects = []
    for rect in recovered:
        cx, cy, _cz = rect.center
        if (_inside_a_circle(rect) or _inside_rectangles(cx, cy, leg_rectangles)
                or _inside_rectangles(cx, cy, recovered_rects)):
            continue   # already a placed column, or a sibling fragment of one just kept
        recovered_rects.append(rect)
    if recovered_rects:
        status_counts["recovered_rect"] += len(recovered_rects)
        total_rectangles += len(recovered_rects)
        leg_rectangles.extend(recovered_rects)
        entries.append({
            "layer": "(recovered)",
            "status": "recovered_rect",
            "approx": True,
            "rectangles": [rect.to_dict() for rect in recovered_rects],
        })

    # Recover a FRAGMENTED lift/stair core: its walls survive only as loose, never-closed
    # faces, so within each DETECTED core region pair opposing faces into thin wall rects
    # (openings have no opposing face -> no wall, so only solid walls place). Gated to the
    # detected cores, so a working plan -- which has no such region -- is never touched.
    cores = _find_core_outlines(unplaced_raw)
    core_paths = open_paths + line_points
    pad_ft = config.mm_to_ft(_CORE_WALL_PAD_MM)
    for core in cores:
        x0, y0, x1, y1 = (v / _MM for v in core["bbox_mm"])
        walls = shapes.recover_core_walls(
            core_paths, (x0 - pad_ft, y0 - pad_ft, x1 + pad_ft, y1 + pad_ft),
            config.mm_to_ft(tol["pair_min_width_mm"]),
            config.mm_to_ft(_CORE_WALL_MAX_MM),
            config.mm_to_ft(_CORE_WALL_OVERLAP_MM),
            bridge_ft=config.mm_to_ft(_CORE_WALL_DOOR_MM), z=recl_z)
        kept = []
        for rect in walls:
            cx, cy, _cz = rect.center
            if _inside_a_circle(rect) or _inside_rectangles(cx, cy, leg_rectangles):
                continue
            kept.append(rect)
        core["recovered_walls"] = len(kept)
        if kept:
            status_counts["recovered_core_wall"] += len(kept)
            total_rectangles += len(kept)
            leg_rectangles.extend(kept)
            entries.append({
                "layer": "(recovered core)",
                "status": "recovered_core_wall",
                "approx": True,
                "rectangles": [rect.to_dict() for rect in kept],
            })

    refined = _apply_column_marks(entries, texts,
                                  config.mm_to_ft(tol["mark_radius_mm"]))
    if refined:
        status_counts["text_sized"] += refined

    dropped = _filter_column_entries(entries, limits or DEFAULT_LIMITS,
                                     standards or {}, tol["snap_tol_mm"])
    if dropped:
        status_counts["out_of_range"] += dropped
    total_rectangles = sum(len(e["rectangles"]) for e in entries)
    entries = [e for e in entries if e["rectangles"]]

    return {
        "status_counts": dict(status_counts),
        "total_rectangles": total_rectangles,
        "entries": entries,
        "warnings": [{"center_mm": c["center_mm"], "area_m2": c["area_m2"],
                      "recovered_walls": c.get("recovered_walls", 0)} for c in cores],
        "line_members": line_members,
        "line_spines": [spine.to_dict() for spine in spines],
        "circles": [circle.to_dict() for circle in circles],
        "dropped_raw": unplaced_raw,
    }


def _pts_mm(points):
    """[(x,y,z) feet ...] -> [[x_mm, y_mm], ...] integer pairs, for debug dumps."""
    return [[int(round(p[0] * _MM)), int(round(p[1] * _MM))] for p in points]


_TEXT_SIZE_OK_MM = 80.0   # a single column already this close to its label is left as-is
_CLIP_TOL_MM = 20.0       # ...unless geometry is shorter than the label by more than this
#                           (a real clip), in which case it is resized up to the label
_SPLIT_CENTRE_SLACK_MM = 80.0      # split fragments' centres lie within (long side + this)
_SPLIT_NO_SIZE_MAX_CENTRE_MM = 800.0   # no label size: only fuse pieces this close

# --- label-guided core-wall placement --------------------------------------
_CORE_LABEL_MARGIN_MM = 1100.0  # a wall's label may sit this far outside the blob
#                                 (bottom-row columns carry their text well below them)
_CORE_DIM_TOL_MM = 80.0         # a cell-rectangle must match the label size this closely
_CORE_EDGE_EPS_MM = 2.0         # merge cell grid edges closer than this (float noise)


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


def correct_columns_with_text(sections, column_texts, radius_ft, schedule=None,
                              grid_x=None, grid_y=None, grid_snap_ft=None):
    """Use column labels (one per real column) to fix clipped/split geometry and
    to name columns.

    A label supplies a SIZE (inline "600x750"), a MARK ("C1"), or both. The size
    used for a column is resolved: inline label size > schedule[mark] > geometry.
    For each label, gather the placed column rectangles within radius_ft:
      * one rectangle already the right size -> left as-is (mark stamped);
      * one CLIPPED rectangle with a known size -> resized + snapped to the grid;
      * two split pieces -> merged into one column (sized to the label/schedule, or
        their combined footprint when no size is known) + snapped to the grid;
      * a single mark-only piece (no size anywhere) -> kept as geometry, mark only.
    Clusters of >2 pieces (multi-leg lift/stair cores) are left as separate legs.
    Returns the count of columns touched (resized/merged/named).
    """
    schedule = schedule or {}
    entries = sections.get("entries", [])
    rects = [rect for entry in entries for rect in entry["rectangles"]]
    labels = [t for t in (column_texts or []) if t.point_internal and
              ((t.b_mm is not None and t.h_mm is not None) or t.mark)]
    used = set()
    outputs = []
    r2 = radius_ft * radius_ft

    # Each rectangle belongs to its NEAREST label. A long member's label reaches far
    # (radius is fixed at mark_radius_mm), so without this a 300x3300 wall's label would
    # swallow a distinct 600x900 column 465 mm away as a "split pair" -- its merge window
    # is the labelled long side (3300). Ownership lets a closer label keep its own column.
    owner = {}
    for rect in rects:
        rcx, rcy = rect["center"][0], rect["center"][1]
        best, best_d2 = None, r2
        for text in labels:
            d2 = ((text.point_internal[0] - rcx) ** 2
                  + (text.point_internal[1] - rcy) ** 2)
            if d2 < best_d2:
                best, best_d2 = text, d2
        owner[id(rect)] = best

    for text in labels:
        tx, ty = text.point_internal[0], text.point_internal[1]
        near = [rect for rect in rects if id(rect) not in used
                and owner.get(id(rect)) is text
                and (rect["center"][0] - tx) ** 2 + (rect["center"][1] - ty) ** 2 <= r2]
        if not near or len(near) > 2:
            continue   # none, or a multi-leg lift/stair core: leave the geometry
        size = _label_size(text, schedule)   # (small, big) mm, or None

        if len(near) == 2 and not _is_split_pair(near, size):
            # One label per column, but an offset label on a tight grid bay (e.g.
            # grids ~1500mm apart) can reach a NEIGHBOURING column too. These are
            # two complete, separate columns -- bind this label to its OWN
            # (nearest) column and leave the other for its own label, instead of
            # fusing them into one column mid-bay with its orientation lost.
            near = [min(near, key=lambda r:
                        (r["center"][0] - tx) ** 2 + (r["center"][1] - ty) ** 2)]

        if size is None and len(near) == 1:
            # Mark only, single clean piece: name it, keep geometry size+position.
            out = _copy_rect(near[0])
            out["mark"] = text.mark
            used.add(id(near[0]))
            outputs.append(out)
            continue
        if size is not None and len(near) == 1:
            if _fills_size(near[0], size) and not _is_clipped(near[0], size):
                out = _copy_rect(near[0])      # already right size: just name it
                out["mark"] = text.mark
                used.add(id(near[0]))
                outputs.append(out)
                continue
            # else fall through: a clipped column (geometry shorter than its known
            # size, e.g. a 270 mm sliver of a scheduled 300 mm column) is resized up
            # to the authoritative label size below, keeping its orientation+centre.
        if size is None:                       # split pieces, no size: use footprint
            size = _union_size(near)

        for rect in near:
            used.add(id(rect))
        rect = _merge_to_label(near, size[0], size[1], text.mark)
        if grid_snap_ft:                       # we moved/resized -> snap onto the grid
            rect["center"][0] = _snap(rect["center"][0], grid_x, grid_snap_ft)
            rect["center"][1] = _snap(rect["center"][1], grid_y, grid_snap_ft)
        # A small column cast hard against a bigger one (C17 beside a 600x900) can
        # survive Revit's import only as a mis-centred sliver. Resizing that sliver to
        # the label size lands the column's CENTRE inside its larger neighbour -- two
        # stacked columns. Don't claim it here: drop the absorbed sliver and leave the
        # mark unplaced so the abutment pass (recover_unplaced_labeled_columns) places
        # it edge-to-edge, exactly as it already does for the same column when the DXF
        # is more fragmented. Only defer a mark the abutment pass can re-place (it needs
        # a schedule size); otherwise keep the placement rather than drop the column.
        if (_center_inside_larger(rect, rects, near) and
                text.mark and text.mark in schedule):
            continue
        outputs.append(rect)
    if not outputs:
        return 0
    leftover = [rect for rect in rects if id(rect) not in used]
    sections["entries"] = [{"layer": "(text-corrected)", "status": "text_corrected",
                            "approx": True, "rectangles": outputs + leftover}]
    counts = sections.setdefault("status_counts", {})
    counts["text_corrected"] = counts.get("text_corrected", 0) + len(outputs)
    sections["total_rectangles"] = len(outputs) + len(leftover)
    return len(outputs)


def apply_circle_marks(sections, column_texts, radius_ft):
    """Stamp the nearest column label's MARK onto each circular column.

    correct_columns_with_text only refines rectangles, so circular columns are
    named here: each circle adopts the mark of the nearest labelled text within
    radius_ft (its size already comes from geometry). Best-effort -- returns the
    count named.
    """
    circles = sections.get("circles") or []
    marks = [t for t in (column_texts or []) if t.mark and t.point_internal]
    if not circles or not marks:
        return 0
    r2 = radius_ft * radius_ft
    count = 0
    for circle in circles:
        cx, cy = circle["center"][0], circle["center"][1]
        best, best_d2 = None, r2
        for text in marks:
            d2 = ((text.point_internal[0] - cx) ** 2
                  + (text.point_internal[1] - cy) ** 2)
            if d2 <= best_d2:
                best, best_d2 = text, d2
        if best is not None:
            circle["mark"] = best.mark
            count += 1
    return count


# A small column cast hard against a bigger one fragments so badly that recovery
# folds its pieces into the neighbour; these tune recovering it from its label.
_ABSORB_RADIUS_MM = 2000.0   # the orphaned label and its leftover pieces lie within this
_ABSORB_PAD_MM = 60.0        # a fragment point this far inside a placed column is "its"
_ABSORB_MIN_PTS = 3          # need at least this much leftover geometry as evidence


def _bbox_half(rect):
    """Axis-aligned half-extents (hx, hy) in feet of a possibly-rotated column rect."""
    theta = math.radians(rect.get("long_axis_deg", 90.0))
    long_ft, short_ft = rect["height_ft"], rect["width_ft"]
    hx = (abs(math.cos(theta)) * long_ft + abs(math.sin(theta)) * short_ft) / 2.0
    hy = (abs(math.sin(theta)) * long_ft + abs(math.cos(theta)) * short_ft) / 2.0
    return hx, hy


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


def _is_split_pair(rects, size):
    """True when two near rectangles are two fragments of ONE clipped column
    (safe to merge), False when they are two complete, separate columns that a
    single offset label happened to reach across a tight grid bay.

    A genuine clip splits one column, so the fragments' centres lie within the
    column's own long dimension; two distinct columns sit a grid bay apart. And
    if BOTH near pieces already fill the labelled size, they cannot be fragments.
    """
    a, b = rects
    centre_mm = math.hypot(a["center"][0] - b["center"][0],
                           a["center"][1] - b["center"][1]) * _MM
    if size is not None:
        if _fills_size(a, size) and _fills_size(b, size):
            return False
        return centre_mm <= size[1] + _SPLIT_CENTRE_SLACK_MM
    return centre_mm <= _SPLIT_NO_SIZE_MAX_CENTRE_MM


def _fills_size(rect, size):
    """True when a rectangle already matches the labelled (small, big) mm size."""
    small_g = min(rect["width_mm"], rect["height_mm"])
    big_g = max(rect["width_mm"], rect["height_mm"])
    return (abs(small_g - size[0]) <= _TEXT_SIZE_OK_MM and
            abs(big_g - size[1]) <= _TEXT_SIZE_OK_MM)


def _is_clipped(rect, size):
    """True when geometry is CLIPPED below the labelled size on either dimension.

    A label's size is authoritative, so a clipped column -- e.g. a 270 mm sliver of
    a scheduled 300 mm column, a shortfall that still lands inside the _fills_size
    'close enough' band -- must be resized UP to the label instead of kept as drawn.
    Only a real shortfall past _CLIP_TOL_MM counts, so geometry noise on an already
    correct column does not trigger a needless resize.
    """
    small_g = min(rect["width_mm"], rect["height_mm"])
    big_g = max(rect["width_mm"], rect["height_mm"])
    return (small_g < size[0] - _CLIP_TOL_MM or big_g < size[1] - _CLIP_TOL_MM)


def _label_size(text, schedule):
    """(small, big) mm for a label: inline size first, else schedule[mark], else None."""
    if text.b_mm is not None and text.h_mm is not None:
        return (min(text.b_mm, text.h_mm), max(text.b_mm, text.h_mm))
    if text.mark and text.mark in schedule:
        b, h = schedule[text.mark]
        return (min(b, h), max(b, h))
    return None


def _union_size(rects):
    """(small, big) mm of the axis-aligned union of the rectangles' footprints."""
    xs, ys = [], []
    for r in rects:
        cx, cy = r["center"][0] * _MM, r["center"][1] * _MM
        xs += [cx - r["width_mm"] / 2.0, cx + r["width_mm"] / 2.0]
        ys += [cy - r["height_mm"] / 2.0, cy + r["height_mm"] / 2.0]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    return (min(w, h), max(w, h))


def _copy_rect(rect):
    out = dict(rect)
    out["center"] = list(rect["center"])
    return out


def _center_inside_larger(rect, rects, exclude):
    """True when rect's centre sits INSIDE a strictly larger placed rectangle.

    A real column centre never lies within another column; when it does, rect is a
    sliver of a column absorbed into a bigger neighbour rather than a column of its
    own. `exclude` are the pieces rect was built from (its own geometry), skipped by
    identity so a split-pair never reads as inside one of its own halves.
    """
    cx, cy = rect["center"][0], rect["center"][1]
    area = rect["width_mm"] * rect["height_mm"]
    skip = set(id(r) for r in exclude)
    for other in rects:
        if id(other) in skip or id(other) == id(rect):
            continue
        if other["width_mm"] * other["height_mm"] <= area:
            continue                           # only a LARGER neighbour absorbs
        ohx, ohy = _bbox_half(other)
        if (abs(cx - other["center"][0]) < ohx and
                abs(cy - other["center"][1]) < ohy):
            return True
    return False


def _snap(value, positions, tol_ft):
    """Snap value to the nearest grid position within tol_ft, else return value."""
    if not positions:
        return value
    nearest = min(positions, key=lambda p: abs(p - value))
    return nearest if abs(nearest - value) <= tol_ft else value


def _merge_to_label(rects, small_mm, big_mm, mark):
    """One column rectangle at the merged centre, sized small x big (short x long)."""
    mcx = sum(r["center"][0] for r in rects) / len(rects)
    mcy = sum(r["center"][1] for r in rects) / len(rects)
    mz = rects[0]["center"][2]
    if len(rects) == 1 and rects[0].get("long_axis_deg") is not None:
        deg = rects[0]["long_axis_deg"]     # keep a clipped oriented column's angle
    else:
        xs = []
        ys = []
        for r in rects:
            hw = (r["width_mm"] / _MM) / 2.0
            hh = (r["height_mm"] / _MM) / 2.0
            xs += [r["center"][0] - hw, r["center"][0] + hw]
            ys += [r["center"][1] - hh, r["center"][1] + hh]
        deg = 90.0 if (max(ys) - min(ys)) >= (max(xs) - min(xs)) else 0.0
    return {"center": [mcx, mcy, mz],
            "width_mm": small_mm, "height_mm": big_mm,
            "width_ft": small_mm / _MM, "height_ft": big_mm / _MM,
            "long_axis_deg": deg, "mark": mark}


def _filter_column_entries(entries, limits, standards, snap_tol_mm):
    """Snap each rectangle's b/h to standard sizes and drop out-of-range ones.

    Snapping preserves which stored dimension (width/height) is the short side, so
    the placement rotation stays correct. Returns the number dropped.
    """
    dims = [d / _MM for d in _standard_dims_mm(standards.get("column", []))]
    tol = snap_tol_mm / _MM
    b_min, b_max = limits["col_b_min_mm"], limits["col_b_max_mm"]
    h_min, h_max = limits["col_h_min_mm"], limits["col_h_max_mm"]
    dropped = 0
    for entry in entries:
        kept = []
        for rect in entry["rectangles"]:
            w_mm, h_mm = rect["width_mm"], rect["height_mm"]
            small, big = min(w_mm, h_mm), max(w_mm, h_mm)
            small = shapes.snap_to_standard(small / _MM, dims, tol) * _MM
            big = shapes.snap_to_standard(big / _MM, dims, tol) * _MM
            if not (b_min <= small <= b_max and h_min <= big <= h_max):
                dropped += 1
                continue
            if w_mm <= h_mm:
                rect["width_mm"], rect["height_mm"] = small, big
            else:
                rect["width_mm"], rect["height_mm"] = big, small
            kept.append(rect)
        entry["rectangles"] = kept
    return dropped


def _polyline_length_ft(points):
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
    return total


def format_column_sections(sections):
    """Plain-text lines summarising the column decomposition (no markup)."""
    if not sections["entries"] and not sections.get("circles"):
        return []

    lines = ["Column sections (rectangular decomposition):"]
    for status, count in sorted(sections["status_counts"].items()):
        lines.append("  {0:<16} {1}".format(status, count))
    lines.append("  {0:<16} {1}".format("-> rectangles", sections["total_rectangles"]))

    warnings = sections.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("!! FRAGMENTED lift/stair core(s) detected (unclosed outline) -- "
                     "VERIFY; redraw as a closed polyline if incomplete:")
        for warn in warnings:
            cx, cy = warn["center_mm"]
            recovered = warn.get("recovered_walls", 0)
            outcome = ("recovered {0} wall(s)".format(recovered) if recovered
                       else "not placed")
            lines.append("   near ({0}, {1}) mm: ~{2:.1f} m2 outline -> {3}".format(
                cx, cy, warn["area_m2"], outcome))

    composites = [e for e in sections["entries"] if e["status"] == "composite"]
    if composites:
        lines.append("")
        lines.append("Composite lift-core shapes split into legs:")
        for index, entry in enumerate(composites, start=1):
            sizes = ", ".join("{0:.0f}x{1:.0f}mm".format(r["width_mm"], r["height_mm"])
                              for r in entry["rectangles"])
            lines.append("  #{0} [{1}] -> {2} rects: {3}".format(
                index, entry["layer"], len(entry["rectangles"]), sizes))

    non_rect = [e for e in sections["entries"] if e["status"] == "non_rectilinear"]
    if non_rect:
        lines.append("")
        lines.append("Non-rectilinear columns (bounding-box approximated, review): {0}".format(
            len(non_rect)))

    spines = sections.get("line_spines", [])
    if spines:
        lines.append("")
        lines.append("Line-spine columns derived from bare lines: {0}".format(len(spines)))
        for spine in spines:
            lines.append("  {0:.0f} x {1:.0f} mm".format(spine["width_mm"], spine["height_mm"]))

    line_members = sections.get("line_members", [])
    if line_members:
        lines.append("")
        lines.append("Bare lines on column layer (some may have formed spines above): {0}".format(
            len(line_members)))
        for member in sorted(line_members, key=lambda m: -m["length_mm"]):
            lines.append("  [{0}] length {1:.0f} mm".format(
                member["layer"], member["length_mm"]))

    circles = sections.get("circles", [])
    if circles:
        lines.append("")
        lines.append("Circular columns detected: {0}".format(len(circles)))
        for circle in circles:
            lines.append("  dia {0:.0f} mm".format(circle["diameter_mm"]))

    return lines


# A curved beam's two edges are each drawn as a chain of many short arc fragments; the
# tiny fragments' circle fits are noisy, so cluster them loosely on centre but tightly on
# radius (so a beam's inner and outer edges -- one width apart -- never merge).
_ARC_EDGE_CENTER_TOL_MM = 250.0   # arc fragments share an edge if their centres agree this far
_ARC_EDGE_RADIUS_TOL_MM = 60.0    # ...and their radii agree this far (< any real beam width)
_EDGE_DUP_TOL_MM = 250.0          # an edge-pair beam this close to a placed beam is a re-trace


_BEAM_END_SNAP_PAD_MM = 250.0   # a beam end this far outside a round/rotated column snaps in


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


def snap_beam_ends_to_columns(beam_segments, sections, circles=None,
                              pad_ft=None):
    """Pull a beam END onto a ROUND or ROTATED column's centre to close the junction gap.

    A beam meeting an axis-aligned column butts cleanly against a flat edge, but a round
    column (tangent contact) or a rotated column (skew edge) leaves an ugly gap. When a
    beam endpoint lands inside such a column (within its radius + a small pad), the end is
    moved to the column centre so the beam runs to the centre. Only ENDPOINTS move, never a
    beam's midspan; axis-aligned columns are left alone. Returns the number of ends snapped.
    """
    if pad_ft is None:
        pad_ft = config.mm_to_ft(_BEAM_END_SNAP_PAD_MM)
    targets = []   # (cx, cy, reach_ft)
    for circle in (circles or []):
        cx, cy, _cz = circle["center"]
        targets.append((cx, cy, circle["diameter_ft"] / 2.0 + pad_ft))
    for entry in sections.get("entries", []):
        for rect in entry["rectangles"]:
            deg = rect.get("long_axis_deg")
            if deg is None:
                continue
            skew = deg % 90.0
            if min(skew, 90.0 - skew) <= 1.0:
                continue                       # axis-aligned: clean butt joint, no gap
            cx, cy, _cz = rect["center"]
            w = rect["width_mm"] / _MM
            h = rect["height_mm"] / _MM
            targets.append((cx, cy, 0.5 * (w * w + h * h) ** 0.5 + pad_ft))
    if not targets:
        return 0
    snapped = 0
    for seg in beam_segments.get("segments", []):
        for end in ("start", "end"):
            ex, ey = seg[end][0], seg[end][1]
            for cx, cy, reach in targets:
                if (ex - cx) ** 2 + (ey - cy) ** 2 <= reach * reach:
                    seg[end][0], seg[end][1] = cx, cy
                    snapped += 1
                    break
    return snapped


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
        if len(ring) == 4:
            result = shapes.beam_centerline_from_quad(ring)
            if result:
                start, end, width = result
                if width > quad_width_max_ft:
                    # A "quad" wider than any beam is NOT one member's outline. It is an OPEN
                    # U-polyline chaining the facing edges of TWO grid beams (plus a leg of a
                    # cross beam) that simplify_ring closed across the void between them --
                    # Test15 placed phantom beams on the MIDLINE between grids J/K and S/T
                    # this way. Its legs are real beam edges: explode them into the pair pool
                    # so the actual on-grid beams are rebuilt from their edge pairs.
                    pts = record.points
                    for i in range(len(pts) - 1):
                        bare_lines.append(((pts[i][0], pts[i][1]),
                                           (pts[i + 1][0], pts[i + 1][1]), pts[i][2]))
                    status["quad_too_wide_explode"] += 1
                    continue
                segments.append(_beam_segment(start, end, width, z, record.layer, "rect"))
                status["rect"] += 1
        elif shapes.is_rectilinear(ring):
            for rect in shapes.decompose_to_rectangles(ring):
                start, end, width = shapes.beam_centerline_from_rect(rect)
                segments.append(_beam_segment(start, end, width, z, record.layer, "segment"))
            status["composite"] += 1
        else:
            bbox = shapes.bounding_rectangle(ring, z)
            start, end, width = shapes.beam_centerline_from_rect(bbox)
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


def _apply_column_marks(entries, texts, radius_ft):
    """Refine each column rectangle from the nearest sized DXF mark, in place.

    Adopts the mark's magnitudes but preserves the geometry's orientation (which
    side is short vs long), so placement rotation stays correct. Returns the count
    refined.
    """
    candidates = marks.sized_texts(texts or [])
    if not candidates:
        return 0
    count = 0
    for entry in entries:
        for rect in entry["rectangles"]:
            cx, cy, _cz = rect["center"]
            hit = marks.nearest_sized_text(cx, cy, candidates, radius_ft)
            if hit is None:
                continue
            small_t, big_t = min(hit.b_mm, hit.h_mm), max(hit.b_mm, hit.h_mm)
            if rect["width_mm"] <= rect["height_mm"]:
                rect["width_mm"], rect["height_mm"] = small_t, big_t
            else:
                rect["width_mm"], rect["height_mm"] = big_t, small_t
            rect["mark"] = hit.mark
            count += 1
    return count


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
            cx = (segment["start"][0] + segment["end"][0]) / 2.0
            cy = (segment["start"][1] + segment["end"][1]) / 2.0
            hit = _nearest_sized_label(cx, cy, sized_labels, radius_ft)
            if hit is None:
                continue
            text, small, big = hit
        segment["width_mm"] = small
        segment["depth_mm"] = big
        segment["mark"] = text.mark
        count += 1
    _dedupe_marks(segments, sized_labels)
    return count


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

        def _d2(seg):
            cx = (seg["start"][0] + seg["end"][0]) / 2.0
            cy = (seg["start"][1] + seg["end"][1]) / 2.0
            return (cx - px) ** 2 + (cy - py) ** 2

        group.sort(key=_d2)
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


def format_beam_segments(beams):
    """Plain-text lines summarising beam derivation (no markup)."""
    curved = beams.get("curved_segments", [])
    if not beams["segments"] and not curved and not beams["review"]:
        return []
    lines = ["Beam segments (centerline from outline):"]
    for status, count in sorted(beams["status_counts"].items()):
        lines.append("  {0:<16} {1}".format(status, count))
    lines.append("  {0:<16} {1}".format("-> segments", len(beams["segments"])))
    if curved:
        lines.append("  {0:<16} {1}".format("-> curved beams", len(curved)))
    widths = Counter(int(round(s["width_mm"])) for s in beams["segments"])
    if widths:
        lines.append("")
        lines.append("Beam widths (mm): " + ", ".join(
            "{0}x{1}".format(width, count) for width, count in sorted(widths.items())))
    if beams["review"]:
        lines.append("")
        lines.append("Beams needing review (not placed): {0}".format(len(beams["review"])))
    return lines


def format_console(result, mapping, sections, beams):
    """Short, copy-friendly console summary. Full detail goes into the JSON."""
    categories = build_category_counts(result.records)
    category_text = ", ".join("{0} {1}".format(name, count)
                              for name, count in sorted(categories.items()))
    counts = sections.get("status_counts", {})
    columns_line = ("columns: rect {0}, composite {1}, oriented {2}, spine {3}, "
                    "circular {4}").format(
        counts.get("rectangle", 0), counts.get("composite", 0),
        counts.get("oriented_rect", 0), counts.get("line_spine", 0),
        counts.get("circle", 0))
    extras = []
    if counts.get("circle_artifact"):
        extras.append("{0} circle-artifact".format(counts["circle_artifact"]))
    if counts.get("line_member"):
        extras.append("{0} line-member".format(counts["line_member"]))
    if extras:
        columns_line += "  ({0})".format(", ".join(extras))
    widths = Counter(int(round(s["width_mm"])) for s in beams.get("segments", []))
    width_text = ", ".join("{0}x{1}".format(w, n) for w, n in sorted(widths.items())) or "-"
    beams_line = "beams: {0} segments (w {1}); {2} review".format(
        len(beams.get("segments", [])), width_text, len(beams.get("review", [])))
    return [
        "{0} - {1} curves".format(result.source_name, len(result.records)),
        "by category: {0}".format(category_text),
        columns_line,
        beams_line,
    ]


def _mm(value_ft):
    """Internal feet -> whole mm (positions/sizes are integers for brevity)."""
    return int(round(value_ft * _MM))


def _compact_columns(sections):
    """One compact dict per placed column rectangle: mark, b, h, position, angle."""
    items = []
    for entry in sections.get("entries", []):
        for rect in entry.get("rectangles", []):
            cx, cy, _cz = rect["center"]
            item = {"b": int(round(rect["width_mm"])), "h": int(round(rect["height_mm"])),
                    "x": _mm(cx), "y": _mm(cy)}
            if rect.get("mark"):
                item["mark"] = rect["mark"]
            if rect.get("long_axis_deg") is not None:
                item["deg"] = round(rect["long_axis_deg"], 1)
            items.append(item)
    return items


def _compact_circles(sections):
    out = []
    for circle in sections.get("circles", []):
        cx, cy, _cz = circle["center"]
        out.append({"dia": int(round(circle["diameter_mm"])), "x": _mm(cx), "y": _mm(cy)})
    return out


def _beam_geometry_dump(result):
    """Raw beam- and slab-edge-layer geometry (mm) as the link reader returned it.

    build_beam_segments works off these records, but the rest of the export only carries
    the PLACED beams -- so a beam that was never detected leaves no trace to debug. Dumping
    the input geometry (the exact polylines/lines/arcs on the beam + floor layers) lets the
    detection be replayed and a missed beam diagnosed OFFLINE, without another Revit run.
    """
    out = []
    for record in result.records:
        if record.category not in (CATEGORY_BEAM, CATEGORY_SLAB_EDGE):
            continue
        out.append({
            "cat": "slab" if record.category == CATEGORY_SLAB_EDGE else "beam",
            "kind": record.kind,
            "layer": record.layer,
            "pts": [[_mm(p[0]), _mm(p[1])] for p in record.points],
        })
    return out


def _compact_beams(beams):
    out = []
    for seg in beams.get("segments", []):
        item = {"w": int(round(seg["width_mm"])), "len": int(round(seg["length_mm"])),
                "x1": _mm(seg["start"][0]), "y1": _mm(seg["start"][1]),
                "x2": _mm(seg["end"][0]), "y2": _mm(seg["end"][1])}
        if seg.get("depth_mm") is not None:
            item["d"] = int(round(seg["depth_mm"]))
        if seg.get("mark"):
            item["mark"] = seg["mark"]
        out.append(item)
    return out


def _compact_texts(texts):
    out = []
    for text in texts or []:
        if text.b_mm is None and not getattr(text, "mark", None):
            continue   # neither a size nor a mark: nothing to replay/debug from it
        point = text.point_internal
        out.append({"mark": text.mark, "layer": text.layer,
                    "b": text.b_mm, "h": text.h_mm,
                    "x": _mm(point[0]) if point else None,
                    "y": _mm(point[1]) if point else None})
    return out


def export_json(path, result, mapping, sections=None, beams=None, outcomes=None,
                texts=None, comparison=None):
    """Write a COMPACT run report (mm). No raw per-curve point dump -- just the
    placed elements and the problem-geometry summary, so the file stays small and
    is easy to paste/review. Each element list is one compact object per member.
    """
    sections = sections or {}
    beams = beams or {"segments": [], "review": [], "status_counts": {}}
    comparison = comparison or {}
    outcomes = outcomes or {}
    payload = {
        "source": result.source_name,
        "units": "mm (sizes and positions; positions derived from internal feet)",
        "totals": {"dxf_curves": len(result.records),
                   "by_category": build_category_counts(result.records)},
        "comparison": {
            "revit_curves": comparison.get("revit_curves"),
            "dxf_curves": comparison.get("dxf_curves"),
            "matched": comparison.get("matched"),
            "dxf_only": comparison.get("dxf_only"),
            "revit_only": comparison.get("revit_only"),
            "clipped": len(comparison.get("clipped", [])),
            "transform": comparison.get("transform"),
        },
        "grids": outcomes.get("grids"),
        "columns": {"outcome": outcomes.get("columns"),
                    "status_counts": sections.get("status_counts", {}),
                    "items": _compact_columns(sections),
                    "circles": _compact_circles(sections),
                    "warnings": sections.get("warnings", []),
                    "dropped_raw": sections.get("dropped_raw", [])},
        "beams": {"outcome": outcomes.get("beams"),
                  "status_counts": beams.get("status_counts", {}),
                  "items": _compact_beams(beams),
                  "raw_geometry": _beam_geometry_dump(result)},
        "texts_sized": _compact_texts(texts),
        "review": beams.get("review", []),
    }
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=1)
    return path

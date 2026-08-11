# -*- coding: utf-8 -*-
"""Reporting: a human summary for the pyRevit output window and a JSON export.

The JSON schema is deliberately the intermediate format the future external
CPython 3 + ezdxf validator will consume, so writing it now is not throwaway --
it is the contract between the in-Revit reader and the out-of-Revit checker.
"""

import json
import math
import re
from collections import defaultdict, Counter

from .geom import shapes
try:
    from . import __version__
except ImportError:                      # test loaders stub the parent package
    __version__ = "?"
from .classify import marks
from . import config
from .classify.layers import (CATEGORY_COLUMN, CATEGORY_BEAM,
                              CATEGORY_SLAB_EDGE, CATEGORY_STAIR,
                              CATEGORY_STRUCT_WALL)

_MM = config.MM_PER_FT

# The console summary and the JSON export moved to export.py; they are re-exported
# here so every caller (and every test) keeps the import it has always used.
from .limits import (DEFAULT_LIMITS, parse_standard_sizes,
                     parse_standard_widths, _standard_dims_mm)  # noqa: E402,F401
from .column_geom import (_ring_closed, _inside_rectangles, _bbox_half,
                          _column_footprints, _distinct_ring_corners, _label_size,
                          column_outline_footprints, column_trim_footprints,
                          _OBSTACLE_SHORT_MIN_MM, _OBSTACLE_SHORT_MAX_MM,
                          _OBSTACLE_LONG_MAX_MM)          # noqa: E402,F401
from .columns_recovery import (recover_core_walls_from_labels,
                               recover_unplaced_labeled_columns,
                               recover_outline_columns, recover_face_columns,
                               drop_nested_columns)        # noqa: E402,F401
from .export import (build_layer_counts, build_category_counts, format_summary,
                     format_column_sections, format_beam_segments,
                     format_console, build_export_payload, export_json,
                     export_storeys_json)          # noqa: E402,F401


_FRAG_MAX_LINE_MM = 2000.0   # column-layer lines shorter than this are junction bits
_FRAG_GAP_MM = 600.0         # fragments within this gap belong to the same column
#                              (a beam cut across an angled column can leave its two
#                              halves ~450 mm apart; still well under the ~1500 mm
#                              spacing of separate columns, so they do not fuse)
_FRAG_CLOSE_GAP_MM = 900.0   # a LONE outline left open this wide at a junction cut is
#                              still one column (rotated corner columns clip to ~600-800);
#                              recovered rects are deduped so this cannot double a column












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
        _anchor_growth(rect, near, rects)
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


_ABUT_TOL_FT = 150.0 / _MM     # a neighbour this close to an end is touching it


def _anchor_growth(rect, near, all_rects):
    """Grow a resized column back over the piece that was CARVED off it.

    A wall crossing another wall is decomposed into pieces, so the drawn piece
    stops at the crossing member's face. Applying the schedule length about the
    PIECE's centre then pushes the wall past its free end -- StaircasePlan-Test2's
    SW10 grew 400mm longer and its centre rose 200mm, off the drawing.

    When the new length exceeds what was drawn and exactly ONE end abuts another
    rectangle, that end is where the carve happened: the FREE end is pinned and
    the column grows inward, back over the piece it lost.
    """
    if not near:
        return
    along_y = (rect.get("long_axis_deg") or 0.0) > 45.0
    axis = 1 if along_y else 0
    cross = 0 if along_y else 1

    def extent(r, index):
        """(lo, hi) of a rect along x (index 0) or y (index 1).

        TWO conventions live in `sections` and they disagree about what
        width_mm/height_mm mean. A plain axis-aligned rectangle (what
        decompose_to_rectangles returns for a rectilinear ring) stores them as
        its X and Y sizes and carries NO long_axis_deg. An ORIENTED rect stores
        them as SHORT and LONG, with long_axis_deg saying which way the long
        side points. Reading the first as if it were the second is what left
        SW10 200mm high: its 7450mm leg measured as the 400mm wall thickness,
        so the growth looked symmetric and no end was pinned.
        """
        deg = r.get("long_axis_deg")
        if deg is None:
            side = r["width_mm"] if index == 0 else r["height_mm"]
        else:
            long_mm = max(r["width_mm"], r["height_mm"])
            short_mm = min(r["width_mm"], r["height_mm"])
            side = long_mm if (index == 1) == (deg > 45.0) else short_mm
        half = (side / _MM) / 2.0
        return (r["center"][index] - half, r["center"][index] + half)

    lo = min(extent(r, axis)[0] for r in near)
    hi = max(extent(r, axis)[1] for r in near)
    new_half = (max(rect["width_mm"], rect["height_mm"]) / _MM) / 2.0
    if 2.0 * new_half <= (hi - lo) + _ABUT_TOL_FT:
        return                              # not growing: nothing to re-anchor

    claimed = set(id(r) for r in near)
    c_lo, c_hi = extent(rect, cross)
    thickness = c_hi - c_lo
    touches_lo = touches_hi = False
    crosses_lo = crosses_hi = False
    for other in all_rects:
        if id(other) in claimed:
            continue
        o_lo, o_hi = extent(other, axis)
        ox_lo, ox_hi = extent(other, cross)
        if ox_hi < c_lo - _ABUT_TOL_FT or ox_lo > c_hi + _ABUT_TOL_FT:
            continue                        # not alongside this column
        # A member that runs ACROSS this wall is what carved it; one that merely
        # butts its end (a column stacked on top) did not. Test2's SW10 has SW9
        # crossing below AND a 900x900 column above, so "exactly one end abuts"
        # was never true and the wall kept its carved centre.
        crossing = (ox_lo < c_lo - thickness or ox_hi > c_hi + thickness)
        if abs(o_hi - lo) <= _ABUT_TOL_FT or (o_lo <= lo <= o_hi):
            touches_lo = True
            crosses_lo = crosses_lo or crossing
        if abs(o_lo - hi) <= _ABUT_TOL_FT or (o_lo <= hi <= o_hi):
            touches_hi = True
            crosses_hi = crosses_hi or crossing
    if crosses_lo != crosses_hi:
        # grow back over the CROSSING member, pinning the other end
        rect["center"][axis] = (hi - new_half) if crosses_lo else (lo + new_half)
        return
    if touches_lo == touches_hi:
        return                              # both ends free (or both blocked)
    rect["center"][axis] = (hi - new_half) if touches_lo else (lo + new_half)


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


_ARC_EDGE_CENTER_TOL_MM = 250.0   # arc fragments share an edge if their centres agree this far
_ARC_EDGE_RADIUS_TOL_MM = 60.0    # ...and their radii agree this far (< any real beam width)
_EDGE_DUP_TOL_MM = 250.0          # an edge-pair beam this close to a placed beam is a re-trace


_BEAM_END_SNAP_PAD_MM = 250.0   # a beam end this far outside a round/rotated column snaps in


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
























def snap_beam_ends_to_columns(beam_segments, sections, circles=None,
                              pad_ft=None):
    """Run a beam END up to a ROUND or ROTATED column's centre to close the junction gap.

    A beam meeting an axis-aligned column butts cleanly against a flat edge, but a round
    column (tangent contact) or a rotated column (skew edge) leaves an ugly gap. When a
    beam endpoint lands inside such a column (within its radius + a small pad), the end is
    slid ALONG THE BEAM'S OWN AXIS to the point abeam of the column centre -- never onto
    the centre itself: a column deliberately drawn OFF the beam's axis (Test11's grid-I
    columns) would otherwise drag the end sideways and skew the whole beam off its CAD
    outline. Only ENDPOINTS move, never a beam's midspan; axis-aligned columns are left
    alone. Returns the number of ends snapped.
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
        for end, other in (("start", "end"), ("end", "start")):
            ex, ey = seg[end][0], seg[end][1]
            ox, oy = seg[other][0], seg[other][1]
            vx, vy = ex - ox, ey - oy
            length = (vx * vx + vy * vy) ** 0.5
            if length == 0:
                continue
            ux, uy = vx / length, vy / length   # axis direction, towards this end
            # NEAREST target, not first-in-list: a short stub clipped between TWO
            # rotated columns has both ends inside both columns' reach, and first-match
            # sent both ends to the same column, collapsing the beam (Test15's B648).
            # Nearest sends each end to its own column, stretching the stub across
            # the full bay.
            best = None
            for cx, cy, reach in targets:
                d2 = (ex - cx) ** 2 + (ey - cy) ** 2
                if d2 <= reach * reach and (best is None or d2 < best[0]):
                    best = (d2, cx, cy)
            if best is not None:
                _d2, cx, cy = best
                # project the column centre onto the beam's carrier line and move the
                # end THERE: extended to the centre's station, still on the beam's axis
                t = (cx - ox) * ux + (cy - oy) * uy
                seg[end][0], seg[end][1] = ox + ux * t, oy + uy * t
                snapped += 1
    return snapped


# A beam OUTLINE drawn straight across a column places a beam ON TOP of it in Revit.
_SPLIT_MIN_PIECE_MM = 100.0        # a leftover piece shorter than this is drafting overshoot
_SPLIT_MIN_PENETRATION_MM = 10.0   # centreline must reach this far inside; grazing a face is not a crossing
_SPLIT_JUNCTION_MARGIN_MM = 100.0  # an end at most this far past the column CENTRE is a junction



def dedupe_beam_segments(beam_segments, tol_mm=10.0):
    """Drop straight segments that RETRACE another segment of the same width.

    A messy beam-layer polyline that runs back over its own edges (test8's outlines
    trace across the column rectangles and back) decomposes into the same centreline
    twice -- or into a short fragment lying ON a longer one -- and every copy becomes
    a beam z-fighting in Revit. Two passes:
      1. EXACT twins: endpoints equal within `tol_mm` (either direction), same width.
      2. CONTAINED fragments: both endpoints of the shorter segment lie on the longer
         one's carrier line (within a small perpendicular band) and inside its span.
    The marked copy survives (a dropped fragment's mark transfers to its keeper when
    the keeper has none). Returns the number of segments removed.
    """
    grid = config.mm_to_ft(tol_mm)
    segments = beam_segments.get("segments", [])
    kept = {}
    order = []
    for seg in segments:
        a = (round(seg["start"][0] / grid), round(seg["start"][1] / grid))
        b = (round(seg["end"][0] / grid), round(seg["end"][1] / grid))
        key = (min(a, b), max(a, b), int(round(seg["width_mm"] / tol_mm)))
        other = kept.get(key)
        if other is None:
            kept[key] = seg
            order.append(key)
        elif not other.get("mark") and seg.get("mark"):
            kept[key] = seg               # keep the marked twin
    survivors = [kept[k] for k in order]

    band_ft = config.mm_to_ft(15.0)       # perpendicular slack off the carrier
    span_ft = config.mm_to_ft(tol_mm)
    by_len = sorted(survivors, key=lambda s: -s["length_mm"])
    removed = set()
    for i, big in enumerate(by_len):
        if id(big) in removed:
            continue
        ox, oy = big["start"][0], big["start"][1]
        vx, vy = big["end"][0] - ox, big["end"][1] - oy
        length = (vx * vx + vy * vy) ** 0.5
        if length <= 0:
            continue
        ux, uy = vx / length, vy / length
        for small in by_len[i + 1:]:
            if id(small) in removed:
                continue
            if abs(small["width_mm"] - big["width_mm"]) > tol_mm:
                continue
            ok = True
            for end in ("start", "end"):
                px, py = small[end][0] - ox, small[end][1] - oy
                t = px * ux + py * uy
                perp = abs(px * uy - py * ux)
                if perp > band_ft or t < -span_ft or t > length + span_ft:
                    ok = False
                    break
            if ok:
                removed.add(id(small))
                if small.get("mark") and not big.get("mark"):
                    big["mark"] = small["mark"]
    if removed:
        survivors = [s for s in survivors if id(s) not in removed]
    dropped = len(segments) - len(survivors)
    if dropped:
        beam_segments["segments"] = survivors
    return dropped










def _clip_slab(t0, t1, f0, df, half):
    """Shrink [t0, t1] to where |f0 + t*df| <= half; None when nothing remains."""
    if abs(df) < 1e-12:
        return (t0, t1) if abs(f0) <= half else None
    ta, tb = (-half - f0) / df, (half - f0) / df
    if ta > tb:
        ta, tb = tb, ta
    t0, t1 = max(t0, ta), min(t1, tb)
    return (t0, t1) if t0 < t1 else None


def _footprint_interval(fp, ox, oy, ux, uy, length, pen_ft):
    """(t0, t1, tc): where the centreline runs INSIDE the footprint, plus the
    column centre's station tc along the segment (the point abeam of the centre).

    None unless the interval's midpoint sits at least pen_ft inside every face,
    so a centreline grazing along a column face never counts as a crossing.
    """
    if fp[0] == "circle":
        _kind, cx, cy, r = fp
        fx, fy = ox - cx, oy - cy
        b = fx * ux + fy * uy
        disc = b * b - (fx * fx + fy * fy - r * r)
        if disc <= 0.0:
            return None
        root = disc ** 0.5
        t0, t1 = max(0.0, -b - root), min(length, -b + root)
        if t0 >= t1:
            return None
        tm = (t0 + t1) / 2.0
        dx, dy = ox + ux * tm - cx, oy + uy * tm - cy
        if (dx * dx + dy * dy) ** 0.5 > r - pen_ft:
            return None
        return t0, t1, -b
    _kind, cx, cy, ca, sa, half_long, half_short = fp
    fx, fy = ox - cx, oy - cy
    u0, du = fx * ca + fy * sa, ux * ca + uy * sa       # along the long axis
    v0, dv = fy * ca - fx * sa, uy * ca - ux * sa       # across it
    span = _clip_slab(0.0, length, u0, du, half_long)
    if span:
        span = _clip_slab(span[0], span[1], v0, dv, half_short)
    if not span:
        return None
    t0, t1 = span
    tm = (t0 + t1) / 2.0
    if (abs(u0 + du * tm) > half_long - pen_ft or
            abs(v0 + dv * tm) > half_short - pen_ft):
        return None
    return t0, t1, -(fx * ux + fy * uy)


def split_beams_at_columns(beam_segments, sections, circles=None,
                           extra_footprints=None):
    """Split a beam DRAWN ACROSS a column so no beam is modelled on top of it.

    Structural CAD routinely draws a continuous beam outline straight over the
    columns it crosses; placing that centreline verbatim buries a beam inside every
    column on its run (test8, client request). Wherever a segment's centreline
    passes through a column footprint with BOTH crossing points strictly inside the
    span, the segment is split into the pieces outside the column, trimmed at its
    faces -- the beam still "goes through" the column line as two members framing
    into opposite faces, but nothing is drawn on top of the column.

    A segment END is allowed to sit AT a column centre -- that is the junction
    convention (and exactly where the snap pass puts ends at round/rotated
    columns) -- so which overlaps count is decided per column:
      * crossing strictly inside the span -> SPLIT at the faces;
      * segment entirely inside one footprint (a "beam" coextensive with the
        column, i.e. the column's own outline mis-read as a beam) -> DROPPED;
      * a terminal end more than _SPLIT_JUNCTION_MARGIN_MM PAST the column
        centre (the beam was drawn across the column, e.g. to its far face)
        -> that end is TRIMMED back to the near face; an end at or before the
        centre (+margin) is a junction and never moves;
      * grazing contact (midpoint within _SPLIT_MIN_PENETRATION_MM of a face,
        e.g. a beam sharing a column's face line) never counts;
      * a piece shorter than _SPLIT_MIN_PIECE_MM is dropped -- that both
        discards drafting overshoot just past a face and absorbs the sliver
        between two near-adjacent crossed columns.
    Untouched segment dicts are REUSED (callers may hold a pre-split snapshot);
    split pieces are copies, with the mark kept on the longest piece only (mark
    ownership stays one-segment-per-mark). Curved beams are left alone.
    `extra_footprints` (from column_outline_footprints) adds obstacles for real
    columns the detector could not place. Returns the number of segments split,
    trimmed or dropped.
    """
    footprints = _column_footprints(sections, circles) + list(extra_footprints or [])
    if not footprints:
        return 0
    min_piece_ft = config.mm_to_ft(_SPLIT_MIN_PIECE_MM)
    pen_ft = config.mm_to_ft(_SPLIT_MIN_PENETRATION_MM)
    margin_ft = config.mm_to_ft(_SPLIT_JUNCTION_MARGIN_MM)
    end_eps_ft = config.mm_to_ft(0.1)
    changed = 0
    rebuilt = []
    for seg in beam_segments.get("segments", []):
        ox, oy = seg["start"][0], seg["start"][1]
        ex, ey = seg["end"][0], seg["end"][1]
        vx, vy = ex - ox, ey - oy
        length = (vx * vx + vy * vy) ** 0.5
        if length <= 0.0:
            rebuilt.append(seg)
            continue
        ux, uy = vx / length, vy / length
        intervals = []
        for fp in footprints:
            span = _footprint_interval(fp, ox, oy, ux, uy, length, pen_ft)
            if span is None:
                continue
            t0, t1, tc = span
            start_touch = t0 <= end_eps_ft
            end_touch = t1 >= length - end_eps_ft
            if start_touch and end_touch:
                intervals.append((0.0, length))     # buried inside the column
            elif start_touch:
                if tc > margin_ft:                  # start pokes past the centre
                    intervals.append((0.0, t1))     # trim it forward to the far face
            elif end_touch:
                if tc < length - margin_ft:         # end pokes past the centre
                    intervals.append((t0, length))  # trim it back to the near face
            else:
                intervals.append((t0, t1))          # genuine crossing: split here
        if not intervals:
            rebuilt.append(seg)
            continue
        intervals.sort()
        merged = [list(intervals[0])]
        for t0, t1 in intervals[1:]:
            if t0 <= merged[-1][1] + min_piece_ft:
                merged[-1][1] = max(merged[-1][1], t1)
            else:
                merged.append([t0, t1])
        pieces = []
        prev = 0.0
        for t0, t1 in merged:
            pieces.append((prev, t0))
            prev = t1
        pieces.append((prev, length))
        pieces = [p for p in pieces if p[1] - p[0] >= min_piece_ft]
        if not pieces:
            # pokes out under _SPLIT_MIN_PIECE_MM on every side: the whole "beam"
            # sits on top of the column -- exactly what must not be drawn
            changed += 1
            continue
        changed += 1
        z = seg["start"][2]
        longest = max(pieces, key=lambda p: p[1] - p[0])
        for t0, t1 in pieces:
            piece = dict(seg)
            piece["start"] = [ox + ux * t0, oy + uy * t0, z]
            piece["end"] = [ox + ux * t1, oy + uy * t1, z]
            piece["length_mm"] = (t1 - t0) * _MM
            if (t0, t1) != longest:
                piece["mark"] = None
            rebuilt.append(piece)
    beam_segments["segments"] = rebuilt
    return changed


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



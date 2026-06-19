# -*- coding: utf-8 -*-
"""Reporting: a human summary for the pyRevit output window and a JSON export.

The JSON schema is deliberately the intermediate format the future external
CPython 3 + ezdxf validator will consume, so writing it now is not throwaway --
it is the contract between the in-Revit reader and the out-of-Revit checker.
"""

import json
import math
from collections import defaultdict, Counter

from cad2bim import shapes
from cad2bim import marks
from cad2bim import config
from cad2bim.layers import CATEGORY_COLUMN, CATEGORY_BEAM

_MM = config.MM_PER_FT

# Acceptance limits (mm) -- the subset of config used as the UI's defaults.
DEFAULT_LIMITS = dict((key, config.DEFAULTS[key]) for key in (
    "beam_width_min_mm", "beam_width_max_mm",
    "col_b_min_mm", "col_b_max_mm", "col_h_min_mm", "col_h_max_mm"))

_FRAG_MAX_LINE_MM = 2000.0   # column-layer lines shorter than this are junction bits
_FRAG_GAP_MM = 400.0         # fragments within this gap belong to the same column


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

    # Recover columns whose Revit outline was clipped into disconnected fragments
    # at a junction (e.g. angled F9): cluster the leftover pieces and fit an
    # oriented rectangle. Skip any that land inside an already-placed column.
    recovered = shapes.recover_oriented_columns(
        fragments, gap_ft=config.mm_to_ft(_FRAG_GAP_MM))
    recovered_rects = []
    for rect in recovered:
        cx, cy, _cz = rect.center
        if _inside_a_circle(rect) or _inside_rectangles(cx, cy, leg_rectangles):
            continue
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
        "line_members": line_members,
        "line_spines": [spine.to_dict() for spine in spines],
        "circles": [circle.to_dict() for circle in circles],
        "dropped_raw": unplaced_raw,
    }


def _pts_mm(points):
    """[(x,y,z) feet ...] -> [[x_mm, y_mm], ...] integer pairs, for debug dumps."""
    return [[int(round(p[0] * _MM)), int(round(p[1] * _MM))] for p in points]


_TEXT_SIZE_OK_MM = 80.0   # a single column already this close to its label is left as-is
_SPLIT_CENTRE_SLACK_MM = 80.0      # split fragments' centres lie within (long side + this)
_SPLIT_NO_SIZE_MAX_CENTRE_MM = 800.0   # no label size: only fuse pieces this close


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
    for text in labels:
        tx, ty = text.point_internal[0], text.point_internal[1]
        near = [rect for rect in rects if id(rect) not in used
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
            if _fills_size(near[0], size):
                out = _copy_rect(near[0])      # already right size: just name it
                out["mark"] = text.mark
                used.add(id(near[0]))
                outputs.append(out)
                continue
        if size is None:                       # split pieces, no size: use footprint
            size = _union_size(near)

        for rect in near:
            used.add(id(rect))
        rect = _merge_to_label(near, size[0], size[1], text.mark)
        if grid_snap_ft:                       # we moved/resized -> snap onto the grid
            rect["center"][0] = _snap(rect["center"][0], grid_x, grid_snap_ft)
            rect["center"][1] = _snap(rect["center"][1], grid_y, grid_snap_ft)
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


def build_beam_segments(records, circles=None, limits=None, standards=None,
                        texts=None, tolerances=None):
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
    circles = circles or []
    status = defaultdict(int)
    segments = []
    review = []
    bare_lines = []
    arc_fits = []
    for record in records:
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
                    arc_fits.append(fit)
            continue
        xy, z = shapes.to_xy(record.points)
        ring = shapes.simplify_ring(xy)
        if not ring or len(ring) < 4:
            status["degenerate"] += 1
            continue
        if len(ring) == 4:
            result = shapes.beam_centerline_from_quad(ring)
            if result:
                start, end, width = result
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

    # (3) Arcs: drop round-column junction fillets; detect concentric curved beams.
    def _is_junction(fit):
        cx, cy, _r = fit
        for circle in circles:
            ccx, ccy, _cz = circle["center"]
            if ((cx - ccx) ** 2 + (cy - ccy) ** 2) ** 0.5 < junction_tol_ft:
                return True
        return False

    free_arcs = [f for f in arc_fits if not _is_junction(f)]
    status["arc_junction"] += (len(arc_fits) - len(free_arcs))
    used = [False] * len(free_arcs)
    curved_pairs = 0
    for a in range(len(free_arcs)):
        if used[a]:
            continue
        ax, ay, ar = free_arcs[a]
        for b in range(a + 1, len(free_arcs)):
            if used[b]:
                continue
            bx, by, br = free_arcs[b]
            same_center = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 < concentric_tol_ft
            gap = abs(ar - br)
            if same_center and pair_min_ft < gap < pair_max_ft:
                used[a] = used[b] = True
                curved_pairs += 1
                break
    if curved_pairs:
        status["curved_pair"] += curved_pairs
        review.append("{0} curved-beam arc pairs detected (placement to follow)".format(curved_pairs))
    lone = sum(1 for u in used if not u)
    if lone:
        status["arc_lone"] += lone

    refined = _apply_beam_marks(segments, texts,
                                config.mm_to_ft(tol["mark_radius_mm"]))
    if refined:
        status["text_sized"] = refined

    segments, dropped = _filter_beam_segments(segments, limits or DEFAULT_LIMITS,
                                              standards or {}, tol["snap_tol_mm"])
    if dropped:
        status["width_out_of_range"] = dropped

    return {"segments": segments, "status_counts": dict(status), "review": review}


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


def _apply_beam_marks(segments, texts, radius_ft):
    """Refine each beam segment from the nearest sized DXF mark, in place.

    width = smaller mark value, depth = larger. Returns the count refined.
    """
    candidates = marks.sized_texts(texts or [])
    if not candidates:
        return 0
    count = 0
    for segment in segments:
        cx = (segment["start"][0] + segment["end"][0]) / 2.0
        cy = (segment["start"][1] + segment["end"][1]) / 2.0
        hit = marks.nearest_sized_text(cx, cy, candidates, radius_ft)
        if hit is None:
            continue
        segment["width_mm"] = min(hit.b_mm, hit.h_mm)
        segment["depth_mm"] = max(hit.b_mm, hit.h_mm)
        segment["mark"] = hit.mark
        count += 1
    return count


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
    if not beams["segments"] and not beams["review"]:
        return []
    lines = ["Beam segments (centerline from outline):"]
    for status, count in sorted(beams["status_counts"].items()):
        lines.append("  {0:<16} {1}".format(status, count))
    lines.append("  {0:<16} {1}".format("-> segments", len(beams["segments"])))
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
        if text.b_mm is None:
            continue
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
                    "dropped_raw": sections.get("dropped_raw", [])},
        "beams": {"outcome": outcomes.get("beams"),
                  "status_counts": beams.get("status_counts", {}),
                  "items": _compact_beams(beams)},
        "texts_sized": _compact_texts(texts),
        "review": beams.get("review", []),
    }
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=1)
    return path

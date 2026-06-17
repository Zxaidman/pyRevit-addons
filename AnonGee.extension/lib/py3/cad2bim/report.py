# -*- coding: utf-8 -*-
"""Reporting: a human summary for the pyRevit output window and a JSON export.

The JSON schema is deliberately the intermediate format the future external
CPython 3 + ezdxf validator will consume, so writing it now is not throwaway --
it is the contract between the in-Revit reader and the out-of-Revit checker.
"""

import json
from collections import defaultdict, Counter

from cad2bim import shapes
from cad2bim import marks
from cad2bim.layers import CATEGORY_COLUMN, CATEGORY_BEAM

_MM = 304.8
_SNAP_TOL_MM = 60.0   # snap a measurement to a standard within this tolerance
_MARK_RADIUS_FT = 1000.0 / _MM   # a size label within ~1 m of a member refines it

# Acceptance limits (mm). The short side / beam width is the discriminating one:
# region blocks and clipped-junction shapes fall outside it. h_max is generous so
# long thin walls / lift spines (e.g. 300 x 12300) still pass.
DEFAULT_LIMITS = {
    "beam_width_min_mm": 150, "beam_width_max_mm": 600,
    "col_b_min_mm": 150, "col_b_max_mm": 1500,
    "col_h_min_mm": 150, "col_h_max_mm": 20000,
}


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


def build_column_sections(records, limits=None, standards=None, texts=None):
    """Decompose every column-category polyline into rectangular sections, and
    derive spine rectangles from bare column-layer lines.

    When `texts` (sized DXF marks, internal feet) are given, each rectangle is
    refined to the size of the nearest mark (e.g. "C1 400x400"), overriding the
    geometry-derived dimensions before limit/standard filtering.

    Line-drawn members (e.g. a lift spine) carry no width on their own; where two
    or more legs meet such a line, a spine rectangle is derived (width = measured
    gap to the legs) and added as a placeable 'line_spine' entry. Lines that do
    not resolve to a spine are reported as leftover line_members.
    """
    status_counts = defaultdict(int)
    total_rectangles = 0
    entries = []
    leg_rectangles = []
    line_points = []
    line_members = []
    arc_records = []
    polyline_records = []
    for record in records:
        if record.category != CATEGORY_COLUMN:
            continue
        if record.kind == "line":
            line_points.append(record.points)
            line_members.append({"layer": record.layer,
                                 "length_mm": _polyline_length_ft(record.points) * 304.8})
        elif record.kind == "arc":
            arc_records.append(record)
        else:
            polyline_records.append(record)

    # Circles first, so polyline fragments of a circle (arcs captured as polylines)
    # can be discarded instead of becoming spurious little rectangles.
    circles = shapes.build_circular_columns(arc_records)

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

    refined = _apply_column_marks(entries, texts)
    if refined:
        status_counts["text_sized"] += refined

    dropped = _filter_column_entries(entries, limits or DEFAULT_LIMITS, standards or {})
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
    }


def _filter_column_entries(entries, limits, standards):
    """Snap each rectangle's b/h to standard sizes and drop out-of-range ones.

    Snapping preserves which stored dimension (width/height) is the short side, so
    the placement rotation stays correct. Returns the number dropped.
    """
    dims = [d / _MM for d in _standard_dims_mm(standards.get("column", []))]
    tol = _SNAP_TOL_MM / _MM
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


_JUNCTION_TOL_FT = 200.0 / 304.8     # an arc centred this close to a round column is a junction
_CONCENTRIC_TOL_FT = 60.0 / 304.8    # two arcs sharing a centre this closely are concentric


def build_beam_segments(records, circles=None, limits=None, standards=None,
                        texts=None):
    """Derive straight beam centerlines from beam-category geometry.

    When `texts` (sized DXF marks, internal feet) are given, each segment is
    refined from the nearest mark (e.g. "B1 230x500"): width = the smaller value,
    DEPTH = the larger -- the depth a 2D outline cannot provide on its own.

    Three sources: (1) closed thin outlines -> one centerline along the long axis;
    multi-segment rectilinear outlines decompose into straight beams. (2) PAIRS of
    parallel lines ~one width apart -> a beam on their midline (this is how the
    perimeter / grid-line beams are drawn). (3) arcs: those centred on a detected
    round column are junction fillets and ignored; genuine curved beams (concentric
    arc pairs) are detected and surfaced (placement to follow).
    """
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
    line_segments, leftover = shapes.pair_parallel_lines(bare_lines)
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
            if ((cx - ccx) ** 2 + (cy - ccy) ** 2) ** 0.5 < _JUNCTION_TOL_FT:
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
            same_center = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 < _CONCENTRIC_TOL_FT
            gap = abs(ar - br)
            if same_center and shapes._PAIR_MIN_WIDTH_FT < gap < shapes._PAIR_MAX_WIDTH_FT:
                used[a] = used[b] = True
                curved_pairs += 1
                break
    if curved_pairs:
        status["curved_pair"] += curved_pairs
        review.append("{0} curved-beam arc pairs detected (placement to follow)".format(curved_pairs))
    lone = sum(1 for u in used if not u)
    if lone:
        status["arc_lone"] += lone

    refined = _apply_beam_marks(segments, texts)
    if refined:
        status["text_sized"] = refined

    segments, dropped = _filter_beam_segments(segments, limits or DEFAULT_LIMITS,
                                              standards or {})
    if dropped:
        status["width_out_of_range"] = dropped

    return {"segments": segments, "status_counts": dict(status), "review": review}


def _apply_column_marks(entries, texts):
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
            hit = marks.nearest_sized_text(cx, cy, candidates, _MARK_RADIUS_FT)
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


def _apply_beam_marks(segments, texts):
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
        hit = marks.nearest_sized_text(cx, cy, candidates, _MARK_RADIUS_FT)
        if hit is None:
            continue
        segment["width_mm"] = min(hit.b_mm, hit.h_mm)
        segment["depth_mm"] = max(hit.b_mm, hit.h_mm)
        segment["mark"] = hit.mark
        count += 1
    return count


def _filter_beam_segments(segments, limits, standards):
    """Snap each beam width to a standard and drop widths outside the limit band.

    This is what rejects junction-clipped 'beams' (e.g. a 1064 mm-wide blob) while
    keeping real 300 mm members. Returns (kept_segments, dropped_count).
    """
    widths = [w / _MM for w in standards.get("beam_widths", [])]
    tol = _SNAP_TOL_MM / _MM
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


def build_report_payload(result, mapping, sections, beams, outcomes=None,
                         texts=None, comparison=None):
    """The full run report, embedded in the JSON so the console can stay short."""
    layer_counts = build_layer_counts(result.records)
    layer_rows = []
    for layer in sorted(layer_counts.keys()):
        layer_rows.append({
            "layer": layer,
            "category": mapping.get(layer, "unmapped"),
            "count": layer_counts[layer]["count"],
            "kinds": dict(layer_counts[layer]["kinds"]),
        })
    beam_widths = Counter(int(round(s["width_mm"])) for s in beams.get("segments", []))
    sized_marks = [t.to_dict() for t in (texts or []) if t.b_mm is not None]
    return {
        "source": result.source_name,
        "curves": len(result.records),
        "category_counts": build_category_counts(result.records),
        "layers": layer_rows,
        "columns": {
            "status_counts": sections.get("status_counts", {}),
            "total_rectangles": sections.get("total_rectangles", 0),
            "circles": sections.get("circles", []),
            "line_members": sections.get("line_members", []),
            "line_spines": sections.get("line_spines", []),
        },
        "beams": {
            "status_counts": beams.get("status_counts", {}),
            "segments": len(beams.get("segments", [])),
            "review": beams.get("review", []),
            "widths_mm": dict(beam_widths),
        },
        "outcomes": outcomes or {},
        "texts": {"sized_count": len(sized_marks), "marks": sized_marks},
        "comparison": comparison or {},
        "console": format_console(result, mapping, sections, beams),
    }


def export_json(path, result, mapping, sections=None, beams=None, outcomes=None,
                texts=None, comparison=None):
    """Write the intermediate JSON consumed by the future ezdxf validator.

    Includes a 'report' block (the same summary shown in the console plus the run
    outcomes) so the console can stay short and the JSON is self-describing.
    Returns the path on success; raises IOError/OSError on a write failure.
    """
    empty_beams = {"segments": [], "review": [], "status_counts": {}}
    payload = {
        "source": result.source_name,
        "units": "internal_feet",          # explicit: NOT rescaled
        "mapping": dict(mapping),
        "curves": [record.to_dict() for record in result.records],
        "report": build_report_payload(result, mapping, sections or {},
                                       beams or empty_beams, outcomes,
                                       texts, comparison),
    }
    if sections is not None:
        payload["column_sections"] = sections
    if beams is not None:
        payload["beam_segments"] = beams
    if texts is not None:
        payload["texts"] = [t.to_dict() for t in texts]
    if comparison is not None:
        payload["comparison"] = comparison
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
    return path

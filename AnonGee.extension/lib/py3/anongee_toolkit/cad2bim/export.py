# -*- coding: utf-8 -*-
"""What a run REPORTS: the console summary and the JSON export.

Split out of report.py, which had grown to hold four unrelated jobs. This is
the output end only -- it reads the structures the rest of the package built
(sections, beam segments, outcomes) and turns them into text a person reads or
a file the next run can be replayed from. Nothing here decides geometry, so a
change in this module can never move an element in Revit.

The JSON is COMPACT and in millimetres: it is a diagnostic that gets diffed
between versions, so it stays small enough to read and stable enough to
fingerprint. `_jsonable` is the last-resort encoder -- a report is a diagnostic
and must never be the reason a completed build reports failure.
"""

import json
import re
from collections import defaultdict, Counter

from . import config
from .classify.layers import (CATEGORY_COLUMN, CATEGORY_BEAM,
                              CATEGORY_SLAB_EDGE, CATEGORY_STAIR,
                              CATEGORY_STRUCT_WALL)

_MM = config.MM_PER_FT


def _version():
    """The package version, read late so this module imports standalone.

    The tests load these modules from their files into a throwaway package that
    has no version of its own, and a report is never worth failing a run over.
    """
    try:
        from . import __version__
        return __version__
    except (ImportError, AttributeError):
        return "unknown"


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
        if record.category not in (CATEGORY_BEAM, CATEGORY_SLAB_EDGE,
                                   CATEGORY_COLUMN, CATEGORY_STAIR,
                                   CATEGORY_STRUCT_WALL):
            continue
        out.append({
            "cat": ("slab" if record.category == CATEGORY_SLAB_EDGE
                    else "column" if record.category == CATEGORY_COLUMN
                    else "stair" if record.category == CATEGORY_STAIR
                    else "wall" if record.category == CATEGORY_STRUCT_WALL
                    else "beam"),
            "kind": record.kind,
            "layer": record.layer,
            "pts": [[round(p[0] * _MM, 1), round(p[1] * _MM, 1)] for p in record.points],
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
    stair_note = re.compile(
        r"^\s*(?:STAIRS?CASE|STAIRS?|ST[-_ ]?\d+|DN|UP)\.?\s*$", re.IGNORECASE)
    for text in texts or []:
        is_stair_note = bool(stair_note.match(text.text or ""))
        if text.b_mm is None and not getattr(text, "mark", None) and not is_stair_note:
            continue   # no size, no mark, no stair note: nothing to replay from it
        mark = getattr(text, "mark", None)
        if is_stair_note and not mark:
            mark = (text.text or "").strip()
        point = text.point_internal
        out.append({"mark": mark, "layer": text.layer,
                    "b": text.b_mm, "h": text.h_mm,
                    "x": _mm(point[0]) if point else None,
                    "y": _mm(point[1]) if point else None,
                    "rot": getattr(text, "rotation_deg", None)})
    return out


def build_export_payload(result, mapping, sections=None, beams=None,
                         outcomes=None, texts=None, comparison=None):
    """The COMPACT run report (mm) as a dict -- see export_json for the format.

    Split out from export_json so a MULTI-STOREY run can put one payload per
    storey inside a single file instead of writing one file per floor.
    """
    sections = sections or {}
    beams = beams or {"segments": [], "review": [], "status_counts": {}}
    comparison = comparison or {}
    outcomes = outcomes or {}
    payload = {
        "source": result.source_name,
        "cad2bim_version": _version(),
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
        "slabs": outcomes.get("slabs"),
        "stairs": outcomes.get("stairs"),
        "beams": {"outcome": outcomes.get("beams"),
                  "status_counts": beams.get("status_counts", {}),
                  "items": _compact_beams(beams),
                  "raw_geometry": _beam_geometry_dump(result)},
        "texts_sized": _compact_texts(texts),
        "review": beams.get("review", []),
    }
    return payload


def _jsonable(value):
    """Last-resort encoder: a report is a diagnostic, never a reason to fail.

    A live Revit object that leaks into the outcomes (an ElementId did once)
    would otherwise raise out of json.dump AFTER the model was built, losing the
    report and reporting a crash for a run that actually worked.
    """
    for attribute in ("IntegerValue", "Value"):
        try:
            return getattr(value, attribute)
        except Exception:
            continue
    return str(value)


def export_json(path, result, mapping, sections=None, beams=None, outcomes=None,
                texts=None, comparison=None):
    """Write a COMPACT run report (mm). No raw per-curve point dump -- just the
    placed elements and the problem-geometry summary, so the file stays small and
    is easy to paste/review. Each element list is one compact object per member.
    """
    payload = build_export_payload(result, mapping, sections, beams, outcomes,
                                   texts, comparison)
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=1, default=_jsonable)
    return path


def export_storeys_json(path, storeys, source_name=None):
    """Write ONE file for a multi-storey run: a `storeys` array of sections.

    `storeys` is [(label, payload), ...] bottom-up. The shared header (source,
    version, units) is lifted out of the first payload so the per-storey
    sections carry only what actually differs between floors -- the user asked
    for one JSON with a section per storey, not one file per floor.
    """
    sections = []
    for label, payload in storeys:
        section = dict(payload)
        for shared in ("source", "cad2bim_version", "units"):
            section.pop(shared, None)
        section["storey"] = label
        sections.append(section)
    first = storeys[0][1] if storeys else {}
    document = {
        "source": source_name or first.get("source"),
        "cad2bim_version": _version(),
        "units": first.get("units",
                           "mm (sizes and positions; positions derived from "
                           "internal feet)"),
        "storey_count": len(sections),
        "storeys": sections,
    }
    with open(path, "w") as handle:
        json.dump(document, handle, indent=1, default=_jsonable)
    return path

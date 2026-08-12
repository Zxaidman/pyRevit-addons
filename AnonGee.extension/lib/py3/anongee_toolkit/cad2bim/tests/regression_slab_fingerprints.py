# -*- coding: utf-8 -*-
"""Regression leg 1 of 3: slab outlines over every archived Revit export.

Rebuilt from `scratchpad/slabbase.py` + `base_after.json`, which held 22 stored
fingerprints, were never committed, and are gone. The corpus here is the LATEST
export of each distinct drawing -- 29 of them, discovered rather than listed --
so it is wider than the 22 it replaces, and five of those drawings (test14,
test15, test18, test19, test20) have no surviving DXF at all. This leg is the
only thing that still watches them.

What makes it worth having next to the DXF sweep: an export carries
`beams.raw_geometry`, the exact geometry the REVIT LINK reader returned, in mm.
The DXF carries the same building as loose linework. They exercise different
inputs into the same passes, and a change can break one without touching the
other.

LIMIT, stated rather than papered over: an export stores texts as PARSED marks
(`{"mark": ..., "b": ..., "h": ...}`) and drops the string they came from. Both
`apply_slab_labels` and `loops_for_unclaimed_notes` re-parse `text.text`, so
slab NOTES and LABELS cannot be replayed from an export -- test13's export has
211 texts, every one with `mark: None`. Note recovery is therefore measured by
regression_dxf_sweep, where the text survives. This leg measures the geometry.

The stored numbers are NOT the lost v0.67.3 baseline -- nobody can produce that
any more. They were measured at v0.68.1, the release confirmed against Revit.
What is being defended from here is drift.

SLOW (~30s), hence `regression_*` and not `test_*`:

    cd cad2bim/tests
    python3 -m unittest regression_slab_fingerprints
    CAD2BIM_BLESS=1 python3 -m unittest regression_slab_fingerprints  # re-record
"""

import json
import os
import re
import unittest

import _golden
import _loader


config, model, layers, marks, report, slab_outlines = _loader.load(
    "config", "model", "classify.layers", "classify.marks", "report",
    "slab_outlines")

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXPORTS = os.path.join(_HERE, "fixtures", "cad", ".json")
_MM = config.MM_PER_FT
_FT = 1.0 / _MM
_BASELINE = "slab_fingerprints"

_EXPORT_NAME = re.compile(r"^(\d+)\.(\d+)\.(\d+)_(.*)_with_textmode\.json$")
_KIND_PREFIX = re.compile(r"^(slab|beam|stair|Layout)_", re.IGNORECASE)


def _corpus():
    """{drawing: path} -- the newest export of each distinct drawing.

    One per drawing, not one per version: the archive holds the same plan
    exported at a dozen releases, and replaying all 286 would measure the
    archive's shape rather than the code's behaviour.
    """
    best = {}
    for folder, _folders, files in os.walk(_EXPORTS):
        for name in files:
            match = _EXPORT_NAME.match(name)
            if not match:
                continue
            version = tuple(int(match.group(i)) for i in (1, 2, 3))
            drawing = _KIND_PREFIX.sub("", match.group(4))
            if drawing not in best or version > best[drawing][0]:
                best[drawing] = (version, os.path.join(folder, name))
    return dict((drawing, path) for drawing, (_v, path) in best.items())


class _Text(object):
    """The parsed text an export preserves. No `.text`: see the module note."""

    def __init__(self, row):
        self.mark = row.get("mark")
        self.b_mm = row.get("b")
        self.h_mm = row.get("h")
        self.layer = row.get("layer")
        x, y = row.get("x"), row.get("y")
        self.point_internal = (None if x is None
                               else (x * _FT, y * _FT, 0.0))


def _storey(document, index=0):
    """One storey's payload, or the document itself for a single-storey export."""
    storeys = document.get("storeys")
    return storeys[index] if storeys else document


def _records(payload):
    """CurveRecords rebuilt from the geometry the Revit link reader returned."""
    records = []
    for geometry in (payload.get("beams") or {}).get("raw_geometry") or []:
        points = [(p[0] * _FT, p[1] * _FT, 0.0) for p in geometry["pts"]]
        record = model.CurveRecord(geometry["kind"], points,
                                   geometry["layer"], 0.0)
        record.category = (layers.CATEGORY_SLAB_EDGE
                           if geometry.get("cat") == "slab"
                           else layers.CATEGORY_BEAM)
        records.append(record)
    return records


def _sections(payload):
    """A sections dict shaped from the PLACED columns the export recorded.

    column_trim_footprints wants what was actually built, which is exactly what
    an export lists -- so this is a more faithful trim set than re-deriving the
    columns would be. `long_axis_deg` is absent from the export, so footprints
    fall back to the same placement default the column builder uses.
    """
    columns = payload.get("columns") or {}
    rectangles = []
    for item in columns.get("items") or []:
        rectangles.append({
            "width_mm": item["b"], "height_mm": item["h"],
            "center": (item["x"] * _FT, item["y"] * _FT, 0.0),
            "mark": item.get("mark"), "long_axis_deg": item.get("rot"),
        })
    circles = [{"center": (c["x"] * _FT, c["y"] * _FT, 0.0),
                "diameter_ft": c["dia"] * _FT,
                "diameter_mm": c["dia"], "mark": c.get("mark")}
               for c in columns.get("circles") or []]
    return {"entries": [{"rectangles": rectangles}] if rectangles else [],
            "circles": circles}


def _area_m2(ring):
    """Plan area of a ring in square metres, sign discarded."""
    total = 0.0
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[(index + 1) % count][0], ring[(index + 1) % count][1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0 * _MM * _MM / 1e6


def _loop_stats(loops, prefix):
    """Count and total area for one outline source."""
    areas = [_area_m2(loop[0]) for loop in loops or []]
    return {prefix: len(areas),
            prefix + "_area_m2": round(sum(areas), 1)}


def _measure(path):
    with open(path, encoding="utf-8") as handle:
        payload = _storey(json.load(handle))
    records = _records(payload)
    sections = _sections(payload)
    footprints = report.column_trim_footprints(sections)
    texts = [_Text(row) for row in payload.get("texts_sized") or []]
    beam_texts = [t for t in texts
                  if layers.classify_text_layer(t.layer or "")
                  == layers.CATEGORY_BEAM_TEXT]
    circles = [{"center": c["center"], "diameter_ft": c["diameter_ft"]}
               for c in sections["circles"]]

    segments = report.build_beam_segments(records, circles, None, None,
                                          texts=beam_texts, tolerances={},
                                          schedule=None)
    beams = segments.get("segments") or []
    measured = {
        "records": len(records),
        "column_rectangles": len(
            (sections["entries"][0]["rectangles"]) if sections["entries"] else []),
        "column_circles": len(sections["circles"]),
        "column_footprints": len(footprints),
        "beams": len(beams),
        "sized_beams": sum(1 for b in beams if b.get("depth_mm")),
    }
    measured.update(_loop_stats(slab_outlines.slab_loops_from_edges(records),
                                "loops_from_edges"))
    measured.update(_loop_stats(slab_outlines.slab_loops_from_beam_graph(beams),
                                "loops_from_beam_graph"))
    measured.update(_loop_stats(
        slab_outlines.slab_loops_from_placed_members(
            records, beams, column_rects=footprints),
        "loops_from_placed_members"))
    return measured


class SlabFingerprints(unittest.TestCase):
    def test_every_archived_export_produces_the_outlines_it_used_to(self):
        corpus = _corpus()
        self.assertTrue(corpus, "no JSON exports found under fixtures/cad/.json")

        current = {}
        for drawing in sorted(corpus):
            current[drawing] = _measure(corpus[drawing])

        path = _golden.baseline_path(_BASELINE)
        baseline = _golden.load(path)
        if baseline is None or _golden.blessing():
            _golden.save(path, current)
            self.skipTest("baseline {0} written ({1} drawings) -- rerun to "
                          "check against it".format(_BASELINE, len(current)))
        moved = _golden.differences(baseline, current)
        self.assertEqual(moved, [], "the slab fingerprints moved:\n  " +
                         "\n  ".join(moved))


if __name__ == "__main__":
    unittest.main()

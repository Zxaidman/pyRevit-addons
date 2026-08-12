# -*- coding: utf-8 -*-
"""Regression leg 2 of 3: the whole DXF corpus through the whole offline pipeline.

Every fixture DXF is read, classified, and run through column sectioning, beam
segmentation and both slab-outline sources. The counts are compared against
`baselines/dxf_sweep.json`. Any number that moves stops the run and is named.

This is the leg that catches what unit tests cannot: a change that is correct on
the case it was written for and wrong on the other sixteen drawings. It is the
rebuilt `scratchpad/sweep67.py`, which was never committed and is gone -- so the
numbers here are NOT the v0.67.3 baseline it held. They were re-measured at
v0.68.1, the release the user confirmed against Revit. The value is drift from
here on, not continuity with a baseline nobody can produce any more.

SLOW -- about a minute, most of it in ezdxf parsing Test4/Test5/Test10. That is
why this file is `regression_*` and not `test_*`: the everyday unit suite stays
under a second, and this runs as a release gate.

    cd cad2bim/tests
    python3 -m unittest discover -p "regression_*.py"     # all three legs
    python3 -m unittest regression_dxf_sweep              # just this one
    CAD2BIM_BLESS=1 python3 -m unittest regression_dxf_sweep   # re-record

Needs ezdxf. On Linux `pip install ezdxf` -- the bundled lib/py3 copy is a
Windows build and will not import (see the skip message).
"""

import os
import unittest

import _golden
import _loader


report, layers, marks, dxf_reader, slab_outlines = _loader.load(
    "report", "classify.layers", "classify.marks", "readers.dxf_reader",
    "slab_outlines")

_HERE = os.path.dirname(os.path.abspath(__file__))
_CAD = os.path.join(_HERE, "fixtures", "cad")
_FT = 1.0 / 304.8
_BASELINE = "dxf_sweep"


def _fixtures():
    """Every fixture DXF, by name, in a fixed order.

    Discovered rather than listed: a DXF added to the corpus should show up as a
    new fixture in the baseline diff, not be silently ignored because nobody
    remembered to add it to a list here.
    """
    if not os.path.isdir(_CAD):
        return []
    return sorted(name for name in os.listdir(_CAD)
                  if name.lower().endswith(".dxf"))


def _measure(path):
    """The fingerprint of one drawing: what the pipeline found in it.

    Counts, not geometry. A count moving is the signal -- WHICH rectangle moved
    is a question for the debugger, and storing every ring would make the
    baseline unreadable and its diffs useless.
    """
    result = dxf_reader.read_dxf(path)
    for record in result.records:
        record.points = [(p[0] * _FT, p[1] * _FT, 0.0) for p in record.points]
    layers.apply_mapping(
        result.records,
        layers.build_default_mapping([r.layer_key for r in result.records]))
    for text in result.texts:
        text.point_internal = (text.point[0] * _FT, text.point[1] * _FT, 0.0)
    marks.parse_texts(result.texts)

    sections = report.build_column_sections(result.records, texts=result.texts,
                                            tolerances={})
    entries = sections.get("entries") or []
    footprints = report.column_trim_footprints(sections)
    segments = report.build_beam_segments(result.records, [], None, None,
                                          texts=result.texts, tolerances={},
                                          schedule=None)
    split = report.split_beams_at_columns(segments, sections,
                                          sections.get("circles"))
    beams = segments.get("segments") or []

    # The slab chain EXACTLY as run_builders._create_slabs runs it: drawn edges
    # first, the placed-member faces when there are none, then the bays a
    # thickness note claims that no outline covered, then the labels. This is
    # the half the export replay cannot reach -- an export stores parsed marks,
    # not the text they were parsed from, so only a DXF can drive it.
    edges = slab_outlines.slab_loops_from_edges(result.records)
    loops = edges
    source = "slab_edges"
    if not loops:
        loops = slab_outlines.slab_loops_from_placed_members(
            result.records, beams, column_rects=footprints)
        source = "placed_members"
    recovered = slab_outlines.loops_for_unclaimed_notes(
        loops, result.records, beams, result.texts, column_rects=footprints)
    if recovered:
        loops = list(loops) + list(recovered)
    labelled = slab_outlines.apply_slab_labels(loops, result.texts)

    return {
        "records": len(result.records),
        "texts": len(result.texts),
        "column_entries": len(entries),
        "column_rectangles": sum(len(e.get("rectangles") or []) for e in entries),
        "column_circles": len(sections.get("circles") or []),
        "column_footprints": len(footprints),
        "marked_rectangles": sum(
            1 for e in entries for r in (e.get("rectangles") or [])
            if r.get("mark")),
        "beams": len(beams),
        "beams_split_at_columns": int(split or 0),
        "marked_beams": sum(1 for b in beams if b.get("mark")),
        "sized_beams": sum(1 for b in beams if b.get("depth_mm")),
        "slab_source": source,
        "slab_loops_from_edges": len(edges),
        "slab_loops_from_beam_graph": len(
            slab_outlines.slab_loops_from_beam_graph(beams)),
        "slab_loops_recovered_from_notes": len(recovered or []),
        "slab_loops_total": len(labelled),
        "slab_loops_marked": sum(1 for s in labelled if s.get("mark")),
        "slab_loops_sized": sum(1 for s in labelled
                                if s.get("thickness_mm") is not None),
    }


class DxfSweep(unittest.TestCase):
    def test_every_fixture_dxf_produces_the_numbers_it_used_to(self):
        if not dxf_reader.ezdxf_available():
            self.skipTest("ezdxf is not importable -- `pip install ezdxf` "
                          "(the bundled lib/py3 copy is a Windows build)")
        names = _fixtures()
        self.assertTrue(names, "no fixture DXFs found under fixtures/cad")

        current = {}
        for name in names:
            current[name] = _measure(os.path.join(_CAD, name))

        path = _golden.baseline_path(_BASELINE)
        baseline = _golden.load(path)
        if baseline is None or _golden.blessing():
            _golden.save(path, current)
            self.skipTest("baseline {0} written ({1} fixtures) -- rerun to "
                          "check against it".format(_BASELINE, len(current)))
        moved = _golden.differences(baseline, current)
        self.assertEqual(moved, [], "the DXF sweep moved:\n  " +
                         "\n  ".join(moved))


if __name__ == "__main__":
    unittest.main()

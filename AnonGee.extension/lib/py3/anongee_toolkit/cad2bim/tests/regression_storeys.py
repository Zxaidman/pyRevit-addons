# -*- coding: utf-8 -*-
"""Regression leg 3 of 3: every storey of every multi-storey export, replayed.

Rebuilt from `scratchpad/t10_full.py` and `t10_cols.py`, which were never
committed and are gone. Four exports carry a storey stack: test10 (10 storeys),
test9 (11), test12 (5), test13 (5). Each storey is replayed on its own and its
numbers recorded per storey, in order.

Why this is not covered by the other two legs: they both replay ONE storey, and
almost every storey bug this project has had lived in the storeys the first one
hides. test10's ROOF is the case that named this harness -- it carries no A-FLOR
layer at all, so the drawn-edge source finds nothing there while finding plenty
on the floors below, and the v0.67.2 "note recovery only ran when edges were
found" bug built zero roof slabs while every storey below looked perfect. A
single-storey fingerprint cannot see that. A per-storey one cannot miss it.

The per-storey lists are stored whole rather than summed, so a diff points at
the storey that moved instead of saying a total changed.

The stored numbers were measured at v0.68.1, the release confirmed against
Revit, not recovered from the lost baseline. Drift is what they defend.

SLOW (~40s), hence `regression_*` and not `test_*`:

    cd cad2bim/tests
    python3 -m unittest regression_storeys
    CAD2BIM_BLESS=1 python3 -m unittest regression_storeys    # re-record
"""

import json
import os
import re
import unittest

import _golden
import _loader
import regression_slab_fingerprints as fingerprints


report, slab_outlines = _loader.load("report", "slab_outlines")

_BASELINE = "storeys"


def _multi_storey_corpus():
    """{drawing: path} for the exports that carry more than one storey."""
    corpus = {}
    for drawing, path in fingerprints._corpus().items():
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        if len(document.get("storeys") or []) > 1:
            corpus[drawing] = path
    return corpus


def _label(storey, index):
    """A storey's title, flattened to one line and trimmed.

    test9's titles carry embedded newlines ("GROUND FLOOR FRAMING PLAN \n( TOWER
    AREA )"); a baseline is read in a diff, so they are stored on one line.
    """
    text = " ".join(str(storey.get("storey") or "").split())
    return text or "storey {0}".format(index + 1)


def _measure(path):
    with open(path, encoding="utf-8") as handle:
        document = json.load(handle)
    storeys = document.get("storeys") or []

    labels, beams, edges, graph, placed, areas = [], [], [], [], [], []
    for index, storey in enumerate(storeys):
        records = fingerprints._records(storey)
        sections = fingerprints._sections(storey)
        footprints = report.column_trim_footprints(sections)
        circles = [{"center": c["center"], "diameter_ft": c["diameter_ft"]}
                   for c in sections["circles"]]
        segments = report.build_beam_segments(records, circles, None, None,
                                              texts=[], tolerances={},
                                              schedule=None)
        placed_loops = slab_outlines.slab_loops_from_placed_members(
            records, segments.get("segments") or [], column_rects=footprints)

        labels.append(_label(storey, index))
        beams.append(len(segments.get("segments") or []))
        edges.append(len(slab_outlines.slab_loops_from_edges(records)))
        graph.append(len(slab_outlines.slab_loops_from_beam_graph(
            segments.get("segments") or [])))
        placed.append(len(placed_loops))
        areas.append(round(sum(fingerprints._area_m2(loop[0])
                               for loop in placed_loops), 1))

    roof = _roof_index(storeys)
    return {
        "storeys": len(storeys),
        "labels": labels,
        "beams_per_storey": beams,
        "loops_from_edges_per_storey": edges,
        "loops_from_beam_graph_per_storey": graph,
        "loops_from_placed_members_per_storey": placed,
        "placed_area_m2_per_storey": areas,
        # The roof, called out on its own because it is the storey that has
        # broken before while every floor below stayed right.
        "roof_loops_from_edges": edges[roof] if edges else 0,
        "roof_loops_from_placed_members": placed[roof] if placed else 0,
    }


def _roof_index(storeys):
    """The storey the drawing CALLS the roof, else the top of the stack.

    Pinned by label, not position -- the same lesson the fingerprint leg
    already learned about its main storey. "Terrace" and "Roof" tie in level
    order (both are top-of-building names), so their stored order can flip
    between two runs of the same drawing: the user's 0.69.0 test10 export came
    back [..., Roof, Terrace] where every earlier one was [..., Terrace,
    Roof], and an index of -1 silently re-pointed the roof metrics at the
    terrace -- reporting 7 -> 30 as if the roof had changed, when nothing in
    either storey had moved at all.
    """
    for index in range(len(storeys) - 1, -1, -1):
        if re.search(r"\broof\b", str(storeys[index].get("storey") or ""),
                     re.IGNORECASE):
            return index
    return len(storeys) - 1


class Storeys(unittest.TestCase):
    def test_every_storey_of_every_stack_produces_what_it_used_to(self):
        corpus = _multi_storey_corpus()
        self.assertTrue(corpus, "no multi-storey exports found")

        current = dict((drawing, _measure(corpus[drawing]))
                       for drawing in sorted(corpus))

        path = _golden.baseline_path(_BASELINE)
        baseline = _golden.load(path)
        if baseline is None or _golden.blessing():
            _golden.save(path, current)
            self.skipTest("baseline {0} written ({1} stacks) -- rerun to check "
                          "against it".format(_BASELINE, len(current)))
        moved = _golden.differences(baseline, current)
        self.assertEqual(moved, [], "the storey replay moved:\n  " +
                         "\n  ".join(moved))


if __name__ == "__main__":
    unittest.main()

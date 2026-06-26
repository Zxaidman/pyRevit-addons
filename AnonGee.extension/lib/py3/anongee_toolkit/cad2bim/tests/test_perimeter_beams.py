# -*- coding: utf-8 -*-
"""report.build_beam_segments -- perimeter / floor-clipped beam recovery (edge_pair).

Revit clips a perimeter beam's inner edge against the floor (slab) outline, so only one
beam edge survives on the beam layer; the other is on the slab/floor layer. The beam is
recovered by pairing the lone beam line with the parallel slab edge, KEPT only where a beam
label of matching width sits across it. A slab edge alone is never a beam, and an edge pair
that merely re-traces an already-placed beam is dropped. Standalone (no Revit / no numpy).
"""

import importlib.util
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_MM = 304.8
_FT = 1.0 / _MM


def _load_report():
    for name in ("_pb", "_pb.geom", "_pb.classify"):
        if name not in sys.modules:
            m = types.ModuleType(name)
            m.__path__ = []
            sys.modules[name] = m

    def load(full, *parts):
        spec = importlib.util.spec_from_file_location(full, os.path.join(_PKG, *parts))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        if "." in full:
            parent, child = full.rsplit(".", 1)
            setattr(sys.modules[parent], child, mod)
        spec.loader.exec_module(mod)
        return mod

    load("_pb.config", "config.py")
    load("_pb.geom.shapes", "geom", "shapes.py")
    load("_pb.classify.marks", "classify", "marks.py")
    load("_pb.classify.layers", "classify", "layers.py")
    return load("_pb.report", "report.py")


report = _load_report()


class _Rec(object):
    def __init__(self, category, *pts_mm):
        # 2 points -> a line; more -> a polyline (the Revit link reader's floor outline).
        self.kind = "line" if len(pts_mm) == 2 else "polyline"
        self.category = category
        self.layer = category
        self.points = [(x * _FT, y * _FT, 0.0) for (x, y) in pts_mm]


def _line(category, x0, y0, x1, y1):
    return _Rec(category, (x0, y0), (x1, y1))


class _Lbl(object):
    def __init__(self, mark, b_mm, h_mm, x_mm, y_mm):
        self.mark = mark
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _edge_beams(out):
    return [s for s in out["segments"] if s["status"] == "edge_pair"]


class PerimeterBeams(unittest.TestCase):

    def test_beam_from_lone_line_plus_floor_edge(self):
        # One surviving beam edge (y=400) + the parallel floor edge (y=0), 400 apart, with
        # a 400x900 label across them -> one edge_pair beam on the midline (y=200).
        recs = [_line("beam", 0, 400, 4000, 400),
                _line("slab_edge", 0, 0, 4000, 0)]
        label = _Lbl("B1", 400.0, 900.0, 2000, 200)
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        eb = _edge_beams(out)
        self.assertEqual(len(eb), 1)
        s = eb[0]
        self.assertEqual(s["mark"], "B1")
        self.assertAlmostEqual(s["width_mm"], 400.0, delta=2.0)
        self.assertAlmostEqual(s["depth_mm"], 900.0, delta=1.0)
        self.assertAlmostEqual((s["start"][1] + s["end"][1]) / 2.0 / _FT, 200.0, delta=2.0)

    def test_no_label_means_no_perimeter_beam(self):
        # The same geometry without a label must NOT invent a beam from a floor edge.
        recs = [_line("beam", 0, 400, 4000, 400),
                _line("slab_edge", 0, 0, 4000, 0)]
        out = report.build_beam_segments(recs, None, None, None, texts=None)
        self.assertEqual(_edge_beams(out), [])

    def test_slab_edges_alone_make_no_beam_without_label(self):
        # Two floor edges a beam-width apart but no label -> a real floor boundary, not a beam.
        recs = [_line("slab_edge", 0, 400, 4000, 400),
                _line("slab_edge", 0, 0, 4000, 0)]
        out = report.build_beam_segments(recs, None, None, None, texts=None)
        self.assertEqual(_edge_beams(out), [])

    def test_wrong_width_floor_edge_not_paired(self):
        # Floor edge 900 from the beam line but label width is 400 -> no match.
        recs = [_line("beam", 0, 900, 4000, 900),
                _line("slab_edge", 0, 0, 4000, 0)]
        label = _Lbl("B1", 400.0, 900.0, 2000, 450)
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        self.assertEqual(_edge_beams(out), [])

    def test_retraced_beam_is_not_doubled(self):
        # A beam drawn with BOTH edges on the beam layer (y=0 and y=400) -> one line_pair
        # beam. The floor outline re-traces the same two edges; the coincident edge pair
        # must be dropped, not placed as a second beam.
        recs = [_line("beam", 0, 0, 4000, 0),
                _line("beam", 0, 400, 4000, 400),
                _line("slab_edge", 0, 0, 4000, 0),
                _line("slab_edge", 0, 400, 4000, 400)]
        label = _Lbl("B1", 400.0, 900.0, 2000, 200)
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        self.assertEqual(len(_edge_beams(out)), 0)
        self.assertEqual(out["status_counts"].get("line_pair"), 1)

    def test_floor_edge_as_polyline_is_exploded(self):
        # The Revit link reader returns the floor outline as ONE polyline, not loose lines.
        # Its segments must still be available to pair with a lone beam line.
        recs = [_line("beam", 0, 400, 4000, 400),
                _Rec("slab_edge", (0, 0), (4000, 0), (4000, -3000))]   # L-shaped floor poly
        label = _Lbl("B1", 400.0, 900.0, 2000, 200)
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        eb = _edge_beams(out)
        self.assertEqual(len(eb), 1)             # paired with the polyline's y=0 segment
        self.assertEqual(eb[0]["mark"], "B1")

    def test_mark_only_beam_sized_from_schedule(self):
        # A mark-only beam label ("B1", no inline size) is sized from the schedule.
        recs = [_line("beam", 0, 0, 4000, 0),
                _line("beam", 0, 300, 4000, 300)]   # line_pair, 300 wide
        label = _Lbl("B1", None, None, 2000, 150)
        out = report.build_beam_segments(recs, None, None, None, texts=[label],
                                         schedule={"B1": (300.0, 600.0)})
        s = out["segments"][0]
        self.assertEqual(s["mark"], "B1")
        self.assertAlmostEqual(s["depth_mm"], 600.0, delta=1.0)   # from schedule

    def test_duplicate_mark_is_deduped(self):
        # Two parallel beams with a single label between them must not BOTH take the mark.
        recs = [_line("beam", 0, 0, 4000, 0),
                _line("beam", 0, 300, 4000, 300),       # beam A (y=150)
                _line("beam", 0, 1200, 4000, 1200),
                _line("beam", 0, 1500, 4000, 1500)]     # beam B (y=1350)
        label = _Lbl("B1", 300.0, 600.0, 2000, 200)     # nearest beam A
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        marked = [s for s in out["segments"] if s.get("mark") == "B1"]
        self.assertEqual(len(marked), 1)                # only the nearer beam keeps B1
        self.assertAlmostEqual((marked[0]["start"][1] + marked[0]["end"][1]) / 2.0 / _FT,
                               150.0, delta=5.0)


    def test_open_beam_polyline_edge_is_paired_not_dropped(self):
        # The link reader gives a beam's surviving edge as a short POLYLINE (kind polyline,
        # 2 pts), not a closed quad. It must feed the line pool, not be dropped as degenerate.
        beam_edge = _Rec("beam", (0, 400), (4000, 400))
        beam_edge.kind = "polyline"            # force the polyline path
        recs = [beam_edge, _line("slab_edge", 0, 0, 4000, 0)]
        label = _Lbl("B1", 400.0, 900.0, 2000, 200)
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        self.assertEqual(len(_edge_beams(out)), 1)
        self.assertEqual(_edge_beams(out)[0]["mark"], "B1")

    def test_same_width_labels_owned_by_nearest_not_first(self):
        # Two 300-wide edge beams + two 300x600 labels (B4 listed first). Each beam must go
        # to the label nearest IT, not be grabbed by whichever label is iterated first.
        recs = [_line("beam", 0, 300, 4000, 300), _line("slab_edge", 0, 0, 4000, 0),
                _line("beam", 0, 2300, 4000, 2300), _line("slab_edge", 0, 2000, 4000, 2000)]
        b4 = _Lbl("B4", 300.0, 600.0, 2000, 2150)   # near the upper pair (y=2150)
        b5 = _Lbl("B5", 300.0, 600.0, 2000, 150)    # near the lower pair (y=150)
        out = report.build_beam_segments(recs, None, None, None, texts=[b4, b5])
        eb = {s["mark"]: (s["start"][1] + s["end"][1]) / 2.0 / _FT for s in _edge_beams(out)}
        self.assertAlmostEqual(eb["B4"], 2150.0, delta=5.0)
        self.assertAlmostEqual(eb["B5"], 150.0, delta=5.0)


if __name__ == "__main__":
    unittest.main()

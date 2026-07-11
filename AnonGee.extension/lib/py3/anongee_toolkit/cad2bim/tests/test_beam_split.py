# -*- coding: utf-8 -*-
"""report.split_beams_at_columns -- no beam drawn ON TOP of a column (test8, client).

CAD draws a continuous beam outline straight over the columns it crosses; placed
verbatim that buries a beam inside every column on the run. A segment whose centreline
passes THROUGH a column footprint (both crossing points strictly inside the span) is
split into the pieces outside it, trimmed at the column faces. Junction ends that merely
reach INTO a column stay untouched, grazing a face never splits, sub-100 mm leftovers
(drafting overshoot) are dropped. Standalone (no Revit / no numpy).
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
    for name in ("_bsp", "_bsp.geom", "_bsp.classify"):
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

    load("_bsp.config", "config.py")
    load("_bsp.geom.shapes", "geom", "shapes.py")
    load("_bsp.classify.marks", "classify", "marks.py")
    load("_bsp.classify.layers", "classify", "layers.py")
    return load("_bsp.report", "report.py")


report = _load_report()


def _seg(x0, y0, x1, y1, mark=None):
    return {"start": [x0 * _FT, y0 * _FT, 0.0], "end": [x1 * _FT, y1 * _FT, 0.0],
            "width_mm": 300.0, "length_mm": abs(x1 - x0) + abs(y1 - y0),
            "mark": mark, "layer": "S-BEAM", "status": "outline"}


def _rect(cx, cy, w, h, deg):
    return {"center": [cx * _FT, cy * _FT, 0.0], "width_mm": float(w),
            "height_mm": float(h), "long_axis_deg": deg}


def _circle(cx, cy, dia):
    return {"center": [cx * _FT, cy * _FT, 0.0], "diameter_ft": dia * _FT}


def _sections(rects):
    return {"entries": [{"status": "x", "rectangles": rects}]}


def _ends_mm(seg):
    return (seg["start"][0] / _FT, seg["start"][1] / _FT,
            seg["end"][0] / _FT, seg["end"][1] / _FT)


class BeamSplitAtColumns(unittest.TestCase):

    # 400 wide (x, short) by 900 long (y): footprint x in [4800, 5200], y in [-450, 450]
    COL = _rect(5000, 0, 400, 900, 90.0)

    def test_through_beam_splits_at_column_faces(self):
        bs = {"segments": [_seg(0, 0, 10000, 0)]}
        n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
        self.assertEqual(n, 1)
        self.assertEqual(len(bs["segments"]), 2)
        a, b = bs["segments"]
        self.assertAlmostEqual(_ends_mm(a)[2], 4800.0, delta=1.0)   # trimmed at near face
        self.assertAlmostEqual(_ends_mm(b)[0], 5200.0, delta=1.0)   # resumes at far face
        self.assertAlmostEqual(_ends_mm(b)[2], 10000.0, delta=1.0)

    def test_junction_end_at_column_centre_untouched(self):
        # ends AT the column centre (the junction convention, and where the snap
        # pass puts ends) or within the margin past it: nothing moves
        for x_end in (4900, 5000, 5080):
            bs = {"segments": [_seg(0, 0, x_end, 0)]}
            n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
            self.assertEqual(n, 0)
            self.assertAlmostEqual(_ends_mm(bs["segments"][0])[2], float(x_end), delta=0.01)

    def test_end_at_far_face_trims_to_near_face(self):
        # drawn ACROSS the column to its far face (well past the centre):
        # trimmed back to the near face so nothing sits on the column
        bs = {"segments": [_seg(0, 0, 5200, 0)]}
        n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
        self.assertEqual(n, 1)
        self.assertEqual(len(bs["segments"]), 1)
        self.assertAlmostEqual(_ends_mm(bs["segments"][0])[2], 4800.0, delta=1.0)

    def test_beam_coextensive_with_column_dropped(self):
        # the column's own outline mis-read as a beam: buried face-to-face -> gone
        bs = {"segments": [_seg(4800, 0, 5200, 0)]}
        n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
        self.assertEqual(n, 1)
        self.assertEqual(len(bs["segments"]), 0)

    def test_overshoot_past_far_face_trims_to_near_face(self):
        # pokes only 50 mm past the far face: the stub is drafting overshoot, dropped
        bs = {"segments": [_seg(0, 0, 5250, 0)]}
        n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
        self.assertEqual(n, 1)
        self.assertEqual(len(bs["segments"]), 1)
        self.assertAlmostEqual(_ends_mm(bs["segments"][0])[2], 4800.0, delta=1.0)

    def test_beam_entirely_on_top_of_column_dropped(self):
        # pokes <100 mm out BOTH sides: the whole "beam" sits on the column
        bs = {"segments": [_seg(4750, 0, 5250, 0)]}
        n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
        self.assertEqual(n, 1)
        self.assertEqual(len(bs["segments"]), 0)

    def test_grazing_a_face_never_splits(self):
        # runs 5 mm inside the y=450 end face, parallel to it: grazing, not a crossing
        bs = {"segments": [_seg(0, 445, 10000, 445)]}
        n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
        self.assertEqual(n, 0)
        self.assertEqual(len(bs["segments"]), 1)

    def test_round_column_splits_at_circle(self):
        bs = {"segments": [_seg(0, 0, 10000, 0)]}
        n = report.split_beams_at_columns(bs, _sections([]), [_circle(5000, 0, 600)])
        self.assertEqual(n, 1)
        a, b = bs["segments"]
        self.assertAlmostEqual(_ends_mm(a)[2], 4700.0, delta=1.0)
        self.assertAlmostEqual(_ends_mm(b)[0], 5300.0, delta=1.0)

    def test_rotated_column_splits_at_skew_faces(self):
        # 400x900 at 45 deg: the beam along y=0 crosses the SHORT slab (|v| <= 200),
        # entering/leaving at 5000 -/+ 200*sqrt(2) = 282.8 mm
        bs = {"segments": [_seg(0, 0, 10000, 0)]}
        n = report.split_beams_at_columns(bs, _sections([_rect(5000, 0, 400, 900, 45.0)]), [])
        self.assertEqual(n, 1)
        a, b = bs["segments"]
        self.assertAlmostEqual(_ends_mm(a)[2], 5000.0 - 282.8, delta=1.0)
        self.assertAlmostEqual(_ends_mm(b)[0], 5000.0 + 282.8, delta=1.0)

    def test_mark_stays_on_longest_piece_only(self):
        bs = {"segments": [_seg(0, 0, 6000, 0, mark="B7")]}
        n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
        self.assertEqual(n, 1)
        a, b = bs["segments"]
        self.assertEqual(a["mark"], "B7")       # 4800 mm piece
        self.assertIsNone(b["mark"])            # 800 mm piece

    def test_two_columns_three_pieces(self):
        cols = [_rect(3000, 0, 400, 900, 90.0), _rect(7000, 0, 400, 900, 90.0)]
        bs = {"segments": [_seg(0, 0, 10000, 0, mark="B1")]}
        n = report.split_beams_at_columns(bs, _sections(cols), [])
        self.assertEqual(n, 1)
        self.assertEqual(len(bs["segments"]), 3)
        ends = [(_ends_mm(s)[0], _ends_mm(s)[2]) for s in bs["segments"]]
        for got, want in zip(ends, [(0, 2800), (3200, 6800), (7200, 10000)]):
            self.assertAlmostEqual(got[0], want[0], delta=1.0)
            self.assertAlmostEqual(got[1], want[1], delta=1.0)
        # the 3600 mm middle piece is the longest: it keeps the mark
        self.assertEqual([s["mark"] for s in bs["segments"]], [None, "B1", None])

    def test_untouched_dicts_are_reused_and_split_originals_unmutated(self):
        # script.py snapshots the segment list for slabs BEFORE splitting: kept
        # segments must be the same dicts, split ones must keep their original ends
        clear = _seg(0, 5000, 10000, 5000)
        through = _seg(0, 0, 10000, 0)
        bs = {"segments": [clear, through]}
        snapshot = list(bs["segments"])
        n = report.split_beams_at_columns(bs, _sections([self.COL]), [])
        self.assertEqual(n, 1)
        self.assertIs(bs["segments"][0], clear)
        self.assertAlmostEqual(_ends_mm(snapshot[1])[2], 10000.0, delta=0.01)

    def test_no_columns_no_change(self):
        bs = {"segments": [_seg(0, 0, 10000, 0)]}
        n = report.split_beams_at_columns(bs, _sections([]), [])
        self.assertEqual(n, 0)
        self.assertEqual(len(bs["segments"]), 1)


if __name__ == "__main__":
    unittest.main()

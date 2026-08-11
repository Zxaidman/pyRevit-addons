# -*- coding: utf-8 -*-
"""report.build_beam_segments -- beam DEPTH + mark come from the beam label.

A 2D plan outline gives a beam its WIDTH but not its DEPTH (the vertical dimension).
script.py now routes the beam-text layer and passes it in, so each detected segment is
sized from its nearest sized label: width = smaller value, depth = larger, plus the mark.
This locks that contract at the report level (script.py wiring can't run without Revit).
Standalone (no Revit / no numpy).
"""

import os
import sys
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_MM = 304.8
_FT = 1.0 / _MM


report = _loader.load("report")


class _Rec(object):
    """Minimal beam CurveRecord stand-in (build_beam_segments reads these attrs only)."""
    def __init__(self, kind, points_mm, layer="S-BEAM"):
        self.kind = kind
        self.category = "beam"                       # layers.CATEGORY_BEAM
        self.layer = layer
        self.points = [(x * _FT, y * _FT, 0.0) for (x, y) in points_mm]


class _Lbl(object):
    def __init__(self, mark, b_mm, h_mm, x_mm, y_mm):
        self.mark = mark
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


# A thin 4000 x 300 mm beam outline (closed quad) -> one centerline segment whose midpoint
# is (2000, 150) mm. Its label sits right on the midpoint.
def _beam_record():
    return _Rec("polyline", [(0, 0), (4000, 0), (4000, 300), (0, 300)])


class BeamTextSizing(unittest.TestCase):

    def test_depth_and_mark_applied_from_label(self):
        recs = [_beam_record()]
        label = _Lbl("B1", 300.0, 600.0, 2000, 150)
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        segs = out["segments"]
        self.assertEqual(len(segs), 1)
        s = segs[0]
        self.assertEqual(s.get("mark"), "B1")
        self.assertAlmostEqual(s["width_mm"], 300.0, delta=1.0)   # smaller label value
        self.assertAlmostEqual(s["depth_mm"], 600.0, delta=1.0)   # larger label value
        self.assertEqual(out["status_counts"].get("text_sized"), 1)

    def test_no_label_means_no_depth(self):
        recs = [_beam_record()]
        out = report.build_beam_segments(recs, None, None, None, texts=None)
        segs = out["segments"]
        self.assertEqual(len(segs), 1)
        self.assertIsNone(segs[0].get("depth_mm"))
        self.assertIsNone(segs[0].get("mark"))

    def test_far_label_not_applied(self):
        # A label outside mark_radius (1300 mm) must not size the segment.
        recs = [_beam_record()]
        label = _Lbl("B1", 300.0, 600.0, 2000, 5000)   # ~4850 mm away from midpoint
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        self.assertIsNone(out["segments"][0].get("depth_mm"))
        self.assertEqual(out["status_counts"].get("text_sized"), None)


if __name__ == "__main__":
    unittest.main()

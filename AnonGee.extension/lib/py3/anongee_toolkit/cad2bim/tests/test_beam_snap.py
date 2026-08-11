# -*- coding: utf-8 -*-
"""report.snap_beam_ends_to_columns -- close the beam/round-or-rotated-column gap.

A beam meeting an axis-aligned column butts a flat edge cleanly, but a ROUND column
(tangent) or a ROTATED column (skew edge) leaves a gap. When a beam END lands inside such
a column, its endpoint is pulled to the column centre. Axis-aligned columns are untouched,
and only endpoints move (never midspan). Standalone (no Revit / no numpy).
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


def _seg(x0, y0, x1, y1):
    return {"start": [x0 * _FT, y0 * _FT, 0.0], "end": [x1 * _FT, y1 * _FT, 0.0],
            "width_mm": 300.0, "length_mm": 1.0}


def _rect(cx, cy, w, h, deg):
    return {"center": [cx * _FT, cy * _FT, 0.0], "width_mm": float(w), "height_mm": float(h),
            "long_axis_deg": deg}


def _circle(cx, cy, dia):
    return {"center": [cx * _FT, cy * _FT, 0.0], "diameter_ft": dia * _FT}


class BeamEndSnap(unittest.TestCase):

    def _sections(self, rects):
        return {"entries": [{"status": "x", "rectangles": rects}]}

    def test_end_snaps_to_rotated_column_centre(self):
        sections = self._sections([_rect(5000, 5000, 400, 900, 45.0)])
        # beam ends ~200 mm shy of the rotated column centre
        bs = {"segments": [_seg(0, 5000, 4800, 5000)]}
        n = report.snap_beam_ends_to_columns(bs, sections, [])
        self.assertEqual(n, 1)
        self.assertAlmostEqual(bs["segments"][0]["end"][0] / _FT, 5000.0, delta=1.0)
        self.assertAlmostEqual(bs["segments"][0]["end"][1] / _FT, 5000.0, delta=1.0)

    def test_end_snaps_to_round_column_centre(self):
        sections = self._sections([])
        bs = {"segments": [_seg(0, 0, 9700, 0)]}    # ends near the round column at (10000,0)
        n = report.snap_beam_ends_to_columns(bs, sections, [_circle(10000, 0, 750)])
        self.assertEqual(n, 1)
        self.assertAlmostEqual(bs["segments"][0]["end"][0] / _FT, 10000.0, delta=1.0)

    def test_axis_aligned_column_not_snapped(self):
        sections = self._sections([_rect(5000, 5000, 400, 900, 0.0),
                                   _rect(5000, 5000, 400, 900, 90.0)])
        bs = {"segments": [_seg(0, 5000, 4800, 5000)]}
        n = report.snap_beam_ends_to_columns(bs, sections, [])
        self.assertEqual(n, 0)
        self.assertAlmostEqual(bs["segments"][0]["end"][0] / _FT, 4800.0, delta=1.0)

    def test_off_axis_column_extends_along_beam_axis(self):
        # A rotated column deliberately drawn OFF the beam's axis (Test11 grid I):
        # the end must slide ALONG the beam to the centre's station -- x stays put,
        # never onto the centre itself (that skewed the whole beam off its outline).
        sections = self._sections([_rect(5300, 10000, 400, 900, 45.0)])
        bs = {"segments": [_seg(5000, 5000, 5000, 9700)]}
        n = report.snap_beam_ends_to_columns(bs, sections, [])
        self.assertEqual(n, 1)
        end = bs["segments"][0]["end"]
        self.assertAlmostEqual(end[0] / _FT, 5000.0, delta=1.0)    # on its own axis
        self.assertAlmostEqual(end[1] / _FT, 10000.0, delta=1.0)   # at the centre's station

    def test_midspan_not_moved(self):
        # A beam passing THROUGH a rotated column (both ends far) keeps its endpoints.
        sections = self._sections([_rect(5000, 5000, 400, 900, 45.0)])
        bs = {"segments": [_seg(0, 5000, 10000, 5000)]}
        n = report.snap_beam_ends_to_columns(bs, sections, [])
        self.assertEqual(n, 0)


if __name__ == "__main__":
    unittest.main()

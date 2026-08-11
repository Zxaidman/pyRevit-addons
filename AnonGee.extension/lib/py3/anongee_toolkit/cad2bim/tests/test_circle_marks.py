# -*- coding: utf-8 -*-
"""report.apply_circle_marks -- name circular columns from the nearest label.

Test18 finding: round columns placed fine but never got their P18/P19 marks
(correct_columns_with_text only refines rectangles). Standalone (no Revit).
"""

import os
import sys
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_FT = 1.0 / 304.8


report = _loader.load("report")


class _Txt(object):
    def __init__(self, mark, x_mm, y_mm):
        self.mark = mark
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _circle(x_mm, y_mm, dia):
    return {"center": [x_mm * _FT, y_mm * _FT, 0.0], "diameter_mm": dia}


class ApplyCircleMarks(unittest.TestCase):

    def test_round_columns_adopt_nearest_mark(self):
        # Real Test18 geometry: circles at grid (11000,3000)/(11000,8000),
        # labels P19/P18 ~820 mm away; C4 is a far rectangle label.
        sections = {"circles": [_circle(11000, 3000, 900), _circle(11000, 8000, 750)]}
        texts = [_Txt("P19", 11358, 3742), _Txt("P18", 11398, 8663),
                 _Txt("C4", 11131, 11663)]
        named = report.apply_circle_marks(sections, texts, 1300.0 * _FT)
        self.assertEqual(named, 2)
        self.assertEqual(sections["circles"][0]["mark"], "P19")
        self.assertEqual(sections["circles"][1]["mark"], "P18")

    def test_label_out_of_radius_leaves_circle_unnamed(self):
        sections = {"circles": [_circle(0, 0, 600)]}
        named = report.apply_circle_marks(sections, [_Txt("P1", 5000, 5000)], 1300.0 * _FT)
        self.assertEqual(named, 0)
        self.assertNotIn("mark", sections["circles"][0])

    def test_no_texts_or_no_circles_is_noop(self):
        self.assertEqual(report.apply_circle_marks({"circles": []}, [_Txt("P1", 0, 0)], _FT), 0)
        self.assertEqual(report.apply_circle_marks({"circles": [_circle(0, 0, 600)]}, None, _FT), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

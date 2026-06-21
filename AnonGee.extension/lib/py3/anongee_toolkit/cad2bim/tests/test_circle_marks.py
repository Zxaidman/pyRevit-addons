# -*- coding: utf-8 -*-
"""report.apply_circle_marks -- name circular columns from the nearest label.

Test18 finding: round columns placed fine but never got their P18/P19 marks
(correct_columns_with_text only refines rectangles). Standalone (no Revit).
"""

import importlib.util
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_FT = 1.0 / 304.8


def _load_report():
    for name in ("_agr", "_agr.geom", "_agr.classify"):
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

    load("_agr.config", "config.py")
    load("_agr.geom.shapes", "geom", "shapes.py")
    load("_agr.classify.marks", "classify", "marks.py")
    load("_agr.classify.layers", "classify", "layers.py")
    return load("_agr.report", "report.py")


report = _load_report()


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

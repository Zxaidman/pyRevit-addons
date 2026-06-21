# -*- coding: utf-8 -*-
"""Fragmented lift/stair-core DETECTION (Test18 #1, advisory only).

report.detect_fragmented_cores flags a cluster of long parallel column lines ~one
wall-thickness apart that never closed into a column (the pre-redraw Test18 core),
so the user is told to redraw it as a closed polyline. It never places geometry.
Coordinates below are the REAL S-COLS wall lines extracted from the fragmented DXF.
Standalone (no Revit).
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
    for name in ("_agc", "_agc.geom", "_agc.classify"):
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

    load("_agc.config", "config.py")
    load("_agc.geom.shapes", "geom", "shapes.py")
    load("_agc.classify.marks", "classify", "marks.py")
    load("_agc.classify.layers", "classify", "layers.py")
    return load("_agc.report", "report.py")


report = _load_report()


def _line(x0, y0, x1, y1):
    return [(x0 * _FT, y0 * _FT, 0.0), (x1 * _FT, y1 * _FT, 0.0)]


class FragmentedCoreDetection(unittest.TestCase):

    def test_real_pre_redraw_core_is_flagged_once(self):
        # The actual S-COLS wall lines of the Test18 fragmented core:
        # left x=2850/3150, right x=7850/8150 (300 apart), top y=7850/8150.
        line_points = [
            _line(2850, 4550, 2850, 7850), _line(3150, 5450, 3150, 7850),  # left wall
            _line(7850, 3450, 7850, 7850), _line(8150, 3150, 8150, 7850),  # right wall
            _line(3150, 7850, 7850, 7850), _line(3150, 8150, 7850, 8150),  # top wall
            _line(4850, 2550, 7850, 2550), _line(4850, 3450, 7850, 3450),  # 900-apart opening
        ]
        warns = report.detect_fragmented_cores(line_points)
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0]["walls"], 3)            # 3 walls; the 900-gap pair excluded
        cx, cy = warns[0]["center_mm"]
        self.assertTrue(3000 <= cx <= 8000 and 5000 <= cy <= 8500)

    def test_normal_columns_no_long_lines_are_not_flagged(self):
        # Short column-edge lines (<= 900 mm) never reach the core length gate.
        line_points = [_line(0, 0, 900, 0), _line(0, 300, 900, 300),
                       _line(5000, 5000, 5000, 600)]
        self.assertEqual(report.detect_fragmented_cores(line_points), [])

    def test_single_long_wall_pair_is_not_a_core(self):
        # One isolated wall pair (< _CORE_MIN_WALLS) is not enough to warn.
        line_points = [_line(2850, 4550, 2850, 7850), _line(3150, 4550, 3150, 7850)]
        self.assertEqual(report.detect_fragmented_cores(line_points), [])

    def test_long_lines_too_far_apart_do_not_pair(self):
        # Parallel long lines 900 mm apart exceed the wall band -> no wall, no warning.
        line_points = [_line(0, 0, 0, 5000), _line(900, 0, 900, 5000),
                       _line(3000, 0, 3000, 5000), _line(3900, 0, 3900, 5000)]
        self.assertEqual(report.detect_fragmented_cores(line_points), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

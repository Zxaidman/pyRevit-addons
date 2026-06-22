# -*- coding: utf-8 -*-
"""Oriented-column and circular-column recovery (Test16 regressions).

Locks the three failure modes Test16 exposed, none of which the Test10 fix covered:
  * a full circle imported as a CLOSED tessellated loop (B7 round column),
  * a single near-closed outline stitched from one junction cut (C2 rotated column),
  * two fragments a beam-width-plus apart that must still cluster (C7 rotated column).

Standalone (no numpy / no Revit): shapes.py + config.py load by file path.
"""

import importlib.util
import math
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)


def _load_shapes():
    # Mirror the package tree so shapes' `from .. import config` resolves.
    for name in ("_ag2", "_ag2.geom"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod

    def _load(full, *parts):
        spec = importlib.util.spec_from_file_location(
            full, os.path.join(_PKG, *parts))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
        return mod

    _load("_ag2.config", "config.py")
    return _load("_ag2.geom.shapes", "geom", "shapes.py")


shapes = _load_shapes()
_MM = 304.8
_FT = 1.0 / _MM


def _ring(*pts_mm):
    return [(x * _FT, y * _FT, 0.0) for x, y in pts_mm]


def _short_long(rect):
    return (round(min(rect.width_ft, rect.height_ft) * _MM),
            round(max(rect.width_ft, rect.height_ft) * _MM))


class CircularRecovery(unittest.TestCase):

    @staticmethod
    def _tessellated_circle(cx, cy, dia, n, closed):
        r = dia / 2.0
        pts = [((cx + r * math.cos(2 * math.pi * k / n)) * _FT,
                (cy + r * math.sin(2 * math.pi * k / n)) * _FT, 0.0)
               for k in range(n)]
        if closed:
            pts.append(pts[0])    # last == first, as a Revit full-circle tessellates
        return type("Rec", (), {"points": pts})()

    def test_full_circle_closed_loop_recovers(self):
        # B7: the old (first, mid, last) triple was degenerate on a closed loop.
        rec = self._tessellated_circle(30000, 5000, 700, 24, closed=True)
        circles = shapes.build_circular_columns(
            [rec], min_dia_ft=150 * _FT, max_dia_ft=2000 * _FT)
        self.assertEqual(len(circles), 1)
        self.assertAlmostEqual(circles[0].diameter * _MM, 700, delta=2)
        self.assertAlmostEqual(circles[0].cx * _MM, 30000, delta=2)

    def test_three_point_arc_still_recovers(self):
        # A genuine 3-point arc record (the DXF path) must keep working.
        cx, cy, r = 1000, 2000, 300
        pts = [((cx + r * math.cos(a)) * _FT, (cy + r * math.sin(a)) * _FT, 0.0)
               for a in (0.0, math.radians(120), math.radians(240))]
        rec = type("Rec", (), {"points": pts})()
        circles = shapes.build_circular_columns(
            [rec], min_dia_ft=150 * _FT, max_dia_ft=2000 * _FT)
        self.assertEqual(len(circles), 1)
        self.assertAlmostEqual(circles[0].diameter * _MM, 600, delta=2)


class OrientedRecovery(unittest.TestCase):

    _GAP = 600 * _FT

    # C2: the import stitched the five outline lines into one open polyline.
    _C2 = [_ring((5251, 10172), (5103, 10489), (4559, 10236),
                 (4897, 9511), (5441, 9764), (5293, 10081))]
    # C7: two L-fragments left by a diagonal beam cut, ~450 mm apart.
    _C7 = [_ring((30177, 10331), (30103, 10489), (29559, 10236), (29595, 10159)),
           _ring((29789, 9743), (29897, 9511), (30441, 9764), (30367, 9923))]

    def test_single_near_closed_fragment_recovers(self):
        rects = shapes.recover_oriented_columns(self._C2, gap_ft=self._GAP)
        self.assertEqual(len(rects), 1)
        self.assertEqual(_short_long(rects[0]), (600, 800))

    def test_single_open_fragment_with_far_ends_is_ignored(self):
        # A lone open L whose ends are far apart is not a near-closed outline.
        far = [_ring((0, 0), (3000, 0), (3000, 200))]
        self.assertEqual(shapes.recover_oriented_columns(far, gap_ft=self._GAP), [])

    def test_two_fragments_cluster_only_within_gap(self):
        self.assertEqual(
            shapes.recover_oriented_columns(self._C7, gap_ft=400 * _FT), [])
        rects = shapes.recover_oriented_columns(self._C7, gap_ft=self._GAP)
        self.assertEqual(len(rects), 1)
        self.assertEqual(_short_long(rects[0]), (600, 800))

    def test_separate_columns_do_not_fuse(self):
        # Two real columns 1500 mm apart must stay two clusters at the 600 mm gap.
        a = _ring((0, 0), (400, 0), (400, 400), (0, 400), (0, 0))
        b = _ring((1900, 0), (2300, 0), (2300, 400), (1900, 400), (1900, 0))
        rects = shapes.recover_oriented_columns([a, b], gap_ft=self._GAP)
        self.assertEqual(len(rects), 2)

    # Real Test18 bottom-right corner: a clipped ROTATED rectangle left open ~804 mm.
    _CORNER = [_ring((11200, 46), (11290, 98), (11490, -248), (10710, -698), (10567, -450))]

    def test_wide_open_corner_recovers_only_past_widened_gap(self):
        # ~804 mm end-gap: ignored at the 600 mm gap, recovered once the lone-fragment
        # close gap widens to 900 mm (the clipped rotated corner-column case).
        self.assertEqual(
            shapes.recover_oriented_columns(self._CORNER, gap_ft=self._GAP), [])
        rects = shapes.recover_oriented_columns(
            self._CORNER, gap_ft=self._GAP, close_gap_ft=900 * _FT)
        self.assertEqual(len(rects), 1)

    def test_many_vertex_arc_is_not_rect_fitted(self):
        # A round column tessellated into a many-vertex near-closed polyline must NOT be
        # rect-fitted into a phantom column, even with the widened close gap.
        r, cx, cy = 450, 8000, 27700
        arc = [_ring(*[(cx + r * math.cos(2 * math.pi * k / 16),
                        cy + r * math.sin(2 * math.pi * k / 16)) for k in range(15)])]
        self.assertEqual(shapes.recover_oriented_columns(
            arc, gap_ft=self._GAP, close_gap_ft=900 * _FT), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

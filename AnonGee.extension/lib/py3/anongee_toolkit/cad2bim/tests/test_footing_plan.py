# -*- coding: utf-8 -*-
"""footing_plan -- where the foundation pads go and how deep.

Two decisions the Revit builder cannot make on its own: pads that OVERLAP must
fuse into one combined footing (Revit would otherwise stack two floors on top of
each other), and a pad's depth follows its plan area. Standalone (no Revit).
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


def _load():
    if "_fpl" not in sys.modules:
        module = types.ModuleType("_fpl")
        module.__path__ = []
        sys.modules["_fpl"] = module

    def load(full, *parts):
        spec = importlib.util.spec_from_file_location(full, os.path.join(_PKG, *parts))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        parent, child = full.rsplit(".", 1)
        setattr(sys.modules[parent], child, mod)
        spec.loader.exec_module(mod)
        return mod

    load("_fpl.config", "config.py")
    return load("_fpl.footing_plan", "footing_plan.py")


footing_plan = _load()


def _rect(cx, cy, width, height, deg=None, mark=None):
    out = {"center": [cx * _FT, cy * _FT, 0.0], "width_mm": float(width),
           "height_mm": float(height), "mark": mark}
    if deg is not None:
        out["long_axis_deg"] = deg
    return out


def _sections(rectangles, circles=None):
    return {"entries": [{"rectangles": list(rectangles)}],
            "circles": list(circles or [])}


class PadsFromColumns(unittest.TestCase):
    def test_a_pad_is_the_column_plus_the_projection_all_round(self):
        pads = footing_plan.pads_for(
            _sections([_rect(0, 0, 400, 600, 90.0, "C1")]), 300.0, 1500.0)
        self.assertEqual(len(pads), 1)
        pad = pads[0]
        self.assertAlmostEqual(2 * pad.half_long * _MM, 1200.0, places=3)
        self.assertAlmostEqual(2 * pad.half_short * _MM, 1000.0, places=3)
        self.assertAlmostEqual(pad.area_m2, 1.2, places=3)

    def test_a_round_column_gets_a_square_pad(self):
        pads = footing_plan.pads_for(
            _sections([], [{"center": [0.0, 0.0, 0.0], "diameter_mm": 600.0,
                            "mark": "C9"}]), 300.0, 1500.0)
        self.assertEqual(len(pads), 1)
        self.assertAlmostEqual(pads[0].half_long, pads[0].half_short)
        self.assertAlmostEqual(2 * pads[0].half_long * _MM, 1200.0, places=3)

    def test_a_lift_region_is_not_given_a_pad(self):
        pads = footing_plan.pads_for(
            _sections([_rect(0, 0, 2700, 3300)]), 300.0, 1500.0)
        self.assertEqual(pads, [])

    def test_the_pad_follows_the_columns_own_angle(self):
        pads = footing_plan.pads_for(
            _sections([_rect(0, 0, 400, 800, 30.0)]), 100.0, 1500.0)
        xs = [p[0] * _MM for p in pads[0].ring()]
        # a 30-degree pad is wider in X than its 600mm short side
        self.assertGreater(max(xs) - min(xs), 700.0)


class CombinedFootings(unittest.TestCase):
    """Two columns close together share ONE footing, not two stacked floors."""

    def test_overlapping_pads_fuse_into_one(self):
        pads = footing_plan.merge_overlapping(footing_plan.pads_for(
            _sections([_rect(0, 0, 400, 400, 0.0, "C1"),
                       _rect(800, 0, 400, 400, 0.0, "C2")]), 300.0, 1500.0))
        self.assertEqual(len(pads), 1)
        self.assertAlmostEqual(2 * pads[0].half_long * _MM, 1800.0, places=3)
        self.assertAlmostEqual(pads[0].cx * _MM, 400.0, places=3)
        self.assertEqual(pads[0].mark(), "F-C1+C2")

    def test_pads_that_clear_each_other_stay_apart(self):
        pads = footing_plan.merge_overlapping(footing_plan.pads_for(
            _sections([_rect(0, 0, 400, 400, 0.0, "C1"),
                       _rect(4000, 0, 400, 400, 0.0, "C2")]), 300.0, 1500.0))
        self.assertEqual(len(pads), 2)
        self.assertEqual(sorted(p.mark() for p in pads), ["F-C1", "F-C2"])

    def test_merging_is_transitive_across_a_row(self):
        pads = footing_plan.merge_overlapping(footing_plan.pads_for(
            _sections([_rect(x, 0, 400, 400, 0.0, "C%d" % i)
                       for i, x in enumerate((0, 800, 1600))]), 300.0, 1500.0))
        self.assertEqual(len(pads), 1)
        self.assertAlmostEqual(2 * pads[0].half_long * _MM, 2600.0, places=3)

    def test_a_merged_pad_can_reach_one_neither_parent_touched(self):
        pads = footing_plan.merge_overlapping(footing_plan.pads_for(
            _sections([_rect(0, 0, 400, 400, 0.0), _rect(800, 0, 400, 400, 0.0),
                       _rect(1750, 0, 400, 400, 0.0)]), 300.0, 1500.0))
        self.assertEqual(len(pads), 1)

    def test_a_mixed_orientation_group_falls_back_to_a_box(self):
        pads = footing_plan.merge_overlapping(footing_plan.pads_for(
            _sections([_rect(0, 0, 400, 800, 0.0), _rect(700, 0, 400, 800, 90.0)]),
            300.0, 1500.0))
        self.assertEqual(len(pads), 1)
        self.assertEqual(pads[0].angle_deg, 0.0)

    def test_a_single_pad_is_returned_unchanged(self):
        pads = footing_plan.pads_for(_sections([_rect(0, 0, 400, 400)]),
                                     300.0, 1500.0)
        self.assertIs(footing_plan.merge_overlapping(pads)[0], pads[0])


class DepthFromArea(unittest.TestCase):
    def test_the_nominal_depth_applies_at_one_square_metre(self):
        self.assertEqual(footing_plan.depth_for(1.0, 600.0), 600.0)

    def test_a_bigger_pad_is_deeper_and_a_smaller_one_thinner(self):
        self.assertGreater(footing_plan.depth_for(2.5, 600.0),
                           footing_plan.depth_for(1.0, 600.0))
        self.assertLess(footing_plan.depth_for(0.4, 600.0),
                        footing_plan.depth_for(1.0, 600.0))

    def test_depth_is_clamped_to_half_and_twice_the_nominal(self):
        self.assertEqual(footing_plan.depth_for(0.001, 600.0), 300.0)
        self.assertEqual(footing_plan.depth_for(400.0, 600.0), 1200.0)

    def test_depth_lands_on_a_buildable_50mm_step(self):
        for area in (0.3, 0.75, 1.1, 1.9, 3.3):
            depth = footing_plan.depth_for(area, 600.0)
            self.assertEqual(depth % 50.0, 0.0, "%s -> %s" % (area, depth))

    def test_a_zero_nominal_keeps_the_types_own_thickness(self):
        self.assertEqual(footing_plan.depth_for(2.0, 0.0), 0.0)


class ReadyToPlace(unittest.TestCase):
    def test_plan_pads_returns_ring_thickness_and_mark(self):
        plans = footing_plan.plan_pads(
            _sections([_rect(0, 0, 400, 400, 0.0, "C1"),
                       _rect(800, 0, 400, 400, 0.0, "C2"),
                       _rect(9000, 0, 400, 400, 0.0, "C3")]),
            300.0, 600.0, 1500.0)
        self.assertEqual(len(plans), 2)
        marks = sorted(mark for _ring, _t, mark in plans)
        self.assertEqual(marks, ["F-C1+C2", "F-C3"])
        for ring, thickness, _mark in plans:
            self.assertEqual(len(ring), 4)
            self.assertGreater(thickness, 0.0)

    def test_the_combined_pad_is_deeper_than_the_single_one(self):
        plans = dict((mark, t) for _r, t, mark in footing_plan.plan_pads(
            _sections([_rect(0, 0, 400, 400, 0.0, "C1"),
                       _rect(800, 0, 400, 400, 0.0, "C2"),
                       _rect(9000, 0, 400, 400, 0.0, "C3")]),
            300.0, 600.0, 1500.0))
        self.assertGreater(plans["F-C1+C2"], plans["F-C3"])


if __name__ == "__main__":
    unittest.main()

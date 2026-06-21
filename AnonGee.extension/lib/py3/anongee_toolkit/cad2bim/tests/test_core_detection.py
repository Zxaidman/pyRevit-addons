# -*- coding: utf-8 -*-
"""Fragmented lift/stair-core DETECTION (Test18 #1, advisory only).

report.detect_fragmented_cores flags a large UNCLOSED outline left on the column layer
that never placed (a lift/stair shaft drawn as disconnected segments), so the user is
told to redraw it as a closed polyline. It never places geometry.

The fixtures below are the REAL in-Revit `dropped_raw` geometry exported from the actual
runs (not the offline DXF reader, which faithlessly explodes the ring into separate
lines): the fragmented Test18 core comes through as ONE open-path polyline enclosing
~19 m^2, while a working plan (Test10) leaves only thin/low-area edge strips, and the
redrawn (fix) plan leaves no open path at all. Standalone (no Revit).
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


def _open_path(pts):
    return {"kind": "polyline", "layer": "S-COLS", "status": "open_path", "pts": pts}


def _line(pts):
    return {"kind": "line", "layer": "S-COLS", "pts": pts}


# The REAL fragmented Test18 core: a single open-path ring enclosing ~19.2 m^2.
FRAG_CORE_RING = _open_path([
    [4850, 3450], [7850, 3450], [7850, 7850], [3150, 7850],
    [3150, 5450], [3750, 5450], [3750, 4550], [3150, 4550],
])

# The three largest open paths a WORKING plan (Test10) leaves in dropped_raw -- all
# either thin (min bbox 300) or low-area (<3 m^2); none is a core.
TEST10_STRIPS = [
    _open_path([[20150, 26150], [7850, 26150], [7850, 26450],
                [11150, 26450], [16850, 26450]]),                  # 12300x300, 3.19 m^2
    _open_path([[7850, -150], [7850, 2850], [7850, 3150], [8150, 3150],
                [8150, -150], [10850, -150], [10850, 3150], [11150, 3150],
                [11150, -150], [16850, -150]]),                    # 9000x3300, 1.98 m^2
    _open_path([[16850, -150], [16850, 3150], [17150, 3150],
                [17150, -150], [19850, -150]]),                    # 3000x3300, 0.99 m^2
]

# The redrawn (fix) plan: the core placed, so dropped_raw is just two degenerate lines.
FIX_DROPPED = [_line([[12504, 1211], [12504, 1211]]),
               _line([[12853, 6483], [12853, 6483]])]


class _Rect(object):
    """Minimal placed-column stand-in (feet) for the centroid guard."""
    def __init__(self, x_min, y_min, x_max, y_max):
        self.x_min, self.y_min, self.x_max, self.y_max = x_min, y_min, x_max, y_max


class FragmentedCoreDetection(unittest.TestCase):

    def test_real_fragmented_core_is_flagged_once(self):
        warns = report.detect_fragmented_cores([FRAG_CORE_RING])
        self.assertEqual(len(warns), 1)
        self.assertAlmostEqual(warns[0]["area_m2"], 19.2, delta=0.3)
        cx, cy = warns[0]["center_mm"]
        self.assertTrue(3000 <= cx <= 8000 and 3500 <= cy <= 7900)

    def test_working_plan_strips_are_not_flagged(self):
        # Test10's leftover edge strips: thin or low-area -> no warning.
        self.assertEqual(report.detect_fragmented_cores(TEST10_STRIPS), [])

    def test_redrawn_fix_plan_has_no_warning(self):
        # Properly closed core places, leaving no open path at all.
        self.assertEqual(report.detect_fragmented_cores(FIX_DROPPED), [])

    def test_placed_core_is_suppressed_by_guard(self):
        # If the outline's centroid sits on an already-placed column, stay quiet.
        guard = [_Rect(14.0, 16.0, 17.0, 19.0)]   # feet, covers the ring centroid
        self.assertEqual(report.detect_fragmented_cores([FRAG_CORE_RING], guard), [])

    def test_thin_long_strip_below_min_bbox_is_ignored(self):
        # A 6000 x 300 sliver encloses area but is too thin to be a shaft.
        thin = _open_path([[0, 0], [6000, 0], [6000, 300], [0, 300]])
        self.assertEqual(report.detect_fragmented_cores([thin]), [])

    def test_small_2x2_shaft_is_flagged(self):
        # A modest 2000 x 2000 (4 m^2) shaft outline still trips the gate.
        ring = _open_path([[0, 0], [2000, 0], [2000, 2000], [0, 2000]])
        warns = report.detect_fragmented_cores([ring])
        self.assertEqual(len(warns), 1)
        self.assertAlmostEqual(warns[0]["area_m2"], 4.0, delta=0.1)


def _ftpath(pts_mm):
    return [(x * _FT, y * _FT, 0.0) for x, y in pts_mm]


class CoreWallRecovery(unittest.TestCase):
    """shapes.recover_core_walls rebuilds the real fragmented Test18 core's FIVE members
    from its loose faces (inner open ring + four outer face lines): the three perimeter
    walls (C6/C8/C10), the deep bottom member (C12, a 900 gap), and the notch member (C7).
    Each lands on its true centre (union span) and the stair opening stays empty."""

    # Inner ring (one open polyline) + the four outer face lines, one column-depth out.
    RING = _ftpath([[4850, 3450], [7850, 3450], [7850, 7850], [3150, 7850],
                    [3150, 5450], [3750, 5450], [3750, 4550], [3150, 4550]])
    OUTER = [_ftpath([[3150, 8150], [7850, 8150]]),   # top  (C6), 300 above inner y=7850
             _ftpath([[8150, 7850], [8150, 3150]]),   # right (C10), 300 right of x=7850
             _ftpath([[2850, 4550], [2850, 7850]]),   # left (C8), 300 left of x=3150
             _ftpath([[4850, 2550], [7850, 2550]])]   # bottom (C12), 900 below y=3450

    def _recover(self):
        pad = report._CORE_WALL_PAD_MM * _FT
        bbox = (3150 * _FT - pad, 3450 * _FT - pad, 7850 * _FT + pad, 7850 * _FT + pad)
        return report.shapes.recover_core_walls(
            [self.RING] + self.OUTER, bbox,
            80.0 * _FT, report._CORE_WALL_MAX_MM * _FT,
            report._CORE_WALL_OVERLAP_MM * _FT)

    def _members(self):
        out = set()
        for r in self._recover():
            small = round(min(r.width_ft, r.height_ft) * 304.8 / 50) * 50
            big = round(max(r.width_ft, r.height_ft) * 304.8 / 50) * 50
            cx = round((r.x_min + r.x_max) / 2.0 * 304.8 / 50) * 50
            cy = round((r.y_min + r.y_max) / 2.0 * 304.8 / 50) * 50
            out.add((small, big, cx, cy))
        return out

    def test_five_members_recovered_on_true_centres(self):
        got = self._members()
        self.assertEqual(len(got), 5)
        # (small, big, cx, cy): union span centres each member where the schedule wants
        self.assertIn((300, 4700, 5500, 8000), got)   # C6 top
        self.assertIn((300, 3300, 3000, 6200), got)   # C8 left  (not y=6650: union span)
        self.assertIn((300, 4700, 8000, 5500), got)   # C10 right (not y=5650)
        self.assertIn((600, 900, 3450, 5000), got)    # C7 notch member
        self.assertIn((900, 3000, 6350, 3000), got)   # C12 deep bottom member

    def test_stair_opening_stays_empty_no_phantom(self):
        # The stair opening (bottom-left, x 3150..4850) has no inner face: no member may
        # cover it, and no far face may span a notch into a phantom (smallest-gap-first).
        walls = self._recover()
        for r in walls:
            cx = (r.x_min + r.x_max) / 2.0
            cy = (r.y_min + r.y_max) / 2.0
            self.assertFalse(3150 * _FT < cx < 4850 * _FT and cy < 3450 * _FT)


if __name__ == "__main__":
    unittest.main(verbosity=2)

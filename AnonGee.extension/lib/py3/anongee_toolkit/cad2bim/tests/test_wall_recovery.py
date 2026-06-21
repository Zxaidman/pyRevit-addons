# -*- coding: utf-8 -*-
"""Thin-wall (lift/stair core) recovery via parallel-edge pairing (Test18 #1).

When beams clip a hollow core's outline the ring breaks into many open fragments;
the oriented-cluster pass would blob them into one solid rectangle over the
opening. recover_wall_columns instead pairs near-parallel edges ~one wall-thickness
apart into individual thin walls. Standalone (no numpy / no Revit).
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


def _load_shapes():
    for name in ("_agw", "_agw.geom"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod

    def _load(full, *parts):
        spec = importlib.util.spec_from_file_location(full, os.path.join(_PKG, *parts))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
        return mod

    _load("_agw.config", "config.py")
    return _load("_agw.geom.shapes", "geom", "shapes.py")


shapes = _load_shapes()


def _edge(x0, y0, x1, y1):
    """A single straight edge as a 2-point fragment, in feet."""
    return [(x0 * _FT, y0 * _FT, 0.0), (x1 * _FT, y1 * _FT, 0.0)]


class WallRecovery(unittest.TestCase):

    def test_single_wall_from_two_parallel_faces(self):
        # Two 2000-long faces 300 apart -> one 2000 x 300 wall on the midline.
        frags = [_edge(0, 0, 2000, 0), _edge(0, 300, 2000, 300)]
        rects, consumed = shapes.recover_wall_columns(frags)
        self.assertEqual(len(rects), 1)
        self.assertEqual(consumed, {0, 1})
        self.assertAlmostEqual(rects[0].short_len * _MM, 300, delta=5)
        self.assertAlmostEqual(rects[0].long_len * _MM, 2000, delta=5)
        self.assertAlmostEqual(rects[0].cy * _MM, 150, delta=5)

    def test_hollow_core_recovers_four_walls_not_one_blob(self):
        # 2000 x 3000 core, 300 walls: 8 face edges -> 4 thin walls (not a solid blob).
        frags = [
            _edge(0, 0, 2000, 0), _edge(0, 300, 2000, 300),        # bottom
            _edge(0, 3000, 2000, 3000), _edge(0, 2700, 2000, 2700),  # top
            _edge(0, 0, 0, 3000), _edge(300, 0, 300, 3000),        # left
            _edge(2000, 0, 2000, 3000), _edge(1700, 0, 1700, 3000),  # right
        ]
        rects, consumed = shapes.recover_wall_columns(frags)
        self.assertEqual(len(rects), 4)
        self.assertEqual(consumed, set(range(8)))
        for rect in rects:
            self.assertAlmostEqual(rect.short_len * _MM, 300, delta=5)
        longs = sorted(round(r.long_len * _MM) for r in rects)
        self.assertEqual(longs, [2000, 2000, 3000, 3000])

    def test_chunky_column_faces_too_far_apart_are_left_for_oriented_pass(self):
        # 900 x 900: faces 900 apart exceed the 700 max width band -> no pair.
        frags = [_edge(0, 0, 900, 0), _edge(0, 900, 900, 900)]
        rects, consumed = shapes.recover_wall_columns(frags)
        self.assertEqual(rects, [])
        self.assertEqual(consumed, set())

    def test_blocky_angled_column_below_aspect_is_left_for_oriented_pass(self):
        # 600-wide x 900-long pairs within the band, but ratio 1.5 < 2.5 -> the
        # aspect guard leaves it for the oriented pass (avoids undersizing it).
        frags = [_edge(0, 0, 900, 0), _edge(0, 600, 900, 600)]
        rects, consumed = shapes.recover_wall_columns(frags)
        self.assertEqual(rects, [])
        self.assertEqual(consumed, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)

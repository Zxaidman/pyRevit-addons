# -*- coding: utf-8 -*-
"""report.build_beam_segments -- CURVED beam detection (concentric arc pairs).

A curved beam is drawn as two concentric edges, each a chain of many short arc fragments
(inner + outer, one beam width apart). The fragments are clustered into edges, an inner/
outer pair becomes one curved member spanning the chain's swept angle, and its depth+mark
come from the nearest sized label. Round-column junction fillets (single radius, centred on
a detected circle) must NOT become beams. Standalone (no Revit / no numpy).
"""

import importlib.util
import math
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_MM = 304.8
_FT = 1.0 / _MM


def _load_report():
    for name in ("_cb", "_cb.geom", "_cb.classify"):
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

    load("_cb.config", "config.py")
    load("_cb.geom.shapes", "geom", "shapes.py")
    load("_cb.classify.marks", "classify", "marks.py")
    load("_cb.classify.layers", "classify", "layers.py")
    return load("_cb.report", "report.py")


report = _load_report()


class _Rec(object):
    def __init__(self, kind, points_mm):
        self.kind = kind
        self.category = "beam"
        self.layer = "S-BEAM"
        self.points = [(x * _FT, y * _FT, 0.0) for (x, y) in points_mm]


class _Lbl(object):
    def __init__(self, mark, b_mm, h_mm, x_mm, y_mm):
        self.mark = mark
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _pt(cx, cy, r, deg):
    a = math.radians(deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def _arc_fragments(cx, cy, r, deg_from, deg_to, n=6):
    """n short 3-point arc records sampling radius r from deg_from..deg_to."""
    recs = []
    step = (deg_to - deg_from) / float(n)
    a = deg_from
    while a < deg_to - 1e-9:
        b = a + step
        recs.append(_Rec("arc", [_pt(cx, cy, r, a), _pt(cx, cy, r, (a + b) / 2.0),
                                 _pt(cx, cy, r, b)]))
        a = b
    return recs


# A curved beam centred at (0,0): inner edge r=2000, outer r=2300 (width 300, centreline
# 2150), each a 6-fragment chain over the top semicircle 0..180 deg.
def _curved_beam_records():
    return (_arc_fragments(0, 0, 2000, 0, 180, 6)
            + _arc_fragments(0, 0, 2300, 0, 180, 6))


class CurvedBeams(unittest.TestCase):

    def test_concentric_pair_becomes_one_curved_beam(self):
        recs = _curved_beam_records()
        out = report.build_beam_segments(recs, None, None, None, texts=None)
        cs = out["curved_segments"]
        self.assertEqual(len(cs), 1)
        s = cs[0]
        self.assertAlmostEqual(s["center"][0] / _FT, 0, delta=2.0)
        self.assertAlmostEqual(s["center"][1] / _FT, 0, delta=2.0)
        self.assertAlmostEqual(s["radius_mm"], 2150, delta=2.0)   # centreline radius
        self.assertAlmostEqual(s["width_mm"], 300, delta=2.0)     # edge gap
        # swept the populated semicircle, not the empty half
        self.assertAlmostEqual(s["start_deg"], 0.0, delta=1.0)
        self.assertAlmostEqual(s["end_deg"], 180.0, delta=1.0)
        self.assertEqual(out["status_counts"].get("curved_pair"), 1)
        self.assertEqual(out["status_counts"].get("arc_lone"), None)  # all consumed

    def test_depth_and_mark_from_nearest_label(self):
        recs = _curved_beam_records()
        # midpoint of the centreline arc is at angle 90 deg -> (0, 2150) mm
        label = _Lbl("BC", 300.0, 900.0, 0, 2150)
        out = report.build_beam_segments(recs, None, None, None, texts=[label])
        s = out["curved_segments"][0]
        self.assertEqual(s.get("mark"), "BC")
        self.assertAlmostEqual(s["depth_mm"], 900.0, delta=1.0)
        self.assertAlmostEqual(s["width_mm"], 300.0, delta=2.0)   # width stays geometric

    def test_single_edge_makes_no_curved_beam(self):
        # Only one radius present (no concentric partner) -> no curved beam, arcs are lone.
        recs = _arc_fragments(0, 0, 2000, 0, 180, 6)
        out = report.build_beam_segments(recs, None, None, None, texts=None)
        self.assertEqual(out["curved_segments"], [])
        self.assertEqual(out["status_counts"].get("curved_pair"), None)

    def test_junction_fillets_not_paired_into_a_beam(self):
        # Two arc rings centred on a round column (a junction) -- one is the column edge.
        # Concentric, but the inner ring sits ON the circle, so _is_junction drops it; the
        # remaining ring has no partner -> no spurious curved beam.
        circles = [{"center": [0.0, 0.0, 0.0], "diameter_mm": 4000.0}]
        recs = (_arc_fragments(0, 0, 2000, 0, 180, 6)     # r=2000 ~ column edge (junction)
                + _arc_fragments(0, 0, 2300, 0, 180, 6))
        out = report.build_beam_segments(recs, circles, None, None, texts=None)
        self.assertEqual(out["curved_segments"], [])


if __name__ == "__main__":
    unittest.main()

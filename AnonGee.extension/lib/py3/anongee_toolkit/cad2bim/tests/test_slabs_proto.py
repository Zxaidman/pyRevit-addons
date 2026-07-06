# -*- coding: utf-8 -*-
"""slabs_proto -- slab loops from the slab-edge layer OR the beam-perimeter graph.

The prototype's two outline sources and its label sizing are exercised on synthetic
plans: a 2x2 beam grid must yield exactly 4 bounded faces (the outer face and the
junction slivers never become slabs); a closed slab-edge polyline is taken as drawn;
loose edge lines chain into a ring; labels size/name a loop from inside it, with
mark-only labels resolving thickness through the schedule. Standalone (no Revit).
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
    for name in ("_slb", "_slb.geom", "_slb.classify"):
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

    load("_slb.config", "config.py")
    load("_slb.classify.layers", "classify", "layers.py")
    return load("_slb.slabs_proto", "slabs_proto.py")


slabs_proto = _load()
layers = sys.modules["_slb.classify.layers"]


def _seg(x0, y0, x1, y1):
    return {"start": [x0 * _FT, y0 * _FT, 0.0], "end": [x1 * _FT, y1 * _FT, 0.0]}


class _Text(object):
    def __init__(self, text, x_mm, y_mm):
        self.text = text
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


class _Record(object):
    def __init__(self, points_mm, closed=False):
        pts = list(points_mm)
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        self.points = [(x * _FT, y * _FT, 0.0) for x, y in pts]
        self.category = layers.CATEGORY_SLAB_EDGE


class BeamGraphFaces(unittest.TestCase):
    def _grid(self):
        # 2x2 bays: grid lines x,y in {0, 5000, 10000}, beams span the full 10 m.
        segs = []
        for v in (0.0, 5000.0, 10000.0):
            segs.append(_seg(0, v, 10000, v))
            segs.append(_seg(v, 0, v, 10000))
        return segs

    def test_two_by_two_grid_gives_four_bays(self):
        loops = slabs_proto.slab_loops_from_beam_graph(self._grid())
        self.assertEqual(len(loops), 4)
        areas = sorted(abs(slabs_proto._signed_area(r)) * _MM * _MM / 1e6
                       for r, _z in loops)
        for a in areas:
            self.assertAlmostEqual(a, 25.0, delta=0.5)   # 5 m x 5 m bays

    def test_crossing_beams_split_at_intersection(self):
        # A plus sign inside a square: the crossing point is NOT an endpoint.
        segs = [_seg(0, 0, 8000, 0), _seg(8000, 0, 8000, 8000),
                _seg(8000, 8000, 0, 8000), _seg(0, 8000, 0, 0),
                _seg(0, 4000, 8000, 4000), _seg(4000, 0, 4000, 8000)]
        loops = slabs_proto.slab_loops_from_beam_graph(segs)
        self.assertEqual(len(loops), 4)

    def test_open_ends_make_no_face(self):
        segs = [_seg(0, 0, 5000, 0), _seg(5000, 0, 5000, 5000)]   # an L, not a loop
        self.assertEqual(slabs_proto.slab_loops_from_beam_graph(segs), [])


class SlabEdgeLoops(unittest.TestCase):
    def test_closed_polyline_is_a_ring(self):
        rec = _Record([(0, 0), (6000, 0), (6000, 4000), (0, 4000)], closed=True)
        loops = slabs_proto.slab_loops_from_edges([rec])
        self.assertEqual(len(loops), 1)
        self.assertEqual(len(loops[0][0]), 4)

    def test_loose_lines_chain_into_a_ring(self):
        recs = [_Record([(0, 0), (6000, 0)]),
                _Record([(6000, 0), (6000, 4000)]),
                _Record([(6000, 4000), (0, 4000)]),
                _Record([(0, 4000), (0, 0)])]
        loops = slabs_proto.slab_loops_from_edges(recs)
        self.assertEqual(len(loops), 1)

    def test_open_chain_is_dropped(self):
        recs = [_Record([(0, 0), (6000, 0)]), _Record([(6000, 0), (6000, 4000)])]
        self.assertEqual(slabs_proto.slab_loops_from_edges(recs), [])


class SlabLabels(unittest.TestCase):
    def _one_loop(self):
        ring = [(0.0, 0.0), (5000 * _FT, 0.0), (5000 * _FT, 5000 * _FT),
                (0.0, 5000 * _FT)]
        return [(ring, 0.0)]

    def test_inline_label_names_and_sizes(self):
        slabs = slabs_proto.apply_slab_labels(
            self._one_loop(), [_Text("S1 150 THK", 2500, 2500)])
        self.assertEqual(slabs[0]["mark"], "S1")
        self.assertEqual(slabs[0]["thickness_mm"], 150.0)

    def test_mark_only_label_resolves_via_schedule(self):
        slabs = slabs_proto.apply_slab_labels(
            self._one_loop(), [_Text("S3", 2500, 2500)], schedule={"S3": 125.0})
        self.assertEqual(slabs[0]["mark"], "S3")
        self.assertEqual(slabs[0]["thickness_mm"], 125.0)

    def test_label_outside_loop_is_ignored(self):
        slabs = slabs_proto.apply_slab_labels(
            self._one_loop(), [_Text("S1 150 THK", 9000, 9000)])
        self.assertIsNone(slabs[0]["mark"])
        self.assertIsNone(slabs[0]["thickness_mm"])

    def test_parse_variants(self):
        self.assertEqual(slabs_proto.parse_slab_label("S2 200 THK"), ("S2", 200.0))
        self.assertEqual(slabs_proto.parse_slab_label("150 thk"), (None, 150.0))
        self.assertEqual(slabs_proto.parse_slab_label("S7"), ("S7", None))
        self.assertEqual(slabs_proto.parse_slab_label("hello"), (None, None))


if __name__ == "__main__":
    unittest.main()

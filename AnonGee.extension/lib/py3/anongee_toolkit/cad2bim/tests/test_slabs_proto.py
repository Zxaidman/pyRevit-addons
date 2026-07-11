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
    load("_slb.geom.shapes", "geom", "shapes.py")
    load("_slb.classify.layers", "classify", "layers.py")
    return load("_slb.slabs_proto", "slabs_proto.py")


slabs_proto = _load()
layers = sys.modules["_slb.classify.layers"]


def _seg(x0, y0, x1, y1, w=0.0):
    return {"start": [x0 * _FT, y0 * _FT, 0.0], "end": [x1 * _FT, y1 * _FT, 0.0],
            "width_mm": w}


class _Text(object):
    def __init__(self, text, x_mm, y_mm):
        self.text = text
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


class _Record(object):
    def __init__(self, points_mm, closed=False, kind="polyline"):
        pts = list(points_mm)
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        self.points = [(x * _FT, y * _FT, 0.0) for x, y in pts]
        self.category = layers.CATEGORY_SLAB_EDGE
        self.kind = kind


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
                       for r, _z, _a in loops)
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


class InsetGraph(unittest.TestCase):
    def test_faces_inset_to_the_beam_faces(self):
        # one 5x5 m bay of 300-wide beams: the slab must stop at the beam FACES,
        # i.e. a 4.7 x 4.7 m panel, not the 5 x 5 centreline face
        segs = [_seg(0, 0, 5000, 0, 300), _seg(5000, 0, 5000, 5000, 300),
                _seg(5000, 5000, 0, 5000, 300), _seg(0, 5000, 0, 0, 300)]
        loops = slabs_proto.slab_loops_from_beam_graph(segs)
        self.assertEqual(len(loops), 1)
        ring, _z, _arcs = loops[0]
        area = abs(slabs_proto._signed_area(ring)) * _MM * _MM / 1e6
        self.assertAlmostEqual(area, 4.7 * 4.7, delta=0.1)
        xs = sorted(p[0] * _MM for p in ring)
        self.assertAlmostEqual(xs[0], 150.0, delta=5.0)      # inset off the centreline

    def test_mixed_widths_inset_per_edge(self):
        # left beam 600 wide, the rest 300: the left edge insets 300, others 150
        segs = [_seg(0, 0, 5000, 0, 300), _seg(5000, 0, 5000, 5000, 300),
                _seg(5000, 5000, 0, 5000, 300), _seg(0, 5000, 0, 0, 600)]
        loops = slabs_proto.slab_loops_from_beam_graph(segs)
        self.assertEqual(len(loops), 1)
        xs = sorted(p[0] * _MM for p in loops[0][0])
        self.assertAlmostEqual(xs[0], 300.0, delta=5.0)


class MemberEdgeFaces(unittest.TestCase):
    class _Rec(object):
        def __init__(self, pts_mm, category):
            self.points = [(x * _FT, y * _FT, 0.0) for x, y in pts_mm]
            self.category = category
            self.kind = "line"

    def _edge_pair(self, x0, y0, x1, y1, width):
        import math as _m
        dx, dy = x1 - x0, y1 - y0
        ln = _m.hypot(dx, dy)
        nx, ny = -dy / ln * width / 2.0, dx / ln * width / 2.0
        mk = lambda pts: self._Rec(pts, layers.CATEGORY_BEAM)
        return [mk([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny)]),
                mk([(x0 - nx, y0 - ny), (x1 - nx, y1 - ny)])]

    def test_drawn_edges_bound_the_panel_exactly(self):
        # a 5x5 m bay of 300-wide beams DRAWN as edge pairs: the inner edges bound
        # a 4.7 x 4.7 panel face; the beam-body strips must NOT become panels
        recs = []
        recs += self._edge_pair(0, 0, 5000, 0, 300)
        recs += self._edge_pair(5000, 0, 5000, 5000, 300)
        recs += self._edge_pair(5000, 5000, 0, 5000, 300)
        recs += self._edge_pair(0, 5000, 0, 0, 300)
        loops = slabs_proto.slab_loops_from_member_edges(recs)
        areas = sorted(abs(slabs_proto._signed_area(r)) * _MM * _MM / 1e6
                       for r, _z, _a in loops)
        self.assertEqual(len(areas), 1)              # only the panel, no body strips
        self.assertAlmostEqual(areas[0], 4.7 * 4.7, delta=0.2)


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
        # underscore join, the fixtures' actual convention ("S7_150 THK.")
        self.assertEqual(slabs_proto.parse_slab_label("S7_150 THK."), ("S7", 150.0))
        self.assertEqual(slabs_proto.parse_slab_label("S12_125 thk"), ("S12", 125.0))

    def test_schedule_tuple_entry_reads_thickness(self):
        # parse_schedule stores a slab row as (thk, thk); entry[0] is the thickness
        slabs = slabs_proto.apply_slab_labels(
            self._one_loop(), [_Text("S3", 2500, 2500)], schedule={"S3": (125.0, 125.0)})
        self.assertEqual(slabs[0]["thickness_mm"], 125.0)


if __name__ == "__main__":
    unittest.main()

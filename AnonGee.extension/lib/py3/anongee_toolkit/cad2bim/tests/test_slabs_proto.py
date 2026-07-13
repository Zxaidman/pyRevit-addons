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

    def test_edge_tip_near_ring_corner_still_bounds(self):
        # THE test4/5 leak: an edge tip landing 44 mm from a column ring corner
        # rounded into a DIFFERENT 50 mm grid cell, dangled, was pruned -- and the
        # bay face flooded over the beam body. Neighbour-cell clustering must weld
        # tip and corner into one node so the edge keeps bounding its bay.
        a = (1.0, 1.0)
        b = (1.0 + 0.144, 1.0)                       # 44 mm right of a cell edge
        segs = [((0.0, 0.0), a), (a, b)]             # chain broken at a? no: shared
        key, nodes = slabs_proto._cluster_nodes(
            [(0.0, 0.0), a, (1.1444, 1.0), b], 0.164)   # 50 mm in ft
        self.assertEqual(key(a), key((1.1444, 1.0)))    # 44 mm apart: same node
        self.assertNotEqual(key((0.0, 0.0)), key(a))

    def test_cluster_chain_does_not_collapse_arc(self):
        # transitive chains must NOT swallow a run of closely-spaced arc chords
        pts = [(i * 0.10, 0.0) for i in range(10)]      # 30 mm steps, 270 mm run
        key, nodes = slabs_proto._cluster_nodes(pts, 0.164)
        self.assertGreater(len(set(key(p) for p in pts)), 3)

    def test_small_arc_tessellates_with_chords_above_snap(self):
        # a 90-degree fillet of 400 mm radius: 16 fixed chords would be ~39 mm --
        # inside the node snap, so the graph would chain-merge them. Adaptive
        # tessellation keeps chords >= ~2x snap.
        r = 400.0 * _FT
        pts = [(r, 0.0, 0.0),
               (r * 0.7071, r * 0.7071, 0.0),
               (0.0, r, 0.0)]
        chords, triple = slabs_proto._tessellate_arc(pts)
        self.assertIsNotNone(triple)
        step = ((chords[1][0] - chords[0][0]) ** 2 +
                (chords[1][1] - chords[0][1]) ** 2) ** 0.5
        self.assertGreaterEqual(step * _MM, 95.0)

    def test_wide_beam_body_corridor_dropped_by_coverage(self):
        # a 900-wide beam's body strip beats the mean-width floor and its
        # perimeter is 100% beam edges -- only AREA coverage identifies it
        recs = []
        recs += self._edge_pair(0, 0, 5000, 0, 900)         # the wide beam
        recs += self._edge_pair(5000, 0, 5000, 5000, 300)
        recs += self._edge_pair(5000, 5000, 0, 5000, 300)
        recs += self._edge_pair(0, 5000, 0, 0, 300)
        segs = [{"start": [0.0, 0.0, 0.0], "end": [5000 * _FT, 0.0, 0.0],
                 "width_mm": 900.0},
                {"start": [5000 * _FT, 0.0, 0.0], "end": [5000 * _FT, 5000 * _FT, 0.0],
                 "width_mm": 300.0},
                {"start": [5000 * _FT, 5000 * _FT, 0.0], "end": [0.0, 5000 * _FT, 0.0],
                 "width_mm": 300.0},
                {"start": [0.0, 5000 * _FT, 0.0], "end": [0.0, 0.0, 0.0],
                 "width_mm": 300.0}]
        loops = slabs_proto.slab_loops_from_member_edges(recs, beam_segments=segs)
        areas = sorted(abs(slabs_proto._signed_area(r)) * _MM * _MM / 1e6
                       for r, _z, _a in loops)
        # the 900-wide body strip (5.0 x 0.9 = 4.5 m2 > 1 m2 floor) must be gone;
        # only the panel remains
        self.assertEqual(len(areas), 1)
        self.assertGreater(areas[0], 15.0)

    def test_round_column_fragments_replaced_by_clean_ring(self):
        # a round column drawn as tiny arc fragments: with a circle footprint the
        # junk is swallowed and the bay corner is trimmed by one clean ring
        import math as _m
        recs = []
        recs += self._edge_pair(0, 0, 5000, 0, 300)
        recs += self._edge_pair(5000, 0, 5000, 5000, 300)
        recs += self._edge_pair(5000, 5000, 0, 5000, 300)
        recs += self._edge_pair(0, 5000, 0, 0, 300)
        r = 300.0
        for k in range(12):                       # broken 30-deg arc fragments
            a0 = 2.0 * _m.pi * k / 12.0
            a1 = 2.0 * _m.pi * (k + 1) / 12.0
            am = (a0 + a1) / 2.0
            pts = [(r * _m.cos(a), r * _m.sin(a)) for a in (a0, am, a1)]
            rec = self._Rec(pts, layers.CATEGORY_COLUMN)
            rec.kind = "arc"
            recs.append(rec)
        circle = ("circle", 0.0, 0.0, r * _FT)
        loops = slabs_proto.slab_loops_from_member_edges(recs, column_rects=[circle])
        areas = sorted(abs(slabs_proto._signed_area(rg)) * _MM * _MM / 1e6
                       for rg, _z, _a in loops)
        self.assertEqual(len(areas), 1)
        self.assertAlmostEqual(areas[0], 4.7 * 4.7, delta=0.3)   # corner wrap trimmed

    def test_column_rects_replace_raw_linework_and_trim(self):
        # a drawn column outline WITH a diagonal marker stroke sits on the bay
        # corner; with column_rects the raw linework (incl. the diagonal) is
        # swallowed and the exact ring trims the corner -- one clean panel, and
        # no face leaks across the beam bodies
        recs = []
        recs += self._edge_pair(0, 0, 5000, 0, 300)
        recs += self._edge_pair(5000, 0, 5000, 5000, 300)
        recs += self._edge_pair(5000, 5000, 0, 5000, 300)
        recs += self._edge_pair(0, 5000, 0, 0, 300)
        # drawn column outline at the (0,0) junction, retraced with a diagonal
        col = [(-300, -300), (300, -300), (300, 300), (-300, 300), (-300, -300),
               (300, 300)]
        col_rec = self._Rec(col, layers.CATEGORY_COLUMN)
        col_rec.kind = "polyline"
        recs.append(col_rec)
        rect = ("rect", 0.0, 0.0, 1.0, 0.0, 300 * _FT, 300 * _FT)
        loops = slabs_proto.slab_loops_from_member_edges(recs, column_rects=[rect])
        areas = sorted(abs(slabs_proto._signed_area(r)) * _MM * _MM / 1e6
                       for r, _z, _a in loops)
        self.assertEqual(len(areas), 1)
        # the column ring clips the bay corner: slightly under the full 4.7 x 4.7
        self.assertAlmostEqual(areas[0], 4.7 * 4.7, delta=0.3)


class PlacedMemberFaces(unittest.TestCase):
    """Faces synthesized from the PLACED beams/columns (the user-proposed source)."""

    def _seg(self, x0, y0, x1, y1, w=300.0):
        return {"start": [x0 * _FT, y0 * _FT, 0.0], "end": [x1 * _FT, y1 * _FT, 0.0],
                "width_mm": w}

    def _bay_segments(self):
        return [self._seg(0, 0, 5000, 0), self._seg(5000, 0, 5000, 5000),
                self._seg(5000, 5000, 0, 5000), self._seg(0, 5000, 0, 0)]

    def test_bay_bounded_by_synthesized_edges(self):
        loops = slabs_proto.slab_loops_from_placed_members([], self._bay_segments())
        areas = [abs(slabs_proto._signed_area(r)) * _MM * _MM / 1e6
                 for r, _z, _a in loops]
        self.assertEqual(len(areas), 1)
        self.assertAlmostEqual(areas[0], 4.7 * 4.7, delta=0.2)

    def test_boundary_stays_exactly_on_beam_edge(self):
        # cluster nodes PREFER beam-edge points: the bay edge must sit at exactly
        # centreline - w/2, not drift toward column-ring vertices
        rect = ("rect", 0.0, 0.0, 1.0, 0.0, 300 * _FT, 300 * _FT)
        loops = slabs_proto.slab_loops_from_placed_members(
            [], self._bay_segments(), column_rects=[rect])
        self.assertEqual(len(loops), 1)
        ring = loops[0][0]
        ys = sorted(set(round(y * _MM, 1) for _x, y in ring))
        self.assertIn(150.0, ys)             # bottom edge exactly at w/2
        self.assertIn(4850.0, ys)            # top edge exactly at 5000 - w/2

    def test_round_column_wrap_gets_true_arc(self):
        circle = ("circle", 0.0, 0.0, 400 * _FT)
        loops = slabs_proto.slab_loops_from_placed_members(
            [], self._bay_segments(), column_rects=[circle])
        self.assertEqual(len(loops), 1)
        ring, _z, arcs = loops[0]
        self.assertGreaterEqual(len(arcs), 1)          # wrap emitted as a triple
        a, m, b = arcs[0]
        for p in (a, m, b):                             # all three ON the circle
            r_mm = ((p[0] ** 2 + p[1] ** 2) ** 0.5) * _MM
            self.assertAlmostEqual(r_mm, 400.0, delta=2.0)


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

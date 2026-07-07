# -*- coding: utf-8 -*-
"""Beam STRESS suite -- every failure mode from Test9-19 in one synthetic plan.

Part 1 runs the REAL pipeline (dxf_reader -> layers -> build_beam_segments) over
fixtures/cad/StressPlan-Beams.dxf (regenerate with fixtures/make_stress_plan.py) and
asserts each zone's beam arrives with the right geometry, size and mark:
    Z1 baseline ring w/ rotated vertical labels        Z5 perimeter beam via A-FLOR
    Z2 sloped 4-deg beam (bbox once flattened it)      Z6 stacked-label mark theft
    Z3 diagonal 45-deg beam                            Z7 curved beam (arc chains)
    Z4 900-wide beam + continuation merge              Z8 junk fabricates nothing

Part 2 feeds synthetic POLYLINES (the Revit LINK reader's shapes, which a DXF cannot
carry) straight into build_beam_segments: the U-snake chaining two grid beams' facing
edges, the open snake whose last leg is collinear with the fabricated closing edge,
and the skewed snake between rotated columns. Standalone (needs ezdxf for part 1).
"""

import importlib.util
import math
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_DXF = os.path.join(_HERE, "fixtures", "cad", "StressPlan-Beams.dxf")
_MM = 304.8
_FT = 1.0 / _MM


def _load():
    for name in ("_bst", "_bst.geom", "_bst.classify", "_bst.readers"):
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

    load("_bst.config", "config.py")
    load("_bst.model", "model.py")
    load("_bst.geom.shapes", "geom", "shapes.py")
    load("_bst.classify.layers", "classify", "layers.py")
    load("_bst.classify.marks", "classify", "marks.py")
    load("_bst.readers.dxf_reader", "readers", "dxf_reader.py")
    return load("_bst.report", "report.py")


report = _load()
model = sys.modules["_bst.model"]
layers = sys.modules["_bst.classify.layers"]
marks = sys.modules["_bst.classify.marks"]
dxf_reader = sys.modules["_bst.readers.dxf_reader"]


def _run_dxf():
    res = dxf_reader.read_dxf(_DXF)
    for record in res.records:
        record.points = [(p[0] * _FT, p[1] * _FT, 0.0) for p in record.points]
    mapping = layers.build_default_mapping([r.layer_key for r in res.records])
    layers.apply_mapping(res.records, mapping)
    for t in res.texts:
        t.point_internal = (t.point[0] * _FT, t.point[1] * _FT, 0.0)
    marks.parse_texts(res.texts)
    beam_texts = [t for t in res.texts
                  if layers.classify_text_layer(t.layer or "")
                  == layers.CATEGORY_BEAM_TEXT]
    return report.build_beam_segments(res.records, [], None, None,
                                      texts=beam_texts, tolerances={}, schedule=None)


_RESULT = _run_dxf()


def _by_mark(mark):
    hits = [s for s in _RESULT["segments"] if s.get("mark") == mark]
    return hits[0] if len(hits) == 1 else None


def _mm_pt(p):
    return (p[0] * _MM, p[1] * _MM)


def _angle(seg):
    sx, sy = _mm_pt(seg["start"])
    ex, ey = _mm_pt(seg["end"])
    a = abs(math.degrees(math.atan2(ey - sy, ex - sx))) % 180.0
    return min(a, 180.0 - a)


class Z1Baseline(unittest.TestCase):
    def test_all_four_ring_beams_placed_and_named(self):
        for mark in ("B1", "B2", "B3", "B4"):
            seg = _by_mark(mark)
            self.assertIsNotNone(seg, mark)
            self.assertAlmostEqual(seg["width_mm"], 300, delta=1)
            self.assertAlmostEqual(seg["depth_mm"], 600, delta=1)

    def test_rotated_labels_stay_on_their_verticals(self):
        # B3/B4 are written ALONG the vertical beams; their anchors sit near the
        # horizontals' rows -- orientation gating must keep them off B1/B2.
        for mark, x_mm in (("B3", 0.0), ("B4", 8000.0)):
            seg = _by_mark(mark)
            self.assertLess(abs(_mm_pt(seg["start"])[0] - x_mm), 50, mark)
            self.assertGreater(_angle(seg), 88.0, mark)


class Z2Z3Angled(unittest.TestCase):
    def test_sloped_beam_keeps_its_four_degrees(self):
        seg = _by_mark("B5")
        self.assertIsNotNone(seg)
        self.assertAlmostEqual(_angle(seg), 4.0, delta=0.3)

    def test_diagonal_beam_keeps_its_45_degrees(self):
        seg = _by_mark("B6")
        self.assertIsNotNone(seg)
        self.assertAlmostEqual(_angle(seg), 45.0, delta=0.3)


class Z4WideContinuation(unittest.TestCase):
    def test_wide_beam_is_one_piece_across_the_crossing(self):
        seg = _by_mark("B7")
        self.assertIsNotNone(seg)
        self.assertAlmostEqual(seg["width_mm"], 900, delta=1)
        xs = sorted((_mm_pt(seg["start"])[0], _mm_pt(seg["end"])[0]))
        self.assertLess(xs[0], 100)          # reaches the left end
        self.assertGreater(xs[1], 19900)     # MERGED across the crossing to the right end

    def test_crossing_beam_survives(self):
        seg = _by_mark("B12")
        self.assertIsNotNone(seg)
        self.assertGreater(_angle(seg), 88.0)


class Z5Perimeter(unittest.TestCase):
    def test_one_edged_beam_pairs_with_the_floor_outline(self):
        seg = _by_mark("B8")
        self.assertIsNotNone(seg)
        self.assertAlmostEqual(seg["width_mm"], 300, delta=1)
        self.assertAlmostEqual(_mm_pt(seg["start"])[1], 14000, delta=30)


class Z6StackedLabels(unittest.TestCase):
    def test_marks_do_not_swap_between_stacked_beams(self):
        b10, b11 = _by_mark("B10"), _by_mark("B11")
        self.assertIsNotNone(b10)
        self.assertIsNotNone(b11)
        self.assertAlmostEqual(b10["width_mm"], 600, delta=1)
        self.assertAlmostEqual(_mm_pt(b10["start"])[1], 17300, delta=30)
        self.assertAlmostEqual(b11["width_mm"], 300, delta=1)
        self.assertAlmostEqual(_mm_pt(b11["start"])[1], 16150, delta=30)


class Z7Curved(unittest.TestCase):
    def test_arc_chains_become_one_named_curved_beam(self):
        curved = _RESULT.get("curved_segments") or []
        self.assertEqual(len(curved), 1)
        c = curved[0]
        self.assertAlmostEqual(c["width_mm"], 300, delta=5)
        self.assertAlmostEqual(c["radius_ft"] * _MM, 3000, delta=10)
        self.assertEqual(c.get("mark"), "B9")


class Z8Junk(unittest.TestCase):
    def test_junk_fabricates_no_beam(self):
        # nothing may land in the junk zone (x>29000, y<9000): the lone/duplicate
        # edge, the zero-length line, the 20mm sliver and the orphan label
        for seg in _RESULT["segments"]:
            sx, sy = _mm_pt(seg["start"])
            ex, ey = _mm_pt(seg["end"])
            in_zone = min(sx, ex) > 29000 and max(sy, ey) < 9000
            self.assertFalse(in_zone, "junk zone fabricated: %s" % seg)

    def test_orphan_label_names_nothing(self):
        self.assertIsNone(_by_mark("B99"))


class PolylineSnakes(unittest.TestCase):
    """The Revit link reader's polyline shapes, fed straight into detection."""

    def _run(self, records):
        return report.build_beam_segments(records, [], None, None,
                                          texts=None, tolerances={}, schedule=None)

    def _poly(self, pts_mm):
        pts = [(x * _FT, y * _FT, 0.0) for x, y in pts_mm]
        r = model.CurveRecord("polyline", pts, "S-BEAM", None)
        r.category = layers.CATEGORY_BEAM
        return r

    def _line(self, x1, y1, x2, y2):
        r = model.CurveRecord("line", [(x1 * _FT, y1 * _FT, 0.0),
                                       (x2 * _FT, y2 * _FT, 0.0)], "S-BEAM", None)
        r.category = layers.CATEGORY_BEAM
        return r

    def test_u_snake_makes_no_midline_phantom(self):
        # facing edges of two grid beams chained by one leg (Test15 J/K phantom)
        recs = [self._poly([(0, 300), (5000, 300), (5000, 2000), (0, 2000)]),
                self._line(0, 0, 5000, 0),          # lower beam's other edge
                self._line(0, 2300, 5000, 2300)]    # upper beam's other edge
        out = self._run(recs)
        ys = sorted(round((_mm_pt(s["start"])[1] + _mm_pt(s["end"])[1]) / 2.0)
                    for s in out["segments"])
        self.assertEqual(ys, [150, 2150])            # on-grid beams, no midline phantom

    def test_open_snake_keeps_its_collinear_last_leg(self):
        # horizontal beam edge turning up into a vertical's edge (Test10 grid-6 loss)
        recs = [self._poly([(0, 0), (5000, 0), (5000, 300), (0, 300), (0, 2500)]),
                self._line(-300, 300, -300, 2500)]   # the vertical's other edge
        out = self._run(recs)
        vertical = [s for s in out["segments"]
                    if abs(_mm_pt(s["start"])[0] - _mm_pt(s["end"])[0]) < 1]
        self.assertEqual(len(vertical), 1)           # the leg survived and paired

    def test_skew_snake_stays_angled(self):
        # sloped beam's two 4-deg edges in one open snake (Test11 grid-I flattening)
        ang = math.radians(4.0)
        ex, ey = 8000 * math.cos(ang), 8000 * math.sin(ang)
        nx, ny = -math.sin(ang) * 150, math.cos(ang) * 150
        recs = [self._poly([(0 + nx, 0 + ny), (ex + nx, ey + ny),
                            (ex - nx, ey - ny), (0 - nx, 0 - ny)])]
        out = self._run(recs)
        self.assertEqual(len(out["segments"]), 1)
        seg = out["segments"][0]
        sx, sy = _mm_pt(seg["start"])
        tx, ty = _mm_pt(seg["end"])
        a = abs(math.degrees(math.atan2(ty - sy, tx - sx))) % 180.0
        self.assertAlmostEqual(min(a, 180.0 - a), 4.0, delta=0.3)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""HATCH support in the DXF reader.

Until now `_geometry_record` handled LINE, ARC, CIRCLE, POINT, LWPOLYLINE,
POLYLINE, ELLIPSE and SPLINE -- and dropped every HATCH on the floor. That is
276 entities in test10, 360 each in test4/test5, 228 in Project1, and it is the
one thing standing between the toolkit and three separate features: foundations
that know where a fold is, sunk slabs, and openings.

A hatch is a REGION, not a curve, and it is read into `result.regions` rather
than `result.records`. Two reasons, and the second is the load-bearing one:

  * a curve pipeline that suddenly received a few hundred closed rings would try
    to make columns and beams out of them;
  * the P0 regression baselines are counts over `records`, so keeping regions
    out of that list means the whole corpus is proof this change altered nothing
    that was already working.

The subtlety worth a test of its own: AutoCAD clips a hatch around any label
drawn on top of it, so test10's fold hatches arrive as THREE boundary paths --
one EXTERNAL rectangle and two TEXTBOX islands cut out for the "F3_1500MM THK"
label. Reading every path would give a region full of holes that are not holes.
Only the external boundary is the region.

Fixtures are generated here rather than read from `fixtures/cad`: test10 is
3.7 MB and parsing it belongs in the regression sweep, not in a suite that has
to stay under a second.
"""

import os
import shutil
import tempfile
import unittest

import _loader


dxf_reader, model = _loader.load("readers.dxf_reader", "model")

_EXTERNAL = 1
_TEXTBOX = 8
_OUTERMOST = 16


def _write_fixture(folder):
    """A DXF holding the three hatch shapes the corpus actually contains."""
    import ezdxf

    document = ezdxf.new("R2010")
    space = document.modelspace()

    # 1. The test10 shape: a patterned region with its label's textbox cut out.
    hatch = space.add_hatch(color=7, dxfattribs={"layer": "S-FND-FOLD"})
    hatch.set_pattern_fill("ANSI37", scale=1.0)
    hatch.paths.add_polyline_path(
        [(0, 0), (2700, 0), (2700, 3000), (0, 3000)],
        is_closed=True, flags=_EXTERNAL)
    hatch.paths.add_polyline_path(
        [(900, 1400), (1800, 1400), (1800, 1600), (900, 1600)],
        is_closed=True, flags=_TEXTBOX | _OUTERMOST)

    # 2. A solid fill, which is how columns are hatched (test0, Project1).
    solid = space.add_hatch(color=2, dxfattribs={"layer": "S-COLS"})
    solid.paths.add_polyline_path(
        [(5000, 0), (5400, 0), (5400, 600), (5000, 600)],
        is_closed=True, flags=_EXTERNAL)

    # 3. Ordinary geometry, to prove regions do not land among the curves.
    space.add_line((0, 0), (1000, 0), dxfattribs={"layer": "S-BEAM"})

    path = os.path.join(folder, "hatches.dxf")
    document.saveas(path)
    return path


class HatchReading(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not dxf_reader.ezdxf_available():
            raise unittest.SkipTest("ezdxf is not importable -- pip install ezdxf")
        cls.folder = tempfile.mkdtemp()
        cls.result = dxf_reader.read_dxf(_write_fixture(cls.folder))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "folder", None) or ".", ignore_errors=True)

    def test_a_hatch_is_read_at_all(self):
        self.assertEqual(len(self.result.regions), 2)

    def test_a_region_keeps_the_layer_it_was_drawn_on(self):
        layers = sorted(r.layer for r in self.result.regions)
        self.assertEqual(layers, ["S-COLS", "S-FND-FOLD"])

    def test_a_region_keeps_its_pattern_name(self):
        fold = self._on("S-FND-FOLD")
        self.assertEqual(fold.pattern, "ANSI37")

    def test_a_solid_fill_says_so(self):
        self.assertTrue(self._on("S-COLS").solid)
        self.assertFalse(self._on("S-FND-FOLD").solid)

    def test_only_the_EXTERNAL_boundary_is_the_region(self):
        # the textbox island AutoCAD cut out for the label is not a hole in the
        # foundation -- it is a hole in the hatching
        fold = self._on("S-FND-FOLD")
        self.assertEqual(len(fold.points), 4)
        xs = [p[0] for p in fold.points]
        ys = [p[1] for p in fold.points]
        self.assertEqual((max(xs) - min(xs), max(ys) - min(ys)), (2700, 3000))

    def test_regions_do_not_appear_among_the_curve_records(self):
        # the whole reason the P0 baselines did not move
        kinds = sorted(set(r.kind for r in self.result.records))
        self.assertEqual(kinds, ["line"])

    def test_a_region_carries_a_layer_key_like_every_other_record(self):
        self.assertEqual(self._on("S-COLS").layer_key, "S-COLS")

    def _on(self, layer):
        found = [r for r in self.result.regions if r.layer == layer]
        self.assertEqual(len(found), 1, "expected one region on " + layer)
        return found[0]


class ReadResultShape(unittest.TestCase):
    def test_a_result_built_without_regions_still_works(self):
        # every existing caller constructs DxfReadResult with three arguments
        result = model.DxfReadResult("x.dxf", [], [])
        self.assertEqual(result.regions, [])
        self.assertTrue(result.is_empty())

    def test_a_result_holding_only_regions_is_not_empty(self):
        region = model.RegionRecord([(0, 0, 0)], "S-FND-SUNK", "ANSI37")
        self.assertFalse(model.DxfReadResult("x.dxf", [], [], [region]).is_empty())


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""floor_plans -- one dxf holding several floor plans -> per-storey records.

Covered on synthetic sheets: boundary rectangles (closed polyline AND four
loose lines) become regions; the origin marker inside each region shifts that
storey's records so the marker lands on (0, 0); plan titles order the storeys
bottom-up and the sheet layout is the fallback; records outside every box are
dropped; missing/extra origin markers leave a note instead of failing.
Standalone (no Revit).
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
    for name in ("_fp", "_fp.geom", "_fp.classify"):
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

    load("_fp.config", "config.py")
    load("_fp.geom.shapes", "geom", "shapes.py")
    load("_fp.classify.layers", "classify", "layers.py")
    return load("_fp.floor_plans", "floor_plans.py")


floor_plans = _load()
layers = sys.modules["_fp.classify.layers"]


class _Rec(object):
    def __init__(self, kind, pts, category, layer="TEST"):
        self.kind = kind
        self.points = [(p[0] * _FT, p[1] * _FT, 0.0) for p in pts]
        self.layer = layer
        self.layer_key = layer
        self.category = category


class _Text(object):
    def __init__(self, text, x_mm, y_mm):
        self.text = text
        self.layer = "TITLE"
        self.layer_key = "TITLE"
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _box(x0, y0, x1, y1, category=None):
    category = category or layers.CATEGORY_FLOOR_BOUNDARY
    return _Rec("polyline",
                [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], category)


def _loose_box(x0, y0, x1, y1):
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [_Rec("line", [corners[i], corners[(i + 1) % 4]],
                 layers.CATEGORY_FLOOR_BOUNDARY) for i in range(4)]


def _origin(x, y):
    # a small cross, drawn as two short lines like a real origin marker
    return [_Rec("line", [(x - 100.0, y), (x + 100.0, y)],
                 layers.CATEGORY_FLOOR_ORIGIN),
            _Rec("line", [(x, y - 100.0), (x, y + 100.0)],
                 layers.CATEGORY_FLOOR_ORIGIN)]


def _centre(record):
    """Bounding-box centre of a record, in mm (the point split_floors keys on)."""
    xs = [p[0] * _MM for p in record.points]
    ys = [p[1] * _MM for p in record.points]
    return (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0


def _column(x, y, size=400.0):
    half = size / 2.0
    return _box(x - half, y - half, x + half, y + half,
                category=layers.CATEGORY_COLUMN)


class LevelNames(unittest.TestCase):
    def test_titles_map_to_order(self):
        order = floor_plans.level_order_from_text
        self.assertEqual(order("GROUND FLOOR PLAN"), 0)
        self.assertEqual(order("FIRST FLOOR"), 1)
        self.assertEqual(order("2ND FLOOR PLAN"), 2)
        self.assertEqual(order("LEVEL 3"), 3)
        self.assertEqual(order("Basement Plan"), -1)
        self.assertEqual(order("TERRACE PLAN"), 999)
        self.assertIsNone(order("COLUMN SCHEDULE"))
        self.assertIsNone(order(None))

    def test_real_fixture_titles(self):
        # StructuralPlan-Test10's own plan titles (the elevation suffix must not
        # be mistaken for the level number)
        order = floor_plans.level_order_from_text
        self.assertEqual(order("Ground Floor @0.00+ Level"), 0)
        self.assertEqual(order("1st Floor @3.00+ Level"), 1)
        # a "typical floor" covers several levels and names none: sheet order
        self.assertIsNone(order("Typical Floor @7.00+, 11.00+, 14.00+ & 17.00+"))


class SplitFloors(unittest.TestCase):
    def _two_sheets(self):
        """Two 20x20 m boxes side by side, each with a column 1 m past its
        origin marker; titles name them GROUND and FIRST."""
        recs = []
        recs.append(_box(0.0, 0.0, 20000.0, 20000.0))
        recs += _origin(2000.0, 2000.0)
        recs.append(_column(3000.0, 2000.0))
        recs.append(_box(30000.0, 0.0, 50000.0, 20000.0))
        recs += _origin(32000.0, 2000.0)
        recs.append(_column(33000.0, 2000.0))
        texts = [_Text("GROUND FLOOR PLAN", 10000.0, 19000.0),
                 _Text("FIRST FLOOR PLAN", 40000.0, 19000.0)]
        return recs, texts

    def test_regions_split_and_align(self):
        recs, texts = self._two_sheets()
        regions, notes = floor_plans.split_floors(recs, texts)
        self.assertEqual(notes, [])
        self.assertEqual(len(regions), 2)
        self.assertEqual([r.label for r in regions],
                         ["GROUND FLOOR PLAN", "FIRST FLOOR PLAN"])
        self.assertEqual([r.order for r in regions], [0, 1])
        # every storey stacks onto the BASE storey's marker (2000, 2000), so
        # the ground plan does not move and the upper one lands on top of it;
        # the column sat 1000mm past the marker in both sheets
        for region in regions:
            columns = [r for r in region.records
                       if r.category == layers.CATEGORY_COLUMN]
            self.assertEqual(len(columns), 1)
            cx, cy = _centre(columns[0])
            self.assertAlmostEqual(cx, 3000.0, places=3)
            self.assertAlmostEqual(cy, 2000.0, places=3)

    def test_base_storey_never_moves(self):
        """The built model must land ON the base CAD, not at Revit's origin."""
        recs, texts = self._two_sheets()
        regions, _notes = floor_plans.split_floors(recs, texts)
        drawn = [r for r in recs if r.category == layers.CATEGORY_COLUMN][0]
        base = [r for r in regions[0].records
                if r.category == layers.CATEGORY_COLUMN][0]
        self.assertAlmostEqual(_centre(base)[0], _centre(drawn)[0], places=6)
        self.assertAlmostEqual(_centre(base)[1], _centre(drawn)[1], places=6)

    def test_texts_travel_with_their_storey(self):
        recs, texts = self._two_sheets()
        texts.append(_Text("C1 400x400", 3000.0, 2600.0))
        regions, _notes = floor_plans.split_floors(recs, texts)
        marks = [[t.text for t in r.texts] for r in regions]
        self.assertIn("C1 400x400", marks[0])
        self.assertNotIn("C1 400x400", marks[1])
        moved = [t for t in regions[0].texts if t.text == "C1 400x400"][0]
        self.assertAlmostEqual(moved.point_internal[0] * _MM, 3000.0, places=3)
        self.assertAlmostEqual(moved.point_internal[1] * _MM, 2600.0, places=3)

    def test_align_false_keeps_drawn_positions(self):
        recs, texts = self._two_sheets()
        regions, _notes = floor_plans.split_floors(recs, texts, align=False)
        columns = [r for r in regions[1].records
                   if r.category == layers.CATEGORY_COLUMN]
        self.assertAlmostEqual(_centre(columns[0])[0], 33000.0, places=3)

    def test_loose_boundary_lines_recovered(self):
        recs = _loose_box(0.0, 0.0, 20000.0, 20000.0)
        recs += _origin(1000.0, 1000.0)
        recs.append(_column(5000.0, 5000.0))
        regions, _notes = floor_plans.split_floors(recs, [])
        self.assertEqual(len(regions), 1)
        self.assertAlmostEqual(regions[0].width_mm, 20000.0, places=3)

    def test_sheet_layout_orders_untitled_plans(self):
        # upper box is the LOWER storey by sheet convention (top row first)
        recs = [_box(0.0, 30000.0, 20000.0, 50000.0)]
        recs += _origin(1000.0, 31000.0)
        recs.append(_column(5000.0, 35000.0))
        recs.append(_box(0.0, 0.0, 20000.0, 20000.0))
        recs += _origin(1000.0, 1000.0)
        recs.append(_column(5000.0, 5000.0))
        regions, notes = floor_plans.split_floors(recs, [])
        self.assertEqual(len(regions), 2)
        self.assertAlmostEqual(regions[0].bounds[1] * _MM, 30000.0, places=3)
        self.assertTrue(any("sheet layout" in n for n in notes))

    def test_missing_origin_uses_centre_with_note(self):
        recs = [_box(0.0, 0.0, 20000.0, 20000.0), _column(5000.0, 5000.0)]
        regions, notes = floor_plans.split_floors(recs, [])
        self.assertEqual(len(regions), 1)
        self.assertTrue(any("no origin marker" in n for n in notes))
        columns = [r for r in regions[0].records
                   if r.category == layers.CATEGORY_COLUMN]
        # a lone storey is its own anchor, so nothing moves
        self.assertAlmostEqual(_centre(columns[0])[0], 5000.0, places=3)

    def test_point_marker_is_an_origin(self):
        # real drawings mark the origin with a bare POINT (Test9 / Test10)
        recs = [_box(0.0, 0.0, 20000.0, 20000.0),
                _Rec("point", [(3000.0, 4000.0)],
                     layers.CATEGORY_FLOOR_ORIGIN),
                _column(5000.0, 5000.0)]
        regions, notes = floor_plans.split_floors(recs, [])
        self.assertEqual(notes, [])
        self.assertEqual(len(regions), 1)
        cx, cy = _centre(regions[0].records[0])
        # single storey: it anchors on itself and stays where it is drawn
        self.assertAlmostEqual(cx, 5000.0, places=3)
        self.assertAlmostEqual(cy, 5000.0, places=3)

    def test_markers_may_come_from_a_second_record_set(self):
        # the pushbutton reads boundary/origin from the DXF records and splits
        # the REVIT records by them (a bare POINT is not always imported)
        markers = [_box(0.0, 0.0, 20000.0, 20000.0),
                   _Rec("point", [(1000.0, 1000.0)],
                        layers.CATEGORY_FLOOR_ORIGIN)]
        build = [_column(5000.0, 5000.0)]
        regions, notes = floor_plans.split_floors(build, [],
                                                  marker_records=markers)
        self.assertEqual(notes, [])
        self.assertEqual(len(regions), 1)
        self.assertEqual(len(regions[0].records), 1)
        self.assertAlmostEqual(_centre(regions[0].records[0])[0], 5000.0,
                               places=3)

    def test_no_boundary_layer_is_reported(self):
        regions, notes = floor_plans.split_floors([_column(1000.0, 1000.0)], [])
        self.assertEqual(regions, [])
        self.assertTrue(any("no closed rectangle" in n for n in notes))

    def test_records_outside_every_box_are_dropped(self):
        recs = [_box(0.0, 0.0, 20000.0, 20000.0)]
        recs += _origin(1000.0, 1000.0)
        recs.append(_column(5000.0, 5000.0))
        recs.append(_column(90000.0, 90000.0))       # stray, outside the sheet
        regions, _notes = floor_plans.split_floors(recs, [])
        self.assertEqual(len(regions[0].records), 1)


if __name__ == "__main__":
    unittest.main()

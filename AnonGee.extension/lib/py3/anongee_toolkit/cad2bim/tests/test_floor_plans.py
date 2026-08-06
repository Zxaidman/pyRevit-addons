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


class TypicalPlanCount(unittest.TestCase):
    def test_range_titles_give_a_repeat_count(self):
        count = floor_plans.typical_count_from_text
        self.assertEqual(count("TYPICAL FLOOR PLAN (2ND TO 8TH FLOOR)"), 7)
        self.assertEqual(count("Typical Floor Plan 3 to 5"), 3)
        self.assertEqual(count("TYPICAL FLOOR PLAN X5"), 5)
        self.assertEqual(count("TYPICAL FLOOR (4 NOS)"), 4)
        self.assertEqual(count("TYPICAL PLAN - 6 FLOORS"), 6)

    def test_a_plan_that_is_not_typical_never_repeats(self):
        count = floor_plans.typical_count_from_text
        self.assertIsNone(count("SECOND FLOOR PLAN"))
        self.assertIsNone(count("BEAM SCHEDULE 2 TO 8"))
        self.assertIsNone(count(None))

    def test_reversed_or_empty_range_is_ignored(self):
        self.assertIsNone(floor_plans.typical_count_from_text("TYPICAL PLAN"))


class AutoDetectStoreys(unittest.TestCase):
    """The dialog must decide multi-storey ON/OFF without being told anything."""

    def _sheet(self, titles=("GROUND FLOOR PLAN", "FIRST FLOOR PLAN"),
               boundary="RANDOM-A", origin="RANDOM-B", with_origin=True):
        records, texts = [], []
        for index, title in enumerate(titles):
            y0 = index * 40000.0
            records.append(_Rec("polyline",
                                [(0, y0), (30000, y0), (30000, y0 + 30000),
                                 (0, y0 + 30000), (0, y0)], None, boundary))
            if with_origin:
                records.append(_Rec("point", [(1000, y0 + 1000)], None, origin))
            for step in range(4):          # a real plan has many columns
                x0 = 5000.0 + step * 4000.0
                records.append(_Rec("polyline",
                                    [(x0, y0 + 5000), (x0 + 400, y0 + 5000),
                                     (x0 + 400, y0 + 5400), (x0, y0 + 5400)],
                                    None, "S-COLS"))
            texts.append(_Text(title, 15000, y0 + 29000))
        return records, texts

    def test_layers_are_found_by_shape_not_by_name(self):
        records, texts = self._sheet()
        found = floor_plans.autodetect_storeys(records, texts)
        self.assertTrue(found.multistorey)
        self.assertEqual(found.boundary_layer, "RANDOM-A")
        self.assertEqual(found.origin_layer, "RANDOM-B")
        self.assertEqual(len(found.plans), 2)
        self.assertEqual([p["label"] for p in found.plans],
                         ["GROUND FLOOR PLAN", "FIRST FLOOR PLAN"])
        self.assertEqual([p["order"] for p in found.plans], [0, 1])

    def test_a_single_plan_leaves_the_box_unticked(self):
        records, texts = self._sheet(titles=("GROUND FLOOR PLAN",))
        found = floor_plans.autodetect_storeys(records, texts)
        self.assertFalse(found.multistorey)
        self.assertIn("one storey", found.reason)

    def test_a_drawing_with_no_boundary_layer_is_single_storey(self):
        records = [_Rec("polyline", [(0, 0), (400, 0), (400, 400), (0, 400)],
                        None, "S-COLS")]
        found = floor_plans.autodetect_storeys(records, [])
        self.assertFalse(found.multistorey)
        self.assertEqual(found.plans, [])

    def test_typical_plan_counts_towards_the_storey_total(self):
        records, texts = self._sheet(
            titles=("GROUND FLOOR PLAN", "TYPICAL FLOOR PLAN (2ND TO 8TH FLOOR)"))
        found = floor_plans.autodetect_storeys(records, texts)
        self.assertEqual([p["repeat"] for p in found.plans], [1, 7])
        self.assertEqual(found.storey_count, 8)
        self.assertIn("building it 7 times", " ".join(found.notes))

    def test_missing_origin_layer_is_reported_not_fatal(self):
        records, texts = self._sheet(with_origin=False)
        found = floor_plans.autodetect_storeys(records, texts)
        self.assertTrue(found.multistorey)
        self.assertIsNone(found.origin_layer)
        self.assertIn("no origin layer", " ".join(found.notes))

    def test_explicit_layers_win_over_the_guess(self):
        records, texts = self._sheet(boundary="MY-BOX", origin="MY-PT")
        found = floor_plans.autodetect_storeys(records, texts,
                                               boundary_layer="MY-BOX",
                                               origin_layer="MY-PT")
        self.assertTrue(found.multistorey)
        self.assertEqual(found.boundary_layer, "MY-BOX")


class ReuseAndReorderStoreys(unittest.TestCase):
    """The storey table IS the stack: its order builds bottom-up, and one plan
    can be used by several rows (a typical floor drawn once, built five times)."""

    def _regions(self):
        return [floor_plans.FloorRegion((0, 0, 1, 1), (0, 0), label="GROUND",
                                        order=0, records=["g"]),
                floor_plans.FloorRegion((0, 0, 1, 1), (0, 0), label="TYPICAL",
                                        order=1, records=["t"])]

    def test_one_plan_can_build_several_storeys(self):
        stack = floor_plans.apply_storey_settings(
            self._regions(),
            [{"plan": 0}, {"plan": 1}, {"plan": 1}, {"plan": 1}])
        self.assertEqual([r.label for r in stack],
                         ["GROUND", "TYPICAL", "TYPICAL", "TYPICAL"])
        # the records are SHARED, not copied: one plan, four storeys
        self.assertIs(stack[1].records, stack[2].records)

    def test_the_row_order_is_the_build_order(self):
        stack = floor_plans.apply_storey_settings(
            self._regions(), [{"plan": 1}, {"plan": 0}])
        self.assertEqual([r.label for r in stack], ["TYPICAL", "GROUND"])

    def test_each_reused_storey_keeps_its_own_height(self):
        stack = floor_plans.apply_storey_settings(
            self._regions(),
            [{"plan": 1, "height_mm": 3000.0}, {"plan": 1, "height_mm": 4500.0}])
        self.assertEqual([r.storey_height_mm for r in stack], [3000.0, 4500.0])

    def test_a_row_naming_a_plan_that_is_gone_falls_back(self):
        stack = floor_plans.apply_storey_settings(
            self._regions(), [{"plan": 9, "label": "TYPICAL"}])
        self.assertEqual([r.label for r in stack], ["TYPICAL"])


class PerStoreySettings(unittest.TestCase):
    def _regions(self):
        return [floor_plans.FloorRegion((0, 0, 1, 1), (0, 0), label="GROUND",
                                        order=0, records=[1]),
                floor_plans.FloorRegion((0, 0, 1, 1), (0, 0), label="TYPICAL",
                                        order=1, records=[1])]

    def test_heights_and_repeats_reach_the_regions(self):
        regions = floor_plans.apply_storey_settings(
            self._regions(),
            [{"label": "GROUND", "plan": 0, "height_mm": 4200.0, "repeat": 1},
             {"label": "TYPICAL", "plan": 1, "height_mm": 3000.0, "repeat": 5}])
        self.assertEqual(regions[0].storey_height_mm, 4200.0)
        self.assertEqual(regions[1].repeat, 5)

    def test_rows_match_positionally_when_labels_are_missing(self):
        regions = [floor_plans.FloorRegion((0, 0, 1, 1), (0, 0), order=i,
                                           records=[1]) for i in range(2)]
        stack = floor_plans.apply_storey_settings(
            regions, [{"label": None, "height_mm": 5000.0, "repeat": 1},
                      {"label": None, "height_mm": 2800.0, "repeat": 1}])
        self.assertEqual([r.storey_height_mm for r in stack], [5000.0, 2800.0])

    def test_an_unticked_plan_is_dropped(self):
        regions = floor_plans.apply_storey_settings(
            self._regions(),
            [{"label": "GROUND", "plan": 0, "include": False, "repeat": 1},
             {"label": "TYPICAL", "plan": 1, "include": True, "repeat": 2}])
        self.assertEqual([r.label for r in regions], ["TYPICAL"])
        self.assertEqual(regions[0].repeat, 2)

    def test_include_defaults_to_true_when_a_row_omits_it(self):
        regions = floor_plans.apply_storey_settings(
            self._regions(), [{"label": "GROUND"}, {"label": "TYPICAL"}])
        self.assertEqual(len(regions), 2)

    def test_dropping_every_plan_leaves_the_split_alone(self):
        # every row unticked is a mistake, not an instruction to build nothing
        regions = self._regions()
        self.assertEqual(len(floor_plans.apply_storey_settings(
            regions, [{"label": "GROUND", "plan": 0, "include": False},
                      {"label": "TYPICAL", "plan": 1, "include": False}])), 2)

    def test_expand_repeats_names_each_copy(self):
        regions = self._regions()
        regions[1].repeat = 3
        pairs = floor_plans.expand_repeats(regions)
        self.assertEqual([label for _r, label in pairs],
                         ["GROUND", "TYPICAL (1/3)", "TYPICAL (2/3)",
                          "TYPICAL (3/3)"])
        self.assertEqual(len(pairs), 4)

    def test_a_boundary_box_height_is_not_the_storey_height(self):
        # height_mm is the sheet box; storey_height_mm is floor-to-floor
        region = floor_plans.FloorRegion((0.0, 0.0, 10.0, 20.0), (0, 0))
        self.assertAlmostEqual(region.height_mm, 20.0 * _MM)
        self.assertIsNone(region.storey_height_mm)



class BoundaryLayerIsNotJustBigShapes(unittest.TestCase):
    """A layer of big members must never be mistaken for the boundary layer.

    Test9 has 24 shear-wall outlines on one layer; before the coverage rule the
    detector called them 24 floor plans. A boundary box ENCLOSES a plan, so
    almost everything drawn falls inside one (measured: 1.00 and 0.67 for the
    two real boundary layers, 0.28 for the best impostor).
    """

    def _plan_with_big_walls(self):
        records = []
        for index in range(2):
            y0 = index * 40000.0
            # six long shear walls: big, closed, disjoint -- and enclosing nothing
            for step in range(6):
                x0 = 2000.0 + step * 4000.0
                records.append(_Rec("polyline",
                                    [(x0, y0), (x0 + 400, y0),
                                     (x0 + 400, y0 + 12000), (x0, y0 + 12000),
                                     (x0, y0)], None, "SHEARWALL"))
            for step in range(20):
                x0 = 1000.0 + step * 1200.0
                records.append(_Rec("line", [(x0, y0 + 20000),
                                             (x0 + 900, y0 + 20000)],
                                    None, "S-BEAM"))
        return records

    def test_member_layer_is_rejected(self):
        found = floor_plans.autodetect_storeys(self._plan_with_big_walls(), [])
        self.assertFalse(found.multistorey)
        self.assertIsNone(found.boundary_layer)

    def test_a_real_boundary_layer_still_wins_alongside_them(self):
        records = self._plan_with_big_walls()
        for index in range(2):
            y0 = index * 40000.0
            records.append(_Rec("polyline",
                                [(0, y0 - 2000), (30000, y0 - 2000),
                                 (30000, y0 + 30000), (0, y0 + 30000),
                                 (0, y0 - 2000)], None, "ZZ"))
        found = floor_plans.autodetect_storeys(records, [])
        self.assertTrue(found.multistorey)
        self.assertEqual(found.boundary_layer, "ZZ")

    def test_overlapping_boxes_are_not_floor_plans(self):
        records = []
        for offset in (0.0, 1000.0):       # two boxes on top of each other
            records.append(_Rec("polyline",
                                [(offset, offset), (30000, offset),
                                 (30000, 30000), (offset, 30000),
                                 (offset, offset)], None, "OVERLAP"))
        records.append(_Rec("line", [(500, 500), (600, 600)], None, "S-BEAM"))
        found = floor_plans.autodetect_storeys(records, [])
        self.assertFalse(found.multistorey)

    def test_partly_boxed_drawing_warns_about_the_rest(self):
        records = []
        for index in range(2):
            y0 = index * 40000.0
            records.append(_Rec("polyline",
                                [(0, y0), (30000, y0), (30000, y0 + 30000),
                                 (0, y0 + 30000), (0, y0)], None, "BOX"))
            for step in range(8):
                records.append(_Rec("line", [(1000.0 + step * 2000, y0 + 5000),
                                             (1900.0 + step * 2000, y0 + 5000)],
                                    None, "S-BEAM"))
        for step in range(6):              # a third plan nobody boxed
            records.append(_Rec("line", [(90000.0 + step * 2000, 5000),
                                         (90900.0 + step * 2000, 5000)],
                                None, "S-BEAM"))
        found = floor_plans.autodetect_storeys(records, [])
        self.assertTrue(found.multistorey)
        self.assertIn("outside the floor boxes", " ".join(found.notes))



class StoreyHeightsFromTitles(unittest.TestCase):
    """Test10's titles quote where each storey sits, so they state the rise."""

    def test_elevations_are_read_in_millimetres(self):
        elev = floor_plans.elevation_from_text
        self.assertEqual(elev("Ground Floor @0.00+ Level"), 0.0)
        self.assertEqual(elev("1st Floor @3.00+ Level"), 3000.0)
        self.assertEqual(elev("Terrace Floor @20.00+ Level"), 20000.0)
        self.assertEqual(elev("EL. +12.500"), 12500.0)
        self.assertEqual(elev("Basement @-3.50 Level"), -3500.0)
        self.assertEqual(elev("SLAB @ 12500"), 12500.0)   # already millimetres
        self.assertIsNone(elev("GROUND FLOOR FRAMING PLAN"))
        self.assertIsNone(elev(None))

    def _sheet(self, titles):
        records, texts = [], []
        for index, title in enumerate(titles):
            y0 = index * 40000.0
            records.append(_Rec("polyline",
                                [(0, y0), (30000, y0), (30000, y0 + 30000),
                                 (0, y0 + 30000), (0, y0)], None, "BOX"))
            records.append(_Rec("point", [(1000, y0 + 1000)], None, "PT"))
            for step in range(4):
                x0 = 5000.0 + step * 4000.0
                records.append(_Rec("polyline",
                                    [(x0, y0 + 5000), (x0 + 400, y0 + 5000),
                                     (x0 + 400, y0 + 5400), (x0, y0 + 5400)],
                                    None, "S-COLS"))
            texts.append(_Text(title, 15000, y0 + 29000))
        return records, texts

    def test_consecutive_elevations_become_storey_heights(self):
        records, texts = self._sheet(["Ground Floor @0.00+ Level",
                                      "1st Floor @3.30+ Level",
                                      "2nd Floor @6.30+ Level"])
        found = floor_plans.autodetect_storeys(records, texts)
        heights = [p["height_mm"] for p in found.plans]
        self.assertEqual(heights[:2], [3300.0, 3000.0])
        self.assertIsNone(heights[2])          # nothing above it to measure to
        self.assertIn("read from the plan titles", " ".join(found.notes))

    def test_a_typical_plan_splits_the_rise_it_covers(self):
        records, texts = self._sheet(
            ["Ground Floor @0.00+ Level",
             "TYPICAL FLOOR PLAN (1ST TO 5TH FLOOR) @3.00+ Level",
             "Terrace Floor @18.00+ Level"])
        found = floor_plans.autodetect_storeys(records, texts)
        typical = found.plans[1]
        self.assertEqual(typical["repeat"], 5)
        self.assertEqual(typical["height_mm"], 3000.0)   # 15000 over 5 storeys
        self.assertEqual(found.storey_count, 7)

    def test_titles_without_elevations_leave_heights_blank(self):
        records, texts = self._sheet(["GROUND FLOOR FRAMING PLAN",
                                      "FIRST FLOOR FRAMING PLAN"])
        found = floor_plans.autodetect_storeys(records, texts)
        self.assertEqual([p["height_mm"] for p in found.plans], [None, None])



class NotesAreNotPlanTitles(unittest.TestCase):
    """Test12 named four of its five storeys from a general note.

    "2) THE BEAM & COLUMN SIZES MAY VARY AT GROUND & PODIUM LEVEL." mentions
    GROUND, so every boxed plan that could see it came out order 0 called
    "GROUND". A note is numbered, or a whole sentence; a plan caption is
    neither, and is never that long.
    """

    NOTE = "2) THE BEAM & COLUMN SIZES MAY VARY AT GROUND & PODIUM LEVEL."

    def test_a_numbered_note_names_no_storey(self):
        self.assertIsNone(floor_plans.level_order_from_text(self.NOTE))
        self.assertFalse(floor_plans.looks_like_a_plan_title(self.NOTE))

    def test_other_note_shapes_are_refused_too(self):
        for note in ("(a) REFER TO THE GROUND FLOOR PLAN FOR DETAILS",
                     "1. ALL LEVELS ARE IN METRES ABOVE DATUM.",
                     "THE TERRACE SLAB SHALL BE CAST IN ONE POUR AFTER CURING."):
            self.assertIsNone(floor_plans.level_order_from_text(note), note)

    def test_real_captions_still_name_their_storey(self):
        for caption, order in (
                ("GROUND FLOOR PLAN", 0),
                ("FIRST FLOOR", 1),
                ("2ND FLOOR PLAN", 2),
                ("TERRACE PLAN", 999),
                ("Basement Plan", -1),
                ("Ground Floor @0.00+ Level", 0),
                ("UPPER BASEMENT FRAMING PLAN\n(SCALE 1:75)", -1),
                ("TYPICAL FLOOR PLAN (2ND TO 8TH FLOOR)", 2)):
            self.assertEqual(floor_plans.level_order_from_text(caption), order,
                             caption)

    def test_a_caption_ending_in_a_full_stop_is_still_a_caption(self):
        # short enough to be a caption: only a long sentence is a note
        self.assertEqual(floor_plans.level_order_from_text("GROUND FLOOR."), 0)

    def test_a_long_caption_that_starts_with_layout_is_still_a_caption(self):
        # "LAYOUT AT PARAPET & LMR BOTTOM LVL." is six words and ends in a stop,
        # but a caption announces itself in its first word
        self.assertTrue(floor_plans.looks_like_a_plan_title(
            "LAYOUT AT PARAPET & LMR BOTTOM LVL."))
        self.assertFalse(floor_plans.looks_like_a_plan_title(
            "THE TERRACE SLAB SHALL BE CAST IN ONE POUR AFTER CURING."))


class PlansWithoutAnOrdinal(unittest.TestCase):
    """Test12: four of five captions name no ordinal at all.

    "LAYOUT AT REFUGE FLOOR LVL." is a real title -- it just says nothing the
    sort understands, so the storey used to come out unnamed and was pushed to
    the bottom of the stack. It should keep its name and hold its place on the
    sheet.
    """

    def test_a_caption_without_an_ordinal_still_names_the_storey(self):
        label, order, repeat, elevation = floor_plans.describe_plan(
            [_Text("LAYOUT AT REFUGE FLOOR LVL.", 0, 0)])
        self.assertEqual(label, "LAYOUT AT REFUGE FLOOR LVL.")
        self.assertIsNone(order)
        self.assertEqual(repeat, 1)
        self.assertIsNone(elevation)

    def test_an_ordinal_caption_still_wins_over_a_plain_one(self):
        label, order, _repeat, _elev = floor_plans.describe_plan(
            [_Text("LAYOUT AT REFUGE FLOOR LVL.", 0, 0),
             _Text("LAYOUT AT 2ND FLOOR LVL.", 0, 0)])
        self.assertEqual(label, "LAYOUT AT 2ND FLOOR LVL.")
        self.assertEqual(order, 2)

    def test_a_dimension_or_a_mark_never_names_a_storey(self):
        for junk in ("C12", "300 X 600", "4500", "S1 200 THK."):
            label, order, _repeat, _elev = floor_plans.describe_plan(
                [_Text(junk, 0, 0)])
            self.assertIsNone(label, junk)
            self.assertIsNone(order, junk)

    def test_the_elevation_can_live_in_a_note_of_its_own(self):
        _label, _order, _repeat, elevation = floor_plans.describe_plan(
            [_Text("LAYOUT AT 2ND FLOOR LVL.", 0, 0),
             _Text("+8.600M LVL.", 0, -1000)])
        self.assertEqual(elevation, 8600.0)

    def test_a_trailing_elevation_note_parses(self):
        self.assertEqual(floor_plans.elevation_from_text("+76.450M LVL."),
                         76450.0)
        self.assertEqual(floor_plans.elevation_from_text("+11.550M LVL."),
                         11550.0)


class SheetReadingOrder(unittest.TestCase):
    """Where an untitled plan belongs in the stack."""

    # test12's layout: five plans in one row, differing in height by metres
    _ROW = [(0, 5291, 148078, 55845), (180642, 5291, 328513, 53815),
            (346832, 5291, 494704, 60826), (513616, 5291, 661488, 53815),
            (709484, 5291, 857355, 59166)]

    def test_one_row_of_unequal_plans_reads_left_to_right(self):
        self.assertEqual(floor_plans.sheet_sequence(self._ROW), [0, 1, 2, 3, 4])

    def test_two_rows_read_top_first(self):
        boxes = [(0, 0, 100, 100), (200, 0, 300, 100),
                 (0, 200, 100, 300), (200, 200, 300, 300)]
        self.assertEqual(floor_plans.sheet_sequence(boxes), [2, 3, 0, 1])

    def test_an_untitled_plan_holds_its_place_between_titled_ones(self):
        # 2ND(2), TYPICAL(?), REFUGE(?), TERRACE(999), PARAPET(?)
        orders = floor_plans.sheet_orders(self._ROW, [2, None, None, 999, None])
        self.assertEqual(orders[0], 2)
        self.assertEqual(orders[3], 999)
        self.assertTrue(2 < orders[1] < orders[2] < 999,
                        "untitled plans out of sheet order: %s" % (orders,))
        self.assertGreater(orders[4], 999)      # above the terrace, as drawn

    def test_a_sheet_with_no_titles_reads_in_layout_order(self):
        orders = floor_plans.sheet_orders(self._ROW, [None] * 5)
        self.assertEqual(orders, [0, 1, 2, 3, 4])

    def test_a_fully_titled_sheet_is_untouched(self):
        orders = floor_plans.sheet_orders(self._ROW, [0, 1, 2, 3, 999])
        self.assertEqual(orders, [0, 1, 2, 3, 999])


if __name__ == "__main__":
    unittest.main()

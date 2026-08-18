# -*- coding: utf-8 -*-
"""Wall planning: outlines, face pairs, and everything the corpus taught it.

The real-fixture coordinates below are EXACT record points lifted from the
three wall-bearing drawings (probe over tests/fixtures/cad, millimetres as the
DXF stores them, scaled to feet here the way the sweep scales every record).
They pin the planner to what the drawings actually contain:

  * test8's S-RCC-WALL: a 150 x 12490 closed quad, a 250 x 12611 quad rotated
    10.3 degrees off axis, and an L-shaped core drawn as OUTER and INNER open
    faces in sibling records -- the pair pass must read three walls off those
    two records, each spanning the UNION of its faces.
  * test9's PI_RETAINING WALL: two 300-apart lines whose spans are offset,
    and PI_SHEAR WALL CUTOUT's door quads, which must be refused by NAME --
    at 240..500 wide they are inside the wall band, so no width rule can.
  * Project1's PARAPET WALL: a closed rectilinear ring one thickness wide
    (decomposes to three walls) and a U open by exactly one wall width, and
    A-WALL-CUT-Brick's 10.3-degree door jamb, whose two angled legs pair.

The synthetic cases cover what the corpus states only implicitly: the door
bridge (collinear stubs merge across a door-sized gap, and NOT across more),
smallest-gap-first binding, the width band, and the overlap tolerance knob.
"""

import unittest

import _loader


wall_plan, layers = _loader.load("wall_plan", "classify.layers")

_MM = 304.8


def _ft(value):
    return value / _MM


class _Record(object):
    """A record as apply_mapping leaves it: points in internal feet."""

    def __init__(self, points_mm, layer="wall", kind="polyline",
                 category=layers.CATEGORY_ARCH_WALL):
        self.points = [(_ft(x), _ft(y), 0.0) for x, y in points_mm]
        self.layer = layer
        self.kind = kind
        self.category = category

    @property
    def layer_key(self):
        return self.layer


def _struct(points_mm, layer="S-RCC-WALL", kind="polyline"):
    return _Record(points_mm, layer, kind, layers.CATEGORY_STRUCT_WALL)


def _line(a, b, **kw):
    kw.setdefault("kind", "line")
    return _Record([a, b], **kw)


def _ends_mm(segment):
    sx, sy = segment["start"][0] * _MM, segment["start"][1] * _MM
    ex, ey = segment["end"][0] * _MM, segment["end"][1] * _MM
    return (round(sx, 1), round(sy, 1)), (round(ex, 1), round(ey, 1))


class TheRccToken(unittest.TestCase):
    """The classification fix that routes S-RCC-WALL to the structural pass."""

    def test_an_rcc_wall_is_structural(self):
        # test8's S-RCC-WALL (29 records) used to fall through to the arch
        # row on its "wall" token; RCC is reinforced concrete.
        self.assertEqual(layers.classify_layer("S-RCC-WALL"),
                         layers.CATEGORY_STRUCT_WALL)

    def test_the_other_rcc_layers_do_not_move(self):
        # The full 72-layer corpus dump moved exactly one layer when the rcc
        # token was added: these two are claimed by earlier convention rows.
        self.assertEqual(layers.classify_layer("S-RCC-COL"),
                         layers.CATEGORY_COLUMN)
        self.assertEqual(layers.classify_layer("PI_RCC BEAM"),
                         layers.CATEGORY_BEAM)

    def test_the_wall_rows_around_it_are_unchanged(self):
        self.assertEqual(layers.classify_layer("PI_RETAINING WALL"),
                         layers.CATEGORY_STRUCT_WALL)
        self.assertEqual(layers.classify_layer("A-WALL-CUT-Brick"),
                         layers.CATEGORY_ARCH_WALL)
        self.assertEqual(layers.classify_layer("PARAPET WALL"),
                         layers.CATEGORY_ARCH_WALL)


class ClosedOutlines(unittest.TestCase):
    """A closed thin ring IS the wall -- test8 and Project1 coordinates."""

    def test_test8s_rcc_quad_reads_straight_off_the_outline(self):
        record = _struct([(25090.0, 37810.0), (37580.0, 37810.0),
                          (37580.0, 37660.0), (25090.0, 37660.0),
                          (25090.0, 37810.0)])
        plan = wall_plan.plan_walls([record])
        self.assertEqual(plan["skipped"], [])
        self.assertEqual(len(plan["segments"]), 1)
        seg = plan["segments"][0]
        self.assertEqual(seg["kind"], "structural")
        self.assertEqual(seg["source"], "outline")
        self.assertAlmostEqual(seg["width_mm"], 150.0, places=1)
        self.assertAlmostEqual(seg["length_mm"], 12490.0, places=1)
        start, end = _ends_mm(seg)
        self.assertEqual(sorted([start, end]),
                         [(25090.0, 37735.0), (37580.0, 37735.0)])

    def test_test8s_rotated_quad_is_not_flattened_onto_an_axis(self):
        # 10.3 degrees off axis: the centreline must stay on the quad's own
        # long axis, joining the two short edges' midpoints.
        record = _struct([(30518.6, 21633.5), (32780.5, 34040.0),
                          (33026.5, 33995.2), (30764.6, 21588.7),
                          (30518.6, 21633.5)])
        plan = wall_plan.plan_walls([record])
        self.assertEqual(len(plan["segments"]), 1)
        seg = plan["segments"][0]
        self.assertEqual(seg["source"], "outline")
        self.assertAlmostEqual(seg["width_mm"], 250.0, delta=0.5)
        self.assertAlmostEqual(seg["length_mm"], 12611.0, delta=1.0)
        start, end = _ends_mm(seg)
        self.assertEqual(sorted([start, end]),
                         [(30641.6, 21611.1), (32903.5, 34017.6)])

    def test_project1s_parapet_ring_decomposes_into_three_walls(self):
        record = _Record([(164036.8, 15716.4), (166746.8, 15716.4),
                          (166746.8, 13916.4), (164036.8, 13916.4),
                          (164036.8, 13766.4), (166896.8, 13766.4),
                          (166896.8, 15866.4), (164036.8, 15866.4),
                          (164036.8, 15716.4)], layer="PARAPET WALL")
        plan = wall_plan.plan_walls([record])
        self.assertEqual(plan["skipped"], [])
        self.assertEqual(sorted(round(s["length_mm"]) for s in
                                plan["segments"]), [1950, 2710, 2860])
        for seg in plan["segments"]:
            self.assertAlmostEqual(seg["width_mm"], 150.0, places=1)
            self.assertEqual(seg["source"], "outline")
            self.assertEqual(seg["kind"], "arch")

    def test_a_u_open_by_one_wall_width_is_the_outline_it_meant_to_be(self):
        # Project1's parapet run, drawn without its far end cap: the ends sit
        # exactly 150 apart. Read as the closed quad it is.
        record = _Record([(168346.8, 26356.4), (164036.8, 26356.4),
                          (164036.8, 26206.4), (168346.8, 26206.4)],
                         layer="PARAPET WALL")
        plan = wall_plan.plan_walls([record])
        self.assertEqual(len(plan["segments"]), 1)
        seg = plan["segments"][0]
        self.assertEqual(seg["source"], "outline")
        self.assertAlmostEqual(seg["width_mm"], 150.0, places=1)
        self.assertAlmostEqual(seg["length_mm"], 4310.0, places=1)
        start, end = _ends_mm(seg)
        self.assertEqual(sorted([start, end]),
                         [(164036.8, 26281.4), (168346.8, 26281.4)])

    def test_a_room_sized_ring_is_never_a_wall_outline(self):
        # A closed quad far wider than any wall: its faces join the pair
        # pool instead, and with no partner in band they are all reported.
        record = _Record([(0.0, 0.0), (4000.0, 0.0), (4000.0, 5000.0),
                          (0.0, 5000.0), (0.0, 0.0)])
        plan = wall_plan.plan_walls([record])
        self.assertEqual(plan["segments"], [])
        self.assertEqual(len(plan["skipped"]), 4)
        for skip in plan["skipped"]:
            self.assertIn("no parallel partner", skip["reason"])


class FacePairs(unittest.TestCase):
    """Loose faces pair into walls -- test8, test9, Project1 coordinates."""

    def test_test8s_core_reads_three_walls_off_its_two_face_records(self):
        # The OUTER and INNER faces of an L-shaped core, sibling records.
        # The inner face is one wall width shorter at every turn; the union
        # span must land each wall on its full drawn extent regardless.
        outer = _struct([(800.0, 8990.0), (0.0, 8990.0),
                         (0.0, 0.0), (3660.0, 0.0)])
        inner = _struct([(800.0, 8840.0), (150.0, 8840.0),
                         (150.0, 150.0), (3660.0, 150.0)])
        plan = wall_plan.plan_walls([outer, inner])
        self.assertEqual(plan["skipped"], [])
        self.assertEqual(sorted(round(s["length_mm"]) for s in
                                plan["segments"]), [800, 3660, 8990])
        for seg in plan["segments"]:
            self.assertAlmostEqual(seg["width_mm"], 150.0, places=1)
            self.assertEqual(seg["kind"], "structural")
            self.assertEqual(seg["source"], "pair")
        spine = max(plan["segments"], key=lambda s: s["length_mm"])
        start, end = _ends_mm(spine)
        self.assertEqual(sorted([start, end]),
                         [(75.0, 0.0), (75.0, 8990.0)])

    def test_test9s_retaining_wall_pairs_across_offset_spans(self):
        first = _line((9777.9, 27977.0), (23182.9, 27977.0),
                      layer="PI_RETAINING WALL",
                      category=layers.CATEGORY_STRUCT_WALL)
        second = _line((22882.9, 27677.0), (9777.9, 27677.0),
                       layer="PI_RETAINING WALL",
                       category=layers.CATEGORY_STRUCT_WALL)
        plan = wall_plan.plan_walls([first, second])
        self.assertEqual(len(plan["segments"]), 1)
        seg = plan["segments"][0]
        self.assertAlmostEqual(seg["width_mm"], 300.0, places=1)
        self.assertAlmostEqual(seg["length_mm"], 13405.0, places=1)
        start, end = _ends_mm(seg)
        self.assertEqual(sorted([start, end]),
                         [(9777.9, 27827.0), (23182.9, 27827.0)])

    def test_project1s_angled_door_jamb_pairs_its_own_legs(self):
        # One brick record, 10.3 degrees off axis: its two long legs are
        # parallel 150 apart and must pair WITHOUT being flattened; the
        # 150-long stroke that closes the jamb is reported, not planned.
        record = _Record([(97891.1, 41869.3), (98085.6, 42936.3),
                          (97735.6, 42936.3), (97735.6, 42786.3),
                          (97905.8, 42786.3), (97743.5, 41896.2)],
                         layer="A-WALL-CUT-Brick")
        plan = wall_plan.plan_walls([record])
        widths = [round(s["width_mm"], 1) for s in plan["segments"]]
        self.assertEqual(len(plan["segments"]), 2)
        self.assertTrue(all(149.0 <= w <= 151.0 for w in widths), widths)
        angled = max(plan["segments"], key=lambda s: s["length_mm"])
        self.assertAlmostEqual(angled["length_mm"], 1084.6, delta=0.5)
        for skip in plan["skipped"]:
            self.assertIn("end cap", skip["reason"])

    def test_a_gap_wider_than_any_wall_pairs_nothing(self):
        # 600 apart: outside the measured band (real widths 100..495; the
        # 565..900 candidates are door artifacts). Both faces are reported.
        plan = wall_plan.plan_walls([
            _line((0.0, 0.0), (3000.0, 0.0)),
            _line((0.0, 600.0), (3000.0, 600.0))])
        self.assertEqual(plan["segments"], [])
        self.assertEqual(len(plan["skipped"]), 2)
        for skip in plan["skipped"]:
            self.assertIn("no parallel partner", skip["reason"])

    def test_the_smallest_gap_binds_first(self):
        # Three parallel faces at 0, 150 and 400: the 150 pair is the wall,
        # and the far face must not reach across it (250 is in band too).
        plan = wall_plan.plan_walls([
            _line((0.0, 0.0), (3000.0, 0.0)),
            _line((0.0, 150.0), (3000.0, 150.0)),
            _line((0.0, 400.0), (3000.0, 400.0))])
        self.assertEqual(len(plan["segments"]), 1)
        self.assertAlmostEqual(plan["segments"][0]["width_mm"], 150.0,
                               places=1)
        self.assertEqual(len(plan["skipped"]), 1)

    def test_structural_and_arch_faces_never_pair_with_each_other(self):
        plan = wall_plan.plan_walls([
            _line((0.0, 0.0), (3000.0, 0.0),
                  layer="PI_RETAINING WALL",
                  category=layers.CATEGORY_STRUCT_WALL),
            _line((0.0, 150.0), (3000.0, 150.0))])
        self.assertEqual(plan["segments"], [])
        self.assertEqual(len(plan["skipped"]), 2)


class TheDoorBridge(unittest.TestCase):
    """Collinear faces merge across a door, and only across a door."""

    def test_a_door_split_face_is_still_one_wall(self):
        # The near face is drawn as two stubs either side of a 1000 door
        # (test8's doors measure 750..1310). One wall, spanning everything.
        plan = wall_plan.plan_walls([
            _line((0.0, 0.0), (5000.0, 0.0)),
            _line((0.0, 150.0), (1800.0, 150.0)),
            _line((2800.0, 150.0), (5000.0, 150.0))])
        self.assertEqual(plan["skipped"], [])
        self.assertEqual(len(plan["segments"]), 1)
        seg = plan["segments"][0]
        self.assertAlmostEqual(seg["length_mm"], 5000.0, places=1)
        self.assertAlmostEqual(seg["width_mm"], 150.0, places=1)

    def test_a_gap_wider_than_a_door_splits_the_wall(self):
        # Both faces interrupted by 1400 -- beyond every measured door.
        # Two walls, one either side of the gap.
        plan = wall_plan.plan_walls([
            _line((0.0, 0.0), (1800.0, 0.0)),
            _line((3200.0, 0.0), (5000.0, 0.0)),
            _line((0.0, 150.0), (1800.0, 150.0)),
            _line((3200.0, 150.0), (5000.0, 150.0))])
        self.assertEqual(plan["skipped"], [])
        self.assertEqual(sorted(round(s["length_mm"]) for s in
                                plan["segments"]), [1800, 1800])

    def test_a_teed_walls_end_cap_completes_the_face_it_interrupts(self):
        # A tee: the crossing wall cuts its host's near face by its own
        # width, and its end cap lies exactly in that cut. The host must
        # still plan as ONE wall over the join.
        plan = wall_plan.plan_walls([
            _line((0.0, 0.0), (5000.0, 0.0)),
            _line((0.0, 150.0), (2425.0, 150.0)),
            _line((2575.0, 150.0), (5000.0, 150.0)),
            _line((2425.0, 150.0), (2575.0, 150.0)),   # the tee'd cap
            _line((2425.0, 150.0), (2425.0, 3000.0)),
            _line((2575.0, 150.0), (2575.0, 3000.0))])
        lengths = sorted(round(s["length_mm"]) for s in plan["segments"])
        self.assertEqual(lengths, [2850, 5000])
        self.assertEqual(plan["skipped"], [])


class WhatIsRefused(unittest.TestCase):
    """Nothing consumed leaves without a reason."""

    def test_test9s_door_cutout_quads_are_refused_by_name(self):
        # 399.6 x 1000: inside the wall band, indistinguishable by width.
        # The layer's own name (and test9's legend) says it is a hole.
        record = _struct([(103831.8, 15853.3), (103831.8, 14853.3),
                          (103432.2, 14853.3), (103432.2, 15853.3),
                          (103831.8, 15853.3)],
                         layer="PI_SHEAR WALL CUTOUT")
        plan = wall_plan.plan_walls([record])
        self.assertEqual(plan["segments"], [])
        self.assertEqual(len(plan["skipped"]), 1)
        self.assertIn("cutout", plan["skipped"][0]["reason"])
        self.assertEqual(plan["skipped"][0]["kind"], "structural")

    def test_test9s_zero_length_stone_lines_are_reported(self):
        record = _line((32057.8, 11533.1), (32057.8, 11533.1),
                       layer="PI_STONE WALL")
        plan = wall_plan.plan_walls([record])
        self.assertEqual(plan["segments"], [])
        self.assertEqual(plan["skipped"][0]["reason"],
                         "degenerate (zero length)")

    def test_an_arc_on_a_wall_layer_is_reported_not_dropped(self):
        record = _Record([(0.0, 0.0), (500.0, 500.0), (1000.0, 0.0)],
                         kind="arc")
        plan = wall_plan.plan_walls([record])
        self.assertEqual(plan["segments"], [])
        self.assertIn("unsupported kind", plan["skipped"][0]["reason"])

    def test_records_of_other_categories_are_not_consumed(self):
        record = _line((0.0, 0.0), (3000.0, 0.0), layer="S-BEAM",
                       category=layers.CATEGORY_BEAM)
        plan = wall_plan.plan_walls([record])
        self.assertEqual(plan, {"segments": [], "skipped": []})


class TheToleranceRoute(unittest.TestCase):
    """The pair knobs arrive the way the beam pass takes them."""

    def test_the_overlap_floor_is_config_defaulted_and_overridable(self):
        # 100 of shared run: under the 150 default, so no pair -- until the
        # caller lowers pair_min_overlap_mm, the same knob beams use.
        lines = [_line((0.0, 0.0), (3000.0, 0.0)),
                 _line((2900.0, 150.0), (5900.0, 150.0))]
        refused = wall_plan.plan_walls(lines)
        self.assertEqual(refused["segments"], [])
        allowed = wall_plan.plan_walls(
            lines, tolerances={"pair_min_overlap_mm": 50.0})
        self.assertEqual(len(allowed["segments"]), 1)
        # the pair still spans the union of both faces
        self.assertAlmostEqual(allowed["segments"][0]["length_mm"], 5900.0,
                               places=1)


if __name__ == "__main__":
    unittest.main()

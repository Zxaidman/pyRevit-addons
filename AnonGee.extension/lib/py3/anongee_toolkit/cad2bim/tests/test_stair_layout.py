# -*- coding: utf-8 -*-
"""stair_layout -- generic dog-leg staircases located by plan text (option 1).

Covered on synthetic plans: the stair/direction text parsing; the dog-leg
numbers (riser count from the storey height, split across two runs, actual
riser recomputed); geometry (runs along the bay's long axis, both anchored at
the landing edge, landing at the DN end); the does-not-fit and squeezed-width
notes; and the keep_points face relaxation that hands a WALL-bounded bay to the
stair layout (the slab chain drops it as a shaft). Standalone (no Revit).
"""

import math
import os
import sys
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_MM = 304.8
_FT = 1.0 / _MM


stair_layout, stair_runs, slab_outlines, layers = _loader.load(
    "stair_layout", "stair_runs", "slab_outlines", "classify.layers")


class _Rec(object):
    def __init__(self, kind, pts, category):
        self.kind = kind
        self.points = [(p[0], p[1], 0.0) for p in pts]
        self.layer = "TEST"
        self.layer_key = "TEST"
        self.category = category


class _Text(object):
    def __init__(self, text, x_mm, y_mm):
        self.text = text
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _wall_bay(x0, y0, x1, y1):
    """A closed rectangle of column-layer (wall) lines, mm in / ft out."""
    c = [(x0 * _FT, y0 * _FT), (x1 * _FT, y0 * _FT),
         (x1 * _FT, y1 * _FT), (x0 * _FT, y1 * _FT)]
    return [_Rec("line", [c[i], c[(i + 1) % 4]], layers.CATEGORY_COLUMN)
            for i in range(4)]


_PARAMS = {"riser_mm": 150.0, "tread_mm": 300.0, "run_width_mm": 1250.0,
           "landing_mm": 0.0}


class StairText(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(stair_layout.stair_label("STAIRCASE"), "ST")
        self.assertEqual(stair_layout.stair_label("Staircase "), "ST")
        self.assertEqual(stair_layout.stair_label("STAIR"), "ST")
        self.assertEqual(stair_layout.stair_label("ST-1"), "ST-1")
        self.assertEqual(stair_layout.stair_label("st 2"), "ST-2")
        self.assertEqual(stair_layout.stair_label("ST3"), "ST-3")
        self.assertIsNone(stair_layout.stair_label("STIRRUP"))
        self.assertIsNone(stair_layout.stair_label("S1 150 THK"))
        self.assertIsNone(stair_layout.stair_label(None))

    def test_direction(self):
        self.assertEqual(stair_layout.direction_label("DN"), "DN")
        self.assertEqual(stair_layout.direction_label("dn."), "DN")
        self.assertEqual(stair_layout.direction_label("UP"), "UP")
        self.assertIsNone(stair_layout.direction_label("DOWN TOWN"))


class DoglegNumbers(unittest.TestCase):
    def _ring(self, w_mm=3000.0, l_mm=6000.0):
        return [(0.0, 0.0), (l_mm * _FT, 0.0), (l_mm * _FT, w_mm * _FT),
                (0.0, w_mm * _FT)]

    def test_riser_count_and_split(self):
        plan, note = stair_layout.plan_dogleg_stair(
            self._ring(), 0.0, "ST-1", _PARAMS, 3000.0)
        self.assertIsNone(note)
        self.assertEqual(plan["risers_total"], 20)
        self.assertAlmostEqual(plan["riser_mm"], 150.0)
        self.assertEqual([r["risers"] for r in plan["runs"]], [10, 10])

    def test_odd_storey_rounds_up(self):
        plan, _n = stair_layout.plan_dogleg_stair(
            self._ring(), 0.0, "ST-1", _PARAMS, 3100.0)
        self.assertEqual(plan["risers_total"], 21)          # 3100/150 -> 20.7
        self.assertAlmostEqual(plan["riser_mm"], 3100.0 / 21, places=4)
        self.assertEqual([r["risers"] for r in plan["runs"]], [11, 10])

    def test_runs_along_long_axis_anchored_at_landing(self):
        plan, _n = stair_layout.plan_dogleg_stair(
            self._ring(), 0.0, "ST-1", _PARAMS, 3000.0)
        (x1, y1), (x2, y2) = plan["runs"][0]["start"], plan["runs"][0]["end"]
        self.assertAlmostEqual(y1, y2, places=6)            # along x = long axis
        run_len_mm = abs(x2 - x1) * _MM
        self.assertAlmostEqual(run_len_mm, 10 * 300.0, places=3)
        # both runs turn at the same axis coordinate (the landing edge)
        e1 = plan["runs"][0]["end"][0]
        s2 = plan["runs"][1]["start"][0]
        self.assertAlmostEqual(e1, s2, places=6)
        # landing depth defaults to the run width
        self.assertAlmostEqual(plan["landing_mm"], 1250.0)

    def test_landing_at_dn_text_end(self):
        ring = self._ring()
        dn_near_x0 = [(300.0 * _FT, 1500.0 * _FT, "DN")]
        plan, _n = stair_layout.plan_dogleg_stair(
            ring, 0.0, "ST-1", _PARAMS, 3000.0, direction_texts=dn_near_x0)
        # landing edge must sit near x = 0 (the DN end): the turn coordinate is
        # landing depth away from that end
        turn_x_mm = plan["runs"][0]["end"][0] * _MM
        self.assertAlmostEqual(turn_x_mm, 1250.0, places=3)

    def test_riser_count_absolute(self):
        params = dict(_PARAMS, riser_count=18)
        plan, _n = stair_layout.plan_dogleg_stair(
            self._ring(), 0.0, "ST-1", params, 3000.0)
        self.assertEqual(plan["risers_total"], 18)     # count wins over riser max
        self.assertAlmostEqual(plan["riser_mm"], 3000.0 / 18, places=4)
        self.assertEqual([r["risers"] for r in plan["runs"]], [9, 9])

    def test_top_landing_beyond_last_run(self):
        plan, _n = stair_layout.plan_dogleg_stair(
            self._ring(), 0.0, "ST-1", _PARAMS, 3000.0)
        top = plan["top_landing"]
        self.assertEqual(len(top), 4)
        run2 = plan["runs"][1]
        # the landing continues past run2's END in the run direction
        (sx, sy), (ex, ey) = run2["start"], run2["end"]
        dx = 1.0 if ex > sx else -1.0
        xs = [p[0] for p in top]
        self.assertAlmostEqual(min(xs) if dx < 0 else max(xs),
                               ex + dx * plan["landing_mm"] / _MM, places=6)
        # and spans BOTH flights like the half landing (the U-stair rule):
        # two runs of the dialog width, side by side
        ys = sorted(p[1] * _MM for p in top)
        self.assertAlmostEqual(ys[-1] - ys[0], 2 * 1250.0, places=3)

    def test_flights_keep_the_dialog_run_width(self):
        """A wide drawn outline must not stretch the flights: both keep the
        run width the dialog asked for, and the half landing spans the pair."""
        plan, note = stair_layout.plan_dogleg_stair(
            self._ring(w_mm=6000.0), 0.0, "ST-1", _PARAMS, 3000.0)
        self.assertIsNone(note)
        for run in plan["runs"]:
            self.assertAlmostEqual(run["width_mm"], 1250.0, places=6)
        # the two centrelines sit exactly one run width apart
        gap = abs(plan["runs"][0]["start"][1] - plan["runs"][1]["start"][1]) * _MM
        self.assertAlmostEqual(gap, 1250.0, places=3)
        # the half landing spans both flights, not the 6 m bay
        landing = plan["landing"]
        self.assertEqual(len(landing), 4)
        span = sorted(p[1] * _MM for p in landing)
        self.assertAlmostEqual(span[-1] - span[0], 2 * 1250.0, places=3)
        # ... and is exactly the landing depth deep, at the turn
        depth = sorted(p[0] * _MM for p in landing)
        self.assertAlmostEqual(depth[-1] - depth[0], plan["landing_mm"],
                               places=3)

    def test_does_not_fit(self):
        plan, note = stair_layout.plan_dogleg_stair(
            self._ring(l_mm=3000.0), 0.0, "ST-1", _PARAMS, 3000.0)
        self.assertIsNone(plan)
        self.assertIn("bay is", note)

    def test_narrow_bay_squeezes_width(self):
        plan, note = stair_layout.plan_dogleg_stair(
            self._ring(w_mm=2000.0), 0.0, "ST-1", _PARAMS, 3000.0)
        self.assertIsNotNone(plan)
        self.assertIn("squeezed", note)
        self.assertAlmostEqual(plan["run_width_mm"], 1000.0)


class KeepPointsFace(unittest.TestCase):
    def test_wall_bay_kept_only_with_keep_points(self):
        recs = _wall_bay(0.0, 0.0, 4000.0, 4000.0)
        centre = (2000.0 * _FT, 2000.0 * _FT)
        dropped = slab_outlines.slab_loops_from_placed_members(recs, [])
        self.assertEqual(dropped, [])
        kept = slab_outlines.slab_loops_from_placed_members(
            recs, [], keep_points=[centre])
        self.assertEqual(len(kept), 1)
        area_m2 = abs(slab_outlines._signed_area(kept[0][0])) * _MM * _MM / 1e6
        self.assertAlmostEqual(area_m2, 16.0, places=1)


def _linework_stair(x0_mm=11150.0, turn_mm=12650.0, last_mm=15350.0,
                    y0_mm=23150.0, mid_mm=24650.0, y1_mm=26150.0):
    """Riser + boundary lines mirroring the StaircasePlan-Test1 ST-1 geometry:
    two stacked runs (across y), vertical risers every 300 mm from `turn_mm` to
    `last_mm` drawn ONCE PER RUN (duplicates), and a drawn half landing between
    x0_mm and turn_mm spanning both runs."""
    recs = []

    def line(ax, ay, bx, by):
        recs.append(_Rec("line", [(ax * _FT, ay * _FT), (bx * _FT, by * _FT)],
                         layers.CATEGORY_STAIR))

    x = turn_mm
    while x <= last_mm + 0.5:
        line(x, y0_mm, x, mid_mm)          # lower-run riser
        line(x, mid_mm, x, y1_mm)          # upper-run riser (same position)
        x += 300.0
    line(x0_mm, y0_mm, turn_mm, y0_mm)     # landing boundary
    line(x0_mm, y1_mm, turn_mm, y1_mm)
    line(x0_mm, y0_mm, x0_mm, y1_mm)
    return recs


class LineworkStairs(unittest.TestCase):
    def test_runs_measured_from_riser_lines(self):
        recs = _linework_stair()
        plans, notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0, texts=[_Text("ST-1", 13679.0, 24513.0)])
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan["source"], "stair_linework")
        self.assertEqual(plan["mark"], "ST-1")
        self.assertEqual([r["risers"] for r in plan["runs"]], [10, 10])
        self.assertEqual(plan["risers_total"], 20)
        self.assertAlmostEqual(plan["riser_mm"], 150.0)
        self.assertAlmostEqual(plan["tread_mm"], 300.0, places=3)
        self.assertAlmostEqual(plan["run_width_mm"], 1500.0, places=3)
        self.assertAlmostEqual(plan["landing_mm"], 1500.0, places=3)
        # first run climbs INTO the landing edge (drawn at x = 12650)
        run1, run2 = plan["runs"]
        self.assertAlmostEqual(run1["end"][0] * _MM, 12650.0, places=2)
        self.assertAlmostEqual(run1["start"][0] * _MM, 15350.0, places=2)
        self.assertAlmostEqual(run2["start"][0] * _MM, 12650.0, places=2)
        # runs sit on the two run centrelines (y 23900 and 25400)
        centres = sorted(round(r["start"][1] * _MM) for r in plan["runs"])
        self.assertEqual(centres, [23900, 25400])
        # arrival landing continues past run2's end (x 15350 + landing 1500)
        # and spans both flights (y 23150..26150) like the drawn half landing
        top = plan["top_landing"]
        self.assertEqual(len(top), 4)
        self.assertAlmostEqual(max(p[0] for p in top) * _MM, 16850.0, places=2)
        ys = sorted(p[1] * _MM for p in top)
        self.assertAlmostEqual(ys[-1] - ys[0], 3000.0, places=2)

    def test_winding_four_flight_stair(self):
        # Project1's square stair: four flights around a 1200 x 1800 well,
        # drawn exactly as in the 0.48.0 export (cluster 0 geometry).
        recs = []

        def line(ax, ay, bx, by):
            recs.append(_Rec("line", [(ax * _FT, ay * _FT), (bx * _FT, by * _FT)],
                             layers.CATEGORY_STAIR))

        for i in range(7):                       # left + right flights (7 each)
            y = 28206.0 + i * 300.0
            line(127801.0, y, 129301.0, y)
            line(130501.0, y, 132001.0, y)
        for i in range(5):                       # bottom flight (5 risers)
            x = 129301.0 + i * 300.0
            line(x, 26706.0, x, 28206.0)
        for i in range(3):                       # top flight (3 risers)
            x = 129901.0 + i * 300.0
            line(x, 30006.0, x, 31506.0)
        plans, notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(len(plan["runs"]), 4)
        self.assertEqual(plan["risers_total"], 22)
        self.assertEqual([r["risers"] for r in plan["runs"]], [5, 7, 3, 7])
        # consecutive flights meet at the corner landings (a well-sized hop)
        for first, second in zip(plan["runs"], plan["runs"][1:]):
            gap = math.hypot(second["start"][0] - first["end"][0],
                             second["start"][1] - first["end"][1]) * _MM
            self.assertLess(gap, 2300.0)
        # the arrival slab stays ONE run wide: the parallel flight is across
        # the well, not adjacent
        top = plan["top_landing"]
        span = (max(math.hypot(top[i][0] - top[j][0], top[i][1] - top[j][1])
                    for i in range(4) for j in range(4))) * _MM
        self.assertLess(span, 2300.0)            # 1500 wide x 1500 deep diagonal

    def test_landing_gap_splits_instead_of_voiding_the_flight(self):
        """test9's stairs: 11 risers at 300 mm, then 800 mm gaps to the landing
        and boundary lines. The odd gaps must SEGMENT the group, not reject it."""
        recs = []

        def line(ax, ay, bx, by):
            recs.append(_Rec("line", [(ax * _FT, ay * _FT), (bx * _FT, by * _FT)],
                             layers.CATEGORY_STAIR))

        for i in range(11):                       # the flight itself
            x = 1000.0 + i * 300.0
            line(x, 0.0, x, 1600.0)
        line(1000.0 + 10 * 300.0 + 800.0, 0.0, 1000.0 + 10 * 300.0 + 800.0, 1600.0)
        line(1000.0 + 10 * 300.0 + 1600.0, 0.0, 1000.0 + 10 * 300.0 + 1600.0, 1600.0)
        runs = stair_runs._riser_runs([(a, b) for a, b in
                                         ((tuple(r.points[0][:2]),
                                           tuple(r.points[1][:2])) for r in recs)])
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(runs[0]["positions"]), 11)

    def test_equidistant_chains_segment_at_odd_gaps(self):
        chains = stair_runs._equidistant_chains
        step = 300.0 * _FT
        pos = [(i * step, 0.0, 1.0) for i in range(11)]
        pos += [(10 * step + 800.0 * _FT, 0.0, 1.0),
                (10 * step + 1600.0 * _FT, 0.0, 1.0)]
        out = chains(pos)
        self.assertEqual([len(c) for c in out], [11])
        # two separate flights either side of a landing both survive
        pos2 = pos[:6] + [(20 * step, 0.0, 1.0), (21 * step, 0.0, 1.0),
                          (22 * step, 0.0, 1.0), (23 * step, 0.0, 1.0)]
        self.assertEqual([len(c) for c in chains(pos2)], [6, 4])

    def test_no_riser_lines_no_plan(self):
        recs = _wall_bay(0.0, 0.0, 4000.0, 4000.0)      # walls, no stair layer
        plans, _notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        self.assertEqual(plans, [])

    def test_two_clusters_two_stairs(self):
        recs = (_linework_stair() +
                _linework_stair(y0_mm=15650.0, mid_mm=17150.0, y1_mm=18650.0))
        plans, _notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        self.assertEqual(len(plans), 2)

    def test_chain_prefers_linework(self):
        recs = (_wall_bay(11000.0, 23000.0, 16500.0, 26300.0) +
                _linework_stair())
        texts = [_Text("ST-1", 13679.0, 24513.0)]
        plans, _notes = stair_layout.plan_stairs(recs, [], None, texts,
                                                 _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["source"], "stair_linework")

    def test_chain_falls_back_to_text(self):
        recs = _wall_bay(0.0, 0.0, 6000.0, 3000.0)
        texts = [_Text("STAIRCASE", 3000.0, 1500.0)]
        plans, _notes = stair_layout.plan_stairs(recs, [], None, texts,
                                                 _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["source"], "stair_text")


class ShapeStairs(unittest.TestCase):
    def test_l_shape_two_flights(self):
        recs = []

        def line(ax, ay, bx, by):
            recs.append(_Rec("line", [(ax * _FT, ay * _FT), (bx * _FT, by * _FT)],
                             layers.CATEGORY_STAIR))

        for i in range(8):                       # flight A along x (risers | y)
            x = 1000.0 + i * 300.0
            line(x, 0.0, x, 1500.0)
        for i in range(8):                       # flight B along y (risers | x)
            y = 3000.0 + i * 300.0
            line(3400.0, y, 4900.0, y)
        plans, _notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(len(plan["runs"]), 2)
        self.assertEqual(plan["risers_total"], 16)
        # the flights connect at ONE corner: end of run 1 near start of run 2
        first, second = plan["runs"]
        hop = math.hypot(second["start"][0] - first["end"][0],
                         second["start"][1] - first["end"][1]) * _MM
        self.assertLess(hop, 3600.0)

    def test_circular_stair_radial_risers(self):
        recs = []
        ccx, ccy = 10000.0, 10000.0
        r_in, r_out = 900.0, 2400.0
        for i in range(13):                      # radial risers over 270 deg
            ang = math.radians(i * 22.5)
            recs.append(_Rec("line", [
                ((ccx + r_in * math.cos(ang)) * _FT,
                 (ccy + r_in * math.sin(ang)) * _FT),
                ((ccx + r_out * math.cos(ang)) * _FT,
                 (ccy + r_out * math.sin(ang)) * _FT)],
                layers.CATEGORY_STAIR))
        plans, _notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        spiral = plan.get("spiral")
        self.assertIsNotNone(spiral)
        self.assertEqual(spiral["risers"], 13)
        self.assertAlmostEqual(spiral["center"][0] * _MM, ccx, delta=20.0)
        self.assertAlmostEqual(spiral["center"][1] * _MM, ccy, delta=20.0)
        self.assertAlmostEqual(spiral["radius"] * _MM, 1650.0, delta=30.0)
        self.assertAlmostEqual(spiral["width_mm"], 1500.0, delta=30.0)
        self.assertAlmostEqual(math.degrees(spiral["included_angle"]),
                               270.0, delta=2.0)
        self.assertAlmostEqual(plan["riser_mm"], 3000.0 / 13, places=3)

    def test_winder_corner_detected(self):
        # dog-leg flights plus three ANGLED risers fanning through the turn
        recs = _linework_stair()
        pivot = (12650.0, 24650.0)               # inner corner of the turn
        for deg in (30.0, 45.0, 60.0):
            ang = math.radians(180.0 - deg)
            recs.append(_Rec("line", [
                (pivot[0] * _FT, pivot[1] * _FT),
                ((pivot[0] + 1500.0 * math.cos(ang)) * _FT,
                 (pivot[1] + 1500.0 * math.sin(ang)) * _FT)],
                layers.CATEGORY_STAIR))
        plans, _notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        winders = plan.get("winders")
        self.assertEqual(len(winders), 1)
        self.assertEqual(winders[0]["after_run"], 0)
        self.assertEqual(len(winders[0]["riser_lines"]), 3)
        # winder risers join the storey division: 20 straight + 3 fan + 1
        self.assertEqual(plan["risers_total"], 24)
        self.assertAlmostEqual(plan["riser_mm"], 3000.0 / 24, places=3)


class GenericShapes(unittest.TestCase):
    def _ring(self, w_mm=4000.0, l_mm=8000.0):
        return [(0.0, 0.0), (l_mm * _FT, 0.0), (l_mm * _FT, w_mm * _FT),
                (0.0, w_mm * _FT)]

    def test_straight_is_one_flight(self):
        plan, _n = stair_layout.plan_shaped_stair(
            self._ring(), 0.0, "ST-1", _PARAMS, 3000.0,
            shape=stair_layout.SHAPE_STRAIGHT)
        self.assertEqual(len(plan["runs"]), 1)
        self.assertEqual(plan["runs"][0]["risers"], 20)
        self.assertEqual(plan["shape"], stair_layout.SHAPE_STRAIGHT)

    def test_u_is_two_flights(self):
        plan, _n = stair_layout.plan_shaped_stair(
            self._ring(), 0.0, "ST-1", _PARAMS, 3000.0,
            shape=stair_layout.SHAPE_U)
        self.assertEqual([r["risers"] for r in plan["runs"]], [10, 10])
        self.assertEqual(plan["shape"], stair_layout.SHAPE_U)

    def test_l_turns_one_corner(self):
        plan, _n = stair_layout.plan_shaped_stair(
            self._ring(), 0.0, "ST-1", _PARAMS, 3000.0,
            shape=stair_layout.SHAPE_L)
        self.assertEqual(len(plan["runs"]), 2)
        self.assertEqual(sum(r["risers"] for r in plan["runs"]), 20)
        first, second = plan["runs"]
        d1 = (first["end"][0] - first["start"][0],
              first["end"][1] - first["start"][1])
        d2 = (second["end"][0] - second["start"][0],
              second["end"][1] - second["start"][1])
        dot = d1[0] * d2[0] + d1[1] * d2[1]
        self.assertAlmostEqual(dot, 0.0, places=6)

    def test_c_wraps_three_sides(self):
        plan, _n = stair_layout.plan_shaped_stair(
            self._ring(), 0.0, "ST-1", _PARAMS, 3000.0,
            shape=stair_layout.SHAPE_C)
        self.assertEqual(len(plan["runs"]), 3)
        self.assertEqual(sum(r["risers"] for r in plan["runs"]), 20)
        d1 = plan["runs"][0]["end"][0] - plan["runs"][0]["start"][0]
        d3 = plan["runs"][2]["end"][0] - plan["runs"][2]["start"][0]
        self.assertLess(d1 * d3, 0.0)

    def test_circular_makes_a_spiral(self):
        plan, _n = stair_layout.plan_shaped_stair(
            self._ring(w_mm=5000.0, l_mm=5000.0), 0.0, "ST-1", _PARAMS, 3000.0,
            shape=stair_layout.SHAPE_CIRCULAR)
        spiral = plan["spiral"]
        self.assertEqual(plan["runs"], [])
        self.assertEqual(spiral["risers"], 20)
        self.assertAlmostEqual(spiral["width_mm"], 1250.0)
        self.assertGreater(spiral["included_angle"], 0.0)
        self.assertLessEqual(spiral["included_angle"], 2 * math.pi)

    def test_riser_count_absolute_across_shapes(self):
        params = dict(_PARAMS, riser_count=18)
        for shape in stair_layout.STAIR_SHAPES:
            plan, _n = stair_layout.plan_shaped_stair(
                self._ring(w_mm=5000.0, l_mm=8000.0), 0.0, "ST-1", params,
                3000.0, shape=shape)
            self.assertIsNotNone(plan, shape)
            self.assertEqual(plan["risers_total"], 18, shape)

    def test_region_source_uses_the_picked_rectangles(self):
        ring = self._ring()
        params = dict(_PARAMS, shape=stair_layout.SHAPE_L)
        plans, notes = stair_layout.plan_stairs([], [], None, [], params,
                                                3000.0, source="region",
                                                regions=[ring])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["source"], "picked_region")
        self.assertEqual(plans[0]["shape"], stair_layout.SHAPE_L)

    def test_region_source_without_regions_reports(self):
        plans, notes = stair_layout.plan_stairs([], [], None, [], _PARAMS,
                                                3000.0, source="region")
        self.assertEqual(plans, [])
        self.assertTrue(any("no region" in n for n in notes))


class FullPipeline(unittest.TestCase):
    def test_plan_stairs_from_texts(self):
        recs = _wall_bay(0.0, 0.0, 6000.0, 3000.0)
        texts = [_Text("STAIRCASE", 3000.0, 1500.0),
                 _Text("DN", 700.0, 2200.0),
                 _Text("C1 400x400", 500.0, 500.0)]
        plans, notes = stair_layout.plan_stairs(recs, [], None, texts,
                                                _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["mark"], "ST")
        self.assertEqual(plans[0]["risers_total"], 20)
        self.assertEqual(len(plans[0]["runs"]), 2)
        # DN sits near x=0: the landing (turn) edge is landing-depth from it
        turn_x_mm = plans[0]["runs"][0]["end"][0] * _MM
        self.assertAlmostEqual(turn_x_mm, 1250.0, places=2)

    def test_no_stair_text(self):
        recs = _wall_bay(0.0, 0.0, 6000.0, 3000.0)
        plans, notes = stair_layout.plan_stairs(recs, [], None,
                                                [_Text("B1 300x600", 1, 1)],
                                                _PARAMS, 3000.0)
        self.assertEqual(plans, [])
        self.assertTrue(any("no STAIRCASE" in n for n in notes))

    def test_text_outside_any_bay(self):
        recs = _wall_bay(0.0, 0.0, 6000.0, 3000.0)
        plans, notes = stair_layout.plan_stairs(
            recs, [], None, [_Text("ST-9", 9000.0, 9000.0)], _PARAMS, 3000.0)
        self.assertEqual(plans, [])
        self.assertTrue(any("ST-9" in n for n in notes))


class RiserRecovery(unittest.TestCase):
    """StaircasePlan-Test2 lost most of its risers to two detection bugs."""

    def _flight(self, positions_mm, reverse_every=0):
        """Vertical riser lines at the given x positions, 1500 long.

        `reverse_every`: draw every Nth line from the other end, which is what a
        real drawing does and what used to split the flight across two
        direction buckets (0 degrees and 180 degrees are ONE direction).
        """
        recs = []
        for index, x in enumerate(positions_mm):
            a = (x * _FT, 0.0)
            b = (x * _FT, 1500.0 * _FT)
            if reverse_every and index % reverse_every == 0:
                a, b = b, a
            recs.append(_Rec("line", [a, b], layers.CATEGORY_STAIR))
        return recs

    def test_direction_buckets_wrap(self):
        """Lines drawn end-for-end are the same direction, not two."""
        positions = [1000.0 + 300.0 * i for i in range(11)]
        runs = stair_runs._riser_runs(
            [(tuple(r.points[0][:2]), tuple(r.points[1][:2]))
             for r in self._flight(positions, reverse_every=3)])
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(runs[0]["positions"]), 11)

    def test_missing_riser_lines_are_rebuilt(self):
        """A 600mm gap in a 300mm flight is ONE undrawn riser, not the end."""
        positions = [0.0, 300.0, 600.0, 1200.0, 1500.0, 1800.0]   # 900 absent
        runs = stair_runs._riser_runs(
            [(tuple(r.points[0][:2]), tuple(r.points[1][:2]))
             for r in self._flight(positions)])
        self.assertEqual(len(runs), 1)
        self.assertEqual(len(runs[0]["positions"]), 7)   # the 900 is restored

    def test_a_landing_still_ends_the_flight(self):
        """A jump far beyond a few treads is a landing: two separate flights."""
        positions = ([0.0, 300.0, 600.0, 900.0]
                     + [4000.0, 4300.0, 4600.0, 4900.0])
        runs = stair_runs._riser_runs(
            [(tuple(r.points[0][:2]), tuple(r.points[1][:2]))
             for r in self._flight(positions)])
        self.assertEqual(sorted(len(r["positions"]) for r in runs), [4, 4])

    def test_tread_multiple_rules(self):
        self.assertEqual(stair_runs._tread_multiple(300.0, 300.0), 1)
        self.assertEqual(stair_runs._tread_multiple(600.0, 300.0), 2)
        self.assertEqual(stair_runs._tread_multiple(900.0, 300.0), 3)
        self.assertEqual(stair_runs._tread_multiple(1200.0, 300.0), 0)  # landing
        self.assertEqual(stair_runs._tread_multiple(450.0, 300.0), 0)   # not a multiple
        self.assertEqual(stair_runs._tread_multiple(300.0, None), 0)


class FlightWidthFromTypicalRiser(unittest.TestCase):
    """A line that runs PAST the flight must not stretch its width.

    StaircasePlan-Test2 stair 1: ten risers span x 11200..13700 (2500 wide)
    and the bottom landing edge runs 11200..14300, right across the 600 well.
    Taking the union made the flight 3100 wide and moved its centreline 300mm.
    """

    def _flight(self, spans_mm, ys_mm):
        recs = []
        for y, (x0, x1) in zip(ys_mm, spans_mm):
            recs.append(_Rec("line", [(x0 * _FT, y * _FT), (x1 * _FT, y * _FT)],
                             layers.CATEGORY_STAIR))
        return [(tuple(r.points[0][:2]), tuple(r.points[1][:2])) for r in recs]

    def test_overrunning_line_does_not_widen_the_flight(self):
        ys = [2600.0 + 300.0 * i for i in range(10)]
        spans = [(11200.0, 14300.0)] + [(11200.0, 13700.0)] * 9   # first overruns
        runs = stair_runs._riser_runs(self._flight(spans, ys))
        self.assertEqual(len(runs), 1)
        width_mm = (runs[0]["span_hi"] - runs[0]["span_lo"]) * _MM
        self.assertAlmostEqual(width_mm, 2500.0, places=3)
        centre_mm = (runs[0]["span_lo"] + runs[0]["span_hi"]) / 2.0 * _MM
        self.assertAlmostEqual(centre_mm, 12450.0, places=3)

    def test_modal_span_is_a_real_drawn_extent(self):
        chain = [(0.0, 10.0, 20.0), (1.0, 10.0, 20.0), (2.0, 10.0, 30.0)]
        lo, hi = stair_runs._modal_span(chain)
        self.assertAlmostEqual(lo, 10.0)
        self.assertAlmostEqual(hi, 20.0)      # the pair two of the three share


class WinderFlights(unittest.TestCase):
    """Angled (fanned) risers -- StaircasePlan-Test2's winder stairs.

    A balanced winder keeps the going constant on the WALK LINE, so its risers
    rotate and their ends spread unevenly along the two sides. The parallel
    detector sees a different direction per riser and finds nothing; what stays
    true is that the MIDPOINTS are one tread apart on a straight line and the
    risers TURN monotonically.
    """

    def _fan(self, count=8, tread=300.0, width=1500.0, turn_deg=30.0,
             x0=0.0, y0=0.0):
        """A fan walking along +x: midpoints one tread apart, risers rotating."""
        recs = []
        for i in range(count):
            mx = x0 + i * tread
            my = y0
            ang = math.radians(90.0 + turn_deg * (float(i) / (count - 1) - 0.5))
            dx = math.cos(ang) * width / 2.0
            dy = math.sin(ang) * width / 2.0
            recs.append(_Rec("line", [((mx - dx) * _FT, (my - dy) * _FT),
                                      ((mx + dx) * _FT, (my + dy) * _FT)],
                             layers.CATEGORY_STAIR))
        return recs

    def test_a_fan_becomes_a_run(self):
        plans, notes = stair_layout.stair_plans_from_linework(
            self._fan(), _PARAMS, 3000.0)
        self.assertEqual(notes, [])
        self.assertEqual(len(plans), 1)
        run = plans[0]["runs"][0]
        self.assertEqual(run["risers"], 8)
        self.assertAlmostEqual(plans[0]["tread_mm"], 300.0, delta=5.0)
        self.assertAlmostEqual(plans[0]["run_width_mm"], 1500.0, delta=40.0)

    def test_the_run_sits_on_the_drawn_midpoints(self):
        plans, _notes = stair_layout.stair_plans_from_linework(
            self._fan(x0=5000.0, y0=7000.0), _PARAMS, 3000.0)
        run = plans[0]["runs"][0]
        for point in (run["start"], run["end"]):
            self.assertAlmostEqual(point[1] * _MM, 7000.0, delta=60.0)
        self.assertGreater(abs(run["end"][0] - run["start"][0]) * _MM, 1800.0)

    def test_parallel_risers_are_not_a_fan(self):
        # zero turn: the ordinary detector's job, and _fan_runs must not add it
        lines = [(a, b) for a, b in
                 stair_layout._stair_lines(self._fan(turn_deg=0.0))[0]]
        self.assertEqual(stair_runs._fan_runs(lines, []), [])

    def test_risers_that_wobble_both_ways_are_not_a_fan(self):
        recs = self._fan(turn_deg=30.0)
        lines, _z = stair_layout._stair_lines(recs)
        angles = [math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
                  for a, b in lines]
        self.assertIsNotNone(stair_runs._monotone_turn(angles))
        angles[3], angles[4] = angles[4], angles[3]      # turn back on itself
        self.assertIsNone(stair_runs._monotone_turn(angles))

    def test_fan_and_straight_flight_both_survive(self):
        recs = self._fan(count=6, x0=3000.0)
        for i in range(5):                    # a straight flight leading in
            x = i * 300.0
            recs.append(_Rec("line", [(x * _FT, -750.0 * _FT),
                                      (x * _FT, 750.0 * _FT)],
                             layers.CATEGORY_STAIR))
        plans, _notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        self.assertGreaterEqual(len(plans[0]["runs"]), 2)
        self.assertGreaterEqual(plans[0]["risers_total"], 11)


class SpiralFromDrawnLinework(unittest.TestCase):
    """Test2's arc stair: 24 risers drawn TWICE each, inner radius only 300."""

    def _spiral(self, risers=24, r_in=300.0, r_out=2300.0, span_deg=304.8,
                twice=True):
        recs = []
        ccx, ccy = 0.0, 0.0
        for i in range(risers):
            ang = math.radians(i * span_deg / (risers - 1))
            pts = [((ccx + r_in * math.cos(ang)) * _FT,
                    (ccy + r_in * math.sin(ang)) * _FT),
                   ((ccx + r_out * math.cos(ang)) * _FT,
                    (ccy + r_out * math.sin(ang)) * _FT)]
            recs.append(_Rec("line", pts, layers.CATEGORY_STAIR))
            if twice:
                recs.append(_Rec("line", list(pts), layers.CATEGORY_STAIR))
        return recs

    def test_duplicated_risers_are_counted_once(self):
        plans, notes = stair_layout.stair_plans_from_linework(
            self._spiral(), _PARAMS, 3000.0)
        self.assertEqual(notes, [])
        self.assertEqual(len(plans), 1)
        spiral = plans[0].get("spiral")
        self.assertIsNotNone(spiral)
        self.assertEqual(spiral["risers"], 24)

    def test_tight_inner_radius_reads_its_going_across_the_middle(self):
        # walk line 300mm off a 300 inner radius reads 139mm and would reject a
        # stair whose treads are exactly 300 across the flight
        plans, _notes = stair_layout.stair_plans_from_linework(
            self._spiral(), _PARAMS, 3000.0)
        spiral = plans[0]["spiral"]
        self.assertAlmostEqual(spiral["tread_mm"], 300.0, delta=15.0)
        self.assertAlmostEqual(spiral["width_mm"], 2000.0, delta=20.0)

    def test_stairwell_walls_on_the_layer_do_not_break_it(self):
        recs = self._spiral()
        for x in (-2600.0, 2600.0):           # two straight wall lines
            recs.append(_Rec("line", [(x * _FT, -2600.0 * _FT),
                                      (x * _FT, 2600.0 * _FT)],
                             layers.CATEGORY_STAIR))
        plans, _notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        self.assertEqual(len(plans), 1)
        self.assertIsNotNone(plans[0].get("spiral"))

    def test_a_fan_in_a_corner_is_not_called_a_spiral(self):
        # radial-ish but nowhere near dominant: must fall through to the fan pass
        recs = []
        for i in range(6):
            ang = math.radians(90.0 + i * 6.0)
            recs.append(_Rec("line", [((i * 300.0 - 750.0 * math.cos(ang)) * _FT,
                                       (-750.0 * math.sin(ang)) * _FT),
                                      ((i * 300.0 + 750.0 * math.cos(ang)) * _FT,
                                       (750.0 * math.sin(ang)) * _FT)],
                             layers.CATEGORY_STAIR))
        for i in range(20):                   # plenty of non-radial linework
            recs.append(_Rec("line", [(0.0, (i * 60.0) * _FT),
                                      (200.0 * _FT, (i * 60.0) * _FT)],
                             layers.CATEGORY_STAIR))
        lines, _z = stair_layout._stair_lines(recs)
        self.assertIsNone(stair_runs._spiral_run(lines))



class LandingsMeetTheFlight(unittest.TestCase):
    """A landing must share an edge with the flight it serves.

    Revit's automatic landing squares itself to the run ends, which against a
    FANNED flight's angled outermost riser leaves a wedge of daylight -- the
    discontinuity reported on StaircasePlan-Test2's winder stairs.
    """

    def _fan(self, count=6, tread=300.0, width=1500.0, turn_deg=30.0):
        recs = []
        for i in range(count):
            mx = i * tread
            ang = math.radians(90.0 + turn_deg * (float(i) / (count - 1) - 0.5))
            dx = math.cos(ang) * width / 2.0
            dy = math.sin(ang) * width / 2.0
            recs.append(_Rec("line", [((mx - dx) * _FT, (-dy) * _FT),
                                      ((mx + dx) * _FT, dy * _FT)],
                             layers.CATEGORY_STAIR))
        return recs

    def test_the_arrival_landing_starts_on_the_last_drawn_riser(self):
        plans, _notes = stair_layout.stair_plans_from_linework(
            self._fan(), _PARAMS, 3000.0)
        run = plans[0]["runs"][-1]
        self.assertTrue(run.get("fanned"))
        ring = plans[0]["top_landing"]
        self.assertIsNotNone(ring)
        riser = run["riser_lines"][-1]
        # both ends of the drawn riser lie ON the landing's near edge
        for point in riser:
            self.assertTrue(
                any(_near(point, corner, 1.0) for corner in ring)
                or _on_segment(point, ring[0], ring[-1], 1.0),
                "riser end %s is not on the landing edge %s" % (point, ring))

    def test_a_square_flight_keeps_its_square_landing(self):
        recs = [_Rec("line", [(0.0, (i * 300.0) * _FT),
                              (1500.0 * _FT, (i * 300.0) * _FT)],
                     layers.CATEGORY_STAIR) for i in range(8)]
        plans, _notes = stair_layout.stair_plans_from_linework(
            recs, _PARAMS, 3000.0)
        ring = plans[0]["top_landing"]
        self.assertEqual(len(ring), 4)
        for i, point in enumerate(ring):
            nxt = ring[(i + 1) % 4]
            self.assertLess(min(abs(point[0] - nxt[0]), abs(point[1] - nxt[1])),
                            1e-6)          # still axis-aligned


class LandingsStepRoundColumns(unittest.TestCase):
    """Stair 1's mid landing ran its corner through C38 and C40."""

    def _plan_with_landing(self):
        ring = [(0.0, 0.0), (5000 * _FT, 0.0),
                (5000 * _FT, 3000 * _FT), (0.0, 3000 * _FT)]
        return [{"mark": "ST-1", "landing": None, "top_landing": ring,
                 "bridge_landings": {}}]

    def _column(self, cx, cy, b, h):
        return ("rect", cx * _FT, cy * _FT, 1.0, 0.0,
                max(b, h) / 2.0 * _FT, min(b, h) / 2.0 * _FT)

    def test_a_column_at_a_corner_becomes_a_step(self):
        plans = stair_layout.notch_landings(
            self._plan_with_landing(), [self._column(5000, 3000, 900, 900)])
        ring = plans[0]["top_landing"]
        corners = set((round(x * _MM), round(y * _MM)) for x, y in ring)
        self.assertEqual(len(ring), 6)              # the L
        self.assertIn((4550, 3000), corners)        # stepped in by half the column
        self.assertIn((4550, 2550), corners)
        self.assertIn((5000, 2550), corners)
        self.assertNotIn((5000, 3000), corners)     # the overlapping corner is gone

    def test_two_columns_give_two_steps(self):
        plans = stair_layout.notch_landings(
            self._plan_with_landing(),
            [self._column(0, 3000, 900, 900), self._column(5000, 3000, 900, 900)])
        ring = plans[0]["top_landing"]
        self.assertEqual(len(ring), 8)
        area = abs(stair_layout.slab_outlines._signed_area(ring)) * _MM * _MM
        self.assertAlmostEqual(area / 1e6, 15.0 - 2 * (0.45 * 0.45), places=3)

    def test_a_landing_clear_of_every_column_is_untouched(self):
        before = self._plan_with_landing()[0]["top_landing"]
        plans = stair_layout.notch_landings(
            self._plan_with_landing(), [self._column(20000, 20000, 900, 900)])
        self.assertEqual(plans[0]["top_landing"], before)

    def test_a_cut_that_would_swallow_the_landing_is_refused(self):
        plans = stair_layout.notch_landings(
            self._plan_with_landing(), [self._column(2500, 1500, 6000, 6000)])
        self.assertEqual(len(plans[0]["top_landing"]), 4)   # left as drawn

    def test_a_column_in_the_middle_would_hole_the_landing_so_is_refused(self):
        plans = stair_layout.notch_landings(
            self._plan_with_landing(), [self._column(2500, 1500, 600, 600)])
        self.assertEqual(len(plans[0]["top_landing"]), 4)

    def test_bridge_landings_are_notched_too(self):
        plans = self._plan_with_landing()
        plans[0]["bridge_landings"] = {0: list(plans[0]["top_landing"])}
        stair_layout.notch_landings(plans, [self._column(5000, 3000, 900, 900)])
        self.assertEqual(len(plans[0]["bridge_landings"][0]), 6)


def _near(a, b, tol_mm):
    return math.hypot(a[0] - b[0], a[1] - b[1]) * _MM <= tol_mm


def _on_segment(point, a, b, tol_mm):
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length <= 0:
        return False
    off = abs((point[0] - a[0]) * (b[1] - a[1])
              - (point[1] - a[1]) * (b[0] - a[0])) / length
    return off * _MM <= tol_mm



if __name__ == "__main__":
    unittest.main()

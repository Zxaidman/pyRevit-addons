# -*- coding: utf-8 -*-
"""stair_layout -- generic dog-leg staircases located by plan text (option 1).

Covered on synthetic plans: the stair/direction text parsing; the dog-leg
numbers (riser count from the storey height, split across two runs, actual
riser recomputed); geometry (runs along the bay's long axis, both anchored at
the landing edge, landing at the DN end); the does-not-fit and squeezed-width
notes; and the keep_points face relaxation that hands a WALL-bounded bay to the
stair layout (the slab chain drops it as a shaft). Standalone (no Revit).
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


def _load():
    for name in ("_str", "_str.geom", "_str.classify"):
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

    load("_str.config", "config.py")
    load("_str.geom.shapes", "geom", "shapes.py")
    load("_str.classify.layers", "classify", "layers.py")
    load("_str.slab_outlines", "slab_outlines.py")
    return load("_str.stair_layout", "stair_layout.py")


stair_layout = _load()
slab_outlines = sys.modules["_str.slab_outlines"]
layers = sys.modules["_str.classify.layers"]


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
        # and spans BOTH flights like the half landing (the U-stair rule)
        ys = sorted(p[1] * _MM for p in top)
        self.assertAlmostEqual(ys[-1] - ys[0], 3000.0, places=3)

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


if __name__ == "__main__":
    unittest.main()

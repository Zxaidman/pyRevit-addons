# -*- coding: utf-8 -*-
"""Folds and sunk bays: the three parts of a step, and when there is no third.

Every number here comes from one of two places, and both are worth naming.

THE USER'S OWN REVIT DETAIL. A 350 THK slab, two levels at 0.000 and -350.000,
and the fold support selected showing `Height Offset From Level = -200.000`
against a 200 dimension. That fixes the support: it hangs from the parent's
soffit, so its offset is minus the parent's thickness.

THE FIXTURE, from the other direction. test10's sunk strip F6 is 1000 thick,
drops 1000, and sits between F5 pads that are 2000 thick. 1000 + 1000 - 2000 = 0
-- and a support of zero depth is exactly right, because a 2000-deep pad is
already the full vertical face at the shared edge. Three numbers from the
drawing landing on zero is what says the convention is soffit-aligned rather
than something convenient.

Those two cases are the whole design: the first is where a support is needed,
the second is where inventing one would double the concrete.
"""

import unittest

import _loader


fold_plan, layers = _loader.load("fold_plan", "classify.layers")

_MM = 304.8


def _mm(value):
    return value / _MM


class _Region(object):
    """A hatch as the classifier leaves it: points in internal feet."""

    def __init__(self, x0, y0, x1, y1, category):
        self.points = [(_mm(x0), _mm(y0), 0.0), (_mm(x1), _mm(y0), 0.0),
                       (_mm(x1), _mm(y1), 0.0), (_mm(x0), _mm(y1), 0.0)]
        self.category = category
        self.pattern = "ANSI37"

    @property
    def layer_key(self):
        return "S-FND-FOLD"


def _fold(x0, y0, x1, y1):
    return _Region(x0, y0, x1, y1, layers.CATEGORY_FOLD)


def _sunk(x0, y0, x1, y1):
    return _Region(x0, y0, x1, y1, layers.CATEGORY_SUNK)


def _ring(x0, y0, x1, y1):
    return [(_mm(x0), _mm(y0)), (_mm(x1), _mm(y0)),
            (_mm(x1), _mm(y1)), (_mm(x0), _mm(y1))]


def _plan(x0, y0, x1, y1, thickness, steps=(), mark=None):
    """An outline as foundation_plan hands it over."""
    return {"ring": _ring(x0, y0, x1, y1), "thickness_mm": thickness,
            "mark": mark, "steps": list(steps)}


def _step(depth, kind, at):
    return {"step_mm": depth, "step_kind": kind,
            "point": (_mm(at[0]), _mm(at[1]), 0.0)}


def _size_mm(ring):
    xs = [p[0] * _MM for p in ring]
    ys = [p[1] * _MM for p in ring]
    return (round(max(xs) - min(xs)), round(max(ys) - min(ys)))


class TheRegionsThemselves(unittest.TestCase):
    def test_a_fold_hatch_and_a_sunk_hatch_are_both_step_regions(self):
        got = fold_plan.step_regions([_fold(0, 0, 2700, 3000),
                                      _sunk(5000, 0, 8500, 5900)])
        self.assertEqual([kind for _ring, kind in got],
                         [fold_plan.FOLD, fold_plan.SUNK])

    def test_a_hatch_on_any_other_layer_is_not_a_step(self):
        # test10 carries 342 column fills and Project1 228; a step reader that
        # took every hatch would drop a pit under every column
        fill = _Region(0, 0, 400, 600, layers.CATEGORY_COLUMN)
        self.assertEqual(fold_plan.step_regions([fill]), [])


class ARegionCutOutOfItsParent(unittest.TestCase):
    """test10's F3: a 2700x3000 fold inside a 13900x6650 raft, 1500 thick."""

    def _planned(self):
        host = _plan(5333, 22050, 19233, 28700, 1500.0,
                     [_step(2000.0, fold_plan.FOLD, (7859, 24738))], "F3")
        out = fold_plan.plan_steps([host],
                                   [_fold(6433, 23150, 9133, 26150)])
        self.assertEqual(out["skipped"], [])
        self.assertEqual(len(out["steps"]), 1)
        return out["steps"][0]

    def test_the_dropped_slab_sits_at_the_step_depth(self):
        step = self._planned()
        self.assertEqual(step["dropped"]["offset_mm"], -2000.0)
        self.assertEqual(step["dropped"]["thickness_mm"], 1500.0)
        self.assertEqual(_size_mm(step["dropped"]["ring"]), (2700, 3000))

    def test_the_parent_gets_the_region_cut_out_of_it(self):
        # without the hole the parent and the dropped slab occupy the same plan
        self.assertIsNotNone(self._planned()["opening"])

    def test_a_mid_footing_fold_gets_ONE_collar_not_a_strip_per_edge(self):
        # concrete continues past all four edges, so the support is one closed
        # band with the fold as its hollow -- four butting strips would be four
        # floors meeting edge-to-edge where the detail shows one cast collar
        step = self._planned()
        self.assertEqual(len(step["supports"]), 1)
        support = step["supports"][0]
        self.assertEqual(len(support["holes"]), 1)
        self.assertEqual(_size_mm(support["holes"][0]), (2700, 3000))
        # the band reaches one parent-thickness past the fold on every side
        self.assertEqual(_size_mm(support["ring"]),
                         (2700 + 2 * 1500, 3000 + 2 * 1500))

    def test_the_support_hangs_from_the_parents_soffit_and_reaches_the_drop(self):
        # the user's detail: offset is minus the PARENT's thickness, and the
        # depth is whatever is left between the two soffits
        support = self._planned()["supports"][0]
        self.assertEqual(support["offset_mm"], -1500.0)
        self.assertEqual(support["thickness_mm"], 2000.0)   # 2000 + 1500 - 1500

    def test_the_users_own_detail_reproduces_its_own_numbers(self):
        # 350 THK slab, levels 0.000 and -350.000, support at -200 with a 200
        # dimension: a 200-thick parent dropping 350
        host = _plan(0, 0, 10000, 8000, 200.0,
                     [_step(350.0, fold_plan.FOLD, (5000, 4000))], "S1")
        step = fold_plan.plan_steps([host],
                                    [_fold(3000, 2000, 7000, 6000)])["steps"][0]
        support = step["supports"][0]
        self.assertEqual(support["offset_mm"], -200.0)
        self.assertEqual(support["thickness_mm"], 350.0)
        # collar 200 wide in plan: outer = hole grown by 200 on every side
        self.assertEqual(_size_mm(support["ring"]), (4000 + 400, 4000 + 400))
        self.assertEqual(_size_mm(support["holes"][0]), (4000, 4000))

    def test_a_corner_fold_gets_one_L_shaped_slab_not_two_strips(self):
        # the region sits in the host's corner: concrete continues past its two
        # INNER edges only, and those are adjacent, so the support is a single
        # L round the inner corner -- with no hollow, because the band never
        # closes round the region
        host = _plan(0, 0, 10000, 8000, 300.0,
                     [_step(400.0, fold_plan.FOLD, (1000, 1000))], "S1")
        step = fold_plan.plan_steps([host],
                                    [_fold(0, 0, 2000, 2000)])["steps"][0]
        self.assertEqual(len(step["supports"]), 1)
        support = step["supports"][0]
        self.assertEqual(support["holes"], [])
        # six corners, spanning the fold plus one width past its inner edges
        self.assertEqual(len(support["ring"]), 6)
        self.assertEqual(_size_mm(support["ring"]), (2300, 2300))
        self.assertEqual(support["thickness_mm"], 400.0)    # 400 + 300 - 300
        self.assertEqual(support["offset_mm"], -300.0)


class ARegionThatISItsParent(unittest.TestCase):
    """test10's F6: the sunk strip IS an outline, between two thicker pads.

    1000 thick, sunk 1000, flanked by 2000-thick pads. The pads are already the
    full vertical face at the shared edge, so a support there would be a second
    slab in the same place.
    """

    def _planned(self):
        strip = _plan(10533, 10050, 14033, 15950, 1000.0,
                      [_step(1000.0, fold_plan.SUNK, (12251, 12944))], "F6")
        left = _plan(5033, 7050, 10533, 18950, 2000.0, [], "F5")
        right = _plan(14033, 7050, 19533, 18950, 2000.0, [], "F5")
        out = fold_plan.plan_steps([strip, left, right],
                                   [_sunk(10533, 10050, 14033, 15950)])
        self.assertEqual(out["skipped"], [])
        return out["steps"][0]

    def test_the_outline_itself_drops_and_nothing_is_cut_out(self):
        step = self._planned()
        self.assertIsNone(step["opening"])
        self.assertEqual(step["dropped"]["offset_mm"], -1000.0)

    def test_no_support_is_invented_where_the_soffits_already_meet(self):
        # sunk 1000 into 2000-thick pads: the drop never clears the pad's own
        # depth, so the pad IS the face. (Its numbers also happen to put the
        # two soffits level -- 1000+1000-2000 -- but that is this drawing's
        # coincidence, not the rule: see TheVoidRule for the case where the
        # soffit gap is positive and there is still nothing to fill.)
        self.assertEqual(self._planned()["supports"], [])

    def test_a_thinner_neighbour_would_need_a_support(self):
        # the same strip against 800-thick pads leaves 1200 unfilled
        strip = _plan(10533, 10050, 14033, 15950, 1000.0,
                      [_step(1000.0, fold_plan.SUNK, (12251, 12944))], "F6")
        left = _plan(5033, 7050, 10533, 18950, 800.0, [], "F5")
        right = _plan(14033, 7050, 19533, 18950, 800.0, [], "F5")
        step = fold_plan.plan_steps([strip, left, right],
                                    [_sunk(10533, 10050, 14033, 15950)])["steps"][0]
        self.assertEqual(len(step["supports"]), 2)      # the two long edges only
        self.assertEqual(step["supports"][0]["thickness_mm"], 1200.0)
        self.assertEqual(step["supports"][0]["offset_mm"], -800.0)

    def test_an_edge_facing_open_ground_gets_no_support(self):
        # the strip's two SHORT edges face the gap between the pads; wrapping
        # concrete round them would hold up nothing
        strip = _plan(10533, 10050, 14033, 15950, 1000.0,
                      [_step(1000.0, fold_plan.SUNK, (12251, 12944))], "F6")
        thin = _plan(5033, 7050, 10533, 18950, 800.0, [], "F5")
        step = fold_plan.plan_steps([strip, thin],
                                    [_sunk(10533, 10050, 14033, 15950)])["steps"][0]
        self.assertEqual(len(step["supports"]), 1)


class TheVoidRule(unittest.TestCase):
    """A support exists only where the drop is deeper than the parent is thick.

    The corridor drawing is the case that forced this. A 250 sunk bay in a 500
    block leaves the dropped slab's top at -250 -- ABOVE the block's soffit at
    -500 -- so the slab's own side face already closes the section. The old
    "soffit gap > 0" condition measured 250+500-500 = 250 there and cast two
    phantom footings inside solid concrete; the user found them in Revit.
    """

    def test_a_drop_shallower_than_its_parent_gets_no_support(self):
        # the redrawn corridor: sunk 250, cut out of a 500-thick block
        block = _plan(0, 0, 20000, 3500, 500.0,
                      [_step(250.0, fold_plan.SUNK, (10000, 1750))], "F3")
        out = fold_plan.plan_steps([block], [_sunk(8000, 0, 12000, 3500)])
        self.assertEqual(out["skipped"], [])
        step = out["steps"][0]
        self.assertEqual(step["supports"], [])
        # the drop itself still happens -- only the phantom support is gone
        self.assertEqual(step["dropped"]["offset_mm"], -250.0)

    def test_a_drop_exactly_the_parents_thickness_gets_no_support_either(self):
        # top of the dropped slab lands ON the soffit: faces meet, no void
        block = _plan(0, 0, 20000, 3500, 500.0,
                      [_step(500.0, fold_plan.SUNK, (10000, 1750))], "F3")
        step = fold_plan.plan_steps([block],
                                    [_sunk(8000, 0, 12000, 3500)])["steps"][0]
        self.assertEqual(step["supports"], [])

    def test_a_drop_deeper_than_the_parent_leaves_a_void_and_fills_it(self):
        # the same block, the drop pushed past the 500 soffit: the region is
        # interior here, so the filled void arrives as one collar
        block = _plan(0, 0, 20000, 3500, 500.0,
                      [_step(750.0, fold_plan.SUNK, (10000, 1750))], "F3")
        step = fold_plan.plan_steps([block],
                                    [_sunk(8000, 500, 12000, 3000)])["steps"][0]
        self.assertEqual(len(step["supports"]), 1)
        self.assertEqual(step["supports"][0]["offset_mm"], -500.0)
        self.assertEqual(step["supports"][0]["thickness_mm"], 750.0)


class NeighbouringFoldsPoolTheirSupport(unittest.TestCase):
    """test10's row of three folds gets ONE support slab, not three collars.

    The folds sit 300 mm apart and a collar reaches 1500 past its region, so
    three separate collars overlap heavily -- three intersecting floors where
    the cast is one piece. Pooled: the outer edge wraps the whole group, the
    three folds are its hollows, and the concrete between them is part of it.
    """

    def _row(self):
        """The north raft as drawn: 1500 thick, three folds, one note each."""
        host = _plan(5333, 22050, 19233, 28700, 1500.0,
                     [_step(2000.0, fold_plan.FOLD, (7859, 24738)),
                      _step(2000.0, fold_plan.FOLD, (12327, 24738)),
                      _step(2000.0, fold_plan.FOLD, (16988, 24738))], "F3")
        return fold_plan.plan_steps(
            [host], [_fold(6433, 23150, 9133, 26150),
                     _fold(9433, 23150, 15133, 26150),
                     _fold(15433, 23150, 18133, 26150)])

    def test_three_folds_in_a_row_make_ONE_support(self):
        out = self._row()
        self.assertEqual(out["skipped"], [])
        self.assertEqual(len(out["steps"]), 3)
        supports = [s for step in out["steps"] for s in step["supports"]]
        self.assertEqual(len(supports), 1)

    def test_the_pooled_support_wraps_the_group_and_keeps_every_hollow(self):
        supports = [s for step in self._row()["steps"]
                    for s in step["supports"]]
        pooled = supports[0]
        self.assertEqual(len(pooled["holes"]), 3)
        # outer edge = the whole group grown by the parent thickness: the row
        # spans 6433..18133 x 23150..26150, so the slab is that plus 1500 round
        self.assertEqual(_size_mm(pooled["ring"]),
                         (18133 - 6433 + 2 * 1500, 26150 - 23150 + 2 * 1500))
        self.assertEqual(pooled["thickness_mm"], 2000.0)
        self.assertEqual(pooled["offset_mm"], -1500.0)

    def test_every_dropped_slab_survives_the_pooling(self):
        out = self._row()
        self.assertEqual([_size_mm(s["dropped"]["ring"]) for s in out["steps"]],
                         [(2700, 3000), (5700, 3000), (2700, 3000)])
        self.assertEqual([s["opening"] is not None for s in out["steps"]],
                         [True, True, True])

    def test_folds_in_DIFFERENT_footings_never_pool(self):
        # the north and south rafts each keep their own support even though
        # a group is a per-cast thing: concrete does not span two footings
        north = _plan(5333, 22050, 19233, 28700, 1500.0,
                      [_step(2000.0, fold_plan.FOLD, (7859, 24738))], "F3")
        south = _plan(5333, -1250, 19233, 3950, 1500.0,
                      [_step(2000.0, fold_plan.FOLD, (7859, 1438))], "F3")
        out = fold_plan.plan_steps(
            [north, south], [_fold(6433, 23150, 9133, 26150),
                             _fold(6433, -150, 9133, 2850)])
        supports = [s for step in out["steps"] for s in step["supports"]]
        self.assertEqual(len(supports), 2)

    def test_two_far_apart_folds_keep_their_own_collars(self):
        host = _plan(0, 0, 40000, 8000, 500.0,
                     [_step(750.0, fold_plan.FOLD, (3000, 4000)),
                      _step(750.0, fold_plan.FOLD, (35000, 4000))], "F1")
        out = fold_plan.plan_steps(
            [host], [_fold(2000, 3000, 4000, 5000),
                     _fold(34000, 3000, 36000, 5000)])
        supports = [s for step in out["steps"] for s in step["supports"]]
        self.assertEqual(len(supports), 2)
        for support in supports:
            self.assertEqual(len(support["holes"]), 1)


class AnOpeningAtTheBoundaryDividesTheOutline(unittest.TestCase):
    """The corridor block: its sunk bay spans the block's full width.

    Handed to Revit as "the block with a hole", the two loops share two edges
    and Floor.Create refuses the profile -- the user's 18-created-1-error run.
    The concrete truth is a north piece and a south piece, with the dropped
    slab between them.
    """

    def test_a_full_width_opening_makes_two_pieces_and_no_hole(self):
        # the block and its sunk bay, at the drawing's own coordinates
        outer = _ring(10533, 4350, 14033, 21650)
        hole = _ring(10533, 10050, 14033, 15950)
        pieces = fold_plan.split_profile(outer, [hole])
        self.assertEqual(len(pieces), 2)
        sizes = sorted(_size_mm(ring) for ring, _holes in pieces)
        self.assertEqual(sizes, [(3500, 5700), (3500, 5700)])
        for _ring_, piece_holes in pieces:
            self.assertEqual(piece_holes, [])

    def test_an_interior_hole_stays_a_hole(self):
        outer = _ring(0, 0, 20000, 10000)
        hole = _ring(8000, 3000, 12000, 7000)
        pieces = fold_plan.split_profile(outer, [hole])
        self.assertEqual(len(pieces), 1)
        ring, holes = pieces[0]
        self.assertEqual(_size_mm(ring), (20000, 10000))
        self.assertEqual(len(holes), 1)

    def test_a_mixed_profile_splits_and_keeps_the_interior_hole(self):
        # one opening reaches the left edge, another sits clear inside: the
        # outline splits round the first and the second stays a hole of the
        # piece that contains it
        outer = _ring(0, 0, 20000, 10000)
        touching = _ring(0, 4000, 6000, 6000)
        interior = _ring(12000, 3000, 16000, 7000)
        pieces = fold_plan.split_profile(outer, [touching, interior])
        self.assertEqual(len(pieces), 1)     # a side notch does not disconnect
        ring, holes = pieces[0]
        self.assertEqual(len(ring), 8)       # the notch is part of the boundary
        self.assertEqual(len(holes), 1)
        self.assertEqual(_size_mm(holes[0]), (4000, 4000))

    def test_an_opening_covering_the_whole_outline_leaves_nothing(self):
        outer = _ring(0, 0, 5000, 4000)
        pieces = fold_plan.split_profile(outer, [_ring(0, 0, 5000, 4000)])
        self.assertEqual(pieces, [])


class PairingAStepToItsDepth(unittest.TestCase):
    def test_each_region_takes_the_note_that_sits_inside_it(self):
        # test10's F3 rings hold THREE fold notes each, one per region;
        # containment pairs them exactly, so proximity is never guessed at
        host = _plan(5333, 22050, 19233, 28700, 1500.0,
                     [_step(2000.0, fold_plan.FOLD, (7859, 24738)),
                      _step(900.0, fold_plan.FOLD, (12327, 24738))], "F3")
        out = fold_plan.plan_steps(host and [host],
                                   [_fold(6433, 23150, 9133, 26150),
                                    _fold(9433, 23150, 15133, 26150)])
        self.assertEqual([s["depth_mm"] for s in out["steps"]], [2000.0, 900.0])

    def test_a_fold_region_never_takes_a_sunk_note(self):
        host = _plan(0, 0, 10000, 8000, 300.0,
                     [_step(400.0, fold_plan.SUNK, (5000, 4000))], "S1")
        out = fold_plan.plan_steps([host], [_fold(3000, 2000, 7000, 6000)])
        self.assertEqual(out["steps"], [])
        self.assertIn("no depth", out["skipped"][0])

    def test_a_region_inside_no_outline_is_reported_not_placed(self):
        out = fold_plan.plan_steps([_plan(0, 0, 1000, 1000, 300.0, [], "S1")],
                                   [_fold(50000, 50000, 52700, 53000)])
        self.assertEqual(out["steps"], [])
        self.assertIn("inside no outline", out["skipped"][0])

    def test_the_smallest_outline_containing_the_region_is_its_parent(self):
        raft = _plan(0, 0, 30000, 30000, 1000.0,
                     [_step(500.0, fold_plan.FOLD, (5000, 5000))], "F1")
        pad = _plan(2000, 2000, 8000, 8000, 600.0,
                    [_step(300.0, fold_plan.FOLD, (5000, 5000))], "F2")
        out = fold_plan.plan_steps([raft, pad], [_fold(3000, 3000, 7000, 7000)])
        self.assertEqual(out["steps"][0]["mark"], "F2")
        self.assertEqual(out["steps"][0]["depth_mm"], 300.0)


class AStoreyIsNotAStep(unittest.TestCase):
    """Test9's legend lists `+50MM`, `+400MM` and `+6250` in the same breath.

    The first two are steps. 6250 is the next floor, and building it as a fold
    would hang a slab a storey deep off this level and call it done.
    """

    def test_a_step_deeper_than_the_limit_is_refused_and_named(self):
        host = _plan(0, 0, 20000, 20000, 300.0,
                     [_step(6250.0, fold_plan.FOLD, (10000, 10000))], "S1")
        out = fold_plan.plan_steps([host], [_fold(5000, 5000, 15000, 15000)])
        self.assertEqual(out["steps"], [])
        self.assertIn("storey", out["skipped"][0])
        self.assertIn("6250", out["skipped"][0])

    def test_test10s_2000mm_fold_is_under_the_limit_and_still_built(self):
        host = _plan(5333, 22050, 19233, 28700, 1500.0,
                     [_step(2000.0, fold_plan.FOLD, (7859, 24738))], "F3")
        out = fold_plan.plan_steps([host], [_fold(6433, 23150, 9133, 26150)])
        self.assertEqual(len(out["steps"]), 1)

    def test_the_limit_can_be_moved_for_a_drawing_that_needs_it(self):
        host = _plan(0, 0, 20000, 20000, 300.0,
                     [_step(4000.0, fold_plan.FOLD, (10000, 10000))], "S1")
        regions = [_fold(5000, 5000, 15000, 15000)]
        self.assertEqual(fold_plan.plan_steps([host], regions)["steps"], [])
        moved = fold_plan.plan_steps([host], regions, max_step_mm=5000.0)
        self.assertEqual(len(moved["steps"]), 1)


class AnUnsizedParentCannotBeStepped(unittest.TestCase):
    def test_a_parent_with_no_thickness_yields_no_support(self):
        # the drop is still known, so the slab is placed; the support depends on
        # the parent's soffit, which an unlabelled parent does not give
        host = _plan(0, 0, 10000, 8000, None,
                     [_step(350.0, fold_plan.FOLD, (5000, 4000))], None)
        step = fold_plan.plan_steps([host],
                                    [_fold(3000, 2000, 7000, 6000)])["steps"][0]
        self.assertEqual(step["supports"], [])
        self.assertEqual(step["dropped"]["offset_mm"], -350.0)


if __name__ == "__main__":
    unittest.main()

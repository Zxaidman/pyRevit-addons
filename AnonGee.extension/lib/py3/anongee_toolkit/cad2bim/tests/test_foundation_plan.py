# -*- coding: utf-8 -*-
"""Foundations read from the drawing: outlines, sizing, and when to refuse.

The fixture behind every number here is test10's foundation level, measured
with the package's own reader:

    S-FND        12 LWPOLYLINE + 8 LINE   ->  13 outlines
    S-FND-IDEN   19 MTEXT                 ->  19 notes, every one inside a ring

Ten of the thirteen outlines are closed polylines and are taken as drawn. The
other three are the interesting ones: two 5500 x 11900 pads with a 3500 x 5900
sunk strip between them, drawn as two open polylines and eight loose lines. The
strip's long sides ARE the pads' inner sides, drawn once and shared, so a
chainer that consumes each segment as it goes closes none of the three. That is
the case `_faces` exists for, and the case these tests pin.

The refusal matters as much as the reading. Test0's `S-FNDN` layer closes into
four accidental faces and carries no label anywhere in the drawing; placing
those as foundations would be worse than the guess it replaced.
"""

import unittest

import _loader


foundation_plan, layers = _loader.load("foundation_plan", "classify.layers")

_MM = 304.8


def _mm(value):
    return value / _MM


class _Record(object):
    """A CurveRecord as the classifier leaves it: points in internal feet."""

    def __init__(self, kind, points_mm, category=None):
        self.kind = kind
        self.points = [(_mm(x), _mm(y), 0.0) for x, y in points_mm]
        self.category = (layers.CATEGORY_FOUNDATION if category is None
                         else category)

    @property
    def layer_key(self):
        return "S-FND"


class _Text(object):
    def __init__(self, text, point_mm):
        self.text = text
        self.point_internal = (_mm(point_mm[0]), _mm(point_mm[1]), 0.0)


def _closed(x0, y0, x1, y1, category=None):
    """A rectangle drawn as ONE closed polyline, the way ten of test10's are."""
    return _Record("polyline",
                   [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)],
                   category)


def _loose(x0, y0, x1, y1):
    """The same rectangle drawn as four separate lines."""
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [_Record("line", [corners[i], corners[(i + 1) % 4]])
            for i in range(4)]


def _shared_edge_trio():
    """test10's centre: two pads flanking a sunk strip, inner edges drawn ONCE.

    Left pad 5033..10533, right pad 14033..19533, both 7050..18950; the strip
    between them 10533..14033 x 10050..15950. The verticals at x=10533 and
    x=14033 each border a pad AND the strip.
    """
    left = _Record("polyline", [(10533, 7050), (5033, 7050),
                                (5033, 18950), (10533, 18950)])
    right = _Record("polyline", [(14033, 18950), (19533, 18950),
                                 (19533, 7050), (14033, 7050)])
    lines = [((10533, 18950), (10533, 15950)),
             ((10533, 15950), (10533, 10050)),
             ((10533, 10050), (10533, 7050)),
             ((14033, 7050), (14033, 10050)),
             ((14033, 10050), (14033, 15950)),
             ((14033, 15950), (14033, 18950)),
             ((10533, 15950), (14033, 15950)),
             ((10533, 10050), (14033, 10050))]
    return [left, right] + [_Record("line", [a, b]) for a, b in lines]


def _bbox_mm(ring):
    xs = [p[0] * _MM for p in ring]
    ys = [p[1] * _MM for p in ring]
    return (round(max(xs) - min(xs)), round(max(ys) - min(ys)))


class Outlines(unittest.TestCase):
    def test_a_closed_polyline_is_an_outline_as_drawn(self):
        got = foundation_plan.outlines([_closed(0, 0, 5200, 6650)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][2], "drawn")
        self.assertEqual(_bbox_mm(got[0][0]), (5200, 6650))

    def test_an_outline_drawn_as_four_loose_lines_still_closes(self):
        got = foundation_plan.outlines(_loose(0, 0, 5200, 6650))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][2], "linework")
        self.assertEqual(_bbox_mm(got[0][0]), (5200, 6650))

    def test_records_of_another_category_are_not_foundations(self):
        columns = [_closed(0, 0, 400, 600, layers.CATEGORY_COLUMN)]
        self.assertEqual(foundation_plan.outlines(columns), [])

    def test_three_outlines_come_out_of_test10s_shared_edge_trio(self):
        # the case a consume-as-you-chain assembler cannot do: each inner
        # vertical borders two of the three, and is drawn once
        got = foundation_plan.outlines(_shared_edge_trio())
        self.assertEqual(len(got), 3)
        self.assertEqual(sorted(_bbox_mm(ring) for ring, _z, _s in got),
                         [(3500, 5900), (5500, 11900), (5500, 11900)])

    def test_an_outline_comes_out_with_the_corners_it_was_drawn_with(self):
        # the walk stops wherever the linework was split -- the shared inner
        # edges make it stop halfway down a straight side -- so a face carries
        # vertices the foundation does not. A rectangle has four corners.
        got = foundation_plan.outlines(_shared_edge_trio())
        for ring, _z, _source in got:
            self.assertEqual(len(ring), 4)

    def test_an_open_line_going_nowhere_produces_no_outline(self):
        stub = _Record("line", [(0, 0), (5000, 0)])
        self.assertEqual(foundation_plan.outlines([stub]), [])

    def test_a_stub_hanging_off_a_closed_shape_does_not_pinch_it(self):
        # a dangling tail makes a face walk out and back through the stub --
        # a pinched ring Revit rejects, so the stub is pruned first
        records = _loose(0, 0, 5200, 6650)
        records.append(_Record("line", [(5200, 6650), (7000, 9000)]))
        got = foundation_plan.outlines(records)
        self.assertEqual(len(got), 1)
        self.assertEqual(_bbox_mm(got[0][0]), (5200, 6650))


def _corridor_block():
    """The middle of the REDRAWN test10, at the coordinates it is drawn at.

    The corridor block (10533..14033 x 4350..21650) closes only through the
    SUNK rectangle's sides: the foundation layer carries the two seams and four
    vertical stubs, and the sunk region drawn between (10050..15950) supplies
    the middle of each side. The two seams double as the mouths of the big
    raft's boundary.
    """
    fnd = [
        _Record("line", [(10533, 21650), (14033, 21650)]),      # top seam
        _Record("polyline", [(10533, 4350), (14033, 4350)]),    # bottom seam
        _Record("line", [(10533, 15950), (10533, 21650)]),      # stubs
        _Record("line", [(14033, 21650), (14033, 15950)]),
        _Record("line", [(10533, 4350), (10533, 10050)]),
        _Record("line", [(14033, 10050), (14033, 4350)]),
    ]
    sunk = [_Record("line", [pair[0], pair[1]],
                    layers.CATEGORY_SUNK)
            for pair in (((10533, 10050), (14033, 10050)),
                         ((10533, 15950), (14033, 15950)),
                         ((14033, 15950), (14033, 10050)),
                         ((10533, 10050), (10533, 15950)))]
    return fnd + sunk


class OutlinesThroughTheStepLayers(unittest.TestCase):
    """The redrawn test10: outlines that close only through the sunk linework."""

    def test_step_layer_lines_complete_an_outline_and_are_dissolved(self):
        # the sunk rectangle's sides carry the middle of the corridor's sides;
        # without them nothing closes, and with them the corridor must come out
        # as ONE block, not three cells split at the sunk boundary
        got = foundation_plan.outlines(_corridor_block())
        self.assertEqual(len(got), 1)
        self.assertEqual(_bbox_mm(got[0][0]), (3500, 17300))

    def test_step_lines_alone_never_make_an_outline(self):
        # the fold/sunk layers mark where a foundation steps, not where one
        # ends: a sunk rectangle with no foundation linework is not a footing
        sunk_only = [r for r in _corridor_block()
                     if r.category == layers.CATEGORY_SUNK]
        self.assertEqual(foundation_plan.outlines(sunk_only), [])

    def test_a_seam_drawn_a_little_long_still_closes_its_outline(self):
        # test10's right seam overshoots the raft corner by 400 mm; the
        # overshoot must be split off and pruned, not drag the seam with it
        records = [
            _Record("polyline", [(0, 6650), (0, 0), (5200, 0)]),
            _Record("line", [(5200, 0), (5200, 7050)]),          # 400 long
            _Record("line", [(5200, 6650), (0, 6650)]),
        ]
        got = foundation_plan.outlines(records)
        self.assertEqual(len(got), 1)
        self.assertEqual(_bbox_mm(got[0][0]), (5200, 6650))

    def test_the_corridor_is_a_stepped_zone_of_the_raft_not_an_element(self):
        # the face walk duly returns the neck of the H as an outline -- but
        # the only note inside it is a STEP note, and a step note describes
        # the hatched region it sits in, never the outline round it. Reading
        # the neck as an element cast two 500 slabs at zero offset over
        # concrete the 750 raft already provides (found by the user in Revit).
        records = [_closed(4933, -1650, 19633, 29100)] + _corridor_block()
        plans = foundation_plan.plan_foundations(
            records,
            [_Text("F3_750MM THK", (12265, 25000)),
             _Text("F3_500MM THK\n250MM SUNK", (12300, 13010))])
        self.assertEqual(len(plans), 1)
        raft = plans[0]
        self.assertEqual(raft["thickness_mm"], 750.0)
        self.assertEqual(raft["holes"], [])       # the zone is not a hole either

    def test_the_dissolved_zones_step_note_moves_to_the_raft(self):
        # the sunk region still has to pair with its note, and after the zone
        # dissolves the raft is the element it steps -- carrying the note's
        # OWN thickness, because a 500 slab drops out of this 750 raft and
        # only the note says 500
        records = [_closed(4933, -1650, 19633, 29100)] + _corridor_block()
        plans = foundation_plan.plan_foundations(
            records,
            [_Text("F3_750MM THK", (12265, 25000)),
             _Text("F3_500MM THK\n250MM SUNK", (12300, 13010))])
        raft = plans[0]
        self.assertEqual(len(raft["steps"]), 1)
        self.assertEqual(raft["steps"][0]["step_kind"], "sunk")
        self.assertEqual(raft["steps"][0]["step_mm"], 250.0)
        self.assertEqual(raft["steps"][0]["thickness_mm"], 500.0)

    def test_a_nested_outline_with_a_plain_note_still_nests_and_places(self):
        # a REAL block drawn inside a raft carries its own plain THK note:
        # that one keeps being an element, and the raft is cast round it
        records = [_closed(0, 0, 30000, 30000), _closed(10000, 10000,
                                                        16000, 18000)]
        plans = foundation_plan.plan_foundations(
            records,
            [_Text("F1_750MM THK", (5000, 5000)),
             _Text("F5_500MM THK", (13000, 14000))])
        self.assertEqual(len(plans), 2)
        raft = next(p for p in plans if p["thickness_mm"] == 750.0)
        block = next(p for p in plans if p["thickness_mm"] == 500.0)
        self.assertEqual(len(raft["holes"]), 1)
        self.assertEqual(block["holes"], [])

    def test_a_TOP_LEVEL_outline_with_only_a_step_note_stays_an_element(self):
        # the original F6: an outline that IS its own sunk region, sitting
        # BETWEEN the pads rather than inside anything. Nothing contains it,
        # so there is nothing to dissolve it into -- it is the element.
        plans = foundation_plan.plan_foundations(
            [_closed(10533, 10050, 14033, 15950)],
            [_Text("F6_1000MM THK\n1000MM SUNK", (12251, 12944))])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["thickness_mm"], 1000.0)
        self.assertEqual(len(plans[0]["steps"]), 1)


class SizingFromTheNote(unittest.TestCase):
    def test_the_note_inside_an_outline_names_and_sizes_it(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650)],
            [_Text("F1_1200MM THK", (2600, 3300))])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["mark"], "F1")
        self.assertEqual(plans[0]["thickness_mm"], 1200.0)

    def test_a_note_OUTSIDE_an_outline_does_not_size_it(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650), _closed(20000, 0, 25200, 6650)],
            [_Text("F1_1200MM THK", (2600, 3300))])
        self.assertEqual(len(plans), 2)
        sized = [p for p in plans if p["thickness_mm"]]
        self.assertEqual(len(sized), 1)
        self.assertEqual(_bbox_mm(sized[0]["ring"]), (5200, 6650))

    def test_each_outline_takes_its_own_note(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650), _closed(20000, 0, 25200, 6650)],
            [_Text("F1_1200MM THK", (2600, 3300)),
             _Text("F4_800MM THK", (22600, 3300))])
        by_mark = dict((p["mark"], p["thickness_mm"]) for p in plans)
        self.assertEqual(by_mark, {"F1": 1200.0, "F4": 800.0})

    def test_a_bare_thickness_on_the_foundation_layer_sizes_a_raft(self):
        # "1200MM THK" with no mark is a raft note here and a SLAB note
        # anywhere else; the routing is what separates them
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 12000, 9000)],
            [_Text("1200MM THK", (6000, 4500))])
        self.assertEqual(plans[0]["thickness_mm"], 1200.0)
        self.assertIsNone(plans[0]["mark"])

    def test_a_sizing_note_beats_a_name_only_note_in_the_same_ring(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 12000, 9000)],
            [_Text("F2", (5900, 4400)),
             _Text("F2_1500MM THK", (3000, 2000))])
        self.assertEqual(plans[0]["mark"], "F2")
        self.assertEqual(plans[0]["thickness_mm"], 1500.0)

    def test_an_unlabelled_outline_keeps_a_None_thickness_for_the_builder(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650), _closed(20000, 0, 25200, 6650)],
            [_Text("F1_1200MM THK", (2600, 3300))])
        unlabelled = [p for p in plans if not p["labels"]]
        self.assertEqual(len(unlabelled), 1)
        self.assertIsNone(unlabelled[0]["thickness_mm"])


class Steps(unittest.TestCase):
    def test_a_fold_note_is_recorded_on_the_outline_it_sits_in(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 13900, 6650)],
            [_Text("F3_1500MM THK\n2000MM FOLD", (7000, 3300))])
        self.assertEqual(plans[0]["thickness_mm"], 1500.0)
        self.assertEqual(len(plans[0]["steps"]), 1)
        self.assertEqual(plans[0]["steps"][0]["step_kind"], "fold")
        self.assertEqual(plans[0]["steps"][0]["step_mm"], 2000.0)

    def test_one_outline_holds_every_step_note_inside_it(self):
        # test10's F3 rings: one plain note plus THREE fold notes, matching the
        # three fold hatches drawn in each. The steps belong to the regions,
        # not to the outline, so they are collected rather than collapsed.
        texts = [_Text("F3_1500MM THK", (7000, 2000))]
        for x in (3000, 7000, 11000):
            texts.append(_Text("F3_1500MM THK\n2000MM FOLD", (x, 5000)))
        plans = foundation_plan.plan_foundations([_closed(0, 0, 13900, 6650)],
                                                 texts)
        self.assertEqual(plans[0]["thickness_mm"], 1500.0)
        self.assertEqual(len(plans[0]["steps"]), 3)

    def test_a_sunk_note_is_kept_apart_from_a_fold(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 3500, 5900)],
            [_Text("F6_1000MM THK\n1000MM SUNK", (1750, 2950))])
        self.assertEqual(plans[0]["steps"][0]["step_kind"], "sunk")


class TheDrawingHasToProveIt(unittest.TestCase):
    def test_outlines_that_NOTHING_labels_are_refused_entirely(self):
        # Test0's S-FNDN: 187 records of arc and angled linework closing into
        # four accidental faces, with no foundation note anywhere in the
        # drawing. The caller falls back to the column derivation.
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650), _closed(20000, 0, 25200, 6650)], [])
        self.assertEqual(plans, [])

    def test_one_labelled_outline_vouches_for_the_rest_of_the_layer(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650), _closed(20000, 0, 25200, 6650)],
            [_Text("F1_1200MM THK", (2600, 3300))])
        self.assertEqual(len(plans), 2)

    def test_a_drawing_with_no_foundation_layer_plans_nothing(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 400, 600, layers.CATEGORY_COLUMN)],
            [_Text("F1_1200MM THK", (200, 300))])
        self.assertEqual(plans, [])

    def test_a_MARKED_slab_note_never_vouches_for_a_foundation_outline(self):
        # "S1 150 THK" carries a slab's mark, so it is not a foundation note at
        # any thickness and on any layer -- the outline stays unvouched-for and
        # the whole drawn set is refused.
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650)], [_Text("S1 150 THK", (2600, 3300))])
        self.assertEqual(plans, [])

    def test_a_BARE_thickness_is_why_the_notes_are_routed_by_layer(self):
        # "150 THK." alone cannot be told from a slab note by its text. Reading
        # it as a 150 mm raft is right only because the caller routed it off
        # the foundation layer; that is the whole reason script.py refuses to
        # fall back to every text in the drawing the way slab notes do.
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650)], [_Text("150 THK.", (2600, 3300))])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["thickness_mm"], 150.0)


class Area(unittest.TestCase):
    def test_a_ring_reports_its_plan_area_in_square_metres(self):
        ring, _z, _source = foundation_plan.outlines(
            [_closed(0, 0, 5000, 4000)])[0]
        self.assertAlmostEqual(foundation_plan.area_m2(ring), 20.0, places=6)


if __name__ == "__main__":
    unittest.main()

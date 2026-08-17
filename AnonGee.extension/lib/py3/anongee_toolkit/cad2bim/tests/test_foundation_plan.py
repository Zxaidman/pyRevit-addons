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


# config rides the same namespace so the raft-threshold test mutates the very
# dict foundation_plan reads at call time
foundation_plan, layers, config = _loader.load("foundation_plan",
                                               "classify.layers", "config")

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


def _cross(x0, y0, x1, y1, inset=0):
    """The standard opening symbol: two diagonals corner-to-corner.

    Drawn on a layer no category claims -- test10 puts its crosses on
    "A-DETL" -- because the symbol is annotation, not linework. `inset` pulls
    both strokes short of the corners, for the tests that prove short strokes
    are not the symbol.
    """
    return [_Record("line",
                    [(x0 + inset, y0 + inset), (x1 - inset, y1 - inset)],
                    layers.CATEGORY_UNMAPPED),
            _Record("line",
                    [(x0 + inset, y1 - inset), (x1 - inset, y0 + inset)],
                    layers.CATEGORY_UNMAPPED)]


class AnXMarkedFaceIsACutout(unittest.TestCase):
    """The corridor's north and south parts carry the opening symbol.

    Measured on test10: each part holds TWO diagonal LINEs on "A-DETL"
    spanning exactly corner-to-corner. The middle part between them is the
    sunk bay. The raft was being cast SOLID over the crossed-out parts --
    dissolving the corridor made the whole strip raft again -- and the user
    found the filled corridor in Revit against a drawing that voids it.
    """

    def _nested(self, extras, texts=()):
        """A raft drawn closed, a block recovered from loose lines inside it."""
        records = ([_closed(0, 0, 30000, 30000)]
                   + _loose(10000, 10000, 16000, 18000) + list(extras))
        return foundation_plan.plan_foundations(
            records, [_Text("F1_750MM THK", (5000, 5000))] + list(texts))

    def test_two_corner_to_corner_diagonals_void_a_nested_face(self):
        plans = self._nested(_cross(10000, 10000, 16000, 18000))
        self.assertEqual(len(plans), 1)          # the block is never an element
        self.assertEqual([_bbox_mm(h) for h in plans[0]["holes"]],
                         [(6000, 8000)])         # only ever the hole
        self.assertEqual(
            foundation_plan.outlines(
                [_closed(0, 0, 30000, 30000)]
                + _loose(10000, 10000, 16000, 18000)
                + _cross(10000, 10000, 16000, 18000)),
            foundation_plan.outlines([_closed(0, 0, 30000, 30000)]))

    def test_ONE_diagonal_is_not_the_symbol(self):
        # a single slash is a section mark or a leader, not the opening cross
        plans = self._nested(_cross(10000, 10000, 16000, 18000)[:1])
        self.assertEqual(len(plans), 2)          # the block stays an element

    def test_diagonals_short_of_the_corners_are_not_the_symbol(self):
        # an X floating 200 mm inside the face belongs to whatever detail it
        # is actually drawn over, and 200 is far outside the 50 mm snap
        plans = self._nested(_cross(10000, 10000, 16000, 18000, inset=200))
        self.assertEqual(len(plans), 2)

    def test_a_TOP_LEVEL_face_with_an_X_keeps_being_an_element(self):
        # nothing contains it, so the X cannot be "void this part of that":
        # voiding a whole foundation on two loose lines would delete elements
        # this pass owns on the strength of ones it does not
        plans = foundation_plan.plan_foundations(
            _loose(0, 0, 5200, 6650) + _cross(0, 0, 5200, 6650),
            [_Text("F1_1200MM THK", (2600, 3300))])
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["thickness_mm"], 1200.0)
        self.assertEqual(plans[0]["holes"], [])

    def test_cutouts_reports_the_crossed_out_rings_for_the_sweep(self):
        records = ([_closed(0, 0, 30000, 30000)]
                   + _loose(10000, 10000, 16000, 18000)
                   + _cross(10000, 10000, 16000, 18000))
        got = foundation_plan.cutouts(records)
        self.assertEqual([_bbox_mm(ring) for ring in got], [(6000, 8000)])


class ACutoutRegionIsAHoleToo(unittest.TestCase):
    """A hatch ROUTED to "cutout" says what the X says, as an area.

    The route is the legend proposal (test9: "HATCH INDICATE CUTOUT FOR DOOR
    ABOVE", every ASPHALT hatch on PI_SHEAR WALL CUTOUT) or a hand pick in
    the dialog -- either way the category arrives through `apply_mapping`,
    the region-category cousin of the fold/sunk hatches. Consumed exactly as
    an X-marked face: only ever a hole of the smallest plan containing it,
    never an element. No fixture draws one over a foundation level yet, so
    the numbers here are synthetic.
    """

    class _Region(object):
        def __init__(self, x0, y0, x1, y1, category):
            self.points = [(_mm(x0), _mm(y0), 0.0), (_mm(x1), _mm(y0), 0.0),
                           (_mm(x1), _mm(y1), 0.0), (_mm(x0), _mm(y1), 0.0)]
            self.category = category
            self.pattern = "ASPHALT"
            self.layer_key = "PI_SHEAR WALL CUTOUT"

    def _plans(self, regions):
        return foundation_plan.plan_foundations(
            [_closed(0, 0, 30000, 30000)],
            [_Text("F1_750MM THK", (5000, 5000))], regions=regions)

    def test_a_cutout_region_holes_the_plan_containing_it(self):
        plans = self._plans([self._Region(10000, 10000, 16000, 18000,
                                          layers.CATEGORY_CUTOUT)])
        self.assertEqual(len(plans), 1)          # never an element of its own
        self.assertEqual([_bbox_mm(h) for h in plans[0]["holes"]],
                         [(6000, 8000)])
        self.assertEqual(plans[0]["kind"], "raft")   # an opening let into it

    def test_any_other_region_category_holes_nothing(self):
        # a fold region is a STEP -- fold_plan's business, not a void
        plans = self._plans([self._Region(10000, 10000, 16000, 18000,
                                          layers.CATEGORY_FOLD)])
        self.assertEqual(plans[0]["holes"], [])

    def test_a_cutout_inside_no_plan_attaches_nowhere(self):
        plans = self._plans([self._Region(40000, 10000, 46000, 18000,
                                          layers.CATEGORY_CUTOUT)])
        self.assertEqual(plans[0]["holes"], [])


class TheCrossedOutCorridor(unittest.TestCase):
    """The redrawn test10 corridor read whole, at the drawing's coordinates.

    The strip 10533..14033 divides into three: north (15950..21650) and south
    (4350..10050) each crossed out on "A-DETL", the sunk bay (10050..15950)
    between them. The right model: the raft is cast around ONE corridor-shaped
    hole, the sunk slab drops into the middle of it, and the crossed-out parts
    get nothing at all.
    """

    def _plans(self):
        records = ([_closed(4933, -1650, 19633, 29100)] + _corridor_block()
                   + _cross(10533, 15950, 14033, 21650)
                   + _cross(10533, 4350, 14033, 10050))
        return foundation_plan.plan_foundations(
            records,
            [_Text("F3_750MM THK", (12265, 25000)),
             _Text("F3_500MM THK\n250MM SUNK", (12300, 13010))])

    def test_the_crossed_out_parts_become_holes_in_the_raft(self):
        plans = self._plans()
        self.assertEqual(len(plans), 1)
        self.assertEqual(sorted(_bbox_mm(h) for h in plans[0]["holes"]),
                         [(3500, 5700), (3500, 5700)])

    def test_the_raft_is_sized_by_its_plain_note_not_the_step_note(self):
        # with the corridor cells gone, the sunk note lands in the raft's own
        # ring, nearly at its centre -- and its 500 is the DROPPED slab's
        # thickness, which must not size the 750 raft
        self.assertEqual(self._plans()[0]["thickness_mm"], 750.0)

    def test_the_sunk_bay_still_steps_the_raft(self):
        raft = self._plans()[0]
        self.assertEqual(len(raft["steps"]), 1)
        self.assertEqual(raft["steps"][0]["step_kind"], "sunk")
        self.assertEqual(raft["steps"][0]["step_mm"], 250.0)
        self.assertEqual(raft["steps"][0]["thickness_mm"], 500.0)


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


class RaftOrPad(unittest.TestCase):
    """Which naming template an outline takes: "raft" or "pad", by the drawing.

    Two tells, either sufficient. Plan AREA at or over config's
    raft_min_area_m2 (60 m2 -- test10's raft is ~450, its largest pad ~35);
    or HOLES, because an outline the drawing cuts openings into is a raft by
    construction. The judgment lives in plan_foundations so the builder only
    routes on it.
    """

    def test_a_pad_sized_outline_is_a_pad(self):
        # 5.2 x 6.65 m = ~34.6 m2: the corpus's biggest pads
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650)], [_Text("F1_1200MM THK", (2600, 3300))])
        self.assertEqual(plans[0]["kind"], "pad")

    def test_an_outline_at_raft_area_is_a_raft(self):
        # 10 x 6 m = 60 m2 exactly: AT the threshold counts, per the spec
        # "at or above"
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 10000, 6000)], [_Text("F3_750MM THK", (5000, 3000))])
        self.assertEqual(plans[0]["kind"], "raft")
        self.assertAlmostEqual(foundation_plan.area_m2(plans[0]["ring"]),
                               60.0, places=6)

    def test_the_threshold_is_read_from_config_not_frozen_here(self):
        self.assertEqual(config.DEFAULTS["raft_min_area_m2"], 60.0)
        original = config.DEFAULTS["raft_min_area_m2"]
        try:
            config.DEFAULTS["raft_min_area_m2"] = 100.0
            plans = foundation_plan.plan_foundations(
                [_closed(0, 0, 10000, 6000)],
                [_Text("F3_750MM THK", (5000, 3000))])
            self.assertEqual(plans[0]["kind"], "pad")
        finally:
            config.DEFAULTS["raft_min_area_m2"] = original

    def test_holes_make_a_raft_of_an_outline_below_the_area(self):
        # 8 x 6 m = 48 m2, under the threshold -- but a nested block is let
        # into it, and a pad with an opening cut in it is not a thing an
        # engineer draws. The block itself stays a pad.
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 8000, 6000), _closed(3000, 2000, 5000, 4000)],
            [_Text("F1_750MM THK", (1000, 1000)),
             _Text("F5_500MM THK", (4000, 3000))])
        self.assertEqual(len(plans), 2)
        outer = next(p for p in plans if p["thickness_mm"] == 750.0)
        block = next(p for p in plans if p["thickness_mm"] == 500.0)
        self.assertEqual(len(outer["holes"]), 1)
        self.assertEqual(outer["kind"], "raft")
        self.assertEqual(block["kind"], "pad")

    def test_a_crossed_out_cutout_is_a_hole_and_therefore_a_raft_too(self):
        # the corridor case in miniature: the X voids a nested linework face,
        # the void becomes a hole of the outer plan, and the hole makes it a
        # raft (only a FACE can be crossed out -- a drawn-closed ring is an
        # outline the engineer vouched for, which is why _loose here)
        records = ([_closed(0, 0, 8000, 6000)]
                   + _loose(3000, 2000, 5000, 4000)
                   + _cross(3000, 2000, 5000, 4000))
        plans = foundation_plan.plan_foundations(
            records, [_Text("F1_750MM THK", (1000, 1000))])
        self.assertEqual(len(plans), 1)
        self.assertEqual(len(plans[0]["holes"]), 1)
        self.assertEqual(plans[0]["kind"], "raft")

    def test_every_plan_carries_a_kind_for_the_builder_to_route_on(self):
        plans = foundation_plan.plan_foundations(
            [_closed(0, 0, 5200, 6650), _closed(20000, 0, 25200, 6650)],
            [_Text("F1_1200MM THK", (2600, 3300))])
        for plan in plans:
            self.assertIn(plan["kind"], ("raft", "pad"))


class TheKindReachesTheBuilder(unittest.TestCase):
    """builders/footings.py imports Revit at module level, so the routing --
    kind picks the template, kind keys the cache -- is pinned the way the
    other Revit-side wiring is: by reading the source. Each link fails
    QUIETLY if dropped: every raft would silently take the pad template."""

    def _source(self):
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "builders", "footings.py")
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8")

    def test_the_type_name_routes_on_kind(self):
        block = self._source().split("def _resolve_type(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn("naming.raft_type_name(", block)
        self.assertIn("naming.footing_type_name(", block)
        self.assertIn('if kind == "raft"', block)

    def test_the_cache_is_keyed_by_kind_AND_thickness(self):
        # one cache keyed by thickness alone would hand a 500-thick raft the
        # 500-thick pad's type -- same depth, wrong name, nothing said
        block = self._source().split("def _resolve_type(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn("key = (kind, int(round(thickness_mm)))", block)

    def test_column_derived_pads_are_always_pads(self):
        block = self._source().split("def place_footings(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn('(ring, thickness, mark, [], "pad")', block)

    def test_drawn_outlines_carry_their_plans_kind_through_division(self):
        block = self._source().split("def _plans_from_outlines(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn('plan.get("kind") or "pad"', block)

    def test_steps_and_supports_keep_the_footing_template(self):
        # their own templates are a later item; until then _place_steps must
        # not pass a kind, so the default "pad" keeps them on the footing row
        block = self._source().split("def _place_steps(", 1)[1].split(
            "\ndef ", 1)[0]
        self.assertIn("_resolve_type(doc, base_type, thickness, cache)", block)
        self.assertNotIn('_resolve_type(doc, base_type, thickness, cache, "raft"',
                         block)


if __name__ == "__main__":
    unittest.main()

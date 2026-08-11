# -*- coding: utf-8 -*-
"""Combined columns recovered from the FACES of an exploded outline.

Test10's roof draws a 12300x300 perimeter wall-column carrying four 300x3300
columns, every piece exploded to bare lines and the wall's own top edge running
THROUGH each column root. No piece closes into a ring, so the older recovery
passes produced two of the ten members plus a couple of 45-degree blobs.

Walking the planar graph's faces recovers each drawn member exactly. Because a
face is easy to invent, one is kept only when the plan's own SIZE LABEL agrees
with it. Standalone (no Revit).
"""

import os
import sys
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_MM = 304.8
_FT = 1.0 / _MM


report, shapes, layers = _loader.load("report", "geom.shapes", "classify.layers")


class _Rec(object):
    def __init__(self, points_mm, category=None):
        self.points = [(x * _FT, y * _FT, 0.0) for x, y in points_mm]
        self.category = category or layers.CATEGORY_COLUMN
        self.kind = "line" if len(points_mm) == 2 else "polyline"
        self.layer = "S-COLS"


class _Lbl(object):
    def __init__(self, b_mm, h_mm, x_mm, y_mm, mark=None):
        self.mark = mark
        self.b_mm = float(b_mm)
        self.h_mm = float(h_mm)
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _comb():
    """A 6000x300 wall with two 300x2000 columns standing on it, exploded.

    Drawn the way test10's roof is: the wall's top edge is ONE line running
    right through both column roots, so nothing closes into a ring.
    """
    lines = [
        [(0, 0), (6000, 0)],            # wall bottom
        [(0, 300), (6000, 300)],        # wall top -- straight through the roots
        [(0, 0), (0, 300)],             # wall end caps
        [(6000, 0), (6000, 300)],
        [(1000, 300), (1000, 2300)],    # column 1
        [(1300, 300), (1300, 2300)],
        [(1000, 2300), (1300, 2300)],
        [(4000, 300), (4000, 2300)],    # column 2
        [(4300, 300), (4300, 2300)],
        [(4000, 2300), (4300, 2300)],
    ]
    return [_Rec(line) for line in lines]


def _labels():
    return [_Lbl(300, 6000, 3000, -400), _Lbl(300, 2000, 1500, 1300),
            _Lbl(300, 2000, 4500, 1300)]


def _sections(rectangles=None):
    entries = ([{"layer": "S-COLS", "status": "composite", "approx": False,
                 "rectangles": list(rectangles)}] if rectangles else [])
    return {"entries": entries, "status_counts": {}, "circles": [],
            "total_rectangles": len(rectangles or [])}


def _rect(cx_mm, cy_mm, w_mm, h_mm, approx=False):
    return {"center": [cx_mm * _FT, cy_mm * _FT, 0.0],
            "width_mm": float(w_mm), "height_mm": float(h_mm),
            "width_ft": w_mm * _FT, "height_ft": h_mm * _FT}


def _placed(rects):
    return [(round(r["center"][0] * _MM), round(r["center"][1] * _MM),
             round(min(r["width_mm"], r["height_mm"])),
             round(max(r["width_mm"], r["height_mm"]))) for r in rects]


class WalkingTheFaces(unittest.TestCase):
    def test_each_drawn_member_comes_back_once(self):
        rects = shapes.recover_face_columns([r.points for r in _comb()])
        sizes = sorted((round(min(r.width_ft, r.height_ft) * _MM),
                        round(max(r.width_ft, r.height_ft) * _MM))
                       for r in rects)
        self.assertEqual(sizes, [(300, 2000), (300, 2000), (300, 6000)])

    def test_the_union_outline_is_not_a_member_of_its_own(self):
        # the walk yields the comb's whole boundary too; keeping it would place
        # the wall twice
        rects = shapes.recover_face_columns([r.points for r in _comb()])
        self.assertEqual(len(rects), 3)

    def test_a_skewed_path_is_left_alone(self):
        skew = [[(0, 0), (1000, 700)]]
        self.assertEqual(shapes.recover_face_columns(skew), [])

    def test_nothing_closed_gives_nothing(self):
        self.assertEqual(shapes.recover_face_columns([[(0, 0), (5000, 0)]]), [])
        self.assertEqual(shapes.recover_face_columns([]), [])


class LabelGatedRecovery(unittest.TestCase):
    def test_the_comb_is_recovered_from_its_labels(self):
        sections = _sections()
        placed = report.recover_face_columns(sections, _comb(), _labels())
        self.assertEqual(placed, 3)
        found = sorted(_placed([r for e in sections["entries"]
                                for r in e["rectangles"]]))
        self.assertEqual(found, [(1150, 1300, 300, 2000),
                                 (3000, 150, 300, 6000),
                                 (4150, 1300, 300, 2000)])
        self.assertEqual(sections["total_rectangles"], 3)

    def test_no_label_no_column(self):
        sections = _sections()
        self.assertEqual(report.recover_face_columns(sections, _comb(), []), 0)
        self.assertEqual(sections["entries"], [])

    def test_a_label_of_the_wrong_size_is_not_evidence(self):
        wrong = [_Lbl(450, 4500, 3000, -400), _Lbl(450, 4500, 1500, 1300)]
        sections = _sections()
        self.assertEqual(report.recover_face_columns(sections, _comb(), wrong), 0)

    def test_a_label_too_far_away_is_not_evidence(self):
        far = [_Lbl(300, 6000, 3000, -9000)]
        sections = _sections()
        self.assertEqual(report.recover_face_columns(sections, _comb(), far), 0)

    def test_an_already_placed_column_is_not_placed_twice(self):
        sections = _sections([_rect(1150, 1300, 300, 2000)])
        placed = report.recover_face_columns(sections, _comb(), _labels())
        self.assertEqual(placed, 2)
        self.assertEqual(sections["total_rectangles"], 3)

    def test_a_guessed_rectangle_inside_a_recovered_face_is_dropped(self):
        # the 45-degree blob the leftover-fragment pass makes of a comb corner
        sections = _sections()
        sections["entries"].append(
            {"layer": "(recovered)", "status": "recovered_rect", "approx": True,
             "rectangles": [_rect(4150, 1400, 212, 424)]})
        sections["total_rectangles"] = 1
        placed = report.recover_face_columns(sections, _comb(), _labels())
        self.assertEqual(placed, 3)
        statuses = [e["status"] for e in sections["entries"]]
        self.assertNotIn("recovered_rect", statuses)
        self.assertEqual(sections["total_rectangles"], 3)

    def test_a_piece_of_the_wall_read_as_its_own_column_is_dropped(self):
        """Test10's roof, in Revit: the 12300 wall AND two 2700 pieces of it.

        The pieces came in as closed outlines of their own, so nothing marked
        them approximate -- yet two solids in one place is always wrong, and the
        face agrees with the plan's label.
        """
        sections = _sections([_rect(1500, 150, 3000, 300),
                              _rect(4500, 150, 3000, 300)])
        placed = report.recover_face_columns(sections, _comb(), _labels())
        self.assertEqual(placed, 3)
        found = sorted(_placed([r for e in sections["entries"]
                                for r in e["rectangles"]]))
        self.assertEqual(found, [(1150, 1300, 300, 2000),
                                 (3000, 150, 300, 6000),
                                 (4150, 1300, 300, 2000)])

    def test_a_column_standing_on_the_wall_is_not_a_piece_of_it(self):
        # the teeth overlap the wall's ends but reach far beyond it: they are
        # members in their own right and must survive
        sections = _sections()
        report.recover_face_columns(sections, _comb(), _labels())
        heights = sorted(max(r["width_mm"], r["height_mm"])
                         for e in sections["entries"] for r in e["rectangles"])
        self.assertEqual([round(h) for h in heights], [2000, 2000, 6000])

    def test_a_fair_guess_at_the_same_member_still_blocks_it(self):
        """Only a FRAGMENT is overruled -- a rect of the right size is the member.

        Without this the pass would re-place (and shift) every approximately
        recovered column in the model, which is churn, not a fix.
        """
        sections = _sections()
        sections["entries"].append(
            {"layer": "(recovered)", "status": "recovered_strip", "approx": True,
             "rectangles": [_rect(4150, 1300, 300, 2000)]})
        sections["total_rectangles"] = 1
        placed = report.recover_face_columns(sections, _comb(), _labels())
        self.assertEqual(placed, 2)                    # the wall and column 1
        statuses = [e["status"] for e in sections["entries"]]
        self.assertIn("recovered_strip", statuses)     # the good guess survives
        self.assertEqual(sections["total_rectangles"], 3)

    def test_a_closed_outline_is_left_to_the_ordinary_passes(self):
        closed = [_Rec([(0, 0), (400, 0), (400, 400), (0, 400), (0, 0)])]
        sections = _sections()
        labels = [_Lbl(400, 400, 200, 200)]
        self.assertEqual(report.recover_face_columns(sections, closed, labels), 0)


class NestedColumns(unittest.TestCase):
    """A column wholly inside another is the same member read twice."""

    def test_a_piece_of_a_wall_is_dropped(self):
        sections = _sections([_rect(3000, 150, 12300, 300),
                              _rect(1500, 150, 2700, 300),
                              _rect(4500, 150, 2700, 300)])
        self.assertEqual(report.drop_nested_columns(sections), 2)
        kept = [r for e in sections["entries"] for r in e["rectangles"]]
        self.assertEqual(len(kept), 1)
        self.assertEqual(round(max(kept[0]["width_mm"], kept[0]["height_mm"])),
                         12300)
        self.assertEqual(sections["total_rectangles"], 1)

    def test_columns_that_merely_touch_are_both_kept(self):
        # a column standing ON the wall overlaps its end but reaches beyond it
        sections = _sections([_rect(3000, 150, 12300, 300),
                              _rect(1500, 1150, 300, 2300)])
        self.assertEqual(report.drop_nested_columns(sections), 0)

    def test_two_identical_columns_in_one_place_collapse_to_one(self):
        # the same member read twice: two solids cannot share ground
        sections = _sections([_rect(0, 0, 400, 400), _rect(0, 0, 400, 400)])
        self.assertEqual(report.drop_nested_columns(sections), 1)

    def test_neighbouring_columns_are_untouched(self):
        sections = _sections([_rect(0, 0, 400, 400), _rect(3000, 0, 400, 400),
                              _rect(0, 3000, 600, 900)])
        self.assertEqual(report.drop_nested_columns(sections), 0)

    def test_an_empty_model_is_no_work(self):
        self.assertEqual(report.drop_nested_columns(_sections()), 0)
        self.assertEqual(report.drop_nested_columns(_sections([_rect(0, 0, 300, 300)])), 0)


if __name__ == "__main__":
    unittest.main()

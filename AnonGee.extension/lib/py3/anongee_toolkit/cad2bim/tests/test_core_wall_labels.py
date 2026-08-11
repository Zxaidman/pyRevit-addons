# -*- coding: utf-8 -*-
"""report.recover_core_walls_from_labels -- label-guided fused core-wall placement.

Test19 finding: a lift/stair core drawn as loose wall lines is assembled into one
blob and decomposed greedily, which mis-assigns the shared corners. Each thin wall
comes out the right THICKNESS but clipped/extended along its length and offset by the
stolen corner (e.g. the 5300 right wall placed as 4700, its centre 600 mm low). This
pass re-tiles the blob from its size+mark labels so every wall lands at its true
position -- but only when the labels tile the WHOLE blob cleanly. Standalone (no Revit).
"""

import os
import sys
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_MM = 304.8
_FT = 1.0 / _MM


report, shapes = _loader.load("report", "geom.shapes")


class _Lbl(object):
    def __init__(self, mark, b_mm, h_mm, x_mm, y_mm):
        self.mark = mark
        self.b_mm = b_mm
        self.h_mm = h_mm
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _rect(cx_mm, cy_mm, w_mm, h_mm):
    return {"center": [cx_mm * _FT, cy_mm * _FT, 0.0],
            "width_mm": float(w_mm), "height_mm": float(h_mm),
            "width_ft": w_mm * _FT, "height_ft": h_mm * _FT}


# Test19's fused core, exactly as the rectilinear-recovery pass decomposes it: five
# thin strips that exactly cover the blob but mis-cut its four shared corners.
def _core_pieces():
    return [_rect(6500, 3000, 3300, 900),    # bottom strip (C12, over-long: 3300 vs 3000)
            _rect(8000, 5800, 300, 4700),    # right strip  (C10, clipped: 4700 vs 5300)
            _rect(3300, 5000, 900, 900),     # C9 block fused with a C8 corner
            _rect(3000, 6800, 300, 2700),    # left strip   (C8, clipped + low)
            _rect(5500, 8000, 4700, 300)]    # top strip    (C6, clipped: 4700 vs 5300)


# One mark+size label per wall (positions are the real Test19 text insertion points).
_LABELS = [_Lbl("C6", 300, 5300, 4891, 8423),
           _Lbl("C8", 300, 3300, 3337, 6111),
           _Lbl("C9", 600, 900, 3214, 5663),
           _Lbl("C10", 300, 5300, 8337, 5058),
           _Lbl("C12", 900, 3000, 6008, 3663)]

# True wall centres + sizes (mm) the carve must recover.
_EXPECT = {
    "C6":  (5500, 8000, 5300, 300),
    "C8":  (3000, 6200, 300, 3300),
    "C9":  (3450, 5000, 600, 900),
    "C10": (8000, 5200, 300, 5300),
    "C12": (6350, 3000, 3000, 900),
}


def _sections(pieces):
    return {"entries": [{"layer": "(recovered)", "status": "recovered_strip",
                         "rectangles": list(pieces)}],
            "status_counts": {}}


class CoreWallLabels(unittest.TestCase):

    def _carved(self, sec):
        return [r for e in sec["entries"] if e["status"] == "label_core_wall"
                for r in e["rectangles"]]

    def test_blob_retiled_to_true_positions(self):
        sec = _sections(_core_pieces())
        n = report.recover_core_walls_from_labels(sec, _LABELS)
        self.assertEqual(n, 1)                       # one blob re-tiled
        walls = {r["mark"]: r for r in self._carved(sec)}
        self.assertEqual(set(walls), set(_EXPECT))
        for mark, (cx, cy, w, h) in _EXPECT.items():
            r = walls[mark]
            self.assertAlmostEqual(r["center"][0] / _FT, cx, delta=1.0)
            self.assertAlmostEqual(r["center"][1] / _FT, cy, delta=1.0)
            self.assertEqual({round(r["width_mm"]), round(r["height_mm"])},
                             {w, h})

    def test_long_axis_matches_orientation(self):
        sec = _sections(_core_pieces())
        report.recover_core_walls_from_labels(sec, _LABELS)
        walls = {r["mark"]: r for r in self._carved(sec)}
        # Vertical walls (taller than wide) carry a 90 deg long axis; horizontal 0.
        self.assertEqual(walls["C10"]["long_axis_deg"], 90.0)
        self.assertEqual(walls["C8"]["long_axis_deg"], 90.0)
        self.assertEqual(walls["C6"]["long_axis_deg"], 0.0)
        self.assertEqual(walls["C12"]["long_axis_deg"], 0.0)

    def test_consumed_pieces_removed_from_source_entry(self):
        sec = _sections(_core_pieces())
        report.recover_core_walls_from_labels(sec, _LABELS)
        leftover = [r for e in sec["entries"]
                    if e["status"] == "recovered_strip" for r in e["rectangles"]]
        self.assertEqual(leftover, [])               # all five strips re-tiled

    def test_incomplete_labels_leave_blob_untouched(self):
        # Drop C9's label: the blob can no longer be cleanly tiled, so the pass must
        # bail and leave the original decomposition exactly as it was.
        sec = _sections(_core_pieces())
        partial = [t for t in _LABELS if t.mark != "C9"]
        n = report.recover_core_walls_from_labels(sec, partial)
        self.assertEqual(n, 0)
        self.assertEqual(self._carved(sec), [])
        kept = [r for e in sec["entries"]
                if e["status"] == "recovered_strip" for r in e["rectangles"]]
        self.assertEqual(len(kept), 5)

    def test_markless_size_labels_do_not_retile(self):
        # Mark-driven: size-only labels (no mark) must never re-place a working wall.
        sec = _sections(_core_pieces())
        markless = [_Lbl(None, t.b_mm, t.h_mm,
                         t.point_internal[0] / _FT, t.point_internal[1] / _FT)
                    for t in _LABELS]
        n = report.recover_core_walls_from_labels(sec, markless)
        self.assertEqual(n, 0)
        self.assertEqual(self._carved(sec), [])

    def test_lone_strip_not_treated_as_blob(self):
        # A single recovered strip (no fused neighbours) is not a core: leave it.
        sec = _sections([_rect(8000, 1500, 300, 3300)])
        n = report.recover_core_walls_from_labels(
            sec, [_Lbl("CX", 300, 3300, 8000, 1500)])
        self.assertEqual(n, 0)

    def test_stacked_adjacent_columns_split_correctly(self):
        # Test19's C15 (600x900) with C16 (300x600) drawn hard against its underside:
        # the two outlines fuse and the greedy cut splits them into a left 300x900
        # strip + a tall 300x1500 strip, which text-correction would merge wholly into
        # C15 -- consuming C16's geometry so the marked column vanishes. The carve must
        # re-cut them into C15 (top) and C16 (bottom-right). C16's label sits well below
        # the blob (bottom-row text offset), so the wider label margin must reach it.
        pieces = [_rect(2850, -300, 300, 900),     # left half of C15
                  _rect(3150, -600, 300, 1500)]    # right half of C15 fused with C16
        labels = [_Lbl("C15", 600, 900, 2711, 363),
                  _Lbl("C16", 300, 600, 2629, -2285)]
        sec = _sections(pieces)
        n = report.recover_core_walls_from_labels(sec, labels)
        self.assertEqual(n, 1)
        walls = {r["mark"]: r for r in self._carved(sec)}
        self.assertEqual(set(walls), {"C15", "C16"})
        self.assertAlmostEqual(walls["C15"]["center"][0] / _FT, 3000, delta=1.0)
        self.assertAlmostEqual(walls["C15"]["center"][1] / _FT, -300, delta=1.0)
        self.assertEqual({round(walls["C15"]["width_mm"]),
                          round(walls["C15"]["height_mm"])}, {600, 900})
        self.assertAlmostEqual(walls["C16"]["center"][0] / _FT, 3150, delta=1.0)
        self.assertAlmostEqual(walls["C16"]["center"][1] / _FT, -1050, delta=1.0)
        self.assertEqual({round(walls["C16"]["width_mm"]),
                          round(walls["C16"]["height_mm"])}, {300, 600})

    def test_stacked_pair_with_markless_lower_both_placed(self):
        # The SAME shape but the lower column is markless-but-sized (Test19's C17 over a
        # "300x600" stub). The blob holds a marked label (C17), so it IS re-tiled, and
        # the markless stub gets its own cell -- placed UNNAMED -- instead of being
        # swallowed into C17.
        pieces = [_rect(8150, -300, 300, 900),
                  _rect(7850, -600, 300, 1500)]
        labels = [_Lbl("C17", 600, 900, 7711, 363),
                  _Lbl(None, 300, 600, 8187, -1887)]
        sec = _sections(pieces)
        n = report.recover_core_walls_from_labels(sec, labels)
        self.assertEqual(n, 1)
        carved = self._carved(sec)
        named = {r["mark"]: r for r in carved if r.get("mark")}
        markless = [r for r in carved if not r.get("mark")]
        self.assertIn("C17", named)
        self.assertAlmostEqual(named["C17"]["center"][0] / _FT, 8000, delta=1.0)
        self.assertAlmostEqual(named["C17"]["center"][1] / _FT, -300, delta=1.0)
        self.assertEqual(len(markless), 1)
        self.assertAlmostEqual(markless[0]["center"][0] / _FT, 7850, delta=1.0)
        self.assertAlmostEqual(markless[0]["center"][1] / _FT, -1050, delta=1.0)
        self.assertEqual({round(markless[0]["width_mm"]),
                          round(markless[0]["height_mm"])}, {300, 600})

    def test_markless_only_core_left_untouched(self):
        # A fused core whose pieces carry ONLY markless labels is a working plan's core:
        # with no marked label present the pass must not fire (no re-tiling).
        pieces = [_rect(8000, 1500, 300, 3300),
                  _rect(8300, 3000, 300, 300)]
        labels = [_Lbl(None, 300, 3300, 8000, 1500),
                  _Lbl(None, 300, 300, 8300, 3000)]
        sec = _sections(pieces)
        n = report.recover_core_walls_from_labels(sec, labels)
        self.assertEqual(n, 0)
        self.assertEqual(self._carved(sec), [])




class GrowBackOverTheCarve(unittest.TestCase):
    """StaircasePlan-Test2 SW10: a wall carved by a crossing wall must grow back
    over the carve, not push past its free end.

    The drawn wall spans y -300..7550 (7850 long). Decomposition gives SW10 only
    the part above the crossing wall SW9 (y 100..7550, 7450 long), so applying
    the schedule's 7850 about THAT centre moved the wall 200mm up and off the
    drawing. The free end must be pinned instead.

    The rectangles come from decompose_to_rectangles here, NOT hand-built: those
    carry no long_axis_deg and store width/height as X and Y sizes, and reading
    them under the oriented short/long convention is what let the bug survive an
    earlier hand-built fixture.
    """

    def _decomposed_u(self):
        """The drawn SW9/SW10/SW11 channel, exactly as the export carries it."""
        ring = [(x * _FT, y * _FT) for x, y in
                [(17200, -300), (16800, -300), (11200, -300), (10800, -300),
                 (10800, 7550), (11200, 7550), (11200, 100), (16800, 100),
                 (16800, 7550), (17200, 7550)]]
        return [r.to_dict() for r in shapes.decompose_to_rectangles(ring)]

    def _run(self, rects):
        sections = {"entries": [{"layer": "S-COLS", "status": "rect",
                                 "rectangles": list(rects)}]}
        texts = [_Lbl("SW10", None, None, 11000.0, 3825.0),
                 _Lbl("SW11", None, None, 17000.0, 3825.0),
                 _Lbl("SW9", None, None, 14000.0, -100.0)]
        report.correct_columns_with_text(
            sections, texts, 1300.0 * _FT,
            schedule={"SW10": (400.0, 7850.0), "SW11": (400.0, 7850.0),
                      "SW9": (400.0, 5600.0)})
        return {rect.get("mark"): rect
                for rect in sections["entries"][0]["rectangles"]}

    def test_the_drawn_channel_decomposes_into_three_legs(self):
        spans = sorted((round(r["width_mm"]), round(r["height_mm"]))
                       for r in self._decomposed_u())
        self.assertEqual(spans, [(400, 7450), (400, 7450), (6400, 400)])

    def test_free_end_is_pinned_when_growing(self):
        placed = self._run(self._decomposed_u())
        for mark in ("SW10", "SW11"):
            grown = placed.get(mark)
            self.assertIsNotNone(grown, mark)
            centre_mm = grown["center"][1] * _MM
            half = max(grown["width_mm"], grown["height_mm"]) / 2.0
            self.assertAlmostEqual(centre_mm, 3625.0, places=3)
            self.assertAlmostEqual(centre_mm - half, -300.0, places=3)
            self.assertAlmostEqual(centre_mm + half, 7550.0, places=3)

    def test_a_column_stacked_on_the_free_end_does_not_block_the_growth(self):
        """The case that survived TWO fixes: BOTH ends abut something.

        Test2's SW10 has SW9 crossing below it and a 900x900 column sitting on
        its top end, so "exactly one end abuts" was never true and the wall kept
        its carved centre. The end to pin is the one whose neighbour merely
        BUTTS; the carve came from the member that runs ACROSS the wall.
        """
        rects = self._decomposed_u()
        for x in (11000.0, 17000.0):        # the columns capping both walls
            rects.append({"center": [x * _FT, 8000.0 * _FT, 0.0],
                          "width_mm": 900.0, "height_mm": 900.0,
                          "width_ft": 900.0 * _FT, "height_ft": 900.0 * _FT})
        placed = self._run(rects)
        for mark in ("SW10", "SW11"):
            grown = placed.get(mark)
            self.assertIsNotNone(grown, mark)
            centre_mm = grown["center"][1] * _MM
            half = max(grown["width_mm"], grown["height_mm"]) / 2.0
            self.assertAlmostEqual(centre_mm, 3625.0, places=3)
            self.assertAlmostEqual(centre_mm - half, -300.0, places=3)
            self.assertAlmostEqual(centre_mm + half, 7550.0, places=3)

    def test_uncarved_column_keeps_its_centre(self):
        # already the scheduled length: nothing to grow, nothing to re-anchor
        whole = {"center": [11000.0 * _FT, 3625.0 * _FT, 0.0],
                 "width_mm": 400.0, "height_mm": 7850.0,
                 "width_ft": 400.0 * _FT, "height_ft": 7850.0 * _FT,
                 "long_axis_deg": 90.0}
        others = [r for r in self._decomposed_u() if r["width_mm"] > 1000.0]
        kept = self._run([whole] + others).get("SW10")
        self.assertIsNotNone(kept)
        self.assertAlmostEqual(kept["center"][1] * _MM, 3625.0, places=3)


if __name__ == "__main__":
    unittest.main()

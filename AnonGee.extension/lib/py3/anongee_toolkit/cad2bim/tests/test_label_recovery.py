# -*- coding: utf-8 -*-
"""report.recover_unplaced_labeled_columns -- recover an ABSORBED labelled column.

Test18 (fragmented) finding: a small column (C16/C17, 300x600) cast hard against a
600x900 neighbour fragments so badly that recovery folds its pieces into the bigger
column and drops the rest, orphaning its label. This last-resort pass replaces it from
its schedule size + the leftover geometry -- but only with hard evidence, and never on
top of an existing column. Standalone (no Revit).
"""

import os
import sys
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_MM = 304.8
_FT = 1.0 / _MM


report = _loader.load("report")


class _Lbl(object):
    def __init__(self, mark, x_mm, y_mm):
        self.mark = mark
        self.b_mm = None
        self.h_mm = None
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _rect(cx_mm, cy_mm, w_mm, h_mm, mark=None):
    return {"center": [cx_mm * _FT, cy_mm * _FT, 0.0],
            "width_mm": float(w_mm), "height_mm": float(h_mm),
            "width_ft": w_mm * _FT, "height_ft": h_mm * _FT, "mark": mark}


def _frag(*pts_mm):
    return {"kind": "polyline", "status": "open_path", "pts": [list(p) for p in pts_mm]}


def _sections(placed, dropped):
    return {"entries": [{"layer": "x", "status": "text_corrected",
                         "rectangles": list(placed)}],
            "circles": [], "dropped_raw": list(dropped), "status_counts": {}}


# A placed 600x900 neighbour (C15) and the leftover bits of an absorbed 300x600 (C16)
# just below it -- outside the neighbour's footprint.
_C15 = _rect(3000, -300, 600, 900, mark="C15")
_C16_BITS = [_frag((3200, -1200), (3100, -1300)), _frag((3300, -1250), (3150, -1150))]
_C16_LABEL = _Lbl("C16", 2630, -1918)
_SCHED = {"C16": (300, 600), "C15": (600, 900)}


class LabelRecovery(unittest.TestCase):

    def _run(self, placed, dropped, texts, schedule, **kw):
        sec = _sections(placed, dropped)
        n = report.recover_unplaced_labeled_columns(sec, texts, schedule,
                                                    limits=report.DEFAULT_LIMITS, **kw)
        recovered = [r for e in sec["entries"] if e["status"] == "label_recovered"
                     for r in e["rectangles"]]
        return n, recovered

    def test_absorbed_column_recovered_abutting_neighbour(self):
        n, rec = self._run([_C15], _C16_BITS, [_C16_LABEL], _SCHED)
        self.assertEqual(n, 1)
        r = rec[0]
        self.assertEqual(r["mark"], "C16")
        self.assertEqual(sorted((r["width_mm"], r["height_mm"])), [300, 600])
        # Abuts C15's bottom edge exactly: edge = centre(-300) - half(450) = -750 mm;
        # the 600-long side hangs below it -> centre = -750 - 300 = -1050 mm. The abut
        # coordinate is fixed by geometry, not guessed from sparse fragment centroids.
        edge = _C15["center"][1] - _C15["height_ft"] / 2.0
        self.assertAlmostEqual(r["center"][1], edge - (600 * _FT) / 2.0, places=4)
        # The cross coordinate stays clamped against the neighbour (columns abut, never
        # drift away) and it is NOT snapped onto the neighbour's grid axis.
        self.assertLessEqual(abs(r["center"][0] - _C15["center"][0]),
                             (_C15["width_ft"] + 300 * _FT) / 2.0 + 1e-6)

    def test_no_leftover_geometry_places_nothing(self):
        # Evidence gate: a label with no nearby leftover fragments cannot fabricate one.
        n, rec = self._run([_C15], [], [_C16_LABEL], _SCHED)
        self.assertEqual((n, rec), (0, []))

    def test_mark_without_schedule_size_places_nothing(self):
        n, rec = self._run([_C15], _C16_BITS, [_C16_LABEL], {"C15": (600, 900)})
        self.assertEqual((n, rec), (0, []))

    def test_already_placed_mark_is_left_alone(self):
        placed = [_C15, _rect(3000, -1200, 300, 600, mark="C16")]
        n, rec = self._run(placed, _C16_BITS, [_C16_LABEL], _SCHED)
        self.assertEqual((n, rec), (0, []))

    def test_no_placed_neighbour_places_nothing(self):
        # The leftover bits exist but there is no placed column nearby -> not a known
        # column region, so nothing is fabricated.
        n, rec = self._run([_rect(40000, 40000, 600, 900, mark="Z9")],
                           _C16_BITS, [_C16_LABEL], _SCHED)
        self.assertEqual((n, rec), (0, []))

    def test_never_overlaps_an_existing_column(self):
        # If the only leftover sits inside another placed column's footprint, the
        # would-be centroid overlaps it -> skipped, never a duplicate.
        big = _rect(3000, -1200, 1200, 1200, mark="CORE")
        n, rec = self._run([_C15, big], _C16_BITS, [_C16_LABEL], _SCHED)
        self.assertEqual((n, rec), (0, []))

    def test_circle_named_mark_is_not_duplicated(self):
        sec = _sections([_C15], _C16_BITS)
        sec["circles"] = [{"center": [3000 * _FT, -1200 * _FT, 0.0], "mark": "C16"}]
        n = report.recover_unplaced_labeled_columns(sec, [_C16_LABEL], _SCHED,
                                                   limits=report.DEFAULT_LIMITS)
        self.assertEqual(n, 0)


class StackedSliverDeferredToAbutment(unittest.TestCase):
    """Redrawn-Test18 C17: a 300x600 cast hard against a 600x900 (C9) survives Revit's
    import only as a mis-centred sliver. Resizing that sliver to the schedule size used
    to land C17's CENTRE inside C9 -- two stacked columns, 450 mm off. Text-correction
    must now DEFER such a stacked result so the abutment pass places it edge-to-edge,
    exactly as it already does for C17 when the DXF is more fragmented.
    """

    # Faithful redrawn-Test18 geometry (mm): the placed neighbour C9 and the absorbed
    # sliver text-correction would otherwise claim as C17, plus C17's leftover outline.
    C9 = _rect(7615, -2624, 600, 900, mark="C9")
    C9["long_axis_deg"] = 90.0
    SLIVER = _rect(7615, -2924, 300, 300)          # clipped piece, no mark
    SLIVER["long_axis_deg"] = 90.0
    C9_LABEL = _Lbl("C9", 7745, -1962)
    C17_LABEL = _Lbl("C17", 7802, -3817)
    C17_BITS = [_frag((7615, -3674), (7315, -3674), (7315, -3374)),
                _frag((7915, -2774), (7915, -3074), (7615, -3074))]
    SCHED = {"C9": (600, 900), "C17": (300, 600)}

    def _pipeline(self):
        sec = {"entries": [{"layer": "geom", "status": "x",
                            "rectangles": [dict(self.C9, center=list(self.C9["center"])),
                                           dict(self.SLIVER,
                                                center=list(self.SLIVER["center"]))]}],
               "circles": [], "dropped_raw": [dict(g) for g in self.C17_BITS],
               "status_counts": {}}
        radius = 1300.0 * _FT
        report.correct_columns_with_text(sec, [self.C9_LABEL, self.C17_LABEL], radius,
                                         schedule=self.SCHED,
                                         grid_x=None, grid_y=None, grid_snap_ft=None)
        report.recover_unplaced_labeled_columns(sec, [self.C9_LABEL, self.C17_LABEL],
                                                self.SCHED, limits=report.DEFAULT_LIMITS)
        return [r for e in sec["entries"] for r in e["rectangles"]]

    def test_c17_abutted_not_stacked(self):
        placed = self._pipeline()
        c17 = [r for r in placed if r.get("mark") == "C17"]
        self.assertEqual(len(c17), 1)                       # placed exactly once
        r = c17[0]
        self.assertEqual(sorted((r["width_mm"], r["height_mm"])), [300, 600])
        # Abuts C9's bottom edge: edge = -2624 - 450 = -3074; the 600 side hangs below
        # -> centre y = -3074 - 300 = -3374 (was the stacked -2924, 450 mm too high).
        self.assertAlmostEqual(r["center"][1], -3374 * _FT, places=3)
        # Its centre is no longer inside C9's footprint (no stacked columns).
        self.assertFalse(report._center_inside_larger(r, [self.C9], []))

    def test_absorbed_sliver_left_no_phantom(self):
        placed = self._pipeline()
        # The discarded sliver must not survive as an unmarked column inside C9.
        ghosts = [r for r in placed if not r.get("mark")
                  and report._center_inside_larger(r, [self.C9], [])]
        self.assertEqual(ghosts, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""report.recover_unplaced_labeled_columns -- recover an ABSORBED labelled column.

Test18 (fragmented) finding: a small column (C16/C17, 300x600) cast hard against a
600x900 neighbour fragments so badly that recovery folds its pieces into the bigger
column and drops the rest, orphaning its label. This last-resort pass replaces it from
its schedule size + the leftover geometry -- but only with hard evidence, and never on
top of an existing column. Standalone (no Revit).
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


def _load_report():
    for name in ("_aglr", "_aglr.geom", "_aglr.classify"):
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

    load("_aglr.config", "config.py")
    load("_aglr.geom.shapes", "geom", "shapes.py")
    load("_aglr.classify.marks", "classify", "marks.py")
    load("_aglr.classify.layers", "classify", "layers.py")
    return load("_aglr.report", "report.py")


report = _load_report()


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

    def test_absorbed_column_recovered_from_label_and_geometry(self):
        n, rec = self._run([_C15], _C16_BITS, [_C16_LABEL], _SCHED)
        self.assertEqual(n, 1)
        self.assertEqual(rec[0]["mark"], "C16")
        self.assertEqual(sorted((rec[0]["width_mm"], rec[0]["height_mm"])), [300, 600])
        # placed below the neighbour, abutting, not on top of it
        self.assertLess(rec[0]["center"][1], _C15["center"][1])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

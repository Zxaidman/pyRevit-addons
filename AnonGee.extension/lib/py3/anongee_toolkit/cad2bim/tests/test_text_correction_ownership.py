# -*- coding: utf-8 -*-
"""report.correct_columns_with_text -- label/rectangle ownership.

Test18 (redrawn-fix) finding: a long member's size label reaches far (radius is a fixed
mark_radius_mm), so a 300x3300 wall's label was swallowing a distinct 600x900 column only
~465 mm away as a "split pair" -- its merge window is the labelled long side (3300). The
column then vanished and the wall shifted, making the text pass WORSE than geometry-only.
Each rectangle now belongs to its NEAREST label, so a closer label keeps its own column;
a genuine clip (two fragments, one label) must still merge. Standalone (no Revit).
"""

import importlib.util
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
_FT = 1.0 / 304.8


def _load_report():
    for name in ("_agt", "_agt.geom", "_agt.classify"):
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

    load("_agt.config", "config.py")
    load("_agt.geom.shapes", "geom", "shapes.py")
    load("_agt.classify.marks", "classify", "marks.py")
    load("_agt.classify.layers", "classify", "layers.py")
    return load("_agt.report", "report.py")


report = _load_report()
_RADIUS = 1300.0 * _FT


class _Lbl(object):
    def __init__(self, mark, x_mm, y_mm, b=None, h=None):
        self.mark = mark
        self.b_mm = b
        self.h_mm = h
        self.point_internal = (x_mm * _FT, y_mm * _FT, 0.0)


def _rect(cx_mm, cy_mm, w_mm, h_mm):
    return {"center": [cx_mm * _FT, cy_mm * _FT, 0.0],
            "width_mm": float(w_mm), "height_mm": float(h_mm),
            "width_ft": w_mm * _FT, "height_ft": h_mm * _FT}


def _run(rects, labels, schedule):
    sections = {"entries": [{"layer": "x", "status": "s", "rectangles": list(rects)}],
                "status_counts": {}}
    report.correct_columns_with_text(sections, labels, _RADIUS, schedule=schedule)
    return sections["entries"][0]["rectangles"] if sections["entries"] else []


class Ownership(unittest.TestCase):

    def test_neighbour_with_own_label_is_not_absorbed(self):
        # Real Test18-fix geometry: C8 (300x3300 wall) and C9 (600x900) marks 465 mm apart.
        c8 = _rect(4861, 4772, 300, 3300)
        c9 = _rect(4737, 4324, 600, 900)
        out = _run([c8, c9], [_Lbl("C8", 4861, 4772), _Lbl("C9", 4737, 4324)],
                   {"C8": (300, 3300), "C9": (600, 900)})
        marks = sorted(r.get("mark") for r in out if r.get("mark"))
        self.assertEqual(marks, ["C8", "C9"])           # both survive; C9 not swallowed
        c9_out = next(r for r in out if r.get("mark") == "C9")
        self.assertEqual(sorted((c9_out["width_mm"], c9_out["height_mm"])), [600, 900])
        self.assertAlmostEqual(c9_out["center"][1], 4324 * _FT, places=4)   # not merged off

    def test_genuine_clip_two_fragments_one_label_still_merges(self):
        # One 300x3300 column clipped into two collinear halves, a single label between
        # them -> ownership keeps both (same nearest label) and they merge into one.
        top = _rect(5000, 5825, 300, 1650)
        bot = _rect(5000, 4175, 300, 1650)
        out = _run([top, bot], [_Lbl("C20", 5000, 5000)], {"C20": (300, 3300)})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["mark"], "C20")
        self.assertEqual(sorted((out[0]["width_mm"], out[0]["height_mm"])), [300, 3300])


class ClippedSizeSnap(unittest.TestCase):
    """A label's size is authoritative: a clipped column is resized up to it, but an
    already-correct column (within geometry noise) is left exactly as drawn."""

    def test_clipped_column_resized_up_to_schedule_size(self):
        # C14: a 270x600 sliver of a scheduled 300x600 column. The 30 mm shortfall sits
        # inside the 80 mm 'close enough' band, yet must snap UP to the schedule size.
        clipped = _rect(-300, -300, 270, 600)
        out = _run([clipped], [_Lbl("C14", -300, -300)], {"C14": (300, 600)})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["mark"], "C14")
        self.assertEqual(sorted((out[0]["width_mm"], out[0]["height_mm"])), [300, 600])

    def test_rotated_clip_keeps_its_angle(self):
        clipped = _rect(0, 0, 270, 600)
        clipped["long_axis_deg"] = 150.0
        out = _run([clipped], [_Lbl("C14", 0, 0)], {"C14": (300, 600)})
        self.assertEqual(sorted((out[0]["width_mm"], out[0]["height_mm"])), [300, 600])
        self.assertAlmostEqual(out[0]["long_axis_deg"], 150.0)

    def test_correctly_sized_column_left_as_drawn(self):
        ok = _rect(0, 0, 600, 900)
        out = _run([ok], [_Lbl("C1", 0, 0)], {"C1": (600, 900)})
        self.assertEqual(out[0]["mark"], "C1")
        self.assertEqual(sorted((out[0]["width_mm"], out[0]["height_mm"])), [600, 900])

    def test_minor_undersize_within_tolerance_not_snapped(self):
        # A 5 mm shortfall is geometry noise, not a clip: kept as drawn, not resized.
        noise = _rect(0, 0, 595, 900)
        out = _run([noise], [_Lbl("C1", 0, 0)], {"C1": (600, 900)})
        self.assertEqual(min(out[0]["width_mm"], out[0]["height_mm"]), 595)


if __name__ == "__main__":
    unittest.main(verbosity=2)

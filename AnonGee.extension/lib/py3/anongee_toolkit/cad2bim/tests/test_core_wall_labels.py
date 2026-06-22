# -*- coding: utf-8 -*-
"""report.recover_core_walls_from_labels -- label-guided fused core-wall placement.

Test19 finding: a lift/stair core drawn as loose wall lines is assembled into one
blob and decomposed greedily, which mis-assigns the shared corners. Each thin wall
comes out the right THICKNESS but clipped/extended along its length and offset by the
stolen corner (e.g. the 5300 right wall placed as 4700, its centre 600 mm low). This
pass re-tiles the blob from its size+mark labels so every wall lands at its true
position -- but only when the labels tile the WHOLE blob cleanly. Standalone (no Revit).
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
    for name in ("_cwl", "_cwl.geom", "_cwl.classify"):
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

    load("_cwl.config", "config.py")
    load("_cwl.geom.shapes", "geom", "shapes.py")
    load("_cwl.classify.marks", "classify", "marks.py")
    load("_cwl.classify.layers", "classify", "layers.py")
    return load("_cwl.report", "report.py")


report = _load_report()


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


if __name__ == "__main__":
    unittest.main()

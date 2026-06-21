# -*- coding: utf-8 -*-
"""Column-schedule parsing (marks.parse_schedule).

Covers the single multi-block table (the real Test15 layout) and the Test17
regression where column / beam / slab schedules share one layer and must be read
as independent tables -- the column's size must not be corrupted by the beam
table's column x-positions (height read as length).

Standalone (no numpy / no Revit): marks.py loads by file path.
"""

import importlib.util
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)


def _load_marks():
    for name in ("_agm", "_agm.classify"):
        if name not in sys.modules:
            mod = types.ModuleType(name)
            mod.__path__ = []
            sys.modules[name] = mod
    spec = importlib.util.spec_from_file_location(
        "_agm.classify.marks", os.path.join(_PKG, "classify", "marks.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_agm.classify.marks"] = mod
    spec.loader.exec_module(mod)
    return mod


marks = _load_marks()


class _Cell(object):
    """Minimal TextRecord stand-in: text at a planar point."""
    def __init__(self, text, x, y):
        self.text = text
        self.point = (x, y, 0.0)
        self.point_internal = None


def _row(y, *pairs):
    """Cells for one row: (x, text) pairs at height y."""
    return [_Cell(text, x, y) for x, text in pairs]


class SingleTable(unittest.TestCase):

    def test_mark_w_l_h_reads_wxl_ignores_h(self):
        cells = []
        cells += _row(1000, (0, "Mark"), (900, "W"), (1800, "L"), (2700, "H"))
        cells += _row(300, (0, "C1"), (900, "400"), (1800, "600"), (2700, "3000"))
        cells += _row(-400, (0, "C2"), (900, "500"), (1800, "500"), (2700, "3000"))
        self.assertEqual(marks.parse_schedule(cells),
                         {"C1": (400.0, 600.0), "C2": (500.0, 500.0)})

    def test_side_by_side_blocks_one_header(self):
        # Test15 layout: Mark|W|L|H repeated across two blocks in one header row.
        cells = []
        cells += _row(1000, (0, "Mark"), (900, "W"), (1800, "L"), (2700, "H"),
                      (5000, "Mark"), (5900, "W"), (6800, "L"), (7700, "H"))
        cells += _row(300, (0, "C1"), (900, "300"), (1800, "600"), (2700, "3000"),
                      (5000, "C3"), (5900, "350"), (6800, "650"), (7700, "3000"))
        self.assertEqual(marks.parse_schedule(cells),
                         {"C1": (300.0, 600.0), "C3": (350.0, 650.0)})

    def test_size_column(self):
        cells = []
        cells += _row(1000, (0, "Mark"), (1500, "Size"))
        cells += _row(300, (0, "C1"), (1500, "400x600"))
        self.assertEqual(marks.parse_schedule(cells), {"C1": (400.0, 600.0)})


class StackedTablesOnOneLayer(unittest.TestCase):
    """Test17: a beam table sits above a column table on the same layer, with a
    different x-layout. Each table must be read with its own x-positions."""

    def _cells(self):
        cells = []
        # Beam schedule (top): Mark W D at x = 0, 2200, 4400
        cells += _row(24000, (0, "Mark"), (2200, "W"), (4400, "D"))
        cells += _row(23000, (0, "B1"), (2200, "230"), (4400, "450"))
        cells += _row(22000, (0, "B2"), (2200, "300"), (4400, "600"))
        # Column schedule (below): Mark W L H at x = 0, 1500, 3000, 4500
        cells += _row(20000, (0, "Mark"), (1500, "W"), (3000, "L"), (4500, "H"))
        cells += _row(19000, (0, "C1"), (1500, "400"), (3000, "400"), (4500, "3000"))
        cells += _row(18000, (0, "C2"), (1500, "500"), (3000, "600"), (4500, "3000"))
        # Slab schedule (bottom): Mark Thk -- not a sizable header, must be ignored
        cells += _row(16000, (0, "Mark"), (2200, "Thk"))
        cells += _row(15000, (0, "S1"), (2200, "150"))
        return cells

    def test_column_sizes_not_corrupted_by_beam_layout(self):
        out = marks.parse_schedule(self._cells())
        # The bug read the H column (3000) as the column length.
        self.assertEqual(out["C1"], (400.0, 400.0))
        self.assertEqual(out["C2"], (500.0, 600.0))

    def test_beam_table_read_with_its_own_columns(self):
        out = marks.parse_schedule(self._cells())
        self.assertEqual(out["B1"], (230.0, 450.0))
        self.assertEqual(out["B2"], (300.0, 600.0))

    def test_slab_table_contributes_nothing(self):
        out = marks.parse_schedule(self._cells())
        self.assertNotIn("S1", out)


class FallbackLayouts(unittest.TestCase):

    def test_inline_cell(self):
        self.assertEqual(
            marks.parse_schedule([_Cell("C1 400x600", 0, 0)]),
            {"C1": (400.0, 600.0)})

    def test_no_cells(self):
        self.assertEqual(marks.parse_schedule([]), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)

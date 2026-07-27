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

    def test_beam_table_w_h_l_reads_wxh_ignores_span(self):
        # Test18 beam schedule is Mark|W|H|L: H is the section DEPTH, L is the SPAN.
        # A beam's size is W x H; the (longer) span L must be ignored, NOT read as depth.
        cells = []
        cells += _row(1000, (0, "Mark"), (900, "W"), (1800, "H"), (2700, "L"))
        cells += _row(300, (0, "B1"), (900, "300"), (1800, "600"), (2700, "2960"))
        cells += _row(-400, (0, "B14"), (900, "400"), (1800, "900"), (2700, "4325"))
        self.assertEqual(marks.parse_schedule(cells),
                         {"B1": (300.0, 600.0), "B14": (400.0, 900.0)})

    def test_column_w_h_l_still_reads_wxl(self):
        # The SAME W H L header for a COLUMN keeps W x L (footprint); H is storey height.
        cells = []
        cells += _row(1000, (0, "Mark"), (900, "W"), (1800, "H"), (2700, "L"))
        cells += _row(300, (0, "C1"), (900, "600"), (1800, "3000"), (2700, "900"))
        self.assertEqual(marks.parse_schedule(cells), {"C1": (600.0, 900.0)})


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

    def test_split_pairs_a_real_table_row(self):
        # A headerless table row -- mark cell beside a single size cell -- still pairs.
        cells = [_Cell("C1", 0, 0), _Cell("400x600", 1500, 0)]
        self.assertEqual(marks.parse_schedule(cells), {"C1": (400.0, 600.0)})


class PlanLabelsAreNotATable(unittest.TestCase):
    """Test17 C5: on the PLAN, a markless size label and an unrelated mark share a
    Y but belong to columns a whole bay apart. Split-pairing must be OFF for plan
    labels, so C5 (which has no size of its own) falls back to its geometry."""

    def _plan(self):
        # 'C5' at x=10300 and a markless '350x750' at x=5300 share y=12300 (5 m apart).
        return [_Cell("350x750", 5300, 12300), _Cell("C5", 10300, 12300)]

    def test_split_off_does_not_pair_far_plan_labels(self):
        self.assertEqual(marks.parse_schedule(self._plan(), allow_split=False), {})

    def test_split_on_would_pair_them(self):
        # Documents why the guard is needed: with split on, C5 wrongly inherits 350x750.
        self.assertEqual(marks.parse_schedule(self._plan(), allow_split=True),
                         {"C5": (350.0, 750.0)})

    def test_inline_plan_label_still_sizes_with_split_off(self):
        # A genuine inline plan label keeps working without the split path.
        self.assertEqual(
            marks.parse_schedule([_Cell("C9 400x600", 0, 0)], allow_split=False),
            {"C9": (400.0, 600.0)})


class MarkToken(unittest.TestCase):
    """parse_mark must read the mark even when it butts straight against the size
    with an underscore (Test19 plan labels: "C16_300 X 600"). An underscore is a
    regex word char, so the old trailing \\b never fired there and the mark was lost
    -- which silently disabled mark-driven recovery and column naming for the plan."""

    def test_underscore_between_mark_and_size(self):
        self.assertEqual(marks.parse_mark("C16_300 X 600"), ("C16", 300.0, 600.0))
        self.assertEqual(marks.parse_mark("C8_300 X 3300"), ("C8", 300.0, 3300.0))
        self.assertEqual(marks.parse_mark("C12_900 X 3000"), ("C12", 900.0, 3000.0))

    def test_underscore_mark_without_parseable_size(self):
        # A diameter label ("750D") yields no BxH, but the mark must still parse.
        self.assertEqual(marks.parse_mark("C7_750D"), ("C7", None, None))

    def test_markless_size_label_stays_markless(self):
        self.assertEqual(marks.parse_mark("300 X 600"), (None, 300.0, 600.0))

    def test_existing_space_and_bare_formats_unchanged(self):
        self.assertEqual(marks.parse_mark("C1 400x400"), ("C1", 400.0, 400.0))
        self.assertEqual(marks.parse_mark("C9"), ("C9", None, None))
        self.assertEqual(marks.parse_mark("RB12"), ("RB12", None, None))
        self.assertEqual(marks.parse_mark("C1A"), ("C1A", None, None))

    def test_underscore_schedule_inline(self):
        # The underscore inline label also flows through parse_schedule.
        self.assertEqual(
            marks.parse_schedule([_Cell("C16_300 X 600", 0, 0)], allow_split=False),
            {"C16": (300.0, 600.0)})


if __name__ == "__main__":
    unittest.main(verbosity=2)

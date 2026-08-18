# -*- coding: utf-8 -*-
"""Revit-free tests for RC Automation's workbook layer.

Run from the repository root::

    python3 -m unittest discover -s tests -v

Everything under test here reads a schedule and decides whether it can be built.
None of it imports Revit. Only ``excel_engine.read_grid`` imports openpyxl, and
it is covered by :class:`ReadGridTests`, which is skipped when openpyxl is not
importable -- the extension vendors a Windows build whose numpy will not load
everywhere, so the file layer cannot be assumed testable. Everything else takes
raw lists of lists, so every rule below is checked against hand-written rows on
any machine at all. That seam is the point.
"""

import csv
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))

from _rc_loader import load as _load_rc                          # noqa: E402

_rc = _load_rc()
models = _rc.models
standards = _rc.standards
excel_engine = _rc.excel_engine
validation = _rc.validation
reconcile = _rc.reconcile

_FIXTURES = os.path.join(_ROOT, "tests", "fixtures", "rc_automation")
_BBS_STANDARD = os.path.join(
    _ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
    "BBS Generator.pushbutton", "standards", "BS_8666_2020.py")


# ── helpers ────────────────────────────────────────────────────────────────

def grid(text):
    """A CSV string as the list of lists ``parse_grid`` consumes."""
    return [row for row in csv.reader(io.StringIO(text.strip("\n")))]


def fixture_grids():
    """The sample workbook, one grid per sheet."""
    grids = {}
    for name in ("FOOTING_TYPES", "FOOTING_REBAR", "FOOTING_PLACEMENT",
                 "COLUMN_TYPES", "COLUMN_REBAR", "COLUMN_PLACEMENT"):
        with io.open(os.path.join(_FIXTURES, name + ".csv"),
                     encoding="utf-8") as handle:
            grids[name] = [row for row in csv.reader(handle)]
    return grids


def errors(issues):
    return [i for i in issues if i.severity == models.SEVERITY_ERROR]


def warnings(issues):
    return [i for i in issues if i.severity == models.SEVERITY_WARNING]


def messages(issues):
    return " | ".join(str(i) for i in issues)


def minimal_grids(**overrides):
    """A workbook that validates clean, so a test can break one thing at a time."""
    grids = {
        "FOOTING_TYPES": grid("""
UNITS,mm
TypeMark,Length,Width,Thickness,CoverTop,CoverBottom,CoverSide
F1,3000,3000,900,50,75,50
"""),
        "FOOTING_REBAR": grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,16,15,200,21
"""),
        "COLUMN_TYPES": grid("""
TypeMark,Width,Depth,Cover
C1,400,400,40
"""),
        "COLUMN_REBAR": grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode
C1,Main,20,8,,00
C1,Tie,10,,200,51
"""),
        "FOOTING_PLACEMENT": grid("""
Mark,TypeMark,X,Y,Level
F1-A1,F1,0,0,Foundation
"""),
        "COLUMN_PLACEMENT": grid("""
Mark,TypeMark,X,Y,BaseLevel,TopLevel
C1-A1,C1,0,0,Foundation,Level 1
"""),
    }
    grids.update(overrides)
    return grids


# ── cell coercion ──────────────────────────────────────────────────────────

class CoercionTests(unittest.TestCase):

    def test_numbers_pass_through(self):
        self.assertEqual(excel_engine.coerce_number(1200), (1200.0, None))
        self.assertEqual(excel_engine.coerce_number(1200.5), (1200.5, None))

    def test_blank_is_not_an_error(self):
        for blank in (None, "", "   "):
            self.assertEqual(excel_engine.coerce_number(blank), (None, None))

    def test_thousands_separator_and_unit_suffix(self):
        self.assertEqual(excel_engine.coerce_number("1,200")[0], 1200.0)
        self.assertEqual(excel_engine.coerce_number("1200 mm")[0], 1200.0)
        self.assertEqual(excel_engine.coerce_number(" 900 ")[0], 900.0)

    def test_text_is_reported_not_guessed(self):
        value, error = excel_engine.coerce_number("N/A")
        self.assertIsNone(value)
        self.assertIn("N/A", error)

    def test_booleans_are_not_numbers(self):
        # Excel hands back True for a checkbox cell; 1.0 would be a silent lie.
        self.assertIsNone(excel_engine.coerce_number(True)[0])

    def test_whole_bar_counts_only(self):
        self.assertEqual(excel_engine.coerce_count(12.0), (12, None))
        self.assertEqual(excel_engine.coerce_count("12"), (12, None))
        value, error = excel_engine.coerce_count(12.5)
        self.assertIsNone(value)
        self.assertIn("whole number", error)

    def test_fold_ignores_case_spaces_and_underscores(self):
        for spelling in ("Cover Top", "cover_top", "COVERTOP", "Cover-Top"):
            self.assertEqual(excel_engine.fold(spelling), "covertop")


class ShapeCodeTests(unittest.TestCase):

    def test_excel_numeric_shape_codes(self):
        # A cell holding 00 comes back as int 0 or float 0.0 depending on how it
        # was formatted; all three spellings are the same shape code.
        for raw in (0, 0.0, "00", "0"):
            self.assertEqual(standards.normalise_shape_code(raw), "00")
        for raw in (51, 51.0, "51"):
            self.assertEqual(standards.normalise_shape_code(raw), "51")

    def test_non_codes_are_rejected(self):
        for raw in (13.5, "abc", "", None, 100, True):
            self.assertIsNone(standards.normalise_shape_code(raw))

    def test_standard_diameters(self):
        self.assertTrue(standards.is_standard_diameter(16))
        self.assertTrue(standards.is_standard_diameter(16.0))
        self.assertFalse(standards.is_standard_diameter(13))
        self.assertFalse(standards.is_standard_diameter(None))


# ── the grid ───────────────────────────────────────────────────────────────

class HeaderDetectionTests(unittest.TestCase):

    def test_header_is_found_below_a_title_block(self):
        data, issues = excel_engine.parse_grid(fixture_grids())
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertIn("F1", data.footing_type_by_mark)
        # Title block is 4 rows, header is row 5, so F1 is row 6 in Excel.
        self.assertEqual(data.footing_type("F1").source_row, 6)

    def test_metadata_above_the_header_is_read(self):
        data, _ = excel_engine.parse_grid(fixture_grids())
        self.assertEqual(data.metadata.get("project"), "Riverside Tower")
        self.assertEqual(data.units, "mm")

    def test_missing_header_is_one_error_naming_the_columns(self):
        grids = minimal_grids(FOOTING_TYPES=grid("""
some,unrelated,spreadsheet
1,2,3
"""))
        _, issues = excel_engine.parse_grid(grids)
        found = [i for i in errors(issues)
                 if i.sheet == "FOOTING_TYPES" and "header" in i.message]
        self.assertEqual(len(found), 1, messages(issues))
        self.assertIn("TypeMark", found[0].message)


class SheetAndColumnTests(unittest.TestCase):

    def test_missing_sheet_is_reported(self):
        grids = minimal_grids()
        del grids["COLUMN_REBAR"]
        _, issues = excel_engine.parse_grid(grids)
        self.assertTrue(any("COLUMN_REBAR" in i.message for i in errors(issues)),
                        messages(issues))

    def test_sheet_names_tolerate_spacing_and_case(self):
        grids = minimal_grids()
        grids["footing types"] = grids.pop("FOOTING_TYPES")
        data, issues = excel_engine.parse_grid(grids)
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertIn("F1", data.footing_type_by_mark)

    def test_missing_column_is_reported_once_not_per_row(self):
        grids = minimal_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Count,Spacing,ShapeCode
F1,B1,X,15,200,21
F1,B2,Y,15,200,21
F1,T1,X,,250,00
"""))
        _, issues = excel_engine.parse_grid(grids)
        missing = [i for i in errors(issues) if "Diameter" in i.message]
        self.assertEqual(len(missing), 1, messages(issues))

    def test_original_spec_column_names_still_load(self):
        # The feature specification called these FootingMark and ColumnMark.
        grids = minimal_grids(FOOTING_REBAR=grid("""
FootingMark,Layer,Direction,Dia,Nos,Spacing,Shape
F1,B1,X,16,15,200,21
"""))
        data, issues = excel_engine.parse_grid(grids)
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertEqual(data.footing_rebar[0].type_mark, "F1")
        self.assertEqual(data.footing_rebar[0].diameter_mm, 16.0)
        self.assertEqual(data.footing_rebar[0].count, 15)

    def test_blank_rows_are_skipped_and_keyless_rows_warn(self):
        grids = minimal_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,16,15,200,21
,,,,,,
,B2,Y,16,15,200,21
"""))
        data, issues = excel_engine.parse_grid(grids)
        self.assertEqual(len(data.footing_rebar), 1)
        self.assertTrue(any("no TypeMark" in i.message for i in warnings(issues)),
                        messages(issues))

    def test_placement_is_read_in_every_mode(self):
        # Parsing is mode-independent so switching mode in the window never
        # means re-reading the file.
        for mode in models.MODES:
            data, _ = excel_engine.parse_grid(minimal_grids(), mode=mode)
            self.assertEqual(len(data.footing_placement), 1, mode)

    def test_rebar_modes_do_not_demand_placement(self):
        grids = minimal_grids()
        del grids["FOOTING_PLACEMENT"]
        del grids["COLUMN_PLACEMENT"]
        for mode in (models.MODE_REBAR_ONLY, models.MODE_RECONCILE):
            _, issues = excel_engine.parse_grid(grids, mode=mode)
            self.assertEqual(errors(issues), [], mode + ": " + messages(issues))

    def test_creating_structure_demands_placement(self):
        grids = minimal_grids()
        del grids["FOOTING_PLACEMENT"]
        _, issues = excel_engine.parse_grid(grids, mode=models.MODE_CREATE_ALL)
        self.assertTrue(any("FOOTING_PLACEMENT" in i.message
                            for i in errors(issues)), messages(issues))

    def test_unused_placement_is_noted_not_rejected(self):
        _, issues = excel_engine.parse_grid(
            minimal_grids(), mode=models.MODE_REBAR_ONLY)
        self.assertEqual(errors(issues), [], messages(issues))
        info = [i for i in issues if i.severity == models.SEVERITY_INFO]
        self.assertTrue(any("not used in this mode" in i.message for i in info),
                        messages(issues))


class UnitsTests(unittest.TestCase):

    def test_declared_millimetres(self):
        data, issues = excel_engine.parse_grid(minimal_grids())
        self.assertEqual(data.units, "mm")
        self.assertEqual(errors(issues), [], messages(issues))

    def test_other_units_are_refused(self):
        grids = minimal_grids(FOOTING_TYPES=grid("""
UNITS,m
TypeMark,Length,Width,Thickness,CoverTop,CoverBottom,CoverSide
F1,3,3,0.9,0.05,0.075,0.05
"""))
        _, issues = excel_engine.parse_grid(grids)
        self.assertTrue(any("UNITS" in i.message for i in errors(issues)),
                        messages(issues))

    def test_undeclared_units_warn_and_assume_mm(self):
        grids = minimal_grids(FOOTING_TYPES=grid("""
TypeMark,Length,Width,Thickness,CoverTop,CoverBottom,CoverSide
F1,3000,3000,900,50,75,50
"""))
        data, issues = excel_engine.parse_grid(grids)
        self.assertEqual(data.units, "mm")
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertTrue(any("UNITS" in i.message for i in warnings(issues)),
                        messages(issues))


# ── layout rules and layer geometry ────────────────────────────────────────

class LayoutRuleTests(unittest.TestCase):

    def rebar(self, count=None, spacing=None):
        return models.FootingRebarRow("F1", layer="B1", direction="X",
                                      diameter_mm=16, count=count,
                                      spacing_mm=spacing)

    def test_count_and_spacing_gives_number_with_spacing(self):
        self.assertEqual(self.rebar(12, 200).layout_rule(),
                         models.LAYOUT_NUMBER_WITH_SPACING)

    def test_count_alone_gives_fixed_number(self):
        self.assertEqual(self.rebar(count=12).layout_rule(),
                         models.LAYOUT_FIXED_NUMBER)

    def test_spacing_alone_gives_maximum_spacing(self):
        self.assertEqual(self.rebar(spacing=200).layout_rule(),
                         models.LAYOUT_MAXIMUM_SPACING)

    def test_neither_has_no_rule(self):
        self.assertIsNone(self.rebar().layout_rule())


class LayerTests(unittest.TestCase):

    def test_outer_layers_are_index_zero(self):
        for layer in ("B1", "T1"):
            row = models.FootingRebarRow("F1", layer=layer)
            self.assertEqual(row.layer_index(), 0)

    def test_second_layers_are_index_one(self):
        # The creation layer turns this into a z-offset of index x diameter:
        # B2 sits one bar above B1.
        for layer in ("B2", "T2"):
            row = models.FootingRebarRow("F1", layer=layer)
            self.assertEqual(row.layer_index(), 1)

    def test_faces_are_distinguished(self):
        self.assertTrue(models.FootingRebarRow("F1", layer="B1").is_bottom)
        self.assertTrue(models.FootingRebarRow("F1", layer="T2").is_top)
        self.assertFalse(models.FootingRebarRow("F1", layer="T1").is_bottom)


# ── validation ─────────────────────────────────────────────────────────────

def validate_grids(mode=models.MODE_CREATE_ALL, **overrides):
    data, parse_issues = excel_engine.parse_grid(
        minimal_grids(**overrides), mode=mode)
    return data, parse_issues + validation.validate(data, mode=mode)


class ValidationBaselineTests(unittest.TestCase):

    def test_the_minimal_workbook_is_clean(self):
        _, issues = validate_grids()
        self.assertEqual(errors(issues), [], messages(issues))

    def test_the_sample_workbook_is_clean(self):
        data, parse_issues = excel_engine.parse_grid(fixture_grids())
        issues = parse_issues + validation.validate(data)
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertEqual(len(data.footing_types), 3)
        self.assertEqual(len(data.column_types), 3)

    def test_sample_column_carries_two_main_bar_groups(self):
        # "4T20 corners + 6T16 faces" is one column, two rows -- the shape the
        # original single-row COLUMN_REBAR sheet could not express.
        data, _ = excel_engine.parse_grid(fixture_grids())
        mains = [r for r in data.column_rebar_for("C1") if r.is_main]
        self.assertEqual(sorted(r.diameter_mm for r in mains), [16.0, 20.0])

    def test_empty_workbook_is_an_error(self):
        issues = validation.validate(models.WorkbookData())
        self.assertTrue(errors(issues), messages(issues))


class TypeValidationTests(unittest.TestCase):

    def test_duplicate_type_marks_are_rejected(self):
        _, issues = validate_grids(FOOTING_TYPES=grid("""
UNITS,mm
TypeMark,Length,Width,Thickness,CoverTop,CoverBottom,CoverSide
F1,3000,3000,900,50,75,50
F1,2400,2400,750,50,75,50
"""))
        self.assertTrue(any("already defined" in i.message for i in errors(issues)),
                        messages(issues))

    def test_duplicate_rows_survive_parsing(self):
        """The evidence has to reach the validator to be reported.

        Keying rows into a dict as they are parsed drops the second row of a
        duplicated mark, and the duplicate rule then has nothing to find. The
        list keeps every row; the lookup keeps the first.
        """
        data, _ = excel_engine.parse_grid(minimal_grids(FOOTING_TYPES=grid("""
UNITS,mm
TypeMark,Length,Width,Thickness,CoverTop,CoverBottom,CoverSide
F1,3000,3000,900,50,75,50
F1,2400,2400,750,50,75,50
""")))
        self.assertEqual(len(data.footing_types), 2)
        self.assertEqual(len(data.footing_type_by_mark), 1)
        self.assertEqual(data.footing_type("F1").length_mm, 3000.0)

    def test_cover_thicker_than_the_footing_is_rejected(self):
        _, issues = validate_grids(FOOTING_TYPES=grid("""
UNITS,mm
TypeMark,Length,Width,Thickness,CoverTop,CoverBottom,CoverSide
F1,3000,3000,100,50,75,50
"""))
        self.assertTrue(any("no room for bars" in i.message for i in errors(issues)),
                        messages(issues))

    def test_metres_typed_as_millimetres_are_flagged(self):
        # 3 mm long is the classic unit slip; it must not reach a transaction.
        _, issues = validate_grids(FOOTING_TYPES=grid("""
UNITS,mm
TypeMark,Length,Width,Thickness,CoverTop,CoverBottom,CoverSide
F1,3,3,0.9,50,75,50
"""))
        self.assertTrue(errors(issues) or warnings(issues), messages(issues))
        self.assertIn("units", messages(issues).lower())

    def test_column_cover_wider_than_the_section(self):
        _, issues = validate_grids(COLUMN_TYPES=grid("""
TypeMark,Width,Depth,Cover
C1,400,60,40
"""))
        self.assertTrue(errors(issues), messages(issues))


class RebarValidationTests(unittest.TestCase):

    def test_non_standard_diameter_is_rejected(self):
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,13,15,200,21
"""))
        self.assertTrue(any("not a BS 8666:2020 bar size" in i.message
                            for i in errors(issues)), messages(issues))

    def test_spacing_tighter_than_the_bar_is_rejected(self):
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,20,15,16,21
"""))
        self.assertTrue(any("overlap" in i.message for i in errors(issues)),
                        messages(issues))

    def test_neither_count_nor_spacing_is_rejected(self):
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,16,,,21
"""))
        self.assertTrue(any("nothing to lay out" in i.message
                            for i in errors(issues)), messages(issues))

    def test_unknown_layer_and_direction_are_rejected(self):
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,MIDDLE,Z,16,15,200,21
"""))
        text = messages(errors(issues))
        self.assertIn("Layer", text)
        self.assertIn("Direction", text)

    def test_one_layer_may_only_be_described_once(self):
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,16,15,200,21
F1,B1,X,20,12,250,21
"""))
        self.assertTrue(any("already described" in i.message
                            for i in errors(issues)), messages(issues))

    def test_a_link_shape_is_not_a_footing_layer(self):
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,16,15,200,51
"""))
        self.assertTrue(any("closed link" in i.message for i in errors(issues)),
                        messages(issues))

    def test_unsupported_shape_warns_and_does_not_block(self):
        # Shape 41 is real BS 8666 and BBS can schedule it; P0 cannot build it.
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,16,15,200,41
"""))
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertTrue(any("cannot build its geometry" in i.message
                            for i in warnings(issues)), messages(issues))

    def test_rebar_referring_to_a_missing_type_is_rejected(self):
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F9,B1,X,16,15,200,21
"""))
        self.assertTrue(any("No footing type" in i.message for i in errors(issues)),
                        messages(issues))

    def test_footing_without_bottom_steel_warns(self):
        _, issues = validate_grids(FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,T1,X,16,15,200,00
"""))
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertTrue(any("no bottom reinforcement" in i.message
                            for i in warnings(issues)), messages(issues))


class ColumnRebarValidationTests(unittest.TestCase):

    def test_a_tie_must_be_a_closed_link(self):
        _, issues = validate_grids(COLUMN_REBAR=grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode
C1,Main,20,8,,00
C1,Tie,10,,200,00
"""))
        self.assertTrue(any("must be a closed link" in i.message
                            for i in errors(issues)), messages(issues))

    def test_a_tie_needs_a_spacing(self):
        _, issues = validate_grids(COLUMN_REBAR=grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode
C1,Main,20,8,,00
C1,Tie,10,,,51
"""))
        self.assertTrue(any("Spacing is required" in i.message
                            for i in errors(issues)), messages(issues))

    def test_main_bars_need_a_count(self):
        _, issues = validate_grids(COLUMN_REBAR=grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode
C1,Main,20,,200,00
C1,Tie,10,,200,51
"""))
        self.assertTrue(any("Count is required" in i.message
                            for i in errors(issues)), messages(issues))

    def test_half_a_confinement_zone_is_rejected(self):
        _, issues = validate_grids(COLUMN_REBAR=grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode,SpacingEnd,ConfinementLength
C1,Main,20,8,,00,,
C1,Tie,10,,200,51,100,
"""))
        self.assertTrue(any("no zone for it to apply to" in i.message
                            for i in errors(issues)), messages(issues))

    def test_looser_end_spacing_warns(self):
        _, issues = validate_grids(COLUMN_REBAR=grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode,SpacingEnd,ConfinementLength
C1,Main,20,8,,00,,
C1,Tie,10,,150,51,250,600
"""))
        self.assertTrue(any("tighter, not looser" in i.message
                            for i in warnings(issues)), messages(issues))

    def test_a_cage_wider_than_its_column_is_rejected(self):
        # 2 x (40 cover + 10 tie + 32 main) = 164 across a 150 mm section.
        _, issues = validate_grids(
            COLUMN_TYPES=grid("""
TypeMark,Width,Depth,Cover
C1,150,600,40
"""),
            COLUMN_REBAR=grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode
C1,Main,32,8,,00
C1,Tie,10,,200,51
"""))
        self.assertTrue(any("cage does not fit" in i.message
                            for i in errors(issues)), messages(issues))

    def test_two_tie_rows_for_one_column_are_ambiguous(self):
        _, issues = validate_grids(COLUMN_REBAR=grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode
C1,Main,20,8,,00
C1,Tie,10,,200,51
C1,Tie,10,,150,51
"""))
        self.assertTrue(any("already described" in i.message
                            for i in errors(issues)), messages(issues))

    def test_column_without_ties_warns(self):
        _, issues = validate_grids(COLUMN_REBAR=grid("""
TypeMark,BarRole,Diameter,Count,Spacing,ShapeCode
C1,Main,20,8,,00
"""))
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertTrue(any("no ties" in i.message for i in warnings(issues)),
                        messages(issues))


class IssueReportingTests(unittest.TestCase):

    def test_an_issue_names_the_cell(self):
        issue = models.Issue(models.SEVERITY_ERROR, "13 mm is not a bar size",
                             sheet="FOOTING_REBAR", row=7, column="Diameter")
        self.assertEqual(str(issue),
                         "FOOTING_REBAR row 7 · Diameter — 13 mm is not a bar size")

    def test_errors_sort_before_warnings_before_info(self):
        issues = models.sort_issues([
            models.Issue(models.SEVERITY_INFO, "counts"),
            models.Issue(models.SEVERITY_WARNING, "odd"),
            models.Issue(models.SEVERITY_ERROR, "broken"),
        ])
        self.assertEqual([i.severity for i in issues],
                         [models.SEVERITY_ERROR, models.SEVERITY_WARNING,
                          models.SEVERITY_INFO])

    def test_counts_cover_every_severity(self):
        counts = models.count_by_severity(
            [models.Issue(models.SEVERITY_ERROR, "x")])
        self.assertEqual(counts[models.SEVERITY_ERROR], 1)
        self.assertEqual(counts[models.SEVERITY_WARNING], 0)
        self.assertEqual(counts[models.SEVERITY_INFO], 0)

    def test_validation_reports_what_it_read(self):
        _, issues = validate_grids()
        info = [i for i in issues if i.severity == models.SEVERITY_INFO]
        self.assertTrue(any("footing types" in i.message for i in info),
                        messages(issues))


# ── the copy of BS 8666 must not drift ─────────────────────────────────────

class StandardsAgreementTests(unittest.TestCase):
    """``standards.py`` holds a subset of BBS Generator's BS 8666 module.

    A copy is only tolerable while something fails when the two disagree, so
    this loads the real module by path -- it cannot be imported, it lives in a
    different pushbutton -- and holds them to each other.
    """

    def bbs(self):
        spec = importlib.util.spec_from_file_location("bs8666", _BBS_STANDARD)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_standard_module_is_where_it_is_expected(self):
        self.assertTrue(os.path.isfile(_BBS_STANDARD), _BBS_STANDARD)

    def test_bar_diameters_match_the_unit_weight_table(self):
        self.assertEqual(sorted(standards.BAR_DIAMETERS_MM),
                         sorted(self.bbs().UNIT_WEIGHTS.keys()))

    def test_known_shape_codes_match(self):
        self.assertEqual(sorted(standards.KNOWN_SHAPE_CODES),
                         sorted(self.bbs().SHAPE_MAP.keys()))

    def test_supported_codes_are_a_subset_of_known_ones(self):
        self.assertTrue(
            set(standards.SUPPORTED_SHAPE_CODES) <= set(standards.KNOWN_SHAPE_CODES))
        self.assertTrue(
            set(standards.LINK_SHAPE_CODES) <= set(standards.SUPPORTED_SHAPE_CODES))

    def test_every_supported_code_has_a_description(self):
        for code in standards.SUPPORTED_SHAPE_CODES:
            self.assertIn(code, standards.SHAPE_DESCRIPTIONS)


# ── placement ──────────────────────────────────────────────────────────────

class OutlineParsingTests(unittest.TestCase):

    def test_a_polygon_reads(self):
        points, error = excel_engine.parse_outline(
            "0,0; 4500,0; 4500,3000; 2250,4200; 0,3000")
        self.assertIsNone(error)
        self.assertEqual(len(points), 5)
        self.assertEqual(points[0], (0.0, 0.0))
        self.assertEqual(points[3], (2250.0, 4200.0))

    def test_blank_is_not_an_error(self):
        self.assertEqual(excel_engine.parse_outline(""), (None, None))
        self.assertEqual(excel_engine.parse_outline(None), (None, None))

    def test_a_repeated_closing_point_is_dropped(self):
        # Writing the first point again at the end is how people close a
        # polygon; carrying it would place a zero-length edge and Revit would
        # refuse the sketch.
        points, error = excel_engine.parse_outline(
            "0,0; 3000,0; 3000,2000; 0,2000; 0,0")
        self.assertIsNone(error)
        self.assertEqual(len(points), 4)

    def test_too_few_points_is_rejected(self):
        _, error = excel_engine.parse_outline("0,0; 3000,0")
        self.assertIn("at least 3", error)

    def test_a_malformed_point_names_itself(self):
        _, error = excel_engine.parse_outline("0,0; 3000; 3000,2000")
        self.assertIn("3000", error)

    def test_a_non_numeric_point_is_rejected(self):
        _, error = excel_engine.parse_outline("0,0; a,b; 3000,2000")
        self.assertIn("numbers", error)


class PlacementValidationTests(unittest.TestCase):

    def test_the_sample_workbook_places_cleanly(self):
        data, parse_issues = excel_engine.parse_grid(fixture_grids())
        issues = parse_issues + validation.validate(data)
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertEqual(len(data.footing_placement), 6)
        self.assertEqual(len(data.column_placement), 5)

    def test_the_sample_carries_a_non_rectangular_pad(self):
        # The reason footings are floors rather than family instances.
        data, _ = excel_engine.parse_grid(fixture_grids())
        shaped = [p for p in data.footing_placement if p.has_outline]
        self.assertEqual(len(shaped), 1)
        self.assertEqual(len(shaped[0].outline), 5)

    def test_grid_references_and_coordinates_both_locate_a_row(self):
        data, _ = excel_engine.parse_grid(fixture_grids())
        by_mark = dict((p.mark, p) for p in data.footing_placement)
        self.assertTrue(by_mark["F1-A1"].has_grid_reference)
        self.assertEqual(by_mark["F1-A1"].location_description(), "A-1")
        self.assertTrue(by_mark["F3-P1"].has_coordinates)
        self.assertTrue(all(p.is_locatable for p in data.footing_placement))

    def test_a_row_with_no_position_is_rejected(self):
        _, issues = validate_grids(FOOTING_PLACEMENT=grid("""
Mark,TypeMark,GridX,GridY,X,Y,Level
F1-A1,F1,,,,,Foundation
"""))
        self.assertTrue(any("No position" in i.message for i in errors(issues)),
                        messages(issues))

    def test_half_a_grid_reference_is_rejected(self):
        _, issues = validate_grids(FOOTING_PLACEMENT=grid("""
Mark,TypeMark,GridX,GridY,X,Y,Level
F1-A1,F1,A,,,,Foundation
"""))
        self.assertTrue(any("Only one grid reference" in i.message
                            for i in errors(issues)), messages(issues))

    def test_half_a_coordinate_is_rejected(self):
        _, issues = validate_grids(FOOTING_PLACEMENT=grid("""
Mark,TypeMark,GridX,GridY,X,Y,Level
F1-A1,F1,,,12500,,Foundation
"""))
        self.assertTrue(any("Only one coordinate" in i.message
                            for i in errors(issues)), messages(issues))

    def test_placing_an_undescribed_type_is_rejected(self):
        _, issues = validate_grids(FOOTING_PLACEMENT=grid("""
Mark,TypeMark,X,Y,Level
F9-A1,F9,0,0,Foundation
"""))
        self.assertTrue(any("No footing type" in i.message
                            for i in errors(issues)), messages(issues))

    def test_duplicate_instance_marks_are_rejected(self):
        _, issues = validate_grids(FOOTING_PLACEMENT=grid("""
Mark,TypeMark,X,Y,Level
F1-A1,F1,0,0,Foundation
F1-A1,F1,3000,0,Foundation
"""))
        self.assertTrue(any("already placed" in i.message
                            for i in errors(issues)), messages(issues))

    def test_a_column_between_one_level_and_itself_is_rejected(self):
        _, issues = validate_grids(COLUMN_PLACEMENT=grid("""
Mark,TypeMark,X,Y,BaseLevel,TopLevel
C1-A1,C1,0,0,Level 1,Level 1
"""))
        self.assertTrue(any("no height" in i.message for i in errors(issues)),
                        messages(issues))

    def test_a_flat_outline_is_rejected(self):
        _, issues = validate_grids(FOOTING_PLACEMENT=grid("""
Mark,TypeMark,X,Y,Level,Outline
F1-A1,F1,0,0,Foundation,"0,0; 1000,0; 2000,0"
"""))
        self.assertTrue(any("no area" in i.message for i in errors(issues)),
                        messages(issues))

    def test_a_type_that_is_never_placed_warns(self):
        _, issues = validate_grids(FOOTING_TYPES=grid("""
UNITS,mm
TypeMark,Length,Width,Thickness,CoverTop,CoverBottom,CoverSide
F1,3000,3000,900,50,75,50
F2,2400,2400,750,50,75,50
"""), FOOTING_REBAR=grid("""
TypeMark,Layer,Direction,Diameter,Count,Spacing,ShapeCode
F1,B1,X,16,15,200,21
F2,B1,X,16,12,200,21
"""))
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertTrue(any("never placed" in i.message for i in warnings(issues)),
                        messages(issues))

    def test_placement_is_not_checked_when_nothing_is_created(self):
        # A workbook with no coordinates in it is perfectly good for putting
        # rebar into a model that is already built.
        _, issues = validate_grids(
            mode=models.MODE_REBAR_ONLY,
            FOOTING_PLACEMENT=grid("""
Mark,TypeMark,GridX,GridY,X,Y,Level
F1-A1,F1,,,,,
"""))
        self.assertEqual(errors(issues), [], messages(issues))


# ── reconciliation ─────────────────────────────────────────────────────────

class ReconciliationTests(unittest.TestCase):

    def compare(self, excel, model, **kwargs):
        return reconcile.compare("F1-A1", "Footing", excel, model, **kwargs)

    def test_agreement_produces_no_conflicts(self):
        result = self.compare({"length_mm": 3000.0}, {"length_mm": 3000.0})
        self.assertTrue(result.agrees)
        self.assertEqual(result.conflicts, [])

    def test_a_difference_is_found_and_described(self):
        result = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        self.assertEqual(result.field_count, 1)
        self.assertEqual(result.conflicts[0].describe(),
                         "Length: 3000 in the schedule, 3200 in the model")

    def test_excel_wins_by_default(self):
        result = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        self.assertEqual(result.source, reconcile.SOURCE_EXCEL)
        self.assertEqual(result.resolved("length_mm"), 3000.0)
        self.assertFalse(result.is_user_choice)

    def test_the_user_can_choose_the_model(self):
        result = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        result.use_model()
        self.assertEqual(result.resolved("length_mm"), 3200.0)
        self.assertTrue(result.is_user_choice)

    def test_a_default_is_distinguishable_from_a_decision(self):
        # A report that cannot tell one from the other is not an audit trail.
        chosen = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        chosen.use_excel()
        untouched = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        self.assertEqual(chosen.source, untouched.source)
        self.assertTrue(chosen.is_user_choice)
        self.assertFalse(untouched.is_user_choice)

    def test_an_unknown_source_is_refused_not_guessed(self):
        result = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        with self.assertRaises(ValueError):
            result.choose("Whatever")

    def test_rounding_noise_is_not_a_conflict(self):
        # The toolkit rounds to the nearest millimetre; 0.4 mm is unit
        # conversion, not a disagreement.
        result = self.compare({"length_mm": 3000.0}, {"length_mm": 3000.4})
        self.assertTrue(result.agrees)

    def test_bar_counts_are_exact(self):
        result = reconcile.compare("F1 B1", "Rebar", {"count": 15}, {"count": 14})
        self.assertEqual(result.field_count, 1)

    def test_a_field_the_model_cannot_report_is_not_a_conflict(self):
        # An unreadable parameter is "unknown", not "zero"; treating it as a
        # difference would bury the real ones.
        result = self.compare({"length_mm": 3000.0}, {})
        self.assertTrue(result.agrees)
        self.assertEqual(result.resolved("length_mm"), 3000.0)

    def test_choosing_the_model_still_falls_back_to_the_schedule(self):
        result = self.compare({"length_mm": 3000.0, "width_mm": 3000.0},
                              {"length_mm": 3200.0})
        result.use_model()
        self.assertEqual(result.resolved("length_mm"), 3200.0)
        self.assertEqual(result.resolved("width_mm"), 3000.0)

    def test_a_field_the_schedule_omits_is_not_compared(self):
        result = self.compare({"length_mm": 3000.0}, {"length_mm": 3000.0,
                                                      "thickness_mm": 900.0})
        self.assertEqual([d.field for d in result.differences], ["length_mm"])

    def test_footings_reconcile_from_workbook_objects(self):
        data, _ = excel_engine.parse_grid(fixture_grids())
        placement = data.footing_placement[0]
        result = reconcile.compare_footing(
            placement, data.footing_type(placement.type_mark),
            {"length_mm": 3200.0, "width_mm": 3000.0, "thickness_mm": 900.0})
        self.assertEqual(result.key, "F1-A1")
        self.assertEqual([d.label for d in result.conflicts], ["Length"])

    def test_columns_reconcile_from_workbook_objects(self):
        data, _ = excel_engine.parse_grid(fixture_grids())
        placement = data.column_placement[0]
        result = reconcile.compare_column(
            placement, data.column_type(placement.type_mark),
            {"width_mm": 300.0, "depth_mm": 600.0, "cover_mm": 30.0})
        self.assertEqual([d.label for d in result.conflicts], ["Cover"])

    def test_rebar_reconciles_from_a_schedule_row(self):
        data, _ = excel_engine.parse_grid(fixture_grids())
        row = data.footing_rebar[0]
        result = reconcile.compare_rebar(
            row, {"diameter_mm": 16.0, "spacing_mm": 250.0, "count": 15})
        self.assertEqual(result.key, "F1 B1")
        self.assertEqual([d.label for d in result.conflicts], ["Spacing"])

    def test_summary_counts_sides_and_decisions(self):
        agreeing = self.compare({"length_mm": 3000.0}, {"length_mm": 3000.0})
        defaulted = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        chosen = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        chosen.use_model()
        summary = reconcile.summarise([agreeing, defaulted, chosen])
        self.assertEqual(summary["compared"], 3)
        self.assertEqual(summary["matching"], 1)
        self.assertEqual(summary["differing"], 2)
        self.assertEqual(summary["using_excel"], 1)
        self.assertEqual(summary["using_model"], 1)
        self.assertEqual(summary["user_decided"], 1)

    def test_differences_are_reported_as_info_not_warnings(self):
        # Disagreeing with the model is the normal reason to run this; grading
        # it as a problem trains people to ignore the colour that means one.
        result = self.compare({"length_mm": 3000.0}, {"length_mm": 3200.0})
        found = reconcile.issues_for([result])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].severity, models.SEVERITY_INFO)
        self.assertIn("using the excel", found[0].message.lower())


class GeometryDeferralTests(unittest.TestCase):
    """Phase 3's rules are recorded but not switched on.

    These pin what the tool does *today* -- report a geometric difference and
    change nothing -- and pin the recorded rule underneath it, so turning
    geometry changes on is a deliberate edit with tests that notice.
    """

    def geometric(self):
        return reconcile.compare("F1-A1", "Footing",
                                 {"length_mm": 3000.0}, {"length_mm": 3200.0})

    def parametric(self):
        return reconcile.compare("F1-A1", "Footing",
                                 {"cover_top_mm": 50.0}, {"cover_top_mm": 40.0})

    def test_geometry_changes_are_deferred(self):
        self.assertTrue(reconcile.GEOMETRY_CHANGES_ARE_DEFERRED)

    def test_a_dimension_difference_is_geometric(self):
        self.assertTrue(self.geometric().conflicts[0].is_geometric)
        self.assertEqual(self.geometric().actionable_conflicts, [])

    def test_a_cover_difference_is_not_geometric(self):
        # Cover is a parameter: resolving it sets a value, it does not rebuild
        # anything, so it is actionable now.
        result = self.parametric()
        self.assertFalse(result.conflicts[0].is_geometric)
        self.assertEqual(len(result.actionable_conflicts), 1)
        self.assertFalse(result.is_report_only)

    def test_every_geometric_difference_reports_only_today(self):
        for has_dependents in (True, False):
            self.assertEqual(reconcile.strategy_for(has_dependents),
                             reconcile.STRATEGY_REPORT_ONLY)
        self.assertTrue(self.geometric().is_report_only)

    def test_the_report_never_implies_a_change_that_did_not_happen(self):
        # "using the schedule" about geometry nothing rewrote is the kind of
        # sentence somebody signs a drawing off against.
        text = self.geometric().describe()
        self.assertIn("Reported only", text)
        self.assertIn("length", text)

    def test_an_agreeing_row_has_no_strategy(self):
        agreeing = reconcile.compare("F1-A1", "Footing",
                                     {"length_mm": 3000.0},
                                     {"length_mm": 3000.0})
        self.assertIsNone(agreeing.strategy())
        self.assertFalse(agreeing.is_report_only)

    def test_the_recorded_rule_is_dependency_driven(self):
        # The phase 3 decision itself: nothing depending on the element means
        # its sketch can be edited in place; dependents mean recreate and move
        # them across instead of deleting first.
        try:
            reconcile.GEOMETRY_CHANGES_ARE_DEFERRED = False
            self.assertEqual(reconcile.strategy_for(False),
                             reconcile.STRATEGY_SKETCH_EDIT)
            self.assertEqual(reconcile.strategy_for(True),
                             reconcile.STRATEGY_RECREATE_AND_REHOST)
            self.assertEqual(self.geometric().strategy(has_dependents=True),
                             reconcile.STRATEGY_RECREATE_AND_REHOST)
        finally:
            reconcile.GEOMETRY_CHANGES_ARE_DEFERRED = True

    def test_every_strategy_has_a_label(self):
        for strategy in reconcile.STRATEGIES:
            self.assertIn(strategy, reconcile.STRATEGY_LABELS)

    def test_summary_counts_what_was_only_reported(self):
        summary = reconcile.summarise([self.geometric(), self.parametric()])
        self.assertEqual(summary["differing"], 2)
        self.assertEqual(summary["report_only"], 1)


# ── the file layer ─────────────────────────────────────────────────────────

try:
    import openpyxl as _openpyxl
except Exception:                       # pragma: no cover - platform dependent
    _openpyxl = None


@unittest.skipIf(_openpyxl is None,
                 "openpyxl not importable — the extension vendors a Windows build")
class ReadGridTests(unittest.TestCase):
    """``read_grid`` is thin, but it is the only thing standing between a real
    workbook and everything else, so its failure modes are worth pinning."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rc_automation_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_workbook(self, grids, name="schedule.xlsx"):
        book = _openpyxl.Workbook()
        book.remove(book.active)
        for sheet_name, rows in grids.items():
            sheet = book.create_sheet(title=sheet_name)
            for row in rows:
                sheet.append(list(row))
        path = os.path.join(self.tmp, name)
        book.save(path)
        return path

    def test_a_real_workbook_round_trips_to_the_same_objects(self):
        # The CSV fixtures and a genuine .xlsx must parse identically, which is
        # what makes testing everything else off a CSV legitimate.
        path = self.write_workbook(fixture_grids())
        data, issues = excel_engine.load(path)
        self.assertEqual(errors(issues), [], messages(issues))
        self.assertEqual(len(data.footing_types), 3)
        self.assertEqual(data.footing_type("F1").length_mm, 3000.0)
        self.assertEqual(data.metadata.get("project"), "Riverside Tower")

    def test_native_excel_types_read_the_same_as_text(self):
        # openpyxl hands back ints and floats where the CSV hands back strings;
        # a shape code of 0 and a count of 15.0 must survive both routes.
        path = self.write_workbook({
            "FOOTING_TYPES": [["UNITS", "mm"],
                              ["TypeMark", "Length", "Width", "Thickness",
                               "CoverTop", "CoverBottom", "CoverSide"],
                              ["F1", 3000, 3000, 900, 50, 75, 50]],
            "FOOTING_REBAR": [["TypeMark", "Layer", "Direction", "Diameter",
                               "Count", "Spacing", "ShapeCode"],
                              ["F1", "B1", "X", 16, 15.0, 200, 0]],
            "COLUMN_TYPES": [["TypeMark", "Width", "Depth", "Cover"],
                             ["C1", 400, 400, 40]],
            "COLUMN_REBAR": [["TypeMark", "BarRole", "Diameter", "Count",
                              "Spacing", "ShapeCode"],
                             ["C1", "Main", 20, 8, None, 0],
                             ["C1", "Tie", 10, None, 200, 51]],
            "FOOTING_PLACEMENT": [["Mark", "TypeMark", "X", "Y", "Level"],
                                  ["F1-A1", "F1", 12500, 8400.5, "Foundation"]],
            "COLUMN_PLACEMENT": [["Mark", "TypeMark", "X", "Y", "BaseLevel",
                                  "TopLevel"],
                                 ["C1-A1", "C1", 12500, 8400.5, "Foundation",
                                  "Level 1"]],
        })
        data, issues = excel_engine.load(path)
        self.assertEqual(errors(issues), [], messages(issues))
        row = data.footing_rebar[0]
        self.assertEqual(row.count, 15)
        self.assertEqual(row.shape_code, "00")
        self.assertEqual(data.column_rebar[1].shape_code, "51")
        # Native numeric coordinates survive the real Excel path.
        self.assertEqual(data.footing_placement[0].x_mm, 12500.0)
        self.assertEqual(data.footing_placement[0].y_mm, 8400.5)

    def test_a_missing_file_is_a_sentence_not_a_traceback(self):
        data, issues = excel_engine.load(os.path.join(self.tmp, "nope.xlsx"))
        self.assertTrue(errors(issues))
        self.assertIn("not found", errors(issues)[0].message)
        self.assertTrue(data.is_empty())

    def test_legacy_xls_says_what_to_do_about_it(self):
        path = os.path.join(self.tmp, "old.xls")
        with io.open(path, "w") as handle:
            handle.write(u"not really a workbook")
        _, issues = excel_engine.load(path)
        self.assertIn("Save As", errors(issues)[0].message)

    def test_a_file_that_is_not_a_workbook_is_refused_by_extension(self):
        _, issues = excel_engine.load(os.path.join(self.tmp, "notes.txt"))
        self.assertTrue(errors(issues))
        self.assertIn("Excel workbook", errors(issues)[0].message)

    def test_no_path_is_refused(self):
        _, issues = excel_engine.load("")
        self.assertTrue(errors(issues))

    def test_a_corrupt_workbook_is_reported_not_raised(self):
        path = os.path.join(self.tmp, "corrupt.xlsx")
        with io.open(path, "w") as handle:
            handle.write(u"PK\x03\x04 and then nonsense")
        _, issues = excel_engine.load(path)
        self.assertTrue(errors(issues), "a corrupt file must not raise")

    def test_reading_does_not_hold_the_file_open(self):
        # read_only workbooks lock the file until closed, which would lock the
        # user out of their own schedule in Excel.
        path = self.write_workbook(fixture_grids())
        excel_engine.load(path)
        os.remove(path)
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()

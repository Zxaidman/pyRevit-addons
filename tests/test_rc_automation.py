# -*- coding: utf-8 -*-
"""Revit-free tests for RC Automation's workbook layer.

Run from the repository root::

    python3 -m unittest discover -s tests -v

Everything under test here reads a schedule and decides whether it can be built.
None of it imports Revit, and only ``excel_engine.read_grid`` -- which is
deliberately not exercised here -- imports openpyxl, because the extension
vendors a Windows build whose numpy will not load on the machine running these.
The seam is the point: ``parse_grid`` takes raw lists of lists, so every rule
below is checked against hand-written rows.
"""

import csv
import importlib.util
import io
import os
import sys
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
    for name in ("FOOTING_TYPES", "FOOTING_REBAR",
                 "COLUMN_TYPES", "COLUMN_REBAR"):
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

    def test_deferred_placement_sheet_is_noted_not_rejected(self):
        grids = minimal_grids()
        grids["FOOTING_PLACEMENT"] = grid("""
Mark,TypeMark,GridX,GridY,Level
F1-A1,F1,A,1,Level 1
""")
        _, issues = excel_engine.parse_grid(grids)
        self.assertEqual(errors(issues), [], messages(issues))
        info = [i for i in issues if i.severity == models.SEVERITY_INFO]
        self.assertTrue(any("FOOTING_PLACEMENT" in i.message for i in info),
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

def validate_grids(**overrides):
    data, parse_issues = excel_engine.parse_grid(minimal_grids(**overrides))
    return data, parse_issues + validation.validate(data)


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


if __name__ == "__main__":
    unittest.main()

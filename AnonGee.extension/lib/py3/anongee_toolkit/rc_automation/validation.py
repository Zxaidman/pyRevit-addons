# -*- coding: utf-8 -*-
"""Decide whether a parsed workbook describes reinforcement that can be built.

:mod:`excel_engine` has already answered "is this a number, is that column
there". This module asks the next question -- does the schedule make sense --
and it runs **before any transaction is opened**, because the cheapest place to
find out that a cover is thicker than the footing is in a grid, not halfway
through writing four hundred elements.

Three severities, and the difference between them is what the user can do next:

``Error``
    Create is blocked. The workbook says something that cannot be built:
    overlapping bars, a footing type nothing references, a cage wider than its
    column.

``Warning``
    Create proceeds. Something is unusual and worth a look -- a footing with no
    bottom steel, a shape code this release cannot build yet, a spacing outside
    the range schedules normally use.

``Info``
    Counts, and decisions taken on the user's behalf.

The plausibility bounds below are **sanity limits, not code compliance**. They
exist to catch a metre typed where a millimetre was meant. Nothing here checks
that reinforcement is adequate for its loads, and the tool must never imply that
it does.
"""

from anongee_toolkit.rc_automation import models
from anongee_toolkit.rc_automation import standards
from anongee_toolkit.rc_automation.models import (
    Issue, SEVERITY_ERROR, SEVERITY_WARNING, SEVERITY_INFO)

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Sanity bounds — a unit typo is the thing being caught, not a design fault
# ---------------------------------------------------------------------------
MIN_PLAN_DIMENSION_MM = 300.0
MAX_PLAN_DIMENSION_MM = 20000.0
MIN_THICKNESS_MM = 100.0
MAX_THICKNESS_MM = 5000.0
MIN_COLUMN_SIDE_MM = 150.0
MAX_COLUMN_SIDE_MM = 5000.0
MIN_COVER_MM = 15.0
MAX_COVER_MM = 150.0
MIN_SPACING_MM = 50.0
MAX_SPACING_MM = 500.0

#: Below this, bars are close enough that placing and compacting concrete around
#: them is a site problem. Flagged, never blocked -- it is a judgement call.
MIN_CLEAR_GAP_MM = 25.0

#: Fewer main bars than this in a column is unusual enough to be worth a look;
#: a rectangular column normally has one in each corner at least.
MIN_MAIN_BARS = 4


def validate(data):
    """Every finding about *data*, errors first.

    Takes a :class:`~models.WorkbookData` and returns a list of
    :class:`~models.Issue`. Pure: no file, no Revit, no model. Whether the marks
    in it match anything in the document is the matching engine's question, not
    this one's.
    """
    issues = []
    if data is None or data.is_empty():
        issues.append(Issue(
            SEVERITY_ERROR,
            "The workbook has no footing or column data to act on."))
        return models.sort_issues(issues)

    _validate_footing_types(data, issues)
    _validate_column_types(data, issues)
    _validate_footing_rebar(data, issues)
    _validate_column_rebar(data, issues)
    _validate_cross_references(data, issues)
    _report_counts(data, issues)
    return models.sort_issues(issues)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _positive(value, name, obj, issues, column=None):
    """True when *value* is a usable positive length; reports it when not."""
    if value is None:
        issues.append(Issue(
            SEVERITY_ERROR, "{0} is required.".format(name),
            sheet=obj.sheet, row=obj.source_row, column=column or name))
        return False
    if value <= 0:
        issues.append(Issue(
            SEVERITY_ERROR,
            "{0} must be greater than zero, found {1:g}.".format(name, value),
            sheet=obj.sheet, row=obj.source_row, column=column or name))
        return False
    return True


def _in_range(value, low, high, name, obj, issues, column=None):
    """Warn when a length is outside the range schedules normally use."""
    if value is None:
        return
    if value < low or value > high:
        issues.append(Issue(
            SEVERITY_WARNING,
            "{0} of {1:g} mm is outside the usual {2:g}–{3:g} mm range. Check "
            "the units.".format(name, value, low, high),
            sheet=obj.sheet, row=obj.source_row, column=column or name))


def _duplicate_marks(objects, issues, label):
    """Report every type mark that appears on more than one row."""
    seen = {}
    for obj in objects:
        seen.setdefault(obj.type_mark, []).append(obj)
    for mark, rows in seen.items():
        if len(rows) > 1:
            first = rows[0].source_row
            for duplicate in rows[1:]:
                issues.append(Issue(
                    SEVERITY_ERROR,
                    "{0} {1!r} is already defined on row {2}. Each type may "
                    "only be described once.".format(label, mark, first),
                    sheet=duplicate.sheet, row=duplicate.source_row,
                    column="TypeMark"))


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

def _validate_footing_types(data, issues):
    footings = data.footing_types
    _duplicate_marks(footings, issues, "Footing type")

    for footing in footings:
        _positive(footing.length_mm, "Length", footing, issues)
        _positive(footing.width_mm, "Width", footing, issues)
        _positive(footing.thickness_mm, "Thickness", footing, issues)
        _in_range(footing.length_mm, MIN_PLAN_DIMENSION_MM,
                  MAX_PLAN_DIMENSION_MM, "Length", footing, issues)
        _in_range(footing.width_mm, MIN_PLAN_DIMENSION_MM,
                  MAX_PLAN_DIMENSION_MM, "Width", footing, issues)
        _in_range(footing.thickness_mm, MIN_THICKNESS_MM, MAX_THICKNESS_MM,
                  "Thickness", footing, issues)

        for value, name in ((footing.cover_top_mm, "CoverTop"),
                            (footing.cover_bottom_mm, "CoverBottom"),
                            (footing.cover_side_mm, "CoverSide")):
            if _positive(value, name, footing, issues):
                _in_range(value, MIN_COVER_MM, MAX_COVER_MM, name, footing,
                          issues)

        # Cover has to leave something to reinforce. Both checks are errors:
        # neither produces a footing, it produces a Revit failure mid-batch.
        top = footing.cover_top_mm
        bottom = footing.cover_bottom_mm
        thickness = footing.thickness_mm
        if None not in (top, bottom, thickness) and top + bottom >= thickness:
            issues.append(Issue(
                SEVERITY_ERROR,
                "Top and bottom cover total {0:g} mm, which is not less than "
                "the {1:g} mm thickness — there is no room for bars.".format(
                    top + bottom, thickness),
                sheet=footing.sheet, row=footing.source_row, column="Thickness"))

        side = footing.cover_side_mm
        plan = [v for v in (footing.length_mm, footing.width_mm) if v]
        if side is not None and plan and 2 * side >= min(plan):
            issues.append(Issue(
                SEVERITY_ERROR,
                "Side cover of {0:g} mm on both faces exceeds the {1:g} mm plan "
                "dimension.".format(side, min(plan)),
                sheet=footing.sheet, row=footing.source_row, column="CoverSide"))


def _validate_column_types(data, issues):
    columns = data.column_types
    _duplicate_marks(columns, issues, "Column type")

    for column in columns:
        _positive(column.width_mm, "Width", column, issues)
        _positive(column.depth_mm, "Depth", column, issues)
        _in_range(column.width_mm, MIN_COLUMN_SIDE_MM, MAX_COLUMN_SIDE_MM,
                  "Width", column, issues)
        _in_range(column.depth_mm, MIN_COLUMN_SIDE_MM, MAX_COLUMN_SIDE_MM,
                  "Depth", column, issues)
        if _positive(column.cover_mm, "Cover", column, issues):
            _in_range(column.cover_mm, MIN_COVER_MM, MAX_COVER_MM, "Cover",
                      column, issues)

        smallest = column.smallest_dimension_mm()
        if column.cover_mm is not None and smallest and 2 * column.cover_mm >= smallest:
            issues.append(Issue(
                SEVERITY_ERROR,
                "Cover of {0:g} mm on both faces exceeds the {1:g} mm section."
                .format(column.cover_mm, smallest),
                sheet=column.sheet, row=column.source_row, column="Cover"))


# ---------------------------------------------------------------------------
# Reinforcement
# ---------------------------------------------------------------------------

def _validate_diameter(row, issues):
    """True when the row names a real bar size."""
    if row.diameter_mm is None:
        issues.append(Issue(
            SEVERITY_ERROR, "Diameter is required.",
            sheet=row.sheet, row=row.source_row, column="Diameter"))
        return False
    if not standards.is_standard_diameter(row.diameter_mm):
        issues.append(Issue(
            SEVERITY_ERROR,
            "{0:g} mm is not a {1} bar size. Use one of: {2}.".format(
                row.diameter_mm, standards.STANDARD_NAME,
                ", ".join(str(d) for d in standards.BAR_DIAMETERS_MM)),
            sheet=row.sheet, row=row.source_row, column="Diameter"))
        return False
    return True


def _validate_shape(row, issues, allow_links, what):
    """Check the shape code exists, suits the role, and can be built yet."""
    code = row.shape_code
    if code is None:
        issues.append(Issue(
            SEVERITY_ERROR, "ShapeCode is required.",
            sheet=row.sheet, row=row.source_row, column="ShapeCode"))
        return
    if code not in standards.KNOWN_SHAPE_CODES:
        issues.append(Issue(
            SEVERITY_ERROR,
            "Shape code {0} is not in {1}.".format(code, standards.STANDARD_NAME),
            sheet=row.sheet, row=row.source_row, column="ShapeCode"))
        return

    is_link = code in standards.LINK_SHAPE_CODES
    if allow_links and not is_link:
        issues.append(Issue(
            SEVERITY_ERROR,
            "A tie must be a closed link — shape {0} is {1}. Use shape {2}."
            .format(code, standards.describe_shape(code),
                    "/".join(standards.LINK_SHAPE_CODES)),
            sheet=row.sheet, row=row.source_row, column="ShapeCode"))
        return
    if not allow_links and is_link:
        issues.append(Issue(
            SEVERITY_ERROR,
            "Shape {0} is a closed link and cannot be used as {1}.".format(
                code, what),
            sheet=row.sheet, row=row.source_row, column="ShapeCode"))
        return

    if code not in standards.SUPPORTED_SHAPE_CODES:
        issues.append(Issue(
            SEVERITY_WARNING,
            "Shape {0} ({1}) is scheduled but this release cannot build its "
            "geometry — the row will be reported and skipped.".format(
                code, standards.describe_shape(code)),
            sheet=row.sheet, row=row.source_row, column="ShapeCode"))


def _validate_quantity(row, issues, require_count=False, require_spacing=False):
    """Count, spacing, and the rule they imply between them."""
    if row.count is not None and row.count <= 0:
        issues.append(Issue(
            SEVERITY_ERROR,
            "Count must be greater than zero, found {0}.".format(row.count),
            sheet=row.sheet, row=row.source_row, column="Count"))
    if row.spacing_mm is not None and row.spacing_mm <= 0:
        issues.append(Issue(
            SEVERITY_ERROR,
            "Spacing must be greater than zero, found {0:g}.".format(
                row.spacing_mm),
            sheet=row.sheet, row=row.source_row, column="Spacing"))

    if require_count and not row.count:
        issues.append(Issue(
            SEVERITY_ERROR,
            "Count is required — the number of bars cannot be derived.",
            sheet=row.sheet, row=row.source_row, column="Count"))
    if require_spacing and not row.spacing_mm:
        issues.append(Issue(
            SEVERITY_ERROR, "Spacing is required.",
            sheet=row.sheet, row=row.source_row, column="Spacing"))

    if not (require_count or require_spacing) and row.layout_rule() is None:
        issues.append(Issue(
            SEVERITY_ERROR,
            "Give a Count, a Spacing, or both — with neither there is nothing "
            "to lay out.",
            sheet=row.sheet, row=row.source_row, column="Spacing"))

    spacing = row.spacing_mm
    diameter = row.diameter_mm
    if spacing and diameter:
        if spacing <= diameter:
            issues.append(Issue(
                SEVERITY_ERROR,
                "Spacing of {0:g} mm is not more than the {1:g} mm bar — the "
                "bars would overlap.".format(spacing, diameter),
                sheet=row.sheet, row=row.source_row, column="Spacing"))
        elif spacing - diameter < MIN_CLEAR_GAP_MM:
            issues.append(Issue(
                SEVERITY_WARNING,
                "Spacing of {0:g} mm leaves only {1:g} mm clear between {2:g} mm "
                "bars.".format(spacing, spacing - diameter, diameter),
                sheet=row.sheet, row=row.source_row, column="Spacing"))
    if spacing:
        _in_range(spacing, MIN_SPACING_MM, MAX_SPACING_MM, "Spacing", row,
                  issues)


def _validate_footing_rebar(data, issues):
    seen = {}
    for row in data.footing_rebar:
        if row.layer not in models.LAYERS:
            issues.append(Issue(
                SEVERITY_ERROR,
                "Layer {0!r} is not one of {1}.".format(
                    row.layer, ", ".join(models.LAYERS)),
                sheet=row.sheet, row=row.source_row, column="Layer"))
        if row.direction not in models.DIRECTIONS:
            issues.append(Issue(
                SEVERITY_ERROR,
                "Direction {0!r} is not one of {1}.".format(
                    row.direction, ", ".join(models.DIRECTIONS)),
                sheet=row.sheet, row=row.source_row, column="Direction"))

        _validate_diameter(row, issues)
        _validate_shape(row, issues, allow_links=False, what="a footing layer")
        _validate_quantity(row, issues)

        # One layer running one way is one row. A second row for the same pair
        # is not extra steel, it is two rows disagreeing about the same bars.
        key = (row.type_mark, row.layer, row.direction)
        if key in seen:
            issues.append(Issue(
                SEVERITY_ERROR,
                "Layer {0} in direction {1} is already described for {2} on "
                "row {3}.".format(row.layer, row.direction, row.type_mark,
                                  seen[key]),
                sheet=row.sheet, row=row.source_row, column="Layer"))
        else:
            seen[key] = row.source_row


def _validate_column_rebar(data, issues):
    tie_rows = {}
    for row in data.column_rebar:
        if row.bar_role not in models.BAR_ROLES:
            issues.append(Issue(
                SEVERITY_ERROR,
                "BarRole {0!r} is not one of {1}.".format(
                    row.bar_role, ", ".join(models.BAR_ROLES)),
                sheet=row.sheet, row=row.source_row, column="BarRole"))
            continue

        _validate_diameter(row, issues)

        if row.is_tie:
            _validate_shape(row, issues, allow_links=True, what="a tie")
            _validate_quantity(row, issues, require_spacing=True)
            # Ties for one column type are one row: a second is ambiguous about
            # which spacing governs.
            if row.type_mark in tie_rows:
                issues.append(Issue(
                    SEVERITY_ERROR,
                    "Ties for {0} are already described on row {1}.".format(
                        row.type_mark, tie_rows[row.type_mark]),
                    sheet=row.sheet, row=row.source_row, column="BarRole"))
            else:
                tie_rows[row.type_mark] = row.source_row
            _validate_confinement(row, issues)
        else:
            _validate_shape(row, issues, allow_links=False,
                            what="a column main bar")
            _validate_quantity(row, issues, require_count=True)
            if row.count and row.count < MIN_MAIN_BARS:
                issues.append(Issue(
                    SEVERITY_WARNING,
                    "{0} main bars is unusual — a rectangular column normally "
                    "has at least one in each corner.".format(row.count),
                    sheet=row.sheet, row=row.source_row, column="Count"))


def _validate_confinement(row, issues):
    """Closer ties at the ends need both a spacing and a length to mean anything."""
    end = row.spacing_end_mm
    length = row.confinement_length_mm
    if end and not length:
        issues.append(Issue(
            SEVERITY_ERROR,
            "SpacingEnd is given without a ConfinementLength, so there is no "
            "zone for it to apply to.",
            sheet=row.sheet, row=row.source_row, column="ConfinementLength"))
    if length and not end:
        issues.append(Issue(
            SEVERITY_ERROR,
            "ConfinementLength is given without a SpacingEnd, so the zone has "
            "no closer spacing to apply.",
            sheet=row.sheet, row=row.source_row, column="SpacingEnd"))
    if end and length and row.spacing_mm and end > row.spacing_mm:
        issues.append(Issue(
            SEVERITY_WARNING,
            "End spacing of {0:g} mm is wider than the {1:g} mm mid-height "
            "spacing — confinement zones are normally tighter, not looser."
            .format(end, row.spacing_mm),
            sheet=row.sheet, row=row.source_row, column="SpacingEnd"))
    if end is not None and end <= 0:
        issues.append(Issue(
            SEVERITY_ERROR,
            "SpacingEnd must be greater than zero, found {0:g}.".format(end),
            sheet=row.sheet, row=row.source_row, column="SpacingEnd"))


# ---------------------------------------------------------------------------
# Across sheets
# ---------------------------------------------------------------------------

def _validate_cross_references(data, issues):
    """Every rebar row must name a type, and every type should have steel."""
    for row in data.footing_rebar:
        if row.type_mark and row.type_mark not in data.footing_type_by_mark:
            issues.append(Issue(
                SEVERITY_ERROR,
                "No footing type {0!r} in {1}.".format(
                    row.type_mark, models.SHEET_FOOTING_TYPES),
                sheet=row.sheet, row=row.source_row, column="TypeMark"))

    for row in data.column_rebar:
        if row.type_mark and row.type_mark not in data.column_type_by_mark:
            issues.append(Issue(
                SEVERITY_ERROR,
                "No column type {0!r} in {1}.".format(
                    row.type_mark, models.SHEET_COLUMN_TYPES),
                sheet=row.sheet, row=row.source_row, column="TypeMark"))

    for mark, footing in data.footing_type_by_mark.items():
        rows = data.footing_rebar_for(mark)
        if not rows:
            issues.append(Issue(
                SEVERITY_WARNING,
                "Footing type {0!r} has no reinforcement scheduled.".format(mark),
                sheet=footing.sheet, row=footing.source_row))
            continue
        if not any(row.is_bottom for row in rows):
            issues.append(Issue(
                SEVERITY_WARNING,
                "Footing type {0!r} has no bottom reinforcement — a pad footing "
                "spans the other way.".format(mark),
                sheet=footing.sheet, row=footing.source_row))

    for mark, column in data.column_type_by_mark.items():
        rows = data.column_rebar_for(mark)
        if not rows:
            issues.append(Issue(
                SEVERITY_WARNING,
                "Column type {0!r} has no reinforcement scheduled.".format(mark),
                sheet=column.sheet, row=column.source_row))
            continue
        mains = [row for row in rows if row.is_main]
        ties = [row for row in rows if row.is_tie]
        if not mains:
            issues.append(Issue(
                SEVERITY_WARNING,
                "Column type {0!r} has ties but no main bars.".format(mark),
                sheet=column.sheet, row=column.source_row))
        if not ties:
            issues.append(Issue(
                SEVERITY_WARNING,
                "Column type {0!r} has main bars but no ties.".format(mark),
                sheet=column.sheet, row=column.source_row))
        _check_cage_fits(column, mains, ties, issues)


def _check_cage_fits(column, mains, ties, issues):
    """The cage has to fit inside the section it is scheduled for.

    Across the narrow face a section spends: cover twice, a tie twice, and a
    main bar twice. If that already exceeds the section there is no arrangement
    that works, whatever the bar count -- so this catches an impossible column
    from the two numbers on the type row plus the two diameters, without
    pretending to know how the bars are arranged.
    """
    smallest = column.smallest_dimension_mm()
    if not smallest or column.cover_mm is None:
        return
    main_dia = max([row.diameter_mm for row in mains if row.diameter_mm] or [0])
    tie_dia = max([row.diameter_mm for row in ties if row.diameter_mm] or [0])
    if not main_dia:
        return
    needed = 2 * (column.cover_mm + tie_dia + main_dia)
    if needed >= smallest:
        issues.append(Issue(
            SEVERITY_ERROR,
            "The cage does not fit {0!r}: {1:g} mm of cover, ties and main bars "
            "across a {2:g} mm section.".format(
                column.type_mark, needed, smallest),
            sheet=column.sheet, row=column.source_row))


def _report_counts(data, issues):
    summary = data.summary()
    issues.append(Issue(
        SEVERITY_INFO,
        "Read {0} footing types with {1} bar rows, and {2} column types with "
        "{3} bar rows.".format(
            summary["footing_types"], summary["footing_rebar"],
            summary["column_types"], summary["column_rebar"])))

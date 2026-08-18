# -*- coding: utf-8 -*-
"""Data objects for the RC Automation workbook.

Everything here is plain Python: no Revit, no WPF, no openpyxl. The workbook can
be parsed, validated and argued with on any machine, which is the whole reason
these live apart from the modules that place rebar.

Two conventions run through the file:

``__slots__`` everywhere
    A schedule row has a fixed shape, and a typo in an attribute name is a bug
    that should fail at the assignment rather than three modules later. It also
    keeps a 500-row workbook cheap.

Millimetres everywhere
    Every length on a DTO is millimetres, already coerced to ``float``. Feet
    appear only where Revit demands them, in the creation layer. Nothing in this
    package ever sees an internal unit.

Rows remember where they came from. ``sheet`` and ``source_row`` are carried on
every DTO so a validation message can name the cell the user has to go and fix,
which is the difference between a report they can act on and one they cannot.
"""

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Severities — the spec's three validation outcomes
# ---------------------------------------------------------------------------
#: Blocks Create. The workbook cannot be acted on until it is fixed.
SEVERITY_ERROR = "Error"
#: Create is allowed. Something is odd and the user should look at it.
SEVERITY_WARNING = "Warning"
#: Neither. Counts, assumptions, and decisions taken on the user's behalf.
SEVERITY_INFO = "Info"

_SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}

# ---------------------------------------------------------------------------
# Sheet names
# ---------------------------------------------------------------------------
SHEET_FOOTING_TYPES = "FOOTING_TYPES"
SHEET_FOOTING_PLACEMENT = "FOOTING_PLACEMENT"
SHEET_FOOTING_REBAR = "FOOTING_REBAR"
SHEET_COLUMN_TYPES = "COLUMN_TYPES"
SHEET_COLUMN_PLACEMENT = "COLUMN_PLACEMENT"
SHEET_COLUMN_REBAR = "COLUMN_REBAR"

#: What P0 reads. The placement sheets are part of the template so the file does
#: not change shape at P1, but nothing in P0 consumes them.
REQUIRED_SHEETS = (
    SHEET_FOOTING_TYPES,
    SHEET_FOOTING_REBAR,
    SHEET_COLUMN_TYPES,
    SHEET_COLUMN_REBAR,
)

#: Defined, accepted, and ignored until structure creation lands.
DEFERRED_SHEETS = (SHEET_FOOTING_PLACEMENT, SHEET_COLUMN_PLACEMENT)

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------
#: Reinforcement layers, outermost first in each face. B1 is the bottom
#: outermost layer, so B2 sits one bar diameter above it -- the order is
#: geometry, not decoration, and the creation layer reads it as such.
LAYER_B1 = "B1"
LAYER_B2 = "B2"
LAYER_T1 = "T1"
LAYER_T2 = "T2"
LAYERS = (LAYER_B1, LAYER_B2, LAYER_T1, LAYER_T2)
BOTTOM_LAYERS = (LAYER_B1, LAYER_B2)
TOP_LAYERS = (LAYER_T1, LAYER_T2)

#: Model axes. A footing layer runs along one of them.
DIRECTIONS = ("X", "Y")

#: What a column bar is for.
ROLE_MAIN = "Main"
ROLE_TIE = "Tie"
BAR_ROLES = (ROLE_MAIN, ROLE_TIE)

# ---------------------------------------------------------------------------
# Revit layout rules
# ---------------------------------------------------------------------------
# Which of these applies is decided by what the workbook supplies, not by a
# column the user has to fill in -- a schedule says "12 T16 @ 200" or "T16 @ 200"
# and means something different by each.
LAYOUT_FIXED_NUMBER = "FixedNumber"
LAYOUT_MAXIMUM_SPACING = "MaximumSpacing"
LAYOUT_NUMBER_WITH_SPACING = "NumberWithSpacing"


class Issue(object):
    """One validation finding, addressed to a cell where it can be.

    ``row`` is the spreadsheet row number the user sees in Excel, 1-based and
    counting the header, so it can be typed straight into the Name Box.
    """

    __slots__ = ("severity", "message", "sheet", "row", "column")

    def __init__(self, severity, message, sheet=None, row=None, column=None):
        self.severity = severity
        self.message = message
        self.sheet = sheet
        self.row = row
        self.column = column

    @property
    def is_error(self):
        return self.severity == SEVERITY_ERROR

    def location(self):
        """"FOOTING_REBAR row 7 · Diameter", or as much of it as is known."""
        parts = []
        if self.sheet:
            parts.append(self.sheet)
        if self.row is not None:
            parts.append("row {0}".format(self.row))
        text = " ".join(parts)
        if self.column:
            text = "{0} · {1}".format(text, self.column) if text else self.column
        return text

    def __str__(self):
        where = self.location()
        return "{0} — {1}".format(where, self.message) if where else self.message

    def __repr__(self):
        return "<Issue {0}: {1}>".format(self.severity, self)


def sort_issues(issues):
    """Errors first, then warnings, then info; original order kept within each.

    Stable on purpose: inside one severity the sheet-then-row order the parser
    produced is already the order the user will work through the file.
    """
    return sorted(issues, key=lambda issue: _SEVERITY_ORDER.get(issue.severity, 9))


def count_by_severity(issues):
    """``{severity: n}`` for every severity, including the ones at zero."""
    counts = dict((name, 0) for name in _SEVERITY_ORDER)
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return counts


def has_errors(issues):
    return any(issue.is_error for issue in issues)


class FootingType(object):
    """A row of FOOTING_TYPES: one footing type, however many are placed.

    ``length_mm`` and ``width_mm`` describe the rectangular case and are what a
    schedule states. They do not constrain creation -- a footing is a floor with
    a sketched outline, so an arbitrary shape is legal and the real extents come
    from the host. They are kept because they are what the matching engine
    compares against when deciding CONFLICT.
    """

    __slots__ = ("type_mark", "length_mm", "width_mm", "thickness_mm",
                 "cover_top_mm", "cover_bottom_mm", "cover_side_mm",
                 "concrete", "comments", "sheet", "source_row")

    def __init__(self, type_mark, length_mm=None, width_mm=None,
                 thickness_mm=None, cover_top_mm=None, cover_bottom_mm=None,
                 cover_side_mm=None, concrete="", comments="",
                 sheet=SHEET_FOOTING_TYPES, source_row=None):
        self.type_mark = type_mark
        self.length_mm = length_mm
        self.width_mm = width_mm
        self.thickness_mm = thickness_mm
        self.cover_top_mm = cover_top_mm
        self.cover_bottom_mm = cover_bottom_mm
        self.cover_side_mm = cover_side_mm
        self.concrete = concrete
        self.comments = comments
        self.sheet = sheet
        self.source_row = source_row

    def smallest_dimension_mm(self):
        """The tightest plan or depth dimension -- what cover has to fit inside."""
        known = [v for v in (self.length_mm, self.width_mm, self.thickness_mm)
                 if v is not None]
        return min(known) if known else None

    def __repr__(self):
        return "<FootingType {0}>".format(self.type_mark)


class ColumnType(object):
    """A row of COLUMN_TYPES: the cross-section, and the cover bars sit inside."""

    __slots__ = ("type_mark", "width_mm", "depth_mm", "cover_mm",
                 "concrete", "comments", "sheet", "source_row")

    def __init__(self, type_mark, width_mm=None, depth_mm=None, cover_mm=None,
                 concrete="", comments="", sheet=SHEET_COLUMN_TYPES,
                 source_row=None):
        self.type_mark = type_mark
        self.width_mm = width_mm
        self.depth_mm = depth_mm
        self.cover_mm = cover_mm
        self.concrete = concrete
        self.comments = comments
        self.sheet = sheet
        self.source_row = source_row

    def smallest_dimension_mm(self):
        known = [v for v in (self.width_mm, self.depth_mm) if v is not None]
        return min(known) if known else None

    def __repr__(self):
        return "<ColumnType {0}>".format(self.type_mark)


class _RebarRow(object):
    """What FOOTING_REBAR and COLUMN_REBAR rows have in common."""

    __slots__ = ()

    def layout_rule(self):
        """Which Revit layout rule this row's numbers imply.

        The workbook does not carry a LayoutRule column because a schedule never
        does; what it carries is a count, a spacing, or both, and each of those
        means a different rule:

        ==================  ==========================================
        Workbook says       Rule
        ==================  ==========================================
        count and spacing   NumberWithSpacing -- both are honoured
        count only          FixedNumber -- spread across the run
        spacing only        MaximumSpacing -- Revit derives the count
        neither             ``None``; validation has already failed it
        ==================  ==========================================
        """
        if self.count and self.spacing_mm:
            return LAYOUT_NUMBER_WITH_SPACING
        if self.count:
            return LAYOUT_FIXED_NUMBER
        if self.spacing_mm:
            return LAYOUT_MAXIMUM_SPACING
        return None


class FootingRebarRow(_RebarRow):
    """One layer of reinforcement in one footing type, running one way."""

    __slots__ = ("type_mark", "layer", "direction", "bar_type", "diameter_mm",
                 "count", "spacing_mm", "shape_code", "end_cover_mm",
                 "comments", "sheet", "source_row")

    def __init__(self, type_mark, layer=None, direction=None, bar_type="",
                 diameter_mm=None, count=None, spacing_mm=None, shape_code=None,
                 end_cover_mm=None, comments="", sheet=SHEET_FOOTING_REBAR,
                 source_row=None):
        self.type_mark = type_mark
        self.layer = layer
        self.direction = direction
        self.bar_type = bar_type
        self.diameter_mm = diameter_mm
        self.count = count
        self.spacing_mm = spacing_mm
        self.shape_code = shape_code
        self.end_cover_mm = end_cover_mm
        self.comments = comments
        self.sheet = sheet
        self.source_row = source_row

    @property
    def is_bottom(self):
        return self.layer in BOTTOM_LAYERS

    @property
    def is_top(self):
        return self.layer in TOP_LAYERS

    def layer_index(self):
        """0 for the outermost layer of a face, 1 for the one behind it.

        The creation layer turns this into a z-offset of ``index * diameter``:
        B2 sits one bar above B1, T2 one bar below T1.
        """
        if self.layer in (LAYER_B1, LAYER_T1):
            return 0
        if self.layer in (LAYER_B2, LAYER_T2):
            return 1
        return None

    def __repr__(self):
        return "<FootingRebarRow {0} {1}-{2}>".format(
            self.type_mark, self.layer, self.direction)


class ColumnRebarRow(_RebarRow):
    """One bar set in one column type -- a main-bar group, or the ties.

    Two ``Main`` rows for one column type is normal and expected: a real schedule
    reads "4T20 corners + 6T16 faces", which is two diameters and two counts.
    """

    __slots__ = ("type_mark", "bar_role", "bar_type", "diameter_mm", "count",
                 "spacing_mm", "shape_code", "spacing_end_mm",
                 "confinement_length_mm", "comments", "sheet", "source_row")

    def __init__(self, type_mark, bar_role=None, bar_type="", diameter_mm=None,
                 count=None, spacing_mm=None, shape_code=None,
                 spacing_end_mm=None, confinement_length_mm=None, comments="",
                 sheet=SHEET_COLUMN_REBAR, source_row=None):
        self.type_mark = type_mark
        self.bar_role = bar_role
        self.bar_type = bar_type
        self.diameter_mm = diameter_mm
        self.count = count
        self.spacing_mm = spacing_mm
        self.shape_code = shape_code
        self.spacing_end_mm = spacing_end_mm
        self.confinement_length_mm = confinement_length_mm
        self.comments = comments
        self.sheet = sheet
        self.source_row = source_row

    @property
    def is_tie(self):
        return self.bar_role == ROLE_TIE

    @property
    def is_main(self):
        return self.bar_role == ROLE_MAIN

    @property
    def has_confinement(self):
        """True when the row asks for closer ties at the column ends.

        Both halves are needed to mean anything -- a closer spacing with no
        length says nothing about where it stops -- so validation rejects one
        without the other and this stays a simple conjunction.
        """
        return bool(self.spacing_end_mm and self.confinement_length_mm)

    def __repr__(self):
        return "<ColumnRebarRow {0} {1}>".format(self.type_mark, self.bar_role)


class WorkbookData(object):
    """Everything P0 reads out of one workbook.

    The **lists** are the source of truth and keep every row the sheet had,
    duplicates included. The ``*_by_mark`` dicts are a lookup built beside them,
    first definition winning.

    That split is not tidiness. Keying the rows straight into a dict as they were
    parsed silently discarded the second row of a duplicated type mark, which
    meant the validator could never see the duplicate it was written to reject:
    the evidence was destroyed before it was asked for. Anything that counts,
    reports or validates reads the lists; only lookups touch the dicts.
    """

    __slots__ = ("path", "units", "footing_types", "column_types",
                 "footing_type_by_mark", "column_type_by_mark",
                 "footing_rebar", "column_rebar", "metadata", "sheets_present")

    def __init__(self, path=None, units=None, footing_types=None,
                 column_types=None, footing_rebar=None, column_rebar=None,
                 metadata=None, sheets_present=None):
        self.path = path
        self.units = units
        self.footing_types = list(footing_types or ())
        self.column_types = list(column_types or ())
        self.footing_rebar = list(footing_rebar or ())
        self.column_rebar = list(column_rebar or ())
        self.footing_type_by_mark = _first_by_mark(self.footing_types)
        self.column_type_by_mark = _first_by_mark(self.column_types)
        self.metadata = metadata if metadata is not None else {}
        self.sheets_present = tuple(sheets_present or ())

    def footing_type(self, type_mark):
        return self.footing_type_by_mark.get(type_mark)

    def column_type(self, type_mark):
        return self.column_type_by_mark.get(type_mark)

    def footing_rebar_for(self, type_mark):
        return [row for row in self.footing_rebar if row.type_mark == type_mark]

    def column_rebar_for(self, type_mark):
        return [row for row in self.column_rebar if row.type_mark == type_mark]

    def is_empty(self):
        return not (self.footing_types or self.column_types
                    or self.footing_rebar or self.column_rebar)

    def summary(self):
        """Counts for the execution log, in the order the log reads best."""
        return {
            "footing_types": len(self.footing_types),
            "footing_rebar": len(self.footing_rebar),
            "column_types": len(self.column_types),
            "column_rebar": len(self.column_rebar),
        }

    def __repr__(self):
        s = self.summary()
        return ("<WorkbookData {0} footing types / {1} footing bars, "
                "{2} column types / {3} column bars>".format(
                    s["footing_types"], s["footing_rebar"],
                    s["column_types"], s["column_rebar"]))


def _first_by_mark(objects):
    """``{type_mark: object}``, the first definition of each mark winning.

    A repeated mark is an Error the validator raises from the list. Until the
    user fixes it, the first row is the one anything else acts on -- the one
    they will find at the top of the sheet.
    """
    lookup = {}
    for obj in objects:
        if obj.type_mark and obj.type_mark not in lookup:
            lookup[obj.type_mark] = obj
    return lookup

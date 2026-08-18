# -*- coding: utf-8 -*-
"""Compare what the model holds against what the schedule says, field by field.

When an element already exists, the workbook stops being an instruction and
becomes a second opinion. The two can disagree -- a footing modelled 3200 wide
against a schedule that says 3000 -- and *somebody has to choose*. This module
works out exactly where they differ and carries the choice; it does not make it,
and it never touches Revit.

**Excel wins by default.** The schedule is the controlled document and the model
is usually the thing that drifted, so an untouched row resolves to the workbook.
The user can flip any row to the model, per row, and the flip is data on the
:class:`Reconciliation` rather than a branch anywhere else -- everything
downstream asks :meth:`Reconciliation.resolved` and gets a number, without
knowing or caring which side won it.

The model side arrives as a plain ``{field: number}`` dict measured on Revit's
thread and marshalled across as scalars, never as elements (§12.8.7.2). That is
what keeps this module pure and testable, and it is why it compares dicts rather
than reading anything itself.
"""

from anongee_toolkit.rc_automation import models

__version__ = "0.1.0"

#: Which side of a disagreement is used. Excel is the default everywhere.
SOURCE_EXCEL = "Excel"
SOURCE_MODEL = "Model"
SOURCES = (SOURCE_EXCEL, SOURCE_MODEL)

#: How far apart two lengths may be and still count as the same. A footing
#: sketched at 3000.4 mm is a 3000 mm footing; the toolkit already rounds to the
#: nearest millimetre, so anything under half of one is noise from unit
#: conversion rather than a real difference.
DEFAULT_TOLERANCE_MM = 0.5

#: Bar counts and diameters are exact. "About 12 bars" is not a thing.
EXACT_FIELDS = ("count", "diameter_mm")

#: What each field is called in the grid, so a difference reads as a sentence
#: rather than an attribute name.
FIELD_LABELS = {
    "length_mm": "Length",
    "width_mm": "Width",
    "thickness_mm": "Thickness",
    "depth_mm": "Depth",
    "cover_mm": "Cover",
    "cover_top_mm": "Top cover",
    "cover_bottom_mm": "Bottom cover",
    "cover_side_mm": "Side cover",
    "diameter_mm": "Diameter",
    "spacing_mm": "Spacing",
    "count": "Count",
    "rotation_deg": "Rotation",
}


def label_for(field):
    return FIELD_LABELS.get(field, field)


class Difference(object):
    """One field where the workbook and the model do not agree.

    ``model_value`` of ``None`` means the model has nothing to say about the
    field -- the parameter is absent or unreadable -- which is not a
    disagreement, and is why :attr:`differs` is False for it. Silently treating
    "unknown" as "zero" would report every unmapped parameter as a conflict and
    bury the real ones.
    """

    __slots__ = ("field", "excel_value", "model_value", "tolerance", "differs")

    def __init__(self, field, excel_value, model_value, tolerance):
        self.field = field
        self.excel_value = excel_value
        self.model_value = model_value
        self.tolerance = tolerance
        self.differs = _differs(excel_value, model_value, tolerance)

    @property
    def label(self):
        return label_for(self.field)

    def describe(self):
        """"Length: 3000 in the schedule, 3200 in the model"."""
        return "{0}: {1} in the schedule, {2} in the model".format(
            self.label, _format(self.excel_value), _format(self.model_value))

    def __repr__(self):
        return "<Difference {0} {1}>".format(
            self.field, "differs" if self.differs else "agrees")


def _format(value):
    if value is None:
        return "—"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    if isinstance(value, float):
        return "{0:g}".format(value)
    return str(value)


def _differs(excel_value, model_value, tolerance):
    """True only when both sides have a value and those values disagree."""
    if excel_value is None or model_value is None:
        return False
    try:
        return abs(float(excel_value) - float(model_value)) > tolerance
    except (TypeError, ValueError):
        return str(excel_value).strip() != str(model_value).strip()


class Reconciliation(object):
    """One element's worth of comparison, and the choice of which side wins.

    Built by :func:`compare`. The chosen source starts at Excel and only moves
    because the user moved it, which :attr:`is_user_choice` records -- a report
    that cannot tell a default from a decision is not much of an audit trail.
    """

    __slots__ = ("key", "category", "differences", "source", "is_user_choice")

    def __init__(self, key, category, differences, source=SOURCE_EXCEL,
                 is_user_choice=False):
        self.key = key
        self.category = category
        self.differences = list(differences or ())
        self.source = source
        self.is_user_choice = is_user_choice

    # -- state ------------------------------------------------------------
    @property
    def conflicts(self):
        """Only the fields that actually disagree."""
        return [d for d in self.differences if d.differs]

    @property
    def agrees(self):
        return not self.conflicts

    @property
    def field_count(self):
        return len(self.conflicts)

    # -- the choice -------------------------------------------------------
    def choose(self, source):
        """Pick a side. Anything but a known source is refused, not guessed."""
        if source not in SOURCES:
            raise ValueError(
                "source must be one of {0}, got {1!r}".format(SOURCES, source))
        self.source = source
        self.is_user_choice = True
        return self

    def use_excel(self):
        return self.choose(SOURCE_EXCEL)

    def use_model(self):
        return self.choose(SOURCE_MODEL)

    def resolved(self, field):
        """The value to build with, given the side currently chosen.

        Falls back to the other side when the chosen one has nothing: choosing
        the model does not mean discarding a schedule value the model never
        held, it means preferring the model where the model has an opinion.
        """
        for difference in self.differences:
            if difference.field != field:
                continue
            if self.source == SOURCE_MODEL:
                return (difference.model_value if difference.model_value
                        is not None else difference.excel_value)
            return (difference.excel_value if difference.excel_value
                    is not None else difference.model_value)
        return None

    def resolved_values(self):
        """``{field: value}`` for every compared field."""
        return dict((d.field, self.resolved(d.field)) for d in self.differences)

    def describe(self):
        if self.agrees:
            return "{0} matches the schedule.".format(self.key)
        return "{0}: {1} — using the {2}.".format(
            self.key,
            "; ".join(d.describe() for d in self.conflicts),
            self.source.lower())

    def __repr__(self):
        return "<Reconciliation {0} {1} conflict(s) source={2}>".format(
            self.key, self.field_count, self.source)


def compare(key, category, excel_values, model_values, fields=None,
            tolerance=DEFAULT_TOLERANCE_MM):
    """Build a :class:`Reconciliation` for one element.

    Args:
        key: how the row is named in the grid -- usually the element's mark.
        category: "Footing" or "Column", for grouping and messages.
        excel_values (dict): ``{field: value}`` from the workbook.
        model_values (dict): ``{field: value}`` measured from the element.
        fields: which fields to compare, in grid order. Defaults to the
            workbook's own keys, so a field the schedule does not mention is not
            invented as a difference.
        tolerance (float): millimetres, for everything except the exact fields.

    Only fields present in *excel_values* are compared by default. A model that
    carries a parameter the schedule says nothing about is not in disagreement
    with it -- it is simply better informed.
    """
    excel_values = excel_values or {}
    model_values = model_values or {}
    if fields is None:
        fields = [f for f in FIELD_LABELS if f in excel_values]
        fields += [f for f in excel_values if f not in FIELD_LABELS]

    differences = [
        Difference(field, excel_values.get(field), model_values.get(field),
                   0.0 if field in EXACT_FIELDS else tolerance)
        for field in fields
    ]
    return Reconciliation(key, category, differences)


def compare_footing(placement, footing_type, model_values, tolerance=None):
    """Reconcile one placed footing against the element found for it."""
    excel_values = {
        "length_mm": footing_type.length_mm if footing_type else None,
        "width_mm": footing_type.width_mm if footing_type else None,
        "thickness_mm": footing_type.thickness_mm if footing_type else None,
        "cover_top_mm": footing_type.cover_top_mm if footing_type else None,
        "cover_bottom_mm": footing_type.cover_bottom_mm if footing_type else None,
        "cover_side_mm": footing_type.cover_side_mm if footing_type else None,
        "rotation_deg": placement.rotation_deg if placement else None,
    }
    key = placement.mark if placement else (
        footing_type.type_mark if footing_type else "?")
    return compare(key, "Footing", excel_values, model_values,
                   tolerance=DEFAULT_TOLERANCE_MM if tolerance is None
                   else tolerance)


def compare_column(placement, column_type, model_values, tolerance=None):
    """Reconcile one placed column against the element found for it."""
    excel_values = {
        "width_mm": column_type.width_mm if column_type else None,
        "depth_mm": column_type.depth_mm if column_type else None,
        "cover_mm": column_type.cover_mm if column_type else None,
        "rotation_deg": placement.rotation_deg if placement else None,
    }
    key = placement.mark if placement else (
        column_type.type_mark if column_type else "?")
    return compare(key, "Column", excel_values, model_values,
                   tolerance=DEFAULT_TOLERANCE_MM if tolerance is None
                   else tolerance)


def compare_rebar(row, model_values, tolerance=None):
    """Reconcile one scheduled bar set against the bars found on the host."""
    excel_values = {
        "diameter_mm": row.diameter_mm,
        "spacing_mm": row.spacing_mm,
        "count": row.count,
    }
    key = "{0} {1}".format(
        row.type_mark,
        getattr(row, "layer", None) or getattr(row, "bar_role", "") or "")
    return compare(key.strip(), "Rebar", excel_values, model_values,
                   tolerance=DEFAULT_TOLERANCE_MM if tolerance is None
                   else tolerance)


def summarise(reconciliations):
    """Counts for the execution log and the report header."""
    items = list(reconciliations or ())
    conflicted = [r for r in items if r.conflicts]
    return {
        "compared": len(items),
        "matching": len(items) - len(conflicted),
        "differing": len(conflicted),
        "using_excel": len([r for r in conflicted
                            if r.source == SOURCE_EXCEL]),
        "using_model": len([r for r in conflicted
                            if r.source == SOURCE_MODEL]),
        "user_decided": len([r for r in conflicted if r.is_user_choice]),
    }


def issues_for(reconciliations):
    """One Info per differing element, so the report carries the decisions.

    Differences are not warnings. A model that disagrees with its schedule is
    the normal reason to run this at all, and grading it as a problem would
    train people to ignore the colour that means something is actually wrong.
    """
    found = []
    for reconciliation in reconciliations or ():
        if reconciliation.conflicts:
            found.append(models.Issue(
                models.SEVERITY_INFO, reconciliation.describe()))
    return found

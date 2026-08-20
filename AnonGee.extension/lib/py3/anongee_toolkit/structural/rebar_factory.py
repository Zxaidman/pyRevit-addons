# -*- coding: utf-8 -*-
"""Place reinforcement. The only module here that writes, and it says so.

Everything upstream decided what the bars are; this is where they become
``Rebar`` elements. Two things about it matter more than the API calls.

**It never opens a transaction.** Every function assumes a transaction the
caller owns and is already inside. That is not laziness -- a run places
thousands of bars in chunks inside one ``TransactionGroup``, and a module that
opened its own would either nest them or hand the user a thousand undo steps.

**A set is one element, and that is the whole performance story.** A layer of
thirty identical bars placed as thirty ``Rebar`` elements is thirty elements;
placed as one with a layout rule it is one, and the schedule reads the same
either way because BBS Generator takes its quantity from
``REBAR_ELEM_QUANTITY_OF_BARS``. Which is why ``rebar_spec`` works out whether a
run is uniform, and why :func:`place_layer` asks it rather than assuming.

Failures come back as results, never as exceptions. One bad bar in four hundred
should cost that bar and a line in the report, not the run.
"""

from Autodesk.Revit.DB import BuiltInParameter
from Autodesk.Revit.DB import ElementId
from Autodesk.Revit.DB.Structure import Rebar
from Autodesk.Revit.DB.Structure import RebarBarType
from Autodesk.Revit.DB.Structure import RebarCoverType
from Autodesk.Revit.DB.Structure import RebarHookOrientation
from Autodesk.Revit.DB.Structure import RebarStyle

from anongee_toolkit.rc_automation import rebar_spec
from anongee_toolkit.revit.units import mm_to_ft
from anongee_toolkit.structural import rebar_types
from anongee_toolkit.structural import rebar_geometry

__version__ = "0.1.0"

#: Set on every bar this tool places, so a later run can tell its own work from
#: a detailer's. Phase 3 replaces only what it made and leaves hand-added bars
#: alone, which it can only do if they are marked at the time of placing.
STAMP_PARAMETER = "Comments"
STAMP_TEXT = "AnonGee RC Automation"


class PlacementResult(object):
    """What one attempt produced: the ids, and why anything is missing."""

    __slots__ = ("created", "skipped", "errors", "bars", "elements",
                 "constrained", "constraint_notes")

    def __init__(self):
        self.created = []
        self.skipped = []
        self.errors = []
        self.bars = 0
        self.elements = 0
        #: Handles tied to the host's cover. Counted rather than assumed,
        #: because a constraint that could not be made costs the automatic
        #: updating and nothing else.
        self.constrained = 0
        self.constraint_notes = []

    def merge(self, other):
        self.created.extend(other.created)
        self.skipped.extend(other.skipped)
        self.errors.extend(other.errors)
        self.bars += other.bars
        self.elements += other.elements
        self.constrained += other.constrained
        for note in other.constraint_notes:
            if note not in self.constraint_notes:
                self.constraint_notes.append(note)
        return self

    @property
    def ok(self):
        return not self.errors

    def __repr__(self):
        return "<PlacementResult {0} element(s), {1} bar(s), {2} error(s)>"\
            .format(self.elements, self.bars, len(self.errors))


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------
#: What a cover type this tool has to invent is called, per face. Named for the
#: element and the face rather than the number, because that is how a project
#: names them -- "FOOTING BOTTOM", not "RC 75 mm" -- and a schedule full of
#: RC-something tells a reader nothing about where it applies.
COVER_TYPE_NAMES = {
    "top": "FOOTING TOP",
    "bottom": "FOOTING BOTTOM",
    "side": "FOOTING ALL SIDE",
}


def ensure_cover_type(doc, cover_mm, face="side", cache=None):
    """A ``RebarCoverType`` of this distance, matched or created once.

    Cover in Revit is an element reference, not a number, which is what turns
    "50 mm cover" into something that can simply be absent from a project.

    *cache* is not an optimisation. A type created inside an open transaction is
    not visible to a fresh ``FilteredElementCollector`` until the document
    regenerates, so without it the second and third face each create another
    50 mm type -- which is exactly what a real run produced: three identical
    cover types, none of them used.

    ``(ElementId, created)``. Requires a transaction when it has to create.
    """
    if not cover_mm:
        return None, False
    cache = cache if cache is not None else {}
    key = int(round(cover_mm))
    if key in cache:
        return cache[key], False

    existing = rebar_types.match_cover_type(doc, cover_mm)
    if existing is not None:
        cache[key] = existing
        return existing, False

    try:
        cover_type = RebarCoverType.Create(
            doc, COVER_TYPE_NAMES.get(face, "RC COVER {0}".format(key)),
            mm_to_ft(cover_mm))
        cache[key] = cover_type.Id
        return cover_type.Id, True
    except Exception:
        return None, False


#: Which host parameter holds which face's cover, when the host data route is
#: not available. Floors and foundations carry three; most other categories
#: carry one, so the fallback matters.
_COVER_PARAMETERS = {
    "top": (BuiltInParameter.CLEAR_COVER_TOP, BuiltInParameter.CLEAR_COVER),
    "bottom": (BuiltInParameter.CLEAR_COVER_BOTTOM,
               BuiltInParameter.CLEAR_COVER),
    "side": (BuiltInParameter.CLEAR_COVER_OTHER, BuiltInParameter.CLEAR_COVER),
}


def _set_cover_parameter(host, face, cover_id):
    """Write one face's cover, host data first, built-in parameter second.

    ``RebarHostData.SetCoverType`` is the route that works for a floor, a wall
    and a family instance alike; the parameters are the fallback for a build or
    a category where it does not.
    """
    try:
        from Autodesk.Revit.DB.Structure import RebarHostData
        from Autodesk.Revit.DB.Structure import RebarCoverFaceType
        host_data = RebarHostData.GetRebarHostData(host)
        if host_data is not None:
            face_type = {"top": "Top", "bottom": "Bottom",
                         "side": "Other"}.get(face)
            enum_value = getattr(RebarCoverFaceType, face_type or "", None)
            if enum_value is not None:
                host_data.SetCoverType(enum_value, cover_id)
                return True
    except Exception:
        pass

    for builtin in _COVER_PARAMETERS[face]:
        try:
            parameter = host.get_Parameter(builtin)
        except Exception:
            parameter = None
        if parameter is not None and not parameter.IsReadOnly:
            try:
                parameter.Set(cover_id)
                return True
            except Exception:
                continue
    return False


def set_host_cover(doc, host, top_mm=None, bottom_mm=None, side_mm=None,
                   cache=None):
    """Write the scheduled cover onto the element itself.

    So the model carries the number, not just the bars: reinforcement
    constrained to cover has something real to follow, and anyone opening the
    footing sees what it was detailed to rather than measuring a bar.

    ``(applied, created, notes)``. Requires a transaction.
    """
    cache = cache if cache is not None else {}
    applied = []
    created = []
    notes = []
    for face, value in (("top", top_mm), ("bottom", bottom_mm),
                        ("side", side_mm)):
        if not value:
            continue
        cover_id, was_created = ensure_cover_type(doc, value, face, cache)
        if cover_id is None:
            notes.append("no cover type for {0:g} mm ({1})".format(value, face))
            continue
        if was_created:
            created.append("{0} ({1:g} mm)".format(
                COVER_TYPE_NAMES.get(face, "cover"), value))
        if _set_cover_parameter(host, face, cover_id):
            applied.append(face)
        else:
            notes.append("{0} cover could not be applied to the element"
                         .format(face))
    return applied, created, notes


def _style_for(bar):
    """A closed link is a StirrupTie; everything else is Standard.

    Revit uses the style for hook defaults and for how the bar is scheduled, so
    getting it wrong gives a tie that behaves like a straight bar.
    """
    return (RebarStyle.StirrupTie if bar.role == rebar_spec.ROLE_COLUMN_TIE
            else RebarStyle.Standard)


def _stamp(rebar):
    """Mark the bar as this tool's work. Best effort — never fail a bar for it."""
    try:
        parameter = rebar.LookupParameter(STAMP_PARAMETER)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(STAMP_TEXT)
    except Exception:
        pass


def show_in_view(rebar, view, solid=True, unobscured=True):
    """Make the bar visible the way a detailer expects to find it.

    Step five of the manual workflow is turning obscured rebar **on**, so the
    steel reads through the concrete instead of disappearing into it. The first
    version of this set both flags to ``False`` — hiding every bar it had just
    placed, which is the opposite of the intent and a good way to conclude that
    nothing was created.

    Revit stores both flags **per view**, so this is what the active view sees;
    other views keep their own answer.
    """
    if view is None:
        return False
    applied = False
    try:
        rebar.SetSolidInView(view, bool(solid))
        applied = True
    except Exception:
        pass
    try:
        rebar.SetUnobscuredInView(view, bool(unobscured))
        applied = True
    except Exception:
        pass
    return applied


def create_bar(doc, host, bar, bar_type_id, origin_ft=None, rotation_deg=0.0,
               start_hook_id=None, end_hook_id=None, view=None,
               array_vector=None):
    """One ``Rebar`` from one :class:`~rc_automation.rebar_spec.BarSpec`.

    Must run inside a transaction the caller opened. Returns the new element or
    raises -- callers above turn that into a reported row.
    """
    curves, skipped = rebar_geometry.line_curves(bar, origin_ft, rotation_deg)
    if curves.Count == 0:
        raise ValueError("bar has no usable segments")

    bar_type = doc.GetElement(bar_type_id)
    if not isinstance(bar_type, RebarBarType):
        raise ValueError("bar type could not be resolved")

    normal = rebar_geometry.normal_for(
        bar, rotation_deg,
        fallback=array_vector if array_vector else (0.0, 0.0, 1.0))

    rebar = Rebar.CreateFromCurves(
        doc,
        _style_for(bar),
        bar_type,
        _element(doc, start_hook_id),
        _element(doc, end_hook_id),
        host,
        normal,
        curves,
        RebarHookOrientation.Right,
        RebarHookOrientation.Right,
        True,      # reuse a matching shape rather than multiplying near-copies
        True,      # but let Revit add one when nothing matches
    )
    _stamp(rebar)
    show_in_view(rebar, view)
    return rebar, skipped


def _element(doc, element_id):
    """An element from an id, treating ``None`` and Invalid alike as "no hook"."""
    if element_id is None or element_id == ElementId.InvalidElementId:
        return None
    return doc.GetElement(element_id)


def apply_layout(rebar, bar_set):
    """Turn one placed bar into the whole run, using the schedule's own rule.

    Which rule applies was decided from what the workbook supplied -- a count, a
    spacing, or both -- back in ``models``. Revit distributes along the normal
    handed to ``CreateFromCurves``, which is why the array vector had to be the
    normal and not a free choice.
    """
    accessor = rebar.GetShapeDrivenAccessor()
    count = max(1, int(bar_set.count or 1))
    spacing_ft = mm_to_ft(bar_set.spacing_mm or 0.0)
    length_ft = mm_to_ft(bar_set.array_length_mm or 0.0)

    from anongee_toolkit.rc_automation import models
    rule = bar_set.layout_rule

    if rule == models.LAYOUT_NUMBER_WITH_SPACING and spacing_ft > 0:
        accessor.SetLayoutAsNumberWithSpacing(count, spacing_ft, True, True, True)
    elif rule == models.LAYOUT_MAXIMUM_SPACING and spacing_ft > 0 and length_ft > 0:
        accessor.SetLayoutAsMaximumSpacing(spacing_ft, length_ft, True, True, True)
    elif length_ft > 0:
        accessor.SetLayoutAsFixedNumber(count, length_ft, True, True, True)
    else:
        # Nothing to array along: leave it as the single bar it already is
        # rather than asking Revit for a zero-length run.
        return False
    return True


def _constrain(doc, host, result, varying=False):
    """Tie what was just placed to the host's cover, and note what happened."""
    from anongee_toolkit.structural import rebar_constraints
    applied, notes = rebar_constraints.apply_to_all(
        result.created, doc, host, varying)
    result.constrained += applied
    for note in notes:
        if note not in result.constraint_notes:
            result.constraint_notes.append(note)
    return result


def place_layer(doc, host, plan, bar_type_id, origin_ft=None,
                rotation_deg=0.0, view=None, constrain=True):
    """One scheduled run of bars, as a set where it can be.

    A uniform run becomes a single element carrying its own layout; a run whose
    bars differ in length -- which is what a non-rectangular pad produces -- has
    to be placed bar by bar, because a Revit set repeats one shape.
    """
    result = PlacementResult()
    if not plan.bars:
        result.skipped.append("nothing to place: {0}".format(
            "; ".join(plan.notes) or "no bar positions"))
        return result

    # One set, whether the bars are identical or not. A run of differing
    # lengths is one distribution region of varying depth -- which is what a
    # varying set is for -- and placing it as N single bars gives the right
    # steel today and nothing that follows an edit tomorrow.
    bar_set = plan.as_set()
    try:
        rebar, _skipped = create_bar(
            doc, host, bar_set.bar, bar_type_id, origin_ft, rotation_deg,
            view=view, array_vector=bar_set.array_vector)
        apply_layout(rebar, bar_set)
        result.created.append(rebar.Id)
        result.elements += 1
        result.bars += bar_set.count
    except Exception as error:
        result.errors.append("{0}: {1}".format(bar_set.bar.label, error))
        return result

    if constrain:
        _constrain(doc, host, result, bar_set.varying)
    return result


def place_set(doc, host, bar_set, bar_type_id, origin_ft=None,
              rotation_deg=0.0, view=None):
    """One :class:`BarSetSpec` -- what column ties come through as."""
    result = PlacementResult()
    try:
        rebar, _skipped = create_bar(
            doc, host, bar_set.bar, bar_type_id, origin_ft, rotation_deg,
            view=view, array_vector=bar_set.array_vector)
        apply_layout(rebar, bar_set)
        result.created.append(rebar.Id)
        result.elements += 1
        result.bars += max(1, int(bar_set.count or 1))
    except Exception as error:
        result.errors.append("{0}: {1}".format(bar_set.bar.label, error))
    return result


def place_bars(doc, host, bars, bar_type_id, origin_ft=None, rotation_deg=0.0,
               view=None, array_vector=None):
    """A list of individual bars -- what column main bars come through as."""
    result = PlacementResult()
    for bar in bars:
        try:
            rebar, _skipped = create_bar(
                doc, host, bar, bar_type_id, origin_ft, rotation_deg, view=view,
                array_vector=array_vector)
            result.created.append(rebar.Id)
            result.elements += 1
            result.bars += 1
        except Exception as error:
            result.errors.append("{0}: {1}".format(bar.label, error))
    return result


def existing_stamped_rebar(doc, host):
    """Ids of bars in *host* that this tool placed.

    What phase 3 replaces. Anything unstamped was put there by a person and is
    left alone.
    """
    found = []
    try:
        from Autodesk.Revit.DB.Structure import RebarHostData
        host_data = RebarHostData.GetRebarHostData(host)
        if host_data is None:
            return found
        for rebar in host_data.GetRebarsInHost():
            parameter = rebar.LookupParameter(STAMP_PARAMETER)
            if (parameter is not None and parameter.HasValue
                    and (parameter.AsString() or "") == STAMP_TEXT):
                found.append(rebar.Id)
    except Exception:
        pass
    return found

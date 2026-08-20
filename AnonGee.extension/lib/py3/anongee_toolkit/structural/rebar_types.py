# -*- coding: utf-8 -*-
"""Find the rebar type elements a schedule names. Reads only.

A schedule says "T16". Revit needs a ``RebarBarType`` element, a
``RebarHookType`` element and a ``RebarCoverType`` element, and none of them are
numbers. Resolving that gap is the step most likely to stop a run before it
starts, so it happens here, up front, where the answer can be shown to the user
and mapped by hand before a transaction is ever opened.

Nothing in this module writes. Creating a bar type that a project template did
not choose to load would put a wrongly-named type in someone's model and a
wrongly-named bar in their schedule, which is worse than saying "this is
missing" and stopping.
"""

from Autodesk.Revit.DB import BuiltInCategory
from Autodesk.Revit.DB import BuiltInParameter
from Autodesk.Revit.DB import FilteredElementCollector

from anongee_toolkit.revit.units import ft_to_mm

__version__ = "0.1.0"

#: How close a cover type's value has to be to count as the one asked for.
COVER_TOLERANCE_MM = 0.5

#: How close a bar type's diameter has to be. Bar sizes are whole millimetres
#: apart, so anything looser would start matching 20 mm to a 25 mm type.
DIAMETER_TOLERANCE_MM = 0.5


def _name(element):
    try:
        return element.Name
    except Exception:
        return ""


def _elements_of_class(doc, class_name, category):
    """Every element type in *category* whose runtime class matches.

    Filtering by class name rather than importing the class keeps this working
    across the API versions where these types moved namespace, and rebar types
    are few enough that the scan costs nothing.
    """
    found = []
    for element in (FilteredElementCollector(doc).OfCategory(category)
                    .WhereElementIsElementType().ToElements()):
        if element.GetType().Name == class_name:
            found.append(element)
    return found


# ---------------------------------------------------------------------------
# Bar types
# ---------------------------------------------------------------------------

def bar_types(doc):
    """``[(name, ElementId, diameter_mm)]`` for every loaded RebarBarType."""
    rows = []
    for element in _elements_of_class(doc, "RebarBarType",
                                      BuiltInCategory.OST_Rebar):
        rows.append((_name(element), element.Id, bar_diameter_mm(element)))
    rows.sort(key=lambda row: (row[2] if row[2] is not None else 0, row[0]))
    return rows


def bar_diameter_mm(bar_type):
    """A bar type's diameter in millimetres, or ``None`` if it will not say.

    ``REBAR_BAR_DIAMETER`` is the nominal size and is what a schedule means.
    ``REBAR_MODEL_BAR_DIAMETER`` is what gets drawn, and on some templates it is
    the only one filled in, so it is worth asking for second rather than giving
    up on a type that is perfectly usable.
    """
    for builtin in (BuiltInParameter.REBAR_BAR_DIAMETER,
                    BuiltInParameter.REBAR_MODEL_BAR_DIAMETER):
        try:
            parameter = bar_type.get_Parameter(builtin)
        except Exception:
            parameter = None
        if parameter is not None and parameter.HasValue:
            try:
                return ft_to_mm(parameter.AsDouble())
            except Exception:
                continue
    return None


def match_bar_type(doc, diameter_mm, name_hint=""):
    """The best ``RebarBarType`` for a scheduled bar, or ``None``.

    Name first, because a project that calls its 16 mm bar "T16" means that one
    specifically and may well have two types at the same diameter. Diameter
    second, so a workbook that names nothing still resolves. Never a guess when
    neither matches -- the caller shows the user a mapping instead.
    """
    rows = bar_types(doc)
    if name_hint:
        wanted = str(name_hint).strip().lower()
        for name, element_id, _diameter in rows:
            if name.strip().lower() == wanted:
                return element_id

    if diameter_mm is None:
        return None
    for name, element_id, diameter in rows:
        if (diameter is not None
                and abs(diameter - float(diameter_mm)) <= DIAMETER_TOLERANCE_MM):
            return element_id
    return None


def unresolved_bar_types(doc, rows):
    """``[(diameter_mm, name_hint)]`` the model cannot supply.

    What the mapping section in the window is built from, and what blocks a run
    when the user leaves it unmapped.
    """
    missing = []
    seen = set()
    for row in rows:
        key = (row.diameter_mm, (row.bar_type or "").strip())
        if key in seen:
            continue
        seen.add(key)
        if match_bar_type(doc, row.diameter_mm, row.bar_type) is None:
            missing.append(key)
    return missing


# ---------------------------------------------------------------------------
# Hook types
# ---------------------------------------------------------------------------

def hook_types(doc):
    """``[(name, ElementId)]`` for every loaded RebarHookType."""
    rows = [(_name(element), element.Id)
            for element in _elements_of_class(doc, "RebarHookType",
                                              BuiltInCategory.OST_RebarShape)]
    if not rows:
        rows = [(_name(element), element.Id)
                for element in _elements_of_class(doc, "RebarHookType",
                                                  BuiltInCategory.OST_Rebar)]
    rows.sort(key=lambda row: row[0])
    return rows


def match_hook_type(doc, name_hint):
    """A hook type by name, or ``None``. No hook is a legitimate answer."""
    if not name_hint:
        return None
    wanted = str(name_hint).strip().lower()
    for name, element_id in hook_types(doc):
        if name.strip().lower() == wanted:
            return element_id
    return None


# ---------------------------------------------------------------------------
# Cover types
# ---------------------------------------------------------------------------

def cover_types(doc):
    """``[(name, ElementId, cover_mm)]`` for every loaded RebarCoverType."""
    rows = []
    for element in _elements_of_class(doc, "RebarCoverType",
                                      BuiltInCategory.OST_Rebar):
        distance = None
        try:
            distance = ft_to_mm(element.CoverDistance)
        except Exception:
            pass
        rows.append((_name(element), element.Id, distance))
    rows.sort(key=lambda row: (row[2] if row[2] is not None else 0, row[0]))
    return rows


def match_cover_type(doc, cover_mm, tolerance_mm=COVER_TOLERANCE_MM,
                     name_hint=""):
    """The cover type the caller means, or ``None``.

    Two different questions, and the caller says which by passing *name_hint*
    or not:

    **Without a hint** -- "does this project already cover 50 mm?" -- the value
    is the whole answer, because names vary by template while 50 mm is 50 mm.
    That is what the pre-run check asks.

    **With a hint** -- "is *this* face's cover type already here?" -- the name
    has to match as well, and ``None`` means *create it* rather than *fall back
    to something the same size*. Value alone is not enough there: a footing's
    top and side cover are both 50 mm on most schedules, so a value-only match
    hands the side face the type named ``FOOTING TOP`` and the model then reads
    "Other Faces: FOOTING TOP", which is wrong on a drawing whatever the number
    says.
    """
    if cover_mm is None:
        return None
    rows = cover_types(doc)
    if name_hint:
        wanted = str(name_hint).strip().lower()
        for name_text, element_id, distance in rows:
            if (name_text.strip().lower() == wanted and distance is not None
                    and abs(distance - float(cover_mm)) <= tolerance_mm):
                return element_id
        return None

    best = None
    best_gap = None
    for _name_text, element_id, distance in rows:
        if distance is None:
            continue
        gap = abs(distance - float(cover_mm))
        if gap <= tolerance_mm and (best_gap is None or gap < best_gap):
            best, best_gap = element_id, gap
    return best


def unresolved_cover_types(doc, values_mm):
    """Which scheduled cover values no loaded cover type provides."""
    missing = []
    for value in sorted(set(v for v in values_mm if v is not None)):
        if match_cover_type(doc, value) is None:
            missing.append(value)
    return missing

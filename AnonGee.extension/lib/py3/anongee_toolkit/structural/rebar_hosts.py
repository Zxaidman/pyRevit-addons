# -*- coding: utf-8 -*-
"""Find the elements a schedule reinforces, and say when one cannot be. Reads only.

Two questions, and the second is the one that bites.

*Which element is this row about?* Answered by a key parameter -- ``Mark`` by
default, but whichever one the project actually keys its schedules off -- with
the level as a tie-breaker.

*Can a bar go into it?* A footing modelled as a floor is only a legal rebar host
once it is flagged structural, and a floor that is not will refuse every bar
placed into it. That is the failure worth finding before a run rather than four
hundred elements into one, so it is checked here and reported as a status, not
raised as an exception.
"""

from Autodesk.Revit.DB import BuiltInCategory
from Autodesk.Revit.DB import BuiltInParameter
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB.Structure import RebarHostData

from anongee_toolkit.revit.units import ft_to_mm

__version__ = "0.1.0"

FOOTING_CATEGORY = BuiltInCategory.OST_StructuralFoundation
COLUMN_CATEGORY = BuiltInCategory.OST_StructuralColumns

#: The parameter offered first, and the one a schedule usually keys off.
DEFAULT_KEY_PARAMETER = "Mark"


def elements_in(doc, category):
    return list(FilteredElementCollector(doc).OfCategory(category)
                .WhereElementIsNotElementType().ToElements())


def is_valid_host(element):
    """True when Revit will accept reinforcement into this element.

    The common false answer is a floor that was never flagged structural, which
    looks exactly like a footing in every view and takes no bars at all.
    """
    try:
        host_data = RebarHostData.GetRebarHostData(element)
        return host_data is not None and host_data.IsValidHost()
    except Exception:
        return False


def why_not_a_host(element):
    """A sentence the user can act on, or ``None`` when the element is fine."""
    if is_valid_host(element):
        return None
    try:
        parameter = element.get_Parameter(
            BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
        if parameter is not None and parameter.HasValue:
            if not parameter.AsInteger():
                return ("the floor is not flagged structural, so Revit will "
                        "not put reinforcement in it — tick Structural on the "
                        "element and re-run")
    except Exception:
        pass
    return "Revit does not accept reinforcement in this element"


def parameter_text(element, parameter_name):
    """A named parameter as text, whatever it is stored as, or ``""``."""
    try:
        parameter = element.LookupParameter(parameter_name)
    except Exception:
        return ""
    if parameter is None or not parameter.HasValue:
        return ""
    try:
        storage = parameter.StorageType.ToString()
        if storage == "String":
            return parameter.AsString() or ""
        if storage == "Integer":
            return str(parameter.AsInteger())
        if storage == "Double":
            return parameter.AsValueString() or str(parameter.AsDouble())
        if storage == "ElementId":
            owner = element.Document.GetElement(parameter.AsElementId())
            return owner.Name if owner is not None else ""
    except Exception:
        return ""
    return ""


def key_parameter_names(doc, category):
    """Text-ish parameter names shared by the elements of *category*.

    What the Key Parameter dropdown offers. Only parameters every element
    carries are listed, because one that half of them lack cannot key a match.
    """
    elements = elements_in(doc, category)
    if not elements:
        return [DEFAULT_KEY_PARAMETER]

    shared = None
    for element in elements[:50]:          # a sample is enough and stays quick
        names = set()
        try:
            for parameter in element.Parameters:
                try:
                    storage = parameter.StorageType.ToString()
                except Exception:
                    continue
                if storage in ("String", "Integer"):
                    names.add(parameter.Definition.Name)
        except Exception:
            continue
        shared = names if shared is None else (shared & names)
    names = sorted(shared or set())
    if DEFAULT_KEY_PARAMETER in names:
        names.remove(DEFAULT_KEY_PARAMETER)
        names.insert(0, DEFAULT_KEY_PARAMETER)
    return names or [DEFAULT_KEY_PARAMETER]


def level_name(element):
    """The element's level, by name, or ``""``.

    Tried in the order a footing, then a column, then anything else stores it.
    """
    for builtin in (BuiltInParameter.LEVEL_PARAM,
                    BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                    BuiltInParameter.SCHEDULE_LEVEL_PARAM):
        try:
            parameter = element.get_Parameter(builtin)
        except Exception:
            continue
        if parameter is None or not parameter.HasValue:
            continue
        try:
            level = element.Document.GetElement(parameter.AsElementId())
            if level is not None:
                return level.Name
        except Exception:
            continue
    return ""


def index_by_key(doc, category, parameter_name=DEFAULT_KEY_PARAMETER):
    """``{key: [elements]}`` for one category.

    A list per key on purpose. ``Mark`` is an instance parameter and Revit does
    not make it unique, so two elements really can answer to one name -- and
    keying them into a single slot would silently reinforce one and skip the
    other. The level is what tells them apart, and :func:`resolve` uses it.
    """
    index = {}
    for element in elements_in(doc, category):
        key = parameter_text(element, parameter_name).strip()
        if key:
            index.setdefault(key, []).append(element)
    return index


def resolve(index, key, level=""):
    """``(element, note)`` for one schedule row.

    ``note`` is ``None`` when the answer is unambiguous, and otherwise says what
    was ambiguous about it, because a match the user cannot see the reasoning
    for is a match they cannot trust.
    """
    candidates = index.get((key or "").strip())
    if not candidates:
        return None, "no element with that key"
    if len(candidates) == 1:
        return candidates[0], None

    if level:
        on_level = [e for e in candidates if level_name(e) == level]
        if len(on_level) == 1:
            return on_level[0], None
        if len(on_level) > 1:
            return None, "{0} elements share this key on {1}".format(
                len(on_level), level)
    return None, "{0} elements share this key; give a Level to tell them apart"\
        .format(len(candidates))


def host_summary(doc, category):
    """``(total, hostable)`` -- and the gap between them is the story."""
    total = 0
    hostable = 0
    for element in elements_in(doc, category):
        total += 1
        if is_valid_host(element):
            hostable += 1
    return total, hostable


def bottom_elevation_mm(element):
    """Height of the element's lowest point above the project origin, in mm.

    Bar heights are worked out from the bottom face because that is what cover
    is measured from, and a bounding box is the one way to ask that holds for a
    sketched floor and a family instance alike.
    """
    try:
        box = element.get_BoundingBox(None)
        if box is not None:
            return ft_to_mm(box.Min.Z)
    except Exception:
        pass
    return None


def plan_origin_mm(element):
    """``(x_mm, y_mm)`` of the element's plan centre, or ``None``.

    Bar centrelines are local to their host, and this is what makes them world
    coordinates. The bounding-box centre is right for a rectangular pad and for
    a sketched one alike, and it is what the outline in the workbook is
    measured from.
    """
    try:
        box = element.get_BoundingBox(None)
        if box is None:
            return None
        return (ft_to_mm((box.Min.X + box.Max.X) / 2.0),
                ft_to_mm((box.Min.Y + box.Max.Y) / 2.0))
    except Exception:
        return None

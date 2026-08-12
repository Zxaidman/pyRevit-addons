# -*- coding: utf-8 -*-
"""The Revit API differences this tool actually touches.

The extension supports Revit 2022 and newer, which straddles two renames:
``ElementId.IntegerValue`` became ``ElementId.Value`` in 2024, and the
``DisplayUnitType`` enum became ``ForgeTypeId`` in 2021. Everything else the
tool uses has been stable across that range. Each helper resolves once and
caches, so the version test is not paid per element.
"""

from Autodesk.Revit.DB import ElementId, UnitUtils

MM_PER_FT = 304.8

_UNIT_MM = None
_UNIT_RESOLVED = False
_SPEC_LENGTH = None
_SPEC_RESOLVED = False


# ── element ids ────────────────────────────────────────────────────────────

def id_value(element_id):
    """``ElementId`` -> int, on either side of the 2024 rename."""
    if element_id is None:
        return None
    try:
        return int(element_id.Value)          # Revit 2024+
    except AttributeError:
        return int(element_id.IntegerValue)   # Revit 2022-2023


def element_id(value):
    """int -> ``ElementId``."""
    if value is None:
        return ElementId.InvalidElementId
    if isinstance(value, ElementId):
        return value
    try:
        return ElementId(int(value))
    except Exception:
        return ElementId.InvalidElementId


# ── lengths ────────────────────────────────────────────────────────────────

def _millimetre_unit():
    """The ForgeTypeId / DisplayUnitType that means millimetres, or None."""
    global _UNIT_MM, _UNIT_RESOLVED
    if _UNIT_RESOLVED:
        return _UNIT_MM
    _UNIT_RESOLVED = True
    try:
        from Autodesk.Revit.DB import UnitTypeId
        _UNIT_MM = UnitTypeId.Millimeters              # Revit 2021+
        return _UNIT_MM
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import DisplayUnitType
        _UNIT_MM = DisplayUnitType.DUT_MILLIMETERS     # legacy
    except Exception:
        _UNIT_MM = None
    return _UNIT_MM


def feet_to_mm(feet):
    """Internal units -> millimetres. Falls back to the exact constant."""
    if feet is None:
        return 0.0
    unit = _millimetre_unit()
    if unit is not None:
        try:
            return float(UnitUtils.ConvertFromInternalUnits(float(feet), unit))
        except Exception:
            pass
    return float(feet) * MM_PER_FT


def mm_to_feet(millimetres):
    """Millimetres -> internal units."""
    if millimetres is None:
        return 0.0
    unit = _millimetre_unit()
    if unit is not None:
        try:
            return float(UnitUtils.ConvertToInternalUnits(float(millimetres), unit))
        except Exception:
            pass
    return float(millimetres) / MM_PER_FT


def _length_spec():
    """``SpecTypeId.Length`` / ``UnitType.UT_Length``, whichever exists."""
    global _SPEC_LENGTH, _SPEC_RESOLVED
    if _SPEC_RESOLVED:
        return _SPEC_LENGTH
    _SPEC_RESOLVED = True
    try:
        from Autodesk.Revit.DB import SpecTypeId
        _SPEC_LENGTH = SpecTypeId.Length               # Revit 2021+
        return _SPEC_LENGTH
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import UnitType
        _SPEC_LENGTH = UnitType.UT_Length              # legacy
    except Exception:
        _SPEC_LENGTH = None
    return _SPEC_LENGTH


def format_length_mm(doc, millimetres):
    """Format a length the way *this project* displays lengths.

    Metric projects get ``3500``, imperial ones get ``11' - 5 3/4"`` — the
    point is that the number in the dialog matches the number in Revit's own
    properties palette. Falls back to plain millimetres if the project's units
    can't be read.
    """
    try:
        from Autodesk.Revit.DB import UnitFormatUtils
        spec = _length_spec()
        if spec is None:
            raise ValueError("no length spec")
        return UnitFormatUtils.Format(doc.GetUnits(), spec,
                                      mm_to_feet(millimetres), False)
    except Exception:
        return "{0:.0f} mm".format(millimetres or 0.0)


# ── names ──────────────────────────────────────────────────────────────────

def element_name(element):
    """An element's name, whichever way this version exposes it."""
    if element is None:
        return ""
    try:
        name = element.Name
        if name:
            return str(name)
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import Element
        return str(Element.Name.GetValue(element) or "")
    except Exception:
        return ""


def set_element_name(element, name):
    """Rename an element. Returns (ok, message) instead of raising."""
    try:
        element.Name = name
        return True, ""
    except Exception as error:
        return False, str(error)[:160]

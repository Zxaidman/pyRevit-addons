# -*- coding: utf-8 -*-
"""Compatibility helpers for the 2024/2025 API split and runtime self-check.

The only hard breaking change across Revit 2023-2026 is the runtime, not the
document API. Two small surfaces still differ and are isolated here so the rest
of the code never branches on version:

  * ElementId.Value (Int64) was introduced in 2024 and ElementId.IntegerValue
    deprecated. We read Value, falling back to IntegerValue on older hosts.
  * Element.Name resolution differs by subtype; Element.Name.GetValue(el) is the
    robust idiom, with a plain .Name fallback.
"""

import sys


def element_id_value(element_id):
    """Return the integer value of an ElementId across Revit versions.

    Fail-fast on a None id rather than masking a programming error downstream.
    """
    if element_id is None:
        raise ValueError("element_id_value received None")
    try:
        return element_id.Value          # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue   # Revit 2023 and earlier


def get_element_name(element):
    """Best-effort element name; returns None instead of raising on odd subtypes."""
    if element is None:
        return None
    try:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(element)
    except Exception:
        try:
            return element.Name
        except Exception:
            return None


def runtime_summary():
    """One-line description of the live Python/IronPython runtime.

    Used by the startup self-check to make the Revit-2025 .NET 8 / IronPython
    2.7.12 loader situation visible in the log if anything misbehaves.
    """
    return "Runtime: {0}".format(sys.version.replace("\n", " "))


# --- element naming --------------------------------------------------------
# Which parameter carries the CAD mark. "Mark" is the Revit default, but a
# practice may keep its element names in Comments, Type Mark, or a shared
# parameter of its own, so the dialog can point this anywhere.
_NAME_PARAMETER = None


def set_name_parameter(name):
    """Choose the instance parameter the CAD mark is written into (None = Mark)."""
    global _NAME_PARAMETER
    _NAME_PARAMETER = (name or "").strip() or None


def name_parameter():
    """The configured name parameter, or None when the Mark default applies."""
    return _NAME_PARAMETER


def set_element_mark(element, mark):
    """Write `mark` onto `element`'s name parameter. True when it landed.

    The configured parameter is tried first and Mark is the fallback, so a
    typo or a parameter that is missing on this family still names the element
    instead of losing the mark. Naming is best-effort: never raises.
    """
    if element is None or mark is None:
        return False
    text = str(mark)
    wanted = _NAME_PARAMETER
    if wanted:
        try:
            parameter = element.LookupParameter(wanted)
            if parameter is not None and not parameter.IsReadOnly:
                parameter.Set(text)
                return True
        except Exception:
            pass
    try:
        from Autodesk.Revit.DB import BuiltInParameter
        parameter = element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(text)
            return True
    except Exception:
        pass
    return False

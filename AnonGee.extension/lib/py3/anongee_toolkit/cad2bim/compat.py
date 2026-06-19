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

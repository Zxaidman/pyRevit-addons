# -*- coding: utf-8 -*-
"""Place an isolated FOOTING under every column, on the column's base level.

One Structural Foundation instance per column footprint, at the column's centre
and rotated to its long axis, sized from the column plus a projection all round
(the dialog's "footing projection"): a 400 x 600 column with a 300 projection
gets a 1000 x 1200 footing. A type is duplicated per distinct size and cached,
exactly as the column and beam builders do, so a model with many column sizes
gets one correctly-named footing type per size rather than a duplicate per
instance.

Levels: footings go on the BASE level of the columns. In a multi-storey run only
the lowest storey builds them -- a building has one set of foundations, not one
per floor -- which the pushbutton decides, not this module.

This module performs Revit writes and must run inside a Transaction.
"""

import math

from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter,
                               ElementTransformUtils, FamilySymbol,
                               FilteredElementCollector, Line, XYZ)
from Autodesk.Revit.DB.Structure import StructuralType

from ..compat import get_element_name, set_element_mark
from .. import config
from .. import naming

_MM = config.MM_PER_FT

_LENGTH_PARAM_NAMES = ("Length", "L", "Width", "b", "B", "Foundation Length")
_WIDTH_PARAM_NAMES = ("Width", "W", "w", "Depth", "Foundation Width")
_THICK_PARAM_NAMES = ("Thickness", "Foundation Thickness", "t", "T", "Height")

# A footprint whose smaller side exceeds this is a raft/region, not a column.
_MAX_COLUMN_MIN_SIDE_MM = config.DEFAULTS["col_region_max_side_mm"]


def foundation_symbols(doc):
    """[(label, ElementId)] of loaded structural foundation types, sorted."""
    symbols = (FilteredElementCollector(doc)
               .OfCategory(BuiltInCategory.OST_StructuralFoundation)
               .OfClass(FamilySymbol)
               .ToElements())
    rows = []
    for symbol in symbols:
        family_name = symbol.Family.Name if symbol.Family else "?"
        rows.append(("{0} : {1}".format(family_name, get_element_name(symbol)),
                     symbol.Id))
    return sorted(rows, key=lambda pair: pair[0])


def _set_dimension(symbol, names, value_mm):
    for name in names:
        parameter = symbol.LookupParameter(name)
        if parameter is not None and not parameter.IsReadOnly:
            try:
                if parameter.Set(value_mm / _MM):
                    return True
            except Exception:
                continue
    return False


def _find_type_in_family(family, type_name):
    if family is None:
        return None
    document = family.Document
    for symbol_id in family.GetFamilySymbolIds():
        symbol = document.GetElement(symbol_id)
        if symbol is not None and get_element_name(symbol) == type_name:
            return symbol
    return None


def _resolve_symbol(base_symbol, length_mm, width_mm, thickness_mm, cache):
    """A footing type of this size, duplicated off the base type and cached."""
    key = (length_mm, width_mm, thickness_mm)
    if key in cache:
        return cache[key]
    type_name = naming.footing_type_name(width_mm, length_mm, thickness_mm)
    existing = _find_type_in_family(base_symbol.Family, type_name)
    if existing is not None:
        cache[key] = existing
        return existing
    new_symbol = base_symbol.Duplicate(type_name)
    _set_dimension(new_symbol, _LENGTH_PARAM_NAMES, max(length_mm, width_mm))
    _set_dimension(new_symbol, _WIDTH_PARAM_NAMES, min(length_mm, width_mm))
    if thickness_mm:
        _set_dimension(new_symbol, _THICK_PARAM_NAMES, thickness_mm)
    cache[key] = new_symbol
    return new_symbol


def place_footings(doc, sections, base_symbol_id, level_id, projection_mm=300.0,
                   thickness_mm=0.0, region_max_side_mm=None):
    """One footing per column rectangle, on `level_id`.

    `projection_mm` is how far the footing reaches past the column on EVERY
    side, so the footing is (column + 2 x projection). `thickness_mm` of 0 keeps
    whatever the base type has. Circular columns get a square footing around
    their diameter -- an isolated pad under a round column is normally square.

    Returns {"created": [ids], "skipped": [reasons], "errors": [reasons]}.
    """
    base_symbol = doc.GetElement(base_symbol_id)
    level = doc.GetElement(level_id)
    result = {"created": [], "skipped": [], "errors": []}
    if base_symbol is None or level is None:
        raise ValueError("footing family or level could not be resolved")

    region_max = (_MAX_COLUMN_MIN_SIDE_MM if region_max_side_mm is None
                  else region_max_side_mm)
    elevation = level.Elevation
    cache = {}
    grow = 2.0 * float(projection_mm or 0.0)

    for entry in sections.get("entries", []):
        for rectangle in entry.get("rectangles", []):
            try:
                width_mm = int(round(rectangle["width_mm"]))
                height_mm = int(round(rectangle["height_mm"]))
                if min(width_mm, height_mm) > region_max:
                    result["skipped"].append(
                        "region {0}x{1} mm is not a column".format(width_mm,
                                                                  height_mm))
                    continue
                small = int(round(min(width_mm, height_mm) + grow))
                big = int(round(max(width_mm, height_mm) + grow))
                symbol = _resolve_symbol(base_symbol, big, small,
                                         thickness_mm, cache)
                if not symbol.IsActive:
                    symbol.Activate()
                    doc.Regenerate()
                cx, cy, _cz = rectangle["center"]
                point = XYZ(cx, cy, elevation)
                instance = doc.Create.NewFamilyInstance(
                    point, symbol, level, StructuralType.Footing)
                _match_column_rotation(doc, instance, rectangle, point,
                                       width_mm, height_mm)
                mark = rectangle.get("mark")
                if mark:
                    set_element_mark(instance, "F-{0}".format(mark))
                result["created"].append(instance.Id)
            except Exception as creation_error:
                result["errors"].append(str(creation_error))

    for circle in sections.get("circles", []) or []:
        try:
            diameter_mm = int(round(circle["diameter_mm"]))
            side = int(round(diameter_mm + grow))
            symbol = _resolve_symbol(base_symbol, side, side, thickness_mm,
                                     cache)
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
            cx, cy, _cz = circle["center"]
            instance = doc.Create.NewFamilyInstance(
                XYZ(cx, cy, elevation), symbol, level, StructuralType.Footing)
            mark = circle.get("mark")
            if mark:
                set_element_mark(instance, "F-{0}".format(mark))
            result["created"].append(instance.Id)
        except Exception as creation_error:
            result["errors"].append(str(creation_error))
    return result


def _match_column_rotation(doc, instance, rectangle, point, width_mm, height_mm):
    """Turn the footing so its long side follows the column's long side."""
    long_axis_deg = rectangle.get("long_axis_deg")
    if long_axis_deg is None:
        long_axis_deg = 0.0 if width_mm >= height_mm else 90.0
    rotation_deg = long_axis_deg
    if abs(rotation_deg % 180.0) < 0.01:
        return
    axis = Line.CreateUnbound(point, XYZ.BasisZ)
    ElementTransformUtils.RotateElement(doc, instance.Id, axis,
                                        math.radians(rotation_deg))


def set_top_of_footing(instance, offset_ft):
    """Drop the footing so its TOP sits on the level (Revit hangs it below)."""
    try:
        parameter = instance.get_Parameter(
            BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(offset_ft)
            return True
    except Exception:
        pass
    return False

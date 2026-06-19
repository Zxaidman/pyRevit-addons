# -*- coding: utf-8 -*-
"""Place rectangular structural columns from decomposed column sections.

Each rectangle (centre + width/height in feet, from shapes.decompose) becomes one
column instance. Cross-section comes from the rectangle; HEIGHT comes from the
chosen base/top levels (not the rectangle). A type is duplicated per distinct
(b, h) size and cached, so a model with many sizes gets correctly-named types
("300 x 900", "300 x 3300", ...) without redundant duplication.

Assumptions (flagged for review):
  * The family's `b` runs along the family X axis and `h` along Y, and instances
    are placed un-rotated, so b = the rectangle's X-extent and h = its Y-extent.
    This reproduces the CAD footprint exactly; if a family's convention differs,
    only the b/h labelling swaps, not the footprint.
  * b/h are set via type parameters, trying several common names (b/width/W ...).

This module performs Revit writes and must run inside a Transaction.
"""

import math

from Autodesk.Revit.DB import (FilteredElementCollector, BuiltInCategory,
                               FamilySymbol, Level, XYZ, BuiltInParameter,
                               ElementTransformUtils, Line)
from Autodesk.Revit.DB.Structure import StructuralType

from .units import mm_to_internal
from .compat import get_element_name
from . import config

_B_PARAM_NAMES = ("b", "width", "w", "Width", "B", "W")
_H_PARAM_NAMES = ("h", "depth", "d", "Depth", "H", "D")
_DIA_PARAM_NAMES = ("d", "diameter", "Diameter", "D", "dia", "Dia", "b", "width")

# A rectangle whose SMALLER side exceeds this is treated as a lift/stair region,
# not a column, and skipped (e.g. 2700x3300, 5700x3300). Tunable (config / UI).
_MAX_COLUMN_MIN_SIDE_MM = config.DEFAULTS["col_region_max_side_mm"]


def structural_column_symbols(doc):
    """[(label, ElementId)] of loaded structural-column family types, sorted."""
    symbols = (FilteredElementCollector(doc)
               .OfCategory(BuiltInCategory.OST_StructuralColumns)
               .OfClass(FamilySymbol)
               .ToElements())
    rows = []
    for symbol in symbols:
        family_name = symbol.Family.Name if symbol.Family else "?"
        rows.append(("{0} : {1}".format(family_name, get_element_name(symbol)),
                     symbol.Id))
    return sorted(rows, key=lambda pair: pair[0])


def levels(doc):
    """[(name, ElementId)] of levels, sorted by elevation (lowest first)."""
    items = list(FilteredElementCollector(doc).OfClass(Level).ToElements())
    items.sort(key=lambda level: level.Elevation)
    return [(get_element_name(level), level.Id) for level in items]


def place_columns(doc, sections, base_symbol_id, base_level_id, top_level_id,
                  region_max_side_mm=None):
    """Place a rectangular column for every section rectangle.

    Conventions (per the project): the type is named/sized smaller-side b x
    bigger-side h for consistency, and a "landscape" rectangle (wider in X than
    deep in Y) is rotated 90 degrees so its long side runs along X -- this keeps a
    single "300 x 900" type instead of duplicate "300 x 900" / "900 x 300".
    Rectangles whose smaller side exceeds the region threshold (lift/stair areas)
    are skipped. Runs inside a caller-owned Transaction.
    """
    base_symbol = doc.GetElement(base_symbol_id)
    base_level = doc.GetElement(base_level_id)
    top_level = doc.GetElement(top_level_id)
    if base_symbol is None or base_level is None or top_level is None:
        raise ValueError("column family or levels could not be resolved")

    region_max = (_MAX_COLUMN_MIN_SIDE_MM if region_max_side_mm is None
                  else region_max_side_mm)
    base_elevation = base_level.Elevation
    cache = {}
    result = {"created": [], "skipped": [], "errors": []}

    for entry in sections.get("entries", []):
        for rectangle in entry.get("rectangles", []):
            try:
                width_mm = int(round(rectangle["width_mm"]))
                height_mm = int(round(rectangle["height_mm"]))
                small = min(width_mm, height_mm)
                big = max(width_mm, height_mm)
                if small > region_max:
                    result["skipped"].append(
                        "region {0}x{1} mm (>{2} min side)".format(
                            width_mm, height_mm, region_max))
                    continue

                symbol = _resolve_symbol(doc, base_symbol, small, big, cache)
                if not symbol.IsActive:
                    symbol.Activate()
                    doc.Regenerate()
                cx, cy, _cz = rectangle["center"]
                point = XYZ(cx, cy, base_elevation)
                instance = doc.Create.NewFamilyInstance(
                    point, symbol, base_level, StructuralType.Column)
                _set_top_level(instance, top_level)
                _set_mark(instance, rectangle.get("mark"))

                # The type is small(b) x big(h) with b along family X (h along Y,
                # i.e. long axis at 90 deg). Rotate so the big side lines up with
                # the rectangle's long axis -- this covers axis-aligned landscape
                # AND rotated columns with one formula.
                long_axis_deg = rectangle.get("long_axis_deg")
                if long_axis_deg is None:
                    long_axis_deg = 0.0 if width_mm >= height_mm else 90.0
                rotation_deg = long_axis_deg - 90.0
                if abs(rotation_deg) > 0.01:
                    axis = Line.CreateUnbound(point, XYZ.BasisZ)
                    ElementTransformUtils.RotateElement(
                        doc, instance.Id, axis, math.radians(rotation_deg))

                result["created"].append(instance.Id)
            except Exception as placement_error:
                result["errors"].append(str(placement_error))
    return result


def place_circular_columns(doc, circles, base_symbol_id, base_level_id, top_level_id):
    """Place a circular column for every detected circle, sizing its diameter.

    Mirrors place_columns: per-diameter type duplication ("600 dia"), diameter set
    via the family's diameter parameter with fallbacks. Runs in a Transaction.
    """
    base_symbol = doc.GetElement(base_symbol_id)
    base_level = doc.GetElement(base_level_id)
    top_level = doc.GetElement(top_level_id)
    if base_symbol is None or base_level is None or top_level is None:
        raise ValueError("circular column family or levels could not be resolved")

    base_elevation = base_level.Elevation
    cache = {}
    result = {"created": [], "skipped": [], "errors": []}

    for circle in circles:
        try:
            diameter_mm = int(round(circle["diameter_mm"]))
            symbol = _resolve_circular_symbol(doc, base_symbol, diameter_mm, cache)
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
            cx, cy, _cz = circle["center"]
            point = XYZ(cx, cy, base_elevation)
            instance = doc.Create.NewFamilyInstance(
                point, symbol, base_level, StructuralType.Column)
            _set_top_level(instance, top_level)
            result["created"].append(instance.Id)
        except Exception as placement_error:
            result["errors"].append(str(placement_error))
    return result


def _resolve_symbol(doc, base_symbol, b_mm, h_mm, cache):
    """Return a FamilySymbol sized b_mm x h_mm, duplicating+caching as needed."""
    key = (b_mm, h_mm)
    if key in cache:
        return cache[key]
    type_name = "{0} x {1}".format(b_mm, h_mm)
    existing = _find_type_in_family(base_symbol.Family, type_name)
    if existing is not None:
        cache[key] = existing
        return existing
    new_symbol = base_symbol.Duplicate(type_name)
    _set_dimension(new_symbol, _B_PARAM_NAMES, b_mm)
    _set_dimension(new_symbol, _H_PARAM_NAMES, h_mm)
    cache[key] = new_symbol
    return new_symbol


def _resolve_circular_symbol(doc, base_symbol, diameter_mm, cache):
    """Return a FamilySymbol of the given diameter, duplicating+caching as needed."""
    if diameter_mm in cache:
        return cache[diameter_mm]
    type_name = "{0} dia".format(diameter_mm)
    existing = _find_type_in_family(base_symbol.Family, type_name)
    if existing is not None:
        cache[diameter_mm] = existing
        return existing
    new_symbol = base_symbol.Duplicate(type_name)
    _set_dimension(new_symbol, _DIA_PARAM_NAMES, diameter_mm)
    cache[diameter_mm] = new_symbol
    return new_symbol


def _find_type_in_family(family, type_name):
    if family is None:
        return None
    document = family.Document
    for symbol_id in family.GetFamilySymbolIds():
        symbol = document.GetElement(symbol_id)
        if symbol is not None and get_element_name(symbol) == type_name:
            return symbol
    return None


def _set_dimension(symbol, param_names, value_mm):
    """Set the first writable matching type parameter to value_mm; True if set."""
    internal = mm_to_internal(value_mm)
    for name in param_names:
        parameter = symbol.LookupParameter(name)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(internal)
            return True
    return False


def _set_mark(instance, mark):
    """Stamp the instance 'Mark' parameter (e.g. C1) when a mark was resolved."""
    if not mark:
        return
    try:
        parameter = instance.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(str(mark))
    except Exception:
        pass   # naming is best-effort; never fail placement over a mark


def _set_top_level(instance, top_level):
    """Attach the column top to top_level with zero offsets (base set at placement)."""
    top = instance.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
    if top is not None and not top.IsReadOnly:
        top.Set(top_level.Id)
    for builtin in (BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM,
                    BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM):
        offset = instance.get_Parameter(builtin)
        if offset is not None and not offset.IsReadOnly:
            offset.Set(0.0)

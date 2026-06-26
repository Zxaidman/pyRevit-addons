# -*- coding: utf-8 -*-
"""Place structural framing beams from derived centerlines.

Each segment (start, end, width) becomes one beam along its centerline at the
chosen level (the columns' top level), with no offset. Width (b) is set from the
outline; DEPTH (h) is inherited from the user-picked base type -- a 2D plan does
not carry per-beam depth, so every beam takes the picked type's depth, which the
user controls by choosing the type. A type is duplicated per width ("300 wide")
and cached.

This module performs Revit writes and must run inside a Transaction.
"""

import math

from Autodesk.Revit.DB import (FilteredElementCollector, BuiltInCategory,
                               FamilySymbol, XYZ, Line, Arc, BuiltInParameter)
from Autodesk.Revit.DB.Structure import StructuralType, StructuralFramingUtils

from ..unit_convert import mm_to_internal
from ..compat import get_element_name


def _disallow_joins(instance):
    """Disallow the structural end-join at BOTH ends so Revit does not auto-extend the beam
    into neighbouring framing. Best-effort: a join-setting failure never fails placement."""
    for end in (0, 1):
        try:
            StructuralFramingUtils.DisallowJoinAtEnd(instance, end)
        except Exception:
            pass

_WIDTH_PARAM_NAMES = ("b", "width", "w", "Width", "B", "W")
_DEPTH_PARAM_NAMES = ("h", "depth", "d", "Depth", "H", "D")
_MIN_BEAM_LENGTH_MM = 50.0   # ignore slivers shorter than this


def _set_mark(instance, mark):
    """Stamp the instance 'Mark' parameter (e.g. B1) when a mark was resolved."""
    if not mark:
        return
    try:
        parameter = instance.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(str(mark))
    except Exception:
        pass   # naming is best-effort; never fail placement over a mark


def structural_framing_symbols(doc):
    """[(label, ElementId)] of loaded structural-framing (beam) family types."""
    symbols = (FilteredElementCollector(doc)
               .OfCategory(BuiltInCategory.OST_StructuralFraming)
               .OfClass(FamilySymbol)
               .ToElements())
    rows = []
    for symbol in symbols:
        family_name = symbol.Family.Name if symbol.Family else "?"
        rows.append(("{0} : {1}".format(family_name, get_element_name(symbol)),
                     symbol.Id))
    return sorted(rows, key=lambda pair: pair[0])


def place_beams(doc, segments, base_symbol_id, level_id):
    """Place a beam for each segment along its centerline at level_id.

    Runs inside a caller-owned Transaction. One bad segment never fails the batch.
    """
    base_symbol = doc.GetElement(base_symbol_id)
    level = doc.GetElement(level_id)
    if base_symbol is None or level is None:
        raise ValueError("beam family or level could not be resolved")

    elevation = level.Elevation
    cache = {}
    result = {"created": [], "skipped": [], "errors": []}

    for segment in segments:
        try:
            if segment["length_mm"] < _MIN_BEAM_LENGTH_MM:
                result["skipped"].append(
                    "tiny beam {0:.0f} mm".format(segment["length_mm"]))
                continue
            width_mm = int(round(segment["width_mm"]))
            depth_mm = segment.get("depth_mm")
            if depth_mm is not None:
                depth_mm = int(round(depth_mm))
            symbol = _resolve_beam_symbol(doc, base_symbol, width_mm, depth_mm, cache)
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
            sx, sy, _sz = segment["start"]
            ex, ey, _ez = segment["end"]
            curve = Line.CreateBound(XYZ(sx, sy, elevation), XYZ(ex, ey, elevation))
            instance = doc.Create.NewFamilyInstance(
                curve, symbol, level, StructuralType.Beam)
            _set_mark(instance, segment.get("mark"))
            _disallow_joins(instance)
            result["created"].append(instance.Id)
        except Exception as placement_error:
            result["errors"].append(str(placement_error))
    return result


def place_curved_beams(doc, curved_segments, base_symbol_id, level_id):
    """Place a curved beam for each concentric-arc-pair segment, driven by an Arc.

    Mirrors place_beams (same per-size type duplication + cache, same width/depth rules);
    only the driving curve differs -- an Arc from the segment's centre, centreline radius
    and swept angle. Runs inside a caller-owned Transaction; one bad segment never fails
    the batch.
    """
    base_symbol = doc.GetElement(base_symbol_id)
    level = doc.GetElement(level_id)
    if base_symbol is None or level is None:
        raise ValueError("beam family or level could not be resolved")

    elevation = level.Elevation
    cache = {}
    result = {"created": [], "skipped": [], "errors": []}

    for segment in curved_segments or []:
        try:
            if segment["length_mm"] < _MIN_BEAM_LENGTH_MM:
                result["skipped"].append(
                    "tiny curved beam {0:.0f} mm".format(segment["length_mm"]))
                continue
            width_mm = int(round(segment["width_mm"]))
            depth_mm = segment.get("depth_mm")
            if depth_mm is not None:
                depth_mm = int(round(depth_mm))
            symbol = _resolve_beam_symbol(doc, base_symbol, width_mm, depth_mm, cache)
            if not symbol.IsActive:
                symbol.Activate()
                doc.Regenerate()
            cx, cy, _cz = segment["center"]
            # Keep startAngle in [0, 2pi) and sweep CCW by (end - start) <= 2pi, the form
            # Arc.Create expects (angles measured CCW from the X axis about Z).
            start = math.radians(segment["start_deg"]) % (2.0 * math.pi)
            sweep = math.radians(segment["end_deg"] - segment["start_deg"])
            arc = Arc.Create(XYZ(cx, cy, elevation), segment["radius_ft"],
                             start, start + sweep, XYZ.BasisX, XYZ.BasisY)
            instance = doc.Create.NewFamilyInstance(
                arc, symbol, level, StructuralType.Beam)
            _set_mark(instance, segment.get("mark"))
            _disallow_joins(instance)
            result["created"].append(instance.Id)
        except Exception as placement_error:
            result["errors"].append(str(placement_error))
    return result


def _resolve_beam_symbol(doc, base_symbol, width_mm, depth_mm, cache):
    """Return a framing FamilySymbol of the given size, duplicating+caching.

    With a text-derived depth the type is sized "{w} x {h}" and BOTH width and
    depth are set; without one it stays "{w} wide" and depth is inherited from the
    base type (a 2D outline carries no depth).
    """
    key = (width_mm, depth_mm)
    if key in cache:
        return cache[key]
    type_name = ("{0} X {1}".format(width_mm, depth_mm) if depth_mm is not None
                 else "{0}".format(width_mm))
    existing = _find_type_in_family(base_symbol.Family, type_name)
    if existing is not None:
        cache[key] = existing
        return existing
    new_symbol = base_symbol.Duplicate(type_name)
    _set_dimension(new_symbol, _WIDTH_PARAM_NAMES, width_mm)
    if depth_mm is not None:
        _set_dimension(new_symbol, _DEPTH_PARAM_NAMES, depth_mm)
    cache[key] = new_symbol
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

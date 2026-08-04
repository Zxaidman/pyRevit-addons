# -*- coding: utf-8 -*-
"""Place an isolated FOOTING pad under every column, on the columns' base level.

Built the same way slabs are: a `Floor.Create` from the pad's outline against a
Structural Foundation floor type ("Foundation Slab"), NOT a family instance.
That keeps footings in the same shape as everything else this tool places -- a
sketched outline the user can edit -- and it sits ON the level with no offset,
where a foundation FAMILY hangs its own depth below the level it is hosted on.

The pad is the column footprint grown by a projection all round, turned with the
column: a 400 x 600 column with a 300 projection gets a 1000 x 1200 pad. A round
column gets a square pad, which is what an isolated pad under a round column
normally is. A type is duplicated per distinct THICKNESS and cached, exactly as
the slab builder does.

Levels: footings go on the BASE level of the columns, with a zero height offset.
In a multi-storey run only the lowest storey builds them -- a building has one
set of foundations, not one per floor -- which the pushbutton decides.

This module performs Revit writes and must run inside a Transaction.
"""

import math

from System.Collections.Generic import List

from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, CurveLoop,
                               ElementId, FilteredElementCollector, Floor,
                               FloorType, Line, XYZ)

from ..compat import get_element_name, set_element_mark
from .. import config
from .. import naming

_MM = config.MM_PER_FT

# A footprint whose smaller side exceeds this is a raft/region, not a column.
_MAX_COLUMN_MIN_SIDE_MM = config.DEFAULTS["col_region_max_side_mm"]


def foundation_types(doc):
    """[(label, ElementId)] of floor types in the Structural Foundation category.

    Every floor type is offered when the model has no foundation type at all, so
    a project that has not loaded one can still place pads (Revit will simply
    file them under Floors) -- with the category noted in the label.
    """
    foundation = []
    other = []
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        try:
            name = get_element_name(floor_type)
            category = floor_type.Category
            is_foundation = (category is not None
                             and category.Id.IntegerValue
                             == int(BuiltInCategory.OST_StructuralFoundation))
        except Exception:
            continue
        if is_foundation:
            foundation.append((name, floor_type.Id))
        else:
            other.append(("{0}  (floor, not foundation)".format(name),
                          floor_type.Id))
    foundation.sort(key=lambda pair: pair[0])
    other.sort(key=lambda pair: pair[0])
    return foundation + other


def _set_thickness(floor_type, thickness_mm):
    """Set a floor type's total thickness through its compound structure."""
    try:
        structure = floor_type.GetCompoundStructure()
        if structure is None:
            return False
        structure.SetLayerWidth(structure.GetFirstCoreLayerIndex(),
                                thickness_mm / _MM)
        floor_type.SetCompoundStructure(structure)
        return True
    except Exception:
        return False


def _resolve_type(doc, base_type, thickness_mm, cache):
    """A foundation type of this thickness, duplicated off the base and cached."""
    if not thickness_mm:
        return base_type
    key = int(round(thickness_mm))
    if key in cache:
        return cache[key]
    name = naming.footing_type_name(0, 0, key)
    for existing in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        try:
            if get_element_name(existing) == name:
                cache[key] = existing
                return existing
        except Exception:
            continue
    try:
        new_type = base_type.Duplicate(name)
    except Exception:
        cache[key] = base_type
        return base_type
    _set_thickness(new_type, thickness_mm)
    cache[key] = new_type
    return new_type


def pad_ring(rectangle, projection_ft):
    """The four corners of the pad under one column rectangle, in feet.

    The pad follows the column's own long axis, so a rotated column gets a
    rotated pad rather than an axis-aligned box around it.
    """
    cx, cy = rectangle["center"][0], rectangle["center"][1]
    width_mm = rectangle["width_mm"]
    height_mm = rectangle["height_mm"]
    long_axis_deg = rectangle.get("long_axis_deg")
    if long_axis_deg is None:
        long_axis_deg = 0.0 if width_mm >= height_mm else 90.0
    half_long = (max(width_mm, height_mm) / _MM) / 2.0 + projection_ft
    half_short = (min(width_mm, height_mm) / _MM) / 2.0 + projection_ft
    angle = math.radians(long_axis_deg)
    ux, uy = math.cos(angle), math.sin(angle)
    nx, ny = -uy, ux
    return [(cx + ux * half_long + nx * half_short,
             cy + uy * half_long + ny * half_short),
            (cx - ux * half_long + nx * half_short,
             cy - uy * half_long + ny * half_short),
            (cx - ux * half_long - nx * half_short,
             cy - uy * half_long - ny * half_short),
            (cx + ux * half_long - nx * half_short,
             cy + uy * half_long - ny * half_short)]


def circle_pad_ring(circle, projection_ft):
    """A square pad around a round column."""
    cx, cy = circle["center"][0], circle["center"][1]
    half = (circle["diameter_mm"] / _MM) / 2.0 + projection_ft
    return [(cx + half, cy + half), (cx - half, cy + half),
            (cx - half, cy - half), (cx + half, cy - half)]


def _curve_loop(ring):
    loop = CurveLoop()
    count = len(ring)
    for index in range(count):
        a = ring[index]
        b = ring[(index + 1) % count]
        loop.Append(Line.CreateBound(XYZ(a[0], a[1], 0.0),
                                     XYZ(b[0], b[1], 0.0)))
    return loop


def _zero_offset(instance):
    """Sit the pad ON the level: no height offset, however the type is set up."""
    for builtin in (BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM,
                    BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM):
        try:
            parameter = instance.get_Parameter(builtin)
        except Exception:
            parameter = None
        if parameter is not None and not parameter.IsReadOnly:
            try:
                parameter.Set(0.0)
            except Exception:
                pass


def place_footings(doc, sections, base_type_id, level_id, projection_mm=300.0,
                   thickness_mm=0.0, region_max_side_mm=None):
    """One foundation pad per column footprint, on `level_id` at zero offset.

    `projection_mm` is how far the pad reaches past the column on EVERY side, so
    the pad is (column + 2 x projection). `thickness_mm` of 0 keeps the picked
    type's own thickness.

    Returns {"created": [ids], "skipped": [reasons], "errors": [reasons]}.
    """
    base_type = doc.GetElement(base_type_id)
    level = doc.GetElement(level_id)
    result = {"created": [], "skipped": [], "errors": []}
    if base_type is None or level is None:
        raise ValueError("foundation type or level could not be resolved")

    region_max = (_MAX_COLUMN_MIN_SIDE_MM if region_max_side_mm is None
                  else region_max_side_mm)
    projection_ft = float(projection_mm or 0.0) / _MM
    cache = {}
    floor_type = _resolve_type(doc, base_type, thickness_mm, cache)

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
                ring = pad_ring(rectangle, projection_ft)
                loops = List[CurveLoop]()
                loops.Add(_curve_loop(ring))
                instance = Floor.Create(doc, loops, floor_type.Id, level.Id)
                _zero_offset(instance)
                mark = rectangle.get("mark")
                if mark:
                    set_element_mark(instance, "F-{0}".format(mark))
                result["created"].append(instance.Id)
            except Exception as creation_error:
                result["errors"].append(str(creation_error))

    for circle in sections.get("circles", []) or []:
        try:
            ring = circle_pad_ring(circle, projection_ft)
            loops = List[CurveLoop]()
            loops.Add(_curve_loop(ring))
            instance = Floor.Create(doc, loops, floor_type.Id, level.Id)
            _zero_offset(instance)
            mark = circle.get("mark")
            if mark:
                set_element_mark(instance, "F-{0}".format(mark))
            result["created"].append(instance.Id)
        except Exception as creation_error:
            result["errors"].append(str(creation_error))
    return result

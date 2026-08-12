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
from .. import footing_plan
from .. import naming
from .. import type_names

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
    """(FloorType, note) of this thickness, duplicated off the base and cached.

    A None type means the name could not be had. That used to fall back to the
    BASE type and say nothing, which cast the pad at whatever depth the picked
    type happened to carry -- a wrong foundation, silently. The caller now skips
    the pad and reports instead.
    """
    if not thickness_mm:
        return base_type, None
    key = int(round(thickness_mm))
    if key in cache:
        return cache[key]
    name = naming.footing_type_name(key)
    floor_type, created, note = type_names.resolve_type(
        base_type, name, lambda: _sibling_types(doc, base_type))
    if created:
        _set_thickness(floor_type, thickness_mm)
    cache[key] = (floor_type, note)
    return floor_type, note


def _sibling_types(doc, base_type):
    """(name, FloorType) for the types in the SAME system family as base_type.

    Foundation Slabs and Floors are both FloorType but different system
    families, and Revit scopes type-name uniqueness to the family. Scanning
    every FloorType could hand a plain FLOOR type back for a pad, filing the
    foundation under the wrong category.
    """
    wanted = _system_family(base_type)
    rows = []
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        if _system_family(floor_type) != wanted:
            continue
        rows.append((get_element_name(floor_type), floor_type))
    return rows


def _system_family(floor_type):
    """The system family a floor type belongs to ("Floor", "Foundation Slab")."""
    try:
        return floor_type.FamilyName
    except Exception:
        return None


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
                   thickness_mm=600.0, region_max_side_mm=None):
    """One foundation pad per column GROUP, on `level_id` at zero offset.

    The layout comes from footing_plan: pads are the column footprints grown by
    `projection_mm` on every side, OVERLAPPING pads are fused into one combined
    footing, and each pad's thickness follows its plan area around
    `thickness_mm` (the depth at one square metre).

    Returns {"created": [ids], "skipped": [reasons], "errors": [reasons]}.
    """
    base_type = doc.GetElement(base_type_id)
    level = doc.GetElement(level_id)
    result = {"created": [], "skipped": [], "errors": [], "notes": [],
              "merged": 0}
    if base_type is None or level is None:
        raise ValueError("foundation type or level could not be resolved")

    region_max = (_MAX_COLUMN_MIN_SIDE_MM if region_max_side_mm is None
                  else region_max_side_mm)
    plans = footing_plan.plan_pads(sections, projection_mm, thickness_mm,
                                   region_max)
    singles = len(footing_plan.pads_for(sections, projection_mm, region_max))
    result["merged"] = max(0, singles - len(plans))
    cache = {}
    for ring, pad_thickness, mark in plans:
        try:
            floor_type, note = _resolve_type(doc, base_type, pad_thickness, cache)
            type_names.record(result, note)
            if floor_type is None:
                result["skipped"].append(
                    "no foundation type for a {0} mm pad".format(pad_thickness))
                continue
            loops = List[CurveLoop]()
            loops.Add(_curve_loop(ring))
            instance = Floor.Create(doc, loops, floor_type.Id, level.Id)
            _zero_offset(instance)
            if mark:
                set_element_mark(instance, mark)
            result["created"].append(instance.Id)
        except Exception as creation_error:
            result["errors"].append(str(creation_error))
    return result

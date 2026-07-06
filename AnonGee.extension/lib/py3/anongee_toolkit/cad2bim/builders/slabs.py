# -*- coding: utf-8 -*-
"""PROTOTYPE: place floor slabs from derived slab loops (see slabs_proto.py).

Status: prototype, NOT wired into the pushbutton -- beams first. Mirrors the
column/beam builders: a base floor type is duplicated per thickness ("150 THK")
and cached; a loop with no thickness inherits the picked type. Runs inside a
caller-owned Transaction; one bad loop never fails the batch.
"""

from Autodesk.Revit.DB import (FilteredElementCollector, XYZ, Line, CurveLoop,
                               Floor, FloorType, BuiltInParameter)

from ..unit_convert import mm_to_internal
from ..compat import get_element_name


def floor_types(doc):
    """[(label, ElementId)] of the model's floor types."""
    types = (FilteredElementCollector(doc).OfClass(FloorType).ToElements())
    rows = [(get_element_name(ft), ft.Id) for ft in types]
    return sorted(rows, key=lambda pair: pair[0])


def place_slabs(doc, slabs, base_type_id, level_id):
    """Place one floor per slab dict {ring, z, mark, thickness_mm}.

    ring: [(x, y), ...] internal feet, closed implicitly. thickness_mm duplicates
    the base type sized to that thickness; None keeps the base type as-is.
    """
    base_type = doc.GetElement(base_type_id)
    level = doc.GetElement(level_id)
    if base_type is None or level is None:
        raise ValueError("floor type or level could not be resolved")

    cache = {}
    result = {"created": [], "skipped": [], "errors": []}
    for slab in slabs:
        try:
            ring = slab["ring"]
            if len(ring) < 3:
                result["skipped"].append("degenerate loop")
                continue
            loop = CurveLoop()
            n = len(ring)
            for i in range(n):
                x1, y1 = ring[i]
                x2, y2 = ring[(i + 1) % n]
                loop.Append(Line.CreateBound(XYZ(x1, y1, 0.0), XYZ(x2, y2, 0.0)))
            floor_type = _resolve_type(doc, base_type, slab.get("thickness_mm"), cache)
            instance = Floor.Create(doc, [loop], floor_type.Id, level.Id)
            _set_mark(instance, slab.get("mark"))
            result["created"].append(instance.Id)
        except Exception as placement_error:
            result["errors"].append(str(placement_error))
    return result


def _resolve_type(doc, base_type, thickness_mm, cache):
    """Floor type of the given thickness, duplicating + caching off the base type."""
    if thickness_mm is None:
        return base_type
    key = int(round(thickness_mm))
    if key in cache:
        return cache[key]
    name = "{0} THK".format(key)
    existing = _find_type(doc, base_type, name)
    if existing is not None:
        cache[key] = existing
        return existing
    new_type = base_type.Duplicate(name)
    _set_thickness(new_type, thickness_mm)
    cache[key] = new_type
    return new_type


def _find_type(doc, base_type, name):
    for ft in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        if get_element_name(ft) == name:
            return ft
    return None


def _set_thickness(floor_type, thickness_mm):
    """Resize the type's structural core layer to the labelled thickness."""
    try:
        structure = floor_type.GetCompoundStructure()
        index = structure.GetFirstCoreLayerIndex()
        structure.SetLayerWidth(index, mm_to_internal(thickness_mm))
        floor_type.SetCompoundStructure(structure)
    except Exception:
        pass   # thickness is best-effort; the loop still places at type default


def _set_mark(instance, mark):
    if not mark:
        return
    try:
        parameter = instance.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(str(mark))
    except Exception:
        pass

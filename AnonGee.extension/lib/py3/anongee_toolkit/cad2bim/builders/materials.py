# -*- coding: utf-8 -*-
"""Give the elements this run creates their structural MATERIAL.

The dialog offers one material per element kind (column, beam, slab, stair,
footing). The material is written onto the TYPE, not the instance, because that
is where Revit keeps a structural member's material and because every element of
one size shares a duplicated type anyway -- so a single write covers the lot.

Two shapes of parameter have to be handled:

  * framing, columns and foundations carry STRUCTURAL_MATERIAL_PARAM directly;
  * a floor keeps its material in the COMPOUND STRUCTURE, one per layer, so the
    material goes on the structural layer (the thick one) instead.

Nothing here is essential to a build: a family that exposes no material
parameter, or a read-only one, is reported and skipped rather than failing the
run. This module performs Revit writes and must run inside a Transaction.
"""

from Autodesk.Revit.DB import (BuiltInParameter, FilteredElementCollector,
                               Material)

from ..compat import get_element_name

# The element kinds the dialog can assign a material to.
KINDS = ("column", "beam", "slab", "stair", "footing")

# Names tried when a family exposes its material as a plain shared parameter
# instead of the built-in one (common in imported/office families).
_LOOKUP_NAMES = ("Structural Material", "Material", "Concrete Material",
                 "Material: Structural")


def materials(doc):
    """[(name, ElementId)] of every material in the model, sorted by name."""
    rows = []
    for material in FilteredElementCollector(doc).OfClass(Material).ToElements():
        try:
            rows.append((get_element_name(material), material.Id))
        except Exception:
            continue
    return sorted(rows, key=lambda pair: pair[0].lower())


def _set_material_parameter(element, material_id):
    """True when `element` took the material through a parameter it exposes."""
    if element is None or material_id is None:
        return False
    parameter = None
    try:
        parameter = element.get_Parameter(
            BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
    except Exception:
        parameter = None
    if parameter is None or parameter.IsReadOnly:
        for name in _LOOKUP_NAMES:
            try:
                candidate = element.LookupParameter(name)
            except Exception:
                candidate = None
            if candidate is not None and not candidate.IsReadOnly:
                parameter = candidate
                break
    if parameter is None or parameter.IsReadOnly:
        return False
    try:
        return bool(parameter.Set(material_id))
    except Exception:
        return False


def _set_floor_material(floor_type, material_id):
    """Put the material on a floor type's STRUCTURAL layer.

    A floor's material lives in its compound structure, so the plain parameter
    route does not reach it. The structural layer is the one Revit flags as the
    structural deck, falling back to the thickest layer.
    """
    try:
        structure = floor_type.GetCompoundStructure()
    except Exception:
        return False
    if structure is None:
        return False
    try:
        count = structure.LayerCount
        best, best_width = None, -1.0
        core = -1
        try:
            core = structure.GetFirstCoreLayerIndex()
        except Exception:
            core = -1
        for index in range(count):
            width = structure.GetLayerWidth(index)
            if index == core:
                best, best_width = index, float("inf")
                break
            if width > best_width:
                best, best_width = index, width
        if best is None:
            return False
        structure.SetMaterialId(best, material_id)
        floor_type.SetCompoundStructure(structure)
        return True
    except Exception:
        return False


def apply(doc, element_types, material_id, kind):
    """Write `material_id` onto each type in `element_types`.

    Returns (applied, skipped) counts. `kind` only decides which route is tried
    first -- a floor type still falls back to the plain parameter when it has
    no compound structure (a face-based or in-place floor).
    """
    if material_id is None:
        return 0, 0
    applied = 0
    skipped = 0
    for element_type in element_types or []:
        if element_type is None:
            continue
        done = False
        if kind == "slab":
            done = _set_floor_material(element_type, material_id)
        if not done:
            done = _set_material_parameter(element_type, material_id)
        if done:
            applied += 1
        else:
            skipped += 1
    return applied, skipped


def types_of(doc, element_ids):
    """The distinct TYPES behind a list of created instance ids."""
    seen = {}
    for element_id in element_ids or []:
        try:
            element = doc.GetElement(element_id)
            if element is None:
                continue
            type_id = element.GetTypeId()
            if type_id is None:
                continue
            if type_id.IntegerValue in seen:
                continue
            element_type = doc.GetElement(type_id)
            if element_type is not None:
                seen[type_id.IntegerValue] = element_type
        except Exception:
            continue
    return list(seen.values())

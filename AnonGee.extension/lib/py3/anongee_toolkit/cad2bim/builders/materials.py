# -*- coding: utf-8 -*-
"""Give the elements this run creates their structural MATERIAL.

The dialog offers one material per element kind (column, beam, slab, stair,
footing). Where the material LIVES depends entirely on how the family was
built, so both places are tried for every element:

  * on the TYPE, which is where a structural member usually keeps it and where
    one write covers every element of that size;
  * on the INSTANCE, because plenty of families expose "Structural Material" as
    an instance parameter instead -- setting only the type leaves those
    elements unchanged, which is exactly what the user saw.

Two shapes of parameter also have to be handled:

  * framing, columns and foundations carry STRUCTURAL_MATERIAL_PARAM directly;
  * a floor (and a foundation pad, which is a floor) keeps its material in the
    COMPOUND STRUCTURE, one per layer, so the material goes on the structural
    layer instead;
  * a STAIR keeps its materials on the stair type's run/landing/support
    sub-parameters, none of which is the built-in structural one.

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
                 "Material: Structural", "Structural Material Parameter")

# A stair type spreads its materials over the tread, riser, landing and support
# parameters; there is no single structural one to set.
_STAIR_PARAM_NAMES = ("Monolithic Material", "Tread Material", "Riser Material",
                      "Landing Material", "Support Material",
                      "Structural Material", "Material")


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


def _set_stair_materials(stairs_type, material_id):
    """Set every material parameter a stair type exposes. True if any took."""
    done = False
    for name in _STAIR_PARAM_NAMES:
        try:
            parameter = stairs_type.LookupParameter(name)
        except Exception:
            parameter = None
        if parameter is None or parameter.IsReadOnly:
            continue
        try:
            if parameter.Set(material_id):
                done = True
        except Exception:
            continue
    return done


def apply(doc, elements, material_id, kind):
    """Write `material_id` onto every element AND its type.

    `elements` are the created instances. Both the type and the instance are
    written: a family may expose the material on either, and setting only the
    type leaves an instance-parameter family untouched.

    Returns (applied, skipped) -- applied counts elements whose material landed
    somewhere, skipped those that exposed no writable material anywhere.
    """
    if material_id is None:
        return 0, 0
    applied = 0
    skipped = 0
    seen_types = set()
    for element in elements or []:
        if element is None:
            continue
        done = False
        element_type = None
        try:
            type_id = element.GetTypeId()
            if type_id is not None:
                element_type = doc.GetElement(type_id)
        except Exception:
            element_type = None
        if element_type is not None:
            key = element_type.Id.IntegerValue
            if key in seen_types:
                done = True             # this type already took it
            else:
                if kind in ("slab", "footing"):
                    done = _set_floor_material(element_type, material_id)
                if not done and kind == "stair":
                    done = _set_stair_materials(element_type, material_id)
                if not done:
                    done = _set_material_parameter(element_type, material_id)
                if done:
                    seen_types.add(key)
        # the instance too: many families put the material here, and a type
        # that took it is not overwritten by this -- it is the same value
        if _set_material_parameter(element, material_id):
            done = True
        if done:
            applied += 1
        else:
            skipped += 1
    return applied, skipped


def elements_of(doc, element_ids):
    """The live elements behind a list of created ids, skipping any that went."""
    out = []
    for element_id in element_ids or []:
        try:
            element = doc.GetElement(element_id)
        except Exception:
            element = None
        if element is not None:
            out.append(element)
    return out

# -*- coding: utf-8 -*-
"""
Element identity helpers — safely retrieve family and type names across all
Revit element kinds (FamilyInstance, system families, categories).
"""
from Autodesk.Revit.DB import ElementId
from anongee_toolkit.revit.application import get_current_doc


def get_family_name(element):
    """
    Return the Family Name of *element*.

    Resolution order:
      1. FamilyInstance.Symbol.Family.Name
      2. ElementType.Name  (system families such as Walls)
      3. Category.Name     (last resort)

    Returns ``"N/A"`` if the element is ``None`` or no name can be resolved.
    """
    if not element:
        return "N/A"

    try:
        if hasattr(element, "Symbol") and element.Symbol and element.Symbol.Family:
            return element.Symbol.Family.Name
    except Exception:
        pass

    try:
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            elem_type = get_current_doc().GetElement(type_id)
            if elem_type:
                return elem_type.Name
    except Exception:
        pass

    if element.Category:
        return element.Category.Name

    return "N/A"


def get_type_name(element):
    """
    Return the Type Name of *element*, or ``"N/A"`` if it cannot be resolved.
    """
    if not element:
        return "N/A"

    try:
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            elem_type = get_current_doc().GetElement(type_id)
            if elem_type:
                return elem_type.Name
    except Exception:
        pass

    return "N/A"

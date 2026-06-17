# -*- coding: utf-8 -*-
from Autodesk.Revit.DB import ElementId
from anongee_toolkit.core import get_current_doc

def get_family_name(element):
    """
    Safely extracts the Family Name of an element.
    Falls back to ElementType Name, then Category Name if it's a System Family.
    """
    if not element:
        return "N/A"

    try:
        # 1. Try if it's a FamilyInstance (has a Symbol)
        if hasattr(element, "Symbol") and element.Symbol:
            if element.Symbol.Family:
                return element.Symbol.Family.Name
    except Exception:
        pass

    try:
        # 2. Try falling back to ElementType (System Families like Walls)
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            doc = get_current_doc()
            elem_type = doc.GetElement(type_id)
            if elem_type:
                return elem_type.Name
    except Exception:
        pass

    # 3. Ultimate fallback: Category Name
    if element.Category:
        return element.Category.Name

    return "N/A"

def get_type_name(element):
    """
    Safely extracts the Type Name of an element.
    """
    if not element:
        return "N/A"
        
    try:
        type_id = element.GetTypeId()
        if type_id and type_id != ElementId.InvalidElementId:
            doc = get_current_doc()
            elem_type = doc.GetElement(type_id)
            if elem_type:
                return elem_type.Name
    except Exception:
        pass
        
    return "N/A"
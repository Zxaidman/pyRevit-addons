# -*- coding: utf-8 -*-
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
from anongee_toolkit.selection import get_selected_elements
from anongee_toolkit.core import get_current_doc, get_current_uidoc

def get_rebars(doc=None, uidoc=None):
    """
    Attempts to get rebars from the active selection. 
    If none are selected, falls back to collecting all rebars in the document.
    
    Returns:
        tuple: (list_of_rebars, is_selection_bool)
    """
    doc = doc if doc else get_current_doc()
    uidoc = uidoc if uidoc else get_current_uidoc()
    
    # 1. Try Selection First
    selected_elems = get_selected_elements(uidoc, doc)
    rebars = [
        e for e in selected_elems 
        if getattr(getattr(e, "Category", None), "Id", None) 
        and e.Category.Id.IntegerValue == int(BuiltInCategory.OST_Rebar)
    ]
    
    if rebars:
        return rebars, True
        
    # 2. Fallback to All Rebars
    rebars = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Rebar)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    return rebars, False
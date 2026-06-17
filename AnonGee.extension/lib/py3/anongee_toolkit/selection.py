# -*- coding: utf-8 -*-
from System.Collections.Generic import List as ListT
from Autodesk.Revit.DB import ElementId
from anongee_toolkit.core import get_current_uidoc, get_current_doc

def get_selected_elements(uidoc=None, doc=None):
    """
    Retrieves the currently selected elements in the Revit UI.
    Fail-Fast: Returns an empty list if nothing is selected.
    """
    uidoc = uidoc if uidoc else get_current_uidoc()
    doc = doc if doc else get_current_doc()
    
    selected_ids = uidoc.Selection.GetElementIds()
    if not selected_ids:
        return []
        
    return [doc.GetElement(e_id) for e_id in selected_ids if doc.GetElement(e_id)]

def set_selection(element_ids, uidoc=None):
    """
    Highlights/Selects the provided ElementIds in the active Revit UI.
    Abstracts the painful CPython3 System.Collections.Generic.List mapping.
    """
    if not element_ids:
        return False
        
    uidoc = uidoc if uidoc else get_current_uidoc()
    
    # Instantiate a strongly typed C# List required by Revit API
    csharp_list = ListT[ElementId]()
    for e_id in element_ids:
        if isinstance(e_id, ElementId):
            csharp_list.Add(e_id)
            
    if csharp_list.Count > 0:
        uidoc.Selection.SetElementIds(csharp_list)
        return True
        
    return False
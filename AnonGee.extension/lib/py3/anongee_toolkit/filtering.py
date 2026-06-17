# -*- coding: utf-8 -*-
from System.Collections.Generic import List as ListT
from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementMulticategoryFilter, ElementId
)
from anongee_toolkit.core import get_current_doc

def get_elements_by_categories(category_names, view_id=None, doc=None):
    """
    Retrieves all elements belonging to a specific list of category names.
    
    Args:
        category_names (list): List of category names as strings (e.g., ["Doors", "Windows"]).
        view_id (ElementId, optional): If provided, filters only in the specified view.
        doc (Document, optional): The Revit Document.
        
    Returns:
        list: A Python list of Revit Elements.
    """
    if not category_names:
        return []

    doc = doc if doc else get_current_doc()
    
    # 1. Match string names to Category Ids
    cat_ids = [c.Id for c in doc.Settings.Categories if c.Name in category_names]
    if not cat_ids:
        return []

    # 2. Build C# List for the MulticategoryFilter
    cat_list = ListT[ElementId]()
    for cid in cat_ids:
        cat_list.Add(cid)
        
    multi_filter = ElementMulticategoryFilter(cat_list)
    
    # 3. Apply Collector
    if view_id:
        collector = FilteredElementCollector(doc, view_id)
    else:
        collector = FilteredElementCollector(doc)
        
    return list(collector.WherePasses(multi_filter).WhereElementIsNotElementType().ToElements())
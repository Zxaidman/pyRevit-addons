# -*- coding: utf-8 -*-
"""
Element collection helpers built on FilteredElementCollector.
"""
from System.Collections.Generic import List as ListT
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    ElementMulticategoryFilter,
    ElementId,
)
from anongee_toolkit.revit.application import get_current_doc


def get_elements_by_categories(category_names, view_id=None, doc=None):
    """
    Collect all non-type elements that belong to the given category names.

    Args:
        category_names (list[str]): Revit category names, e.g. ``["Doors", "Windows"]``.
        view_id (ElementId, optional): Restrict the collector to this view.
        doc (Document, optional): Target document; defaults to the active document.

    Returns:
        list[Element]: Matching elements, or an empty list if none found.
    """
    if not category_names:
        return []

    doc = doc or get_current_doc()

    cat_ids = [c.Id for c in doc.Settings.Categories if c.Name in category_names]
    if not cat_ids:
        return []

    cat_list = ListT[ElementId]()
    for cid in cat_ids:
        cat_list.Add(cid)

    multi_filter = ElementMulticategoryFilter(cat_list)
    collector = (
        FilteredElementCollector(doc, view_id)
        if view_id
        else FilteredElementCollector(doc)
    )

    return list(
        collector
        .WherePasses(multi_filter)
        .WhereElementIsNotElementType()
        .ToElements()
    )

# -*- coding: utf-8 -*-
"""
Helpers for reading and writing the active Revit UI selection.

Abstracts the CPython3/pythonnet ``System.Collections.Generic.List`` mapping
that Revit's Selection API requires.
"""
from System.Collections.Generic import List as ListT
from Autodesk.Revit.DB import ElementId
from anongee_toolkit.revit.application import get_current_uidoc, get_current_doc


def get_selected_elements(uidoc=None, doc=None):
    """
    Return the currently selected elements as a Python list.

    Returns an empty list when nothing is selected.
    """
    uidoc = uidoc or get_current_uidoc()
    doc = doc or get_current_doc()

    selected_ids = uidoc.Selection.GetElementIds()
    if not selected_ids:
        return []

    return [doc.GetElement(eid) for eid in selected_ids if doc.GetElement(eid)]


def set_selection(element_ids, uidoc=None):
    """
    Highlight *element_ids* in the active Revit UI.

    Args:
        element_ids (iterable[ElementId]): ElementIds to select.
        uidoc (UIDocument, optional): Defaults to the active UIDocument.

    Returns:
        bool: ``True`` if at least one element was selected.
    """
    if not element_ids:
        return False

    uidoc = uidoc or get_current_uidoc()

    csharp_list = ListT[ElementId]()
    for eid in element_ids:
        if isinstance(eid, ElementId):
            csharp_list.Add(eid)

    if csharp_list.Count > 0:
        uidoc.Selection.SetElementIds(csharp_list)
        return True

    return False

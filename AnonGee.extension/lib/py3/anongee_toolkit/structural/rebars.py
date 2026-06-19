# -*- coding: utf-8 -*-
"""
Rebar collection helper.

Tries the active UI selection first; falls back to a whole-document collect
so callers never need to branch on "did the user pre-select anything?".
"""
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
from anongee_toolkit.revit.application import get_current_doc, get_current_uidoc
from anongee_toolkit.revit.selection import get_selected_elements

_REBAR_CATEGORY_INT = int(BuiltInCategory.OST_Rebar)


def get_rebars(doc=None, uidoc=None):
    """
    Return rebars from the active selection, or all rebars in the document.

    Args:
        doc (Document, optional): Defaults to the active document.
        uidoc (UIDocument, optional): Defaults to the active UIDocument.

    Returns:
        tuple[list[Element], bool]: ``(rebars, is_from_selection)``
    """
    doc   = doc   or get_current_doc()
    uidoc = uidoc or get_current_uidoc()

    selected = get_selected_elements(uidoc, doc)
    rebars = [
        e for e in selected
        if (
            getattr(getattr(e, "Category", None), "Id", None)
            and e.Category.Id.IntegerValue == _REBAR_CATEGORY_INT
        )
    ]
    if rebars:
        return rebars, True

    rebars = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Rebar)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    return rebars, False

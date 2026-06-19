# -*- coding: utf-8 -*-
"""
View enumeration and labelling utilities.

Filters the document's views to the subset that is meaningful for element
visibility and annotation work (plans, sections, elevations, 3-D views).
"""
from Autodesk.Revit.DB import FilteredElementCollector, View, ViewType
from anongee_toolkit.revit.application import get_current_doc

ALLOWED_VIEW_TYPES = frozenset({
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.EngineeringPlan,
    ViewType.Section,
    ViewType.Elevation,
    ViewType.ThreeD,
})

_VIEW_TYPE_LABELS = {
    ViewType.FloorPlan:       "Floor Plan",
    ViewType.CeilingPlan:     "Ceiling Plan",
    ViewType.EngineeringPlan: "Structural Plan",
    ViewType.Section:         "Section",
    ViewType.Elevation:       "Elevation",
    ViewType.ThreeD:          "3D",
}


def get_view_label(view):
    """Return ``"<view name> [<type label>]"`` for a given View."""
    label = _VIEW_TYPE_LABELS.get(view.ViewType, str(view.ViewType))
    return "{} [{}]".format(view.Name, label)


def get_eligible_views(doc=None):
    """
    Return a name-sorted list of non-template views of allowed types.

    Args:
        doc (Document, optional): Defaults to the active document.

    Returns:
        list[View]
    """
    doc = doc or get_current_doc()
    all_views = (
        FilteredElementCollector(doc)
        .OfClass(View)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    return sorted(
        [v for v in all_views if not v.IsTemplate and v.ViewType in ALLOWED_VIEW_TYPES],
        key=lambda v: v.Name,
    )

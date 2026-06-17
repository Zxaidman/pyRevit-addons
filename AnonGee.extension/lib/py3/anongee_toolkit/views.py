# -*- coding: utf-8 -*-
from Autodesk.Revit.DB import FilteredElementCollector, View, ViewType
from anongee_toolkit.core import get_current_doc

ALLOWED_VIEW_TYPES = {
    ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.EngineeringPlan,
    ViewType.Section, ViewType.Elevation, ViewType.ThreeD,
}

VIEW_TYPE_LABELS = {
    ViewType.ThreeD: "3D", ViewType.EngineeringPlan: "Structural Plan",
    ViewType.FloorPlan: "Floor Plan", ViewType.CeilingPlan: "Ceiling Plan",
    ViewType.Section: "Section", ViewType.Elevation: "Elevation",
}

def get_view_label(view):
    """Returns a formatted string: View Name [View Type Label]"""
    label = VIEW_TYPE_LABELS.get(view.ViewType, str(view.ViewType))
    return "{} [{}]".format(view.Name, label)

def get_eligible_views(doc=None):
    """Returns a sorted list of non-template views of allowed types."""
    doc = doc if doc else get_current_doc()
    all_views = FilteredElementCollector(doc).OfClass(View).WhereElementIsNotElementType().ToElements()
    
    return sorted(
        [v for v in all_views if not v.IsTemplate and v.ViewType in ALLOWED_VIEW_TYPES],
        key=lambda v: v.Name
    )
# -*- coding: utf-8 -*-
"""
anongee_toolkit.revit
~~~~~~~~~~~~~~~~~~~~~
Revit API abstraction layer — safe document/app access, element queries,
parameter I/O, transaction management, geometry helpers, unit conversions,
and view utilities.
"""
from anongee_toolkit.revit.application import get_app, get_current_uidoc, get_current_doc
from anongee_toolkit.revit.compatibility import create_element_id, get_element_id_value
from anongee_toolkit.revit.elements import get_family_name, get_type_name
from anongee_toolkit.revit.filtering import get_elements_by_categories
from anongee_toolkit.revit.geometry import get_solid_volume_m3, bounding_boxes_overlap
from anongee_toolkit.revit.parameters import get_parameter, get_parameter_value, set_parameter_value
from anongee_toolkit.revit.selection import get_selected_elements, set_selection
from anongee_toolkit.revit.transactions import (
    SuppressWarningsPreprocessor,
    RevitTransaction,
    RevitTransactionGroup,
)
from anongee_toolkit.revit.units import (
    m_to_mm, mm_to_ft, m_to_ft, ft_to_mm, clean_ft, strip_unit,
    CF_TO_M3, SF_TO_M2, FT_TO_MM, FT_TO_M,
)
from anongee_toolkit.revit.views import get_eligible_views, get_view_label

__all__ = [
    # application
    "get_app", "get_current_uidoc", "get_current_doc",
    # compatibility
    "create_element_id", "get_element_id_value",
    # elements
    "get_family_name", "get_type_name",
    # filtering
    "get_elements_by_categories",
    # geometry
    "get_solid_volume_m3", "bounding_boxes_overlap",
    # parameters
    "get_parameter", "get_parameter_value", "set_parameter_value",
    # selection
    "get_selected_elements", "set_selection",
    # transactions
    "SuppressWarningsPreprocessor", "RevitTransaction", "RevitTransactionGroup",
    # units
    "CF_TO_M3", "SF_TO_M2", "FT_TO_MM", "FT_TO_M",
    "m_to_mm", "mm_to_ft", "m_to_ft", "ft_to_mm", "clean_ft", "strip_unit",
    # views
    "get_eligible_views", "get_view_label",
]

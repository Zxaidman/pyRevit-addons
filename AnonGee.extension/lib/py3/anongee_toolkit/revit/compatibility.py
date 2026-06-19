# -*- coding: utf-8 -*-
"""
Revit API version compatibility shims.

Revit 2024 changed ElementId's underlying integer type from System.Int32 to
System.Int64.  The helpers here abstract that difference so all other modules
can work across Revit 2023 and 2024+.
"""
import System
from pyrevit import HOST_APP
from Autodesk.Revit.DB import ElementId


def create_element_id(id_value):
    """
    Create an ElementId from an integer, handling the Int32→Int64 change in
    Revit 2024.

    Args:
        id_value (int): Raw integer value of the ElementId.

    Returns:
        ElementId
    """
    if not isinstance(id_value, int):
        raise TypeError(
            "ElementId value must be an integer. Received: {}".format(type(id_value))
        )
    if int(HOST_APP.version) >= 2024:
        return ElementId(System.Int64(id_value))
    return ElementId(id_value)


def get_element_id_value(element_id):
    """
    Extract the integer value from an ElementId, handling the .Value / .IntegerValue
    API difference between Revit 2024+ and 2023.

    Args:
        element_id (ElementId): The ElementId to unpack.

    Returns:
        int
    """
    if not isinstance(element_id, ElementId):
        raise TypeError("Expected ElementId, got {}".format(type(element_id)))
    if int(HOST_APP.version) >= 2024:
        return int(element_id.Value)
    return element_id.IntegerValue

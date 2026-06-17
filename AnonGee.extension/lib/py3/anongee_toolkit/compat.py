# -*- coding: utf-8 -*-
import System
from pyrevit import HOST_APP
from Autodesk.Revit.DB import ElementId

def create_element_id(id_value):
    """
    Safely creates a Revit ElementId, automatically handling the Int64 
    changes introduced in Revit 2024.
    
    Args:
        id_value (int): The integer value of the ElementId.
        
    Returns:
        ElementId: A valid Revit ElementId object.
    """
    if not isinstance(id_value, int):
        raise TypeError("ElementId value must be an integer. Received: {}".format(type(id_value)))
    
    # Revit 2024 and above require System.Int64
    if int(HOST_APP.version) >= 2024:
        return ElementId(System.Int64(id_value))
    
    # Fallback for Revit 2023 and older
    return ElementId(id_value)

def get_element_id_value(element_id):
    """
    Safely extracts the integer value from an ElementId.
    
    Args:
        element_id (ElementId): The Revit ElementId.
        
    Returns:
        int: The integer value.
    """
    if not isinstance(element_id, ElementId):
        raise TypeError("Expected ElementId, got {}".format(type(element_id)))
        
    if int(HOST_APP.version) >= 2024:
        return int(element_id.Value)
    else:
        return element_id.IntegerValue
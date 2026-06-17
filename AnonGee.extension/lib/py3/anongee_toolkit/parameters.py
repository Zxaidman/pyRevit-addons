# -*- coding: utf-8 -*-
from Autodesk.Revit.DB import StorageType, ElementId 
from anongee_toolkit.core import get_current_doc

def get_parameter(element, param_name):
    """
    Safely retrieves a Parameter object, checking the instance first, 
    and falling back to the ElementType if not found.
    """
    if not element or not param_name:
        return None

    # 1. Try Instance Parameter
    param = element.LookupParameter(param_name)
    if param is not None:
        return param

    # 2. Try Type Parameter
    doc = get_current_doc()
    type_id = element.GetTypeId()
    if type_id != ElementId.InvalidElementId:
        elem_type = doc.GetElement(type_id)
        if elem_type:
            return elem_type.LookupParameter(param_name)
            
    return None

def get_parameter_value(element, param_name, as_string=True):
    """
    Extracts the value of a parameter, handling Revit's StorageTypes.
    Includes advanced formatting for ElementId StorageTypes (returns '[ID] Element Name').
    
    Args:
        element: Revit Element.
        param_name (str): Name of the parameter.
        as_string (bool): If True, forces the return value to be a string format.
    """
    param = get_parameter(element, param_name)
    if not param:
        return None

    st = param.StorageType

    # Advanced Handling: ElementId resolution
    if st == StorageType.ElementId:
        eid = param.AsElementId()
        # Handle Revit 2024 Int64 and Revit 2023 int values
        eid_val = getattr(eid, "Value", getattr(eid, "IntegerValue", -1))
        
        if eid_val != -1:
            doc = get_current_doc()
            ref_elem = doc.GetElement(eid)
            name = ref_elem.Name if ref_elem else (param.AsValueString() or "Unknown")
            val_str = "[{}] {}".format(eid_val, name)
            return val_str if as_string else eid
        return "None" if as_string else None

    # Handle standard string, int, double
    val_str = param.AsValueString()
    if val_str is None:
        if st == StorageType.String:
            val_str = param.AsString()
        elif st == StorageType.Integer:
            val_str = str(param.AsInteger())
        elif st == StorageType.Double:
            val_str = str(param.AsDouble())

    if not as_string:
        if st == StorageType.Integer: return param.AsInteger()
        if st == StorageType.Double: return param.AsDouble()
        return val_str

    return val_str if val_str is not None else ""

def set_parameter_value(element, param_name, value):
    """
    Safely sets a parameter value based on its StorageType.
    Fail-Fast: Returns False if parameter is read-only or not found.
    """
    param = get_parameter(element, param_name)
    if not param or param.IsReadOnly:
        return False

    st = param.StorageType
    try:
        if st == StorageType.String:
            param.Set(str(value) if value is not None else "")
        elif st == StorageType.Integer:
            # Try SetValueString first (handles unit conversions natively), fallback to integer
            if not param.SetValueString(str(value)):
                param.Set(int(float(value)) if value else 0)
        elif st == StorageType.Double:
            if not param.SetValueString(str(value)):
                param.Set(float(value) if value else 0.0)
        elif st == StorageType.ElementId:
            param.Set(value if isinstance(value, ElementId) else ElementId.InvalidElementId)
        return True
    except Exception:
        return False
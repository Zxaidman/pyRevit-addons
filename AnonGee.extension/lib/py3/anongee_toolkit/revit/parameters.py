# -*- coding: utf-8 -*-
"""
Parameter read/write helpers.

Handles all four Revit StorageTypes (String, Integer, Double, ElementId) and
resolves instance parameters before falling back to the element's type.
"""
from Autodesk.Revit.DB import StorageType, ElementId
from anongee_toolkit.revit.application import get_current_doc


def get_parameter(element, param_name):
    """
    Return the Parameter named *param_name* from *element*.

    Checks the element instance first, then its ElementType.
    Returns ``None`` if not found.
    """
    if not element or not param_name:
        return None

    param = element.LookupParameter(param_name)
    if param is not None:
        return param

    doc = get_current_doc()
    type_id = element.GetTypeId()
    if type_id != ElementId.InvalidElementId:
        elem_type = doc.GetElement(type_id)
        if elem_type:
            return elem_type.LookupParameter(param_name)

    return None


def get_parameter_value(element, param_name, as_string=True):
    """
    Return the value of *param_name* on *element*.

    For ElementId parameters the return format is ``"[<id>] <element name>"``.

    Args:
        element: Revit Element.
        param_name (str): Parameter name.
        as_string (bool): When ``True`` (default) always returns a ``str``;
            when ``False`` returns the native Python type.

    Returns:
        str | int | float | ElementId | None
    """
    param = get_parameter(element, param_name)
    if not param:
        return None

    st = param.StorageType

    if st == StorageType.ElementId:
        eid = param.AsElementId()
        eid_val = getattr(eid, "Value", getattr(eid, "IntegerValue", -1))
        if eid_val != -1:
            ref_elem = get_current_doc().GetElement(eid)
            name = ref_elem.Name if ref_elem else (param.AsValueString() or "Unknown")
            return "[{}] {}".format(eid_val, name) if as_string else eid
        return "None" if as_string else None

    val_str = param.AsValueString()
    if val_str is None:
        if st == StorageType.String:
            val_str = param.AsString()
        elif st == StorageType.Integer:
            val_str = str(param.AsInteger())
        elif st == StorageType.Double:
            val_str = str(param.AsDouble())

    if not as_string:
        if st == StorageType.Integer:
            return param.AsInteger()
        if st == StorageType.Double:
            return param.AsDouble()
        return val_str

    return val_str if val_str is not None else ""


def set_parameter_value(element, param_name, value):
    """
    Set *param_name* on *element* to *value*.

    Returns ``False`` if the parameter is read-only, not found, or if setting
    raises an exception; ``True`` on success.
    """
    param = get_parameter(element, param_name)
    if not param or param.IsReadOnly:
        return False

    st = param.StorageType
    try:
        if st == StorageType.String:
            param.Set(str(value) if value is not None else "")
        elif st == StorageType.Integer:
            if not param.SetValueString(str(value)):
                param.Set(int(float(value)) if value else 0)
        elif st == StorageType.Double:
            if not param.SetValueString(str(value)):
                param.Set(float(value) if value else 0.0)
        elif st == StorageType.ElementId:
            param.Set(
                value if isinstance(value, ElementId) else ElementId.InvalidElementId
            )
        return True
    except Exception:
        return False

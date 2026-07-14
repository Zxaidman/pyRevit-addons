#! python3
# -*- coding: utf-8 -*-

"""
Rotates selected columns sequentially by a dynamically calculated step angle.
Strictly uses pure Revit API via PythonNet to ensure CPython 3.12 compatibility.
"""

import math
import clr

# Load Revit API libraries directly via PythonNet
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI

def get_selected_elements(uidoc, doc):
    """Retrieve currently selected elements from the active document."""
    selection_ids = uidoc.Selection.GetElementIds()
    return [doc.GetElement(eid) for eid in selection_ids]

def filter_columns(elements):
    """
    Fail-Fast: Filter the selection to strictly Structural and Architectural columns.
    """
    columns = []
    allowed_categories = {
        int(DB.BuiltInCategory.OST_Columns), 
        int(DB.BuiltInCategory.OST_StructuralColumns)
    }
    
    for el in elements:
        if isinstance(el, DB.FamilyInstance) and el.Category:
            if el.Category.Id.IntegerValue in allowed_categories:
                columns.append(el)
    return columns

def get_element_location_point(element):
    """Safely extract the XYZ location of an element, handling slanted columns."""
    loc = element.Location
    if isinstance(loc, DB.LocationPoint):
        return loc.Point
    elif isinstance(loc, DB.LocationCurve):
        return loc.Curve.Evaluate(0.5, True) 
    return None

def sort_columns_spatially(columns):
    """
    Sort columns predictably by Y coordinate, then X coordinate.
    """
    def sort_key(col):
        pt = get_element_location_point(col)
        if pt:
            return (round(pt.Y, 3), round(pt.X, 3))
        return (0, 0)
    
    return sorted(columns, key=sort_key)

def rotate_column(doc, column, angle_degrees):
    """
    Rotates a single column around its internal Z-axis.
    Catches exceptions for pinned elements or group restrictions.
    """
    loc_point = get_element_location_point(column)
    if not loc_point:
        return False
        
    axis_start = loc_point
    axis_end = DB.XYZ(loc_point.X, loc_point.Y, loc_point.Z + 1.0)
    
    try:
        axis = DB.Line.CreateBound(axis_start, axis_end)
        angle_radians = math.radians(angle_degrees)
        DB.ElementTransformUtils.RotateElement(doc, column.Id, axis, angle_radians)
        return True
    except Exception as e:
        print(f"Failed to rotate column ID {column.Id}: {e}")
        return False

def show_dialog(title, message):
    """Helper for displaying native Revit UI dialogs."""
    UI.TaskDialog.Show(title, message)

def main():
    # Rely on pyRevit's built-in global context 
    app = __revit__.Application
    uidoc = __revit__.ActiveUIDocument
    doc = uidoc.Document

    # 1. Retrieve Selection
    selected_elements = get_selected_elements(uidoc, doc)
    if not selected_elements:
        show_dialog("Error", "Please select columns before running the script.")
        return

    # 2. Filter Columns
    columns = filter_columns(selected_elements)
    if not columns:
        show_dialog("Error", "No valid columns found in your selection.")
        return

    # 3. Sort Spatially
    sorted_columns = sort_columns_spatially(columns)
    total_columns = len(sorted_columns)
    
    # 4. Calculate Step Angle
    step_angle = 360.0 / total_columns

    # 5. Execute Rotation natively
    success_count = 0
    t = DB.Transaction(doc, "Sequential Column Rotation")
    t.Start()
    
    try:
        for index, col in enumerate(sorted_columns):
            current_target_angle = step_angle * (index + 1)
            if rotate_column(doc, col, current_target_angle):
                success_count += 1
        t.Commit()
    except Exception as e:
        t.RollBack()
        show_dialog("Transaction Failed", str(e))
        return
                
    # 6. Report Summary
    summary = (
        "Rotation Complete!\n\n"
        f"Total Columns Processed: {total_columns}\n"
        f"Successfully Rotated: {success_count}\n"
        f"Step Angle Increment: {step_angle:.3f}°"
    )
    show_dialog("Success", summary)

if __name__ == "__main__":
    main()
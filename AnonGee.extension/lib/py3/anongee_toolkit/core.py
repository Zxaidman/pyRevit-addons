# -*- coding: utf-8 -*-
import sys

def get_app():
    """
    Retrieves the Revit UIApplication instance (__revit__).
    Bypasses `pyrevit.revit` to prevent CPython3 interface crashes in events.py.
    """
    # Fetch __revit__ from the main execution script's namespace
    import __main__
    if hasattr(__main__, '__revit__'):
        return __main__.__revit__
        
    # Fallback to Python 3 builtins
    import builtins
    if hasattr(builtins, '__revit__'):
        return builtins.__revit__
        
    raise RuntimeError("Revit Application instance (__revit__) could not be resolved.")

def get_current_uidoc():
    """
    Retrieves the current active Revit UIDocument.
    Fail-Fast: Raises a RuntimeError immediately if no UI document is active.
    """
    app = get_app()
    uidoc = app.ActiveUIDocument
    if not uidoc:
        raise RuntimeError("No active Revit UI document found.")
    return uidoc

def get_current_doc():
    """
    Retrieves the current active Revit Document.
    Fail-Fast: Raises a RuntimeError immediately if no document is active.
    """
    uidoc = get_current_uidoc()
    doc = uidoc.Document
    if not doc:
        raise RuntimeError("No active Revit document found. Please open a project or family.")
    return doc
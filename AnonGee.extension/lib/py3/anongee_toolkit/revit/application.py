# -*- coding: utf-8 -*-
"""
Safe access to the Revit UIApplication, UIDocument, and Document.

Bypasses ``pyrevit.revit`` to prevent CPython3 interface crashes that occur
inside event callbacks and external-event handlers.
"""


def get_app():
    """Return the active Revit UIApplication (``__revit__``)."""
    import __main__
    if hasattr(__main__, "__revit__"):
        return __main__.__revit__

    import builtins
    if hasattr(builtins, "__revit__"):
        return builtins.__revit__

    raise RuntimeError(
        "__revit__ could not be resolved. "
        "Ensure this code runs inside a pyRevit script context."
    )


def get_current_uidoc():
    """Return the active UIDocument, or raise RuntimeError if none is open."""
    uidoc = get_app().ActiveUIDocument
    if not uidoc:
        raise RuntimeError("No active Revit UI document found.")
    return uidoc


def get_current_doc():
    """Return the active Document, or raise RuntimeError if none is open."""
    doc = get_current_uidoc().Document
    if not doc:
        raise RuntimeError(
            "No active Revit document found. Please open a project or family."
        )
    return doc

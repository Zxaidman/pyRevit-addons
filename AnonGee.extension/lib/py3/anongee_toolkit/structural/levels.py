# -*- coding: utf-8 -*-
"""Read the model's levels, and hand the name matching to something testable.

The matching itself is in :mod:`anongee_toolkit.rc_automation.naming`, which
imports no Revit and is unit-tested. What is left here is the part that needs a
document: reading the levels out of one, and turning matched names back into
element ids.
"""

from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB import Level

from anongee_toolkit.rc_automation import naming
from anongee_toolkit.revit.units import ft_to_mm

__version__ = "0.2.0"


def levels(doc):
    """``[(name, ElementId, elevation_mm)]``, lowest first."""
    found = []
    for level in FilteredElementCollector(doc).OfClass(Level).ToElements():
        try:
            found.append((level.Name, level.Id, ft_to_mm(level.Elevation)))
        except Exception:
            continue
    found.sort(key=lambda row: row[2])
    return found


def names(doc):
    """Just the names, for a message that has to list what is available."""
    return [name for name, _id, _elevation in levels(doc)]


def build_map(doc, wanted_names, overrides=None):
    """``({schedule name: ElementId}, notes, missing)``."""
    by_name = dict((name, element_id)
                   for name, element_id, _elevation in levels(doc))
    matched, notes, missing = naming.build_name_map(
        list(by_name), wanted_names, overrides)
    return (dict((wanted, by_name[found]) for wanted, found in matched.items()),
            notes, missing)

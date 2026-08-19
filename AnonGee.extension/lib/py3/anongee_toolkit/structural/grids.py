# -*- coding: utf-8 -*-
"""Turn a pair of grid names into a point. Reads only.

``GridX = A``, ``GridY = 1`` is how a drawing says where a footing goes, and the
only way of saying it that survives the model being moved.

The crossing arithmetic is in :mod:`anongee_toolkit.rc_automation.naming`, where
it can be tested. It is done by hand rather than through ``Curve.Intersect``
because that returns its answer through an ``out`` parameter, which needs a
``clr.Reference`` from CPython 3 and fails in ways that are tedious to diagnose
inside a modeless window. Two straight lines cross four multiplications away; a
curved grid is refused by name rather than approximated.
"""

from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB import Grid
from Autodesk.Revit.DB import Line

from anongee_toolkit.rc_automation import naming
from anongee_toolkit.revit.units import ft_to_mm

__version__ = "0.2.0"


def grids(doc):
    """``{name: Grid}`` for every grid in the model."""
    found = {}
    for grid in FilteredElementCollector(doc).OfClass(Grid).ToElements():
        try:
            found[grid.Name] = grid
        except Exception:
            continue
    return found


def names(doc):
    return sorted(grids(doc))


def segment_mm(grid):
    """``((x1, y1), (x2, y2))`` in mm, or ``None`` when it is not straight."""
    try:
        curve = grid.Curve
    except Exception:
        return None
    if not isinstance(curve, Line):
        return None
    try:
        start, end = curve.GetEndPoint(0), curve.GetEndPoint(1)
    except Exception:
        return None
    return ((ft_to_mm(start.X), ft_to_mm(start.Y)),
            (ft_to_mm(end.X), ft_to_mm(end.Y)))


def intersection_mm(doc_grids, name_x, name_y):
    """``((x, y), note)`` for a named grid intersection, in millimetres."""
    first, second = doc_grids.get(name_x), doc_grids.get(name_y)
    if first is None or second is None:
        absent = [n for n, g in ((name_x, first), (name_y, second))
                  if g is None]
        return None, "no grid named {0}".format(
            " or ".join("'{0}'".format(n) for n in absent))

    one, two = segment_mm(first), segment_mm(second)
    if one is None or two is None:
        return None, ("grid '{0}' or '{1}' is not a straight line, which this "
                      "release cannot cross".format(name_x, name_y))
    return naming.cross_segments(one, two)

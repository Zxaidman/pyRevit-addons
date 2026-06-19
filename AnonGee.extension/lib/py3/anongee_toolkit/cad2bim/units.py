# -*- coding: utf-8 -*-
"""Unit conversion -- the single source of truth for mm <-> Revit internal feet.

Rules from the implementation plan, enforced here:
  * Always use ForgeTypeId / UnitTypeId. DisplayUnitType is deprecated (Revit 2021)
    and must never appear in new code.
  * Geometry read back from a *linked* CAD is ALREADY in Revit internal units
    (decimal feet) with the DWG drawing-unit scale baked in by the link transform.
    It must never be rescaled. These helpers exist ONLY to convert our own
    millimetre inputs (future column/beam/slab dimensions), not CAD coordinates.
"""

from Autodesk.Revit.DB import UnitUtils, UnitTypeId


def mm_to_internal(value_mm):
    """Convert a millimetre value to Revit internal units (decimal feet).

    Raises ValueError if the input cannot be read as a number, rather than
    silently producing a wrong length.
    """
    try:
        return UnitUtils.ConvertToInternalUnits(float(value_mm), UnitTypeId.Millimeters)
    except (TypeError, ValueError):
        raise ValueError("mm_to_internal expected a number, got: {0!r}".format(value_mm))


def internal_to_mm(value_ft):
    """Convert a Revit internal-unit (feet) value to millimetres."""
    try:
        return UnitUtils.ConvertFromInternalUnits(float(value_ft), UnitTypeId.Millimeters)
    except (TypeError, ValueError):
        raise ValueError("internal_to_mm expected a number, got: {0!r}".format(value_ft))

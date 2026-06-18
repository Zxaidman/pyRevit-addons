# -*- coding: utf-8 -*-
"""
Geometry helpers — solid volume extraction and bounding-box overlap tests.
"""
from Autodesk.Revit.DB import Options, ViewDetailLevel, Solid, GeometryInstance

_CF_TO_M3 = 0.028316846592


def get_solid_volume_m3(element):
    """
    Return the total net solid volume of *element* in cubic metres.

    Iterates through all geometry objects and GeometryInstances safely.
    Returns ``0.0`` on any geometry error rather than raising.
    """
    total_cf = 0.0
    opts = Options()
    opts.ComputeReferences = False
    opts.DetailLevel = ViewDetailLevel.Medium

    try:
        geo = element.get_Geometry(opts)
        if not geo:
            return 0.0
        for obj in geo:
            if isinstance(obj, Solid):
                if obj.Volume > 1e-9:
                    total_cf += obj.Volume
            elif isinstance(obj, GeometryInstance):
                for inst_obj in obj.GetInstanceGeometry():
                    if isinstance(inst_obj, Solid) and inst_obj.Volume > 1e-9:
                        total_cf += inst_obj.Volume
    except Exception:
        pass

    return total_cf * _CF_TO_M3


def bounding_boxes_overlap(bb1, bb2, tol=0.08):
    """
    Return ``True`` if two BoundingBoxXYZ objects overlap in 3-D space.

    Args:
        bb1 (BoundingBoxXYZ): First bounding box.
        bb2 (BoundingBoxXYZ): Second bounding box.
        tol (float): Expansion tolerance in feet (default 0.08 ft ≈ 1 inch).

    Returns:
        bool: ``False`` if either box is ``None`` or the boxes are separated.
    """
    if bb1 is None or bb2 is None:
        return False

    return not (
        bb1.Max.X + tol < bb2.Min.X or bb1.Min.X - tol > bb2.Max.X
        or bb1.Max.Y + tol < bb2.Min.Y or bb1.Min.Y - tol > bb2.Max.Y
        or bb1.Max.Z + tol < bb2.Min.Z or bb1.Min.Z - tol > bb2.Max.Z
    )

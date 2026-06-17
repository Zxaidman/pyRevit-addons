# -*- coding: utf-8 -*-
from Autodesk.Revit.DB import Options, ViewDetailLevel, Solid, GeometryInstance

def get_solid_volume_m3(element):
    """
    Extracts the total net solid volume of an element in cubic meters.
    Iterates safely through GeometryInstances.
    """
    tot_vol_cf = 0.0
    geo_opt = Options()
    geo_opt.ComputeReferences = False
    geo_opt.DetailLevel = ViewDetailLevel.Medium

    try:
        geo_element = element.get_Geometry(geo_opt)
        if not geo_element:
            return 0.0

        for geom_obj in geo_element:
            if isinstance(geom_obj, Solid):
                if geom_obj.Volume > 1e-9:
                    tot_vol_cf += geom_obj.Volume
            elif isinstance(geom_obj, GeometryInstance):
                for inst_geom in geom_obj.GetInstanceGeometry():
                    if isinstance(inst_geom, Solid) and inst_geom.Volume > 1e-9:
                        tot_vol_cf += inst_geom.Volume
    except Exception:
        pass

    # Convert cubic feet to cubic meters
    return tot_vol_cf * 0.028316846592

def bounding_boxes_overlap(bb1, bb2, tol=0.08):
    """
    Checks if two Revit BoundingBoxes overlap in 3D space.
    Fail-Fast: Returns False if either bounding box is None.
    
    Args:
        bb1 (BoundingBoxXYZ): First bounding box.
        bb2 (BoundingBoxXYZ): Second bounding box.
        tol (float): Tolerance in decimal feet.
    """
    if bb1 is None or bb2 is None:
        return False
        
    # Check for separation across all 3 axes
    if (bb1.Max.X + tol < bb2.Min.X or bb1.Min.X - tol > bb2.Max.X or
        bb1.Max.Y + tol < bb2.Min.Y or bb1.Min.Y - tol > bb2.Max.Y or
        bb1.Max.Z + tol < bb2.Min.Z or bb1.Min.Z - tol > bb2.Max.Z):
        return False
        
    return True
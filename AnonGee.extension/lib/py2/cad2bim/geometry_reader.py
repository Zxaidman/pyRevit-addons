# -*- coding: utf-8 -*-
"""Extract curves from a linked CAD, already in Revit project coordinates.

Design choice -- transform handling
-----------------------------------
We recurse into every nested GeometryInstance with GetInstanceGeometry(), which
returns geometry already transformed into the project coordinate system at each
level. We therefore never compound transforms by hand.

  + Pro: impossible to double-transform (the documented failure mode when a
    transform is re-applied to geometry already returned in project coords).
  - Con: slightly more work than carrying SymbolGeometry + one compounded
    transform, because every block level is re-evaluated into project coords.

Units: the returned coordinates are in Revit internal feet with the DWG scale
already baked in by the link transform. They are stored verbatim -- never rescaled.
"""

from Autodesk.Revit.DB import (Options, GeometryInstance, PolyLine, Curve, Line,
                               Arc, ElementId)

from cad2bim.model import CurveRecord, ReadResult
from cad2bim.cad_links import describe_link

_ARC_SAMPLES = 0.5  # arcs are kept as start / mid / end so the arc can be rebuilt


def read_link(doc, import_instance):
    """Read one linked CAD instance into a ReadResult.

    Fail-fast on bad inputs; returns an empty ReadResult (not None) when the link
    genuinely has no geometry, so callers branch on .is_empty() consistently.
    """
    if doc is None or import_instance is None:
        raise ValueError("read_link requires both a document and an import instance")

    source_name = describe_link(doc, import_instance)
    geometry_element = import_instance.get_Geometry(Options())
    if geometry_element is None:
        return ReadResult(source_name, [])

    records = []
    _walk(doc, geometry_element, records)
    return ReadResult(source_name, records)


def _walk(doc, geometry_element, records):
    """Depth-first walk; appends a CurveRecord for every curve/polyline found."""
    for geom_obj in geometry_element:
        if isinstance(geom_obj, GeometryInstance):
            instance_geometry = geom_obj.GetInstanceGeometry()  # project coords
            if instance_geometry is not None:
                _walk(doc, instance_geometry, records)
            continue

        if isinstance(geom_obj, PolyLine):
            record = _polyline_to_record(doc, geom_obj)
            if record is not None:
                records.append(record)
            continue

        if isinstance(geom_obj, Curve):
            record = _curve_to_record(doc, geom_obj)
            if record is not None:
                records.append(record)
        # Solids, meshes, points and text are intentionally ignored by the reader.


def _curve_to_record(doc, curve):
    points = _curve_points(curve)
    if len(points) < 2:
        return None
    return CurveRecord(_curve_kind(curve), points, _layer_name(doc, curve),
                       _safe_length(curve))


def _polyline_to_record(doc, polyline):
    coords = polyline.GetCoordinates()
    points = [(p.X, p.Y, p.Z) for p in coords]
    if len(points) < 2:
        return None
    return CurveRecord("polyline", points, _layer_name(doc, polyline), None)


def _curve_kind(curve):
    name = type(curve).__name__
    if name == "Line":
        return "line"
    if name == "Arc":
        return "arc"
    return name.lower()  # ellipse, nurbspline, hermitespline, ...


def _curve_points(curve):
    """Sample a curve into (x, y, z) tuples in internal feet.

    Unbound curves (infinite construction lines, full circles) have no
    endpoints, so they are handled first: closed ones (circles/ellipses) are
    tessellated so a circular column is still captured; open infinite lines are
    skipped (return []), since they carry no structural geometry and Revit raises
    "curve is not bound" on any endpoint access. Bound lines keep two endpoints;
    bound arcs keep start/mid/end; any other bound curve is tessellated.
    """
    if not curve.IsBound:
        if getattr(curve, "IsClosed", False):
            return _safe_tessellate(curve)
        return []

    if isinstance(curve, Line):
        return [_xyz(curve.GetEndPoint(0)), _xyz(curve.GetEndPoint(1))]

    if isinstance(curve, Arc):
        return [_xyz(curve.GetEndPoint(0)),
                _xyz(curve.Evaluate(_ARC_SAMPLES, True)),
                _xyz(curve.GetEndPoint(1))]

    return _safe_tessellate(curve)


def _safe_tessellate(curve):
    """Tessellate to (x, y, z) tuples; return [] on any failure (caller skips it)."""
    try:
        return [_xyz(p) for p in curve.Tessellate()]
    except Exception:
        return []


def _safe_length(curve):
    try:
        return curve.Length
    except Exception:
        return None


def _layer_name(doc, geom_obj):
    """CAD layer name via GraphicsStyle.GraphicsStyleCategory.Name.

    GraphicsStyleId can be InvalidElementId for some primitives (a known gotcha
    that yields a null style), so every step is null-guarded and returns None.
    """
    try:
        style_id = geom_obj.GraphicsStyleId
        if style_id is None or style_id == ElementId.InvalidElementId:
            return None
        style = doc.GetElement(style_id)
        if style is None:
            return None
        category = style.GraphicsStyleCategory
        if category is None:
            return None
        return category.Name
    except Exception:
        return None


def _xyz(point):
    return (point.X, point.Y, point.Z)

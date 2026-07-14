# -*- coding: utf-8 -*-
"""Self Dimension.

Dimensions a selected element's own extents, measured along the element's
OWN orientation, on whichever axes lie in the active view's plane:

    Plan view          -> element local X + local Y      (width + depth)
    Elevation / section -> in-plane horizontal + world Z (width + height)

Usage:
    * Select one (or several) solid elements -> each is dimensioned.
        Family instances (column, framing, foundation, generic model),
        walls, and floors/slabs are supported.
    * Select 2+ parallel grids (or 2+ levels) -> a chained dimension is
        placed between them instead.

Targets Revit 2025. Written to run on both the IronPython 2.7 and the
CPython 3 pyRevit engines (no f-strings, parenthesised prints, XYZ methods
instead of operators).
"""

from pyrevit import revit, DB, forms, script

doc = revit.doc
active_view = doc.ActiveView
logger = script.get_logger()
output = script.get_output()

# --------------------------------------------------------------------- config
DIM_OFFSET_MM = 300.0    # distance the dim line sits off the element
LINE_MARGIN_MM = 150.0   # extra length added to each end of the dim line
PARALLEL_MIN = 0.985     # |dot| >= this => vectors treated as parallel (~10 deg)
IN_PLANE_MAX = 0.150     # |dot with view normal| <= this => axis is in-view-plane
FLIP_SIDE = False        # flip which side of the element the dim line sits on
# -----------------------------------------------------------------------------

# View types that cannot host dimensions.
_NO_DIM_VIEWS = (
    DB.ViewType.Schedule, DB.ViewType.DrawingSheet, DB.ViewType.Legend,
    DB.ViewType.ThreeD, DB.ViewType.Walkthrough, DB.ViewType.Rendering,
    DB.ViewType.Undefined,
)


def mm(value):
    """Millimetres -> Revit internal units (decimal feet)."""
    try:
        return DB.UnitUtils.ConvertToInternalUnits(value, DB.UnitTypeId.Millimeters)
    except Exception:
        return DB.UnitUtils.ConvertToInternalUnits(
            value, DB.DisplayUnitType.DUT_MILLIMETERS)


DIM_OFFSET = mm(DIM_OFFSET_MM)
LINE_MARGIN = mm(LINE_MARGIN_MM)


# --------------------------------------------------------------- geometry utils
def project_to_view_plane(pt, view):
    """Drop a world point onto the active view's plane."""
    n = view.ViewDirection.Normalize()
    dist = pt.Subtract(view.Origin).DotProduct(n)
    return pt.Subtract(n.Multiply(dist))


def element_frame(elem):
    """Return (bx, by, bz) unit vectors describing the element's own orientation."""
    if isinstance(elem, DB.FamilyInstance):
        t = elem.GetTransform()
        return (t.BasisX.Normalize(), t.BasisY.Normalize(), t.BasisZ.Normalize())

    if isinstance(elem, DB.Wall):
        loc = elem.Location
        if isinstance(loc, DB.LocationCurve):
            c = loc.Curve
            x = c.GetEndPoint(1).Subtract(c.GetEndPoint(0)).Normalize()
            y = elem.Orientation.Normalize()
            z = x.CrossProduct(y).Normalize()
            return (x, y, z)

    # Floors, slabs, sketch-based elements: no clean local frame -> world axes.
    return (DB.XYZ.BasisX, DB.XYZ.BasisY, DB.XYZ.BasisZ)


def planar_faces(elem):
    """All planar faces of an element that carry a usable reference."""
    opt = DB.Options()
    opt.ComputeReferences = True
    opt.IncludeNonVisibleObjects = False
    # No opt.View: we want the full solid so edge faces are always available
    # (a floor in plan would otherwise only expose its top face).
    ge = elem.get_Geometry(opt)
    result = []
    if ge is None:
        return result

    stack = [ge]
    while stack:
        geo = stack.pop()
        for g in geo:
            if isinstance(g, DB.Solid):
                if g.Faces.Size == 0:
                    continue
                for f in g.Faces:
                    if isinstance(f, DB.PlanarFace) and f.Reference is not None:
                        result.append(f)
            elif isinstance(g, DB.GeometryInstance):
                stack.append(g.GetInstanceGeometry())
    return result


def extreme_faces(faces, axis):
    """The two outermost planar faces whose normal is parallel to `axis`."""
    a = axis.Normalize()
    matched = []
    for f in faces:
        if abs(f.FaceNormal.Normalize().DotProduct(a)) >= PARALLEL_MIN:
            matched.append((f.Origin.DotProduct(a), f))
    if len(matched) < 2:
        return None
    matched.sort(key=lambda p: p[0])
    lo, hi = matched[0][1], matched[-1][1]
    if lo.Reference is None or hi.Reference is None:
        return None
    if abs(matched[-1][0] - matched[0][0]) < 1e-6:  # coincident planes
        return None
    return (lo, hi)


def build_dim_line(view, center, axis, half_len, side_dir):
    """A dim line parallel to `axis`, offset off the element, in the view plane."""
    a = axis.Normalize()
    c = project_to_view_plane(center, view)
    off = side_dir.Multiply(DIM_OFFSET)
    p1 = c.Subtract(a.Multiply(half_len)).Add(off)
    p2 = c.Add(a.Multiply(half_len)).Add(off)
    return DB.Line.CreateBound(p1, p2)


def bbox_center(elem):
    bb = elem.get_BoundingBox(None) or elem.get_BoundingBox(active_view)
    if bb is None:
        return DB.XYZ(0, 0, 0)
    return bb.Min.Add(bb.Max).Multiply(0.5)


# ---------------------------------------------------------------- core routines
def dimension_element(elem):
    """Create up to two dimensions across an element's in-plane extents.

    Returns (created_count, note)."""
    faces = planar_faces(elem)
    if not faces:
        return (0, "no planar faces")

    n_view = active_view.ViewDirection.Normalize()
    bx, by, bz = element_frame(elem)

    # Keep only element axes that lie in the view plane (perp. to view normal).
    axes = [ax for ax in (bx, by, bz)
            if abs(ax.Normalize().DotProduct(n_view)) <= IN_PLANE_MAX]
    if not axes:
        return (0, "no element axis lies in the view plane")

    center = bbox_center(elem)
    created = 0
    for axis in axes:
        pair = extreme_faces(faces, axis)
        if pair is None:
            continue
        lo, hi = pair
        extent = abs(hi.Origin.Subtract(lo.Origin).DotProduct(axis.Normalize()))
        half_len = extent * 0.5 + LINE_MARGIN

        side = n_view.CrossProduct(axis).Normalize()
        if FLIP_SIDE:
            side = side.Negate()

        ra = DB.ReferenceArray()
        ra.Append(lo.Reference)
        ra.Append(hi.Reference)
        line = build_dim_line(active_view, center, axis, half_len, side)
        try:
            doc.Create.NewDimension(active_view, line, ra)
            created += 1
        except Exception as ex:
            logger.debug("dim failed ({}): {}".format(elem.Id, ex))

    return (created, None if created else "no dimensionable face pairs")


def datum_curve(datum):
    """Representative curve for a grid/level as it appears in the active view."""
    try:
        curves = datum.GetCurvesInView(DB.DatumExtentType.Model, active_view)
        if curves and curves.Count > 0:
            return curves[0]
    except Exception:
        pass
    # Grids expose .Curve directly as a fallback.
    try:
        return datum.Curve
    except Exception:
        return None


def dimension_datums(datums):
    """Chain a dimension between 2+ parallel straight datums. Returns (count, note)."""
    n_view = active_view.ViewDirection.Normalize()
    items = []          # (datum, point_on_curve, curve_dir)
    for d in datums:
        c = datum_curve(d)
        if c is None:
            continue
        p0 = c.GetEndPoint(0)
        cd = c.GetEndPoint(1).Subtract(p0).Normalize()
        items.append((d, p0, cd))

    if len(items) < 2:
        return (0, "need 2+ datums that are visible in this view")

    base_dir = items[0][2]
    for _, _, cd in items:
        if abs(cd.DotProduct(base_dir)) < PARALLEL_MIN:
            return (0, "selected datums are not all parallel")

    # Measurement axis: in-plane, perpendicular to the datums.
    axis = n_view.CrossProduct(base_dir).Normalize()
    items.sort(key=lambda it: it[1].DotProduct(axis))

    ra = DB.ReferenceArray()
    for d, _, _ in items:
        ra.Append(DB.Reference(d))

    p_first = project_to_view_plane(items[0][1], active_view)
    span = items[-1][1].DotProduct(axis) - items[0][1].DotProduct(axis)
    off = base_dir.Multiply(DIM_OFFSET)
    start = p_first.Subtract(axis.Multiply(LINE_MARGIN)).Add(off)
    end = p_first.Add(axis.Multiply(span + LINE_MARGIN)).Add(off)
    line = DB.Line.CreateBound(start, end)

    try:
        doc.Create.NewDimension(active_view, line, ra)
        return (1, None)
    except Exception as ex:
        return (0, "datum dimension failed: {}".format(ex))


# ------------------------------------------------------------------------- main
def main():
    if active_view.ViewType in _NO_DIM_VIEWS:
        forms.alert("This view type can't host dimensions.\n"
                    "Open a plan, elevation or section and try again.",
                    exitscript=True)

    selection = list(revit.get_selection())
    if not selection:
        forms.alert("Select an element (or 2+ grids / levels) first.",
                    exitscript=True)

    datum_types = (DB.Grid, DB.Level)
    datums = [e for e in selection if isinstance(e, datum_types)]
    solids = [e for e in selection if not isinstance(e, datum_types)]

    total = 0
    notes = []
    with revit.Transaction("Self dimension"):
        if datums and not solids:
            count, note = dimension_datums(datums)
            total += count
            if note:
                notes.append(note)
        else:
            for elem in solids:
                count, note = dimension_element(elem)
                total += count
                if note:
                    notes.append("{}: {}".format(output.linkify(elem.Id), note))

    if total:
        print("Placed {} dimension(s).".format(total))
    else:
        print("No dimensions placed.")
    for note in notes:
        print(" - {}".format(note))


main()
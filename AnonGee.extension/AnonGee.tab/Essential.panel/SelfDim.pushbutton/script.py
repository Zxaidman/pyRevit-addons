# -*- coding: utf-8 -*-
"""Self Dimension.

Dimensions a selected element's own extents, measured along the element's
OWN orientation, on whichever axes lie in the active view's plane. Placement
is tuned per category so the dimensions stay clear of the geometry:

    Grids / levels   -> chained between them, near their end points (inset)
    Columns / family instances -> both extents, offset outside the bbox
    Walls / beams     -> width only (shorter axis), drawn on the body
    Floors / slabs    -> both extents, inset onto the body

Usage:
    * Select one or several solid elements  -> each is dimensioned.
    * Select 2+ parallel grids (or levels)  -> a chained dimension between them.

Targets Revit 2025. Runs on both the IronPython 2.7 and CPython 3 pyRevit
engines (no f-strings, parenthesised prints, XYZ methods not operators).
"""

from pyrevit import revit, DB, forms, script

doc = revit.doc
active_view = doc.ActiveView
logger = script.get_logger()
output = script.get_output()

# --------------------------------------------------------------------- config
DIM_OFFSET_MM = 300.0    # gap outside bbox / inset from edge / datum inset
LINE_MARGIN_MM = 150.0   # extra length on each end of the dim line
PARALLEL_MIN = 0.985     # |dot| >= this => vectors treated as parallel (~10 deg)
IN_PLANE_MAX = 0.150     # |dot with view normal| <= this => axis is in-view-plane
FLIP_SIDE = False        # flip which side of the element the dim line sits on
# -----------------------------------------------------------------------------

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
    n = view.ViewDirection.Normalize()
    dist = pt.Subtract(view.Origin).DotProduct(n)
    return pt.Subtract(n.Multiply(dist))


def bic(elem):
    try:
        return elem.Category.BuiltInCategory
    except Exception:
        return None


def element_frame(elem):
    """(bx, by, bz) unit vectors describing the element's own orientation."""
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
    """Planar faces of an element that carry a usable reference."""
    opt = DB.Options()
    opt.ComputeReferences = True
    opt.IncludeNonVisibleObjects = False
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
    """Two outermost planar faces whose normal is parallel to `axis`."""
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
    if abs(matched[-1][0] - matched[0][0]) < 1e-6:
        return None
    return (lo, hi)


def extent_along(faces, elem, direction):
    """Element size along `direction`, from faces if possible else the bbox."""
    d = direction.Normalize()
    pair = extreme_faces(faces, d)
    if pair:
        lo, hi = pair
        return abs(hi.Origin.Subtract(lo.Origin).DotProduct(d))
    bb = elem.get_BoundingBox(None) or elem.get_BoundingBox(active_view)
    if bb is None:
        return 0.0
    mn, mx = bb.Min, bb.Max
    corners = [DB.XYZ(x, y, z)
               for x in (mn.X, mx.X) for y in (mn.Y, mx.Y) for z in (mn.Z, mx.Z)]
    ps = [c.DotProduct(d) for c in corners]
    return max(ps) - min(ps)


def bbox_center(elem):
    bb = elem.get_BoundingBox(None) or elem.get_BoundingBox(active_view)
    if bb is None:
        return DB.XYZ(0, 0, 0)
    return bb.Min.Add(bb.Max).Multiply(0.5)


def build_dim_line(view, center, axis, half_len, side_dir, offset_dist):
    """Dim line parallel to `axis`, shifted `offset_dist` along `side_dir`."""
    a = axis.Normalize()
    c = project_to_view_plane(center, view)
    off = side_dir.Multiply(offset_dist)
    p1 = c.Subtract(a.Multiply(half_len)).Add(off)
    p2 = c.Add(a.Multiply(half_len)).Add(off)
    return DB.Line.CreateBound(p1, p2)


# ---------------------------------------------------------------- classification
def classify(elem):
    """Return (axes_mode, placement) for an element.

    axes_mode : 'both' | 'width_only'   (width = shorter in-plane axis)
    placement : 'outside' | 'inset' | 'on_body'
    """
    if isinstance(elem, DB.Wall):
        return ("width_only", "on_body")
    cat = bic(elem)
    if cat == DB.BuiltInCategory.OST_StructuralFraming:
        return ("width_only", "on_body")
    if cat in (DB.BuiltInCategory.OST_Floors,
               DB.BuiltInCategory.OST_StructuralFoundation):
        return ("both", "inset")
    # Columns and everything else.
    return ("both", "outside")


# ---------------------------------------------------------------- core routines
def dimension_element(elem):
    """Create dimensions across an element's in-plane extents. (count, note)."""
    faces = planar_faces(elem)
    if not faces:
        return (0, "no planar faces")

    n_view = active_view.ViewDirection.Normalize()
    bx, by, bz = element_frame(elem)
    cand = [ax for ax in (bx, by, bz)
            if abs(ax.Normalize().DotProduct(n_view)) <= IN_PLANE_MAX]
    if not cand:
        return (0, "no element axis lies in the view plane")

    specs = []                                  # (axis, extent, lo_face, hi_face)
    for axis in cand:
        pair = extreme_faces(faces, axis)
        if pair is None:
            continue
        lo, hi = pair
        extent = abs(hi.Origin.Subtract(lo.Origin).DotProduct(axis.Normalize()))
        specs.append((axis, extent, lo, hi))
    if not specs:
        return (0, "no dimensionable face pairs")

    axes_mode, placement = classify(elem)
    if axes_mode == "width_only":
        specs = [min(specs, key=lambda s: s[1])]   # shorter axis = width

    center = bbox_center(elem)
    created = 0
    for axis, extent, lo, hi in specs:
        side = n_view.CrossProduct(axis).Normalize()
        if FLIP_SIDE:
            side = side.Negate()
        half_side = extent_along(faces, elem, side) * 0.5

        if placement == "outside":
            offset = half_side + DIM_OFFSET
        elif placement == "inset":
            offset = max(0.0, half_side - DIM_OFFSET)
        else:                                       # on_body
            offset = 0.0

        half_len = extent * 0.5 + LINE_MARGIN
        ra = DB.ReferenceArray()
        ra.Append(lo.Reference)
        ra.Append(hi.Reference)
        line = build_dim_line(active_view, center, axis, half_len, side, offset)
        try:
            doc.Create.NewDimension(active_view, line, ra)
            created += 1
        except Exception as ex:
            logger.debug("dim failed ({}): {}".format(elem.Id, ex))

    return (created, None if created else "no dimension could be placed")


def datum_curve(datum):
    """Representative curve for a grid/level as it appears in the active view."""
    try:
        curves = datum.GetCurvesInView(DB.DatumExtentType.Model, active_view)
        if curves and curves.Count > 0:
            return curves[0]
    except Exception:
        pass
    try:
        return datum.Curve
    except Exception:
        return None


def dimension_datums(datums):
    """Chain a dimension between 2+ parallel datums, near their ends. (count, note)."""
    n_view = active_view.ViewDirection.Normalize()
    O = active_view.Origin

    items = []                                  # (datum, p0, p1, dir)
    for d in datums:
        c = datum_curve(d)
        if c is None:
            continue
        p0 = c.GetEndPoint(0)
        p1 = c.GetEndPoint(1)
        items.append((d, p0, p1, p1.Subtract(p0).Normalize()))
    if len(items) < 2:
        return (0, "need 2+ datums that are visible in this view")

    base_dir = items[0][3]                       # along the datum lines
    for it in items:
        if abs(it[3].DotProduct(base_dir)) < PARALLEL_MIN:
            return (0, "selected datums are not all parallel")

    axis = n_view.CrossProduct(base_dir).Normalize()   # across the datums

    # Placement along the datums: pulled inward from the far end points.
    ends = []
    for _, p0, p1, _ in items:
        ends.append(p0.Subtract(O).DotProduct(base_dir))
        ends.append(p1.Subtract(O).DotProduct(base_dir))
    lo_end, hi_end = min(ends), max(ends)
    v_place = hi_end - DIM_OFFSET
    if v_place < lo_end:                         # datums shorter than the inset
        v_place = (lo_end + hi_end) * 0.5

    items.sort(key=lambda it: it[1].Subtract(O).DotProduct(axis))
    u_first = items[0][1].Subtract(O).DotProduct(axis)
    u_last = items[-1][1].Subtract(O).DotProduct(axis)

    ra = DB.ReferenceArray()
    for d, _, _, _ in items:
        ra.Append(DB.Reference(d))

    start = O.Add(axis.Multiply(u_first)).Add(base_dir.Multiply(v_place))
    end = O.Add(axis.Multiply(u_last)).Add(base_dir.Multiply(v_place))
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

    print("Placed {} dimension(s).".format(total) if total
          else "No dimensions placed.")
    for note in notes:
        print(" - {}".format(note))


main()

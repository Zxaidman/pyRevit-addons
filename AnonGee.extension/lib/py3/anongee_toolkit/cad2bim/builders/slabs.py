# -*- coding: utf-8 -*-
"""Place floor slabs from derived slab loops (see slabs_proto.py).

Mirrors the column/beam builders: a base floor type is duplicated per thickness
("150 THK") and cached; a loop with no thickness inherits the picked type. A loop
lying fully INSIDE another becomes that floor's OPENING (a hole), not its own slab.
Runs inside a caller-owned Transaction; one bad loop never fails the batch.
"""

from System.Collections.Generic import List

from Autodesk.Revit.DB import (FilteredElementCollector, XYZ, Line, CurveLoop,
                               Floor, FloorType, BuiltInParameter)

from ..unit_convert import mm_to_internal
from ..compat import get_element_name


def floor_types(doc):
    """[(label, ElementId)] of the model's floor types."""
    types = (FilteredElementCollector(doc).OfClass(FloorType).ToElements())
    rows = [(get_element_name(ft), ft.Id) for ft in types]
    return sorted(rows, key=lambda pair: pair[0])


def place_slabs(doc, slabs, base_type_id, level_id):
    """Place one floor per outer slab dict {ring, z, mark, thickness_mm}.

    ring: [(x, y), ...] internal feet, closed implicitly. thickness_mm duplicates
    the base type sized to that thickness; None keeps the base type as-is. A slab
    whose ring lies fully inside another slab's ring is treated as an OPENING of
    the enclosing slab (stair/lift void) and appended as an inner CurveLoop.

    Floor.Create requires a .NET IList<CurveLoop> -- a Python list does not
    convert under CPython3/pythonnet ("No method matches given arguments"), so
    the loops are packed into System.Collections.Generic.List[CurveLoop].
    """
    base_type = doc.GetElement(base_type_id)
    level = doc.GetElement(level_id)
    if base_type is None or level is None:
        raise ValueError("floor type or level could not be resolved")

    outers, openings = _nest_openings(slabs)
    cache = {}
    result = {"created": [], "skipped": [], "errors": []}
    for index, slab in enumerate(outers):
        try:
            ring = slab["ring"]
            if len(ring) < 3:
                result["skipped"].append("degenerate loop")
                continue
            loops = List[CurveLoop]()
            loops.Add(_curve_loop(ring))
            for hole in openings.get(index, []):
                loops.Add(_curve_loop(hole["ring"]))
            floor_type = _resolve_type(doc, base_type, slab.get("thickness_mm"), cache)
            instance = Floor.Create(doc, loops, floor_type.Id, level.Id)
            _set_structural(instance)
            _set_mark(instance, slab.get("mark"))
            result["created"].append(instance.Id)
        except Exception as placement_error:
            result["errors"].append(str(placement_error))
    return result


_MIN_EDGE_FT = 15.0 / 304.8       # skip sub-tolerance slivers (Revit rejects them)
_COLLINEAR_FT = 1.0 / 304.8       # merge vertices that add no real corner


def _curve_loop(ring):
    """Ring -> CurveLoop, sanitized: duplicate points, sub-tolerance edges and
    collinear stops are merged first -- a tessellated ARC boundary otherwise feeds
    Revit hundreds of tiny segments and Floor.Create rejects the loop."""
    pts = _sanitize_ring(ring)
    loop = CurveLoop()
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        loop.Append(Line.CreateBound(XYZ(x1, y1, 0.0), XYZ(x2, y2, 0.0)))
    return loop


def _sanitize_ring(ring):
    pts = []
    for x, y in ring:
        if pts and ((x - pts[-1][0]) ** 2 + (y - pts[-1][1]) ** 2) ** 0.5 < _MIN_EDGE_FT:
            continue
        pts.append((x, y))
    if len(pts) > 1 and ((pts[0][0] - pts[-1][0]) ** 2
                         + (pts[0][1] - pts[-1][1]) ** 2) ** 0.5 < _MIN_EDGE_FT:
        pts.pop()
    out = []
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        cx, cy = pts[(i + 1) % n]
        # perpendicular distance of b from segment a-c: a true corner keeps it
        vx, vy = cx - ax, cy - ay
        length = (vx * vx + vy * vy) ** 0.5
        if length > 0 and abs((bx - ax) * vy - (by - ay) * vx) / length < _COLLINEAR_FT:
            continue
        out.append(pts[i])
    return out if len(out) >= 3 else pts


def _nest_openings(slabs):
    """Split loops into (outer slabs, {outer index: [opening slabs]}).

    A loop whose every vertex lies inside another loop is that loop's opening --
    the way a stair/lift void is drawn inside the floor outline. Nesting one level
    deep only (an island inside a void becomes its own slab again is NOT handled;
    none of the fixtures draws one)."""
    outers = []
    openings = {}
    order = sorted(range(len(slabs)),
                   key=lambda i: -abs(_ring_area(slabs[i]["ring"])))
    placed = []                       # indices into `outers`, biggest first
    for i in order:
        ring = slabs[i]["ring"]
        host = None
        for j in placed:
            if _ring_inside(ring, outers[j]["ring"]):
                host = j
                break
        if host is None:
            placed.append(len(outers))
            outers.append(slabs[i])
        else:
            openings.setdefault(host, []).append(slabs[i])
    return outers, openings


def _ring_area(ring):
    s = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


_HOLE_CLEARANCE_FT = 50.0 / 304.8


def _ring_inside(inner, outer):
    """True only when `inner` sits STRICTLY inside `outer`, clear of its boundary.

    Adjacent slab panels SHARE edges; a shared-edge vertex sits ON the boundary,
    where a plain point-in-polygon answer is arbitrary -- that once classified a
    neighbouring panel as this floor's hole, and Floor.Create rejected the
    intersecting loops. A genuine void (stair/lift) is well inside: every vertex
    must be inside AND at least the clearance away from the outer boundary.
    """
    n = len(outer)
    for x, y in inner:
        if not _point_in_ring(x, y, outer):
            return False
        for i in range(n):
            if _pt_seg_dist(x, y, outer[i], outer[(i + 1) % n]) < _HOLE_CLEARANCE_FT:
                return False
    return True


def _pt_seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2)) if l2 else 0.0
    qx, qy = ax + t * dx, ay + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


def _point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                inside = not inside
    return inside


def _set_structural(instance):
    """Flag the floor structural (this is a structural toolkit); best-effort."""
    try:
        parameter = instance.get_Parameter(
            BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(1)
    except Exception:
        pass


def _resolve_type(doc, base_type, thickness_mm, cache):
    """Floor type of the given thickness, duplicating + caching off the base type."""
    if thickness_mm is None:
        return base_type
    key = int(round(thickness_mm))
    if key in cache:
        return cache[key]
    name = "{0} THK".format(key)
    existing = _find_type(doc, base_type, name)
    if existing is not None:
        cache[key] = existing
        return existing
    new_type = base_type.Duplicate(name)
    _set_thickness(new_type, thickness_mm)
    cache[key] = new_type
    return new_type


def _find_type(doc, base_type, name):
    for ft in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        if get_element_name(ft) == name:
            return ft
    return None


def _set_thickness(floor_type, thickness_mm):
    """Resize the type's structural core layer to the labelled thickness."""
    try:
        structure = floor_type.GetCompoundStructure()
        index = structure.GetFirstCoreLayerIndex()
        structure.SetLayerWidth(index, mm_to_internal(thickness_mm))
        floor_type.SetCompoundStructure(structure)
    except Exception:
        pass   # thickness is best-effort; the loop still places at type default


def _set_mark(instance, mark):
    if not mark:
        return
    try:
        parameter = instance.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(str(mark))
    except Exception:
        pass

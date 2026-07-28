# -*- coding: utf-8 -*-
"""Hatch Slab (v2).

AutoCAD-style hatch behaviour for Revit: click inside a closed region formed by
structural framing and structural columns in a plan view, and a structural floor
or foundation slab is created with its boundary on the INNER FACES of those
elements.

Click repeatedly to fill more regions. Press ESC to finish.

v2 changes
  - type names resolved properly (SYMBOL_NAME_PARAM / Element.Name.GetValue)
  - list shows "Type Name  [id]"
  - object snapping disabled while picking (snapping was dragging the click
    onto a beam edge, which made point-in-region always fail)
  - a sketch plane is set on the view if it has none (PickPoint needs one)
  - no more blanket excepts: real exception type and message get printed
  - DEBUG flag dumps graph statistics so failures are diagnosable

Target: Revit 2022+ (uses Floor.Create). Engine: IronPython 2.7.
"""

__title__ = 'Hatch\nSlab'
__author__ = 'AnonGee'

import math
import time
import traceback

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    CurveLoop,
    Element,
    ExtrusionAnalyzer,
    FilteredElementCollector,
    Floor,
    FloorType,
    GeometryInstance,
    Line,
    Options,
    Plane,
    SketchPlane,
    Solid,
    Transaction,
    ViewDetailLevel,
    ViewPlan,
    XYZ,
)
from Autodesk.Revit.UI.Selection import ObjectSnapTypes
import Autodesk.Revit.Exceptions as RevitExceptions
from System.Collections.Generic import List

from pyrevit import forms, script


doc = __revit__.ActiveUIDocument.Document          # noqa: F821
uidoc = __revit__.ActiveUIDocument                 # noqa: F821
output = script.get_output()
logger = script.get_logger()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

DEBUG = True                                  # print graph statistics

SHORT = doc.Application.ShortCurveTolerance   # ~0.00256 ft (~0.78 mm)
SNAP = SHORT                                  # node merge distance
GRID_CELL = 2.0                               # broad-phase bucket size, ft
COLLINEAR_TOL = 1.0e-6
MIN_FACE_AREA = 0.01                          # ft^2, ignore slivers

# ObjectSnapTypes.None -- 'None' is a Python keyword, so fetch it by name.
NO_SNAP = getattr(ObjectSnapTypes, 'None')


# ---------------------------------------------------------------------------
# Naming helpers -- the v1 bug lived here
# ---------------------------------------------------------------------------

def element_id_value(element_id):
    """ElementId.Value on Revit 2024+, IntegerValue on older releases."""
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def element_name(element):
    """Get an element's name despite IronPython's flaky .Name resolution."""
    for bip in (BuiltInParameter.SYMBOL_NAME_PARAM,
                BuiltInParameter.ALL_MODEL_TYPE_NAME):
        try:
            param = element.get_Parameter(bip)
            if param is not None and param.HasValue:
                value = param.AsString()
                if value:
                    return value
        except Exception:
            pass

    try:
        # Reflected property access -- bypasses the ambiguous binding.
        value = Element.Name.GetValue(element)
        if value:
            return value
    except Exception:
        pass

    try:
        return element.Name
    except Exception:
        pass

    return 'Unnamed type'


def bic_value(bic):
    try:
        return int(bic)
    except (TypeError, ValueError):
        return bic.value__


# ---------------------------------------------------------------------------
# Step 1 -- plan footprints of beams and columns
# ---------------------------------------------------------------------------

def iter_solids(geo_element):
    if geo_element is None:
        return
    for geo in geo_element:
        if isinstance(geo, Solid):
            try:
                if geo.Volume > 1.0e-6 and geo.Faces.Size > 0:
                    yield geo
            except Exception:
                continue
        elif isinstance(geo, GeometryInstance):
            for sub in iter_solids(geo.GetInstanceGeometry()):
                yield sub


def footprint_loops(element, opts, plane):
    loops = []
    try:
        geo = element.get_Geometry(opts)
    except Exception as err:
        logger.debug('geometry failed on {0}: {1}'.format(element.Id, err))
        return loops

    for solid in iter_solids(geo):
        try:
            analyzer = ExtrusionAnalyzer.Create(solid, plane, XYZ.BasisZ)
            for curve_loop in analyzer.GetExtrusionBase().GetEdgesAsCurveLoops():
                loops.append(curve_loop)
        except Exception as err:
            logger.debug('footprint failed on {0}: {1}'.format(element.Id, err))
            continue
    return loops


def loops_to_segments(loops):
    segments = []
    for curve_loop in loops:
        for curve in curve_loop:
            try:
                pts = curve.Tessellate()
            except Exception:
                continue
            for i in range(len(pts) - 1):
                a = pts[i]
                b = pts[i + 1]
                if a.DistanceTo(b) > SHORT:
                    segments.append(((a.X, a.Y), (b.X, b.Y)))
    return segments


def gather_boundary_segments(view):
    opts = Options()
    opts.ComputeReferences = False
    opts.IncludeNonVisibleObjects = False
    opts.DetailLevel = ViewDetailLevel.Fine

    plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ.Zero)

    elements = []
    skipped = 0
    for bic in (BuiltInCategory.OST_StructuralFraming,
                BuiltInCategory.OST_StructuralColumns):
        elements.extend(
            FilteredElementCollector(doc, view.Id)
            .OfCategory(bic)
            .WhereElementIsNotElementType()
            .ToElements()
        )

    segments = []
    if not elements:
        return segments, 0, 0

    with forms.ProgressBar(
            title='Reading beams and columns... {value}/{max_value}',
            cancellable=True) as pbar:
        for idx, element in enumerate(elements):
            if pbar.cancelled:
                break
            pbar.update_progress(idx + 1, len(elements))
            found = loops_to_segments(footprint_loops(element, opts, plane))
            if not found:
                skipped += 1
            segments.extend(found)

    return segments, len(elements), skipped


# ---------------------------------------------------------------------------
# Step 2 -- split segments at intersections
# ---------------------------------------------------------------------------

class SegmentGrid(object):

    def __init__(self, cell):
        self.cell = cell
        self.buckets = {}

    def _range(self, seg):
        (x1, y1), (x2, y2) = seg
        return (int(math.floor(min(x1, x2) / self.cell)),
                int(math.floor(max(x1, x2) / self.cell)),
                int(math.floor(min(y1, y2) / self.cell)),
                int(math.floor(max(y1, y2) / self.cell)))

    def add(self, index, seg):
        i0, i1, j0, j1 = self._range(seg)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                self.buckets.setdefault((i, j), []).append(index)

    def query(self, seg):
        found = set()
        i0, i1, j0, j1 = self._range(seg)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                found.update(self.buckets.get((i, j), ()))
        return found


def _sub(p, q):
    return (p[0] - q[0], p[1] - q[1])


def _cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def pair_cuts(seg_a, seg_b):
    pa, qa = seg_a
    pb, qb = seg_b
    ra = _sub(qa, pa)
    rb = _sub(qb, pb)
    denom = _cross(ra, rb)
    delta = _sub(pb, pa)

    if abs(denom) > 1.0e-12:
        t = _cross(delta, rb) / denom
        u = _cross(delta, ra) / denom
        if -0.001 <= t <= 1.001 and -0.001 <= u <= 1.001:
            return [(t, u)]
        return []

    len_a = math.hypot(ra[0], ra[1])
    if len_a < 1.0e-9:
        return []
    if abs(_cross(ra, delta)) / len_a > SNAP:
        return []

    cuts = []
    for point in (pb, qb):
        d = _sub(point, pa)
        cuts.append(((d[0] * ra[0] + d[1] * ra[1]) / (len_a * len_a), None))
    rb_len = math.hypot(rb[0], rb[1])
    if rb_len > 1.0e-9:
        for point in (pa, qa):
            d = _sub(point, pb)
            cuts.append((None, (d[0] * rb[0] + d[1] * rb[1]) / (rb_len * rb_len)))
    return cuts


def split_all(segments):
    grid = SegmentGrid(GRID_CELL)
    for index, seg in enumerate(segments):
        grid.add(index, seg)

    cuts = [[] for _ in segments]
    eps = 1.0e-7

    for i, seg_a in enumerate(segments):
        for j in grid.query(seg_a):
            if j <= i:
                continue
            for t, u in pair_cuts(seg_a, segments[j]):
                if t is not None and eps < t < 1.0 - eps:
                    cuts[i].append(t)
                if u is not None and eps < u < 1.0 - eps:
                    cuts[j].append(u)

    pieces = []
    for i, seg in enumerate(segments):
        (x1, y1), (x2, y2) = seg
        params = sorted(set([0.0, 1.0] + cuts[i]))
        for k in range(len(params) - 1):
            t0, t1 = params[k], params[k + 1]
            if t1 - t0 < 1.0e-9:
                continue
            a = (x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0)
            b = (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)
            if math.hypot(b[0] - a[0], b[1] - a[1]) > SHORT:
                pieces.append((a, b))
    return pieces


# ---------------------------------------------------------------------------
# Step 3 -- planar graph and faces
# ---------------------------------------------------------------------------

class NodeStore(object):

    def __init__(self, snap):
        self.snap = snap
        self.cell = snap * 2.0
        self.buckets = {}
        self.points = []

    def add(self, x, y):
        kx = int(math.floor(x / self.cell))
        ky = int(math.floor(y / self.cell))
        best = None
        best_d = self.snap
        for i in (kx - 1, kx, kx + 1):
            for j in (ky - 1, ky, ky + 1):
                for index in self.buckets.get((i, j), ()):
                    px, py = self.points[index]
                    d = math.hypot(px - x, py - y)
                    if d <= best_d:
                        best_d = d
                        best = index
        if best is not None:
            return best
        index = len(self.points)
        self.points.append((x, y))
        self.buckets.setdefault((kx, ky), []).append(index)
        return index


def build_graph(pieces):
    nodes = NodeStore(SNAP)
    adjacency = {}
    for a, b in pieces:
        na = nodes.add(a[0], a[1])
        nb = nodes.add(b[0], b[1])
        if na == nb:
            continue
        adjacency.setdefault(na, set()).add(nb)
        adjacency.setdefault(nb, set()).add(na)

    raw_nodes = len(adjacency)

    changed = True
    while changed:
        changed = False
        for node in list(adjacency.keys()):
            if len(adjacency[node]) <= 1:
                for other in list(adjacency[node]):
                    adjacency[other].discard(node)
                del adjacency[node]
                changed = True

    return nodes.points, adjacency, raw_nodes


def trace_faces(points, adjacency):
    ordered = {}
    position = {}
    for node, neighbours in adjacency.items():
        ring = []
        for other in neighbours:
            ring.append((math.atan2(points[other][1] - points[node][1],
                                    points[other][0] - points[node][0]), other))
        ring.sort()
        ordered[node] = ring
        position[node] = dict((other, idx) for idx, (_, other) in enumerate(ring))

    visited = set()
    faces = []
    guard = sum(len(v) for v in adjacency.values()) + 10

    for start in adjacency:
        for first in adjacency[start]:
            if (start, first) in visited:
                continue
            cycle = []
            cur_a, cur_b = start, first
            steps = 0
            while True:
                visited.add((cur_a, cur_b))
                cycle.append(cur_a)
                ring = ordered[cur_b]
                idx = position[cur_b][cur_a]
                nxt = ring[(idx - 1) % len(ring)][1]
                cur_a, cur_b = cur_b, nxt
                steps += 1
                if (cur_a, cur_b) == (start, first):
                    break
                if steps > guard:
                    cycle = []
                    break
            if len(cycle) >= 3:
                faces.append(cycle)
    return faces


def signed_area(points, cycle):
    total = 0.0
    count = len(cycle)
    for i in range(count):
        x1, y1 = points[cycle[i]]
        x2, y2 = points[cycle[(i + 1) % count]]
        total += x1 * y2 - x2 * y1
    return total * 0.5


def point_in_cycle(points, cycle, x, y):
    inside = False
    count = len(cycle)
    for i in range(count):
        x1, y1 = points[cycle[i]]
        x2, y2 = points[cycle[(i + 1) % count]]
        if (y1 > y) != (y2 > y):
            x_at = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x_at > x:
                inside = not inside
    return inside


def find_region(points, faces, x, y):
    best = None
    best_area = None
    for cycle in faces:
        area = abs(signed_area(points, cycle))
        if area < MIN_FACE_AREA:
            continue
        if not point_in_cycle(points, cycle, x, y):
            continue
        if best_area is None or area < best_area:
            best_area = area
            best = cycle
    return best, best_area


def nearest_face_distance(points, faces, x, y):
    """Diagnostic: how far is the click from the closest face centroid."""
    best = None
    for cycle in faces:
        if abs(signed_area(points, cycle)) < MIN_FACE_AREA:
            continue
        cx = sum(points[n][0] for n in cycle) / float(len(cycle))
        cy = sum(points[n][1] for n in cycle) / float(len(cycle))
        d = math.hypot(cx - x, cy - y)
        if best is None or d < best:
            best = d
    return best


# ---------------------------------------------------------------------------
# Step 4 -- cycle to CurveLoop
# ---------------------------------------------------------------------------

def simplify(points, cycle):
    ring = [points[n] for n in cycle]
    result = []
    count = len(ring)
    for i in range(count):
        prev_pt = ring[(i - 1) % count]
        this_pt = ring[i]
        next_pt = ring[(i + 1) % count]
        u = _sub(this_pt, prev_pt)
        v = _sub(next_pt, this_pt)
        lu = math.hypot(u[0], u[1])
        lv = math.hypot(v[0], v[1])
        if lu < 1.0e-9 or lv < 1.0e-9:
            continue
        if abs(_cross(u, v)) / (lu * lv) > COLLINEAR_TOL:
            result.append(this_pt)
    return result if len(result) >= 3 else ring


def make_curve_loop(ring, elevation):
    loop = CurveLoop()
    count = len(ring)
    appended = 0
    for i in range(count):
        ax, ay = ring[i]
        bx, by = ring[(i + 1) % count]
        start = XYZ(ax, ay, elevation)
        end = XYZ(bx, by, elevation)
        if start.DistanceTo(end) <= SHORT:
            continue
        loop.Append(Line.CreateBound(start, end))
        appended += 1
    return loop if appended >= 3 else None


# ---------------------------------------------------------------------------
# Step 5 -- type selection
# ---------------------------------------------------------------------------

def collect_types(target_bic):
    wanted = bic_value(target_bic)
    result = {}
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        category = floor_type.Category
        if category is None or element_id_value(category.Id) != wanted:
            continue
        label = '{0}  [{1}]'.format(element_name(floor_type),
                                    element_id_value(floor_type.Id))
        result[label] = floor_type
    return result


def choose_type():
    kind = forms.CommandSwitchWindow.show(
        ['Structural Floor', 'Foundation Slab'],
        message='What should be created?',
    )
    if not kind:
        return None, None

    target = (BuiltInCategory.OST_Floors if kind == 'Structural Floor'
              else BuiltInCategory.OST_StructuralFoundation)

    available = collect_types(target)
    if not available:
        forms.alert('No {0} types found in this project.'.format(kind.lower()),
                    exitscript=True)

    picked = forms.SelectFromList.show(
        sorted(available.keys()),
        title='Pick a {0} type'.format(kind.lower()),
        button_name='Use this type',
        multiselect=False,
    )
    if not picked:
        return None, None
    return available[picked], kind


# ---------------------------------------------------------------------------
# Sketch plane -- PickPoint needs one
# ---------------------------------------------------------------------------

def ensure_sketch_plane(view, elevation):
    try:
        if view.SketchPlane is not None:
            return True
    except Exception:
        pass

    transaction = Transaction(doc, 'Hatch Slab - set work plane')
    transaction.Start()
    try:
        plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ(0, 0, elevation))
        view.SketchPlane = SketchPlane.Create(doc, plane)
        transaction.Commit()
        return True
    except Exception as err:
        transaction.RollBack()
        output.print_md('- Could not set a work plane: `{0}`'.format(err))
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    view = doc.ActiveView

    if not isinstance(view, ViewPlan):
        forms.alert('Run this from a plan view (floor plan or structural plan).',
                    exitscript=True)

    level = view.GenLevel
    if level is None:
        forms.alert('This plan view has no associated level.', exitscript=True)

    floor_type, kind = choose_type()
    if floor_type is None:
        return

    segments, element_count, skipped = gather_boundary_segments(view)
    if not segments:
        forms.alert('No structural framing or columns visible in this view.',
                    exitscript=True)

    pieces = split_all(segments)
    points, adjacency, raw_nodes = build_graph(pieces)
    if not adjacency:
        forms.alert('No closed regions found -- every edge was a dead end. '
                    'Check that the beams actually meet in plan.',
                    exitscript=True)

    faces = trace_faces(points, adjacency)
    usable = [f for f in faces if abs(signed_area(points, f)) >= MIN_FACE_AREA]
    elevation = level.Elevation

    if DEBUG:
        output.print_md('### Graph')
        output.print_md(
            '- elements read: **{0}** (no geometry: {1})\n'
            '- raw segments: **{2}** -> after splitting: **{3}**\n'
            '- graph nodes: **{4}** (before pruning dead ends: {5})\n'
            '- faces traced: **{6}** (usable: **{7}**)'.format(
                element_count, skipped, len(segments), len(pieces),
                len(adjacency), raw_nodes, len(faces), len(usable)))

    if not usable:
        forms.alert('The graph built, but no enclosed regions came out of it. '
                    'This usually means the beams do not overlap in plan.',
                    exitscript=True)

    ensure_sketch_plane(view, elevation)

    output.print_md('### Picking')
    output.print_md('Click inside a region. **ESC** to finish.')

    created = 0
    spurious_retried = False

    while True:
        started = time.time()
        try:
            pick = uidoc.Selection.PickPoint(
                NO_SNAP, 'Click inside a closed region (ESC to finish)')
        except RevitExceptions.OperationCanceledException:
            # A pick that cancels instantly is usually the click that dismissed
            # the previous dialog bleeding through, not a real ESC.
            if (time.time() - started) < 0.25 and not spurious_retried:
                spurious_retried = True
                continue
            break
        except Exception as err:
            output.print_md(
                '- **PickPoint failed:** `{0}: {1}`'.format(
                    type(err).__name__, err))
            output.print_md('```\n{0}\n```'.format(traceback.format_exc()))
            break

        spurious_retried = False

        try:
            cycle, area = find_region(points, usable, pick.X, pick.Y)
        except Exception as err:
            output.print_md('- Region search failed: `{0}`'.format(err))
            continue

        if cycle is None:
            gap = nearest_face_distance(points, usable, pick.X, pick.Y)
            output.print_md(
                '- No region at ({0:.2f}, {1:.2f}). Nearest region centre is '
                '{2:.2f} ft away.'.format(pick.X, pick.Y,
                                          gap if gap is not None else -1))
            continue

        ring = simplify(points, cycle)
        loop = make_curve_loop(ring, elevation)
        if loop is None:
            output.print_md('- Region boundary was too small to sketch.')
            continue

        profile = List[CurveLoop]()
        profile.Add(loop)

        transaction = Transaction(doc, 'Hatch Slab')
        transaction.Start()
        try:
            new_floor = Floor.Create(doc, profile, floor_type.Id, level.Id)
            structural = new_floor.get_Parameter(
                BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
            if structural is not None and not structural.IsReadOnly:
                structural.Set(1)
            transaction.Commit()
            created += 1
            output.print_md(
                '- Created {0} **{1}** -- {2:.2f} sq ft, '
                '{3} boundary segments'.format(
                    kind.lower(), element_name(floor_type), area, len(ring)))
        except Exception as err:
            transaction.RollBack()
            output.print_md('- **Create failed:** `{0}: {1}`'.format(
                type(err).__name__, err))

    output.print_md('**Done.** {0} slab(s) created.'.format(created))


main()

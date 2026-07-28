# -*- coding: utf-8 -*-
"""Hatch Slab.

AutoCAD-style hatch behaviour for Revit: click inside a closed region formed by
structural framing and structural columns in a plan view, and a structural floor
or foundation slab is created with its boundary on the INNER FACES of those
elements.

Click repeatedly to fill more regions. Press ESC to finish.

Tested target: Revit 2022+ (uses Floor.Create). Engine: IronPython 2.7.
"""

__title__ = 'Hatch\nSlab'
__author__ = 'AnonGee'

import math

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    CurveLoop,
    ExtrusionAnalyzer,
    FilteredElementCollector,
    Floor,
    FloorType,
    GeometryInstance,
    Line,
    Options,
    Plane,
    Solid,
    Transaction,
    ViewDetailLevel,
    ViewPlan,
    XYZ,
)
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

from pyrevit import forms, script


doc = __revit__.ActiveUIDocument.Document          # noqa: F821
uidoc = __revit__.ActiveUIDocument                 # noqa: F821
output = script.get_output()
logger = script.get_logger()


# ---------------------------------------------------------------------------
# Tolerances (all internal Revit units = decimal feet)
# ---------------------------------------------------------------------------

SHORT = doc.Application.ShortCurveTolerance   # ~0.00256 ft (~0.78 mm)
SNAP = SHORT                                  # node merge distance
GRID_CELL = 2.0                               # broad-phase bucket size, ft
COLLINEAR_TOL = 1.0e-6                        # cross-product tol for simplify
MIN_FACE_AREA = 0.01                          # ft^2, ignore slivers


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def cat_id_value(element_id):
    """ElementId.Value on 2024+, IntegerValue on older releases."""
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def bic_value(bic):
    try:
        return int(bic)
    except (TypeError, ValueError):
        return bic.value__


# ---------------------------------------------------------------------------
# Step 1 -- pull plan footprints of beams and columns
# ---------------------------------------------------------------------------

def iter_solids(geo_element):
    """Yield every meaningful Solid inside a GeometryElement, recursively."""
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
    """Project an element's solids onto the plan plane and return CurveLoops.

    ExtrusionAnalyzer gives the true projected outline, so rotated columns and
    sloped/skewed beams come out correct -- much better than a bounding box.
    """
    loops = []
    try:
        geo = element.get_Geometry(opts)
    except Exception:
        return loops

    for solid in iter_solids(geo):
        try:
            analyzer = ExtrusionAnalyzer.Create(solid, plane, XYZ.BasisZ)
            base_face = analyzer.GetExtrusionBase()
            for curve_loop in base_face.GetEdgesAsCurveLoops():
                loops.append(curve_loop)
        except Exception as err:
            logger.debug('footprint failed on {0}: {1}'.format(element.Id, err))
            continue
    return loops


def loops_to_segments(loops):
    """Tessellate CurveLoops into flat 2D line segments.

    Everything downstream works on straight segments only -- that keeps the
    intersection maths and face traversal simple and robust. Curved beams come
    out as fine polylines.
    """
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
    """Collect footprint segments for every beam and column visible in view."""
    opts = Options()
    opts.ComputeReferences = False
    opts.IncludeNonVisibleObjects = False
    opts.DetailLevel = ViewDetailLevel.Fine   # coarse turns beams into sticks

    plane = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ.Zero)

    categories = [
        BuiltInCategory.OST_StructuralFraming,
        BuiltInCategory.OST_StructuralColumns,
    ]

    elements = []
    for bic in categories:
        collected = FilteredElementCollector(doc, view.Id) \
            .OfCategory(bic) \
            .WhereElementIsNotElementType() \
            .ToElements()
        elements.extend(collected)

    segments = []
    if not elements:
        return segments

    with forms.ProgressBar(title='Reading beams and columns... {value}/{max_value}',
                           cancellable=True) as pbar:
        for idx, element in enumerate(elements):
            if pbar.cancelled:
                break
            pbar.update_progress(idx + 1, len(elements))
            segments.extend(loops_to_segments(footprint_loops(element, opts, plane)))

    return segments


# ---------------------------------------------------------------------------
# Step 2 -- split every segment at its intersections with the others
# ---------------------------------------------------------------------------

class SegmentGrid(object):
    """Uniform grid so we don't test every segment against every other one."""

    def __init__(self, cell):
        self.cell = cell
        self.buckets = {}

    def _range(self, seg):
        (x1, y1), (x2, y2) = seg
        i0 = int(math.floor(min(x1, x2) / self.cell))
        i1 = int(math.floor(max(x1, x2) / self.cell))
        j0 = int(math.floor(min(y1, y2) / self.cell))
        j1 = int(math.floor(max(y1, y2) / self.cell))
        return i0, i1, j0, j1

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
    """Return (t_on_a, t_on_b) split params, or [] if they don't cross."""
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

    # Parallel. If also collinear and overlapping, project b's ends onto a.
    len_a = math.hypot(ra[0], ra[1])
    if len_a < 1.0e-9:
        return []
    if abs(_cross(ra, delta)) / len_a > SNAP:
        return []

    cuts = []
    for point in (pb, qb):
        d = _sub(point, pa)
        t = (d[0] * ra[0] + d[1] * ra[1]) / (len_a * len_a)
        cuts.append((t, None))
    for point in (pa, qa):
        rb_len = math.hypot(rb[0], rb[1])
        if rb_len < 1.0e-9:
            continue
        d = _sub(point, pb)
        u = (d[0] * rb[0] + d[1] * rb[1]) / (rb_len * rb_len)
        cuts.append((None, u))
    return cuts


def split_all(segments):
    """Cut every segment wherever another segment touches or crosses it."""
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
            t0 = params[k]
            t1 = params[k + 1]
            if t1 - t0 < 1.0e-9:
                continue
            a = (x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0)
            b = (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)
            if math.hypot(b[0] - a[0], b[1] - a[1]) > SHORT:
                pieces.append((a, b))
    return pieces


# ---------------------------------------------------------------------------
# Step 3 -- planar graph
# ---------------------------------------------------------------------------

class NodeStore(object):
    """Point set with tolerance-based merging."""

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

    # Prune dead ends -- a dangling beam bounds no region.
    changed = True
    while changed:
        changed = False
        for node in list(adjacency.keys()):
            if len(adjacency[node]) <= 1:
                for other in list(adjacency[node]):
                    adjacency[other].discard(node)
                del adjacency[node]
                changed = True

    return nodes.points, adjacency


def trace_faces(points, adjacency):
    """Walk every minimal cycle of the planar graph."""
    ordered = {}
    position = {}
    for node, neighbours in adjacency.items():
        ring = []
        for other in neighbours:
            angle = math.atan2(points[other][1] - points[node][1],
                               points[other][0] - points[node][0])
            ring.append((angle, other))
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
    """Smallest face that contains the click. Excludes the unbounded face."""
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


# ---------------------------------------------------------------------------
# Step 4 -- turn the cycle into a CurveLoop
# ---------------------------------------------------------------------------

def simplify(points, cycle):
    """Drop collinear intermediate vertices so the sketch stays clean."""
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
    if appended < 3:
        return None
    return loop


# ---------------------------------------------------------------------------
# Step 5 -- slab type selection
# ---------------------------------------------------------------------------

def collect_types(target_bic):
    wanted = bic_value(target_bic)
    result = {}
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        category = floor_type.Category
        if category is None:
            continue
        if cat_id_value(category.Id) != wanted:
            continue
        try:
            name = floor_type.Name
        except Exception:
            name = 'Type {0}'.format(floor_type.Id)
        result[name] = floor_type
    return result


def choose_type():
    kind = forms.CommandSwitchWindow.show(
        ['Structural Floor', 'Foundation Slab'],
        message='What should be created?',
    )
    if not kind:
        return None, None

    if kind == 'Structural Floor':
        target = BuiltInCategory.OST_Floors
    else:
        target = BuiltInCategory.OST_StructuralFoundation

    available = collect_types(target)
    if not available:
        forms.alert('No {0} types found in this project.'.format(kind.lower()),
                    exitscript=True)
        return None, None

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

    segments = gather_boundary_segments(view)
    if not segments:
        forms.alert('No structural framing or columns visible in this view.',
                    exitscript=True)

    pieces = split_all(segments)
    points, adjacency = build_graph(pieces)
    if not adjacency:
        forms.alert('No closed regions found. Check that the beams actually '
                    'meet in plan.', exitscript=True)

    faces = trace_faces(points, adjacency)
    elevation = level.Elevation

    output.print_md('**Hatch Slab** -- click inside a region, ESC to finish.')

    created = 0
    while True:
        try:
            pick = uidoc.Selection.PickPoint(
                'Click inside a closed region (ESC to finish)')
        except OperationCanceledException:
            break
        except Exception:
            break

        cycle, area = find_region(points, faces, pick.X, pick.Y)
        if cycle is None:
            output.print_md('- No closed region at that point.')
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
                '- Created {0} `{1}` -- {2:.2f} sq ft '
                '({3} boundary segments)'.format(
                    kind.lower(), floor_type.Name, area, len(ring)))
        except Exception as err:
            transaction.RollBack()
            output.print_md('- Failed: {0}'.format(err))

    output.print_md('**Done.** {0} slab(s) created.'.format(created))


main()

# -*- coding: utf-8 -*-
"""Hatch Slab 1.4.0

Click inside a closed region formed by structural framing and structural
columns in a plan view; a structural floor or foundation slab is created with
its boundary on the INNER FACES of those elements.

Workflow
  pick a type -> click regions -> ESC -> pick another type -> click more
  ESC at the type dialog (so: ESC twice) closes the tool. So does "Finish".
  SHIFT-click the button to force a fresh scan, ignoring the session cache.

Diagnostics
  EXPORT_JSON   dump a scoped JSON file when a click fails      (on)
  EXPORT_ALWAYS also dump on every successful click             (off)
  DUMP_GRAPH    write the whole graph to JSON after scanning     (off)
  Files land in the system temp folder; every path is printed to the output
  panel and the folder is reported at the end of the run.

Changelog
  1.0.0  first working version
  1.0.1  fixed type-name resolution, disabled object snap, sketch-plane guard
  1.1.0  added DEBUG graph statistics
  1.2.0  performance pass: per-symbol footprint templates, session cache,
         crop pre-filter, throttled progress bar, Medium-detail read
  1.3.0  - FIX: geometry is read at the ACTIVE VIEW'S detail level. 1.2.0 read
           at Medium, which for some families returns a slimmer solid than the
           view draws, so slab edges landed inside the beam instead of on its
           face. This was the cause of slabs overlapping beams.
         - FIX: arcs survive. Segments now carry their source curve, and
           consecutive runs off the same arc are rebuilt as real Arc geometry
           instead of 48 chords per circle.
         - FIX: a failed geometry read is no longer cached as an empty
           template, which previously blanked every sibling instance.
         - template key now includes hand/facing flip state
         - USE_TEMPLATES toggle for A/B testing the template cache
         - EXPORT_JSON writes a scoped dump around each click for diagnosis
  1.3.1  - the crop-box pre-filter added in 1.2.0 is OFF by default. It could
           drop a beam whose bounding box sat just outside the crop outline,
           leaving that bay open while every other bay filled. It is the last
           1.2.0 change capable of silently changing the output.
         - when enabled, the crop outline is padded by CROP_PADDING first
         - USE_CROP_FILTER and CROP_PADDING exposed as settings
  1.4.0  - multi-round workflow: ESC ends the current round and returns to the
           type dialog, so you can keep drawing with a different slab type.
           ESC again (or Finish) closes the tool. The geometry scan happens
           once and is shared by every round.
         - EXPORT_ALWAYS and DUMP_GRAPH for on-demand JSON, since the failure
           dumps never fire once everything works
         - temp folder path reported at the end of the run

Bisection order if regions are still missing:
  1. run as shipped (crop filter off, templates on)
  2. if still missing, set USE_TEMPLATES = False
  Between those two runs every 1.2.0 change is accounted for.

Runs on pyRevit's IronPython 2.7 and CPython 3 engines (no 2/3-only syntax).
Target: Revit 2022+.
"""

__title__ = 'Draw Floor'
__author__ = 'AnonGee'
__version__ = '1.4.0'
__highlight__ = 'new'

import json
import math
import os
import tempfile
import time
import traceback

from Autodesk.Revit.DB import (
    Arc,
    BoundingBoxIntersectsFilter,
    BuiltInCategory,
    BuiltInParameter,
    CurveLoop,
    Element,
    ExtrusionAnalyzer,
    FamilyInstance,
    FilteredElementCollector,
    Floor,
    FloorType,
    GeometryInstance,
    Line,
    Options,
    Outline,
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

FORCE_RESCAN = bool(globals().get('__shiftclick__', False))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

DEBUG = True
USE_TEMPLATES = True        # set False to bypass the per-symbol cache entirely
EXPORT_JSON = True          # dump a scoped diagnostic file when a click fails
EXPORT_ALWAYS = False       # also dump on every SUCCESSFUL click
DUMP_GRAPH = False          # write the whole graph to JSON right after scanning
EXPORT_RADIUS = 40.0        # ft of context around the click to include
REBUILD_ARCS = True

# Speed-only optimisation. It can drop a boundary element that sits just past
# the crop edge, which opens the bay next to it. Off until the missing-region
# bug is understood; turn on for very large plans once it is.
USE_CROP_FILTER = False
CROP_PADDING = 50.0         # ft of slack added around the crop outline

SHORT = doc.Application.ShortCurveTolerance   # ~0.00256 ft
SNAP = SHORT
COLLINEAR_TOL = 1.0e-6
MIN_FACE_AREA = 0.01                          # ft^2
Z_ALIGN_TOL = 1.0e-6
ARC_MIN_POINTS = 3                            # need >=2 edges to rebuild an arc

CACHE_KEY = 'hatchslab_graph_cache'
NO_SNAP = getattr(ObjectSnapTypes, 'None')

LINE_SOURCE = 0             # source index 0 always means "straight"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def element_id_value(element_id):
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def element_name(element):
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


def _sub(p, q):
    return (p[0] - q[0], p[1] - q[1])


def _cross(u, v):
    return u[0] * v[1] - u[1] * v[0]


def edge_key(a, b):
    return (a, b) if a < b else (b, a)


# ---------------------------------------------------------------------------
# Curve sources -- how arcs survive the tessellation
# ---------------------------------------------------------------------------

class SourceTable(object):
    """Every segment remembers which original curve it came from."""

    def __init__(self):
        self.entries = [('line',)]      # index 0 reserved for straight edges
        self.lookup = {}

    def add_curve(self, curve):
        if not isinstance(curve, Arc):
            return LINE_SOURCE
        try:
            centre = curve.Center
            key = ('arc',
                   round(centre.X, 6),
                   round(centre.Y, 6),
                   round(curve.Radius, 6))
        except Exception:
            return LINE_SOURCE

        index = self.lookup.get(key)
        if index is None:
            index = len(self.entries)
            self.entries.append(key)
            self.lookup[key] = index
        return index

    def is_arc(self, index):
        return index != LINE_SOURCE and self.entries[index][0] == 'arc'

    def arc_data(self, index):
        _, cx, cy, radius = self.entries[index]
        return (cx, cy), radius

    def dump(self):
        return [list(entry) for entry in self.entries]


SOURCES = SourceTable()


# ---------------------------------------------------------------------------
# Footprint extraction
# ---------------------------------------------------------------------------

PLAN_PLANE = Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ.Zero)


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


def _footprint_at_detail(element, detail):
    opts = Options()
    opts.ComputeReferences = False
    opts.IncludeNonVisibleObjects = False
    opts.DetailLevel = detail

    segments = []
    try:
        geo = element.get_Geometry(opts)
    except Exception as err:
        logger.debug('geometry failed on {0}: {1}'.format(element.Id, err))
        return segments

    for solid in iter_solids(geo):
        try:
            analyzer = ExtrusionAnalyzer.Create(solid, PLAN_PLANE, XYZ.BasisZ)
            base_face = analyzer.GetExtrusionBase()
        except Exception as err:
            logger.debug('analyzer failed on {0}: {1}'.format(element.Id, err))
            continue

        for curve_loop in base_face.GetEdgesAsCurveLoops():
            for curve in curve_loop:
                source = SOURCES.add_curve(curve)
                try:
                    pts = curve.Tessellate()
                except Exception:
                    continue
                for i in range(len(pts) - 1):
                    a = pts[i]
                    b = pts[i + 1]
                    if a.DistanceTo(b) > SHORT:
                        segments.append(((a.X, a.Y), (b.X, b.Y), source))
    return segments


def exact_footprint(element, primary_detail):
    """Read at the view's detail level; only fall back if that yields nothing."""
    segments = _footprint_at_detail(element, primary_detail)
    if not segments and primary_detail != ViewDetailLevel.Fine:
        segments = _footprint_at_detail(element, ViewDetailLevel.Fine)
    return segments


# ---------------------------------------------------------------------------
# Per-symbol template cache
# ---------------------------------------------------------------------------

def template_key(element):
    if not isinstance(element, FamilyInstance):
        return None
    symbol = element.Symbol
    if symbol is None:
        return None
    box = element.get_BoundingBox(None)
    if box is None:
        return None

    try:
        hand = bool(element.HandFlipped)
        facing = bool(element.FacingFlipped)
    except Exception:
        hand = facing = False

    return (
        element_id_value(symbol.Id),
        round(box.Max.X - box.Min.X, 4),
        round(box.Max.Y - box.Min.Y, 4),
        round(box.Max.Z - box.Min.Z, 4),
        bool(element.Mirrored),
        hand,
        facing,
    )


def z_aligned(transform):
    try:
        return abs(abs(transform.BasisZ.Z) - 1.0) < Z_ALIGN_TOL
    except Exception:
        return False


def to_local(transform, segments):
    inverse = transform.Inverse
    local = []
    for (ax, ay), (bx, by), source in segments:
        pa = inverse.OfPoint(XYZ(ax, ay, 0.0))
        pb = inverse.OfPoint(XYZ(bx, by, 0.0))
        local.append(((pa.X, pa.Y), (pb.X, pb.Y), source))
    return local


def to_model(transform, local_segments):
    model = []
    for (ax, ay), (bx, by), source in local_segments:
        pa = transform.OfPoint(XYZ(ax, ay, 0.0))
        pb = transform.OfPoint(XYZ(bx, by, 0.0))
        # An arc source is tied to a fixed centre, so a moved copy cannot
        # reuse it. Reuse the shape, drop the arc identity.
        model.append(((pa.X, pa.Y), (pb.X, pb.Y), LINE_SOURCE))
    return model


class FootprintReader(object):

    def __init__(self, primary_detail):
        self.primary_detail = primary_detail
        self.templates = {}
        self.exact_calls = 0
        self.template_hits = 0
        self.no_geometry = 0
        self.per_element = {}

    def read(self, element):
        eid = element_id_value(element.Id)

        transform = None
        if USE_TEMPLATES and isinstance(element, FamilyInstance):
            try:
                transform = element.GetTransform()
            except Exception:
                transform = None

        key = None
        if transform is not None and z_aligned(transform):
            key = template_key(element)

        if key is not None:
            cached = self.templates.get(key)
            if cached:
                self.template_hits += 1
                segments = to_model(transform, cached)
                self.per_element[eid] = ('template', len(segments))
                return segments

        self.exact_calls += 1
        segments = exact_footprint(element, self.primary_detail)

        if not segments:
            self.no_geometry += 1
            self.per_element[eid] = ('empty', 0)
            # Deliberately NOT cached -- 1.2.0 cached empties and blanked
            # every sibling instance sharing the key.
            return []

        # An arc-bearing footprint is kept element-specific: arc centres are
        # absolute, so they cannot be reused by a copy elsewhere.
        has_arc = any(SOURCES.is_arc(s) for _, _, s in segments)
        if key is not None and not has_arc:
            self.templates[key] = to_local(transform, segments)

        self.per_element[eid] = ('exact', len(segments))
        return segments


# ---------------------------------------------------------------------------
# Element collection
# ---------------------------------------------------------------------------

CATEGORIES = (BuiltInCategory.OST_StructuralFraming,
              BuiltInCategory.OST_StructuralColumns)


def crop_filter(view):
    if not USE_CROP_FILTER:
        return None
    try:
        if not view.CropBoxActive:
            return None
        box = view.CropBox
        transform = box.Transform
        corners = []
        for x in (box.Min.X, box.Max.X):
            for y in (box.Min.Y, box.Max.Y):
                for z in (box.Min.Z, box.Max.Z):
                    corners.append(transform.OfPoint(XYZ(x, y, z)))
        pad = CROP_PADDING
        lo = XYZ(min(p.X for p in corners) - pad,
                 min(p.Y for p in corners) - pad,
                 min(p.Z for p in corners) - 1000.0)
        hi = XYZ(max(p.X for p in corners) + pad,
                 max(p.Y for p in corners) + pad,
                 max(p.Z for p in corners) + 1000.0)
        return BoundingBoxIntersectsFilter(Outline(lo, hi))
    except Exception as err:
        logger.debug('crop filter unavailable: {0}'.format(err))
        return None


def collect_elements(view):
    bbox_filter = crop_filter(view)
    elements = []
    for bic in CATEGORIES:
        collector = FilteredElementCollector(doc, view.Id) \
            .OfCategory(bic) \
            .WhereElementIsNotElementType()
        if bbox_filter is not None:
            collector = collector.WherePasses(bbox_filter)
        elements.extend(collector.ToElements())
    return elements


def read_detail_level(view):
    """Match what the view draws -- this is the 1.2.0 regression fix."""
    try:
        detail = view.DetailLevel
    except Exception:
        return ViewDetailLevel.Fine
    if detail == ViewDetailLevel.Coarse:
        # Coarse renders framing as a stick with no solid; Fine is the only
        # honest substitute.
        return ViewDetailLevel.Fine
    return detail


def gather_boundary_segments(elements, primary_detail):
    reader = FootprintReader(primary_detail)
    segments = []
    total = len(elements)
    step = max(1, total // 40)

    with forms.ProgressBar(
            title='Reading beams and columns... {value}/{max_value}',
            cancellable=True) as pbar:
        for idx, element in enumerate(elements):
            if idx % step == 0:
                if pbar.cancelled:
                    break
                pbar.update_progress(idx + 1, total)
            segments.extend(reader.read(element))

    return segments, reader


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------

class SegmentGrid(object):

    def __init__(self, cell):
        self.cell = cell
        self.buckets = {}

    def _range(self, seg):
        (x1, y1), (x2, y2) = seg[0], seg[1]
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


def pick_cell_size(segments):
    if not segments:
        return 2.0
    lengths = sorted(math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1])
                     for s in segments)
    median = lengths[len(lengths) // 2]
    return max(1.0, min(20.0, median * 2.0))


def pair_cuts(seg_a, seg_b):
    pa, qa = seg_a[0], seg_a[1]
    pb, qb = seg_b[0], seg_b[1]
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
    grid = SegmentGrid(pick_cell_size(segments))
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
        (x1, y1), (x2, y2), source = seg
        params = sorted(set([0.0, 1.0] + cuts[i]))
        for k in range(len(params) - 1):
            t0, t1 = params[k], params[k + 1]
            if t1 - t0 < 1.0e-9:
                continue
            a = (x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0)
            b = (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)
            if math.hypot(b[0] - a[0], b[1] - a[1]) > SHORT:
                pieces.append((a, b, source))
    return pieces


# ---------------------------------------------------------------------------
# Planar graph
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
    edge_source = {}

    for a, b, source in pieces:
        na = nodes.add(a[0], a[1])
        nb = nodes.add(b[0], b[1])
        if na == nb:
            continue
        adjacency.setdefault(na, set()).add(nb)
        adjacency.setdefault(nb, set()).add(na)
        key = edge_key(na, nb)
        # An arc source wins over a straight one on the same edge.
        if source != LINE_SOURCE or key not in edge_source:
            edge_source[key] = source

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

    return nodes.points, adjacency, edge_source, raw_nodes


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
            if x1 + (y - y1) * (x2 - x1) / (y2 - y1) > x:
                inside = not inside
    return inside


class FaceIndex(object):

    def __init__(self, points, faces, cell=40.0):
        self.points = points
        self.faces = faces
        self.cell = cell
        self.buckets = {}
        self.boxes = []
        for index, cycle in enumerate(faces):
            xs = [points[n][0] for n in cycle]
            ys = [points[n][1] for n in cycle]
            box = (min(xs), min(ys), max(xs), max(ys))
            self.boxes.append(box)
            for i in range(int(math.floor(box[0] / cell)),
                           int(math.floor(box[2] / cell)) + 1):
                for j in range(int(math.floor(box[1] / cell)),
                               int(math.floor(box[3] / cell)) + 1):
                    self.buckets.setdefault((i, j), []).append(index)

    def find(self, x, y):
        key = (int(math.floor(x / self.cell)), int(math.floor(y / self.cell)))
        best = None
        best_area = None
        for index in self.buckets.get(key, ()):
            x0, y0, x1, y1 = self.boxes[index]
            if x < x0 or x > x1 or y < y0 or y > y1:
                continue
            cycle = self.faces[index]
            if not point_in_cycle(self.points, cycle, x, y):
                continue
            area = abs(signed_area(self.points, cycle))
            if best_area is None or area < best_area:
                best_area = area
                best = cycle
        return best, best_area


def nearest_face_distance(points, faces, x, y):
    best = None
    for cycle in faces:
        cx = sum(points[n][0] for n in cycle) / float(len(cycle))
        cy = sum(points[n][1] for n in cycle) / float(len(cycle))
        d = math.hypot(cx - x, cy - y)
        if best is None or d < best:
            best = d
    return best


# ---------------------------------------------------------------------------
# Cycle -> CurveLoop, with arcs preserved
# ---------------------------------------------------------------------------

def group_runs(cycle, edge_source):
    """Split the ring into consecutive runs sharing one source curve."""
    count = len(cycle)
    sources = []
    for i in range(count):
        a = cycle[i]
        b = cycle[(i + 1) % count]
        sources.append(edge_source.get(edge_key(a, b), LINE_SOURCE))

    # Rotate so index 0 starts a run, otherwise the wrap-around splits one.
    offset = 0
    for i in range(count):
        if sources[i] != sources[i - 1]:
            offset = i
            break

    runs = []
    current_source = None
    current = []
    for k in range(count):
        i = (offset + k) % count
        source = sources[i]
        if source != current_source and current:
            runs.append((current_source, current))
            current = []
        current_source = source
        if not current:
            current.append(cycle[i])
        current.append(cycle[(i + 1) % count])
    if current:
        runs.append((current_source, current))
    return runs


def simplify_line_run(points, node_run):
    """Drop collinear interior vertices, keeping both ends."""
    ring = [points[n] for n in node_run]
    if len(ring) <= 2:
        return ring
    kept = [ring[0]]
    for i in range(1, len(ring) - 1):
        u = _sub(ring[i], kept[-1])
        v = _sub(ring[i + 1], ring[i])
        lu = math.hypot(u[0], u[1])
        lv = math.hypot(v[0], v[1])
        if lu < 1.0e-9 or lv < 1.0e-9:
            continue
        if abs(_cross(u, v)) / (lu * lv) > COLLINEAR_TOL:
            kept.append(ring[i])
    kept.append(ring[-1])
    return kept


def arc_through(points, node_run, elevation):
    """Rebuild one Arc from a run of chords off the same circle."""
    if len(node_run) < ARC_MIN_POINTS:
        return None
    start = points[node_run[0]]
    end = points[node_run[-1]]
    middle = points[node_run[len(node_run) // 2]]

    p0 = XYZ(start[0], start[1], elevation)
    p1 = XYZ(end[0], end[1], elevation)
    pm = XYZ(middle[0], middle[1], elevation)

    if p0.DistanceTo(p1) <= SHORT or p0.DistanceTo(pm) <= SHORT:
        return None
    try:
        return Arc.Create(p0, p1, pm)
    except Exception as err:
        logger.debug('arc rebuild failed: {0}'.format(err))
        return None


def build_loop(points, cycle, edge_source, elevation):
    """Return (CurveLoop, arc_count, curve_count) or (None, 0, 0)."""
    curves = []
    arc_count = 0

    runs = group_runs(cycle, edge_source) if REBUILD_ARCS else \
        [(LINE_SOURCE, list(cycle) + [cycle[0]])]

    for source, node_run in runs:
        if REBUILD_ARCS and SOURCES.is_arc(source):
            arc = arc_through(points, node_run, elevation)
            if arc is not None:
                curves.append(arc)
                arc_count += 1
                continue
            # fall through and emit chords if the rebuild failed

        ring = simplify_line_run(points, node_run)
        for i in range(len(ring) - 1):
            a = XYZ(ring[i][0], ring[i][1], elevation)
            b = XYZ(ring[i + 1][0], ring[i + 1][1], elevation)
            if a.DistanceTo(b) <= SHORT:
                continue
            curves.append(Line.CreateBound(a, b))

    if len(curves) < 3:
        return None, 0, 0

    loop = CurveLoop()
    for curve in curves:
        try:
            loop.Append(curve)
        except Exception as err:
            logger.debug('append failed: {0}'.format(err))
            return None, 0, 0
    return loop, arc_count, len(curves)


# ---------------------------------------------------------------------------
# Diagnostic export
# ---------------------------------------------------------------------------

def export_dump(view, pick, points, faces, edge_source, reader_info,
                chosen, note):
    """Write everything within EXPORT_RADIUS of the click to a JSON file."""
    try:
        cx, cy = pick.X, pick.Y
        radius = EXPORT_RADIUS

        near_nodes = {}
        for index, (x, y) in enumerate(points):
            if abs(x - cx) <= radius and abs(y - cy) <= radius:
                near_nodes[index] = (round(x, 5), round(y, 5))

        near_edges = []
        for (a, b), source in edge_source.items():
            if a in near_nodes or b in near_nodes:
                near_edges.append([a, b, source])

        near_faces = []
        for cycle in faces:
            xs = [points[n][0] for n in cycle]
            ys = [points[n][1] for n in cycle]
            if (max(xs) < cx - radius or min(xs) > cx + radius or
                    max(ys) < cy - radius or min(ys) > cy + radius):
                continue
            near_faces.append({
                'nodes': list(cycle),
                'area_sqft': round(abs(signed_area(points, cycle)), 4),
                'centroid': [round(sum(xs) / len(xs), 4),
                             round(sum(ys) / len(ys), 4)],
                'contains_click': point_in_cycle(points, cycle, cx, cy),
            })
        near_faces.sort(key=lambda f: f['area_sqft'])

        payload = {
            'version': __version__,
            'note': note,
            'view': {
                'name': element_name(view),
                'id': element_id_value(view.Id),
                'detail_level': str(view.DetailLevel),
            },
            'settings': {
                'use_templates': USE_TEMPLATES,
                'use_crop_filter': USE_CROP_FILTER,
                'rebuild_arcs': REBUILD_ARCS,
                'snap_ft': SNAP,
                'min_face_area_sqft': MIN_FACE_AREA,
                'export_radius_ft': radius,
            },
            'click': [round(cx, 5), round(cy, 5)],
            'reader': reader_info,
            'curve_sources': SOURCES.dump(),
            'nodes': dict((str(k), list(v)) for k, v in near_nodes.items()),
            'edges': near_edges,
            'faces_near_click': near_faces,
            'chosen_face_nodes': list(chosen) if chosen else None,
        }

        name = 'hatchslab_{0}.json'.format(int(time.time()))
        path = os.path.join(tempfile.gettempdir(), name)
        handle = open(path, 'w')
        try:
            handle.write(json.dumps(payload, indent=1))
        finally:
            handle.close()
        return path
    except Exception as err:
        logger.debug('export failed: {0}'.format(err))
        return None


def dump_full_graph(view, points, faces, edge_source, reader_info):
    """Write the entire graph -- every node, edge and region -- to JSON."""
    try:
        payload = {
            'version': __version__,
            'kind': 'full_graph',
            'view': {
                'name': element_name(view),
                'id': element_id_value(view.Id),
                'detail_level': str(view.DetailLevel),
            },
            'settings': {
                'use_templates': USE_TEMPLATES,
                'use_crop_filter': USE_CROP_FILTER,
                'rebuild_arcs': REBUILD_ARCS,
                'snap_ft': SNAP,
                'min_face_area_sqft': MIN_FACE_AREA,
            },
            'reader': reader_info,
            'curve_sources': SOURCES.dump(),
            'nodes': [[round(x, 5), round(y, 5)] for x, y in points],
            'edges': [[a, b, source]
                      for (a, b), source in edge_source.items()],
            'faces': [],
        }

        for cycle in faces:
            xs = [points[n][0] for n in cycle]
            ys = [points[n][1] for n in cycle]
            payload['faces'].append({
                'nodes': list(cycle),
                'area_sqft': round(abs(signed_area(points, cycle)), 4),
                'centroid': [round(sum(xs) / len(xs), 4),
                             round(sum(ys) / len(ys), 4)],
            })
        payload['faces'].sort(key=lambda f: f['area_sqft'])

        name = 'hatchslab_graph_{0}.json'.format(int(time.time()))
        path = os.path.join(tempfile.gettempdir(), name)
        handle = open(path, 'w')
        try:
            handle.write(json.dumps(payload, indent=1))
        finally:
            handle.close()
        return path
    except Exception as err:
        logger.debug('graph dump failed: {0}'.format(err))
        return None


# ---------------------------------------------------------------------------
# Type selection
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
        ['Structural Floor', 'Foundation Slab', 'Finish'],
        message='What should be created?  (ESC or Finish to close the tool)',
    )
    if not kind or kind == 'Finish':
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
# Sketch plane
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
# Session cache
# ---------------------------------------------------------------------------

def signature(view, elements, detail):
    ids = sorted(element_id_value(e.Id) for e in elements)
    return (doc.Title,
            element_id_value(view.Id),
            str(detail),
            USE_TEMPLATES,
            len(ids),
            hash(tuple(ids)))


def load_cached(sig):
    if FORCE_RESCAN:
        return None
    try:
        cached = script.get_envvar(CACHE_KEY)
    except Exception:
        return None
    if not cached or cached.get('signature') != sig:
        return None
    return cached


def store_cached(sig, points, faces, edge_source, sources, reader_info):
    try:
        script.set_envvar(CACHE_KEY, {
            'signature': sig,
            'points': points,
            'faces': faces,
            'edge_source': edge_source,
            'sources': sources,
            'reader': reader_info,
            'stamp': time.time(),
        })
    except Exception as err:
        logger.debug('cache store failed: {0}'.format(err))


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_regions(view):
    detail = read_detail_level(view)
    elements = collect_elements(view)
    if not elements:
        forms.alert('No structural framing or columns visible in this view.',
                    exitscript=True)

    sig = signature(view, elements, detail)
    cached = load_cached(sig)
    if cached is not None:
        SOURCES.entries = [tuple(e) for e in cached['sources']]
        age = time.time() - cached.get('stamp', 0)
        output.print_md(
            '_Reusing the scan from {0:.0f}s ago '
            '(SHIFT-click to force a rescan)._'.format(age))
        return (cached['points'], cached['faces'], cached['edge_source'],
                cached['reader'])

    clock = time.time()
    segments, reader = gather_boundary_segments(elements, detail)
    read_time = time.time() - clock

    if not segments:
        forms.alert('No usable geometry found on the beams and columns.',
                    exitscript=True)

    clock = time.time()
    pieces = split_all(segments)
    points, adjacency, edge_source, raw_nodes = build_graph(pieces)
    if not adjacency:
        forms.alert('No closed regions found -- every edge was a dead end.',
                    exitscript=True)

    faces = trace_faces(points, adjacency)
    usable = [f for f in faces if abs(signed_area(points, f)) >= MIN_FACE_AREA]
    graph_time = time.time() - clock

    arc_sources = sum(1 for e in SOURCES.entries if e[0] == 'arc')
    reader_info = {
        'elements': len(elements),
        'detail_level': str(detail),
        'exact_reads': reader.exact_calls,
        'template_hits': reader.template_hits,
        'no_geometry': reader.no_geometry,
        'arc_sources': arc_sources,
        'read_seconds': round(read_time, 2),
        'graph_seconds': round(graph_time, 2),
        'segments': len(segments),
        'pieces': len(pieces),
        'nodes': len(adjacency),
        'faces_traced': len(faces),
        'faces_usable': len(usable),
    }

    if DEBUG:
        total = reader.exact_calls + reader.template_hits
        reuse = (100.0 * reader.template_hits / total) if total else 0.0
        output.print_md('### Scan')
        output.print_md(
            '- detail level used: **{0}** (view setting)\n'
            '- elements: **{1}** (no geometry: {2})\n'
            '- exact reads: **{3}** / template reuses: **{4}** '
            '({5:.0f}% reused)\n'
            '- distinct arcs found: **{6}**\n'
            '- read **{7:.1f}s**, graph **{8:.1f}s**\n'
            '- segments {9} -> {10} split, nodes {11} (pre-prune {12})\n'
            '- faces: {13} traced, **{14}** usable'.format(
                detail, len(elements), reader.no_geometry,
                reader.exact_calls, reader.template_hits, reuse,
                arc_sources, read_time, graph_time,
                len(segments), len(pieces), len(adjacency), raw_nodes,
                len(faces), len(usable)))

    if not usable:
        forms.alert('The graph built, but no enclosed regions came out of it.',
                    exitscript=True)

    store_cached(sig, points, usable, edge_source, SOURCES.dump(), reader_info)
    return points, usable, edge_source, reader_info


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def draw_session(view, level, floor_type, kind, points, usable, index,
                 edge_source, reader_info, dumps):
    """One drawing round with a single slab type. ESC ends the round."""
    elevation = level.Elevation
    created = 0
    spurious_retried = False

    while True:
        started = time.time()
        try:
            pick = uidoc.Selection.PickPoint(
                NO_SNAP,
                'Click inside a region ({0}) - ESC to change type'.format(kind))
        except RevitExceptions.OperationCanceledException:
            if (time.time() - started) < 0.25 and not spurious_retried:
                spurious_retried = True
                continue
            break
        except Exception as err:
            output.print_md('- **PickPoint failed:** `{0}: {1}`'.format(
                type(err).__name__, err))
            output.print_md('```\n{0}\n```'.format(traceback.format_exc()))
            break

        spurious_retried = False

        try:
            cycle, area = index.find(pick.X, pick.Y)
        except Exception as err:
            output.print_md('- Region search failed: `{0}`'.format(err))
            continue

        if cycle is None:
            gap = nearest_face_distance(points, usable, pick.X, pick.Y)
            output.print_md(
                '- No region at ({0:.2f}, {1:.2f}). Nearest centre {2:.2f} ft '
                'away.'.format(pick.X, pick.Y, gap if gap is not None else -1))
            if EXPORT_JSON:
                path = export_dump(view, pick, points, usable, edge_source,
                                   reader_info, None, 'no region found at click')
                if path:
                    dumps.append(path)
                    output.print_md('  dump: `{0}`'.format(path))
            continue

        loop, arcs, curve_count = build_loop(points, cycle, edge_source, elevation)
        if loop is None:
            output.print_md('- Could not build a valid boundary here.')
            if EXPORT_JSON:
                path = export_dump(view, pick, points, usable, edge_source,
                                   reader_info, cycle, 'loop build failed')
                if path:
                    dumps.append(path)
                    output.print_md('  dump: `{0}`'.format(path))
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
                '- Created **{0}** -- {1:.2f} sq ft, {2} curves '
                '({3} arcs)'.format(element_name(floor_type), area,
                                    curve_count, arcs))
            if EXPORT_ALWAYS:
                path = export_dump(view, pick, points, usable, edge_source,
                                   reader_info, cycle, 'slab created ok')
                if path:
                    dumps.append(path)
                    output.print_md('  dump: `{0}`'.format(path))
        except Exception as err:
            transaction.RollBack()
            output.print_md('- **Create failed:** `{0}: {1}`'.format(
                type(err).__name__, err))
            if EXPORT_JSON:
                path = export_dump(view, pick, points, usable, edge_source,
                                   reader_info, cycle,
                                   'Floor.Create failed: {0}'.format(err))
                if path:
                    dumps.append(path)
                    output.print_md('  dump: `{0}`'.format(path))

    return created


def main():
    view = doc.ActiveView

    if not isinstance(view, ViewPlan):
        forms.alert('Run this from a plan view (floor plan or structural plan).',
                    exitscript=True)

    level = view.GenLevel
    if level is None:
        forms.alert('This plan view has no associated level.', exitscript=True)

    points, usable, edge_source, reader_info = build_regions(view)
    index = FaceIndex(points, usable)

    ensure_sketch_plane(view, level.Elevation)

    dumps = []
    if DUMP_GRAPH:
        path = dump_full_graph(view, points, usable, edge_source, reader_info)
        if path:
            dumps.append(path)
            output.print_md('Full graph written to `{0}`'.format(path))

    total = 0
    rounds = 0

    while True:
        floor_type, kind = choose_type()
        if floor_type is None:
            break

        rounds += 1
        output.print_md('### Round {0} - {1}'.format(
            rounds, element_name(floor_type)))
        output.print_md(
            'Click inside regions. **ESC** to pick a different type, '
            '**ESC again** to finish.')

        made = draw_session(view, level, floor_type, kind, points, usable,
                            index, edge_source, reader_info, dumps)
        total += made
        output.print_md('_{0} slab(s) this round._'.format(made))

    output.print_md('**Done.** {0} slab(s) across {1} round(s).'.format(
        total, rounds))
    if dumps:
        output.print_md('{0} JSON dump(s) in `{1}`'.format(
            len(dumps), tempfile.gettempdir()))


main()
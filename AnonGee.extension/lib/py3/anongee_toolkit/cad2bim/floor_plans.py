# -*- coding: utf-8 -*-
"""Split ONE dxf that holds SEVERAL floor plans into per-storey record sets.

The user's drawing convention (test9 / test10):

    * a BOUNDARY layer carries one rectangle around each floor plan (the plan
      itself plus its schedules), so the rectangles say where one storey's
      drawing ends and the next begins;
    * an ORIGIN layer carries ONE marker inside each rectangle -- the point of
      that plan which must land on the model's origin, so the storeys stack
      exactly on top of each other instead of sitting side by side as drawn.

Layer NAMES differ per drawing, so nothing here matches on names: the dialog
routes whichever layers the user picks to CATEGORY_FLOOR_BOUNDARY and
CATEGORY_FLOOR_ORIGIN, and this module works purely off those categories.

The output is one `FloorRegion` per rectangle, each carrying the records that
fall inside it ALREADY SHIFTED so its origin marker sits at (0, 0) -- feed one
region's records to the normal single-floor pipeline and it builds that storey.
Storeys are ordered bottom-up: by a level label found inside the rectangle when
there is one ("SECOND FLOOR PLAN", "LEVEL 3", "TERRACE"), else in reading order
(top row first, left to right), which matches how plans are laid out on a sheet.

Revit-free, so the split can be unit-tested and replayed from JSON exports.
"""

import math
import re

from . import config
from .classify.layers import (CATEGORY_FLOOR_BOUNDARY, CATEGORY_FLOOR_ORIGIN)

_MM = config.MM_PER_FT

_MIN_REGION_M2 = 4.0        # smaller than this is a detail box, not a floor plan
_ORIGIN_MAX_MM = 2000.0     # an origin marker is a POINT-like mark, not linework

# "GROUND FLOOR PLAN" / "FIRST FLOOR" / "LEVEL 2" / "2ND FLOOR" / "TERRACE PLAN"
_NAMED_LEVELS = (
    (r"\bbasement\b|\bbsmt\b", -1),
    (r"\bground\b|\bgf\b|\bplinth\b", 0),
    (r"\bterrace\b|\broof\b|\bhead\s*room\b", 999),
)
_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}
_LEVEL_NUMBER = re.compile(
    r"\b(?:level|floor|storey|story|flr|lvl)\s*[-_ ]?(\d+)\b|"
    r"\b(\d+)(?:st|nd|rd|th)\b", re.IGNORECASE)


class FloorRegion(object):
    """One storey's drawing: its boundary box, origin, records and level order.

    `records` are already SHIFTED so `origin` maps to (0, 0); `label` is the
    plan text that named it (None when the order came from the sheet layout),
    and `order` sorts the storeys bottom-up.
    """

    def __init__(self, bounds, origin, label=None, order=0, records=None,
                 texts=None):
        self.bounds = bounds          # (x0, y0, x1, y1) in internal feet
        self.origin = origin          # (x, y) in internal feet, DRAWN position
        self.label = label
        self.order = order
        self.records = records or []
        self.texts = texts or []

    @property
    def width_mm(self):
        return (self.bounds[2] - self.bounds[0]) * _MM

    @property
    def height_mm(self):
        return (self.bounds[3] - self.bounds[1]) * _MM

    def contains(self, x, y):
        x0, y0, x1, y1 = self.bounds
        return x0 <= x <= x1 and y0 <= y <= y1

    def __repr__(self):
        return "<FloorRegion {0} {1:.0f}x{2:.0f}mm {3} records>".format(
            self.label or "(unnamed)", self.width_mm, self.height_mm,
            len(self.records))


def level_order_from_text(text):
    """A sort key for a plan title, or None when the text names no storey.

    "GROUND FLOOR PLAN" -> 0, "FIRST FLOOR" -> 1, "LEVEL 3" -> 3,
    "2ND FLOOR PLAN" -> 2, "TERRACE" -> 999, "BASEMENT" -> -1.
    """
    if not text:
        return None
    lowered = text.lower()
    match = _LEVEL_NUMBER.search(lowered)
    if match:
        return int(match.group(1) or match.group(2))
    for word, value in _ORDINAL_WORDS.items():
        if re.search(r"\b" + word + r"\b", lowered):
            return value
    for pattern, value in _NAMED_LEVELS:
        if re.search(pattern, lowered):
            return value
    return None


def _record_bounds(record):
    xs = [p[0] for p in record.points]
    ys = [p[1] for p in record.points]
    return min(xs), min(ys), max(xs), max(ys)


def _record_point(record):
    """The point that decides which region a record belongs to (its centre)."""
    x0, y0, x1, y1 = _record_bounds(record)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def boundary_regions(records):
    """[(x0, y0, x1, y1)] -- one box per closed rectangle on the boundary layer.

    Boxes fully inside another box are dropped (a title block drawn inside the
    sheet boundary is not a second storey), and boxes smaller than
    _MIN_REGION_M2 are ignored as details.
    """
    boxes = []
    min_ft2 = _MIN_REGION_M2 * (1000.0 / _MM) ** 2
    for record in records:
        if record.category != CATEGORY_FLOOR_BOUNDARY:
            continue
        if len(record.points) < 3:
            continue
        x0, y0, x1, y1 = _record_bounds(record)
        if (x1 - x0) * (y1 - y0) < min_ft2:
            continue
        boxes.append((x0, y0, x1, y1))
    # a boundary rectangle drawn as four separate lines arrives as four records
    # covering the SAME box; merge duplicates and dissolve nested boxes
    merged = []
    for box in sorted(boxes, key=lambda b: -((b[2] - b[0]) * (b[3] - b[1]))):
        inside_existing = False
        for kept in merged:
            if (box[0] >= kept[0] - 1e-6 and box[1] >= kept[1] - 1e-6 and
                    box[2] <= kept[2] + 1e-6 and box[3] <= kept[3] + 1e-6):
                inside_existing = True
                break
        if not inside_existing:
            merged.append(box)
    return merged


def _boundary_lines_to_boxes(records):
    """Boxes recovered when the boundary rectangle is drawn as LOOSE lines.

    Four separate lines share corners; grouping by connectivity and taking each
    group's extents gives the same box a closed polyline would.
    """
    segments = []
    for record in records:
        if record.category != CATEGORY_FLOOR_BOUNDARY:
            continue
        pts = record.points
        for i in range(len(pts) - 1):
            segments.append(((pts[i][0], pts[i][1]),
                             (pts[i + 1][0], pts[i + 1][1])))
    if len(segments) < 4:
        return []
    parent = list(range(len(segments)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    tol = config.mm_to_ft(50.0)
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            for a in segments[i]:
                for b in segments[j]:
                    if math.hypot(a[0] - b[0], a[1] - b[1]) <= tol:
                        parent[find(i)] = find(j)
    groups = {}
    for i in range(len(segments)):
        groups.setdefault(find(i), []).append(segments[i])
    min_ft2 = _MIN_REGION_M2 * (1000.0 / _MM) ** 2
    boxes = []
    for group in groups.values():
        if len(group) < 4:
            continue
        xs = [q[0] for seg in group for q in seg]
        ys = [q[1] for seg in group for q in seg]
        box = (min(xs), min(ys), max(xs), max(ys))
        if (box[2] - box[0]) * (box[3] - box[1]) >= min_ft2:
            boxes.append(box)
    return boxes


def origin_points(records):
    """[(x, y)] -- one point per marker on the origin layer.

    A marker is any small piece of linework (a point, a short cross, a small
    circle): its centre is the origin. Pieces closer than the marker size are
    merged, so a cross drawn as two lines yields ONE point.
    """
    points = []
    max_ft = config.mm_to_ft(_ORIGIN_MAX_MM)
    for record in records:
        if record.category != CATEGORY_FLOOR_ORIGIN:
            continue
        x0, y0, x1, y1 = _record_bounds(record)
        if (x1 - x0) > max_ft or (y1 - y0) > max_ft:
            continue
        points.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0))
    merged = []
    for x, y in points:
        for i, (mx, my) in enumerate(merged):
            if math.hypot(x - mx, y - my) <= max_ft:
                merged[i] = ((mx + x) / 2.0, (my + y) / 2.0)
                break
        else:
            merged.append((x, y))
    return merged


def _shift_record(record, dx, dy):
    """A copy of `record` moved by (dx, dy); the original is left untouched."""
    clone = record.__class__.__new__(record.__class__)
    clone.__dict__.update(record.__dict__)
    clone.points = [(p[0] + dx, p[1] + dy, p[2] if len(p) > 2 else 0.0)
                    for p in record.points]
    return clone


def _shift_text(text, dx, dy):
    clone = text.__class__.__new__(text.__class__)
    clone.__dict__.update(text.__dict__)
    point = getattr(text, "point_internal", None)
    if point is not None:
        clone.point_internal = (point[0] + dx, point[1] + dy,
                                point[2] if len(point) > 2 else 0.0)
    return clone


def split_floors(records, texts=None, align=True, marker_records=None):
    """Split one drawing into per-storey FloorRegions.

    `marker_records` supplies the boundary/origin geometry when it is not in
    `records` -- a plan's origin is usually a bare POINT, which the Revit link
    does not always import, so the pushbutton reads the markers from the DXF
    records and splits the Revit records by them.

    Returns (regions, notes). `regions` is bottom-up; every region's records
    and texts are shifted so its origin marker lands on (0, 0) (pass
    align=False to keep the drawn positions). `notes` explains anything the
    convention could not resolve, so the console can say WHY a storey was
    dropped instead of silently building one floor.
    """
    notes = []
    markers = marker_records if marker_records is not None else records
    boxes = boundary_regions(markers)
    if not boxes:
        boxes = _boundary_lines_to_boxes(markers)
    if not boxes:
        return [], ["no closed rectangle on the floor-boundary layer"]

    origins = origin_points(markers)
    regions = []
    for box in boxes:
        inside = [p for p in origins
                  if box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]]
        if not inside:
            centre = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
            notes.append("floor box at ({0:.0f}, {1:.0f}) mm has no origin "
                         "marker -- using its centre".format(centre[0] * _MM,
                                                             centre[1] * _MM))
            origin = centre
        else:
            if len(inside) > 1:
                notes.append("floor box at ({0:.0f}, {1:.0f}) mm has {2} origin "
                             "markers -- using the first".format(
                                 box[0] * _MM, box[1] * _MM, len(inside)))
            origin = inside[0]
        regions.append(FloorRegion(box, origin))

    # name each region from the plan title inside it, if there is one
    for region in regions:
        best = None
        for text in (texts or []):
            point = getattr(text, "point_internal", None)
            if point is None or not region.contains(point[0], point[1]):
                continue
            order = level_order_from_text(getattr(text, "text", None))
            if order is None:
                continue
            if best is None or order < best[0]:
                best = (order, getattr(text, "text", "").strip())
        if best is not None:
            region.order, region.label = best

    unnamed = [r for r in regions if r.label is None]
    if unnamed:
        # sheet reading order: top row first, then left to right. Rows group by
        # overlapping y extents so a slightly misaligned plan stays in its row.
        ordered = sorted(unnamed, key=lambda r: (-r.bounds[3], r.bounds[0]))
        used = {r.order for r in regions if r.label is not None}
        next_order = 0
        for region in ordered:
            while next_order in used:
                next_order += 1
            region.order = next_order
            used.add(next_order)
        if len(unnamed) == len(regions) and len(regions) > 1:
            notes.append("no plan titles found -- storeys ordered by sheet "
                         "layout (top row first, then left to right)")

    for region in regions:
        dx, dy = ((-region.origin[0], -region.origin[1]) if align else (0.0, 0.0))
        for record in records:
            if record.category in (CATEGORY_FLOOR_BOUNDARY,
                                   CATEGORY_FLOOR_ORIGIN):
                continue
            x, y = _record_point(record)
            if region.contains(x, y):
                region.records.append(_shift_record(record, dx, dy))
        for text in (texts or []):
            point = getattr(text, "point_internal", None)
            if point is not None and region.contains(point[0], point[1]):
                region.texts.append(_shift_text(text, dx, dy))

    regions.sort(key=lambda r: r.order)
    empty = [r for r in regions if not r.records]
    for region in empty:
        notes.append("floor '{0}' has no geometry inside its boundary".format(
            region.label or "(unnamed)"))
    return [r for r in regions if r.records], notes

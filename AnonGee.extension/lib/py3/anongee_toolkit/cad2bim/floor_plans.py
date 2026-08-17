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
# Measured over the fixture DXFs: a real boundary layer covers 1.00 (Test9)
# and 0.67 (Test10, whose third plan is not boxed); the best impostor -- a
# layer of big members -- reaches only 0.28. Half sits well clear of both.
_MIN_COVERAGE = 0.5         # boundary boxes must enclose most of the drawing

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

# "TYPICAL FLOOR PLAN (2ND TO 8TH FLOOR)" / "... X5" / "... (4 NOS)"
_TYPICAL_RANGE = re.compile(
    r"(\d+)\s*(?:st|nd|rd|th)?\s*(?:to|through|~|-{1,2})\s*(\d+)\s*(?:st|nd|rd|th)?",
    re.IGNORECASE)
_TYPICAL_COUNT = re.compile(
    r"\bx\s*(\d+)\b|\b(\d+)\s*(?:nos?|times|floors?|storeys?|stories|levels?)\b",
    re.IGNORECASE)

# "Ground Floor @0.00+ Level" / "1st Floor @3.00+ Level" / "EL. +12.500"
_ELEVATION = re.compile(
    r"(?:@|\bel\.?\s*|\blvl\.?\s*)\s*([+-]?\d+(?:\.\d+)?)", re.IGNORECASE)
# ... and the other way round, which is how test12 writes it: "+8.600M LVL."
_ELEVATION_TRAILING = re.compile(
    r"([+-]?\d+(?:\.\d+)?)\s*(?:m|mm)?\.?\s*(?:lvl|level)\b", re.IGNORECASE)
# A caption names a storey with one of these; anything else inside a plan box is
# a dimension, a note or a mark, and must never end up as the storey's name.
_TITLE_WORDS = re.compile(
    r"\b(layout|plan|floor|storey|story|level|lvl|terrace|roof|parapet|lmr|"
    r"basement|podium|refuge|typical|stilt|mezzanine)\b", re.IGNORECASE)
_STRONG_TITLE_WORDS = re.compile(r"\b(layout|plan)\b", re.IGNORECASE)
_ELEV_MM_CUTOFF = 100.0     # above this the number is millimetres, not metres

# Auto-detection: layer NAMES only break ties, the shape of what is drawn decides.
_BOUNDARY_HINTS = ("boundar", "bound", "extent", "outline", "frame", "sheet")
_ORIGIN_HINTS = ("origin", "basept", "base point", "base_pt", "datum",
                 "refpt", "ref point", "insert")


class FloorRegion(object):
    """One storey's drawing: its boundary box, origin, records and level order.

    `records` are already SHIFTED so `origin` maps to (0, 0); `label` is the
    plan text that named it (None when the order came from the sheet layout),
    and `order` sorts the storeys bottom-up.
    """

    def __init__(self, bounds, origin, label=None, order=0, records=None,
                 texts=None, repeat=1, storey_height_mm=None, regions=None,
                 level_id=None):
        self.bounds = bounds          # (x0, y0, x1, y1) in internal feet
        self.origin = origin          # (x, y) in internal feet, DRAWN position
        self.label = label
        self.order = order
        self.records = records or []
        self.texts = texts or []
        # the hatches inside this storey: fold and sunk regions belong to the
        # plan they are drawn on, exactly as its records and notes do
        self.regions = regions or []
        self.repeat = repeat          # a TYPICAL plan stands for this many storeys
        # this storey's own floor-to-floor height; None means the tab's default.
        # NOT height_mm -- that property is the boundary BOX's height on the sheet.
        self.storey_height_mm = storey_height_mm
        # the MODEL level this storey builds on (the dialog's per-row Level
        # pick, an opaque id this module never reads); None keeps the
        # positional ladder the run has always used.
        self.level_id = level_id

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


# A general NOTE mentions storeys without being a plan title: Test12's
# "2) THE BEAM & COLUMN SIZES MAY VARY AT GROUND & PODIUM LEVEL." named four of
# its five storeys "GROUND". A note is numbered, or a sentence; a plan title is
# neither, and is never this long.
_NOTE_MARKER = re.compile(r"^\s*[\(\[]?\s*(?:\d{1,2}|[a-z])\s*[).\]]\s+", re.IGNORECASE)
_TITLE_MAX_CHARS = 80


def looks_like_a_plan_title(text):
    """False for text that mentions a storey but is prose, not a title."""
    if not text:
        return False
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    if len(text.strip()) > _TITLE_MAX_CHARS:
        return False
    if _NOTE_MARKER.match(first):
        return False               # "2) ..." / "(a) ..." is a numbered note
    if _STRONG_TITLE_WORDS.match(first):
        return True                # "LAYOUT AT PARAPET & LMR BOTTOM LVL." --
        #                            a caption announces itself in its first word
    if first.endswith(".") and len(re.findall(r"[A-Za-z]+", first)) >= 6:
        return False               # a full sentence, not a caption
    return True


def level_order_from_text(text):
    """A sort key for a plan title, or None when the text names no storey.

    "GROUND FLOOR PLAN" -> 0, "FIRST FLOOR" -> 1, "LEVEL 3" -> 3,
    "2ND FLOOR PLAN" -> 2, "TERRACE" -> 999, "BASEMENT" -> -1. Text that reads
    as a general note rather than a caption never names a storey.
    """
    if not text or not looks_like_a_plan_title(text):
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


def typical_count_from_text(text):
    """How many storeys one TYPICAL plan stands for, or None.

    "TYPICAL FLOOR PLAN (2ND TO 8TH FLOOR)" -> 7, "TYPICAL FLOOR PLAN X5" -> 5,
    "TYPICAL FLOOR (4 NOS)" -> 4. A plan that does not call itself typical
    always stands for itself, so a bare range elsewhere never counts.
    """
    if not text or "typical" not in text.lower():
        return None
    match = _TYPICAL_RANGE.search(text)
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        if high >= low:
            return high - low + 1
    match = _TYPICAL_COUNT.search(text)
    if match:
        count = int(match.group(1) or match.group(2))
        if count > 0:
            return count
    return None


def elevation_from_text(text):
    """The storey elevation a plan title states, in MILLIMETRES, or None.

    "Ground Floor @0.00+ Level" -> 0, "1st Floor @3.00+ Level" -> 3000,
    "EL. +12.500" -> 12500. Titles quote metres; a number big enough to be
    nothing else (over 100) is taken as millimetres already.
    """
    if not text:
        return None
    match = _ELEVATION.search(text) or _ELEVATION_TRAILING.search(text)
    if not match:
        return None
    value = float(match.group(1))
    return value if abs(value) >= _ELEV_MM_CUTOFF else value * 1000.0


def _squash(text):
    """Lower-cased and single-spaced: what two names must share to be one name."""
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def propose_level(title, level_names):
    """The model level a plan title names, or None when no single one does.

    Feeds the Multi-storey tab's per-row Level combo: "Ground Floor Level"
    <-> "Ground Floor" match on the words (either name containing the other,
    case and spacing ignored), and "1st Floor Plan" <-> "Level 1" match on
    the storey number both state. A proposal is only made when EXACTLY ONE
    level matches -- a level placed on the wrong storey silently is worse
    than a row left on "(auto)".
    """
    wanted = " {0} ".format(_squash(title))
    if not wanted.strip():
        return None
    contained = []
    for name in (level_names or []):
        squashed = " {0} ".format(_squash(name))
        if squashed.strip() and (squashed in wanted or wanted in squashed):
            contained.append(name)
    if contained:
        return contained[0] if len(contained) == 1 else None
    order = level_order_from_text(title)
    if order is None:
        return None
    numbered = [name for name in (level_names or [])
                if level_order_from_text(name) == order]
    return numbered[0] if len(numbered) == 1 else None


def describe_plan(texts):
    """What one floor box's texts say about it.

    Returns (label, order, repeat, elevation_mm) with order None when nothing
    inside names a storey the sort understands -- the caller then falls back to
    the sheet's reading order, as it always has.

    Two things beyond the ordered title, both from test12: a plan can be
    captioned "LAYOUT AT REFUGE FLOOR LVL." -- a real title naming no ordinal,
    which used to leave the storey unnamed -- and its elevation can sit in a
    note of its own ("+8.600M LVL.") rather than in the title.
    """
    ordered = None                  # (order, text)
    caption = None                  # (score, text)
    elevation = None
    for text in (texts or []):
        value = (getattr(text, "text", None) or "").strip()
        if not value:
            continue
        order = level_order_from_text(value)
        if order is not None and (ordered is None or order < ordered[0]):
            ordered = (order, value)
        if looks_like_a_plan_title(value) and _TITLE_WORDS.search(value):
            score = (2 if _STRONG_TITLE_WORDS.search(value) else 1, len(value))
            if caption is None or score > caption[0]:
                caption = (score, value)
        if elevation is None and _TITLE_WORDS.search(value):
            elevation = elevation_from_text(value)
    if ordered is not None:
        label, order = ordered[1], ordered[0]
        elevation = elevation_from_text(label) or elevation
    elif caption is not None:
        label, order = caption[1], None
    else:
        return None, None, 1, elevation
    return label, order, typical_count_from_text(label) or 1, elevation


_ROW_OVERLAP = 0.5          # boxes sharing this much height are on one row


def sheet_sequence(bounds):
    """Indices of `bounds` in sheet reading order: top row first, left to right.

    Plans on one row are rarely the same height -- test12's five plans differ by
    up to 7 m -- so grouping on the exact top edge shuffles them into five
    "rows" and reads them in the wrong order entirely. Boxes whose y extents
    overlap by half their height are one row.
    """
    remaining = sorted(range(len(bounds)), key=lambda i: -bounds[i][3])
    sequence = []
    while remaining:
        first = remaining.pop(0)
        low, high = bounds[first][1], bounds[first][3]
        row = [first]
        for index in list(remaining):
            y0, y1 = bounds[index][1], bounds[index][3]
            overlap = min(high, y1) - max(low, y0)
            shortest = min(high - low, y1 - y0)
            if shortest > 0 and overlap >= _ROW_OVERLAP * shortest:
                row.append(index)
                remaining.remove(index)
                low, high = min(low, y0), max(high, y1)
        sequence.extend(sorted(row, key=lambda i: bounds[i][0]))
    return sequence


def sheet_orders(bounds, orders):
    """Fill in the storeys the titles did not place, from the sheet layout.

    `bounds` and `orders` are parallel lists, one entry per floor box, `orders`
    holding None where no title named a storey. A plan without an ordinal is
    NOT simply pushed to the bottom of the stack: it belongs where the sheet
    draws it, BETWEEN the titled plans on either side of it. Test12 lays out
    2ND, TYPICAL, REFUGE, TERRACE, PARAPET left to right; filling the lowest
    free numbers instead put REFUGE and PARAPET underneath the 2nd floor.

    Sheet reading order is top row first, then left to right. Returns the
    filled orders (floats where a plan was interpolated -- they are sort keys,
    nothing counts with them).
    """
    sequence = sheet_sequence(bounds)
    filled = list(orders)
    if all(order is None for order in orders):
        for rank, index in enumerate(sequence):
            filled[index] = rank
        return filled
    for position, index in enumerate(sequence):
        if filled[index] is not None:
            continue
        before = None
        for earlier in reversed(sequence[:position]):
            if orders[earlier] is not None:
                before = orders[earlier]
                break
        after = None
        for later in sequence[position + 1:]:
            if orders[later] is not None:
                after = orders[later]
                break
        gap = sum(1 for i in sequence[:position] if orders[i] is None
                  and _same_slot(sequence, orders, i, index))
        if before is None:
            filled[index] = after - 1.0 - gap
        elif after is None or after <= before:
            filled[index] = before + 1.0 + gap
        else:
            step = (after - before) / (2.0 + gap)
            filled[index] = before + step * (1.0 + gap)
    return filled


def _same_slot(sequence, orders, first, second):
    """True when two untitled plans fall between the same titled pair."""
    def neighbours(index):
        position = sequence.index(index)
        before = next((orders[i] for i in reversed(sequence[:position])
                       if orders[i] is not None), None)
        after = next((orders[i] for i in sequence[position + 1:]
                      if orders[i] is not None), None)
        return before, after
    return neighbours(first) == neighbours(second)


def _record_bounds(record):
    xs = [p[0] for p in record.points]
    ys = [p[1] for p in record.points]
    return min(xs), min(ys), max(xs), max(ys)


def _record_point(record):
    """The point that decides which region a record belongs to (its centre)."""
    x0, y0, x1, y1 = _record_bounds(record)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def _on_layer(records, category, layer):
    """The marker records: those on `layer` when given, else those categorised.

    The dialog routes a picked layer to a category, but AUTO-DETECTION runs
    before any mapping exists -- it has only the raw layer names, so every
    marker reader takes the layer route too.
    """
    if layer:
        return [r for r in records if getattr(r, "layer", None) == layer]
    return [r for r in records if r.category == category]


def boundary_regions(records, layer=None):
    """[(x0, y0, x1, y1)] -- one box per closed rectangle on the boundary layer.

    Boxes fully inside another box are dropped (a title block drawn inside the
    sheet boundary is not a second storey), and boxes smaller than
    _MIN_REGION_M2 are ignored as details.
    """
    boxes = []
    min_ft2 = _MIN_REGION_M2 * (1000.0 / _MM) ** 2
    for record in _on_layer(records, CATEGORY_FLOOR_BOUNDARY, layer):
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


def _boundary_lines_to_boxes(records, layer=None):
    """Boxes recovered when the boundary rectangle is drawn as LOOSE lines.

    Four separate lines share corners; grouping by connectivity and taking each
    group's extents gives the same box a closed polyline would.
    """
    segments = []
    for record in _on_layer(records, CATEGORY_FLOOR_BOUNDARY, layer):
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


def origin_points(records, layer=None):
    """[(x, y)] -- one point per marker on the origin layer.

    A marker is any small piece of linework (a point, a short cross, a small
    circle): its centre is the origin. Pieces closer than the marker size are
    merged, so a cross drawn as two lines yields ONE point.
    """
    points = []
    max_ft = config.mm_to_ft(_ORIGIN_MAX_MM)
    for record in _on_layer(records, CATEGORY_FLOOR_ORIGIN, layer):
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


def split_floors(records, texts=None, align=True, marker_records=None,
                 boundary_layer=None, origin_layer=None, hatches=None):
    """Split one drawing into per-storey FloorRegions.

    `marker_records` supplies the boundary/origin geometry when it is not in
    `records` -- a plan's origin is usually a bare POINT, which the Revit link
    does not always import, so the pushbutton reads the markers from the DXF
    records and splits the Revit records by them.

    Returns (regions, notes). `regions` is bottom-up; every storey is shifted
    so its origin marker lands on the BASE storey's marker -- the base plan
    therefore does not move at all and the model is built straight on top of
    the drawing, with the upper storeys stacked onto it. (Shifting everything
    to (0, 0) instead put the model at Revit's origin, away from the CAD.)
    Pass align=False to keep every plan at its drawn position. `notes`
    explains anything the convention could not resolve, so the console can say
    WHY a storey was dropped instead of silently building one floor.
    """
    notes = []
    markers = marker_records if marker_records is not None else records
    boxes = boundary_regions(markers, boundary_layer)
    if not boxes:
        boxes = _boundary_lines_to_boxes(markers, boundary_layer)
    if not boxes:
        return [], ["no closed rectangle on the floor-boundary layer"]

    origins = origin_points(markers, origin_layer)
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

    # name each region from the plan title inside it, if there is one. A title
    # that names no ordinal ("LAYOUT AT REFUGE FLOOR LVL.") still NAMES the
    # storey; only its position in the stack comes from the sheet layout.
    sorted_by_title = []
    for region in regions:
        inside_texts = [text for text in (texts or [])
                        if getattr(text, "point_internal", None) is not None
                        and region.contains(text.point_internal[0],
                                            text.point_internal[1])]
        label, order, repeat, _elevation = describe_plan(inside_texts)
        if label is not None:
            region.label = label
            region.repeat = repeat
        if order is not None:
            region.order = order
            sorted_by_title.append(region)

    if len(sorted_by_title) < len(regions):
        known = [region.order if region in sorted_by_title else None
                 for region in regions]
        for region, order in zip(regions,
                                 sheet_orders([r.bounds for r in regions],
                                              known)):
            region.order = order
        if not sorted_by_title and len(regions) > 1:
            notes.append("no plan titles found -- storeys ordered by sheet "
                         "layout (top row first, then left to right)")

    # Anchor on the BASE storey's marker, not the model origin: the lowest
    # storey stays exactly where it is drawn, so the built model sits on top of
    # its CAD, and every storey above lands on the same marker.
    anchor = (0.0, 0.0)
    if align and regions:
        anchor = min(regions, key=lambda r: r.order).origin
    for region in regions:
        dx, dy = ((anchor[0] - region.origin[0], anchor[1] - region.origin[1])
                  if align else (0.0, 0.0))
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
        for hatch in (hatches or []):
            x, y = _record_point(hatch)
            if region.contains(x, y):
                region.regions.append(_shift_record(hatch, dx, dy))

    regions.sort(key=lambda r: r.order)
    empty = [r for r in regions if not r.records]
    for region in empty:
        notes.append("floor '{0}' has no geometry inside its boundary".format(
            region.label or "(unnamed)"))
    return [r for r in regions if r.records], notes


class StoreyDetection(object):
    """What auto-detection made of one drawing: is it a sheet of storeys?

    `multistorey` is what the dialog's checkbox should be set to; `plans` is one
    entry per detected floor plan, bottom-up, each a dict with `label`, `order`,
    `repeat` and `height_mm` (None until the user types one). `reason` is the
    one-line explanation the Multi-storey tab shows.
    """

    def __init__(self, multistorey=False, boundary_layer=None, origin_layer=None,
                 plans=None, reason="", notes=None):
        self.multistorey = multistorey
        self.boundary_layer = boundary_layer
        self.origin_layer = origin_layer
        self.plans = plans or []
        self.reason = reason
        self.notes = notes or []

    @property
    def storey_count(self):
        """Storeys BUILT: a typical plan counts once per repeat."""
        return sum(max(1, p.get("repeat") or 1) for p in self.plans)

    def __repr__(self):
        return "<StoreyDetection {0} plan(s) -> {1} storey(s) {2}>".format(
            len(self.plans), self.storey_count,
            "on" if self.multistorey else "off")


def _layer_of(record):
    return getattr(record, "layer", None)


def _hint_score(name, hints):
    lowered = (name or "").lower()
    return 1 if any(hint in lowered for hint in hints) else 0


def _disjoint(boxes):
    """True when no two boxes overlap -- floor plans never sit on top of each other."""
    slack = config.mm_to_ft(1.0)
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if (a[0] < b[2] - slack and b[0] < a[2] - slack and
                    a[1] < b[3] - slack and b[1] < a[3] - slack):
                return False
    return True


def _coverage(records, boxes, layer):
    """Fraction of the OTHER records that fall inside one of these boxes.

    This is what separates a real boundary layer from a layer of big members: a
    boundary box encloses a whole plan, so nearly everything drawn lands inside
    one, while 24 shear-wall outlines enclose almost nothing (Test9 picked its
    'PI_COLUMN & SHEAR WALL' layer as the boundary until this check went in).
    """
    others = [r for r in records if _layer_of(r) != layer and r.points]
    if not others:
        return 0.0
    inside = 0
    for record in others:
        x, y = _record_point(record)
        for box in boxes:
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                inside += 1
                break
    return float(inside) / len(others)


def _origin_score(records):
    """How much a layer looks like the ORIGIN convention: tiny lone marks."""
    max_ft = config.mm_to_ft(_ORIGIN_MAX_MM)
    marks = 0
    for record in records:
        x0, y0, x1, y1 = _record_bounds(record)
        if (x1 - x0) <= max_ft and (y1 - y0) <= max_ft:
            marks += 1
    return marks


def _boxes_on(records, layer):
    boxes = boundary_regions(records, layer)
    return boxes or _boundary_lines_to_boxes(records, layer)


def autodetect_marker_layers(records):
    """(boundary_layer, origin_layer) guessed from the drawing itself.

    Layer names differ per office, so the guess is SHAPE-first and a name hint
    only breaks ties -- that is what lets a drawing whose layers are called
    anything at all still be detected.

      * the BOUNDARY layer carries several big closed boxes and little else;
      * the ORIGIN layer carries small lone marks, EXACTLY ONE INSIDE EACH BOX.
        That last clause is what keeps a column layer out: its members are small
        too, but there are dozens of them per plan.

    Either may come back None.
    """
    by_layer = {}
    for record in records or []:
        name = _layer_of(record)
        if name:
            by_layer.setdefault(name, []).append(record)

    boundary, best = None, 0.0
    for name, group in by_layer.items():
        boxes = _boxes_on(records, name)
        if len(boxes) < 2:
            continue                       # one box is a title block, not a sheet
        if not _disjoint(boxes):
            continue                       # overlapping boxes are not floor plans
        covered = _coverage(records, boxes, name)
        if covered < _MIN_COVERAGE:
            continue                       # these boxes enclose almost nothing
        score = covered + _hint_score(name, _BOUNDARY_HINTS) * 0.5
        score -= 0.05 * max(0, len(group) - len(boxes))
        if score > best:
            boundary, best = name, score
    if boundary is None:
        return None, None

    boxes = _boxes_on(records, boundary)
    origin, best = None, 0.0
    for name, group in by_layer.items():
        if name == boundary:
            continue
        if _origin_score(group) < len(group):
            continue                       # something big lives on this layer too
        marks = origin_points(records, name)
        if len(marks) != len(boxes):
            continue                       # not one marker per plan
        per_box = [sum(1 for m in marks
                       if box[0] <= m[0] <= box[2] and box[1] <= m[1] <= box[3])
                   for box in boxes]
        if set(per_box) != set([1]):
            continue                       # not exactly one INSIDE each plan
        points = sum(1 for r in group if getattr(r, "kind", None) == "point")
        score = (1.0 + _hint_score(name, _ORIGIN_HINTS)
                 + float(points) / max(1, len(group)))
        if score > best:
            origin, best = name, score
    return boundary, origin


def autodetect_storeys(records, texts=None, boundary_layer=None,
                       origin_layer=None):
    """StoreyDetection: does this ONE drawing hold several floor plans?

    Runs the same boundary/origin convention the split uses, but off raw LAYER
    names so it can run before any mapping exists -- the dialog calls it while
    it builds, ticks its multi-storey box from the answer and fills the per
    storey rows. Explicit layers (the user picked some) are honoured; otherwise
    they are guessed by autodetect_marker_layers.
    """
    notes = []
    records = records or []
    if not boundary_layer and not origin_layer:
        boundary_layer, origin_layer = autodetect_marker_layers(records)
    if not boundary_layer:
        return StoreyDetection(
            reason="no layer boxes each floor plan -- building as one storey")

    boxes = boundary_regions(records, boundary_layer)
    if not boxes:
        boxes = _boundary_lines_to_boxes(records, boundary_layer)
    if len(boxes) < 2:
        return StoreyDetection(
            boundary_layer=boundary_layer, origin_layer=origin_layer,
            reason="layer '{0}' holds {1} floor box -- building as one "
                   "storey".format(boundary_layer, len(boxes)))

    origins = origin_points(records, origin_layer) if origin_layer else []
    plans = []
    for box in boxes:
        inside_texts = [text for text in (texts or [])
                        if getattr(text, "point_internal", None) is not None
                        and box[0] <= text.point_internal[0] <= box[2]
                        and box[1] <= text.point_internal[1] <= box[3]]
        label, order, repeat, elevation = describe_plan(inside_texts)
        inside = [p for p in origins
                  if box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]]
        plans.append({"label": label, "order": order, "repeat": repeat,
                      "height_mm": None, "bounds": box,
                      "elevation_mm": elevation,
                      "has_origin": bool(inside)})

    # a plan the titles did not place goes where the SHEET draws it, exactly as
    # the split does it
    named = [p for p in plans if p["order"] is not None]
    for plan, order in zip(plans, sheet_orders([p["bounds"] for p in plans],
                                               [p["order"] for p in plans])):
        plan["order"] = order
    plans.sort(key=lambda p: p["order"])

    _heights_from_elevations(plans, notes)

    covered = _coverage(records, boxes, boundary_layer)
    if covered < 0.9:
        notes.append("{0:.0f}% of the drawing lies outside the floor boxes and "
                     "will not be built".format((1.0 - covered) * 100.0))
    if not origin_layer:
        notes.append("no origin layer found -- each plan will be anchored on "
                     "its boundary centre")
    else:
        missing = [p for p in plans if not p["has_origin"]]
        if missing:
            notes.append("{0} of {1} floor boxes have no origin marker".format(
                len(missing), len(plans)))
    if not named:
        notes.append("no plan titles found -- storeys ordered by sheet layout")
    repeats = [p for p in plans if p["repeat"] > 1]
    for plan in repeats:
        notes.append("'{0}' is a typical plan -- building it {1} times".format(
            plan["label"], plan["repeat"]))

    detection = StoreyDetection(
        multistorey=True, boundary_layer=boundary_layer,
        origin_layer=origin_layer, plans=plans, notes=notes)
    detection.reason = "{0} floor plan(s) on layer '{1}'{2} -- {3} storey(s)".format(
        len(plans), boundary_layer,
        ", origins on '{0}'".format(origin_layer) if origin_layer else "",
        detection.storey_count)
    return detection


def _heights_from_elevations(plans, notes):
    """Fill each plan's height from the NEXT plan's stated elevation.

    Titles like "1st Floor @3.00+ Level" quote where the storey sits, so a
    consecutive pair states the rise between them -- which is exactly the
    per-storey height the Multi-storey tab wants, without the user typing it.
    """
    filled = 0
    for index, plan in enumerate(plans[:-1]):
        here = plan.get("elevation_mm")
        above = plans[index + 1].get("elevation_mm")
        if here is None or above is None:
            continue
        rise = above - here
        if rise <= 0:
            continue
        # a typical plan stands for `repeat` storeys, so the stated rise to the
        # next plan covers all of them
        plan["height_mm"] = rise / max(1, int(plan.get("repeat") or 1))
        filled += 1
    if filled:
        notes.append("{0} storey height(s) read from the plan titles".format(
            filled))
    return plans


def apply_storey_settings(regions, settings):
    """Rebuild the storey stack from the dialog's table.

    `settings` is one row per STOREY, bottom-up, each naming which detected plan
    it uses ("plan": an index into the detection's plan list). That is what lets
    the same drawing build several floors -- a typical plan drawn once and used
    on rows 2, 3 and 4 -- and what makes the row ORDER the build order, so a
    storey can be moved up or down the stack.

    A row the user unticked is dropped. With no settings, or rows that name no
    plan, the split's own order is kept untouched.
    """
    if not settings:
        return regions
    by_label = dict((r.label, r) for r in regions if r.label)
    stack = []
    for index, row in enumerate(settings):
        if not row.get("include", True):
            continue
        source = None
        if row.get("plan") is not None:
            position = int(row["plan"])
            if 0 <= position < len(regions):
                source = regions[position]
        if source is None:
            source = by_label.get(row.get("label"))
        if source is None and index < len(regions):
            source = regions[index]
        if source is None:
            continue
        storey = _reuse(source)
        height = row.get("height_mm")
        if height:
            storey.storey_height_mm = float(height)
        repeat = row.get("repeat")
        if repeat:
            storey.repeat = max(1, int(repeat))
        # the row's Level pick, carried as-is: the run pipeline reads it, this
        # module only keeps it with the storey it belongs to
        storey.level_id = row.get("level_id")
        stack.append(storey)
    return stack or regions


def _reuse(region):
    """A shallow copy of a region, so ONE plan can build several storeys.

    The records are SHARED, not copied: they are read-only to the builders, and
    a typical plan reused five times would otherwise carry five copies of a
    whole floor's geometry.
    """
    return FloorRegion(region.bounds, region.origin, label=region.label,
                       order=region.order, records=region.records,
                       texts=region.texts, repeat=region.repeat,
                       storey_height_mm=region.storey_height_mm,
                       regions=region.regions, level_id=region.level_id)


def expand_repeats(regions):
    """[(region, label)] with each TYPICAL plan repeated to its storey count."""
    out = []
    for region in regions:
        count = max(1, int(region.repeat or 1))
        for index in range(count):
            label = region.label or "storey {0}".format(len(out) + 1)
            if count > 1:
                label = "{0} ({1}/{2})".format(label, index + 1, count)
            out.append((region, label))
    return out

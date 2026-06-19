# -*- coding: utf-8 -*-
"""Parse structural marks from DXF text and match them to members.

A label like "C1 400x400" or "B1 230x500" carries the one thing geometry alone
cannot give: the member's intended size (and, for a beam, its DEPTH). This module
turns those strings into (name, b_mm, h_mm) and finds the nearest sized label to a
member's centroid so column/beam sizing can be refined from the drawing's own text.

Revit-free and 2D (internal feet), so it is unit-testable outside Revit.
"""

import re

# size token: 400x400, 230 x 500, 400X600, 400*600 (b first, h second -- order kept)
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[x×X*]\s*(\d+(?:\.\d+)?)")
# mark token: one to three letters then digits, optional trailing letter (C1, RB12, C1A)
_MARK_RE = re.compile(r"\b([A-Za-z]{1,3}\d+[A-Za-z]?)\b")


def parse_mark(text):
    """Parse one text string into (name, b_mm, h_mm); any field may be None.

    `name` is the first mark-like token (e.g. "C1"); `b_mm`/`h_mm` come from the
    first BxH token, order preserved (b = first number, h = second). Tolerant of
    surrounding junk and multi-line text.
    """
    if not text:
        return (None, None, None)
    flat = text.replace("\n", " ").strip()

    b_mm = h_mm = None
    size = _SIZE_RE.search(flat)
    if size:
        try:
            b_mm = float(size.group(1))
            h_mm = float(size.group(2))
        except (ValueError, TypeError):
            b_mm = h_mm = None

    name = None
    mark = _MARK_RE.search(flat)
    if mark:
        name = mark.group(1).upper()

    return (name, b_mm, h_mm)


def parse_texts(texts):
    """Stamp .mark/.b_mm/.h_mm on every TextRecord in place; return the list."""
    for record in texts:
        name, b_mm, h_mm = parse_mark(record.text)
        record.mark = name
        record.b_mm = b_mm
        record.h_mm = h_mm
    return texts


def sized_texts(texts):
    """The subset of texts that carry a usable BxH size and an internal point."""
    return [t for t in texts
            if t.b_mm is not None and t.h_mm is not None and t.point_internal]


def parse_schedule(texts):
    """Build a {mark: (b_mm, h_mm)} lookup from a column-schedule's text cells.

    A column schedule is a table; in DXF its cells are individual TEXT entities.
    This reconstructs the mark->size mapping the table encodes so a plan label
    that carries ONLY a mark ("C9") can still be sized from its schedule row.

    Two cell layouts are handled:
      * inline -- one cell carries both mark and size ("C1  400x600"); these are
        position-independent and always trusted first;
      * split -- the mark and the size sit in separate cells on the same table
        row, paired by their shared y (the nearest mark cell to a size cell that
        is more to its side than above/below it).
    On a conflict the inline reading wins, then the first split pairing found.
    Returns {} for no input. Sizes keep (b, h) order as written.
    """
    schedule = {}
    if not texts:
        return schedule

    parsed = []   # (mark, b_mm, h_mm, (x, y)) for every cell we can place
    for record in texts:
        mark, b_mm, h_mm = parse_mark(record.text)
        parsed.append((mark, b_mm, h_mm, _schedule_xy(record)))

    # 1. Inline cells: a single cell carrying both a mark and a size.
    for mark, b_mm, h_mm, _xy in parsed:
        if mark and b_mm is not None and h_mm is not None:
            schedule.setdefault(mark, (b_mm, h_mm))

    # 2. Split cells: pair each size-only cell with its row's mark-only cell.
    mark_cells = [(mark, xy) for mark, b_mm, h_mm, xy in parsed
                  if mark and b_mm is None and xy is not None]
    size_cells = [(b_mm, h_mm, xy) for mark, b_mm, h_mm, xy in parsed
                  if b_mm is not None and h_mm is not None and mark is None
                  and xy is not None]
    for b_mm, h_mm, (sx, sy) in size_cells:
        best_mark = None
        best_d2 = None
        for mark, (mx, my) in mark_cells:
            dx, dy = mx - sx, my - sy
            if abs(dy) >= abs(dx):
                continue   # the mark is in another row (above/below), not this one
            d2 = dx * dx + dy * dy
            if best_d2 is None or d2 < best_d2:
                best_d2, best_mark = d2, mark
        if best_mark and best_mark not in schedule:
            schedule[best_mark] = (b_mm, h_mm)

    return schedule


def _schedule_xy(record):
    """Planar (x, y) for a schedule cell: internal feet if mapped, else DXF coords.

    Only the cells' positions RELATIVE to each other matter for row pairing, and
    both spaces share one scale within a file, so either works."""
    point = record.point_internal or record.point
    if not point:
        return None
    return (point[0], point[1])


def nearest_sized_text(cx, cy, candidates, radius_ft):
    """Return the nearest sized TextRecord within radius_ft of (cx, cy), or None.

    `candidates` should already be filtered to sized_texts (each has b_mm/h_mm and
    point_internal). Distance is planar (x, y) in feet.
    """
    best = None
    best_d2 = radius_ft * radius_ft
    for text in candidates:
        px, py = text.point_internal[0], text.point_internal[1]
        d2 = (px - cx) ** 2 + (py - cy) ** 2
        if d2 <= best_d2:
            best = text
            best_d2 = d2
    return best

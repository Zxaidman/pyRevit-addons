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

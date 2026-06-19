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
    This reconstructs the mark->size mapping so a plan label that carries ONLY a
    mark ("C9") can still be sized from its schedule row.

    Three cell layouts are handled, most specific first:
      * tabular -- a real table with a header row (e.g. "Mark W L H", repeated for
        several side-by-side blocks). The header fixes each column's x and role;
        every data row is read column by column. Plan size is W x L; a height
        column (H) is ignored. This is the common CAD column schedule.
      * inline -- one cell carries both mark and size ("C1  400x600").
      * split -- a mark cell and a single size cell ("400x600") share a row.
    On a conflict the tabular reading wins, then inline, then the first split.
    Returns {} for no input. Sizes keep (b, h) order as written.
    """
    schedule = {}
    if not texts:
        return schedule

    placed = [(record.text, _schedule_xy(record)) for record in texts]
    cells = [(xy[0], xy[1], text) for text, xy in placed if xy]

    # 1. Tabular: header-driven, the usual CAD column schedule.
    for mark, size in _parse_schedule_table(_cluster_rows(cells)).items():
        schedule.setdefault(mark, size)

    parsed = [(parse_mark(text) + (xy,)) for text, xy in placed]

    # 2. Inline cells: a single cell carrying both a mark and a size.
    for mark, b_mm, h_mm, _xy in parsed:
        if mark and b_mm is not None and h_mm is not None:
            schedule.setdefault(mark, (b_mm, h_mm))

    # 3. Split cells: pair each size-only cell with its row's mark-only cell.
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


# Schedule header keywords -> column role. Plan size is W x L; H is the column's
# vertical height (ignored for the footprint). Single letters cover terse CAD
# headers ("W L H"); full words cover verbose ones.
_HDR_MARK = ("mark", "ref", "col", "column", "type", "no", "id")
_HDR_W = ("w", "b", "width", "breadth")
_HDR_L = ("l", "d", "depth", "length")
_HDR_H = ("h", "ht", "height", "lvl", "level")
_HDR_SIZE = ("size", "section", "dim", "dimensions", "bxd", "wxl", "wxd")


def _header_role(text):
    """Role of a header cell ('mark'/'w'/'l'/'h'/'size'), or None if not a header."""
    t = (text or "").strip().lower().rstrip(".")
    if t in _HDR_MARK:
        return "mark"
    if t in _HDR_W:
        return "w"
    if t in _HDR_L:
        return "l"
    if t in _HDR_H:
        return "h"
    if t in _HDR_SIZE:
        return "size"
    return None


def _cluster_rows(cells):
    """Group (x, y, text) cells into table rows by y (single-linkage).

    The row pitch is learned from the data (median y-gap), so this works in mm or
    metres without a hard-coded tolerance. Returns [(row_y, [(x, text), ...]), ...]
    ordered top-to-bottom.
    """
    if not cells:
        return []
    ys = sorted(set(c[1] for c in cells))
    gaps = [b - a for a, b in zip(ys, ys[1:]) if b - a > 1e-9]
    pitch = _median(gaps) if gaps else 1.0
    tol = pitch * 0.45
    rows = []   # each: [anchor_y, [(x, text), ...], last_y]
    for x, y, text in sorted(cells, key=lambda c: -c[1]):
        if rows and (rows[-1][2] - y) <= tol:
            rows[-1][1].append((x, text))
            rows[-1][2] = y
        else:
            rows.append([y, [(x, text)], y])
    return [(r[0], r[1]) for r in rows]


def _parse_schedule_table(rows):
    """Header-driven {mark: (w, l)} from row-clustered schedule cells.

    Finds a header row, splits it into side-by-side Mark|W|L(|H) blocks by the
    header cells' x, then reads each data row column by column. Empty if no header.
    """
    header = None
    for _y, cells in rows:
        roles = [(x, _header_role(t)) for x, t in cells]
        roles = [(x, r) for x, r in roles if r]
        n_mark = sum(1 for _, r in roles if r == "mark")
        n_dim = sum(1 for _, r in roles if r in ("w", "l"))
        n_size = sum(1 for _, r in roles if r == "size")
        if n_mark >= 1 and (n_dim >= 2 or n_size >= 1):
            header = sorted(roles)
            break
    if not header:
        return {}

    blocks = []   # each: {"mark": x, "w": x, "l": x} or {"mark": x, "size": x}
    current = None
    for x, role in header:
        if role == "mark":
            current = {"mark": x}
            blocks.append(current)
        elif current is not None and role in ("w", "l", "size"):
            current.setdefault(role, x)
    blocks = [b for b in blocks if ("w" in b and "l" in b) or "size" in b]
    if not blocks:
        return {}

    xs = sorted(x for x, _ in header)
    pitch = min((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    tol = pitch * 0.5 if pitch > 0 else None

    out = {}
    for _y, cells in rows:
        if any(_header_role(t) for _, t in cells):
            continue   # skip header row(s)
        for block in blocks:
            name, _b, _h = parse_mark(_cell_at(cells, block["mark"], tol) or "")
            if not name:
                continue
            if "size" in block:
                wh = _two_numbers(_cell_at(cells, block["size"], tol))
            else:
                w = _number(_cell_at(cells, block["w"], tol))
                l = _number(_cell_at(cells, block["l"], tol))
                wh = (w, l) if (w is not None and l is not None) else None
            if wh:
                out.setdefault(name, wh)
    return out


def _cell_at(cells, target_x, tol):
    """Text of the cell whose x is nearest target_x (within tol, if given)."""
    best, best_d = None, None
    for x, text in cells:
        d = abs(x - target_x)
        if (tol is None or d <= tol) and (best_d is None or d < best_d):
            best, best_d = text, d
    return best


def _number(text):
    """A plain numeric cell as float, or None."""
    if not text:
        return None
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


def _two_numbers(text):
    """(a, b) from a 'AxB' size cell, or None."""
    if not text:
        return None
    match = _SIZE_RE.search(text)
    if not match:
        return None
    try:
        return (float(match.group(1)), float(match.group(2)))
    except (ValueError, TypeError):
        return None


def _median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


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

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
# mark token: one to three letters then digits, optional trailing letter (C1, RB12, C1A).
# The token may butt directly against a size with an underscore ("C16_300 X 600"): an
# underscore is a regex word char, so a trailing \b would NOT fire there and the mark was
# lost. A negative lookahead instead just forbids the token running on into another
# letter/digit, so "_", a space, or end-of-string all close it.
_MARK_RE = re.compile(r"\b([A-Za-z]{1,3}\d+[A-Za-z]?)(?![A-Za-z0-9])")
# "B20(c)" -- the mark carries a parenthesised SCHEDULE KEY instead of a size;
# the size lives in a MARK/SIZE table whose mark column reads "(a)", "(b)"...
_SIZE_KEY_RE = re.compile(r"\(\s*([A-Za-z0-9]{1,3})\s*\)")


def size_key(text):
    """The parenthesised SCHEDULE KEY in a label, normalised, or None.

    Some drawings write the size as a key into a beam-size table instead of
    spelling it out: "B20(c)" means beam B20 of size (c), and a MARK/SIZE
    schedule elsewhere on the sheet says (c) = 400x600. The key is returned in
    the same "(C)" form the schedule reader stores, so one lookup serves both.
    """
    if not text:
        return None
    flat = text.replace("\n", " ")
    found = _SIZE_KEY_RE.search(flat)
    if not found:
        return None
    key = found.group(1).strip().upper()
    # a bare number in brackets is a quantity/callout, not a size key
    if key.isdigit():
        return None
    return "({0})".format(key)


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
    """Stamp .mark/.b_mm/.h_mm/.size_key on every TextRecord; return the list."""
    for record in texts:
        name, b_mm, h_mm = parse_mark(record.text)
        record.mark = name
        record.b_mm = b_mm
        record.h_mm = h_mm
        record.size_key = size_key(record.text)
    return texts


def sized_texts(texts):
    """The subset of texts that carry a usable BxH size and an internal point."""
    return [t for t in texts
            if t.b_mm is not None and t.h_mm is not None and t.point_internal]


def parse_schedule(texts, allow_split=True):
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

    `allow_split` gates the split layout. It must be OFF when parsing PLAN labels
    (not a table): there, a markless size label and an unrelated mark merely sharing
    a Y are different columns metres apart, and pairing them mis-sizes a column from
    a neighbour's label (e.g. C5 inheriting a 350x750 label a whole bay away).
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
    if not allow_split:
        return schedule
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
# "comments": a schedule exported FROM Revit keeps the element name in the
# Comments column (StaircasePlan-Test2), so that column heads the table there
_HDR_MARK = ("mark", "ref", "col", "column", "type", "no", "id",
             "comments", "comment", "name")
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


def _is_header_row(cells):
    """Header roles [(x, role), ...] sorted by x if `cells` is a schedule header,
    else None. A header needs a Mark column and either two dimension columns
    (W and L) or a single combined Size column."""
    roles = [(x, _header_role(t)) for x, t in cells]
    roles = [(x, r) for x, r in roles if r]
    n_mark = sum(1 for _, r in roles if r == "mark")
    n_dim = sum(1 for _, r in roles if r in ("w", "l"))
    n_size = sum(1 for _, r in roles if r == "size")
    if n_mark >= 1 and (n_dim >= 2 or n_size >= 1):
        return sorted(roles)
    return None


def _parse_schedule_table(rows):
    """Header-driven {mark: (w, l)} from row-clustered cells -- ONE table per header.

    Several schedules (column / beam / slab) often share a layer and stack
    vertically. Each header row starts an INDEPENDENT table that owns the data rows
    beneath it (until the next header), and every table is read with its OWN block
    x-positions. That keeps a beam table's 'D' column from being read as a column
    table's length, and a column's 'H' from being read as its length, when the
    tables sit on one layer. The common single-header case (including side-by-side
    blocks) is unchanged.
    """
    out = {}
    header = None
    data_rows = None
    for _y, cells in rows:
        roles = _is_header_row(cells)
        if roles is not None:
            if header is not None:
                _read_table(header, data_rows, out)
            header, data_rows = roles, []
        elif header is not None:
            data_rows.append(cells)
    if header is not None:
        _read_table(header, data_rows, out)
    return out


def _read_table(header, data_rows, out):
    """Read one table's data rows into `out` using only that header's block x's.

    Splits the header into side-by-side Mark|W|L|H (or Mark|Size) blocks and reads each
    data row column by column. The section is W x (its second dimension): for a COLUMN
    that is W x L (footprint), the H column is the storey height and is ignored; for a
    BEAM (a "B"-mark) the section is W x H (depth) and the L column is the SPAN, ignored.
    A column schedule with the columns ordered "W H L" would otherwise read a beam's span
    as its depth.
    """
    blocks = []   # each: {"mark": x, "w": x, "l": x, "h": x} or {"mark": x, "size": x}
    current = None
    for x, role in header:
        if role == "mark":
            current = {"mark": x}
            blocks.append(current)
        elif current is not None and role in ("w", "l", "h", "size"):
            current.setdefault(role, x)
    blocks = [b for b in blocks
              if ("w" in b and ("l" in b or "h" in b)) or "size" in b
              or ("h" in b and "w" not in b and "l" not in b)]
    if not blocks:
        return

    xs = sorted(x for x, _ in header)
    pitch = min((b - a for a, b in zip(xs, xs[1:])), default=0.0)
    tol = pitch * 0.5 if pitch > 0 else None

    for cells in data_rows:
        for block in blocks:
            mark_cell = _cell_at(cells, block["mark"], tol) or ""
            name, _b, _h = parse_mark(mark_cell)
            if not name:
                # a KEYED table ("SCHEDULE OF BEAM SIZE": MARK (a) | SIZE
                # 200x600). The key is the mark here, and plan labels reach it
                # through the "(a)" written after their own mark: "B20(c)".
                name = size_key(mark_cell)
            if not name:
                continue
            if "size" in block:
                wh = _two_numbers(_cell_at(cells, block["size"], tol))
            elif "w" not in block and "l" not in block:
                # thickness-only table (slab schedule: Mark | H | Volume). Only an
                # S-mark may read it -- a column table reduced to Mark | H would be
                # the storey height, never a section size.
                h = _number(_cell_at(cells, block["h"], tol))
                wh = (h, h) if (_is_slab_mark(name) and h is not None) else None
            else:
                w = _number(_cell_at(cells, block["w"], tol))
                l = _number(_cell_at(cells, block["l"], tol)) if "l" in block else None
                h = _number(_cell_at(cells, block["h"], tol)) if "h" in block else None
                if _is_beam_mark(name) and h is not None:
                    second = h          # beam: depth is H; L is the span (ignore)
                else:
                    second = l if l is not None else h   # column: footprint W x L
                wh = (w, second) if (w is not None and second is not None) else None
            if wh:
                out.setdefault(name, wh)


def _is_beam_mark(name):
    """True for a beam mark like 'B1'/'B23' (a 'B' followed by a digit)."""
    return bool(name) and name[:1].upper() == "B" and name[1:2].isdigit()


def _is_slab_mark(name):
    """True for a slab mark like 'S1'/'S12' (an 'S' followed by a digit)."""
    return bool(name) and name[:1].upper() == "S" and name[1:2].isdigit()


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

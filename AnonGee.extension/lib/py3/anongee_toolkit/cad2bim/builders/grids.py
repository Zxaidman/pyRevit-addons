# -*- coding: utf-8 -*-
"""Create Revit grids from classified CAD grid curves.

Naming: the actual grid labels live as TEXT in the DWG, which the Revit geometry
API does NOT reliably expose (only curves/arcs come through get_Geometry). So
grids are named by a deterministic convention here — constant-X (vertical) lines
ordered left-to-right and lettered A, B, C...; constant-Y (horizontal) lines
ordered bottom-to-top and numbered 1, 2, 3... The namer is structured so a real
text-derived mapping can be injected later if a text-reading route is added.
"""

import math

from Autodesk.Revit.DB import Line, Arc, XYZ, Grid, FilteredElementCollector

from .. import naming
from .. import type_names

_MIN_LENGTH_FT = 1.0e-3   # ignore degenerate/zero-length curves


def _xyz(point):
    return XYZ(point[0], point[1], point[2])


def _curve_from_record(record):
    """Build a bound Revit curve from a grid record, or None if unsupported."""
    points = record.points
    if record.kind == "line" and len(points) >= 2:
        start, end = _xyz(points[0]), _xyz(points[-1])
        if start.DistanceTo(end) < _MIN_LENGTH_FT:
            return None
        return Line.CreateBound(start, end)
    if record.kind == "arc" and len(points) >= 3:
        # records store arcs as [start, mid, end]
        return Arc.Create(_xyz(points[0]), _xyz(points[-1]), _xyz(points[1]))
    return None


def existing_grid_names(doc):
    names = set()
    for grid in FilteredElementCollector(doc).OfClass(Grid).ToElements():
        try:
            names.add(grid.Name)
        except Exception:
            pass
    return names


class GridNamer:
    """Assigns convention names to grid records (letters one axis, numbers other)."""

    def __init__(self, grid_records, letters_for_constant_x=True):
        self._names = {}
        constant_x = []   # lines running in Y (vertical on plan)
        constant_y = []   # lines running in X (horizontal on plan)
        for record in grid_records:
            points = record.points
            if len(points) < 2:
                continue
            d_x = abs(points[-1][0] - points[0][0])
            d_y = abs(points[-1][1] - points[0][1])
            if d_x <= d_y:
                constant_x.append((points[0][0], record))
            else:
                constant_y.append((points[0][1], record))

        lettered = constant_x if letters_for_constant_x else constant_y
        numbered = constant_y if letters_for_constant_x else constant_x
        for index, (_, record) in enumerate(sorted(lettered, key=lambda pair: pair[0])):
            self._names[id(record)] = _to_letters(index)
        for index, (_, record) in enumerate(sorted(numbered, key=lambda pair: pair[0])):
            self._names[id(record)] = str(index + 1)

    def name_for(self, record):
        return self._names.get(id(record))


# A grid bubble/label sits at (or just beyond) one end of its grid line; match a
# label to the line whose nearest endpoint is within this distance.
_GRID_TEXT_MAX_FT = 2500.0 / 304.8


class TextGridNamer:
    """Names grids from grid-text labels (e.g. DWG grid bubbles 'A', '1').

    Each label is assigned to the grid line whose nearest endpoint is closest to
    it; that grid takes the label's text as its name. Any grid without a nearby
    label falls back to the convention namer, so naming degrades gracefully.
    """

    def __init__(self, grid_records, grid_texts, fallback):
        self._names = {}
        self._fallback = fallback
        ends = [(r, r.points[0], r.points[-1]) for r in grid_records
                if len(r.points) >= 2]
        max_d2 = _GRID_TEXT_MAX_FT * _GRID_TEXT_MAX_FT
        for text in grid_texts or []:
            point = text.point_internal
            label = (text.text or "").strip()
            if not point or not label:
                continue
            tx, ty = point[0], point[1]
            best = None
            best_d2 = max_d2
            for record, p0, p1 in ends:
                d2 = min((p0[0] - tx) ** 2 + (p0[1] - ty) ** 2,
                         (p1[0] - tx) ** 2 + (p1[1] - ty) ** 2)
                if d2 <= best_d2:
                    best = record
                    best_d2 = d2
            if best is not None:
                self._names[id(best)] = label

    def name_for(self, record):
        return self._names.get(id(record)) or self._fallback.name_for(record)


def build_grid_namer(grid_records, grid_texts=None):
    """Convention namer, upgraded to text-derived names when grid labels exist."""
    convention = GridNamer(grid_records)
    if grid_texts:
        return TextGridNamer(grid_records, grid_texts, convention)
    return convention


def _to_letters(index):
    """0->A, 1->B, ... 25->Z, 26->AA, ..."""
    text = ""
    n = index
    while True:
        text = chr(ord("A") + (n % 26)) + text
        n = n // 26 - 1
        if n < 0:
            return text


_DUPLICATE_TOL_FT = 50.0 / 304.8   # a grid this close to an existing one is the same


def _grid_fingerprints(doc):
    """{(rounded direction, rounded offset)} of the grids already in the model.

    A grid is a DATUM: it spans every level, so a multi-storey run whose floors
    share one grid must not create the same line once per storey. Matching on
    direction + perpendicular offset (not endpoints) also catches a grid drawn
    to a different length on another floor.
    """
    seen = set()
    for grid in FilteredElementCollector(doc).OfClass(Grid).ToElements():
        try:
            fingerprint = _line_fingerprint(grid.Curve)
        except Exception:
            continue
        if fingerprint is not None:
            seen.add(fingerprint)
    return seen


def _line_fingerprint(curve):
    """(direction, perpendicular offset) rounded to the duplicate tolerance."""
    try:
        start, end = curve.GetEndPoint(0), curve.GetEndPoint(1)
    except Exception:
        return None
    dx, dy = end.X - start.X, end.Y - start.Y
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        return None
    ux, uy = dx / length, dy / length
    if (ux, uy) < (-ux, -uy):          # direction is unsigned: A->B == B->A
        ux, uy = -ux, -uy
    offset = -uy * start.X + ux * start.Y      # signed distance from the origin
    step = _DUPLICATE_TOL_FT
    return (round(ux / 0.01), round(uy / 0.01), round(offset / step))


def create_grids(doc, grid_records, namer):
    """Create grids inside an already-open transaction. Returns a result dict.

    Caller owns the Transaction/TransactionGroup; this function only creates and
    names, accumulating per-record outcomes so nothing fails the whole batch.
    A line that coincides with a grid ALREADY in the model is skipped -- grids
    are datums shared by every storey, so a multi-storey run creates each one
    once instead of stacking a copy per floor.
    """
    result = {"created": [], "skipped": [], "errors": []}
    # keyed the way Revit compares grid names: a model holding "a" refuses "A"
    used_names = set(type_names.key(name) for name in existing_grid_names(doc))
    placed = _grid_fingerprints(doc)
    for record in grid_records:
        try:
            curve = _curve_from_record(record)
            if curve is None:
                result["skipped"].append("unsupported or zero-length grid curve")
                continue
            fingerprint = _line_fingerprint(curve)
            if fingerprint is not None and fingerprint in placed:
                result["skipped"].append("grid already in the model")
                continue
            grid = Grid.Create(doc, curve)
            if fingerprint is not None:
                placed.add(fingerprint)
            name = naming.grid_name(namer.name_for(record))
            if name and type_names.key(name) not in used_names:
                try:
                    grid.Name = name
                    used_names.add(type_names.key(name))
                except Exception:
                    pass  # name clash/invalid: keep Revit's auto name
            result["created"].append(grid.Id)
        except Exception as creation_error:
            result["errors"].append(str(creation_error))
    return result

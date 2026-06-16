# -*- coding: utf-8 -*-
"""Create Revit grids from classified CAD grid curves.

Naming: the actual grid labels live as TEXT in the DWG, which the Revit geometry
API does NOT reliably expose (only curves/arcs come through get_Geometry). So
grids are named by a deterministic convention here — constant-X (vertical) lines
ordered left-to-right and lettered A, B, C...; constant-Y (horizontal) lines
ordered bottom-to-top and numbered 1, 2, 3... The namer is structured so a real
text-derived mapping can be injected later if a text-reading route is added.
"""

from Autodesk.Revit.DB import Line, Arc, XYZ, Grid, FilteredElementCollector

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


def _to_letters(index):
    """0->A, 1->B, ... 25->Z, 26->AA, ..."""
    text = ""
    n = index
    while True:
        text = chr(ord("A") + (n % 26)) + text
        n = n // 26 - 1
        if n < 0:
            return text


def create_grids(doc, grid_records, namer):
    """Create grids inside an already-open transaction. Returns a result dict.

    Caller owns the Transaction/TransactionGroup; this function only creates and
    names, accumulating per-record outcomes so nothing fails the whole batch.
    """
    result = {"created": [], "skipped": [], "errors": []}
    used_names = existing_grid_names(doc)
    for record in grid_records:
        try:
            curve = _curve_from_record(record)
            if curve is None:
                result["skipped"].append("unsupported or zero-length grid curve")
                continue
            grid = Grid.Create(doc, curve)
            name = namer.name_for(record)
            if name and name not in used_names:
                try:
                    grid.Name = name
                    used_names.add(name)
                except Exception:
                    pass  # name clash/invalid: keep Revit's auto name
            result["created"].append(grid.Id)
        except Exception as creation_error:
            result["errors"].append(str(creation_error))
    return result

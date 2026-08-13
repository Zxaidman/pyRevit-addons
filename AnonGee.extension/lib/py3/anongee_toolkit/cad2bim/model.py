# -*- coding: utf-8 -*-
"""Plain data holders. IronPython 2.7 safe -- no dataclasses, no type hints.

A CurveRecord is geometry-only and unit-correct: points are (x, y, z) tuples in
Revit internal feet (NOT rescaled). Category is assigned later by the layer
classifier, so it lives on the record as a mutable field that defaults to None.
"""

NO_LAYER = "<no layer>"   # display key for geometry whose GraphicsStyle is missing


class CurveRecord(object):
    """One extracted curve from a linked CAD."""

    def __init__(self, kind, points, layer, length_ft):
        self.kind = kind            # 'line' | 'arc' | 'polyline' | <other lowercased>
        self.points = points        # list of (x, y, z) tuples, internal feet
        self.layer = layer          # CAD layer name, or None if unresolved
        self.length_ft = length_ft  # float or None
        self.category = None        # filled in after classification

    @property
    def layer_key(self):
        """Stable dictionary key, collapsing a missing layer to NO_LAYER."""
        return self.layer if self.layer else NO_LAYER

    def to_dict(self):
        return {
            "kind": self.kind,
            "layer": self.layer,
            "category": self.category,
            "length_ft": self.length_ft,
            "points": [list(p) for p in self.points],
        }

    def __repr__(self):
        return "<CurveRecord {0} layer={1!r} pts={2}>".format(
            self.kind, self.layer, len(self.points))


class RegionRecord(object):
    """One filled REGION read from a drawing -- a DXF HATCH.

    A region is not a curve. It says "this AREA means something": a fold in a
    foundation, a sunk bay, a cutout, a column's concrete fill. It is kept apart
    from CurveRecord for that reason and, practically, so a few hundred closed
    rings never reach the passes that try to make columns and beams out of
    closed rings.

    `points` is the EXTERNAL boundary only. AutoCAD clips a hatch around any
    label drawn over it, so a hatch commonly arrives with textbox islands cut
    out of it; those are holes in the hatching, not holes in the thing.
    """

    def __init__(self, points, layer, pattern=None, solid=False):
        self.points = points        # outer ring, [(x, y, z), ...]
        self.layer = layer          # CAD layer name, or None if unresolved
        self.pattern = pattern      # "ANSI37", "SOLID", ... or None
        self.solid = bool(solid)    # a solid fill carries no pattern to read
        self.category = None        # filled in after classification

    @property
    def layer_key(self):
        """Stable dictionary key, collapsing a missing layer to NO_LAYER."""
        return self.layer if self.layer else NO_LAYER

    def to_dict(self):
        return {
            "layer": self.layer,
            "category": self.category,
            "pattern": self.pattern,
            "solid": self.solid,
            "points": [list(p) for p in self.points],
        }

    def __repr__(self):
        return "<RegionRecord layer={0!r} pattern={1!r} pts={2}>".format(
            self.layer, self.pattern, len(self.points))


class TextRecord(object):
    """One text entity read from the DXF (TEXT / MTEXT / block ATTRIB).

    The Revit API cannot read text inside a CAD link, so these come from parsing
    the DXF file directly. `point` is in the DXF's own coordinate space; once the
    DXF->internal transform is known it is filled into `point_internal` (Revit feet)
    so the label can be matched to the nearest member. `mark`, `b_mm` and `h_mm`
    are populated later by marks.parse_mark (e.g. "C1 400x400").
    """

    def __init__(self, text, layer, point, rotation_deg=0.0):
        self.text = text                # raw string, formatting already stripped
        self.layer = layer              # CAD layer name, or None
        self.point = point              # (x, y, z) in DXF coords
        self.rotation_deg = rotation_deg  # text angle; beam labels run ALONG their beam
        self.point_internal = None      # (x, y, z) in Revit internal feet
        self.size_key = None            # "(C)" from a "B20(c)" keyed label
        self.mark = None                # parsed mark name, e.g. "C1"
        self.b_mm = None                # parsed width, mm
        self.h_mm = None                # parsed height/depth, mm

    @property
    def layer_key(self):
        return self.layer if self.layer else NO_LAYER

    def to_dict(self):
        return {
            "text": self.text,
            "layer": self.layer,
            "point": list(self.point) if self.point else None,
            "point_internal": (list(self.point_internal)
                               if self.point_internal else None),
            "mark": self.mark,
            "b_mm": self.b_mm,
            "h_mm": self.h_mm,
            "rotation_deg": self.rotation_deg,
        }

    def __repr__(self):
        return "<TextRecord {0!r} layer={1!r}>".format(self.text, self.layer)


class DxfReadResult(object):
    """Geometry + text extracted from a DXF file by the ezdxf reader.

    `records` are CurveRecords (same shape as the Revit reader's output) so the
    whole downstream pipeline is reused verbatim. Coordinates are in DXF space
    until transform.apply maps them to internal feet.
    """

    def __init__(self, source_name, records, texts, regions=None):
        self.source_name = source_name
        self.records = records      # list[CurveRecord], DXF coords
        self.texts = texts          # list[TextRecord], DXF coords
        # Hatches, kept OUT of `records` so the curve pipeline is untouched by
        # their arrival. Optional so every existing three-argument caller works.
        self.regions = regions if regions is not None else []

    def is_empty(self):
        return not self.records and not self.texts and not self.regions


class ReadResult(object):
    """The full outcome of reading one linked CAD."""

    def __init__(self, source_name, records):
        self.source_name = source_name  # human-readable link name
        self.records = records          # list[CurveRecord]

    @property
    def layer_names(self):
        """Distinct layer keys present, sorted for stable display."""
        seen = set(r.layer_key for r in self.records)
        return sorted(seen)

    def is_empty(self):
        return not self.records

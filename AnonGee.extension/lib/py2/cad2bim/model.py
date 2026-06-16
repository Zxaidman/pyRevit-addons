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

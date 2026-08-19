# -*- coding: utf-8 -*-
"""Millimetres local to a host, into Revit curves in world feet.

The whole of the unit and placement conversion lives here, in one place, done
once. :mod:`anongee_toolkit.rc_automation.rebar_spec` works out *what* a bar is
in plain millimetres relative to its host; this turns that into the ``XYZ`` and
``Curve`` objects the API wants, offset to where the host actually stands and
turned to whatever angle it was placed at.

Keeping the two apart is what lets every bar-layout decision be argued with on a
machine with no Revit on it. Nothing here decides anything -- it converts.
"""

import math

from Autodesk.Revit.DB import Curve
from Autodesk.Revit.DB import Line
from Autodesk.Revit.DB import XYZ
from System.Collections.Generic import List

from anongee_toolkit.revit.units import mm_to_ft

__version__ = "0.1.0"

#: Two points closer than this are the same point. Revit refuses a line shorter
#: than about 1/32", and a zero-length segment fails the whole sketch, so a
#: duplicated outline point has to be dropped before it reaches the API.
MIN_SEGMENT_FT = 0.0026          # ~0.8 mm


def to_xyz(point_mm, origin_ft=None, rotation_deg=0.0):
    """One local millimetre point as a world ``XYZ`` in feet.

    Rotation is applied about the host's own origin before the offset, which is
    the order that makes a rotated footing's bars turn with the pad rather than
    swing away from it.
    """
    x_mm, y_mm = point_mm[0], point_mm[1]
    z_mm = point_mm[2] if len(point_mm) > 2 else 0.0

    if rotation_deg:
        angle = math.radians(rotation_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        x_mm, y_mm = (x_mm * cos_a - y_mm * sin_a,
                      x_mm * sin_a + y_mm * cos_a)

    point = XYZ(mm_to_ft(x_mm), mm_to_ft(y_mm), mm_to_ft(z_mm))
    return point if origin_ft is None else point.Add(origin_ft)


def origin_xyz(x_mm=0.0, y_mm=0.0, z_mm=0.0):
    """A host origin in feet from millimetre coordinates."""
    return XYZ(mm_to_ft(x_mm), mm_to_ft(y_mm), mm_to_ft(z_mm))


def rotate_vector(vector, rotation_deg=0.0):
    """Turn a unit direction in plan, so a set arrays along the rotated host."""
    x, y, z = vector[0], vector[1], (vector[2] if len(vector) > 2 else 0.0)
    if rotation_deg:
        angle = math.radians(rotation_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        x, y = x * cos_a - y * sin_a, x * sin_a + y * cos_a
    return XYZ(x, y, z)


def line_curves(bar, origin_ft=None, rotation_deg=0.0):
    """``(List[Curve], skipped)`` — a bar spec's centreline, ready for the API.

    The list is a typed ``List[Curve]`` built with ``Add``: a raw Python list is
    a fatal marshalling fault across the pythonnet bridge, not a TypeError
    (§12.9.4).

    Segments shorter than :data:`MIN_SEGMENT_FT` are dropped rather than passed
    on: Revit rejects an entire sketch for one zero-length line, so a repeated
    outline point would otherwise cost the whole bar instead of the duplicate.
    ``skipped`` counts them, so a caller can say what it dropped rather than
    leaving the user to find a bar with a missing leg.
    """
    points = [to_xyz(point, origin_ft, rotation_deg) for point in bar.points]
    curves = List[Curve]()
    skipped = 0
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        if start.DistanceTo(end) < MIN_SEGMENT_FT:
            skipped += 1
            continue
        curves.Add(Line.CreateBound(start, end))
    return curves, skipped


def normal_for(bar_or_set, rotation_deg=0.0, fallback=None):
    """The plane normal Revit wants, which is also the way a set arrays.

    For shape-driven reinforcement the bars of a set are distributed along this
    vector, so it is not a free choice: a footing layer running along X and
    spaced along Y has to hand over Y, or the set marches off vertically. The
    array vector worked out in ``rebar_spec`` is exactly that, which is why it
    is carried on the plan rather than recomputed here.
    """
    vector = getattr(bar_or_set, "array_vector", None)
    if vector is None:
        vector = fallback if fallback is not None else (0.0, 0.0, 1.0)
    return rotate_vector(vector, rotation_deg)


def length_ft(curves):
    """Total length of a curve list, for reporting what was actually built."""
    total = 0.0
    for curve in curves:
        try:
            total += curve.Length
        except Exception:
            continue
    return total

# -*- coding: utf-8 -*-
"""Finding the stairs a drawing TALKS about, before any geometry is read.

A structural plan says "STAIRCASE", "ST-2" or "DN" somewhere in the bay, and
that text is often the only unambiguous statement that a stair belongs there --
the linework alone can read as a shaft, a lift or a hatch. These readers turn
those notes into: which texts name a stair, what each one calls it, which way it
climbs, and roughly what area it occupies.

Revit-free and content-driven: the layer a note sits on is a hint the dialog can
route, never a requirement.
"""

import math
import re

from . import config
from . import slab_outlines

_MM = config.MM_PER_FT


# "STAIRCASE" / "STAIR" / "STAIRS" / "ST-1" / "ST1" / "ST 2" -- the note that sits
# inside the stair bay on the plan (any text layer; content decides, like slabs).
_STAIR_TEXT = re.compile(r"^\s*(?:STAIRS?CASE|STAIRS?|ST[-_ ]?(\d+))\s*$", re.IGNORECASE)
# "DN" / "DN." / "UP" -- the run direction note; DN sits at the TOP of the flight.


# "DN" / "DN." / "UP" -- the run direction note; DN sits at the TOP of the flight.
_DIR_TEXT = re.compile(r"^\s*(DN|UP)\.?\s*$", re.IGNORECASE)


_MIN_STAIR_AREA_M2 = 4.0     # a bay smaller than this cannot hold a real stair


_MAX_STAIR_AREA_M2 = 60.0    # bigger than this is a floor plate, not a stair bay


def stair_label(text):
    """The stair mark for a stair note ("ST-1" -> "ST-1", "STAIRCASE" -> "ST"),
    or None when the text is not a stair note."""
    match = _STAIR_TEXT.match(text or "")
    if not match:
        return None
    number = match.group(1)
    return "ST-{0}".format(number) if number else "ST"


def direction_label(text):
    """"DN" / "UP" for a run-direction note, or None."""
    match = _DIR_TEXT.match(text or "")
    return match.group(1).upper() if match else None


def find_stair_texts(texts):
    """[(x_ft, y_ft, mark)] for every stair note with an internal point."""
    out = []
    for t in texts:
        mark = stair_label(getattr(t, "text", None))
        p = getattr(t, "point_internal", None)
        if mark and p is not None:
            out.append((p[0], p[1], mark))
    return out


def find_direction_texts(texts):
    """[(x_ft, y_ft, "DN"|"UP")] for every run-direction note."""
    out = []
    for t in texts:
        label = direction_label(getattr(t, "text", None))
        p = getattr(t, "point_internal", None)
        if label and p is not None:
            out.append((p[0], p[1], label))
    return out


def stair_areas_from_texts(records, beam_segments, column_rects, texts):
    """[(ring, z, mark)] -- the bounded face under each stair note.

    The faces come from the placed-members machinery with `keep_points` so the
    wall-bounded stair bay is not discarded as a shaft. A note whose face cannot
    be found (or is implausibly small/large) is reported in `notes` instead of
    silently dropped: returns (areas, notes).
    """
    stair_pts = find_stair_texts(texts)
    if not stair_pts:
        return [], ["no STAIRCASE/ST-n text on the plan"]
    loops = slab_outlines.slab_loops_from_placed_members(
        records, beam_segments, column_rects=column_rects,
        keep_points=[(x, y) for x, y, _m in stair_pts])
    areas = []
    notes = []
    min_ft2 = _MIN_STAIR_AREA_M2 * (1000.0 / _MM) ** 2
    max_ft2 = _MAX_STAIR_AREA_M2 * (1000.0 / _MM) ** 2
    for x, y, mark in stair_pts:
        hit = None
        for ring, z, _arcs in loops:
            if slab_outlines._point_in_ring((x, y), ring):
                hit = (ring, z)
                break
        if hit is None:
            notes.append("{0}: no closed bay found around the text".format(mark))
            continue
        area = abs(slab_outlines._signed_area(hit[0]))
        if area < min_ft2 or area > max_ft2:
            notes.append("{0}: bay area {1:.1f} m2 outside {2}-{3} m2".format(
                mark, area * (_MM / 1000.0) ** 2,
                int(_MIN_STAIR_AREA_M2), int(_MAX_STAIR_AREA_M2)))
            continue
        areas.append((hit[0], hit[1], mark))
    return areas, notes

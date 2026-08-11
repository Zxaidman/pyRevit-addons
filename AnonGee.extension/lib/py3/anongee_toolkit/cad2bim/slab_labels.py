# -*- coding: utf-8 -*-
"""What a slab is CALLED and how thick it is -- read off the plan's own notes.

An outline is geometry; a slab is geometry plus a thickness. Both come from the
same place columns and beams get their sizes: a note sitting inside the loop.
"S1 150 THK", "150 THK.", or a bare mark "S3" whose thickness the schedule
carries. A loop with no note keeps thickness None and the builder falls back to
the floor type the user picked.

`loops_for_unclaimed_notes` is the other direction, and it earns its keep on
test10's roof: a note with no outline under it means a bay whose slab edge was
never drawn, so the placed members are asked for that one face -- and only that
one, which is what keeps this from inventing slabs across a whole drawing.
"""

import re

from . import config
from . import slab_outlines
from .slab_graph import _centroid, _point_in_ring, _signed_area

_MM = config.MM_PER_FT


# "S1 150 THK" / "S7_150 THK." / "S12 125" / "150 THK" / "S3" (mark-only; thickness
# via schedule). The mark joins its thickness by SPACE or UNDERSCORE -- the same
# convention the beam labels use ("B1_300 X 600").
_SLAB_LABEL = re.compile(
    r"^\s*(?:(S\d+))?[\s_]*(?:(\d{2,4})\s*(?:MM\s*)?(?:THK|THICK)?\.?)?\s*$",
    re.IGNORECASE)


# ------------------------------------------------------------------- label / sizing
def parse_slab_label(text):
    """(mark, thickness_mm) from a slab label; either may be None."""
    m = _SLAB_LABEL.match(text or "")
    if not m or (m.group(1) is None and m.group(2) is None):
        return None, None
    mark = m.group(1).upper() if m.group(1) else None
    thk = float(m.group(2)) if m.group(2) else None
    return mark, thk


_ORPHAN_MIN_AREA_M2 = 1.0     # smaller than any slab a plan bothers to note


def loops_for_unclaimed_notes(loops, records, beam_segments, texts,
                              column_rects=None, min_area_m2=_ORPHAN_MIN_AREA_M2):
    """Outlines for slab notes that the drawn slab edges left uncovered.

    A plan can note "200 THK." over a bay whose slab edge was never drawn --
    test10's roof draws the A-FLOR rings on its south bays and only a single
    edge line on the north ones, yet both sides carry the note. The edge rings
    are found, the fallback never runs (it only runs when NOTHING was found),
    and three slabs go missing with no complaint.

    So the two sources become additive, but only exactly where the drawing asks:
    a face of the placed beams/columns is taken ONLY when it contains a slab
    note that no drawn ring covers, and only when it does not overlap a ring
    that was found. Every other face of the member graph is ignored, so a plan
    whose notes are all covered builds precisely what it built before.

    Returns the extra loops, in the same [(ring, z, arcs)] shape.
    """
    notes = []
    for text in (texts or []):
        mark, thickness = parse_slab_label(getattr(text, "text", "") or "")
        if mark is None and thickness is None:
            continue
        point = getattr(text, "point_internal", None)
        if point is None:
            continue
        if any(_point_in_ring((point[0], point[1]), loop[0]) for loop in loops):
            continue
        notes.append((point[0], point[1]))
    if not notes:
        return []
    # the notes double as keep_points: a bay whose fourth side is a WALL rather
    # than a beam (test10's roof) is otherwise dropped as a shaft, and the note
    # standing in it is the drawing saying there is a slab here
    extra = slab_outlines.slab_loops_from_placed_members(records, beam_segments,
                                           column_rects=column_rects,
                                           keep_points=notes)
    min_area_ft2 = min_area_m2 * 1e6 / (config.MM_PER_FT ** 2)
    kept = []
    for loop in extra:
        ring = loop[0]
        if not any(_point_in_ring(note, ring) for note in notes):
            continue
        if abs(_signed_area(ring)) < min_area_ft2:
            continue
        if _overlaps_any(ring, loops) or _overlaps_any(ring, kept):
            continue
        kept.append(loop)
    return kept


def _overlaps_any(ring, loops):
    """True when `ring` and any loop cover the same ground.

    Centroid containment both ways: cheap, and enough to tell a bay that was
    already found from one that was not.
    """
    centre = _centroid(ring)
    for loop in loops or []:
        other = loop[0]
        if _point_in_ring(centre, other):
            return True
        if _point_in_ring(_centroid(other), ring):
            return True
    return False


def apply_slab_labels(loops, texts, schedule=None):
    """[{ring, z, mark, thickness_mm}] -- name/size each loop like columns/beams.

    A label INSIDE the loop wins (nearest to the loop centroid when several);
    a mark-only label resolves thickness via schedule[mark]. Unlabelled loops
    keep thickness None (builder falls back to the picked floor type).
    """
    schedule = schedule or {}
    out = []
    for loop in loops:
        ring, z = loop[0], loop[1]
        arcs = loop[2] if len(loop) > 2 else []
        cx, cy = _centroid(ring)
        best = None                     # (dist, mark, thk)
        for t in (texts or []):
            mark, thk = parse_slab_label(getattr(t, "text", "") or "")
            if mark is None and thk is None:
                continue
            p = t.point_internal
            if p is None or not _point_in_ring((p[0], p[1]), ring):
                continue
            d = (p[0] - cx) ** 2 + (p[1] - cy) ** 2
            if best is None or d < best[0]:
                best = (d, mark, thk)
        mark = best[1] if best else None
        thk = best[2] if best else None
        if thk is None and mark is not None and mark in schedule:
            entry = schedule[mark]
            thk = entry[0] if isinstance(entry, (tuple, list)) else entry
        out.append({"ring": ring, "z": z, "mark": mark, "thickness_mm": thk,
                    "arcs": arcs})
    return out

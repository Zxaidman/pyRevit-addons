# -*- coding: utf-8 -*-
"""Beam passes that need the COLUMNS to have been decided first.

`beam_segments` derives centrelines from the drawing alone. These three then
reconcile them with the placed columns, which is only possible once column
detection and every recovery pass have finished:

    split_beams_at_columns     a beam drawn straight ACROSS a column would be
                               buried inside it; cut it into the pieces either
                               side, dropping any stub too short to be a member
    snap_beam_ends_to_columns  a beam meeting a ROUND or ROTATED column leaves a
                               visible gap at the junction; run its end to the
                               column centre (axis-aligned columns butt cleanly
                               and are left alone)
    dedupe_beam_segments       a messy outline that retraces its own edges
                               decomposes to the same centreline twice, which is
                               two beams z-fighting in Revit

All three edit the beam_segments dict in place and return how many segments they
changed, so the console can report each pass separately. Revit-free.
"""

import math

from . import config
from .column_geom import _column_footprints, column_outline_footprints

_MM = config.MM_PER_FT

_BEAM_END_SNAP_PAD_MM = 250.0   # a beam end this far outside a round/rotated column snaps in


def snap_beam_ends_to_columns(beam_segments, sections, circles=None,
                              pad_ft=None):
    """Run a beam END up to a ROUND or ROTATED column's centre to close the junction gap.

    A beam meeting an axis-aligned column butts cleanly against a flat edge, but a round
    column (tangent contact) or a rotated column (skew edge) leaves an ugly gap. When a
    beam endpoint lands inside such a column (within its radius + a small pad), the end is
    slid ALONG THE BEAM'S OWN AXIS to the point abeam of the column centre -- never onto
    the centre itself: a column deliberately drawn OFF the beam's axis (Test11's grid-I
    columns) would otherwise drag the end sideways and skew the whole beam off its CAD
    outline. Only ENDPOINTS move, never a beam's midspan; axis-aligned columns are left
    alone. Returns the number of ends snapped.
    """
    if pad_ft is None:
        pad_ft = config.mm_to_ft(_BEAM_END_SNAP_PAD_MM)
    targets = []   # (cx, cy, reach_ft)
    for circle in (circles or []):
        cx, cy, _cz = circle["center"]
        targets.append((cx, cy, circle["diameter_ft"] / 2.0 + pad_ft))
    for entry in sections.get("entries", []):
        for rect in entry["rectangles"]:
            deg = rect.get("long_axis_deg")
            if deg is None:
                continue
            skew = deg % 90.0
            if min(skew, 90.0 - skew) <= 1.0:
                continue                       # axis-aligned: clean butt joint, no gap
            cx, cy, _cz = rect["center"]
            w = rect["width_mm"] / _MM
            h = rect["height_mm"] / _MM
            targets.append((cx, cy, 0.5 * (w * w + h * h) ** 0.5 + pad_ft))
    if not targets:
        return 0
    snapped = 0
    for seg in beam_segments.get("segments", []):
        for end, other in (("start", "end"), ("end", "start")):
            ex, ey = seg[end][0], seg[end][1]
            ox, oy = seg[other][0], seg[other][1]
            vx, vy = ex - ox, ey - oy
            length = (vx * vx + vy * vy) ** 0.5
            if length == 0:
                continue
            ux, uy = vx / length, vy / length   # axis direction, towards this end
            # NEAREST target, not first-in-list: a short stub clipped between TWO
            # rotated columns has both ends inside both columns' reach, and first-match
            # sent both ends to the same column, collapsing the beam (Test15's B648).
            # Nearest sends each end to its own column, stretching the stub across
            # the full bay.
            best = None
            for cx, cy, reach in targets:
                d2 = (ex - cx) ** 2 + (ey - cy) ** 2
                if d2 <= reach * reach and (best is None or d2 < best[0]):
                    best = (d2, cx, cy)
            if best is not None:
                _d2, cx, cy = best
                # project the column centre onto the beam's carrier line and move the
                # end THERE: extended to the centre's station, still on the beam's axis
                t = (cx - ox) * ux + (cy - oy) * uy
                seg[end][0], seg[end][1] = ox + ux * t, oy + uy * t
                snapped += 1
    return snapped


# A beam OUTLINE drawn straight across a column places a beam ON TOP of it in Revit.
_SPLIT_MIN_PIECE_MM = 100.0        # a leftover piece shorter than this is drafting overshoot


_SPLIT_MIN_PENETRATION_MM = 10.0   # centreline must reach this far inside; grazing a face is not a crossing


_SPLIT_JUNCTION_MARGIN_MM = 100.0  # an end at most this far past the column CENTRE is a junction


def dedupe_beam_segments(beam_segments, tol_mm=10.0):
    """Drop straight segments that RETRACE another segment of the same width.

    A messy beam-layer polyline that runs back over its own edges (test8's outlines
    trace across the column rectangles and back) decomposes into the same centreline
    twice -- or into a short fragment lying ON a longer one -- and every copy becomes
    a beam z-fighting in Revit. Two passes:
      1. EXACT twins: endpoints equal within `tol_mm` (either direction), same width.
      2. CONTAINED fragments: both endpoints of the shorter segment lie on the longer
         one's carrier line (within a small perpendicular band) and inside its span.
    The marked copy survives (a dropped fragment's mark transfers to its keeper when
    the keeper has none). Returns the number of segments removed.
    """
    grid = config.mm_to_ft(tol_mm)
    segments = beam_segments.get("segments", [])
    kept = {}
    order = []
    for seg in segments:
        a = (round(seg["start"][0] / grid), round(seg["start"][1] / grid))
        b = (round(seg["end"][0] / grid), round(seg["end"][1] / grid))
        key = (min(a, b), max(a, b), int(round(seg["width_mm"] / tol_mm)))
        other = kept.get(key)
        if other is None:
            kept[key] = seg
            order.append(key)
        elif not other.get("mark") and seg.get("mark"):
            kept[key] = seg               # keep the marked twin
    survivors = [kept[k] for k in order]

    band_ft = config.mm_to_ft(15.0)       # perpendicular slack off the carrier
    span_ft = config.mm_to_ft(tol_mm)
    by_len = sorted(survivors, key=lambda s: -s["length_mm"])
    removed = set()
    for i, big in enumerate(by_len):
        if id(big) in removed:
            continue
        ox, oy = big["start"][0], big["start"][1]
        vx, vy = big["end"][0] - ox, big["end"][1] - oy
        length = (vx * vx + vy * vy) ** 0.5
        if length <= 0:
            continue
        ux, uy = vx / length, vy / length
        for small in by_len[i + 1:]:
            if id(small) in removed:
                continue
            if abs(small["width_mm"] - big["width_mm"]) > tol_mm:
                continue
            ok = True
            for end in ("start", "end"):
                px, py = small[end][0] - ox, small[end][1] - oy
                t = px * ux + py * uy
                perp = abs(px * uy - py * ux)
                if perp > band_ft or t < -span_ft or t > length + span_ft:
                    ok = False
                    break
            if ok:
                removed.add(id(small))
                if small.get("mark") and not big.get("mark"):
                    big["mark"] = small["mark"]
    if removed:
        survivors = [s for s in survivors if id(s) not in removed]
    dropped = len(segments) - len(survivors)
    if dropped:
        beam_segments["segments"] = survivors
    return dropped


def _clip_slab(t0, t1, f0, df, half):
    """Shrink [t0, t1] to where |f0 + t*df| <= half; None when nothing remains."""
    if abs(df) < 1e-12:
        return (t0, t1) if abs(f0) <= half else None
    ta, tb = (-half - f0) / df, (half - f0) / df
    if ta > tb:
        ta, tb = tb, ta
    t0, t1 = max(t0, ta), min(t1, tb)
    return (t0, t1) if t0 < t1 else None


def _footprint_interval(fp, ox, oy, ux, uy, length, pen_ft):
    """(t0, t1, tc): where the centreline runs INSIDE the footprint, plus the
    column centre's station tc along the segment (the point abeam of the centre).

    None unless the interval's midpoint sits at least pen_ft inside every face,
    so a centreline grazing along a column face never counts as a crossing.
    """
    if fp[0] == "circle":
        _kind, cx, cy, r = fp
        fx, fy = ox - cx, oy - cy
        b = fx * ux + fy * uy
        disc = b * b - (fx * fx + fy * fy - r * r)
        if disc <= 0.0:
            return None
        root = disc ** 0.5
        t0, t1 = max(0.0, -b - root), min(length, -b + root)
        if t0 >= t1:
            return None
        tm = (t0 + t1) / 2.0
        dx, dy = ox + ux * tm - cx, oy + uy * tm - cy
        if (dx * dx + dy * dy) ** 0.5 > r - pen_ft:
            return None
        return t0, t1, -b
    _kind, cx, cy, ca, sa, half_long, half_short = fp
    fx, fy = ox - cx, oy - cy
    u0, du = fx * ca + fy * sa, ux * ca + uy * sa       # along the long axis
    v0, dv = fy * ca - fx * sa, uy * ca - ux * sa       # across it
    span = _clip_slab(0.0, length, u0, du, half_long)
    if span:
        span = _clip_slab(span[0], span[1], v0, dv, half_short)
    if not span:
        return None
    t0, t1 = span
    tm = (t0 + t1) / 2.0
    if (abs(u0 + du * tm) > half_long - pen_ft or
            abs(v0 + dv * tm) > half_short - pen_ft):
        return None
    return t0, t1, -(fx * ux + fy * uy)


def split_beams_at_columns(beam_segments, sections, circles=None,
                           extra_footprints=None):
    """Split a beam DRAWN ACROSS a column so no beam is modelled on top of it.

    Structural CAD routinely draws a continuous beam outline straight over the
    columns it crosses; placing that centreline verbatim buries a beam inside every
    column on its run (test8, client request). Wherever a segment's centreline
    passes through a column footprint with BOTH crossing points strictly inside the
    span, the segment is split into the pieces outside the column, trimmed at its
    faces -- the beam still "goes through" the column line as two members framing
    into opposite faces, but nothing is drawn on top of the column.

    A segment END is allowed to sit AT a column centre -- that is the junction
    convention (and exactly where the snap pass puts ends at round/rotated
    columns) -- so which overlaps count is decided per column:
      * crossing strictly inside the span -> SPLIT at the faces;
      * segment entirely inside one footprint (a "beam" coextensive with the
        column, i.e. the column's own outline mis-read as a beam) -> DROPPED;
      * a terminal end more than _SPLIT_JUNCTION_MARGIN_MM PAST the column
        centre (the beam was drawn across the column, e.g. to its far face)
        -> that end is TRIMMED back to the near face; an end at or before the
        centre (+margin) is a junction and never moves;
      * grazing contact (midpoint within _SPLIT_MIN_PENETRATION_MM of a face,
        e.g. a beam sharing a column's face line) never counts;
      * a piece shorter than _SPLIT_MIN_PIECE_MM is dropped -- that both
        discards drafting overshoot just past a face and absorbs the sliver
        between two near-adjacent crossed columns.
    Untouched segment dicts are REUSED (callers may hold a pre-split snapshot);
    split pieces are copies, with the mark kept on the longest piece only (mark
    ownership stays one-segment-per-mark). Curved beams are left alone.
    `extra_footprints` (from column_outline_footprints) adds obstacles for real
    columns the detector could not place. Returns the number of segments split,
    trimmed or dropped.
    """
    footprints = _column_footprints(sections, circles) + list(extra_footprints or [])
    if not footprints:
        return 0
    min_piece_ft = config.mm_to_ft(_SPLIT_MIN_PIECE_MM)
    pen_ft = config.mm_to_ft(_SPLIT_MIN_PENETRATION_MM)
    margin_ft = config.mm_to_ft(_SPLIT_JUNCTION_MARGIN_MM)
    end_eps_ft = config.mm_to_ft(0.1)
    changed = 0
    rebuilt = []
    for seg in beam_segments.get("segments", []):
        ox, oy = seg["start"][0], seg["start"][1]
        ex, ey = seg["end"][0], seg["end"][1]
        vx, vy = ex - ox, ey - oy
        length = (vx * vx + vy * vy) ** 0.5
        if length <= 0.0:
            rebuilt.append(seg)
            continue
        ux, uy = vx / length, vy / length
        intervals = []
        for fp in footprints:
            span = _footprint_interval(fp, ox, oy, ux, uy, length, pen_ft)
            if span is None:
                continue
            t0, t1, tc = span
            start_touch = t0 <= end_eps_ft
            end_touch = t1 >= length - end_eps_ft
            if start_touch and end_touch:
                intervals.append((0.0, length))     # buried inside the column
            elif start_touch:
                if tc > margin_ft:                  # start pokes past the centre
                    intervals.append((0.0, t1))     # trim it forward to the far face
            elif end_touch:
                if tc < length - margin_ft:         # end pokes past the centre
                    intervals.append((t0, length))  # trim it back to the near face
            else:
                intervals.append((t0, t1))          # genuine crossing: split here
        if not intervals:
            rebuilt.append(seg)
            continue
        intervals.sort()
        merged = [list(intervals[0])]
        for t0, t1 in intervals[1:]:
            if t0 <= merged[-1][1] + min_piece_ft:
                merged[-1][1] = max(merged[-1][1], t1)
            else:
                merged.append([t0, t1])
        pieces = []
        prev = 0.0
        for t0, t1 in merged:
            pieces.append((prev, t0))
            prev = t1
        pieces.append((prev, length))
        pieces = [p for p in pieces if p[1] - p[0] >= min_piece_ft]
        if not pieces:
            # pokes out under _SPLIT_MIN_PIECE_MM on every side: the whole "beam"
            # sits on top of the column -- exactly what must not be drawn
            changed += 1
            continue
        changed += 1
        z = seg["start"][2]
        longest = max(pieces, key=lambda p: p[1] - p[0])
        for t0, t1 in pieces:
            piece = dict(seg)
            piece["start"] = [ox + ux * t0, oy + uy * t0, z]
            piece["end"] = [ox + ux * t1, oy + uy * t1, z]
            piece["length_mm"] = (t1 - t0) * _MM
            if (t0, t1) != longest:
                piece["mark"] = None
            rebuilt.append(piece)
    beam_segments["segments"] = rebuilt
    return changed

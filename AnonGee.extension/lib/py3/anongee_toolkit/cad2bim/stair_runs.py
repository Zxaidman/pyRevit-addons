# -*- coding: utf-8 -*-
"""Reading RUNS out of drawn riser lines.

The risers are the one part of a stair a structural plan always draws, so the
flights are recovered from them: lines that share a direction and a spacing are
one run, and the spacing itself is the tread. Three shapes need three readers:

    _riser_runs         straight flights -- equidistant parallel lines
    _spiral_run         a spiral: risers radiating from one centre, ordered by
                        angle rather than by position
    _fan_runs           winders: a fan of risers whose midpoints are equidistant
                        and whose direction turns monotonically, which is what
                        separates a real winder from a mess of stray lines

Everything is measured, never assumed: the tread comes from the modal spacing of
the drawn lines, the width from their length, and a run with too few risers to
be evidence is refused rather than guessed at. Revit-free.
"""

import math
from collections import defaultdict

from . import config
from . import stair_tolerances as tol

_MM = config.MM_PER_FT
_POSITION_DEDUPE_MM = 10.0    # the same riser drawn per-run appears twice


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ------------------------------------------------------- option 2: stair linework
_RISER_ANGLE_TOL = math.radians(3.0)


_RISER_MIN_LINES = 3          # fewer parallel lines than this is not a flight


def _riser_runs(lines):
    """RUNS from one stair's linework, EVERY direction considered.

    Riser lines bucket by direction; within a bucket, same-length lines whose
    ACROSS spans overlap belong to the same run; each run's riser positions
    (deduped -- the shared riser between adjacent panels is drawn once per
    panel) must be >= 3 and equidistant within tread limits. A dog-leg keeps
    one direction; a SQUARE stair (four flights around a well, Project1)
    contributes runs from two perpendicular directions.

    Returns [{"axis", "normal", "positions", "span_lo", "span_hi", "center"}]
    -- axis is the unit vector positions are measured along, normal the riser
    direction spans are measured along.
    """
    buckets = defaultdict(list)
    # a line's direction is unsigned, so the bucket key WRAPS: an angle just
    # under pi is the same direction as one just over zero. Without the wrap a
    # flight drawn with some risers "backwards" split into two buckets and lost
    # most of its lines (StaircasePlan-Test2's stairs).
    bucket_count = max(1, int(round(math.pi / _RISER_ANGLE_TOL)))
    for a, b in lines:
        ang = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        key = int(round(ang / _RISER_ANGLE_TOL)) % bucket_count
        buckets[key].append((a, b))
    runs = []
    dedupe_ft = config.mm_to_ft(_POSITION_DEDUPE_MM)
    for _key, bucket in sorted(buckets.items()):
        if len(bucket) < _RISER_MIN_LINES:
            continue
        # risers are same-length; a boundary line in the same direction (the
        # drawn landing edge, twice their length) would BRIDGE the run groups
        lengths = sorted(_dist(a, b) for a, b in bucket)
        median_len = lengths[len(lengths) // 2]
        bucket = [(a, b) for a, b in bucket
                  if 0.6 * median_len <= _dist(a, b) <= 1.4 * median_len]
        if len(bucket) < _RISER_MIN_LINES:
            continue
        a0, b0 = bucket[0]
        ang = math.atan2(b0[1] - a0[1], b0[0] - a0[0]) % math.pi
        dx, dy = math.cos(ang), math.sin(ang)      # along a riser line
        px, py = -dy, dx                           # the run axis
        items = []
        for a, b in bucket:
            pos = ((a[0] + b[0]) / 2.0) * px + ((a[1] + b[1]) / 2.0) * py
            lo = min(a[0] * dx + a[1] * dy, b[0] * dx + b[1] * dy)
            hi = max(a[0] * dx + a[1] * dy, b[0] * dx + b[1] * dy)
            items.append((pos, lo, hi))
        parent = list(range(len(items)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                lo = max(items[i][1], items[j][1])
                hi = min(items[i][2], items[j][2])
                shorter = min(items[i][2] - items[i][1],
                              items[j][2] - items[j][1])
                if shorter > 0 and (hi - lo) > 0.3 * shorter:
                    parent[find(i)] = find(j)
        grouped = defaultdict(list)
        for i in range(len(items)):
            grouped[find(i)].append(items[i])
        stray_ft = config.mm_to_ft(tol._TREAD_MIN_MM * 0.9)
        for group in grouped.values():
            merged = []
            for pos, lo, hi in sorted(group):
                # closer than a tread = the per-panel duplicate of the same
                # riser, or a stray near-parallel line -- one position only
                if merged and pos - merged[-1][0] <= stray_ft:
                    prev = merged[-1]
                    merged[-1] = (prev[0], min(prev[1], lo), max(prev[2], hi))
                else:
                    merged.append((pos, lo, hi))
            for chain in _equidistant_chains(merged):
                positions = [p for p, _lo, _hi in chain]
                # the flight's width is the TYPICAL riser span, not the union:
                # one line often runs past the flight (a U's bottom landing edge
                # crosses the well), and taking the extremes stretched the run
                # over that well and threw its centreline off (Test2 stair 1).
                lo, hi = _modal_span(chain)
                mid_pos = (positions[0] + positions[-1]) / 2.0
                mid_off = (lo + hi) / 2.0
                runs.append({"axis": (px, py), "normal": (dx, dy),
                             "positions": positions, "span_lo": lo,
                             "span_hi": hi,
                             "center": (px * mid_pos + dx * mid_off,
                                        py * mid_pos + dy * mid_off)})
    return runs + _fan_runs(lines, runs)


_FAN_MID_TOL_MM = 60.0        # a fan's midpoints stay this close to one line


_FAN_LENGTH_TOL = 0.30        # winder risers grow along the turn, but not wildly


_FAN_MIN_RISERS = 4           # fewer than this is noise, not a winder flight


_FAN_MIN_TURN = math.radians(12.0)   # a fan TURNS; a straight flight does not


def _fan_runs(lines, runs):
    """Runs whose risers FAN instead of staying parallel (a winder flight).

    A balanced winder keeps the going constant on the WALK LINE, so its risers
    rotate and their ends spread unevenly along the two sides -- the parallel
    detector sees a different direction per riser and finds nothing (three of
    StaircasePlan-Test2's six stairs). Two things stay true and identify it:

      * the riser MIDPOINTS sit on one straight line, one tread apart;
      * the risers TURN, monotonically, by a real angle across the flight.

    That second test is what keeps this off ordinary geometry -- a straight
    flight turns by nothing and is already the parallel detector's job.
    """
    seen = set()
    pool = []
    for a, b in lines:
        length = _dist(a, b)
        if length <= 0:
            continue
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
        key = (round(mid[0] * _MM), round(mid[1] * _MM), round(length * _MM))
        if key in seen:
            continue                     # the same riser drawn twice
        seen.add(key)
        pool.append((mid, a, b, length,
                     math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi))
    if len(pool) < _FAN_MIN_RISERS:
        return []
    tol = config.mm_to_ft(_FAN_MID_TOL_MM)
    found = []
    for band in _length_bands(pool):
        found += _fans_in_band(band, tol)
    return _best_fans(found, runs)


def _length_bands(pool):
    """The distinct groups of similar-length lines, biggest group first.

    Length bands, not one median: a stair's linework is mostly short nosing and
    outline marks, so the median length of the whole cluster is nowhere near the
    flight width and a single band misses the winder entirely. Riser lines of
    one flight DO share a length (the flight width), so a band is a candidate.
    """
    bands = {}
    for item in pool:
        length = item[3]
        if length <= 0:
            continue
        band = tuple(sorted(
            i for i, other in enumerate(pool)
            if abs(other[3] - length) <= _FAN_LENGTH_TOL * length))
        if len(band) >= _FAN_MIN_RISERS:
            bands[band] = [pool[i] for i in band]
    return sorted(bands.values(), key=len, reverse=True)


def _fans_in_band(band, tol):
    """Fan runs among one length band, over every walk direction."""
    found = []
    # try every walk direction on the same angular grid the parallel pass uses
    steps = max(1, int(round(math.pi / _RISER_ANGLE_TOL)))
    for step in range(steps):
        angle = step * _RISER_ANGLE_TOL
        ux, uy = math.cos(angle), math.sin(angle)
        # the normal follows the parallel pass's handedness -- axis is the
        # normal turned +90 degrees -- or the rebuilt centreline mirrors
        nx, ny = uy, -ux
        rows = defaultdict(list)
        for item in band:
            mid = item[0]
            across = mid[0] * nx + mid[1] * ny
            rows[int(round(across / tol))].append(
                (mid[0] * ux + mid[1] * uy, item))
        for row in rows.values():
            if len(row) < _FAN_MIN_RISERS:
                continue
            row.sort()
            across = sum(item[0][0] * nx + item[0][1] * ny
                         for _p, item in row) / len(row)
            for chain in _equidistant_chains([(p, 0.0, 0.0) for p, _i in row]):
                if len(chain) < _FAN_MIN_RISERS:
                    continue
                wanted = set(round(p * _MM) for p, _lo, _hi in chain)
                members = [(p, item) for p, item in row
                           if round(p * _MM) in wanted]
                if len(members) < _FAN_MIN_RISERS:
                    continue
                turn = _monotone_turn([item[4] for _p, item in members])
                if turn is None or abs(turn) < _FAN_MIN_TURN:
                    continue             # parallel risers: not a winder
                widths = sorted(item[3] for _p, item in members)
                width = widths[len(widths) // 2]
                positions = [p for p, _item in members]
                mid_pos = (positions[0] + positions[-1]) / 2.0
                found.append({
                    "axis": (ux, uy), "normal": (nx, ny),
                    "positions": positions,
                    # span_lo/hi are ABSOLUTE projections on the normal, exactly
                    # as the parallel runs report them: the run dicts rebuild
                    # the centreline from them, and centred values would put it
                    # on the axis instead of on the flight
                    "span_lo": across - width / 2.0,
                    "span_hi": across + width / 2.0,
                    "fanned": True, "turn": turn,
                    "riser_lines": [(item[1], item[2]) for _p, item in members],
                    "center": (ux * mid_pos + nx * across,
                               uy * mid_pos + ny * across)})
    return found


def _monotone_turn(angles):
    """Total signed rotation across a fan, or None when it does not turn evenly.

    Riser directions are unsigned (mod pi), so each step is taken as the SHORT
    way round; the steps must all lean the same way for the flight to be a fan
    rather than a scatter of near-parallel strays.
    """
    if len(angles) < 3:
        return None
    total = 0.0
    sign = 0
    for i in range(len(angles) - 1):
        step = (angles[i + 1] - angles[i]) % math.pi
        if step > math.pi / 2.0:
            step -= math.pi              # the short way round
        if abs(step) < 1e-9:
            continue
        if sign and (step > 0) != (sign > 0):
            return None                  # turns back on itself
        sign = 1 if step > 0 else -1
        total += step
    return total if sign else None


def _best_fans(fans, runs):
    """Keep the longest fans that share no risers with each other or a run.

    The direction sweep finds the same flight from several nearby angles and
    also finds its sub-chains, so the raw list over-counts; a fan survives only
    when most of its risers are still unclaimed.
    """
    def keys(fan):
        return set((round(a[0] * _MM), round(a[1] * _MM),
                    round(b[0] * _MM), round(b[1] * _MM))
                   for a, b in fan["riser_lines"])

    claimed = set()
    for run in runs:
        for pos in run["positions"]:
            claimed.add(round(pos * _MM / 15.0))
    kept = []
    used = set()
    for fan in sorted(fans, key=lambda f: (-len(f["positions"]),
                                           -abs(f.get("turn") or 0.0))):
        mine = keys(fan)
        if len(mine - used) < _FAN_MIN_RISERS:
            continue                     # already covered by a longer fan
        on_a_run = sum(1 for pos in fan["positions"]
                       if round(pos * _MM / 15.0) in claimed)
        if on_a_run > len(fan["positions"]) / 2:
            continue                     # a parallel run already has these
        used |= mine
        kept.append(fan)
    return kept


_SPAN_BUCKET_MM = 5.0        # riser ends within this are the same drawn span


def _modal_span(chain):
    """The (lo, hi) span MOST of the chain's riser lines actually have.

    Always a real drawn extent, unlike a per-end median, which can pair the low
    end of one line with the high end of another and invent a width no riser
    has.
    """
    bucket = config.mm_to_ft(_SPAN_BUCKET_MM)
    tally = defaultdict(list)
    for _pos, lo, hi in chain:
        tally[(round(lo / bucket), round(hi / bucket))].append((lo, hi))
    best = max(tally.values(), key=lambda group: (len(group),
                                                  group[0][1] - group[0][0]))
    return (sum(g[0] for g in best) / len(best),
            sum(g[1] for g in best) / len(best))


def _equidistant_chains(merged):
    """Split riser positions into maximal EQUIDISTANT chains (one per flight).

    A drawn flight is a run of positions one tread apart; the landing and the
    boundary lines past the last riser sit further away. Rejecting the whole
    group when its gaps are not uniform threw away real flights (test9's stairs
    lose 11 risers at 300 mm to two trailing 800 mm gaps), so the gaps that are
    not a tread SEGMENT the group instead of disqualifying it.
    """
    step = _tread_step(merged)
    chains = []
    current = []
    for item in merged:
        if not current:
            current = [item]
            continue
        gap = (item[0] - current[-1][0]) * _MM
        multiple = _tread_multiple(gap, step)
        if multiple:
            # a gap of exactly k treads means k-1 riser lines were not drawn
            # (a break line, a landing edge drawn over them): rebuild them so
            # the flight stays whole and its riser count stays right
            previous = current[-1]
            for missing in range(1, multiple):
                fraction = float(missing) / multiple
                current.append((previous[0] + (item[0] - previous[0]) * fraction,
                                previous[1], previous[2]))
            current.append(item)
        else:
            if len(current) >= _RISER_MIN_LINES:
                chains.append(current)
            current = [item]
    if len(current) >= _RISER_MIN_LINES:
        chains.append(current)
    return chains


def _tread_step(merged):
    """The flight's tread: the median gap that falls inside the tread range."""
    gaps = sorted((merged[i + 1][0] - merged[i][0]) * _MM
                  for i in range(len(merged) - 1))
    inside = [g for g in gaps if tol._TREAD_MIN_MM <= g <= tol._TREAD_MAX_MM]
    if not inside:
        return None
    return inside[len(inside) // 2]


_MAX_MISSING_RISERS = 3      # a bigger jump is a landing, not a gap in a flight


def _tread_multiple(gap, step):
    """How many treads this gap spans (1 = the next riser), or 0 if it is not
    a whole multiple of the tread -- that is where the flight really ends."""
    if step is None or step <= 0:
        return 0
    for multiple in range(1, _MAX_MISSING_RISERS + 1):
        if abs(gap - step * multiple) <= 60.0:
            return multiple
    return 0


_SPIRAL_MIN_LINES = 5          # radial risers needed to call a stair circular


_SPIRAL_CENTER_TOL = 0.20      # extension must pass within 20% of riser length


_SPIRAL_DOMINANCE = 0.60       # radial lines must be most of the cluster


_SPIRAL_STEP_TOL = 0.60        # one flight turns at an even angular pitch


_SPIRAL_SAME_RISER = 0.40      # angles this much closer than the pitch are one riser


_SPIRAL_DUP_RAD = math.radians(0.5)   # below this two lines are the SAME riser


_SPIRAL_MIN_TURN = math.radians(90.0)  # less turn than this is a winder corner


_WINDER_REACH = 1.6            # corner leftovers within reach x width join it


def _spiral_run(cluster):
    """A CIRCULAR stair: riser lines RADIATE from a common centre.

    Every line's extension must pass near one point and the endpoint distances
    must form a consistent radial band. Returns {"center", "radius" (mid),
    "width_mm", "start_angle", "included_angle", "clockwise", "risers",
    "tread_mm"} or None.
    """
    if len(cluster) < _SPIRAL_MIN_LINES:
        return None
    # candidate centre: intersect the first line with the most-perpendicular one
    inter = []
    n = len(cluster)
    for i in range(n):
        a1, b1 = cluster[i]
        d1 = (b1[0] - a1[0], b1[1] - a1[1])
        for j in range(i + 1, n):
            a2, b2 = cluster[j]
            d2 = (b2[0] - a2[0], b2[1] - a2[1])
            den = d1[0] * d2[1] - d1[1] * d2[0]
            L1 = math.hypot(*d1)
            L2 = math.hypot(*d2)
            if L1 <= 0 or L2 <= 0 or abs(den) < 0.3 * L1 * L2:
                continue                     # near-parallel: unstable crossing
            t = ((a2[0] - a1[0]) * d2[1] - (a2[1] - a1[1]) * d2[0]) / den
            inter.append((a1[0] + d1[0] * t, a1[1] + d1[1] * t))
    if len(inter) < 3:
        return None
    cx = sorted(p[0] for p in inter)[len(inter) // 2]
    cy = sorted(p[1] for p in inter)[len(inter) // 2]
    lengths = sorted(_dist(a, b) for a, b in cluster)
    median_len = lengths[len(lengths) // 2]
    # SELECT the radial lines, do not demand them: a drawn spiral carries its
    # stairwell walls and nosing marks on the same layer, and bailing on the
    # first non-radial line is why Test2's spiral produced nothing.
    radial = []
    for a, b in cluster:
        dxl, dyl = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dxl, dyl)
        if L <= 0:
            continue
        # distance from the centre to the infinite line
        off = abs((a[0] - cx) * dyl - (a[1] - cy) * dxl) / L
        if off <= _SPIRAL_CENTER_TOL * median_len:
            radial.append((a, b))
    if len(radial) < _SPIRAL_MIN_LINES:
        return None
    if float(len(radial)) / len(cluster) < _SPIRAL_DOMINANCE:
        return None                          # a fan in a corner, not a spiral
    angles = []
    r_in = []
    r_out = []
    for a, b in radial:
        ra = math.hypot(a[0] - cx, a[1] - cy)
        rb = math.hypot(b[0] - cx, b[1] - cy)
        r_in.append(min(ra, rb))
        r_out.append(max(ra, rb))
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        angles.append(math.atan2(my - cy, mx - cx))
    r_lo = sorted(r_in)[len(r_in) // 2]
    r_hi = sorted(r_out)[len(r_out) // 2]
    if (r_hi - r_lo) < 0.5 * median_len:
        return None
    # order angularly; the largest gap separates the flight from empty air
    order = sorted(range(len(angles)), key=lambda i: angles[i])
    sorted_angles = [angles[i] for i in order]
    gaps = [(sorted_angles[(i + 1) % len(sorted_angles)] - sorted_angles[i])
            % (2.0 * math.pi) for i in range(len(sorted_angles))]
    cut = max(range(len(gaps)), key=lambda i: gaps[i])
    seq = [sorted_angles[(cut + 1 + i) % len(sorted_angles)]
           for i in range(len(sorted_angles))]
    unwrapped = [seq[0]]
    for ang in seq[1:]:
        step = (ang - unwrapped[-1]) % (2.0 * math.pi)
        unwrapped.append(unwrapped[-1] + step)
    unwrapped = _merge_close_angles(unwrapped)
    if len(unwrapped) < _SPIRAL_MIN_LINES:
        return None
    included = unwrapped[-1] - unwrapped[0]
    if included <= 0 or included > 2.0 * math.pi * 0.999:
        return None
    if included < _SPIRAL_MIN_TURN:
        return None                          # a winder corner, not a spiral
    steps = [unwrapped[i + 1] - unwrapped[i] for i in range(len(unwrapped) - 1)]
    even = sorted(steps)[len(steps) // 2]
    if even <= 0 or max(abs(s - even) for s in steps) > _SPIRAL_STEP_TOL * even:
        return None                          # uneven pitch: not one spiral flight
    mid_r = (r_lo + r_hi) / 2.0
    # A spiral's going can be read on the WALK LINE (300mm off the inner edge,
    # the code measure) or across the MIDDLE of the flight. Neither suits every
    # stair: Test2's spiral is 2000 wide on a 300 inner radius, where the walk
    # line reads 139mm and would reject treads that are exactly 300 across the
    # middle. Take whichever reading is a plausible going, walk line first.
    pitch = included / len(steps)
    walk_mm = pitch * (r_lo + config.mm_to_ft(300.0)) * _MM
    mid_mm = pitch * mid_r * _MM
    tread_mm = None
    for value in (walk_mm, mid_mm):
        if tol._TREAD_MIN_MM <= value <= tol._TREAD_MAX_MM:
            tread_mm = value
            break
    if tread_mm is None:
        return None
    return {"center": (cx, cy), "radius": mid_r,
            "width_mm": (r_hi - r_lo) * _MM,
            "start_angle": unwrapped[0], "included_angle": included,
            "clockwise": False, "risers": len(unwrapped),
            "tread_mm": tread_mm}


def _merge_close_angles(unwrapped):
    """Collapse risers drawn twice: angles far closer than the typical step.

    Test2's spiral carries every riser as two collinear lines, so 24 treads
    arrived as 48 and the going came out half of what is drawn. Duplicates sit
    at a step of ~0, so they must be kept OUT of the median -- with half the
    steps zero the median is zero and nothing merges at all.
    """
    if len(unwrapped) < 3:
        return unwrapped
    steps = sorted(step for step in (unwrapped[i + 1] - unwrapped[i]
                                     for i in range(len(unwrapped) - 1))
                   if step > _SPIRAL_DUP_RAD)
    if not steps:
        return unwrapped
    typical = steps[len(steps) // 2]
    merged = [unwrapped[0]]
    for angle in unwrapped[1:]:
        if angle - merged[-1] < _SPIRAL_SAME_RISER * typical:
            continue                         # the same riser drawn again
        merged.append(angle)
    return merged


def _winder_corners(cluster, runs, run_dicts):
    """ANGLED risers in a turn (a winder corner instead of a flat landing).

    Leftover riser-length lines that sit in the corner between two consecutive
    flights and point BETWEEN their riser directions are the drawn winders.
    Returns [{"after_run": i, "riser_lines": [((x1,y1),(x2,y2)), ...]}].
    """
    if len(run_dicts) < 2 or not runs:
        return []
    lengths = sorted((r["span_hi"] - r["span_lo"]) for r in runs)
    median_w = lengths[len(lengths) // 2]
    used = []
    for run in runs:
        px, py = run["axis"]
        for pos in run["positions"]:
            used.append((run, pos))

    def in_a_run(a, b):
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        ang_line = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        for run in runs:
            nx, ny = run["normal"]
            ang_norm = math.atan2(ny, nx) % math.pi
            dang = abs(ang_line - ang_norm) % math.pi
            if min(dang, math.pi - dang) > 0.1:
                continue
            px, py = run["axis"]
            pos = mx * px + my * py
            if any(abs(pos - q) * _MM < 15.0 for q in run["positions"]):
                return True
        return False

    def angled(a, b):
        # a WINDER riser points BETWEEN the flights: a leftover parallel to a
        # flight's risers (a stray) or to its axis (a landing boundary) is not
        ang_line = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
        for run in runs:
            for vx, vy in (run["normal"], run["axis"]):
                ang_v = math.atan2(vy, vx) % math.pi
                dang = abs(ang_line - ang_v) % math.pi
                if min(dang, math.pi - dang) < 0.12:
                    return False
        return True

    # a FANNED run is already made of angled risers -- counting them again here
    # would place the same winder twice and double the stair's riser total
    fanned = set()
    for run in runs:
        for a, b in run.get("riser_lines") or []:
            fanned.add((round(a[0] * _MM), round(a[1] * _MM),
                        round(b[0] * _MM), round(b[1] * _MM)))

    def in_a_fan(a, b):
        return (round(a[0] * _MM), round(a[1] * _MM),
                round(b[0] * _MM), round(b[1] * _MM)) in fanned

    leftovers = [(a, b) for a, b in cluster
                 if 0.6 * median_w <= _dist(a, b) <= 1.4 * median_w
                 and not in_a_run(a, b) and not in_a_fan(a, b)
                 and angled(a, b)]
    if not leftovers:
        return []
    out = []
    reach = median_w * _WINDER_REACH
    inside = median_w * 1.1        # a winder stays IN the corner square; a
    #                                break-line diagonal shoots past it
    for i in range(len(run_dicts) - 1):
        ex, ey = run_dicts[i]["end"]
        sx, sy = run_dicts[i + 1]["start"]
        cx, cy = (ex + sx) / 2.0, (ey + sy) / 2.0
        fan = [(a, b) for a, b in leftovers
               if math.hypot((a[0] + b[0]) / 2.0 - cx,
                             (a[1] + b[1]) / 2.0 - cy) <= reach
               and math.hypot(a[0] - cx, a[1] - cy) <= inside
               and math.hypot(b[0] - cx, b[1] - cy) <= inside]
        if fan:
            out.append({"after_run": i, "riser_lines": fan})
    return out

# -*- coding: utf-8 -*-
"""Work out the geometry of a FOLD or SUNK step, before Revit is touched.

A step is not one element. The office builds it from THREE floors -- confirmed
against their own Revit detail -- and the middle one is the part a naive
two-floor reading has no answer for:

  1. the PARENT, on its level, with the stepped area cut out of it;
  2. the SUPPORT, hanging under the parent's edge along the step line: the
     vertical concrete between the two soffits;
  3. the DROPPED slab, at the lower level.

Without the support the step is a gap rather than concrete -- a model that looks
right in plan and is hollow in section.

THE SUPPORT'S EXISTENCE AND DEPTH ARE DERIVED, NOT CONFIGURED. Take the
parent's top as 0:

    parent soffit          -T_parent
    dropped slab top       -d                    (d = the fold/sunk value)
    dropped slab soffit    -(d + T_dropped)

A support exists only where there is a VOID to fill -- where the drop is
deeper than the parent is thick (d > T_parent), so the dropped slab's top sits
below the parent's soffit and daylight shows between them. Where d <= T_parent
the dropped slab's own side face already rises past the parent's soffit: the
two faces overlap, the section is solid, and a "support" there is a second
slab buried inside concrete that exists. That is not hypothetical -- the
corridor drawing produced exactly that pair of phantom 250 mm footings before
this condition was tightened from "soffit gap > 0" to "void exists".

Where the void is real, the support is cast full height, soffit to soffit --
the user's own detail shows the 350 drop off a 200 slab cast as one 350-deep
support at -200, overlapping the dropped slab's edge rather than stopping at
its top:

    offset  = -T_parent
    depth   =  d + T_dropped - T_parent
    width   =  T_parent                          (in plan, under the parent)

The sunk cases both land right under this rule, each for its own reason.
test10's original F6 (1000 thick, sunk 1000, between 2000-thick pads):
1000 < 2000, no void, the pad IS the face. The redrawn corridor (sunk 250 in a
500 block): 250 < 500, no void, the dropped slab's edge IS the face. The
first looks like "the soffit gap is zero" -- 1000+1000-2000 -- but that is the
coincidence of its numbers, not the rule; the corridor's gap is 250 and there
is still nothing to fill.

A support is one slab per contiguous stepped RUN, never a strip per edge, and
neighbouring step regions POOL theirs: three folds drawn in a row inside one
footing get one support slab whose outer edge wraps the whole group and whose
hollows are the three folds -- the concrete between them is part of the same
cast. Separate collars would overlap each other in the gaps, which Revit takes
as three intersecting floors.

Revit-free, so all of it is unit-testable and replayable offline. Compare
`footing_plan.py`, which does the same job for the pads.
"""

import math

from . import config
from .classify.layers import CATEGORY_FOLD, CATEGORY_SUNK
from .slab_graph import _centroid, _dedup_ring, _point_in_ring, _signed_area

_MM = config.MM_PER_FT

FOLD = "fold"
SUNK = "sunk"

_CATEGORY_KIND = {CATEGORY_FOLD: FOLD, CATEGORY_SUNK: SUNK}

# A "step" deeper than this is a STOREY, not a step. Test9's legend carries
# `T.O.S. +50MM`, `+400MM` and `+6250` in the same list: the first two are
# steps and the third is a different floor, which must never be built as a fold
# hanging off this one. 2000 is a real fold (test10's F3), so the line sits
# above that and well below a storey height.
_MAX_STEP_MM = 3000.0

# How far outside an edge to look for the concrete the step steps down from.
# Small: the dropped region and its neighbour SHARE the edge in the fixture, so
# anything wider than the neighbour is not a subtler test, just a wrong one.
_PROBE_MM = 10.0

# Two rings are "the same outline" within this much area. test10's sunk hatch
# and its F6 outline are drawn to identical coordinates; the tolerance is for
# arithmetic, not for drafting slop.
_SAME_AREA = 0.01


def step_regions(regions):
    """[(ring, kind)] for the hatched fold/sunk regions, in reading order.

    `regions` are RegionRecords the reader kept out of `records` (a hatch is an
    area, not a curve). Only the two step categories are taken; a column fill
    or a legend swatch on some other layer is not a step.
    """
    out = []
    for region in (regions or []):
        kind = _CATEGORY_KIND.get(getattr(region, "category", None))
        if kind is None:
            continue
        ring = _dedup_ring([(p[0], p[1]) for p in region.points])
        if len(ring) >= 3:
            out.append((ring, kind))
    return out


def plan_steps(plans, regions, max_step_mm=None):
    """The three parts of every step, plus what was refused and why.

    `plans` are the outlines `foundation_plan.plan_foundations` read (or any
    dicts shaped {"ring", "thickness_mm", "steps", "mark"} -- slab loops carry
    the same three keys, which is what lets this serve both). `regions` are the
    reader's hatches, already classified.

    Returns {"steps": [...], "skipped": [reasons], "notes": [reasons]}. Each
    step is

        {"kind", "ring", "depth_mm", "mark",
         "dropped": {"ring", "thickness_mm", "offset_mm"},
         "supports": [{"ring", "holes", "thickness_mm", "offset_mm"}],
         "opening": ring or None,
         "host_index": i}

    Neighbouring collars POOL (`_pool_collars`): one slab per touching group,
    carried by the group's first step, every pooled region in its `holes`.

    `opening` is the hole the PARENT needs cut in it, and it is None exactly
    when the region IS its host outline -- test10's sunk strip is its own F6
    foundation, so there is nothing to cut and the host itself is what drops.
    """
    limit = _MAX_STEP_MM if max_step_mm is None else float(max_step_mm)
    out = {"steps": [], "skipped": [], "notes": []}
    rings = [(index, plan) for index, plan in enumerate(plans or [])
             if plan.get("ring") and len(plan["ring"]) >= 3]
    for ring, kind in step_regions(regions):
        host_index, host = _host_for(ring, rings)
        if host is None:
            out["skipped"].append(
                "a {0} region of {1:.1f} m2 sits inside no outline: nothing to "
                "step".format(kind, area_m2(ring)))
            continue
        depth = _depth_for(ring, host, kind)
        if depth is None:
            out["skipped"].append(
                "a {0} region in {1} carries no depth: the note that would "
                "give it is missing".format(kind, host.get("mark") or "an "
                                            "unnamed outline"))
            continue
        if depth > limit:
            # NOT a fold: a different storey. Building it as one would hang a
            # floor a storey below this one off the wrong level.
            out["skipped"].append(
                "{0:.0f} mm is a storey, not a {1} (over {2:.0f} mm): the "
                "region in {3} is left flat".format(
                    depth, kind, limit, host.get("mark") or "an unnamed outline"))
            continue
        out["steps"].append(_parts(ring, kind, depth, host, host_index, rings))
    _pool_collars(out["steps"], out["notes"])
    return out


def _pool_collars(steps, notes):
    """Merge the collars of NEIGHBOURING regions into one slab per group.

    test10 draws three fold rectangles in a row inside each raft, 300 mm
    apart, and a collar reaches one parent-thickness (1500) past its region --
    so the three collars overlap heavily, and Revit reads them as three
    intersecting floors. The cast reality is ONE support: its outer edge wraps
    the whole group, the three folds are its hollows, and the concrete between
    folds belongs to it. So collars in the same host, at the same thickness
    and offset, whose outer rings touch, pool: outer ring = the union outline,
    holes = every region in the group (mutated in place -- the pooled slab
    replaces the first group member's collar and the rest lose theirs).

    Pooling is rectilinear -- the union walks a compressed grid -- so a group
    with a non-rectangular collar is left unpooled and says so. Every hatch in
    this corpus is a rectangle; the note is for the drawing that breaks that.
    """
    collars = []               # (step, support, rect) for every poolable collar
    irregular = False
    for step in steps:
        for support in step["supports"]:
            if not support["holes"]:
                continue                     # strips and Ls do not pool
            rect = _as_rect(support["ring"])
            if rect is None:
                irregular = True
                continue
            collars.append((step, support, rect))
    if irregular and len(collars) < 2:
        return
    groups = _touching_groups(collars)
    for group in groups:
        if len(group) < 2:
            continue
        outer, pockets = _rect_union_outline([rect for _s, _sup, rect in group])
        if outer is None:
            notes.append("{0} overlapping support collars left separate: a "
                         "non-rectangular union".format(len(group)))
            continue
        first = group[0][1]
        first["ring"] = outer
        holes = []
        for _step, support, _rect in group:
            holes.extend(support["holes"])
        first["holes"] = holes + pockets
        for step, support, _rect in group[1:]:
            step["supports"].remove(support)


def _touching_groups(collars):
    """Collars grouped transitively by touching outers, same depth and offset.

    A group never crosses hosts: a support is cast within one footing, so two
    footings' collars stay two slabs even if the drawn rectangles graze.
    """
    groups = []
    for entry in collars:
        step, support, rect = entry
        joined = None
        for group in groups:
            for other_step, other_support, other_rect in group:
                if other_step["host_index"] != step["host_index"]:
                    continue
                if other_support["thickness_mm"] != support["thickness_mm"]:
                    continue
                if other_support["offset_mm"] != support["offset_mm"]:
                    continue
                if not _rects_touch(rect, other_rect):
                    continue
                if joined is None:
                    group.append(entry)
                    joined = group
                else:
                    joined.extend(group)
                    group[:] = []
                break
        if joined is None:
            groups.append([entry])
    return [group for group in groups if group]


_TOUCH_TOL_FT = 1.0 / 304.8    # a millimetre: drawn-to-meet counts as touching


def _rects_touch(a, b):
    return not (a[2] < b[0] - _TOUCH_TOL_FT or b[2] < a[0] - _TOUCH_TOL_FT
                or a[3] < b[1] - _TOUCH_TOL_FT or b[3] < a[1] - _TOUCH_TOL_FT)


def _as_rect(ring):
    """(x0, y0, x1, y1) when the ring is an axis-aligned rectangle, else None."""
    cleaned = _dedup_ring(list(ring))
    if len(cleaned) != 4:
        return None
    tol = _TOUCH_TOL_FT
    for index in range(4):
        a = cleaned[index]
        b = cleaned[(index + 1) % 4]
        if abs(a[0] - b[0]) > tol and abs(a[1] - b[1]) > tol:
            return None                  # a slanted edge
    xs = [p[0] for p in cleaned]
    ys = [p[1] for p in cleaned]
    return (min(xs), min(ys), max(xs), max(ys))


def _rect_union_outline(rects):
    """(outer_ring, pocket_rings) -- the outline of a union of rectangles.

    Walks a coordinate-compressed grid: cells covered by any rectangle are the
    union, and the boundary between covered and uncovered is the outline.
    Exact for axis-aligned input, which is what `_as_rect` guarantees. Returns
    (None, []) if the union is not one connected piece -- the caller grouped
    by touching, so that would mean the grouping and the geometry disagree.

    `pocket_rings` are ENCLOSED uncovered areas -- a courtyard of collars.
    They become holes: the parent above them is full depth, so support
    concrete there would hang below solid slab that needs none.
    """
    # Coordinates within a millimetre are ONE coordinate. The drawn rectangles
    # carry float noise in their last bits, and without this the union outline
    # grows micro-jogs a fraction of a nanometre wide -- sixteen vertices where
    # the shape has four, on edges shorter than Revit's curve tolerance.
    snap_x = _snapped([r[0] for r in rects] + [r[2] for r in rects])
    snap_y = _snapped([r[1] for r in rects] + [r[3] for r in rects])
    rects = [(snap_x[r[0]], snap_y[r[1]], snap_x[r[2]], snap_y[r[3]])
             for r in rects]
    xs = sorted(set(snap_x.values()))
    ys = sorted(set(snap_y.values()))
    covered = {}
    for x0, y0, x1, y1 in rects:
        for column in range(len(xs) - 1):
            if xs[column] < x0 - _TOUCH_TOL_FT or xs[column + 1] > x1 + _TOUCH_TOL_FT:
                continue
            for row in range(len(ys) - 1):
                if ys[row] < y0 - _TOUCH_TOL_FT or ys[row + 1] > y1 + _TOUCH_TOL_FT:
                    continue
                covered[(column, row)] = True

    # Boundary segments, oriented with the COVERED side on the left, so the
    # outer ring walks counter-clockwise and every pocket clockwise -- the
    # sign of the walked area tells the two apart without a containment test.
    segments = {}
    for (column, row) in covered:
        x0, x1 = xs[column], xs[column + 1]
        y0, y1 = ys[row], ys[row + 1]
        if (column, row - 1) not in covered:
            segments[((x0, y0), (x1, y0))] = True    # bottom edge, left-to-right
        if (column, row + 1) not in covered:
            segments[((x1, y1), (x0, y1))] = True    # top edge, right-to-left
        if (column - 1, row) not in covered:
            segments[((x0, y1), (x0, y0))] = True    # left edge, downward
        if (column + 1, row) not in covered:
            segments[((x1, y0), (x1, y1))] = True    # right edge, upward

    starts = {}
    for (a, b) in segments:
        starts.setdefault(a, []).append(b)
    rings = []
    while segments:
        (a, b) = next(iter(segments))
        ring = [a]
        cursor = (a, b)
        while True:
            del segments[cursor]
            starts[cursor[0]].remove(cursor[1])
            ring.append(cursor[1])
            if cursor[1] == a:
                break
            following = starts.get(cursor[1]) or []
            if not following:
                return None, []          # open boundary: not a clean union
            cursor = (cursor[1], following[0])
        rings.append(_collinear_simplified(ring[:-1]))

    outers = [ring for ring in rings if _signed_area(ring) > 0]
    if len(outers) != 1:
        return None, []                  # disconnected union, or none at all
    pockets = [ring for ring in rings if _signed_area(ring) < 0]
    return outers[0], pockets


def _snapped(values):
    """{value: cluster representative} -- coordinates within a mm collapse."""
    mapping = {}
    anchor = None
    for value in sorted(set(values)):
        if anchor is None or value - anchor > _TOUCH_TOL_FT:
            anchor = value
        mapping[value] = anchor
    return mapping


def _collinear_simplified(ring):
    """The ring without the vertices the grid compression introduced."""
    out = []
    count = len(ring)
    for index in range(count):
        previous = ring[(index - 1) % count]
        point = ring[index]
        following = ring[(index + 1) % count]
        cross = ((point[0] - previous[0]) * (following[1] - point[1])
                 - (point[1] - previous[1]) * (following[0] - point[0]))
        if abs(cross) > 1e-12:
            out.append(point)
    return out if len(out) >= 3 else ring


def _host_for(ring, rings):
    """(index, plan) of the outline a step region belongs to, else (None, None).

    The SMALLEST outline containing the region's centre wins, so a pad drawn
    inside a raft takes its own step rather than the raft's.
    """
    centre = _centroid(ring)
    best = (None, None, None)
    for index, plan in rings:
        if not _point_in_ring(centre, plan["ring"]):
            continue
        size = abs(_signed_area(plan["ring"]))
        if best[2] is None or size < best[2]:
            best = (index, plan, size)
    return best[0], best[1]


def _depth_for(ring, host, kind):
    """The step's depth in mm: the note INSIDE this region, else the host's one.

    A host can hold several steps -- test10's F3 rings carry three fold notes
    each, one per fold region, and each note sits inside the region it belongs
    to. Containment therefore pairs them exactly, and proximity never has to be
    guessed at. The single-note fallback is for a region whose note was placed
    just outside it.
    """
    same_kind = [step for step in (host.get("steps") or [])
                 if step.get("step_kind") == kind and step.get("step_mm")]
    if not same_kind:
        return None
    for step in same_kind:
        point = step.get("point")
        if point and _point_in_ring((point[0], point[1]), ring):
            return float(step["step_mm"])
    if len(same_kind) == 1:
        return float(same_kind[0]["step_mm"])
    return None


def _parts(ring, kind, depth_mm, host, host_index, rings):
    """One step's parent opening, support slab(s) and dropped slab.

    The parent is read PER EDGE, from whatever outline abuts it, because the two
    cases disagree about who the parent is. A region cut out of its host steps
    down from that host. A region that IS its host -- an outline the drawing
    marks sunk in its entirety -- steps down from the NEIGHBOURS it abuts, and
    they are a different thickness: reading the host there says the region
    steps down from itself, and invents a support that the drawing's own
    arithmetic says is not there.

    A support is ONE slab per contiguous run of stepped edges, not a strip per
    edge. A fold in the middle of a footing gets a closed band round the whole
    region -- the region itself the hollow in it; a fold in a corner gets one
    L-shaped slab round its two inner edges. Separate strips would meet at the
    corners edge-to-edge, which Revit joins as two butting floors rather than
    the one cast collar the detail shows.
    """
    # The dropped slab is as thick as whatever it is a piece of: its own
    # outline when it IS one, otherwise the parent it was cut out of.
    dropped_thickness = host.get("thickness_mm")
    coincident = _is_host_itself(ring, host["ring"])
    edges = _outward_edges(ring)
    sides = []                          # per edge: (width_mm, depth_mm) or None
    for edge in edges:
        parent = _neighbour_beyond(edge, rings,
                                   skip=host_index if coincident else None)
        thickness = parent.get("thickness_mm") if parent else None
        if not thickness:
            sides.append(None)         # open ground: nothing to step down from
            continue
        if depth_mm <= thickness:
            # No void. The drop is shallower than the parent is thick, so the
            # dropped slab's own side face rises past the parent's soffit and
            # the section is already solid concrete. A support here is a
            # phantom slab inside it -- the corridor drawing's pair of 250 mm
            # footings at -500 were exactly this.
            sides.append(None)
            continue
        sides.append((thickness,
                      depth_mm + (dropped_thickness or 0.0) - thickness))
    return {"kind": kind, "ring": ring, "depth_mm": depth_mm,
            "mark": host.get("mark"), "host_index": host_index,
            "dropped": {"ring": ring, "thickness_mm": dropped_thickness,
                        "offset_mm": -depth_mm},
            "supports": _support_slabs(edges, sides),
            "opening": None if coincident else ring}


def _support_slabs(edges, sides):
    """[{ring, holes, thickness_mm, offset_mm}] -- one slab per stepped run.

    Every edge is stepped the same way -> ONE closed band: the outer ring is
    the region offset outward by the parent's thickness, and the region itself
    the hollow -- a collar with the drop cut out of it. Otherwise each
    contiguous run of stepped edges (same parent thickness, same remaining
    depth) becomes one polygon: outward offsets along the run, mitred at the
    corners it turns, closed back along the region's own edge -- a single edge
    gives the plain strip, a corner's two edges the L.

    `holes` is a LIST because collars pool: `_pool_collars` merges the collars
    of neighbouring regions into one slab carrying every region as a hollow.
    """
    stepped = [side for side in sides if side]
    if stepped and len(stepped) == len(sides) and len(set(stepped)) == 1:
        width, depth = stepped[0]
        outer = [_miter(edges[index - 1], edges[index], width, width)
                 for index in range(len(edges))]
        return [{"ring": outer, "holes": [[edge[0] for edge in edges]],
                 "thickness_mm": depth, "offset_mm": -width}]
    slabs = []
    for run in _runs(sides):
        width, depth = sides[run[0]]
        outer = [_offset_point(edges[run[0]], 0, width)]
        for position in range(1, len(run)):
            outer.append(_miter(edges[run[position] - 1], edges[run[position]],
                                width, width))
        outer.append(_offset_point(edges[run[-1]], 1, width))
        inner = [edges[index][0] for index in reversed(run)]
        slabs.append({"ring": outer + [edges[run[-1]][1]] + inner,
                      "holes": [],
                      "thickness_mm": depth, "offset_mm": -width})
    return slabs


def _runs(sides):
    """Maximal circular runs of consecutive edges stepped the same way."""
    count = len(sides)
    in_run = [index for index in range(count) if sides[index]]
    if not in_run:
        return []
    runs = []
    current = [in_run[0]]
    for index in in_run[1:]:
        if index == current[-1] + 1 and sides[index] == sides[current[0]]:
            current.append(index)
        else:
            runs.append(current)
            current = [index]
    runs.append(current)
    # The ring is circular: a run ending at the last edge continues into one
    # starting at the first, so a corner fold's two edges join into one L even
    # when the ring happens to start between them.
    if (len(runs) > 1 and runs[0][0] == 0 and runs[-1][-1] == count - 1
            and sides[0] == sides[count - 1]):
        runs[0] = runs.pop() + runs[0]
    return runs


def _offset_point(edge, end, width_mm):
    """An edge endpoint pushed straight out by the support's width."""
    point = edge[end]
    normal = edge[2]
    reach = config.mm_to_ft(width_mm)
    return (point[0] + normal[0] * reach, point[1] + normal[1] * reach)


def _miter(edge_a, edge_b, width_a, width_b):
    """Where the two edges' outward offsets MEET at their shared corner.

    The intersection of the two offset lines -- for the right angles the corpus
    draws, the corner pushed out by both normals at once. Parallel edges (a
    straight side arriving as two pieces) have no intersection; either offset
    is already the point.
    """
    shared = edge_b[0]
    na, nb = edge_a[2], edge_b[2]
    wa, wb = config.mm_to_ft(width_a), config.mm_to_ft(width_b)
    cross = na[0] * nb[1] - na[1] * nb[0]
    if abs(cross) < 1e-9:
        return (shared[0] + na[0] * wa, shared[1] + na[1] * wa)
    # Solve (p - shared) . na = wa and (p - shared) . nb = wb.
    dx = (wa * nb[1] - wb * na[1]) / cross
    dy = (wb * na[0] - wa * nb[0]) / cross
    return (shared[0] + dx, shared[1] + dy)


def _is_host_itself(ring, host_ring):
    """True when the region and its host are the same outline, drawn twice.

    test10's sunk hatch is drawn to the same coordinates as its F6 foundation.
    That is not a hole in F6 -- it is the statement that F6 is the sunk one.
    """
    host_area = abs(_signed_area(host_ring))
    if host_area <= 0:
        return False
    return abs(abs(_signed_area(ring)) - host_area) / host_area <= _SAME_AREA


def _outward_edges(ring):
    """[(a, b, normal)] for each edge, `normal` pointing OUT of the ring."""
    ordered = list(ring)
    if _signed_area(ordered) < 0:
        ordered.reverse()               # counter-clockwise: interior on the left
    edges = []
    count = len(ordered)
    for index in range(count):
        a = ordered[index]
        b = ordered[(index + 1) % count]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.sqrt(dx * dx + dy * dy)
        if length <= 0:
            continue
        edges.append((a, b, (dy / length, -dx / length)))
    return edges


def _neighbour_beyond(edge, rings, skip=None):
    """The outline just beyond this edge -- the step's parent there -- else None.

    `skip` drops the host from the search: when the region IS its host, the
    host's own concrete is the thing that dropped, so finding it beyond the edge
    would say the strip steps down from itself. The SMALLEST match wins, for the
    same reason the host does: a pad drawn inside a raft is the nearer parent.
    """
    a, b, normal = edge
    reach = config.mm_to_ft(_PROBE_MM)
    probe = ((a[0] + b[0]) / 2.0 + normal[0] * reach,
             (a[1] + b[1]) / 2.0 + normal[1] * reach)
    best, smallest = None, None
    for index, plan in rings:
        if index == skip:
            continue
        if not _point_in_ring(probe, plan["ring"]):
            continue
        size = abs(_signed_area(plan["ring"]))
        if smallest is None or size < smallest:
            best, smallest = plan, size
    return best


def area_m2(ring):
    """A ring's plan area in square metres, for reporting and thresholds."""
    return abs(_signed_area(ring)) * (_MM / 1000.0) ** 2

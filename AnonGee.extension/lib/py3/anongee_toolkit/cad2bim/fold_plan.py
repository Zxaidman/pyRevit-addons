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

THE SUPPORT'S DEPTH IS DERIVED, NOT CONFIGURED. Take the parent's top as 0:

    parent soffit          -T_parent
    dropped slab top       -d                    (d = the fold/sunk value)
    dropped slab soffit    -(d + T_dropped)

The support fills what is between the two soffits, so it hangs from the parent's
soffit and reaches the dropped slab's:

    offset  = -T_parent
    depth   =  d + T_dropped - T_parent          (nothing to fill when <= 0)
    width   =  T_parent                          (in plan, under the parent)

The user's own detail is the equal-thickness case of that formula: a 350 THK
slab dropping 350 gives depth 350 + 350 - 350 = 350 at offset -350... and the
detail they supplied reads 200 for both, on a slab whose two levels are 0.000
and -350.000, which is the same arithmetic with T = 200: depth 350, offset -200.

The formula is corroborated by the fixture from the other direction. test10's
sunk strip F6 is 1000 thick, drops 1000, and sits between F5 pads 2000 thick:
1000 + 1000 - 2000 = 0. No support -- and none is needed, because the pad is
full depth right up to the shared edge and already IS the vertical face. Three
independent numbers landing on exactly zero is not a coincidence; it is what
tells us the convention is soffit-aligned rather than something we chose.

A support is emitted per EDGE, and only where concrete continues on the far side
of it. The test is a probe just outside the edge: inside another outline means
there is something for the step to step down from. test10's sunk strip abuts a
pad on its two long sides and open ground on its two short ones, so a naive
"support all the way round" would wrap concrete round two faces that have
nothing to hold.

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
         "supports": [{"ring", "thickness_mm", "offset_mm"}],
         "opening": ring or None,
         "host_index": i}

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
    return out


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
        depth = depth_mm + (dropped_thickness or 0.0) - thickness
        if depth <= 0:
            # The two soffits already meet -- the parent is deep enough to BE
            # the vertical face. Filling this would double the concrete.
            sides.append(None)
            continue
        sides.append((thickness, depth))
    return {"kind": kind, "ring": ring, "depth_mm": depth_mm,
            "mark": host.get("mark"), "host_index": host_index,
            "dropped": {"ring": ring, "thickness_mm": dropped_thickness,
                        "offset_mm": -depth_mm},
            "supports": _support_slabs(edges, sides),
            "opening": None if coincident else ring}


def _support_slabs(edges, sides):
    """[{ring, hole, thickness_mm, offset_mm}] -- one slab per stepped run.

    Every edge is stepped the same way -> ONE closed band: the outer ring is
    the region offset outward by the parent's thickness, and the region itself
    is the `hole` -- a collar with the drop as its hollow. Otherwise each
    contiguous run of stepped edges (same parent thickness, same remaining
    depth) becomes one polygon: outward offsets along the run, mitred at the
    corners it turns, closed back along the region's own edge -- a single edge
    gives the plain strip, a corner's two edges the L.
    """
    stepped = [side for side in sides if side]
    if stepped and len(stepped) == len(sides) and len(set(stepped)) == 1:
        width, depth = stepped[0]
        outer = [_miter(edges[index - 1], edges[index], width, width)
                 for index in range(len(edges))]
        return [{"ring": outer, "hole": [edge[0] for edge in edges],
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
                      "hole": None,
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

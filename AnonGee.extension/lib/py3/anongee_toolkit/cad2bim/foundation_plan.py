# -*- coding: utf-8 -*-
"""Read the foundations the DRAWING carries, instead of inventing them.

`footing_plan.py` derives pads from the columns: it grows each column footprint
by a projection and merges the overlaps. That is a guess, and it can only ever
produce pads -- a raft is larger than a column by definition, so no amount of
growing a column reaches one. This module reads what the engineer actually
drew: an outline on the foundation layer, sized and named by the note sitting
inside it (test10's foundation level, `S-FND` + `S-FND-IDEN`).

An outline arrives three ways, and the one real fixture uses all of them:

  * DRAWN CLOSED. A closed polyline IS the outline; it is taken exactly as
    drawn, never re-derived, because a foundation the engineer closed by hand
    is not a thing to second-guess.

  * FROM THE LINEWORK. Loose lines and open polylines whose planar FACES are
    the outlines. Shared edges are the norm, not the exception -- two outlines
    drawn against each other carry their common edge ONCE -- so the faces are
    walked half-edge style, which reads a shared edge from both sides where a
    consume-as-you-chain assembler closes nothing.

  * COMPLETED THROUGH THE STEP LAYERS. test10's corridor block closes only
    through the SUNK rectangle's sides: the foundation layer carries the top
    and bottom seams and two vertical stubs, and the drawn sunk region supplies
    the middle of each side. Step-layer LINES therefore join the face graph --
    and are then DISSOLVED: a fold or sunk line marks where a foundation steps,
    never where one ends, so two faces separated only by step linework are one
    outline and are merged back together.

The face graph also splits segments wherever another segment ENDS on them.
Drafting reality: test10's right seam overshoots the raft corner by 400 mm, and
without the split that whole edge dangles and is pruned, taking the outline
with it.

NESTED outlines are the drawing's way of saying "a different foundation is let
into this one": the corridor block sits wholly inside the big raft. The inner
ring is reported as a HOLE of its parent (`plan["holes"]`), one level deep, the
same way the slab builder nests openings -- the parent is cast around it and
the inner outline is cast as its own slab inside.

A CROSSED-OUT face is the drawing's way of saying "no concrete here at all".
The convention is the standard opening symbol: two straight strokes spanning
the face corner-to-corner, an X -- test10 draws them on "A-DETL", a detail
layer no category claims, over the north and south parts of the corridor
strip. A nested face carrying the X is a CUTOUT: it is never an element, it
never completes a neighbour through the step-line dissolve, and its ring
becomes a hole of the plan that contains it. Read any other way the raft was
cast solid over the crossed-out parts -- the user found the corridor filled in
Revit against a drawing that crosses it out. Both strokes must reach the
corners (within `_CUTOUT_MARK_MM`), one per diagonal: a single slash is a
section mark or a leader, and an X floating short of the corners belongs to
whatever it is actually drawn on.

**A drawing has to prove it uses the convention before any of this is
trusted.** `plan_foundations` returns nothing unless at least one outline
carries a foundation note. Test0 is why: its `S-FNDN` layer holds 187 records
of arcs and angled linework that close into four accidental faces and carry no
label anywhere in the drawing. Placing those as foundations would be worse than
the column-derived guess it replaced. Refusing them costs nothing -- the caller
falls back to `footing_plan` exactly as before.

Sizing and naming mirror the slab chain deliberately: a note names and sizes
the SMALLEST ring it sits inside -- nested outlines make "any ring it sits
inside" ambiguous -- and an unlabelled ring keeps `thickness_mm` None for the
builder to fall back on. Compare `slab_labels.py`.

Revit-free, so it is unit-testable and replayable offline.
"""

from collections import defaultdict

from . import config
from . import foundation_labels
from . import slab_graph
from .classify.layers import (CATEGORY_FOLD, CATEGORY_FOUNDATION,
                              CATEGORY_SUNK)
from .geom import shapes
from .slab_graph import (_centroid, _cluster_nodes, _dedup_ring, _dist,
                         _is_simple_ring, _next_ccw, _point_in_ring,
                         _signed_area)

_MM = config.MM_PER_FT

# A face smaller than this is a junction sliver, not a foundation. Deliberately
# below slab_graph's 1 m2: a pile cap under a single column is legitimately
# small, and unlike a slab bay it has a label to prove it means something.
_MIN_AREA_M2 = 0.25

# Endpoint identity for the face walk: read LIVE from slab_graph at each use,
# never copied at import -- a copy freezes the value before apply_tolerances
# runs, and the dialog's "Node weld distance" silently stops reaching the
# foundation walk (the exact trap stair_tolerances.py warns about).

# The categories whose LINES may complete an outline without being one.
_STEP_CATEGORIES = (CATEGORY_FOLD, CATEGORY_SUNK)

# How close a cross stroke's end must land to the face corner it claims. The
# fixture's strokes hit their corners exactly; 50 mm forgives an annotator's
# snap without letting a slash across half the face count as the symbol.
_CUTOUT_MARK_MM = 50.0


def apply_tolerances(tolerances):
    """Override the module's tunables from the dialog's Foundations tab.

    The pushbutton calls this once per run; anything absent keeps its default,
    so the offline tests and replays are unaffected.
    """
    global _MIN_AREA_M2
    if not tolerances:
        return
    _MIN_AREA_M2 = float(tolerances.get("foundation_min_area_m2",
                                        _MIN_AREA_M2))


def outlines(records, category=CATEGORY_FOUNDATION):
    """[(ring, z, source)] -- every closed foundation outline on the plan.

    `source` is "drawn" for a ring the engineer closed and "linework" for one
    recovered from the loose segments, so a caller (and a test) can tell which
    machinery produced it. Rings are in internal feet, like every other ring in
    this package. A crossed-out face is NOT an outline -- see `cutouts`.
    """
    return _outlines_and_cutouts(records, category)[0]


def cutouts(records, category=CATEGORY_FOUNDATION):
    """The crossed-out rings: faces the drawing voids with the X symbol.

    Counted by the regression sweep; `plan_foundations` attaches them as holes
    of the plan containing them itself, so nothing else needs to.
    """
    return _outlines_and_cutouts(records, category)[1]


def _outlines_and_cutouts(records, category):
    """(outlines, cutout rings) from ONE walk over the foundation linework."""
    tol_ft = config.mm_to_ft(slab_graph._CHAIN_TOL_MM)
    rings = []
    segments = []
    flags = []                       # True: outline linework; False: step linework
    for record in records:
        on_outline = record.category == category
        on_step = record.category in _STEP_CATEGORIES
        if not on_outline and not on_step:
            continue
        points = [(p[0], p[1]) for p in record.points]
        if len(points) < 2:
            continue
        z = record.points[0][2]
        if on_outline and len(points) >= 4 and _dist(points[0], points[-1]) <= tol_ft:
            ring = _dedup_ring(points)
            if len(ring) >= 3:
                rings.append((ring, z, "drawn"))
            continue
        for index in range(len(points) - 1):
            if _dist(points[index], points[index + 1]) > 1e-9:
                segments.append((points[index], points[index + 1]))
                flags.append(on_outline)
    # The cross is annotation, so its strokes live on whatever layer the
    # drafter annotates on -- the FULL record list is searched, not the
    # foundation categories the walk itself is built from.
    strokes = _cross_strokes(records) if len(segments) >= 3 else []
    faces, marked = _faces(segments, flags, strokes,
                           [ring for ring, _z, _source in rings])
    for ring in faces:
        rings.append((ring, 0.0, "linework"))
    return rings, marked


def _faces(segments, flags, strokes=(), drawn=()):
    """The bounded faces of the loose foundation linework, as rings.

    Endpoints within `_SNAP_MM` are one node, and a segment is SPLIT wherever
    another segment's endpoint lands on its body -- a seam drawn a little long
    (test10's overshoots by 400 mm) otherwise dangles from its far end and is
    pruned, taking the boundary with it. A chain that still ends in mid-air is
    pruned, because a face walking out and back along a stub is a pinched ring
    Revit will not accept.

    Step-layer segments (`flags[i]` False) take part in the walk and are then
    dissolved: any two REAL faces separated only by step linework are merged,
    because a fold line says "the foundation steps here", not "the foundation
    ends here". The walk traces bounded faces counter-clockwise and each
    component's outer face clockwise, so keeping positive area drops the outer
    ones without needing to know which they were.

    Returns (rings, cutout rings). Crossed-out faces are split off BEFORE the
    dissolve, which is what makes the order matter: the X spans the PART it
    voids, never the merged whole, and a voided part must not carry its
    neighbours through the step lines either -- pull test10's north part out
    first and the sunk bay between the two crosses is left bounded entirely by
    step linework, which the rule below already refuses.
    """
    if len(segments) < 3:
        return [], []
    snap_ft = config.mm_to_ft(slab_graph._SNAP_MM)
    segments, flags = _split_at_endpoints(segments, flags, snap_ft)
    key, nodes = _cluster_nodes([p for segment in segments for p in segment],
                                snap_ft)
    adjacency = defaultdict(set)
    outline_edges = set()
    for (a, b), on_outline in zip(segments, flags):
        node_a, node_b = key(a), key(b)
        if node_a == node_b:
            continue
        adjacency[node_a].add(node_b)
        adjacency[node_b].add(node_a)
        if on_outline:
            outline_edges.add(frozenset((node_a, node_b)))
    changed = True
    while changed:
        changed = False
        for node in list(adjacency.keys()):
            if len(adjacency[node]) == 1:
                adjacency[next(iter(adjacency[node]))].discard(node)
                del adjacency[node]
                changed = True

    faces = _key_faces(nodes, adjacency)
    faces, cutout_rings = _split_off_cutouts(faces, nodes, strokes, drawn)
    faces = _dissolve_steps(faces, nodes, outline_edges)

    min_area_ft2 = _MIN_AREA_M2 * (1000.0 / _MM) ** 2
    out = []
    for keys in faces:
        count = len(keys)
        if not any(frozenset((keys[i], keys[(i + 1) % count])) in outline_edges
                   for i in range(count)):
            # bounded entirely by step linework: a sunk region drawn with lines
            # but no foundation boundary anywhere is a step mark, not a footing
            continue
        ring = _dedup_ring([nodes[k] for k in keys])
        if len(ring) < 3:
            continue
        if _signed_area(ring) < min_area_ft2:
            continue                   # an outer face (negative), or a sliver
        if not _is_simple_ring(ring):
            continue                   # bow-tie: never a foundation
        # Drop the vertices the SPLITTING left behind, not any the drawing has:
        # a face stops wherever the linework was cut, so a straight side can
        # arrive as several collinear pieces. Collinear-only, so no shape moves.
        simplified = shapes.simplify_ring(ring)
        out.append(simplified if len(simplified) >= 3 else ring)
    return out, cutout_rings


def _cross_strokes(records):
    """[(a, b)] -- every straight two-point record, whatever its layer.

    A LINE, or a polyline holding exactly two points. Category is deliberately
    not consulted: the cross is drawn on an annotation layer ("A-DETL" in the
    fixture) that maps to nothing, and the strokes prove themselves by landing
    on a face's corners, not by where they live.
    """
    out = []
    for record in (records or []):
        if getattr(record, "kind", None) not in ("line", "polyline"):
            continue
        points = getattr(record, "points", None) or []
        if len(points) != 2:
            continue
        a, b = (points[0][0], points[0][1]), (points[1][0], points[1][1])
        if _dist(a, b) > 1e-9:
            out.append((a, b))
    return out


def _split_off_cutouts(faces, nodes, strokes, drawn):
    """(faces without the crossed-out ones, their rings as holes-to-be).

    A face is a cutout when BOTH of its diagonals are drawn corner-to-corner
    (`_crossed`) AND it is nested inside another face or a drawn ring. The
    nesting requirement is the same boundary the step-note rule stands on: a
    zone inside a foundation describes that foundation, while a top-level
    outline is its own element -- an X over one of those is a detail crop or a
    demolition mark on something this pass does not own, and voiding it would
    delete a foundation on the strength of two loose lines.
    """
    if not strokes:
        return faces, []
    rings = []
    for keys in faces:
        ring = _dedup_ring([nodes[k] for k in keys])
        rings.append(ring if len(ring) >= 3 and _signed_area(ring) > 0
                     else None)
    marked = []
    for index, ring in enumerate(rings):
        if ring is None or not _crossed(ring, strokes):
            continue
        containers = [c for c in drawn] + [
            other for other_index, other in enumerate(rings)
            if other is not None and other_index != index
            and _signed_area(other) > _signed_area(ring)]
        if any(all(_point_in_ring(vertex, container) for vertex in ring)
               for container in containers):
            marked.append(index)
    if not marked:
        return faces, []
    keep = [keys for index, keys in enumerate(faces) if index not in marked]
    cut = []
    for index in marked:
        simplified = shapes.simplify_ring(rings[index])
        cut.append(simplified if len(simplified) >= 3 else rings[index])
    return keep, cut


def _crossed(ring, strokes):
    """True when two strokes span the face corner-to-corner -- the X symbol.

    The face's CORNERS are what the strokes are measured against, not its
    vertices: the walk stops wherever the linework was split, so a straight
    side can carry mid-edge vertices the drawing does not have. Four corners,
    two diagonals, one stroke per diagonal, each end within `_CUTOUT_MARK_MM`
    of the corner it claims. One diagonal alone is not the symbol.
    """
    corners = shapes.simplify_ring(ring)
    if len(corners) != 4:
        return False
    tol = config.mm_to_ft(_CUTOUT_MARK_MM)

    def lands(stroke, a, b):
        p, q = stroke
        return ((_dist(p, a) <= tol and _dist(q, b) <= tol)
                or (_dist(p, b) <= tol and _dist(q, a) <= tol))

    return all(any(lands(stroke, corners[first], corners[first + 2])
                   for stroke in strokes)
               for first in (0, 1))


def _split_at_endpoints(segments, flags, tol_ft):
    """Segments cut wherever ANOTHER segment's endpoint lies on their body.

    This is the T-junction case the endpoint clustering cannot see: the
    crossing point is a vertex of one piece and the middle of the other, so no
    pair of ENDPOINTS is close and nothing unifies. Splitting makes the meeting
    a node of both.
    """
    points = []
    for a, b in segments:
        points.append(a)
        points.append(b)
    tol2 = tol_ft * tol_ft
    out = []
    out_flags = []
    for (a, b), flag in zip(segments, flags):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length2 = dx * dx + dy * dy
        cuts = []
        for p in points:
            t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2
            if t <= 1e-9 or t >= 1.0 - 1e-9:
                continue
            fx, fy = a[0] + t * dx, a[1] + t * dy
            if (fx - p[0]) ** 2 + (fy - p[1]) ** 2 <= tol2:
                cuts.append(t)
        vertices = [a]
        for t in sorted(cuts):
            fx, fy = a[0] + t * dx, a[1] + t * dy
            if _dist(vertices[-1], (fx, fy)) > tol_ft / 2.0:
                vertices.append((fx, fy))
        if _dist(vertices[-1], b) <= tol_ft / 2.0:
            vertices[-1] = b
        else:
            vertices.append(b)
        for index in range(len(vertices) - 1):
            out.append((vertices[index], vertices[index + 1]))
            out_flags.append(flag)
    return out, out_flags


def _key_faces(nodes, adjacency):
    """Every face of the planar graph, as NODE KEY rings.

    The same half-edge walk as `slab_graph._walk_faces`, kept in keys rather
    than coordinates because the dissolve step needs to know which face is on
    the other side of an edge, and keys make that a dictionary lookup.
    """
    visited = set()
    faces = []
    for a in adjacency:
        for b in adjacency[a]:
            if (a, b) in visited:
                continue
            keys = []
            edge = (a, b)
            while edge not in visited:
                visited.add(edge)
                keys.append(edge[0])
                edge = (edge[1], _next_ccw(nodes, adjacency, edge))
            faces.append(keys)
    return faces


def _dissolve_steps(faces, nodes, outline_edges):
    """Merge REAL faces separated only by step linework.

    Only two POSITIVE faces merge: a step line on the boundary of a component
    also separates a cell from that component's outer (negative) face, and
    merging with the outside would dissolve the outline itself. One merge per
    pass, repeated until nothing merges, because each merge rewrites the face
    list the edge->face map was built from.
    """
    def area(keys):
        return _signed_area([nodes[k] for k in keys])

    changed = True
    while changed:
        changed = False
        owner = {}
        for index, keys in enumerate(faces):
            count = len(keys)
            for position in range(count):
                owner[(keys[position], keys[(position + 1) % count])] = index
        for (u, v), index in owner.items():
            if frozenset((u, v)) in outline_edges:
                continue
            other = owner.get((v, u))
            if other is None or other == index:
                continue
            if area(faces[index]) <= 0 or area(faces[other]) <= 0:
                continue
            merged = _stitch(faces[index], faces[other], outline_edges)
            if merged is None:
                continue
            faces = [merged if i == index else keys
                     for i, keys in enumerate(faces) if i != other]
            changed = True
            break
    return faces


def _stitch(face_a, face_b, outline_edges):
    """One ring from two, dropping every step edge the pair shares.

    The surviving directed edges of both faces are walked back into a single
    cycle. A node with more than one way out, or edges left over after the
    walk, means the union pinches or holds a hole -- not a foundation outline,
    so the merge is refused rather than guessed at.
    """
    def directed(keys):
        count = len(keys)
        return [(keys[i], keys[(i + 1) % count]) for i in range(count)]

    edges_a = directed(face_a)
    edges_b = directed(face_b)
    reversed_b = set((v, u) for u, v in edges_b)
    shared = set(edge for edge in edges_a
                 if edge in reversed_b
                 and frozenset(edge) not in outline_edges)
    keep = ([edge for edge in edges_a if edge not in shared]
            + [edge for edge in edges_b if (edge[1], edge[0]) not in shared])
    if not keep:
        return None
    outgoing = {}
    for u, v in keep:
        if u in outgoing:
            return None                # a pinch: two ways out of one node
        outgoing[u] = v
    start = keep[0][0]
    ring = [start]
    node = outgoing[start]
    while node != start:
        if node not in outgoing or len(ring) > len(keep):
            return None
        ring.append(node)
        node = outgoing[node]
    if len(ring) != len(keep):
        return None                    # leftover edges: a hole, not one ring
    return ring


def plan_foundations(records, texts, category=CATEGORY_FOUNDATION):
    """[{ring, z, mark, thickness_mm, steps, source, labels, holes, kind}] for
    the DRAWN foundations.

    `texts` are the foundation notes -- the caller routes them by layer, the
    way slab notes are routed, because that is what tells `foundation_labels`
    a bare "1200MM THK" is a raft rather than a slab.

    EMPTY when the drawing does not carry the convention: no foundation layer,
    or a foundation layer whose rings nothing names. The caller falls back to
    the column-offset derivation then, which is what it did before this module
    existed.

    Each note belongs to the SMALLEST ring containing it: outlines nest, and
    the corridor block's note sits inside the big raft too, where it would
    otherwise size both. `steps` collects the FOLD/SUNK notes assigned to the
    ring, for `fold_plan` to pair against the hatched regions. `holes` are the
    rings the parent is cast AROUND: outlines nested directly inside it, and
    any crossed-out face it contains -- the difference being that a nested
    outline is also placed as its own slab, while a cutout is only ever the
    hole. `kind` is "raft" or "pad" -- see `_kind`. Decided HERE, in the
    Revit-free layer, so the builder only routes on it and a test can pin the
    rule offline.
    """
    rings, crossed_out = _outlines_and_cutouts(records, category)
    assigned = [[] for _ring in rings]
    labelled = 0
    for text, note in _parsed_labels(texts):
        best = None
        best_area = None
        point = text.point_internal
        if not point:
            continue
        for index, (ring, _z, _source) in enumerate(rings):
            if not _point_in_ring((point[0], point[1]), ring):
                continue
            size = abs(_signed_area(ring))
            if best_area is None or size < best_area:
                best, best_area = index, size
        if best is not None:
            assigned[best].append((text, note))
    plans = []
    for index, (ring, z, source) in enumerate(rings):
        inside = assigned[index]
        mark, thickness = _size_from(inside, ring)
        steps = [{"step_mm": note["step_mm"], "step_kind": note["step_kind"],
                  # The note's THK is the DROPPED slab's own thickness: the
                  # folds repeat their raft's 750, but the sunk bay says 500
                  # against a 750 raft, and the host cannot know that.
                  "thickness_mm": note["thickness_mm"],
                  "point": text.point_internal}
                 for text, note in inside if note["step_kind"]]
        plain = sum(1 for _text, note in inside if not note["step_kind"])
        plans.append({"ring": ring, "z": z, "mark": mark,
                      "thickness_mm": thickness, "steps": steps,
                      "source": source, "labels": len(inside), "holes": [],
                      "_plain": plain})
    _dissolve_step_zones(plans)
    for plan in plans:
        del plan["_plain"]
        if plan["labels"]:
            labelled += 1
    if not labelled:
        return []
    _nest(plans)
    _hole_cutouts(plans, crossed_out)
    # Kind is judged LAST, after nesting and cutouts, because holes are half
    # the evidence: the raft that earns its name by carrying the corridor hole
    # only carries it once _hole_cutouts has run.
    for plan in plans:
        plan["kind"] = _kind(plan)
    return plans


def _kind(plan):
    """"raft" or "pad" -- which naming template a placed outline takes.

    Two tells, either sufficient, both read off the drawing rather than
    configured per outline:

      * AREA. A raft covers ground no pad reaches. The threshold is
        config's `raft_min_area_m2` (60 m2): test10's raft measures ~450 m2
        and its largest pad ~35, so the line sits well clear of both sides.
        Read at call time so the number keeps one home.

      * HOLES. An outline the drawing cuts openings into -- a nested block, a
        crossed-out corridor -- is a raft by construction: a pad with an
        opening let into it is not a thing an engineer draws.

    The column-derived path never reaches here and is always "pad": a pad
    invented by growing a column footprint cannot be a raft, whatever its
    area -- that filter is the whole point of `col_region_max_side_mm`.
    """
    if plan.get("holes"):
        return "raft"
    if area_m2(plan["ring"]) >= config.DEFAULTS["raft_min_area_m2"]:
        return "raft"
    return "pad"


def _dissolve_step_zones(plans):
    """Remove a NESTED outline whose only labels are step notes.

    The redrawn test10's corridor is the case. The raft is an H whose neck is
    drawn with seams and caps, and the face walk duly returns the neck as an
    outline of its own -- but the only note inside it is `F3_500MM THK / 250MM
    SUNK`, a STEP note. A step note describes the hatched region it sits in,
    never the outline round it: reading the neck as an element cast two 500
    slabs at zero offset over concrete the 750 raft already provides (the
    user found them in Revit against a drawing that shows one raft).

    Only a nested zone dissolves. The original F6 -- an outline that IS its
    own sunk region, sitting BETWEEN pads rather than inside anything -- keeps
    being the element it always was. The zone's step notes move to the outline
    that contains it, which is the element they step.
    """
    for index in range(len(plans) - 1, -1, -1):
        plan = plans[index]
        if not plan["labels"] or plan["_plain"]:
            continue                    # unlabelled, or a real named element
        parent = None
        parent_area = None
        for other in plans:
            if other is plan:
                continue
            if not all(_point_in_ring(vertex, other["ring"])
                       for vertex in plan["ring"]):
                continue
            area = abs(_signed_area(other["ring"]))
            if parent_area is None or area < parent_area:
                parent, parent_area = other, area
        if parent is None:
            continue                    # top-level: the old F6, a real element
        parent["steps"].extend(plan["steps"])
        parent["labels"] += plan["labels"]
        plans.pop(index)


def _nest(plans):
    """Give each plan the rings of the outlines nested DIRECTLY inside it.

    Smallest container wins, one level deep, exactly as the slab builder nests
    openings: the corridor block becomes a hole in the big raft it sits in, and
    is still placed as its own slab. Without the hole the parent and the block
    occupy the same plan, which Revit takes and sections as two overlapping
    foundations.
    """
    for index, plan in enumerate(plans):
        parent = None
        parent_area = None
        area = abs(_signed_area(plan["ring"]))
        for other_index, other in enumerate(plans):
            if other_index == index:
                continue
            other_area = abs(_signed_area(other["ring"]))
            if other_area <= area:
                continue
            if not all(_point_in_ring(vertex, other["ring"])
                       for vertex in plan["ring"]):
                continue
            if parent_area is None or other_area < parent_area:
                parent, parent_area = other, other_area
        if parent is not None:
            parent["holes"].append(plan["ring"])


def _hole_cutouts(plans, cutout_rings):
    """Attach each crossed-out ring as a hole of the plan containing it.

    Smallest container, like `_nest` -- but where a nested outline is a hole
    AND its own slab, a cutout is only the hole: the X is the drawing saying
    nothing is cast there. A cutout no plan contains attaches nowhere, which
    can only happen when its container never became a plan; dropping it then
    is right, because there is no element left to cut it out of.
    """
    for ring in cutout_rings:
        parent = None
        parent_area = None
        for plan in plans:
            if not all(_point_in_ring(vertex, plan["ring"])
                       for vertex in ring):
                continue
            area = abs(_signed_area(plan["ring"]))
            if parent_area is None or area < parent_area:
                parent, parent_area = plan, area
        if parent is not None:
            parent["holes"].append(ring)


def _parsed_labels(texts):
    """[(text, note)] for the texts that read as foundation notes."""
    out = []
    for text in (texts or []):
        note = foundation_labels.parse(getattr(text, "text", None),
                                       on_foundation_layer=True)
        if note is not None:
            out.append((text, note))
    return out


def _size_from(inside, ring):
    """(mark, thickness_mm) from the notes sitting in one ring.

    A ring can hold several notes that agree -- test10's F3 rafts carry a plain
    "F3_750MM THK" plus fold notes repeating the same mark and thickness. A
    note that SIZES the foundation is preferred over one that only names it, a
    PLAIN note over a step note -- a step note's THK is the DROPPED slab's own
    thickness, so the corridor's "F3_500MM THK / 250MM SUNK" sitting near the
    raft's centre must not size the 750 raft; it still sizes F6, whose only
    note it is, because there the outline IS the dropped region -- and the
    closest to the ring's centre breaks the remaining tie, exactly as
    `slab_labels.apply_slab_labels` picks between competing slab notes.
    """
    if not inside:
        return None, None
    centre = _centroid(ring)

    def rank(pair):
        text, note = pair
        point = text.point_internal
        gap = ((point[0] - centre[0]) ** 2 + (point[1] - centre[1]) ** 2)
        return (0 if note["thickness_mm"] is not None else 1,
                1 if note["step_kind"] else 0, gap)

    text, note = min(inside, key=rank)
    mark = note["mark"]
    thickness = note["thickness_mm"]
    if mark is None or thickness is None:
        # A ring named by one note and sized by another is legitimate -- the
        # halves are read from whichever note carries them rather than dropped
        # because no single note held both.
        for _other_text, other in inside:
            if mark is None:
                mark = other["mark"]
            if thickness is None:
                thickness = other["thickness_mm"]
    return mark, thickness


def area_m2(ring):
    """A ring's plan area in square metres, for reporting and thresholds."""
    return abs(_signed_area(ring)) * (_MM / 1000.0) ** 2

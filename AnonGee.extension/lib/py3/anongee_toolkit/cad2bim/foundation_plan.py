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

# Endpoint identity for the face walk, the same 50 mm the beam graph uses.
_SNAP_MM = slab_graph._SNAP_MM

# The categories whose LINES may complete an outline without being one.
_STEP_CATEGORIES = (CATEGORY_FOLD, CATEGORY_SUNK)


def outlines(records, category=CATEGORY_FOUNDATION):
    """[(ring, z, source)] -- every closed foundation outline on the plan.

    `source` is "drawn" for a ring the engineer closed and "linework" for one
    recovered from the loose segments, so a caller (and a test) can tell which
    machinery produced it. Rings are in internal feet, like every other ring in
    this package.
    """
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
    for ring in _faces(segments, flags):
        rings.append((ring, 0.0, "linework"))
    return rings


def _faces(segments, flags):
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
    """
    if len(segments) < 3:
        return []
    snap_ft = config.mm_to_ft(_SNAP_MM)
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

    faces = _dissolve_steps(_key_faces(nodes, adjacency), nodes, outline_edges)

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
    return out


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
    """[{ring, z, mark, thickness_mm, steps, source, labels, holes}] for the
    DRAWN foundations.

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
    rings of outlines nested directly inside this one -- the parent is cast
    around them.
    """
    rings = outlines(records, category)
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
                  "point": text.point_internal}
                 for text, note in inside if note["step_kind"]]
        if inside:
            labelled += 1
        plans.append({"ring": ring, "z": z, "mark": mark,
                      "thickness_mm": thickness, "steps": steps,
                      "source": source, "labels": len(inside), "holes": []})
    if not labelled:
        return []
    _nest(plans)
    return plans


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
    note that SIZES the foundation is preferred over one that only names it,
    and the closest to the ring's centre breaks a tie, exactly as
    `slab_labels.apply_slab_labels` picks between competing slab notes.
    """
    if not inside:
        return None, None
    centre = _centroid(ring)

    def rank(pair):
        text, note = pair
        point = text.point_internal
        gap = ((point[0] - centre[0]) ** 2 + (point[1] - centre[1]) ** 2)
        return (0 if note["thickness_mm"] is not None else 1, gap)

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

# -*- coding: utf-8 -*-
"""Read the foundations the DRAWING carries, instead of inventing them.

`footing_plan.py` derives pads from the columns: it grows each column footprint
by a projection and merges the overlaps. That is a guess, and it can only ever
produce pads -- a raft is larger than a column by definition, so no amount of
growing a column reaches one. This module reads what the engineer actually
drew: an outline on the foundation layer, sized and named by the note sitting
inside it (test10's foundation level, `S-FND` + `S-FND-IDEN`).

Two ways an outline arrives, and both are needed on the one real fixture:

  * DRAWN CLOSED. A closed polyline IS the outline; it is taken exactly as
    drawn, never re-derived, because a foundation the engineer closed by hand
    is not a thing to second-guess. Ten of test10's thirteen arrive this way.

  * FROM THE LINEWORK. The rest is loose lines and open polylines whose FACES
    are the outlines. test10's central three (two 5500x11900 pads with a
    3500x5900 sunk strip between them) share their long edges: the strip's two
    sides are also the pads' inner sides, each drawn ONCE. Anything that
    consumes a segment as it chains -- `slab_outlines._chain_into_rings` -- can
    therefore close at most one of the three and in practice closes none. A
    planar face walk reads a shared edge from both sides, which is the whole
    reason it is used here.

**A drawing has to prove it uses the convention before any of this is
trusted.** `plan_foundations` returns nothing unless at least one outline
carries a foundation note. Test0 is why: its `S-FNDN` layer holds 187 records
of arcs and angled linework that close into four accidental faces and carry no
label anywhere in the drawing. Placing those as foundations would be worse than
the column-derived guess it replaced. Refusing them costs nothing -- the caller
falls back to `footing_plan` exactly as before.

Sizing and naming mirror the slab chain deliberately: a note INSIDE a ring
names and sizes it, an unlabelled ring keeps `thickness_mm` None and the
builder falls back to the type's own depth. Compare `slab_labels.py`.

Revit-free, so it is unit-testable and replayable offline.
"""

from collections import defaultdict

from . import config
from . import foundation_labels
from . import slab_graph
from .classify.layers import CATEGORY_FOUNDATION
from .geom import shapes
from .slab_graph import (_centroid, _cluster_nodes, _dedup_ring, _dist,
                         _is_simple_ring, _point_in_ring, _signed_area,
                         _walk_faces)

_MM = config.MM_PER_FT

# A face smaller than this is a junction sliver, not a foundation. Deliberately
# below slab_graph's 1 m2: a pile cap under a single column is legitimately
# small, and unlike a slab bay it has a label to prove it means something.
_MIN_AREA_M2 = 0.25

# Endpoint identity for the face walk, the same 50 mm the beam graph uses.
_SNAP_MM = slab_graph._SNAP_MM


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
    for record in records:
        if record.category != category:
            continue
        points = [(p[0], p[1]) for p in record.points]
        if len(points) < 2:
            continue
        z = record.points[0][2]
        if len(points) >= 4 and _dist(points[0], points[-1]) <= tol_ft:
            ring = _dedup_ring(points)
            if len(ring) >= 3:
                rings.append((ring, z, "drawn"))
            continue
        for index in range(len(points) - 1):
            if _dist(points[index], points[index + 1]) > 1e-9:
                segments.append((points[index], points[index + 1]))
    for ring in _faces(segments):
        rings.append((ring, 0.0, "linework"))
    return rings


def _faces(segments):
    """The bounded faces of the loose foundation linework, as rings.

    Endpoints within `_SNAP_MM` are one node; a chain that ends in mid-air is
    pruned, because a face walking out and back along a stub is a pinched ring
    Revit will not accept. The walk traces bounded faces counter-clockwise and
    the single outer face clockwise, so keeping positive area drops the outer
    one without needing to know which it was.
    """
    if len(segments) < 3:
        return []
    snap_ft = config.mm_to_ft(_SNAP_MM)
    key, nodes = _cluster_nodes([p for segment in segments for p in segment],
                                snap_ft)
    adjacency = defaultdict(set)
    for a, b in segments:
        node_a, node_b = key(a), key(b)
        if node_a != node_b:
            adjacency[node_a].add(node_b)
            adjacency[node_b].add(node_a)
    changed = True
    while changed:
        changed = False
        for node in list(adjacency.keys()):
            if len(adjacency[node]) == 1:
                adjacency[next(iter(adjacency[node]))].discard(node)
                del adjacency[node]
                changed = True
    min_area_ft2 = _MIN_AREA_M2 * (1000.0 / _MM) ** 2
    faces = []
    for ring in _walk_faces(nodes, adjacency):
        ring = _dedup_ring(ring)
        if len(ring) < 3:
            continue
        if _signed_area(ring) < min_area_ft2:
            continue                   # the outer face (negative), or a sliver
        if not _is_simple_ring(ring):
            continue                   # bow-tie: never a foundation
        # Drop the vertices the SPLITTING left behind, not any the drawing has:
        # test10's pads meet the sunk strip halfway along their inner edge, so
        # the walk stops there and the sketch would carry a corner where the
        # foundation has a straight side. Collinear-only, so no shape moves.
        simplified = shapes.simplify_ring(ring)
        faces.append(simplified if len(simplified) >= 3 else ring)
    return faces


def plan_foundations(records, texts, category=CATEGORY_FOUNDATION):
    """[{ring, z, mark, thickness_mm, steps, source, labels}] for the DRAWN foundations.

    `texts` are the foundation notes -- the caller routes them by layer, the
    way slab notes are routed, because that is what tells `foundation_labels`
    a bare "1200MM THK" is a raft rather than a slab.

    EMPTY when the drawing does not carry the convention: no foundation layer,
    or a foundation layer whose rings nothing names. The caller falls back to
    the column-offset derivation then, which is what it did before this module
    existed.

    `steps` collects every FOLD/SUNK note inside the ring rather than stamping
    one on it. A stepped foundation carries a step per region, not per outline:
    test10's two big F3 rings hold three fold notes each, matching the three
    fold hatches drawn inside them. Placing those regions is P2's job; this
    keeps the evidence together for it.
    """
    labels = _parsed_labels(texts)
    plans = []
    labelled = 0
    for ring, z, source in outlines(records, category):
        inside = [(text, note) for text, note in labels
                  if text.point_internal
                  and _point_in_ring((text.point_internal[0],
                                      text.point_internal[1]), ring)]
        mark, thickness = _size_from(inside, ring)
        steps = [{"step_mm": note["step_mm"], "step_kind": note["step_kind"],
                  "point": text.point_internal}
                 for text, note in inside if note["step_kind"]]
        if inside:
            labelled += 1
        plans.append({"ring": ring, "z": z, "mark": mark,
                      "thickness_mm": thickness, "steps": steps,
                      "source": source, "labels": len(inside)})
    if not labelled:
        return []
    return plans


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

    A ring can hold several notes that agree -- test10's F3 rings carry a plain
    "F3_1500MM THK" plus three fold notes repeating the same mark and
    thickness. A note that SIZES the foundation is preferred over one that only
    names it, and the closest to the ring's centre breaks a tie, exactly as
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

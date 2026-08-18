# -*- coding: utf-8 -*-
"""Turn a schedule row into bar geometry, in millimetres, with no Revit in sight.

This is where "T16 @ 200 B1 running X" becomes actual centrelines: where each bar
starts and stops, how far apart they sit, how high off the bottom face. The
creation layer converts these to feet and hands them to
``Rebar.CreateFromCurves``; everything decided here is decided in plain numbers
so it can be checked without opening Revit.

Two things this module works out that a schedule does not state, and both matter:

**A set only works when every bar in it is the same.** Revit lays a bar set out
by repeating one shape, so a run of bars can be a single ``Rebar`` element only
if all of them are the same length. That is true in a rectangular pad and false
the moment the outline is not -- in the five-sided pad the sample workbook
carries, bars in the same layer are genuinely different lengths. Uniform runs
collapse to a set (one element standing for thirty bars); varying runs stay
individual bars, and :attr:`LayerPlan.uniform` says which happened so the report
can too.

**Bar count does not describe an arrangement.** Eight bars in a 300 x 600 column
can sit several ways, and Revit will not infer any of them.
:func:`arrange_column_bars` puts one in each corner and distributes the rest
along the faces by length, which is what a detailer draws.

Coordinates are local to the element: the footing's own origin for a footing,
the column's section centre for a column, ``z`` measured up from the bottom
face. Placing and rotating happens later, once, in the creation layer.
"""

from anongee_toolkit.rc_automation import models

__version__ = "0.1.0"

#: Two lengths within this are the same length. Bars are scheduled in
#: millimetres and a run of "identical" bars can differ by a rounding artefact
#: from intersecting an outline; treating that as a varying run would turn a
#: perfectly good set into thirty separate elements.
UNIFORM_TOLERANCE_MM = 1.0

#: Anything shorter than this is not a bar. A scan line clipping a corner of an
#: outline produces slivers, and a 40 mm bar is a Revit failure, not steel.
MIN_BAR_LENGTH_MM = 100.0

ROLE_FOOTING_LAYER = "FootingLayer"
ROLE_COLUMN_MAIN = "ColumnMain"
ROLE_COLUMN_TIE = "ColumnTie"


# ---------------------------------------------------------------------------
# Geometry helpers — plain lists of tuples, no library
# ---------------------------------------------------------------------------

def bounds(points):
    """``(min_x, min_y, max_x, max_y)`` of a polygon."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def rectangle(length_mm, width_mm, origin=(0.0, 0.0)):
    """A rectangle centred on *origin*, ``length`` along X and ``width`` along Y.

    The fallback outline for a footing type that does not carry one, which is
    most of them: a schedule states Length and Width and means a rectangle.
    """
    half_length = length_mm / 2.0
    half_width = width_mm / 2.0
    x, y = origin
    return [(x - half_length, y - half_width),
            (x + half_length, y - half_width),
            (x + half_length, y + half_width),
            (x - half_length, y + half_width)]


def scan_segments(points, position, axis="X"):
    """Where a line across the polygon at *position* is inside it.

    ``axis="X"`` scans a line running along X at ``y = position`` and returns
    ``[(x_start, x_end), ...]``; ``axis="Y"`` is the same the other way about.

    Returns a list because a polygon need not be convex: an L-shaped or waisted
    pad can put two separate runs of steel on one scan line, and each is a bar.
    Treating only the outermost pair as "the" bar would quietly reinforce the
    void between them.
    """
    along, across = (0, 1) if axis == "X" else (1, 0)
    crossings = []
    count = len(points)
    for index in range(count):
        a = points[index]
        b = points[(index + 1) % count]
        a_across, b_across = a[across], b[across]
        if a_across == b_across:
            continue                       # parallel to the scan line
        low, high = min(a_across, b_across), max(a_across, b_across)
        # Half-open so a vertex shared by two edges is counted once, not twice.
        if not (low <= position < high):
            continue
        ratio = (position - a_across) / float(b_across - a_across)
        crossings.append(a[along] + ratio * (b[along] - a[along]))

    crossings.sort()
    return [(crossings[i], crossings[i + 1])
            for i in range(0, len(crossings) - 1, 2)]


def inset_segment(start, end, inset_mm):
    """Pull both ends of a 1-D span in by *inset_mm*, or ``None`` if nothing left."""
    low, high = (start, end) if start <= end else (end, start)
    low += inset_mm
    high -= inset_mm
    if high - low < MIN_BAR_LENGTH_MM:
        return None
    return low, high


def bar_positions(low, high, count=None, spacing_mm=None):
    """Where the bars of one run sit across the span ``low..high``.

    The three cases are the three layout rules, and they space bars the way
    Revit does so the preview and the model agree:

    * count and spacing -- honour both, centred on the span.
    * count only -- spread evenly, half a gap in from each end.
    * spacing only -- as many as fit at that spacing, centred.
    """
    span = high - low
    if span <= 0:
        return []

    if count and spacing_mm:
        used = (count - 1) * spacing_mm
        start = low + (span - used) / 2.0
        return [start + index * spacing_mm for index in range(count)]

    if count:
        if count == 1:
            return [(low + high) / 2.0]
        gap = span / float(count)
        return [low + gap / 2.0 + index * gap for index in range(count)]

    if spacing_mm:
        fits = int(span // spacing_mm) + 1
        used = (fits - 1) * spacing_mm
        start = low + (span - used) / 2.0
        return [start + index * spacing_mm for index in range(fits)]

    return []


# ---------------------------------------------------------------------------
# What comes out
# ---------------------------------------------------------------------------

class BarSpec(object):
    """One bar: its centreline, in millimetres, local to its host."""

    __slots__ = ("points", "diameter_mm", "bar_type", "shape_code", "role",
                 "label")

    def __init__(self, points, diameter_mm, bar_type="", shape_code=None,
                 role=None, label=""):
        self.points = list(points)
        self.diameter_mm = diameter_mm
        self.bar_type = bar_type
        self.shape_code = shape_code
        self.role = role
        self.label = label

    @property
    def length_mm(self):
        """Centreline length, following every leg."""
        total = 0.0
        for index in range(len(self.points) - 1):
            a, b = self.points[index], self.points[index + 1]
            total += _distance(a, b)
        return total

    def __repr__(self):
        return "<BarSpec {0} d{1:g} {2:.0f}mm>".format(
            self.label or self.role, self.diameter_mm or 0, self.length_mm)


def _distance(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(len(a))) ** 0.5


class BarSetSpec(object):
    """One bar, repeated -- a single Revit element standing for a whole run."""

    __slots__ = ("bar", "count", "spacing_mm", "layout_rule", "array_vector",
                 "array_length_mm")

    def __init__(self, bar, count, spacing_mm, layout_rule, array_vector,
                 array_length_mm):
        self.bar = bar
        self.count = count
        self.spacing_mm = spacing_mm
        self.layout_rule = layout_rule
        self.array_vector = array_vector
        self.array_length_mm = array_length_mm

    def __repr__(self):
        return "<BarSetSpec {0} x {1} @ {2}>".format(
            self.bar.label, self.count, self.spacing_mm)


class LayerPlan(object):
    """Every bar of one scheduled run, and whether it can ship as a set."""

    __slots__ = ("row", "bars", "uniform", "array_vector", "array_length_mm",
                 "notes")

    def __init__(self, row, bars, uniform, array_vector=None,
                 array_length_mm=None, notes=None):
        self.row = row
        self.bars = list(bars)
        self.uniform = uniform
        self.array_vector = array_vector
        self.array_length_mm = array_length_mm
        self.notes = list(notes or ())

    @property
    def count(self):
        return len(self.bars)

    @property
    def element_count(self):
        """How many Revit elements this becomes -- one if it is a set, else N.

        The difference between 2,000 elements and 50,000 at the stated scale,
        which is why uniformity is worth working out rather than assuming.
        """
        return 1 if (self.uniform and self.bars) else len(self.bars)

    def as_set(self):
        """A :class:`BarSetSpec`, or ``None`` when the bars are not identical."""
        if not (self.uniform and self.bars):
            return None
        return BarSetSpec(self.bars[0], len(self.bars),
                          self.row.spacing_mm, self.row.layout_rule(),
                          self.array_vector, self.array_length_mm)

    def __repr__(self):
        return "<LayerPlan {0} bars, {1}>".format(
            self.count, "set" if self.uniform else "individual")


# ---------------------------------------------------------------------------
# Footings
# ---------------------------------------------------------------------------

def outline_for(footing_type, placement=None):
    """The pad's plan shape: its scheduled outline, else its Length x Width."""
    if placement is not None and getattr(placement, "outline", None):
        return list(placement.outline)
    return rectangle(footing_type.length_mm or 0.0, footing_type.width_mm or 0.0)


def layer_elevation(row, rows, thickness_mm, cover_top_mm, cover_bottom_mm):
    """Centreline height of one layer above the pad's bottom face.

    Layers stack outward-in, and the bar below decides where the bar above
    starts: B2 clears the cover, then B1's whole diameter, then half its own.
    Which is why the *other* layer's diameter is looked up rather than assumed
    equal to this one's -- a T20 bottom mat under a T12 second layer would put
    every bar of that layer 4 mm out otherwise.
    """
    index = row.layer_index() or 0
    own = row.diameter_mm or 0.0
    beneath = 0.0
    if index:
        outer = models.LAYER_B1 if row.is_bottom else models.LAYER_T1
        for other in rows:
            if other.layer == outer and other.diameter_mm:
                beneath = other.diameter_mm
                break
        beneath = beneath or own

    if row.is_bottom:
        return cover_bottom_mm + beneath + own / 2.0
    return thickness_mm - cover_top_mm - beneath - own / 2.0


def plan_footing_layer(row, outline, thickness_mm, cover_top_mm,
                       cover_bottom_mm, cover_side_mm, sibling_rows=()):
    """Every bar of one scheduled footing layer.

    Bars run along ``row.direction`` and are arrayed across it. Each bar's
    length comes from intersecting its own scan line with the outline, then
    pulling both ends in by the side cover -- so a pad that is not rectangular
    gets bars that actually fit it, rather than a rectangle's worth of steel
    poking out of the concrete.
    """
    notes = []
    axis = row.direction if row.direction in models.DIRECTIONS else "X"
    across = "Y" if axis == "X" else "X"
    min_x, min_y, max_x, max_y = bounds(outline)

    across_low, across_high = (min_y, max_y) if axis == "X" else (min_x, max_x)
    span = inset_segment(across_low, across_high, cover_side_mm)
    if span is None:
        return LayerPlan(row, [], False, notes=[
            "side cover of {0:g} mm leaves no room to array bars across the "
            "pad".format(cover_side_mm)])

    z = layer_elevation(row, list(sibling_rows) or [row], thickness_mm,
                        cover_top_mm, cover_bottom_mm)
    positions = bar_positions(span[0], span[1], row.count, row.spacing_mm)

    bars = []
    skipped = 0
    for position in positions:
        for start, end in scan_segments(outline, position, axis=axis):
            extent = inset_segment(start, end, cover_side_mm)
            if extent is None:
                skipped += 1
                continue
            if axis == "X":
                points = [(extent[0], position, z), (extent[1], position, z)]
            else:
                points = [(position, extent[0], z), (position, extent[1], z)]
            bars.append(BarSpec(
                points, row.diameter_mm, row.bar_type, row.shape_code,
                ROLE_FOOTING_LAYER,
                "{0} {1}{2}".format(row.type_mark, row.layer, row.direction)))

    if skipped:
        notes.append(
            "{0} bar position(s) fell outside the pad once side cover was "
            "taken off".format(skipped))

    uniform = _lengths_agree(bars)
    if bars and not uniform:
        notes.append(
            "bars vary in length, so this layer is placed as {0} individual "
            "bars rather than one set".format(len(bars)))

    vector = (1.0, 0.0, 0.0) if axis == "X" else (0.0, 1.0, 0.0)
    across_vector = (0.0, 1.0, 0.0) if axis == "X" else (1.0, 0.0, 0.0)
    return LayerPlan(row, bars, uniform, across_vector,
                     span[1] - span[0], notes)


def _lengths_agree(bars):
    if len(bars) < 2:
        return bool(bars)
    lengths = [bar.length_mm for bar in bars]
    return max(lengths) - min(lengths) <= UNIFORM_TOLERANCE_MM


def plan_footing(footing_type, rows, placement=None):
    """Every layer of one footing type, in schedule order."""
    outline = outline_for(footing_type, placement)
    rows = list(rows)
    return [
        plan_footing_layer(
            row, outline,
            footing_type.thickness_mm or 0.0,
            footing_type.cover_top_mm or 0.0,
            footing_type.cover_bottom_mm or 0.0,
            row.end_cover_mm if row.end_cover_mm is not None
            else (footing_type.cover_side_mm or 0.0),
            sibling_rows=rows)
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def arrange_column_bars(count, width_mm, depth_mm, cover_mm, tie_diameter_mm,
                        main_diameter_mm):
    """Where *count* main bars sit in the section, corners first.

    A count on its own does not describe an arrangement and Revit will not
    invent one, so this does what a detailer does: one bar in each corner, then
    the rest shared between the four faces in proportion to their length, so a
    300 x 600 column puts more bars down its long faces than across its short
    ones. Positions are bar centres relative to the section centre.
    """
    inset = cover_mm + tie_diameter_mm + main_diameter_mm / 2.0
    half_width = width_mm / 2.0 - inset
    half_depth = depth_mm / 2.0 - inset
    if count <= 0 or half_width <= 0 or half_depth <= 0:
        return []

    corners = [(-half_width, -half_depth), (half_width, -half_depth),
               (half_width, half_depth), (-half_width, half_depth)]
    if count <= 4:
        return corners[:count]

    remaining = count - 4
    # Two faces run along X and two along Y; share the extras by face length so
    # the spacing comes out even all the way round rather than even per face.
    x_face = 2 * half_width
    y_face = 2 * half_depth
    total = x_face + y_face
    per_x_face = int(round(remaining * (x_face / total) / 2.0)) if total else 0
    per_x_face = max(0, min(per_x_face, remaining // 2))
    per_y_face = (remaining - 2 * per_x_face) // 2
    leftover = remaining - 2 * per_x_face - 2 * per_y_face

    positions = list(corners)
    for index in range(per_x_face):
        offset = -half_width + (index + 1) * (x_face / (per_x_face + 1.0))
        positions.append((offset, -half_depth))
        positions.append((offset, half_depth))
    for index in range(per_y_face):
        offset = -half_depth + (index + 1) * (y_face / (per_y_face + 1.0))
        positions.append((-half_width, offset))
        positions.append((half_width, offset))
    # An odd leftover cannot be shared symmetrically; it goes on a long face,
    # which is where a detailer would put it.
    for index in range(leftover):
        positions.append((0.0, half_depth if index % 2 == 0 else -half_depth))
    return positions[:count]


def plan_column_mains(row, column_type, height_mm, tie_diameter_mm=0.0,
                      base_z=0.0):
    """Straight vertical bars for one main-bar group.

    Laps and starter bars are deliberately absent -- the plan says so, the
    report says so per column, and a bar that stops at the top of the pour is
    honest about being incomplete in a way a guessed lap length would not be.
    """
    positions = arrange_column_bars(
        row.count or 0, column_type.width_mm or 0.0, column_type.depth_mm or 0.0,
        column_type.cover_mm or 0.0, tie_diameter_mm, row.diameter_mm or 0.0)
    return [
        BarSpec([(x, y, base_z), (x, y, base_z + height_mm)],
                row.diameter_mm, row.bar_type, row.shape_code, ROLE_COLUMN_MAIN,
                "{0} main".format(row.type_mark))
        for x, y in positions
    ]


def tie_outline(column_type, tie_diameter_mm, z):
    """The closed link's centreline: the section, inset by cover and half a tie."""
    inset = (column_type.cover_mm or 0.0) + tie_diameter_mm / 2.0
    half_width = (column_type.width_mm or 0.0) / 2.0 - inset
    half_depth = (column_type.depth_mm or 0.0) / 2.0 - inset
    if half_width <= 0 or half_depth <= 0:
        return None
    corners = [(-half_width, -half_depth), (half_width, -half_depth),
               (half_width, half_depth), (-half_width, half_depth)]
    points = [(x, y, z) for x, y in corners]
    points.append(points[0])              # closed link
    return points


def plan_column_ties(row, column_type, height_mm, base_z=0.0):
    """The tie sets for one column: confined ends and a looser middle.

    A single spacing all the way up is not what any code accepts -- IS 13920,
    ACI 318 Ch. 18 and EC8 all want ties closer together over a length at each
    end -- so a row carrying SpacingEnd and ConfinementLength becomes three
    sets, and one without stays the single set it asked for.
    """
    if not row.spacing_mm:
        return []

    def build(start, end, spacing, label):
        span = end - start
        if span <= 0:
            return None
        points = tie_outline(column_type, row.diameter_mm or 0.0, start)
        if points is None:
            return None
        count = max(1, int(span // spacing) + 1)
        bar = BarSpec(points, row.diameter_mm, row.bar_type, row.shape_code,
                      ROLE_COLUMN_TIE,
                      "{0} tie {1}".format(row.type_mark, label))
        return BarSetSpec(bar, count, spacing,
                          models.LAYOUT_NUMBER_WITH_SPACING,
                          (0.0, 0.0, 1.0), span)

    top = base_z + height_mm
    if not row.has_confinement:
        return [s for s in [build(base_z, top, row.spacing_mm, "full")] if s]

    zone = min(row.confinement_length_mm, height_mm / 2.0)
    sets = [
        build(base_z, base_z + zone, row.spacing_end_mm, "bottom"),
        build(base_z + zone, top - zone, row.spacing_mm, "middle"),
        build(top - zone, top, row.spacing_end_mm, "top"),
    ]
    return [s for s in sets if s]

# -*- coding: utf-8 -*-
"""What goes in the project's identity parameters, worked out from the schedule.

The office's schedules key off five fields -- ``ID``, ``ID_LIC``, ``ID_V``,
``ITEM`` and ``LEVEL_V`` -- and a footing that arrives without them is a
footing that is in the model and in none of the drawings. None of those fields
is stated in the workbook: every one is derivable from what is, and this is
where that derivation lives so it can be read, argued with and tested without
opening Revit.

The rules, in one place because they are conventions rather than facts:

``ID``
    The **type** mark. ``F2-C1`` is an instance of ``F2``, and what a
    quantities schedule groups on is the type.
``ID_LIC``
    **L**\\ ocation **I**\\ n **C**\\ ontext: which grid intersection this one is
    at -- ``C-1`` -- so two identical pads can still be told apart. A pad placed
    by coordinate has no grid to name, and falls back to whatever its mark
    carries beyond the type mark.
``ID_V``
    The **variant**: the full mark on a host, and the layer and direction on a
    bar -- ``B1-X``. It is what makes one row of a schedule different from the
    row above it.
``ITEM``
    What the thing *is*, in the form the schedule prints: ``2400x2400x750`` for
    a pad, ``#12-16T@200`` for a run of bars.
``LEVEL_V``
    The level's name as the **model** spells it, not as the workbook does. A
    workbook saying ``Foundation`` against a model saying
    ``00 FOUNDATION LVL.`` has to write the model's, or the schedule sorts into
    two levels that are one level.

Bars additionally carry ``Host Category`` and ``Host Mark``, which are the two
things a rebar schedule cannot show about its host without them.

Pure. No Revit, no workbook reading -- values in, strings out.
"""

__version__ = "0.1.0"

#: What separates a type mark from the rest of an instance mark. Checked in
#: this order, longest-lived convention first.
MARK_SEPARATORS = ("-", "_", ".", " ", "/")


def mark_suffix(mark, type_mark):
    """The part of an instance mark that is not its type mark.

    ``("F2-C1", "F2")`` -> ``"C1"``. A mark that does not start with its type
    mark is returned whole, because a project that marks its pads some other
    way has still told us something and inventing a rule for it would not.
    """
    text = (mark or "").strip()
    prefix = (type_mark or "").strip()
    if not prefix or not text:
        return text
    if text[:len(prefix)].lower() != prefix.lower():
        return text
    rest = text[len(prefix):]
    while rest and rest[0] in MARK_SEPARATORS:
        rest = rest[1:]
    return rest or text


def location_code(mark, type_mark="", grid_x="", grid_y=""):
    """Where this instance is, as a schedule would print it.

    The grid intersection when there is one -- ``C-1`` -- because that is what
    somebody standing on site can find. Otherwise the mark's own suffix, which
    is at least unique.
    """
    grid_x = (grid_x or "").strip()
    grid_y = (grid_y or "").strip()
    if grid_x and grid_y:
        return "{0}-{1}".format(grid_x, grid_y)
    if grid_x or grid_y:
        return grid_x or grid_y
    return mark_suffix(mark, type_mark)


def _dimension(value):
    """``2400.0`` -> ``"2400"``. Nothing at all -> ``"?"``."""
    if value is None:
        return "?"
    return "{0:g}".format(float(value))


def footing_item(footing_type, outline_mm=None):
    """A pad's size, the way a schedule prints it: ``2400x2400x750``.

    An outline pad is measured across its own extent rather than reported as
    the type's rectangle, because the type row describes a shape that pad is
    not.
    """
    if outline_mm:
        xs = [point[0] for point in outline_mm]
        ys = [point[1] for point in outline_mm]
        length, width = max(xs) - min(xs), max(ys) - min(ys)
    else:
        length = getattr(footing_type, "length_mm", None)
        width = getattr(footing_type, "width_mm", None)
    return "{0}x{1}x{2}".format(
        _dimension(length), _dimension(width),
        _dimension(getattr(footing_type, "thickness_mm", None)))


def bar_item(count, bar_type_name, spacing_mm=None):
    """A run of bars as the schedule prints it: ``#12-16T@200``.

    *bar_type_name* is the name of the type in the **model**, not the one the
    workbook used: a workbook saying ``T16`` against a model whose type is
    called ``16T`` has to print the model's, or the schedule and the model
    disagree about what was built.
    """
    name = (bar_type_name or "").strip() or "?"
    parts = []
    if count:
        parts.append("#{0:g}-".format(float(count)))
    parts.append(name)
    if spacing_mm:
        parts.append("@{0:g}".format(float(spacing_mm)))
    return "".join(parts)


def host_values(mark, type_mark, level_name="", item="", grid_x="", grid_y=""):
    """The five identity fields for one footing."""
    return {
        "ID": (type_mark or "").strip(),
        "ID_LIC": location_code(mark, type_mark, grid_x, grid_y),
        "ID_V": (mark or "").strip(),
        "ITEM": item or "",
        "LEVEL_V": level_name or "",
    }


def from_placement(placement, footing_type, level_name="", outline_mm=None):
    """:func:`host_values` for a workbook row, sizes and grids included."""
    return host_values(
        getattr(placement, "mark", ""),
        getattr(placement, "type_mark", ""),
        level_name,
        footing_item(footing_type, outline_mm),
        getattr(placement, "grid_x", ""),
        getattr(placement, "grid_y", ""))


def rebar_values(host, row, bar_type_name, count,
                 host_category="Structural Foundations"):
    """The identity fields for one run of bars, plus what hosts it.

    Built **from the host's own values** rather than re-derived from the
    workbook, so a bar and the pad it sits in can never disagree about which
    level they are on or which grid they are at -- which they could, and did,
    when each worked it out for itself.
    """
    host = host or {}
    layer = (getattr(row, "layer", "") or "").strip()
    direction = (getattr(row, "direction", "") or "").strip()
    variant = "-".join(part for part in (layer, direction) if part)
    return {
        "ID": host.get("ID", ""),
        "ID_LIC": host.get("ID_LIC", ""),
        "ID_V": variant,
        "ITEM": bar_item(count, bar_type_name,
                         getattr(row, "spacing_mm", None)),
        "LEVEL_V": host.get("LEVEL_V", ""),
        "Host Category": host_category or "",
        "Host Mark": host.get("ID_V", ""),
    }

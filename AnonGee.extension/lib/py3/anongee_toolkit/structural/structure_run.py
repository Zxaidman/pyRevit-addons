# -*- coding: utf-8 -*-
"""Build the footings a schedule describes. Phase 1.

Everything a pad needs comes from somewhere different — its shape from the type
row, its position from a grid crossing or a coordinate, its level from a name
that probably is not spelled the way the model spells it — and any one of them
missing means the pad cannot be built. So the whole lot is resolved first, for
every row, and reported together. A run that stops halfway through four hundred
footings because the twelfth names a level nobody mapped is the outcome this is
arranged to avoid.

Nothing here opens a transaction. :func:`plan` reads; :func:`create_one` writes
inside one the caller owns.
"""

from anongee_toolkit.rc_automation import rebar_spec
from anongee_toolkit.structural import footings
from anongee_toolkit.structural import grids as grid_module
from anongee_toolkit.structural import levels as level_module
from anongee_toolkit.structural import rebar_hosts

__version__ = "0.1.0"

STATUS_CREATE = "Create"
STATUS_EXISTS = "Exists"
STATUS_INVALID = "Invalid"


class FootingPlan(object):
    """One pad: where it goes, what shape, and whether it can be built."""

    __slots__ = ("mark", "type_mark", "status", "reason", "position_mm",
                 "outline_mm", "level_id", "level_name", "thickness_mm",
                 "rotation_deg", "offset_mm", "cover_top_mm",
                 "cover_bottom_mm", "cover_side_mm")

    def __init__(self, mark, type_mark, status=STATUS_CREATE, reason="",
                 position_mm=None, outline_mm=None, level_id=None,
                 level_name="", thickness_mm=None, rotation_deg=0.0,
                 offset_mm=0.0, cover_top_mm=None, cover_bottom_mm=None,
                 cover_side_mm=None):
        self.mark = mark
        self.type_mark = type_mark
        self.status = status
        self.reason = reason
        self.position_mm = position_mm
        self.outline_mm = outline_mm
        self.level_id = level_id
        self.level_name = level_name
        self.thickness_mm = thickness_mm
        self.rotation_deg = rotation_deg
        self.offset_mm = offset_mm
        self.cover_top_mm = cover_top_mm
        self.cover_bottom_mm = cover_bottom_mm
        self.cover_side_mm = cover_side_mm

    @property
    def will_create(self):
        return self.status == STATUS_CREATE

    def __repr__(self):
        return "<FootingPlan {0} {1}>".format(self.mark, self.status)


def existing_marks(doc, key_parameter=rebar_hosts.DEFAULT_KEY_PARAMETER):
    """Marks already on a foundation, so a second run does not duplicate them."""
    found = set()
    for element in rebar_hosts.elements_in(doc, rebar_hosts.FOOTING_CATEGORY):
        value = rebar_hosts.parameter_text(element, key_parameter).strip()
        if value:
            found.add(value)
    return found


def plan(doc, workbook, key_parameter=rebar_hosts.DEFAULT_KEY_PARAMETER,
         level_overrides=None):
    """``(plans, notes, blockers)`` — every scheduled pad, resolved. Reads only.

    ``blockers`` are the things wrong with the run as a whole rather than with
    one row: no foundation type in the project, a level nobody can match. They
    are separate because one of them stops everything and a hundred row-level
    problems do not.
    """
    notes = []
    blockers = []

    base_type_id = footings.default_type_id(doc)
    if base_type_id is None:
        blockers.append(
            "This project has no floor types at all, so there is nothing to "
            "make a foundation from. Load a Structural Foundation floor type.")
    elif not any(is_foundation for _n, element_id, is_foundation
                 in footings.foundation_types(doc)
                 if element_id == base_type_id):
        notes.append(
            "No Structural Foundation floor type is loaded — pads will be "
            "created as ordinary floors and filed under Floors.")

    wanted_levels = [row.level for row in workbook.footing_placement]
    # The workbook's own LEVELS sheet, unless the caller passed something else.
    overrides = (level_overrides if level_overrides is not None
                 else getattr(workbook, "level_map", None))
    level_ids, level_notes, level_missing = level_module.build_map(
        doc, wanted_levels, overrides)
    notes.extend(level_notes)
    if level_missing:
        available = level_module.names(doc)
        blockers.append(
            "These level names could not be matched: {0}. The model has: "
            "{1}. Add a LEVELS sheet to the workbook — two columns, the name "
            "the schedule uses and the name this model uses — or rename the "
            "level.".format("; ".join(level_missing), ", ".join(available)))

    doc_grids = grid_module.grids(doc)
    already = existing_marks(doc, key_parameter)

    plans = []
    for placement in workbook.footing_placement:
        plans.append(_plan_one(workbook, placement, level_ids, doc_grids,
                               already))
    return plans, notes, blockers


def _plan_one(workbook, placement, level_ids, doc_grids, already):
    footing_type = workbook.footing_type(placement.type_mark)
    item = FootingPlan(placement.mark, placement.type_mark,
                       level_name=placement.level,
                       rotation_deg=placement.rotation_deg or 0.0,
                       offset_mm=placement.top_offset_mm or 0.0)

    if footing_type is None:
        item.status = STATUS_INVALID
        item.reason = "no footing type {0!r} in the workbook".format(
            placement.type_mark)
        return item

    if placement.mark in already:
        item.status = STATUS_EXISTS
        item.reason = ("a foundation already carries this mark — it is left "
                       "alone rather than duplicated")
        return item

    item.level_id = level_ids.get(placement.level)
    if item.level_id is None:
        item.status = STATUS_INVALID
        item.reason = "level {0!r} could not be matched".format(placement.level)
        return item

    position, note = _position_mm(placement, doc_grids)
    if position is None:
        item.status = STATUS_INVALID
        item.reason = note
        return item
    item.position_mm = position

    # An outline is placed as drawn; everything else is the type's rectangle,
    # which the outline helper centres on the placement point for us.
    item.outline_mm = rebar_spec.outline_for(footing_type, placement)
    item.thickness_mm = footing_type.thickness_mm
    item.cover_top_mm = footing_type.cover_top_mm
    item.cover_bottom_mm = footing_type.cover_bottom_mm
    item.cover_side_mm = footing_type.cover_side_mm
    if not item.thickness_mm:
        item.status = STATUS_INVALID
        item.reason = "the footing type has no thickness"
    return item


def _position_mm(placement, doc_grids):
    """``((x, y), note)`` — where the pad goes, from grids or coordinates."""
    if placement.has_grid_reference:
        point, note = grid_module.intersection_mm(
            doc_grids, placement.grid_x, placement.grid_y)
        if point is None:
            if placement.has_coordinates:
                # The grid reference was preferred and did not resolve; the
                # coordinates are still a perfectly good answer.
                return (placement.x_mm, placement.y_mm), None
            return None, note
        return point, None
    if placement.has_coordinates:
        return (placement.x_mm, placement.y_mm), None
    return None, "no grid reference and no coordinates"


def create_one(doc, item, base_type_id, type_cache=None):
    """Place one pad. **Requires a transaction the caller opened.**

    ``(element, notes)``. Raises only on something that stops the pad existing;
    a note is for something worth saying that did not.
    """
    notes = []
    floor_type, note = footings.resolve_type(
        doc, base_type_id, item.thickness_mm, type_cache)
    if floor_type is None:
        raise ValueError(note or "no floor type")
    if note:
        notes.append(note)

    element, skipped = footings.create(
        doc, item.outline_mm, floor_type.Id, item.level_id,
        item.position_mm, item.rotation_deg, item.offset_mm, item.mark)
    if skipped:
        notes.append("{0} repeated outline point(s) were dropped".format(
            skipped))

    # The cover goes on the element, so the model carries the number rather
    # than only the bars, and anything constrained to cover has something real
    # to follow.
    from anongee_toolkit.structural import rebar_factory
    _applied, created, cover_notes = rebar_factory.set_host_cover(
        doc, element, item.cover_top_mm, item.cover_bottom_mm,
        item.cover_side_mm)
    for value in created:
        notes.append("created a {0:g} mm cover type".format(value))
    notes.extend(cover_notes)
    return element, notes


def summarise(plans):
    counts = {}
    for item in plans:
        counts[item.status] = counts.get(item.status, 0) + 1
    return {
        "footings": len(plans),
        "creating": len([p for p in plans if p.will_create]),
        "by_status": counts,
    }

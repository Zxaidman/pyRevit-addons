# -*- coding: utf-8 -*-
"""Place the FOUNDATIONS: what the drawing shows, else pads under the columns.

Built the same way slabs are: a `Floor.Create` from the outline against a
Structural Foundation floor type ("Foundation Slab"), NOT a family instance.
That keeps footings in the same shape as everything else this tool places -- a
sketched outline the user can edit -- and it sits ON the level with no offset,
where a foundation FAMILY hangs its own depth below the level it is hosted on.

Two sources, in that order of preference:

(1) THE DRAWING. `foundation_plan` reads the outlines off the foundation layer
    and sizes each from the note inside it ("F3_1500MM THK"). This is the only
    source that can produce a RAFT, and the only one that gets the thickness
    from the engineer rather than from a formula.

(2) THE COLUMNS, when the drawing carries no foundation layer. The pad is the
    column footprint grown by a projection all round, turned with the column: a
    400 x 600 column with a 300 projection gets a 1000 x 1200 pad. A round
    column gets a square pad, which is what an isolated pad under a round column
    normally is. Depth follows plan area, since nothing drawn says otherwise.

A type is duplicated per distinct THICKNESS and cached in both cases, exactly as
the slab builder does.

Levels: footings go on the BASE level of the columns, with a zero height offset.
In a multi-storey run only the lowest storey builds them -- a building has one
set of foundations, not one per floor -- which the pushbutton decides.

This module performs Revit writes and must run inside a Transaction.
"""

import math

from System.Collections.Generic import List

from Autodesk.Revit.DB import (BuiltInCategory, BuiltInParameter, CurveLoop,
                               ElementId, FilteredElementCollector, Floor,
                               FloorType, Line, XYZ)

from ..compat import get_element_name, set_element_mark
from .. import config
from .. import fold_plan
from .. import footing_plan
from .. import naming
from .. import type_names

_MM = config.MM_PER_FT

# A footprint whose smaller side exceeds this is a raft/region, not a column.
_MAX_COLUMN_MIN_SIDE_MM = config.DEFAULTS["col_region_max_side_mm"]


def foundation_types(doc):
    """[(label, ElementId)] of floor types in the Structural Foundation category.

    Every floor type is offered when the model has no foundation type at all, so
    a project that has not loaded one can still place pads (Revit will simply
    file them under Floors) -- with the category noted in the label.
    """
    foundation = []
    other = []
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        try:
            name = get_element_name(floor_type)
            category = floor_type.Category
            is_foundation = (category is not None
                             and category.Id.IntegerValue
                             == int(BuiltInCategory.OST_StructuralFoundation))
        except Exception:
            continue
        if is_foundation:
            foundation.append((name, floor_type.Id))
        else:
            other.append(("{0}  (floor, not foundation)".format(name),
                          floor_type.Id))
    foundation.sort(key=lambda pair: pair[0])
    other.sort(key=lambda pair: pair[0])
    return foundation + other


def _set_thickness(floor_type, thickness_mm):
    """Set a floor type's total thickness through its compound structure."""
    try:
        structure = floor_type.GetCompoundStructure()
        if structure is None:
            return False
        structure.SetLayerWidth(structure.GetFirstCoreLayerIndex(),
                                thickness_mm / _MM)
        floor_type.SetCompoundStructure(structure)
        return True
    except Exception:
        return False


def _resolve_type(doc, base_type, thickness_mm, cache):
    """(FloorType, note) of this thickness, duplicated off the base and cached.

    A None type means the name could not be had. That used to fall back to the
    BASE type and say nothing, which cast the pad at whatever depth the picked
    type happened to carry -- a wrong foundation, silently. The caller now skips
    the pad and reports instead.
    """
    if not thickness_mm:
        return base_type, None
    key = int(round(thickness_mm))
    if key in cache:
        return cache[key]
    name = naming.footing_type_name(key)
    floor_type, created, note = type_names.resolve_type(
        base_type, name, lambda: _sibling_types(doc, base_type))
    if created:
        _set_thickness(floor_type, thickness_mm)
    cache[key] = (floor_type, note)
    return floor_type, note


def _sibling_types(doc, base_type):
    """(name, FloorType) for the types in the SAME system family as base_type.

    Foundation Slabs and Floors are both FloorType but different system
    families, and Revit scopes type-name uniqueness to the family. Scanning
    every FloorType could hand a plain FLOOR type back for a pad, filing the
    foundation under the wrong category.
    """
    wanted = _system_family(base_type)
    rows = []
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        if _system_family(floor_type) != wanted:
            continue
        rows.append((get_element_name(floor_type), floor_type))
    return rows


def _system_family(floor_type):
    """The system family a floor type belongs to ("Floor", "Foundation Slab")."""
    try:
        return floor_type.FamilyName
    except Exception:
        return None


def _curve_loop(ring):
    loop = CurveLoop()
    count = len(ring)
    for index in range(count):
        a = ring[index]
        b = ring[(index + 1) % count]
        loop.Append(Line.CreateBound(XYZ(a[0], a[1], 0.0),
                                     XYZ(b[0], b[1], 0.0)))
    return loop


def _zero_offset(instance):
    """Sit the pad ON the level: no height offset, however the type is set up."""
    for builtin in (BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM,
                    BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM):
        try:
            parameter = instance.get_Parameter(builtin)
        except Exception:
            parameter = None
        if parameter is not None and not parameter.IsReadOnly:
            try:
                parameter.Set(0.0)
            except Exception:
                pass


def _offset(instance, offset_mm):
    """Hang the element `offset_mm` BELOW its level (0 sits it on the level).

    A fold's three floors are told apart by nothing but this number, so it is
    set explicitly rather than left to whatever the type carries. A parameter
    that will not take it is reported, not swallowed: an unmoved floor is a
    dropped slab sitting flush with its parent, which looks built and is wrong.
    """
    if not offset_mm:
        _zero_offset(instance)
        return None
    # ONE parameter, not the pair `_zero_offset` writes. The two agree at zero
    # and disagree everywhere else: HEIGHTABOVELEVEL positions the slab's TOP,
    # STRUCTURAL_ELEVATION_AT_BOTTOM its BOTTOM, so falling back to the second
    # would place the element one thickness out and say nothing. Better to
    # report that the offset could not be set than to move it to the wrong one.
    try:
        parameter = instance.get_Parameter(
            BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
    except Exception:
        parameter = None
    if parameter is not None and not parameter.IsReadOnly:
        try:
            parameter.Set(offset_mm / _MM)
            return None
        except Exception:
            pass
    return ("could not offset a floor to {0:.0f} mm: it is flush with its "
            "level".format(offset_mm))


def _place_steps(doc, steps, base_type, level, cache, result):
    """The dropped slabs and their supports, per step region.

    Openings are NOT cut here: the parent outline is placed with the step ring
    as a hole by the outline pass, which already nests rings the way the slab
    builder does. What this adds is the two elements that have no outline of
    their own -- the slab at the bottom of the step, and the vertical concrete
    between the two soffits.
    """
    for step in (steps or []):
        for part, ring, step_holes, thickness, offset in _step_parts(step):
            floor_type, note = _resolve_type(doc, base_type, thickness, cache)
            type_names.record(result, note)
            if floor_type is None:
                result["skipped"].append(
                    "no foundation type for a {0:.0f} mm {1}".format(
                        thickness or 0.0, part))
                continue
            try:
                loops = List[CurveLoop]()
                loops.Add(_curve_loop([(p[0], p[1]) for p in ring]))
                for hole in (step_holes or []):
                    # a fold support is a closed collar (or a pooled group of
                    # collars): the band round the region(s), each region a
                    # hollow cut out of the one slab
                    loops.Add(_curve_loop([(p[0], p[1]) for p in hole]))
                instance = Floor.Create(doc, loops, floor_type.Id, level.Id)
                problem = _offset(instance, offset)
                if problem:
                    result["skipped"].append(problem)
                if step.get("mark"):
                    set_element_mark(instance, "{0}-{1}".format(
                        step["mark"], part.upper()))
                result["created"].append(instance.Id)
            except Exception as creation_error:
                result["errors"].append(str(creation_error))


def _step_parts(step):
    """[(part, ring, holes, thickness_mm, offset_mm)] -- the dropped slab, then
    its support slab(s)."""
    dropped = step.get("dropped") or {}
    parts = []
    if dropped.get("ring"):
        parts.append((step.get("kind") or "step", dropped["ring"], None,
                      dropped.get("thickness_mm"), dropped.get("offset_mm")))
    for support in (step.get("supports") or []):
        parts.append(("support", support["ring"], support.get("holes"),
                      support.get("thickness_mm"), support.get("offset_mm")))
    return parts


def place_footings(doc, sections, base_type_id, level_id, projection_mm=300.0,
                   thickness_mm=600.0, region_max_side_mm=None, outlines=None,
                   steps=None):
    """The foundations, on `level_id` at zero offset.

    `outlines` is what `foundation_plan.plan_foundations` read off the drawing.
    When it holds anything, it IS the foundation layout: each ring placed as
    drawn, at the thickness its own note gave, falling back to `thickness_mm`
    for a ring the drawing left unlabelled.

    With no drawn outlines the layout comes from footing_plan as before: pads
    are the column footprints grown by `projection_mm` on every side,
    OVERLAPPING pads are fused into one combined footing, and each pad's
    thickness follows its plan area around `thickness_mm` (the depth at one
    square metre).

    Returns {"created": [ids], "skipped": [reasons], "errors": [reasons],
    "notes": [...], "merged": n, "source": "drawing"|"columns"}.
    """
    base_type = doc.GetElement(base_type_id)
    level = doc.GetElement(level_id)
    result = {"created": [], "skipped": [], "errors": [], "notes": [],
              "merged": 0, "source": "columns"}
    if base_type is None or level is None:
        raise ValueError("foundation type or level could not be resolved")

    if outlines:
        result["source"] = "drawing"
        plans = _plans_from_outlines(outlines, thickness_mm, result, steps)
    else:
        region_max = (_MAX_COLUMN_MIN_SIDE_MM if region_max_side_mm is None
                      else region_max_side_mm)
        oversized = []
        plans = [(ring, thickness, mark, []) for ring, thickness, mark
                 in footing_plan.plan_pads(sections, projection_mm, thickness_mm,
                                           region_max, oversized)]
        singles = len(footing_plan.pads_for(sections, projection_mm, region_max))
        result["merged"] = max(0, singles - len(plans))
        result["skipped"].extend(oversized)
    cache = {}
    for ring, pad_thickness, mark, holes in plans:
        try:
            floor_type, note = _resolve_type(doc, base_type, pad_thickness, cache)
            type_names.record(result, note)
            if floor_type is None:
                result["skipped"].append(
                    "no foundation type for a {0} mm pad".format(pad_thickness))
                continue
            loops = List[CurveLoop]()
            loops.Add(_curve_loop(ring))
            # The stepped area is a HOLE in the parent: without it the parent
            # and the dropped slab claim the same plan, which Revit takes and
            # sections as two slabs in one place.
            for hole in holes:
                loops.Add(_curve_loop([(p[0], p[1]) for p in hole]))
            instance = Floor.Create(doc, loops, floor_type.Id, level.Id)
            _zero_offset(instance)
            if mark:
                set_element_mark(instance, mark)
            result["created"].append(instance.Id)
        except Exception as creation_error:
            result["errors"].append(str(creation_error))
    _place_steps(doc, steps, base_type, level, cache, result)
    return result


def _plans_from_outlines(outlines, thickness_mm, result, steps=None):
    """[(ring, thickness_mm, mark, holes)] from what the drawing showed.

    A ring the drawing did not size falls back to the dialog's thickness and
    says so, the way an unlabelled slab loop falls back to its floor type.

    `holes` are the areas cut out of THIS outline: its stepped regions, and any
    NESTED outline the drawing lets into it -- the corridor block in the middle
    of a raft is a hole in the raft and a slab of its own. A step whose region
    IS its own outline contributes none: there the outline itself is the thing
    that drops, and cutting it would leave a hole where the slab should be.
    """
    openings = {}
    for step in (steps or []):
        if step.get("opening") is not None:
            openings.setdefault(step["host_index"], []).append(step["opening"])
    plans = []
    for index, plan in enumerate(outlines):
        ring = plan.get("ring")
        if not ring or len(ring) < 3:
            continue
        thickness = plan.get("thickness_mm")
        if not thickness:
            thickness = thickness_mm
            result["notes"].append(
                "{0} outline has no thickness note: cast at {1:.0f} mm".format(
                    plan.get("mark") or "an unnamed", thickness or 0.0))
        holes = list(plan.get("holes") or []) + openings.get(index, [])
        # A step region that IS this outline drops the WHOLE outline: the
        # parent is not placed flat and then stepped, it is placed at the
        # depth. Skipping it here leaves the dropped slab as the only element.
        if _drops_entirely(index, steps):
            continue
        # An opening that reaches the outline's boundary is not a hole -- it
        # DIVIDES the outline. The corridor block's full-width sunk bay is the
        # case: handed over as a hole, its loops share two edges with the
        # block's own and Floor.Create refuses the profile. Each piece is
        # placed on its own, at the outline's thickness and mark.
        pieces = fold_plan.split_profile([(p[0], p[1]) for p in ring], holes)
        if len(pieces) > 1:
            result["notes"].append(
                "{0} outline divided into {1} piece(s): an opening reaches "
                "its boundary".format(plan.get("mark") or "an unnamed",
                                      len(pieces)))
        for piece_ring, piece_holes in pieces:
            plans.append((piece_ring, thickness, plan.get("mark"),
                          piece_holes))
    result["notes"].append(
        "{0} foundation outline(s) read from the drawing".format(len(plans)))
    return plans


def _drops_entirely(index, steps):
    """True when a step says this whole outline is the one that drops."""
    for step in (steps or []):
        if step.get("host_index") == index and step.get("opening") is None:
            return True
    return False

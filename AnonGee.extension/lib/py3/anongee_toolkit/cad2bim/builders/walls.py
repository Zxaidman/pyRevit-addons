# -*- coding: utf-8 -*-
"""Place the WALLS as real `DB.Wall`, from the planner's centrelines.

`wall_plan.plan_walls` (Revit-free) has already turned the wall-layer linework
into centreline segments -- closed thin outlines read as drawn, loose faces
merged across door gaps and paired -- so what is left here is only the Revit
half: one line-based `Wall.Create` per segment, against a wall type duplicated
per distinct width.

Width lives in the TYPE, not on the instance. A wall carries no width
parameter -- the number comes from the type's compound structure -- so the
picked base type is duplicated per distinct (kind, width) and its core layer
resized, exactly as the floor builders duplicate per thickness. A compound
structure can REFUSE a width (a membrane layer is zero-width by definition,
and a curtain or stacked type has no compound structure at all): that failure
goes into `result["errors"]` rather than raising, and the wall still places at
the base type's own width -- a wall standing where the drawing shows one, with
the console naming the wrong width in red, beats a doorwayless gap and a
silent skip.

Heights follow the roadmap convention (classify/layers.py's header):
STRUCTURAL walls rise base-to-top like columns; ARCH walls run base level to
the level above -- in a per-storey run the same pair -- and both stand at the
storey height, unconnected, when no top level exists. `Wall.Create` only takes
an unconnected height, so the top CONSTRAINT is a parameter attached after
placement, the way the column builder attaches FAMILY_TOP_LEVEL_PARAM. The
`structural` flag on Create is the kind: it files the wall under structure for
the analytical model, the same reason footings set FLOOR_PARAM_IS_STRUCTURAL.

This module performs Revit writes and must run inside a Transaction.
"""

import math

from Autodesk.Revit.DB import (BuiltInParameter, FilteredElementCollector,
                               Line, Wall, WallKind, WallType, XYZ)

from ..compat import get_element_name
from .. import config
from .. import naming
from .. import type_names

_MM = config.MM_PER_FT

# Below this a centreline is a sliver Line.CreateBound may refuse outright.
# The shortest REAL wall in the corpus is a 250 mm drawn nib (findings #12),
# so 50 discards nothing the planner emits from a drawing.
_MIN_WALL_LENGTH_MM = 50.0


def wall_types(doc):
    """[(label, ElementId)] of the model's wall types, basic ones first.

    Only a BASIC wall type carries the compound structure the width pass
    resizes. Curtain and stacked types are still offered -- a model may hold
    nothing else -- but labelled, so picking one is a choice, not an accident:
    walls duplicated off one keep whatever width the type has.
    """
    basic = []
    other = []
    for wall_type in FilteredElementCollector(doc).OfClass(WallType).ToElements():
        try:
            name = get_element_name(wall_type)
            is_basic = wall_type.Kind == WallKind.Basic
        except Exception:
            continue
        if is_basic:
            basic.append((name, wall_type.Id))
        else:
            other.append(("{0}  (curtain/stacked, width not settable)".format(
                name), wall_type.Id))
    basic.sort(key=lambda pair: pair[0])
    other.sort(key=lambda pair: pair[0])
    return basic + other


def _set_width(wall_type, width_mm):
    """Resize the type's core layer to `width_mm`. None, or why it refused.

    A single-layer structure resizes its one layer; a build-up resizes the
    CORE (the concrete or masonry between the finishes), which is where a
    drawn wall width belongs. Refusals are sentences, not exceptions: a
    membrane layer is zero-width by definition and SetLayerWidth throws on
    it, and a type with no core has nowhere honest to put the number.
    """
    try:
        structure = wall_type.GetCompoundStructure()
        if structure is None:
            return ("the base type has no compound structure (curtain or "
                    "stacked wall)")
        index = (0 if structure.LayerCount == 1
                 else structure.GetFirstCoreLayerIndex())
        if index < 0:
            return "the base type's compound structure has no core layer"
        structure.SetLayerWidth(index, width_mm / _MM)
        wall_type.SetCompoundStructure(structure)
        return None
    except Exception as width_error:
        return "the compound structure refused the width ({0})".format(
            str(width_error)[:120])


def _resolve_type(doc, base_type, width_mm, cache, kind):
    """(WallType, note, problem) of this kind and width, duplicated + cached.

    `kind` picks the template -- "structural" renders the Naming tab's
    structural-wall row, anything else the arch row -- and is part of the
    cache key, because a 200-wide shear wall and a 200-wide partition are two
    types with two names. `problem` is a width the compound structure refused
    on a type this run CREATED: the caller reports it as an error (once per
    type, like a resolve note) and still places, so the drawing's wall exists
    at the wrong width rather than not at all. A type the model already owns
    is never resized, exactly as everywhere else since v0.68.1.
    """
    key = (kind, int(round(width_mm)))
    if key in cache:
        return cache[key]
    if kind == "structural":
        name = naming.struct_wall_type_name(key[1])
    else:
        name = naming.arch_wall_type_name(key[1])
    wall_type, created, note = type_names.resolve_type(
        base_type, name, lambda: _sibling_types(doc, base_type))
    problem = None
    if created:
        problem = _set_width(wall_type, width_mm)
        if problem:
            problem = ("{0}: {1} -- every {2} mm {3} wall is cast at the "
                       "base type's own width".format(name, problem, key[1],
                                                      kind))
    cache[key] = (wall_type, note, problem)
    return cache[key]


def _sibling_types(doc, base_type):
    """(name, WallType) for the types in the SAME system family as base_type.

    Basic, Curtain and Stacked walls are all WallType but different system
    families, and Revit scopes type-name uniqueness to the family -- the same
    reason the footing builder scopes its scan to Foundation Slabs.
    """
    wanted = _system_family(base_type)
    rows = []
    for wall_type in FilteredElementCollector(doc).OfClass(WallType).ToElements():
        if _system_family(wall_type) != wanted:
            continue
        rows.append((get_element_name(wall_type), wall_type))
    return rows


def _system_family(wall_type):
    """The system family a wall type belongs to ("Basic Wall", "Curtain Wall")."""
    try:
        return wall_type.FamilyName
    except Exception:
        return None


def _attach_top(instance, top_level):
    """Constrain the wall's top to the level above, zeroing both offsets.

    `Wall.Create` only takes an unconnected height, so the constraint is a
    parameter set afterwards -- WALL_HEIGHT_TYPE, the "Top Constraint" the
    Properties palette shows. A wall whose top will not take the level keeps
    the computed height (right size, unconstrained) and says so, because an
    unconstrained wall stops following its level when the storey moves.
    """
    try:
        top = instance.get_Parameter(BuiltInParameter.WALL_HEIGHT_TYPE)
    except Exception:
        top = None
    attached = False
    if top is not None and not top.IsReadOnly:
        try:
            top.Set(top_level.Id)
            attached = True
        except Exception:
            pass
    for builtin in (BuiltInParameter.WALL_TOP_OFFSET,
                    BuiltInParameter.WALL_BASE_OFFSET):
        try:
            offset = instance.get_Parameter(builtin)
        except Exception:
            offset = None
        if offset is not None and not offset.IsReadOnly:
            try:
                offset.Set(0.0)
            except Exception:
                pass
    if not attached:
        return ("could not constrain a wall top to its level: it stands at "
                "the computed height, unconnected")
    return None


def place_walls(doc, segments, base_type_id, base_level_id, top_level_id=None,
                height_mm=None, structural=True):
    """The walls of ONE kind, based on `base_level_id`.

    `segments` is the planner's list for this kind: centreline `start`/`end`
    in internal feet, `width_mm` measured off the drawing. The top constrains
    to `top_level_id` when it sits above the base -- structural walls rise
    base-to-top like columns, arch walls run to the level above -- else the
    wall stands unconnected at `height_mm` (the dialog's storey height).

    Returns {"created": [ids], "skipped": [reasons], "errors": [reasons],
    "notes": [...]} -- the builders' shared shape, one bad segment never
    failing the batch. Runs inside a caller-owned Transaction.
    """
    base_type = doc.GetElement(base_type_id)
    base_level = doc.GetElement(base_level_id)
    top_level = (doc.GetElement(top_level_id) if top_level_id is not None
                 else None)
    if base_type is None or base_level is None:
        raise ValueError("wall type or base level could not be resolved")

    height_ft = None
    if top_level is not None:
        height_ft = top_level.Elevation - base_level.Elevation
    if not height_ft or height_ft <= 0:
        # a top at or below the base constrains nothing: stand unconnected
        top_level = None
        height_ft = config.mm_to_ft(height_mm
                                    or config.DEFAULTS["storey_height_mm"])

    elevation = base_level.Elevation
    cache = {}
    result = {"created": [], "skipped": [], "errors": [], "notes": []}
    for segment in segments:
        try:
            sx, sy = segment["start"][0], segment["start"][1]
            ex, ey = segment["end"][0], segment["end"][1]
            length_mm = math.hypot(ex - sx, ey - sy) * _MM
            if length_mm < _MIN_WALL_LENGTH_MM:
                result["skipped"].append(
                    "tiny wall {0:.0f} mm".format(length_mm))
                continue
            width_mm = segment["width_mm"]
            wall_type, note, width_problem = _resolve_type(
                doc, base_type, width_mm, cache,
                "structural" if structural else "arch")
            type_names.record(result, note)
            if wall_type is None:
                result["skipped"].append(
                    "no wall type for {0:.0f} mm".format(width_mm))
                continue
            if width_problem and width_problem not in result["errors"]:
                result["errors"].append(width_problem)
            line = Line.CreateBound(XYZ(sx, sy, elevation),
                                    XYZ(ex, ey, elevation))
            instance = Wall.Create(doc, line, wall_type.Id, base_level.Id,
                                   height_ft, 0.0, False, structural)
            if top_level is not None:
                problem = _attach_top(instance, top_level)
                if problem and problem not in result["skipped"]:
                    result["skipped"].append(problem)
            result["created"].append(instance.Id)
        except Exception as placement_error:
            result["errors"].append(str(placement_error))
    return result

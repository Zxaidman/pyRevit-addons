# -*- coding: utf-8 -*-
"""Place staircases from dog-leg stair plans (see stair_layout.py).

Stairs use their own StairsEditScope (the Revit stairs sandbox) -- it must run
OUTSIDE any open transaction or transaction group, so the script calls this
after the slab group has committed. One scope per staircase: a failed stair
rolls back alone instead of taking the others with it.

The user's riser/tread/width numbers are pushed onto a DUPLICATED stairs type
(same pattern the slabs use for thickness): max riser height, min tread depth
and min run width are type parameters, and Revit computes the actual stair
from them plus the run's riser counts.
"""

import math

from Autodesk.Revit.DB import (BuiltInParameter, ElementId, ElementTypeGroup,
                               Line, Transaction, XYZ)
from Autodesk.Revit.DB.Architecture import (StairsEditScope, StairsRun,
                                            StairsRunJustification)

from .. import config
from . import txn_failures

_MM = config.MM_PER_FT


def _stairs_type_id(doc, plan):
    """A stairs type carrying the user's numbers: duplicate of the default type
    named by them, reused across stairs of the same run (idempotent)."""
    base_id = doc.GetDefaultElementTypeId(ElementTypeGroup.StairsType)
    if base_id is None or base_id == ElementId.InvalidElementId:
        return None
    base = doc.GetElement(base_id)
    if base is None:
        return None
    name = "cad2bim {0:.0f}R x {1:.0f}T x {2:.0f}W".format(
        plan["riser_mm"], plan["tread_mm"], plan["run_width_mm"])
    from Autodesk.Revit.DB import FilteredElementCollector
    for existing in FilteredElementCollector(doc).OfClass(type(base)):
        try:
            if existing.get_Parameter(
                    BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString() == name:
                return existing.Id
        except Exception:
            continue
    try:
        dup = base.Duplicate(name)
    except Exception:
        return base_id                     # name clash / read-only: default type
    _set_length_param(dup, ("STAIRSTYPE_MAX_RISER_HEIGHT",
                            "STAIRS_ATTR_MAX_RISER_HEIGHT"),
                      plan["riser_mm"] + 0.5)
    _set_length_param(dup, ("STAIRSTYPE_MINIMUM_TREAD_DEPTH",
                            "STAIRS_ATTR_MINIMUM_TREAD_DEPTH",
                            "STAIRSTYPE_MIN_TREAD_DEPTH"), plan["tread_mm"])
    _set_length_param(dup, ("STAIRSTYPE_MINIMUM_RUN_WIDTH",
                            "STAIRS_ATTR_MINIMUM_RUN_WIDTH",
                            "STAIRSTYPE_MIN_RUN_WIDTH"), plan["run_width_mm"])
    return dup.Id


def _set_length_param(element, builtin_names, value_mm):
    """Set the first existing BuiltInParameter from `builtin_names` (the enum
    member names differ across Revit versions; missing ones are skipped)."""
    for name in builtin_names:
        bip = getattr(BuiltInParameter, name, None)
        if bip is None:
            continue
        try:
            param = element.get_Parameter(bip)
            if param is not None and not param.IsReadOnly:
                param.Set(value_mm / _MM)
                return True
        except Exception:
            continue
    return False


def place_stairs(doc, plans, base_level_id, top_level_id):
    """Create one dog-leg stair per plan. Returns created/skipped/errors lists.

    Each stair gets its own StairsEditScope + inner transaction; the landing
    between the two runs is Revit's automatic landing (it fills the 180-degree
    turn between the run ends on its own).
    """
    result = {"created": [], "skipped": [], "errors": []}
    for plan in plans:
        mark = plan.get("mark") or "ST"
        runs = plan.get("runs") or []
        if not runs:
            result["skipped"].append("{0}: no runs in the plan".format(mark))
            continue
        scope = None
        try:
            scope = StairsEditScope(doc, "CAD to BIM: Stair {0}".format(mark))
            stairs_id = scope.Start(base_level_id, top_level_id)
            transaction = Transaction(doc, "Stair runs {0}".format(mark))
            transaction.Start()
            txn_failures.attach_warning_swallower(transaction)
            type_id = _stairs_type_id(doc, plan)
            run_ids = []
            for run in runs:
                sx, sy = run["start"]
                ex, ey = run["end"]
                if math.hypot(ex - sx, ey - sy) <= 1e-6:
                    continue
                line = Line.CreateBound(XYZ(sx, sy, 0.0), XYZ(ex, ey, 0.0))
                stairs_run = StairsRun.CreateStraightRun(
                    doc, stairs_id, line, StairsRunJustification.Center)
                try:
                    stairs_run.ActualRunWidth = run["width_mm"] / _MM
                except Exception:
                    pass
                run_ids.append(stairs_run.Id)
            if len(run_ids) >= 2:
                try:
                    from Autodesk.Revit.DB.Architecture import StairsLanding
                    StairsLanding.CreateAutomaticLanding(doc, run_ids[0],
                                                         run_ids[1])
                except Exception as landing_error:
                    result["skipped"].append("{0}: landing not created ({1})"
                                             .format(mark,
                                                     str(landing_error)[:120]))
            transaction.Commit()
            if type_id is not None:
                change = Transaction(doc, "Stair type {0}".format(mark))
                change.Start()
                try:
                    stairs = doc.GetElement(stairs_id)
                    if stairs is not None:
                        stairs.ChangeTypeId(type_id)
                    change.Commit()
                except Exception:
                    change.RollBack()
            scope.Commit(txn_failures.WarningSwallower())
            result["created"].append(mark)
        except Exception as stair_error:
            try:
                if scope is not None:
                    scope.Cancel()
            except Exception:
                pass
            result["errors"].append("{0}: {1}".format(mark,
                                                      str(stair_error)[:220]))
    return result

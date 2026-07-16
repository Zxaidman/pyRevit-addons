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

# StairsEditScope lives in Autodesk.Revit.DB (NOT .Architecture -- the run/
# landing classes do): https://www.revitapidocs.com/2025/ StairsEditScope Class
from Autodesk.Revit.DB import (BuiltInParameter, CurveLoop, ElementId,
                               ElementTypeGroup, FilteredElementCollector,
                               Line, StairsEditScope, Transaction, XYZ)
from Autodesk.Revit.DB.Architecture import (StairsLanding, StairsRun,
                                            StairsRunJustification, StairsType)

from .. import config
from ..compat import get_element_name
from . import txn_failures

_MM = config.MM_PER_FT


def stairs_types(doc):
    """[(label, ElementId)] of the model's stairs types (for the Build combo)."""
    types = FilteredElementCollector(doc).OfClass(StairsType).ToElements()
    rows = [(get_element_name(st), st.Id) for st in types]
    return sorted(rows, key=lambda pair: pair[0])


def _stairs_type_id(doc, plan, base_type_id=None):
    """A stairs type carrying the user's numbers: duplicate of the PICKED type
    (dialog combo; model default when none), named by the numbers and reused
    across stairs of the same run (idempotent)."""
    base_id = base_type_id
    if base_id is None or base_id == ElementId.InvalidElementId:
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


def place_stairs(doc, plans, base_level_id, top_level_id, base_type_id=None):
    """Create one dog-leg stair per plan. Returns created/skipped/errors lists.

    Each stair gets its own StairsEditScope + inner transaction; the landing
    between the two runs is Revit's automatic landing (it fills the 180-degree
    turn between the run ends on its own), and the ARRIVAL landing at the top
    is a sketched landing from the plan's top_landing ring (relative elevation
    = the full storey; CreateSketchedLanding takes elevations relative to the
    stairs base and rounds them to a riser multiple).

    Per the API contract for CreateStraightRun, a run's location line carries
    its BASE elevation in Z and points in the direction of ascent -- the first
    run starts on the base level, the second starts where the first ended
    (base + first run's risers). The stair type (with the user's numbers,
    duplicated from `base_type_id` -- the dialog's stair type pick) is switched
    BEFORE the runs are created: Revit derives each run's riser/tread counts
    from the type at creation time.
    """
    result = {"created": [], "skipped": [], "errors": []}
    base_level = doc.GetElement(base_level_id)
    top_level = doc.GetElement(top_level_id)
    storey_ft = top_level.Elevation - base_level.Elevation
    for plan in plans:
        mark = plan.get("mark") or "ST"
        runs = plan.get("runs") or []
        if not runs:
            result["skipped"].append("{0}: no runs in the plan".format(mark))
            continue
        risers_total = sum(r.get("risers") or 0 for r in runs) or 1
        scope = None
        transaction = None
        try:
            scope = StairsEditScope(doc, "CAD to BIM: Stair {0}".format(mark))
            stairs_id = scope.Start(base_level_id, top_level_id)
            transaction = Transaction(doc, "Stair runs {0}".format(mark))
            transaction.Start()
            txn_failures.attach_warning_swallower(transaction)
            type_id = _stairs_type_id(doc, plan, base_type_id)
            if type_id is not None:
                stairs_element = doc.GetElement(stairs_id)
                if stairs_element is not None:
                    stairs_element.ChangeTypeId(type_id)
            run_ids = []
            risers_done = 0
            for run in runs:
                sx, sy = run["start"]
                ex, ey = run["end"]
                if math.hypot(ex - sx, ey - sy) <= 1e-6:
                    continue
                z = base_level.Elevation + storey_ft * (
                    float(risers_done) / risers_total)
                line = Line.CreateBound(XYZ(sx, sy, z), XYZ(ex, ey, z))
                stairs_run = StairsRun.CreateStraightRun(
                    doc, stairs_id, line, StairsRunJustification.Center)
                try:
                    stairs_run.ActualRunWidth = run["width_mm"] / _MM
                except Exception:
                    pass
                run_ids.append(stairs_run.Id)
                risers_done += run.get("risers") or 0
            if len(run_ids) >= 2:
                try:
                    StairsLanding.CreateAutomaticLanding(doc, run_ids[0],
                                                         run_ids[1])
                except Exception as landing_error:
                    result["skipped"].append("{0}: landing not created ({1})"
                                             .format(mark,
                                                     str(landing_error)[:120]))
            top_ring = plan.get("top_landing")
            if top_ring and risers_done:
                try:
                    z_top = base_level.Elevation + storey_ft
                    loop = CurveLoop()
                    n = len(top_ring)
                    for i in range(n):
                        ax, ay = top_ring[i]
                        bx, by = top_ring[(i + 1) % n]
                        loop.Append(Line.CreateBound(XYZ(ax, ay, z_top),
                                                     XYZ(bx, by, z_top)))
                    StairsLanding.CreateSketchedLanding(doc, stairs_id, loop,
                                                        storey_ft)
                except Exception as landing_error:
                    result["skipped"].append(
                        "{0}: top landing not created ({1})".format(
                            mark, str(landing_error)[:120]))
            transaction.Commit()
            scope.Commit(txn_failures.WarningSwallower())
            result["created"].append(mark)
        except Exception as stair_error:
            try:
                if (transaction is not None and transaction.HasStarted()
                        and not transaction.HasEnded()):
                    transaction.RollBack()
            except Exception:
                pass
            try:
                if scope is not None:
                    scope.Cancel()
            except Exception:
                pass
            result["errors"].append("{0}: {1}".format(mark,
                                                      str(stair_error)[:220]))
    return result

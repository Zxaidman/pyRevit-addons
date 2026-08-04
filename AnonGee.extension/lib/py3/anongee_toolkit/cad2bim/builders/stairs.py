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
from Autodesk.Revit.DB.Architecture import (Railing, StairsLanding,
                                            StairsRun,
                                            StairsRunJustification,
                                            StairsType)

from .. import config
from ..compat import get_element_name
from .. import naming
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
    waist_mm = float(plan.get("waist_mm") or 0.0)
    name = naming.stair_type_name(plan["riser_mm"], plan["tread_mm"],
                                  plan["run_width_mm"], waist_mm)
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
    if waist_mm > 0:
        _apply_waist(doc, dup, waist_mm)
    return dup.Id


def _apply_waist(doc, stairs_type, waist_mm):
    """Push the WAIST thickness onto the stair's run and landing types.

    The waist lives on the RUN type (monolithic structural depth) and its
    counterpart on the LANDING type; both hang off the stairs type. Each is
    duplicated (idempotent by name) so the model's stock types stay untouched.
    Best effort -- a family-based stair type without these parameters is left
    as it is."""
    for member_names, depth_names in (
            (("STAIRSTYPE_RUN_TYPE",),
             ("STAIRS_RUNTYPE_STRUCTURAL_DEPTH",
              "STAIRSTYPE_RUN_STRUCTURAL_DEPTH")),
            (("STAIRSTYPE_LANDING_TYPE",),
             ("STAIRS_LANDINGTYPE_STRUCTURAL_DEPTH",
              "STAIRS_LANDINGTYPE_TOTAL_THICKNESS"))):
        try:
            member_param = None
            for name in member_names:
                bip = getattr(BuiltInParameter, name, None)
                if bip is not None:
                    member_param = stairs_type.get_Parameter(bip)
                    if member_param is not None:
                        break
            if member_param is None:
                continue
            member = doc.GetElement(member_param.AsElementId())
            if member is None:
                continue
            dup_name = naming.stair_waist_type_name(waist_mm)
            dup = None
            for existing in FilteredElementCollector(doc).OfClass(type(member)):
                try:
                    if existing.get_Parameter(
                            BuiltInParameter.ALL_MODEL_TYPE_NAME
                            ).AsString() == dup_name:
                        dup = existing
                        break
                except Exception:
                    continue
            if dup is None:
                dup = member.Duplicate(dup_name)
                if not _set_length_param(dup, depth_names, waist_mm):
                    lookup = dup.LookupParameter("Structural Depth")
                    if lookup is not None and not lookup.IsReadOnly:
                        lookup.Set(waist_mm / _MM)
            if not member_param.IsReadOnly:
                member_param.Set(dup.Id)
        except Exception:
            continue


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
    created_stairs_ids = []
    for plan in plans:
        mark = plan.get("mark") or "ST"
        runs = plan.get("runs") or []
        spiral = plan.get("spiral")
        if not runs and not spiral:
            result["skipped"].append("{0}: no runs in the plan".format(mark))
            continue
        risers_total = (plan.get("risers_total")
                        or sum(r.get("risers") or 0 for r in runs) or 1)
        winders = {w["after_run"]: w for w in (plan.get("winders") or [])}
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
            if spiral:
                cx, cy = spiral["center"]
                stairs_run = StairsRun.CreateSpiralRun(
                    doc, stairs_id,
                    XYZ(cx, cy, base_level.Elevation),
                    spiral["radius"], spiral["start_angle"],
                    spiral["included_angle"], bool(spiral.get("clockwise")),
                    StairsRunJustification.Center)
                try:
                    stairs_run.ActualRunWidth = spiral["width_mm"] / _MM
                except Exception:
                    pass
                run_ids.append(stairs_run.Id)
                risers_done = risers_total
            for number, run in enumerate(runs):
                sx, sy = run["start"]
                ex, ey = run["end"]
                if math.hypot(ex - sx, ey - sy) <= 1e-6:
                    continue
                z = base_level.Elevation + storey_ft * (
                    float(risers_done) / risers_total)
                stairs_run = None
                if run.get("fanned") and run.get("riser_lines"):
                    # ANGLED risers: a straight run would square them off, so
                    # the flight is SKETCHED from the lines the drawing carries
                    try:
                        stairs_run = _create_fanned_run(doc, stairs_id, z, run)
                    except Exception as fan_error:
                        result["skipped"].append(
                            "{0}: angled risers fell back to a straight run "
                            "({1})".format(mark, str(fan_error)[:120]))
                if stairs_run is None:
                    line = Line.CreateBound(XYZ(sx, sy, z), XYZ(ex, ey, z))
                    stairs_run = StairsRun.CreateStraightRun(
                        doc, stairs_id, line, StairsRunJustification.Center)
                try:
                    stairs_run.ActualRunWidth = run["width_mm"] / _MM
                except Exception:
                    pass
                run_ids.append(stairs_run.Id)
                risers_done += run.get("risers") or 0
                winder = winders.get(number)
                if winder is not None:
                    risers_done += len(winder["riser_lines"]) + 1
            # the turn between consecutive flights: drawn WINDER risers become
            # a sketched run through the corner; otherwise Revit's automatic
            # landing fills it (dog-leg turn, winding-stair corners)
            mid_ring = plan.get("landing")
            bridges = plan.get("bridge_landings") or {}
            for number, (first, second) in enumerate(zip(run_ids,
                                                         run_ids[1:])):
                # a landing that BRIDGES two drawn risers exactly: an automatic
                # landing squares itself to the run ends and leaves a wedge of
                # daylight against a fanned flight's angled outermost riser
                bridge = bridges.get(number)
                if bridge is not None and not spiral:
                    risers_below = sum(r.get("risers") or 0
                                       for r in runs[:number + 1])
                    if _create_sketched_landing(
                            doc, stairs_id, bridge,
                            storey_ft * float(risers_below) / risers_total,
                            base_level.Elevation):
                        continue
                    result["skipped"].append(
                        "{0}: bridge landing did not sketch -- using Revit's "
                        "automatic landing".format(mark))
                winder = winders.get(number) if not spiral else None
                if winder is not None:
                    try:
                        _create_winder_run(doc, stairs_id, base_level,
                                           storey_ft, risers_total,
                                           runs, number, winder)
                        continue
                    except Exception as winder_error:
                        result["skipped"].append(
                            "{0}: winder corner fell back to a landing "
                            "({1})".format(mark, str(winder_error)[:120]))
                if mid_ring and number == 0 and not spiral:
                    risers_below = sum(r.get("risers") or 0
                                       for r in runs[:number + 1])
                    if _create_sketched_landing(
                            doc, stairs_id, mid_ring,
                            storey_ft * float(risers_below) / risers_total,
                            base_level.Elevation):
                        continue
                    result["skipped"].append(
                        "{0}: planned half landing did not sketch -- using "
                        "Revit's automatic landing".format(mark))
                try:
                    StairsLanding.CreateAutomaticLanding(doc, first, second)
                except Exception as landing_error:
                    result["skipped"].append("{0}: landing not created ({1})"
                                             .format(mark,
                                                     str(landing_error)[:120]))
            top_ring = plan.get("top_landing")
            if top_ring and risers_done:
                if not _create_sketched_landing(doc, stairs_id, top_ring,
                                                storey_ft,
                                                base_level.Elevation):
                    result["skipped"].append(
                        "{0}: top landing not created".format(mark))
            transaction.Commit()
            scope.Commit(txn_failures.WarningSwallower())
            created_stairs_ids.append(stairs_id)
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
    _delete_auto_railings(doc, created_stairs_ids, result)
    # the Stairs elements themselves, so the caller can reach their types (the
    # material pass writes onto types, not instances)
    result["created_ids"] = list(created_stairs_ids)
    return result


def _delete_auto_railings(doc, stairs_ids, result):
    """Remove the railings Revit auto-hosts on each new stair (user request:
    no railing after every run). Own transaction, after the edit scopes."""
    if not stairs_ids:
        return
    wanted = set(stairs_ids)
    try:
        doomed = [r.Id for r in FilteredElementCollector(doc).OfClass(Railing)
                  if r.HasHost and r.HostId in wanted]
    except Exception:
        doomed = []
    if not doomed:
        return
    transaction = Transaction(doc, "Remove stair railings")
    try:
        transaction.Start()
        txn_failures.attach_warning_swallower(transaction)
        for railing_id in doomed:
            doc.Delete(railing_id)
        transaction.Commit()
    except Exception:
        try:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        except Exception:
            pass


def _create_sketched_landing(doc, stairs_id, ring, relative_elevation,
                             base_elevation):
    """Sketch one landing from a planned ring. True when Revit accepted it.

    `relative_elevation` is measured from the stairs base, as the API requires
    (it rounds the value to a riser multiple itself); the curve loop is drawn
    at the matching absolute height.
    """
    if not ring or len(ring) < 3:
        return False
    try:
        z = base_elevation + relative_elevation
        loop = CurveLoop()
        count = len(ring)
        for index in range(count):
            ax, ay = ring[index]
            bx, by = ring[(index + 1) % count]
            if math.hypot(bx - ax, by - ay) <= 1e-9:
                continue
            loop.Append(Line.CreateBound(XYZ(ax, ay, z), XYZ(bx, by, z)))
        StairsLanding.CreateSketchedLanding(doc, stairs_id, loop,
                                            relative_elevation)
        return True
    except Exception:
        return False


def _create_fanned_run(doc, stairs_id, bottom_elevation, run):
    """A whole flight of ANGLED risers, sketched from the drawn lines.

    A balanced winder's risers are not perpendicular to the walk line, so
    CreateStraightRun would square them off and lose the turn. The drawn lines
    ARE the sketch: they are the risers, the chains through their two ends are
    the boundaries, and the chain through their midpoints is the stairs path.
    """
    from System.Collections.Generic import List
    from Autodesk.Revit.DB import Curve
    lines = run["riser_lines"]
    if len(lines) < 2:
        return None

    def pt(p):
        return XYZ(p[0], p[1], bottom_elevation)

    def chain(points):
        out = []
        for first, second in zip(points, points[1:]):
            if math.hypot(second[0] - first[0], second[1] - first[1]) > 1e-7:
                out.append(Line.CreateBound(pt(first), pt(second)))
        return out

    left = [a for a, _b in lines]
    right = [b for _a, b in lines]
    mids = [((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0) for a, b in lines]
    boundary = List[Curve]()
    for curve in chain(left) + chain(right):
        boundary.Add(curve)
    risers = List[Curve]()
    for a, b in lines:
        risers.Add(Line.CreateBound(pt(a), pt(b)))
    path = List[Curve]()
    for curve in chain(mids):
        path.Add(curve)
    if boundary.Count < 2 or path.Count < 1:
        return None
    return StairsRun.CreateSketchedRun(doc, stairs_id, bottom_elevation,
                                       boundary, risers, path)


def _create_winder_run(doc, stairs_id, base_level, storey_ft, risers_total,
                       runs, number, winder):
    """A SKETCHED run through a turn whose corner is drawn with ANGLED risers
    (a winder) instead of a flat landing.

    Geometry from the flights themselves: the corner square between run
    `number`'s end and run `number+1`'s start; its outer/inner edge pairs are
    the boundary chains, the drawn fan lines (plus the entry and exit edges)
    are the risers, and the path runs end -> corner -> start along the
    centrelines. Everything is Line-based per the CreateSketchedRun contract.
    """
    from System.Collections.Generic import List
    from Autodesk.Revit.DB import Curve
    run_a = runs[number]
    run_b = runs[number + 1]
    ax0, ay0 = run_a["start"]
    ax1, ay1 = run_a["end"]
    bx0, by0 = run_b["start"]
    bx1, by1 = run_b["end"]
    da = (ax1 - ax0, ay1 - ay0)
    la = math.hypot(*da)
    db = (bx1 - bx0, by1 - by0)
    lb = math.hypot(*db)
    da = (da[0] / la, da[1] / la)
    db = (db[0] / lb, db[1] / lb)
    den = da[0] * db[1] - da[1] * db[0]
    if abs(den) < 0.2:
        raise ValueError("flights are near-parallel; no corner to wind")
    # centreline corner point C: run_a's line meets run_b's line
    t = ((bx0 - ax1) * db[1] - (by0 - ay1) * db[0]) / den
    cx, cy = ax1 + da[0] * t, ay1 + da[1] * t
    half_w = (min(run_a["width_mm"], run_b["width_mm"]) / _MM) / 2.0
    na = (-da[1], da[0])
    nb = (-db[1], db[0])
    turn = da[0] * db[1] - da[1] * db[0]     # +1 left turn, -1 right turn
    sa = 1.0 if turn > 0 else -1.0           # inner side sign along na/nb
    inner_c = _line_x_line((ax1 + na[0] * half_w * sa, ay1 + na[1] * half_w * sa), da,
                           (bx0 + nb[0] * half_w * sa, by0 + nb[1] * half_w * sa), db)
    outer_c = _line_x_line((ax1 - na[0] * half_w * sa, ay1 - na[1] * half_w * sa), da,
                           (bx0 - nb[0] * half_w * sa, by0 - nb[1] * half_w * sa), db)
    z = base_level.Elevation + storey_ft * (
        float(sum(r.get("risers") or 0 for r in runs[:number + 1]))
        / risers_total)

    def pt(p):
        return XYZ(p[0], p[1], z)

    entry_in = (ax1 + na[0] * half_w * sa, ay1 + na[1] * half_w * sa)
    entry_out = (ax1 - na[0] * half_w * sa, ay1 - na[1] * half_w * sa)
    exit_in = (bx0 + nb[0] * half_w * sa, by0 + nb[1] * half_w * sa)
    exit_out = (bx0 - nb[0] * half_w * sa, by0 - nb[1] * half_w * sa)
    boundary = List[Curve]()
    boundary.Add(Line.CreateBound(pt(entry_in), pt(inner_c)))
    boundary.Add(Line.CreateBound(pt(inner_c), pt(exit_in)))
    boundary.Add(Line.CreateBound(pt(entry_out), pt(outer_c)))
    boundary.Add(Line.CreateBound(pt(outer_c), pt(exit_out)))
    risers = List[Curve]()
    risers.Add(Line.CreateBound(pt(entry_in), pt(entry_out)))
    # fan lines ordered by angle around the inner corner, entry -> exit
    ang0 = math.atan2(entry_out[1] - inner_c[1], entry_out[0] - inner_c[0])
    def fan_key(ln):
        (p, q) = ln
        mx, my = (p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0
        return abs((math.atan2(my - inner_c[1], mx - inner_c[0]) - ang0)
                   % (2.0 * math.pi))
    for p, q in sorted(winder["riser_lines"], key=fan_key):
        risers.Add(Line.CreateBound(pt(p), pt(q)))
    risers.Add(Line.CreateBound(pt(exit_in), pt(exit_out)))
    path = List[Curve]()
    path.Add(Line.CreateBound(pt((ax1, ay1)), pt((cx, cy))))
    path.Add(Line.CreateBound(pt((cx, cy)), pt((bx0, by0))))
    StairsRun.CreateSketchedRun(doc, stairs_id, z, boundary, risers, path)


def _line_x_line(p1, d1, p2, d2):
    """Intersection of two infinite lines given point + unit direction."""
    den = d1[0] * d2[1] - d1[1] * d2[0]
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    return (p1[0] + d1[0] * t, p1[1] + d1[1] * t)

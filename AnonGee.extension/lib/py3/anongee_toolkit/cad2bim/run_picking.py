# -*- coding: utf-8 -*-
"""Handing the view back to the user so they can POINT at something.

Revit will not run its own line tool while a modal window is up, and the API
cannot resume a posted command, so "draw the stair outlines" cannot happen while
the dialog is open. The dialog closes, these functions drive a snapped
point-by-point outline picker (creating real detail lines as feedback), and the
dialog is rebuilt afterwards with every setting restored.

`_wrap_selection_filter` builds its ISelectionFilter through the CLR registry:
Python.NET emits a real .NET type from that class body, and an AppDomain refuses
a second one of the same name, so picking twice in one session used to raise
"Duplicate type name within an assembly".
"""

import anongee_clr

from Autodesk.Revit.DB import XYZ, Transaction

from . import config, slab_outlines
from .builders import txn_failures
from .run_console import _say
from .ui_dialogs import _alert


def _uidoc():
    """The active UIDocument. `__revit__` is injected into the pushbutton's own
    namespace by pyRevit, so it is read from the builtins the host set up rather
    than closed over at import time."""
    import builtins
    revit = getattr(builtins, "__revit__", None)
    if revit is None:
        raise RuntimeError("no Revit host: __revit__ is not available")
    return revit.ActiveUIDocument


# Picked stair detail lines chain into an outline when their ends are this close.
_STAIR_LINE_CHAIN_MM = 50.0


class _CurveElementFilter(object):
    """Selection filter: only the lines the user drew (detail or model).

    `__namespace__` is required by Python.NET 3 to build a real derived CLR
    type from the ISelectionFilter interface -- without it the constructor
    routes to the interface cast and raises "takes exactly one argument".
    """

    __namespace__ = "CadToBim"

    def AllowElement(self, element):
        from Autodesk.Revit.DB import CurveElement
        return isinstance(element, CurveElement)

    def AllowReference(self, reference, point):
        return False


def _draw_stair_outlines(doc):
    """Let the user DRAW one closed outline per stair, snapped, in the view.

    Revit will not run its own Detail Line command while a modal window is up,
    and the API cannot resume a posted command, so the outline is drawn here:
    PickPoint uses Revit's real snapping (to the CAD link and to the model), a
    detail line is created after every second point so the shape is visible as
    it grows, and Escape closes the current outline. Escape on the first point
    of a new outline ends the session. Returns [ring, ...] in internal feet.
    """
    from Autodesk.Revit.DB import Line, Transaction, XYZ
    from Autodesk.Revit.UI.Selection import ObjectSnapTypes

    uidoc = _uidoc()
    if uidoc is None:
        return []
    view = uidoc.ActiveView
    snaps = (ObjectSnapTypes.Endpoints | ObjectSnapTypes.Intersections
             | ObjectSnapTypes.Midpoints | ObjectSnapTypes.Nearest
             | ObjectSnapTypes.Perpendicular | ObjectSnapTypes.WorkPlaneGrid)
    rings = []
    while True:
        points = []
        while True:
            prompt = ("Stair outline {0}: click a corner (Esc closes this "
                      "outline)".format(len(rings) + 1) if points else
                      "Stair outline {0}: click the first corner (Esc when "
                      "all stairs are drawn)".format(len(rings) + 1))
            try:
                picked = uidoc.Selection.PickPoint(snaps, prompt)
            except Exception:
                picked = None
            if picked is None:
                break
            points.append(picked)
            if len(points) >= 2:
                transaction = Transaction(doc, "Stair outline")
                try:
                    transaction.Start()
                    txn_failures.attach_warning_swallower(transaction)
                    doc.Create.NewDetailCurve(
                        view, Line.CreateBound(points[-2], points[-1]))
                    transaction.Commit()
                except Exception:
                    if transaction.HasStarted() and not transaction.HasEnded():
                        transaction.RollBack()
        if len(points) < 3:
            break                       # Escape on an empty/short outline: done
        transaction = Transaction(doc, "Stair outline close")
        try:                            # close the loop back to the first point
            transaction.Start()
            txn_failures.attach_warning_swallower(transaction)
            doc.Create.NewDetailCurve(
                view, Line.CreateBound(points[-1], points[0]))
            transaction.Commit()
        except Exception:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        ring = slab_outlines._dedup_ring([(p.X, p.Y) for p in points])
        if len(ring) >= 3:
            rings.append(ring)
            area_m2 = abs(slab_outlines._signed_area(ring)) * 304.8 * 304.8 / 1e6
            _say("Stairs -- outline {0}: {1} corners, {2:.1f} m2".format(
                len(rings), len(ring), area_m2))
    return rings


def _pick_stair_regions():
    """Stair outlines taken from DETAIL LINES already drawn in the view.

    A drag-box is only as accurate as the drag; a detail line snaps to the CAD
    link and to the model, so the boundary is exact and can be any shape. The
    picked curves are chained end-to-end into closed rings (arcs tessellated),
    one ring per stair. Returns [ring, ...] in internal feet.
    """
    from Autodesk.Revit.UI.Selection import ObjectType
    from Autodesk.Revit.DB import Line

    uidoc = _uidoc()
    if uidoc is None:
        return []
    try:
        picked = uidoc.Selection.PickObjects(
            ObjectType.Element, _wrap_selection_filter(),
            "Select the detail lines outlining each stair, then click Finish")
    except Exception:
        return []                       # Escape / cancelled
    pieces = []
    for reference in picked or []:
        element = uidoc.Document.GetElement(reference.ElementId)
        curve = getattr(element, "GeometryCurve", None)
        if curve is None:
            continue
        if isinstance(curve, Line):
            points = [curve.GetEndPoint(0), curve.GetEndPoint(1)]
        else:                           # arc / spline: sample it
            try:
                points = list(curve.Tessellate())
            except Exception:
                points = [curve.GetEndPoint(0), curve.GetEndPoint(1)]
        flat = [(p.X, p.Y) for p in points]
        if len(flat) >= 2:
            pieces.append((flat, points[0].Z))
    if not pieces:
        _say("Stairs -- no detail lines picked.")
        return []

    tol_ft = config.mm_to_ft(_STAIR_LINE_CHAIN_MM)
    rings = []
    for ring, _z in slab_outlines._chain_into_rings(pieces, tol_ft):
        ring = slab_outlines._dedup_ring(ring)
        if len(ring) >= 3:
            rings.append(ring)
    if not rings:
        _say("Stairs -- the picked lines do not close into an outline "
             "(ends must meet within {0:.0f} mm).".format(_STAIR_LINE_CHAIN_MM))
        return []
    for index, ring in enumerate(rings, start=1):
        area_m2 = abs(slab_outlines._signed_area(ring)) * 304.8 * 304.8 / 1e6
        _say("Stairs -- outline {0}: {1} corners, {2:.1f} m2".format(
            index, len(ring), area_m2))
    return rings


def _wrap_selection_filter():
    """The CLR-derived ISelectionFilter instance.

    Built through the registry, so the CLR type is emitted once per Revit
    session however often this is called: the class used to be declared inside
    this function, which meant picking stair outlines a SECOND time in one
    session raised "Duplicate type name within an assembly".
    """
    def build():
        from Autodesk.Revit.UI.Selection import ISelectionFilter

        class _Filter(ISelectionFilter, _CurveElementFilter):
            __namespace__ = "CadToBim"

        return _Filter

    return anongee_clr.get_or_create("CurveSelectionFilter", build)()

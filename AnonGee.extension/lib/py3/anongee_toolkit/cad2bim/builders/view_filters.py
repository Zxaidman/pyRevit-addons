# -*- coding: utf-8 -*-
"""Colour what this run built, so it can be told apart at a glance.

One ParameterFilterElement per element kind, each matching that kind's category
and given its own colour, applied to every OPEN view in the document. Columns
come out one colour, beams another, and a glance at any open view says which
elements this tool placed and what they are.

The filters are made once and reused: a second run finds them by name and only
re-applies the overrides, so repeated runs do not litter the project with
"cad2bim columns 1", "cad2bim columns 2".

A view that cannot take filters -- a schedule, a sheet, a template-controlled
view -- is skipped and counted rather than failing the run. This module performs
Revit writes and must run inside a Transaction.
"""

from Autodesk.Revit.DB import (BuiltInCategory, ElementId,
                               FilteredElementCollector, OverrideGraphicSettings,
                               ParameterFilterElement, Color, View)
try:                                     # 2019+; the older name still works
    from Autodesk.Revit.DB import FillPatternElement, FillPatternTarget
except Exception:                        # pragma: no cover - host-version guard
    FillPatternElement = None
    FillPatternTarget = None

from System.Collections.Generic import List

from ..compat import get_element_name

# kind -> (filter name, category, RGB). LIGHT tints: the fill is what identifies
# an element, and a saturated fill over a whole floor plate is unreadable. Each
# stays distinguishable from the others in greyscale too.
KINDS = (
    ("column", "cad2bim columns", BuiltInCategory.OST_StructuralColumns,
     (170, 200, 240)),
    ("beam", "cad2bim beams", BuiltInCategory.OST_StructuralFraming,
     (245, 190, 175)),
    ("slab", "cad2bim slabs", BuiltInCategory.OST_Floors,
     (185, 225, 200)),
    ("stair", "cad2bim stairs", BuiltInCategory.OST_Stairs,
     (215, 190, 235)),
    ("footing", "cad2bim footings", BuiltInCategory.OST_StructuralFoundation,
     (240, 220, 165)),
    ("grid", "cad2bim grids", BuiltInCategory.OST_Grids,
     (205, 205, 205)),
)

_LINE_WEIGHT = 5          # thick enough to read without hiding the geometry


def _existing(doc, name):
    for element in (FilteredElementCollector(doc)
                    .OfClass(ParameterFilterElement).ToElements()):
        try:
            if get_element_name(element) == name:
                return element
        except Exception:
            continue
    return None


def _solid_fill(doc):
    """The <Solid fill> drafting pattern, or None when the host has none."""
    if FillPatternElement is None:
        return None
    try:
        return FillPatternElement.GetFillPatternElementByName(
            doc, FillPatternTarget.Drafting, "<Solid fill>")
    except Exception:
        return None


def _overrides(doc, rgb, transparency=0, colour_lines=False):
    """The graphic override for one kind.

    `colour_lines` is off by default: colouring the LINES as well as the
    patterns rewrites the drawing's linework, and what the user wants is the
    fill. `transparency` is 0-100, 0 (solid) by default.
    """
    settings = OverrideGraphicSettings()
    colour = Color(rgb[0], rgb[1], rgb[2])
    if colour_lines:
        try:
            settings.SetProjectionLineColor(colour)
            settings.SetCutLineColor(colour)
            settings.SetProjectionLineWeight(_LINE_WEIGHT)
        except Exception:
            pass
    pattern = _solid_fill(doc)
    if pattern is not None:
        try:
            settings.SetSurfaceForegroundPatternId(pattern.Id)
            settings.SetSurfaceForegroundPatternColor(colour)
            settings.SetSurfaceForegroundPatternVisible(True)
            settings.SetCutForegroundPatternId(pattern.Id)
            settings.SetCutForegroundPatternColor(colour)
            settings.SetCutForegroundPatternVisible(True)
        except Exception:
            pass
    try:
        settings.SetSurfaceTransparency(max(0, min(100, int(transparency))))
    except Exception:
        pass
    return settings


def _filter_for(doc, name, category):
    """The named filter, made if it is not in the project yet."""
    found = _existing(doc, name)
    if found is not None:
        return found
    categories = List[ElementId]()
    categories.Add(ElementId(category))
    try:
        return ParameterFilterElement.Create(doc, name, categories)
    except Exception:
        return None


def open_views(uidoc):
    """The views the user currently has open, newest first. [] when unavailable."""
    views = []
    try:
        for ui_view in uidoc.GetOpenUIViews():
            view = uidoc.Document.GetElement(ui_view.ViewId)
            if view is not None:
                views.append(view)
    except Exception:
        return []
    return views


def apply(doc, views, kinds=None, transparency=0, colour_lines=False):
    """Add the cad2bim filters to `views`, each colour-coded.

    Returns {"filters": n_created_or_reused, "views": n_views_coloured,
             "skipped": [reason, ...]}.
    """
    wanted = set(kinds) if kinds else set(k for k, _n, _c, _rgb in KINDS)
    result = {"filters": 0, "views": 0, "skipped": []}
    prepared = []
    for kind, name, category, rgb in KINDS:
        if kind not in wanted:
            continue
        element_filter = _filter_for(doc, name, category)
        if element_filter is None:
            result["skipped"].append("{0}: filter could not be created".format(name))
            continue
        prepared.append((element_filter,
                         _overrides(doc, rgb, transparency, colour_lines),
                         name))
        result["filters"] += 1
    if not prepared:
        return result
    for view in views or []:
        if not _can_take_filters(view):
            continue
        coloured = False
        for element_filter, settings, name in prepared:
            try:
                if not view.IsFilterApplied(element_filter.Id):
                    view.AddFilter(element_filter.Id)
                view.SetFilterOverrides(element_filter.Id, settings)
                coloured = True
            except Exception as filter_error:
                result["skipped"].append("{0} in {1}: {2}".format(
                    name, get_element_name(view), str(filter_error)[:80]))
        if coloured:
            result["views"] += 1
    return result


def _can_take_filters(view):
    """Schedules, sheets and template-driven views cannot hold view filters."""
    if view is None:
        return False
    try:
        if view.IsTemplate:
            return False
        if not isinstance(view, View):
            return False
        if view.ViewTemplateId is not None and view.ViewTemplateId.IntegerValue > 0:
            return False       # the template owns the filters, not the view
        return view.AreGraphicsOverridesAllowed()
    except Exception:
        return False

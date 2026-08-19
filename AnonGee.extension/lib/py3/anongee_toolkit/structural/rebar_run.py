# -*- coding: utf-8 -*-
"""Reinforce a model that is already built. Phase 2, and the first thing that writes.

One workbook, one document, one pass: match each schedule row to the elements it
describes, work out the bars, and place them. Everything it decides is decided
before a transaction opens, so the caller can show the user what is about to
happen and stop.

Three judgements are worth pulling out, because they are where this is easy to
get quietly wrong.

**A host that cannot take reinforcement is skipped, not attempted.** A floor
that was never flagged structural looks like a footing in every view and refuses
every bar. Asking first turns a run of four hundred failures into four hundred
words of explanation.

**A pad that is not the size it was scheduled is skipped too.** Bars are planned
from the schedule's Length and Width and placed against the host's bounding box.
Where those disagree -- because the footing was modelled differently, or because
it is rotated, which makes its box bigger than itself -- the bars would not fit
the concrete. Reporting that beats reinforcing the wrong shape.

**Nothing is placed into a host that already has bars.** Re-running a workbook
must not double the steel, so a host carrying reinforcement is reported and left
alone unless the caller explicitly asks to replace what this tool placed before.
"""

from anongee_toolkit.rc_automation import rebar_spec
from anongee_toolkit.revit.units import mm_to_ft
from anongee_toolkit.structural import rebar_factory
from anongee_toolkit.structural import rebar_hosts
from anongee_toolkit.structural import rebar_types

__version__ = "0.1.0"

#: How far a modelled pad may differ from its scheduled size and still be
#: reinforced from that schedule. Generous enough for a millimetre of rounding,
#: tight enough that a rotated pad's bounding box never passes.
SIZE_TOLERANCE_MM = 25.0

STATUS_CREATE = "Create"
STATUS_SKIP = "Skip"
STATUS_INVALID = "Invalid"
STATUS_EXISTS = "Has rebar"


class HostPlan(object):
    """One element, what it would get, and whether it is going to get it."""

    __slots__ = ("key", "type_mark", "category", "element_id", "status",
                 "reason", "bars", "elements", "layers", "level")

    def __init__(self, key, type_mark, category, element_id=None,
                 status=STATUS_CREATE, reason="", bars=0, elements=0,
                 layers=None, level=""):
        self.key = key
        self.type_mark = type_mark
        self.category = category
        self.element_id = element_id
        self.status = status
        self.reason = reason
        self.bars = bars
        self.elements = elements
        self.layers = layers or []
        self.level = level

    @property
    def will_create(self):
        return self.status == STATUS_CREATE

    def __repr__(self):
        return "<HostPlan {0} {1} {2}>".format(self.key, self.category,
                                               self.status)


def _type_mark_for(key, placement_by_mark):
    """Which schedule type a matched host belongs to.

    The key read off the element is a placement mark when the workbook carries
    placement, and the type mark itself otherwise. One rule covers both the
    project that keys its schedules off ``Mark`` and the one that keys them off
    ``Type Mark``, without asking the user which they meant.
    """
    placement = placement_by_mark.get(key)
    return placement.type_mark if placement is not None else key


def _sized_as_scheduled(element, length_mm, width_mm):
    """``(ok, note)`` -- does the modelled pad match what was scheduled?"""
    if not length_mm or not width_mm:
        return True, ""
    try:
        box = element.get_BoundingBox(None)
        if box is None:
            return True, ""
        from anongee_toolkit.revit.units import ft_to_mm
        measured = sorted([ft_to_mm(box.Max.X - box.Min.X),
                           ft_to_mm(box.Max.Y - box.Min.Y)])
        scheduled = sorted([float(length_mm), float(width_mm)])
    except Exception:
        return True, ""

    for index in (0, 1):
        if abs(measured[index] - scheduled[index]) > SIZE_TOLERANCE_MM:
            return False, (
                "the modelled pad measures {0:.0f} x {1:.0f} mm where the "
                "schedule says {2:.0f} x {3:.0f} — it may be a different type, "
                "or rotated, which makes its bounding box bigger than itself"
                .format(measured[1], measured[0], scheduled[1], scheduled[0]))
    return True, ""


def plan_footings(doc, workbook, key_parameter=rebar_hosts.DEFAULT_KEY_PARAMETER,
                  replace=False):
    """What each existing footing would get. Reads only; opens no transaction."""
    placement_by_mark = dict((p.mark, p) for p in workbook.footing_placement
                             if p.mark)
    index = rebar_hosts.index_by_key(doc, rebar_hosts.FOOTING_CATEGORY,
                                     key_parameter)
    plans = []
    for key in sorted(index):
        for element in index[key]:
            plans.append(_plan_one_footing(
                doc, workbook, key, element, placement_by_mark, replace))
    return plans


def _plan_one_footing(doc, workbook, key, element, placement_by_mark, replace):
    placement = placement_by_mark.get(key)
    type_mark = _type_mark_for(key, placement_by_mark)
    plan = HostPlan(key, type_mark, "Footing", element.Id,
                    level=rebar_hosts.level_name(element))

    footing = workbook.footing_type(type_mark)
    if footing is None:
        plan.status = STATUS_SKIP
        plan.reason = "no footing type {0!r} in the workbook".format(type_mark)
        return plan

    rows = workbook.footing_rebar_for(type_mark)
    if not rows:
        plan.status = STATUS_SKIP
        plan.reason = "no reinforcement scheduled for {0}".format(type_mark)
        return plan

    if not rebar_hosts.is_valid_host(element):
        plan.status = STATUS_INVALID
        plan.reason = rebar_hosts.why_not_a_host(element)
        return plan

    length_mm, width_mm = rebar_spec.scheduled_extent_mm(
        footing, placement)
    sized, note = _sized_as_scheduled(element, length_mm, width_mm)
    if not sized:
        plan.status = STATUS_INVALID
        plan.reason = note
        return plan

    existing = rebar_factory.existing_stamped_rebar(doc, element)
    if _has_any_rebar(doc, element) and not (replace and existing):
        plan.status = STATUS_EXISTS
        plan.reason = ("this footing already carries reinforcement; "
                       "tick Replace to rebuild what this tool placed")
        return plan

    # The placement is passed through so a pad scheduled with an outline is
    # reinforced to that shape rather than to its type's rectangle.
    layers = rebar_spec.plan_footing(footing, rows, placement)
    plan.layers = layers
    plan.bars = sum(layer.count for layer in layers)
    plan.elements = sum(layer.element_count for layer in layers)
    if not plan.bars:
        plan.status = STATUS_SKIP
        plan.reason = "; ".join(n for layer in layers for n in layer.notes) \
            or "no bars fell inside the pad"
    return plan


def _has_any_rebar(doc, element):
    try:
        from Autodesk.Revit.DB.Structure import RebarHostData
        host_data = RebarHostData.GetRebarHostData(element)
        if host_data is None:
            return False
        return len(list(host_data.GetRebarsInHost())) > 0
    except Exception:
        return False


def resolve_bar_types(doc, workbook):
    """``({(diameter, name): ElementId}, missing)`` for every scheduled bar.

    Resolved once for the run rather than per host, because a thousand footings
    of one type ask the same question a thousand times.
    """
    resolved = {}
    missing = []
    rows = list(workbook.footing_rebar) + list(workbook.column_rebar)
    for row in rows:
        key = (row.diameter_mm, (row.bar_type or "").strip())
        if key in resolved or key in missing:
            continue
        element_id = rebar_types.match_bar_type(doc, row.diameter_mm,
                                                row.bar_type)
        if element_id is None:
            missing.append(key)
        else:
            resolved[key] = element_id
    return resolved, missing


def place_footing(doc, plan, workbook, bar_type_ids, view=None, replace=False):
    """Place one footing's reinforcement. **Requires an open transaction.**"""
    result = rebar_factory.PlacementResult()
    element = doc.GetElement(plan.element_id)
    if element is None:
        result.errors.append("{0}: the element is gone".format(plan.key))
        return result

    if replace:
        for rebar_id in rebar_factory.existing_stamped_rebar(doc, element):
            try:
                doc.Delete(rebar_id)
            except Exception as delete_error:
                result.errors.append("{0}: could not remove an earlier bar: "
                                     "{1}".format(plan.key, delete_error))

    centre = rebar_hosts.plan_origin_mm(element)
    bottom = rebar_hosts.bottom_elevation_mm(element)
    if centre is None or bottom is None:
        result.errors.append("{0}: could not measure the element".format(
            plan.key))
        return result

    from anongee_toolkit.structural import rebar_geometry
    origin = rebar_geometry.origin_xyz(centre[0], centre[1], bottom)

    for layer in plan.layers:
        key = (layer.row.diameter_mm, (layer.row.bar_type or "").strip())
        bar_type_id = bar_type_ids.get(key)
        if bar_type_id is None:
            result.skipped.append("{0} {1}: no bar type for {2:g} mm".format(
                plan.key, layer.row.layer, layer.row.diameter_mm or 0))
            continue
        result.merge(rebar_factory.place_layer(
            doc, element, layer, bar_type_id, origin, 0.0, view))
    return result


def summarise(plans):
    """Counts for the log, keyed the way the grid groups them."""
    counts = {}
    for plan in plans:
        counts[plan.status] = counts.get(plan.status, 0) + 1
    creating = [p for p in plans if p.will_create]
    return {
        "hosts": len(plans),
        "creating": len(creating),
        "bars": sum(p.bars for p in creating),
        "elements": sum(p.elements for p in creating),
        "by_status": counts,
    }

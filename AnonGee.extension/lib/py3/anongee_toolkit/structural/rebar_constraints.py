# -*- coding: utf-8 -*-
"""Tie a placed bar to its host's cover, so the host stays in charge.

Geometry alone puts a bar in the right place *once*. A constraint keeps it
there: widen the footing, change its cover, and the reinforcement follows,
because Revit is recomputing the bar against the face rather than remembering
where somebody put it. That is the difference between a model that can be
edited and one that has to be regenerated, and it is the behaviour the "Edit
Constraints" tool on the Rebar ribbon exposes by hand.

Rebar constraints are their own thing, unrelated to dimension or alignment
constraints elsewhere in the model: a ``Rebar`` exposes a handle per end and per
face, and each handle carries a preferred target — usually the host's cover on
some face, optionally with an offset.

**Written without a Revit to try it against.** The shape of this API varies
across releases, so nothing here assumes: every call is probed before it is
made, every failure is counted and reported rather than raised, and
:func:`describe` exists to report what a given Revit build actually offers so
the next pass can stop guessing. Bars are placed in the right position either
way — a constraint that cannot be made costs the automatic updating, not the
reinforcement.
"""

__version__ = "0.1.0"

#: Handle names worth constraining on a footing bar, in the order they matter.
#: A start and an end that follow the cover are what make a bar re-length when
#: the pad changes; the plane keeps it at the right height.
_INTERESTING_HANDLES = ("StartOfBar", "EndOfBar", "RebarPlane", "TopOfBar",
                        "BottomOfBar")


def _manager(rebar):
    """The bar's constraints manager, or ``None`` if this build has none."""
    getter = getattr(rebar, "GetRebarConstraintsManager", None)
    if getter is None:
        return None
    try:
        return getter()
    except Exception:
        return None


def is_available(rebar):
    """Whether this Revit exposes rebar constraints at all."""
    return _manager(rebar) is not None


def handles(rebar):
    """``[(name, handle)]`` for every constrainable handle on the bar."""
    manager = _manager(rebar)
    if manager is None:
        return []
    getter = getattr(manager, "GetAllHandles", None)
    if getter is None:
        return []
    try:
        found = list(getter())
    except Exception:
        return []

    named = []
    for handle in found:
        name = ""
        for attribute in ("GetHandleType", "HandleType"):
            value = getattr(handle, attribute, None)
            try:
                value = value() if callable(value) else value
            except Exception:
                value = None
            if value is not None:
                name = str(value)
                break
        named.append((name, handle))
    return named


def describe(rebar):
    """What this bar's constraints look like, as plain text.

    A diagnostic, not a step in the run. It is here so a report from a real
    model can say which handles exist and what they are tied to, which is the
    only way to replace the guesswork above with something exact.
    """
    manager = _manager(rebar)
    if manager is None:
        return "this Revit build exposes no rebar constraints manager"

    lines = []
    for name, handle in handles(rebar):
        target = "unconstrained"
        getter = getattr(manager, "GetPreferredConstraintForHandle", None)
        if getter is not None:
            try:
                constraint = getter(handle)
                if constraint is not None:
                    to_cover = getattr(constraint, "IsConstraintToCover", None)
                    try:
                        to_cover = (to_cover() if callable(to_cover)
                                    else to_cover)
                    except Exception:
                        to_cover = None
                    target = ("cover" if to_cover else "a face"
                              if to_cover is not None else "set")
            except Exception:
                target = "unreadable"
        lines.append("  {0}: {1}".format(name or "?", target))
    return "\n".join(lines) if lines else "  no handles reported"


def constrain_to_cover(rebar, host, offset_mm=0.0):
    """Point every interesting handle at the host's cover.

    ``(applied, note)``. Never raises: a bar that cannot be constrained is still
    a bar in the right place, and losing the run over a feature that is a
    convenience would be the wrong trade.
    """
    manager = _manager(rebar)
    if manager is None:
        return 0, "no constraints manager on this Revit build"

    setter = getattr(manager, "SetPreferredConstraintForHandle", None)
    if setter is None:
        return 0, "this build exposes no way to set a preferred constraint"

    try:
        from Autodesk.Revit.DB.Structure import RebarConstraint
    except Exception:
        return 0, "RebarConstraint is not importable on this build"

    from System.Collections.Generic import List
    from Autodesk.Revit.DB import Reference
    from anongee_toolkit.revit.units import mm_to_ft

    applied = 0
    failures = []
    for name, handle in handles(rebar):
        if name and not any(word in name for word in _INTERESTING_HANDLES):
            continue
        try:
            targets = List[Reference]()
            targets.Add(Reference(host))
            constraint = RebarConstraint.Create(
                handle, targets, True, mm_to_ft(offset_mm or 0.0))
            setter(handle, constraint)
            applied += 1
        except Exception as constraint_error:
            failures.append("{0} ({1})".format(name or "?", constraint_error))

    if applied:
        return applied, ""
    return 0, ("no handle could be constrained: {0}".format(
        "; ".join(failures[:2])) if failures else "no handles to constrain")


def apply_to_all(rebar_ids, doc, host, offset_mm=0.0):
    """Constrain a run's worth of bars. ``(applied, notes)``.

    The note is collapsed to one line however many bars failed, because four
    hundred copies of the same sentence is not a report.
    """
    applied = 0
    reasons = {}
    for rebar_id in rebar_ids:
        rebar = doc.GetElement(rebar_id)
        if rebar is None:
            continue
        count, note = constrain_to_cover(rebar, host, offset_mm)
        applied += count
        if note:
            reasons[note] = reasons.get(note, 0) + 1

    notes = ["{0} bar(s): {1}".format(count, note)
             for note, count in sorted(reasons.items())]
    return applied, notes

# -*- coding: utf-8 -*-
"""Tie a shape-driven bar to its host's cover, so the host stays in charge.

Geometry alone puts a bar in the right place *once*. A constraint keeps it
there: widen the footing or change its cover and the reinforcement follows,
because Revit recomputes the bar against the face rather than remembering where
something put it. That is what the ribbon's **Edit Constraints** does by hand,
and it is unrelated to the dimension and alignment constraints elsewhere in a
model.

**Shape-driven and free-form rebar have different constraint APIs**, and the
first version of this module used the wrong one. ``RebarConstraint.Create`` is
free-form only; called against a bar from ``CreateFromCurves`` it raises
*"Constrained rebar isn't a free form rebar element"*, which is exactly what a
real run reported. For shape-driven bars Revit offers **candidates** and the
caller picks one:

    manager.GetConstraintCandidatesForHandle(handle, host.Id)
        -> the constraints that handle *could* have
    constraint.IsToCover()
        -> this one follows the cover rather than a bare face
    manager.SetPreferredConstraint(constraint)
        -> take it; the constraint already knows its handle
    manager.ApplyRebarConstraints()
        -> commit

See ``REVIT_API_RESEARCH.md`` in the repository root for where that comes from.

Still defensive, because the shape of this API moves between releases: every
call is reached through a probe and a failure is reported rather than raised. A
bar that cannot be constrained is still a bar in the right place — what is lost
is the automatic updating, which is not worth losing a run over.
"""

__version__ = "0.2.0"

#: Handles worth tying to cover on a footing bar. The ends make a bar re-length
#: when the pad changes; the plane keeps it at the right height.
INTERESTING_HANDLES = ("StartOfBar", "EndOfBar", "RebarPlane", "TopOfBar",
                       "BottomOfBar")


def _call(owner, name, *args):
    """Call ``owner.name(*args)`` if it exists. ``(value, error)``."""
    method = getattr(owner, name, None)
    if method is None:
        return None, "{0} is not available on this build".format(name)
    try:
        return method(*args), None
    except Exception as error:
        return None, "{0}: {1}".format(name, error)


def manager_for(rebar):
    """The bar's constraints manager, or ``None``."""
    value, _error = _call(rebar, "GetRebarConstraintsManager")
    return value


def is_shape_driven(rebar):
    """True for the bars this tool creates. Free-form takes the other API."""
    value, _error = _call(rebar, "IsRebarShapeDriven")
    if value is None:
        # Older builds without the query: a shape-driven accessor is the tell.
        accessor, _accessor_error = _call(rebar, "GetShapeDrivenAccessor")
        return accessor is not None
    return bool(value)


def handles(manager):
    """``[(name, handle)]`` for every handle on the bar."""
    found, _error = _call(manager, "GetAllHandles")
    if not found:
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
    """What this bar's handles are tied to, as plain text.

    A diagnostic rather than a step in a run: a report from a real model is what
    replaces guessing about this API with knowing.
    """
    manager = manager_for(rebar)
    if manager is None:
        return "  this build exposes no rebar constraints manager"

    lines = ["  shape-driven: {0}".format(is_shape_driven(rebar))]
    for name, handle in handles(manager):
        constraint, error = _call(manager, "GetCurrentConstraintOnHandle",
                                  handle)
        if error:
            lines.append("  {0}: {1}".format(name or "?", error))
            continue
        if constraint is None:
            lines.append("  {0}: unconstrained".format(name or "?"))
            continue
        to_cover, _e = _call(constraint, "IsToCover")
        face, _e2 = _call(constraint, "GetRebarConstraintTargetHostFaceType")
        lines.append("  {0}: {1}{2}".format(
            name or "?", "cover" if to_cover else "face",
            " ({0})".format(face) if face is not None else ""))
    return "\n".join(lines)


def constrain_to_cover(rebar, host, handle_names=INTERESTING_HANDLES):
    """Point every interesting handle at the host's cover.

    ``(applied, notes)``. Never raises.
    """
    manager = manager_for(rebar)
    if manager is None:
        return 0, ["no constraints manager on this build"]
    if not is_shape_driven(rebar):
        return 0, ["this bar is free-form; it needs the other constraint API"]

    applied = 0
    notes = []
    for name, handle in handles(manager):
        if name and handle_names and not any(word in name
                                             for word in handle_names):
            continue
        candidates, error = _call(manager, "GetConstraintCandidatesForHandle",
                                  handle, host.Id)
        if error:
            notes.append("{0}: {1}".format(name or "?", error))
            continue
        if not candidates:
            notes.append("{0}: Revit offered no constraint to this host"
                         .format(name or "?"))
            continue

        # Prefer a candidate that follows the cover; a bare face is the
        # fallback, because a bar tied to the face ignores a cover change.
        chosen = None
        for candidate in candidates:
            to_cover, _error = _call(candidate, "IsToCover")
            if to_cover:
                chosen = candidate
                break
        if chosen is None:
            chosen = list(candidates)[0]
            notes.append("{0}: no cover candidate; tied to a face instead"
                         .format(name or "?"))

        _value, set_error = _call(manager, "SetPreferredConstraint", chosen)
        if set_error:
            notes.append("{0}: {1}".format(name or "?", set_error))
            continue
        applied += 1

    if applied:
        _value, apply_error = _call(manager, "ApplyRebarConstraints")
        if apply_error:
            notes.append(apply_error)
    return applied, notes


def set_varying(rebar, varying=True):
    """Turn the ribbon's **Varying Rebar Set** on for this set.

    One flag on the shape-driven accessor, and it only does anything once the
    handles are constrained -- the constraints are what produce the variation,
    which is why this runs after :func:`constrain_to_cover` and not before.

    ``(applied, note)``.
    """
    accessor, error = _call(rebar, "GetShapeDrivenAccessor")
    if accessor is None:
        return False, error or "no shape-driven accessor"
    try:
        accessor.UseRebarConstraintsToProduceVaryingBars = bool(varying)
        return True, ""
    except Exception as set_error:
        return False, "could not set varying bars: {0}".format(set_error)


def array_length_mm(rebar):
    """How long a distribution Revit actually ended up with, in millimetres.

    Read back after constraining, because a set told to fill between two
    constrained ends decides its own length -- and a run that reports what it
    intended rather than what happened is not reporting.
    """
    accessor, _error = _call(rebar, "GetShapeDrivenAccessor")
    if accessor is None:
        return None
    try:
        from anongee_toolkit.revit.units import ft_to_mm
        return ft_to_mm(accessor.ArrayLength)
    except Exception:
        return None


def apply_to_all(rebar_ids, doc, host, varying=False):
    """Constrain a run's worth of bars, optionally as varying sets.

    ``(applied, notes)``. Notes are collapsed to one line per distinct reason,
    because four hundred copies of one sentence is not a report.
    """
    applied = 0
    reasons = {}
    for rebar_id in rebar_ids:
        rebar = doc.GetElement(rebar_id)
        if rebar is None:
            continue
        count, notes = constrain_to_cover(rebar, host)
        applied += count
        if varying and count:
            ok, note = set_varying(rebar, True)
            if not ok and note:
                notes.append(note)
        for note in notes:
            reasons[note] = reasons.get(note, 0) + 1

    return applied, ["{0}x {1}".format(count, note)
                     for note, count in sorted(reasons.items())]

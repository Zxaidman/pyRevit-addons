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
caller picks one::

    manager = rebar.GetRebarConstraintsManager()
    for handle in manager.GetAllHandles():
        candidates = manager.GetConstraintCandidatesForHandle(handle, host.Id)
        to_cover = [c for c in candidates if c.IsToCover()]
        nearest = min(to_cover, key=lambda c: abs(c.GetDistanceToTargetCover()))
        nearest.SetDistanceToTargetCover(0)
        manager.SetPreferredConstraintForHandle(handle, nearest)

Two things in that were wrong here before, and both showed in the model:

**Nearest, not first.** The old code took the first candidate that answered
``IsToCover()``. A pad footing offers a cover candidate for every face, so
"first" is whichever face Revit happened to list first -- and on the gable end
of a non-rectangular pad that is never the sloping edge. The bars were placed
in the right regions and then constrained to the wrong face, so the varying set
had nothing to vary along. ``GetDistanceToTargetCover()`` is what picks the
face a handle is actually *at*, and the comparison has to be on the absolute
value because the distance is signed.

**``SetPreferredConstraintForHandle``, not ``SetPreferredConstraint``.** The
handle-less overload reported success and changed nothing. There is no
``ApplyRebarConstraints()`` to follow it with either -- calling it produced
*"No method matches given arguments"* in a real run and the note went in the
report as though a constraint had failed. Setting the preferred constraint on
the handle *is* the commit.

See ``REVIT_API_RESEARCH.md`` in the repository root for where that comes from.

Still defensive, because the shape of this API moves between releases: every
call is reached through a probe and a failure is reported rather than raised. A
bar that cannot be constrained is still a bar in the right place -- what is
lost is the automatic updating, which is not worth losing a run over.
"""

from anongee_toolkit.revit.units import ft_to_mm
from anongee_toolkit.revit.units import mm_to_ft

__version__ = "0.3.0"

#: Handles worth tying to cover on a footing bar. The ends make a bar re-length
#: when the pad changes; the plane keeps it at the right height.
INTERESTING_HANDLES = ("StartOfBar", "EndOfBar", "RebarPlane", "TopOfBar",
                       "BottomOfBar")

#: A handle this close to the cover it is being tied to is *on* it, and the
#: constraint is set to zero so the model carries a round number rather than a
#: rounding artefact. Anything further is a real offset -- a second layer sits a
#: whole bar diameter off its cover and must keep doing so -- and is left alone.
SNAP_TOLERANCE_MM = 1.0


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


def distance_to_cover_mm(constraint):
    """How far this candidate's handle is from the cover it targets, in mm.

    Signed in Revit and left signed here; callers compare magnitudes. ``None``
    when the build will not say, which makes the candidate unrankable rather
    than nearest -- guessing zero would make every unknown candidate win.
    """
    value, _error = _call(constraint, "GetDistanceToTargetCover")
    if value is None:
        return None
    try:
        return ft_to_mm(value)
    except Exception:
        return None


def target_face(constraint):
    """Which host face a candidate targets, as text, or ``""``.

    Only for the report. It is the line that says whether the varying set on a
    tapered pad found the sloping edge or one of the square ones, which is a
    question no amount of reading the code answers.
    """
    for name in ("GetRebarConstraintTargetHostFaceType",
                 "GetTargetHostFaceType"):
        value, _error = _call(constraint, name)
        if value is not None:
            return str(value)
    return ""


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
        face = target_face(constraint)
        gap = distance_to_cover_mm(constraint)
        lines.append("  {0}: {1}{2}{3}".format(
            name or "?", "cover" if to_cover else "face",
            " ({0})".format(face) if face else "",
            " at {0:+.1f} mm".format(gap) if gap is not None else ""))
    return "\n".join(lines)


def _nearest_cover_candidate(candidates):
    """The cover candidate this handle is actually at. ``(constraint, gap_mm)``.

    Nearest by absolute distance. Taking the first one that answers
    ``IsToCover()`` instead is what tied the gable-end bars of a tapered pad to
    a square face and left the varying set with nothing to vary along.
    """
    best = None
    best_gap = None
    unranked = None
    for candidate in candidates:
        to_cover, _error = _call(candidate, "IsToCover")
        if not to_cover:
            continue
        gap = distance_to_cover_mm(candidate)
        if gap is None:
            if unranked is None:
                unranked = candidate
            continue
        if best_gap is None or abs(gap) < abs(best_gap):
            best, best_gap = candidate, gap
    if best is not None:
        return best, best_gap
    return unranked, None


def constrain_to_cover(rebar, host, handle_names=None,
                       snap_tolerance_mm=SNAP_TOLERANCE_MM):
    """Tie every handle to the cover face it already sits on.

    *handle_names* filters by handle type when the caller wants only some of
    them; the default is all of them, which is what **Edit Constraints ->
    constrain to cover** does by hand and what a footing bar wants.

    ``(applied, notes, faces)``. *faces* is ``[(handle, face, gap_mm)]`` for
    what was tied to what, so the report can show it. Never raises.
    """
    manager = manager_for(rebar)
    if manager is None:
        return 0, ["no constraints manager on this build"], []
    if not is_shape_driven(rebar):
        return 0, ["this bar is free-form; it needs the other constraint API"], []

    applied = 0
    notes = []
    faces = []
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

        chosen, gap = _nearest_cover_candidate(candidates)
        if chosen is None:
            chosen = list(candidates)[0]
            notes.append("{0}: no cover candidate; tied to a face instead"
                         .format(name or "?"))
        elif gap is not None and abs(gap) <= snap_tolerance_mm:
            # Already on the cover: say so exactly, rather than leaving a
            # fraction of a millimetre in a parameter someone has to read.
            _value, _snap_error = _call(chosen, "SetDistanceToTargetCover",
                                        mm_to_ft(0.0))
            gap = 0.0

        if not _prefer(manager, handle, chosen, notes, name):
            continue
        applied += 1
        faces.append((_short(name), target_face(chosen), gap))

    return applied, notes, faces


def _prefer(manager, handle, constraint, notes, name):
    """Make *constraint* the one the handle uses. True when it took.

    ``SetPreferredConstraintForHandle`` is the call that works on every build
    this tool targets. It is marked obsolete from 2025 in favour of the
    handle-less ``SetPreferredConstraint``, so that is tried first -- but only
    accepted if it does not report an error, because on the build a real run
    used it reported none and changed nothing, which is why the newer call is
    verified rather than trusted.
    """
    _value, error = _call(manager, "SetPreferredConstraintForHandle",
                          handle, constraint)
    if error is None:
        return True
    _value, fallback_error = _call(manager, "SetPreferredConstraint",
                                   constraint)
    if fallback_error is None:
        return True
    notes.append("{0}: {1}".format(name or "?", error))
    return False


def _short(handle_name):
    """``RebarConstrainedHandleType.EndOfBar`` -> ``EndOfBar``."""
    text = str(handle_name or "?")
    return text.rsplit(".", 1)[-1]


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
        return ft_to_mm(accessor.ArrayLength)
    except Exception:
        return None


def apply_to_all(rebar_ids, doc, host, varying=False, label=""):
    """Constrain a run's worth of bars, optionally as varying sets.

    ``(applied, notes, faces)``. *notes* are what went wrong, collapsed to one
    line per distinct reason, because four hundred copies of one sentence is not
    a report. *faces* is what went **right** for a varying set: which cover face
    each end found. It is reported separately and always, because "the varying
    set did not vary" and "the varying set was tied to the wrong face" look
    identical in a model and are the same bug.
    """
    applied = 0
    reasons = {}
    faces = []
    for rebar_id in rebar_ids:
        rebar = doc.GetElement(rebar_id)
        if rebar is None:
            continue
        count, notes, found = constrain_to_cover(rebar, host)
        applied += count
        if varying:
            if count:
                ok, note = set_varying(rebar, True)
                if not ok and note:
                    notes.append(note)
            line = "{0}: {1}".format(
                label or "varying set",
                ", ".join("{0}→{1}{2}".format(
                    handle, face or "face",
                    "" if gap is None else " ({0:+.0f} mm)".format(gap))
                    for handle, face, gap in found)
                or "Revit offered no cover face to vary along")
            if line not in faces:
                faces.append(line)
        for note in notes:
            reasons[note] = reasons.get(note, 0) + 1

    return (applied,
            ["{0}x {1}".format(count, note)
             for note, count in sorted(reasons.items())],
            faces)

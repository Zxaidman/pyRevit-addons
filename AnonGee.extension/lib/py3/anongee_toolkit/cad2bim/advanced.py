# -*- coding: utf-8 -*-
"""The ADVANCED tunables: module constants an expert may override, in one place.

The dialog's tabs carry every setting an ordinary run should touch. Underneath
them the geometry modules keep constants that were measured against the fixture
corpus and deliberately NOT put on a tab -- probe reaches, sliver thresholds,
chamfer limits. An advanced user asked for them anyway, so this registry names
each one, says what it does in a sentence a newcomer can read, and rebinds it
at run time. The Advanced window renders the registry; nothing is listed twice.

WHAT QUALIFIES. Only a constant that its consumers read LIVE -- a module-global
looked up at call time. A copy frozen at import (`from .slab_graph import
_COLUMN_RECT_PAD_MM` in slab_outlines) or at function definition
(`min_area_m2=_ORPHAN_MIN_AREA_M2` in slab_labels) would take the override in
this module and never deliver it, which is the exact trap
foundation_plan warns about beside its own tolerances. Excluded on that rule:

  * slab_graph._COLUMN_RECT_PAD_MM -- slab_outlines imports the NAME, so the
    working copy froze at import; making it live is its own change, not this
    one.
  * slab_labels._ORPHAN_MIN_AREA_M2 -- frozen as a def-time default argument,
    and the live knob already exists (the dialog's slab_note_min_area_m2,
    which run_builders passes explicitly).
  * builders/beams._MIN_BEAM_LENGTH_MM and the builders' other constants --
    builders/ imports Revit at module level, so this Revit-free module cannot
    import them to rebind, and no offline test could prove the wiring.

The dialog-owned tolerances (slab_graph's _SNAP_MM group, foundation_plan's
_MIN_AREA_M2, ...) are equally deliberately absent: they have controls, and a
second path to the same attribute is a fight over who wrote last.

Overrides persist in the preferences file under "advanced" and ride the
explicit settings file too; the pushbutton applies them before any planning
runs, because storey detection is already a consumer.

Revit-free, so the registry's liveness -- every attribute exists and equals its
registered default until overridden -- is provable by unit test. That test is
also the drift alarm: change a constant in its module and the registry (and
this file's measured story) must move with it.
"""

from collections import namedtuple

from . import floor_plans, fold_plan, footing_plan, prefs, slab_graph

Tunable = namedtuple("Tunable",
                     "key module attribute unit default label effect")

_MODULES = {"floor_plans": floor_plans, "fold_plan": fold_plan,
            "footing_plan": footing_plan, "slab_graph": slab_graph}

# One row per tunable. `effect` is ONE plain sentence: what moves when this
# number does, in the drawing's terms, not the code's.
REGISTRY = (
    # --- fold / sunk steps --------------------------------------------------
    Tunable("fold_probe_mm", "fold_plan", "_PROBE_MM", "mm", 10.0,
            "Step parent probe",
            "How far past a step region's edge to look for the concrete it "
            "steps down from; wider than the neighbour is not subtler, just "
            "wrong."),
    Tunable("fold_same_area_ratio", "fold_plan", "_SAME_AREA", "ratio", 0.01,
            "Same-outline area tolerance",
            "A step region whose area matches its host outline within this "
            "fraction IS the host, so the whole outline drops instead of "
            "being cut."),

    # --- column-derived pads ------------------------------------------------
    Tunable("pad_depth_step_mm", "footing_plan", "_DEPTH_STEP_MM", "mm", 50.0,
            "Pad depth rounding",
            "A derived pad thickness is rounded to this casting step, not to "
            "the millimetre."),
    Tunable("pad_depth_min_factor", "footing_plan", "_DEPTH_MIN_FACTOR",
            "x nominal", 0.5, "Thinnest pad factor",
            "A derived pad is never thinner than the nominal depth times "
            "this."),
    Tunable("pad_depth_max_factor", "footing_plan", "_DEPTH_MAX_FACTOR",
            "x nominal", 2.0, "Thickest pad factor",
            "A derived pad is never thicker than the nominal depth times "
            "this."),

    # --- the slab face graph ------------------------------------------------
    Tunable("beam_heal_mm", "slab_graph", "_HEAL_MM", "mm", 600.0,
            "Beam-end heal reach",
            "A beam end is extended up to this far to meet the junction it "
            "was drawn short of."),
    Tunable("slab_min_face_area_m2", "slab_graph", "_MIN_FACE_AREA_M2", "m2",
            1.0, "Smallest slab bay",
            "A bounded face smaller than this is a junction sliver, not a "
            "slab bay."),
    Tunable("arc_chords", "slab_graph", "_ARC_CHORDS", "chords", 16,
            "Arc tessellation",
            "How many chords a boundary arc is sampled into for ring "
            "geometry; the placed edge stays a true arc."),
    Tunable("chamfer_max_mm", "slab_graph", "_CHAMFER_MAX_MM", "mm", 150.0,
            "False-chamfer stub limit",
            "A boundary stub shorter than this may be a corner welded across "
            "two members, and is squared back off."),
    Tunable("chamfer_parallel", "slab_graph", "_CHAMFER_PARALLEL",
            "sin(angle)", 0.17, "Chamfer parallel tolerance",
            "A stub lying along a real edge within this much (about ten "
            "degrees) reads as part of that edge, not a chamfer to square "
            "off."),
    Tunable("min_beam_fraction", "slab_graph", "_MIN_BEAM_FRACTION",
            "fraction", 0.35, "Least beam boundary",
            "A face with less than this fraction of its boundary on beam "
            "edges is a gap between members, not a slab bay."),
    Tunable("max_body_coverage", "slab_graph", "_MAX_BODY_COVERAGE",
            "fraction", 0.5, "Most member coverage",
            "A face covered more than this much by member bodies is the "
            "inside of a member, not a bay to floor."),
    Tunable("coverage_step_mm", "slab_graph", "_COVERAGE_STEP_MM", "mm",
            150.0, "Coverage sample pitch",
            "The sampling grid for the member-coverage estimate; finer is "
            "slower and steadier."),
    Tunable("joint_tol_mm", "slab_graph", "_JOINT_TOL_MM", "mm", 2.0,
            "Drawn-joint tolerance",
            "Endpoints this close are literally the same drawn point, welded "
            "before any healing runs."),
    Tunable("graph_cell_mm", "slab_graph", "_GRAPH_CELL_MM", "mm", 3000.0,
            "Graph bucket size",
            "The spatial bucket for the graph passes; it trades speed, and "
            "must stay larger than the heal reach or distant pairs are "
            "missed."),

    # --- multi-storey plan detection ----------------------------------------
    Tunable("plan_min_region_m2", "floor_plans", "_MIN_REGION_M2", "m2", 4.0,
            "Smallest floor plan",
            "A boundary region smaller than this is a detail box, not a "
            "floor plan of its own."),
    Tunable("origin_marker_max_mm", "floor_plans", "_ORIGIN_MAX_MM", "mm",
            2000.0, "Largest origin marker",
            "An origin marker wider than this is linework, not the "
            "point-like mark each storey aligns on."),
    Tunable("plan_min_coverage", "floor_plans", "_MIN_COVERAGE", "fraction",
            0.5, "Least boundary coverage",
            "Boundary boxes must enclose at least this fraction of the "
            "drawing before it splits into storeys at all."),
    Tunable("elevation_mm_cutoff", "floor_plans", "_ELEV_MM_CUTOFF", "mm",
            100.0, "Metres-or-millimetres cutoff",
            "A plan-title elevation at or above this number reads as "
            "millimetres; below it, metres."),
)

_BY_KEY = dict((entry.key, entry) for entry in REGISTRY)

_problems = []


def problems():
    """Overrides that could not be used, as ["key: why", ...]."""
    return list(_problems)


def _coerced(entry, value):
    """`value` as the entry's own numeric type, or None when it cannot be.

    The type is the DEFAULT's type: a chord count stays a whole number, a
    tolerance stays a float. Text from a settings file coerces the same way a
    dialog box does.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if isinstance(entry.default, int):
        return int(round(number))
    return number


def apply(overrides):
    """Rebind every registered constant: the override where one is given,
    the registered default everywhere else.

    Starting every attribute from its default is what makes this idempotent --
    two runs with different overrides never inherit each other -- and what
    makes `reset()` a one-liner. An override that does not read as a number
    keeps the default and says so through `problems()`; a wrong number here
    fails quietly downstream, so a non-number must not.
    """
    global _problems
    _problems = []
    overrides = overrides or {}
    for entry in REGISTRY:
        value = entry.default
        if entry.key in overrides:
            coerced = _coerced(entry, overrides[entry.key])
            if coerced is None:
                _problems.append("{0}: {1!r} is not a number -- using {2}"
                                 .format(entry.key, overrides[entry.key],
                                         entry.default))
            else:
                value = coerced
        setattr(_MODULES[entry.module], entry.attribute, value)


def reset():
    """Restore every registered constant to its measured default."""
    apply({})


def effective():
    """{key: the value its module holds right now} -- read, never cached.

    On an untouched session this equals `defaults()`, and the test that pins
    that equality is the registry's liveness check: an attribute that has
    drifted from its registration, or vanished, fails it by name.
    """
    return dict((entry.key,
                 getattr(_MODULES[entry.module], entry.attribute))
                for entry in REGISTRY)


def defaults():
    """{key: registered default}."""
    return dict((entry.key, entry.default) for entry in REGISTRY)


def load():
    """The saved overrides from the preferences file: known keys only.

    Values come back as saved; `apply` is the one place that judges them, so
    a hand-edited file misbehaves in exactly one reported way.
    """
    saved = prefs.load().get("advanced") or {}
    if not isinstance(saved, dict):
        return {}
    return dict((key, value) for key, value in saved.items()
                if key in _BY_KEY)


def save(values):
    """Remember these overrides for the next Revit session.

    Only known keys that read as numbers AND differ from their default are
    kept -- a file of defaults is the same as no file, and deleting it must
    stay a way to get the defaults back. Returns what was stored.
    """
    keep = {}
    for key, value in (values or {}).items():
        entry = _BY_KEY.get(key)
        if entry is None:
            continue
        coerced = _coerced(entry, value)
        if coerced is None or coerced == entry.default:
            continue
        keep[key] = coerced
    prefs.update({"advanced": keep})
    return keep

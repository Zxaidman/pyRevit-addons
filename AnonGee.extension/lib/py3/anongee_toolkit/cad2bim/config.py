# -*- coding: utf-8 -*-
"""Central tunables for cad2bim -- the single place hard-coded limits and
tolerances live, so they can be reviewed and overridden from the UI.

All values are millimetres (or degrees) unless noted. Pure geometric epsilons
that are NOT user knobs (collinearity ~1e-4 ft, zero-length guards ~1e-12) stay
in shapes.py on purpose -- they are numerical stability constants, not settings.

The UI "Units & Tolerances" tab reads DEFAULTS, lets the user edit them, and
passes the edited dict back through build_* so a run can be tuned without code
changes.
"""

MM_PER_FT = 304.8


def mm_to_ft(mm):
    return float(mm) / MM_PER_FT


# The full set of user-tunable knobs, grouped by stage. Keys are stable; the UI
# and the build pipeline both reference them by name.
DEFAULTS = {
    # --- acceptance limits (mm) ---------------------------------------------
    "beam_width_min_mm": 150,
    "beam_width_max_mm": 1000,
    "col_b_min_mm": 150,
    "col_b_max_mm": 1500,
    "col_h_min_mm": 150,
    "col_h_max_mm": 20000,

    # --- snapping & matching (mm) -------------------------------------------
    "snap_tol_mm": 60.0,          # snap a measured size to a standard within this
    "mark_radius_mm": 1300.0,     # a size label this close to a member sizes it
                                  # (labels sit offset from the column, ~1.1 m)
    "compare_tol_mm": 300.0,      # Revit-vs-DXF "same member" match radius
    "grid_snap_mm": 300.0,        # snap a text-corrected column centre to a grid line

    # --- columns ------------------------------------------------------------
    "col_region_max_side_mm": 1500.0,  # min side above this = lift/stair, skipped
    "circle_min_dia_mm": 150.0,
    "circle_max_dia_mm": 2000.0,

    # --- beams (parallel-line pairing + arc handling) -----------------------
    "pair_min_width_mm": 80.0,
    "pair_max_width_mm": 700.0,
    "pair_min_overlap_mm": 150.0,
    "parallel_angle_deg": 3.0,
    "junction_tol_mm": 200.0,     # arc centred this close to a round column = junction
    "concentric_tol_mm": 60.0,    # two arcs sharing a centre this closely = concentric

    # --- staircase (generic dog-leg from the dialog's Staircase tab, mm) -----
    "stair_riser_mm": 150.0,      # target MAX riser height; count = storey / this
    "stair_tread_mm": 300.0,      # tread depth (the fixtures' riser spacing)
    "stair_run_width_mm": 1250.0, # width of each run
    "stair_landing_mm": 0.0,      # landing depth along the runs; 0 = run width
    "stair_waist_mm": 200.0,      # waist (structural depth) of runs + landings

    # --- multi-storey (several floor plans in ONE dxf) ----------------------
    "storey_height_mm": 3000.0,   # level spacing when the model has no level yet
}


def merged(overrides):
    """Return DEFAULTS updated with any provided overrides (None-safe)."""
    out = dict(DEFAULTS)
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                out[key] = value
    return out

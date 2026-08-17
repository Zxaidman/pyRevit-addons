# -*- coding: utf-8 -*-
"""Central tunables for cad2bim -- the single place hard-coded limits and
tolerances live, so they can be reviewed and overridden from the UI.

All values are millimetres (or degrees) unless noted. Pure geometric epsilons
that are NOT user knobs (collinearity ~1e-4 ft, zero-length guards ~1e-12) stay
in shapes.py on purpose -- they are numerical stability constants, not settings.

The UI reads DEFAULTS (most rows sit on its Tolerances tab, the rest beside
the element they tune), lets the user edit them, and passes the edited dict
back through build_* so a run can be tuned without code changes.
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

    # --- snapping & matching (mm; the Tolerances tab's GENERAL group, except
    #     compare_tol_mm, which sits with the export on Output & Graphics) ----
    "snap_tol_mm": 60.0,          # snap a measured size to a standard within this
    "mark_radius_mm": 1300.0,     # a size label this close to a member sizes it
                                  # (labels sit offset from the column, ~1.1 m)
    "compare_tol_mm": 300.0,      # Revit-vs-DXF "same member" match radius
    "grid_snap_mm": 300.0,        # snap a text-corrected column centre to a grid line

    # --- columns ------------------------------------------------------------
    "col_region_max_side_mm": 1500.0,  # min side above this = lift/stair, skipped
    "circle_min_dia_mm": 150.0,
    "circle_max_dia_mm": 2000.0,

    # --- beams (parallel-line pairing + arc handling; Tolerances tab) -------
    "pair_min_width_mm": 80.0,
    "pair_max_width_mm": 700.0,
    "pair_min_overlap_mm": 150.0,
    "parallel_angle_deg": 3.0,
    "junction_tol_mm": 200.0,     # arc centred this close to a round column = junction
    "concentric_tol_mm": 60.0,    # two arcs sharing a centre this closely = concentric

    # --- staircase (generic dog-leg from the Build > Staircase sub-tab, mm) --
    "stair_riser_mm": 150.0,      # target MAX riser height; count = storey / this
    "stair_tread_mm": 300.0,      # tread depth (the fixtures' riser spacing)
    "stair_run_width_mm": 1250.0, # width of each run
    "stair_landing_mm": 0.0,      # landing depth along the runs; 0 = run width
    "stair_waist_mm": 200.0,      # waist (structural depth) of runs + landings

    # --- multi-storey (several floor plans in ONE dxf) ----------------------
    "storey_height_mm": 3000.0,   # level spacing when the model has no level yet

    # --- slab outline tolerances (exposed on the Tolerances tab) ------------
    "slab_snap_mm": 50.0,         # two boundary points this close are one node
    "slab_heal_mm": 350.0,        # close a junction gap up to this far
    "slab_chain_mm": 150.0,       # loose slab-edge lines chain within this
    "slab_min_width_mm": 500.0,   # a face slimmer than this (2A/P) is a member
    "slab_min_step_mm": 20.0,     # a boundary jog below this is noise, not a step
    "slab_note_min_area_m2": 1.0, # smallest bay recovered for a thickness note whose
                                  # outline was never drawn (test10's roof)

    # --- combined columns (Tolerances tab) ----------------------------------
    "face_label_reach_mm": 900.0, # how far outside a member its size label may sit
    "face_size_tol_mm": 60.0,     # drawn vs labelled dimension of a recovered face

    # --- standard sizes (Tolerances tab; a drawn size within snap_tol_mm of one
    # of these is rounded onto it, so a 298 wide beam reads as the 300 it is).
    # Shipped with the common RC sizes; the tab remembers whatever is typed.
    "standard_columns": ("230x230, 230x300, 230x450, 300x300, 300x450, "
                         "300x600, 400x400, 400x600, 450x600, 600x600"),
    "standard_beam_widths": "200, 230, 250, 300, 350, 400, 450",

    # --- foundations (Build > Foundation sub-tab) ---------------------------
    "footing_projection_mm": 300.0,   # MINIMUM reach past the column, every side
    "footing_thickness_mm": 600.0,    # depth at 1 m2; a pad scales from its area
    "max_step_mm": 3000.0,            # a fold/sunk step deeper than this is a
                                      # storey, not a step, and is refused
    "foundation_min_area_m2": 0.25,   # smallest linework face that is an outline
                                      # (a pile cap is small; a sliver is smaller)

    # --- view filters (Output & Graphics tab) -------------------------------
    "filter_transparency": 0,     # 0 = solid fill; the fill is what identifies

    # --- staircase tolerances (exposed on the Tolerances tab) ---------------
    "stair_cluster_mm": 2000.0,   # drawn stair lines closer than this = one stair
    "stair_tread_min_mm": 150.0,  # a drawn riser spacing below this is not a tread
    "stair_tread_max_mm": 500.0,  # ... and above this it is a landing, not a tread
    "stair_arrival_merge_mm": 800.0,  # parallel flights this close share the top slab
}


def merged(overrides):
    """Return DEFAULTS updated with any provided overrides (None-safe)."""
    out = dict(DEFAULTS)
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                out[key] = value
    return out

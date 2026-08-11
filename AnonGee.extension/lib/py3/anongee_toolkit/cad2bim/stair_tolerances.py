# -*- coding: utf-8 -*-
"""The four stair tunables the dialog can move, in one place.

They are mutable module state, written once per run by `apply_tolerances` and
read by the run finder, the tread test, the spiral finder, the arrival landing
and the plan builder -- code that now lives in several modules. Every reader
therefore reaches them through THIS module (`tol._TREAD_MIN_MM`), never through
a from-import, which would freeze the default and silently ignore whatever the
user typed on the Tolerances tab.
"""

_ARRIVAL_MERGE_GAP_MM = 800.0   # runs this close across = one shared arrival slab
_TREAD_MIN_MM = 150.0         # drawn riser spacing accepted as a tread
_TREAD_MAX_MM = 500.0
_CLUSTER_GAP_MM = 2000.0      # stair pieces closer than this belong together


def apply_tolerances(tolerances):
    """Override the tunables from the dialog's Tolerances tab.

    Called once per run by the pushbutton; anything absent keeps its default so
    the offline tests and replays are unaffected.
    """
    global _CLUSTER_GAP_MM, _TREAD_MIN_MM, _TREAD_MAX_MM, _ARRIVAL_MERGE_GAP_MM
    if not tolerances:
        return
    _CLUSTER_GAP_MM = float(tolerances.get("stair_cluster_mm", _CLUSTER_GAP_MM))
    _TREAD_MIN_MM = float(tolerances.get("stair_tread_min_mm", _TREAD_MIN_MM))
    _TREAD_MAX_MM = float(tolerances.get("stair_tread_max_mm", _TREAD_MAX_MM))
    _ARRIVAL_MERGE_GAP_MM = float(tolerances.get("stair_arrival_merge_mm",
                                                 _ARRIVAL_MERGE_GAP_MM))

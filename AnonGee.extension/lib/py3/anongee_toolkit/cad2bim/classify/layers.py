# -*- coding: utf-8 -*-
"""Layer -> element-category classification.

Hybrid model (as chosen): a default naming *convention* proposes a category for
every layer, and the override dialog (ui.prompt_mapping_override) can change any
of them before anything is used. Classification logic lives here so it is unit-
testable and reusable; the dialog lives in ui.py.

The convention below is a placeholder ordering of common structural-CAD tokens.
Replace the patterns with your real layer names once you share a sample -- this
is the one spot to edit, and the override dialog covers anything it misses.
"""

import re

CATEGORY_GRID = "grid"
CATEGORY_COLUMN = "column"
CATEGORY_BEAM = "beam"
CATEGORY_SLAB_EDGE = "slab_edge"
# Upcoming layer-driven passes (user roadmap): structural walls rise base-to-top
# like columns; arch walls sit ON beams (to the level above, else free-standing);
# stairs come from the stair-plan linework. Mapped now so real projects
# (LayoutPlan-Project1: A-WALL-CUT-Brick, PARAPET WALL, A-STAIR-Steps;
# StaircasePlan-Test1: S-STRS) can already be routed in the override dialog.
CATEGORY_STRUCT_WALL = "structural wall"
CATEGORY_ARCH_WALL = "arch wall"
CATEGORY_STAIR = "stair"
# MULTI-STOREY from ONE dxf (user convention): each floor plan is enclosed by a
# rectangle on a BOUNDARY layer, and carries a single marker on an ORIGIN layer
# that fixes where that plan sits in the model. Names differ per drawing, so the
# convention below is only a proposal -- the dialog's layer table overrides it.
CATEGORY_FLOOR_BOUNDARY = "floor boundary"
CATEGORY_FLOOR_ORIGIN = "floor origin"
# FOUNDATIONS from the drawing rather than invented from column offsets. The
# outline layer carries footings AND rafts; the step layers carry the hatched
# regions where the foundation drops (test10: S-FND, S-FND-FOLD, S-FND-SUNK).
CATEGORY_FOUNDATION = "foundation"
CATEGORY_FOLD = "fold"
CATEGORY_SUNK = "sunk"
CATEGORY_UNMAPPED = "unmapped"

# Identification / annotation layers must NEVER inherit a structural category,
# even though their names contain a structural token. These run first and win.
# (Fixes e.g. "S-GRID-IDEN" -- grid bubbles drawn as arcs -- being read as grid.)
EXCLUSION_PATTERNS = (
    r"iden",       # S-GRID-IDEN, S-COLS-IDEN, ... (tags/bubbles)
    r"anno",       # S-STRS-ANNO, A-ANNO-*
    r"text",       # G-ANNO-TEXT
    r"dim",        # A-ANNO-DIMS-50
    r"defpoint",   # AutoCAD Defpoints
    r"hdln",       # S-BEAM-HDLN -- hidden lines of beams (ignore)
    r"hidden",     # any explicit "hidden" layer
)

# Order matters: first regex (case-insensitive) to match wins.
# A perimeter beam's inner edge is clipped against the floor/slab outline at import, so the
# floor edge (A-FLOR) IS the surviving partner edge for half the beams. It is routed to
# slab_edge so the beam pass can pair a lone beam line against it (label-confirmed only --
# a slab edge alone never becomes a beam).
DEFAULT_CONVENTION = (
    (r"grid|axis", CATEGORY_GRID),
    # The two STEP layers before the foundation one: "S-FND-FOLD" contains
    # "fnd", so a foundation-first ordering would swallow both of them.
    (r"fold", CATEGORY_FOLD),
    (r"sunk|sink", CATEGORY_SUNK),
    # Foundation before "col": a footing layer never carries a column token, but
    # keeping it early means a "S-FND-COL-PAD" style name reads as foundation.
    # Deliberately NOT matching "step"/"thk"/"drop" -- those live on stair and
    # wall layers in this corpus ("A-STAIR-Steps", "JW_ 150 thk NON-STRU. WALL").
    (r"fnd|found|footing|raft|pcc|pile", CATEGORY_FOUNDATION),
    (r"col", CATEGORY_COLUMN),
    (r"beam|girder|joist", CATEGORY_BEAM),
    (r"slab|flor|floor", CATEGORY_SLAB_EDGE),
    (r"stair|strs|step", CATEGORY_STAIR),
    (r"boundar|bound|extent|sheet.?box", CATEGORY_FLOOR_BOUNDARY),
    (r"origin|basept|base.?point|datum", CATEGORY_FLOOR_ORIGIN),
    (r"shear|retain", CATEGORY_STRUCT_WALL),   # structural walls before plain "wall"
    (r"wall|parapet", CATEGORY_ARCH_WALL),
)

ALL_CATEGORIES = (
    CATEGORY_GRID, CATEGORY_COLUMN, CATEGORY_BEAM,
    CATEGORY_SLAB_EDGE, CATEGORY_STRUCT_WALL, CATEGORY_ARCH_WALL,
    CATEGORY_STAIR, CATEGORY_FOUNDATION, CATEGORY_FOLD, CATEGORY_SUNK,
    CATEGORY_FLOOR_BOUNDARY, CATEGORY_FLOOR_ORIGIN,
    CATEGORY_UNMAPPED,
)

# Text/label layers carry the size marks (e.g. "S-COLS-IDEN", "S-BEAM-IDEN").
# They are routed separately from geometry: a column-text label refines/merges
# columns, a beam-text label refines beams. The geometry exclusion of "iden"
# does NOT apply here -- these layers are exactly where the marks live.
CATEGORY_COLUMN_TEXT = "column text"
CATEGORY_BEAM_TEXT = "beam text"
CATEGORY_GRID_TEXT = "grid text"
# The column-schedule table: mark<->size rows that size MARK-ONLY plan labels
# (e.g. "C9" on the plan, "C9 400x600" in the table). Routed apart from plan
# column text because the table is a block of cells, not member-adjacent labels.
CATEGORY_COLUMN_SCHEDULE = "schedule (column/beam/slab)"
# Slab notes ("S1 150 THK", "150 THK.") name and size a floor. They are found by
# CONTENT wherever they sit, so routing a layer here is a way to say "the slab
# notes are on THIS layer" -- which narrows the search on a drawing whose other
# text happens to read like a thickness.
CATEGORY_SLAB_TEXT = "slab text"
# Foundation notes name, size and STEP a footing or raft in one label:
# "F3_1500MM THK" and, where it drops, a second paragraph "2000MM FOLD".
CATEGORY_FOUNDATION_TEXT = "foundation text"
CATEGORY_TEXT_IGNORE = "ignore"
TEXT_CATEGORIES = (CATEGORY_COLUMN_TEXT, CATEGORY_BEAM_TEXT,
                   CATEGORY_GRID_TEXT, CATEGORY_SLAB_TEXT,
                   CATEGORY_FOUNDATION_TEXT,
                   CATEGORY_COLUMN_SCHEDULE, CATEGORY_TEXT_IGNORE)


def classify_text_layer(layer_name):
    """Default routing for a TEXT layer: column / beam / grid / schedule, or ignore."""
    if not layer_name:
        return CATEGORY_TEXT_IGNORE
    text = layer_name.lower()
    if "grid" in text or "axis" in text:
        return CATEGORY_GRID_TEXT
    # A schedule layer carries "sched"/"schd"/"table" -- check before plain "col"
    # so a "S-COLS-SCHEDULE" layer routes to the table, not to plan column text.
    if "sched" in text or "schd" in text or "table" in text:
        return CATEGORY_COLUMN_SCHEDULE
    # Before "col": a foundation note layer may well be named "S-FND-COL-IDEN".
    if re.search(r"fnd|found|footing|raft|pcc|pile", text):
        return CATEGORY_FOUNDATION_TEXT
    if "col" in text:
        return CATEGORY_COLUMN_TEXT
    if "beam" in text or "girder" in text or "joist" in text:
        return CATEGORY_BEAM_TEXT
    if "slab" in text or "flor" in text or "floor" in text or "thk" in text:
        return CATEGORY_SLAB_TEXT
    return CATEGORY_TEXT_IGNORE


def build_default_text_mapping(layer_keys):
    """Pre-fill {text_layer: text_category} from the convention for the dialog."""
    return dict((key, classify_text_layer(key)) for key in layer_keys)


def classify_layer(layer_name, overrides=None):
    """Return a category for one layer.

    Precedence: explicit override > exclusion (annotation/ID) > convention match
    > unmapped. A missing layer name is always unmapped unless overridden.
    """
    if overrides and layer_name in overrides:
        return overrides[layer_name]
    if not layer_name:
        return CATEGORY_UNMAPPED
    text = layer_name.lower()
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, text):
            return CATEGORY_UNMAPPED
    for pattern, category in DEFAULT_CONVENTION:
        if re.search(pattern, text):
            return category
    return CATEGORY_UNMAPPED


def build_default_mapping(layer_keys):
    """Pre-fill {layer_key: category} from the convention for the override dialog."""
    return dict((key, classify_layer(key)) for key in layer_keys)


def apply_mapping(records, mapping):
    """Stamp each record's .category from the (possibly overridden) mapping."""
    for record in records:
        record.category = mapping.get(record.layer_key, CATEGORY_UNMAPPED)
    return records

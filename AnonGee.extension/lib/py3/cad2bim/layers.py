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
# 'floor' is intentionally NOT a slab token -- A-FLOR is architectural finish,
# not a structural slab edge (structural slabs derive from the beam graph).
DEFAULT_CONVENTION = (
    (r"grid|axis", CATEGORY_GRID),
    (r"col", CATEGORY_COLUMN),
    (r"beam|girder|joist", CATEGORY_BEAM),
    (r"slab", CATEGORY_SLAB_EDGE),
)

ALL_CATEGORIES = (
    CATEGORY_GRID, CATEGORY_COLUMN, CATEGORY_BEAM,
    CATEGORY_SLAB_EDGE, CATEGORY_UNMAPPED,
)


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

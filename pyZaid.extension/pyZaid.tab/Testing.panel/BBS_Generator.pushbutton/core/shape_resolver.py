# -*- coding: utf-8 -*-
"""
core/shape_resolver.py
Maps a Revit RebarShape name to the standard shape code and extracts
A/B/C/D/E dimensions.

Root cause of empty dims: Revit stores dimension parameters (A, B, C, D)
on the RebarShape TYPE element, not on the Rebar instance. This module
reads from the shape type first, then supplements from the instance.
"""

import re


def _normalise(name):
    n = name.lower()
    for prefix in ("m_rebar shape ", "rebar shape ", "m_", "rebar_shape_"):
        n = n.replace(prefix, "")
    return re.sub(r"[^a-z0-9]", "", n)


# ── Universal Revit rebar shape fallback map ─────────────────────────────────
# Covers all M_Rebar Shape 00–98 built-in shapes.
# Used when a shape suffix is not in the standard's SHAPE_MAP.
# This ensures EVERY shape gets a meaningful code and description
# instead of "??" — keeping the BBS and Calc Sheet informative.
_UNIVERSAL_SHAPE_MAP = {
    "00": "Straight bar",
    "01": "Straight bar with hook one end",
    "11": "L-bar — one 90 deg bend",
    "12": "L-bar — one 90 deg bend (short leg)",
    "13": "L-bar — one 90 deg bend (long leg)",
    "14": "Cranked bar — 45 deg crank",
    "15": "Cranked bar — 30 deg crank",
    "21": "Z-bar — two 90 deg bends same direction",
    "22": "Z-bar — two 90 deg bends (offset)",
    "23": "Z-bar — two 90 deg bends (long offset)",
    "24": "S-bar — two 90 deg bends opposite direction",
    "25": "Step bar — two bends",
    "26": "Step bar with hook",
    "27": "Trussed bar — double cranked",
    "28": "Step bar — three bends",
    "29": "Step bar variation",
    "31": "U-bar / hairpin — two 90 deg bends",
    "32": "U-bar — two 90 deg bends (wide)",
    "33": "U-bar — two 90 deg bends (equal legs)",
    "34": "U-bar with hook",
    "35": "U-bar variation",
    "36": "U-bar — deep",
    "41": "Cranked bar — 45 deg crank (main bar)",
    "44": "T-shape / step bar",
    "46": "Four-bend bar",
    "47": "Diagonal link",
    "51": "Rectangular closed stirrup / link",
    "56": "Rectangular closed stirrup (alternate hook)",
    "60": "Circular ring",
    "61": "Spiral link",
    "63": "Triangular link",
    "64": "Rhombus / diamond link",
    "67": "Polygonal link",
    "75": "Helical / spiral bar (lap end)",
    "77": "Circular ring (full overlap)",
    "80": "Helical bar",
    "98": "Complex / non-standard shape",
}

def resolve_shape(shape_family_name, standard_module, override_map=None):
    """
    Maps a Revit RebarShape family name to a shape code.
    Returns (shape_code, description, formula_stub).

    Three-tier strategy:
      Tier 1 — User override map (highest priority)
      Tier 2 — Standard SHAPE_MAP (IS/BS/ACI specific codes + formulas)
      Tier 3 — Universal fallback (Revit suffix used directly as code,
                description from _UNIVERSAL_SHAPE_MAP, no formula crash)
    NEVER returns "??" — every shape gets a usable code.
    """
    shape_map = standard_module.SHAPE_MAP
    norm      = _normalise(shape_family_name)

    # Extract numeric suffix from the shape name for Tier 3 fallback
    # "M_Rebar Shape 51" → "51",  "M_Rebar Shape 14a" → "14"
    suffix_match = re.search(r"(\d+)", shape_family_name)
    raw_suffix   = suffix_match.group(1).zfill(2) if suffix_match else None

    # ── Tier 1: User override ─────────────────────────────────────────────────
    if override_map:
        for raw_key, code in override_map.items():
            if _normalise(raw_key) == norm:
                entry = shape_map.get(code, {})
                return (code,
                        entry.get("description", "User override"),
                        entry.get("formula", ""))

    # ── Tier 2: Standard SHAPE_MAP lookup ────────────────────────────────────
    # 2a. Direct code match
    for key, entry in shape_map.items():
        if norm == _normalise(entry["code"]):
            return entry["code"], entry["description"], entry["formula"]

    # 2b. Exact suffix match: norm ends with a SHAPE_MAP key
    for key, entry in shape_map.items():
        if norm.endswith(key) or norm == key:
            return entry["code"], entry["description"], entry["formula"]

    # 2c. Suffix matches raw_suffix
    if raw_suffix and raw_suffix in shape_map:
        entry = shape_map[raw_suffix]
        return entry["code"], entry["description"], entry["formula"]

    # 2d. Fuzzy: any SHAPE_MAP key contained in the normalised name
    for key, entry in shape_map.items():
        if key in norm:
            return entry["code"], entry["description"], entry["formula"]

    # ── Tier 3: Universal fallback — use raw suffix as display code ───────────
    # This handles ALL shapes not in the standard map (01,12,13,22,23...98)
    # without crashing or returning "??"
    if raw_suffix:
        desc = _UNIVERSAL_SHAPE_MAP.get(raw_suffix,
               f"Shape {raw_suffix} — refer to Revit shape library")
        # Build a basic formula stub based on the universal description
        formula = f"L = per shape {raw_suffix} — verify dimensions A/B/C/D in model"
        return raw_suffix, desc, formula

    # ── Last resort: use full name (should never reach here) ─────────────────
    clean = shape_family_name.strip() or "Unknown"
    return clean, f"Non-standard shape: {clean}", ""


# Dimension labels we look for — A through E plus R (radius)
_DIM_LABELS    = ["A", "B", "C", "D", "E"]
_RADIUS_LABELS = ["R", "r"]

# All parameter name variants tried per label
def _param_variants(label):
    """Returns a list of parameter name strings to try for a given label."""
    return [
        label,                          # "A"
        label.upper(),                  # redundant but safe
        "Rebar " + label,               # "Rebar A"
        "Bar " + label,                 # "Bar A"
        "Dimension " + label,           # "Dimension A"
        label + " Length",              # "A Length"
        "Schedule " + label,            # "Schedule A"
    ]


def _read_dim_from_params(element, label, unit_factor):
    """Try all param name variants for a label on a given element."""
    for pname in _param_variants(label):
        try:
            p = element.LookupParameter(pname)
            if p is None:
                continue
            if not p.HasValue:
                continue
            st = p.StorageType.ToString()
            if st == "Double":
                val_mm = int(round(p.AsDouble() * unit_factor))
                if val_mm > 0:
                    return val_mm
        except Exception:
            continue
    return None


def extract_dimensions(rebar_shape, rebar_element, unit_factor=304.8):
    """
    Extracts dimension values (A, B, C, D, E) in mm from a Revit rebar.

    Strategy (in priority order):
      1. Read from the RebarShape TYPE parameters — this is where Revit
         stores the scheduled dimension values (A, B, C, D).
      2. Supplement any missing labels from the Rebar INSTANCE parameters.
      3. Try iterating ALL parameters on the shape and matching by name.
      4. Try Revit 2019+ GetBendData() segment lengths as a last resort.

    Returns a dict like {"A": 350, "B": 200, "C": 450}.
    Empty dict means Revit did not expose dimension params for this shape.
    """
    dims = {}

    # ── Pass 1: Read from RebarShape type parameters ──────────────────────────
    if rebar_shape is not None:
        for label in _DIM_LABELS:
            val = _read_dim_from_params(rebar_shape, label, unit_factor)
            if val:
                dims[label] = val

    # ── Pass 2: Supplement missing labels from rebar instance ─────────────────
    if rebar_element is not None:
        for label in _DIM_LABELS:
            if label not in dims:
                val = _read_dim_from_params(rebar_element, label, unit_factor)
                if val:
                    dims[label] = val

    # ── Pass 3: Iterate ALL shape parameters matching A–E by name ─────────────
    # Catches non-standard param names like "dim_A", "Length_B" etc.
    if rebar_shape is not None and len(dims) < 2:
        try:
            for p in rebar_shape.Parameters:
                try:
                    name = p.Definition.Name.strip()
                    # Match single letter or "XX_A" style
                    label = None
                    if name.upper() in _DIM_LABELS:
                        label = name.upper()
                    elif len(name) > 1 and name[-1].upper() in _DIM_LABELS and name[-2] in ("_", "-", " "):
                        label = name[-1].upper()
                    if label and label not in dims and p.HasValue:
                        val_mm = int(round(p.AsDouble() * unit_factor))
                        if val_mm > 0:
                            dims[label] = val_mm
                except Exception:
                    continue
        except Exception:
            pass

    # ── Pass 4: GetBendData segment lengths (Revit 2019+ API) ─────────────────
    # Each segment between bends corresponds to a dimension label A, B, C...
    if rebar_element is not None and len(dims) < 1:
        try:
            if hasattr(rebar_element, "GetBendData"):
                bend_data = rebar_element.GetBendData()
                if bend_data is not None:
                    segs = list(bend_data.GetSegmentLengths())
                    for i, seg_ft in enumerate(segs):
                        label = _DIM_LABELS[i] if i < len(_DIM_LABELS) else None
                        if label:
                            val_mm = int(round(seg_ft * unit_factor))
                            if val_mm > 0 and label not in dims:
                                dims[label] = val_mm
        except Exception:
            pass

    return dims

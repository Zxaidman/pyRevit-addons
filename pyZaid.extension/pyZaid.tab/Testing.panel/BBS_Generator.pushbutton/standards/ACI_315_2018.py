# -*- coding: utf-8 -*-
"""
ACI 318-19 / ACI 315-18 / CRSI Detailing Manual 2008
Bar bending schedule standard for the United States.

Bar sizes use imperial # designation but metric equivalents provided.
Bend deductions follow ACI 318-19 Table 25.3.1.
"""

STANDARD_NAME  = "ACI 318-19 / CRSI"
STANDARD_SHORT = "ACI"

# ---------------------------------------------------------------------------
# Unit weights — CRSI  (kg/m, converted from lb/ft for metric output)
# Bar size  #3   #4   #5   #6   #7   #8   #9  #10  #11  #14  #18
# dia mm    9.5  12.7 15.9 19.1 22.2 25.4 28.7 32.3 35.8 43.0 57.3
# ---------------------------------------------------------------------------
UNIT_WEIGHTS = {
    10:  0.617,   # closest to #3
    13:  0.994,   # #4
    16:  1.552,   # #5
    19:  2.235,   # #6
    22:  2.985,   # #7
    25:  3.973,   # #8
    29:  5.060,   # #9
    32:  6.404,   # #10
    36:  7.907,   # #11
    43: 11.384,   # #14
    57: 20.240,   # #18
}

# ACI bar number → nominal diameter mm (for display)
BAR_NUMBER_TO_DIA = {
    3: 9.5, 4: 12.7, 5: 15.9, 6: 19.1,
    7: 22.2, 8: 25.4, 9: 28.7, 10: 32.3,
    11: 35.8, 14: 43.0, 18: 57.3,
}

# ---------------------------------------------------------------------------
# Minimum bend diameter — ACI 318-19 Table 25.3.1
# Standard hooks: 6φ for #3–#8, 8φ for #9–#11, 10φ for #14–#18
# Stirrup/tie hooks: 4φ for #5 and smaller, 6φ for #6–#8
# ---------------------------------------------------------------------------
def bend_diameter_mm(diameter_mm: int, is_link: bool = False) -> int:
    if is_link:
        if diameter_mm <= 16:   # ≤ #5
            return 4 * diameter_mm
        elif diameter_mm <= 25:  # #6–#8
            return 6 * diameter_mm
        else:
            return 8 * diameter_mm
    # Standard bends / hooks
    if diameter_mm <= 25:    # #3–#8
        return 6 * diameter_mm
    elif diameter_mm <= 36:  # #9–#11
        return 8 * diameter_mm
    else:                    # #14–#18
        return 10 * diameter_mm


# ---------------------------------------------------------------------------
# Bend deduction — ACI 318 / CRSI
# 90° bend:  deduction = 2φ  (conservative practical value)
# 45° bend:  deduction = φ
# 180° hook: no deduction (hook length added separately)
# ---------------------------------------------------------------------------
def bend_deduction_per_bend(diameter_mm: int, angle_deg: int) -> int:
    table = {45: 1, 90: 2, 135: 2, 180: 0}
    return table.get(angle_deg, 2) * diameter_mm


# ---------------------------------------------------------------------------
# ACI / CRSI shape types
# ACI 315-18 uses "type" letters rather than numbered shape codes.
# S = straight, L = L-bar, U = U-bar, T = T-bar, Z = Z-bar, etc.
# ---------------------------------------------------------------------------
SHAPE_MAP = {
    "00": {"code": "S",  "dims": ["A"],
           "formula": "A",
           "description": "Straight bar"},

    "11": {"code": "L",  "dims": ["A", "B"],
           "formula": "A + B - 2φ  (one 90° bend)",
           "description": "L-bar — one 90° bend"},

    "21": {"code": "Z",  "dims": ["A", "B", "C"],
           "formula": "A + B + C - 4φ  (two 90° bends, same dir.)",
           "description": "Z-bar — two 90° bends same direction"},

    "31": {"code": "U",  "dims": ["A", "B"],
           "formula": "2A + B - 4φ  (U-bar)",
           "description": "U-bar / hairpin"},

    "51": {"code": "T",  "dims": ["A", "B"],
           "formula": "2(A+B) + 12φ  [stirrup hooks per ACI 318-19 Cl.25.7.1.3]",
           "description": "Closed rectangular tie / stirrup"},

    "14": {"code": "C",  "dims": ["A", "B", "C"],
           "formula": "A + B/sin45° + C - 2φ  (crank bar)",
           "description": "Cranked / trussed bar"},

    "41": {"code": "G",  "dims": ["A", "B", "C"],
           "formula": "A + B + C - 3φ",
           "description": "T-step bar"},

    "77": {"code": "R",  "dims": ["D"],
           "formula": "π × D + lap  [ACI 318-19 Cl.25.5 for splice]",
           "description": "Circular ring"},

    "80": {"code": "SP", "dims": ["D", "P"],
           "formula": "√((πD)² + P²) per pitch",
           "description": "Spiral / helix"},
}

# ---------------------------------------------------------------------------
# Standard hook lengths — ACI 318-19 Table 25.3.1
# Used for adding to bar schedules where end hooks are specified
# ---------------------------------------------------------------------------
def standard_hook_length_mm(diameter_mm: int, angle_deg: int = 90) -> int:
    """
    Returns the hook extension (straight portion after bend) in mm.
    90° hook:  12φ straight extension
    180° hook: 4φ (min 65 mm) extension
    Stirrup/tie 90° hook: 6φ (or 75 mm) extension
    """
    if angle_deg == 180:
        return max(4 * diameter_mm, 65)
    return 12 * diameter_mm  # 90° standard hook


# ---------------------------------------------------------------------------
# Formula strings for Calculation Sheet
# ---------------------------------------------------------------------------
def cutting_length_formula(shape_code: str, dims: dict, diameter_mm: int) -> str:
    phi = diameter_mm
    sc = str(shape_code)

    if sc == "S":
        return f"L = A = {dims.get('A','A')} mm  (Straight, no deduction)"

    if sc == "L":
        A, B = dims.get("A","A"), dims.get("B","B")
        ded = 2 * phi
        return (f"L = A + B - 2φ  [ACI 315-18]\n"
                f"  φ = {phi} mm\n"
                f"  L = {A} + {B} - {ded} mm")

    if sc == "T":
        A, B = dims.get("A","A"), dims.get("B","B")
        hook = 12 * phi
        return (f"L = 2(A + B) + hook allowance\n"
                f"  = 2({A} + {B}) + {hook} mm  [ACI 318-19 Cl.25.7.1.3]\n"
                f"  Hook = 12φ = {hook} mm per leg at 90°")

    if sc == "U":
        A, B = dims.get("A","A"), dims.get("B","B")
        ded = 4 * phi
        return (f"L = 2A + B - 4φ\n"
                f"  = 2×{A} + {B} - {ded} mm")

    if sc == "R":
        D = dims.get("D","D")
        import math
        lap = 12 * phi
        return (f"L = π × D + lap\n"
                f"  = 3.1416 × {D} + {lap} mm  [ACI 318-19 Cl.25.5 lap splice]")

    return f"L = per ACI 315-18 type {sc}  (dims: {dims})"


COMMON_SHAPES = ["S", "L", "T", "U", "C"]
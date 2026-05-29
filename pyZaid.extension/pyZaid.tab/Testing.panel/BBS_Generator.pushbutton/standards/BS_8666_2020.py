# -*- coding: utf-8 -*-
"""
BS 8666:2020 — Scheduling, dimensioning, bending and cutting of steel
reinforcement for concrete. Specification.

All shape codes, bend radii, deductions and formula strings follow
the 2020 edition (supersedes BS 8666:2005).
"""

STANDARD_NAME  = "BS 8666:2020"
STANDARD_SHORT = "BS"

# ---------------------------------------------------------------------------
# Unit weights — BS 4449 / BS 8666:2020 Table 1  (kg/m)
# ---------------------------------------------------------------------------
UNIT_WEIGHTS = {
    6:  0.222,
    8:  0.395,
    10: 0.616,
    12: 0.888,
    16: 1.579,
    20: 2.466,
    25: 3.854,
    32: 6.313,
    40: 9.864,
    50: 15.413,
}

# ---------------------------------------------------------------------------
# Minimum scheduling radius (r) — BS 8666:2020 Table 8
# Returns minimum bend radius in mm (NOT diameter — radius = d/2 of mandrel)
# ---------------------------------------------------------------------------
_SCHED_RADIUS = {
    # (dia_mm): min_radius_mm
    6:   12,
    8:   16,
    10:  20,
    12:  24,
    16:  32,
    20:  70,   # ≥ 20 mm: r = 3.5φ per Table 8 for Grade B500B
    25:  87,
    32: 112,
    40: 140,
    50: 175,
}

def bend_diameter_mm(diameter_mm: int, is_link: bool = False) -> int:
    """
    Returns the minimum bend DIAMETER (2r) per BS 8666:2020 Table 8.
    For links ≤ 16 mm: 3φ minimum per Cl. 10.
    """
    if is_link and diameter_mm <= 16:
        return 3 * diameter_mm
    r = _SCHED_RADIUS.get(diameter_mm)
    if r:
        return 2 * r
    # Interpolate for sizes not in table: r = 3.5φ for ≥20 mm
    return int(7 * diameter_mm) if diameter_mm >= 20 else int(4 * diameter_mm)


# ---------------------------------------------------------------------------
# Bend deduction — BS 8666:2020 Annex B Formula
# Deduction per 90° bend = 2r + φ  where r = scheduling radius
# For other angles: deduction = (r + φ/2) × tan(angle/2) − (r + φ/2) × angle_rad / 2
# Simplified per-bend deduction table (mm) used in practice:
# ---------------------------------------------------------------------------
def bend_deduction_per_bend(diameter_mm: int, angle_deg: int) -> int:
    r = _SCHED_RADIUS.get(diameter_mm, int(3.5 * diameter_mm))
    phi = diameter_mm
    import math
    angle_rad = math.radians(angle_deg)
    # BS Annex B: d = (r + phi/2)(tan(a/2) - a/2)  where a = π - bend_angle_rad
    # For 90° bend (internal angle 90°), outer angle = π/2
    outer = math.pi - angle_rad
    deduction = (r + phi / 2.0) * (math.tan(outer / 2.0) - outer / 2.0)
    return max(0, int(round(deduction)))


# ---------------------------------------------------------------------------
# BS 8666:2020 Shape codes — Table 2 (selected most common)
# Revit shape family partial name → BS shape data
# ---------------------------------------------------------------------------
SHAPE_MAP = {
    "00": {"code": "00", "dims": ["A"],
           "formula": "A",
           "description": "Straight bar — no bends"},

    "11": {"code": "11", "dims": ["A", "B"],
           "formula": "A + B - 0.5r - φ/2  (BS Annex B, 90° bend)",
           "description": "One end 90° bend (L-bar)"},

    "12": {"code": "12", "dims": ["A", "B"],
           "formula": "A + B - 0.5r - φ/2",
           "description": "One end 90° bend — long/short leg variation"},

    "13": {"code": "13", "dims": ["A", "B", "C"],
           "formula": "A + B + C - 2(0.5r + φ/2)",
           "description": "Two 90° bends — same direction (Z-bar)"},

    "14": {"code": "14", "dims": ["A", "B", "C"],
           "formula": "A + B + C - 2(0.5r + φ/2)",
           "description": "Two 90° bends — opposite direction (S-bar)"},

    "15": {"code": "15", "dims": ["A", "B", "C", "D"],
           "formula": "A + B + C + D - 3(0.5r + φ/2)",
           "description": "Three 90° bends"},

    "21": {"code": "21", "dims": ["A", "B"],
           "formula": "A + B  (U-bar, semi-circular bend: add πr)",
           "description": "U-bar / hairpin — 180° bend"},

    "31": {"code": "31", "dims": ["A"],
           "formula": "A + 2(4φ)  (hooks each end per BS 8666 Cl.10)",
           "description": "Straight with standard hooks both ends"},

    "32": {"code": "32", "dims": ["A", "B"],
           "formula": "A + B + 4φ  (one hook end)",
           "description": "L-bar with hook one end"},

    "41": {"code": "41", "dims": ["A", "B", "C"],
           "formula": "2A + B + C - 3(0.5r + φ/2)",
           "description": "Cranked bar — 45° crank"},

    "51": {"code": "51", "dims": ["A", "B"],
           "formula": "2(A + B) - 3(0.5r + φ/2) + hooks\n"
                      "  hooks = 2×(10φ) per BS 8666:2020 Cl.10.5",
           "description": "Closed rectangular link / stirrup"},

    "60": {"code": "60", "dims": ["D"],
           "formula": "π(D + φ) + 20φ  (lap included)",
           "description": "Circular ring"},

    "77": {"code": "77", "dims": ["A", "B"],
           "formula": "C = √(A² + B²)  then L = nC per pitch",
           "description": "Helical bar"},
}

# ---------------------------------------------------------------------------
# Formula strings for Calculation Sheet
# ---------------------------------------------------------------------------
def cutting_length_formula(shape_code: str, dims: dict, diameter_mm: int) -> str:
    phi = diameter_mm
    r = _SCHED_RADIUS.get(diameter_mm, int(3.5 * phi))
    sc = str(shape_code)

    if sc == "00":
        return f"L = A = {dims.get('A','A')} mm  (Straight, no deduction)"

    if sc in ("11", "12"):
        A, B = dims.get("A","A"), dims.get("B","B")
        ded = round(0.5 * r + phi / 2)
        return (f"L = A + B - (0.5r + φ/2)  [BS 8666:2020 Annex B]\n"
                f"  r = {r} mm  (scheduling radius, Table 8)\n"
                f"  deduction = 0.5×{r} + {phi}/2 = {ded} mm\n"
                f"  L = {A} + {B} - {ded} mm")

    if sc in ("13", "14"):
        A, B, C = dims.get("A","A"), dims.get("B","B"), dims.get("C","C")
        ded = round(0.5 * r + phi / 2)
        return (f"L = A + B + C - 2×(0.5r + φ/2)  [BS 8666:2020 Annex B]\n"
                f"  r = {r} mm, deduction per bend = {ded} mm\n"
                f"  L = {A} + {B} + {C} - {2*ded} mm")

    if sc == "51":
        A, B = dims.get("A","A"), dims.get("B","B")
        ded = round(0.5 * r + phi / 2)
        hook = 10 * phi
        return (f"L = 2(A + B) - 3×(0.5r + φ/2) + 2×hook\n"
                f"  r = {r} mm, bend deduction = {ded} mm\n"
                f"  hook = 10φ = {hook} mm per BS 8666:2020 Cl.10.5\n"
                f"  L = 2({A}+{B}) - {3*ded} + {2*hook} mm")

    if sc == "60":
        D = dims.get("D","D")
        import math
        lap = 20 * phi
        return (f"L = π(D + φ) + lap\n"
                f"  = 3.1416 × ({D} + {phi}) + {lap} mm")

    return f"L = per BS 8666:2020 shape {sc}  (dims: {dims})"


COMMON_SHAPES = ["00", "11", "51", "21", "41"]
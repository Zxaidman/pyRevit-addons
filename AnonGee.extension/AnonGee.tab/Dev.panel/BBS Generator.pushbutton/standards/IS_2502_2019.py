# -*- coding: utf-8 -*-
"""
IS 2502:2019 — Code of Practice for Bending and Fixing of Bars
for Concrete Reinforcement (Third Revision).

SHAPE_MAP keys = Revit rebar shape family suffix (from "M_Rebar Shape XX").
IS shape codes follow IS 2502:2019 Annex A numbering (1, 2, 3, 5, 37, etc.)
"""

STANDARD_NAME  = "IS 2502:2019"
STANDARD_SHORT = "IS"

# ── Unit weights — IS 1786 / IS 2502:2019 Annex A (kg/m) ────────────────────
UNIT_WEIGHTS = {
    6:  0.222, 8:  0.395, 10: 0.617, 12: 0.888,
    16: 1.578, 20: 2.466, 25: 3.853, 32: 6.313, 40: 9.864,
}

# ── Minimum bend diameter — IS 2502:2019 Clause 5.2 ─────────────────────────
def bend_diameter_mm(diameter_mm, is_link=False):
    """
    Returns minimum mandrel/bend diameter in mm.
    Links/stirrups (is_link=True): 4*phi for all sizes.
    Main bars: 4*phi for phi<=25, 7*phi for phi>25.
    """
    if is_link:
        return 4 * diameter_mm
    return 4 * diameter_mm if diameter_mm <= 25 else 7 * diameter_mm

# ── Bend deduction per bend — IS 2502:2019 Clause 5.3 ───────────────────────
_BEND_MULTIPLIER = {45: 1, 90: 2, 135: 3, 180: 4}

def bend_deduction_per_bend(diameter_mm, angle_deg):
    """Deduction = multiplier * phi per individual bend."""
    return _BEND_MULTIPLIER.get(angle_deg, 2) * diameter_mm

# ── Shape map — Revit shape suffix → IS 2502:2019 shape data ────────────────
# Keys are the numeric suffix of the Revit built-in rebar shape family name.
# Multiple keys can map to the same IS code where Revit has shape variants.
SHAPE_MAP = {
    # Straight bar — IS Shape 1
    "00": {"code": "00",  "dims": ["A"],
           "formula": "A",
           "description": "Straight bar — IS 2502 Shape 1"},

    # L-bar / one 90 deg bend — IS Shape 2
    "11": {"code": "11",  "dims": ["A", "B"],
           "formula": "A + B - 2*phi",
           "description": "L-bar, one 90 deg bend — IS 2502 Shape 2"},
    "12": {"code": "11",  "dims": ["A", "B"],
           "formula": "A + B - 2*phi",
           "description": "L-bar variation, one 90 deg bend — IS 2502 Shape 2"},

    # Z-bar / two 90 deg bends same direction — IS Shape 3
    "21": {"code": "21",  "dims": ["A", "B", "C"],
           "formula": "A + B + C - 4*phi",
           "description": "Z-bar, two 90 deg bends same direction — IS 2502 Shape 3"},
    "22": {"code": "21",  "dims": ["A", "B", "C"],
           "formula": "A + B + C - 4*phi",
           "description": "Z-bar variation — IS 2502 Shape 3"},

    # U-bar / hairpin — IS Shape 5
    "31": {"code": "31",  "dims": ["A", "B"],
           "formula": "2*A + B - 4*phi",
           "description": "U-bar / hairpin — IS 2502 Shape 5"},
    "32": {"code": "31",  "dims": ["A", "B"],
           "formula": "2*A + B - 4*phi",
           "description": "U-bar variation — IS 2502 Shape 5"},

    # Rectangular closed stirrup — IS Shape 37
    "51": {"code": "51", "dims": ["A", "B"],
           "formula": "2*(A+B) + 20*phi  [IS 2502:2019 Cl.5.4 — 135 deg hooks]",
           "description": "Rectangular closed stirrup — IS 2502 Shape 37"},
    "56": {"code": "51", "dims": ["A", "B"],
           "formula": "2*(A+B) + 20*phi  [IS 2502:2019 Cl.5.4 — 135 deg hooks]",
           "description": "Rectangular closed stirrup (alt) — IS 2502 Shape 37"},

    # Cranked / bent-up bar 45 deg — IS Shape 12
    "41": {"code": "41", "dims": ["A", "B", "C"],
           "formula": "A + B/sin(45) + C - 2*phi",
           "description": "Cranked bar 45 deg — IS 2502 Shape 12"},
    "14": {"code": "41", "dims": ["A", "B", "C"],
           "formula": "A + B/sin(45) + C - 2*phi",
           "description": "Cranked bar 45 deg variation — IS 2502 Shape 12"},

    # T-shape / step bar — IS Shape 7
    "44": {"code": "44",  "dims": ["A", "B", "C"],
           "formula": "A + B + C - 4*phi",
           "description": "T-shape / step bar — IS 2502 Shape 7"},

    # Diagonal / spiral link — IS Shape 47
    "61": {"code": "61", "dims": ["A", "B"],
           "formula": "1.414*(A+B) + 20*phi",
           "description": "Diagonal link — IS 2502 Shape 47"},

    # Circular ring — IS Shape 77
    "77": {"code": "77", "dims": ["D"],
           "formula": "pi*D + 20*phi  [IS 2502:2019 Cl.6 lap]",
           "description": "Circular ring — IS 2502 Shape 77"},

    # Helical / spiral bar — IS Shape 80
    "80": {"code": "80", "dims": ["D", "P"],
           "formula": "sqrt((pi*D)^2 + P^2) per pitch",
           "description": "Helical / spiral bar — IS 2502 Shape 80"},
}

# ── Cutting length formula strings — for Calculation Sheet ──────────────────
def cutting_length_formula(shape_code, dims, diameter_mm):
    """
    Returns a multi-line formula string for the Calculation Sheet.
    phi = bar diameter, deduction per 90 deg bend = 2*phi (IS 2502:2019 Cl.5.3).
    """
    d  = diameter_mm
    sc = str(shape_code)
    A  = dims.get("A", "A")
    B  = dims.get("B", "B")
    C  = dims.get("C", "C")
    D  = dims.get("D", "D")
    P  = dims.get("P", "P")

    if sc == "00":
        return (f"L = A  [IS 2502:2019 Shape 1 — Straight bar]\n"
                f"  L = {A} mm  (no bend deduction)")

    if sc == "11":
        ded = 2 * d
        return (f"L = A + B - 2*phi  [IS 2502:2019 Shape 2 — one 90 deg bend]\n"
                f"  phi = {d} mm  |  deduction = 2*{d} = {ded} mm\n"
                f"  L = {A} + {B} - {ded} mm")

    if sc == "21":
        ded = 4 * d
        return (f"L = A + B + C - 4*phi  [IS 2502:2019 Shape 3 — two 90 deg bends]\n"
                f"  phi = {d} mm  |  deduction = 4*{d} = {ded} mm\n"
                f"  L = {A} + {B} + {C} - {ded} mm")

    if sc == "31":
        ded = 4 * d
        return (f"L = 2*A + B - 4*phi  [IS 2502:2019 Shape 5 — U-bar / hairpin]\n"
                f"  phi = {d} mm  |  deduction = 4*{d} = {ded} mm\n"
                f"  L = 2*{A} + {B} - {ded} mm")

    if sc == "51":
        hook = 20 * d
        return (f"L = 2*(A+B) + hook allowance  [IS 2502:2019 Shape 37 — closed stirrup]\n"
                f"  Hook = 20*phi per IS 2502:2019 Cl.5.4 (135 deg bend)\n"
                f"  Hook = 20*{d} = {hook} mm\n"
                f"  L = 2*({A}+{B}) + {hook} mm")

    if sc == "41":
        ded = 2 * d
        return (f"L = A + B/sin(45) + C - 2*phi  [IS 2502:2019 Shape 12 — 45 deg crank]\n"
                f"  phi = {d} mm  |  deduction = 2*{d} = {ded} mm\n"
                f"  L approx {A} + {B}*1.4142 + {C} - {ded} mm")

    if sc == "44":
        ded = 4 * d
        return (f"L = A + B + C - 4*phi  [IS 2502:2019 Shape 7 — T/step bar]\n"
                f"  phi = {d} mm  |  deduction = 4*{d} = {ded} mm\n"
                f"  L = {A} + {B} + {C} - {ded} mm")

    if sc == "61":
        hook = 20 * d
        return (f"L = 1.414*(A+B) + 20*phi  [IS 2502 Shape 47 — diagonal link]\n"
                f"  L = 1.4142*({A}+{B}) + {hook} mm")

    if sc == "77":
        lap = 20 * d
        return (f"L = pi*D + lap  [IS 2502:2019 Shape 77 / Cl.6 — circular ring]\n"
                f"  lap = 20*phi = 20*{d} = {lap} mm\n"
                f"  L = 3.1416*{D} + {lap} mm")

    if sc == "80":
        return (f"L = sqrt((pi*D)^2 + P^2) per pitch  [IS 2502:2019 Shape 80 — helical]\n"
                f"  D = {D} mm (helix diameter)  |  P = {P} mm (pitch per turn)")

    return f"L = per IS 2502:2019 shape {sc}  (dims: {dims})"

# ── Common shapes — always shown in Calculation Sheet reference section ───────
COMMON_SHAPES = ["00", "11", "31", "51", "41"]

# -*- coding: utf-8 -*-
"""
Unit conversion utilities for Revit's internal foot-based coordinate system.

Revit stores all lengths internally in decimal feet.  These helpers convert
between feet, millimetres, and metres, and strip known unit suffixes from
user-supplied strings.
"""

# ---------------------------------------------------------------------------
# Conversion constants
# ---------------------------------------------------------------------------
CF_TO_M3 = 0.028316846592   # cubic feet → cubic metres
SF_TO_M2 = 0.09290304       # square feet → square metres
FT_TO_MM = 304.8            # feet → millimetres
FT_TO_M  = 0.3048           # feet → metres


# ---------------------------------------------------------------------------
# Scalar converters
# ---------------------------------------------------------------------------

def m_to_mm(meters):
    """Convert metres to millimetres (rounded to nearest integer)."""
    return int(round(float(meters) * 1000.0))


def mm_to_ft(mm):
    """Convert millimetres to decimal feet."""
    return float(mm) / FT_TO_MM


def m_to_ft(meters):
    """Convert metres to decimal feet."""
    return mm_to_ft(m_to_mm(meters))


def ft_to_mm(feet):
    """Convert decimal feet to millimetres."""
    return float(feet) * FT_TO_MM


def clean_ft(feet):
    """Round *feet* to the nearest millimetre then convert back to feet."""
    return mm_to_ft(int(round(float(feet) * FT_TO_MM)))


# ---------------------------------------------------------------------------
# Unit-suffix stripper
# ---------------------------------------------------------------------------

def _normalise_unit(token):
    """Lowercase, map Unicode superscripts, strip spaces."""
    token = token.strip().lower()
    token = (
        token.replace(u"\xb2", "2").replace(u"\xb3", "3")
             .replace(u"\xe2", "").replace(u"\xc2", "")
    )
    return token.replace(" ", "")


_KNOWN_UNITS = {
    _normalise_unit(u)
    for u in [
        "mm", "cm", "m", "km",
        "mm2", "cm2", "m2", "km2", "sq m", "sqm", u"mm²", u"cm²", u"m²",
        "mm3", "cm3", "m3", "cu m", "cum", u"mm³", u"cm³", u"m³",
        "g", "kg", "t", "ton", "tonne",
        "kg/m", "kg/m2", "kg/m3", "kg/cm2", u"kg/m²", u"kg/m³",
        "n", "kn", "kn/m", "kn/m2", "n/mm2", u"n/mm²", "pa", "kpa", "mpa",
        "l", "ml", "deg", u"°", "%",
    ]
}


def strip_unit(value):
    """
    Convert ``"<number><unit>"`` strings to a native Python int or float.

    Only strips suffixes that appear in the known engineering unit set so that
    hyphenated codes such as ``"10-20"`` are left untouched.

    Args:
        value: Any value.  Non-strings are returned unchanged.

    Returns:
        int | float | original value
    """
    if not isinstance(value, str):
        return value

    s = value.strip()
    if not s:
        return value

    i, sign = 0, ""
    if s[0] in "+-":
        sign = s[0]
        i = 1

    digits, seen_dot = [], False
    while i < len(s):
        ch = s[i]
        if ch.isdigit():
            digits.append(ch)
        elif ch == "." and not seen_dot:
            digits.append(ch)
            seen_dot = True
        elif ch == ",":
            pass  # thousands separator
        else:
            break
        i += 1

    if not digits:
        return value

    suffix = s[i:]
    if suffix and _normalise_unit(suffix) not in _KNOWN_UNITS:
        return value

    try:
        f = float(sign + "".join(digits))
    except ValueError:
        return value

    return int(f) if f == int(f) else f

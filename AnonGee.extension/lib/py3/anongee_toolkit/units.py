# -*- coding: utf-8 -*-

# Revit Internal Unit Constants
CF_TO_M3 = 0.028316846592
SF_TO_M2 = 0.09290304
FT_TO_MM = 304.8
FT_TO_M  = 0.3048

def m_to_mm(meters): return int(round(float(meters) * 1000.0))
def mm_to_ft(mm): return float(mm) / FT_TO_MM
def m_to_ft(meters): return mm_to_ft(m_to_mm(meters))
def ft_to_mm(feet): return float(feet) * FT_TO_MM
def clean_ft(feet): return mm_to_ft(int(round(float(feet) * FT_TO_MM)))

def _norm_unit(u):
    """Normalize a unit token: lowercase, map superscripts (² ³) and artifacts."""
    u = u.strip().lower()
    u = (u.replace(u"\xb2", "2").replace(u"\xb3", "3")
           .replace(u"\xe2", "").replace(u"\xc2", ""))
    return u.replace(" ", "")

KNOWN_UNITS = set(_norm_unit(u) for u in [
    "mm", "cm", "m", "km",
    "mm2", "cm2", "m2", "km2", "sq m", "sqm", u"mm²", u"cm²", u"m²",
    "mm3", "cm3", "m3", "cu m", "cum", u"mm³", u"cm³", u"m³",
    "g", "kg", "t", "ton", "tonne",
    "kg/m", "kg/m2", "kg/m3", "kg/cm2", u"kg/m²", u"kg/m³",
    "n", "kn", "kn/m", "kn/m2", "n/mm2", u"n/mm²", "pa", "kpa", "mpa",
    "l", "ml", "deg", u"°", "%",
])

def strip_unit(value):
    """
    Converts 'number + known unit' to int/float natively.
    Leaves text that does not match a known unit untouched (e.g., "10-20").
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return value

    i, sign = 0, ""
    if s[0] in "+-":
        sign = s[0]; i = 1
    num = []
    seen_dot = False
    while i < len(s):
        ch = s[i]
        if ch.isdigit():
            num.append(ch)
        elif ch == "." and not seen_dot:
            num.append(ch); seen_dot = True
        elif ch == ",":
            pass
        else:
            break
        i += 1

    if not num:
        return value

    rest = s[i:]
    if rest and _norm_unit(rest) not in KNOWN_UNITS:
        return value

    try:
        f = float(sign + "".join(num))
    except ValueError:
        return value
    return int(f) if f == int(f) else f
# -*- coding: utf-8 -*-
"""The slice of BS 8666:2020 the workbook validator needs.

**BBS Generator's ``standards/BS_8666_2020.py`` is the authority.** It carries
the unit weights, scheduling radii, bend deductions and cutting-length formulae,
and nothing here duplicates any of that. What lives here is the much smaller
question the validator asks -- *is this a bar size, is this a shape code, can
this shape carry this role* -- because a validator that has to import another
pushbutton to reject a typo is a validator nobody can unit-test.

The two files are held to each other by ``tests/test_rc_automation.py``, which
loads the BBS module by path and fails if the diameters or the shape codes drift
apart. That is the whole reason a copy is tolerable: it cannot silently rot.

Reinforcement geometry -- hooks, bends, cutting lengths -- is not computed here
and must not be. It is the creation layer's job and it goes through the BBS
module so both tools schedule the same bar.
"""

__version__ = "0.1.0"

#: BS 8666:2020 / BS 4449 preferred sizes -- the keys of the standard's unit
#: weight table. A diameter outside this set is a schedule typo, not an
#: exotic bar, so validation rejects it rather than rounding it.
BAR_DIAMETERS_MM = (6, 8, 10, 12, 16, 20, 25, 32, 40, 50)

#: Every shape code BBS Generator can already schedule.
KNOWN_SHAPE_CODES = ("00", "11", "12", "13", "14", "15",
                     "21", "31", "32", "41", "51", "60", "77")

#: What P0 builds Revit geometry for. A row using a known-but-unsupported code
#: is reported as such and skipped -- never silently dropped, and never quietly
#: substituted with a straight bar, which would put a wrong bar in the model and
#: a wrong length in the schedule.
SUPPORTED_SHAPE_CODES = ("00", "11", "21", "51")

#: Closed links. A tie has to be one of these; a straight bar is not a tie, and
#: accepting one would produce a column with no confinement at all.
LINK_SHAPE_CODES = ("51",)

#: Shapes that make sense as a footing layer or a column main bar.
STRAIGHT_OR_BENT_SHAPE_CODES = ("00", "11", "12", "13", "14", "15",
                                "21", "31", "32", "41")

#: Human text for the codes P0 supports, for validation messages and the grid.
SHAPE_DESCRIPTIONS = {
    "00": "Straight bar — no bends",
    "11": "One end 90° bend (L-bar)",
    "21": "U-bar / hairpin",
    "51": "Closed rectangular link / stirrup",
}

STANDARD_NAME = "BS 8666:2020"


def is_standard_diameter(diameter_mm):
    """True for a preferred bar size. Tolerates 16.0 as well as 16."""
    if diameter_mm is None:
        return False
    try:
        value = float(diameter_mm)
    except (TypeError, ValueError):
        return False
    return any(abs(value - size) < 1e-9 for size in BAR_DIAMETERS_MM)


def normalise_shape_code(value):
    """Return a two-character shape code, or ``None`` if it is not one.

    Excel is the reason this exists. A cell holding ``0`` comes back as the int
    ``0`` and a cell holding ``00`` may come back as the float ``0.0``, both of
    which have to read as shape code "00"; a cell formatted as text gives the
    string. Anything that is not a whole number in range is not a shape code.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, float):
        if value != int(value):
            return None
        value = int(value)
    if isinstance(value, int):
        if value < 0 or value > 99:
            return None
        return "{0:02d}".format(value)
    text = str(value).strip()
    if not text:
        return None
    if len(text) > 2 or not text.isdigit():
        return None
    return text.zfill(2)


def describe_shape(shape_code):
    """A short description, falling back to the bare code for unlisted ones."""
    return SHAPE_DESCRIPTIONS.get(shape_code, "shape {0}".format(shape_code))

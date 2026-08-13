# -*- coding: utf-8 -*-
"""Read a foundation note: what it is called, how thick it is, where it steps.

A footing or raft label carries everything the builder needs, on one or two
lines (test10's foundation level):

    F1_1200MM THK
    F3_1500MM THK
    2000MM FOLD
    F6_1000MM THK
    1000MM SUNK

The mark names it, the first line sizes it, and where the foundation steps a
SECOND paragraph gives the step depth and which kind of step it is. MTEXT stores
that break as `\\P`; the DXF reader's `plain_text()` hands it over as a newline,
so both are accepted here -- a record built by hand should not read differently
from one that came through the reader.

`fold` and `sunk` are kept apart rather than collapsed into "a step". They are
the same measurement but not the same detail, the drawing puts them on separate
layers (`S-FND-FOLD`, `S-FND-SUNK`), and the builder that consumes them will
place different geometry for each.

Revit-free, so it is unit-testable outside Revit. Compare `slab_labels.py`,
which does the same job for "S1 150 THK" slab notes.
"""

import re

FOLD = "fold"
SUNK = "sunk"

# "F3", "F12" -- a foundation mark is the letter F and a number. Anchored to the
# start so "REF3" is not a mark, and the letter is fixed so a beam's "B1" or a
# column's "C1" cannot be read as a foundation.
_MARK = r"(?P<mark>F\d+)"

# "1500MM THK", "1500 THK", "1500mm thk." -- MM optional, trailing dot allowed.
_THICKNESS = r"(?P<thickness>\d+(?:\.\d+)?)\s*(?:MM)?\s*THK\.?"

# The whole first line: a mark, a thickness, or a mark joined to a thickness by
# a space or an underscore (the drawing uses "F1_1200MM THK").
_SIZED = re.compile(r"^\s*" + _MARK + r"\s*[_ ]\s*" + _THICKNESS + r"\s*$",
                    re.IGNORECASE)
_MARK_ONLY = re.compile(r"^\s*" + _MARK + r"\s*$", re.IGNORECASE)
_THICKNESS_ONLY = re.compile(r"^\s*" + _THICKNESS + r"\s*$", re.IGNORECASE)

# "2000MM FOLD" / "1000 SUNK" -- the step paragraph.
_STEP = re.compile(
    r"^\s*(?P<depth>\d+(?:\.\d+)?)\s*(?:MM)?\s*(?P<kind>FOLD|SUNK)\.?\s*$",
    re.IGNORECASE)


def parse(text, on_foundation_layer=False):
    """{mark, thickness_mm, step_mm, step_kind} for a foundation note, else None.

    None means "this is not a foundation label", so the caller can use it as the
    test. A label that names without sizing ("F3") is still a foundation label;
    the missing half comes back None and the builder falls back the way the slab
    builder does.

    `on_foundation_layer` resolves the one genuinely ambiguous case. A BARE
    thickness -- "1200MM THK" with no mark -- is a raft note on `S-FND-IDEN` and
    a slab note ("150 THK.", which slab_labels owns) anywhere else. The text
    cannot tell them apart and must not guess: claiming every bare thickness
    would steal the slab notes this toolkit has been reading since v0.36. The
    caller knows which layer the text came from, so it says.
    """
    if not text:
        return None
    found = {"mark": None, "thickness_mm": None,
             "step_mm": None, "step_kind": None}
    claimed = False
    for line in _lines(text):
        if _read_size(line, found, on_foundation_layer):
            claimed = True
        elif _read_step(line, found):
            claimed = True
    return found if claimed else None


def _lines(text):
    """The label's paragraphs, however the break survived the round trip."""
    return [line for line in text.replace("\\P", "\n").splitlines()
            if line.strip()]


def _read_size(line, found, on_foundation_layer):
    match = _SIZED.match(line)
    if match:
        found["mark"] = match.group("mark").upper()
        found["thickness_mm"] = float(match.group("thickness"))
        return True
    match = _MARK_ONLY.match(line)
    if match:
        found["mark"] = match.group("mark").upper()
        return True
    if not on_foundation_layer:
        return False           # a bare thickness belongs to the slab notes
    match = _THICKNESS_ONLY.match(line)
    if match:
        found["thickness_mm"] = float(match.group("thickness"))
        return True
    return False


def _read_step(line, found):
    match = _STEP.match(line)
    if not match:
        return False
    found["step_mm"] = float(match.group("depth"))
    found["step_kind"] = match.group("kind").lower()
    return True

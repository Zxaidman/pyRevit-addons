# -*- coding: utf-8 -*-
"""What counts as a plausible member size, and the office's standard sizes.

The acceptance band (a column between 150 and 1500 wide, a beam between 150 and
1000) is the first thing every pass consults and the last thing anyone should
have to hunt for, so it lives in a file of its own rather than at the top of a
three-thousand-line module. The Tolerances tab edits these; the defaults come
from config.

`parse_standard_sizes` / `parse_standard_widths` read the office list the dialog
carries ("230x230, 300x600, ..."), which snaps a drawn 298 onto the 300 it is.
"""

import re

from . import config

DEFAULT_LIMITS_KEYS = ("beam_width_min_mm", "beam_width_max_mm",
                       "col_b_min_mm", "col_b_max_mm",
                       "col_h_min_mm", "col_h_max_mm")


# Acceptance limits (mm) -- the subset of config used as the UI's defaults.
DEFAULT_LIMITS = dict((key, config.DEFAULTS[key]) for key in (
    "beam_width_min_mm", "beam_width_max_mm",
    "col_b_min_mm", "col_b_max_mm", "col_h_min_mm", "col_h_max_mm"))


def parse_standard_sizes(text):
    """Parse '300x600, 300x750' -> [(300.0, 600.0), ...] (b<=h). Tolerant of junk."""
    pairs = []
    if not text:
        return pairs
    for token in text.replace(";", ",").split(","):
        token = token.strip().lower().replace("X", "x")
        if "x" not in token:
            continue
        a, _, b = token.partition("x")
        try:
            va, vb = float(a.strip()), float(b.strip())
        except ValueError:
            continue
        pairs.append((min(va, vb), max(va, vb)))
    return pairs


def parse_standard_widths(text):
    """Parse '300, 450, 600' -> [300.0, 450.0, 600.0]. Tolerant of junk."""
    widths = []
    if not text:
        return widths
    for token in text.replace(";", ",").split(","):
        token = token.strip()
        try:
            widths.append(float(token))
        except ValueError:
            continue
    return widths


def _standard_dims_mm(pairs):
    """Flatten standard (b, h) pairs into the set of distinct dimensions."""
    dims = set()
    for b, h in pairs:
        dims.add(b)
        dims.add(h)
    return sorted(dims)

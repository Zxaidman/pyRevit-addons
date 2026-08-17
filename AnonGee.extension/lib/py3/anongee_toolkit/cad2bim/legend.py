# -*- coding: utf-8 -*-
"""Read the LEGEND a Test9-style drawing carries, and turn it into PROPOSALS.

test10 says what a hatch means by LAYER: S-FND-FOLD is folds, S-FND-SUNK is
sunk. test9 says it by LEGEND: small swatch rectangles, each demonstrating a
hatch pattern, sit beside texts reading "HATCH INDICATE T.O.S. +50MM.",
"HATCH INDICATE CUTOUT FOR DOOR ABOVE", and every plan hatch OF THAT PATTERN
inherits the meaning. The mapping is swatch pattern -> legend text -> meaning.

Everything here is measured on test9, not assumed:

  * The swatches are 807x484, 1001x601 and 1100x400 rectangles; the drawing's
    smallest non-swatch hatches are 83x83 level markers and 600x75 wall
    slivers, and column fills start at 500x700. The size band (both sides
    200..1500 mm) is drawn between those.
  * A legend text's anchor sits 657..947 mm from its own swatch's centre; the
    NEXT row's swatch is 839..1020 mm away (rows stack 617..640 mm apart).
    Nearest-alone would still pair every row right, but with a margin of only
    ~200 mm -- so pairing is MUTUAL nearest: the text's closest swatch must
    also call that text its closest. A missing swatch then unpairs its row
    instead of stealing the neighbour's.
  * A PLAN hatch sits 6622..16140 mm from the nearest legend text. That is the
    measured reason the meaning travels by PATTERN and never by proximity --
    the nearest text to a plan hatch is routinely a different tower's legend,
    which is the mispairing findings.md #6 observed at 5000 mm+.
  * test9 is THREE tower plans on one sheet, each with its own legend block,
    and the SAME pattern means different things per block: ZIGZAG is
    "T.O.S. +50MM." in one, "COMPENSATORY STRIP." in another, "TOS. +6250."
    in the third. A whole-sheet read therefore REFUSES those patterns loudly
    (two meanings -> no proposal, a note instead) rather than picking one.
    Only ASPHALT survives ambiguity AND the one-layer rule on test9: its 9
    plan hatches all sit on PI_SHEAR WALL CUTOUT, and the legend calls it
    "CUTOUT FOR DOOR ABOVE".

The result is PROPOSED into the override dialog, never applied silently: a
proposal overrides the name-convention default for its layer, the row is
marked with the legend text that drove it, and the user can still change it.

THE SIGN QUESTION IS OPEN. Every step value on test9 is "+" (the VIN_LEVEL
spot levels read +50, +400, +950, +6250, +6450 -- all raised), and a plan
cannot say what the parent slab's own level is, so "+" cannot be proven to
mean fold-up rather than drop relative to its parent. Step proposals
therefore go to CATEGORY_FOLD whatever the sign, and findings.md records the
question instead of this module guessing at it.

Revit-free, like fold_plan and foundation_plan, so all of it runs offline.
"""

import math
import re

from . import config
from .classify.layers import CATEGORY_CUTOUT, CATEGORY_FOLD

# The meanings this module can act on. "step" carries a value for the fold
# machinery (the max-step threshold still decides step-vs-storey downstream);
# "cutout" feeds the cutout/opening machinery; "other" is kept verbatim and
# only ever reported.
KIND_STEP = "step"
KIND_CUTOUT = "cutout"
KIND_OTHER = "other"

# A legend row's text. test9 writes every entry "HATCH INDICATE ..."; the one
# near-miss in the corpus ("*A- INDICATE 20mm CAMBER TO BE PROVIDED IN BEAM")
# lacks the HATCH prefix and is correctly not a legend row.
_LEGEND_TEXT = re.compile(r"HATCH\s+INDICATE", re.IGNORECASE)

# T.O.S. in all the spellings test9 uses: "T.O.S. +50MM.", "T.O.S. +400MM.",
# "TOS. +6250." -- dots optional, MM optional, sign optional (default +).
_STEP_VALUE = re.compile(
    r"\bT\.?\s*O\.?\s*S\.?\s*([+-])?\s*(\d+(?:\.\d+)?)\s*(?:MM)?\b",
    re.IGNORECASE)

_CUTOUT_WORD = re.compile(r"\bCUT[\s-]*OUT\b", re.IGNORECASE)

# The swatch size band, drawn between test9's swatches (807x484, 1001x601,
# 1100x400) and its nearest non-swatches (83x83 level markers, 600x75 and
# 600x125 wall slivers below; plan hatches from 500x700 up are excluded by
# never sitting within reach of a legend text, not by size).
_SWATCH_MIN_SIDE_MM = 200.0
_SWATCH_MAX_SIDE_MM = 1500.0

# How far a legend text may sit from its swatch's centre. Measured pairs are
# 657..947 mm; the nearest PLAN hatch to any legend text is 6622 mm away, so
# 2500 keeps a 2.6x margin on both sides of the band it separates.
_REACH_MM = 2500.0


def read(regions, texts, reach_mm=None):
    """[{pattern, layer, meaning, kind, value_mm, evidence, swatch}] -- one
    entry per PAIRED legend row, in the texts' own order.

    `regions` and `texts` are the reader's output after the transform: region
    points in internal feet, text anchors in `point_internal` (a text that
    never got one falls back to `point`, which is what the offline tests
    hand in). A row pairs by MUTUAL nearest within reach -- see the module
    docstring for the measured margins that make mutual necessary.

    `swatch` is the paired RegionRecord itself, so `propose` can tell the
    demonstration swatches apart from the plan hatches that inherit the
    meaning. Everything else in the entry is plain data.
    """
    reach = config.mm_to_ft(_REACH_MM if reach_mm is None else float(reach_mm))
    labels = [text for text in (texts or [])
              if _LEGEND_TEXT.search(getattr(text, "text", None) or "")]
    swatches = [region for region in (regions or []) if _swatch_sized(region)]
    if not labels or not swatches:
        return []

    nearest_swatch = {}                      # label index -> (gap, swatch index)
    for label_index, label in enumerate(labels):
        anchor = _anchor(label)
        if anchor is None:
            continue
        best = None
        for swatch_index, region in enumerate(swatches):
            gap = _dist(anchor, _centre(region))
            if gap > reach:
                continue
            if best is None or gap < best[0]:
                best = (gap, swatch_index)
        if best is not None:
            nearest_swatch[label_index] = best

    nearest_label = {}                       # swatch index -> label index
    for swatch_index, region in enumerate(swatches):
        centre = _centre(region)
        best = None
        for label_index, label in enumerate(labels):
            anchor = _anchor(label)
            if anchor is None:
                continue
            gap = _dist(anchor, centre)
            if gap > reach:
                continue
            if best is None or gap < best[0]:
                best = (gap, label_index)
        if best is not None:
            nearest_label[swatch_index] = best[1]

    entries = []
    for label_index, label in enumerate(labels):
        paired = nearest_swatch.get(label_index)
        if paired is None:
            continue
        gap, swatch_index = paired
        if nearest_label.get(swatch_index) != label_index:
            continue                         # not mutual: no pair, no guess
        region = swatches[swatch_index]
        meaning = " ".join((label.text or "").split())
        kind, value = _parse_meaning(meaning)
        width, height = _size_mm(region)
        entries.append({
            "pattern": region.pattern,
            "layer": region.layer_key,
            "meaning": meaning,
            "kind": kind,
            "value_mm": value,
            "evidence": "'{0}' {1:.0f} mm from a {2:.0f}x{3:.0f} {4} swatch "
                        "on {5}".format(meaning, gap * config.MM_PER_FT,
                                        width, height, region.pattern,
                                        region.layer_key),
            "swatch": region,
        })
    return entries


def propose(entries, regions):
    """Translate legend entries into per-LAYER category proposals.

    Returns {"mapping": {layer: category}, "rows": {layer: note},
    "reports": [...], "notes": [...]}. `mapping` is what overrides the
    name-convention default in the dialog; `rows` is the marker text for each
    proposed row; `reports` are the agreed report-only meanings (kind
    "other", kept verbatim); `notes` name every refusal and why.

    The rules, each carrying its measured reason:

      * AMBIGUITY IS REFUSED LOUDLY. Two different meanings for one pattern
        -> no proposal for that pattern, a note instead. test9's three tower
        legends give ZIGZAG three meanings and STARS two; a whole-sheet read
        that picked one would silently apply the wrong tower's step to the
        other two.
      * ONE LAYER OR NOTHING. The proposal is per LAYER (that is what the
        dialog maps), so every PLAN hatch of the pattern must sit on one
        layer. AR-CONC fails this on test9 (26 on PI_COLUMN HATCH, 8 on
        PI_RETAINING WALL HATCH); ASPHALT passes (9, all on
        PI_SHEAR WALL CUTOUT).
      * A PATTERN NOBODY USES proposes nothing. test9's STARS and ANSI37
        exist only as their own swatches -- there is no plan hatch to
        inherit the meaning, so there is nothing to route.
      * STEP -> CATEGORY_FOLD, whatever the sign, because the drawing cannot
        prove which sign means fold-up (module docstring); CUTOUT ->
        CATEGORY_CUTOUT; OTHER -> report-only, never a category.
    """
    out = {"mapping": {}, "rows": {}, "reports": [], "notes": []}
    agreed = _agreed(entries, out["notes"])
    swatch_ids = set(id(entry["swatch"]) for entry in (entries or []))
    categories = {KIND_STEP: CATEGORY_FOLD, KIND_CUTOUT: CATEGORY_CUTOUT}
    for pattern, entry in agreed:
        if entry["kind"] == KIND_OTHER:
            out["reports"].append("pattern {0} notes {1!r} (report only)"
                                  .format(pattern, entry["meaning"]))
            continue
        layers_used = set(region.layer_key for region in (regions or [])
                          if region.pattern == pattern
                          and id(region) not in swatch_ids)
        if not layers_used:
            out["notes"].append(
                "pattern {0} appears only in the legend -- no plan hatch "
                "carries it, nothing to route".format(pattern))
            continue
        if len(layers_used) > 1:
            out["notes"].append(
                "pattern {0} sits on {1} layers ({2}): a per-layer proposal "
                "cannot carry it".format(pattern, len(layers_used),
                                         ", ".join(sorted(layers_used))))
            continue
        layer = layers_used.pop()
        category = categories[entry["kind"]]
        if layer in out["mapping"] and out["mapping"][layer] != category:
            out["notes"].append(
                "layer {0} is claimed as both {1} and {2} by different "
                "patterns: neither proposal stands".format(
                    layer, out["mapping"][layer], category))
            del out["mapping"][layer]
            del out["rows"][layer]
            continue
        out["mapping"][layer] = category
        out["rows"][layer] = "proposed as {0} -- {1}".format(
            category, entry["evidence"])
    return out


def legend_steps(entries, max_step_mm=None):
    """({pattern: value_mm}, notes) -- the step DEPTH each pattern's plan
    hatches inherit, for the fold machinery.

    Values keep their sign as drawn (+50 is the drawing's raised T.O.S.; the
    open sign question lives in the module docstring). The magnitude runs
    through the SAME storey threshold `fold_plan.plan_steps` applies --
    config's `max_step_mm`, the dialog's own knob -- so test9's +6250 is
    refused and named here exactly as a 6250 step note would be there.

    Wiring these depths end-to-end into placed slabs is the P2-on-slabs
    remainder recorded in task_plan.md; this accessor is the seam it will
    read from.
    """
    limit = float(config.DEFAULTS["max_step_mm"] if max_step_mm is None
                  else max_step_mm)
    notes = []
    out = {}
    for pattern, entry in _agreed(entries, notes):
        if entry["kind"] != KIND_STEP:
            continue
        value = entry["value_mm"]
        if abs(value) > limit:
            # NOT a step: a different storey. Same refusal, same wording
            # stance as fold_plan -- named, never silently dropped.
            notes.append(
                "{0:.0f} mm is a storey, not a step (over {1:.0f} mm): "
                "pattern {2} proposes no depth".format(abs(value), limit,
                                                       pattern))
            continue
        out[pattern] = value
    return out, notes


def _agreed(entries, notes):
    """[(pattern, entry)] where every entry of the pattern says the same
    thing; a pattern whose entries disagree lands in `notes` instead.

    Agreement is (kind, value) -- and for report-only meanings the text
    itself, normalised for case and whitespace, because the text IS the
    meaning there. test9's SOLID fails even that: its three towers write
    three different termination notes.
    """
    by_pattern = {}
    order = []
    for entry in (entries or []):
        key = entry["pattern"]
        if key not in by_pattern:
            order.append(key)
        by_pattern.setdefault(key, []).append(entry)
    agreed = []
    for pattern in order:
        rows = by_pattern[pattern]
        meanings = set(_meaning_key(entry) for entry in rows)
        if len(meanings) > 1:
            notes.append(
                "pattern {0} means {1} different things ({2}): no proposal "
                "for it".format(pattern, len(meanings), " / ".join(
                    sorted(repr(entry["meaning"]) for entry in rows))))
            continue
        agreed.append((pattern, rows[0]))
    return agreed


def _meaning_key(entry):
    if entry["kind"] == KIND_OTHER:
        normalised = " ".join(entry["meaning"].upper().split()).rstrip(".")
        return (KIND_OTHER, normalised)
    return (entry["kind"], entry["value_mm"])


def _parse_meaning(meaning):
    """(kind, value_mm) for one legend text.

    A T.O.S. value is the strongest signal -- it carries the number the step
    machinery needs -- so it is read first; the cutout keyword second; and
    anything else is kept verbatim as report-only rather than dropped.
    """
    step = _STEP_VALUE.search(meaning)
    if step:
        sign = -1.0 if step.group(1) == "-" else 1.0
        return KIND_STEP, sign * float(step.group(2))
    if _CUTOUT_WORD.search(meaning):
        return KIND_CUTOUT, None
    return KIND_OTHER, None


def _swatch_sized(region):
    points = getattr(region, "points", None) or []
    if len(points) < 3:
        return False
    width, height = _size_mm(region)
    return (_SWATCH_MIN_SIDE_MM <= width <= _SWATCH_MAX_SIDE_MM
            and _SWATCH_MIN_SIDE_MM <= height <= _SWATCH_MAX_SIDE_MM)


def _size_mm(region):
    xs = [point[0] for point in region.points]
    ys = [point[1] for point in region.points]
    return ((max(xs) - min(xs)) * config.MM_PER_FT,
            (max(ys) - min(ys)) * config.MM_PER_FT)


def _centre(region):
    xs = [point[0] for point in region.points]
    ys = [point[1] for point in region.points]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _anchor(text):
    point = getattr(text, "point_internal", None) or getattr(text, "point",
                                                             None)
    if point is None:
        return None
    return (point[0], point[1])


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])

# -*- coding: utf-8 -*-
"""Match the names in a schedule to the names in a model. No Revit.

A schedule says ``Foundation``. The model says ``00 Ground Lvl.``. Neither is
wrong and no amount of exact matching will join them, and this is the single
most common reason a workbook that is perfectly correct will not build.

It lives here, away from Revit, because it is the piece most worth arguing with:
every rule below is a judgement about what two names have in common, and a
judgement nobody can run a test against is a guess. The Revit side of it is a
dozen lines in :mod:`anongee_toolkit.structural.levels` that hand this a list of
names and act on what comes back.

Four passes, loosening in order, and **each has to be unambiguous before it is
accepted**. A guess that quietly puts a foundation on the second floor is far
worse than a message naming the three levels it could have meant.
"""

__version__ = "0.1.0"

#: Words that say what a level *is* rather than which one it is. Dropped before
#: comparing, so "00 Ground Lvl." and "Ground Level" can meet in the middle.
LEVEL_NOISE = ("level", "lvl", "storey", "story", "floor", "flr",
               "elevation", "elev", "el", "ffl", "sfl", "tos")


def fold(text):
    """Lowercase, alphanumerics only -- the shape names are compared in."""
    if text is None:
        return ""
    return "".join(ch.lower() for ch in str(text) if ch.isalnum())


def significant(text, noise=LEVEL_NOISE):
    """The name with its ordinal and its noise words taken off.

    ``"00 Ground Lvl."`` and ``"Ground Level"`` both come out as ``"ground"``.
    The leading number goes because a model numbers its levels and a schedule
    usually does not, and the numbering is the model's own convention rather
    than part of the name.
    """
    cleaned = []
    for char in str(text or ""):
        cleaned.append(char if char.isalnum() else " ")
    words = [word.lower() for word in "".join(cleaned).split()]
    return "".join(word for word in words
                   if word not in noise and not word.isdigit())


def ordinal(text, noise=LEVEL_NOISE):
    """Which storey a name is about, or ``None`` when it does not say.

    ``"Level 1"``, ``"L1"`` and ``"01 1st Floor Lvl."`` are all storey 1, which
    matters because the first two have nothing left once the noise words and the
    ordinal come off -- :func:`significant` returns an empty string for them, and
    an empty string cannot be matched against anything without matching
    everything.

    Every number in the name has to agree, so ``"01 1st Floor"`` reads as 1 and
    a name carrying two different numbers reads as neither. Written without
    ``re``: the engine ships a partial stdlib and does not have it (§12.9.3).
    """
    numbers = []
    digits = []
    for char in str(text or "") + " ":
        if char.isdigit():
            digits.append(char)
        elif digits:
            numbers.append(int("".join(digits)))
            digits = []
    if not numbers:
        return None
    first = numbers[0]
    return first if all(number == first for number in numbers) else None


def resolve_name(candidates, wanted, noise=LEVEL_NOISE):
    """``(matched name, note)`` -- which candidate *wanted* means.

    ``note`` is ``None`` on an exact match and otherwise says how the match was
    reached, or why none was: a match whose reasoning the user cannot see is a
    match they cannot check.
    """
    if not wanted:
        return None, "nothing named"
    if not candidates:
        return None, "the model has none"

    for name in candidates:
        if name == wanted:
            return name, None

    target = fold(wanted)
    matches = [n for n in candidates if fold(n) == target]
    if len(matches) == 1:
        return matches[0], "matched '{0}' ignoring case and spacing".format(
            matches[0])
    if len(matches) > 1:
        return None, _ambiguous(wanted, matches)

    target = significant(wanted, noise)
    if target:
        matches = [n for n in candidates if significant(n, noise) == target]
        if len(matches) == 1:
            return matches[0], "matched '{0}'".format(matches[0])
        if len(matches) > 1:
            return None, _ambiguous(wanted, matches)

        # One name contained in the other. Short fragments are excluded
        # because "1" inside "Level 1" and "Level 10" alike would match
        # everything and mean nothing.
        matches = [n for n in candidates
                   if significant(n, noise)
                   and (target in significant(n, noise)
                        or significant(n, noise) in target)]
        if len(matches) == 1:
            return matches[0], "matched '{0}' loosely".format(matches[0])
        if len(matches) > 1:
            return None, _ambiguous(wanted, matches)

    # Storey number. This is what catches "Level 1" against "01 1st Floor
    # Lvl." -- both are storey 1, and neither has anything left to compare
    # once the noise words come off.
    wanted_storey = ordinal(wanted, noise)
    if wanted_storey is not None:
        matches = [n for n in candidates
                   if ordinal(n, noise) == wanted_storey]
        if len(matches) == 1:
            return matches[0], "matched '{0}' by storey number".format(
                matches[0])
        if len(matches) > 1:
            return None, _ambiguous(wanted, matches)

    return None, "nothing in the model resembles '{0}'".format(wanted)


def _ambiguous(wanted, matches):
    return "'{0}' could be {1} — rename one, or map it explicitly".format(
        wanted, " or ".join("'{0}'".format(name) for name in sorted(matches)))


def build_name_map(candidates, wanted_names, overrides=None,
                   noise=LEVEL_NOISE):
    """``({wanted: matched}, notes, missing)`` for a whole schedule's worth.

    *overrides* is an explicit ``{schedule name: model name}``, and it wins over
    every pass above: when someone has written down what a name means, guessing
    is not an improvement on being told.

    A mapping pointing at a name the model does not have is a different matter.
    That is not being told, it is being told something stale -- levels get
    renamed and the sheet does not follow -- so it is reported and then the
    passes run anyway. Blocking a run on a mapping that has simply gone out of
    date, when the name it was written for is sitting right there, helps nobody.
    """
    overrides = overrides or {}
    available = list(candidates)
    resolved = {}
    notes = []
    missing = []

    for wanted in sorted(set(name for name in wanted_names if name)):
        override = overrides.get(wanted)
        if override and override in available:
            resolved[wanted] = override
            notes.append("{0} → {1} (mapped)".format(wanted, override))
            continue

        matched, note = resolve_name(available, wanted, noise)
        if override:
            stale = ("{0}: mapped to '{1}', which this model does not have"
                     .format(wanted, override))
            if matched is None:
                missing.append("{0} — and {1}".format(stale, note))
                continue
            notes.append("{0}; matched '{1}' instead".format(stale, matched))
            resolved[wanted] = matched
            continue
        if matched is None:
            missing.append("{0}: {1}".format(wanted, note))
        else:
            resolved[wanted] = matched
            if note:
                notes.append("{0} → {1}".format(wanted, note))
    return resolved, notes, missing


# ---------------------------------------------------------------------------
# Grid crossings — also pure, for the same reason
# ---------------------------------------------------------------------------

#: Two grids closer to parallel than this do not cross usefully: below it the
#: intersection runs off to somewhere arithmetically real and architecturally
#: nonsense.
MIN_CROSS = 1e-6


def cross_segments(first, second):
    """``((x, y), note)`` where two 2-D segments' infinite lines cross.

    Infinite lines rather than the drawn segments, because a grid bubble stops
    where the drawing needed it to and a footing can perfectly well sit on the
    crossing of two grids whose drawn lengths never reach each other.
    """
    (x1, y1), (x2, y2) = first
    (x3, y3), (x4, y4) = second
    dx1, dy1 = x2 - x1, y2 - y1
    dx2, dy2 = x4 - x3, y4 - y3

    denominator = dx1 * dy2 - dy1 * dx2
    if abs(denominator) < MIN_CROSS:
        return None, "the two grids are parallel"

    t = ((x3 - x1) * dy2 - (y3 - y1) * dx2) / denominator
    return (x1 + t * dx1, y1 + t * dy1), None

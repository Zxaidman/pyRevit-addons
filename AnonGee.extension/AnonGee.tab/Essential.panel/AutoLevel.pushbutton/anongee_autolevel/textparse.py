# -*- coding: utf-8 -*-
"""Smart elevation detection — turn drawing text into level candidates.

The scanner is hand-rolled on purpose. §12.9.3 of the brand guidelines lists
``re`` as missing from the CPython 3 engine's stripped stdlib, and this module
runs inside that engine, so nothing here may import it. Character scanning is
also easier to reason about for the shapes that actually turn up on structural
drawings::

    FFL +3.500          TOS -1.200          ± 0.00
    LVL. +3500          EL. 3.50 M          RL 100.500
    SECOND FLOOR (+7.000)                   TERRACE LVL +14'-6"

Two things make the detection "smart" rather than a regex sweep:

  * **Unit inference over the whole set.** A bare ``3.500`` is 3.5 m or 3500 mm
    depending on the drawing. One text can't tell you; twelve can — the reading
    whose storey-to-storey deltas land in the 1.5–9 m band wins.
  * **Position cross-check.** When the texts carry drawing coordinates, the
    written elevations must climb in the same order as the text positions and
    at a constant scale. A text that disagrees with its neighbours is flagged
    instead of silently creating a level in the wrong place.
"""

DIGITS = "0123456789"
SIGNS = "+-±−"          # + - ± − (unicode minus)
MINUS_SIGNS = "-−"
SEPARATORS = ".,"
# Drawing text is full of non-breaking spaces — CAD editors emit them between
# a level word and its value. They are whitespace here, exactly like a space.
SPACES = " \t\u00a0"
DASHES = "-–—"
NAME_STRIP = SPACES + ":;" + DASHES + "_.,()[]{}<>|/\\\"'*=~"

MM_PER_M = 1000.0
MM_PER_CM = 10.0
MM_PER_FT = 304.8
MM_PER_IN = 25.4

# Unit suffixes written after the number. Longest first — "mm" must beat "m".
UNIT_TOKENS = (
    ("mm", MM_PER_M / 1000.0),
    ("cm", MM_PER_CM),
    ("m", MM_PER_M),
    ("ft", MM_PER_FT),
    ("in", MM_PER_IN),
)

UNIT_FACTORS = {
    # "ftin" is not a unit anyone writes — it is the marker for a run the
    # scanner has already resolved to millimetres (12'-6" and friends), so its
    # factor is 1 and it never gets converted twice.
    "ftin": 1.0,
    "mm": 1.0,
    "cm": MM_PER_CM,
    "m": MM_PER_M,
    "ft": MM_PER_FT,
    "in": MM_PER_IN,
}

# Words that mean "this text is about a height". Hitting one is the single
# strongest confidence signal a line can carry.
LEVEL_WORDS = (
    "FFL", "SFL", "SSL", "FGL", "TOS", "TOC", "TOB", "TOW", "BOS", "USL",
    "LVL", "LEVEL", "LEVELS", "EL", "ELEV", "ELEVATION", "RL", "FL", "GL",
    "FLOOR", "STOREY", "STORY", "SLAB", "DECK", "PLINTH", "TERRACE", "ROOF",
    "PARAPET", "BASEMENT", "MEZZANINE", "PODIUM", "STILT", "GROUND", "GRD",
    "CEILING", "COPING", "LANDING", "SILL", "SOFFIT", "DATUM", "PLATFORM",
)

# Short floor codes that name a storey without spelling it out.
FLOOR_CODES = (
    "GF", "FF", "SF", "TF", "LG", "UG", "GRD", "BF", "RF", "TR", "PH",
    "B1", "B2", "B3", "B4", "L1", "L2", "L3", "L4", "L5",
)


class Candidate(object):
    """One detected level: a name, an elevation in millimetres, and why."""

    __slots__ = ("name", "elevation_mm", "raw", "confidence", "reasons",
                 "source", "x", "y", "unit", "explicit_unit", "signed",
                 "position_mm", "merged")

    def __init__(self, name, elevation_mm, raw="", confidence=0, reasons=None,
                 source="", x=None, y=None, unit=None, explicit_unit=False,
                 signed=False, position_mm=None):
        self.name = name
        self.elevation_mm = elevation_mm
        self.raw = raw
        self.confidence = confidence
        self.reasons = list(reasons or [])
        self.source = source
        self.x = x
        self.y = y
        self.unit = unit
        self.explicit_unit = explicit_unit
        self.signed = signed
        self.position_mm = position_mm      # elevation implied by drawing y
        self.merged = 1                     # how many texts agreed on this one

    def __repr__(self):                                       # pragma: no cover
        return "Candidate({0!r}, {1:.1f}mm, {2}%)".format(
            self.name, self.elevation_mm, self.confidence)


class DetectionResult(object):
    """Everything one scan produced, plus the notes to show the user."""

    __slots__ = ("candidates", "unit", "unit_reason", "notes", "rejected",
                 "scanned")

    def __init__(self):
        self.candidates = []
        self.unit = None
        self.unit_reason = ""
        self.notes = []
        self.rejected = 0
        self.scanned = 0


# ── text cleanup ───────────────────────────────────────────────────────────

def strip_mtext_codes(text):
    """Drop DXF MTEXT formatting so the scanner sees plain characters.

    MTEXT arrives as ``{\\fArial|b0|i0;FFL \\P+3.500}``: brace groups carry the
    formatting, ``\\P`` is a paragraph break, and ``\\f``/``\\H``/``\\C`` style
    codes run until a semicolon. Everything else survives untouched.
    """
    if not text:
        return ""
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt in "Pp":
                out.append("\n")
                i += 2
                continue
            if nxt in "fFhHcCqQwWtTaA":
                # formatting run — skip to the terminating semicolon
                j = i + 2
                while j < n and text[j] != ";":
                    j += 1
                i = j + 1
                continue
            if nxt in "{}\\":
                out.append(nxt)
                i += 2
                continue
            i += 2
            continue
        if ch in "{}":
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def split_lines(text):
    """Split a text blob into candidate lines, MTEXT codes already removed."""
    cleaned = strip_mtext_codes(text)
    lines = []
    for chunk in cleaned.replace("\r", "\n").split("\n"):
        chunk = chunk.strip()
        if chunk:
            lines.append(chunk)
    return lines


def _clean_name(text):
    """Trim punctuation noise off a name and collapse inner whitespace."""
    parts = []
    for token in text.split():
        token = token.strip(NAME_STRIP)
        if token:
            parts.append(token)
    return " ".join(parts)


def _words(text):
    """Uppercase alphabetic words, punctuation removed — for keyword tests."""
    out = []
    current = []
    for ch in text.upper():
        if ch.isalpha():
            current.append(ch)
        else:
            if current:
                out.append("".join(current))
                current = []
    if current:
        out.append("".join(current))
    return out


def has_level_word(text):
    """True when the line names a height (FFL, LVL, TERRACE, ...)."""
    words = _words(text)
    for word in words:
        if word in LEVEL_WORDS:
            return True
    return False


def has_floor_code(text):
    """True when the line carries a short storey code (GF, 2F, B1, ...)."""
    for word in _words(text):
        if word in FLOOR_CODES:
            return True
    upper = text.upper()
    for i, ch in enumerate(upper):
        if ch in DIGITS and i + 1 < len(upper) and upper[i + 1] == "F":
            after = upper[i + 2] if i + 2 < len(upper) else " "
            if not after.isalpha():
                return True
    return False


# ── number scanning ────────────────────────────────────────────────────────

class _Number(object):
    __slots__ = ("start", "end", "raw", "magnitude", "negative", "signed",
                 "unit", "decimals", "letter_prefix", "dimension_pair")

    def __init__(self):
        self.start = 0
        self.end = 0
        self.raw = ""
        self.magnitude = 0.0
        self.negative = False
        self.signed = False
        self.unit = None
        self.decimals = 0
        self.letter_prefix = False
        self.dimension_pair = False


def _read_unsigned(text, i):
    """Read ``digits[.,digits]`` at *i*. Returns (value, decimals, end) or None.

    A comma is read as a decimal point, not a thousands separator: level marks
    write ``+3,500`` for three and a half metres far more often than they write
    three thousand five hundred of anything.
    """
    n = len(text)
    start = i
    whole = []
    while i < n and text[i] in DIGITS:
        whole.append(text[i])
        i += 1
    frac = []
    if i < n and text[i] in SEPARATORS and i + 1 < n and text[i + 1] in DIGITS:
        i += 1
        while i < n and text[i] in DIGITS:
            frac.append(text[i])
            i += 1
    if not whole and not frac:
        return None
    if not whole:
        whole = ["0"]
    if i == start:
        return None
    value = float("".join(whole))
    if frac:
        value += float("".join(frac)) / (10.0 ** len(frac))
    return value, len(frac), i


def _read_unit(text, i):
    """Read a trailing unit word at *i*. Returns (unit, end) or (None, i)."""
    n = len(text)
    j = i
    while j < n and text[j] in SPACES:
        j += 1
    lowered = text.lower()
    for token, _factor in UNIT_TOKENS:
        end = j + len(token)
        if lowered[j:end] == token:
            after = text[end] if end < n else " "
            if not after.isalpha():
                return token, end
    return None, i


def _read_feet_inches(text, i, feet_value):
    """Read the inches part of ``12'-6 1/2"``. Returns (mm, end) or None."""
    n = len(text)
    j = i
    while j < n and text[j] in SPACES + DASHES:
        j += 1
    inches = 0.0
    read = _read_unsigned(text, j)
    if read is not None:
        inches, _decimals, j = read
        # optional vulgar fraction: 6 1/2"
        k = j
        while k < n and text[k] in SPACES + "-":
            k += 1
        numerator = _read_unsigned(text, k)
        if numerator is not None and numerator[2] < n and text[numerator[2]] == "/":
            denominator = _read_unsigned(text, numerator[2] + 1)
            if denominator is not None and denominator[0]:
                inches += numerator[0] / denominator[0]
                j = denominator[2]
    while j < n and text[j] in SPACES:
        j += 1
    if j < n and text[j] in "\"”″":
        j += 1
    elif read is None:
        return feet_value * MM_PER_FT, i
    return feet_value * MM_PER_FT + inches * MM_PER_IN, j


def scan_numbers(text):
    """Every number-looking run in *text*, in order, with its context flags."""
    numbers = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        signed = False
        negative = False
        start = i
        if ch in SIGNS:
            j = i + 1
            while j < n and text[j] in SPACES:
                j += 1
            if j < n and (text[j] in DIGITS or (text[j] in SEPARATORS and
                                                j + 1 < n and text[j + 1] in DIGITS)):
                signed = True
                negative = ch in MINUS_SIGNS
                i = j
            else:
                i += 1
                continue
        elif ch not in DIGITS:
            i += 1
            continue

        read = _read_unsigned(text, i)
        if read is None:
            i += 1
            continue
        magnitude, decimals, end = read

        number = _Number()
        number.start = start
        number.signed = signed
        number.negative = negative
        number.decimals = decimals

        # feet-and-inches beats every other reading of the same run
        feet_end = end
        while feet_end < n and text[feet_end] in SPACES:
            feet_end += 1
        if feet_end < n and text[feet_end] in "'’′":
            converted = _read_feet_inches(text, feet_end + 1, magnitude)
            if converted is not None:
                millimetres, end = converted
                number.magnitude = millimetres
                number.unit = "ftin"
                number.end = end
                number.raw = text[start:end].strip()
                number.letter_prefix = _letter_before(text, start)
                numbers.append(number)
                i = end
                continue

        unit, end_with_unit = _read_unit(text, end)
        if unit is not None:
            end = end_with_unit
        number.magnitude = magnitude
        number.unit = unit
        number.end = end
        number.raw = text[start:end].strip()
        number.letter_prefix = _letter_before(text, start)
        number.dimension_pair = _dimension_neighbour(text, start, end)
        numbers.append(number)
        i = end
    return numbers


def _letter_before(text, start):
    """True when the number is glued to a letter — ``C1``, ``M20``, ``B2``."""
    j = start - 1
    while j >= 0 and text[j] in SIGNS:
        j -= 1
    return j >= 0 and text[j].isalpha()


def _dimension_neighbour(text, start, end):
    """True for the ``400x400`` / ``230X450`` shape — a size, not a height."""
    if end < len(text) and text[end] in "xX×":
        return True
    j = start - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    return j >= 0 and text[j] in "xX×"


# ── per-line parsing ───────────────────────────────────────────────────────

def _score_number(number, keyword, floor_code):
    """Rank the numbers on a line so the elevation beats the room number."""
    score = 0
    if number.signed:
        score += 40
    if number.unit is not None:
        score += 25
    if number.decimals in (2, 3):
        score += 20
    elif number.decimals == 1:
        score += 5
    if keyword:
        score += 10
    if floor_code:
        score += 2
    if number.letter_prefix:
        score -= 45
    if number.dimension_pair:
        score -= 60
    if number.magnitude == 0.0:
        score += 15                 # "±0.00" is a level mark almost every time
    return score


def parse_line(text, unit_hint=None, require_evidence=True, source=""):
    """Parse one line into a raw candidate (elevation still in drawing units).

    ``elevation_mm`` is only final once :func:`detect` has settled the unit for
    the whole set; until then it carries the magnitude as written, and ``unit``
    records whether the text said which unit that was.
    """
    line = text.strip()
    if not line:
        return None
    numbers = scan_numbers(line)
    if not numbers:
        return None

    keyword = has_level_word(line)
    floor_code = has_floor_code(line)

    best = None
    best_score = None
    for number in numbers:
        score = _score_number(number, keyword, floor_code)
        if best_score is None or score > best_score:
            best, best_score = number, score
    if best is None:
        return None
    if best.dimension_pair or (best.letter_prefix and not best.signed):
        return None

    # Evidence gate — without it every drawing number becomes a level.
    if require_evidence and not (best.signed or best.unit or keyword
                                 or best.decimals >= 2):
        return None

    magnitude = best.magnitude
    if best.negative:
        magnitude = -magnitude

    name = _clean_name(line[:best.start] + " " + line[best.end:])

    reasons = []
    confidence = 5
    if keyword:
        confidence += 40
        reasons.append("level keyword")
    if best.signed:
        confidence += 20
        reasons.append("signed value")
    if best.unit is not None:
        confidence += 20
        reasons.append("explicit unit")
    if best.decimals in (2, 3):
        confidence += 10
        reasons.append("{0} decimals".format(best.decimals))
    if name:
        confidence += 10
        reasons.append("named")
    if floor_code:
        confidence += 5
        reasons.append("floor code")
    if best.letter_prefix:
        confidence -= 25
        reasons.append("glued to a letter")
    confidence = max(5, min(100, confidence))

    return Candidate(
        name=name,
        elevation_mm=magnitude,
        raw=line,
        confidence=confidence,
        reasons=reasons,
        source=source,
        unit=best.unit or unit_hint,
        explicit_unit=best.unit is not None,
        signed=best.signed,
    )


# ── unit inference ─────────────────────────────────────────────────────────

# A storey is between 1.5 m and 9 m in every building this tool will see; a
# building is under 800 m. Those two facts are enough to pick the unit.
MIN_STOREY_MM = 1500.0
MAX_STOREY_MM = 9000.0
MAX_BUILDING_MM = 800000.0
CANDIDATE_UNITS = ("mm", "m", "cm", "ft")


def _score_unit(values, unit):
    """How plausible is *unit* as the reading of these raw magnitudes?"""
    factor = UNIT_FACTORS[unit]
    converted = sorted(set(round(v * factor, 3) for v in values))
    if not converted:
        return -1.0
    span = converted[-1] - converted[0]
    if abs(converted[0]) > MAX_BUILDING_MM or abs(converted[-1]) > MAX_BUILDING_MM:
        return -1.0

    score = 0.0
    if len(converted) == 1:
        # Nothing to compare against — judge the lone value on its own merits.
        magnitude = abs(converted[0])
        if magnitude == 0.0:
            return 1.0
        if MIN_STOREY_MM * 0.2 <= magnitude <= MAX_BUILDING_MM * 0.25:
            score += 3.0
        return score

    deltas = [converted[i + 1] - converted[i] for i in range(len(converted) - 1)]
    inside = 0
    for delta in deltas:
        if MIN_STOREY_MM <= delta <= MAX_STOREY_MM:
            inside += 1
            score += 3.0
        elif delta < MIN_STOREY_MM * 0.5:
            score -= 1.5           # levels stacked implausibly close together
        elif delta > MAX_STOREY_MM * 2:
            score -= 2.0           # storeys taller than any building has
    if inside == len(deltas):
        score += 3.0
    if 0.0 < span <= MAX_BUILDING_MM * 0.5:
        score += 1.0
    return score


def infer_unit(candidates, hint=None):
    """Settle one unit for the whole detected set.

    An explicit unit written on any text wins outright — a drawing that says
    ``3.5 M`` once is telling you how to read the rest of its numbers.
    """
    explicit = {}
    for candidate in candidates:
        if candidate.explicit_unit and candidate.unit:
            explicit[candidate.unit] = explicit.get(candidate.unit, 0) + 1
    if explicit:
        best = None
        for unit, count in explicit.items():
            if best is None or count > explicit[best]:
                best = unit
        if best == "ftin":
            # A drawing that writes 12'-6" is an imperial drawing: read its
            # bare numbers as feet, not as the millimetres that run resolved to.
            return "ft", "the drawing writes feet and inches"
        return best, "{0} text(s) name their unit ({1})".format(explicit[best], best)

    if hint and hint in UNIT_FACTORS:
        return hint, "unit set to {0} by hand".format(hint)

    values = [c.elevation_mm for c in candidates]
    if not values:
        return "mm", "nothing to infer from"

    scored = []
    for unit in CANDIDATE_UNITS:
        scored.append((_score_unit(values, unit), unit))
    scored.sort(key=lambda pair: (-pair[0], CANDIDATE_UNITS.index(pair[1])))
    best_score, best_unit = scored[0]
    if best_score < 0:
        return "mm", "no reading looked plausible — defaulted to mm"
    runner_up = scored[1] if len(scored) > 1 else None
    if runner_up and abs(runner_up[0] - best_score) < 0.001:
        return best_unit, "{0} and {1} scored equally — took {0}".format(
            best_unit, runner_up[1])
    return best_unit, "storey heights read best as {0}".format(best_unit)


# ── position cross-check ───────────────────────────────────────────────────

def cross_check_positions(candidates, tolerance_ratio=0.06):
    """Flag candidates whose written value fights their position on the sheet.

    Given text positions, drawing y and true elevation are related by one
    constant — the drawing scale. Fit that constant from the median of the
    pairwise slopes (robust to the outlier we are hunting), then compare every
    candidate's implied elevation against what it says. Anything off by more
    than *tolerance_ratio* of the total height is suspect.

    Returns the number of candidates that were flagged; the offenders lose
    confidence and gain a reason.
    """
    usable = [c for c in candidates if c.y is not None]
    if len(usable) < 3:
        return 0

    slopes = []
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            dy = usable[j].y - usable[i].y
            de = usable[j].elevation_mm - usable[i].elevation_mm
            if abs(dy) > 1e-9 and abs(de) > 1e-9:
                slopes.append(de / dy)
    if not slopes:
        return 0
    slopes.sort()
    scale = slopes[len(slopes) // 2]
    if abs(scale) < 1e-12:
        return 0

    elevations = [c.elevation_mm for c in usable]
    height = max(elevations) - min(elevations)
    if height <= 0:
        return 0
    tolerance = max(height * tolerance_ratio, 50.0)

    # Anchor on the median offset so a single bad text can't drag the fit.
    offsets = sorted(c.elevation_mm - c.y * scale for c in usable)
    offset = offsets[len(offsets) // 2]

    flagged = 0
    for candidate in usable:
        implied = candidate.y * scale + offset
        candidate.position_mm = implied
        if abs(implied - candidate.elevation_mm) > tolerance:
            candidate.confidence = max(5, candidate.confidence - 35)
            candidate.reasons.append(
                "position suggests {0:.0f} mm".format(implied))
            flagged += 1
    return flagged


# ── merging ────────────────────────────────────────────────────────────────

def merge_candidates(candidates, tolerance_mm=5.0):
    """Collapse candidates that describe the same level.

    Two texts 4 mm apart are the same slab annotated twice, not two levels.
    The better-evidenced name wins; a name always beats no name.
    """
    ordered = sorted(candidates, key=lambda c: c.elevation_mm)
    merged = []
    for candidate in ordered:
        if merged and abs(candidate.elevation_mm - merged[-1].elevation_mm) <= tolerance_mm:
            kept = merged[-1]
            kept.merged += 1
            better_name = bool(candidate.name) and not kept.name
            if better_name or (candidate.confidence > kept.confidence
                               and (candidate.name or not kept.name)):
                kept.name = candidate.name or kept.name
                kept.raw = candidate.raw
                kept.reasons = candidate.reasons
            kept.confidence = min(100, max(kept.confidence, candidate.confidence) + 5)
            if "agreed by {0} texts".format(kept.merged) not in kept.reasons:
                kept.reasons.append("agreed by {0} texts".format(kept.merged))
            continue
        merged.append(candidate)
    return merged


# ── the public entry point ─────────────────────────────────────────────────

def detect(entries, unit_hint=None, require_evidence=True, merge_tolerance_mm=5.0,
           datum_offset_mm=0.0, use_positions=True):
    """Run the whole detection pipeline over a batch of texts.

    *entries* are dicts with ``text`` and optionally ``x`` / ``y`` (drawing
    coordinates) and ``source`` (where the text came from, for the UI).
    """
    result = DetectionResult()
    raw = []
    for entry in entries or []:
        text = entry.get("text") or ""
        source = entry.get("source") or ""
        for line in split_lines(text):
            result.scanned += 1
            candidate = parse_line(line, require_evidence=require_evidence,
                                   source=source)
            if candidate is None:
                result.rejected += 1
                continue
            candidate.x = entry.get("x")
            candidate.y = entry.get("y")
            raw.append(candidate)

    if not raw:
        result.unit = unit_hint or "mm"
        result.unit_reason = "no elevation text found"
        return result

    unit, reason = infer_unit(raw, unit_hint)
    result.unit = unit
    result.unit_reason = reason

    factor = UNIT_FACTORS[unit]
    for candidate in raw:
        if candidate.explicit_unit and candidate.unit:
            candidate.elevation_mm = candidate.elevation_mm * UNIT_FACTORS[candidate.unit]
        else:
            candidate.elevation_mm = candidate.elevation_mm * factor
        candidate.elevation_mm -= datum_offset_mm

    if use_positions:
        flagged = cross_check_positions(raw)
        if flagged:
            result.notes.append(
                "{0} text(s) sit where their written value says they shouldn't"
                .format(flagged))

    result.candidates = merge_candidates(raw, merge_tolerance_mm)
    result.notes.append("read {0} line(s), kept {1} level(s)".format(
        result.scanned, len(result.candidates)))
    result.notes.append(reason)
    return result


def parse_elevation_input(text, unit_hint="mm"):
    """Parse one typed elevation — the grid's inline editor uses this.

    Accepts everything the detector accepts: ``3500``, ``3.5 m``, ``+3.500``,
    ``11'-6"``, ``-1200``. A bare number means *unit_hint*.
    """
    if text is None:
        return None
    line = str(text).strip()
    if not line:
        return None
    numbers = scan_numbers(line)
    if not numbers:
        return None
    number = numbers[0]
    magnitude = number.magnitude
    if number.negative:
        magnitude = -magnitude
    unit = number.unit or unit_hint or "mm"
    if unit not in UNIT_FACTORS:
        unit = "mm"
    return magnitude * UNIT_FACTORS[unit]


def format_mm(value_mm, decimals=0):
    """Millimetres as a right-alignable string — no thousands separators."""
    if value_mm is None:
        return "—"
    if decimals <= 0:
        return "{0:.0f}".format(value_mm)
    return "{0:.{1}f}".format(value_mm, decimals)


def format_metres(value_mm):
    """Millimetres as the ``+3.500`` notation drawings actually use."""
    if value_mm is None:
        return "—"
    metres = value_mm / MM_PER_M
    sign = "+" if metres > 0 else ("-" if metres < 0 else "±")
    return "{0}{1:.3f}".format(sign, abs(metres))

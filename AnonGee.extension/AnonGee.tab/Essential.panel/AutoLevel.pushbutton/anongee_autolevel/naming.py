# -*- coding: utf-8 -*-
"""Level naming — learn the model's own convention, or render a template.

An office template arrives with levels already named the way that office names
levels: ``02 2ND FLOOR LVL.``, ``L03 - Third Floor``, ``Level 4``. A tool that
appends ``Level 12`` to that stack is making a mess someone has to clean up.

So this module reads the names that are already there, works out the pattern
including how the index is spelled, and continues it. When there is no pattern
to find — or the user would rather say it themselves — a small template
language covers the rest.

No ``re``: the CPython 3 engine ships without it (§12.9.3).
"""

DIGITS = "0123456789"

ORDINAL_WORDS = (
    "ZEROTH", "FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH",
    "SEVENTH", "EIGHTH", "NINTH", "TENTH", "ELEVENTH", "TWELFTH",
    "THIRTEENTH", "FOURTEENTH", "FIFTEENTH", "SIXTEENTH", "SEVENTEENTH",
    "EIGHTEENTH", "NINETEENTH", "TWENTIETH",
)

ROMAN_PAIRS = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
               (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
               (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


# ── index spellings ────────────────────────────────────────────────────────

def ordinal_suffix(index):
    """``ST``/``ND``/``RD``/``TH`` — with the 11–13 exception English needs."""
    if 10 <= (index % 100) <= 20:
        return "TH"
    return {1: "ST", 2: "ND", 3: "RD"}.get(index % 10, "TH")


def to_roman(index):
    if index <= 0 or index > 3999:
        return str(index)
    out = []
    remainder = index
    for value, glyph in ROMAN_PAIRS:
        while remainder >= value:
            out.append(glyph)
            remainder -= value
    return "".join(out)


def from_roman(token):
    if not token:
        return None
    total = 0
    previous = 0
    for ch in reversed(token.upper()):
        if ch not in ROMAN_VALUES:
            return None
        value = ROMAN_VALUES[ch]
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total if total > 0 else None


def _apply_case(text, case):
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "title":
        return text.title()
    return text


def _case_of(token):
    letters = [ch for ch in token if ch.isalpha()]
    if not letters:
        return "upper"
    if token.isupper():
        return "upper"
    if token.islower():
        return "lower"
    return "title"


def _split_affixes(token):
    """Peel non-alphanumeric edges off a token: ``(02.,`` -> ``(``, ``02``, ``.,``."""
    start = 0
    end = len(token)
    while start < end and not token[start].isalnum():
        start += 1
    while end > start and not token[end - 1].isalnum():
        end -= 1
    return token[:start], token[start:end], token[end:]


# ── one variable token in a name ───────────────────────────────────────────

class _IndexFormat(object):
    """How a single token spells an index, so it can be spelled again."""

    __slots__ = ("kind", "width", "case", "prefix", "suffix")

    def __init__(self, kind, width=0, case="upper", prefix="", suffix=""):
        self.kind = kind          # plain | pad | ord | word | roman
        self.width = width
        self.case = case
        self.prefix = prefix
        self.suffix = suffix

    def render(self, index):
        if self.kind == "pad":
            body = str(index).rjust(self.width, "0")
        elif self.kind == "ord":
            body = _apply_case("{0}{1}".format(index, ordinal_suffix(index)),
                               self.case)
        elif self.kind == "word":
            if 0 <= index < len(ORDINAL_WORDS):
                body = _apply_case(ORDINAL_WORDS[index], self.case)
            else:
                body = _apply_case("{0}{1}".format(index, ordinal_suffix(index)),
                                   self.case)
        elif self.kind == "roman":
            body = _apply_case(to_roman(index), self.case)
        else:
            body = str(index)
        return self.prefix + body + self.suffix


def _decode_token(token):
    """Every way *token* can be read as an index: [(value, _IndexFormat)]."""
    prefix, body, suffix = _split_affixes(token)
    if not body:
        return []
    readings = []
    upper = body.upper()

    if body.isdigit():
        value = int(body)
        if len(body) > 1 and body[0] == "0":
            readings.append((value, _IndexFormat("pad", len(body),
                                                 prefix=prefix, suffix=suffix)))
        else:
            readings.append((value, _IndexFormat("plain", prefix=prefix,
                                                 suffix=suffix)))
        return readings

    # 2ND / 12th
    digits = []
    i = 0
    while i < len(body) and body[i] in DIGITS:
        digits.append(body[i])
        i += 1
    if digits and upper[i:] in ("ST", "ND", "RD", "TH"):
        value = int("".join(digits))
        if upper[i:] == ordinal_suffix(value):
            readings.append((value, _IndexFormat("ord", case=_case_of(body),
                                                 prefix=prefix, suffix=suffix)))
            return readings

    if upper in ORDINAL_WORDS:
        readings.append((ORDINAL_WORDS.index(upper),
                         _IndexFormat("word", case=_case_of(body),
                                      prefix=prefix, suffix=suffix)))
        return readings

    # A letter glued to the number — L01, FL02, B1. The letters belong to the
    # literal part of the name; only the digits count up.
    tail = len(body)
    while tail > 0 and body[tail - 1] in DIGITS:
        tail -= 1
    head, digit_run = body[:tail], body[tail:]
    if digit_run and head and head.isalpha():
        value = int(digit_run)
        kind = "pad" if len(digit_run) > 1 and digit_run[0] == "0" else "plain"
        readings.append((value, _IndexFormat(kind, len(digit_run),
                                             prefix=prefix + head,
                                             suffix=suffix)))
        return readings

    roman = from_roman(body)
    if roman is not None and all(ch.upper() in ROMAN_VALUES for ch in body):
        readings.append((roman, _IndexFormat("roman", case=_case_of(body),
                                             prefix=prefix, suffix=suffix)))
    return readings


# ── the learned convention ─────────────────────────────────────────────────

class Convention(object):
    """A name pattern learned from the model, ready to be continued."""

    __slots__ = ("tokens", "slots", "last_index", "sample", "step")

    def __init__(self, tokens, slots, last_index, sample, step=1):
        self.tokens = tokens          # literal tokens, None where an index goes
        self.slots = slots            # {token position: _IndexFormat}
        self.last_index = last_index
        self.sample = sample
        self.step = step

    def render(self, index):
        parts = []
        for position, literal in enumerate(self.tokens):
            fmt = self.slots.get(position)
            parts.append(fmt.render(index) if fmt is not None else literal)
        return " ".join(parts)

    def next_names(self, count, start_index=None):
        start = self.last_index + self.step if start_index is None else start_index
        return [self.render(start + i * self.step) for i in range(count)]

    def describe(self):
        return "continues \"{0}\" from {1}".format(
            self.sample, self.last_index + self.step)


def learn_convention(names):
    """Infer the naming pattern from existing level names, lowest level first.

    Returns a :class:`Convention` or ``None``. The names must agree on their
    word count and on at least one word that counts up — two levels called
    ``Level 1`` and ``Level 2`` are a convention; ``Ground`` and ``Roof`` are
    not, and saying so is the honest answer.
    """
    cleaned = [name.strip() for name in names or [] if name and name.strip()]
    if len(cleaned) < 2:
        return None

    split = [name.split() for name in cleaned]
    counts = {}
    for tokens in split:
        counts[len(tokens)] = counts.get(len(tokens), 0) + 1
    best_count = None
    for count, seen in counts.items():
        if best_count is None or seen > counts[best_count] or (
                seen == counts[best_count] and count > best_count):
            best_count = count
    group = [tokens for tokens in split if len(tokens) == best_count]
    if len(group) < 2:
        return None

    literals = []
    slots = {}
    varying = []
    for position in range(best_count):
        column = [tokens[position] for tokens in group]
        if all(value == column[0] for value in column):
            literals.append(column[0])
        else:
            literals.append(None)
            varying.append((position, column))
    if not varying:
        return None

    # Each varying column must count up in step, and all of them must agree on
    # the same step and the same final index.
    resolved = []
    for position, column in varying:
        reading = _resolve_column(column)
        if reading is None:
            return None
        values, fmt = reading
        resolved.append((position, values, fmt))

    steps = set()
    finals = set()
    for _position, values, _fmt in resolved:
        steps.add(values[1] - values[0])
        finals.add(values[-1])
    if len(steps) != 1 or len(finals) != 1:
        return None
    step = steps.pop()
    if step == 0:
        return None

    for position, _values, fmt in resolved:
        slots[position] = fmt
        literals[position] = None

    convention = Convention(literals, slots, finals.pop(), cleaned[-1], step)
    return convention


def _resolve_column(column):
    """Read a varying token column as one index spelling. (values, fmt) or None."""
    per_token = [_decode_token(token) for token in column]
    if any(not readings for readings in per_token):
        return None
    for value, fmt in per_token[0]:
        values = [value]
        formats = [fmt]
        ok = True
        for readings in per_token[1:]:
            match = None
            for other_value, other_fmt in readings:
                if (other_fmt.kind == fmt.kind and other_fmt.prefix == fmt.prefix
                        and other_fmt.suffix == fmt.suffix
                        and (fmt.kind != "pad" or other_fmt.width == fmt.width)):
                    match = (other_value, other_fmt)
                    break
            if match is None:
                ok = False
                break
            values.append(match[0])
            formats.append(match[1])
        if not ok or len(values) < 2:
            continue
        step = values[1] - values[0]
        if step == 0:
            continue
        if all(values[i + 1] - values[i] == step for i in range(len(values) - 1)):
            return values, formats[0]
    return None


# ── the template language ──────────────────────────────────────────────────

TEMPLATE_TOKENS = (
    "{n}", "{nn}", "{nnn}", "{ordinal}", "{Ordinal}", "{ORDINAL}",
    "{word}", "{Word}", "{WORD}", "{roman}", "{elev_m}", "{elev_mm}",
    "{label}",
)

TEMPLATE_HELP = (
    "{n} 1 · {nn} 01 · {nnn} 001 · {ordinal} 1st · {ORDINAL} 1ST · "
    "{Word} First · {roman} I · {elev_m} 3.500 · {elev_mm} 3500 · {label}"
)


def render_template(template, index, elevation_mm=None, label=""):
    """Fill a user template. Unknown ``{tokens}`` are left exactly as typed."""
    if not template:
        return ""
    out = []
    i = 0
    n = len(template)
    while i < n:
        ch = template[i]
        if ch != "{":
            out.append(ch)
            i += 1
            continue
        close = template.find("}", i)
        if close < 0:
            out.append(template[i:])
            break
        token = template[i:close + 1]
        replacement = _template_value(token, index, elevation_mm, label)
        out.append(token if replacement is None else replacement)
        i = close + 1
    return "".join(out).strip()


def _template_value(token, index, elevation_mm, label):
    if token == "{n}":
        return str(index)
    if token == "{nn}":
        return str(index).rjust(2, "0")
    if token == "{nnn}":
        return str(index).rjust(3, "0")
    if token in ("{ordinal}", "{Ordinal}", "{ORDINAL}"):
        text = "{0}{1}".format(index, ordinal_suffix(index))
        return {"{ordinal}": text.lower(), "{Ordinal}": text.upper(),
                "{ORDINAL}": text.upper()}[token]
    if token in ("{word}", "{Word}", "{WORD}"):
        if 0 <= index < len(ORDINAL_WORDS):
            text = ORDINAL_WORDS[index]
        else:
            text = "{0}{1}".format(index, ordinal_suffix(index))
        return {"{word}": text.lower(), "{Word}": text.title(),
                "{WORD}": text.upper()}[token]
    if token == "{roman}":
        return to_roman(index)
    if token == "{elev_m}":
        if elevation_mm is None:
            return ""
        return "{0:.3f}".format(elevation_mm / 1000.0)
    if token == "{elev_mm}":
        if elevation_mm is None:
            return ""
        return "{0:.0f}".format(elevation_mm)
    if token == "{label}":
        return label or ""
    return None


# ── uniqueness ─────────────────────────────────────────────────────────────

def unique_name(base, taken, separator=" "):
    """A name Revit will accept — level names must be unique in a document."""
    name = (base or "Level").strip() or "Level"
    lowered = set(str(item).strip().lower() for item in taken or ())
    if name.lower() not in lowered:
        return name
    counter = 2
    while True:
        candidate = "{0}{1}({2})".format(name, separator, counter)
        if candidate.lower() not in lowered:
            return candidate
        counter += 1


def apply_affixes(name, prefix="", suffix="", find="", replace="",
                  case_mode="keep"):
    """Batch-rename primitive: prefix/suffix, find-replace, case."""
    text = name or ""
    if find:
        text = text.replace(find, replace or "")
    text = "{0}{1}{2}".format(prefix or "", text, suffix or "")
    if case_mode == "upper":
        text = text.upper()
    elif case_mode == "lower":
        text = text.lower()
    elif case_mode == "title":
        text = text.title()
    return text.strip()

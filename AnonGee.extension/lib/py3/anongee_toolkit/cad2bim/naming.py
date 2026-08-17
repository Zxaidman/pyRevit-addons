# -*- coding: utf-8 -*-
"""How AUTO-CREATED family types are named, and where that choice is kept.

Every builder that duplicates a type invents a name for it -- "400 X 600" for a
column, "200 THK" for a floor. Offices name their types to their own standard,
so the names come from TEMPLATES the Naming tab owns instead of being hard-coded
at each Duplicate() call.

A template is a plain format string over the sizes that type carries:

    column_rect   {b} {h}          400 x 600 column      "{b} X {h}"
    column_round  {d}              600 dia column        "{d}D"
    beam_sized    {w} {d}          300 x 600 beam        "{w} X {d}"
    beam_width    {w}              width-only beam       "{w}"
    floor         {t}              200 thick slab        "{t} THK"
    stair         {r} {t} {w} {k}  riser/tread/width/waist
    stair_waist   {k}              the stair's waist type
    footing       {t}              600 thick foundation pad
    raft          {t}              750 thick raft foundation
    level         {n} {o} {e} {label}  a storey level ({o} = 1st/2nd/3rd)
    grid          {name}           a grid line (its CAD bubble, or A/B/1/2)

Sizes reach a template already rounded to whole millimetres, so "{b} X {h}"
gives "400 X 600" and never "400.0 X 600.0". A template that references a field
that does not exist -- or is malformed -- falls back to the default rather than
failing a build halfway through, and says so through `problems()`.

Revit-free, so the templates can be unit-tested outside Revit.
"""

import re
import string

from . import prefs

DEFAULTS = {
    "column_rect": "{b} X {h}",
    "column_round": "{d}D",
    "beam_sized": "{w} X {d}",
    "beam_width": "{w}",
    "floor": "{t} THK",
    "stair": "cad2bim {r}R x {t}T x {w}W x {k}wst",
    "stair_waist": "cad2bim waist {k}",
    "footing": "PAD {t} THK",
    "raft": "RAFT {t} THK",
    "level": "CAD Level {n}",
    "grid": "{name}",
}

# what each template may refer to, for the dialog's help text and validation
FIELDS = {
    "column_rect": ("b", "h"),
    "column_round": ("d",),
    "beam_sized": ("w", "d"),
    "beam_width": ("w",),
    "floor": ("t",),
    "stair": ("r", "t", "w", "k"),
    "stair_waist": ("k",),
    "footing": ("t",),
    "raft": ("t",),
    "level": ("n", "o", "e", "label"),
    "grid": ("name",),
}

_templates = dict(DEFAULTS)
_problems = []


def apply(templates):
    """Install the Naming tab's templates. Anything absent keeps its default."""
    global _templates, _problems
    _templates = dict(DEFAULTS)
    _problems = []
    for key, value in (templates or {}).items():
        if key not in DEFAULTS:
            continue
        text = (value or "").strip()
        if text:
            _templates[key] = text


def templates():
    """The templates currently in force (a copy)."""
    return dict(_templates)


def problems():
    """Templates that could not be used, as ["column_rect: ...", ...]."""
    return list(_problems)


# fields that are TEXT, not a size, so validation feeds them something readable
_TEXT_FIELDS = ("label", "name")

# Templates whose fields TOGETHER identify the type. Drop one and two different
# members render the same name -- the second one Revit is asked for raises "The
# name is already in use for this element type" and that member is lost. The
# templates left out are unique on the field they do use ({t} thickness, {n}
# level number) or name something the drawing already made unique ({name}).
#
# `raft` requires its one field even so. A raft's thickness comes from the
# ENGINEER's note, not a formula, and since v0.68.1 a name collision is not an
# error but a silent reuse -- two rafts noted 500 and 750 rendering the same
# name would cast the second at the first one's depth with nothing said. The
# older single-field templates keep their latitude ("GENERIC SLAB" is a choice
# offices have already saved); the raft template is new, so the trap is closed
# from day one.
_MUST_USE = {
    "column_rect": ("b", "h"),
    "beam_sized": ("w", "d"),
    "stair": ("r", "t", "w", "k"),
    "raft": ("t",),
}


def _fields_used(template):
    """The field names a template refers to, format specs and all ({b:04d} -> b)."""
    used = set()
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError:
        return used                 # malformed; the format() check reports it
    for _literal, field, _spec, _conversion in parsed:
        if field:
            used.add(field.split(".")[0].split("[")[0])
    return used


def validate(key, template):
    """None when `template` is a usable name for `key`, else why it is not."""
    if key not in DEFAULTS:
        return "unknown name"
    sample = dict((field, field if field in _TEXT_FIELDS else 100)
                  for field in FIELDS[key])
    try:
        text = template.format(**sample)
    except (KeyError, IndexError, ValueError) as error:
        allowed = ", ".join("{" + f + "}" for f in FIELDS[key])
        return "{0} (use {1})".format(error, allowed)
    if not text.strip():
        return "gives an empty name"
    used = _fields_used(template)
    missing = [field for field in _MUST_USE.get(key, ()) if field not in used]
    if missing:
        return ("drops {0}, so two different sizes would get the same type "
                "name -- Revit refuses the second one".format(
                    ", ".join("{" + field + "}" for field in missing)))
    return None


def _render(key, values):
    template = _templates.get(key, DEFAULTS[key])
    try:
        text = template.format(**values).strip()
    except (KeyError, IndexError, ValueError) as error:
        message = "{0}: {1} -- using '{2}'".format(key, error, DEFAULTS[key])
        if message not in _problems:
            _problems.append(message)
        text = DEFAULTS[key].format(**values).strip()
    return text or DEFAULTS[key].format(**values)


def _mm(value):
    """A size as a whole number of millimetres ("400", not "400.0")."""
    return int(round(float(value)))


def column_type_name(b_mm, h_mm):
    return _render("column_rect", {"b": _mm(b_mm), "h": _mm(h_mm)})


def circular_column_type_name(diameter_mm):
    return _render("column_round", {"d": _mm(diameter_mm)})


def beam_type_name(width_mm, depth_mm=None):
    if depth_mm is None:
        return _render("beam_width", {"w": _mm(width_mm)})
    return _render("beam_sized", {"w": _mm(width_mm), "d": _mm(depth_mm)})


def floor_type_name(thickness_mm):
    return _render("floor", {"t": _mm(thickness_mm)})


def stair_type_name(riser_mm, tread_mm, width_mm, waist_mm):
    return _render("stair", {"r": _mm(riser_mm), "t": _mm(tread_mm),
                             "w": _mm(width_mm), "k": _mm(waist_mm)})


def stair_waist_type_name(waist_mm):
    return _render("stair_waist", {"k": _mm(waist_mm)})


def footing_type_name(thickness_mm):
    """The name for a foundation pad type.

    A pad is a floor, so its TYPE only carries a thickness -- the outline is
    per-pad sketch geometry, not part of the type. Naming a type after a plan
    size would invent one type per column, which is what "F 0 X 0 X 300" was
    telling us.
    """
    return _render("footing", {"t": _mm(thickness_mm)})


def raft_type_name(thickness_mm):
    """The name for a RAFT foundation type.

    A raft is the same Revit shape as a pad -- a foundation-slab floor whose
    type carries only a thickness -- but offices name the two differently
    ("RAFT 750 THK" beside "PAD 600 THK"), so it gets a template of its own.
    Which template a placed outline takes is decided in the Revit-free layer
    (foundation_plan's "kind"), never guessed here.
    """
    return _render("raft", {"t": _mm(thickness_mm)})


def level_name(index, elevation_mm=0.0, label=None):
    """The name for a level this run creates.

    `index` counts from 1 over the levels ADDED, `elevation_mm` is where the
    level sits, and `label` is the plan title that storey came from (empty when
    the drawing did not name it). `{o}` is the same number written as an
    ordinal, so "{o} Floor Level" gives "3rd Floor Level" and not "3th".
    """
    return _render("level", {"n": int(index), "o": ordinal(index),
                             "e": _mm(elevation_mm),
                             "label": (label or "").strip()})


def ordinal(number):
    """1 -> "1st", 2 -> "2nd", 3 -> "3rd", 11 -> "11th"."""
    value = int(number)
    if 10 <= abs(value) % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(abs(value) % 10, "th")
    return "{0}{1}".format(value, suffix)


# "00 GROUND LVL" / "01 1ST FLOOR LVL." -- a numbered level naming convention
_NUMBERED_LEVEL = re.compile(r"^\s*(\d+)(\s*[-_.:]?\s*)(.*)$")
_ORDINAL_IN_NAME = re.compile(r"\b(\d+)\s*(st|nd|rd|th)\b", re.IGNORECASE)


def next_level_names(existing_names, count):
    """Continue the MODEL's own level naming, or None when it has no pattern.

    An office template arrives with its levels already named to a convention --
    "00 GROUND LVL", "01 1ST FLOOR LVL.", "02 2ND FLOOR LVL." -- and a level
    this run adds should read like the next line of that list rather than like
    a template nobody set. The number is continued at the width it is written
    (02 -> 03), and the body is the highest-numbered existing body with its
    ordinal moved on ("2ND FLOOR LVL." -> "3RD FLOOR LVL.", in that name's own
    case).

    Returns `count` names, or None when the existing names carry no numbered
    convention to continue -- the caller then falls back to the template.
    """
    numbered = []
    for name in (existing_names or []):
        match = _NUMBERED_LEVEL.match(name or "")
        if not match:
            continue
        numbered.append((int(match.group(1)), len(match.group(1)),
                         match.group(2), match.group(3).strip()))
    if len(numbered) < 2:
        return None                 # one level is a coincidence, not a pattern
    numbered.sort(key=lambda row: row[0])
    highest = numbered[-1]
    width = max(row[1] for row in numbered)
    separator = highest[2] or " "
    # the body's ordinal need not equal the level number ("002 1ST FLOOR" on a
    # model whose ground floor is 001), so carry the OFFSET between them
    source = next((row for row in reversed(numbered)
                   if _ORDINAL_IN_NAME.search(row[3])), highest)
    match = _ORDINAL_IN_NAME.search(source[3])
    offset = (int(match.group(1)) - source[0]) if match else 0
    out = []
    for step in range(1, int(count) + 1):
        number = highest[0] + step
        out.append("{0}{1}{2}".format(
            str(number).zfill(width), separator,
            _renumber_body(source[3], number + offset)).strip())
    return out


def _renumber_body(body, number):
    """"2ND FLOOR LVL." at number 3 -> "3RD FLOOR LVL." (keeping its case)."""
    match = _ORDINAL_IN_NAME.search(body or "")
    if not match:
        return body or ""
    text = ordinal(number)
    if match.group(2).isupper():
        text = text.upper()
    return body[:match.start()] + text + body[match.end():]


def grid_name(name):
    """The name for a grid line, around whatever the drawing/convention gave.

    A grid the drawing never labelled comes in empty and goes out empty -- the
    builder skips an empty name and keeps Revit's own, so a prefix template
    must not turn an unnamed grid into a bare "G-".
    """
    base = (name or "").strip()
    if not base:
        return ""
    return _render("grid", {"name": base})


def load():
    """The saved templates from the last session, merged over the defaults."""
    saved = prefs.load().get("naming") or {}
    merged = dict(DEFAULTS)
    for key, value in saved.items():
        if key in DEFAULTS and (value or "").strip():
            merged[key] = value
    return merged


def save(templates):
    """Remember these templates for the next Revit session."""
    keep = dict((key, value) for key, value in (templates or {}).items()
                if key in DEFAULTS and (value or "").strip()
                and value != DEFAULTS[key])
    prefs.update({"naming": keep})

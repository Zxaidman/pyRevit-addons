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
    footing       {w} {l} {t}      1000 x 1200 x 300 isolated footing
    level         {n} {e} {label}  a storey level this run creates
    grid          {name}           a grid line (its CAD bubble, or A/B/1/2)

Sizes reach a template already rounded to whole millimetres, so "{b} X {h}"
gives "400 X 600" and never "400.0 X 600.0". A template that references a field
that does not exist -- or is malformed -- falls back to the default rather than
failing a build halfway through, and says so through `problems()`.

Revit-free, so the templates can be unit-tested outside Revit.
"""

from . import prefs

DEFAULTS = {
    "column_rect": "{b} X {h}",
    "column_round": "{d}D",
    "beam_sized": "{w} X {d}",
    "beam_width": "{w}",
    "floor": "{t} THK",
    "stair": "cad2bim {r}R x {t}T x {w}W x {k}wst",
    "stair_waist": "cad2bim waist {k}",
    "footing": "F {w} X {l} X {t}",
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
    "footing": ("w", "l", "t"),
    "level": ("n", "e", "label"),
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


def footing_type_name(width_mm, length_mm, thickness_mm=0.0):
    """The name for an isolated footing type (short x long x thickness)."""
    return _render("footing", {"w": _mm(width_mm), "l": _mm(length_mm),
                               "t": _mm(thickness_mm)})


def level_name(index, elevation_mm=0.0, label=None):
    """The name for a level this run creates.

    `index` counts from 1 over the levels ADDED, `elevation_mm` is where the
    level sits, and `label` is the plan title that storey came from (empty when
    the drawing did not name it).
    """
    return _render("level", {"n": int(index), "e": _mm(elevation_mm),
                             "label": (label or "").strip()})


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

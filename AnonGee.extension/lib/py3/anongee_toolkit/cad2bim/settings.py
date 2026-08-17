# -*- coding: utf-8 -*-
"""The WHOLE dialog as a plain dict, so a run can be saved and reloaded.

`prefs.py` remembers the two office conventions -- naming templates and standard
sizes. Everything else was rebuilt from defaults on every Revit session, so a
user who had tuned twenty boxes had to tune them again the next morning. This
module snapshots every named control in the window instead:

    {"schema": 2, "version": "0.67.0",
     "controls": {"tb_slab_step": "20", "chk_beams": True,
                  "cb_floor_type": "Generic 150mm"},
     "layers": {"S-COLS": "Column", ...},
     "texts":  {"S-TEXT": "Column mark", ...},
     "advanced": {"beam_heal_mm": 400.0, ...}}

Two rules make the snapshot safe to reload into a DIFFERENT model:

  * a combo is stored by its LABEL, never by ElementId -- ids do not survive a
    session, let alone another project, and a label that no longer exists simply
    leaves that combo alone;
  * anything the dialog computes for itself (previews, counts, the source name,
    the version banner) is never captured, so a reload cannot overwrite what the
    current drawing says.

Nothing here touches Revit or WPF: the script hands it plain values, which keeps
it testable and keeps the file format independent of the dialog's plumbing.
"""

import json
import os

# 2 added the OPTIONAL "advanced" section (module-constant overrides). The
# number is a statement of what a file may carry, not a gate: every reader
# here takes what it recognises and ignores the rest, so a schema-1 file loads
# unchanged (its advanced section simply reads as empty) and a schema-2 file
# in old hands restores everything but the section it does not know.
SCHEMA = 2

# Controls the dialog OWNS: read-only text it computes, or a list whose contents
# come from the drawing. Restoring these would either be a no-op or a lie.
SKIP_NAMES = frozenset((
    "version_text", "source_text", "status_text",
    "naming_saved_text", "settings_text", "storey_selection_text",
    "multistorey_preview", "stair_outline_text", "stair_floor_text",
    "layer_rows", "text_rows", "storey_rows",
    "link_version_text", "tb_active_view",
))

# Preview labels (lbl_*) and push buttons (btn_*) hold nothing worth keeping.
SKIP_PREFIXES = ("lbl_", "btn_")

# Answered by THIS drawing, not by the last one: auto-detection reads the
# storey layers and decides whether the CAD is multi-storey at all, so a saved
# tick from a different plan must not talk over it. Saved, so the file is a full
# record; simply not restored.
DETECTED_NAMES = frozenset(("chk_multistorey", "cb_boundary_layer",
                            "cb_origin_layer"))


def saveable(name):
    """True when a control's value belongs in a saved settings file."""
    if not name:
        return False
    if name in SKIP_NAMES:
        return False
    return not name.startswith(SKIP_PREFIXES)


def restorable(name):
    """True when a saved value may be put back on the dialog."""
    return saveable(name) and name not in DETECTED_NAMES


def pick_index(items, wanted):
    """Index of `wanted` in `items`, or -1.

    Combos are matched on their label, which is how a saved file survives a new
    model: an exact match first, then case-insensitively, then a unique prefix
    match so "Generic 150mm" still finds "Generic 150mm (2)" after Revit has
    renamed a duplicate. Anything ambiguous is refused rather than guessed.
    """
    if wanted is None:
        return -1
    labels = [("" if item is None else str(item)) for item in items]
    text = str(wanted)
    if text in labels:
        return labels.index(text)
    lowered = [label.lower() for label in labels]
    if text.lower() in lowered:
        return lowered.index(text.lower())
    starts = [index for index, label in enumerate(lowered)
              if label.startswith(text.lower())]
    return starts[0] if len(starts) == 1 else -1


def payload(controls, layers=None, texts=None, version="", advanced=None):
    """A complete settings dict, ready for `write()` or `prefs`.

    `advanced` is the Advanced window's overrides ({key: number}); it rides
    the file so a settings file is the WHOLE run, not the whole run minus the
    values that bite hardest when they silently differ.
    """
    return {"schema": SCHEMA,
            "version": version or "",
            "controls": dict(controls or {}),
            "layers": dict(layers or {}),
            "texts": dict(texts or {}),
            "advanced": dict(advanced or {})}


def sections(data):
    """(controls, layers, texts) out of a saved dict, whatever shape it is in.

    A file from a future schema, a hand-edited one, or an outright wrong file
    reads as three empty dicts rather than raising into the dialog.
    """
    if not isinstance(data, dict):
        return {}, {}, {}
    out = []
    for key in ("controls", "layers", "texts"):
        section = data.get(key)
        out.append(section if isinstance(section, dict) else {})
    return tuple(out)


def advanced_overrides(data):
    """The saved advanced overrides, or {} -- a schema-1 file has none.

    Kept OUT of `sections()` so its three-tuple callers do not all change
    shape for a section most files will not carry.
    """
    if not isinstance(data, dict):
        return {}
    section = data.get("advanced")
    return dict(section) if isinstance(section, dict) else {}


def describe(data):
    """One line about a saved file, for the dialog's status text."""
    controls, layers, texts = sections(data)
    version = (data or {}).get("version") or "?"
    return "{0} setting(s), {1} layer(s) -- saved by v{2}".format(
        len(controls), len(layers) + len(texts), version)


def read(path):
    """Load a settings file. A missing or broken one reads as {}."""
    try:
        with open(path, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"))
    except (IOError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write(path, data):
    """Save a settings file. Returns None on success, else the reason why not."""
    try:
        folder = os.path.dirname(path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with open(path, "wb") as handle:
            handle.write(json.dumps(data, indent=2,
                                    sort_keys=True).encode("utf-8"))
        return None
    except (IOError, OSError, ValueError, TypeError) as error:
        return str(error)

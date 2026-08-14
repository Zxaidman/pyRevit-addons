# -*- coding: utf-8 -*-
"""Remember the dialog's options between Revit sessions.

Everything here is a *preference* — how you like the tool set up — never
anything about a particular model. Ids are deliberately not stored: a view
family type id means nothing in the next project, so view types and templates
are remembered by name and re-matched when the model loads.

Stored as JSON under the user's roaming profile, beside pyRevit's own data:

    %APPDATA%/AnonGee/autolevel_settings.json

Every entry point returns rather than raises. Preferences are a convenience;
a read-only profile or a corrupt file must not stop the tool from opening.
"""

import os

FOLDER = "AnonGee"
FILENAME = "autolevel_settings.json"

# The shipped defaults, and the whitelist of what is allowed to persist —
# a key that is not here is never written and never read back.
DEFAULTS = {
    "source_index": 0,
    "unit_index": 0,
    "datum_mm": "0",
    "tolerance_mm": "25",
    "layers": "",
    "require_evidence": True,
    "cross_check_positions": True,
    "adopt_names": True,
    "count": "4",
    "storey_height_mm": "3000",
    "naming_follow": True,
    "template": "Level {n}",
    "start_index": "",
    "push_above": False,
    "snap_index": 2,
    "prefix": "",
    "suffix": "",
    "find": "",
    "replace": "",
    "case_index": 0,
    "scope_selected": True,
    "rename_use_template": False,
    "rename_template": "{nn} {ORDINAL} FLOOR",
    "rename_start": "1",
    "create_views": False,
    "view_type_names": [],
    "view_template_name": "",
}


def folder():
    """The directory the settings file lives in, without creating it."""
    base = (os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
            or os.path.expanduser("~"))
    return os.path.join(base, FOLDER)


def path():
    return os.path.join(folder(), FILENAME)


def defaults():
    """A fresh copy of the shipped defaults — never the shared dict."""
    return dict((key, list(value) if isinstance(value, list) else value)
                for key, value in DEFAULTS.items())


def load():
    """Saved preferences merged over the defaults. Never raises.

    Returns ``(settings, note)``; *note* is empty when the defaults were used
    because nothing has been saved yet, and carries the reason otherwise.
    """
    settings = defaults()
    target = path()
    if not os.path.isfile(target):
        return settings, ""
    try:
        import json
    except ImportError:
        return settings, "this engine has no json module — settings not loaded"
    try:
        handle = open(target, "r")
        try:
            stored = json.load(handle)
        finally:
            handle.close()
    except Exception as error:
        return settings, "couldn't read your settings ({0})".format(
            str(error)[:80])
    if not isinstance(stored, dict):
        return settings, "your settings file isn't in the expected shape"
    for key, value in stored.items():
        if key in DEFAULTS and isinstance(value, type(DEFAULTS[key])):
            settings[key] = value
    return settings, "loaded from {0}".format(target)


def save(settings):
    """Write the preferences. Returns ``(ok, message)`` — never raises."""
    try:
        import json
    except ImportError:
        return False, "This engine has no json module; settings can't be saved."
    keep = dict((key, value) for key, value in (settings or {}).items()
                if key in DEFAULTS)
    target = path()
    try:
        directory = folder()
        if not os.path.isdir(directory):
            os.makedirs(directory)
        handle = open(target, "w")
        try:
            json.dump(keep, handle, indent=2, sort_keys=True)
        finally:
            handle.close()
    except Exception as error:
        return False, "Couldn't save: {0}".format(str(error)[:120])
    return True, "Saved to {0}".format(target)


def forget():
    """Delete the saved preferences so the shipped defaults come back."""
    target = path()
    if not os.path.isfile(target):
        return True, "There was nothing saved."
    try:
        os.remove(target)
    except Exception as error:
        return False, "Couldn't remove: {0}".format(str(error)[:120])
    return True, "Back to the built-in defaults."

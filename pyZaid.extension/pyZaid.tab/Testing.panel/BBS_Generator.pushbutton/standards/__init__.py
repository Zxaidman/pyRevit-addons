# -*- coding: utf-8 -*-
"""Standards package loader."""
import importlib
import os
import sys

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

_MODULES = {
    "IS":  "IS_2502_2019",
    "BS":  "BS_8666_2020",
    "ACI": "ACI_315_2018",
}

def get_standard(key):
    mod_name = _MODULES.get(key.upper())
    if not mod_name:
        raise KeyError(
            "Unknown standard key: {0!r}. Valid: {1}".format(key, list(_MODULES)))
    return importlib.import_module(mod_name)

def available_standards():
    return list(_MODULES.keys())
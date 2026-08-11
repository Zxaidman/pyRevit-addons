# -*- coding: utf-8 -*-
"""Load cad2bim modules by PATH, without importing the package.

`import anongee_toolkit.cad2bim.report` pulls in the package __init__, which
pulls in Revit assemblies that do not exist outside Revit. Every test therefore
loads the module under test from its file into a throwaway package namespace.

That worked while each test hand-listed its dependencies -- and broke the day
`report.py` grew a sibling, because thirteen loaders had to learn about it. The
dependency graph lives here now, once:

    report = load("report")                      # and everything it needs
    shapes, report = load("geom.shapes", "report")

Names are module paths relative to cad2bim ("geom.shapes", "classify.marks").
Each call gets its own namespace, so one test cannot see another's state.
"""

import importlib.util
import itertools
import os
import sys
import types

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COUNTER = itertools.count(1)

# What each module needs loaded BEFORE it, in order. Only the modules the tests
# actually reach are listed; add a line when a new one grows a dependency.
_NEEDS = {
    "config": (),
    "model": (),
    "geom.shapes": ("config",),
    "geom.transform": ("config",),
    "classify.layers": (),
    "classify.marks": ("config",),
    "naming": ("prefs",),
    "prefs": (),
    "settings": (),
    "export": ("config", "classify.layers"),
    "limits": ("config",),
    "column_geom": ("config", "classify.layers"),
    "columns_recovery": ("config", "geom.shapes", "classify.layers", "limits",
                         "column_geom"),
    "beam_segments": ("config", "geom.shapes", "classify.layers", "classify.marks",
                      "limits", "column_geom"),
    "beam_cleanup": ("config", "column_geom"),
    "report": ("config", "model", "geom.shapes", "classify.layers",
               "classify.marks", "naming", "export", "limits", "column_geom",
               "columns_recovery", "beam_segments", "beam_cleanup"),
    "slab_outlines": ("config", "geom.shapes", "classify.layers"),
    "stair_layout": ("config", "geom.shapes", "classify.layers",
                     "slab_outlines"),
    "floor_plans": ("config", "geom.shapes", "classify.layers"),
    "footing_plan": ("config",),
    "readers.dxf_reader": ("config", "model"),
}


def load(*names):
    """Load each named module (plus its dependencies) into a fresh namespace.

    Returns the requested modules in the order asked for; a single name still
    returns a single module, which is what most tests want.
    """
    prefix = "_cad2bim_test_{0}".format(next(_COUNTER))
    for package in (prefix, prefix + ".geom", prefix + ".classify",
                    prefix + ".builders", prefix + ".readers"):
        module = types.ModuleType(package)
        module.__path__ = []
        sys.modules[package] = module
        if "." in package:
            parent, child = package.rsplit(".", 1)
            setattr(sys.modules[parent], child, module)

    loaded = {}

    def one(name):
        if name in loaded:
            return loaded[name]
        for dependency in _NEEDS.get(name, ()):
            one(dependency)
        full = "{0}.{1}".format(prefix, name)
        path = os.path.join(_PKG, *name.split(".")) + ".py"
        spec = importlib.util.spec_from_file_location(full, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[full] = module
        parent, child = full.rsplit(".", 1)
        setattr(sys.modules[parent], child, module)
        spec.loader.exec_module(module)
        loaded[name] = module
        return module

    wanted = [one(name) for name in names]
    return wanted[0] if len(wanted) == 1 else tuple(wanted)

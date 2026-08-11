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

import importlib
import itertools
import os
import sys
import types

_PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COUNTER = itertools.count(1)

# What each module needs loaded BEFORE it, in order. Only the modules the tests
# actually reach are listed; add a line when a new one grows a dependency.


def load(*names):
    """Load each named module into a fresh, throwaway package namespace.

    The fake package carries a real `__path__` pointing at cad2bim, so a module
    that imports a sibling -- `from . import config`, `from .slab_graph import
    ...` -- resolves it by file exactly as it does inside Revit. That means the
    tests exercise the REAL import graph, cycles included, instead of a
    hand-listed approximation that had to be updated every time a module grew a
    neighbour.

    Returns the requested modules in the order asked for; a single name returns
    a single module.
    """
    prefix = "_cad2bim_test_{0}".format(next(_COUNTER))
    for suffix in ("", "geom", "classify", "builders", "readers"):
        name = prefix if not suffix else "{0}.{1}".format(prefix, suffix)
        module = types.ModuleType(name)
        module.__path__ = [_PKG if not suffix else os.path.join(_PKG, suffix)]
        sys.modules[name] = module
        if "." in name:
            parent, child = name.rsplit(".", 1)
            setattr(sys.modules[parent], child, module)

    loaded = [importlib.import_module("{0}.{1}".format(prefix, name))
              for name in names]
    return loaded[0] if len(loaded) == 1 else tuple(loaded)

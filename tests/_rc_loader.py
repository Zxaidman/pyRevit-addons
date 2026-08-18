# -*- coding: utf-8 -*-
"""Import ``anongee_toolkit.rc_automation`` without importing the toolkit.

``anongee_toolkit/__init__.py`` publishes the whole toolkit API, which means it
imports the Revit layer, which means importing it outside Revit fails on the
first ``Autodesk.Revit.DB``. The rc_automation package deliberately has no Revit
in it, so the only thing standing between the test suite and the code under test
is that ``__init__``.

cad2bim solves the same problem by loading each module from its file into a
throwaway namespace. This does the smaller version: shadow the *top* package
with an empty module whose ``__path__`` points at the real folder, and let the
normal import machinery do the rest. Subpackages then resolve by file, absolute
imports inside them work unchanged, and the real ``__init__`` never runs.

Note what is deliberately absent: ``lib/py3`` is never put on ``sys.path``. The
shim's ``__path__`` is enough to resolve the package, and adding the folder would
put the extension's *vendored Windows* wheels -- an openpyxl whose numpy cannot
load off Windows -- ahead of the ones installed on the machine running the tests,
silently disabling the file-layer tests it should be running.
"""

import os
import sys
import types

_PKG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "AnonGee.extension", "lib", "py3", "anongee_toolkit")


def load():
    """Return the imported ``rc_automation`` package."""
    if "anongee_toolkit" not in sys.modules:
        shim = types.ModuleType("anongee_toolkit")
        shim.__path__ = [_PKG]
        shim.__doc__ = "Test shim — see tests/_rc_loader.py"
        sys.modules["anongee_toolkit"] = shim
    import anongee_toolkit.rc_automation as rc_automation
    return rc_automation

# -*- coding: utf-8 -*-
"""CLR types must be emitted once per Revit session, not once per import.

Python.NET emits a real CLR type from a class that derives from a .NET
interface, and an AppDomain refuses a second type of the same name. The buttons
re-import their library on every run (so a release is picked up without
restarting Revit), which used to run those class bodies again:

    Duplicate type name within an assembly

The registry hands back the type it built the first time. Standalone: no Revit,
no CLR -- the factory here returns a plain object, which is all the registry
promises to care about.
"""

import ast
import importlib.util
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)                       # .../cad2bim
_LIB = os.path.dirname(os.path.dirname(_PKG))       # .../lib/py3


def _load():
    spec = importlib.util.spec_from_file_location(
        "_clr_under_test", os.path.join(_LIB, "anongee_clr.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


anongee_clr = _load()


class BuiltOncePerSession(unittest.TestCase):
    def setUp(self):
        anongee_clr.forget()

    def test_the_factory_runs_once_however_often_it_is_asked(self):
        calls = []

        def factory():
            calls.append(1)
            return type("Fake", (object,), {})

        first = anongee_clr.get_or_create("Fake", factory)
        second = anongee_clr.get_or_create("Fake", factory)
        third = anongee_clr.get_or_create("Fake", factory)
        self.assertEqual(len(calls), 1)
        self.assertIs(first, second)
        self.assertIs(second, third)

    def test_two_names_are_two_types(self):
        one = anongee_clr.get_or_create("One", lambda: type("A", (object,), {}))
        two = anongee_clr.get_or_create("Two", lambda: type("B", (object,), {}))
        self.assertIsNot(one, two)
        self.assertEqual(anongee_clr.registered(), ["One", "Two"])

    def test_a_factory_that_raises_is_not_remembered(self):
        def broken():
            raise RuntimeError("no CLR here")

        with self.assertRaises(RuntimeError):
            anongee_clr.get_or_create("Broken", broken)
        self.assertEqual(anongee_clr.registered(), [])
        # the next attempt gets a fresh try rather than a cached half-state
        made = anongee_clr.get_or_create("Broken",
                                         lambda: type("C", (object,), {}))
        self.assertIsNotNone(made)

    def test_a_factory_that_produces_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            anongee_clr.get_or_create("Empty", lambda: None)


class TheRegistrySurvivesTheReload(unittest.TestCase):
    """It has to live outside the package the buttons purge every run."""

    def test_it_is_not_inside_anongee_toolkit(self):
        self.assertTrue(os.path.isfile(os.path.join(_LIB, "anongee_clr.py")))
        self.assertFalse(os.path.isfile(
            os.path.join(_LIB, "anongee_toolkit", "anongee_clr.py")))

    def test_it_imports_no_revit_assemblies(self):
        with open(os.path.join(_LIB, "anongee_clr.py"), "rb") as handle:
            source = handle.read().decode("utf-8")
        for banned in ("import clr", "Autodesk.Revit", "System."):
            self.assertNotIn(banned, source)


class NoClassBodyEmitsAClrTypeAtImport(unittest.TestCase):
    """A .NET-derived class declared at module level is the bug itself.

    Scanned statically over the whole toolkit: any module-level class whose
    bases name a Revit/.NET interface would run at import time, and the buttons
    import more than once per session.
    """

    _INTERFACES = ("IFailuresPreprocessor", "ISelectionFilter",
                   "IExternalEventHandler", "IUpdater", "IExternalCommand",
                   "IDuplicateTypeNamesHandler", "ISelectionChangedEventHandler")

    def _python_files(self):
        root = os.path.join(_LIB, "anongee_toolkit")
        for folder, _dirs, files in os.walk(root):
            if "__pycache__" in folder or os.sep + "tests" in folder:
                continue
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(folder, name)

    def test_no_module_level_clr_subclass_in_the_toolkit(self):
        offenders = []
        for path in self._python_files():
            with open(path, "rb") as handle:
                tree = ast.parse(handle.read().decode("utf-8"), path)
            for node in tree.body:                      # module level only
                if not isinstance(node, ast.ClassDef):
                    continue
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                if any(base in self._INTERFACES for base in bases):
                    offenders.append("{0}:{1}".format(
                        os.path.relpath(path, _LIB), node.name))
        self.assertEqual(offenders, [],
                         "emitted at import time, so a re-import crashes: %s"
                         % offenders)

    def test_the_known_sites_go_through_the_registry(self):
        expected = {
            os.path.join(_LIB, "anongee_toolkit", "cad2bim", "builders",
                         "txn_failures.py"): "WarningSwallower",
            os.path.join(_LIB, "anongee_toolkit", "revit",
                         "transactions.py"): "SuppressWarningsPreprocessor",
        }
        for path, name in expected.items():
            with open(path, "rb") as handle:
                source = handle.read().decode("utf-8")
            self.assertIn("import anongee_clr", source, path)
            # the call is often wrapped over two lines
            flat = " ".join(source.split())
            self.assertIn('anongee_clr.get_or_create( "{0}"'.format(name)
                          .replace("( ", "("), flat.replace("( ", "("), path)


if __name__ == "__main__":
    unittest.main()

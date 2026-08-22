# -*- coding: utf-8 -*-
"""The bridge spike, checked where it can be checked without Revit.

Three things here, and each has a specific failure in mind.

**The URL contract.** The host, the port, the API name and the route names are
written down in three places — the routes in ``startup.py``, the VBA in
``bridge/excel/``, and the Bridge Check pushbutton. A disagreement between any
two of them produces a call that times out, and it looks exactly like a network
problem for as long as it takes somebody to compare three files by hand. So the
three are compared here instead.

**The engine.** ``startup.py`` is loaded by pyRevit's core engine, which is
IronPython 2.7 — not the CPython 3 engine the rest of the toolkit runs on. An
f-string in that file is a syntax error at pyRevit load, and the symptom is that
the whole extension fails to appear. Which Python actually runs it is the third
question the spike exists to answer; until it has, the file has to be valid in
both.

**The blast radius.** A startup script that raises takes pyRevit's load with it,
so a broken bridge would cost the user every other tool on the ribbon. The
module-level registration is required to be wrapped, and the wrap is checked.
"""

import ast
import io
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STARTUP = os.path.join(_ROOT, "AnonGee.extension", "startup.py")
_VBA = os.path.join(_ROOT, "bridge", "excel", "modAnonGeeBridge.bas")
_CHECK = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
                      "Bridge Check.pushbutton", "script.py")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _constants(source):
    """Top-level ``NAME = <literal>`` assignments, as a dict."""
    found = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and isinstance(node.value,
                                                           ast.Constant):
                found[target.id] = node.value.value
    return found


def _vba_constant(source, name):
    """``Public Const NAME As T = value`` -> the value, unquoted."""
    for line in source.splitlines():
        text = line.strip()
        if not text.startswith("Public Const " + name + " "):
            continue
        value = text.split("=", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        return int(value)
    raise AssertionError("no Public Const {0} in the VBA".format(name))


def _routes(source):
    """``{route: [argument names]}`` for every ``@api.route`` handler."""
    found = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if (isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr == "route"
                    and decorator.args
                    and isinstance(decorator.args[0], ast.Constant)):
                found[decorator.args[0].value] = [
                    argument.arg for argument in node.args.args]
    return found


class UrlContractTests(unittest.TestCase):
    """Three files, one URL. They agree here or they never agree at all."""

    def setUp(self):
        self.startup = _constants(_read(_STARTUP))
        self.check = _constants(_read(_CHECK))
        self.vba = _read(_VBA)

    def test_the_api_name_is_the_same_everywhere(self):
        self.assertEqual(self.startup["API_NAME"], "anongee")
        self.assertEqual(self.check["API"], self.startup["API_NAME"])
        self.assertEqual(_vba_constant(self.vba, "BRIDGE_API"),
                         self.startup["API_NAME"])

    def test_the_host_and_port_are_the_same_everywhere(self):
        self.assertEqual(self.check["HOST"], self.startup["DEFAULT_HOST"])
        self.assertEqual(self.check["PORT"], self.startup["DEFAULT_PORT"])
        self.assertEqual(_vba_constant(self.vba, "BRIDGE_HOST"),
                         self.startup["DEFAULT_HOST"])
        self.assertEqual(_vba_constant(self.vba, "BRIDGE_PORT"),
                         self.startup["DEFAULT_PORT"])

    def test_every_route_called_from_outside_is_one_that_exists(self):
        served = set(route.strip("/") for route in _routes(_read(_STARTUP)))
        self.assertEqual(served, set(["ping", "status"]))
        for caller, source in (("the VBA", self.vba),
                               ("Bridge Check", _read(_CHECK))):
            for route in served:
                self.assertIn('"{0}"'.format(route), source,
                              "{0} never calls /{1}".format(caller, route))

    def test_both_callers_build_the_url_from_the_same_three_parts(self):
        # Not a hardcoded string in either, or the constants above are
        # decoration and the test proves nothing.
        self.assertIn("BRIDGE_HOST & \":\"", self.vba)
        self.assertIn('"http://{0}:{1}/{2}/{3}".format(HOST, PORT, API',
                      _read(_CHECK))


class TwoRoutesTests(unittest.TestCase):
    """The reason there are two routes is the reason the spike is worth doing."""

    def setUp(self):
        self.routes = _routes(_read(_STARTUP))

    def test_ping_asks_revit_for_nothing(self):
        # No uiapp/uidoc/doc argument, so pyRevit does NOT run it as an
        # External Event -- which is what lets it answer while Revit is busy.
        self.assertEqual(self.routes["/ping"], [])

    def test_status_declares_uiapp_and_so_runs_as_an_external_event(self):
        # Declaring one of uiapp/uidoc/doc is the whole mechanism. If this
        # argument is ever removed the route stops proving anything.
        self.assertEqual(self.routes["/status"], ["uiapp"])

    def test_status_reads_the_document_defensively_rather_than_declaring_it(self):
        # Declaring `doc` would make "no document open" an error instead of an
        # answer, and a bridge that cannot say that looks broken every morning.
        source = _read(_STARTUP)
        self.assertIn("uiapp.ActiveUIDocument", source)
        self.assertIn("no document is open", source)


class EngineCompatibilityTests(unittest.TestCase):
    """``startup.py`` is loaded by pyRevit's core engine, which is IronPython."""

    def setUp(self):
        self.source = _read(_STARTUP)
        self.tree = ast.parse(self.source)

    def test_it_compiles(self):
        compile(self.source, _STARTUP, "exec")

    def test_no_f_strings(self):
        """An f-string here is a syntax error at pyRevit load, and the symptom
        is the whole extension failing to appear."""
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.JoinedStr)

    def test_nothing_newer_than_python_2_7(self):
        for node in ast.walk(self.tree):
            self.assertNotIsInstance(node, ast.NamedExpr)      # :=
            self.assertNotIsInstance(node, ast.AnnAssign)      # x: int = 1
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.assertIsNone(node.returns, node.name)
                for argument in node.args.args:
                    self.assertIsNone(argument.annotation, node.name)

    def test_the_toolkit_is_not_imported_at_module_scope(self):
        """It lives in ``lib/py3`` and may not be on this engine's path at all.

        Whether a route handler can reach it is question 3 of the spike, and
        importing it here would answer it by crashing.
        """
        for node in self.tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                module = getattr(node, "module", "") or ""
                self.assertNotIn("anongee_toolkit", module)
                for name in names:
                    self.assertNotIn("anongee_toolkit", name)

    def test_pyrevit_is_imported_inside_the_function_not_at_module_scope(self):
        # So the file stays importable by this test suite, off Revit.
        self.assertNotIn("\nfrom pyrevit import", self.source)
        self.assertIn("    from pyrevit import routes", self.source)


class BlastRadiusTests(unittest.TestCase):
    """A startup script that raises costs the user every other tool."""

    def test_registration_is_wrapped(self):
        source = _read(_STARTUP)
        tail = source.split("REGISTRATION_NOTE = \"\"", 1)[1]
        self.assertIn("try:", tail)
        self.assertIn("register()", tail)
        self.assertIn("except Exception", tail)

    def test_register_returns_its_failure_rather_than_raising(self):
        # Read as a tree, not as text. The first version of this test searched
        # the source for "raise" and matched the word in the docstring that
        # promises it does not.
        for node in ast.walk(ast.parse(_read(_STARTUP))):
            if isinstance(node, ast.FunctionDef) and node.name == "register":
                for inner in ast.walk(node):
                    self.assertNotIsInstance(inner, ast.Raise)
                returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                self.assertTrue(returns)
                break
        else:
            self.fail("startup.py defines no register()")

    def test_the_check_tool_writes_nothing(self):
        source = _read(_CHECK)
        for forbidden in ("Transaction(", "TransactionGroup(", ".Delete(",
                          "doc.Create"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_the_check_tool_reaches_the_wire_through_dotnet_first(self):
        """The CPython 3 engine ships a partial stdlib — ``re`` and ``csv`` are
        both missing. The tool that has to work when nothing else does should
        not be the one betting on ``urllib`` being complete."""
        # By import order in the tree, not by position in the text: the first
        # version of this matched the word "urllib" in the comment explaining
        # why it comes second.
        order = []
        for node in ast.walk(ast.parse(_read(_CHECK))):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "System.Net" in node.module or "urllib" in node.module:
                    order.append((node.lineno, node.module))
        order.sort()
        self.assertEqual([module for _line, module in order],
                         ["System.Net", "urllib.request"])


if __name__ == "__main__":
    unittest.main()

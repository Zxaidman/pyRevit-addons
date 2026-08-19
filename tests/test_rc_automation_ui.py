# -*- coding: utf-8 -*-
"""Static checks on the RC Automation window, against the faults that cost most.

A XAML file can be perfectly well-formed and still produce a window that never
opens, or opens with blank cells and dead buttons. Every failure below is one
that otherwise turns up as a Revit restart:

* a literal starting with ``{`` read as a markup extension, so ``XamlReader``
  throws and the window never appears at all;
* a ``{StaticResource}`` naming a key nothing defines;
* a ``{Binding}`` path with no matching ``__slots__`` entry -- which fails
  *silently* under Python.NET 3 and renders an empty column (§12.7.G);
* a ``FindName`` for a control the XAML does not have, or a named control the
  script never touches;
* the engine rules: no ``re``, no pyRevit imports, no ``StaticResource`` on the
  root ``Window``, CLR classes defined once per session, no ``__init__`` on an
  interface subclass, ``Show()`` before the owner is set.

It also holds this build to being read-only, because that is the claim the whole
thing is published under.
"""

import ast
import io
import os
import unittest
from xml.etree import ElementTree

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUTTON = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab", "Dev.panel",
                       "RC Automation.pushbutton")
_XAML = os.path.join(_BUTTON, "ui.xaml")
_SCRIPT = os.path.join(_BUTTON, "script.py")
_BUNDLE = os.path.join(_BUTTON, "bundle.yaml")
_CHANGELOG = os.path.join(_BUTTON, "CHANGELOG.md")

_XMLNS = "{http://schemas.microsoft.com/winfx/2006/xaml}"


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


def _tree():
    return ElementTree.parse(_XAML).getroot()


_TEMPLATE_TAGS = ("ControlTemplate", "DataTemplate", "ItemsPanelTemplate")


def _iter(root):
    for element in root.iter():
        yield element


def _window_scope(root):
    """Every element except those inside a template.

    Names, tooltips and bindings inside a ``ControlTemplate`` belong to that
    template's own scope: ``Bd`` and ``Bg`` repeat across the button, textbox
    and combobox templates on purpose, ``FindName`` cannot reach them from the
    window, and a template part like ``PART_EditableTextBox`` is not a control
    a user is meant to be told about. Only the window's own tree is held to the
    rules below.
    """
    found = []

    def walk(element):
        for child in element:
            if child.tag.split("}")[-1] in _TEMPLATE_TAGS:
                continue
            found.append(child)
            walk(child)

    found.append(root)
    walk(root)
    return found


def _subtree_text(tag_name):
    """The raw XAML of the first element with this tag, as written.

    Scoping a text search to one element beats splitting the whole file, which
    would sweep in the 588-line inlined theme above it.
    """
    text = _read(_XAML)
    start = text.index("<" + tag_name)
    depth = 0
    cursor = start
    while cursor < len(text):
        open_at = text.find("<" + tag_name, cursor)
        close_at = text.find("</" + tag_name + ">", cursor)
        if close_at == -1:
            break
        if open_at != -1 and open_at < close_at:
            depth += 1
            cursor = open_at + 1
            continue
        depth -= 1
        cursor = close_at + len("</" + tag_name + ">")
        if depth == 0:
            return text[start:cursor]
    return text[start:]


class XamlStructureTests(unittest.TestCase):

    def test_the_file_is_well_formed(self):
        _tree()

    def test_no_literal_value_is_mistaken_for_a_markup_extension(self):
        """A value starting with ``{`` must be an extension or be escaped.

        ``XamlReader.Load`` throws on an unescaped literal brace, and the window
        simply never opens -- no window, no error in the log worth reading.
        """
        offenders = []
        for element in _iter(_tree()):
            for name, value in element.attrib.items():
                if value.startswith("{") and not value.startswith("{}"):
                    inner = value[1:].split()[0] if len(value) > 1 else ""
                    if not inner.split("=")[0].rstrip("}") in (
                            "StaticResource", "DynamicResource", "Binding",
                            "TemplateBinding", "x:Static", "RelativeSource",
                            "x:Null", "x:Type"):
                        offenders.append("{0}@{1}={2}".format(
                            element.tag, name, value))
        self.assertEqual(offenders, [])

    def test_the_root_window_uses_literals_only(self):
        """Root ``Window`` attributes resolve before ``Window.Resources`` parses.

        A ``{StaticResource}`` on the ``Window`` element itself throws at parse
        time (§12.7.A), so the root carries literals and nothing else.
        """
        root = _tree()
        for name, value in root.attrib.items():
            self.assertFalse(value.startswith("{"),
                             "root Window.{0} is {1}".format(name, value))

    def test_every_resource_reference_resolves(self):
        text = _read(_XAML)
        defined = set()
        for element in _iter(_tree()):
            key = element.attrib.get(_XMLNS + "Key")
            if key and not key.startswith("{"):
                defined.add(key)

        missing = set()
        cursor = 0
        needle = "{StaticResource "
        while True:
            start = text.find(needle, cursor)
            if start == -1:
                break
            end = text.find("}", start)
            name = text[start + len(needle):end].strip()
            if name and not name.startswith("{") and name not in defined:
                missing.add(name)
            cursor = end
        self.assertEqual(sorted(missing), [])

    def test_no_resource_key_is_defined_twice(self):
        seen = []
        for element in _iter(_tree()):
            key = element.attrib.get(_XMLNS + "Key")
            if key and not key.startswith("{"):
                seen.append(key)
        duplicates = sorted(set(k for k in seen if seen.count(k) > 1))
        self.assertEqual(duplicates, [])

    def test_every_name_is_unique(self):
        names = [element.attrib[_XMLNS + "Name"]
                 for element in _window_scope(_tree())
                 if _XMLNS + "Name" in element.attrib]
        duplicates = sorted(set(n for n in names if names.count(n) > 1))
        self.assertEqual(duplicates, [])

    def test_every_trigger_targets_an_element_in_its_own_template(self):
        for template in _tree().iter():
            if not template.tag.endswith("ControlTemplate"):
                continue
            declared = set()
            for node in template.iter():
                name = node.attrib.get(_XMLNS + "Name")
                if name:
                    declared.add(name)
            for node in template.iter():
                target = node.attrib.get("TargetName")
                if target:
                    self.assertIn(target, declared)

    def test_every_interactive_control_carries_a_tooltip(self):
        """A control the user can act on says what it does (§12.7 / §8)."""
        interactive = ("Button", "TextBox", "ComboBox", "CheckBox", "DataGrid")
        missing = []
        for element in _window_scope(_tree()):
            tag = element.tag.split("}")[-1]
            if tag not in interactive:
                continue
            if _XMLNS + "Name" not in element.attrib:
                continue          # template-internal parts, not user surface
            if not element.attrib.get("ToolTip"):
                missing.append(element.attrib[_XMLNS + "Name"])
        self.assertEqual(missing, [])


class BindingTests(unittest.TestCase):
    """Every bound column has a slot behind it, or the cell renders empty."""

    def slots(self):
        tree = ast.parse(_read(_SCRIPT))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "FindingRow":
                for statement in node.body:
                    if (isinstance(statement, ast.Assign)
                            and getattr(statement.targets[0], "id", "")
                            == "__slots__"):
                        return set(ast.literal_eval(statement.value))
        self.fail("FindingRow.__slots__ not found")

    def test_every_binding_path_has_a_slot(self):
        # Only the grid's own columns bind to a row object; bindings inside the
        # theme's control templates bind to their templated parent.
        text = _subtree_text("DataGrid.Columns")
        slots = self.slots()
        missing = set()
        cursor = 0
        needle = "{Binding "
        while True:
            start = text.find(needle, cursor)
            if start == -1:
                break
            end = text.find("}", start)
            path = text[start + len(needle):end].split(",")[0].strip()
            if path and not path.startswith("{") and path not in slots:
                missing.add(path)
            cursor = end
        self.assertEqual(sorted(missing), [])

    def test_the_grid_is_read_only_and_bindings_are_one_way(self):
        # Nothing in this build edits the model, so nothing in the grid should
        # look editable either.
        grid = _subtree_text("DataGrid")
        self.assertIn('IsReadOnly="True"', grid)
        self.assertNotIn("Mode=TwoWay", _subtree_text("DataGrid.Columns"))


class ScriptWiringTests(unittest.TestCase):

    def setUp(self):
        self.source = _read(_SCRIPT)
        self.tree = ast.parse(self.source)

    def looked_up(self):
        found = set()
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "FindName"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)):
                found.add(node.args[0].value)
        return found

    def named_in_xaml(self):
        return set(element.attrib[_XMLNS + "Name"]
                   for element in _window_scope(_tree())
                   if _XMLNS + "Name" in element.attrib)

    def test_the_script_compiles(self):
        compile(self.source, _SCRIPT, "exec")

    def test_every_looked_up_control_exists_in_the_xaml(self):
        self.assertEqual(sorted(self.looked_up() - self.named_in_xaml()), [])

    def test_every_named_control_is_looked_up(self):
        """A named control nothing reaches is either dead XAML or a dead button."""
        self.assertEqual(sorted(self.named_in_xaml() - self.looked_up()), [])

    def test_every_button_is_wired_to_a_handler(self):
        for name in ("BrowseBtn", "LoadBtn", "ProbeBtn", "ExportBtn",
                     "ClearBtn", "CloseBtn"):
            self.assertIn("self.{0}.Click +=".format(name), self.source, name)

    def test_no_pyrevit_imports(self):
        """pyRevit's IronPython modules do not load under CPython 3 (§12.8.4)."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(alias.name.startswith("pyrevit"))
            elif isinstance(node, ast.ImportFrom):
                self.assertFalse((node.module or "").startswith("pyrevit"))

    def test_no_re_module(self):
        """The engine ships a partial stdlib and ``re`` is not in it (§12.9.3)."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                self.assertNotIn("re", [a.name for a in node.names])
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "re")

    def test_no_star_imports(self):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom):
                self.assertNotIn("*", [a.name for a in node.names])

    def test_the_clr_class_is_defined_once_per_session(self):
        """Re-emitting a ``__namespace__`` type raises on the second press."""
        self.assertIn("_state.handler_cls is None", self.source)
        self.assertIn("sys.modules[_STATE_MODULE]", self.source)

    def test_the_interface_subclass_has_no_init(self):
        """``__init__`` on a Revit-interface subclass raises at construction."""
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.ClassDef)
                    and node.name == "RCAutomationHandler"):
                names = [n.name for n in node.body
                         if isinstance(n, ast.FunctionDef)]
                self.assertNotIn("__init__", names)
                return
        self.fail("RCAutomationHandler not found")

    def test_the_handler_declares_its_namespace(self):
        self.assertIn('__namespace__ = "AnonGee"', self.source)

    def test_the_window_is_shown_then_anchored(self):
        """Anchoring before ``Show()`` opens the window behind Revit (§12.8.3)."""
        shown = self.source.index("self.window.Show()")
        anchored = self.source.index("helper.Owner")
        self.assertLess(shown, anchored)

    def test_the_grid_is_flushed_before_it_is_refilled(self):
        """WPF reuses row containers unless ``ItemsSource`` is cleared first."""
        index = self.source.index("self.FindingsGrid.ItemsSource = None")
        self.assertIn("self.FindingsGrid.ItemsSource = rows",
                      self.source[index:])

    def test_results_come_back_through_the_dispatcher(self):
        self.assertIn("Dispatcher.BeginInvoke", self.source)

    def test_requests_are_serialized_rather_than_single_slotted(self):
        for fragment in ("self._queue", "self._busy", "def _pump"):
            self.assertIn(fragment, self.source)


class CreationSafetyTests(unittest.TestCase):
    """What stands between a Create click and a damaged model.

    This build writes, so "it writes nothing" is no longer the guarantee. These
    are the guarantees that replaced it, and each is here because the failure it
    prevents is expensive and quiet.
    """

    def setUp(self):
        self.source = _read(_SCRIPT)
        self.tree = ast.parse(self.source)

    def test_reconcile_cannot_write(self):
        """Reconcile resolves differences, and resolving them is not built.

        The other two modes build: one creates footings and reinforces them,
        one reinforces what is already there. Reconcile would have to change
        elements that exist, which is deliberately report-only.
        """
        body = self.source.split("def _ready_to_plan")[1].split("\n    def ")[0]
        self.assertIn("models.MODE_RECONCILE", body)
        self.assertIn("_MODE_NOT_BUILT", body)

    def test_each_mode_creates_through_its_own_path(self):
        # Phase 1 makes pads then reinforces them; Phase 2 reinforces what is
        # there. Sharing one branch would silently do the wrong one.
        for name in ("_plan_structure", "_create_structure"):
            self.assertIn("def {0}".format(name), self.source, name)
        for branch in ("_plan", "_create"):
            body = self.source.split("def {0}(self, uiapp)".format(branch))[1]\
                .split("\n        def ")[0]
            self.assertIn("models.MODE_CREATE_ALL", body, branch)

    def test_new_pads_and_their_bars_share_one_undo_step(self):
        """Otherwise a user reversing the run is left with bare footings."""
        body = self.source.split("def _create_structure")[1]\
            .split("\n        def ")[0]
        self.assertEqual(body.count("TransactionGroup("), 1)
        self.assertIn("group.Assimilate()", body)
        self.assertIn("_reinforce_new", body)

    def test_a_new_pad_and_its_bars_share_one_frame(self):
        """Bars are planned from the outline the pad was built from, and placed
        at the point the pad was placed at, turned by the same angle.

        Anything else and the two drift apart. Planning from the type's
        rectangle and placing against the element's bounding-box centre put the
        bars 2.25 m outside the concrete on the one pad in the sample that is
        not a rectangle, because its outline runs from the placement point
        rather than around it.
        """
        body = self.source.split("def _reinforce_new")[1].split("\ndef ")[0]
        self.assertIn("outline=item.outline_mm", body)
        self.assertIn("item.position_mm", body)
        self.assertIn("item.rotation_deg", body)
        # The bounding-box centre is exactly what must not be used here.
        self.assertNotIn("plan_origin_mm", body)
        # The height still is: the frame does not carry it.
        self.assertIn("bottom_elevation_mm", body)
        self.assertIn("is_valid_host", body)

    def test_the_scheduled_cover_goes_onto_the_element(self):
        """So the model carries the number, not only the bars — and anything
        constrained to cover has something real to follow."""
        run = _read(os.path.join(
            _ROOT, "AnonGee.extension", "lib", "py3", "anongee_toolkit",
            "structural", "structure_run.py"))
        body = run.split("def create_one")[1].split("\ndef ")[0]
        self.assertIn("set_host_cover", body)
        factory = _read(os.path.join(
            _ROOT, "AnonGee.extension", "lib", "py3", "anongee_toolkit",
            "structural", "rebar_factory.py"))
        self.assertIn("RebarCoverType.Create", factory)
        for builtin in ("CLEAR_COVER_TOP", "CLEAR_COVER_BOTTOM",
                        "CLEAR_COVER_OTHER"):
            self.assertIn(builtin, factory, builtin)

    def test_a_constraint_that_cannot_be_made_never_costs_the_run(self):
        """The bars are in the right place either way; what is lost is the
        automatic updating, and that is not worth a rolled-back chunk."""
        constraints = _read(os.path.join(
            _ROOT, "AnonGee.extension", "lib", "py3", "anongee_toolkit",
            "structural", "rebar_constraints.py"))
        for function in ("def constrain_to_cover", "def apply_to_all"):
            body = constraints.split(function)[1].split("\ndef ")[0]
            self.assertNotIn("raise ", body, function)
        self.assertIn("except Exception", constraints)

    def test_a_plan_has_to_exist_before_anything_is_written(self):
        body = self.source.split("def _on_create")[1].split("\n    def ")[0]
        self.assertIn("self.plan is None", body)
        self.assertIn("MessageBox.Show", body)
        self.assertIn("MessageBoxResult.OK", body)

    def test_the_button_is_disabled_until_there_is_something_to_do(self):
        self.assertIn('IsEnabled="False"', _read(_XAML))
        self.assertIn("def _update_create_button", self.source)

    def test_a_stale_plan_is_thrown_away(self):
        """A plan belongs to the workbook and mode it was made in."""
        for hook in ("def _on_mode_changed", "def _on_load", "def _on_clear"):
            body = self.source.split(hook)[1].split("\n    def ")[0]
            self.assertIn("self.plan = None", body, hook)

    def test_the_run_is_one_undo_step(self):
        # A user who does not like the result must be able to reverse it with
        # one Ctrl+Z, not four hundred.
        body = self.source.split("def _create")[1].split("\n        def ")[0]
        self.assertIn("TransactionGroup(", body)
        self.assertIn("group.Assimilate()", body)

    def test_every_transaction_is_rolled_back_when_it_fails(self):
        body = self.source.split("def _create")[1].split("\n        def ")[0]
        self.assertIn("transaction.HasStarted() and not transaction.HasEnded()",
                      body)
        self.assertIn("transaction.RollBack()", body)
        self.assertIn("group.RollBack()", body)

    def test_work_is_chunked_so_a_failure_is_contained(self):
        self.assertIn("CHUNK_SIZE", self.source)
        body = self.source.split("def _create")[1].split("\n        def ")[0]
        self.assertIn("range(0, len(plans), CHUNK_SIZE)", body)

    def test_only_warnings_are_swallowed_never_errors(self):
        """Suppressing an error would let the run write something invalid.

        A batch of several hundred bars raises a warning dialog per host, which
        makes a modeless tool unusable — but an error has to reach Revit so the
        chunk rolls back instead of committing nonsense.
        """
        body = self.source.split("class RebarWarningSwallower")[1]\
            .split("\n    _state.failures_cls")[0]
        self.assertIn("FailureSeverity.Warning", body)
        self.assertIn("DeleteWarning", body)
        self.assertNotIn("DeleteAllWarnings", body)
        self.assertNotIn("ResolveFailure", body)

    def test_the_failure_preprocessor_follows_the_interface_rules(self):
        """Same three traps as the event handler (§12.9.4)."""
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.ClassDef)
                    and node.name == "RebarWarningSwallower"):
                names = [n.name for n in node.body
                         if isinstance(n, ast.FunctionDef)]
                self.assertNotIn("__init__", names)
                self.assertIn("PreprocessFailures", names)
                break
        else:
            self.fail("RebarWarningSwallower not found")
        self.assertIn("failures_cls", self.source)

    def test_existing_reinforcement_is_not_doubled(self):
        # Running the same workbook twice must not place the steel twice.
        self.assertIn("ReplaceCheck", self.source)
        self.assertIn('"replace"', self.source)

    def test_only_this_tools_own_bars_are_ever_removed(self):
        run = _read(os.path.join(
            _ROOT, "AnonGee.extension", "lib", "py3", "anongee_toolkit",
            "structural", "rebar_run.py"))
        body = run.split("def place_footing")[1].split("\ndef ")[0]
        self.assertIn("existing_stamped_rebar", body)
        # Never a blanket delete of whatever the host happens to contain.
        self.assertNotIn("GetRebarsInHost", body)

    def test_the_document_being_read_only_is_checked(self):
        self.assertIn("doc.IsReadOnly", self.source)

    def test_the_user_is_told_what_the_build_does_and_does_not_do(self):
        for path in (_BUNDLE, _CHANGELOG):
            text = _read(path).lower()
            self.assertIn("undo", text, path)


class ModuleScopeTests(unittest.TestCase):
    """Names read while the file loads have to be defined by then.

    This exists because a constant referencing ``models`` was written above the
    import that provides it. The script raised ``NameError: name 'models' is
    not defined`` before a single line of it ran — and every test here passed,
    because they all *parse* the file and none of them *executes* it. Importing
    it is not an option (it imports Revit at module scope), so the order is
    checked instead.

    Only what actually runs at import time is looked at. A function body runs
    later and may name anything defined by the time it is called; its
    decorators and argument defaults run now and may not.
    """

    #: Bound by pyRevit before the script runs, not by the script itself.
    INJECTED = ("__revit__", "__file__", "__name__", "__doc__", "__builtins__")

    def _immediate(self, node):
        """The parts of *node* evaluated when the module loads."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            return (list(node.decorator_list) + list(args.defaults)
                    + [d for d in args.kw_defaults if d])
        if isinstance(node, ast.ClassDef):
            # A class body does execute; the bodies of its methods do not.
            parts = list(node.decorator_list) + list(node.bases)
            for statement in node.body:
                parts.extend(self._immediate(statement))
            return parts
        return [node]

    def _loads(self, node):
        """Name reads inside *node*, not descending into deferred bodies."""
        found = []
        stack = [node]
        while stack:
            current = stack.pop()
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.Lambda, ast.ClassDef)):
                stack.extend(self._immediate(current))
                continue
            if (isinstance(current, ast.Name)
                    and isinstance(current.ctx, ast.Load)):
                found.append(current)
            stack.extend(ast.iter_child_nodes(current))
        return found

    def _bound(self, node):
        """Every name *node* binds — including its own locals and targets."""
        names = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.alias):
                names.add(inner.asname or inner.name.split(".")[0])
            elif isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef,
                                    ast.ClassDef)):
                names.add(inner.name)
            elif isinstance(inner, ast.Name) and isinstance(inner.ctx,
                                                            ast.Store):
                names.add(inner.id)
            elif isinstance(inner, ast.arg):
                names.add(inner.arg)
            elif isinstance(inner, ast.ExceptHandler) and inner.name:
                names.add(inner.name)
        return names

    def module_scope_problems(self, path):
        """``[(name, line)]`` read at import time before anything binds them."""
        import builtins
        tree = ast.parse(_read(path))
        bound = set(dir(builtins)) | set(self.INJECTED)
        problems = []

        for statement in tree.body:
            local = self._bound(statement)
            for part in self._immediate(statement):
                for name in self._loads(part):
                    if name.id not in bound and name.id not in local:
                        problems.append((name.id, name.lineno))
            bound |= local
        return problems

    def test_the_check_catches_the_fault_it_was_written_for(self):
        """A check that reports nothing is indistinguishable from a broken one."""
        import tempfile
        handle, path = tempfile.mkstemp(suffix=".py")
        os.close(handle)
        try:
            with io.open(path, "w", encoding="utf-8") as out:
                out.write(u"BUILDABLE = (models.MODE_CREATE_ALL,)\n"
                          u"from anongee_toolkit.rc_automation import models\n")
            problems = self.module_scope_problems(path)
            self.assertEqual([name for name, _line in problems], ["models"])
        finally:
            os.remove(path)

    def test_a_correct_order_is_not_reported(self):
        import tempfile
        handle, path = tempfile.mkstemp(suffix=".py")
        os.close(handle)
        try:
            with io.open(path, "w", encoding="utf-8") as out:
                out.write(u"from anongee_toolkit.rc_automation import models\n"
                          u"BUILDABLE = (models.MODE_CREATE_ALL,)\n"
                          u"def later():\n    return undefined_until_called\n"
                          u"class Thing(object):\n    value = BUILDABLE\n"
                          u"    def method(self):\n        return self.value\n")
            self.assertEqual(self.module_scope_problems(path), [])
        finally:
            os.remove(path)

    def test_the_pushbutton_script_loads_in_order(self):
        problems = self.module_scope_problems(_SCRIPT)
        self.assertEqual(
            problems, [],
            "used before it is defined: " + ", ".join(
                "{0} (line {1})".format(name, line) for name, line in problems))

    def test_every_toolkit_module_loads_in_order(self):
        import glob
        root = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                            "anongee_toolkit")
        checked = 0
        for folder in ("rc_automation", "structural"):
            for path in sorted(glob.glob(os.path.join(root, folder, "*.py"))):
                self.assertEqual(self.module_scope_problems(path), [],
                                 os.path.basename(path))
                checked += 1
        self.assertGreater(checked, 10)


class ReportingTests(unittest.TestCase):
    """What the tool says when it does nothing — which is most of the time.

    Every check here comes from one exported report that was, in its own words,
    a "read-only report" from a build that writes, in an encoding nothing could
    decode, that listed two zeroes and left the reader to work out that the
    model was empty and the mode unsupported.
    """

    def setUp(self):
        self.source = _read(_SCRIPT)

    def test_the_report_is_written_as_utf8(self):
        # open() without an encoding writes cp1252 on Windows, which mangles
        # every dash and makes the file undecodable.
        body = self.source.split("def _on_export")[1].split("\n    def ")[0]
        self.assertIn('encoding="utf-8"', body)
        self.assertNotIn('open(target, "w")', body)

    def test_the_report_does_not_call_itself_read_only(self):
        # It writes now. A report that says otherwise is telling the reader
        # something false about what just happened to their model.
        body = self.source.split("def _report_text")[1].split("\n    def ")[0]
        self.assertNotIn("read-only", body.lower())
        self.assertIn("__version__", body)

    def test_which_modes_can_build_is_decided_in_one_place(self):
        """The count of these messages is not the thing worth pinning.

        An earlier test asserted the sentence appeared at least three times and
        passed happily while all three said the wrong thing: Phase 1 shipped,
        and four comparisons still read "anything but reinforce-existing is
        unsupported", so the report told the user a mode was not built while
        the button beside it would have built it. What matters is that the
        decision is made once.
        """
        self.assertIn("BUILDABLE_MODES", self.source)
        self.assertIn("def can_build", self.source)
        # No surviving hand-rolled comparison against a single mode.
        self.assertNotIn("!= models.MODE_REBAR_ONLY", self.source)

    def test_every_buildable_mode_is_one_the_window_can_plan(self):
        body = self.source.split("def _ready_to_plan")[1].split("\n    def ")[0]
        buildable = self.source.split("BUILDABLE_MODES = (")[1].split(")")[0]
        for mode in ("MODE_CREATE_ALL", "MODE_REBAR_ONLY"):
            self.assertIn(mode, buildable, mode)
            self.assertNotIn(
                "mode == models.{0}".format(mode) + ":", body,
                "{0} must not be refused by _ready_to_plan".format(mode))

    def test_the_mode_is_flagged_when_the_workbook_loads(self):
        # Not only when Plan is pressed — a user who loads, exports and never
        # presses Plan is told nothing otherwise.
        body = self.source.split("def _describe_plan")[1].split("\n    def ")[0]
        self.assertIn("can_build(mode)", body)

    def test_the_probe_states_its_conclusion(self):
        # A reader should not have to infer "nothing to reinforce" from a pair
        # of zeroes.
        self.assertIn("def _verdict", self.source)
        body = self.source.split("def _verdict")[1].split("\n    def ")[0]
        self.assertIn("nothing to reinforce", body)
        self.assertIn("flagged structural", body)

    def test_the_probe_resolves_levels_the_way_the_run_will(self):
        """A set difference is not what the run does, so it must not be what
        the probe reports.

        It called "Foundation" missing from a model containing
        "00 FOUNDATION LVL." — a level the run matches and builds on.
        """
        body = self.source.split("def _missing_level_lines")[1]\
            .split("\n    def ")[0]
        self.assertIn("naming.build_name_map", body)
        self.assertIn("self.workbook.level_map", body)
        self.assertIn("base_level", body)
        self.assertIn("top_level", body)
        self.assertNotIn("wanted - set(", body)


class ToolkitApiTests(unittest.TestCase):
    """Every toolkit attribute the script names actually exists.

    ``script.py`` imports Revit at module scope, so it cannot be imported here
    to find out. But a typo or a renamed function in the toolkit would surface
    as an ``AttributeError`` in a modeless window inside Revit, which is the
    slowest possible place to learn about it -- so the references are checked
    statically instead.
    """

    MODULES = ("models", "excel_engine", "validation", "rebar_spec")

    def setUp(self):
        import sys
        tests_dir = os.path.join(_ROOT, "tests")
        if tests_dir not in sys.path:
            sys.path.insert(0, tests_dir)
        from _rc_loader import load
        self.rc = load()
        self.tree = ast.parse(_read(_SCRIPT))

    def test_every_referenced_attribute_exists(self):
        missing = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Attribute):
                continue
            owner = node.value
            if not isinstance(owner, ast.Name) or owner.id not in self.MODULES:
                continue
            module = getattr(self.rc, owner.id)
            if not hasattr(module, node.attr):
                missing.append("{0}.{1}".format(owner.id, node.attr))
        self.assertEqual(sorted(set(missing)), [])

    def test_the_script_imports_only_modules_the_package_has(self):
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.ImportFrom)
                    and (node.module or "").endswith("rc_automation")):
                for alias in node.names:
                    self.assertTrue(hasattr(self.rc, alias.name), alias.name)

    def test_every_mode_the_window_lists_has_a_label(self):
        # The combo is filled from MODES and labelled from MODE_LABELS; a mode
        # missing a label would raise KeyError as the window opens.
        for mode in self.rc.models.MODES:
            self.assertIn(mode, self.rc.models.MODE_LABELS)


class VersionTests(unittest.TestCase):
    """One build, one number, in all three places it is shown."""

    def test_the_versions_agree(self):
        script = _read(_SCRIPT)
        start = script.index('__version__ = "') + len('__version__ = "')
        version = script[start:script.index('"', start)]
        self.assertIn("Version: {0}".format(version), _read(_BUNDLE))
        self.assertIn("## {0}".format(version), _read(_CHANGELOG))

    def test_the_bundle_names_the_tool(self):
        self.assertIn("title: RC Automation", _read(_BUNDLE))


if __name__ == "__main__":
    unittest.main()

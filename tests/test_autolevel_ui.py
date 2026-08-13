# -*- coding: utf-8 -*-
"""Static checks on the Auto Level Manager's XAML and its Python wiring.

None of this needs Revit, and all of it catches the failures that are most
expensive to find inside Revit: a control the script looks up by a name the
XAML doesn't define (``FindName`` returns ``None`` and the tool dies on the
first click), a ``{Binding}`` path with no matching ``__slots__`` entry (§12.7.G
— the cell renders blank, silently), or a ``{StaticResource}`` on the root
``<Window>`` element, which throws at parse time (§12.7.A).
"""

import ast
import os
import sys
import unittest
import xml.etree.ElementTree as ElementTree

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUTTON = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab",
                       "Essential.panel", "AutoLevel.pushbutton")
_XAML = os.path.join(_BUTTON, "ui.xaml")
_SCRIPT = os.path.join(_BUTTON, "script.py")
_PACKAGE = os.path.join(_BUTTON, "anongee_autolevel")

if _BUTTON not in sys.path:
    sys.path.insert(0, _BUTTON)

from anongee_autolevel import (VERSION, naming, planner,        # noqa: E402
                               settings)

XAML_NS = "{http://schemas.microsoft.com/winfx/2006/xaml}"
PRESENTATION_NS = "{http://schemas.microsoft.com/winfx/2006/xaml/presentation}"


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def load_xaml():
    return ElementTree.parse(_XAML).getroot()


# A ControlTemplate or DataTemplate opens its own WPF name scope, so the same
# x:Name may legitimately appear in several of them. Only names in the window's
# own scope are reachable through window.FindName().
TEMPLATE_TAGS = frozenset((
    PRESENTATION_NS + "ControlTemplate",
    PRESENTATION_NS + "DataTemplate",
    PRESENTATION_NS + "ItemsPanelTemplate",
    PRESENTATION_NS + "HierarchicalDataTemplate",
))


def named_elements(root):
    """{x:Name: tag} for the window's own name scope, templates excluded."""
    names = {}

    def walk(element):
        for child in element:
            if child.tag in TEMPLATE_TAGS:
                continue
            name = child.get(XAML_NS + "Name")
            if name:
                names[name] = child.tag.replace(PRESENTATION_NS, "")
            walk(child)

    walk(root)
    return names


def binding_paths(root):
    """Every ``{Binding Foo...}`` path in the file, deduplicated."""
    paths = set()
    for element in root.iter():
        for value in element.attrib.values():
            text = value.strip()
            start = 0
            while True:
                start = text.find("{Binding", start)
                if start < 0:
                    break
                cursor = start + len("{Binding")
                while cursor < len(text) and text[cursor] == " ":
                    cursor += 1
                path = []
                while cursor < len(text) and (text[cursor].isalnum()
                                              or text[cursor] == "_"):
                    path.append(text[cursor])
                    cursor += 1
                if path:
                    paths.add("".join(path))
                start = cursor
    return paths


# XAML reads any attribute value that STARTS with "{" as a markup extension.
# These are the extensions this file legitimately uses; a literal value that
# happens to start with a brace has to be escaped as "{}...".
MARKUP_EXTENSIONS = ("Binding", "StaticResource", "DynamicResource",
                     "TemplateBinding", "RelativeSource", "x:Static", "x:Null",
                     "x:Type", "x:Array", "Static", "ThemeDictionary",
                     "ComponentResourceKey")


def _static_resource_name(value):
    """The key out of a ``{StaticResource Foo}`` attribute, or None."""
    text = (value or "").strip()
    if not text.startswith("{StaticResource"):
        return None
    return text[len("{StaticResource"):].strip().rstrip("}").strip() or None


def resource_keys(root):
    """Every x:Key defined in the file."""
    keys = set()
    for element in root.iter():
        key = element.get(XAML_NS + "Key")
        if key:
            keys.add(key)
    return keys


def resource_references(root):
    """Every {StaticResource Foo} / {DynamicResource Foo} name used."""
    names = set()
    for element in root.iter():
        for value in element.attrib.values():
            for marker in ("{StaticResource", "{DynamicResource"):
                start = 0
                while True:
                    start = value.find(marker, start)
                    if start < 0:
                        break
                    cursor = start + len(marker)
                    while cursor < len(value) and value[cursor] == " ":
                        cursor += 1
                    name = []
                    while cursor < len(value) and (value[cursor].isalnum()
                                                   or value[cursor] in "_."):
                        name.append(value[cursor])
                        cursor += 1
                    if name:
                        names.add("".join(name))
                    start = cursor
    return names


class XamlTests(unittest.TestCase):

    def test_the_file_is_well_formed(self):
        self.assertIsNotNone(load_xaml())

    def test_no_literal_value_is_mistaken_for_a_markup_extension(self):
        """A value starting with "{" is parsed as markup, not as text.

        This is invisible to an XML parser — the file is perfectly well-formed
        — and it throws at XamlReader.Load, so the window never opens at all.
        It shipped once: a tooltip listing the naming tokens began "{n} 1 ..."
        and XAML read "{n}" as an extension, then choked on the rest with
        "Unexpected token after end of markup extension". The escape is a
        leading "{}".
        """
        offenders = []
        for element in load_xaml().iter():
            tag = element.tag.replace(PRESENTATION_NS, "")
            for key, value in element.attrib.items():
                text = value.lstrip()
                if not text.startswith("{") or text.startswith("{}"):
                    continue
                body = text[1:].lstrip()
                if not any(body.startswith(name) for name in MARKUP_EXTENSIONS):
                    offenders.append("<{0} {1}=\"{2}…\"".format(
                        tag, key, value[:40]))
        self.assertEqual(offenders, [],
                         "escape these with a leading {{}}: "
                         + "; ".join(offenders))

    def test_no_resource_key_is_defined_twice(self):
        """A repeated x:Key in one dictionary throws at load."""
        root = load_xaml()
        seen = [element.get(XAML_NS + "Key") for element in root.iter()
                if element.get(XAML_NS + "Key")]
        duplicates = sorted({key for key in seen if seen.count(key) > 1})
        self.assertEqual(duplicates, [])

    def test_every_style_matches_the_element_it_is_applied_to(self):
        """A Style whose TargetType is not the element's type throws at load."""
        root = load_xaml()
        styles = {}
        for element in root.iter():
            if (element.tag.replace(PRESENTATION_NS, "") == "Style"
                    and element.get(XAML_NS + "Key")):
                styles[element.get(XAML_NS + "Key")] = element.get("TargetType")

        wrong = []
        for element in root.iter():
            key = _static_resource_name(element.get("Style"))
            if not key:
                continue
            target = styles.get(key)
            tag = element.tag.replace(PRESENTATION_NS, "")
            if target and tag != target:
                wrong.append("<{0} Style={1}> targets {2}".format(
                    tag, key, target))
        self.assertEqual(wrong, [])

    def test_every_based_on_style_agrees_on_its_target_type(self):
        """BasedOn across different TargetTypes throws at load."""
        root = load_xaml()
        styles = {}
        for element in root.iter():
            if (element.tag.replace(PRESENTATION_NS, "") == "Style"
                    and element.get(XAML_NS + "Key")):
                styles[element.get(XAML_NS + "Key")] = element.get("TargetType")

        mismatched = []
        for element in root.iter():
            if element.tag.replace(PRESENTATION_NS, "") != "Style":
                continue
            base = _static_resource_name(element.get("BasedOn"))
            if base and styles.get(base) \
                    and element.get("TargetType") != styles[base]:
                mismatched.append("{0} BasedOn {1}".format(
                    element.get(XAML_NS + "Key"), base))
        self.assertEqual(mismatched, [])

    def test_every_trigger_targets_an_element_in_its_own_template(self):
        """A TargetName with no such element throws when the style applies.

        Later than load, and therefore harder to spot: the window opens and
        the control misbehaves only once the trigger fires.
        """
        missing = []
        for template in load_xaml().iter():
            if template.tag not in TEMPLATE_TAGS:
                continue
            names = set(child.get(XAML_NS + "Name") for child in template.iter()
                        if child.get(XAML_NS + "Name"))
            for child in template.iter():
                target = child.get("TargetName")
                if target and target not in names:
                    missing.append("{0} -> {1}".format(
                        template.get("TargetType"), target))
        self.assertEqual(missing, [])

    def test_every_resource_reference_resolves(self):
        """A {StaticResource} naming a key that isn't there throws on load.

        Same failure mode as above — well-formed XML, dead window — so it is
        worth catching here rather than in Revit.
        """
        root = load_xaml()
        keys = resource_keys(root)
        missing = sorted(name for name in resource_references(root)
                         if name not in keys)
        self.assertEqual(missing, [],
                         "no x:Key for: {0}".format(", ".join(missing)))

    def test_the_root_window_uses_literals_only(self):
        """§12.7.A — XamlReader resolves Window attributes before Resources."""
        root = load_xaml()
        for key, value in root.attrib.items():
            self.assertNotIn("StaticResource", value,
                             "Window.{0} uses StaticResource".format(key))
            self.assertNotIn("DynamicResource", value,
                             "Window.{0} uses DynamicResource".format(key))

    def test_every_name_in_the_window_scope_is_unique(self):
        """A repeat in the window's own scope makes FindName ambiguous."""
        root = load_xaml()
        names = named_elements(root)
        seen = []

        def walk(element):
            for child in element:
                if child.tag in TEMPLATE_TAGS:
                    continue
                name = child.get(XAML_NS + "Name")
                if name:
                    seen.append(name)
                walk(child)

        walk(root)
        duplicates = sorted(name for name in names if seen.count(name) > 1)
        self.assertEqual(duplicates, [])

    def test_bindings_resolve_to_row_slots(self):
        """§12.7.G — a binding path with no slot renders an empty cell."""
        allowed = set(planner.LevelRow.__slots__)
        # Bindings onto WPF's own properties rather than the data item.
        allowed.update({"IsDropDownOpen", "ActualWidth"})
        for path in binding_paths(load_xaml()):
            self.assertIn(path, allowed,
                          "{{Binding {0}}} has no LevelRow slot".format(path))

    def test_editable_columns_bind_two_way(self):
        """WPF only offers a real editor for a binding it can write back."""
        text = _read(_XAML)
        for path in ("Name", "ElevText"):
            needle = "{{Binding {0}, Mode=TwoWay}}".format(path)
            self.assertIn(needle, text,
                          "{0} must bind TwoWay to be editable".format(path))

    def test_display_only_columns_bind_one_way(self):
        """Nothing but the two editable columns may write back to a row."""
        text = _read(_XAML)
        for path in ("ProjectText", "DeltaText", "SourceText", "ViewsText",
                     "CountText", "NoteText"):
            needle = "{{Binding {0}, Mode=OneWay}}".format(path)
            self.assertIn(needle, text, "{0} must bind OneWay".format(path))

    def test_a_rejected_edit_cancels_the_commit(self):
        """Otherwise WPF writes the raw text into the slot behind the planner."""
        self.assertIn("args.Cancel = True", _read(_SCRIPT))

    def test_the_grid_checkbox_uses_the_rows_own_flag(self):
        """§12.7.Q — a Python bool does not drive the tick reliably."""
        text = _read(_XAML)
        self.assertIn("RelativeSource={RelativeSource AncestorType=DataGridRow}",
                      text)

    def test_the_scrollbar_style_covers_both_orientations(self):
        """§12.7.P — a vertical-only style renders a broken horizontal bar."""
        text = _read(_XAML)
        self.assertIn('<Trigger Property="Orientation" Value="Vertical">', text)
        self.assertIn('<Trigger Property="Orientation" Value="Horizontal">', text)

    def test_every_interactive_control_carries_a_tooltip(self):
        """The tool has a lot of switches; each one has to say what it does.

        Added after the first round of testing, where the report was "I don't
        know how to use this — too much is going on". A control the user has
        to guess at is a defect, so this is enforced rather than hoped for.
        """
        root = load_xaml()
        needs_tooltip = ("Button", "TextBox", "ComboBox", "CheckBox",
                         "RadioButton", "DataGrid", "Canvas")
        missing = []

        def has_tooltip(element):
            if element.get("ToolTip"):
                return True
            tag = element.tag.replace(PRESENTATION_NS, "")
            # <Canvas.ToolTip> element syntax, for multi-line tips
            for child in element:
                if child.tag.replace(PRESENTATION_NS, "") == tag + ".ToolTip":
                    return True
            return False

        def walk(element):
            for child in element:
                if child.tag in TEMPLATE_TAGS:
                    continue
                name = child.get(XAML_NS + "Name")
                tag = child.tag.replace(PRESENTATION_NS, "")
                if name and tag in needs_tooltip and not has_tooltip(child):
                    missing.append("{0} ({1})".format(name, tag))
                walk(child)

        walk(root)
        self.assertEqual(missing, [],
                         "no ToolTip on: {0}".format(", ".join(missing)))

    def test_the_guide_tab_exists(self):
        """The one place that explains the whole tool in prose."""
        names = named_elements(load_xaml())
        self.assertIn("TabGuide", names)
        self.assertIn("PanelGuide", names)
        self.assertIn("TabHint", names)

    def test_the_editable_combobox_part_is_present(self):
        """§12.7.C — without PART_EditableTextBox, editable mode dies quietly."""
        text = _read(_XAML)
        self.assertIn('x:Name="PART_EditableTextBox"', text)
        self.assertIn('x:Name="PART_ContentHost"', text)


class ScriptWiringTests(unittest.TestCase):

    def setUp(self):
        self.source = _read(_SCRIPT)
        self.tree = ast.parse(self.source)
        self.names = named_elements(load_xaml())

    def _bound_control_names(self):
        """The name tuple inside AutoLevelApp._bind_controls."""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_bind_controls":
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Tuple):
                        values = [item.value for item in inner.elts
                                  if isinstance(item, ast.Constant)
                                  and isinstance(item.value, str)]
                        if len(values) > 5:
                            return values
        return []

    def test_every_looked_up_control_exists_in_the_xaml(self):
        looked_up = self._bound_control_names()
        self.assertTrue(looked_up, "_bind_controls has no name list")
        missing = [name for name in looked_up if name not in self.names]
        self.assertEqual(missing, [],
                         "FindName would return None for: {0}".format(missing))

    def test_every_named_control_the_xaml_defines_is_bound(self):
        """A name in the window scope that nothing looks up is dead weight."""
        looked_up = set(self._bound_control_names())
        unbound = sorted(name for name in self.names if name not in looked_up)
        self.assertEqual(unbound, [],
                         "named but never used by the script: {0}".format(unbound))

    def test_every_tab_has_a_hint_line(self):
        """The strip under the tabs always says what the current tab is for."""
        tabs = [name for name in self.names if name.startswith("Tab")
                and name != "TabHint"]
        for tab in tabs:
            self.assertIn('("{0}",'.format(tab), self.source,
                          "{0} has no entry in TAB_HINTS".format(tab))

    def test_the_stack_drawing_is_interactive(self):
        """Click, drag, double-click and wheel are all wired to the canvas."""
        for handler in ("self.StackCanvas.MouseLeftButtonDown",
                        "self.StackCanvas.MouseMove",
                        "self.StackCanvas.MouseLeftButtonUp",
                        "self.StackCanvas.MouseWheel"):
            self.assertIn(handler, self.source)
        # A drag must release the capture it took, or the canvas eats the mouse.
        self.assertIn("CaptureMouse()", self.source)
        self.assertIn("ReleaseMouseCapture()", self.source)

    def _method_source(self, name):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.get_source_segment(self.source, node) or ""
        self.fail("no method named {0}".format(name))

    def test_the_grid_is_only_rebuilt_at_the_end_of_a_drag(self):
        """Rebuilding ItemsSource per mouse-move would make dragging crawl."""
        moving = self._method_source("_on_canvas_move")
        self.assertNotIn("refresh_grid", moving)
        self.assertIn("draw_stack", moving)
        self.assertIn("refresh_grid", self._method_source("_on_canvas_up"))

    def test_the_rename_placeholder_is_a_name_revit_accepts(self):
        """The two-phase rename parks each level on a temporary name.

        The first version used tildes — "~AutoLevel~0~123" — and "~" is on
        Revit's prohibited list, so every rename failed on the parking step
        and reported the level's OLD name, which read as if the user's own
        names were at fault. The placeholder is built from a format string, so
        check the string itself rather than trusting it by eye.
        """
        source = _read(os.path.join(_PACKAGE, "revit_ops.py"))
        start = source.index("def _placeholder")
        body = source[start:source.index("\n\n\n", start)]
        literals = [chunk for chunk in body.split('"') if "AutoLevel" in chunk]
        self.assertTrue(literals, "no placeholder literal found")
        for literal in literals:
            rendered = literal.replace("{0}", "7").replace("{1}", "123456")
            self.assertEqual(naming.bad_characters(rendered), [],
                             "placeholder {0!r} uses a prohibited character"
                             .format(rendered))

    def test_every_staged_change_takes_a_history_step(self):
        """Undo is only trustworthy if nothing mutates without a checkpoint."""
        for handler in ("_absorb", "_on_generate", "_on_respace",
                        "_on_apply_rename", "_on_mark_delete", "_on_restore",
                        "_on_reset", "_on_cell_edit_ending", "_on_canvas_down"):
            self.assertIn("_checkpoint(", self._method_source(handler),
                          "{0} changes the plan without a history step"
                          .format(handler))

    def test_the_drag_takes_one_history_step_not_one_per_pixel(self):
        self.assertIn("_checkpoint(", self._method_source("_on_canvas_down"))
        self.assertNotIn("_checkpoint(", self._method_source("_on_canvas_move"))

    def test_applying_clears_the_history(self):
        """Those steps described a model that no longer exists."""
        self.assertIn("clear_history()", self._method_source("_on_applied"))

    def test_every_saved_setting_is_read_and_written(self):
        """A key in DEFAULTS that one side forgets silently stops persisting."""
        collect = self._method_source("_collect_settings")
        apply_to_ui = self._method_source("_apply_settings")
        for key in settings.DEFAULTS:
            self.assertIn('"{0}"'.format(key), collect,
                          "_collect_settings never writes {0}".format(key))
        # source_index and the view lists are restored where the model's own
        # contents are known, not in _apply_settings.
        deferred = ("source_index", "view_type_names", "view_template_name")
        for key in settings.DEFAULTS:
            if key in deferred:
                continue
            self.assertIn('"{0}"'.format(key), apply_to_ui,
                          "_apply_settings never reads {0}".format(key))
        source = self.source
        for key in deferred:
            self.assertIn('"{0}"'.format(key), source,
                          "{0} is saved but never restored".format(key))

    def test_undo_and_redo_are_reachable_by_keyboard_and_button(self):
        names = named_elements(load_xaml())
        self.assertIn("UndoBtn", names)
        self.assertIn("RedoBtn", names)
        self.assertIn("PreviewKeyDown", self.source)
        keys = self._method_source("_on_key_down")
        self.assertIn("Key.Z", keys)
        self.assertIn("Key.Y", keys)
        # Ctrl+Z inside a text box belongs to the text box.
        self.assertIn("TextBox", keys)

    def test_no_pyrevit_imports(self):
        """§12.8.4 — pyRevit's IronPython modules crash the CPython 3 engine."""
        for path in _python_files():
            text = _read(path)
            self.assertNotIn("from pyrevit", text, path)
            self.assertNotIn("import pyrevit", text, path)

    def test_no_re_module(self):
        """§12.9.3 — `re` is missing from this engine's stripped stdlib."""
        for path in _python_files():
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(alias.name, "re", path)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "re", path)

    def test_no_star_imports(self):
        """§12.1 — Python.NET 3 needs explicit imports."""
        for path in _python_files():
            tree = ast.parse(_read(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        self.assertNotEqual(alias.name, "*", path)

    def test_the_clr_classes_are_defined_once_per_session(self):
        """§12.8.7.1 — re-running the class statement raises on the 2nd press."""
        self.assertIn("_state.handler_cls is None", self.source)
        self.assertIn("_state.preprocessor_cls is None", self.source)
        self.assertIn('__namespace__ = "AnonGee"', self.source)

    def test_the_interface_subclasses_have_no_init(self):
        """§12.8.7.1 rule 2 — a constructor trips pythonnet's interface __new__."""
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [base.id for base in node.bases if isinstance(base, ast.Name)]
            if not any(base.startswith("I") for base in bases):
                continue
            methods = [item.name for item in node.body
                       if isinstance(item, ast.FunctionDef)]
            self.assertNotIn("__init__", methods,
                             "{0} defines __init__".format(node.name))

    def test_the_window_is_shown_modeless_and_anchored_after(self):
        """§12.8.3 — anchoring before Show() puts the window behind Revit."""
        show = self.source.index("self.window.Show()")
        anchor = self.source.index("helper.Owner = __revit__.MainWindowHandle")
        self.assertLess(show, anchor)
        # The file dialog's ShowDialog() is fine; the tool window's is not.
        self.assertNotIn("self.window.ShowDialog", self.source)

    def test_typed_lists_are_built_with_add(self):
        """§12.9.4 — List[T](python_list) is a fatal marshalling fault."""
        text = _read(os.path.join(_PACKAGE, "revit_ops.py"))
        self.assertIn("ids = List[ElementId]()", text)
        self.assertIn("ids.Add(element_id)", text)

    def test_every_module_compiles(self):
        for path in _python_files():
            compile(_read(path), path, "exec")


def _python_files():
    paths = [_SCRIPT]
    for name in sorted(os.listdir(_PACKAGE)):
        if name.endswith(".py"):
            paths.append(os.path.join(_PACKAGE, name))
    return paths


class VersionTests(unittest.TestCase):
    """The version is written in four places; they have to agree.

    The header badge is what a user can see and quote, so it has to be the
    build they are actually running — which means one constant feeding
    everything else, and a test to keep it that way.
    """

    def test_the_version_is_semantic(self):
        parts = VERSION.split(".")
        self.assertEqual(len(parts), 3,
                         "{0} is not MAJOR.MINOR.PATCH".format(VERSION))
        for part in parts:
            self.assertTrue(part.isdigit(),
                            "{0} is not MAJOR.MINOR.PATCH".format(VERSION))

    def test_the_bundle_tooltip_states_the_same_version(self):
        bundle = _read(os.path.join(_BUTTON, "bundle.yaml"))
        self.assertIn("Version: {0}".format(VERSION), bundle)

    def test_the_changelog_leads_with_this_version(self):
        changelog = _read(os.path.join(_BUTTON, "CHANGELOG.md"))
        headings = [line.strip() for line in changelog.splitlines()
                    if line.startswith("## ")]
        self.assertTrue(headings, "CHANGELOG.md has no version headings")
        self.assertEqual(headings[0], "## {0}".format(VERSION),
                         "newest CHANGELOG entry is {0}, package says {1}"
                         .format(headings[0], VERSION))

    def test_every_released_version_is_written_down(self):
        changelog = _read(os.path.join(_BUTTON, "CHANGELOG.md"))
        headings = [line[3:].strip() for line in changelog.splitlines()
                    if line.startswith("## ")]
        for heading in headings:
            parts = heading.split(".")
            self.assertEqual(len(parts), 3, heading)
            for part in parts:
                self.assertTrue(part.isdigit(), heading)
        self.assertEqual(headings, sorted(
            headings, key=lambda v: [int(p) for p in v.split(".")], reverse=True),
            "CHANGELOG entries are not newest-first")

    def test_the_window_shows_the_version(self):
        script = _read(_SCRIPT)
        self.assertIn('self.VersionText.Text = "v{0}".format(VERSION)', script)
        self.assertIn("VersionText", named_elements(load_xaml()))


class BundleTests(unittest.TestCase):

    def test_the_bundle_ships_what_pyrevit_needs(self):
        for name in ("bundle.yaml", "icon.png", "ui.xaml", "script.py",
                     "CHANGELOG.md"):
            self.assertTrue(os.path.isfile(os.path.join(_BUTTON, name)), name)

    def test_the_script_targets_cpython_3(self):
        first = _read(_SCRIPT).splitlines()[0].strip()
        self.assertEqual(first, "#! python3")

    def test_the_panel_layout_lists_the_button(self):
        layout = _read(os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab",
                                    "Essential.panel", "bundle.yaml"))
        self.assertIn("AutoLevel", layout)


if __name__ == "__main__":                                    # pragma: no cover
    unittest.main(verbosity=2)

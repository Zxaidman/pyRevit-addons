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

from anongee_autolevel import planner                            # noqa: E402

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


class XamlTests(unittest.TestCase):

    def test_the_file_is_well_formed(self):
        self.assertIsNotNone(load_xaml())

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


class BundleTests(unittest.TestCase):

    def test_the_bundle_ships_what_pyrevit_needs(self):
        for name in ("bundle.yaml", "icon.png", "ui.xaml", "script.py"):
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

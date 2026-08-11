# -*- coding: utf-8 -*-
"""The pushbutton dialog and its XAML must agree on every named control.

A control added to ui.xaml but never bound in script.py (or bound but missing
from the XAML) only fails when the user opens the dialog in Revit -- exactly how
v0.59.0's `tb_slab_step` got out. Both files are plain text here, so the check
is a static one: no Revit, no WPF, no XamlReader.
"""

import ast
import os
import re
import unittest
import xml.etree.ElementTree as ET

_HERE = os.path.dirname(os.path.abspath(__file__))
_BUTTON = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "..", "..",
    "AnonGee.tab", "Core.panel", "cad2bim.pushbutton"))
_SCRIPT = os.path.join(_BUTTON, "script.py")
# the dialogs moved into the library; the button keeps the run pipeline
_WINDOW = os.path.normpath(os.path.join(_HERE, "..", "ui_window.py"))
# ...and the element-creation drivers moved beside them
_BUILDERS = os.path.normpath(os.path.join(_HERE, "..", "run_builders.py"))
_XAML = os.path.join(_BUTTON, "ui.xaml")
_LINK_XAML = os.path.join(_BUTTON, "link_options.xaml")

_FIND = re.compile(r'\bfind\(\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)')


def _xaml_names(*paths):
    """Every x:Name in the given .xaml files (both dialogs by default)."""
    key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
    names = set()
    for path in (paths or (_XAML, _LINK_XAML)):
        names.update(el.get(key) for el in ET.parse(path).iter() if el.get(key))
    return names


def _script_source():
    """The pushbutton itself -- the run pipeline and its entry point."""
    with open(_SCRIPT, "rb") as handle:
        return handle.read().decode("utf-8")


def _window_source():
    """The dialog: every control binding lives here now."""
    with open(_WINDOW, "rb") as handle:
        return handle.read().decode("utf-8")


def _builders_source():
    """The element-creation drivers: one transaction and one outcome per kind."""
    with open(_BUILDERS, "rb") as handle:
        return handle.read().decode("utf-8")


def _all_source():
    """Both, for checks that span the dialog and the run it starts."""
    return "\n".join((_script_source(), _window_source(),
                      _builders_source()))


class DialogControlNames(unittest.TestCase):
    def test_every_bound_control_exists_in_the_xaml(self):
        missing = sorted(set(_FIND.findall(_window_source())) - _xaml_names())
        self.assertEqual(missing, [], "bound but absent from ui.xaml: %s" % missing)

    def test_every_control_the_dialog_uses_is_bound(self):
        """self.tb_x / self.cb_x / self.chk_x must come from a find(...) call.

        Catches the reverse slip: a new textbox read by _init_tolerances or
        _read_tolerances that nobody ever assigned.
        """
        source = _window_source()
        bound = set(_FIND.findall(source))
        prefixes = ("tb_", "cb_", "chk_", "rb_", "btn_", "lbl_")
        assigned = set()
        used = set()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Name) or node.value.id != "self":
                continue
            if not node.attr.startswith(prefixes):
                continue
            if isinstance(node.ctx, ast.Store):
                assigned.add(node.attr)
            else:
                used.add(node.attr)
        unbound = sorted(name for name in used
                         if name not in bound and name not in assigned)
        self.assertEqual(unbound, [],
                         "used but never bound to a control: %s" % unbound)


class SlabToleranceRow(unittest.TestCase):
    """Every slab tolerance on the Tolerances tab reaches slab_outlines."""

    def test_slab_tolerance_boxes_are_all_present(self):
        names = _xaml_names(_XAML)
        for control in ("tb_slab_snap", "tb_slab_heal", "tb_slab_chain",
                        "tb_slab_width", "tb_slab_step", "tb_slab_note_area"):
            self.assertIn(control, names)

    def test_every_tolerance_the_build_reads_is_on_the_tab(self):
        """The user's standing rule: a tolerance the project uses is shown here.

        Every key _read_tolerances returns has to come from a control, not from
        a constant buried in a module.
        """
        source = _window_source()
        block = source.split("def _read_tolerances(", 1)[1].split(
            "def ", 1)[0]
        keys = re.findall(r'"([a-z0-9_]+)":\s*self\._read_(?:float|int)\(',
                          block)
        self.assertGreater(len(keys), 10)
        for key in ("slab_note_min_area_m2", "face_label_reach_mm",
                    "face_size_tol_mm"):
            self.assertIn(key, keys, "%s is not read from a control" % key)


class NamingTabControls(unittest.TestCase):
    """The Naming tab's boxes are bound through a format string, so the static
    find() check cannot see them -- list them explicitly instead."""

    _CONTROL = {"column_rect": "column", "column_round": "column_round",
                "beam_sized": "beam", "beam_width": "beam_width",
                "floor": "floor", "stair": "stair",
                "stair_waist": "stair_waist", "level": "level",
                "grid": "grid", "footing": "footing"}

    def test_one_box_and_one_preview_per_template(self):
        names = _xaml_names(_XAML)
        for control in self._CONTROL.values():
            self.assertIn("tb_name_{0}".format(control), names)
            self.assertIn("lbl_name_{0}".format(control), names)
        self.assertIn("btn_name_defaults", names)
        self.assertIn("naming_saved_text", names)
        self.assertIn("chk_level_follow", names)

    def _template_keys(self):
        with open(os.path.join(os.path.dirname(_HERE), "naming.py"),
                  "rb") as handle:
            source = handle.read().decode("utf-8")
        block = source.split("DEFAULTS = {", 1)[1].split("}", 1)[0]
        keys = re.findall(r'"([a-z_]+)":', block)
        self.assertTrue(keys)
        return keys

    def test_every_template_key_has_a_dialog_row(self):
        names = _xaml_names(_XAML)
        for key in self._template_keys():
            self.assertIn(key, self._CONTROL,
                          "no dialog row for template %r" % key)
            self.assertIn("tb_name_{0}".format(self._CONTROL[key]), names)

    def test_every_template_key_is_bound_in_the_dialog(self):
        """A row in the XAML that __init__ never binds is a dead box.

        `footing` was exactly that: the template, the row and the preview label
        all existed, and the box came up blank because the binding loop had
        nine keys in it instead of ten.
        """
        source = _window_source()
        block = source.split("self.name_boxes = {}", 1)[1].split(
            "self.naming_saved_text", 1)[0]
        bound = set(re.findall(r'\("([a-z_]+)",\s*"[a-z_]+"\)', block))
        for key in self._template_keys():
            self.assertIn(key, bound, "the Naming tab never binds %r" % key)


class MaterialAndFootingControls(unittest.TestCase):
    """Material combos are bound through a format string over materials.KINDS."""

    def test_one_material_combo_per_kind(self):
        with open(os.path.join(os.path.dirname(_HERE), "builders",
                               "materials.py"), "rb") as handle:
            source = handle.read().decode("utf-8")
        block = source.split("KINDS = (", 1)[1].split(")", 1)[0]
        kinds = re.findall(r'"([a-z_]+)"', block)
        self.assertTrue(kinds)
        names = _xaml_names(_XAML)
        for kind in kinds:
            self.assertIn("cb_mat_{0}".format(kind), names)

    def test_the_footing_row_is_on_the_structure_tab(self):
        names = _xaml_names(_XAML)
        for control in ("chk_footings", "cb_footing_family",
                        "tb_footing_projection", "tb_footing_thickness",
                        "chk_view_filters"):
            self.assertIn(control, names)


class OutcomesReachTheExportClean(unittest.TestCase):
    """The live ElementIds the material pass needs must not reach json.dump."""

    def _script_namespace(self):
        source = _builders_source()
        start = source.index('_IDS = "_element_ids"')
        end = source.index("def _skip_details(")
        namespace = {}
        exec(compile(source[start:end], "<script>", "exec"), namespace)
        return namespace

    def test_strip_ids_removes_the_id_key_and_keeps_the_rest(self):
        namespace = self._script_namespace()
        outcomes = {"columns": {"rect": 3, namespace["_IDS"]: ["id1", "id2"]},
                    "beams": {"created": 9},
                    "materials": {"column": {"elements": 3}}}
        clean = namespace["_strip_ids"](outcomes)
        self.assertNotIn(namespace["_IDS"], clean["columns"])
        self.assertEqual(clean["columns"]["rect"], 3)
        self.assertEqual(clean["beams"]["created"], 9)
        self.assertEqual(clean["materials"], {"column": {"elements": 3}})
        # the original is untouched: the material pass still needs the ids
        self.assertIn(namespace["_IDS"], outcomes["columns"])

    def test_every_material_kind_records_the_ids_it_created(self):
        """A creator that returns counts only is invisible to the material pass.

        `_create_beams` did exactly that: the beams outcome had no _IDS key, so
        `_apply_materials` found no elements and said "nothing of this kind was
        built" on every run with beams in it.
        """
        source = _builders_source()
        creator = {"column": "_create_columns", "beam": "_create_beams",
                   "slab": "_create_slabs", "stair": "_create_stairs",
                   "footing": "_create_footings"}
        tree = ast.parse(source)
        functions = dict((node.name, node) for node in ast.walk(tree)
                         if isinstance(node, ast.FunctionDef))
        for kind, name in creator.items():
            node = functions.get(name)
            self.assertIsNotNone(node, "no %s in script.py" % name)
            records = False
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Dict):
                    continue
                for key in inner.keys:
                    if isinstance(key, ast.Name) and key.id == "_IDS":
                        records = True
            self.assertTrue(records,
                            "%s never records _IDS: %s takes no material"
                            % (name, kind))

    def test_no_outcome_dict_exports_an_id_list_under_a_plain_key(self):
        # reading a builder's own result["created_ids"] is fine; putting one
        # into an outcome dict under a plain key is what broke the export
        source = _builders_source()
        self.assertNotIn('"created_ids":', source,
                         "an outcome dict exports an id list under a plain key")


class StoreyTableIsSelectable(unittest.TestCase):
    """The storey stack has to be pickable, and visibly so.

    Rows were a StackPanel of Grids with a click handler on the Grid: the combo
    box and text boxes inside each row swallowed the mouse, so the handler
    rarely fired and nothing ever looked selected. A ListBox gives native
    selection -- highlight, arrow keys, SelectedIndex -- for free.
    """

    def test_the_storey_table_is_a_listbox(self):
        tree = ET.parse(_XAML)
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        found = [el for el in tree.iter() if el.get(key) == "storey_rows"]
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0].tag.endswith("ListBox"),
                        "storey_rows is %s, not a ListBox" % found[0].tag)

    def test_the_row_click_is_a_preview_handler(self):
        # a bubbling handler never sees the click: the child controls take it
        source = _window_source()
        self.assertIn("PreviewMouseLeftButtonDown", source)
        self.assertNotIn("grid.MouseLeftButtonDown", source)

    def test_selection_drives_the_move_buttons(self):
        source = _window_source()
        self.assertIn("self.storey_rows.SelectedIndex", source)
        self.assertIn("storey_selection_text", source)
        names = _xaml_names(_XAML)
        for control in ("btn_storey_up", "btn_storey_down", "btn_storey_add",
                        "btn_storey_remove", "storey_selection_text"):
            self.assertIn(control, names)


class LevelNamesReachTheBuilder(unittest.TestCase):
    """The Naming tab decides what a created level is called.

    _storey_level_pairs hard-coded "CAD Level {0}" at the Level.Create call, so
    naming.level_name -- written and tested -- was called by nothing at all.
    """

    def test_the_level_name_comes_from_naming(self):
        source = _script_source()
        self.assertIn("naming.level_name(", source)
        self.assertIn("naming.next_level_names(", source)

    def test_no_hard_coded_level_name_is_left(self):
        source = _script_source()
        self.assertNotIn('"CAD Level {0}".format', source)

    def test_following_the_model_is_a_choice_the_dialog_offers(self):
        # the tick is on the dialog, the decision is read in the run pipeline
        source = _all_source()
        self.assertIn('"level_follow_existing"', source)
        self.assertIn("self.chk_level_follow", source)


class TheEngineKeepsModulesBetweenRuns(unittest.TestCase):
    """A fresh click must run the library on disk, not last session's copy.

    The CPython3 engine outlives a run: script.py is re-read every click, its
    imports are not. v0.67.1 shipped naming.next_level_names and a session that
    had already run v0.67.0 raised AttributeError on it until Revit restarted.
    """

    def test_stale_modules_are_dropped_before_the_imports(self):
        source = _script_source()
        purge = source.index("def _drop_stale_modules(")
        call = source.index("\n_drop_stale_modules()")
        first_import = source.index("\nfrom anongee_toolkit import cad2bim")
        registry = source.index("\nimport anongee_clr")
        self.assertLess(purge, call)
        self.assertLess(call, first_import)
        # the CLR registry is imported AFTER the purge and is not part of it:
        # it holds this session's emitted types and must outlive the reload
        self.assertLess(call, registry)
        self.assertLess(registry, first_import)

    def test_the_parent_attribute_goes_too(self):
        # `from anongee_toolkit import cad2bim` reads the attribute off the
        # parent module and never consults sys.modules
        source = _script_source()
        block = source.split("def _drop_stale_modules(", 1)[1].split(
            "\n\n_bootstrap", 1)[0]
        self.assertIn("del sys.modules[name]", block)
        self.assertIn("delattr(parent", block)

    def test_a_library_older_than_the_button_says_so_up_front(self):
        source = _script_source()
        self.assertIn("_library_mismatch()", source)
        for attribute in ("next_level_names", "recover_face_columns",
                          "loops_for_unclaimed_notes"):
            self.assertIn(attribute, source)


class SettingsSaveAndLoad(unittest.TestCase):
    """The whole dialog has to survive a Revit session, not just two boxes."""

    def test_the_footer_has_both_buttons(self):
        names = _xaml_names(_XAML)
        for control in ("btn_settings_save", "btn_settings_load", "status_text"):
            self.assertIn(control, names)

    def test_the_buttons_are_wired(self):
        source = _all_source()
        self.assertIn("self.btn_settings_save.Click += self.on_settings_save",
                      source)
        self.assertIn("self.btn_settings_load.Click += self.on_settings_load",
                      source)

    def test_the_run_remembers_the_whole_dialog(self):
        source = _all_source()
        self.assertIn('"dialog": self._capture_settings()', source)
        self.assertIn('_saved_prefs.get("dialog")', source)
        self.assertIn("saved_settings=saved_settings", source)

    def test_capture_is_driven_by_the_xaml_names(self):
        """Listing controls by hand is how a new one gets forgotten."""
        source = _all_source()
        self.assertIn("for name in _control_names():", source)
        self.assertIn("settings.saveable(name)", source)
        self.assertIn("settings.restorable(name)", source)

    def test_every_saveable_xaml_control_is_a_kind_capture_understands(self):
        """A control type _control_value cannot read saves as nothing at all."""
        import xml.etree.ElementTree as Tree
        known = ("TextBox", "CheckBox", "RadioButton", "ComboBox", "Slider",
                 "TextBlock", "ListBox", "Button", "StackPanel", "Grid",
                 "Border", "Expander", "TabItem", "ScrollViewer", "Window",
                 "Separator", "Label")
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        unknown = []
        for element in Tree.parse(_XAML).iter():
            name = element.get(key)
            if not name:
                continue
            tag = element.tag.rsplit("}", 1)[-1]
            if tag not in known:
                unknown.append((name, tag))
        self.assertEqual(unknown, [],
                         "settings cannot read these control types: %s"
                         % unknown)


if __name__ == "__main__":
    unittest.main()

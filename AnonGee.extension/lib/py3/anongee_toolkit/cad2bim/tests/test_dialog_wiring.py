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


def _tab_homes():
    """{x:Name: tab header} for every named control under a TabItem.

    Which tab a control sits on is invisible to FindName -- WPF resolves names
    per window -- so a control pasted onto the wrong tab still binds and still
    runs. Only the user sees the difference, which makes the tab a thing worth
    asserting."""
    key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
    homes = {}

    def walk(element, header):
        if element.tag.endswith("TabItem"):
            header = element.get("Header")
        name = element.get(key)
        if name and header:
            homes[name] = header
        for child in element:
            walk(child, header)
    walk(ET.parse(_XAML).getroot(), None)
    return homes


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

    def test_the_footing_row_lives_on_the_foundations_tab(self):
        homes = _tab_homes()
        for control in ("chk_footings", "cb_footing_family",
                        "tb_footing_projection", "tb_footing_thickness",
                        "tb_max_step", "tb_fnd_min_area"):
            self.assertEqual(homes.get(control), "Foundations",
                             "%s sits on %r" % (control, homes.get(control)))
        self.assertEqual(homes.get("chk_view_filters"), "Output & Graphics")


class TheDialogTabSet(unittest.TestCase):
    """The restructure's contract: eight tabs, every moved control on its new one.

    Settings files restore controls BY NAME, so moving a node between tabs is
    free -- but a control moved by copy-paste is easily left behind in the old
    tab too, and a duplicated x:Name is something XamlReader only refuses at
    runtime, in Revit, exactly where these checks exist not to look.
    """

    _TABS = ["Layers", "Elements", "Foundations", "Stairs", "Multi-storey",
             "Tolerances", "Output & Graphics", "Naming"]

    def test_the_eight_tabs_in_order(self):
        headers = [el.get("Header") for el in ET.parse(_XAML).iter()
                   if el.tag.endswith("TabItem")]
        self.assertEqual(headers, self._TABS)

    def test_no_name_is_declared_twice(self):
        key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
        for path in (_XAML, _LINK_XAML):
            names = [el.get(key) for el in ET.parse(path).iter() if el.get(key)]
            doubled = sorted(name for name in set(names)
                             if names.count(name) > 1)
            self.assertEqual(doubled, [], "%s declares twice: %s"
                             % (os.path.basename(path), doubled))

    def test_the_moved_controls_landed_where_the_layout_says(self):
        homes = _tab_homes()
        for control, tab in (("chk_stairs", "Stairs"),
                             ("chk_export", "Output & Graphics"),
                             ("tb_compare", "Output & Graphics"),
                             ("tb_grid_snap", "Tolerances"),
                             ("cb_name_param", "Elements")):
            self.assertEqual(homes.get(control), tab,
                             "%s sits on %r" % (control, homes.get(control)))


class TheNewTolerancesAreWired(unittest.TestCase):
    """A box on the dialog is only real once it is seeded AND read back out.

    max_step_mm is the cautionary tale: run_builders read it from the
    tolerances dict since the fold planner landed, and nothing ever put it
    there -- no box, no _read_tolerances key, a dead wire the fixture runs
    could not see because the default happened to match. These checks tie
    each new key to a control at both ends.
    """

    _WIRES = {  # x:Name -> the tolerances key its box feeds
        "tb_grid_snap": "grid_snap_mm",
        "tb_pair_overlap": "pair_min_overlap_mm",
        "tb_parallel_angle": "parallel_angle_deg",
        "tb_junction_tol": "junction_tol_mm",
        "tb_concentric_tol": "concentric_tol_mm",
        "tb_max_step": "max_step_mm",
        "tb_fnd_min_area": "foundation_min_area_m2",
    }

    def test_each_box_is_in_the_xaml(self):
        names = _xaml_names(_XAML)
        for control in self._WIRES:
            self.assertIn(control, names)

    def test_each_box_is_seeded_from_the_defaults(self):
        block = _window_source().split("def _init_tolerances(", 1)[1].split(
            "\n    def ", 1)[0]
        for control in self._WIRES:
            self.assertIn("self.{0}.Text".format(control), block,
                          "%s is never seeded" % control)

    def test_each_key_is_emitted_from_its_box(self):
        block = _window_source().split("def _read_tolerances(", 1)[1].split(
            "\n    def ", 1)[0]
        keys = re.findall(r'"([a-z0-9_]+)":\s*self\._read_(?:float|int)\(',
                          block)
        for control, key in self._WIRES.items():
            self.assertIn(key, keys, "%s is not read from a control" % key)
            self.assertIn("self.{0}".format(control), block)

    def test_the_dead_wire_is_live_at_both_ends(self):
        # the consumers already read these keys off the tolerances dict; what
        # was missing was the dialog EMITTING them
        self.assertIn('.get("max_step_mm")', _builders_source())
        window = _window_source()
        self.assertIn('"max_step_mm": self._read_float(', window)
        self.assertIn('"foundation_min_area_m2": self._read_float(', window)


class TheDrawStairsRoundTripKeepsTheWholeDialog(unittest.TestCase):
    """Closing the window to draw outlines must not cost the user's settings.

    _apply_preset used to re-enumerate the dialog by hand and put back only
    the ~45 values it happened to name; every control added since fell to its
    default on reopen. The preset now carries the same snapshot a settings
    file does, restored through the same path, so the two cannot drift apart
    again.
    """

    def test_collect_carries_the_snapshot(self):
        block = _window_source().split("def _collect(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn('"preset_payload": self._capture_settings()', block)

    def test_the_preset_lands_through_the_settings_path(self):
        block = _window_source().split("def _apply_preset(", 1)[1].split(
            "\n    def ", 1)[0]
        self.assertIn('preset.get("preset_payload")', block)
        self.assertIn("self._restore_controls(", block)
        # the live parts the snapshot cannot carry keep their special handling
        self.assertIn('preset.get("storey_settings")', block)
        self.assertIn("self._show_outline_count()", block)


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


class TheDrawnFoundationsReachTheBuilder(unittest.TestCase):
    """The drawing-fed footing path is Revit-side, so only a static check sees it.

    Every link in it fails QUIETLY. Drop the records or the notes at the call
    and `plan_foundations` reads an empty drawing; drop `outlines=` and the
    builder falls back to the column-offset derivation. Either way the run says
    "footings created" and lays invented pads over a drawing that showed the
    real ones -- the same class of silent wrong answer as the swallowed type
    clash in v0.68.1, and unreachable by the offline harnesses because
    builders/footings.py imports Revit at module level.
    """

    def _function(self, source, name):
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return node
        self.fail("no %s" % name)

    def _call(self, node, name):
        """The call to `name` (plain or dotted) inside `node`."""
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            called = (func.id if isinstance(func, ast.Name)
                      else getattr(func, "attr", None))
            if called == name:
                return inner
        return None

    def test_the_storey_hands_its_geometry_and_notes_to_the_footings(self):
        call = self._call(self._function(_script_source(), "_build_one_storey"),
                          "_create_footings")
        self.assertIsNotNone(call, "_build_one_storey never creates footings")
        passed = set(keyword.arg for keyword in call.keywords)
        for argument in ("records", "texts"):
            self.assertIn(argument, passed,
                          "the footing pass is called without %s: the drawing's "
                          "own foundations cannot be read" % argument)

    def test_the_notes_are_routed_by_layer_and_never_fall_back_to_all_text(self):
        # a BARE "1200MM THK" is a raft on the foundation layer and a slab note
        # anywhere else; only the routing separates them, so the slab notes'
        # "use every text when nothing is routed" fallback would claim them
        source = _script_source()
        self.assertIn("CATEGORY_FOUNDATION_TEXT", source)
        assignments = [node for node in ast.walk(ast.parse(source))
                       if isinstance(node, ast.Assign)
                       and any(getattr(t, "id", None) == "foundation_texts"
                               for t in node.targets)]
        self.assertEqual(len(assignments), 1,
                         "foundation_texts is assigned more than once: one of "
                         "them is a fall back to every text in the drawing")
        self.assertIsInstance(assignments[0].value, ast.ListComp)

    def test_the_outlines_the_drawing_carries_reach_place_footings(self):
        node = self._function(_builders_source(), "_create_footings")
        self.assertIsNotNone(self._call(node, "plan_foundations"),
                             "the footing pass never reads the drawing")
        call = self._call(node, "place_footings")
        self.assertIsNotNone(call, "the footing pass places nothing")
        self.assertIn("outlines", [keyword.arg for keyword in call.keywords],
                      "place_footings is called without the drawn outlines: "
                      "every run falls back to pads invented from the columns")

    def test_the_hatches_are_moved_and_classified_like_everything_else(self):
        """A region read but never placed or categorised is a region ignored.

        The reader keeps hatches OUT of `records`, which is what stopped them
        reaching the column passes -- and also what stops them being carried by
        anything that walks records. Both passes have to name them explicitly.
        """
        source = _script_source()
        self.assertIn("transform.apply_to_records(text_affine, dxf_result.regions)",
                      source, "hatches are never moved into model coordinates")
        self.assertIn("layers.apply_mapping(dxf_result.regions", source,
                      "hatches are never classified, so no fold is a fold")

    def test_each_storey_keeps_the_hatches_drawn_on_it(self):
        # one DXF holds every storey side by side; a fold belongs to the plan it
        # was drawn on, so the splitter has to carry hatches as it carries
        # records, or the foundation storey inherits the whole sheet's folds
        source = _script_source()
        self.assertIn("hatches=dxf_result.regions", source)
        self.assertIn("hatches=region.regions", source)
        call = self._call(self._function(_builders_source(), "_create_footings"),
                          "place_footings")
        self.assertIn("steps", [keyword.arg for keyword in call.keywords],
                      "the planned steps never reach the builder")

    def test_the_region_limit_is_read_where_the_dialog_files_it(self):
        # it lives in TOLERANCES, where the column pass reads it; the footing
        # pass looked in "limits" and so always found None, which meant the
        # user's own setting never reached it
        call = self._call(self._function(_builders_source(), "_create_footings"),
                          "place_footings")
        keyword = [k for k in call.keywords if k.arg == "region_max_side_mm"]
        self.assertEqual(len(keyword), 1)
        read = set(node.value for node in ast.walk(keyword[0])
                   if isinstance(node, ast.Constant)
                   and isinstance(node.value, str))
        self.assertIn("tolerances", read)
        self.assertNotIn("limits", read)


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


class AnOldLibraryIsReportedNotCrashed(unittest.TestCase):
    """The button imports five modules that a stale library will not have.

    Those imports run at MODULE level, before main() can catch anything, so an
    ImportError there would surface as a raw traceback instead of the sentence
    _library_mismatch exists to give. The import is therefore deferred into a
    reported failure -- and the report itself needs names the failed import was
    supposed to provide.
    """

    def test_the_new_module_imports_are_guarded(self):
        source = _script_source()
        block = source.split("_MISSING_MODULE = None", 1)[1].split(
            "_HERE = ", 1)[0]
        self.assertIn("try:", block)
        self.assertIn("except ImportError", block)
        for module in ("run_builders", "run_picking", "ui_window", "ui_dialogs",
                       "run_console"):
            self.assertIn(module, block, "%s imported outside the guard" % module)

    def test_the_failure_path_can_still_talk(self):
        """Every name main() uses to REPORT the failure must have a fallback."""
        source = _script_source()
        tree = ast.parse(source)
        handler = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            for candidate in node.handlers:
                if any(isinstance(inner, ast.Assign)
                       and getattr(inner.targets[0], "id", "") == "_MISSING_MODULE"
                       for inner in ast.walk(candidate)):
                    handler = candidate
        self.assertIsNotNone(handler, "the guarded import has no handler")
        defined = set()
        for node in ast.walk(handler):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
        for name in ("_say", "_alert", "_error", "_OUT", "_close_progress"):
            self.assertIn(name, defined,
                          "%s has no fallback: the report would raise" % name)

    def test_the_missing_module_reaches_the_report(self):
        source = _script_source()
        block = source.split("def _library_mismatch(", 1)[1].split("\n\n\n", 1)[0]
        self.assertIn("_MISSING_MODULE", block)


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

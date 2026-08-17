# -*- coding: utf-8 -*-
"""The two windows: Link DXF, and the main cad2bim dialog.

Both are CAPTURE-ONLY. They hold no Revit API references and write nothing to
the model -- they gather the user's choices into `self.result` and close, and
every model write happens afterwards on the Revit API thread. That separation is
what lets the whole run be replayed offline from an exported JSON.

The main dialog's tabs are its structure: Layers, Build, Multi-storey,
Tolerances, Output & Graphics, Naming -- with Build split discipline-wise into
General, Structure, Architecture, Foundation and Staircase sub-tabs (a
nested TabControl; FindName resolves per window, so the bindings below never
care about the nesting). Two of the tabs
carry state that outlives the run -- the naming templates and the standard sizes
are office conventions kept in the preferences file, and the whole dialog is
snapshotted so the next session opens where this one left off.

The XAML lives beside the pushbutton, not beside this module, so the button
hands over both paths with `use_xaml()` before opening anything.
"""

import os
import xml.etree.ElementTree as ElementTree

from System.Windows import (Thickness, GridLength, GridUnitType,
                            VerticalAlignment)
from System.Windows.Controls import (Grid as WpfGrid, ColumnDefinition, TextBlock,
                                     ComboBox, TextBox, CheckBox, ListBoxItem)

from . import config, floor_plans, naming, prefs, report, settings, stair_layout
from .builders import materials
from .classify import layers
from .readers import dxf_linker
from .run_console import _say
from .ui_dialogs import (_alert, _load_window, _select_containing, _open_dxf,
                         _control_value, _set_control_value,
                         _open_settings_file, _save_settings_file)

_XAML = None
_LINK_XAML = None


def _version():
    """The package version for the window banners, read late."""
    try:
        from . import __version__
        return __version__
    except (ImportError, AttributeError):
        return "?"


def use_xaml(main_path, link_path):
    """Tell the windows where their .xaml files are (they live by the button)."""
    global _XAML, _LINK_XAML
    _XAML, _LINK_XAML = main_path, link_path


_XAML_NAME_KEY = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"


_CONTROL_NAMES = None


def _control_names():
    """Every x:Name in ui.xaml, read once.

    The saved-settings pass needs the list of controls, and the XAML file is the
    only place that HAS the list -- WPF gives no enumeration of named elements.
    Reading the same file the window was built from means a control added to the
    dialog tomorrow is saved and restored without touching this code.
    """
    global _CONTROL_NAMES
    if _CONTROL_NAMES is None:
        try:
            tree = ElementTree.parse(_XAML)
            _CONTROL_NAMES = [element.get(_XAML_NAME_KEY) for element in tree.iter()
                              if element.get(_XAML_NAME_KEY)]
        except Exception:
            _CONTROL_NAMES = []      # settings are a convenience, never a blocker
    return _CONTROL_NAMES


class LinkOptionsDialog(object):
    """Small modal that mirrors Revit's Link CAD dialog: pick file + unit + placement."""

    def __init__(self, active_view_name="-"):
        self.result = None
        self.window = _load_window(_LINK_XAML)
        find = self.window.FindName
        self.tb_path = find("tb_path")
        self.cb_unit = find("cb_unit")
        self.cb_placement = find("cb_placement")
        self.chk_view_only = find("chk_view_only")
        find("tb_active_view").Text = active_view_name
        find("link_version_text").Text = "v{0}".format(_version())
        for label, _value in dxf_linker.UNIT_CHOICES:
            self.cb_unit.Items.Add(label)
        for label, _value in dxf_linker.PLACEMENT_CHOICES:
            self.cb_placement.Items.Add(label)
        if self.cb_unit.Items.Count:
            self.cb_unit.SelectedIndex = 0
        if self.cb_placement.Items.Count:
            self.cb_placement.SelectedIndex = 0
            # Default to Origin-to-Origin (most predictable alignment).
            _select_containing(self.cb_placement, ["origin to origin"])
        find("btn_browse").Click += self._on_browse
        find("btn_link").Click += self._on_link
        find("btn_cancel").Click += self._on_cancel

    def _on_browse(self, sender, args):
        path = _open_dxf()
        if path:
            self.tb_path.Text = path

    def _on_link(self, sender, args):
        path = (self.tb_path.Text or "").strip()
        if not path or not os.path.exists(path):
            _alert("DXF required", "Pick a DXF file that exists before linking.")
            return
        if not self.cb_unit.SelectedItem or not self.cb_placement.SelectedItem:
            _alert("Options required", "Choose a drawing unit and positioning.")
            return
        self.result = {"path": path,
                       "unit": self.cb_unit.SelectedItem,
                       "placement": self.cb_placement.SelectedItem,
                       "this_view_only": bool(self.chk_view_only.IsChecked)}
        self.window.Close()

    def _on_cancel(self, sender, args):
        self.result = None
        self.window.Close()

    def show(self):
        self.window.ShowDialog()


class CadToBimWindow(object):
    """Capture-only window: edit the layer mapping and pick what to build.

    Holds no Revit API references and performs no model writes -- it only gathers
    the user's choices into self.result and closes. All model work happens after
    show() returns, on the Revit API thread.
    """

    def __init__(self, source_name, layer_rows, categories, default_mapping,
                 column_symbols, level_options, beam_symbols, floor_type_options=None,
                 text_layer_rows=None, text_categories=None, default_text_mapping=None,
                 stair_type_options=None, level_elevations=None,
                 stair_regions=None, preset=None, storey_detection=None,
                 saved_naming=None, saved_standards=None,
                 footing_type_options=None, material_options=None,
                 saved_settings=None):
        self.result = None
        self._combos = []
        self._text_combos = []
        saved_naming = saved_naming or naming.DEFAULTS
        saved_standards = saved_standards or {}
        self._saved_standards = saved_standards
        self.window = _load_window(_XAML)
        find = self.window.FindName

        find("version_text").Text = "v{0}".format(_version())
        find("source_text").Text = source_name
        self._build_rows(find("layer_rows"), layer_rows, categories,
                         default_mapping, self._combos)
        self._build_rows(find("text_rows"), text_layer_rows or [],
                         text_categories or [], default_text_mapping or {},
                         self._text_combos)

        self.cb_family = find("cb_family")
        self.cb_circular_family = find("cb_circular_family")
        self.cb_base_level = find("cb_base_level")
        self.cb_top_level = find("cb_top_level")
        self.cb_beam_family = find("cb_beam_family")
        self._family_ids = self._fill_combo(self.cb_family, column_symbols)
        _select_containing(self.cb_family, ["rect"])
        self._fill_combo(self.cb_circular_family, column_symbols)
        _select_containing(self.cb_circular_family, ["round", "circ"])
        # Levels are sorted lowest-first, so combo index ascends with elevation.
        # Base defaults to the lowest, top to the next level above it. The same
        # list feeds the per-storey Level combos on the Multi-storey tab.
        self._level_options = list(level_options or [])
        self._level_ids = self._fill_combo(self.cb_base_level, level_options)
        self._fill_combo(self.cb_top_level, level_options)
        if self.cb_top_level.Items.Count > 1:
            self.cb_top_level.SelectedIndex = 1
        self._beam_ids = self._fill_combo(self.cb_beam_family, beam_symbols)
        _select_containing(self.cb_beam_family, ["rect"])
        self.cb_floor_type = find("cb_floor_type")
        self._floor_ids = self._fill_combo(self.cb_floor_type, floor_type_options or [])
        self.cb_stair_type = find("cb_stair_type")
        self._stair_ids = self._fill_combo(self.cb_stair_type, stair_type_options or [])
        _select_containing(self.cb_stair_type, ["mono"])
        self._level_elevations = level_elevations or {}

        self.chk_grids = find("chk_grids")
        self.chk_columns = find("chk_columns")
        self.chk_beams = find("chk_beams")
        self.chk_slabs = find("chk_slabs")
        self.chk_stairs = find("chk_stairs")
        self.chk_export = find("chk_export")
        self.tb_stair_count = find("tb_stair_count")
        self.tb_stair_waist = find("tb_stair_waist")
        self.cb_stair_source = find("cb_stair_source")
        for label in ("Auto (linework, else shape)", "Drawn stair linework",
                      "Shape at the plan text", "Pick detail lines in Revit"):
            self.cb_stair_source.Items.Add(label)
        self.cb_stair_source.SelectedIndex = 0
        self.shape_buttons = [
            (find("rb_shape_u"), stair_layout.SHAPE_U),
            (find("rb_shape_straight"), stair_layout.SHAPE_STRAIGHT),
            (find("rb_shape_l"), stair_layout.SHAPE_L),
            (find("rb_shape_c"), stair_layout.SHAPE_C),
            (find("rb_shape_circular"), stair_layout.SHAPE_CIRCULAR),
        ]
        self.cb_name_param = find("cb_name_param")
        for label in ("Mark", "Comments", "Type Mark", "Type Comments"):
            self.cb_name_param.Items.Add(label)
        self.cb_name_param.Text = "Comments"
        self.chk_footings = find("chk_footings")
        self.cb_footing_family = find("cb_footing_family")
        self.tb_footing_projection = find("tb_footing_projection")
        self.tb_footing_thickness = find("tb_footing_thickness")
        self.tb_max_step = find("tb_max_step")
        self.tb_fnd_min_area = find("tb_fnd_min_area")
        self._footing_ids = {}
        for label, symbol_id in (footing_type_options or []):
            self.cb_footing_family.Items.Add(label)
            self._footing_ids[label] = symbol_id
        if self._footing_ids:
            self.cb_footing_family.SelectedIndex = 0
        else:
            self.chk_footings.IsChecked = False
            self.chk_footings.IsEnabled = False
            self.chk_footings.Content = ("Create footings (the model has no "
                                         "floor/foundation type)")
        # Materials: one picker per element kind, "(unchanged)" leaving the
        # family's own material alone
        self.material_combos = {}
        self._material_ids = {"": None}
        for kind in materials.KINDS:
            combo = find("cb_mat_{0}".format(kind))
            combo.Items.Add("(unchanged)")
            for label, material_id in (material_options or []):
                combo.Items.Add(label)
                self._material_ids[label] = material_id
            combo.SelectedIndex = 0
            self.material_combos[kind] = combo
        # concrete grade: one figure per element kind, written to a parameter
        # of its own or appended to the element's name
        self.grade_boxes = {}
        for kind in materials.KINDS:
            self.grade_boxes[kind] = find("tb_grade_{0}".format(kind))
        self.cb_grade_param = find("cb_grade_param")
        for label in materials.GRADE_PARAM_CHOICES:
            self.cb_grade_param.Items.Add(label)
        self.cb_grade_param.Text = "Comments"
        self.chk_grade_in_mark = find("chk_grade_in_mark")
        self.chk_view_filters = find("chk_view_filters")
        self.tb_filter_transparency = find("tb_filter_transparency")
        self.chk_filter_lines = find("chk_filter_lines")
        self.chk_multistorey = find("chk_multistorey")
        self.cb_boundary_layer = find("cb_boundary_layer")
        self.cb_origin_layer = find("cb_origin_layer")
        self.tb_storey_height = find("tb_storey_height")
        self.multistorey_preview = find("multistorey_preview")
        self.storey_rows = find("storey_rows")
        self._storey_plans = []
        self._storey_rows = []
        self.storey_selection_text = find("storey_selection_text")
        self.storey_rows.SelectionChanged += self.on_storey_selection_changed
        self.btn_storey_up = find("btn_storey_up")
        self.btn_storey_down = find("btn_storey_down")
        self.btn_storey_add = find("btn_storey_add")
        self.btn_storey_remove = find("btn_storey_remove")
        self.btn_storey_up.Click += self.on_storey_move_up
        self.btn_storey_down.Click += self.on_storey_move_down
        self.btn_storey_add.Click += self.on_storey_add
        self.btn_storey_remove.Click += self.on_storey_remove
        layer_names = [name for name, _count in layer_rows]
        for combo in (self.cb_boundary_layer, self.cb_origin_layer):
            combo.Items.Add("(none)")
            for name in layer_names:
                combo.Items.Add(name)
            combo.SelectedIndex = 0
        # Auto-detection reads the drawing itself, so the tab arrives already
        # answered: the layers picked, the box ticked and one row per plan. A
        # name guess is only the fallback when detection found nothing.
        self.detection = storey_detection
        self._storey_boxes = []
        self._apply_detection()
        self.btn_draw_stairs = find("btn_draw_stairs")
        self.stair_outline_text = find("stair_outline_text")
        self.btn_draw_stairs.Click += self.on_draw_stairs
        self.stair_regions = list(stair_regions or [])
        self._show_outline_count()
        self.stair_floor_text = find("stair_floor_text")
        self._stair_count_manual = False
        self.tb_stair_riser = find("tb_stair_riser")
        self.tb_stair_tread = find("tb_stair_tread")
        self.tb_stair_width = find("tb_stair_width")
        self.tb_stair_landing = find("tb_stair_landing")

        self.tb_beam_min = find("tb_beam_min")
        self.tb_beam_max = find("tb_beam_max")
        self.tb_colb_min = find("tb_colb_min")
        self.tb_colb_max = find("tb_colb_max")
        self.tb_colh_min = find("tb_colh_min")
        self.tb_colh_max = find("tb_colh_max")
        self.sl_beam_min = find("sl_beam_min")
        self.sl_beam_max = find("sl_beam_max")
        self.sl_colb_min = find("sl_colb_min")
        self.sl_colb_max = find("sl_colb_max")
        self.sl_colh_min = find("sl_colh_min")
        self.sl_colh_max = find("sl_colh_max")
        self.tb_std_columns = find("tb_std_columns")
        self.tb_std_beams = find("tb_std_beams")

        # Naming tab: one template per auto-created type, remembered between
        # Revit sessions (the dialog is rebuilt from scratch every run).
        self.name_boxes = {}
        self.name_labels = {}
        for key, control in (("column_rect", "column"),
                             ("column_round", "column_round"),
                             ("beam_sized", "beam"),
                             ("beam_width", "beam_width"),
                             ("floor", "floor"),
                             ("stair", "stair"),
                             ("stair_waist", "stair_waist"),
                             ("level", "level"),
                             ("grid", "grid"),
                             ("footing", "footing")):
            box = find("tb_name_{0}".format(control))
            box.Text = saved_naming.get(key, naming.DEFAULTS[key])
            box.TextChanged += self.on_naming_changed
            self.name_boxes[key] = box
            self.name_labels[key] = find("lbl_name_{0}".format(control))
        self.naming_saved_text = find("naming_saved_text")
        self.chk_level_follow = find("chk_level_follow")
        self.btn_name_defaults = find("btn_name_defaults")
        self.btn_name_defaults.Click += self.on_naming_defaults
        self._show_naming_preview()
        self.tb_snap = find("tb_snap")
        self.tb_markrad = find("tb_markrad")
        self.tb_compare = find("tb_compare")
        self.tb_grid_snap = find("tb_grid_snap")
        self.tb_region = find("tb_region")
        self.tb_circ_min = find("tb_circ_min")
        self.tb_circ_max = find("tb_circ_max")
        self.tb_pair_min = find("tb_pair_min")
        self.tb_pair_max = find("tb_pair_max")
        self.tb_pair_overlap = find("tb_pair_overlap")
        self.tb_parallel_angle = find("tb_parallel_angle")
        self.tb_junction_tol = find("tb_junction_tol")
        self.tb_concentric_tol = find("tb_concentric_tol")
        self.tb_slab_snap = find("tb_slab_snap")
        self.tb_slab_heal = find("tb_slab_heal")
        self.tb_slab_chain = find("tb_slab_chain")
        self.tb_slab_width = find("tb_slab_width")
        self.tb_slab_step = find("tb_slab_step")
        self.tb_slab_note_area = find("tb_slab_note_area")
        self.tb_face_reach = find("tb_face_reach")
        self.tb_face_size = find("tb_face_size")
        self.tb_stair_cluster = find("tb_stair_cluster")
        self.tb_tread_min = find("tb_tread_min")
        self.tb_tread_max = find("tb_tread_max")
        self.tb_arrival_merge = find("tb_arrival_merge")
        self._init_sizing()
        self._init_tolerances()

        if not column_symbols:
            self.chk_columns.IsChecked = False
            self.chk_columns.IsEnabled = False
            self.chk_columns.Content = "Create columns (load a structural column family first)"
        if not beam_symbols:
            self.chk_beams.IsChecked = False
            self.chk_beams.IsEnabled = False
            self.chk_beams.Content = "Create beams (load a structural framing family first)"
        if not floor_type_options:
            self.chk_slabs.IsChecked = False
            self.chk_slabs.IsEnabled = False
            self.chk_slabs.Content = "Create slabs (the model has no floor type)"
        if not stair_type_options:
            self.chk_stairs.IsChecked = False
            self.chk_stairs.IsEnabled = False
            self.chk_stairs.Content = "Create staircases (the model has no stair type)"

        # Build > Staircase sub-tab live sync: floor height follows the level
        # picks (Build > General); an
        # ABSOLUTE riser count drives the riser height (storey / count)
        self.cb_base_level.SelectionChanged += self._on_stair_sync
        self.cb_top_level.SelectionChanged += self._on_stair_sync
        self.tb_stair_count.LostFocus += self._on_stair_count_edit
        self.tb_stair_riser.LostFocus += self._on_stair_sync
        self._stair_sync()

        self.status_text = find("status_text")
        self.btn_settings_save = find("btn_settings_save")
        self.btn_settings_load = find("btn_settings_load")
        self.btn_settings_save.Click += self.on_settings_save
        self.btn_settings_load.Click += self.on_settings_load
        # last run's dialog, restored before the preset so the round trip
        # through "draw stair outlines" still wins
        if saved_settings:
            landed = self._restore_controls(saved_settings)
            if landed:
                self.status_text.Text = ("{0} setting(s) restored from the last "
                                         "run".format(landed))

        if preset:
            self._apply_preset(preset)

        find("btn_run").Click += self.on_run
        find("btn_cancel").Click += self.on_cancel

    def _fill_combo(self, combo, label_id_pairs):
        """Populate a combo with labels; return {label: ElementId}. Selects the first."""
        mapping = {}
        for label, element_id in label_id_pairs:
            combo.Items.Add(label)
            mapping[label] = element_id
        if combo.Items.Count:
            combo.SelectedIndex = 0
        return mapping

    def _build_rows(self, panel, layer_rows, categories, default_mapping, combo_store):
        """One row per layer: name, count, category combo. Appends (layer, combo)
        to combo_store so the caller can read the chosen mapping back."""
        for layer, count in layer_rows:
            row = WpfGrid()
            row.Margin = Thickness(0, 1, 0, 1)
            for width in (None, 70, 180):   # None -> star column
                column = ColumnDefinition()
                column.Width = (GridLength(1, GridUnitType.Star) if width is None
                                else GridLength(width))
                row.ColumnDefinitions.Add(column)

            name_block = TextBlock()
            name_block.Text = layer
            name_block.VerticalAlignment = VerticalAlignment.Center
            WpfGrid.SetColumn(name_block, 0)

            count_block = TextBlock()
            count_block.Text = str(count)
            count_block.VerticalAlignment = VerticalAlignment.Center
            WpfGrid.SetColumn(count_block, 1)

            combo = ComboBox()
            combo.Height = 22.0
            for category in categories:
                combo.Items.Add(category)
            combo.SelectedItem = default_mapping.get(layer)
            if combo.SelectedItem is None and combo.Items.Count:
                combo.SelectedIndex = combo.Items.Count - 1   # last = unmapped/ignore
            WpfGrid.SetColumn(combo, 2)

            row.Children.Add(name_block)
            row.Children.Add(count_block)
            row.Children.Add(combo)
            panel.Children.Add(row)
            combo_store.append((layer, combo))

    def _init_sizing(self):
        """Seed the limit fields from defaults and two-way link each slider+input."""
        defaults = report.DEFAULT_LIMITS
        pairs = [
            (self.tb_beam_min, self.sl_beam_min, defaults["beam_width_min_mm"]),
            (self.tb_beam_max, self.sl_beam_max, defaults["beam_width_max_mm"]),
            (self.tb_colb_min, self.sl_colb_min, defaults["col_b_min_mm"]),
            (self.tb_colb_max, self.sl_colb_max, defaults["col_b_max_mm"]),
            (self.tb_colh_min, self.sl_colh_min, defaults["col_h_min_mm"]),
            (self.tb_colh_max, self.sl_colh_max, defaults["col_h_max_mm"]),
        ]
        for textbox, slider, value in pairs:
            textbox.Text = str(int(value))
            try:
                slider.Value = float(value)
                self._link(textbox, slider)
            except Exception:
                pass   # a slider hiccup must never break the dialog

    def _link(self, textbox, slider):
        def on_slider(sender, args):
            textbox.Text = str(int(round(slider.Value)))

        def on_text(sender, args):
            try:
                slider.Value = float(textbox.Text)
            except (ValueError, TypeError):
                pass
        slider.ValueChanged += on_slider
        textbox.LostFocus += on_text

    def _init_tolerances(self):
        """Seed every tunable box from config defaults (mm unless it says not)."""
        d = config.DEFAULTS
        self.tb_snap.Text = str(int(d["snap_tol_mm"]))
        self.tb_markrad.Text = str(int(d["mark_radius_mm"]))
        self.tb_compare.Text = str(int(d["compare_tol_mm"]))
        self.tb_grid_snap.Text = str(int(d["grid_snap_mm"]))
        self.tb_region.Text = str(int(d["col_region_max_side_mm"]))
        self.tb_circ_min.Text = str(int(d["circle_min_dia_mm"]))
        self.tb_circ_max.Text = str(int(d["circle_max_dia_mm"]))
        self.tb_pair_min.Text = str(int(d["pair_min_width_mm"]))
        self.tb_pair_max.Text = str(int(d["pair_max_width_mm"]))
        self.tb_pair_overlap.Text = str(int(d["pair_min_overlap_mm"]))
        self.tb_parallel_angle.Text = "{0:g}".format(d["parallel_angle_deg"])
        self.tb_junction_tol.Text = str(int(d["junction_tol_mm"]))
        self.tb_concentric_tol.Text = str(int(d["concentric_tol_mm"]))
        self.tb_slab_snap.Text = str(int(d["slab_snap_mm"]))
        self.tb_slab_heal.Text = str(int(d["slab_heal_mm"]))
        self.tb_slab_chain.Text = str(int(d["slab_chain_mm"]))
        self.tb_slab_width.Text = str(int(d["slab_min_width_mm"]))
        self.tb_slab_step.Text = str(int(d["slab_min_step_mm"]))
        self.tb_stair_cluster.Text = str(int(d["stair_cluster_mm"]))
        self.tb_tread_min.Text = str(int(d["stair_tread_min_mm"]))
        self.tb_tread_max.Text = str(int(d["stair_tread_max_mm"]))
        self.tb_arrival_merge.Text = str(int(d["stair_arrival_merge_mm"]))
        self.tb_stair_riser.Text = str(int(d["stair_riser_mm"]))
        self.tb_stair_waist.Text = str(int(d["stair_waist_mm"]))
        self.tb_storey_height.Text = str(int(d["storey_height_mm"]))
        self.tb_stair_count.Text = "0"
        self.tb_stair_tread.Text = str(int(d["stair_tread_mm"]))
        self.tb_stair_width.Text = str(int(d["stair_run_width_mm"]))
        self.tb_stair_landing.Text = str(int(d["stair_landing_mm"]))
        # standard sizes are an office convention, not a per-drawing number, so
        # they come back from the last session like the naming templates do
        saved = getattr(self, "_saved_standards", None) or {}
        self.tb_std_columns.Text = saved.get("column",
                                             d["standard_columns"])
        self.tb_std_beams.Text = saved.get("beam_widths",
                                           d["standard_beam_widths"])
        self.tb_slab_note_area.Text = str(d["slab_note_min_area_m2"])
        self.tb_face_reach.Text = str(int(d["face_label_reach_mm"]))
        self.tb_face_size.Text = str(int(d["face_size_tol_mm"]))
        self.tb_footing_projection.Text = str(int(d["footing_projection_mm"]))
        self.tb_footing_thickness.Text = str(int(d["footing_thickness_mm"]))
        self.tb_max_step.Text = str(int(d["max_step_mm"]))
        self.tb_fnd_min_area.Text = str(d["foundation_min_area_m2"])
        self.tb_filter_transparency.Text = str(int(d["filter_transparency"]))

    def _read_int(self, textbox, fallback):
        try:
            return int(round(float(textbox.Text)))
        except (ValueError, TypeError):
            return fallback

    def _read_float(self, textbox, fallback):
        try:
            return float(textbox.Text)
        except (ValueError, TypeError):
            return fallback

    def _read_tolerances(self):
        d = config.DEFAULTS
        return {
            "snap_tol_mm": self._read_float(self.tb_snap, d["snap_tol_mm"]),
            "mark_radius_mm": self._read_float(self.tb_markrad, d["mark_radius_mm"]),
            "compare_tol_mm": self._read_float(self.tb_compare, d["compare_tol_mm"]),
            "grid_snap_mm": self._read_float(self.tb_grid_snap, d["grid_snap_mm"]),
            "col_region_max_side_mm": self._read_float(self.tb_region, d["col_region_max_side_mm"]),
            "circle_min_dia_mm": self._read_float(self.tb_circ_min, d["circle_min_dia_mm"]),
            "circle_max_dia_mm": self._read_float(self.tb_circ_max, d["circle_max_dia_mm"]),
            "pair_min_width_mm": self._read_float(self.tb_pair_min, d["pair_min_width_mm"]),
            "pair_max_width_mm": self._read_float(self.tb_pair_max, d["pair_max_width_mm"]),
            "pair_min_overlap_mm": self._read_float(self.tb_pair_overlap,
                                                    d["pair_min_overlap_mm"]),
            "parallel_angle_deg": self._read_float(self.tb_parallel_angle,
                                                   d["parallel_angle_deg"]),
            "junction_tol_mm": self._read_float(self.tb_junction_tol,
                                                d["junction_tol_mm"]),
            "concentric_tol_mm": self._read_float(self.tb_concentric_tol,
                                                  d["concentric_tol_mm"]),
            "max_step_mm": self._read_float(self.tb_max_step, d["max_step_mm"]),
            "foundation_min_area_m2": self._read_float(
                self.tb_fnd_min_area, d["foundation_min_area_m2"]),
            "slab_snap_mm": self._read_float(self.tb_slab_snap, d["slab_snap_mm"]),
            "slab_heal_mm": self._read_float(self.tb_slab_heal, d["slab_heal_mm"]),
            "slab_chain_mm": self._read_float(self.tb_slab_chain, d["slab_chain_mm"]),
            "slab_min_width_mm": self._read_float(self.tb_slab_width,
                                                  d["slab_min_width_mm"]),
            "slab_min_step_mm": self._read_float(self.tb_slab_step,
                                                 d["slab_min_step_mm"]),
            "slab_note_min_area_m2": self._read_float(
                self.tb_slab_note_area, d["slab_note_min_area_m2"]),
            "face_label_reach_mm": self._read_float(self.tb_face_reach,
                                                    d["face_label_reach_mm"]),
            "face_size_tol_mm": self._read_float(self.tb_face_size,
                                                 d["face_size_tol_mm"]),
            "stair_cluster_mm": self._read_float(self.tb_stair_cluster,
                                                 d["stair_cluster_mm"]),
            "stair_tread_min_mm": self._read_float(self.tb_tread_min,
                                                   d["stair_tread_min_mm"]),
            "stair_tread_max_mm": self._read_float(self.tb_tread_max,
                                                   d["stair_tread_max_mm"]),
            "stair_arrival_merge_mm": self._read_float(self.tb_arrival_merge,
                                                       d["stair_arrival_merge_mm"]),
        }

    def _storey_mm(self):
        """Top minus base level elevation in mm, or None before both are picked."""
        base = self._level_elevations.get(self.cb_base_level.SelectedItem)
        top = self._level_elevations.get(self.cb_top_level.SelectedItem)
        if base is None or top is None:
            return None
        return (top - base) * 304.8

    def _on_stair_sync(self, sender, args):
        self._stair_sync()

    def _on_stair_count_edit(self, sender, args):
        # the user typed a count: it becomes ABSOLUTE (0 returns to automatic)
        self._stair_count_manual = self._read_int(self.tb_stair_count, 0) > 0
        self._stair_sync()

    def _stair_sync(self):
        """Riser count <-> riser height <-> storey, live.

        AUTOMATIC (default): count = ceil(storey / max riser), e.g. 20 for
        3000/150, refreshed when levels or the riser height change. MANUAL
        (user typed a count): the count is absolute and the riser height
        becomes storey / count instead."""
        import math as _math
        storey = self._storey_mm()
        self.stair_floor_text.Text = ("{0} mm".format(int(round(storey)))
                                      if storey and storey > 0 else "-")
        if not storey or storey <= 0:
            return
        if self._stair_count_manual:
            count = self._read_int(self.tb_stair_count, 0)
            if count > 0:
                self.tb_stair_riser.Text = "{0:.1f}".format(storey / count)
            else:
                self._stair_count_manual = False
        if not self._stair_count_manual:
            riser = self._read_float(self.tb_stair_riser,
                                     config.DEFAULTS["stair_riser_mm"])
            if riser > 0:
                self.tb_stair_count.Text = str(
                    int(_math.ceil(storey / riser - 1e-9)))

    def _stair_shape(self):
        """The generic stair shape picked on Build > Staircase (U by default)."""
        for button, shape in self.shape_buttons:
            if button.IsChecked:
                return shape
        return stair_layout.SHAPE_U

    def _read_limits(self):
        defaults = report.DEFAULT_LIMITS
        return {
            "beam_width_min_mm": self._read_int(self.tb_beam_min, defaults["beam_width_min_mm"]),
            "beam_width_max_mm": self._read_int(self.tb_beam_max, defaults["beam_width_max_mm"]),
            "col_b_min_mm": self._read_int(self.tb_colb_min, defaults["col_b_min_mm"]),
            "col_b_max_mm": self._read_int(self.tb_colb_max, defaults["col_b_max_mm"]),
            "col_h_min_mm": self._read_int(self.tb_colh_min, defaults["col_h_min_mm"]),
            "col_h_max_mm": self._read_int(self.tb_colh_max, defaults["col_h_max_mm"]),
        }

    def _validate_levels(self):
        """If columns/beams are requested, ensure top level is above base.

        Combo index ascends with elevation (levels are sorted lowest-first), so the
        check is index-based. Returns an error string, or None when valid.
        """
        if not (self.chk_columns.IsChecked or self.chk_beams.IsChecked):
            return None
        base_idx = self.cb_base_level.SelectedIndex
        top_idx = self.cb_top_level.SelectedIndex
        if base_idx < 0 or top_idx < 0:
            return "Select a base level and a top level."
        if base_idx == top_idx:
            return ("Base level and top level are the same. Choose a top level "
                    "above the base to give columns/beams their height.")
        if top_idx < base_idx:
            return ("Base level is set above the top level. Adjust so the top "
                    "level is above the base to proceed.")
        return None

    def on_run(self, sender, args):
        level_error = self._validate_levels()
        if level_error:
            _alert("Check levels", level_error)
            return   # keep the window open so the user can fix it
        mapping = {}
        for layer, combo in self._combos:
            mapping[layer] = combo.SelectedItem or layers.CATEGORY_UNMAPPED
        text_mapping = {}
        for layer, combo in self._text_combos:
            text_mapping[layer] = combo.SelectedItem or layers.CATEGORY_TEXT_IGNORE
        self.result = self._collect(mapping=mapping, text_mapping=text_mapping)
        self._remember_conventions()
        self.window.Close()

    def _collect(self, mapping=None, text_mapping=None, action=None):
        """Every dialog value as one dict -- shared by Run and the draw button
        so re-opening the window restores exactly what was on screen."""
        if mapping is None:
            mapping = {}
            for layer, combo in self._combos:
                mapping[layer] = combo.SelectedItem or layers.CATEGORY_UNMAPPED
        if text_mapping is None:
            text_mapping = {}
            for layer, combo in self._text_combos:
                text_mapping[layer] = (combo.SelectedItem
                                       or layers.CATEGORY_TEXT_IGNORE)
        return {
            "action": action,
            "stair_regions": list(self.stair_regions),
            "mapping": mapping,
            "text_mapping": text_mapping,
            "create_grids": bool(self.chk_grids.IsChecked),
            "create_columns": bool(self.chk_columns.IsChecked),
            "create_beams": bool(self.chk_beams.IsChecked),
            "create_slabs": bool(self.chk_slabs.IsChecked),
            "create_stairs": bool(self.chk_stairs.IsChecked),
            "stair_type_id": self._stair_ids.get(self.cb_stair_type.SelectedItem),
            "stair_source": ("linework" if self.cb_stair_source.SelectedIndex == 1
                             else "text" if self.cb_stair_source.SelectedIndex == 2
                             else "region" if self.cb_stair_source.SelectedIndex == 3
                             else "auto"),
            "multistorey": bool(self.chk_multistorey.IsChecked),
            "boundary_layer": (None if self.cb_boundary_layer.SelectedIndex <= 0
                               else self.cb_boundary_layer.SelectedItem),
            "origin_layer": (None if self.cb_origin_layer.SelectedIndex <= 0
                             else self.cb_origin_layer.SelectedItem),
            "storey_height_mm": self._read_float(
                self.tb_storey_height, config.DEFAULTS["storey_height_mm"]),
            "storey_settings": self._read_storey_settings(),
            "stair_params": {
                "riser_count": self._read_int(self.tb_stair_count, 0),
                "waist_mm": self._read_float(self.tb_stair_waist,
                                             config.DEFAULTS["stair_waist_mm"]),
                "shape": self._stair_shape(),
                "riser_mm": self._read_float(self.tb_stair_riser,
                                             config.DEFAULTS["stair_riser_mm"]),
                "tread_mm": self._read_float(self.tb_stair_tread,
                                             config.DEFAULTS["stair_tread_mm"]),
                "run_width_mm": self._read_float(self.tb_stair_width,
                                                 config.DEFAULTS["stair_run_width_mm"]),
                "landing_mm": self._read_float(self.tb_stair_landing,
                                               config.DEFAULTS["stair_landing_mm"]),
            },
            "floor_type_id": self._floor_ids.get(self.cb_floor_type.SelectedItem),
            "column_family_id": self._family_ids.get(self.cb_family.SelectedItem),
            "circular_family_id": self._family_ids.get(self.cb_circular_family.SelectedItem),
            "beam_family_id": self._beam_ids.get(self.cb_beam_family.SelectedItem),
            "base_level_id": self._level_ids.get(self.cb_base_level.SelectedItem),
            "top_level_id": self._level_ids.get(self.cb_top_level.SelectedItem),
            "name_parameter": (self.cb_name_param.Text or "Mark").strip(),
            "export": bool(self.chk_export.IsChecked),
            "limits": self._read_limits(),
            "tolerances": self._read_tolerances(),
            "standards": {
                "column": report.parse_standard_sizes(self.tb_std_columns.Text),
                "beam_widths": report.parse_standard_widths(self.tb_std_beams.Text),
            },
            "create_footings": bool(self.chk_footings.IsChecked),
            "footing_symbol_id": self._footing_ids.get(
                self.cb_footing_family.SelectedItem),
            "footing_projection_mm": self._read_float(
                self.tb_footing_projection,
                config.DEFAULTS["footing_projection_mm"]),
            "footing_thickness_mm": self._read_float(
                self.tb_footing_thickness,
                config.DEFAULTS["footing_thickness_mm"]),
            "materials": dict(
                (kind, self._material_ids.get(combo.SelectedItem))
                for kind, combo in self.material_combos.items()),
            "grades": dict((kind, (box.Text or "").strip())
                           for kind, box in self.grade_boxes.items()),
            "grade_parameter": (self.cb_grade_param.Text or "Comments").strip(),
            "grade_in_mark": bool(self.chk_grade_in_mark.IsChecked),
            "view_filters": bool(self.chk_view_filters.IsChecked),
            "filter_transparency": self._read_int(
                self.tb_filter_transparency,
                config.DEFAULTS["filter_transparency"]),
            "filter_colour_lines": bool(self.chk_filter_lines.IsChecked),
            "naming": self._read_naming(),
            "level_follow_existing": bool(self.chk_level_follow.IsChecked),
            # the window itself, as a settings snapshot: the draw-stairs round
            # trip restores from this, so every control survives the rebuild
            "preset_payload": self._capture_settings(),
        }

    def _apply_preset(self, preset):
        """Put a previous run of this dialog back on screen.

        The window is rebuilt after the user draws stair outlines in the view,
        so everything they had already chosen must come back with it. The
        preset carries the same snapshot a settings file does (the
        "preset_payload" _collect takes as the window closes), and it lands
        through the same restore path -- one code path, every control, instead
        of a hand-kept list that forgets the boxes added since it was written.
        Only what the snapshot cannot carry is re-applied here: the storey
        table (its rows are rebuilt from the drawing, then reshaped from the
        preset) and the drawn-outline count. What detection answers from the
        drawing itself (settings.DETECTED_NAMES) stays with the drawing.
        """
        self._restore_controls(preset.get("preset_payload") or {})
        saved_rows = preset.get("storey_settings") or []
        if saved_rows and self._storey_plans:
            self._storey_rows = [
                {"plan": min(saved.get("plan") or 0,
                             len(self._storey_plans) - 1),
                 "height_mm": saved.get("height_mm"),
                 "repeat": int(saved.get("repeat") or 1),
                 "include": saved.get("include", True),
                 "level_id": saved.get("level_id")}
                for saved in saved_rows]
            self._refresh_storey_rows()
        self._show_outline_count()

    def _apply_detection(self):
        """Fill the Multi-storey tab from what auto-detection found in the DXF.

        Detection decides the checkbox, the two layer combos and the storey
        rows; the user can override every one of them afterwards. With no
        detection (an older caller, or nothing found) the tab falls back to the
        name guess it always used.
        """
        found = self.detection
        if found is None or not getattr(found, "boundary_layer", None):
            _select_containing(self.cb_boundary_layer,
                               ["boundar", "bound", "extent"])
            _select_containing(self.cb_origin_layer,
                               ["origin", "basept", "datum"])
            if found is not None:
                self.multistorey_preview.Text = found.reason
            self._show_storey_selection()
            return

        for combo, layer in ((self.cb_boundary_layer, found.boundary_layer),
                             (self.cb_origin_layer, found.origin_layer)):
            if layer and combo.Items.Contains(layer):
                combo.SelectedItem = layer
        self.chk_multistorey.IsChecked = bool(found.multistorey)
        lines = [found.reason] + list(found.notes or [])
        self.multistorey_preview.Text = "\n".join(lines)
        self._build_storey_rows(found.plans)

    def _build_storey_rows(self, plans):
        """One editable row per storey: which plan, its height, its repeat.

        The rows are created here rather than declared in the XAML because how
        many there are is only known once the drawing has been read. Each row's
        PLAN is a dropdown over every detected floor drawing, so the same plan
        can be used on several storeys (a typical floor drawn once and built
        five times), and the row ORDER is the build order, bottom-up.
        """
        self._storey_plans = list(plans or [])
        self._storey_rows = []
        level_names = [label for label, _level_id in self._level_options]
        for index in range(len(self._storey_plans)):
            # a plan titled like a model level starts on that level ("Ground
            # Floor Level" <-> "Ground Floor"); every other row starts on
            # "(auto)" and climbs the ladder exactly as before
            proposed = floor_plans.propose_level(
                self._storey_plans[index].get("label"), level_names)
            self._storey_rows.append({"plan": index, "height_mm": None,
                                      "repeat": self._storey_plans[index].get(
                                          "repeat") or 1,
                                      "include": True,
                                      "level_id": (self._level_ids.get(proposed)
                                                   if proposed else None)})
        self._refresh_storey_rows()

    def _plan_label(self, index):
        plan = self._storey_plans[index]
        label = (plan.get("label") or "").splitlines()
        text = label[0].strip() if label else ""
        return text or "plan {0}".format(index + 1)

    def _refresh_storey_rows(self):
        """Redraw the storey table from self._storey_rows (the model).

        Each storey is a real ListBoxItem, so selection is Revit-native: the
        row highlights, the arrow keys walk the stack, and the Move/Add/Remove
        buttons act on whatever is highlighted. A hand-rolled click handler on
        the row could not work -- the combo box and text boxes inside it swallow
        the mouse before the row ever sees it, which is why nothing looked
        selectable.
        """
        keep = self.storey_rows.SelectedIndex
        self.storey_rows.Items.Clear()
        self._storey_boxes = []
        for position, row in enumerate(self._storey_rows):
            grid = WpfGrid()
            for width in (40.0, 30.0, 0.0, 110.0, 70.0, 52.0):
                column = ColumnDefinition()
                column.Width = (GridLength(1, GridUnitType.Star) if not width
                                else GridLength(width))
                grid.ColumnDefinitions.Add(column)
            include = CheckBox()
            include.IsChecked = bool(row.get("include", True))
            include.VerticalAlignment = VerticalAlignment.Center
            include.ToolTip = "Untick to leave this storey out of the model"
            WpfGrid.SetColumn(include, 0)
            grid.Children.Add(include)

            number = TextBlock()
            number.Text = str(position + 1)
            number.VerticalAlignment = VerticalAlignment.Center
            WpfGrid.SetColumn(number, 1)
            grid.Children.Add(number)

            plan_combo = ComboBox()
            plan_combo.Height = 22
            plan_combo.Margin = Thickness(0, 1, 8, 1)
            for index in range(len(self._storey_plans)):
                plan_combo.Items.Add(self._plan_label(index))
            plan_combo.SelectedIndex = min(row.get("plan") or 0,
                                           max(0, len(self._storey_plans) - 1))
            WpfGrid.SetColumn(plan_combo, 2)
            grid.Children.Add(plan_combo)

            # which MODEL level this storey builds on: "(auto)" keeps the
            # positional ladder, a named level pins the storey's base to it
            level_combo = ComboBox()
            level_combo.Height = 22
            level_combo.Margin = Thickness(0, 1, 8, 1)
            level_combo.Items.Add("(auto)")
            for label, _level_id in self._level_options:
                level_combo.Items.Add(label)
            level_combo.SelectedIndex = self._level_index(row.get("level_id"))
            level_combo.ToolTip = ("The model level this storey's base sits "
                                   "on; (auto) follows the row order upward "
                                   "from the base level")
            WpfGrid.SetColumn(level_combo, 3)
            grid.Children.Add(level_combo)

            height = TextBox()
            height.Height = 22
            height.Margin = Thickness(0, 1, 8, 1)
            height.Text = ("" if row.get("height_mm") is None
                           else "{0:g}".format(row["height_mm"]))
            WpfGrid.SetColumn(height, 4)
            grid.Children.Add(height)

            repeat = TextBox()
            repeat.Height = 22
            repeat.Margin = Thickness(0, 1, 0, 1)
            repeat.Text = str(int(row.get("repeat") or 1))
            WpfGrid.SetColumn(repeat, 5)
            grid.Children.Add(repeat)

            item = ListBoxItem()
            item.Content = grid
            item.Padding = Thickness(2, 1, 2, 1)
            # PREVIEW: the tunnelling event reaches the row before the combo box
            # or text box inside it can handle the click, so clicking anywhere
            # on a row selects it
            item.PreviewMouseLeftButtonDown += self._on_storey_row_clicked
            item.PreviewGotKeyboardFocus += self._on_storey_row_clicked
            self.storey_rows.Items.Add(item)
            self._storey_boxes.append((row, plan_combo, level_combo, height,
                                       repeat, include, item))
        if self._storey_boxes:
            if not (0 <= keep < len(self._storey_boxes)):
                keep = 0
            self.storey_rows.SelectedIndex = keep
        self._show_storey_selection()

    def _show_storey_selection(self):
        """Say which storey the Move/Add/Remove buttons will act on."""
        for button in (self.btn_storey_up, self.btn_storey_down,
                       self.btn_storey_add, self.btn_storey_remove):
            button.IsEnabled = bool(self._storey_rows)
        if not self._storey_rows:
            self.storey_selection_text.Text = "no floor plans detected"
            return
        index = self.storey_rows.SelectedIndex
        if index is None or index < 0:
            self.storey_selection_text.Text = "click a row to select a storey"
            return
        self.btn_storey_up.IsEnabled = index > 0
        self.btn_storey_down.IsEnabled = index < len(self._storey_rows) - 1
        self.btn_storey_remove.IsEnabled = len(self._storey_rows) > 1
        self.storey_selection_text.Text = "storey {0} of {1} selected".format(
            index + 1, len(self._storey_rows))

    def _on_storey_row_clicked(self, sender, args):
        try:
            self.storey_rows.SelectedItem = sender
        except Exception:
            pass
        self._show_storey_selection()

    def on_storey_selection_changed(self, sender, args):
        self._show_storey_selection()

    def _level_index(self, level_id):
        """A row's Level combo index for a level id: 0 is "(auto)"."""
        if level_id is not None:
            for position, (_label, candidate) in enumerate(self._level_options):
                if candidate == level_id:
                    return position + 1
        return 0

    def _capture_storey_rows(self):
        """Read the on-screen table back into the model before reordering it."""
        for (row, plan_combo, level_combo, height, repeat, include,
             _grid) in self._storey_boxes:
            row["plan"] = max(0, plan_combo.SelectedIndex)
            picked = level_combo.SelectedIndex - 1     # 0 is "(auto)"
            row["level_id"] = (self._level_options[picked][1]
                               if 0 <= picked < len(self._level_options)
                               else None)
            row["height_mm"] = self._read_float(height, None)
            row["repeat"] = self._read_int(repeat, row.get("repeat") or 1)
            row["include"] = bool(include.IsChecked)

    def _selected_storey(self):
        index = self.storey_rows.SelectedIndex
        if index is None or index < 0:
            return len(self._storey_rows) - 1 if self._storey_rows else -1
        return index

    def on_storey_move_up(self, sender, args):
        self._move_storey(-1)

    def on_storey_move_down(self, sender, args):
        self._move_storey(1)

    def _move_storey(self, step):
        self._capture_storey_rows()
        position = self._selected_storey()
        target = position + step
        if position < 0 or target < 0 or target >= len(self._storey_rows):
            return
        rows = self._storey_rows
        rows[position], rows[target] = rows[target], rows[position]
        self._refresh_storey_rows()
        if 0 <= target < len(self._storey_boxes):
            self.storey_rows.SelectedIndex = target      # follow the moved row
            self._show_storey_selection()

    def on_storey_add(self, sender, args):
        """Another storey built from an existing plan (a typical floor reused)."""
        if not self._storey_plans:
            return
        self._capture_storey_rows()
        position = max(0, self._selected_storey())
        source = (self._storey_rows[position] if self._storey_rows
                  else {"plan": 0})
        self._storey_rows.insert(position + 1,
                                 {"plan": source.get("plan", 0),
                                  "height_mm": source.get("height_mm"),
                                  "repeat": 1, "include": True})
        self._refresh_storey_rows()
        self.storey_rows.SelectedIndex = position + 1
        self._show_storey_selection()

    def on_storey_remove(self, sender, args):
        self._capture_storey_rows()
        position = self._selected_storey()
        if position < 0 or len(self._storey_rows) <= 1:
            return
        self._storey_rows.pop(position)
        self._refresh_storey_rows()
        self.storey_rows.SelectedIndex = min(position, len(self._storey_rows) - 1)
        self._show_storey_selection()

    def _read_storey_settings(self):
        """The per-storey rows as plain dicts, bottom-up (what the build wants)."""
        self._capture_storey_rows()
        rows_out = []
        for row in self._storey_rows:
            plan = self._storey_plans[min(row.get("plan") or 0,
                                          len(self._storey_plans) - 1)]
            rows_out.append({
                "label": plan.get("label"),
                "plan": row.get("plan") or 0,
                "order": plan.get("order"),
                "include": bool(row.get("include", True)),
                "height_mm": row.get("height_mm"),
                "repeat": int(row.get("repeat") or 1),
                # the MODEL level this storey builds on; None keeps the
                # positional ladder
                "level_id": row.get("level_id")})
        return rows_out

    def _remember_conventions(self):
        """Keep this dialog for the NEXT Revit session.

        The naming templates and standard sizes keep their own files (they are
        office conventions, edited on their own tab and shared between tools);
        everything ELSE on the window goes into the preferences under "dialog",
        so a user who tuned twenty boxes finds them tuned tomorrow morning.
        """
        naming.save(self._read_naming())
        prefs.update({"standards": {"column": self.tb_std_columns.Text or "",
                                    "beam_widths": self.tb_std_beams.Text or ""},
                      "dialog": self._capture_settings()})
        failure = prefs.last_error()
        self.naming_saved_text.Text = (
            "could not save: {0}".format(failure)[:70] if failure
            else "saved to {0}".format(prefs.path()))

    def _capture_settings(self):
        """Every box, tick, slider and dropdown on this window, as plain JSON.

        Driven by ui.xaml's own x:Names, so nothing has to be listed here twice
        -- a control added to the dialog is captured the day it appears.
        """
        values = {}
        for name in _control_names():
            if not settings.saveable(name):
                continue
            value = _control_value(self.window.FindName(name))
            if value is not None:
                values[name] = value
        layer_map = dict((layer, str(combo.SelectedItem))
                         for layer, combo in self._combos
                         if combo.SelectedItem is not None)
        text_map = dict((layer, str(combo.SelectedItem))
                        for layer, combo in self._text_combos
                        if combo.SelectedItem is not None)
        return settings.payload(values, layer_map, text_map,
                                _version())

    def _restore_controls(self, data):
        """Land a captured snapshot back on the window; returns how many took.

        The one restore path: a settings file, the last session's dialog and
        the draw-stairs preset all come through here, so they restore exactly
        the same set of controls. Layer mappings are restored by LAYER NAME, so
        a saved file helps on the next drawing from the same office even when
        the layer list differs -- the layers it recognises are mapped, the rest
        keep their guess.
        """
        controls, layer_map, text_map = settings.sections(data)
        landed = 0
        for name, value in controls.items():
            if not settings.restorable(name):
                continue
            if _set_control_value(self.window.FindName(name), value):
                landed += 1
        for store, saved in ((self._combos, layer_map),
                             (self._text_combos, text_map)):
            for layer, combo in store:
                index = settings.pick_index(combo.Items, saved.get(layer))
                if index >= 0:
                    combo.SelectedIndex = index
                    landed += 1
        self._show_naming_preview()
        self._stair_sync()
        return landed

    def on_settings_save(self, sender, args):
        path = _save_settings_file()
        if not path:
            return
        failure = settings.write(path, self._capture_settings())
        self.status_text.Text = ("could not save: {0}".format(failure)[:90]
                                 if failure else "settings saved to {0}".format(
                                     os.path.basename(path)))

    def on_settings_load(self, sender, args):
        path = _open_settings_file()
        if not path:
            return
        data = settings.read(path)
        if not data:
            self.status_text.Text = "not a cad2bim settings file: {0}".format(
                os.path.basename(path))
            return
        landed = self._restore_controls(data)
        self.status_text.Text = "{0} setting(s) loaded -- {1}".format(
            landed, settings.describe(data))

    _NAMING_SAMPLE = {"b": 400, "h": 600, "d": 600, "w": 300, "t": 200,
                      "r": 150, "k": 200, "n": 3, "o": "3rd", "e": 3000,
                      "label": "First Floor", "name": "A"}

    def _show_naming_preview(self):
        """Show what each template would call a type, or why it cannot."""
        for key, box in self.name_boxes.items():
            text = (box.Text or "").strip()
            problem = naming.validate(key, text) if text else "empty"
            if problem:
                self.name_labels[key].Text = problem[:44]
                continue
            sample = dict((field, self._NAMING_SAMPLE[field])
                          for field in naming.FIELDS[key])
            self.name_labels[key].Text = text.format(**sample)[:44]

    def on_naming_changed(self, sender, args):
        self._show_naming_preview()

    def on_naming_defaults(self, sender, args):
        for key, box in self.name_boxes.items():
            box.Text = naming.DEFAULTS[key]
        self._show_naming_preview()

    def _read_naming(self):
        """The Naming tab's templates; a broken one falls back to its default."""
        out = {}
        for key, box in self.name_boxes.items():
            text = (box.Text or "").strip()
            out[key] = (text if text and not naming.validate(key, text)
                        else naming.DEFAULTS[key])
        return out

    def _show_outline_count(self):
        count = len(self.stair_regions)
        self.stair_outline_text.Text = (
            "no outlines drawn" if not count
            else "{0} outline(s) ready".format(count))

    def on_draw_stairs(self, sender, args):
        """Hand the view back to the user so they can DRAW the outlines.

        Revit will not run its own line tool while a modal window is up and
        the API cannot resume a posted command, so the window closes, the
        script drives a snapped point-by-point outline picker (real detail
        lines are created as feedback), and then this window is rebuilt with
        every setting restored.
        """
        self.result = self._collect(action="draw_stairs")
        self.window.Close()

    def on_cancel(self, sender, args):
        self.result = None
        self.window.Close()

    def show(self):
        self.window.ShowDialog()

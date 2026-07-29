#! python3
# -*- coding: utf-8 -*-
"""CAD to BIM -- pick a DXF, link it, and build Revit structure from it.

Workflow (CAD-free model is the normal case):
  1. Pick a .dxf, choose its drawing unit and positioning (Link DXF dialog).
  2. Link it programmatically (like Revit's Link CAD dialog).
  3. Hybrid extraction: read the Revit link's geometry (internal feet) AND read the
     same DXF with ezdxf for geometry + TEXT; align them with the link transform.
  4. Compare the two to find problem geometry (Revit clips/merges at junctions) and
     build from the cleaner ezdxf geometry.
  5. Classify layers, refine sizes from text marks ("C1 400x400"), and create grids,
     columns and beams in a TransactionGroup with warning suppression.

CPython3 engine compliance (AnonGee Brand Guidelines 12.1 / 12.8.4 / 12.9):
  * `#! python3` shebang on line 1; explicit imports only.
  * NO pyRevit IronPython modules (pyrevit.forms / pyrevit.revit) -- they crash the
    CPython3 engine. Windows load via XamlReader.Load from a .xaml file; the active
    document comes from `__revit__`; dialogs use System.Windows.MessageBox and
    System.Windows.Forms file dialogs (mirrors the shipping BIM Generation tool).
  * Model writes happen after the modal window closes, on the Revit API thread.

The cad2bim package lives in lib/py3/anongee_toolkit; path_resolver puts lib/py3
on sys.path. If the banner's version/path is not what you expect, a stale shadow
copy is on sys.path.
"""

__title__ = "CAD to BIM"
__author__ = "AnonGee"
__min_revit_ver__ = 2022

import os
import re
import sys
import traceback

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xml")
clr.AddReference("System.Windows.Forms")

from System.Windows.Markup import XamlReader
from System.IO import FileStream, FileMode, FileAccess
from System.Windows import (MessageBox, MessageBoxButton, MessageBoxImage,
                            Thickness, GridLength, GridUnitType, VerticalAlignment,
                            TextTrimming)
from System.Windows.Controls import (Grid as WpfGrid, ColumnDefinition, TextBlock,
                                     ComboBox, TextBox, CheckBox)
import System.Windows.Forms


def _bootstrap_lib_path():
    """Put the engine-appropriate lib subfolder (py2/py3) on sys.path.

    Primary: the repo's own path_resolver, which pyRevit makes importable by
    adding the extension `lib/` folder to sys.path. Fallback: climb from this
    file to find the `lib` dir and inject py2/py3 directly.
    """
    try:
        import path_resolver
        path_resolver.update_paths()
        return
    except ImportError:
        pass

    sub = "py3" if sys.version_info[0] == 3 else "py2"
    try:
        cursor = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return

    for _ in range(8):  # bounded: button -> panel -> tab -> extension -> lib
        candidate = os.path.join(cursor, "lib", sub)
        if os.path.isdir(candidate):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return
        cursor = parent


_bootstrap_lib_path()

from anongee_toolkit import cad2bim
from anongee_toolkit.cad2bim import (compat, config, floor_plans, naming,
                                     prefs, report, slab_outlines, stair_layout)
from anongee_toolkit.cad2bim.geom import transform, compare
from anongee_toolkit.cad2bim.classify import layers, marks
from anongee_toolkit.cad2bim.readers import geometry_reader, dxf_reader, dxf_linker
from anongee_toolkit.cad2bim.builders import (columns, beams, grids, slabs,
                                              stairs, txn_failures)

_HERE = os.path.dirname(os.path.abspath(__file__))
_XAML = os.path.join(_HERE, "ui.xaml")
_LINK_XAML = os.path.join(_HERE, "link_options.xaml")

# --- deferred console: the whole run is buffered and only REVEALED when something
# goes wrong (user request: a clean run should not open the pyRevit console at all).
# Printing is what opens that window, so a successful run prints nothing; a failure
# flushes the entire log -- progress bar, per-phase counts, notes -- for diagnosis.
_REAL_PRINT = print   # the genuine print; only the buffer uses it


class _DeferredOut(object):
    def __init__(self):
        self._buf = []
        self.live = False
        self.failed = False

    def say(self, msg=""):
        if self.live:
            _REAL_PRINT(msg)
        else:
            self._buf.append(msg)

    def fail(self):
        """Mark the run as failed: the log is shown when it finishes."""
        self.failed = True

    def flush(self):
        for msg in self._buf:
            _REAL_PRINT(msg)
        self._buf = []
        self.live = True

    def finish(self, outcomes=None):
        """Reveal the log only when the run failed; stay silent otherwise.

        An outcome with errors, a rollback, or a category that produced nothing
        while it was asked for all count as failure -- those are exactly the
        runs where the console is worth opening.
        """
        pending = list((outcomes or {}).values())
        while pending:                      # per-storey runs nest one level
            outcome = pending.pop()
            if not isinstance(outcome, dict):
                continue
            if outcome.get("errors") or outcome.get("rolled_back"):
                self.failed = True
            pending.extend(v for v in outcome.values() if isinstance(v, dict))
        if self.failed:
            self.flush()
        else:
            self._buf = []


_OUT = _DeferredOut()


def _say(msg=""):
    _OUT.say(msg)


def _progress(done, total, label):
    """Print a 10-cell progress bar line: ``[####------]  40%  beams``."""
    frac = (float(done) / total) if total else 1.0
    fill = int(round(frac * 10))
    _say("[{0}{1}] {2:3d}%  {3}".format("#" * fill, "-" * (10 - fill),
                                        int(round(frac * 100)), label))

# A size label within this distance of a member refines it; also the proximity the
# comparison uses to decide "this is the same member" (~half a column).
_COMPARE_TOL_FT = 300.0 / 304.8

# Picked stair detail lines chain into an outline when their ends are this close.
_STAIR_LINE_CHAIN_MM = 50.0


# --- dialogs / messaging (System.Windows only -- no pyRevit) -----------------

def _alert(title, message):
    MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Warning)


def _error(title, message, detail=None):
    _OUT.fail()
    body = message
    if detail:
        body += "\n\n--- technical detail ---\n{0}".format(detail)
    MessageBox.Show(body, title, MessageBoxButton.OK, MessageBoxImage.Error)


def _persisted(tstatus, gstatus):
    """True only if both the inner transaction and the group actually committed."""
    from Autodesk.Revit.DB import TransactionStatus
    return (tstatus == TransactionStatus.Committed
            and gstatus == TransactionStatus.Committed)


def _rollback_alert(label, tstatus, gstatus):
    """Report a silent commit rollback truthfully instead of faking success."""
    message = (
        "{0} were computed but the Revit transaction did NOT persist (commit "
        "status: {1}, group: {2}).\n\nThis usually means error-severity failures "
        "at commit -- most often running into a project that already contains "
        "these elements. Try a fresh/empty project (or undo the previous run), "
        "then run again.".format(label, tstatus, gstatus))
    _OUT.fail()
    _say(message)
    _error("{0} not saved".format(label), message)


def _load_window(xaml_path):
    """Load a WPF Window from a .xaml file via XamlReader (CPython3-safe)."""
    stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
    try:
        return XamlReader.Load(stream)
    finally:
        stream.Close()


def _open_dxf():
    dialog = System.Windows.Forms.OpenFileDialog()
    dialog.Title = "Pick a DXF to link and convert"
    dialog.Filter = "DXF files (*.dxf)|*.dxf|All files (*.*)|*.*"
    if dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK:
        return dialog.FileName
    return None


def _save_json(default_name):
    dialog = System.Windows.Forms.SaveFileDialog()
    dialog.Title = "Export parsed curves to JSON"
    dialog.Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*"
    dialog.FileName = default_name
    if dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK:
        return dialog.FileName
    return None


def _select_containing(combo, keywords):
    """Select the first combo item whose label contains any keyword (lowercased).

    Returns True if a match was selected, leaving the prior selection otherwise.
    """
    for index in range(combo.Items.Count):
        label = str(combo.Items[index]).lower()
        if any(keyword in label for keyword in keywords):
            combo.SelectedIndex = index
            return True
    return False


# --- Link DXF dialog (file + unit + positioning) -----------------------------

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
        find("link_version_text").Text = "v{0}".format(cad2bim.__version__)
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


# --- main mapping / build window (capture-only) ------------------------------

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
                 saved_naming=None, saved_standards=None):
        self.result = None
        self._combos = []
        self._text_combos = []
        saved_naming = saved_naming or naming.DEFAULTS
        saved_standards = saved_standards or {}
        self._saved_standards = saved_standards
        self.window = _load_window(_XAML)
        find = self.window.FindName

        find("version_text").Text = "v{0}".format(cad2bim.__version__)
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
        # Base defaults to the lowest, top to the next level above it.
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
        self.chk_multistorey = find("chk_multistorey")
        self.cb_boundary_layer = find("cb_boundary_layer")
        self.cb_origin_layer = find("cb_origin_layer")
        self.tb_storey_height = find("tb_storey_height")
        self.multistorey_preview = find("multistorey_preview")
        self.storey_rows = find("storey_rows")
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
                             ("stair_waist", "stair_waist")):
            box = find("tb_name_{0}".format(control))
            box.Text = saved_naming.get(key, naming.DEFAULTS[key])
            box.TextChanged += self.on_naming_changed
            self.name_boxes[key] = box
            self.name_labels[key] = find("lbl_name_{0}".format(control))
        self.naming_saved_text = find("naming_saved_text")
        self.btn_name_defaults = find("btn_name_defaults")
        self.btn_name_defaults.Click += self.on_naming_defaults
        self._show_naming_preview()
        self.tb_snap = find("tb_snap")
        self.tb_markrad = find("tb_markrad")
        self.tb_compare = find("tb_compare")
        self.tb_region = find("tb_region")
        self.tb_circ_min = find("tb_circ_min")
        self.tb_circ_max = find("tb_circ_max")
        self.tb_pair_min = find("tb_pair_min")
        self.tb_pair_max = find("tb_pair_max")
        self.tb_slab_snap = find("tb_slab_snap")
        self.tb_slab_heal = find("tb_slab_heal")
        self.tb_slab_chain = find("tb_slab_chain")
        self.tb_slab_width = find("tb_slab_width")
        self.tb_slab_step = find("tb_slab_step")
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

        # Staircase tab live sync: floor height follows the level picks; an
        # ABSOLUTE riser count drives the riser height (storey / count)
        self.cb_base_level.SelectionChanged += self._on_stair_sync
        self.cb_top_level.SelectionChanged += self._on_stair_sync
        self.tb_stair_count.LostFocus += self._on_stair_count_edit
        self.tb_stair_riser.LostFocus += self._on_stair_sync
        self._stair_sync()

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
        """Seed the Units & Tolerances fields from config defaults (mm)."""
        d = config.DEFAULTS
        self.tb_snap.Text = str(int(d["snap_tol_mm"]))
        self.tb_markrad.Text = str(int(d["mark_radius_mm"]))
        self.tb_compare.Text = str(int(d["compare_tol_mm"]))
        self.tb_region.Text = str(int(d["col_region_max_side_mm"]))
        self.tb_circ_min.Text = str(int(d["circle_min_dia_mm"]))
        self.tb_circ_max.Text = str(int(d["circle_max_dia_mm"]))
        self.tb_pair_min.Text = str(int(d["pair_min_width_mm"]))
        self.tb_pair_max.Text = str(int(d["pair_max_width_mm"]))
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
        self.tb_std_columns.Text = saved.get("column", "")
        self.tb_std_beams.Text = saved.get("beam_widths", "")

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
            "col_region_max_side_mm": self._read_float(self.tb_region, d["col_region_max_side_mm"]),
            "circle_min_dia_mm": self._read_float(self.tb_circ_min, d["circle_min_dia_mm"]),
            "circle_max_dia_mm": self._read_float(self.tb_circ_max, d["circle_max_dia_mm"]),
            "pair_min_width_mm": self._read_float(self.tb_pair_min, d["pair_min_width_mm"]),
            "pair_max_width_mm": self._read_float(self.tb_pair_max, d["pair_max_width_mm"]),
            "slab_snap_mm": self._read_float(self.tb_slab_snap, d["slab_snap_mm"]),
            "slab_heal_mm": self._read_float(self.tb_slab_heal, d["slab_heal_mm"]),
            "slab_chain_mm": self._read_float(self.tb_slab_chain, d["slab_chain_mm"]),
            "slab_min_width_mm": self._read_float(self.tb_slab_width,
                                                  d["slab_min_width_mm"]),
            "slab_min_step_mm": self._read_float(self.tb_slab_step,
                                                 d["slab_min_step_mm"]),
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
        """The generic stair shape picked on the Staircase tab (U by default)."""
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
            "naming": self._read_naming(),
            "standard_text": {"column": self.tb_std_columns.Text,
                              "beam_widths": self.tb_std_beams.Text},
        }

    def _apply_preset(self, preset):
        """Put a previous run of this dialog back on screen.

        The window is rebuilt after the user draws stair outlines in the view,
        so everything they had already chosen must come back with it. Anything
        the preset does not name keeps the freshly computed default.
        """
        def combo(control, ids, wanted):
            if wanted is None:
                return
            for label, element_id in ids.items():
                if element_id == wanted:
                    control.SelectedItem = label
                    return

        for layer, control in self._combos:
            value = (preset.get("mapping") or {}).get(layer)
            if value:
                control.SelectedItem = value
        for layer, control in self._text_combos:
            value = (preset.get("text_mapping") or {}).get(layer)
            if value:
                control.SelectedItem = value
        for key, box in (("create_grids", self.chk_grids),
                         ("create_columns", self.chk_columns),
                         ("create_beams", self.chk_beams),
                         ("create_slabs", self.chk_slabs),
                         ("create_stairs", self.chk_stairs),
                         ("export", self.chk_export),
                         ("multistorey", self.chk_multistorey)):
            if key in preset and box.IsEnabled:
                box.IsChecked = bool(preset[key])
        combo(self.cb_family, self._family_ids, preset.get("column_family_id"))
        combo(self.cb_circular_family, self._family_ids,
              preset.get("circular_family_id"))
        combo(self.cb_beam_family, self._beam_ids, preset.get("beam_family_id"))
        combo(self.cb_floor_type, self._floor_ids, preset.get("floor_type_id"))
        combo(self.cb_stair_type, self._stair_ids, preset.get("stair_type_id"))
        combo(self.cb_base_level, self._level_ids, preset.get("base_level_id"))
        combo(self.cb_top_level, self._level_ids, preset.get("top_level_id"))
        if preset.get("name_parameter"):
            self.cb_name_param.Text = preset["name_parameter"]
        source = preset.get("stair_source")
        if source:
            self.cb_stair_source.SelectedIndex = {
                "auto": 0, "linework": 1, "text": 2, "region": 3}.get(source, 0)
        shape = preset.get("stair_shape")
        for radio, value in self.shape_buttons:
            if value == shape:
                radio.IsChecked = True
        params = preset.get("stair_params") or {}
        for key, box in (("riser_count", self.tb_stair_count),
                         ("riser_mm", self.tb_stair_riser),
                         ("tread_mm", self.tb_stair_tread),
                         ("run_width_mm", self.tb_stair_width),
                         ("landing_mm", self.tb_stair_landing),
                         ("waist_mm", self.tb_stair_waist)):
            if params.get(key) is not None:
                box.Text = "{0:g}".format(params[key])
        for name in ("boundary_layer", "origin_layer"):
            wanted = preset.get(name)
            control = (self.cb_boundary_layer if name == "boundary_layer"
                       else self.cb_origin_layer)
            if wanted:
                control.SelectedItem = wanted
        for row, saved in zip(self._storey_boxes,
                              preset.get("storey_settings") or []):
            _plan, height_box, repeat_box, include_box = row
            height = saved.get("height_mm")
            height_box.Text = "" if height is None else "{0:g}".format(height)
            repeat_box.Text = str(int(saved.get("repeat") or 1))
            include_box.IsChecked = saved.get("include", True)
        for key, box in self.name_boxes.items():
            value = (preset.get("naming") or {}).get(key)
            if value:
                box.Text = value
        self._show_naming_preview()
        self._stair_sync()

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
        """One editable row per detected plan: label, height, repeat.

        The rows are created here rather than declared in the XAML because how
        many there are is only known once the drawing has been read; each row's
        two boxes are kept in self._storey_boxes so _read_selections can read
        them back in the same bottom-up order.
        """
        self.storey_rows.Children.Clear()
        self._storey_boxes = []
        for plan in plans or []:
            row = WpfGrid()
            row.Margin = Thickness(0, 1, 0, 1)
            for width in (0.0, 80.0, 60.0):
                column = ColumnDefinition()
                column.Width = (GridLength(1, GridUnitType.Star) if not width
                                else GridLength(width))
                row.ColumnDefinitions.Add(column)
            # the checkbox IS the label: untick a plan to leave that storey out
            include = CheckBox()
            include.IsChecked = True
            include.VerticalAlignment = VerticalAlignment.Center
            label = TextBlock()
            label.Text = (plan.get("label")
                          or "storey {0}".format(len(self._storey_boxes) + 1))
            label.TextTrimming = TextTrimming.CharacterEllipsis
            include.Content = label
            WpfGrid.SetColumn(include, 0)
            row.Children.Add(include)
            height = TextBox()
            height.Height = 22
            height.Margin = Thickness(0, 1, 8, 1)
            height.Text = ("" if plan.get("height_mm") is None
                           else "{0:g}".format(plan["height_mm"]))
            WpfGrid.SetColumn(height, 1)
            row.Children.Add(height)
            repeat = TextBox()
            repeat.Height = 22
            repeat.Margin = Thickness(0, 1, 0, 1)
            repeat.Text = str(int(plan.get("repeat") or 1))
            WpfGrid.SetColumn(repeat, 2)
            row.Children.Add(repeat)
            self.storey_rows.Children.Add(row)
            self._storey_boxes.append((plan, height, repeat, include))

    def _read_storey_settings(self):
        """The per-storey rows as plain dicts, bottom-up (what the build wants)."""
        settings = []
        for plan, height_box, repeat_box, include_box in self._storey_boxes:
            settings.append({
                "label": plan.get("label"),
                "order": plan.get("order"),
                "include": bool(include_box.IsChecked),
                "height_mm": self._read_float(height_box, None),
                "repeat": self._read_int(repeat_box, plan.get("repeat") or 1)})
        return settings

    def _remember_conventions(self):
        """Keep the office conventions for the NEXT Revit session.

        Only the naming templates and the standard sizes: everything else on
        the dialog is about this drawing and should start fresh each run.
        """
        naming.save(self._read_naming())
        prefs.update({"standards": {"column": self.tb_std_columns.Text or "",
                                    "beam_widths": self.tb_std_beams.Text or ""}})
        failure = prefs.last_error()
        self.naming_saved_text.Text = (
            "could not save: {0}".format(failure)[:70] if failure
            else "saved to {0}".format(prefs.path()))

    _NAMING_SAMPLE = {"b": 400, "h": 600, "d": 600, "w": 300, "t": 200,
                      "r": 150, "k": 200}

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


def _layer_names(records):
    """Distinct layer keys present in a record list, sorted for stable display."""
    return sorted(set(r.layer_key for r in records))


def _grid_axis_positions(records):
    """(grid_x, grid_y) lists in internal feet from the grid lines: a vertical
    grid contributes its x, a horizontal grid its y. Used to snap columns."""
    grid_x, grid_y = set(), set()
    for record in records:
        if layers.classify_layer(record.layer_key) != layers.CATEGORY_GRID:
            continue
        if record.kind != "line" or len(record.points) < 2:
            continue
        p0, p1 = record.points[0], record.points[-1]
        if abs(p1[0] - p0[0]) <= abs(p1[1] - p0[1]):
            grid_x.add((p0[0] + p1[0]) / 2.0)   # vertical grid -> constant x
        else:
            grid_y.add((p0[1] + p1[1]) / 2.0)   # horizontal grid -> constant y
    return sorted(grid_x), sorted(grid_y)


def main():
    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None or uidoc.Document is None:
        _alert("No document", "Open a Revit project before running CAD to BIM.")
        return
    doc = uidoc.Document

    module_dir = os.path.dirname(os.path.abspath(report.__file__))
    _say("cad2bim {0} loaded from {1}".format(cad2bim.__version__, module_dir))
    _say(compat.runtime_summary())
    try:
        _say("Host: Revit {0}".format(__revit__.Application.VersionNumber))
    except Exception:
        pass

    if not dxf_reader.ezdxf_available():
        _error("ezdxf not available",
               "ezdxf could not be imported on this engine.\n\nIf you just "
               "provisioned it, run the button again (or fully restart Revit). "
               "Otherwise run tools/auto_provision.py to install it into lib/py3.",
               detail=str(dxf_reader._EZDXF_ERROR))
        return

    # 1. Pick the DXF + its unit + positioning, then link it (own transaction).
    active_view_name = getattr(getattr(doc, "ActiveView", None), "Name", "-")
    options = LinkOptionsDialog(active_view_name)
    options.show()
    if not options.result:
        return
    path = options.result["path"]
    _progress(1, 9, "link DXF")
    try:
        instance = dxf_linker.link_dxf(doc, path, options.result["unit"],
                                       options.result["placement"],
                                       this_view_only=options.result["this_view_only"])
    except Exception:
        _error("Link failed", "Could not link the DXF.", traceback.format_exc())
        _OUT.finish()
        return

    # 2. Hybrid read: Revit link geometry is the BUILD source (already in Revit
    #    coordinates and pre-merged into polylines). The DXF (ezdxf) supplies TEXT
    #    only, mapped into Revit coordinates by the link's own exact transform.
    _progress(2, 9, "read link geometry")
    revit_result = geometry_reader.read_link(doc, instance)
    if revit_result.is_empty():
        _alert("Empty link", "The linked DXF produced no readable geometry in "
               "Revit. Check the link is visible in the active view.")
        _OUT.fail()
        _OUT.finish()
        return
    try:
        dxf_result = dxf_reader.read_dxf(path)
    except Exception:
        _error("DXF read failed", "Could not read the DXF for text.", traceback.format_exc())
        _OUT.finish()
        return

    # Map DXF coords -> Revit feet using the GRID lines as anchors: they are the
    # same lines in both the Revit and DXF extractions, so aligning their bounding
    # boxes is exact (no symbol-space unit guessing). A plan with NO grid layer
    # (Test20 stress plan) anchors on ALL shared geometry instead -- the two reads
    # are the same drawing, so their overall bboxes align the same way. Only when
    # both anchors are empty do we trust the link's own transform: Revit can bake
    # the unit scale into the imported geometry and report an identity instance
    # transform, which threw every Test20 label 304.8x off and killed all sizing.
    rev_grids = [r for r in revit_result.records
                 if layers.classify_layer(r.layer_key) == layers.CATEGORY_GRID]
    dxf_grids = [r for r in dxf_result.records
                 if layers.classify_layer(r.layer_key) == layers.CATEGORY_GRID]
    rev_bbox = transform.bbox_of_records(rev_grids)
    dxf_bbox = transform.bbox_of_records(dxf_grids)
    rev_all = transform.bbox_of_records(revit_result.records)
    dxf_all = transform.bbox_of_records(dxf_result.records)
    if rev_bbox and dxf_bbox:
        text_affine = transform.empirical_affine(dxf_bbox, rev_bbox)
        transform_method = "grid_anchored"
    elif rev_all and dxf_all:
        text_affine = transform.empirical_affine(dxf_all, rev_all)
        transform_method = "geometry_anchored"
    else:
        text_affine = transform.from_link(instance)
        transform_method = "link_GetTotalTransform"
    transform.apply_to_texts(text_affine, dxf_result.texts)
    marks.parse_texts(dxf_result.texts)
    # Map a copy of the DXF geometry the same way, only to report problem geometry.
    transform.apply_to_records(text_affine, dxf_result.records)

    # Build the window from the REVIT records (the build source) UNIONED with the
    # DXF-only layers. Revit's import drops some entity types outright -- a bare
    # POINT is the floor-ORIGIN convention and never survives it -- so a layer
    # that exists only in the DXF was invisible in this table and unmappable,
    # which left multi-storey runs without an origin and every storey shifted.
    layer_counts = report.build_layer_counts(revit_result.records)
    dxf_counts = report.build_layer_counts(dxf_result.records)
    names = sorted(set(layer_counts) | set(dxf_counts))
    layer_rows = []
    for name in names:
        revit_n = layer_counts.get(name, {}).get("count", 0)
        dxf_n = dxf_counts.get(name, {}).get("count", 0)
        layer_rows.append((name, revit_n if revit_n else dxf_n))
    dxf_only = [name for name in names if not layer_counts.get(name)]
    if dxf_only:
        _say("Layers present in the DXF but not in the Revit link (still "
             "mappable): {0}".format(", ".join(dxf_only)))
    default_mapping = layers.build_default_mapping(names)
    column_symbols = columns.structural_column_symbols(doc)
    level_options = columns.levels(doc)
    beam_symbols = beams.structural_framing_symbols(doc)
    floor_type_options = slabs.floor_types(doc)
    stair_type_options = stairs.stairs_types(doc)
    level_elevations = {label: doc.GetElement(level_id).Elevation
                        for label, level_id in level_options}

    # Text layers (size marks) come from the DXF, routed separately from geometry.
    text_layer_counts = {}
    for text in dxf_result.texts:
        text_layer_counts[text.layer_key] = text_layer_counts.get(text.layer_key, 0) + 1
    text_names = sorted(text_layer_counts.keys())
    text_layer_rows = [(name, text_layer_counts[name]) for name in text_names]
    default_text_mapping = layers.build_default_text_mapping(text_names)

    # Is this ONE plan or a sheet of storeys? Read off the DXF (its bare origin
    # POINTs do not always survive Revit's import) so the Multi-storey tab opens
    # already answered instead of waiting for the user to guess two layer names.
    storey_detection = floor_plans.autodetect_storeys(dxf_result.records,
                                                      dxf_result.texts)
    # Naming templates and standard sizes are office conventions, not per-drawing
    # numbers, so they come back from the preferences file the last run wrote.
    saved_naming = naming.load()
    saved_standards = prefs.load().get("standards") or {}
    _say("Storeys: {0}".format(storey_detection.reason))
    for note in storey_detection.notes:
        _say("  storey: {0}".format(note))

    # The dialog can hand the view back so the user DRAWS the stair outlines:
    # it closes, the outlines are picked in the model, and it reopens with every
    # setting restored. Anything else falls straight through to the build.
    preset = None
    stair_regions = []
    while True:
        window = CadToBimWindow(dxf_result.source_name, layer_rows,
                                list(layers.ALL_CATEGORIES), default_mapping,
                                column_symbols, level_options, beam_symbols,
                                floor_type_options,
                                text_layer_rows, list(layers.TEXT_CATEGORIES),
                                default_text_mapping,
                                stair_type_options=stair_type_options,
                                level_elevations=level_elevations,
                                stair_regions=stair_regions, preset=preset,
                                storey_detection=storey_detection,
                                saved_naming=saved_naming,
                                saved_standards=saved_standards)
        window.show()
        if not window.result:
            return   # cancelled -- nothing was flushed, console stays closed
        if window.result.get("action") != "draw_stairs":
            break
        preset = window.result
        drawn = _draw_stair_outlines(doc)
        if drawn:
            stair_regions = drawn
        preset["stair_regions"] = stair_regions

    selections = window.result
    layers.apply_mapping(revit_result.records, selections["mapping"])
    # the DXF records carry the markers a Revit import drops, so they get the
    # SAME mapping -- otherwise a DXF-only layer stays uncategorised
    layers.apply_mapping(dxf_result.records, selections["mapping"])
    # The Multi-storey tab picks the boundary/origin layers BY NAME (they differ
    # per drawing), so route them here -- after the layer table, so an explicit
    # pick always wins over the naming convention.
    for layer_name, category in ((selections.get("boundary_layer"),
                                  layers.CATEGORY_FLOOR_BOUNDARY),
                                 (selections.get("origin_layer"),
                                  layers.CATEGORY_FLOOR_ORIGIN)):
        if not layer_name:
            continue
        for record in list(revit_result.records) + list(dxf_result.records):
            if record.layer_key == layer_name:
                record.category = category
    limits = selections.get("limits")
    standards = selections.get("standards")
    tolerances = selections.get("tolerances") or {}
    # the Tolerances tab owns every tunable, including the ones that used to be
    # module constants in the slab and stair geometry
    slab_outlines.apply_tolerances(tolerances)
    stair_layout.apply_tolerances(tolerances)
    # every element writes its CAD mark into the parameter chosen on the
    # Structure tab (Mark stays the fallback when a family lacks it)
    compat.set_name_parameter(selections.get("name_parameter"))
    # every auto-created family type is named from the Naming tab's templates
    naming.apply(selections.get("naming"))
    for problem in naming.problems():
        _say("naming: {0}".format(problem))

    # Diagnostic only: how much Revit's import dropped/clipped vs the raw DXF.
    compare_tol_ft = config.mm_to_ft(tolerances.get("compare_tol_mm",
                                                    config.DEFAULTS["compare_tol_mm"]))
    comparison = compare.diff(revit_result.records, dxf_result.records, compare_tol_ft)
    comparison["transform"] = {"method": transform_method}

    # MULTI-STOREY: one dxf holding several floor plans, each boxed on the
    # boundary layer with an origin marker inside. Each storey is built by the
    # SAME pipeline below, on its own level pair, from records shifted so its
    # marker lands on the model origin.
    storeys = None
    if selections.get("multistorey"):
        # the boundary rectangle and origin POINT come from the DXF read (a
        # bare POINT does not always survive Revit's import), and the RECORDS
        # split by them are the Revit ones the pipeline builds from
        regions, floor_notes = floor_plans.split_floors(
            revit_result.records, dxf_result.texts,
            marker_records=dxf_result.records,
            boundary_layer=selections.get("boundary_layer"),
            origin_layer=selections.get("origin_layer"))
        for note in floor_notes:
            _say("  storey: {0}".format(note))
        regions = floor_plans.apply_storey_settings(
            regions, selections.get("storey_settings"))
        if len(regions) > 1:
            _say("Multi-storey: {0} floor plan(s) found -- {1}".format(
                len(regions),
                ", ".join((r.label or "storey {0}".format(i + 1))
                          for i, r in enumerate(regions))))
            storeys = regions
        elif regions:
            _say("Multi-storey: only one floor plan found -- building it alone.")
        else:
            _say("Multi-storey: no floor boundaries found -- building the whole "
                 "drawing as one storey.")

    if storeys:
        # A TYPICAL plan builds once per repeat, each on its own level pair, so
        # the ladder is sized from the EXPANDED list, not the plan count.
        built = floor_plans.expand_repeats(storeys)
        level_pairs = _storey_level_pairs(doc, selections, built)
        storey_payloads = []
        all_outcomes = {}
        for index, (region, label) in enumerate(built):
            base_id, top_id = level_pairs[index]
            _say("")
            _say("=== {0} ({1} records) ===".format(label, len(region.records)))
            storey_selections = dict(selections)
            storey_selections["base_level_id"] = base_id
            storey_selections["top_level_id"] = top_id
            storey_result = _StoreyResult(revit_result, region.records)
            outcomes = _build_one_storey(
                doc, storey_result, region.texts, storey_selections,
                schedule_source=dxf_result.texts, path=path,
                comparison=comparison, transform_method=transform_method,
                storey_label=label, collect=storey_payloads)
            all_outcomes["{0}".format(label)] = outcomes
        if storey_payloads:
            _export_storeys(storey_payloads, revit_result.source_name,
                            _export_name(path, selections))
        _OUT.finish(all_outcomes)
        return

    outcomes = _build_one_storey(doc, revit_result, dxf_result.texts, selections,
                                 schedule_source=dxf_result.texts, path=path,
                                 comparison=comparison,
                                 transform_method=transform_method)
    _OUT.finish(outcomes)


class _StoreyResult(object):
    """One storey's read result: the parent result with its records swapped."""

    def __init__(self, base_result, records):
        self.__dict__.update(base_result.__dict__)
        self.records = records


def _storey_level_pairs(doc, selections, built):
    """[(base_level_id, top_level_id)] for the storeys in `built`, lowest first.

    `built` is [(region, label)] with typical plans already repeated. The lowest
    storey sits on the chosen base level and each one above it moves up a level.
    When the model runs out, new levels are created -- each at ITS OWN storey's
    height (the Multi-storey tab's per-plan Height column), falling back to the
    single storey height when a row was left blank.
    """
    from Autodesk.Revit.DB import Level, Transaction, FilteredElementCollector

    count = len(built)
    default_mm = (selections.get("storey_height_mm")
                  or config.DEFAULTS["storey_height_mm"])
    heights_mm = [(getattr(region, "storey_height_mm", None) or default_mm)
                  for region, _label in built]

    existing = sorted(FilteredElementCollector(doc).OfClass(Level).ToElements(),
                      key=lambda lv: lv.Elevation)
    base_id = selections.get("base_level_id")
    start = 0
    for i, level in enumerate(existing):
        if level.Id == base_id:
            start = i
            break
    ladder = existing[start:]
    needed = count + 1
    if len(ladder) < needed:
        transaction = Transaction(doc, "CAD to BIM: storey levels")
        transaction.Start()
        try:
            txn_failures.attach_warning_swallower(transaction)
            created = 0
            while len(ladder) < needed:
                # the level being ADDED tops the storey whose height it takes
                rise_mm = heights_mm[min(len(ladder) - 1, count - 1)]
                elevation = ladder[-1].Elevation + config.mm_to_ft(rise_mm)
                new_level = Level.Create(doc, elevation)
                try:
                    new_level.Name = "CAD Level {0}".format(len(ladder) + 1)
                except Exception:
                    pass          # a name clash keeps Revit's default name
                ladder.append(new_level)
                created += 1
            transaction.Commit()
            spacing = sorted(set(int(h) for h in heights_mm))
            _say("Multi-storey: created {0} level(s) at {1} mm".format(
                created, ", ".join(str(value) for value in spacing)))
        except Exception as level_error:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
            _say("Multi-storey: could not create levels ({0}) -- storeys will "
                 "share the chosen pair".format(str(level_error)[:120]))
            return [(selections.get("base_level_id"),
                     selections.get("top_level_id"))] * count
    return [(ladder[i].Id, ladder[i + 1].Id) for i in range(count)]


def _build_one_storey(doc, revit_result, texts, selections, schedule_source=None,
                      path=None, comparison=None, transform_method=None,
                      storey_label=None, collect=None):
    """Build ONE storey: columns, beams, slabs and stairs from its records.

    `collect` is the multi-storey accumulator: when it is a list this storey
    appends (label, payload) to it instead of writing its own JSON, so the run
    ends with ONE file holding a section per storey.
    """
    limits = selections.get("limits")
    standards = selections.get("standards")
    tolerances = selections.get("tolerances") or {}
    dxf_texts = texts

    _progress(3, 9, "build columns")
    sections = report.build_column_sections(revit_result.records, limits, standards,
                                            texts=None, tolerances=tolerances)

    # Route text labels by their (user-confirmed) layer.
    text_mapping = selections.get("text_mapping") or {}
    column_texts = [t for t in dxf_texts
                    if text_mapping.get(t.layer_key) == layers.CATEGORY_COLUMN_TEXT]
    grid_texts = [t for t in dxf_texts
                  if text_mapping.get(t.layer_key) == layers.CATEGORY_GRID_TEXT]
    # THIS storey's own schedule first: a keyed table ("(a) = 200x600") is per
    # sheet, and test9's floors disagree on what (a) means, so reading the whole
    # file would size a beam off the wrong floor's table. A shared schedule that
    # lives on ONE sheet still works -- the whole file is the fallback below.
    own_schedule_texts = [t for t in dxf_texts
                          if text_mapping.get(t.layer_key)
                          == layers.CATEGORY_COLUMN_SCHEDULE]
    schedule_texts = own_schedule_texts or [
        t for t in (schedule_source or dxf_texts)
        if text_mapping.get(t.layer_key) == layers.CATEGORY_COLUMN_SCHEDULE]
    beam_texts = [t for t in dxf_texts
                  if text_mapping.get(t.layer_key) == layers.CATEGORY_BEAM_TEXT]

    # The schedule (mark -> size) sizes MARK-ONLY plan labels (columns AND beams). The
    # table is authoritative; any sized plan label supplements a mark the table omits.
    schedule = marks.parse_schedule(schedule_texts)
    # Plan labels are NOT a table: only adopt an INLINE size ("C9 400x600") from one,
    # never split-pair a markless size label with a far mark sharing its row (which
    # mis-sized C5 from a neighbour's 350x750 a bay away).
    for mark, size in marks.parse_schedule(column_texts, allow_split=False).items():
        schedule.setdefault(mark, size)
    if schedule:
        _say("columns: parsed {0} schedule size(s) from text".format(len(schedule)))

    # Beam DEPTH (the larger label dimension) cannot be read from a 2D plan outline, so a
    # beam is sized from its label -- an inline "B1 300x600" OR a mark-only "B1" via the
    # schedule. Pass beam labels + the schedule so each segment gets its width/depth + mark.
    _progress(4, 9, "build beams")
    beam_segments = report.build_beam_segments(revit_result.records,
                                               sections.get("circles"),
                                               limits, standards,
                                               texts=beam_texts, tolerances=tolerances,
                                               schedule=schedule)
    sized_beams = beam_segments["status_counts"].get("text_sized", 0)
    if sized_beams:
        _say("beams: sized {0} segment(s) from labels (width + depth)".format(sized_beams))

    # Grid-line axis positions (internal feet) -> snap text-corrected column
    # centres onto the grid (columns sit on grid intersections).
    grid_x, grid_y = _grid_axis_positions(revit_result.records)

    # Column-text labels (one per real column) resize clipped columns (G9) and
    # merge grid-crossing-split pieces (E9), snapped to the grid intersection.
    mark_radius_ft = config.mm_to_ft(tolerances.get("mark_radius_mm",
                                                    config.DEFAULTS["mark_radius_mm"]))
    grid_snap_ft = config.mm_to_ft(config.DEFAULTS["grid_snap_mm"])

    # A fused lift/stair core (loose wall lines blobbed + greedily decomposed) mis-cuts
    # its shared corners, so each wall is the right thickness but offset along its length.
    # Re-tile each such blob from its mark+size labels first, so text-correction then just
    # names the now-correctly-placed walls instead of resizing a mis-centred piece.
    retiled = report.recover_core_walls_from_labels(sections, column_texts, schedule)
    if retiled:
        _say("columns: re-tiled {0} fused core(s) from labels".format(retiled))
    fixed = report.correct_columns_with_text(sections, column_texts, mark_radius_ft,
                                             schedule=schedule,
                                             grid_x=grid_x, grid_y=grid_y,
                                             grid_snap_ft=grid_snap_ft)
    if fixed:
        _say("columns: text-corrected {0} (clipped/merged from size labels)".format(fixed))
    named_circles = report.apply_circle_marks(sections, column_texts, mark_radius_ft)
    if named_circles:
        _say("columns: named {0} circular column(s) from labels".format(named_circles))

    # Last resort: a small column cast against a bigger one can fragment so badly that
    # recovery folds it into the neighbour, orphaning its label. Recover it from its
    # schedule size + leftover geometry (never overlapping an already-placed column).
    recovered_labeled = report.recover_unplaced_labeled_columns(
        sections, column_texts, schedule, limits=limits)
    if recovered_labeled:
        _say("columns: recovered {0} absorbed labelled column(s) from "
              "schedule+geometry".format(recovered_labeled))

    # Blade / wall-columns beyond the size limits (dropped by detection) whose
    # outlines are drawn CLOSED on the column layer: place them at drawn size,
    # position and angle (test8's AC19..BC28 strips).
    recovered_outline = report.recover_outline_columns(
        sections, revit_result.records, column_texts)
    if recovered_outline:
        _say("columns: placed {0} blade/outline column(s) beyond the size "
             "limits".format(recovered_outline))

    # Close the junction gap where a beam end meets a ROUND or ROTATED column: run the beam
    # end to the column centre (columns are now final). Axis-aligned columns are untouched.
    snapped_ends = report.snap_beam_ends_to_columns(
        beam_segments, sections, sections.get("circles"))
    if snapped_ends:
        _say("beams: snapped {0} end(s) to round/rotated column centres".format(snapped_ends))

    # A messy beam outline that RETRACES its own edges decomposes into the same
    # centreline twice -> two beams z-fighting in Revit (test8's column strips).
    deduped_beams = report.dedupe_beam_segments(beam_segments)
    if deduped_beams:
        _say("beams: removed {0} duplicate segment(s)".format(deduped_beams))

    # A beam outline drawn straight ACROSS a column would bury a beam inside it: split
    # such beams at the column faces so they frame IN, not through (client request).
    # Obstacles include closed rectangular column-LAYER outlines the detector dropped
    # (blade columns beyond the size limits are still real columns). Slabs keep the
    # PRE-SPLIT centrelines -- the beam-graph slab source needs its bay loops to run
    # continuously over the columns (split never mutates kept dicts).
    slab_beam_segments = dict(beam_segments)
    slab_beam_segments["segments"] = list(beam_segments["segments"])
    # recover_outline_columns has PLACED every usable closed outline, so the placed
    # footprints cover everything -- passing the outline fits AS WELL doubled every
    # ring (two slightly-offset squares per column = 0.42.0's jagged diamond trims)
    # and doubled the slab graph cost.
    column_footprints = report.column_trim_footprints(sections)
    split_beams = report.split_beams_at_columns(
        beam_segments, sections, sections.get("circles"))
    if split_beams:
        _say("beams: split {0} beam(s) drawn across column footprints".format(split_beams))

    if storey_label is None:
        _say("### CAD to BIM {0}".format(cad2bim.__version__))
    for line in compare.format_console(comparison or {}):
        _say(line)
    for line in report.format_console(revit_result, selections["mapping"],
                                      sections, beam_segments):
        _say(line)

    outcomes = {}
    _progress(5, 9, "create grids")
    if selections["create_grids"]:
        outcomes["grids"] = _create_grids(doc, revit_result.records, grid_texts)
    _progress(6, 9, "create columns")
    if selections["create_columns"]:
        outcomes["columns"] = _create_columns(doc, sections, selections)
    _progress(7, 9, "create beams")
    if selections["create_beams"]:
        outcomes["beams"] = _create_beams(doc, beam_segments, selections)
    # SLABS: outlines from the slab-edge (A-FLOR) rings, falling back to the
    # PLACED beams + column footprints when the DWG has no slab layer;
    # thickness/mark from "S1 150 THK" / "150 THK." notes anywhere in the text.
    _progress(8, 9, "create slabs")
    if selections["create_slabs"]:
        outcomes["slabs"] = _create_slabs(doc, revit_result.records, slab_beam_segments,
                                          dxf_texts, selections, schedule,
                                          column_rects=column_footprints)
    # STAIRS (option 1, parametric): a STAIRCASE / ST-n text marks the bay; a
    # generic dog-leg from the Staircase tab numbers is laid out inside it.
    _progress(9, 9, "create stairs")
    if selections.get("create_stairs"):
        outcomes["stairs"] = _create_stairs(doc, revit_result.records,
                                            slab_beam_segments, dxf_texts,
                                            selections,
                                            column_rects=column_footprints)
    if selections["export"]:
        if collect is not None:
            collect.append((storey_label or "storey",
                            report.build_export_payload(
                                revit_result, selections["mapping"], sections,
                                beam_segments, outcomes, texts=dxf_texts,
                                comparison=comparison)))
        else:
            _export(revit_result, selections["mapping"], sections, beam_segments,
                    outcomes, dxf_texts, comparison,
                    default_name=_export_name(path, selections,
                                              storey_label=storey_label))
    return outcomes


def _create_grids(doc, records, grid_texts=None):
    """Create grids from classified grid lines, inside a transaction group.

    Names come from grid-text labels (e.g. DWG bubbles 'A','1') when available,
    falling back to the A-Z x 1-9 convention. All Revit writes happen here on the
    API thread after the window closes; both transaction and group roll back on
    any failure.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup, TransactionStatus
    grid_records = [r for r in records
                    if r.category == layers.CATEGORY_GRID and r.kind in ("line", "arc")]
    if not grid_records:
        _say("Grids -- no grid-category lines to create.")
        return {"created": 0, "skipped": 0, "errors": 0}

    namer = grids.build_grid_namer(grid_records, grid_texts)
    group = TransactionGroup(doc, "CAD to BIM: Grids")
    transaction = Transaction(doc, "Create grids")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = grids.create_grids(doc, grid_records, namer)
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Grid creation failed", "Grid creation failed.", str(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Grids", tstatus, gstatus)
        return {"created": 0, "skipped": 0, "errors": 0, "rolled_back": True}

    _say("Grids -- created: {0}, skipped: {1}, errors: {2}".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    for message in result["errors"]:
        _say("  grid: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"])}


def _create_columns(doc, sections, selections):
    """Place rectangular + circular columns from the decomposed sections, in a group."""
    from Autodesk.Revit.DB import Transaction, TransactionGroup, TransactionStatus
    family_id = selections.get("column_family_id")
    base_id = selections.get("base_level_id")
    top_id = selections.get("top_level_id")
    if family_id is None or base_id is None or top_id is None:
        _alert("Columns skipped", "Choose a column family and base/top levels.")
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0}
    if not sections.get("entries"):
        _say("Columns -- no column sections to place.")
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0}

    group = TransactionGroup(doc, "CAD to BIM: Columns")
    transaction = Transaction(doc, "Create columns")
    region_max = (selections.get("tolerances") or {}).get("col_region_max_side_mm")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = columns.place_columns(doc, sections, family_id, base_id, top_id,
                                       region_max_side_mm=region_max)
        circles = sections.get("circles", [])
        circular_id = selections.get("circular_family_id")
        circular = {"created": [], "errors": []}
        if circles and circular_id is not None:
            circular = columns.place_circular_columns(
                doc, circles, circular_id, base_id, top_id)
        elif circles:
            _say("  circular columns skipped: no circular family selected")
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Column creation failed", "Column creation failed.", str(creation_error))
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 1}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Columns", tstatus, gstatus)
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0, "rolled_back": True}

    _say("Columns -- rect created: {0}, circular: {1}, skipped: {2}, errors: {3}".format(
        len(result["created"]), len(circular["created"]),
        len(result["skipped"]), len(result["errors"]) + len(circular["errors"])))
    for message in result["errors"] + circular["errors"] + result["skipped"]:
        _say("  column: {0}".format(message))
    return {"rect": len(result["created"]), "circular": len(circular["created"]),
            "skipped": len(result["skipped"]),
            "errors": len(result["errors"]) + len(circular["errors"])}


def _create_beams(doc, beam_segments, selections):
    """Place beams along derived centerlines at the columns' top level, in a group."""
    from Autodesk.Revit.DB import Transaction, TransactionGroup, TransactionStatus
    beam_id = selections.get("beam_family_id")
    level_id = selections.get("top_level_id")
    if beam_id is None or level_id is None:
        _alert("Beams skipped", "Choose a beam family and a top level.")
        return {"created": 0, "skipped": 0, "errors": 0}
    segments = beam_segments.get("segments", [])
    curved = beam_segments.get("curved_segments", [])
    if not segments and not curved:
        _say("Beams -- no beam segments to place.")
        return {"created": 0, "skipped": 0, "errors": 0}

    group = TransactionGroup(doc, "CAD to BIM: Beams")
    transaction = Transaction(doc, "Create beams")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = beams.place_beams(doc, segments, beam_id, level_id)
        # Curved beams (concentric arc pairs, e.g. a curved perimeter member) are placed
        # along an Arc; fold their outcome into the same result tallies.
        curved_result = beams.place_curved_beams(doc, curved, beam_id, level_id)
        for key in ("created", "skipped", "errors"):
            result[key] = result[key] + curved_result[key]
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Beam creation failed", "Beam creation failed.", str(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Beams", tstatus, gstatus)
        return {"created": 0, "skipped": 0, "errors": 0, "rolled_back": True}

    _say("Beams -- created: {0}, skipped: {1}, errors: {2}".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    for message in result["errors"] + result["skipped"]:
        _say("  beam: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"])}


def _create_slabs(doc, records, beam_segments, texts, selections, schedule=None,
                  column_rects=None):
    """Place floor slabs after the beams, in a transaction group.

    Outline sources, in order: (1) closed rings on the slab-edge (A-FLOR) layer;
    (2) faces of the PLACED beam edge lines with the placed column footprints
    trimming the corners (exact boundary, re-derived onto the carrier lines).
    Thickness and mark come from slab notes ("S1 150 THK", "150 THK.") lying
    INSIDE the loop -- content-driven, any text layer. The floor type is the one
    picked in the window, duplicated per thickness; the level is the beams' level.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup
    level_id = selections.get("top_level_id")
    if level_id is None:
        _say("Slabs -- skipped (no top level chosen).")
        return {"created": 0, "skipped": 0, "errors": 0}
    base_type_id = selections.get("floor_type_id")
    if base_type_id is None:
        _say("Slabs -- skipped (no floor type chosen).")
        return {"created": 0, "skipped": 0, "errors": 0}
    # Outline source chain (user directive: these TWO only): (1) slab-edge layer
    # rings as drawn; (2) faces of the PLACED geometry -- the placed beams' edge
    # lines form the boundary, and the column footprint rings inside it trim the
    # corners. The beams are placed aligned, so the slab edges align with them by
    # construction; the drawn-linework fallbacks are retired.
    loops = slab_outlines.slab_loops_from_edges(records)
    source = "slab_edges"
    if not loops:
        # Column trimming is back ON (the 0.45.1 beam-edges-only isolation proved
        # the misalignment lived in the trim interaction): the exactness pass now
        # picks each vertex's carriers by RING-EDGE DIRECTION, so a diamond
        # column's 45-degree edges can no longer out-crowd the beam edge and weld
        # a long boundary onto the column apex.
        loops = slab_outlines.slab_loops_from_placed_members(
            records, beam_segments.get("segments"), column_rects=column_rects)
        source = "placed_members"
    if not loops:
        _say("Slabs -- no closed slab outline found (any source).")
        return {"created": 0, "skipped": 0, "errors": 0, "source": source}
    slab_schedule = {m: v for m, v in (schedule or {}).items()
                     if str(m)[:1].upper() == "S" and str(m)[1:2].isdigit()}
    slab_defs = slab_outlines.apply_slab_labels(loops, texts, schedule=slab_schedule)

    group = TransactionGroup(doc, "CAD to BIM: Slabs")
    transaction = Transaction(doc, "Create slabs")
    group.Start()
    transaction.Start()
    try:
        txn_failures.attach_warning_swallower(transaction)
        result = slabs.place_slabs(doc, slab_defs, base_type_id, level_id)
        tstatus = transaction.Commit()
        gstatus = group.Assimilate()
    except Exception as creation_error:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        _error("Slab creation failed", "Slab creation failed.", str(creation_error))
        return {"created": 0, "skipped": 0, "errors": 1, "source": source}

    if not _persisted(tstatus, gstatus):
        _rollback_alert("Slabs", tstatus, gstatus)
        return {"created": 0, "skipped": 0, "errors": 0, "rolled_back": True,
                "source": source}

    sized = sum(1 for sd in slab_defs if sd.get("thickness_mm") is not None)
    _say("Slabs -- source: {0}, loops: {1}, thickness-noted: {2}, "
         "created: {3}, skipped: {4}, errors: {5}".format(
             source, len(slab_defs), sized, len(result["created"]),
             len(result["skipped"]), len(result["errors"])))
    for message in result["errors"] + result["skipped"]:
        _say("  slab: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"]), "source": source, "loops": len(slab_defs),
            "error_details": [str(e)[:220] for e in result["errors"][:8]],
            "skip_details": [str(e)[:120] for e in result["skipped"][:8]]}


class _CurveElementFilter(object):
    """Selection filter: only the lines the user drew (detail or model).

    `__namespace__` is required by Python.NET 3 to build a real derived CLR
    type from the ISelectionFilter interface -- without it the constructor
    routes to the interface cast and raises "takes exactly one argument".
    """

    __namespace__ = "CadToBim"

    def AllowElement(self, element):
        from Autodesk.Revit.DB import CurveElement
        return isinstance(element, CurveElement)

    def AllowReference(self, reference, point):
        return False


def _draw_stair_outlines(doc):
    """Let the user DRAW one closed outline per stair, snapped, in the view.

    Revit will not run its own Detail Line command while a modal window is up,
    and the API cannot resume a posted command, so the outline is drawn here:
    PickPoint uses Revit's real snapping (to the CAD link and to the model), a
    detail line is created after every second point so the shape is visible as
    it grows, and Escape closes the current outline. Escape on the first point
    of a new outline ends the session. Returns [ring, ...] in internal feet.
    """
    from Autodesk.Revit.DB import Line, Transaction, XYZ
    from Autodesk.Revit.UI.Selection import ObjectSnapTypes

    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None:
        return []
    view = uidoc.ActiveView
    snaps = (ObjectSnapTypes.Endpoints | ObjectSnapTypes.Intersections
             | ObjectSnapTypes.Midpoints | ObjectSnapTypes.Nearest
             | ObjectSnapTypes.Perpendicular | ObjectSnapTypes.WorkPlaneGrid)
    rings = []
    while True:
        points = []
        while True:
            prompt = ("Stair outline {0}: click a corner (Esc closes this "
                      "outline)".format(len(rings) + 1) if points else
                      "Stair outline {0}: click the first corner (Esc when "
                      "all stairs are drawn)".format(len(rings) + 1))
            try:
                picked = uidoc.Selection.PickPoint(snaps, prompt)
            except Exception:
                picked = None
            if picked is None:
                break
            points.append(picked)
            if len(points) >= 2:
                transaction = Transaction(doc, "Stair outline")
                try:
                    transaction.Start()
                    txn_failures.attach_warning_swallower(transaction)
                    doc.Create.NewDetailCurve(
                        view, Line.CreateBound(points[-2], points[-1]))
                    transaction.Commit()
                except Exception:
                    if transaction.HasStarted() and not transaction.HasEnded():
                        transaction.RollBack()
        if len(points) < 3:
            break                       # Escape on an empty/short outline: done
        transaction = Transaction(doc, "Stair outline close")
        try:                            # close the loop back to the first point
            transaction.Start()
            txn_failures.attach_warning_swallower(transaction)
            doc.Create.NewDetailCurve(
                view, Line.CreateBound(points[-1], points[0]))
            transaction.Commit()
        except Exception:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        ring = slab_outlines._dedup_ring([(p.X, p.Y) for p in points])
        if len(ring) >= 3:
            rings.append(ring)
            area_m2 = abs(slab_outlines._signed_area(ring)) * 304.8 * 304.8 / 1e6
            _say("Stairs -- outline {0}: {1} corners, {2:.1f} m2".format(
                len(rings), len(ring), area_m2))
    return rings


def _pick_stair_regions():
    """Stair outlines taken from DETAIL LINES already drawn in the view.

    A drag-box is only as accurate as the drag; a detail line snaps to the CAD
    link and to the model, so the boundary is exact and can be any shape. The
    picked curves are chained end-to-end into closed rings (arcs tessellated),
    one ring per stair. Returns [ring, ...] in internal feet.
    """
    from Autodesk.Revit.UI.Selection import ObjectType
    from Autodesk.Revit.DB import Line

    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None:
        return []
    try:
        picked = uidoc.Selection.PickObjects(
            ObjectType.Element, _wrap_selection_filter(),
            "Select the detail lines outlining each stair, then click Finish")
    except Exception:
        return []                       # Escape / cancelled
    pieces = []
    for reference in picked or []:
        element = uidoc.Document.GetElement(reference.ElementId)
        curve = getattr(element, "GeometryCurve", None)
        if curve is None:
            continue
        if isinstance(curve, Line):
            points = [curve.GetEndPoint(0), curve.GetEndPoint(1)]
        else:                           # arc / spline: sample it
            try:
                points = list(curve.Tessellate())
            except Exception:
                points = [curve.GetEndPoint(0), curve.GetEndPoint(1)]
        flat = [(p.X, p.Y) for p in points]
        if len(flat) >= 2:
            pieces.append((flat, points[0].Z))
    if not pieces:
        _say("Stairs -- no detail lines picked.")
        return []

    tol_ft = config.mm_to_ft(_STAIR_LINE_CHAIN_MM)
    rings = []
    for ring, _z in slab_outlines._chain_into_rings(pieces, tol_ft):
        ring = slab_outlines._dedup_ring(ring)
        if len(ring) >= 3:
            rings.append(ring)
    if not rings:
        _say("Stairs -- the picked lines do not close into an outline "
             "(ends must meet within {0:.0f} mm).".format(_STAIR_LINE_CHAIN_MM))
        return []
    for index, ring in enumerate(rings, start=1):
        area_m2 = abs(slab_outlines._signed_area(ring)) * 304.8 * 304.8 / 1e6
        _say("Stairs -- outline {0}: {1} corners, {2:.1f} m2".format(
            index, len(ring), area_m2))
    return rings


def _wrap_selection_filter():
    """The CLR-derived ISelectionFilter instance (built lazily so the module
    imports outside Revit)."""
    from Autodesk.Revit.UI.Selection import ISelectionFilter

    class _Filter(ISelectionFilter, _CurveElementFilter):
        __namespace__ = "CadToBim"

    return _Filter()


def _create_stairs(doc, records, beam_segments, texts, selections,
                   column_rects=None):
    """Place generic dog-leg staircases at the plan's STAIRCASE / ST-n texts.

    Option 1 (no stair linework): the bay containing the text is the stair's
    area (placed-members faces with the shaft filter relaxed); riser count,
    tread, run width and landing come from the Staircase tab plus the base-to-
    top storey height. The builder runs its own StairsEditScope per stair --
    NO outer transaction group here (Revit forbids nesting an edit scope).
    """
    base_id = selections.get("base_level_id")
    top_id = selections.get("top_level_id")
    if base_id is None or top_id is None:
        _say("Stairs -- skipped (base and top levels are both required).")
        return {"created": 0, "skipped": 0, "errors": 0}
    base_level = doc.GetElement(base_id)
    top_level = doc.GetElement(top_id)
    storey_mm = (top_level.Elevation - base_level.Elevation) * 304.8
    if storey_mm <= 0:
        _say("Stairs -- skipped (top level is not above the base level).")
        return {"created": 0, "skipped": 0, "errors": 0}

    source = selections.get("stair_source") or "auto"
    regions = list(selections.get("stair_regions") or []) or None
    if regions:
        # outlines the user drew from the Staircase tab win over any source
        source = "region"
    elif source == "region":
        regions = _pick_stair_regions()
        if not regions:
            _say("Stairs -- skipped (no closed outline picked in the view).")
            return {"created": 0, "skipped": 0, "errors": 0}
    plans, notes = stair_layout.plan_stairs(
        records, (beam_segments or {}).get("segments"), column_rects, texts,
        selections.get("stair_params") or {}, storey_mm,
        source=source, regions=regions)
    for note in notes:
        _say("  stair: {0}".format(note))
    if not plans:
        _say("Stairs -- no staircase planned (see notes above).")
        return {"created": 0, "skipped": len(notes), "errors": 0}

    result = stairs.place_stairs(doc, plans, base_id, top_id,
                                 base_type_id=selections.get("stair_type_id"))
    _say("Stairs -- source: {0}, planned: {1}, created: {2}, skipped: {3}, "
         "errors: {4} (storey {5} mm, {6} risers @ {7:.1f} mm)".format(
             plans[0].get("source") or "stair_text", len(plans),
             len(result["created"]), len(result["skipped"]),
             len(result["errors"]), int(storey_mm), plans[0]["risers_total"],
             plans[0]["riser_mm"]))
    for message in result["errors"] + result["skipped"]:
        _say("  stair: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"]), "planned": len(plans),
            "notes": notes[:8],
            "error_details": [str(e)[:220] for e in result["errors"][:8]]}


def _export_name(cad_path, selections, storey_label=None):
    """Default export file name (user convention):
    [version]_[main element]_[testN from the CAD name]_[textmode].json
    e.g. "0.44.0_slab_test1_with_textmode.json"."""
    element = ("stair" if selections.get("create_stairs")
               else "slab" if selections.get("create_slabs")
               else "beam" if selections.get("create_beams")
               else "column" if selections.get("create_columns")
               else "grid")
    stem = os.path.splitext(os.path.basename(cad_path or ""))[0]
    m = re.search(r"(test|project)\s*-?_?(\d+)", stem, re.IGNORECASE)
    plan = "{0}{1}".format(m.group(1).lower(), m.group(2)) if m else (stem or "plan")
    text_mapping = selections.get("text_mapping") or {}
    routed = any(cat and cat != layers.CATEGORY_TEXT_IGNORE
                 for cat in text_mapping.values())
    mode = "with_textmode" if routed else "no_text"
    if storey_label:
        plan = "{0}-{1}".format(plan, re.sub(r"[^a-z0-9]+", "",
                                             storey_label.lower())[:12])
    return "{0}_{1}_{2}_{3}.json".format(cad2bim.__version__, element, plan, mode)


def _export_storeys(storey_payloads, source_name, default_name):
    """Write ONE JSON for a multi-storey run -- a section per storey."""
    target = _save_json(default_name)
    if not target:
        return
    try:
        report.export_storeys_json(target, storey_payloads,
                                   source_name=source_name)
        _say("Exported JSON ({0} storeys in one file) -> {1}".format(
            len(storey_payloads), target))
    except (IOError, OSError) as write_error:
        _error("JSON export failed", "Could not write the JSON file.",
               str(write_error))


def _export(read_result, mapping, sections, beam_segments, outcomes, texts, comparison,
            default_name="cad_to_bim_read.json"):
    """Write the intermediate JSON (the user opted in via the window)."""
    target = _save_json(default_name)
    if not target:
        return
    try:
        report.export_json(target, read_result, mapping, sections, beam_segments,
                           outcomes, texts=texts, comparison=comparison)
        _say("Exported JSON (with report) -> {0}".format(target))
    except (IOError, OSError) as write_error:
        _error("JSON export failed", "Could not write the JSON file.", str(write_error))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _error("Unexpected error",
               "An unexpected error occurred. The CPython3 engine is still running "
               "-- you do not need to restart Revit.", traceback.format_exc())
        _OUT.finish()

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

The cad2bim package lives in lib/py3; path_resolver injects it. If the banner's
version/path is not what you expect, a stale shadow copy is on sys.path.
"""

__title__ = "CAD to BIM"
__author__ = "AnonGee"
__min_revit_ver__ = 2022

import os
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
                            Thickness, GridLength, GridUnitType, VerticalAlignment)
from System.Windows.Controls import (Grid as WpfGrid, ColumnDefinition, TextBlock,
                                     ComboBox)
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

import cad2bim
from cad2bim import (compat, geometry_reader, layers, report, grids,
                     transactions, columns, beams, dxf_linker, dxf_reader,
                     transform, compare, marks, config)

_HERE = os.path.dirname(os.path.abspath(__file__))
_XAML = os.path.join(_HERE, "ui.xaml")
_LINK_XAML = os.path.join(_HERE, "link_options.xaml")

# A size label within this distance of a member refines it; also the proximity the
# comparison uses to decide "this is the same member" (~half a column).
_COMPARE_TOL_FT = 300.0 / 304.8


# --- dialogs / messaging (System.Windows only -- no pyRevit) -----------------

def _alert(title, message):
    MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Warning)


def _error(title, message, detail=None):
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
    print(message)
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
                 column_symbols, level_options, beam_symbols,
                 text_layer_rows=None, text_categories=None, default_text_mapping=None):
        self.result = None
        self._combos = []
        self._text_combos = []
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

        self.chk_grids = find("chk_grids")
        self.chk_columns = find("chk_columns")
        self.chk_beams = find("chk_beams")
        self.chk_slabs = find("chk_slabs")
        self.chk_export = find("chk_export")

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
        self.tb_snap = find("tb_snap")
        self.tb_markrad = find("tb_markrad")
        self.tb_compare = find("tb_compare")
        self.tb_region = find("tb_region")
        self.tb_circ_min = find("tb_circ_min")
        self.tb_circ_max = find("tb_circ_max")
        self.tb_pair_min = find("tb_pair_min")
        self.tb_pair_max = find("tb_pair_max")
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
            row.Margin = Thickness(0, 2, 0, 2)
            for width in (None, 70, 150):   # None -> star column
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
        }

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
        self.result = {
            "mapping": mapping,
            "text_mapping": text_mapping,
            "create_grids": bool(self.chk_grids.IsChecked),
            "create_columns": bool(self.chk_columns.IsChecked),
            "create_beams": bool(self.chk_beams.IsChecked),
            "column_family_id": self._family_ids.get(self.cb_family.SelectedItem),
            "circular_family_id": self._family_ids.get(self.cb_circular_family.SelectedItem),
            "beam_family_id": self._beam_ids.get(self.cb_beam_family.SelectedItem),
            "base_level_id": self._level_ids.get(self.cb_base_level.SelectedItem),
            "top_level_id": self._level_ids.get(self.cb_top_level.SelectedItem),
            "export": bool(self.chk_export.IsChecked),
            "limits": self._read_limits(),
            "tolerances": self._read_tolerances(),
            "standards": {
                "column": report.parse_standard_sizes(self.tb_std_columns.Text),
                "beam_widths": report.parse_standard_widths(self.tb_std_beams.Text),
            },
        }
        self.window.Close()

    def on_cancel(self, sender, args):
        self.result = None
        self.window.Close()

    def show(self):
        self.window.ShowDialog()


def _layer_names(records):
    """Distinct layer keys present in a record list, sorted for stable display."""
    return sorted(set(r.layer_key for r in records))


def main():
    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None or uidoc.Document is None:
        _alert("No document", "Open a Revit project before running CAD to BIM.")
        return
    doc = uidoc.Document

    module_dir = os.path.dirname(os.path.abspath(report.__file__))
    print("cad2bim {0} loaded from {1}".format(cad2bim.__version__, module_dir))
    print(compat.runtime_summary())
    try:
        print("Host: Revit {0}".format(__revit__.Application.VersionNumber))
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
    try:
        instance = dxf_linker.link_dxf(doc, path, options.result["unit"],
                                       options.result["placement"],
                                       this_view_only=options.result["this_view_only"])
    except Exception:
        _error("Link failed", "Could not link the DXF.", traceback.format_exc())
        return

    # 2. Hybrid read: Revit link geometry is the BUILD source (already in Revit
    #    coordinates and pre-merged into polylines). The DXF (ezdxf) supplies TEXT
    #    only, mapped into Revit coordinates by the link's own exact transform.
    revit_result = geometry_reader.read_link(doc, instance)
    if revit_result.is_empty():
        _alert("Empty link", "The linked DXF produced no readable geometry in "
               "Revit. Check the link is visible in the active view.")
        return
    try:
        dxf_result = dxf_reader.read_dxf(path)
    except Exception:
        _error("DXF read failed", "Could not read the DXF for text.", traceback.format_exc())
        return

    # Map DXF coords -> Revit feet using the GRID lines as anchors: they are the
    # same lines in both the Revit and DXF extractions, so aligning their bounding
    # boxes is exact (no symbol-space unit guessing). Fall back to the link's own
    # transform only if no grid geometry is available.
    rev_grids = [r for r in revit_result.records
                 if layers.classify_layer(r.layer_key) == layers.CATEGORY_GRID]
    dxf_grids = [r for r in dxf_result.records
                 if layers.classify_layer(r.layer_key) == layers.CATEGORY_GRID]
    rev_bbox = transform.bbox_of_records(rev_grids)
    dxf_bbox = transform.bbox_of_records(dxf_grids)
    if rev_bbox and dxf_bbox:
        text_affine = transform.empirical_affine(dxf_bbox, rev_bbox)
        transform_method = "grid_anchored"
    else:
        text_affine = transform.from_link(instance)
        transform_method = "link_GetTotalTransform"
    transform.apply_to_texts(text_affine, dxf_result.texts)
    marks.parse_texts(dxf_result.texts)
    # Map a copy of the DXF geometry the same way, only to report problem geometry.
    transform.apply_to_records(text_affine, dxf_result.records)

    # Build the window from the REVIT records (the build source); no API calls.
    layer_counts = report.build_layer_counts(revit_result.records)
    names = _layer_names(revit_result.records)
    layer_rows = [(name, layer_counts.get(name, {}).get("count", 0)) for name in names]
    default_mapping = layers.build_default_mapping(names)
    column_symbols = columns.structural_column_symbols(doc)
    level_options = columns.levels(doc)
    beam_symbols = beams.structural_framing_symbols(doc)

    # Text layers (size marks) come from the DXF, routed separately from geometry.
    text_layer_counts = {}
    for text in dxf_result.texts:
        text_layer_counts[text.layer_key] = text_layer_counts.get(text.layer_key, 0) + 1
    text_names = sorted(text_layer_counts.keys())
    text_layer_rows = [(name, text_layer_counts[name]) for name in text_names]
    default_text_mapping = layers.build_default_text_mapping(text_names)

    window = CadToBimWindow(dxf_result.source_name, layer_rows,
                            list(layers.ALL_CATEGORIES), default_mapping,
                            column_symbols, level_options, beam_symbols,
                            text_layer_rows, list(layers.TEXT_CATEGORIES),
                            default_text_mapping)
    window.show()
    if not window.result:
        return

    selections = window.result
    layers.apply_mapping(revit_result.records, selections["mapping"])
    limits = selections.get("limits")
    standards = selections.get("standards")
    tolerances = selections.get("tolerances") or {}

    # Diagnostic only: how much Revit's import dropped/clipped vs the raw DXF.
    compare_tol_ft = config.mm_to_ft(tolerances.get("compare_tol_mm",
                                                    config.DEFAULTS["compare_tol_mm"]))
    comparison = compare.diff(revit_result.records, dxf_result.records, compare_tol_ft)
    comparison["transform"] = {"method": transform_method}

    sections = report.build_column_sections(revit_result.records, limits, standards,
                                            texts=None, tolerances=tolerances)
    beam_segments = report.build_beam_segments(revit_result.records,
                                               sections.get("circles"),
                                               limits, standards,
                                               texts=None, tolerances=tolerances)

    # Layer-routed text correction: column-text labels (one per real column) resize
    # clipped columns (G9) and merge grid-crossing-split pieces (E9) into one.
    text_mapping = selections.get("text_mapping") or {}
    column_texts = [t for t in dxf_result.texts
                    if text_mapping.get(t.layer_key) == layers.CATEGORY_COLUMN_TEXT]
    mark_radius_ft = config.mm_to_ft(tolerances.get("mark_radius_mm",
                                                    config.DEFAULTS["mark_radius_mm"]))
    fixed = report.correct_columns_with_text(sections, column_texts, mark_radius_ft)
    if fixed:
        print("columns: text-corrected {0} (clipped/merged from size labels)".format(fixed))

    print("### CAD to BIM {0}".format(cad2bim.__version__))
    for line in compare.format_console(comparison):
        print(line)
    for line in report.format_console(revit_result, selections["mapping"],
                                      sections, beam_segments):
        print(line)

    outcomes = {}
    if selections["create_grids"]:
        outcomes["grids"] = _create_grids(doc, revit_result.records)
    if selections["create_columns"]:
        outcomes["columns"] = _create_columns(doc, sections, selections)
    if selections["create_beams"]:
        outcomes["beams"] = _create_beams(doc, beam_segments, selections)
    if selections["export"]:
        _export(revit_result, selections["mapping"], sections, beam_segments,
                outcomes, dxf_result.texts, comparison)


def _create_grids(doc, records):
    """Create grids from classified grid lines, inside a transaction group.

    All Revit writes happen here on the Revit API thread after the window closes.
    Both the inner transaction and the group roll back on any failure.
    """
    from Autodesk.Revit.DB import Transaction, TransactionGroup, TransactionStatus
    grid_records = [r for r in records
                    if r.category == layers.CATEGORY_GRID and r.kind in ("line", "arc")]
    if not grid_records:
        print("Grids -- no grid-category lines to create.")
        return {"created": 0, "skipped": 0, "errors": 0}

    namer = grids.GridNamer(grid_records)
    group = TransactionGroup(doc, "CAD to BIM: Grids")
    transaction = Transaction(doc, "Create grids")
    group.Start()
    transaction.Start()
    try:
        transactions.attach_warning_swallower(transaction)
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

    print("Grids -- created: {0}, skipped: {1}, errors: {2}".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    for message in result["errors"]:
        print("  grid: {0}".format(message))
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
        print("Columns -- no column sections to place.")
        return {"rect": 0, "circular": 0, "skipped": 0, "errors": 0}

    group = TransactionGroup(doc, "CAD to BIM: Columns")
    transaction = Transaction(doc, "Create columns")
    region_max = (selections.get("tolerances") or {}).get("col_region_max_side_mm")
    group.Start()
    transaction.Start()
    try:
        transactions.attach_warning_swallower(transaction)
        result = columns.place_columns(doc, sections, family_id, base_id, top_id,
                                       region_max_side_mm=region_max)
        circles = sections.get("circles", [])
        circular_id = selections.get("circular_family_id")
        circular = {"created": [], "errors": []}
        if circles and circular_id is not None:
            circular = columns.place_circular_columns(
                doc, circles, circular_id, base_id, top_id)
        elif circles:
            print("  circular columns skipped: no circular family selected")
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

    print("Columns -- rect created: {0}, circular: {1}, skipped: {2}, errors: {3}".format(
        len(result["created"]), len(circular["created"]),
        len(result["skipped"]), len(result["errors"]) + len(circular["errors"])))
    for message in result["errors"] + circular["errors"] + result["skipped"]:
        print("  column: {0}".format(message))
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
    if not segments:
        print("Beams -- no beam segments to place.")
        return {"created": 0, "skipped": 0, "errors": 0}

    group = TransactionGroup(doc, "CAD to BIM: Beams")
    transaction = Transaction(doc, "Create beams")
    group.Start()
    transaction.Start()
    try:
        transactions.attach_warning_swallower(transaction)
        result = beams.place_beams(doc, segments, beam_id, level_id)
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

    print("Beams -- created: {0}, skipped: {1}, errors: {2}".format(
        len(result["created"]), len(result["skipped"]), len(result["errors"])))
    for message in result["errors"] + result["skipped"]:
        print("  beam: {0}".format(message))
    return {"created": len(result["created"]), "skipped": len(result["skipped"]),
            "errors": len(result["errors"])}


def _export(read_result, mapping, sections, beam_segments, outcomes, texts, comparison):
    """Write the intermediate JSON (the user opted in via the window)."""
    target = _save_json("cad_to_bim_read.json")
    if not target:
        return
    try:
        report.export_json(target, read_result, mapping, sections, beam_segments,
                           outcomes, texts=texts, comparison=comparison)
        print("Exported JSON (with report) -> {0}".format(target))
    except (IOError, OSError) as write_error:
        _error("JSON export failed", "Could not write the JSON file.", str(write_error))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _error("Unexpected error",
               "An unexpected error occurred. The CPython3 engine is still running "
               "-- you do not need to restart Revit.", traceback.format_exc())

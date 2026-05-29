# -*- coding: utf-8 -*-
"""
ui/main_window.py
Full WPF event logic for BBS Generator.
"""

import sys
import os
import datetime
import json
import traceback

_TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in [
    _TOOL_ROOT,
    os.path.join(_TOOL_ROOT, "core"),
    os.path.join(_TOOL_ROOT, "standards"),
    os.path.join(_TOOL_ROOT, "output"),
    os.path.join(_TOOL_ROOT, "ui"),
    os.path.join(_TOOL_ROOT, "ui", "xaml"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

import System
import System.Windows
from System.Windows.Markup import XamlReader
from System.IO import MemoryStream
from System.Text import Encoding
from System.Windows.Controls import CheckBox
from System.Collections import ArrayList

from bbs_window import MAIN_XAML, PARAM_EDITOR_XAML
import standards as std_pkg
from rebar_reader import read_bars, get_all_levels, get_all_member_types, get_rebar_diameters
from revision_tracker import (
    load_previous_revision, save_revision,
    compare_revisions, build_diff_summary,
    CHANGE_NEW, CHANGE_CHANGED, CHANGE_DELETED,
)
from excel_writer import write_bbs_workbook
from pdf_exporter import export_pdf

from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory

class BarVM:
    __slots__ = [
        "bar_mark", "member_name", "member_type", "floor_level",
        "diameter_mm", "shape_code", "no_of_bars",
        "cutting_length_mm", "total_weight_kg", "bar_type_name", "bar_detail",
        "dim_A", "dim_B", "dim_C"
    ]
    def __init__(self, r):
        self.bar_mark          = r.bar_mark
        self.member_name       = r.member_name
        self.member_type       = r.member_type
        self.floor_level       = r.floor_level
        self.diameter_mm       = r.diameter_mm
        self.shape_code        = r.shape_code
        self.no_of_bars        = r.no_of_bars
        self.cutting_length_mm = r.cutting_length_mm
        self.total_weight_kg   = round(r.total_weight_kg, 3)
        self.bar_type_name     = r.bar_type_name
        self.bar_detail        = r.bar_detail
        self.dim_A             = r.dimensions.get("A", "")
        self.dim_B             = r.dimensions.get("B", "")
        self.dim_C             = r.dimensions.get("C", "")

class DiaVM:
    __slots__ = ["dia_label", "no_bars", "total_len_m", "total_wt_kg"]
    def __init__(self, dia, no_bars, total_len_m, total_wt_kg):
        self.dia_label   = f"T{dia}"
        self.no_bars     = no_bars
        self.total_len_m = round(total_len_m, 2)
        self.total_wt_kg = round(total_wt_kg, 3)

def _get_all_rebar_params(doc):
    """Extracts all parameter names from a sample rebar in the model."""
    rebars = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rebar).WhereElementIsNotElementType().ToElements()
    params = set()
    for r in rebars:
        if r.GetType().Name == "Rebar":
            for p in r.Parameters:
                params.add(p.Definition.Name)
            break
    return sorted(list(params))

def open_param_editor(owner_window, title, tb_control, doc):
    """Opens the Parameter Editor Popup."""
    stream = MemoryStream(Encoding.UTF8.GetBytes(PARAM_EDITOR_XAML))
    popup = XamlReader.Load(stream)
    popup.Owner = owner_window
    popup.Title = f"Edit {title}"
    
    cb_available = popup.FindName("cb_available")
    btn_add      = popup.FindName("btn_add")
    lst_params   = popup.FindName("lst_params")
    btn_up       = popup.FindName("btn_up")
    btn_down     = popup.FindName("btn_down")
    btn_del      = popup.FindName("btn_del")
    btn_save     = popup.FindName("btn_save")
    
    for p in _get_all_rebar_params(doc): cb_available.Items.Add(p)
        
    current_items = [x.strip() for x in tb_control.Text.split(",") if x.strip()]
    for item in current_items: lst_params.Items.Add(item)
        
    def on_add(s, a):
        val = cb_available.Text.strip()
        if val and val not in lst_params.Items:
            lst_params.Items.Add(val)
            cb_available.Text = ""
    btn_add.Click += on_add
    
    def on_del(s, a):
        idx = lst_params.SelectedIndex
        if idx >= 0: lst_params.Items.RemoveAt(idx)
    btn_del.Click += on_del
    
    def on_up(s, a):
        idx = lst_params.SelectedIndex
        if idx > 0:
            item = lst_params.Items[idx]
            lst_params.Items.RemoveAt(idx)
            lst_params.Items.Insert(idx - 1, item)
            lst_params.SelectedIndex = idx - 1
    btn_up.Click += on_up
    
    def on_down(s, a):
        idx = lst_params.SelectedIndex
        if idx >= 0 and idx < lst_params.Items.Count - 1:
            item = lst_params.Items[idx]
            lst_params.Items.RemoveAt(idx)
            lst_params.Items.Insert(idx + 1, item)
            lst_params.SelectedIndex = idx + 1
    btn_down.Click += on_down
    
    def on_save(s, a):
        items = []
        for i in range(lst_params.Items.Count): items.append(lst_params.Items[i])
        tb_control.Text = ", ".join(items)
        popup.Close()
    btn_save.Click += on_save
    
    popup.ShowDialog()

def run_ui(doc, uidoc):
    xaml_bytes = Encoding.UTF8.GetBytes(MAIN_XAML)
    stream     = MemoryStream(xaml_bytes)
    window     = XamlReader.Load(stream)

    def W(name):
        ctrl = window.FindName(name)
        if ctrl is None: raise RuntimeError(f"XAML control not found: {name!r}")
        return ctrl

    lbl_bar_count      = W("lbl_bar_count")
    lbl_standard_badge = W("lbl_standard_badge")
    cb_standard        = W("cb_standard")
    
    tb_param_mark      = W("tb_param_mark")
    tb_param_type      = W("tb_param_type")
    tb_param_level     = W("tb_param_level")
    tb_param_length    = W("tb_param_length")
    tb_param_qty       = W("tb_param_qty")
    tb_param_shape     = W("tb_param_shape")
    tb_param_member    = W("tb_param_member")
    tb_param_detail    = W("tb_param_detail")

    W("btn_edit_mark").Click   += lambda s,a: open_param_editor(window, "Bar Mark Params", tb_param_mark, doc)
    W("btn_edit_type").Click   += lambda s,a: open_param_editor(window, "Bar Type Params", tb_param_type, doc)
    W("btn_edit_level").Click  += lambda s,a: open_param_editor(window, "Level Params", tb_param_level, doc)
    W("btn_edit_length").Click += lambda s,a: open_param_editor(window, "Length Params", tb_param_length, doc)
    W("btn_edit_qty").Click    += lambda s,a: open_param_editor(window, "Quantity Params", tb_param_qty, doc)
    W("btn_edit_shape").Click  += lambda s,a: open_param_editor(window, "Shape Params", tb_param_shape, doc)
    W("btn_edit_member").Click += lambda s,a: open_param_editor(window, "Member Params", tb_param_member, doc)
    W("btn_edit_detail").Click += lambda s,a: open_param_editor(window, "Detail Params", tb_param_detail, doc)

    rb_org_floor       = W("rb_org_floor")
    rb_org_elem        = W("rb_org_elem")
    rb_org_both        = W("rb_org_both")
    chk_bbs_sheet      = W("chk_bbs_sheet")
    chk_calc_sheet     = W("chk_calc_sheet")
    chk_summary_sheet  = W("chk_summary_sheet")
    chk_unit_weight    = W("chk_unit_weight")
    chk_pdf            = W("chk_pdf")
    chk_revision       = W("chk_revision")
    tb_prev_bbs        = W("tb_prev_bbs")
    btn_browse_prev    = W("btn_browse_prev")
    lbl_rev_status     = W("lbl_rev_status")
    tb_project_name    = W("tb_project_name")
    tb_drawing_no      = W("tb_drawing_no")
    tb_prepared_by     = W("tb_prepared_by")
    tb_revision        = W("tb_revision")
    btn_save_settings  = W("btn_save_settings")
    rb_scope_model     = W("rb_scope_model")
    rb_scope_view      = W("rb_scope_view")
    rb_scope_selection = W("rb_scope_selection")
    
    level_filter_panel  = W("level_filter_panel")
    member_filter_panel = W("member_filter_panel")
    dia_filter_panel    = W("dia_filter_panel")
    
    preview_grid       = W("preview_grid")
    badge_total_bars   = W("badge_total_bars")
    badge_total_weight = W("badge_total_weight")
    badge_warnings     = W("badge_warnings")
    btn_refresh_preview= W("btn_refresh_preview")
    tb_output_folder   = W("tb_output_folder")
    btn_browse_output  = W("btn_browse_output")
    tb_filename        = W("tb_filename")
    lbl_diff_new       = W("lbl_diff_new")
    lbl_diff_changed   = W("lbl_diff_changed")
    lbl_diff_deleted   = W("lbl_diff_deleted")
    lbl_diff_same      = W("lbl_diff_same")
    btn_export         = W("btn_export")
    lbl_export_path    = W("lbl_export_path")
    tb_log             = W("tb_log")
    btn_load_bars      = W("btn_load_bars")
    rp_total_bars      = W("rp_total_bars")
    rp_total_weight    = W("rp_total_weight")
    rp_dia_grid        = W("rp_dia_grid")
    rp_warnings        = W("rp_warnings")
    progress_bar       = W("progress_bar")
    lbl_progress       = W("lbl_progress")
    status_badge       = W("status_badge")
    status_text        = W("status_text")
    error_badge        = W("error_badge")
    error_text_ctrl    = W("error_text")
    btn_close          = W("btn_close")

    state = {
        "records":           [],
        "changes":           {},
        "dia_checkboxes":    {},
        "level_checkboxes":  {},
        "member_checkboxes": {},
    }

    _CFG_DIR = os.path.join(os.environ.get("APPDATA", ""), "pyRevit")
    _CFG_FILE = os.path.join(_CFG_DIR, "bbs_generator_config.json")
    _local_cfg = {}
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, "r") as f:
                _local_cfg = json.load(f)
    except Exception: pass

    def cfg_get(key, default=""): return _local_cfg.get(key, default)
    def cfg_set(key, value): _local_cfg[key] = value

    def _save_local_cfg():
        try:
            if not os.path.exists(_CFG_DIR): os.makedirs(_CFG_DIR)
            with open(_CFG_FILE, "w") as f:
                json.dump(_local_cfg, f, indent=4)
        except Exception: pass

    def set_status(msg, is_error=False):
        status_text.Text = msg
        if is_error:
            status_badge.Visibility = System.Windows.Visibility.Collapsed
            error_badge.Visibility  = System.Windows.Visibility.Visible
            error_text_ctrl.Text    = msg
        else:
            status_badge.Visibility = System.Windows.Visibility.Visible
            error_badge.Visibility  = System.Windows.Visibility.Collapsed
            error_text_ctrl.Text    = ""

    def log(msg):
        tb_log.Text += msg + "\n"
        tb_log.ScrollToEnd()

    def set_progress(pct, msg=""):
        progress_bar.Value = max(0, min(100, pct))
        lbl_progress.Text  = msg

    _std_options = [("IS 2502:2019", "IS"), ("BS 8666:2020", "BS"), ("ACI 318-19 / CRSI", "ACI")]
    for label, _ in _std_options: cb_standard.Items.Add(label)

    def _current_standard_key():
        idx = cb_standard.SelectedIndex
        return _std_options[idx][1] if 0 <= idx < len(_std_options) else "IS"

    def _current_standard_module():
        return std_pkg.get_standard(_current_standard_key())

    cb_standard.SelectionChanged += lambda s, a: setattr(lbl_standard_badge, "Text", _std_options[cb_standard.SelectedIndex][0] if 0 <= cb_standard.SelectedIndex < len(_std_options) else "")

    # Default param names used before load_config() populates the textboxes
    _DEFAULT_PARAMS = {
        "mark":   "Mark, Bar Mark, BarMark, Rebar Mark",
        "type":   "Bar Type, BarType, Rebar Type, Comments",
        "level":  "SCHEDULE_LEVEL_PARAM, LEVEL_V, Level",
        "length": "Length of each bar, Bar Length, Cut Length, Cutting Length, Length",
        "qty":    "Quantity, Number of Bars, NumberOfBarPositions, Rebar Quantity",
        "shape":  "Shape",
        "member": "Partition, ID_LIC, ID_V",
        "detail": "ITEM_V",
    }

    def _safe_text(ctrl, default_key):
        """Read textbox safely — returns default if control not yet populated."""
        try:
            val = ctrl.Text.strip()
            return val if val else _DEFAULT_PARAMS.get(default_key, "")
        except Exception:
            return _DEFAULT_PARAMS.get(default_key, "")

    def get_params_config():
        """Returns param name lists. Safe to call at any point including startup."""
        return {
            "mark":   [p.strip() for p in _safe_text(tb_param_mark,   "mark").split(",")   if p.strip()],
            "type":   [p.strip() for p in _safe_text(tb_param_type,   "type").split(",")   if p.strip()],
            "level":  [p.strip() for p in _safe_text(tb_param_level,  "level").split(",")  if p.strip()],
            "length": [p.strip() for p in _safe_text(tb_param_length, "length").split(",") if p.strip()],
            "qty":    [p.strip() for p in _safe_text(tb_param_qty,    "qty").split(",")    if p.strip()],
            "shape":  [p.strip() for p in _safe_text(tb_param_shape,  "shape").split(",")  if p.strip()],
            "member": [p.strip() for p in _safe_text(tb_param_member, "member").split(",") if p.strip()],
            "detail": [p.strip() for p in _safe_text(tb_param_detail, "detail").split(",") if p.strip()],
        }

    def refresh_levels():
        level_filter_panel.Children.Clear()
        state["level_checkboxes"].clear()
        try:
            levels = get_all_levels(doc, get_params_config())
            for lvl_name in levels:
                chk = CheckBox()
                chk.Content = lvl_name
                chk.IsChecked = True
                chk.Margin = System.Windows.Thickness(0, 2, 10, 2)
                chk.Cursor = System.Windows.Input.Cursors.Hand
                chk.VerticalContentAlignment = System.Windows.VerticalAlignment.Center
                level_filter_panel.Children.Add(chk)
                state["level_checkboxes"][lvl_name] = chk
        except Exception as ex:
            set_status(f"Could not load levels: {ex}", True)

    def refresh_members():
        member_filter_panel.Children.Clear()
        state["member_checkboxes"].clear()
        try:
            mtypes = get_all_member_types(doc, get_params_config())
            for m_name in mtypes:
                chk = CheckBox()
                chk.Content = m_name
                chk.IsChecked = True
                chk.Margin = System.Windows.Thickness(0, 2, 10, 2)
                chk.Cursor = System.Windows.Input.Cursors.Hand
                chk.VerticalContentAlignment = System.Windows.VerticalAlignment.Center
                member_filter_panel.Children.Add(chk)
                state["member_checkboxes"][m_name] = chk
        except Exception as ex:
            set_status(f"Could not load member types: {ex}", True)

    def refresh_diameter_filters():
        dia_filter_panel.Children.Clear()
        state["dia_checkboxes"].clear()
        try:
            dias = get_rebar_diameters(doc)
            if not dias: dias = [8, 10, 12, 16, 20, 25, 32]
            for d in dias:
                chk = CheckBox()
                chk.Content = f"T{d}"
                chk.IsChecked = True
                chk.Margin = System.Windows.Thickness(0, 2, 10, 2)
                chk.Cursor = System.Windows.Input.Cursors.Hand
                chk.VerticalContentAlignment = System.Windows.VerticalAlignment.Center
                dia_filter_panel.Children.Add(chk)
                state["dia_checkboxes"][d] = chk
        except Exception as ex:
            set_status(f"Could not load diameters: {ex}", True)

    def get_selected_levels():
        selected = [name for name, chk in state["level_checkboxes"].items() if chk.IsChecked]
        return selected if selected else None

    def get_selected_member_types():
        selected = [name for name, chk in state["member_checkboxes"].items() if chk.IsChecked]
        return selected if selected else None

    def get_selected_diameters():
        dias = [d for d, chk in state["dia_checkboxes"].items() if chk.IsChecked]
        return dias if dias else None

    def load_bars(refresh_only=False):
        set_status("Reading rebar…")
        set_progress(0, "Initialising…")
        btn_load_bars.IsEnabled = False

        try:
            std_mod = _current_standard_module()
            scope = "view" if rb_scope_view.IsChecked else "selection" if rb_scope_selection.IsChecked else "whole"
            levels = get_selected_levels()
            members = get_selected_member_types()
            dias = get_selected_diameters()
            warnings = []

            def progress_cb(current, total, msg):
                set_progress(int((current / max(total, 1)) * 100), msg)
                System.Windows.Forms.Application.DoEvents()

            records = read_bars(
                doc=doc, uidoc=uidoc, standard_module=std_mod, scope=scope,
                level_filter=levels, member_filter=members, diameter_filter=dias, 
                progress_callback=progress_cb, params_config=get_params_config()
            )

            for r in records:
                if r.shape_code == "??": warnings.append(f"⚠ {r.bar_mark} ({r.member_name}): shape unresolved")
                if r.cutting_length_mm == 0: warnings.append(f"⚠ {r.bar_mark} ({r.member_name}): cutting length = 0")

            state["records"] = records

            prev_path = tb_prev_bbs.Text.strip()
            if chk_revision.IsChecked and prev_path:
                prev_data = load_previous_revision(prev_path)
                if prev_data:
                    state["changes"] = compare_revisions(records, prev_data)
                    diff = build_diff_summary(state["changes"])
                    lbl_diff_new.Text     = f"New bars:     {diff['new']}"
                    lbl_diff_changed.Text = f"Changed bars: {diff['changed']}"
                    lbl_diff_deleted.Text = f"Deleted bars: {diff['deleted']}"
                    lbl_diff_same.Text    = f"Unchanged:    {diff['same']}"
                    lbl_rev_status.Text   = f"Revision diff loaded — {diff['new']} new, {diff['changed']} changed, {diff['deleted']} deleted"
                else:
                    lbl_rev_status.Text = "⚠ Previous BBS sidecar (.bbs_rev) not found beside that file."
            else:
                state["changes"] = {}
                lbl_diff_new.Text = lbl_diff_changed.Text = lbl_diff_deleted.Text = lbl_diff_same.Text = "—"

            _update_preview(records, warnings)
            _update_auto_filename()

            total_wt = sum(r.total_weight_kg for r in records)
            lbl_bar_count.Text = f"{len(records)} bars loaded"
            set_status(f"Loaded {len(records)} bars  |  Total weight: {total_wt:.3f} kg")
            set_progress(100, f"Done — {len(records)} bars")

        except Exception as ex:
            err_msg = traceback.format_exc()
            set_status(f"Error loading bars: {ex}", True)
            log(f"CRITICAL ERROR LOADING BARS:\n{err_msg}\n")
            set_progress(0, "Error.")
        finally:
            btn_load_bars.IsEnabled = True

    def _update_preview(records, warnings=None):
        from collections import defaultdict
        
        items = ArrayList()
        for r in records: items.Add(BarVM(r))
        preview_grid.ItemsSource = items

        total_wt = sum(r.total_weight_kg for r in records)
        badge_total_bars.Text = rp_total_bars.Text = f"{len(records)} bars"
        badge_total_weight.Text = rp_total_weight.Text = f"{total_wt:.3f} kg"
        badge_warnings.Text = f"{len(warnings or [])} warnings"

        dia_data = defaultdict(lambda: {"no_bars": 0, "len_m": 0.0, "wt_kg": 0.0})
        for r in records:
            dia_data[r.diameter_mm]["no_bars"] += r.no_of_bars
            dia_data[r.diameter_mm]["len_m"]   += r.total_length_mm / 1000.0
            dia_data[r.diameter_mm]["wt_kg"]   += r.total_weight_kg

        dia_items = ArrayList()
        for dia in sorted(dia_data.keys()):
            d = dia_data[dia]
            dia_items.Add(DiaVM(dia, d["no_bars"], d["len_m"], d["wt_kg"]))
        rp_dia_grid.ItemsSource = dia_items

        rp_warnings.Items.Clear()
        for w in (warnings or []): rp_warnings.Items.Add(w)

    def _update_auto_filename():
        proj   = tb_project_name.Text.strip() or "Project"
        std    = _current_standard_key()
        today  = datetime.date.today().strftime("%Y%m%d")
        tb_filename.Text = f"{proj}_BBS_{std}_{today}"

    def load_config():
        saved_std = cfg_get("standard", "IS 2502:2019")
        for i, (label, _) in enumerate(_std_options):
            if label == saved_std: cb_standard.SelectedIndex = i; break
        else: cb_standard.SelectedIndex = 0

        tb_param_mark.Text = cfg_get("param_mark", "Mark, Bar Mark, BarMark, Rebar Mark")
        tb_param_type.Text = cfg_get("param_type", "Bar Type, BarType, Rebar Type, Comments")
        tb_param_level.Text = cfg_get("param_level", "SCHEDULE_LEVEL_PARAM, LEVEL_V, Level")
        tb_param_length.Text = cfg_get("param_length", "Length of each bar, Bar Length, Cut Length, Cutting Length, Length")
        tb_param_qty.Text = cfg_get("param_qty", "Quantity, Number of Bars, NumberOfBarPositions, Rebar Quantity")
        tb_param_shape.Text = cfg_get("param_shape", "Shape")
        tb_param_member.Text = cfg_get("param_member", "Partition, ID_LIC, ID_V")
        tb_param_detail.Text = cfg_get("param_detail", "ITEM_V")

        chk_unit_weight.IsChecked   = cfg_get("show_unit_weight", False)
        chk_pdf.IsChecked           = cfg_get("export_pdf",       False)
        chk_revision.IsChecked      = cfg_get("revision_track",   True)
        chk_calc_sheet.IsChecked    = cfg_get("calc_sheet",       True)
        chk_summary_sheet.IsChecked = cfg_get("summary_sheet",    True)
        chk_bbs_sheet.IsChecked     = cfg_get("bbs_sheet",        True)

        tb_project_name.Text = cfg_get("project_name", "")
        tb_drawing_no.Text   = cfg_get("drawing_no",   "")
        tb_prepared_by.Text  = cfg_get("prepared_by",  "")
        tb_revision.Text     = cfg_get("revision",     "A")
        tb_prev_bbs.Text     = cfg_get("prev_bbs_path","")
        tb_output_folder.Text = cfg_get("output_folder", "")

        saved_scope = cfg_get("scope", "whole")
        if saved_scope == "view": rb_scope_view.IsChecked = True
        elif saved_scope == "selection": rb_scope_selection.IsChecked = True
        else: rb_scope_model.IsChecked = True

        saved_org = cfg_get("org", "floor")
        if saved_org == "elem": rb_org_elem.IsChecked = True
        elif saved_org == "both": rb_org_both.IsChecked = True
        else: rb_org_floor.IsChecked = True

        _update_auto_filename()

    def save_config():
        cfg_set("standard", cb_standard.Text)
        cfg_set("param_mark", tb_param_mark.Text.strip())
        cfg_set("param_type", tb_param_type.Text.strip())
        cfg_set("param_level", tb_param_level.Text.strip())
        cfg_set("param_length", tb_param_length.Text.strip())
        cfg_set("param_qty", tb_param_qty.Text.strip())
        cfg_set("param_shape", tb_param_shape.Text.strip())
        cfg_set("param_member", tb_param_member.Text.strip())
        cfg_set("param_detail", tb_param_detail.Text.strip())
        
        cfg_set("show_unit_weight", bool(chk_unit_weight.IsChecked))
        cfg_set("export_pdf", bool(chk_pdf.IsChecked))
        cfg_set("revision_track", bool(chk_revision.IsChecked))
        cfg_set("calc_sheet", bool(chk_calc_sheet.IsChecked))
        cfg_set("summary_sheet", bool(chk_summary_sheet.IsChecked))
        cfg_set("bbs_sheet", bool(chk_bbs_sheet.IsChecked))
        
        cfg_set("project_name", tb_project_name.Text.strip())
        cfg_set("drawing_no", tb_drawing_no.Text.strip())
        cfg_set("prepared_by", tb_prepared_by.Text.strip())
        cfg_set("revision", tb_revision.Text.strip())
        cfg_set("prev_bbs_path", tb_prev_bbs.Text.strip())
        cfg_set("output_folder", tb_output_folder.Text.strip())
        
        cfg_set("scope", "view" if rb_scope_view.IsChecked else "selection" if rb_scope_selection.IsChecked else "whole")
        cfg_set("org", "elem" if rb_org_elem.IsChecked else "both" if rb_org_both.IsChecked else "floor")
        
        _save_local_cfg()
        set_status("Settings saved.")

    btn_browse_prev.Click += lambda s,a: setattr(tb_prev_bbs, "Text", System.Windows.Forms.OpenFileDialog(Title="Select Previous BBS", Filter="Excel files|*.xlsx").FileName if System.Windows.Forms.OpenFileDialog(Title="Select Previous BBS", Filter="Excel files|*.xlsx").ShowDialog() == System.Windows.Forms.DialogResult.OK else tb_prev_bbs.Text)
    
    def on_browse_output(s,a):
        dlg = System.Windows.Forms.FolderBrowserDialog()
        if dlg.ShowDialog() == System.Windows.Forms.DialogResult.OK:
            tb_output_folder.Text = dlg.SelectedPath
    btn_browse_output.Click += on_browse_output

    def on_export(s, a):
        records = state["records"]
        if not records:
            set_status("No bars loaded. Click 'Load Bars' first.", True)
            return

        out_folder = tb_output_folder.Text.strip()
        if not out_folder or not os.path.isdir(out_folder):
            set_status("Output folder is not set or does not exist.", True)
            return

        filename = tb_filename.Text.strip() or "BBS_Export"
        if not filename.endswith(".xlsx"): filename += ".xlsx"
        xlsx_path = os.path.join(out_folder, filename)

        project_info = {
            "project_name": tb_project_name.Text.strip(),
            "drawing_no":   tb_drawing_no.Text.strip(),
            "prepared_by":  tb_prepared_by.Text.strip(),
            "date":         datetime.date.today().strftime("%d %b %Y"),
            "standard":     cb_standard.Text,
            "revision":     tb_revision.Text.strip(),
        }

        tb_log.Text = ""
        btn_export.IsEnabled = False
        set_status("Exporting…")
        set_progress(0, "Preparing export…")

        try:
            std_mod = _current_standard_module()
            changes = state["changes"] if chk_revision.IsChecked else None

            log(f"Export started: {xlsx_path}")
            log(f"Standard: {std_mod.STANDARD_NAME}")
            log(f"Bars: {len(records)}")

            def exp_progress(current, total, msg):
                set_progress(10 + int((current / max(total, 1)) * 80), msg)
                log(f"  {msg}")

            write_bbs_workbook(
                records=records, output_path=xlsx_path, project_info=project_info,
                show_unit_weight=bool(chk_unit_weight.IsChecked), include_calc_sheet=bool(chk_calc_sheet.IsChecked),
                include_summary_sheet=bool(chk_summary_sheet.IsChecked), revision_changes=changes,
                standard_module=std_mod, progress_callback=exp_progress,
            )
            log(f"✓ Excel saved: {xlsx_path}")
            set_progress(90, "Excel saved.")

            if chk_revision.IsChecked:
                save_revision(records, xlsx_path, std_mod.STANDARD_SHORT, metadata=project_info)
                log("✓ Revision sidecar saved.")

            if chk_pdf.IsChecked:
                set_progress(92, "Exporting PDF…")
                log("Exporting PDF…")
                ok, msg_pdf, pdf_path = export_pdf(xlsx_path)
                if ok: log(f"✓ PDF saved: {pdf_path}")
                else: log(f"⚠ PDF export: {msg_pdf}")

            set_progress(100, "Export complete ✓")
            lbl_export_path.Text = f"Saved: {xlsx_path}"
            set_status(f"Export complete — {len(records)} bars → {filename}")
            
            try: os.startfile(xlsx_path)
            except Exception: pass

        except Exception as ex:
            err_msg = traceback.format_exc()
            set_status(f"Export failed: {ex}", True)
            log(f"✗ ERROR EXPORTING:\n{err_msg}\n")
            set_progress(0, "Export failed.")
        finally:
            btn_export.IsEnabled = True

    def on_scope_changed(s, a):
        refresh_levels()
        refresh_members()
        refresh_diameter_filters()

    rb_scope_model.Checked     += on_scope_changed
    rb_scope_view.Checked      += on_scope_changed
    rb_scope_selection.Checked += on_scope_changed

    btn_load_bars.Click       += lambda s, a: load_bars()
    btn_refresh_preview.Click += lambda s, a: load_bars(refresh_only=True)
    btn_save_settings.Click   += lambda s, a: save_config()
    btn_export.Click          += on_export
    btn_close.Click           += lambda s, a: window.Close()

    tb_project_name.TextChanged += lambda s, a: _update_auto_filename()
    cb_standard.SelectionChanged += lambda s, a: _update_auto_filename()

    load_config()
    refresh_levels()
    refresh_members()
    refresh_diameter_filters()
    set_status("Ready — configure settings, then load bars.")

    window.ShowDialog()
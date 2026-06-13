#! python3
# -*- coding: utf-8 -*-

import os
import clr
import System

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementCategoryFilter, ElementMulticategoryFilter,
    CategoryType, ElementId, StorageType, Transaction
)

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import BitmapImage
from System.IO import FileStream, FileMode, FileAccess
from System import Uri, UriKind
from System.Collections.Generic import List as ListT
from System.Windows import (
    Thickness, Visibility, GridLength, GridUnitType, FontWeights, VerticalAlignment,
    MessageBox, MessageBoxButton, MessageBoxImage
)
from System.Windows.Controls import (
    Grid, ColumnDefinition, ComboBox, TextBox, Button, TextBlock, ListBoxItem, CheckBox
)

doc       = __revit__.ActiveUIDocument.Document
uidoc     = __revit__.ActiveUIDocument
LOCAL_DIR = os.path.dirname(__file__)

try:
    import traceback as _tb
    def _fmt_exc():
        return _tb.format_exc()
except ImportError:
    import sys as _sys
    def _fmt_exc():
        t, v, _ = _sys.exc_info()
        return "{}: {}".format(t.__name__ if t else "Error", v)


# ── numeric extractor (no re module in this engine) — mimics -?\d+(\.\d+)? ─────
def extract_numeric(text):
    if not text:
        return None
    s = str(text).replace(" ", "")
    last_dot = s.rfind('.')
    last_comma = s.rfind(',')
    if last_comma > last_dot:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '')
    n = len(s)
    j = 0
    while j < n:
        c = s[j]
        if c.isdigit() or (c == '-' and j + 1 < n and s[j + 1].isdigit()):
            digits = []
            k = j
            if s[k] == '-':
                digits.append('-')
                k += 1
            while k < n and s[k].isdigit():
                digits.append(s[k])
                k += 1
            if k < n and s[k] == '.':
                frac, m = [], k + 1
                while m < n and s[m].isdigit():
                    frac.append(s[m])
                    m += 1
                if frac:
                    digits.append('.')
                    digits.extend(frac)
            try:
                return float(''.join(digits))
            except ValueError:
                pass
        j += 1
    return None


# ──────────────────────────────────────────────────────────────────────────────
def run_ui():
    xaml_path = os.path.join(LOCAL_DIR, "ui.xaml")
    stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
    try:
        window = XamlReader.Load(stream)
    finally:
        stream.Close()

    icon_path = os.path.join(LOCAL_DIR, "icon.png")
    if os.path.exists(icon_path):
        window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

    f = window.FindName
    main_tabs         = f("main_tabs")
    btn_refresh       = f("btn_refresh")
    category_list     = f("category_list")
    btn_all_cats      = f("btn_all_cats")
    btn_none_cats     = f("btn_none_cats")
    btn_load_params   = f("btn_load_params")
    rb_whole          = f("rb_whole")
    rb_view           = f("rb_view")
    rb_selection      = f("rb_selection")
    rb_match_all      = f("rb_match_all")
    filter_rows_container = f("filter_rows_container")
    btn_apply_filter  = f("btn_apply_filter")
    filter_status     = f("filter_status")
    edit_rows_container = f("edit_rows_container")
    btn_execute       = f("btn_execute")
    edit_status       = f("edit_status")
    status_badge      = f("status_badge")
    status_textblock  = f("status_textblock")
    error_badge       = f("error_badge")
    error_text        = f("error_text")
    btn_select_elems  = f("btn_select_elems")
    btn_close         = f("btn_close")

    # Brand resources used by dynamically-built rows
    R_COMBO   = window.FindResource("InputComboBox")
    R_TEXT    = window.FindResource("InputTextBox")
    R_PRIMARY = window.FindResource("ButtonPrimary")
    R_SEC     = window.FindResource("ButtonSecondary")
    R_DANGER  = window.FindResource("ButtonDanger")
    R_CHAR    = window.FindResource("BrushCharcoalBlack")

    state = {
        "filtered_ids": [],
        "filtered_elements": [],
        "all_params_cache": [],
        "writable_params_cache": [],
        "val_to_num": {},
        "_suppress": False,   # mute auto-populate during programmatic Items edits
    }
    filter_rows = []
    edit_rows = []

    # ── Revit helpers ─────────────────────────────────────────────────────────
    def get_categories_by_scope():
        cats = set()
        try:
            if rb_whole.IsChecked:
                for c in doc.Settings.Categories:
                    if c.CategoryType == CategoryType.Model and c.AllowsBoundParameters:
                        try:
                            cf = ElementCategoryFilter(c.Id)
                            if FilteredElementCollector(doc).WherePasses(cf) \
                                    .WhereElementIsNotElementType().GetElementCount() > 0:
                                cats.add(c.Name)
                        except Exception:
                            pass
            elif rb_view.IsChecked:
                col = FilteredElementCollector(doc, doc.ActiveView.Id).WhereElementIsNotElementType()
                for e in col:
                    if e.Category:
                        cats.add(e.Category.Name)
            elif rb_selection.IsChecked:
                for eid in uidoc.Selection.GetElementIds():
                    el = doc.GetElement(eid)
                    if el and el.Category:
                        cats.add(el.Category.Name)
            return sorted(cats)
        except Exception:
            return []

    def get_elements_by_categories(category_names, scope):
        if not category_names:
            return []
        cat_ids = [c.Id for c in doc.Settings.Categories if c.Name in category_names]
        if not cat_ids:
            return []
        cat_list = ListT[ElementId]()
        for cid in cat_ids:
            cat_list.Add(cid)
        mf = ElementMulticategoryFilter(cat_list)
        if scope == "whole":
            return list(FilteredElementCollector(doc).WherePasses(mf)
                        .WhereElementIsNotElementType().ToElements())
        elif scope == "view":
            return list(FilteredElementCollector(doc, doc.ActiveView.Id).WherePasses(mf)
                        .WhereElementIsNotElementType().ToElements())
        else:
            out = []
            for eid in uidoc.Selection.GetElementIds():
                e = doc.GetElement(eid)
                if e and e.Category and e.Category.Name in category_names:
                    out.append(e)
            return out

    def get_common_params(elements, writable_only=False):
        if not elements:
            return []
        common = None
        for e in elements[:50]:
            cur = set()
            for p in e.Parameters:
                try:
                    if writable_only and p.IsReadOnly:
                        continue
                    cur.add(p.Definition.Name)
                except Exception:
                    continue
            common = cur if common is None else common.intersection(cur)
            if len(common) == 0:
                break
        return sorted(common) if common else []

    def get_param_values(elements, param_name):
        values = set()
        if param_name not in state["val_to_num"]:
            state["val_to_num"][param_name] = {}
        for e in elements:
            try:
                param = e.LookupParameter(param_name)
                if param is None:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te:
                            param = te.LookupParameter(param_name)
                if param is not None:
                    val = param.AsValueString()
                    if val is None:
                        if param.StorageType == StorageType.String:
                            val = param.AsString()
                        elif param.StorageType == StorageType.Integer:
                            val = str(param.AsInteger())
                        elif param.StorageType == StorageType.Double:
                            val = str(param.AsDouble())
                    if val is not None:
                        values.add(val)
                        if param.StorageType == StorageType.Double:
                            state["val_to_num"][param_name][val] = param.AsDouble()
                        elif param.StorageType == StorageType.Integer:
                            state["val_to_num"][param_name][val] = float(param.AsInteger())
            except Exception:
                continue
        return sorted(values)

    def evaluate_single_condition(e, param_name, operator, value):
        if value is None:
            value = ""
        try:
            param = e.LookupParameter(param_name)
            if param is None:
                tid = e.GetTypeId()
                if tid and tid != ElementId.InvalidElementId:
                    te = doc.GetElement(tid)
                    if te:
                        param = te.LookupParameter(param_name)
            if param is None:
                return False

            cur = param.AsValueString()
            if cur is None:
                if param.StorageType == StorageType.String:
                    cur = param.AsString()
                elif param.StorageType == StorageType.Integer:
                    cur = str(param.AsInteger())
                elif param.StorageType == StorageType.Double:
                    cur = str(param.AsDouble())
                else:
                    cur = ""
            if cur is None:
                cur = ""

            cur_low = cur.lower()
            val_low = str(value).lower()

            text_ops = ("equals", "does not equal", "contains", "does not contain",
                        "begins with", "does not begin with", "ends with", "does not end with")
            if operator in text_ops:
                if operator == "equals":               return cur_low == val_low
                if operator == "does not equal":        return cur_low != val_low
                if operator == "contains":              return val_low in cur_low
                if operator == "does not contain":      return val_low not in cur_low
                if operator == "begins with":           return cur_low.startswith(val_low)
                if operator == "does not begin with":   return not cur_low.startswith(val_low)
                if operator == "ends with":             return cur_low.endswith(val_low)
                if operator == "does not end with":     return not cur_low.endswith(val_low)
            else:
                st = param.StorageType
                if st not in (StorageType.Integer, StorageType.Double):
                    return False
                cur_num = float(param.AsInteger()) if st == StorageType.Integer else param.AsDouble()
                num_val = state["val_to_num"].get(param_name, {}).get(value)
                if num_val is None:
                    c_ext = extract_numeric(cur)
                    n_ext = extract_numeric(value)
                    if c_ext is not None and n_ext is not None:
                        cur_num, num_val = c_ext, n_ext
                    else:
                        num_val = float(value)
                if operator == "is greater than":              return cur_num > num_val
                if operator == "is greater than or equal to":  return cur_num >= num_val
                if operator == "is less than":                 return cur_num < num_val
                if operator == "is less than or equal to":     return cur_num <= num_val
        except Exception:
            pass
        return False

    def apply_single_modification(elem, param_name, operation, val1, val2):
        try:
            param = elem.LookupParameter(param_name)
            if param is None or param.IsReadOnly:
                return False, "Not found or read-only"
            st = param.StorageType
            if operation == "Delete":
                if st == StorageType.String:      param.Set("")
                elif st == StorageType.Integer:   param.Set(0)
                elif st == StorageType.Double:    param.Set(0.0)
                elif st == StorageType.ElementId: param.Set(ElementId.InvalidElementId)
                else: return False, "Cannot delete parameter type"
                return True, None
            if operation in ("Prefix", "Suffix", "Replace"):
                if st != StorageType.String:
                    return False, "Requires text parameter"
                cur = param.AsString() if param.AsString() else ""
                if operation == "Prefix":   param.Set(val1 + cur)
                elif operation == "Suffix": param.Set(cur + val1)
                elif operation == "Replace":
                    if not val1:
                        return False, "Empty search string"
                    param.Set(cur.replace(val1, val2))
                return True, None
            if operation == "Set":
                if st == StorageType.String:
                    param.Set(val1)
                elif st == StorageType.Integer:
                    if not param.SetValueString(val1):
                        param.Set(int(float(val1)))
                elif st == StorageType.Double:
                    if not param.SetValueString(val1):
                        param.Set(float(val1))
                elif st == StorageType.ElementId:
                    return False, "Set ElementId not supported"
                else:
                    param.Set(val1)
                return True, None
            return False, "Unknown operation"
        except Exception as ex:
            return False, str(ex)

    # ── Dynamic row builders ──────────────────────────────────────────────────
    def _icon_button(content, style):
        b = Button()
        b.Content = content
        b.Style = style
        b.Width = 24
        b.Height = 24
        b.Padding = Thickness(0)
        return b

    def update_filter_rows_ui():
        for i, row in enumerate(filter_rows):
            row['lbl'].Text = "{}.".format(i + 1)
            row['btn_minus'].IsEnabled = len(filter_rows) > 1

    def update_edit_rows_ui():
        for i, row in enumerate(edit_rows):
            row['lbl'].Text = "{}.".format(i + 1)
            row['btn_minus'].IsEnabled = len(edit_rows) > 1

    def _set_param_items(combo, params):
        """Populate a parameter combo without firing the auto-load handler."""
        prev = combo.Text
        state["_suppress"] = True
        try:
            combo.Items.Clear()
            for p in params:
                combo.Items.Add(p)
        finally:
            state["_suppress"] = False
        combo.Text = prev

    def confirm_filter_row(row_dict):
        if state["_suppress"]:
            return
        param_name = row_dict['cb_param'].Text.strip()
        if not param_name or not state["filtered_elements"]:
            return
        if row_dict.get('_last_param') == param_name:
            return   # unchanged — don't reset the user's operator/value
        row_dict['_last_param'] = param_name
        numeric = False
        for e in state["filtered_elements"][:20]:
            try:
                param = e.LookupParameter(param_name)
                if not param:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te:
                            param = te.LookupParameter(param_name)
                if param:
                    if param.StorageType in (StorageType.Integer, StorageType.Double):
                        numeric = True
                    break
            except Exception:
                continue
        cb_op = row_dict['cb_op']
        cb_op.Items.Clear()
        ops = (["equals", "does not equal", "is greater than", "is greater than or equal to",
                "is less than", "is less than or equal to"]
               if numeric else
               ["equals", "does not equal", "contains", "does not contain",
                "begins with", "does not begin with", "ends with", "does not end with"])
        for op in ops:
            cb_op.Items.Add(op)
        if cb_op.Items.Count > 0:
            cb_op.SelectedIndex = 0
        cb_val = row_dict['cb_val']
        cb_val.Items.Clear()
        for v in get_param_values(state["filtered_elements"], param_name):
            cb_val.Items.Add(v)

    def _edit_value_source():
        # Prefer the filtered (matched) elements; fall back to the loaded set.
        if state["filtered_ids"]:
            out = []
            for eid in state["filtered_ids"]:
                e = doc.GetElement(eid)
                if e:
                    out.append(e)
            if out:
                return out
        return state["filtered_elements"]

    def confirm_edit_row(row_dict):
        if state["_suppress"]:
            return
        param_name = row_dict['cb_param'].Text.strip()
        elems = _edit_value_source()
        if not param_name or not elems:
            return
        if row_dict.get('_last_param') == param_name:
            return   # unchanged — don't wipe the user's value
        row_dict['_last_param'] = param_name
        cb_val1 = row_dict['cb_val1']
        cb_val1.Items.Clear()
        for v in get_param_values(elems, param_name):
            cb_val1.Items.Add(v)

    def _on_edit_op_changed(row_dict):
        """val2 (replacement) shows only for Replace; the value combo is
        disabled for Delete (no value needed)."""
        op = str(row_dict['cb_op'].SelectedItem) if row_dict['cb_op'].SelectedItem else ""
        is_replace = (op == "Replace")
        is_delete  = (op == "Delete")
        row_dict['cb_val2'].Visibility = Visibility.Visible if is_replace else Visibility.Collapsed
        # collapse the column too so val1 reclaims the space
        row_dict['grid'].ColumnDefinitions[4].Width = (
            GridLength(1.5, GridUnitType.Star) if is_replace else GridLength(0))
        row_dict['cb_val1'].IsEnabled = not is_delete

    def _row_grid(star_widths):
        grid = Grid()
        grid.Margin = Thickness(0, 0, 0, 6)
        for w in star_widths:
            cd = ColumnDefinition()
            cd.Width = GridLength(w) if isinstance(w, int) else w
            grid.ColumnDefinitions.Add(cd)
        return grid

    def _row_label(grid):
        lbl = TextBlock()
        lbl.VerticalAlignment = VerticalAlignment.Center
        lbl.FontWeight = FontWeights.SemiBold
        lbl.Foreground = R_CHAR
        Grid.SetColumn(lbl, 0)
        grid.Children.Add(lbl)
        return lbl

    def add_filter_row():
        STAR = GridLength(1.5, GridUnitType.Star)
        grid = _row_grid([20, STAR, STAR, STAR, 28, 28])
        lbl = _row_label(grid)

        cb_param = ComboBox(); cb_param.Style = R_COMBO; cb_param.IsEditable = True
        cb_param.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_param, 1); grid.Children.Add(cb_param)

        cb_op = ComboBox(); cb_op.Style = R_COMBO
        cb_op.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_op, 2); grid.Children.Add(cb_op)

        cb_val = ComboBox(); cb_val.Style = R_COMBO; cb_val.IsEditable = True
        cb_val.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_val, 3); grid.Children.Add(cb_val)

        btn_plus = _icon_button("+", R_SEC)
        btn_plus.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(btn_plus, 4); grid.Children.Add(btn_plus)

        btn_minus = _icon_button("−", R_DANGER)  # −
        Grid.SetColumn(btn_minus, 5); grid.Children.Add(btn_minus)

        row_dict = {'grid': grid, 'lbl': lbl, 'cb_param': cb_param,
                    'cb_op': cb_op, 'cb_val': cb_val, 'btn_plus': btn_plus, 'btn_minus': btn_minus}

        btn_plus.Click  += lambda s, a: add_filter_row()
        btn_minus.Click += lambda s, a: remove_filter_row(row_dict)
        # Populate operator + value when the parameter is COMMITTED — dropdown
        # closes (pick) or focus leaves (typed/autocompleted). Not on scroll.
        cb_param.DropDownClosed += lambda s, a: confirm_filter_row(row_dict)
        cb_param.LostFocus      += lambda s, a: confirm_filter_row(row_dict)

        _set_param_items(cb_param, state["all_params_cache"])

        filter_rows.append(row_dict)
        filter_rows_container.Children.Add(grid)
        update_filter_rows_ui()

    def remove_filter_row(row_dict):
        if len(filter_rows) > 1:
            filter_rows.remove(row_dict)
            filter_rows_container.Children.Remove(row_dict['grid'])
            update_filter_rows_ui()

    def add_edit_row():
        STAR15 = GridLength(1.5, GridUnitType.Star)
        STAR12 = GridLength(1.2, GridUnitType.Star)
        grid = _row_grid([20, STAR15, STAR12, STAR15, STAR15, 28, 28])
        lbl = _row_label(grid)

        cb_param = ComboBox(); cb_param.Style = R_COMBO; cb_param.IsEditable = True
        cb_param.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_param, 1); grid.Children.Add(cb_param)

        cb_op = ComboBox(); cb_op.Style = R_COMBO
        for op in ["Prefix", "Suffix", "Replace", "Set", "Delete"]:
            cb_op.Items.Add(op)
        cb_op.SelectedIndex = 3
        cb_op.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_op, 2); grid.Children.Add(cb_op)

        cb_val1 = ComboBox(); cb_val1.Style = R_COMBO; cb_val1.IsEditable = True
        cb_val1.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_val1, 3); grid.Children.Add(cb_val1)

        tb_val2 = TextBox(); tb_val2.Style = R_TEXT
        tb_val2.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(tb_val2, 4); grid.Children.Add(tb_val2)

        btn_plus = _icon_button("+", R_SEC)
        btn_plus.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(btn_plus, 5); grid.Children.Add(btn_plus)

        btn_minus = _icon_button("−", R_DANGER)
        Grid.SetColumn(btn_minus, 6); grid.Children.Add(btn_minus)

        row_dict = {'grid': grid, 'lbl': lbl, 'cb_param': cb_param, 'cb_op': cb_op,
                    'cb_val1': cb_val1, 'cb_val2': tb_val2, 'btn_plus': btn_plus, 'btn_minus': btn_minus}

        btn_plus.Click  += lambda s, a: add_edit_row()
        btn_minus.Click += lambda s, a: remove_edit_row(row_dict)
        cb_op.SelectionChanged += lambda s, a: _on_edit_op_changed(row_dict)
        # Populate values when the parameter is COMMITTED — dropdown closes
        # (pick) or focus leaves (typed/autocompleted). Not on scroll.
        cb_param.DropDownClosed += lambda s, a: confirm_edit_row(row_dict)
        cb_param.LostFocus      += lambda s, a: confirm_edit_row(row_dict)

        _set_param_items(cb_param, state["writable_params_cache"])

        edit_rows.append(row_dict)
        edit_rows_container.Children.Add(grid)
        update_edit_rows_ui()
        _on_edit_op_changed(row_dict)   # init: hidden/disabled per default op (Set)

    def remove_edit_row(row_dict):
        if len(edit_rows) > 1:
            edit_rows.remove(row_dict)
            edit_rows_container.Children.Remove(row_dict['grid'])
            update_edit_rows_ui()

    # ── Status / counts ───────────────────────────────────────────────────────
    def set_status(message, is_error=False):
        status_textblock.Text = message
        if not is_error:
            status_badge.Visibility = Visibility.Visible
            error_badge.Visibility = Visibility.Collapsed
        else:
            status_badge.Visibility = Visibility.Collapsed
            error_badge.Visibility = Visibility.Visible
        error_text.Text = message if is_error else ""

    def _checked_cat_names():
        return [item.Content.Content.Text for item in category_list.Items
                if item.Content.IsChecked]

    def refresh_category_list():
        category_list.Items.Clear()
        for cat_name in get_categories_by_scope():
            tb = TextBlock(); tb.Text = cat_name
            chk = CheckBox(); chk.Content = tb; chk.IsChecked = False
            item = ListBoxItem(); item.Content = chk
            category_list.Items.Add(item)

    def refresh_params():
        """Header Refresh — (re)load the parameter dropdowns for BOTH tabs and,
        for each row's chosen parameter, its operator/value lists.

        The heavy category scan runs only when parameters aren't loaded yet;
        once loaded it's skipped (re-syncing the rows is cheap)."""
        if not state["all_params_cache"]:
            cats = _checked_cat_names()
            if cats:
                scope = "whole" if rb_whole.IsChecked else "view" if rb_view.IsChecked else "selection"
                elements = get_elements_by_categories(cats, scope)
                if elements:
                    state["filtered_elements"] = elements
                    state["all_params_cache"] = get_common_params(elements)
        if not state["writable_params_cache"]:
            src = _edit_value_source() if state["filtered_ids"] else state["filtered_elements"]
            if src:
                state["writable_params_cache"] = get_common_params(src, writable_only=True)
        # Repopulate param lists AND, for each row's chosen parameter, its
        # operator/value lists — the one and only repopulate path.
        for row in filter_rows:
            _set_param_items(row['cb_param'], state["all_params_cache"])
            row['_last_param'] = None   # force reload past the change-guard
            confirm_filter_row(row)
        for row in edit_rows:
            _set_param_items(row['cb_param'], state["writable_params_cache"])
            row['_last_param'] = None
            confirm_edit_row(row)
        set_status("Refreshed — {} filter / {} edit params".format(
            len(state["all_params_cache"]), len(state["writable_params_cache"])))

    # ── Events ────────────────────────────────────────────────────────────────
    def on_scope_changed(s, a):
        refresh_category_list()
    rb_whole.Checked += on_scope_changed
    rb_view.Checked += on_scope_changed
    rb_selection.Checked += on_scope_changed

    def on_select_all(s, a):
        for item in category_list.Items:
            item.Content.IsChecked = True

    def on_select_none(s, a):
        for item in category_list.Items:
            item.Content.IsChecked = False
    btn_all_cats.Click += on_select_all
    btn_none_cats.Click += on_select_none
    btn_refresh.Click += lambda s, a: refresh_params()

    def on_load_params(s, a):
        cats = _checked_cat_names()
        if not cats:
            set_status("Select at least one category", True)
            return
        set_status("Loading parameters...")
        scope = "whole" if rb_whole.IsChecked else "view" if rb_view.IsChecked else "selection"
        elements = get_elements_by_categories(cats, scope)
        if not elements:
            set_status("No elements found in selected categories.", True)
            return
        state["filtered_elements"] = elements
        state["all_params_cache"] = get_common_params(elements)
        for row in filter_rows:
            _set_param_items(row['cb_param'], state["all_params_cache"])
        set_status("Loaded {} parameters from {} elements.".format(
            len(state["all_params_cache"]), len(elements)))
        main_tabs.SelectedIndex = 1
    btn_load_params.Click += on_load_params

    def on_apply_filter(s, a):
        if not state["filtered_elements"]:
            filter_status.Text = "Load parameters from the Categories tab first."
            return
        filter_status.Text = "Applying multi-filter..."
        match_all = rb_match_all.IsChecked
        passed = []
        for e in state["filtered_elements"]:
            elem_passed = match_all
            active = 0
            for row in filter_rows:
                p_name = row['cb_param'].Text.strip()
                if not p_name:
                    continue
                active += 1
                op = str(row['cb_op'].SelectedItem) if row['cb_op'].SelectedItem else "contains"
                val = row['cb_val'].Text
                cond = evaluate_single_condition(e, p_name, op, val)
                if match_all:
                    if not cond:
                        elem_passed = False
                        break
                else:
                    if cond:
                        elem_passed = True
                        break
            if not match_all and active == 0:
                elem_passed = True
            if elem_passed:
                passed.append(e)

        state["filtered_ids"] = [e.Id for e in passed]
        if state["filtered_ids"]:
            filter_status.Text = "Filtered: {} elements match the criteria.".format(len(passed))
            set_status("{} elements filtered".format(len(passed)))
            btn_select_elems.IsEnabled = True
            state["writable_params_cache"] = get_common_params(passed, writable_only=True)
            for row in edit_rows:
                _set_param_items(row['cb_param'], state["writable_params_cache"])
            edit_status.Text = "Ready to edit {} filtered elements.".format(len(passed))
            main_tabs.SelectedIndex = 2
        else:
            filter_status.Text = "No elements match the combination of filters."
            set_status("No matches", True)
            btn_select_elems.IsEnabled = False
    btn_apply_filter.Click += on_apply_filter

    def on_execute(s, a):
        if not state["filtered_ids"]:
            edit_status.Text = "Apply filter first."
            return
        btn_execute.IsEnabled = False
        edit_status.Text = "Modifying elements in batch..."
        modified = 0
        errors = []
        t = Transaction(doc, "AnonGee · Multi Filter Parameter Edit")
        t.Start()
        try:
            for eid in state["filtered_ids"]:
                elem = doc.GetElement(eid)
                if not elem:
                    continue
                elem_modified = False
                for row in edit_rows:
                    p_name = row['cb_param'].Text.strip()
                    if not p_name:
                        continue
                    op = str(row['cb_op'].SelectedItem) if row['cb_op'].SelectedItem else "Set"
                    val1 = row['cb_val1'].Text
                    val2 = row['cb_val2'].Text
                    ok, err = apply_single_modification(elem, p_name, op, val1, val2)
                    if ok:
                        elem_modified = True
                    if err:
                        errors.append("Element {}: {}".format(_id_value(eid), err))
                if elem_modified:
                    modified += 1
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            errors.append("Transaction failed: " + str(ex))

        if modified > 0:
            msg = "Modified {} elements successfully.".format(modified)
            if errors:
                msg += " ({} partial errors).".format(len(errors))
            edit_status.Text = msg
            set_status("Modified {} elements".format(modified))
        else:
            err_str = "; ".join(errors[:3]) if errors else "No valid parameters selected."
            edit_status.Text = "No elements modified. " + err_str
            set_status("No elements modified", True)
        btn_execute.IsEnabled = True
    btn_execute.Click += on_execute

    def on_select_elements(s, a):
        if state["filtered_ids"]:
            try:
                # Build List[ElementId] with .Add() — pythonnet has no ctor
                # overload that accepts a raw Python list (§12.9.4).
                ids = ListT[ElementId]()
                for eid in state["filtered_ids"]:
                    ids.Add(eid)
                uidoc.Selection.SetElementIds(ids)
                window.Close()
            except Exception as ex:
                set_status("Selection failed: " + str(ex), True)
    btn_select_elems.Click += on_select_elements

    btn_close.Click += lambda s, a: window.Close()

    # Initial setup
    refresh_category_list()
    add_filter_row()
    add_edit_row()
    set_status("Ready")

    window.ShowDialog()


def _id_value(eid):
    return getattr(eid, "Value", getattr(eid, "IntegerValue", -1))


if __name__ == "__main__":
    try:
        run_ui()
    except Exception:
        MessageBox.Show(
            _fmt_exc()[-3000:],
            "Multi Filter Parameter — Unhandled Error",
            MessageBoxButton.OK, MessageBoxImage.Error)

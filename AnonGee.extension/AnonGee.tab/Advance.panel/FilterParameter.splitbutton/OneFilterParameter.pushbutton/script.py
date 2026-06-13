#! python3
# -*- coding: utf-8 -*-
# pyRevit script - OneFilterParameter (CPython 3)
# AnonGee BIM Tools v3.0 — theme loaded from shared Resources/

import sys
import clr
import System

# Standard Revit API imports
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

# Bypassing 'from pyrevit import revit' to avoid CPython interface bugs in events.py
doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument


def _bracket_int(s):
    """Parse a leading '[<int>]' prefix to an int (else None). Replaces
    re.match — the `re` module is unavailable in this CPython3 engine."""
    if not s or not s.startswith('['):
        return None
    end = s.find(']')
    if end < 1:
        return None
    try:
        return int(s[1:end].strip())
    except ValueError:
        return None

# Add WPF assemblies
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader
from System.Windows import UIElement, Visibility, RoutedEventHandler
from System.Windows.Media import VisualTreeHelper
from System.IO import MemoryStream, File, StreamReader, Path
from System.Text import Encoding
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Controls import ListBoxItem, CheckBox, DataGridCell, DataGridRow as WpfDataGridRow
from System.Collections.Generic import List
from System.Collections import ArrayList
from System import String as NetString, TimeSpan

# ======================================================================
# PREVIEW DATA CLASS — simple __slots__ for reliable WPF DataGrid binding
# ======================================================================
class PreviewItem:
    """One row in the live preview DataGrid. __slots__ is required for
    Python.NET 3 to expose attributes as bindable properties."""
    __slots__ = ['ElementId', 'FamilyName', 'TypeName',
                 'FilterValue', 'EditPreview', 'IsSelected', 'InFilter', 'Element']

    def __init__(self, element_id, element, family_name, type_name):
        self.ElementId   = str(element_id)
        self.Element     = element
        self.FamilyName  = family_name or "N/A"
        self.TypeName    = type_name   or "N/A"
        self.FilterValue = ""
        self.EditPreview = ""
        self.IsSelected  = True
        self.InFilter    = True

# ======================================================================
# LOAD XAML
# ======================================================================
def load_xaml_window():
    """Read ui.xaml — fully self-contained inline theme, no runtime injection needed."""
    script_dir = Path.GetDirectoryName(Path.GetFullPath(__file__))
    xaml_path = Path.Combine(script_dir, "ui.xaml")
    if not File.Exists(xaml_path):
        raise Exception("ui.xaml not found at: " + xaml_path)
    reader = StreamReader(xaml_path, Encoding.UTF8)
    content = reader.ReadToEnd()
    reader.Close()
    return content

# ======================================================================
# DEBOUNCE TIMER HELPER
# ======================================================================
class DebounceTimer:
    def __init__(self, callback, delay_ms=300):
        from System.Windows.Threading import DispatcherTimer
        self._timer = DispatcherTimer()
        self._timer.Interval = TimeSpan.FromMilliseconds(delay_ms)
        self._timer.Tick += self._on_tick
        self._callback = callback

    def _on_tick(self, sender, args):
        self._timer.Stop()
        self._callback()

    def reset(self):
        self._timer.Stop()
        self._timer.Start()

    def stop(self):
        self._timer.Stop()

# ======================================================================
# MAIN UI LOGIC
# ======================================================================
def run_ui():
    # Load XAML from external file
    xaml = load_xaml_window()
    bytes = Encoding.UTF8.GetBytes(xaml)
    stream = MemoryStream(bytes)
    window = XamlReader.Load(stream)

    # Find controls
    header_title      = window.FindName("header_title")
    btn_refresh       = window.FindName("btn_refresh")
    category_list     = window.FindName("category_list")
    btn_all_cats      = window.FindName("btn_all_cats")
    btn_none_cats     = window.FindName("btn_none_cats")
    btn_load_params   = window.FindName("btn_load_params")

    rb_whole          = window.FindName("rb_whole")
    rb_view           = window.FindName("rb_view")
    rb_selection      = window.FindName("rb_selection")

    filter_param      = window.FindName("filter_param")
    filter_op         = window.FindName("filter_op")
    filter_val        = window.FindName("filter_val")
    btn_apply_filter  = window.FindName("btn_apply_filter")
    btn_select_elems  = window.FindName("btn_select_elems")

    edit_param        = window.FindName("edit_param")
    edit_op           = window.FindName("edit_op")
    edit_val1         = window.FindName("edit_val1")
    edit_val2         = window.FindName("edit_val2")
    lbl_replace       = window.FindName("lbl_replace")
    btn_execute       = window.FindName("btn_execute")

    status_badge      = window.FindName("status_badge")
    status_textblock  = window.FindName("status_textblock")
    error_badge       = window.FindName("error_badge")
    error_text        = window.FindName("error_text")
    btn_close         = window.FindName("btn_close")

    # Live preview controls
    preview_list      = window.FindName("preview_list")
    preview_info      = window.FindName("preview_info")
    btn_select_all_rows  = window.FindName("btn_select_all_rows")
    btn_deselect_all_rows = window.FindName("btn_deselect_all_rows")

    # State Variables
    state = {
        "filtered_ids": [],
        "filtered_elements": [],
        "all_params_cache": [],
        "val_to_num": {},
        "preview_items": [],       # List[PreviewItem]
        "filter_param_name": "",   # Current filter parameter name
        "edit_param_name": "",     # Current edit parameter name
        "current_filter_param": None, # Parameter object for live preview
        "current_edit_param": None,   # Parameter object for edit preview
        "filter_applied_once": False, # Gate: realtime filter only runs after Apply Filter clicked
        "_refreshing": False,         # Guard against reentrant events during refresh
        "last_click_index": -1,       # Tracks last clicked row for Shift+click range selection
    }

    # ------------------------------------------------------------------
    # Helper functions (Revit API)
    # ------------------------------------------------------------------
    def get_categories_by_scope():
        cats = set()
        try:
            if rb_whole.IsChecked:
                for c in doc.Settings.Categories:
                    if c.CategoryType == CategoryType.Model and c.AllowsBoundParameters:
                        try:
                            cat_filter = ElementCategoryFilter(c.Id)
                            if FilteredElementCollector(doc).WherePasses(cat_filter).WhereElementIsNotElementType().GetElementCount() > 0:
                                cats.add(c.Name)
                        except:
                            pass
            elif rb_view.IsChecked:
                view = doc.ActiveView
                collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
                for e in collector:
                    if e.Category:
                        cats.add(e.Category.Name)
            elif rb_selection.IsChecked:
                sel = uidoc.Selection.GetElementIds()
                for id in sel:
                    elem = doc.GetElement(id)
                    if elem and elem.Category:
                        cats.add(elem.Category.Name)
            return sorted(cats)
        except Exception as ex:
            return []

    def get_elements_by_categories(category_names, scope):
        if not category_names:
            return []

        cat_ids = []
        for c in doc.Settings.Categories:
            if c.Name in category_names:
                cat_ids.append(c.Id)

        if not cat_ids:
            return []

        cat_list = List[ElementId]()
        for cid in cat_ids:
            cat_list.Add(cid)

        multi_filter = ElementMulticategoryFilter(cat_list)

        if scope == "whole":
            collector = FilteredElementCollector(doc).WherePasses(multi_filter).WhereElementIsNotElementType()
            return list(collector.ToElements())
        elif scope == "view":
            view = doc.ActiveView
            collector = FilteredElementCollector(doc, view.Id).WherePasses(multi_filter).WhereElementIsNotElementType()
            return list(collector.ToElements())
        else:
            sel_ids = uidoc.Selection.GetElementIds()
            if not sel_ids:
                return []
            elements = []
            for id in sel_ids:
                e = doc.GetElement(id)
                if e and e.Category and e.Category.Name in category_names:
                    elements.append(e)
            return elements

    def get_param_val_str(param, store_numeric=False):
        if param is None:
            return None

        st = param.StorageType

        if st == StorageType.ElementId:
            eid = param.AsElementId()
            eid_val = getattr(eid, "Value", getattr(eid, "IntegerValue", -1))
            if eid_val != -1:
                ref_elem = doc.GetElement(eid)
                name = ref_elem.Name if ref_elem else (param.AsValueString() or "Unknown")
                return "[{0}] {1}".format(eid_val, name)
            else:
                return "None"

        val_str = param.AsValueString()
        if val_str is None:
            if st == StorageType.String:
                val_str = param.AsString()
            elif st == StorageType.Integer:
                val_str = str(param.AsInteger())
            elif st == StorageType.Double:
                val_str = str(param.AsDouble())

        if store_numeric and val_str is not None:
            if st == StorageType.Double:
                state["val_to_num"][val_str] = param.AsDouble()
            elif st == StorageType.Integer:
                state["val_to_num"][val_str] = float(param.AsInteger())

        return val_str if val_str is not None else ""

    def get_common_params(elements, writable_only=False, string_only=False):
        if not elements:
            return []
        common = None
        for e in elements[:50]:
            cur = set()
            for p in e.Parameters:
                try:
                    if writable_only and p.IsReadOnly: continue
                    if string_only and p.StorageType != StorageType.String: continue
                    cur.add(p.Definition.Name)
                except: continue

            tid = e.GetTypeId()
            if tid and tid != ElementId.InvalidElementId:
                te = doc.GetElement(tid)
                if te:
                    for p in te.Parameters:
                        try:
                            if writable_only and p.IsReadOnly: continue
                            if string_only and p.StorageType != StorageType.String: continue
                            cur.add(p.Definition.Name)
                        except: continue

            if common is None:
                common = cur
            else:
                common = common.intersection(cur)
            if len(common) == 0:
                break
        return sorted(common) if common else []

    def get_param_values(elements, param_name):
        values = set()
        state["val_to_num"] = {}
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
                    val_str = get_param_val_str(param, store_numeric=True)
                    if val_str is not None:
                        values.add(val_str)
            except:
                continue
        return sorted(values)

    def extract_numeric(text):
        if not text: return None
        s = str(text).replace(" ", "")
        last_dot = s.rfind('.')
        last_comma = s.rfind(',')
        if last_comma > last_dot:
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
        # first -?\d+(\.\d+)? without the re module
        n = len(s); j = 0
        while j < n:
            c = s[j]
            if c.isdigit() or (c == '-' and j + 1 < n and s[j + 1].isdigit()):
                digits = []; k = j
                if s[k] == '-': digits.append('-'); k += 1
                while k < n and s[k].isdigit(): digits.append(s[k]); k += 1
                if k < n and s[k] == '.':
                    frac = []; mm = k + 1
                    while mm < n and s[mm].isdigit(): frac.append(s[mm]); mm += 1
                    if frac: digits.append('.'); digits.extend(frac)
                try: return float(''.join(digits))
                except ValueError: pass
            j += 1
        return None

    def filter_elements(elements, param_name, operator, value):
        filtered_ids = []
        if value is None:
            value = ""

        for e in elements:
            try:
                param = e.LookupParameter(param_name)
                if param is None:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te:
                            param = te.LookupParameter(param_name)
                if param is None:
                    continue

                cur_val_str = get_param_val_str(param) or ""
                cur_low = cur_val_str.lower()
                val_low = str(value).lower()

                if operator in ("equals", "does not equal", "contains", "does not contain",
                                "begins with", "does not begin with", "ends with", "does not end with"):
                    if operator == "equals" and cur_low != val_low: continue
                    elif operator == "does not equal" and cur_low == val_low: continue
                    elif operator == "contains" and val_low not in cur_low: continue
                    elif operator == "does not contain" and val_low in cur_low: continue
                    elif operator == "begins with" and not cur_low.startswith(val_low): continue
                    elif operator == "does not begin with" and cur_low.startswith(val_low): continue
                    elif operator == "ends with" and not cur_low.endswith(val_low): continue
                    elif operator == "does not end with" and cur_low.endswith(val_low): continue
                    filtered_ids.append(e.Id)
                else:
                    try:
                        cur_num = None
                        num_val = None
                        st = param.StorageType
                        if st not in (StorageType.Integer, StorageType.Double): continue

                        if st == StorageType.Integer:
                            cur_num = float(param.AsInteger())
                        elif st == StorageType.Double:
                            cur_num = param.AsDouble()

                        if value in state.get("val_to_num", {}):
                            num_val = state["val_to_num"][value]
                        else:
                            cur_num_ext = extract_numeric(cur_val_str)
                            num_val_ext = extract_numeric(value)
                            if cur_num_ext is not None and num_val_ext is not None:
                                cur_num = cur_num_ext
                                num_val = num_val_ext
                            else:
                                num_val = float(value)

                        if cur_num is None or num_val is None: continue

                        if operator == "is greater than" and not cur_num > num_val: continue
                        elif operator == "is greater than or equal to" and not cur_num >= num_val: continue
                        elif operator == "is less than" and not cur_num < num_val: continue
                        elif operator == "is less than or equal to" and not cur_num <= num_val: continue

                        filtered_ids.append(e.Id)
                    except Exception:
                        continue
            except Exception:
                continue
        return filtered_ids

    def modify_elements(ids, param_name, operation, val1, val2):
        modified = 0
        errors = []
        if not ids:
            return 0, ["No elements selected."]

        t = Transaction(doc, "OneParameter Batch Edit")
        t.Start()
        try:
            processed_types = set()
            for e in ids:
                try:
                    elem = doc.GetElement(e)
                    if not elem: continue
                    target = elem
                    param = elem.LookupParameter(param_name)
                    if param is None:
                        tid = elem.GetTypeId()
                        if tid and tid != ElementId.InvalidElementId:
                            te = doc.GetElement(tid)
                            if te:
                                param = te.LookupParameter(param_name)
                                target = te
                    if param is None or param.IsReadOnly:
                        errors.append("Param '{0}' not found/read-only on {1}".format(param_name, str(e)))
                        continue
                    if target.Id != elem.Id:
                        tid_val = getattr(target.Id, "Value", -1)
                        if tid_val in processed_types:
                            modified += 1
                            continue
                    st = param.StorageType
                    if operation == "Delete":
                        if st == StorageType.String: param.Set(System.String(""))
                        elif st == StorageType.Integer: param.Set(System.Int32(0))
                        elif st == StorageType.Double: param.Set(System.Double(0.0))
                        elif st == StorageType.ElementId: param.Set(ElementId.InvalidElementId)
                        else: errors.append("Cannot delete on {0}".format(str(e))); continue
                        modified += 1
                    elif operation in ("Prefix", "Suffix", "Replace"):
                        if st != StorageType.String: errors.append("Operation '{0}' needs text param".format(operation)); continue
                        cur = param.AsString() or ""
                        if operation == "Prefix": param.Set(System.String(val1 + cur))
                        elif operation == "Suffix": param.Set(System.String(cur + val1))
                        elif operation == "Replace":
                            if not val1: errors.append("Empty search string"); continue
                            param.Set(System.String(cur.replace(val1, val2)))
                        modified += 1
                    elif operation == "Set":
                        try:
                            if st == StorageType.String: param.Set(System.String(val1))
                            elif st == StorageType.Integer:
                                vl = str(val1).strip().lower()
                                if vl in ("yes","true","1","on"): param.Set(System.Int32(1))
                                elif vl in ("no","false","0","off"): param.Set(System.Int32(0))
                                else:
                                    if not param.SetValueString(System.String(val1)): param.Set(System.Int32(int(float(val1))))
                            elif st == StorageType.Double:
                                if not param.SetValueString(System.String(val1)): param.Set(System.Double(float(val1)))
                            elif st == StorageType.ElementId:
                                id_int = _bracket_int(str(val1).strip())
                                if id_int is None: id_int = int(float(val1))
                                new_id = ElementId(System.Int64(id_int))
                                param.Set(new_id)
                            else: param.Set(System.String(val1))
                            modified += 1
                        except Exception as ex: errors.append("Set failed: " + str(ex))
                    if target.Id != elem.Id:
                        tid_val = getattr(target.Id, "Value", -1)
                        processed_types.add(tid_val)
                except Exception as ex: errors.append("Error: " + str(ex))
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded(): t.RollBack()
            errors.append("Transaction failed: " + str(ex))
        return modified, errors

    # ------------------------------------------------------------------
    # LIVE PREVIEW FUNCTIONS
    # ------------------------------------------------------------------
    def get_element_family_name(elem):
        """Get the family name of an element."""
        try:
            # Try symbol (family instance)
            sym = elem.Symbol
            if sym:
                fam = sym.Family
                if fam: return fam.Name
        except:
            pass
        try:
            # Try element type
            tid = elem.GetTypeId()
            if tid and tid != ElementId.InvalidElementId:
                te = doc.GetElement(tid)
                if te: return te.Name
        except:
            pass
        # Try category
        try:
            if elem.Category: return elem.Category.Name
        except:
            pass
        return "N/A"

    def get_element_type_name(elem):
        """Get the type name of an element."""
        try:
            tid = elem.GetTypeId()
            if tid and tid != ElementId.InvalidElementId:
                te = doc.GetElement(tid)
                if te: return te.Name
        except:
            pass
        return "N/A"

    def build_preview_items(elements):
        """Create PreviewItem list from Revit elements."""
        items = []
        for e in elements:
            eid_val = getattr(e.Id, "Value", getattr(e.Id, "IntegerValue", -1))
            fam_name = get_element_family_name(e)
            type_name = get_element_type_name(e)
            item = PreviewItem(eid_val, e, fam_name, type_name)
            items.append(item)
        return items

    def update_preview_info():
        total   = len(state["preview_items"])
        visible = len([i for i in state["preview_items"] if i.InFilter])
        checked = len([i for i in state["preview_items"] if i.InFilter and i.IsSelected])
        base = "{0} elements".format(total) if visible == total \
            else "{0} / {1} matched".format(visible, total)
        preview_info.Text = "{0}  -  {1} checked".format(base, checked)

    def refresh_preview_display():
        """Populate the DataGrid — only rows where InFilter=True are shown."""
        state["_refreshing"] = True
        try:
            items = ArrayList()
            for item in state["preview_items"]:
                if item.InFilter:
                    items.Add(item)
            preview_list.ItemsSource = None
            preview_list.ItemsSource = items
            # Re-apply the native row selection (= the checkbox state) from each
            # item's IsSelected, which survives the rebuild on the Python side.
            preview_list.SelectedItems.Clear()
            for item in state["preview_items"]:
                if item.InFilter and item.IsSelected:
                    preview_list.SelectedItems.Add(item)
            update_preview_info()
        finally:
            state["_refreshing"] = False

    def update_live_filter_preview():
        """Update FilterValue on all preview items based on current filter."""
        param_name = filter_param.Text.strip()
        state["filter_param_name"] = param_name
        if not param_name or not state["preview_items"]:
            return
        # Get the parameter value for each element
        for item in state["preview_items"]:
            try:
                param = item.Element.LookupParameter(param_name)
                if param is None:
                    tid = item.Element.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te: param = te.LookupParameter(param_name)
                if param:
                    val_str = get_param_val_str(param) or ""
                    item.FilterValue = val_str
                else:
                    item.FilterValue = "-"
            except:
                item.FilterValue = "?"
        refresh_preview_display()

    def update_live_edit_preview():
        """Update EditPreview on all preview items based on current edit settings."""
        param_name = edit_param.Text.strip()
        operation = str(edit_op.SelectedItem) if edit_op.SelectedItem else "Set"
        val1 = edit_val1.Text
        val2 = edit_val2.Text
        state["edit_param_name"] = param_name

        if not param_name or not state["preview_items"]:
            return
        for item in state["preview_items"]:
            if not item.IsSelected:
                item.EditPreview = "(skip)"   # unchecked rows won't be edited
                continue
            try:
                param = item.Element.LookupParameter(param_name)
                if param is None:
                    tid = item.Element.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te: param = te.LookupParameter(param_name)
                if param:
                    cur_val = get_param_val_str(param) or ""
                    # Compute preview
                    st = param.StorageType
                    if operation == "Delete":
                        item.EditPreview = "(deleted)"
                    elif operation == "Prefix":
                        item.EditPreview = val1 + cur_val
                    elif operation == "Suffix":
                        item.EditPreview = cur_val + val1
                    elif operation == "Replace":
                        item.EditPreview = cur_val.replace(val1, val2) if val1 else cur_val
                    elif operation == "Set":
                        item.EditPreview = val1
                    else:
                        item.EditPreview = cur_val
                else:
                    item.EditPreview = "N/A"
            except:
                item.EditPreview = "?"
        refresh_preview_display()

    def realtime_filter_update():
        """Called on debounced timer - only runs after Apply Filter has been clicked once,
        so changing the parameter dropdown doesn't wipe the preview before the user is ready."""
        if not state.get("filtered_elements"):
            return
        if not state.get("filter_applied_once"):
            return
        param_name = filter_param.Text.strip()
        operator = str(filter_op.SelectedItem) if filter_op.SelectedItem else "contains"
        value = filter_val.Text

        if not param_name:
            for item in state["preview_items"]:
                item.InFilter   = True
                item.IsSelected = True
            refresh_preview_display()
            return

        filtered_ids_set = set(filter_elements(state["filtered_elements"], param_name, operator, value))
        for item in state["preview_items"]:
            matched = item.Element.Id in filtered_ids_set
            item.InFilter   = matched
            item.IsSelected = matched

        refresh_preview_display()

    # Create debounced filter timer
    filter_debounce = DebounceTimer(realtime_filter_update, 300)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def set_status(message, is_error=False):
        status_textblock.Text = message
        if not is_error:
            status_badge.Visibility = Visibility.Visible
            error_badge.Visibility = Visibility.Collapsed
        else:
            status_badge.Visibility = Visibility.Collapsed
            error_badge.Visibility = Visibility.Visible
        error_text.Text = message if is_error else ""

    # The three section statuses now live in the footer status bar: assigning
    # `.Text` on these proxies routes the message to set_status().
    class _StatusLine(object):
        __slots__ = ['_t']
        def __init__(self):
            self._t = ""
        def _get(self):
            return self._t
        def _set(self, v):
            self._t = v
            set_status(v)
        Text = property(_get, _set)

    cat_status    = _StatusLine()
    filter_status = _StatusLine()
    edit_status   = _StatusLine()

    def refresh_category_list():
        category_list.Items.Clear()
        cats = get_categories_by_scope()
        for cat_name in cats:
            item = ListBoxItem()
            chk = CheckBox()
            chk.Content = cat_name
            chk.IsChecked = False
            item.Content = chk
            item.Tag = cat_name
            category_list.Items.Add(item)

    def _repopulate_values(combo, values):
        """Refresh the dropdown options without touching the current input."""
        prev = combo.Text
        combo.Items.Clear()
        for v in values:
            combo.Items.Add(v)
        combo.Text = prev

    def refresh_params(sender=None, args=None):
        """Header Refresh — re-scan the available filter/edit VALUE options for
        the current parameters. Deliberately does NOT touch the chosen operator,
        the typed values, the filter result, or the row checks."""
        if not state.get("filtered_elements"):
            set_status("Load parameters first.", is_error=True)
            return
        fp = filter_param.Text.strip()
        if fp:
            _repopulate_values(filter_val, get_param_values(state["filtered_elements"], fp))
        ep = edit_param.Text.strip()
        if ep and state.get("filtered_ids"):
            elems = [doc.GetElement(eid) for eid in state["filtered_ids"] if doc.GetElement(eid)]
            _repopulate_values(edit_val1, get_param_values(elems, ep))
        set_status("Value lists refreshed")

    def get_selected_categories():
        selected = []
        for item in category_list.Items:
            chk = item.Content
            if chk.IsChecked:
                selected.append(str(chk.Content))
        return selected

    def update_operators_and_values(param_name, elements):
        numeric = False
        for e in elements[:20]:
            try:
                param = e.LookupParameter(param_name)
                if param is None:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te: param = te.LookupParameter(param_name)
                if param:
                    st = param.StorageType
                    if st in (StorageType.Integer, StorageType.Double):
                        numeric = True
                    break
            except:
                continue

        filter_op.Items.Clear()
        if numeric:
            ops = ["equals", "does not equal", "is greater than",
                   "is greater than or equal to", "is less than",
                   "is less than or equal to"]
        else:
            ops = ["equals", "does not equal", "contains", "does not contain",
                   "begins with", "does not begin with", "ends with", "does not end with"]
        for op in ops:
            filter_op.Items.Add(op)
        if filter_op.Items.Count > 0:
            filter_op.SelectedIndex = 0

        filter_val.Items.Clear()
        for v in get_param_values(elements, param_name):
            filter_val.Items.Add(v)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_scope_changed(sender, args):
        refresh_category_list()
    rb_whole.Checked += on_scope_changed
    rb_view.Checked += on_scope_changed
    rb_selection.Checked += on_scope_changed

    def on_select_all(sender, args):
        for item in category_list.Items:
            chk = item.Content
            chk.IsChecked = True
    def on_select_none(sender, args):
        for item in category_list.Items:
            chk = item.Content
            chk.IsChecked = False
    btn_all_cats.Click += on_select_all
    btn_none_cats.Click += on_select_none
    btn_refresh.Click += refresh_params

    def on_load_params(sender, args):
        cats = get_selected_categories()
        if not cats:
            cat_status.Text = "Please select at least one category."
            return
        cat_status.Text = "Loading elements..."
        scope = "whole" if rb_whole.IsChecked else "view" if rb_view.IsChecked else "selection"
        elements = get_elements_by_categories(cats, scope)
        if not elements:
            cat_status.Text = "No elements found in selected categories."
            return

        state["filtered_elements"] = elements
        state["all_params_cache"] = get_common_params(elements)
        filter_param.Items.Clear()
        for p in state["all_params_cache"]:
            filter_param.Items.Add(p)
        cat_status.Text = "Loaded {0} parameters from {1} elements.".format(len(state["all_params_cache"]), len(elements))

        # Build preview items (reset filter gate so realtime doesn't fire on fresh load)
        state["filter_applied_once"] = False
        preview_items = build_preview_items(elements)
        state["preview_items"] = preview_items
        refresh_preview_display()

    btn_load_params.Click += on_load_params

    def on_confirm_filter_param(sender, args):
        current_text = filter_param.Text.strip()
        if not (current_text and state["filtered_elements"] and current_text in state["all_params_cache"]):
            return
        if state.get("_last_filter_param") == current_text:
            return   # unchanged — don't reset operator/value the user set
        state["_last_filter_param"] = current_text
        update_operators_and_values(current_text, state["filtered_elements"])
        update_live_filter_preview()
    # Commit on dropdown close (pick) or focus leave (typed) — never on scroll.
    filter_param.DropDownClosed += on_confirm_filter_param
    filter_param.LostFocus      += on_confirm_filter_param

    def on_filter_key_up(sender, args):
        """Trigger debounced real-time filter on key input."""
        filter_debounce.reset()

    def on_filter_value_changed(sender, args):
        """Trigger debounced real-time filter on value changes."""
        filter_debounce.reset()

    filter_param.KeyUp += on_filter_key_up
    filter_op.SelectionChanged += on_filter_value_changed
    filter_val.KeyUp += on_filter_key_up

    def on_apply_filter(sender, args):
        if not state["filtered_elements"]:
            filter_status.Text = "Please load parameters first."
            return
        param_name = filter_param.Text
        if not param_name:
            filter_status.Text = "Please select a parameter."
            return

        operator = str(filter_op.SelectedItem) if filter_op.SelectedItem else "contains"
        value = filter_val.Text
        filter_status.Text = "Applying filter..."
        state["filter_applied_once"] = True

        filtered_ids = filter_elements(state["filtered_elements"], param_name, operator, value)
        state["filtered_ids"] = filtered_ids

        # InFilter controls table visibility; IsSelected marks the checkbox
        filtered_set = set(filtered_ids)
        for item in state["preview_items"]:
            matched = item.Element.Id in filtered_set
            item.InFilter   = matched
            item.IsSelected = matched
        refresh_preview_display()

        msg = "Filtered: {0} elements.".format(len(filtered_ids))
        filter_status.Text = msg
        if filtered_ids:
            filtered_elems = [item.Element for item in state["preview_items"] if item.InFilter]
            edit_params = get_common_params(filtered_elems, writable_only=True)
            edit_param.Items.Clear()
            for p in edit_params:
                edit_param.Items.Add(p)
            if edit_params:
                edit_param.SelectedIndex = 0
            btn_select_elems.IsEnabled = True
            edit_status.Text = "Ready to edit {0} elements.".format(len(filtered_ids))
            set_status("{0} elements filtered".format(len(filtered_ids)))
        else:
            edit_param.Items.Clear()
            edit_status.Text = "No elements match the filter."
            btn_select_elems.IsEnabled = False
            filter_status.Text = "No elements match the filter. Try different values."
            set_status("No Matches Filtered", is_error=True)

    btn_apply_filter.Click += on_apply_filter

    def on_select_elements(sender, args):
        # Only the checked rows, matching what Execute would edit.
        target_ids = [item.Element.Id for item in state["preview_items"]
                      if item.InFilter and item.IsSelected]
        if not target_ids:
            set_status("No rows are checked.", is_error=True)
            return
        try:
            net_list = List[ElementId]()
            for eid in target_ids:
                net_list.Add(eid)
            uidoc.Selection.SetElementIds(net_list)
            set_status("Selected {0} checked element(s) in Revit".format(len(target_ids)))
        except Exception as ex:
            set_status("Selection failed: " + str(ex), is_error=True)
    btn_select_elems.Click += on_select_elements

    def on_confirm_edit(sender, args):
        current_text = edit_param.Text.strip()
        if not (current_text and state["filtered_ids"]):
            return
        if state.get("_last_edit_param") != current_text:
            state["_last_edit_param"] = current_text
            edit_status.Text = "Ready to edit parameter: " + current_text
            try:
                filtered_elems = [doc.GetElement(eid) for eid in state["filtered_ids"] if doc.GetElement(eid)]
                vals = get_param_values(filtered_elems, current_text)
                edit_val1.Items.Clear()
                for v in vals:
                    edit_val1.Items.Add(v)
            except:
                pass
        update_live_edit_preview()
    edit_param.DropDownClosed += on_confirm_edit
    edit_param.LostFocus      += on_confirm_edit

    # Live edit preview on field changes
    def on_edit_field_changed(sender, args):
        update_live_edit_preview()

    def on_edit_op_changed(sender, args):
        """Replace → reveal the replace field; Delete → disable the value combo."""
        op = str(edit_op.SelectedItem) if edit_op.SelectedItem else ""
        is_replace = (op == "Replace")
        is_delete  = (op == "Delete")
        vis = Visibility.Visible if is_replace else Visibility.Collapsed
        lbl_replace.Visibility = vis
        edit_val2.Visibility   = vis
        edit_val1.IsEnabled    = not is_delete
        update_live_edit_preview()

    edit_op.SelectionChanged += on_edit_op_changed
    edit_val1.KeyUp += on_edit_field_changed
    edit_val2.TextChanged += on_edit_field_changed

    def on_execute(sender, args):
        if not state["filtered_ids"]:
            edit_status.Text = "Apply filter first."
            return
        if not edit_param.Text:
            edit_status.Text = "Choose a parameter to edit."
            return

        # Only edit rows the user left CHECKED (IsSelected) among the matches.
        target_ids = [item.Element.Id for item in state["preview_items"]
                      if item.InFilter and item.IsSelected]
        if not target_ids:
            edit_status.Text = "No rows are checked — tick the rows to edit."
            set_status("Nothing checked to edit", is_error=True)
            return

        param_name = edit_param.Text
        operation = str(edit_op.SelectedItem) if edit_op.SelectedItem else "Set"
        val1 = edit_val1.Text
        val2 = edit_val2.Text

        btn_execute.IsEnabled = False
        edit_status.Text = "Modifying {0} checked element(s)...".format(len(target_ids))
        modified, errors = modify_elements(target_ids, param_name, operation, val1, val2)

        if modified > 0:
            edit_status.Text = "Modified {0} elements.".format(modified)
            if errors:
                edit_status.Text += " ({0} partial errors)".format(len(errors))
            set_status("Modified {0} elements".format(modified))
        else:
            err_str = "; ".join(errors[:3]) if errors else "Unknown error"
            edit_status.Text = "No elements modified. Errors: " + err_str
            set_status("No elements modified", is_error=True)
        btn_execute.IsEnabled = True
    btn_execute.Click += on_execute

    edit_op.Items.Add("Prefix")
    edit_op.Items.Add("Suffix")
    edit_op.Items.Add("Replace")
    edit_op.Items.Add("Set")
    edit_op.Items.Add("Delete")
    edit_op.SelectedIndex = 3

    # The select column's CheckBox is bound to the DataGridRow's native
    # .IsSelected (a real .NET bool — reliable, unlike binding a Python bool).
    # Grid selection is the source of truth; mirror it into each PreviewItem.
    def on_grid_selection_changed(sender, args):
        if state.get("_refreshing"):
            return
        sel = set()
        for it in preview_list.SelectedItems:
            sel.add(it)
        for item in state["preview_items"]:
            if item.InFilter:
                item.IsSelected = item in sel
        update_preview_info()
    preview_list.SelectionChanged += on_grid_selection_changed

    # Checkbox click → toggle THAT row's membership ourselves and mark handled,
    # so the DataGrid's default (replace-)select gesture never runs and clears
    # the other checks. Row-body clicks are swallowed entirely.
    def on_grid_mousedown(sender, args):
        dep = args.OriginalSource
        chk = None
        while dep is not None:
            if isinstance(dep, CheckBox):
                chk = dep
                break
            if isinstance(dep, DataGridCell):
                break
            try:
                dep = VisualTreeHelper.GetParent(dep)
            except Exception:
                break
        if chk is not None:
            item = chk.DataContext
            if item is not None:
                if preview_list.SelectedItems.Contains(item):
                    preview_list.SelectedItems.Remove(item)
                else:
                    preview_list.SelectedItems.Add(item)
            args.Handled = True             # suppress the grid's replace-select
            return
        # plain click on a data cell → no selection change
        dep = args.OriginalSource
        while dep is not None:
            if isinstance(dep, DataGridCell):
                args.Handled = True
                return
            try:
                dep = VisualTreeHelper.GetParent(dep)
            except Exception:
                break
    preview_list.PreviewMouseLeftButtonDown += on_grid_mousedown

    # Row selection buttons
    def on_select_all_rows(sender, args):
        for item in state["preview_items"]:
            if item.InFilter:
                item.IsSelected = True
        refresh_preview_display()
    btn_select_all_rows.Click += on_select_all_rows

    def on_deselect_all_rows(sender, args):
        for item in state["preview_items"]:
            if item.InFilter:
                item.IsSelected = False
        refresh_preview_display()
    btn_deselect_all_rows.Click += on_deselect_all_rows

    def on_close(sender, args):
        state["filtered_elements"] = []
        state["filtered_ids"] = []
        state["all_params_cache"] = []
        window.Close()
    btn_close.Click += on_close

    # Initial load
    refresh_category_list()
    set_status("Ready")

    # Anchor to Revit main window (CenterOwner + prevents dialog behind Revit)
    try:
        helper = WindowInteropHelper(window)
        helper.Owner = __revit__.MainWindowHandle
    except Exception:
        pass

    # Show dialog
    window.ShowDialog()

# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    run_ui()
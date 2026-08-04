#! python3
# -*- coding: utf-8 -*-
# pyRevit script - OneFilterParameter (CPython 3) — MODELESS
# AnonGee BIM Tools v3.0 — theme loaded from shared Resources/
#
# Converted from modal (ShowDialog) to modeless (Show) using the AnonGee
# modeless reference pattern (§12.8):
#   • window.Show()  -> runs WPF on a separate thread.
#   • FilterParameterHandler (IExternalEventHandler) -> all Revit DB/UI work
#     inside Execute(), queued via ExternalEvent.Raise() from the WPF thread.
#   • A serialized request queue guarantees one Revit-thread request at a time,
#     in order — rapid typing can't swallow a button request.
#   • The handler class + live window ref live in a dedicated session-state
#     module kept in sys.modules. The CPython 3 persistent engine re-executes
#     this script on every button press, so:
#       - Python.NET 3 emits __namespace__ interface subclasses as real CLR
#         types; re-running the class statement after the first press raises
#         "Duplicate type name within an assembly". The class is therefore
#         defined exactly once per Revit session.
#       - The window ref survives run() returning, so re-launch activates the
#         existing window instead of stacking a new one.
#   * No pyRevit modules are imported — Autodesk.* + System.* only.
#
# Visuals are unchanged: ui.xaml is not modified; all control lookups, status
# strings, operator sets, DataGrid checkbox/row-selection behavior and the
# footer _StatusLine proxies are ported verbatim. The only internal data
# change: PreviewItem stores an int id (Revit objects can't cross threads).

import os
import sys
import types
import clr
import System

# Standard Revit API imports
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

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
from System import String as NetString, TimeSpan, Action
from System.Windows.Threading import DispatcherPriority


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


# ======================================================================
# PREVIEW DATA CLASS — simple __slots__ for reliable WPF DataGrid binding
# ======================================================================
class PreviewItem:
    """One row in the live preview DataGrid. __slots__ is required for
    Python.NET 3 to expose attributes as bindable properties.

    Stores an int id (IdInt) instead of the Revit Element — Revit objects
    cannot cross threads in the modeless architecture. The bound grid columns
    (ElementId, FamilyName, TypeName, FilterValue, EditPreview) are unchanged.
    """
    __slots__ = ['ElementId', 'IdInt', 'FamilyName', 'TypeName',
                 'FilterValue', 'EditPreview', 'IsSelected', 'InFilter']

    def __init__(self, id_int, family_name, type_name):
        self.ElementId   = str(id_int)
        self.IdInt       = id_int
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
# PERSISTENT SESSION STATE
# ======================================================================
# pyRevit's persistent CPython 3 engine re-executes this script module on
# every button press, but the interpreter, sys.modules and the CLR AppDomain
# outlive any single execution. Two consequences are handled here:
#
#   1. Python.NET 3 emits a __namespace__ interface subclass (below) as a
#      real CLR type in a dynamic assembly. Re-running the class statement
#      on a later press tries to re-emit the same type name and raises
#      "Duplicate type name within an assembly". The class is therefore
#      defined exactly once per Revit session and cached here.
#
#   2. The live window would otherwise be GC'd / forgotten when run()
#      returns and the ephemeral script namespace is dropped. Holding the
#      reference here lets a re-launch activate the existing window instead
#      of stacking a second one.
_STATE_MODULE = "AnonGee_FilterParameterState"
_state = sys.modules.get(_STATE_MODULE)
if _state is None:
    _state = types.ModuleType(_STATE_MODULE)
    _state.handler_cls = None
    _state.window_ref = None
    sys.modules[_STATE_MODULE] = _state


# ======================================================================
# REVIT-THREAD HANDLER
# ======================================================================
if _state.handler_cls is None:
    # Defined only on the FIRST execution of this script per Revit session.
    # See the session-state comment above for why this guard is mandatory.
    class FilterParameterHandler(IExternalEventHandler):
        """
        Runs on Revit's primary thread. The WPF thread writes `data`, Raise()
        queues Execute(), and results are marshalled back to the WPF thread via
        the window's Dispatcher.
        """

        # __namespace__ is required by Python.NET 3 to build a real derived CLR
        # type from a .NET interface -- without it, FilterParameterHandler()
        # routes to the interface's one-arg cast and raises
        # "TypeError: interface takes exactly one argument" (see
        # anongee_toolkit/cad2bim/builders/txn_failures.py, WarningSwallower).
        __namespace__ = "AnonGee"

        # NOTE — deliberately no __init__ here.
        # Defining __init__ on a Python class that inherits a Revit interface
        # trips pythonnet's interface __new__ in the CPython 3 engine and raises
        # "TypeError: interface takes exactly one argument" at instantiation.
        # Per-instance state is reset explicitly in run() right after
        # construction — same behaviour, no interface trap.
        data = {}          # per-instance state dict (rebound in run())
        app = None         # FilterParameterApp — set after it is created
        _elements = []     # Revit elements loaded for the current session
        _id_to_elem = {}   # id_int -> Element

        # ── IExternalEventHandler contract ────────────────────────────
        def Execute(self, app):
            req = self.data.get("request")
            uidoc = app.ActiveUIDocument
            if req:
                self._dispatch(req, uidoc)
            self.data["request"] = None

        def GetName(self):
            return "AnonGee_FilterParameterHandler"

        def _dispatch(self, req, uidoc):
            d = self.data.get("data", {})
            if req == "load_categories":
                self._load_categories(d, uidoc)
            elif req == "load_elements":
                self._load_elements(d, uidoc)
            elif req == "filter_param_info":
                self._filter_param_info(d, uidoc)
            elif req == "apply_filter":
                self._apply_filter(d, uidoc)
            elif req == "filter_only":
                self._filter_only(d, uidoc)
            elif req == "refresh_values":
                self._refresh_values(d, uidoc)
            elif req == "edit_param_info":
                self._edit_param_info(d, uidoc)
            elif req == "edit_values_map":
                self._edit_values_map(d, uidoc)
            elif req == "select_elements":
                self._select_elements(d, uidoc)
            elif req == "execute_edit":
                self._execute_edit(d, uidoc)

        # ── WPF-thread marshal ────────────────────────────────────────
        def _marshal_to_ui(self):
            """Queue the UI-update callback onto the window's WPF dispatcher."""
            try:
                self.app.window.Dispatcher.BeginInvoke(
                    DispatcherPriority.Normal, Action(self.app._on_handler_done))
            except Exception:
                pass

        # ── Shared Revit helpers ──────────────────────────────────────
        def _lookup_param(self, doc, elem, name):
            try:
                param = elem.LookupParameter(name)
                if param is None:
                    tid = elem.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te:
                            param = te.LookupParameter(name)
                return param
            except Exception:
                return None

        def _get_param_val_str(self, doc, param, store_numeric=False, val_to_num=None):
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
            if store_numeric and val_str is not None and val_to_num is not None:
                if st == StorageType.Double:
                    val_to_num[val_str] = param.AsDouble()
                elif st == StorageType.Integer:
                    val_to_num[val_str] = float(param.AsInteger())
            return val_str if val_str is not None else ""

        def _get_categories_by_scope(self, doc, uidoc, scope):
            cats = set()
            try:
                if scope == "whole":
                    for c in doc.Settings.Categories:
                        if c.CategoryType == CategoryType.Model and c.AllowsBoundParameters:
                            try:
                                cat_filter = ElementCategoryFilter(c.Id)
                                if FilteredElementCollector(doc).WherePasses(cat_filter).WhereElementIsNotElementType().GetElementCount() > 0:
                                    cats.add(c.Name)
                            except:
                                pass
                elif scope == "view":
                    view = doc.ActiveView
                    collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
                    for e in collector:
                        if e.Category:
                            cats.add(e.Category.Name)
                elif scope == "selection":
                    sel = uidoc.Selection.GetElementIds()
                    for id in sel:
                        elem = doc.GetElement(id)
                        if elem and elem.Category:
                            cats.add(elem.Category.Name)
                return sorted(cats)
            except Exception:
                return []

        def _get_elements_by_categories(self, doc, uidoc, category_names, scope):
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

        def _get_common_params(self, doc, elements, writable_only=False, string_only=False):
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

        def _get_param_values(self, doc, elements, param_name):
            values = set()
            val_to_num = {}
            for e in elements:
                try:
                    param = self._lookup_param(doc, e, param_name)
                    if param is not None:
                        val_str = self._get_param_val_str(doc, param, store_numeric=True, val_to_num=val_to_num)
                        if val_str is not None:
                            values.add(val_str)
                except:
                    continue
            return sorted(values), val_to_num

        def _extract_numeric(self, text):
            if not text: return None
            s = str(text).replace(" ", "")
            last_dot = s.rfind('.')
            last_comma = s.rfind(',')
            if last_comma > last_dot:
                s = s.replace('.', '').replace(',', '.')
            else:
                s = s.replace(',', '')
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

        def _filter_elements(self, doc, elements, param_name, operator, value, val_to_num):
            filtered_ids = []
            if value is None:
                value = ""
            for e in elements:
                try:
                    param = self._lookup_param(doc, e, param_name)
                    if param is None:
                        continue
                    cur_val_str = self._get_param_val_str(doc, param) or ""
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
                            if value in val_to_num:
                                num_val = val_to_num[value]
                            else:
                                cur_num_ext = self._extract_numeric(cur_val_str)
                                num_val_ext = self._extract_numeric(value)
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

        def _get_element_family_name(self, doc, elem):
            try:
                sym = elem.Symbol
                if sym:
                    fam = sym.Family
                    if fam: return fam.Name
            except:
                pass
            try:
                tid = elem.GetTypeId()
                if tid and tid != ElementId.InvalidElementId:
                    te = doc.GetElement(tid)
                    if te: return te.Name
            except:
                pass
            try:
                if elem.Category: return elem.Category.Name
            except:
                pass
            return "N/A"

        def _get_element_type_name(self, doc, elem):
            try:
                tid = elem.GetTypeId()
                if tid and tid != ElementId.InvalidElementId:
                    te = doc.GetElement(tid)
                    if te: return te.Name
            except:
                pass
            return "N/A"

        def _id_int(self, eid):
            return int(getattr(eid, "Value", getattr(eid, "IntegerValue", -1)))

        # ── Request handlers ──────────────────────────────────────────
        def _load_categories(self, d, uidoc):
            doc = uidoc.Document
            scope = d.get("scope", "whole")
            result = {"request": "load_categories",
                      "categories": self._get_categories_by_scope(doc, uidoc, scope)}
            self.data["result"] = result
            self._marshal_to_ui()

        def _load_elements(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "load_elements"}
            if doc is None:
                result["error"] = "Open a Revit model to load elements."
            else:
                categories = d.get("categories", [])
                scope = d.get("scope", "whole")
                elements = self._get_elements_by_categories(doc, uidoc, categories, scope)
                if not elements:
                    result["error"] = "No elements found in selected categories."
                else:
                    self._elements = elements
                    self._id_to_elem = {}
                    items = []
                    for e in elements:
                        eid_val = self._id_int(e.Id)
                        self._id_to_elem[eid_val] = e
                        items.append({
                            "id": eid_val,
                            "family": self._get_element_family_name(doc, e),
                            "type": self._get_element_type_name(doc, e),
                        })
                    result["elements"] = items
                    result["params"] = self._get_common_params(doc, elements)
            self.data["result"] = result
            self._marshal_to_ui()

        def _filter_param_info(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "filter_param_info"}
            param_name = d.get("param_name", "")
            id_ints = d.get("id_ints", [])
            elements = [self._id_to_elem[i] for i in id_ints if i in self._id_to_elem]
            numeric = False
            for e in elements[:20]:
                try:
                    param = self._lookup_param(doc, e, param_name)
                    if param:
                        st = param.StorageType
                        if st in (StorageType.Integer, StorageType.Double):
                            numeric = True
                        break
                except:
                    continue
            values, _ = self._get_param_values(doc, elements, param_name)
            result["numeric"] = numeric
            result["values"] = values
            fv = {}
            for e in elements:
                iid = self._id_int(e.Id)
                try:
                    param = self._lookup_param(doc, e, param_name)
                    if param:
                        fv[iid] = self._get_param_val_str(doc, param) or ""
                    else:
                        fv[iid] = "-"
                except:
                    fv[iid] = "?"
            result["filter_values"] = fv
            self.data["result"] = result
            self._marshal_to_ui()

        def _apply_filter(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "apply_filter"}
            param_name = d.get("param_name", "")
            operator = d.get("operator", "contains")
            value = d.get("value", "")
            id_ints = d.get("id_ints", [])
            elements = [self._id_to_elem[i] for i in id_ints if i in self._id_to_elem]
            _, val_to_num = self._get_param_values(doc, elements, param_name)
            filtered_ids = self._filter_elements(doc, elements, param_name, operator, value, val_to_num)
            result["filtered_ids"] = [self._id_int(eid) for eid in filtered_ids]
            filtered_elems = [self._id_to_elem[i] for i in result["filtered_ids"] if i in self._id_to_elem]
            result["edit_params"] = self._get_common_params(doc, filtered_elems, writable_only=True)
            self.data["result"] = result
            self._marshal_to_ui()

        def _filter_only(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "filter_only"}
            param_name = d.get("param_name", "")
            operator = d.get("operator", "contains")
            value = d.get("value", "")
            id_ints = d.get("id_ints", [])
            elements = [self._id_to_elem[i] for i in id_ints if i in self._id_to_elem]
            _, val_to_num = self._get_param_values(doc, elements, param_name)
            filtered_ids = self._filter_elements(doc, elements, param_name, operator, value, val_to_num)
            result["filtered_ids"] = [self._id_int(eid) for eid in filtered_ids]
            self.data["result"] = result
            self._marshal_to_ui()

        def _refresh_values(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "refresh_values"}
            fp = d.get("filter_param", "")
            ep = d.get("edit_param", "")
            filter_id_ints = d.get("filter_id_ints", [])
            edit_id_ints = d.get("edit_id_ints", [])
            if fp:
                elems = [self._id_to_elem[i] for i in filter_id_ints if i in self._id_to_elem]
                vals, _ = self._get_param_values(doc, elems, fp)
                result["filter_values"] = vals
            if ep:
                elems = [self._id_to_elem[i] for i in edit_id_ints if i in self._id_to_elem]
                vals, _ = self._get_param_values(doc, elems, ep)
                result["edit_values"] = vals
            self.data["result"] = result
            self._marshal_to_ui()

        def _edit_param_info(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "edit_param_info"}
            param_name = d.get("param_name", "")
            id_ints = d.get("id_ints", [])
            elements = [self._id_to_elem[i] for i in id_ints if i in self._id_to_elem]
            vals, _ = self._get_param_values(doc, elements, param_name)
            result["values"] = vals
            self.data["result"] = result
            self._marshal_to_ui()

        def _edit_values_map(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "edit_values_map"}
            param_name = d.get("param_name", "")
            operation = d.get("operation", "Set")
            val1 = d.get("val1", "")
            val2 = d.get("val2", "")
            id_ints = d.get("id_ints", [])
            selected_ints = d.get("selected_ints", [])
            previews = {}
            for i in id_ints:
                if i not in selected_ints:
                    previews[i] = "(skip)"
                    continue
                elem = self._id_to_elem.get(i)
                if elem is None:
                    previews[i] = "?"
                    continue
                try:
                    param = self._lookup_param(doc, elem, param_name)
                    if param:
                        cur_val = self._get_param_val_str(doc, param) or ""
                        st = param.StorageType
                        if operation == "Delete":
                            previews[i] = "(deleted)"
                        elif operation == "Prefix":
                            previews[i] = val1 + cur_val
                        elif operation == "Suffix":
                            previews[i] = cur_val + val1
                        elif operation == "Replace":
                            previews[i] = cur_val.replace(val1, val2) if val1 else cur_val
                        elif operation == "Set":
                            previews[i] = val1
                        else:
                            previews[i] = cur_val
                    else:
                        previews[i] = "N/A"
                except:
                    previews[i] = "?"
            result["previews"] = previews
            self.data["result"] = result
            self._marshal_to_ui()

        def _select_elements(self, d, uidoc):
            result = {"request": "select_elements"}
            id_ints = d.get("id_ints", [])
            try:
                net_list = List[ElementId]()
                for i in id_ints:
                    net_list.Add(ElementId(System.Int64(i)))
                uidoc.Selection.SetElementIds(net_list)
                result["selected"] = len(id_ints)
            except Exception as ex:
                result["error"] = "Selection failed: " + str(ex)
            self.data["result"] = result
            self._marshal_to_ui()

        def _execute_edit(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "execute_edit"}
            id_ints = d.get("id_ints", [])
            param_name = d.get("param_name", "")
            operation = d.get("operation", "Set")
            val1 = d.get("val1", "")
            val2 = d.get("val2", "")
            modified = 0
            errors = []
            if not id_ints:
                errors.append("No elements selected.")
            else:
                t = Transaction(doc, "OneParameter Batch Edit")
                t.Start()
                try:
                    processed_types = set()
                    for i in id_ints:
                        try:
                            elem = self._id_to_elem.get(i)
                            if elem is None:
                                elem = doc.GetElement(ElementId(System.Int64(i)))
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
                                errors.append("Param '{0}' not found/read-only on {1}".format(param_name, str(i)))
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
                                else: errors.append("Cannot delete on {0}".format(str(i))); continue
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
                                        if vl in ("yes", "true", "1", "on"): param.Set(System.Int32(1))
                                        elif vl in ("no", "false", "0", "off"): param.Set(System.Int32(0))
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
            result["modified"] = modified
            result["errors"] = errors
            self.data["result"] = result
            self._marshal_to_ui()

    _state.handler_cls = FilterParameterHandler
else:
    # Later press: the Python.NET 3 CLR type is already emitted and cached —
    # reuse it instead of re-running the class statement (which would raise
    # "Duplicate type name within an assembly").
    FilterParameterHandler = _state.handler_cls


# ======================================================================
# WPF APP — MODELESS
# ======================================================================
class FilterParameterApp(object):
    """The modeless window. Fresh instance per launch — subscriptions are
    never made at module scope (§12.9.2 handler accumulation)."""

    def __init__(self, xaml_path, handler, ext_event):
        self.handler = handler
        self.ext_event = ext_event
        self._queue = []              # serialized request queue
        self._busy = False
        self._current_callback = None
        self._filter_debounce = None  # created lazily on the WPF thread

        xaml = load_xaml_window()
        bytes = Encoding.UTF8.GetBytes(xaml)
        stream = MemoryStream(bytes)
        self.window = XamlReader.Load(stream)
        stream.Close()

        # Find controls
        self.header_title      = self.window.FindName("header_title")
        self.btn_refresh       = self.window.FindName("btn_refresh")
        self.category_list     = self.window.FindName("category_list")
        self.btn_all_cats      = self.window.FindName("btn_all_cats")
        self.btn_none_cats     = self.window.FindName("btn_none_cats")
        self.btn_load_params   = self.window.FindName("btn_load_params")

        self.rb_whole          = self.window.FindName("rb_whole")
        self.rb_view           = self.window.FindName("rb_view")
        self.rb_selection      = self.window.FindName("rb_selection")

        self.filter_param      = self.window.FindName("filter_param")
        self.filter_op         = self.window.FindName("filter_op")
        self.filter_val        = self.window.FindName("filter_val")
        self.btn_apply_filter  = self.window.FindName("btn_apply_filter")
        self.btn_select_elems  = self.window.FindName("btn_select_elems")

        self.edit_param        = self.window.FindName("edit_param")
        self.edit_op           = self.window.FindName("edit_op")
        self.edit_val1         = self.window.FindName("edit_val1")
        self.edit_val2         = self.window.FindName("edit_val2")
        self.lbl_replace       = self.window.FindName("lbl_replace")
        self.btn_execute       = self.window.FindName("btn_execute")

        self.status_badge      = self.window.FindName("status_badge")
        self.status_textblock  = self.window.FindName("status_textblock")
        self.error_badge       = self.window.FindName("error_badge")
        self.error_text        = self.window.FindName("error_text")
        self.btn_close         = self.window.FindName("btn_close")

        # Live preview controls
        self.preview_list      = self.window.FindName("preview_list")
        self.preview_info      = self.window.FindName("preview_info")
        self.btn_select_all_rows  = self.window.FindName("btn_select_all_rows")
        self.btn_deselect_all_rows = self.window.FindName("btn_deselect_all_rows")

        # State Variables
        self.state = {
            "filtered_ids": [],
            "all_params_cache": [],
            "val_to_num": {},
            "preview_items": [],       # List[PreviewItem]
            "filter_param_name": "",   # Current filter parameter name
            "edit_param_name": "",     # Current edit parameter name
            "filter_applied_once": False, # Gate: realtime filter only runs after Apply Filter clicked
            "_refreshing": False,         # Guard against reentrant events during refresh
            "last_click_index": -1,       # Tracks last clicked row for Shift+click range selection
            "_last_filter_param": None,
            "_last_edit_param": None,
        }

        # The three section statuses now live in the footer status bar: assigning
        # `.Text` on these proxies routes the message to set_status().
        app_self = self
        class _StatusLine(object):
            __slots__ = ['_t']
            def __init__(self):
                self._t = ""
            def _get(self):
                return self._t
            def _set(self, v):
                self._t = v
                app_self.set_status(v)
            Text = property(_get, _set)

        self.cat_status    = _StatusLine()
        self.filter_status = _StatusLine()
        self.edit_status   = _StatusLine()

        self.wire_events()

    # ── UI wiring ─────────────────────────────────────────────────────
    def wire_events(self):
        self.rb_whole.Checked += self.on_scope_changed
        self.rb_view.Checked += self.on_scope_changed
        self.rb_selection.Checked += self.on_scope_changed
        self.btn_all_cats.Click += self.on_select_all
        self.btn_none_cats.Click += self.on_select_none
        self.btn_refresh.Click += self.refresh_params
        self.btn_load_params.Click += self.on_load_params
        self.filter_param.DropDownClosed += self.on_confirm_filter_param
        self.filter_param.LostFocus += self.on_confirm_filter_param
        self.filter_param.KeyUp += self.on_filter_key_up
        self.filter_op.SelectionChanged += self.on_filter_value_changed
        self.filter_val.KeyUp += self.on_filter_key_up
        self.btn_apply_filter.Click += self.on_apply_filter
        self.btn_select_elems.Click += self.on_select_elements
        self.edit_param.DropDownClosed += self.on_confirm_edit
        self.edit_param.LostFocus += self.on_confirm_edit
        self.edit_op.SelectionChanged += self.on_edit_op_changed
        self.edit_val1.KeyUp += self.on_edit_field_changed
        self.edit_val2.TextChanged += self.on_edit_field_changed
        self.btn_execute.Click += self.on_execute
        self.preview_list.SelectionChanged += self.on_grid_selection_changed
        self.preview_list.PreviewMouseLeftButtonDown += self.on_grid_mousedown
        self.btn_select_all_rows.Click += self.on_select_all_rows
        self.btn_deselect_all_rows.Click += self.on_deselect_all_rows
        self.btn_close.Click += self.on_close
        self.window.Closed += self.on_closed

        self.edit_op.Items.Add("Prefix")
        self.edit_op.Items.Add("Suffix")
        self.edit_op.Items.Add("Replace")
        self.edit_op.Items.Add("Set")
        self.edit_op.Items.Add("Delete")
        self.edit_op.SelectedIndex = 3

    # ── Serialized request queue ──────────────────────────────────────
    def _enqueue(self, req, data, callback=None):
        self._queue.append((req, data, callback))
        self._pump()

    def _pump(self):
        if self._busy or not self._queue:
            return
        self._busy = True
        req, data, callback = self._queue.pop(0)
        self._current_callback = callback
        self.handler.data["request"] = req
        self.handler.data["data"] = data
        try:
            self.ext_event.Raise()
        except Exception as e:
            self._busy = False
            self._current_callback = None
            self.set_status("Could not raise event: {}".format(e), True)
            self._pump()

    def _on_handler_done(self):
        result = self.handler.data.get("result") or {}
        self.handler.data["result"] = None
        self._busy = False
        callback = self._current_callback
        self._current_callback = None
        if callback:
            try:
                callback(result)
            except Exception:
                pass
        self._pump()

    # ── Debounce (lazy — created on the WPF thread) ──────────────────
    def _get_filter_debounce(self):
        if self._filter_debounce is None:
            self._filter_debounce = DebounceTimer(self.realtime_filter_update, 300)
        return self._filter_debounce

    # ── UI helpers ────────────────────────────────────────────────────
    def set_status(self, message, is_error=False):
        self.status_textblock.Text = message
        if not is_error:
            self.status_badge.Visibility = Visibility.Visible
            self.error_badge.Visibility = Visibility.Collapsed
        else:
            self.status_badge.Visibility = Visibility.Collapsed
            self.error_badge.Visibility = Visibility.Visible
        self.error_text.Text = message if is_error else ""

    def _repopulate_values(self, combo, values):
        """Refresh the dropdown options without touching the current input."""
        prev = combo.Text
        combo.Items.Clear()
        for v in values:
            combo.Items.Add(v)
        combo.Text = prev

    def get_selected_categories(self):
        selected = []
        for item in self.category_list.Items:
            chk = item.Content
            if chk.IsChecked:
                selected.append(str(chk.Content))
        return selected

    def update_preview_info(self):
        total   = len(self.state["preview_items"])
        visible = len([i for i in self.state["preview_items"] if i.InFilter])
        checked = len([i for i in self.state["preview_items"] if i.InFilter and i.IsSelected])
        base = "{0} elements".format(total) if visible == total \
            else "{0} / {1} matched".format(visible, total)
        self.preview_info.Text = "{0}  -  {1} checked".format(base, checked)

    def refresh_preview_display(self):
        """Populate the DataGrid — only rows where InFilter=True are shown."""
        self.state["_refreshing"] = True
        try:
            items = ArrayList()
            for item in self.state["preview_items"]:
                if item.InFilter:
                    items.Add(item)
            self.preview_list.ItemsSource = None
            self.preview_list.ItemsSource = items
            # Re-apply the native row selection (= the checkbox state) from each
            # item's IsSelected, which survives the rebuild on the Python side.
            self.preview_list.SelectedItems.Clear()
            for item in self.state["preview_items"]:
                if item.InFilter and item.IsSelected:
                    self.preview_list.SelectedItems.Add(item)
            self.update_preview_info()
        finally:
            self.state["_refreshing"] = False

    # ── Category / scope ──────────────────────────────────────────────
    def refresh_category_list(self):
        self.category_list.Items.Clear()
        scope = "whole" if self.rb_whole.IsChecked else "view" if self.rb_view.IsChecked else "selection"
        self._enqueue("load_categories", {"scope": scope}, self._on_categories_loaded)

    def _on_categories_loaded(self, result):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        self.category_list.Items.Clear()
        for cat_name in result.get("categories", []):
            item = ListBoxItem()
            chk = CheckBox()
            chk.Content = cat_name
            chk.IsChecked = False
            item.Content = chk
            item.Tag = cat_name
            self.category_list.Items.Add(item)

    def on_scope_changed(self, sender, args):
        self.refresh_category_list()

    def on_select_all(self, sender, args):
        for item in self.category_list.Items:
            chk = item.Content
            chk.IsChecked = True

    def on_select_none(self, sender, args):
        for item in self.category_list.Items:
            chk = item.Content
            chk.IsChecked = False

    # ── Load elements ─────────────────────────────────────────────────
    def on_load_params(self, sender, args):
        cats = self.get_selected_categories()
        if not cats:
            self.cat_status.Text = "Please select at least one category."
            return
        self.cat_status.Text = "Loading elements..."
        scope = "whole" if self.rb_whole.IsChecked else "view" if self.rb_view.IsChecked else "selection"
        self._enqueue("load_elements", {"categories": cats, "scope": scope}, self._on_elements_loaded)

    def _on_elements_loaded(self, result):
        if "error" in result:
            self.cat_status.Text = result["error"]
            return
        elements = result.get("elements", [])
        params = result.get("params", [])
        self.state["all_params_cache"] = params
        self.filter_param.Items.Clear()
        for p in params:
            self.filter_param.Items.Add(p)
        self.cat_status.Text = "Loaded {0} parameters from {1} elements.".format(len(params), len(elements))

        # Build preview items (reset filter gate so realtime doesn't fire on fresh load)
        self.state["filter_applied_once"] = False
        self.state["filtered_ids"] = []
        self.state["_last_filter_param"] = None
        self.state["_last_edit_param"] = None
        self.state["preview_items"] = [PreviewItem(e["id"], e["family"], e["type"]) for e in elements]
        self.refresh_preview_display()

    # ── Filter parameter selection ────────────────────────────────────
    def on_confirm_filter_param(self, sender, args):
        current_text = self.filter_param.Text.strip()
        if not (current_text and self.state["preview_items"] and current_text in self.state["all_params_cache"]):
            return
        if self.state.get("_last_filter_param") == current_text:
            return   # unchanged — don't reset operator/value the user set
        self.state["_last_filter_param"] = current_text
        id_ints = [item.IdInt for item in self.state["preview_items"]]
        self._enqueue("filter_param_info", {"param_name": current_text, "id_ints": id_ints}, self._on_filter_param_info)

    def _on_filter_param_info(self, result):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        numeric = result.get("numeric", False)
        values = result.get("values", [])
        fv = result.get("filter_values", {})
        self.filter_op.Items.Clear()
        if numeric:
            ops = ["equals", "does not equal", "is greater than",
                   "is greater than or equal to", "is less than",
                   "is less than or equal to"]
        else:
            ops = ["equals", "does not equal", "contains", "does not contain",
                   "begins with", "does not begin with", "ends with", "does not end with"]
        for op in ops:
            self.filter_op.Items.Add(op)
        if self.filter_op.Items.Count > 0:
            self.filter_op.SelectedIndex = 0
        self.filter_val.Items.Clear()
        for v in values:
            self.filter_val.Items.Add(v)
        for item in self.state["preview_items"]:
            item.FilterValue = fv.get(item.IdInt, "-")
        self.refresh_preview_display()

    # ── Filtering ─────────────────────────────────────────────────────
    def on_filter_key_up(self, sender, args):
        """Trigger debounced real-time filter on key input."""
        self._get_filter_debounce().reset()

    def on_filter_value_changed(self, sender, args):
        """Trigger debounced real-time filter on value changes."""
        self._get_filter_debounce().reset()

    def realtime_filter_update(self):
        """Called on debounced timer - only runs after Apply Filter has been clicked once,
        so changing the parameter dropdown doesn't wipe the preview before the user is ready."""
        if not self.state["preview_items"]:
            return
        if not self.state.get("filter_applied_once"):
            return
        param_name = self.filter_param.Text.strip()
        operator = str(self.filter_op.SelectedItem) if self.filter_op.SelectedItem else "contains"
        value = self.filter_val.Text

        if not param_name:
            for item in self.state["preview_items"]:
                item.InFilter   = True
                item.IsSelected = True
            self.refresh_preview_display()
            return

        id_ints = [item.IdInt for item in self.state["preview_items"]]
        self._enqueue("filter_only", {
            "param_name": param_name,
            "operator": operator,
            "value": value,
            "id_ints": id_ints,
        }, self._on_filter_only_done)

    def _on_filter_only_done(self, result):
        if "error" in result:
            return
        filtered_set = set(result.get("filtered_ids", []))
        for item in self.state["preview_items"]:
            matched = item.IdInt in filtered_set
            item.InFilter   = matched
            item.IsSelected = matched
        self.refresh_preview_display()

    def on_apply_filter(self, sender, args):
        if not self.state["preview_items"]:
            self.filter_status.Text = "Please load parameters first."
            return
        param_name = self.filter_param.Text
        if not param_name:
            self.filter_status.Text = "Please select a parameter."
            return

        operator = str(self.filter_op.SelectedItem) if self.filter_op.SelectedItem else "contains"
        value = self.filter_val.Text
        self.filter_status.Text = "Applying filter..."
        self.state["filter_applied_once"] = True

        id_ints = [item.IdInt for item in self.state["preview_items"]]
        self._enqueue("apply_filter", {
            "param_name": param_name,
            "operator": operator,
            "value": value,
            "id_ints": id_ints,
        }, self._on_apply_filter_done)

    def _on_apply_filter_done(self, result):
        if "error" in result:
            self.filter_status.Text = result["error"]
            self.set_status(result["error"], True)
            return
        filtered_ids = result.get("filtered_ids", [])
        edit_params = result.get("edit_params", [])
        self.state["filtered_ids"] = filtered_ids

        # InFilter controls table visibility; IsSelected marks the checkbox
        filtered_set = set(filtered_ids)
        for item in self.state["preview_items"]:
            matched = item.IdInt in filtered_set
            item.InFilter   = matched
            item.IsSelected = matched
        self.refresh_preview_display()

        msg = "Filtered: {0} elements.".format(len(filtered_ids))
        self.filter_status.Text = msg
        if filtered_ids:
            self.edit_param.Items.Clear()
            for p in edit_params:
                self.edit_param.Items.Add(p)
            if edit_params:
                self.edit_param.SelectedIndex = 0
            self.btn_select_elems.IsEnabled = True
            self.edit_status.Text = "Ready to edit {0} elements.".format(len(filtered_ids))
            self.set_status("{0} elements filtered".format(len(filtered_ids)))
        else:
            self.edit_param.Items.Clear()
            self.edit_status.Text = "No elements match the filter."
            self.btn_select_elems.IsEnabled = False
            self.filter_status.Text = "No elements match the filter. Try different values."
            self.set_status("No Matches Filtered", is_error=True)

    # ── Refresh values ────────────────────────────────────────────────
    def refresh_params(self, sender=None, args=None):
        """Header Refresh — re-scan the available filter/edit VALUE options for
        the current parameters. Deliberately does NOT touch the chosen operator,
        the typed values, the filter result, or the row checks."""
        if not self.state["preview_items"]:
            self.set_status("Load parameters first.", is_error=True)
            return
        fp = self.filter_param.Text.strip()
        ep = self.edit_param.Text.strip()
        filter_id_ints = [item.IdInt for item in self.state["preview_items"]]
        edit_id_ints = self.state.get("filtered_ids", [])
        self._enqueue("refresh_values", {
            "filter_param": fp,
            "edit_param": ep,
            "filter_id_ints": filter_id_ints,
            "edit_id_ints": edit_id_ints,
        }, self._on_refresh_values_done)

    def _on_refresh_values_done(self, result):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        if "filter_values" in result:
            self._repopulate_values(self.filter_val, result["filter_values"])
        if "edit_values" in result:
            self._repopulate_values(self.edit_val1, result["edit_values"])
        self.set_status("Value lists refreshed")

    # ── Select elements ───────────────────────────────────────────────
    def on_select_elements(self, sender, args):
        # Only the checked rows, matching what Execute would edit.
        target_ids = [item.IdInt for item in self.state["preview_items"]
                      if item.InFilter and item.IsSelected]
        if not target_ids:
            self.set_status("No rows are checked.", is_error=True)
            return
        self._enqueue("select_elements", {"id_ints": target_ids}, self._on_select_elements_done)

    def _on_select_elements_done(self, result):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        self.set_status("Selected {0} checked element(s) in Revit".format(result.get("selected", 0)))

    # ── Edit parameter ────────────────────────────────────────────────
    def on_confirm_edit(self, sender, args):
        current_text = self.edit_param.Text.strip()
        if not (current_text and self.state.get("filtered_ids")):
            return
        if self.state.get("_last_edit_param") != current_text:
            self.state["_last_edit_param"] = current_text
            self.edit_status.Text = "Ready to edit parameter: " + current_text
            id_ints = self.state["filtered_ids"]
            self._enqueue("edit_param_info", {"param_name": current_text, "id_ints": id_ints}, self._on_edit_param_info)
        self.update_live_edit_preview()

    def _on_edit_param_info(self, result):
        if "error" in result:
            return
        self.edit_val1.Items.Clear()
        for v in result.get("values", []):
            self.edit_val1.Items.Add(v)

    # ── Live edit preview ─────────────────────────────────────────────
    def on_edit_field_changed(self, sender, args):
        self.update_live_edit_preview()

    def on_edit_op_changed(self, sender, args):
        """Replace → reveal the replace field; Delete → disable the value combo."""
        op = str(self.edit_op.SelectedItem) if self.edit_op.SelectedItem else ""
        is_replace = (op == "Replace")
        is_delete  = (op == "Delete")
        vis = Visibility.Visible if is_replace else Visibility.Collapsed
        self.lbl_replace.Visibility = vis
        self.edit_val2.Visibility   = vis
        self.edit_val1.IsEnabled    = not is_delete
        self.update_live_edit_preview()

    def update_live_edit_preview(self):
        """Update EditPreview on all preview items based on current edit settings."""
        param_name = self.edit_param.Text.strip()
        operation = str(self.edit_op.SelectedItem) if self.edit_op.SelectedItem else "Set"
        val1 = self.edit_val1.Text
        val2 = self.edit_val2.Text
        self.state["edit_param_name"] = param_name

        if not param_name or not self.state["preview_items"]:
            return
        id_ints = [item.IdInt for item in self.state["preview_items"]]
        selected_ints = [item.IdInt for item in self.state["preview_items"] if item.IsSelected]
        self._enqueue("edit_values_map", {
            "param_name": param_name,
            "operation": operation,
            "val1": val1,
            "val2": val2,
            "id_ints": id_ints,
            "selected_ints": selected_ints,
        }, self._on_edit_values_map_done)

    def _on_edit_values_map_done(self, result):
        if "error" in result:
            return
        previews = result.get("previews", {})
        for item in self.state["preview_items"]:
            item.EditPreview = previews.get(item.IdInt, "?")
        self.refresh_preview_display()

    # ── Execute edit ──────────────────────────────────────────────────
    def on_execute(self, sender, args):
        if not self.state.get("filtered_ids"):
            self.edit_status.Text = "Apply filter first."
            return
        if not self.edit_param.Text:
            self.edit_status.Text = "Choose a parameter to edit."
            return

        # Only edit rows the user left CHECKED (IsSelected) among the matches.
        target_ids = [item.IdInt for item in self.state["preview_items"]
                      if item.InFilter and item.IsSelected]
        if not target_ids:
            self.edit_status.Text = "No rows are checked — tick the rows to edit."
            self.set_status("Nothing checked to edit", is_error=True)
            return

        param_name = self.edit_param.Text
        operation = str(self.edit_op.SelectedItem) if self.edit_op.SelectedItem else "Set"
        val1 = self.edit_val1.Text
        val2 = self.edit_val2.Text

        self.btn_execute.IsEnabled = False
        self.edit_status.Text = "Modifying {0} checked element(s)...".format(len(target_ids))
        self._enqueue("execute_edit", {
            "id_ints": target_ids,
            "param_name": param_name,
            "operation": operation,
            "val1": val1,
            "val2": val2,
        }, self._on_execute_done)

    def _on_execute_done(self, result):
        modified = result.get("modified", 0)
        errors = result.get("errors", [])
        if modified > 0:
            self.edit_status.Text = "Modified {0} elements.".format(modified)
            if errors:
                self.edit_status.Text += " ({0} partial errors)".format(len(errors))
            self.set_status("Modified {0} elements".format(modified))
        else:
            err_str = "; ".join(errors[:3]) if errors else "Unknown error"
            self.edit_status.Text = "No elements modified. Errors: " + err_str
            self.set_status("No elements modified", is_error=True)
        self.btn_execute.IsEnabled = True

    # ── DataGrid selection / checkbox ─────────────────────────────────
    # The select column's CheckBox is bound to the DataGridRow's native
    # .IsSelected (a real .NET bool — reliable, unlike binding a Python bool).
    # Grid selection is the source of truth; mirror it into each PreviewItem.
    def on_grid_selection_changed(self, sender, args):
        if self.state.get("_refreshing"):
            return
        sel = set()
        for it in self.preview_list.SelectedItems:
            sel.add(it)
        for item in self.state["preview_items"]:
            if item.InFilter:
                item.IsSelected = item in sel
        self.update_preview_info()

    # Checkbox click → toggle THAT row's membership ourselves and mark handled,
    # so the DataGrid's default (replace-)select gesture never runs and clears
    # the other checks. Row-body clicks are swallowed entirely.
    def on_grid_mousedown(self, sender, args):
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
                if self.preview_list.SelectedItems.Contains(item):
                    self.preview_list.SelectedItems.Remove(item)
                else:
                    self.preview_list.SelectedItems.Add(item)
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

    # Row selection buttons
    def on_select_all_rows(self, sender, args):
        for item in self.state["preview_items"]:
            if item.InFilter:
                item.IsSelected = True
        self.refresh_preview_display()

    def on_deselect_all_rows(self, sender, args):
        for item in self.state["preview_items"]:
            if item.InFilter:
                item.IsSelected = False
        self.refresh_preview_display()

    # ── Close ─────────────────────────────────────────────────────────
    def on_close(self, sender, args):
        self.state["preview_items"] = []
        self.state["filtered_ids"] = []
        self.state["all_params_cache"] = []
        self.window.Close()

    def on_closed(self, sender, args):
        if _state.window_ref is self:
            _state.window_ref = None

    # ── Show modeless + anchor to Revit ───────────────────────────────
    def show(self):
        self.window.Show()
        # Anchor AFTER Show() so the window stays above Revit without blocking
        helper = WindowInteropHelper(self.window)
        helper.Owner = __revit__.MainWindowHandle
        # Initial load runs on the WPF dispatcher thread
        self.window.Dispatcher.BeginInvoke(
            DispatcherPriority.Normal, Action(self._initial_load))

    def _initial_load(self):
        self.refresh_category_list()
        self.set_status("Ready")


# ======================================================================
# ENTRY POINT
# ======================================================================
def run():
    # Re-opening while an instance is alive: activate instead of stacking.
    ref = _state.window_ref
    if ref is not None:
        try:
            if ref.window.IsVisible:
                ref.window.Activate()
                return
        except Exception:
            _state.window_ref = None

    script_dir = os.path.dirname(__file__)
    xaml_path = os.path.join(script_dir, "ui.xaml")

    handler = FilterParameterHandler()
    handler.data = {}          # per-instance state (no __init__ — see class note)
    handler._elements = []
    handler._id_to_elem = {}
    ext_event = ExternalEvent.Create(handler)
    app = FilterParameterApp(xaml_path, handler, ext_event)
    handler.app = app
    _state.window_ref = app    # survives run() → re-launch activates it
    app.show()


def main():
    run()


if __name__ == "__main__":
    # Module-level guard: report a logic error cleanly instead of leaving the
    # persistent engine in a half-state.
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            TaskDialog.Show(
                "AnonGee · OneFilterParameter",
                "Failed to launch: {}".format(e))
        except Exception:
            pass
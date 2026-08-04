#! python3
# -*- coding: utf-8 -*-
# pyRevit script - MultiFilterParameter (CPython 3) — MODELESS
# AnonGee BIM Tools v3.0 — theme loaded from shared Resources/
#
# Converted from modal (ShowDialog) to modeless (Show) using the AnonGee
# modeless reference pattern (§12.8.7):
#   • window.Show()  -> runs WPF on a separate thread.
#   • MultiFilterParameterHandler (IExternalEventHandler) -> all Revit DB/UI
#     work inside Execute(), queued via ExternalEvent.Raise() from the WPF
#     thread.
#   • A serialized request queue guarantees one Revit-thread request at a time,
#     in order — per-row filter/edit callbacks capture their row_dict so
#     results land on the right row.
#   • The handler class + live window ref live in a dedicated session-state
#     module kept in sys.modules (§12.8.7.1):
#       - Python.NET 3 emits __namespace__ interface subclasses as real CLR
#         types; re-running the class statement after the first press raises
#         "Duplicate type name within an assembly". The class is therefore
#         defined exactly once per Revit session.
#       - The window ref survives run() returning, so re-launch activates the
#         existing window instead of stacking a new one.
#
# Visuals are unchanged: ui.xaml is not modified. All dynamic row building
# (filter rows, edit rows, + / − buttons) and status strings are ported
# verbatim. The only internal change: filtered ids cross the bridge as ints;
# the handler keeps the id -> Element map on the Revit thread.

import os
import sys
import types
import clr
import System

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementCategoryFilter, ElementMulticategoryFilter,
    CategoryType, ElementId, StorageType, Transaction
)
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import BitmapImage
from System.IO import FileStream, FileMode, FileAccess
from System import Uri, UriKind, Action
from System.Collections.Generic import List as ListT
from System.Windows import (
    Thickness, Visibility, GridLength, GridUnitType, FontWeights, VerticalAlignment,
    MessageBox, MessageBoxButton, MessageBoxImage
)
from System.Windows.Controls import (
    Grid, ColumnDefinition, ComboBox, TextBox, Button, TextBlock, ListBoxItem, CheckBox
)
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Threading import DispatcherPriority

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
_STATE_MODULE = "AnonGee_MultiFilterParameterState"
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
    class MultiFilterParameterHandler(IExternalEventHandler):
        """
        Runs on Revit's primary thread. The WPF thread writes `data`, Raise()
        queues Execute(), and results are marshalled back to the WPF thread via
        the window's Dispatcher.
        """

        # __namespace__ is required by Python.NET 3 to build a real derived CLR
        # type from a .NET interface -- without it, MultiFilterParameterHandler()
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
        app = None         # MultiFilterParameterApp — set after it is created
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
            return "AnonGee_MultiFilterParameterHandler"

        def _dispatch(self, req, uidoc):
            d = self.data.get("data", {})
            if req == "load_categories":
                self._load_categories(d, uidoc)
            elif req == "load_params":
                self._load_params(d, uidoc)
            elif req == "row_filter_info":
                self._row_filter_info(d, uidoc)
            elif req == "row_edit_info":
                self._row_edit_info(d, uidoc)
            elif req == "apply_filter":
                self._apply_filter(d, uidoc)
            elif req == "refresh_params":
                self._refresh_params(d, uidoc)
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
        def _id_int(self, eid):
            return int(getattr(eid, "Value", getattr(eid, "IntegerValue", -1)))

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

        def _get_categories_by_scope(self, doc, uidoc, scope):
            cats = set()
            try:
                if scope == "whole":
                    for c in doc.Settings.Categories:
                        if c.CategoryType == CategoryType.Model and c.AllowsBoundParameters:
                            try:
                                cf = ElementCategoryFilter(c.Id)
                                if FilteredElementCollector(doc).WherePasses(cf) \
                                        .WhereElementIsNotElementType().GetElementCount() > 0:
                                    cats.add(c.Name)
                            except Exception:
                                pass
                elif scope == "view":
                    col = FilteredElementCollector(doc, doc.ActiveView.Id).WhereElementIsNotElementType()
                    for e in col:
                        if e.Category:
                            cats.add(e.Category.Name)
                elif scope == "selection":
                    for eid in uidoc.Selection.GetElementIds():
                        el = doc.GetElement(eid)
                        if el and el.Category:
                            cats.add(el.Category.Name)
                return sorted(cats)
            except Exception:
                return []

        def _get_elements_by_categories(self, doc, uidoc, category_names, scope):
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

        def _get_common_params(self, elements, writable_only=False):
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

        def _get_param_values(self, doc, elements, param_name, val_to_num=None):
            values = set()
            if val_to_num is None:
                val_to_num = {}
            if param_name not in val_to_num:
                val_to_num[param_name] = {}
            for e in elements:
                try:
                    param = self._lookup_param(doc, e, param_name)
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
                                val_to_num[param_name][val] = param.AsDouble()
                            elif param.StorageType == StorageType.Integer:
                                val_to_num[param_name][val] = float(param.AsInteger())
                except Exception:
                    continue
            return sorted(values)

        def _evaluate_single_condition(self, doc, e, param_name, operator, value, val_to_num):
            if value is None:
                value = ""
            try:
                param = self._lookup_param(doc, e, param_name)
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
                    num_val = val_to_num.get(param_name, {}).get(value)
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

        def _apply_single_modification(self, elem, param_name, operation, val1, val2):
            try:
                param = elem.LookupParameter(param_name)
                if param is None or param.IsReadOnly:
                    return False, "Not found or read-only"
                st = param.StorageType
                if operation == "Delete":
                    if st == StorageType.String:      param.Set(System.String(""))
                    elif st == StorageType.Integer:   param.Set(System.Int32(0))
                    elif st == StorageType.Double:    param.Set(System.Double(0.0))
                    elif st == StorageType.ElementId: param.Set(ElementId.InvalidElementId)
                    else: return False, "Cannot delete parameter type"
                    return True, None
                if operation in ("Prefix", "Suffix", "Replace"):
                    if st != StorageType.String:
                        return False, "Requires text parameter"
                    cur = param.AsString() if param.AsString() else ""
                    if operation == "Prefix":   param.Set(System.String(val1 + cur))
                    elif operation == "Suffix": param.Set(System.String(cur + val1))
                    elif operation == "Replace":
                        if not val1:
                            return False, "Empty search string"
                        param.Set(System.String(cur.replace(val1, val2)))
                    return True, None
                if operation == "Set":
                    if st == StorageType.String:
                        param.Set(System.String(val1))
                    elif st == StorageType.Integer:
                        if not param.SetValueString(System.String(val1)):
                            param.Set(System.Int32(int(float(val1))))
                    elif st == StorageType.Double:
                        if not param.SetValueString(System.String(val1)):
                            param.Set(System.Double(float(val1)))
                    elif st == StorageType.ElementId:
                        return False, "Set ElementId not supported"
                    else:
                        param.Set(System.String(val1))
                    return True, None
                return False, "Unknown operation"
            except Exception as ex:
                return False, str(ex)

        # ── Request handlers ──────────────────────────────────────────
        def _load_categories(self, d, uidoc):
            doc = uidoc.Document
            scope = d.get("scope", "whole")
            result = {"request": "load_categories",
                      "categories": self._get_categories_by_scope(doc, uidoc, scope)}
            self.data["result"] = result
            self._marshal_to_ui()

        def _load_params(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "load_params"}
            categories = d.get("categories", [])
            scope = d.get("scope", "whole")
            elements = self._get_elements_by_categories(doc, uidoc, categories, scope)
            if not elements:
                result["error"] = "No elements found in selected categories."
            else:
                self._elements = elements
                self._id_to_elem = {}
                for e in elements:
                    self._id_to_elem[self._id_int(e.Id)] = e
                result["params"] = self._get_common_params(elements)
                result["count"] = len(elements)
            self.data["result"] = result
            self._marshal_to_ui()

        def _row_filter_info(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "row_filter_info"}
            param_name = d.get("param_name", "")
            elements = list(self._elements)
            numeric = False
            for e in elements[:20]:
                try:
                    param = self._lookup_param(doc, e, param_name)
                    if param:
                        if param.StorageType in (StorageType.Integer, StorageType.Double):
                            numeric = True
                        break
                except Exception:
                    continue
            values = self._get_param_values(doc, elements, param_name)
            result["numeric"] = numeric
            result["values"] = values
            self.data["result"] = result
            self._marshal_to_ui()

        def _row_edit_info(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "row_edit_info"}
            param_name = d.get("param_name", "")
            src_ids = d.get("src_ids", [])
            if src_ids:
                elements = [self._id_to_elem[i] for i in src_ids if i in self._id_to_elem]
                if not elements:
                    elements = list(self._elements)
            else:
                elements = list(self._elements)
            values = self._get_param_values(doc, elements, param_name)
            result["values"] = values
            self.data["result"] = result
            self._marshal_to_ui()

        def _apply_filter(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "apply_filter"}
            rows = d.get("rows", [])
            match_all = d.get("match_all", True)
            elements = list(self._elements)
            val_to_num = {}
            for spec in rows:
                pn = spec.get("param_name", "")
                if pn and pn not in val_to_num:
                    self._get_param_values(doc, elements, pn, val_to_num)
            passed = []
            for e in elements:
                elem_passed = match_all
                active = 0
                for spec in rows:
                    p_name = spec.get("param_name", "")
                    if not p_name:
                        continue
                    active += 1
                    op = spec.get("operator", "contains")
                    val = spec.get("value", "")
                    cond = self._evaluate_single_condition(doc, e, p_name, op, val, val_to_num)
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
            result["filtered_ids"] = [self._id_int(e.Id) for e in passed]
            passed_elems = [self._id_to_elem[i] for i in result["filtered_ids"]
                            if i in self._id_to_elem]
            result["writable_params"] = self._get_common_params(passed_elems, writable_only=True)
            self.data["result"] = result
            self._marshal_to_ui()

        def _refresh_params(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "refresh_params"}
            elements = list(self._elements)
            if d.get("need_load") and d.get("categories"):
                cats = d.get("categories", [])
                scope = d.get("scope", "whole")
                loaded = self._get_elements_by_categories(doc, uidoc, cats, scope)
                if not loaded:
                    result["error"] = "No elements found in selected categories."
                    self.data["result"] = result
                    self._marshal_to_ui()
                    return
                elements = loaded
                self._elements = elements
                self._id_to_elem = {}
                for e in elements:
                    self._id_to_elem[self._id_int(e.Id)] = e
            if elements:
                result["elements_count"] = len(elements)
            all_params = self._get_common_params(elements) if elements else []

            src_ids = d.get("src_ids", [])
            if src_ids:
                src_elems = [self._id_to_elem[i] for i in src_ids if i in self._id_to_elem]
                if not src_elems:
                    src_elems = list(elements)
            else:
                src_elems = list(elements)
            writable = self._get_common_params(src_elems, writable_only=True) if src_elems else []

            filter_infos = []
            for spec in d.get("filter_rows", []):
                pn = spec.get("param_name", "")
                info = {"param_name": pn}
                if pn:
                    numeric = False
                    for e in elements[:20]:
                        try:
                            param = self._lookup_param(doc, e, pn)
                            if param:
                                if param.StorageType in (StorageType.Integer, StorageType.Double):
                                    numeric = True
                                break
                        except Exception:
                            continue
                    values = self._get_param_values(doc, elements, pn)
                    info["numeric"] = numeric
                    info["values"] = values
                filter_infos.append(info)

            edit_infos = []
            for spec in d.get("edit_rows", []):
                pn = spec.get("param_name", "")
                info = {"param_name": pn}
                if pn:
                    info["values"] = self._get_param_values(doc, src_elems, pn)
                edit_infos.append(info)

            result["params"] = all_params
            result["writable_params"] = writable
            result["filter_infos"] = filter_infos
            result["edit_infos"] = edit_infos
            self.data["result"] = result
            self._marshal_to_ui()

        def _select_elements(self, d, uidoc):
            result = {"request": "select_elements"}
            id_ints = d.get("id_ints", [])
            try:
                ids = ListT[ElementId]()
                for i in id_ints:
                    ids.Add(ElementId(System.Int64(i)))
                uidoc.Selection.SetElementIds(ids)
                result["selected"] = len(id_ints)
            except Exception as ex:
                result["error"] = "Selection failed: " + str(ex)
            self.data["result"] = result
            self._marshal_to_ui()

        def _execute_edit(self, d, uidoc):
            doc = uidoc.Document
            result = {"request": "execute_edit"}
            id_ints = d.get("id_ints", [])
            rows = d.get("rows", [])
            modified = 0
            errors = []
            if not id_ints:
                errors.append("Apply filter first.")
            else:
                t = Transaction(doc, "AnonGee · Multi Filter Parameter Edit")
                t.Start()
                try:
                    for i in id_ints:
                        elem = self._id_to_elem.get(i)
                        if elem is None:
                            elem = doc.GetElement(ElementId(System.Int64(i)))
                        if not elem:
                            continue
                        elem_modified = False
                        for spec in rows:
                            p_name = spec.get("param_name", "")
                            if not p_name:
                                continue
                            op = spec.get("operation", "Set")
                            val1 = spec.get("val1", "")
                            val2 = spec.get("val2", "")
                            ok, err = self._apply_single_modification(elem, p_name, op, val1, val2)
                            if ok:
                                elem_modified = True
                            if err:
                                errors.append("Element {}: {}".format(i, err))
                        if elem_modified:
                            modified += 1
                    t.Commit()
                except Exception as ex:
                    if t.HasStarted() and not t.HasEnded():
                        t.RollBack()
                    errors.append("Transaction failed: " + str(ex))
            result["modified"] = modified
            result["errors"] = errors
            self.data["result"] = result
            self._marshal_to_ui()

    _state.handler_cls = MultiFilterParameterHandler
else:
    # Later press: the Python.NET 3 CLR type is already emitted and cached —
    # reuse it instead of re-running the class statement (which would raise
    # "Duplicate type name within an assembly").
    MultiFilterParameterHandler = _state.handler_cls


# ======================================================================
# WPF APP — MODELESS
# ======================================================================
class MultiFilterParameterApp(object):
    """The modeless window. Fresh instance per launch — subscriptions are
    never made at module scope (§12.9.2 handler accumulation)."""

    def __init__(self, xaml_path, handler, ext_event):
        self.handler = handler
        self.ext_event = ext_event
        self._queue = []              # serialized request queue
        self._busy = False
        self._current_callback = None
        self._loaded = False          # elements loaded on the Revit thread?

        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        try:
            self.window = XamlReader.Load(stream)
        finally:
            stream.Close()

        icon_path = os.path.join(LOCAL_DIR, "icon.png")
        if os.path.exists(icon_path):
            self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

        f = self.window.FindName
        self.main_tabs         = f("main_tabs")
        self.btn_refresh       = f("btn_refresh")
        self.category_list     = f("category_list")
        self.btn_all_cats      = f("btn_all_cats")
        self.btn_none_cats     = f("btn_none_cats")
        self.btn_load_params   = f("btn_load_params")
        self.rb_whole          = f("rb_whole")
        self.rb_view           = f("rb_view")
        self.rb_selection      = f("rb_selection")
        self.rb_match_all      = f("rb_match_all")
        self.filter_rows_container = f("filter_rows_container")
        self.btn_apply_filter  = f("btn_apply_filter")
        self.filter_status     = f("filter_status")
        self.edit_rows_container = f("edit_rows_container")
        self.btn_execute       = f("btn_execute")
        self.edit_status       = f("edit_status")
        self.status_badge      = f("status_badge")
        self.status_textblock  = f("status_textblock")
        self.error_badge       = f("error_badge")
        self.error_text        = f("error_text")
        self.btn_select_elems  = f("btn_select_elems")
        self.btn_close         = f("btn_close")

        # Brand resources used by dynamically-built rows
        self.R_COMBO   = self.window.FindResource("InputComboBox")
        self.R_TEXT    = self.window.FindResource("InputTextBox")
        self.R_PRIMARY = self.window.FindResource("ButtonPrimary")
        self.R_SEC     = self.window.FindResource("ButtonSecondary")
        self.R_DANGER  = self.window.FindResource("ButtonDanger")
        self.R_CHAR    = self.window.FindResource("BrushCharcoalBlack")

        self.state = {
            "filtered_ids": [],
            "all_params_cache": [],
            "writable_params_cache": [],
            "val_to_num": {},
            "_suppress": False,   # mute auto-populate during programmatic Items edits
        }
        self.filter_rows = []
        self.edit_rows = []

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
        self.btn_apply_filter.Click += self.on_apply_filter
        self.btn_execute.Click += self.on_execute
        self.btn_select_elems.Click += self.on_select_elements
        self.btn_close.Click += self.on_close
        self.window.Closed += self.on_closed

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

    # ── Status / counts ───────────────────────────────────────────────
    def set_status(self, message, is_error=False):
        self.status_textblock.Text = message
        if not is_error:
            self.status_badge.Visibility = Visibility.Visible
            self.error_badge.Visibility = Visibility.Collapsed
        else:
            self.status_badge.Visibility = Visibility.Collapsed
            self.error_badge.Visibility = Visibility.Visible
        self.error_text.Text = message if is_error else ""

    def _checked_cat_names(self):
        return [item.Content.Content.Text for item in self.category_list.Items
                if item.Content.IsChecked]

    # ── Category / scope ──────────────────────────────────────────────
    def refresh_category_list(self):
        scope = "whole" if self.rb_whole.IsChecked else "view" if self.rb_view.IsChecked else "selection"
        self._enqueue("load_categories", {"scope": scope}, self._on_categories_loaded)

    def _on_categories_loaded(self, result):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        self.category_list.Items.Clear()
        for cat_name in result.get("categories", []):
            tb = TextBlock(); tb.Text = cat_name
            chk = CheckBox(); chk.Content = tb; chk.IsChecked = False
            item = ListBoxItem(); item.Content = chk
            self.category_list.Items.Add(item)

    def on_scope_changed(self, sender, args):
        self.refresh_category_list()

    def on_select_all(self, sender, args):
        for item in self.category_list.Items:
            item.Content.IsChecked = True

    def on_select_none(self, sender, args):
        for item in self.category_list.Items:
            item.Content.IsChecked = False

    # ── Load parameters ───────────────────────────────────────────────
    def on_load_params(self, sender, args):
        cats = self._checked_cat_names()
        if not cats:
            self.set_status("Select at least one category", True)
            return
        self.set_status("Loading parameters...")
        scope = "whole" if self.rb_whole.IsChecked else "view" if self.rb_view.IsChecked else "selection"
        self._enqueue("load_params", {"categories": cats, "scope": scope}, self._on_params_loaded)

    def _on_params_loaded(self, result):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        params = result.get("params", [])
        count = result.get("count", 0)
        self.state["all_params_cache"] = params
        self._loaded = True
        for row in self.filter_rows:
            self._set_param_items(row['cb_param'], params)
        self.set_status("Loaded {} parameters from {} elements.".format(len(params), count))
        self.main_tabs.SelectedIndex = 1

    # ── Refresh (header) ──────────────────────────────────────────────
    def refresh_params(self, sender, args):
        need_load = not self._loaded
        categories = []
        scope = "whole"
        if need_load:
            cats = self._checked_cat_names()
            if cats:
                categories = cats
                scope = "whole" if self.rb_whole.IsChecked else "view" if self.rb_view.IsChecked else "selection"
        filter_specs = [{"param_name": row['cb_param'].Text.strip()} for row in self.filter_rows]
        edit_specs = [{"param_name": row['cb_param'].Text.strip()} for row in self.edit_rows]
        src_ids = list(self.state.get("filtered_ids", []))
        self._enqueue("refresh_params", {
            "need_load": need_load,
            "categories": categories,
            "scope": scope,
            "filter_rows": filter_specs,
            "edit_rows": edit_specs,
            "src_ids": src_ids,
        }, self._on_refresh_done)

    def _on_refresh_done(self, result):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        self.state["all_params_cache"] = result.get("params", [])
        self.state["writable_params_cache"] = result.get("writable_params", [])
        if "elements_count" in result:
            self._loaded = True
        filter_infos = result.get("filter_infos", [])
        edit_infos = result.get("edit_infos", [])
        for i, row in enumerate(self.filter_rows):
            self._set_param_items(row['cb_param'], self.state["all_params_cache"])
            row['_last_param'] = None   # force reload past the change-guard
            if i < len(filter_infos) and row['cb_param'].Text.strip():
                self._apply_filter_row_info(row, filter_infos[i])
        for i, row in enumerate(self.edit_rows):
            self._set_param_items(row['cb_param'], self.state["writable_params_cache"])
            row['_last_param'] = None
            if i < len(edit_infos) and row['cb_param'].Text.strip():
                self._apply_edit_row_info(row, edit_infos[i].get("values", []))
        self.set_status("Refreshed — {} filter / {} edit params".format(
            len(self.state["all_params_cache"]), len(self.state["writable_params_cache"])))

    # ── Filter rows ───────────────────────────────────────────────────
    def confirm_filter_row(self, row_dict):
        if self.state["_suppress"]:
            return
        param_name = row_dict['cb_param'].Text.strip()
        if not param_name or not self._loaded:
            return
        if row_dict.get('_last_param') == param_name:
            return   # unchanged — don't reset the user's operator/value
        row_dict['_last_param'] = param_name
        self._enqueue("row_filter_info", {"param_name": param_name},
                      lambda result: self._on_row_filter_info(result, row_dict))

    def _on_row_filter_info(self, result, row_dict):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        self._apply_filter_row_info(row_dict, result)

    def _apply_filter_row_info(self, row, info):
        numeric = info.get("numeric", False)
        values = info.get("values", [])
        cb_op = row['cb_op']
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
        cb_val = row['cb_val']
        cb_val.Items.Clear()
        for v in values:
            cb_val.Items.Add(v)

    # ── Edit rows ─────────────────────────────────────────────────────
    def confirm_edit_row(self, row_dict):
        if self.state["_suppress"]:
            return
        param_name = row_dict['cb_param'].Text.strip()
        if not param_name:
            return
        if row_dict.get('_last_param') == param_name:
            return   # unchanged — don't wipe the user's value
        row_dict['_last_param'] = param_name
        src_ids = list(self.state.get("filtered_ids", []))
        self._enqueue("row_edit_info", {"param_name": param_name, "src_ids": src_ids},
                      lambda result: self._on_row_edit_info(result, row_dict))

    def _on_row_edit_info(self, result, row_dict):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        self._apply_edit_row_info(row_dict, result.get("values", []))

    def _apply_edit_row_info(self, row, values):
        cb_val1 = row['cb_val1']
        cb_val1.Items.Clear()
        for v in values:
            cb_val1.Items.Add(v)

    # ── Apply filter ──────────────────────────────────────────────────
    def on_apply_filter(self, sender, args):
        if not self._loaded:
            self.filter_status.Text = "Load parameters from the Categories tab first."
            return
        self.filter_status.Text = "Applying multi-filter..."
        match_all = self.rb_match_all.IsChecked
        rows = []
        for row in self.filter_rows:
            p_name = row['cb_param'].Text.strip()
            if not p_name:
                continue
            op = str(row['cb_op'].SelectedItem) if row['cb_op'].SelectedItem else "contains"
            val = row['cb_val'].Text
            rows.append({"param_name": p_name, "operator": op, "value": val})
        self._enqueue("apply_filter", {"rows": rows, "match_all": match_all}, self._on_apply_filter_done)

    def _on_apply_filter_done(self, result):
        if "error" in result:
            self.filter_status.Text = result["error"]
            self.set_status(result["error"], True)
            return
        filtered_ids = result.get("filtered_ids", [])
        self.state["filtered_ids"] = filtered_ids
        if filtered_ids:
            self.state["writable_params_cache"] = result.get("writable_params", [])
            self.filter_status.Text = "Filtered: {} elements match the criteria.".format(len(filtered_ids))
            self.set_status("{} elements filtered".format(len(filtered_ids)))
            self.btn_select_elems.IsEnabled = True
            for row in self.edit_rows:
                self._set_param_items(row['cb_param'], self.state["writable_params_cache"])
            self.edit_status.Text = "Ready to edit {} filtered elements.".format(len(filtered_ids))
            self.main_tabs.SelectedIndex = 2
        else:
            self.filter_status.Text = "No elements match the combination of filters."
            self.set_status("No matches", True)
            self.btn_select_elems.IsEnabled = False

    # ── Select elements ───────────────────────────────────────────────
    def on_select_elements(self, sender, args):
        if self.state["filtered_ids"]:
            self._enqueue("select_elements", {"id_ints": self.state["filtered_ids"]}, self._on_selected_done)

    def _on_selected_done(self, result):
        if "error" in result:
            self.set_status(result["error"], True)
            return
        self.window.Close()

    # ── Execute edit ──────────────────────────────────────────────────
    def on_execute(self, sender, args):
        if not self.state["filtered_ids"]:
            self.edit_status.Text = "Apply filter first."
            return
        self.btn_execute.IsEnabled = False
        self.edit_status.Text = "Modifying elements in batch..."
        rows = []
        for row in self.edit_rows:
            p_name = row['cb_param'].Text.strip()
            if not p_name:
                continue
            op = str(row['cb_op'].SelectedItem) if row['cb_op'].SelectedItem else "Set"
            val1 = row['cb_val1'].Text
            val2 = row['cb_val2'].Text
            rows.append({"param_name": p_name, "operation": op, "val1": val1, "val2": val2})
        self._enqueue("execute_edit",
                      {"id_ints": self.state["filtered_ids"], "rows": rows}, self._on_execute_done)

    def _on_execute_done(self, result):
        modified = result.get("modified", 0)
        errors = result.get("errors", [])
        if modified > 0:
            msg = "Modified {} elements successfully.".format(modified)
            if errors:
                msg += " ({} partial errors).".format(len(errors))
            self.edit_status.Text = msg
            self.set_status("Modified {} elements".format(modified))
        else:
            err_str = "; ".join(errors[:3]) if errors else "No valid parameters selected."
            self.edit_status.Text = "No elements modified. " + err_str
            self.set_status("No elements modified", True)
        self.btn_execute.IsEnabled = True

    # ── Dynamic row builders ──────────────────────────────────────────
    def _icon_button(self, content, style):
        b = Button()
        b.Content = content
        b.Style = style
        b.Width = 24
        b.Height = 24
        b.Padding = Thickness(0)
        return b

    def update_filter_rows_ui(self):
        for i, row in enumerate(self.filter_rows):
            row['lbl'].Text = "{}.".format(i + 1)
            row['btn_minus'].IsEnabled = len(self.filter_rows) > 1

    def update_edit_rows_ui(self):
        for i, row in enumerate(self.edit_rows):
            row['lbl'].Text = "{}.".format(i + 1)
            row['btn_minus'].IsEnabled = len(self.edit_rows) > 1

    def _set_param_items(self, combo, params):
        """Populate a parameter combo without firing the auto-load handler."""
        prev = combo.Text
        self.state["_suppress"] = True
        try:
            combo.Items.Clear()
            for p in params:
                combo.Items.Add(p)
        finally:
            self.state["_suppress"] = False
        combo.Text = prev

    def _row_grid(self, star_widths):
        grid = Grid()
        grid.Margin = Thickness(0, 0, 0, 6)
        for w in star_widths:
            cd = ColumnDefinition()
            cd.Width = GridLength(w) if isinstance(w, int) else w
            grid.ColumnDefinitions.Add(cd)
        return grid

    def _row_label(self, grid):
        lbl = TextBlock()
        lbl.VerticalAlignment = VerticalAlignment.Center
        lbl.FontWeight = FontWeights.SemiBold
        lbl.Foreground = self.R_CHAR
        Grid.SetColumn(lbl, 0)
        grid.Children.Add(lbl)
        return lbl

    def add_filter_row(self):
        STAR = GridLength(1.5, GridUnitType.Star)
        grid = self._row_grid([20, STAR, STAR, STAR, 28, 28])
        lbl = self._row_label(grid)

        cb_param = ComboBox(); cb_param.Style = self.R_COMBO; cb_param.IsEditable = True
        cb_param.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_param, 1); grid.Children.Add(cb_param)

        cb_op = ComboBox(); cb_op.Style = self.R_COMBO
        cb_op.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_op, 2); grid.Children.Add(cb_op)

        cb_val = ComboBox(); cb_val.Style = self.R_COMBO; cb_val.IsEditable = True
        cb_val.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_val, 3); grid.Children.Add(cb_val)

        btn_plus = self._icon_button("+", self.R_SEC)
        btn_plus.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(btn_plus, 4); grid.Children.Add(btn_plus)

        btn_minus = self._icon_button("−", self.R_DANGER)  # −
        Grid.SetColumn(btn_minus, 5); grid.Children.Add(btn_minus)

        row_dict = {'grid': grid, 'lbl': lbl, 'cb_param': cb_param,
                    'cb_op': cb_op, 'cb_val': cb_val, 'btn_plus': btn_plus, 'btn_minus': btn_minus}

        btn_plus.Click  += lambda s, a: self.add_filter_row()
        btn_minus.Click += lambda s, a: self.remove_filter_row(row_dict)
        # Populate operator + value when the parameter is COMMITTED — dropdown
        # closes (pick) or focus leaves (typed/autocompleted). Not on scroll.
        cb_param.DropDownClosed += lambda s, a: self.confirm_filter_row(row_dict)
        cb_param.LostFocus      += lambda s, a: self.confirm_filter_row(row_dict)

        self._set_param_items(cb_param, self.state["all_params_cache"])

        self.filter_rows.append(row_dict)
        self.filter_rows_container.Children.Add(grid)
        self.update_filter_rows_ui()

    def remove_filter_row(self, row_dict):
        if len(self.filter_rows) > 1:
            self.filter_rows.remove(row_dict)
            self.filter_rows_container.Children.Remove(row_dict['grid'])
            self.update_filter_rows_ui()

    def add_edit_row(self):
        STAR15 = GridLength(1.5, GridUnitType.Star)
        STAR12 = GridLength(1.2, GridUnitType.Star)
        grid = self._row_grid([20, STAR15, STAR12, STAR15, STAR15, 28, 28])
        lbl = self._row_label(grid)

        cb_param = ComboBox(); cb_param.Style = self.R_COMBO; cb_param.IsEditable = True
        cb_param.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_param, 1); grid.Children.Add(cb_param)

        cb_op = ComboBox(); cb_op.Style = self.R_COMBO
        for op in ["Prefix", "Suffix", "Replace", "Set", "Delete"]:
            cb_op.Items.Add(op)
        cb_op.SelectedIndex = 3
        cb_op.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_op, 2); grid.Children.Add(cb_op)

        cb_val1 = ComboBox(); cb_val1.Style = self.R_COMBO; cb_val1.IsEditable = True
        cb_val1.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(cb_val1, 3); grid.Children.Add(cb_val1)

        tb_val2 = TextBox(); tb_val2.Style = self.R_TEXT
        tb_val2.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(tb_val2, 4); grid.Children.Add(tb_val2)

        btn_plus = self._icon_button("+", self.R_SEC)
        btn_plus.Margin = Thickness(0, 0, 4, 0); Grid.SetColumn(btn_plus, 5); grid.Children.Add(btn_plus)

        btn_minus = self._icon_button("−", self.R_DANGER)
        Grid.SetColumn(btn_minus, 6); grid.Children.Add(btn_minus)

        row_dict = {'grid': grid, 'lbl': lbl, 'cb_param': cb_param, 'cb_op': cb_op,
                    'cb_val1': cb_val1, 'cb_val2': tb_val2, 'btn_plus': btn_plus, 'btn_minus': btn_minus}

        btn_plus.Click  += lambda s, a: self.add_edit_row()
        btn_minus.Click += lambda s, a: self.remove_edit_row(row_dict)
        cb_op.SelectionChanged += lambda s, a: self._on_edit_op_changed(row_dict)
        # Populate values when the parameter is COMMITTED — dropdown closes
        # (pick) or focus leaves (typed/autocompleted). Not on scroll.
        cb_param.DropDownClosed += lambda s, a: self.confirm_edit_row(row_dict)
        cb_param.LostFocus      += lambda s, a: self.confirm_edit_row(row_dict)

        self._set_param_items(cb_param, self.state["writable_params_cache"])

        self.edit_rows.append(row_dict)
        self.edit_rows_container.Children.Add(grid)
        self.update_edit_rows_ui()
        self._on_edit_op_changed(row_dict)   # init: hidden/disabled per default op (Set)

    def remove_edit_row(self, row_dict):
        if len(self.edit_rows) > 1:
            self.edit_rows.remove(row_dict)
            self.edit_rows_container.Children.Remove(row_dict['grid'])
            self.update_edit_rows_ui()

    def _on_edit_op_changed(self, row_dict):
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

    # ── Close ─────────────────────────────────────────────────────────
    def on_close(self, sender, args):
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
        self.add_filter_row()
        self.add_edit_row()
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

    handler = MultiFilterParameterHandler()
    handler.data = {}          # per-instance state (no __init__ — see class note)
    handler._elements = []
    handler._id_to_elem = {}
    ext_event = ExternalEvent.Create(handler)
    app = MultiFilterParameterApp(xaml_path, handler, ext_event)
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
    except Exception:
        MessageBox.Show(
            _fmt_exc()[-3000:],
            "Multi Filter Parameter — Unhandled Error",
            MessageBoxButton.OK, MessageBoxImage.Error)
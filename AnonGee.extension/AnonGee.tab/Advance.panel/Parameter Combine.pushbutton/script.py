#! python3
# -*- coding: utf-8 -*-

import os
import re
import math
import clr

# Load Revit API
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import TaskDialog

# Load .NET/WPF Libraries
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')
clr.AddReference('System')
clr.AddReference('System.Data')

from System.Windows.Markup import XamlReader
from System.Windows.Media import Brushes
from System.Windows.Documents import TextRange, TextElement, LogicalDirection, TextPointerContext
from System.Windows import FontWeights, Visibility
from System.IO import FileStream, FileMode, FileAccess
from System.Diagnostics import Process
from System.Windows.Interop import WindowInteropHelper
from System import String, Predicate, Object, Boolean
from System.Collections.Generic import List
from System.Windows.Data import CollectionViewSource
from System.Windows.Input import Key
from System.Data import DataTable

# Safe Math Dictionary for eval()
base_math = {
    'abs': abs, 'round': round, 'min': min, 'max': max,
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
    'sqrt': math.sqrt, 'pi': math.pi, 'ceil': math.ceil, 'floor': math.floor
}
SAFE_MATH = {}
for k, v in base_math.items():
    SAFE_MATH[k] = v
    SAFE_MATH[k.capitalize()] = v
    SAFE_MATH[k.upper()] = v

# ====================================================================
# HELPER FUNCTIONS
# ====================================================================

def get_unit_type(parameter, document):
    if parameter.StorageType != DB.StorageType.Double: return None
    if hasattr(parameter.Definition, 'GetDataType'):
        try: return document.GetUnits().GetFormatOptions(parameter.Definition.GetDataType()).GetUnitTypeId()
        except: return None
    if hasattr(parameter, 'DisplayUnitType'):
        try: return parameter.DisplayUnitType
        except: return None
    return None

def convert_to_display_units(internal_value, parameter, document):
    unit_type = get_unit_type(parameter, document)
    if not unit_type: return internal_value
    return DB.UnitUtils.ConvertFromInternalUnits(internal_value, unit_type)

def convert_to_internal_units(display_value, parameter, document):
    unit_type = get_unit_type(parameter, document)
    if not unit_type: return display_value
    return DB.UnitUtils.ConvertToInternalUnits(display_value, unit_type)

def is_yesno_parameter(parameter):
    try:
        if hasattr(parameter.Definition, 'ParameterType'):
            return str(parameter.Definition.ParameterType) == "YesNo"
        if hasattr(parameter.Definition, 'GetDataType'):
            return "spec.bool" in str(parameter.Definition.GetDataType().TypeId).lower()
    except: pass
    return False

def get_element_parameters_dict(element, document):
    params_dict = {}
    for p in element.Parameters: params_dict[p.Definition.Name] = p
    type_id = element.GetTypeId()
    if type_id != DB.ElementId.InvalidElementId:
        elem_type = document.GetElement(type_id)
        if elem_type:
            for p in elem_type.Parameters: params_dict[f"[Type] {p.Definition.Name}"] = p
    return params_dict

def extract_parameter_value(parameter, document, requires_number):
    if not parameter: return 0.0 if requires_number else ""
    storage_type = parameter.StorageType

    if requires_number:
        if storage_type == DB.StorageType.Double:
            return float(convert_to_display_units(parameter.AsDouble(), parameter, document))
        if storage_type == DB.StorageType.Integer: return int(parameter.AsInteger())
        try: return float(parameter.AsString() or 0)
        except: return 0.0

    if is_yesno_parameter(parameter):
        return "Yes" if parameter.AsInteger() == 1 else "No"
        
    if storage_type == DB.StorageType.Double:
        val = convert_to_display_units(parameter.AsDouble(), parameter, document)
        return "{:g}".format(round(val, 6))
        
    if storage_type == DB.StorageType.Integer: return str(parameter.AsInteger())
    return parameter.AsString() or ""

def evaluate_parameter(element, document, target_name, expression, eval_math):
    params_dict = get_element_parameters_dict(element, document)
    target_param = params_dict.get(target_name)
    
    if not target_param: return False, "Missing target parameter"
    
    is_numeric_target = target_param.StorageType in [DB.StorageType.Double, DB.StorageType.Integer]
    variables = re.findall(r'\{(.*?)\}', expression)
    evaluated_expr = expression

    for var_name in variables:
        source_param = params_dict.get(var_name)
        val = extract_parameter_value(source_param, document, is_numeric_target)
        evaluated_expr = evaluated_expr.replace(f"{{{var_name}}}", str(val))

    try:
        if is_numeric_target:
            calc_result = eval(evaluated_expr, {"__builtins__": None}, SAFE_MATH)
            if target_param.StorageType == DB.StorageType.Integer:
                return True, int(round(calc_result))
            if target_param.StorageType == DB.StorageType.Double:
                return True, float(calc_result)
        else:
            if eval_math:
                parts = evaluated_expr.split('"')
                result_str = ""
                for i, part in enumerate(parts):
                    if i % 2 == 1:
                        result_str += part
                    else:
                        trimmed = part.strip()
                        if trimmed:
                            leading_ws = part[:len(part) - len(part.lstrip())]
                            trailing_ws = part[len(part.rstrip()):]
                            try:
                                math_res = eval(trimmed, {"__builtins__": None}, SAFE_MATH)
                                if isinstance(math_res, float) and math_res.is_integer():
                                    math_res = int(math_res)
                                elif isinstance(math_res, float):
                                    math_res = round(math_res, 6)
                                result_str += f"{leading_ws}{math_res}{trailing_ws}"
                            except Exception:
                                return False, f"Math error in: {trimmed}"
                        else:
                            result_str += part
                return True, result_str
            else:
                return True, evaluated_expr
                
    except Exception as e:
        return False, f"Syntax error: {str(e)}"

# ====================================================================
# WPF APPLICATION
# ====================================================================

class ParameterCombinerApp(object):
    def __init__(self, xaml_path, elements, document):
        self.elements = elements
        self.document = document
        self.is_updating = False
        self.apply_changes = False
        
        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        self.window = XamlReader.Load(stream)
        stream.Close()
        WindowInteropHelper(self.window).Owner = Process.GetCurrentProcess().MainWindowHandle

        # Global UI Mapping
        self.TargetParamCombo = self.window.FindName("TargetParamCombo")
        self.TextCaseCombo = self.window.FindName("TextCaseCombo")
        self.StatusBar = self.window.FindName("StatusBar")
        self.ApplyBtn = self.window.FindName("ApplyBtn")
        self.CancelBtn = self.window.FindName("CancelBtn")
        self.ElementGrid = self.window.FindName("ElementGrid")
        
        # Grid Controls
        self.FilterGridTextBox = self.window.FindName("FilterGridTextBox")
        self.BtnSelectAll = self.window.FindName("BtnSelectAll")
        self.BtnSelectNone = self.window.FindName("BtnSelectNone")

        # Modes
        self.ModeFormula = self.window.FindName("ModeFormula")
        self.ModeReplace = self.window.FindName("ModeReplace")
        self.ModeAffix = self.window.FindName("ModeAffix")
        self.ModeSeq = self.window.FindName("ModeSeq")
        
        self.GridFormula = self.window.FindName("GridFormula")
        self.GridReplace = self.window.FindName("GridReplace")
        self.GridAffix = self.window.FindName("GridAffix")
        self.GridSeq = self.window.FindName("GridSeq")
        
        # Mode 1: Formula
        self.FormulaRichTextBox = self.window.FindName("FormulaRichTextBox")
        self.ToggleMath = self.window.FindName("ToggleMath")
        self.SuggestPopup = self.window.FindName("SuggestPopup")
        self.SuggestListBox = self.window.FindName("SuggestListBox")
        self.SourceParamCombo = self.window.FindName("SourceParamCombo")
        self.InsertParamBtn = self.window.FindName("InsertParamBtn")
        
        # Mode 2, 3, 4 Inputs
        self.FindTextBox = self.window.FindName("FindTextBox")
        self.ReplaceTextBox = self.window.FindName("ReplaceTextBox")
        self.PrefixTextBox = self.window.FindName("PrefixTextBox")
        self.SuffixTextBox = self.window.FindName("SuffixTextBox")
        self.SeqStartTextBox = self.window.FindName("SeqStartTextBox")
        self.SeqStepTextBox = self.window.FindName("SeqStepTextBox")

        self.setup_data_table()
        self.setup_ui_data()
        self.wire_events()

    def get_rtb_text(self):
        tr = TextRange(self.FormulaRichTextBox.Document.ContentStart, self.FormulaRichTextBox.Document.ContentEnd)
        return tr.Text.strip()

    def setup_data_table(self):
        self.dt = DataTable("ElementsTable")
        self.dt.Columns.Add("Apply", clr.GetClrType(Boolean))
        self.dt.Columns.Add("ID", clr.GetClrType(String))
        self.dt.Columns.Add("Family", clr.GetClrType(String))
        self.dt.Columns.Add("Type", clr.GetClrType(String))
        self.dt.Columns.Add("Preview", clr.GetClrType(String))

        for el in self.elements:
            row = self.dt.NewRow()
            row["Apply"] = True
            row["ID"] = str(el.Id.IntegerValue)
            try:
                row["Family"] = el.Symbol.FamilyName if hasattr(el, 'Symbol') else type(el).__name__
                row["Type"] = el.Name
            except:
                row["Family"], row["Type"] = "Unknown", "Unknown"
            row["Preview"] = ""
            self.dt.Rows.Add(row)
            
        self.ElementGrid.ItemsSource = self.dt.DefaultView

    def setup_ui_data(self):
        if not self.elements: return
        first_elem_params = get_element_parameters_dict(self.elements[0], self.document)
        target_names = {n for n, p in first_elem_params.items() if not p.IsReadOnly}
        source_names = set(first_elem_params.keys())

        for el in self.elements[1:]:
            elem_params = get_element_parameters_dict(el, self.document)
            target_names.intersection_update({n for n, p in elem_params.items() if not p.IsReadOnly})
            source_names.intersection_update(set(elem_params.keys()))

        t_list, s_list = List[String](), List[String]()
        for n in sorted(list(target_names)): t_list.Add(n)
        for n in sorted(list(source_names)): s_list.Add(n)

        self.TargetParamCombo.ItemsSource = t_list
        self.SourceParamCombo.ItemsSource = s_list
        self.SuggestListBox.ItemsSource = s_list
        
        if t_list.Count > 0: self.TargetParamCombo.SelectedIndex = 0
        if s_list.Count > 0: self.SourceParamCombo.SelectedIndex = 0

    def wire_events(self):
        self.ModeFormula.Checked += self.on_mode_changed
        self.ModeReplace.Checked += self.on_mode_changed
        self.ModeAffix.Checked += self.on_mode_changed
        self.ModeSeq.Checked += self.on_mode_changed

        # Fixed "One step behind" bug by hooking SelectionChanged explicitly to SelectedItem
        self.TargetParamCombo.SelectionChanged += self.trigger_preview_update
        self.TextCaseCombo.SelectionChanged += self.trigger_preview_update
        
        self.ToggleMath.Checked += self.trigger_preview_update
        self.ToggleMath.Unchecked += self.trigger_preview_update
        
        self.FindTextBox.TextChanged += self.trigger_preview_update
        self.ReplaceTextBox.TextChanged += self.trigger_preview_update
        self.PrefixTextBox.TextChanged += self.trigger_preview_update
        self.SuffixTextBox.TextChanged += self.trigger_preview_update
        self.SeqStartTextBox.TextChanged += self.trigger_preview_update
        self.SeqStepTextBox.TextChanged += self.trigger_preview_update
        
        # Grid Actions
        self.BtnSelectAll.Click += self.on_select_all
        self.BtnSelectNone.Click += self.on_select_none
        self.FilterGridTextBox.GotFocus += self.on_filter_focus
        self.FilterGridTextBox.LostFocus += self.on_filter_lost_focus
        self.FilterGridTextBox.TextChanged += self.on_filter_changed
        self.ElementGrid.PreviewKeyDown += self.on_grid_keydown 
        
        # Formula RTB
        self.FormulaRichTextBox.TextChanged += self.on_rtb_text_changed
        self.FormulaRichTextBox.PreviewKeyDown += self.on_rtb_preview_keydown
        self.InsertParamBtn.Click += self.on_insert_click
        self.SuggestListBox.MouseDoubleClick += self.on_suggest_doubleclick
        
        self.ApplyBtn.Click += self.on_apply_click
        self.CancelBtn.Click += self.on_cancel_click
        
        self.TargetParamCombo.GotKeyboardFocus += self.combo_got_focus
        self.TargetParamCombo.PreviewKeyUp += self.combo_key_up
        self.SourceParamCombo.GotKeyboardFocus += self.combo_got_focus
        self.SourceParamCombo.PreviewKeyUp += self.combo_key_up

        # Hook row check changes to live preview refresh
        self.dt.ColumnChanged += self.on_dt_column_changed

    def on_dt_column_changed(self, sender, args):
        if args.Column.ColumnName == "Apply":
            self.update_previews()

    def show_error(self, message, is_error=True):
        self.StatusBar.Text = message
        self.StatusBar.Foreground = Brushes.Red if is_error else Brushes.Gray

    # ====================================================================
    # QOL GRID ACTIONS
    # ====================================================================
    def on_select_all(self, sender, args):
        for row in self.dt.Rows: row["Apply"] = True
        self.dt.AcceptChanges()
        self.update_previews()

    def on_select_none(self, sender, args):
        for row in self.dt.Rows: row["Apply"] = False
        self.dt.AcceptChanges()
        self.update_previews()

    def on_filter_focus(self, sender, args):
        if self.FilterGridTextBox.Text == "Filter results...":
            self.FilterGridTextBox.Text = ""
            self.FilterGridTextBox.Foreground = Brushes.Black

    def on_filter_lost_focus(self, sender, args):
        if not self.FilterGridTextBox.Text:
            self.FilterGridTextBox.Text = "Filter results..."
            self.FilterGridTextBox.Foreground = Brushes.Gray

    def on_filter_changed(self, sender, args):
        search_text = self.FilterGridTextBox.Text.lower()
        if search_text == "filter results...": return
        
        view = self.dt.DefaultView
        if not search_text:
            view.RowFilter = ""
        else:
            view.RowFilter = f"ID LIKE '%{search_text}%' OR Family LIKE '%{search_text}%' OR Type LIKE '%{search_text}%'"

    def on_grid_keydown(self, sender, args):
        # Spacebar Multi-Toggle!
        if args.Key == Key.Space and self.ElementGrid.SelectedItems.Count > 0:
            try:
                first_row = self.ElementGrid.SelectedItems[0].Row
                new_state = not first_row["Apply"]
                for item in self.ElementGrid.SelectedItems:
                    item.Row["Apply"] = new_state
                self.dt.AcceptChanges()
                self.update_previews()
                args.Handled = True
            except: pass

    def combo_got_focus(self, sender, args):
        sender.IsDropDownOpen = True

    def combo_key_up(self, sender, args):
        if args.Key in [Key.Up, Key.Down, Key.Enter, Key.Escape, Key.Left, Key.Right]: return
        search_text = sender.Text.lower()
        view = CollectionViewSource.GetDefaultView(sender.ItemsSource)
        if not view: return
        view.Filter = Predicate[Object](lambda item: not search_text or search_text in str(item).lower())
        sender.IsDropDownOpen = True

    # ====================================================================
    # MODE LOGIC
    # ====================================================================
    def on_mode_changed(self, sender, args):
        self.GridFormula.Visibility = Visibility.Collapsed
        self.GridReplace.Visibility = Visibility.Collapsed
        self.GridAffix.Visibility = Visibility.Collapsed
        self.GridSeq.Visibility = Visibility.Collapsed
        
        if self.ModeFormula.IsChecked: self.GridFormula.Visibility = Visibility.Visible
        elif self.ModeReplace.IsChecked: self.GridReplace.Visibility = Visibility.Visible
        elif self.ModeAffix.IsChecked: self.GridAffix.Visibility = Visibility.Visible
        elif self.ModeSeq.IsChecked: self.GridSeq.Visibility = Visibility.Visible
        
        self.update_previews()

    def trigger_preview_update(self, sender, args):
        self.update_previews()

    def update_previews(self):
        # Pull exact SelectedItem instead of .Text to fix scrolling bug
        target = self.TargetParamCombo.SelectedItem
        if not target: target = self.TargetParamCombo.Text
        if not target: return
        
        case_mode = self.TextCaseCombo.Text
        
        mode = 0
        if self.ModeReplace.IsChecked: mode = 1
        elif self.ModeAffix.IsChecked: mode = 2
        elif self.ModeSeq.IsChecked: mode = 3
        
        expr = self.get_rtb_text()
        eval_math = self.ToggleMath.IsChecked
        
        find_text = self.FindTextBox.Text
        repl_text = self.ReplaceTextBox.Text
        pref_text = self.PrefixTextBox.Text
        suff_text = self.SuffixTextBox.Text
        seq_start = self.SeqStartTextBox.Text
        try: seq_step = int(self.SeqStepTextBox.Text)
        except: seq_step = 1
        
        seq_index = 0
        
        for i, el in enumerate(self.elements):
            row = self.dt.Rows[i]
            
            params_dict = get_element_parameters_dict(el, self.document)
            target_param = params_dict.get(target)
            existing_val = str(extract_parameter_value(target_param, self.document, False)) if target_param else ""
            
            preview_val = existing_val
            
            if row["Apply"]:
                if mode == 0:
                    if expr:
                        success, result = evaluate_parameter(el, self.document, target, expr, eval_math)
                        preview_val = str(result)
                elif mode == 1:
                    if find_text:
                        preview_val = existing_val.replace(find_text, repl_text)
                elif mode == 2:
                    if pref_text or suff_text:
                        preview_val = pref_text + existing_val + suff_text
                elif mode == 3:
                    if seq_start:
                        match = re.search(r'(\d+)$', seq_start)
                        if match:
                            num_str = match.group(1)
                            prefix = seq_start[:-len(num_str)]
                            num_len = len(num_str)
                            new_num = int(num_str) + seq_index * seq_step
                            preview_val = prefix + str(new_num).zfill(num_len)
                        else:
                            preview_val = seq_start + (str(seq_index * seq_step) if seq_index > 0 else "")
                        seq_index += 1
            
            # Apply Global Case Conversion
            if target_param and target_param.StorageType != DB.StorageType.Double and target_param.StorageType != DB.StorageType.Integer:
                if case_mode == "UPPERCASE": preview_val = preview_val.upper()
                elif case_mode == "lowercase": preview_val = preview_val.lower()
                elif case_mode == "Title Case": preview_val = preview_val.title()

            row["Preview"] = preview_val
                    
        self.ElementGrid.Items.Refresh()

    # ====================================================================
    # FORMULA RTB LOGIC
    # ====================================================================
    def highlight_syntax(self):
        doc_range = TextRange(self.FormulaRichTextBox.Document.ContentStart, self.FormulaRichTextBox.Document.ContentEnd)
        doc_range.ApplyPropertyValue(TextElement.ForegroundProperty, Brushes.Black)
        doc_range.ApplyPropertyValue(TextElement.FontWeightProperty, FontWeights.Normal)

        ranges_to_highlight = []
        ptr = self.FormulaRichTextBox.Document.ContentStart

        while ptr is not None:
            if ptr.GetPointerContext(LogicalDirection.Forward) == TextPointerContext.Text:
                text = ptr.GetTextInRun(LogicalDirection.Forward)
                for match in re.finditer(r'\{[^}]+\}', text):
                    start_ptr = ptr.GetPositionAtOffset(match.start())
                    end_ptr = ptr.GetPositionAtOffset(match.end())
                    if start_ptr and end_ptr:
                        ranges_to_highlight.append(TextRange(start_ptr, end_ptr))
            ptr = ptr.GetNextContextPosition(LogicalDirection.Forward)

        for tr in ranges_to_highlight:
            tr.ApplyPropertyValue(TextElement.ForegroundProperty, Brushes.DodgerBlue)
            tr.ApplyPropertyValue(TextElement.FontWeightProperty, FontWeights.Bold)

    def on_rtb_text_changed(self, sender, args):
        if self.is_updating: return
        self.is_updating = True
        try:
            self.highlight_syntax()
            self.update_previews()
            self.handle_autosuggest()
        finally:
            self.is_updating = False

    def handle_autosuggest(self):
        caret = self.FormulaRichTextBox.CaretPosition
        tr = TextRange(self.FormulaRichTextBox.Document.ContentStart, caret)
        text_before = tr.Text
        
        match = re.search(r'\{([^}]*)$', text_before)
        if match:
            search_query = match.group(1).lower()
            view = CollectionViewSource.GetDefaultView(self.SuggestListBox.ItemsSource)
            view.Filter = Predicate[Object](lambda item: not search_query or search_query in str(item).lower())
            
            if view.IsEmpty:
                self.SuggestPopup.IsOpen = False
            else:
                self.SuggestListBox.SelectedIndex = 0
                self.SuggestPopup.IsOpen = True
        else:
            self.SuggestPopup.IsOpen = False

    def on_rtb_preview_keydown(self, sender, args):
        if self.SuggestPopup.IsOpen:
            if args.Key == Key.Down:
                idx = self.SuggestListBox.SelectedIndex + 1
                if idx >= self.SuggestListBox.Items.Count: idx = 0
                self.SuggestListBox.SelectedIndex = idx
                self.SuggestListBox.ScrollIntoView(self.SuggestListBox.SelectedItem)
                args.Handled = True
            elif args.Key == Key.Up:
                idx = self.SuggestListBox.SelectedIndex - 1
                if idx < 0: idx = self.SuggestListBox.Items.Count - 1
                self.SuggestListBox.SelectedIndex = idx
                self.SuggestListBox.ScrollIntoView(self.SuggestListBox.SelectedItem)
                args.Handled = True
            elif args.Key in [Key.Enter, Key.Tab]:
                if self.SuggestListBox.SelectedItem:
                    self.insert_parameter(self.SuggestListBox.SelectedItem, replace_partial=True)
                    args.Handled = True
            elif args.Key == Key.Escape:
                self.SuggestPopup.IsOpen = False
                args.Handled = True

    def insert_parameter(self, param_name, replace_partial=False):
        self.is_updating = True
        try:
            caret = self.FormulaRichTextBox.CaretPosition
            if replace_partial:
                tr_search = TextRange(self.FormulaRichTextBox.Document.ContentStart, caret)
                match = re.search(r'\{([^}]*)$', tr_search.Text)
                if match:
                    start_ptr = caret.GetPositionAtOffset(-len(match.group(0)), LogicalDirection.Backward)
                    if start_ptr:
                        TextRange(start_ptr, caret).Text = ""
                        caret = self.FormulaRichTextBox.CaretPosition

            tr_insert = TextRange(caret, caret)
            tr_insert.Text = f"{{{param_name}}}"
            self.FormulaRichTextBox.CaretPosition = tr_insert.End
            self.SuggestPopup.IsOpen = False

        finally:
            self.is_updating = False

        self.is_updating = True
        try:
            self.highlight_syntax()
            self.update_previews()
        finally:
            self.is_updating = False

        self.FormulaRichTextBox.Focus()

    def on_suggest_doubleclick(self, sender, args):
        if self.SuggestListBox.SelectedItem:
            self.insert_parameter(self.SuggestListBox.SelectedItem, replace_partial=True)

    def on_insert_click(self, sender, args):
        if self.SourceParamCombo.Text:
            self.insert_parameter(self.SourceParamCombo.Text, replace_partial=False)

    def on_cancel_click(self, sender, args):
        self.window.Close()

    # ====================================================================
    # APPLY LOGIC
    # ====================================================================
    def on_apply_click(self, sender, args):
        target_name = self.TargetParamCombo.Text
        if not target_name:
            self.show_error("Please select a target parameter.")
            return

        test_param = get_element_parameters_dict(self.elements[0], self.document).get(target_name)
        
        for i, el in enumerate(self.elements):
            row = self.dt.Rows[i]
            if not row["Apply"]: continue 
            val_str = row["Preview"]
            
            if "error" in val_str.lower() or "missing" in val_str.lower() or "unsupported" in val_str.lower():
                self.show_error(f"Error on ID {el.Id}: Please fix formula before applying.")
                return
                
            if test_param and test_param.StorageType in [DB.StorageType.Double, DB.StorageType.Integer]:
                try:
                    float(val_str)
                except ValueError:
                    self.show_error(f"Format Error: Tried to push text '{val_str}' into a numeric parameter.")
                    return

        self.apply_changes = True
        self.final_target = target_name
        self.window.Close()


# ====================================================================
# MAIN EXECUTION
# ====================================================================

if __name__ == "__main__":
    uidoc = __revit__.ActiveUIDocument
    doc = uidoc.Document

    selection_ids = uidoc.Selection.GetElementIds()
    selected_elements = [doc.GetElement(e_id) for e_id in selection_ids]

    if not selected_elements:
        TaskDialog.Show("Error", "Please select elements before running this tool.")
    else:
        script_dir = os.path.dirname(__file__)
        xaml_path = os.path.join(script_dir, 'ui.xaml')
        
        app = ParameterCombinerApp(xaml_path, selected_elements, doc)
        app.window.ShowDialog()

        if app.apply_changes:
            transaction = DB.Transaction(doc, "Combine Parameters")
            transaction.Start()
            
            error_encountered = False
            for i, el in enumerate(app.elements):
                row = app.dt.Rows[i]
                if not row["Apply"]: continue 
                
                preview_val = row["Preview"]
                try:
                    param = get_element_parameters_dict(el, doc).get(app.final_target)
                    
                    if param.StorageType == DB.StorageType.Double:
                        internal_num = convert_to_internal_units(float(preview_val), param, doc)
                        param.Set(float(internal_num))
                    elif param.StorageType == DB.StorageType.Integer:
                        param.Set(int(float(preview_val)))
                    else:
                        param.Set(str(preview_val))
                except Exception as e:
                    print(f"Failed to set ID {el.Id}: {e}")
                    error_encountered = True

            transaction.Commit()
            
            if error_encountered:
                TaskDialog.Show("Warning", "Changes applied, but some elements failed. Check pyRevit console for details.")
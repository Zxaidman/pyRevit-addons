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
from System.Windows import FontWeights
from System.IO import FileStream, FileMode, FileAccess
from System.Diagnostics import Process
from System.Windows.Interop import WindowInteropHelper
from System import String, Predicate, Object, Boolean
from System.Collections.Generic import List
from System.Windows.Data import CollectionViewSource
from System.Windows.Input import Key
from System.Data import DataTable

# Safe Math Dictionary for eval() - Generated dynamically for case-insensitivity
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

# ====================================================================
# EVALUATION LOGIC
# ====================================================================

def evaluate_parameter(element, document, target_name, expression, eval_math, mixed_mode):
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
        # Numeric Parameters ALWAYS Evaluate Math
        if is_numeric_target:
            calc_result = eval(evaluated_expr, {"__builtins__": None}, SAFE_MATH)
            if target_param.StorageType == DB.StorageType.Integer:
                return True, int(round(calc_result))
            if target_param.StorageType == DB.StorageType.Double:
                return True, float(calc_result)
                
        # Text Parameters Behaviors
        else:
            if mixed_mode:
                # Parse string by double-quotes
                parts = evaluated_expr.split('"')
                result_str = ""
                for i, part in enumerate(parts):
                    if i % 2 == 1:
                        # Inside quotes: Literal Text
                        result_str += part
                    else:
                        # Outside quotes: Math eval (preserves whitespace wrapping)
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
                            except Exception as e:
                                return False, f"Math error in: {trimmed}"
                        else:
                            result_str += part # Just spaces
                return True, result_str
                
            elif eval_math:
                # Force entire expression to be calculated
                trimmed = evaluated_expr.strip()
                if trimmed:
                    calc_result = eval(trimmed, {"__builtins__": None}, SAFE_MATH)
                    if isinstance(calc_result, float) and calc_result.is_integer():
                        calc_result = int(calc_result)
                    elif isinstance(calc_result, float):
                        calc_result = round(calc_result, 6)
                    return True, str(calc_result)
                return True, ""
                
            else:
                # Default (No toggles): Standard string replacement
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
        self.final_target = ""
        self.final_formula = ""
        self.final_eval_math = False
        self.final_mixed_mode = False

        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        self.window = XamlReader.Load(stream)
        stream.Close()
        WindowInteropHelper(self.window).Owner = Process.GetCurrentProcess().MainWindowHandle

        self.TargetParamCombo = self.window.FindName("TargetParamCombo")
        self.FormulaRichTextBox = self.window.FindName("FormulaRichTextBox")
        self.ToggleEvalMath = self.window.FindName("ToggleEvalMath")
        self.ToggleMixedMode = self.window.FindName("ToggleMixedMode")
        self.SuggestPopup = self.window.FindName("SuggestPopup")
        self.SuggestListBox = self.window.FindName("SuggestListBox")
        self.SourceParamCombo = self.window.FindName("SourceParamCombo")
        self.InsertParamBtn = self.window.FindName("InsertParamBtn")
        self.ApplyBtn = self.window.FindName("ApplyBtn")
        self.CancelBtn = self.window.FindName("CancelBtn")
        self.StatusBar = self.window.FindName("StatusBar")
        self.ElementGrid = self.window.FindName("ElementGrid")

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
        self.TargetParamCombo.SelectionChanged += self.trigger_preview_update
        self.ToggleEvalMath.Checked += self.trigger_preview_update
        self.ToggleEvalMath.Unchecked += self.trigger_preview_update
        self.ToggleMixedMode.Checked += self.trigger_preview_update
        self.ToggleMixedMode.Unchecked += self.trigger_preview_update
        
        self.FormulaRichTextBox.TextChanged += self.on_rtb_text_changed
        self.FormulaRichTextBox.PreviewKeyDown += self.on_rtb_preview_keydown
        self.InsertParamBtn.Click += self.on_insert_click
        self.ApplyBtn.Click += self.on_apply_click
        self.CancelBtn.Click += self.on_cancel_click
        self.SuggestListBox.MouseDoubleClick += self.on_suggest_doubleclick

        self.TargetParamCombo.GotKeyboardFocus += self.combo_got_focus
        self.TargetParamCombo.PreviewKeyUp += self.combo_key_up
        self.SourceParamCombo.GotKeyboardFocus += self.combo_got_focus
        self.SourceParamCombo.PreviewKeyUp += self.combo_key_up

    def show_error(self, message, is_error=True):
        self.StatusBar.Text = message
        self.StatusBar.Foreground = Brushes.Red if is_error else Brushes.Gray

    def combo_got_focus(self, sender, args):
        sender.IsDropDownOpen = True

    def combo_key_up(self, sender, args):
        if args.Key in [Key.Up, Key.Down, Key.Enter, Key.Escape, Key.Left, Key.Right]: return
        search_text = sender.Text.lower()
        view = CollectionViewSource.GetDefaultView(sender.ItemsSource)
        if not view: return
        view.Filter = Predicate[Object](lambda item: not search_text or search_text in str(item).lower())
        sender.IsDropDownOpen = True

    def trigger_preview_update(self, sender, args):
        self.update_previews()

    def update_previews(self):
        target = self.TargetParamCombo.Text
        if not target: return
        expr = self.get_rtb_text()
        eval_math = self.ToggleEvalMath.IsChecked
        mixed_mode = self.ToggleMixedMode.IsChecked
        
        for i, el in enumerate(self.elements):
            row = self.dt.Rows[i]
            if not expr:
                row["Preview"] = ""
                continue
            success, result = evaluate_parameter(el, self.document, target, expr, eval_math, mixed_mode)
            row["Preview"] = str(result)
            
        self.ElementGrid.Items.Refresh()

    def highlight_syntax(self):
        """Finds all {Parameters} in the document and colors them Blue automatically."""
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
            tr.ApplyPropertyValue(TextElement.ForegroundProperty, Brushes.Blue)
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

    def on_apply_click(self, sender, args):
        target_name = self.TargetParamCombo.Text
        if not target_name:
            self.show_error("Please select a target parameter.")
            return
            
        expr = self.get_rtb_text()
        if not expr:
            self.show_error("Please write a formula.")
            return

        for i, el in enumerate(self.elements):
            row = self.dt.Rows[i]
            if not row["Apply"]: continue 
            val_str = row["Preview"]
            if "Math error" in val_str or "Missing" in val_str or "Syntax" in val_str or "Unsupported" in val_str:
                self.show_error(f"Error on ID {el.Id}: Please fix formula before applying.")
                return

        self.apply_changes = True
        self.final_target = target_name
        self.final_formula = expr
        self.final_eval_math = self.ToggleEvalMath.IsChecked
        self.final_mixed_mode = self.ToggleMixedMode.IsChecked
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
                
                success, result = evaluate_parameter(el, doc, app.final_target, app.final_formula, app.final_eval_math, app.final_mixed_mode)
                if success:
                    try:
                        param = get_element_parameters_dict(el, doc).get(app.final_target)
                        if param.StorageType == DB.StorageType.Double:
                            param.Set(float(convert_to_internal_units(result, param, doc)))
                        elif param.StorageType == DB.StorageType.Integer:
                            param.Set(int(result))
                        else:
                            param.Set(str(result))
                    except Exception as e:
                        print(f"Failed to set ID {el.Id}: {e}")
                        error_encountered = True

            transaction.Commit()
            
            if error_encountered:
                TaskDialog.Show("Warning", "Changes applied, but some elements failed. Check console for details.")
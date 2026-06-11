# -*- coding: utf-8 -*-

__title__ = 'Export Schedules'
__author__ = 'ZAID'

import os
import clr
import tempfile

clr.AddReference('RevitAPI')
clr.AddReference('RevitUIAPI')
from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewSchedule, ViewScheduleExportOptions,
    ExportTextQualifier, ExportColumnHeaders, Transaction, SectionType
)

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Windows.Forms')

import System
from System.Windows import Window, Thickness, HorizontalAlignment, VerticalAlignment, \
    GridLength, GridUnitType, TextWrapping, Visibility, MessageBox
from System.Windows.Controls import (
    Grid, StackPanel, Border, Label, TextBox, Button, ScrollViewer, 
    RowDefinition, ColumnDefinition, TextBlock, CheckBox, ListBox, ListBoxItem
)
from System.Windows.Media import (
    SolidColorBrush, Color, LinearGradientBrush, GradientStop, FontFamily
)
from System.Windows.Media.Effects import DropShadowEffect
from System.Windows.Input import Cursors
from System.Windows.Markup import XamlReader

from pyrevit import script, forms

# Initialize Revit document
doc = __revit__.ActiveUIDocument.Document

# ═══════════════════════════════════════════════════════════════════════════
# COLOURS & STYLING (Matching Claude AI Script)
# ═══════════════════════════════════════════════════════════════════════════
C_BG        = Color.FromRgb(13,  17,  30)    # #0D111E deep navy
C_SURFACE   = Color.FromRgb(22,  28,  46)    # #161C2E card
C_BORDER    = Color.FromRgb(40,  50,  80)    # subtle border
C_ACCENT    = Color.FromRgb(32, 200, 170)    # #20C8AA teal
C_ACCENT2   = Color.FromRgb(20, 150, 200)    # #1496C8 blue highlight
C_TEXT      = Color.FromRgb(230, 235, 245)   # near-white
C_MUTED     = Color.FromRgb(120, 135, 165)   # muted label
C_INPUT_BG  = Color.FromRgb(18,  23,  40)    # input field bg

def brush(c): return SolidColorBrush(c)

def accent_gradient():
    g = LinearGradientBrush()
    g.StartPoint = System.Windows.Point(0, 0)
    g.EndPoint   = System.Windows.Point(1, 0)
    g.GradientStops.Add(GradientStop(C_ACCENT, 0.0))
    g.GradientStops.Add(GradientStop(C_ACCENT2, 1.0))
    return g

def shadow(blur=12, opacity=0.4, depth=2):
    e = DropShadowEffect()
    e.BlurRadius  = blur
    e.Opacity     = opacity
    e.ShadowDepth = depth
    e.Color       = Color.FromRgb(0, 0, 0)
    return e

# ═══════════════════════════════════════════════════════════════════════════
# WPF HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def section_header(text):
    sp = StackPanel()
    sp.Orientation = System.Windows.Controls.Orientation.Horizontal
    sp.Margin      = Thickness(0, 0, 0, 8)
    bar = Border()
    bar.Width, bar.Background, bar.Margin = 3, accent_gradient(), Thickness(0, 2, 10, 2)
    sp.Children.Add(bar)
    tb = TextBlock()
    tb.Text, tb.FontSize, tb.Foreground = text, 11, brush(C_ACCENT)
    tb.FontWeight = System.Windows.FontWeights.SemiBold
    sp.Children.Add(tb)
    return sp

def card(content_panel):
    b = Border()
    b.Background, b.BorderBrush, b.BorderThickness = brush(C_SURFACE), brush(C_BORDER), Thickness(1)
    b.CornerRadius, b.Padding, b.Margin = System.Windows.CornerRadius(8), Thickness(16, 14, 16, 14), Thickness(0, 0, 0, 12)
    b.Effect = shadow()
    b.Child = content_panel
    return b

# ═══════════════════════════════════════════════════════════════════════════
# MAIN DIALOG CLASS
# ═══════════════════════════════════════════════════════════════════════════
class ScheduleExportDialog(Window):
    def __init__(self, schedules):
        self.result = None
        self.schedules = sorted(schedules, key=lambda s: s.Name)
        self._build_ui()

    def _build_ui(self):
        self.Title = "Export Schedules to Excel"
        self.Width, self.Height = 500, 620
        self.Background, self.FontFamily = brush(C_BG), FontFamily("Segoe UI")
        self.WindowStartupLocation = System.Windows.WindowStartupLocation.CenterScreen
        self.ResizeMode = System.Windows.ResizeMode.NoResize

        main_grid = Grid()
        main_grid.RowDefinitions.Add(RowDefinition()) # Header
        main_grid.RowDefinitions[0].Height = GridLength(80)
        main_grid.RowDefinitions.Add(RowDefinition()) # Content
        main_grid.RowDefinitions.Add(RowDefinition()) # Footer
        main_grid.RowDefinitions[2].Height = GridLength(80)
        self.Content = main_grid

        # Header
        header = Border()
        header.Background = brush(C_BG)
        header.Padding = Thickness(24, 0, 24, 0)
        title_stack = StackPanel()
        title_stack.VerticalAlignment = VerticalAlignment.Center
        t1 = TextBlock()
        t1.Text, t1.FontSize, t1.FontWeight, t1.Foreground = "Excel Exporter", 20, System.Windows.FontWeights.Bold, brush(C_TEXT)
        t2 = TextBlock()
        t2.Text, t2.FontSize, t2.Foreground = "Compile multiple schedules into one Excel file", 11, brush(C_MUTED)
        title_stack.Children.Add(t1); title_stack.Children.Add(t2)
        header.Child = title_stack
        Grid.SetRow(header, 0); main_grid.Children.Add(header)

        # Content
        content_stack = StackPanel()
        content_stack.Margin = Thickness(24, 10, 24, 10)
        
        # Schedule List Card
        list_panel = StackPanel()
        
        # Header with All/None buttons
        list_header_grid = Grid()
        list_header_grid.ColumnDefinitions.Add(ColumnDefinition())
        list_header_grid.ColumnDefinitions.Add(ColumnDefinition())
        list_header_grid.ColumnDefinitions[1].Width = GridLength.Auto
        
        list_header_grid.Children.Add(section_header("SELECT SCHEDULES"))
        
        btn_stack = StackPanel()
        btn_stack.Orientation = System.Windows.Controls.Orientation.Horizontal
        
        btn_all = Button()
        btn_all.Content, btn_all.Width, btn_all.Margin = "All", 50, Thickness(0,0,5,8)
        self._apply_button_style(btn_all)
        btn_all.Click += self._select_all
        
        btn_none = Button()
        btn_none.Content, btn_none.Width, btn_none.Margin = "None", 50, Thickness(0,0,0,8)
        self._apply_button_style(btn_none)
        btn_none.Click += self._select_none
        
        btn_stack.Children.Add(btn_all); btn_stack.Children.Add(btn_none)
        Grid.SetColumn(btn_stack, 1); list_header_grid.Children.Add(btn_stack)
        list_panel.Children.Add(list_header_grid)

        # Search Bar
        search_panel = Border()
        search_panel.Margin = Thickness(0, 0, 0, 10)
        self.search_box = TextBox()
        self.search_box.Text = "Search schedules..."
        self.search_box.Background = brush(C_INPUT_BG)
        self.search_box.Foreground = brush(C_MUTED)
        self.search_box.BorderBrush = brush(C_BORDER)
        self.search_box.Padding = Thickness(8, 5, 8, 5)
        
        def on_search_focus(s, e):
            if s.Text == "Search schedules...":
                s.Text = ""; s.Foreground = brush(C_TEXT)
        def on_search_blur(s, e):
            if not s.Text:
                s.Text = "Search schedules..."; s.Foreground = brush(C_MUTED)
        
        self.search_box.GotFocus += on_search_focus
        self.search_box.LostFocus += on_search_blur
        self.search_box.TextChanged += self._filter_list
        search_panel.Child = self.search_box
        list_panel.Children.Add(search_panel)

        # Unit Stripping Checkbox
        self.chk_strip = CheckBox()
        self.chk_strip.Content = "Strip Units"
        self.chk_strip.ToolTip = "Removes unit suffixes (mm, m, kg, etc.) and converts values to numbers for calculation."
        self.chk_strip.IsChecked = True
        self.chk_strip.Foreground = brush(C_TEXT)
        self.chk_strip.Margin = Thickness(0, 0, 0, 10)
        list_panel.Children.Add(self.chk_strip)
        
        # Hidden Fields Checkbox
        self.chk_hidden = CheckBox()
        self.chk_hidden.Content = "Include Hidden"
        self.chk_hidden.ToolTip = "Temporarily unhides columns that are hidden in the Revit schedule view."
        self.chk_hidden.IsChecked = False
        self.chk_hidden.Foreground = brush(C_TEXT)
        self.chk_hidden.Margin = Thickness(0, 0, 0, 10)
        list_panel.Children.Add(self.chk_hidden)

        # Alternating Row Shading Checkbox
        self.chk_shade = CheckBox()
        self.chk_shade.Content = "Zebra Shading"
        self.chk_shade.ToolTip = "Applies alternating background colors to rows for better readability."
        self.chk_shade.IsChecked = True
        self.chk_shade.Foreground = brush(C_TEXT)
        self.chk_shade.Margin = Thickness(0, 0, 0, 10)
        list_panel.Children.Add(self.chk_shade)

        # Save as PDF Checkbox
        self.chk_pdf = CheckBox()
        self.chk_pdf.Content = "Save PDF"
        self.chk_pdf.ToolTip = "Generates a PDF version of the schedules in the same location as the Excel file."
        self.chk_pdf.IsChecked = False
        self.chk_pdf.Foreground = brush(C_TEXT)
        self.chk_pdf.Margin = Thickness(0, 0, 0, 10)
        list_panel.Children.Add(self.chk_pdf)

        self.listbox = ListBox()
        self.listbox.Background = brush(C_INPUT_BG)
        self.listbox.BorderThickness = Thickness(0)
        self.listbox.Height = 350
        self.listbox.Foreground = brush(C_TEXT)
        
        for s in self.schedules:
            item = ListBoxItem()
            chk = CheckBox()
            # Wrapping name in TextBlock prevents WPF from interpreting underscores (_) as mnemonics/shortcuts
            tb_name = TextBlock()
            tb_name.Text = s.Name
            chk.Content = tb_name
            chk.Foreground = brush(C_TEXT)
            chk.Margin = Thickness(5)
            item.Content = chk
            item.Tag = s
            self.listbox.Items.Add(item)
            
        list_panel.Children.Add(self.listbox)
        content_stack.Children.Add(card(list_panel))
        
        Grid.SetRow(content_stack, 1); main_grid.Children.Add(content_stack)

        # Footer
        footer = Border()
        footer.Padding = Thickness(24, 0, 24, 0)
        footer_stack = StackPanel()
        footer_stack.Orientation = System.Windows.Controls.Orientation.Horizontal
        footer_stack.HorizontalAlignment = HorizontalAlignment.Right
        footer_stack.VerticalAlignment = VerticalAlignment.Center
        
        btn_cancel = Button()
        btn_cancel.Content, btn_cancel.Width, btn_cancel.Height = "Cancel", 100, 35
        btn_cancel.Click += lambda s, e: self.Close()
        btn_cancel.Margin = Thickness(0, 0, 10, 0)
        
        btn_run = Button()
        btn_run.Content, btn_run.Width, btn_run.Height = "Export", 120, 35
        btn_run.Background = accent_gradient()
        btn_run.Foreground = brush(C_BG)
        btn_run.FontWeight = System.Windows.FontWeights.Bold
        btn_run.Click += self._run
        
        footer_stack.Children.Add(btn_cancel)
        footer_stack.Children.Add(btn_run)
        footer.Child = footer_stack
        Grid.SetRow(footer, 2); main_grid.Children.Add(footer)

    def _apply_button_style(self, btn):
        """Applies the outline theme from the Claude AI script."""
        btn.Background = brush(C_SURFACE)
        btn.Foreground = brush(C_ACCENT)
        btn.BorderBrush = brush(C_ACCENT)
        btn.BorderThickness = Thickness(1)
        btn.Padding = Thickness(5, 2, 5, 2)
        btn.Cursor = Cursors.Hand
        def enter(s, e): 
            s.BorderBrush = brush(Color.FromRgb(45, 220, 185))
            s.Foreground = brush(Color.FromRgb(45, 220, 185))
        def leave(s, e): 
            s.BorderBrush = brush(C_ACCENT)
            s.Foreground = brush(C_ACCENT)
        btn.MouseEnter += enter
        btn.MouseLeave += leave

    def _filter_list(self, sender, args):
        search_txt = self.search_box.Text.lower()
        if search_txt == "search schedules...": return
        for item in self.listbox.Items:
            # ListBoxItem -> CheckBox -> TextBlock
            name = item.Content.Content.Text.lower()
            if search_txt in name:
                item.Visibility = Visibility.Visible
            else:
                item.Visibility = Visibility.Collapsed

    def _select_all(self, sender, args):
        for item in self.listbox.Items:
            item.Content.IsChecked = True

    def _select_none(self, sender, args):
        for item in self.listbox.Items:
            item.Content.IsChecked = False

    def _run(self, sender, args):
        selected = []
        for item in self.listbox.Items:
            if item.Content.IsChecked:
                selected.append(item.Tag)
        
        if not selected:
            MessageBox.Show("Please select at least one schedule.")
            return
            
        # Predefined name based on Revit Project
        default_name = "{}_Schedules.xlsx".format(doc.Title)
        path = forms.save_file(
            file_ext='xlsx', 
            default_name=default_name, 
            title="Select Export Location"
        )
        
        if not path: return
            
        self.result = (selected, path, self.chk_strip.IsChecked, self.chk_hidden.IsChecked, self.chk_shade.IsChecked, self.chk_pdf.IsChecked)
        self.Close()

# ═══════════════════════════════════════════════════════════════════════════
# EXCEL EXPORT LOGIC
# ═══════════════════════════════════════════════════════════════════════════
def export_schedules_to_excel(schedules, output_path, strip_units=True, include_hidden=False, shade_rows=True, save_pdf=False):
    """
    Exports schedules to temporary text files, then compiles them into 
    a single Excel workbook using COM Interop.
    """
    # Using Activator and Reflection to avoid Reference/IOError and AttributeError issues
    from System import Type, Activator, Reflection
    f_get = Reflection.BindingFlags.GetProperty
    f_set = Reflection.BindingFlags.SetProperty
    f_inv = Reflection.BindingFlags.InvokeMethod

    excel_type = Type.GetTypeFromProgID("Excel.Application")
    excel_app = Activator.CreateInstance(excel_type)
    
    # Safely set app properties
    excel_type.InvokeMember("Visible", f_set, None, excel_app, System.Array[object]([False]))
    excel_type.InvokeMember("DisplayAlerts", f_set, None, excel_app, System.Array[object]([False]))
    
    workbooks = excel_type.InvokeMember("Workbooks", f_get, None, excel_app, None)
    workbook = excel_type.InvokeMember("Add", f_inv, None, workbooks, None)
    workbook_type = workbook.GetType()
    
    try:
        temp_dir = tempfile.gettempdir()
        sheets = workbook_type.InvokeMember("Sheets", f_get, None, workbook, None)
        sheets_type = sheets.GetType()

        # Remove default sheets except the first one
        count = sheets_type.InvokeMember("Count", f_get, None, sheets, None)
        while count > 1:
            sheet_to_del = sheets_type.InvokeMember("Item", f_get, None, sheets, System.Array[object]([2]))
            sheet_to_del.GetType().InvokeMember("Delete", f_inv, None, sheet_to_del, None)
            count = sheets_type.InvokeMember("Count", f_get, None, sheets, None)
            
        for i, sched in enumerate(schedules):
            # 1. Export Schedule to Temp TSV (Tab Separated Values)
            temp_filename = "revit_export_{}.txt".format(i)
            temp_path = os.path.join(temp_dir, temp_filename)
            
            opt = ViewScheduleExportOptions()
            opt.FieldDelimiter = "\t" # Tab
            opt.TextQualifier = ExportTextQualifier.DoubleQuote
            opt.ColumnHeaders = ExportColumnHeaders.OneRow
            
            # Temporarily unhide fields if requested
            hidden_fields = []
            if include_hidden:
                definition = sched.Definition
                count = definition.GetFieldCount()
                t_unhide = Transaction(doc, "Temp Unhide Fields")
                t_unhide.Start()
                for j in range(count):
                    field = definition.GetField(j)
                    if field.IsHidden:
                        hidden_fields.append(j)
                        field.IsHidden = False
                t_unhide.Commit()

            sched.Export(temp_dir, temp_filename, opt)
            
            # Restore hidden state
            if include_hidden and hidden_fields:
                t_restore = Transaction(doc, "Restore Hidden Fields")
                t_restore.Start()
                for j in hidden_fields:
                    sched.Definition.GetField(j).IsHidden = True
                t_restore.Commit()

            # 2. Add or use sheet
            if i == 0:
                worksheet = sheets_type.InvokeMember("Item", f_get, None, sheets, System.Array[object]([1]))
            else:
                # Get the current last sheet to use as the 'After' argument
                current_count = sheets_type.InvokeMember("Count", f_get, None, sheets, None)
                last_sheet = sheets_type.InvokeMember("Item", f_get, None, sheets, System.Array[object]([current_count]))
                # Add(Before, After, Count, Type) - Passing 'Missing' for Before and the last_sheet for After
                args = System.Array[object]([System.Type.Missing, last_sheet])
                worksheet = sheets_type.InvokeMember("Add", f_inv, None, sheets, args)
            
            worksheet_type = worksheet.GetType()
            
            # Preserving names: Only replace characters strictly forbidden by Excel (\ / ? * [ ] :)
            sheet_name = sched.Name
            for char in [':', '\\', '/', '?', '*', '[', ']']:
                sheet_name = sheet_name.replace(char, '_')
            worksheet_type.InvokeMember("Name", f_set, None, worksheet, System.Array[object]([sheet_name[:31]]))
            
            # 3. Import data from TSV into the sheet
            # We use QueryTables for high performance import of the text file
            connection_str = "TEXT;" + temp_path
            
            qts = worksheet_type.InvokeMember("QueryTables", f_get, None, worksheet, None)
            range_obj = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[object](["A1"]))
            
            qt = qts.GetType().InvokeMember("Add", f_inv, None, qts, System.Array[object]([connection_str, range_obj]))
            qt_type = qt.GetType()
            
            qt_type.InvokeMember("TextFileParseType", f_set, None, qt, System.Array[object]([1])) # 1 = xlDelimited
            qt_type.InvokeMember("TextFileTabDelimiter", f_set, None, qt, System.Array[object]([True]))
            qt_type.InvokeMember("Refresh", f_inv, None, qt, System.Array[object]([False]))
            qt_type.InvokeMember("Delete", f_inv, None, qt, None)
            
            # 4. Global Formatting (Cambria 9, Thin Borders, Row Height, Column Min Width)
            used_range = worksheet_type.InvokeMember("UsedRange", f_get, None, worksheet, None)
            ur_type = used_range.GetType()
            
            # Set Font: Cambria, Size 9
            ur_font = ur_type.InvokeMember("Font", f_get, None, used_range, None)
            ur_font_type = ur_font.GetType()
            ur_font_type.InvokeMember("Name", f_set, None, ur_font, System.Array[object](["Cambria"]))
            ur_font_type.InvokeMember("Size", f_set, None, ur_font, System.Array[object]([9]))
            
            # Apply Thin Borders (xlContinuous=1, xlThin=2) - Excel.XlLineStyle.xlContinuous, Excel.XlBorderWeight.xlThin
            ur_borders = ur_type.InvokeMember("Borders", f_get, None, used_range, None)
            ur_borders_type = ur_borders.GetType()
            ur_borders_type.InvokeMember("LineStyle", f_set, None, ur_borders, System.Array[object]([1]))
            ur_borders_type.InvokeMember("Weight", f_set, None, ur_borders, System.Array[object]([2]))

            # Set Row Height for all rows
            rows_obj = worksheet_type.InvokeMember("Rows", f_get, None, worksheet, None)
            rows_obj.GetType().InvokeMember("RowHeight", f_set, None, rows_obj, System.Array[object]([20]))

            # 5. Themed Header Formatting (Rows 1-3, limited to column data)
            ur_cols = ur_type.InvokeMember("Columns", f_get, None, used_range, None)
            last_col_idx = ur_cols.GetType().InvokeMember("Count", f_get, None, ur_cols, None)
            
            # Merge Row 1 across the width of the data body and center it
            r1_cell1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([1, 1]))
            r1_cell2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([1, last_col_idx]))
            r1_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[object]([r1_cell1, r1_cell2]))
            r1_range.GetType().InvokeMember("Merge", f_inv, None, r1_range, None)
            r1_range.GetType().InvokeMember("HorizontalAlignment", f_set, None, r1_range, System.Array[object]([-4108])) # xlCenter

            # Set custom header with Project Name and Current Date
            page_setup = worksheet_type.InvokeMember("PageSetup", f_get, None, worksheet, None)
            page_setup_type = page_setup.GetType()
            # Left Header: Project Name
            page_setup_type.InvokeMember("LeftHeader", f_set, None, page_setup, System.Array[object]([doc.Title]))
            # Right Header: Current Date
            current_date = System.DateTime.Now.ToString("yyyy-MM-dd")
            page_setup_type.InvokeMember("RightHeader", f_set, None, page_setup, System.Array[object]([current_date]))
            
            # Automatic Print Adjustment (Fit all columns on one page)
            # Orientation: xlPortrait = 1, xlLandscape = 2. Switch to Landscape if wide (> 7 cols)
            orientation = 2 if last_col_idx > 7 else 1
            page_setup_type.InvokeMember("Orientation", f_set, None, page_setup, System.Array[object]([orientation]))
            page_setup_type.InvokeMember("Zoom", f_set, None, page_setup, System.Array[object]([False]))
            page_setup_type.InvokeMember("FitToPagesWide", f_set, None, page_setup, System.Array[object]([1]))
            page_setup_type.InvokeMember("FitToPagesTall", f_set, None, page_setup, System.Array[object]([False]))

            # 6. Clean Units and Format Columns (Currency & Precision)
            if strip_units:
                # Set format to General first to ensure Excel re-evaluates the data type after stripping text
                ur_type.InvokeMember("NumberFormat", f_set, None, used_range, System.Array[object](["General"]))
                
                # Aggressive list to catch variations like m2, m3, and superscripts
                # Expanded list to ensure m2/m3/sqm/cum are all caught and converted to numbers
                # Added u"Â²" and u"Â³" to fix misidentified encoding characters
                units_to_strip = [" mm", " mm2", " mm3", " m", " kg", " m2", " m^2", " sq m", "sq m", 
                                  u" m\xb2", u" mÂ²", u"Â²",
                                  u" m\xb3", " m3", " m^3", " cu m", "cu m", u" mÂ³", u"Â³"]
                for unit in units_to_strip:
                    # Range.Replace(What, Replacement, LookAt[xlPart=2])
                    replace_args = System.Array[object]([unit, "", 2])
                    ur_type.InvokeMember("Replace", f_inv, None, used_range, replace_args)

                # Iterate through columns to detect Cost/Price and apply precision
                for col_idx in range(1, last_col_idx + 1):
                    # Check Header Cell in Row 3 (Parameter Name)
                    h_cell = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([3, col_idx]))
                    h_val = h_cell.GetType().InvokeMember("Value2", f_get, None, h_cell, None)
                    h_str = str(h_val).lower() if h_val else ""
                    
                    target_col = worksheet_type.InvokeMember("Columns", f_get, None, worksheet, System.Array[object]([col_idx]))
                    tc_type = target_col.GetType()
                    
                    if "cost" in h_str or "price" in h_str:
                        # Format as Currency
                        tc_type.InvokeMember("NumberFormat", f_set, None, target_col, System.Array[object](["$#,##0.00"]))
                    else:
                        # Precision logic: Check first data row (Row 4) to determine if it's a whole number or float
                        d_cell = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([4, col_idx]))
                        d_val = d_cell.GetType().InvokeMember("Value2", f_get, None, d_cell, None)
                        
                        if isinstance(d_val, (int, float)):
                            # If number is an integer, show no decimals
                            if d_val % 1 == 0:
                                tc_type.InvokeMember("NumberFormat", f_set, None, target_col, System.Array[object](["0"]))
                            else:
                                # If number is a float, force two decimal places
                                tc_type.InvokeMember("NumberFormat", f_set, None, target_col, System.Array[object](["0.00"]))
            else:
                # If unit stripping is unchecked, just clean up encoding artifacts like "Â"
                # which often incorrectly appears before "²" or "³" symbols.
                replace_args = System.Array[object]([u"Â", "", 2]) # 2 = xlPart
                ur_type.InvokeMember("Replace", f_inv, None, used_range, replace_args)

            # 7. Smart Header Detection
            # Check Row 2 content. Revit pattern:
            # - Pattern A (Gap): R1=Title, R2=Blank, R3=Headers -> h_depth = 3
            # - Pattern B (No Gap): R1=Title, R2=Headers, R3=Data -> h_depth = 2
            r2_c1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([2, 1]))
            r2_c2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([2, last_col_idx]))
            r2_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[object]([r2_c1, r2_c2]))
            
            r3_c1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([3, 1]))
            r3_c2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([3, last_col_idx]))
            r3_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[object]([r3_c1, r3_c2]))
            
            ws_func = excel_type.InvokeMember("WorksheetFunction", f_get, None, excel_app, None)
            count_r2 = ws_func.GetType().InvokeMember("CountA", f_inv, None, ws_func, System.Array[object]([r2_range]))
            count_r3 = ws_func.GetType().InvokeMember("CountA", f_inv, None, ws_func, System.Array[object]([r3_range]))
            
            # Logic: If Row 2 is empty, the headers must be on Row 3. Otherwise, headers are on Row 2.
            h_depth = 3 if (count_r2 == 0 and count_r3 > 0) else 2

            cell1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([1, 1]))
            cell2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([h_depth, last_col_idx]))
            header_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[object]([cell1, cell2]))
            hr_type = header_range.GetType()
            
            # Background: Electric Teal (C_ACCENT: 32, 200, 170 -> 11192352)
            hr_interior = hr_type.InvokeMember("Interior", f_get, None, header_range, None)
            hr_interior.GetType().InvokeMember("Color", f_set, None, hr_interior, System.Array[object]([11192352]))
            
            # Text Color: Black (0)
            hr_font = hr_type.InvokeMember("Font", f_get, None, header_range, None)
            hr_font_type = hr_font.GetType()
            hr_font_type.InvokeMember("Bold", f_set, None, hr_font, System.Array[object]([True]))
            hr_font_type.InvokeMember("Color", f_set, None, hr_font, System.Array[object]([0]))
            
            # Center the header text
            hr_type.InvokeMember("VerticalAlignment", f_set, None, header_range, System.Array[object]([-4108]))
            hr_type.InvokeMember("HorizontalAlignment", f_set, None, header_range, System.Array[object]([-4108]))

            # 8. Freeze Panes below headers
            # Select the first cell of the body data
            body_start_cell = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([h_depth + 1, 1]))
            body_start_cell.GetType().InvokeMember("Select", f_inv, None, body_start_cell, None)
            active_window = excel_type.InvokeMember("ActiveWindow", f_get, None, excel_app, None)
            active_window.GetType().InvokeMember("FreezePanes", f_set, None, active_window, System.Array[object]([True]))

            # 9. Alternating Row Shading (Zebra Striping)
            if shade_rows:
                last_row = ur_type.InvokeMember("Rows", f_get, None, used_range, None).GetType().InvokeMember("Count", f_get, None, ur_type.InvokeMember("Rows", f_get, None, used_range, None), None)
                if last_row > h_depth:
                    # Define body range starting after headers
                    b_cell1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([h_depth + 1, 1]))
                    b_cell2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[object]([last_row, last_col_idx]))
                    body_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[object]([b_cell1, b_cell2]))
                    
                    # Apply Conditional Formatting: =MOD(ROW(),2)=0
                    fcs = body_range.GetType().InvokeMember("FormatConditions", f_get, None, body_range, None)
                    # xlExpression = 2
                    fc = fcs.GetType().InvokeMember("Add", f_inv, None, fcs, System.Array[object]([2, System.Type.Missing, "=MOD(ROW(),2)=0"]))
                    interior = fc.GetType().InvokeMember("Interior", f_get, None, fc, None)
                    # Light Gray Shade: 15921906
                    interior.GetType().InvokeMember("Color", f_set, None, interior, System.Array[object]([15921906]))

            # Auto-fit columns
            cols = worksheet_type.InvokeMember("Columns", f_get, None, worksheet, None)
            cols.GetType().InvokeMember("AutoFit", f_inv, None, cols, None)
            
            # Apply minimum column width after AutoFit
            for col_idx in range(1, last_col_idx + 1):
                col_range = worksheet_type.InvokeMember("Columns", f_get, None, worksheet, System.Array[object]([col_idx]))
                current_width = col_range.GetType().InvokeMember("ColumnWidth", f_get, None, col_range, None)
                # Excel's ColumnWidth is in "units of 256th of the width of the zero character"
                # A value of 8 is a reasonable minimum for readability.
                if current_width < 8:
                    col_range.GetType().InvokeMember("ColumnWidth", f_set, None, col_range, System.Array[object]([8]))
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        # Save Final Workbook
        workbook_type.InvokeMember("SaveAs", f_inv, None, workbook, System.Array[object]([output_path]))
        
        # Save as PDF if requested
        if save_pdf:
            pdf_path = output_path.replace(".xlsx", ".pdf")
            # xlTypePDF = 0
            # ExportAsFixedFormat(Type, Filename)
            workbook_type.InvokeMember("ExportAsFixedFormat", f_inv, None, workbook, System.Array[object]([0, pdf_path]))

        return True, "Successfully exported {} schedules to {}".format(len(schedules), output_path)
        
    except Exception as e:
        return False, str(e)
    finally:
        # Close the workbook and quit the Excel application using reflection
        if 'workbook_type' in locals():
            workbook_type.InvokeMember("Close", f_inv, None, workbook, System.Array[object]([False]))
        
        excel_type.InvokeMember("Quit", f_inv, None, excel_app, None)
        # Ensure COM objects are released
        System.Runtime.InteropServices.Marshal.ReleaseComObject(excel_app)

# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION
# ═══════════════════════════════════════════════════════════════════════════
all_schedules = FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements()

# Filter out templates and schedules with 3 or fewer data rows
exportable_schedules = []
for s in all_schedules:
    if s.IsTemplate:
        continue
    try:
        if s.GetTableData().GetSectionData(SectionType.Body).NumberOfRows > 3:
            exportable_schedules.append(s)
    except:
        continue

if not exportable_schedules:
    forms.alert("No schedules found in the current document.", exitscript=True)

dialog = ScheduleExportDialog(exportable_schedules)
dialog.ShowDialog()

if dialog.result:
    selected_schedules, save_path, strip_units, include_hidden, shade_rows, save_pdf = dialog.result
    
    with forms.ProgressBar(title="Exporting Schedules...", cancellable=False) as pb:
        success, message = export_schedules_to_excel(selected_schedules, save_path, strip_units, include_hidden, shade_rows, save_pdf)
        
    if success:
        output = script.get_output()
        output.print_md("### ✓ Export Complete")
        output.print_md("- **File:** " + save_path)
        output.print_md("- **Schedules:** " + str(len(selected_schedules)))
        
        # Auto-open the file
        try:
            os.startfile(save_path)
        except Exception as e:
            print("Could not auto-open file: {}".format(e))
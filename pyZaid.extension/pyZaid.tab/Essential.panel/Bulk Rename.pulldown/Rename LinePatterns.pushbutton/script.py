#! python
# -*- coding: utf-8 -*-

import re
import clr

# Load WPF/XAML Assemblies and the core System engine
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
import System

from System.Windows import Window, WindowStartupLocation, Thickness, HorizontalAlignment, GridLength
from System.Windows.Controls import Grid, Label, TextBox, Button, ColumnDefinition, RowDefinition
from pyrevit import revit, DB, forms, script

doc = revit.doc
# Initialize pyRevit's custom output wrapper window for clean logging
output = script.get_output()

class FindReplaceDialog(Window):
    """Custom WPF Window combining Find and Replace inputs on a single screen."""
    def __init__(self):
        self.Title = "Find & Replace Line Patterns"
        self.Width = 350
        self.Height = 180
        self.WindowStartupLocation = WindowStartupLocation.CenterScreen
        self.Topmost = True
        
        # Setup Grid Layout
        grid = Grid()
        grid.Margin = Thickness(15)
        
        # Define 2 Columns
        col1 = ColumnDefinition()
        col1.Width = GridLength.Auto
        col2 = ColumnDefinition()
        grid.ColumnDefinitions.Add(col1)
        grid.ColumnDefinitions.Add(col2)
        
        # Define 3 Rows (Find, Replace, Buttons)
        for i in range(3):
            row = RowDefinition()
            row.Height = GridLength.Auto
            grid.RowDefinitions.Add(row)
            
        # Row 0: Find Input
        lbl_find = Label(Content="Find Text:")
        lbl_find.Margin = Thickness(0, 0, 10, 10)
        Grid.SetRow(lbl_find, 0)
        Grid.SetColumn(lbl_find, 0)
        
        self.txt_find = TextBox()
        self.txt_find.Margin = Thickness(0, 0, 0, 10)
        Grid.SetRow(self.txt_find, 0)
        Grid.SetColumn(self.txt_find, 1)
        
        # Row 1: Replace Input
        lbl_replace = Label(Content="Replace With:")
        lbl_replace.Margin = Thickness(0, 0, 10, 10)
        Grid.SetRow(lbl_replace, 1)
        Grid.SetColumn(lbl_replace, 0)
        
        self.txt_replace = TextBox()
        self.txt_replace.Margin = Thickness(0, 0, 0, 10)
        Grid.SetRow(self.txt_replace, 1)
        Grid.SetColumn(self.txt_replace, 1)
        
        # Row 2: Action Buttons Layout
        btn_grid = Grid()
        btn_grid.Margin = Thickness(0, 10, 0, 0)
        Grid.SetRow(btn_grid, 2)
        Grid.SetColumnSpan(btn_grid, 2)
        
        btn_col1 = ColumnDefinition()
        btn_col2 = ColumnDefinition()
        btn_grid.ColumnDefinitions.Add(btn_col1)
        btn_grid.ColumnDefinitions.Add(btn_col2)
        
        btn_ok = Button(Content="Rename", IsDefault=True)
        btn_ok.Width = 80
        btn_ok.HorizontalAlignment = HorizontalAlignment.Right
        btn_ok.Margin = Thickness(0, 0, 5, 0)
        btn_ok.Click += self.on_ok
        Grid.SetColumn(btn_ok, 0)
        
        btn_cancel = Button(Content="Cancel", IsCancel=True)
        btn_cancel.Width = 80
        btn_cancel.HorizontalAlignment = HorizontalAlignment.Left
        btn_cancel.Margin = Thickness(5, 0, 0, 0)
        btn_cancel.Click += self.on_cancel
        Grid.SetColumn(btn_cancel, 1)
        
        btn_grid.Children.Add(btn_ok)
        btn_grid.Children.Add(btn_cancel)
        
        grid.Children.Add(lbl_find)
        grid.Children.Add(self.txt_find)
        grid.Children.Add(lbl_replace)
        grid.Children.Add(self.txt_replace)
        grid.Children.Add(btn_grid)
        
        self.Content = grid
        self.cancelled = True
        
    def on_ok(self, sender, e):
        self.cancelled = False
        self.Close()
        
    def on_cancel(self, sender, e):
        self.Close()

def bulk_rename_linepatterns_combined_ui():
    dialog = FindReplaceDialog()
    dialog.ShowDialog()
    
    if dialog.cancelled:
        return
        
    find_text = dialog.txt_find.Text
    replace_text = dialog.txt_replace.Text

    if not find_text:
        forms.alert("The 'Find' search term cannot be empty.", exitscript=True)

    match_case = forms.alert(
        "Should the search match case exactly?",
        yes=True, 
        no=True
    )

    # Fetch all LinePatternElements in the current document
    try:
        line_patterns = DB.FilteredElementCollector(doc)\
                          .OfClass(DB.LinePatternElement)\
                          .ToElements()
    except Exception as e:
        forms.alert("Could not access model Line Patterns: {}".format(e), exitscript=True)
        return

    renamed_count = 0
    
    with revit.Transaction("Bulk Rename Line Patterns (Console Output)"):
        for pattern_element in line_patterns:
            if pattern_element is None:
                continue
                
            current_name = pattern_element.Name
            if not current_name:
                continue
                
            is_match = False
            new_name = current_name
            
            if match_case:
                if find_text in current_name:
                    is_match = True
                    new_name = current_name.replace(find_text, replace_text)
            else:
                if find_text.lower() in current_name.lower():
                    is_match = True
                    pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                    new_name = pattern.sub(replace_text, current_name)

            if is_match:
                try:
                    pattern_element.Name = new_name
                    renamed_count += 1
                    # Log successful rename out to pyRevit CLI window
                    print("SUCCESS: Renamed Line Pattern '{}' -> '{}'".format(current_name, new_name))
                except Exception as err:
                    print("SKIPPED: System-locked pattern '{}' could not be modified. Reason: {}".format(current_name, err))

    # Print summary block directly to the log window
    print("\n" + "="*50)
    print("LINE PATTERN PROCESSING SUMMARY")
    print("="*50)
    print("Total line patterns successfully updated: {}".format(renamed_count))
    print("="*50 + "\n")

if __name__ == "__main__":
    bulk_rename_linepatterns_combined_ui()

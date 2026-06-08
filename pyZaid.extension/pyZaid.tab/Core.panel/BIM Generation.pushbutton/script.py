#! python3
# -*- coding: utf-8 -*-
__title__ = 'BIM Generation Pro'
__author__ = 'AnonGee'

import sys
import os

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xml')

from System.Windows.Markup import XamlReader
from System.IO import FileStream, FileMode, FileAccess
from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage
import System.Windows.Forms

# Expose local modules within this package directory
local_directory = os.path.dirname(os.path.realpath(__file__))
if local_directory not in sys.path:
    sys.path.append(local_directory)

import core
import parser_service

# __revit__ is natively injected into the runtime environment by pyRevit's engine
doc = __revit__.ActiveUIDocument.Document

class InpToBimDialog(object):
    def __init__(self):
        xaml_path = os.path.join(local_directory, 'ui.xaml')
        
        # Load ui.xaml (Contains all embedded resources so it compiles self-contained instantly)
        ui_stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        try:
            self.window = XamlReader.Load(ui_stream)
        except Exception as e:
            MessageBox.Show(f"Failed to load UI Window:\n\n{str(e)}", "UI Error", MessageBoxButton.OK, MessageBoxImage.Error)
            ui_stream.Close()
            return
        finally:
            ui_stream.Close()
            
        # Map the elements dynamically by their x:Name
        self.ComboStructuralColumns = self.window.FindName("ComboStructuralColumns")
        self.ComboStructuralBeams = self.window.FindName("ComboStructuralBeams")
        self.ComboFloorTypes = self.window.FindName("ComboFloorTypes")
        
        self.InputFilePathBox = self.window.FindName("InputFilePathBox")
        self.LevelPrefixInput = self.window.FindName("LevelPrefixInput")
        self.LevelBaseInput = self.window.FindName("LevelBaseInput")
        self.LevelSuffixInput = self.window.FindName("LevelSuffixInput")
        self.LevelSeparatorInput = self.window.FindName("LevelSeparatorInput")
        self.TextLevelPreview = self.window.FindName("TextLevelPreview")
        
        # Bind Events dynamically
        self.window.FindName("ButtonCancel").Click += self.CancelButton_Click
        self.window.FindName("ButtonGenerate").Click += self.GenerateModelButton_Click
        self.window.FindName("ButtonBrowsePath").Click += self.BrowseButton_Click
        
        self.LevelPrefixInput.TextChanged += self.UpdateLevelPreview
        self.LevelBaseInput.TextChanged += self.UpdateLevelPreview
        self.LevelSuffixInput.TextChanged += self.UpdateLevelPreview
        self.LevelSeparatorInput.TextChanged += self.UpdateLevelPreview
        
        # Load Domain data from core
        self.column_families = core.get_structural_columns(doc)
        self.beam_families = core.get_structural_framings(doc)
        self.floor_types = core.get_floor_types(doc)
        
        self._initialize_combo_selections()

    def _initialize_combo_selections(self):
        if not self.column_families or not self.beam_families or not self.floor_types:
            MessageBox.Show(
                "Warning: Critical missing Family components. Generation tool cannot safely execute.", 
                "System Setup Required", 
                MessageBoxButton.OK, 
                MessageBoxImage.Warning
            )
            self.window.Close()
            return
            
        for name in self.column_families.keys():
            self.ComboStructuralColumns.Items.Add(name)
            
        for name in self.beam_families.keys():
            self.ComboStructuralBeams.Items.Add(name)
            
        for name in self.floor_types.keys():
            self.ComboFloorTypes.Items.Add(name)

        if self.ComboStructuralColumns.Items.Count > 0:
            self.ComboStructuralColumns.SelectedIndex = 0
            
        if self.ComboStructuralBeams.Items.Count > 0:
            self.ComboStructuralBeams.SelectedIndex = 0
            
        if self.ComboFloorTypes.Items.Count > 0:
            self.ComboFloorTypes.SelectedIndex = 0

    def ShowDialog(self):
        self.window.ShowDialog()

    def BrowseButton_Click(self, sender, args):
        dialog = System.Windows.Forms.OpenFileDialog()
        dialog.Title = "Select FRAME File"
        dialog.Filter = "INP/TXT files (*.inp;*.txt)|*.inp;*.txt|All files (*.*)|*.*"
        
        if dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK:
            self.InputFilePathBox.Text = dialog.FileName

    def UpdateLevelPreview(self, sender, args):
        try:
            prefix = self.LevelPrefixInput.Text.strip()
            floor_base_name = self.LevelBaseInput.Text.strip()
            suffix = self.LevelSuffixInput.Text.strip()
            
            separator = self.LevelSeparatorInput.Text if self.LevelSeparatorInput else " "
            
            ordinal_name_current = parser_service.get_ordinal_string(parser_service.get_numeric_portion(floor_base_name))
            ordinal_name_next = parser_service.get_ordinal_string(parser_service.get_numeric_portion(floor_base_name) + 1)
            
            current_prefix = str(int(prefix)).zfill(len(prefix)) if prefix.isdigit() else prefix
            next_prefix = str(int(prefix) + 1).zfill(len(prefix)) if prefix.isdigit() else prefix
            
            demo_level_first = f"{current_prefix}{separator}{ordinal_name_current}{separator}{suffix}".replace("  ", " ").strip()
            demo_level_next = f"{next_prefix}{separator}{ordinal_name_next}{separator}{suffix}".replace("  ", " ").strip()

            self.TextLevelPreview.Text = f"Preview: {demo_level_first} → {demo_level_next} → ..."
            
        except Exception:
            if getattr(self, "TextLevelPreview", None):
                self.TextLevelPreview.Text = "Awaiting complete preview schema configuration."

    def CancelButton_Click(self, sender, args):
        self.window.Close()

    def GenerateModelButton_Click(self, sender, args):
        target_file = self.InputFilePathBox.Text.strip()
        
        if not os.path.exists(target_file):
            MessageBox.Show(
                "The input structural schematic path could not be mapped locally. Validate file path availability.", 
                "Generation Incomplete", 
                MessageBoxButton.OK, 
                MessageBoxImage.Warning
            )
            return

        column_target = list(self.column_families.values())[self.ComboStructuralColumns.SelectedIndex]
        beam_target = list(self.beam_families.values())[self.ComboStructuralBeams.SelectedIndex]
        floor_target = list(self.floor_types.values())[self.ComboFloorTypes.SelectedIndex]
        
        try:
            structural_model_manifest = parser_service.extract_schematics(target_file)
            core.execute_generation_protocol(
                doc=doc,
                parsed_model=structural_model_manifest,
                col_symbol=column_target,
                beam_symbol=beam_target,
                floor_type=floor_target,
                level_prefix=self.LevelPrefixInput.Text.strip(),
                level_start_name=self.LevelBaseInput.Text.strip(),
                level_suffix=self.LevelSuffixInput.Text.strip(),
                separator=self.LevelSeparatorInput.Text
            )
            MessageBox.Show(
                "Model structures securely generated strictly matching schematics file operations.", 
                "Generation Complete", 
                MessageBoxButton.OK, 
                MessageBoxImage.Information
            )
            self.window.Close()
            
        except Exception as deployment_issue:
            MessageBox.Show(
                f"Failed Model Data processing: {str(deployment_issue)}", 
                "Generation Context Blocked", 
                MessageBoxButton.OK, 
                MessageBoxImage.Error
            )

if __name__ == '__main__':
    dialog_frame = InpToBimDialog()
    if hasattr(dialog_frame, 'window'):
        dialog_frame.ShowDialog()
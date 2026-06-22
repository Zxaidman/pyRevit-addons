#! python3
# -*- coding: utf-8 -*-
"""
AnonGee Create Button — scaffold a new pyRevit pushbutton.

Renders a brand-themed WPF dialog from ui.xaml (kept in sync with
AnonGee_BIM_Tools_Brand_Guidelines.md), collects the new tool's tab / panel /
group / files / metadata, writes the folder + script + icon + bundle.yaml into
the current extension, then asks pyRevit to reload.
"""

import os
import shutil
import clr

# Load native Windows / Revit libraries safely
clr.AddReference("System")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")
clr.AddReference("RevitAPIUI")

from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import BitmapImage
from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage
from System.IO import FileStream, FileMode, FileAccess
from System import Uri, UriKind
from Microsoft.Win32 import OpenFileDialog

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Dynamically find the EXACT extension path this tool lives in
ext_dir = LOCAL_DIR
while ext_dir and not ext_dir.endswith('.extension'):
    parent = os.path.dirname(ext_dir)
    if parent == ext_dir:
        break
    ext_dir = parent

if not ext_dir.endswith('.extension'):
    MessageBox.Show(
        "Could not detect root .extension folder. Place this tool inside an extension.",
        "Create Button", MessageBoxButton.OK, MessageBoxImage.Error)
    raise Exception("Extension path not found.")


class ButtonGeneratorApp:
    def __init__(self):
        self.ext_dir = ext_dir
        self.success = False

        # 2. Load the brand-themed UI from ui.xaml
        xaml_path = os.path.join(LOCAL_DIR, "ui.xaml")
        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        try:
            self.window = XamlReader.Load(stream)
        finally:
            stream.Close()

        icon_path = os.path.join(LOCAL_DIR, "icon.png")
        if os.path.exists(icon_path):
            self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

        # Bind UI elements
        self.ExtNameBlock = self.window.FindName("ExtNameBlock")
        self.TabCombo = self.window.FindName("TabCombo")
        self.PanelCombo = self.window.FindName("PanelCombo")
        self.ChkGroup = self.window.FindName("ChkGroup")
        self.GroupTypeCombo = self.window.FindName("GroupTypeCombo")
        self.GroupNameText = self.window.FindName("GroupNameText")
        self.BtnNameText = self.window.FindName("BtnNameText")
        self.BundleTitleText = self.window.FindName("BundleTitleText")
        self.AuthorText = self.window.FindName("AuthorText")
        self.ScriptPath = self.window.FindName("ScriptPath")
        self.IconPath = self.window.FindName("IconPath")
        self.Description = self.window.FindName("Description")

        # Wire up event handlers
        self.window.FindName("BrowseScriptBtn").Click += self.browse_script
        self.window.FindName("BrowseIconBtn").Click += self.browse_icon
        self.window.FindName("GenerateBtn").Click += self.create_button
        self.window.FindName("CancelBtn").Click += lambda s, e: self.window.Close()

        self.TabCombo.DropDownOpened += self.tab_dropdown_opened
        self.TabCombo.SelectionChanged += self.tab_changed
        self.ChkGroup.Click += self.toggle_group

        # Initialize scope strictly to the current extension
        self.ExtNameBlock.Text = os.path.basename(self.ext_dir).replace('.extension', '')
        self.populate_tabs()
        self.toggle_group(None, None)

        self.window.ShowDialog()

    def populate_tabs(self, sender=None, args=None):
        self.TabCombo.Items.Clear()
        if not os.path.exists(self.ext_dir):
            return

        tabs = [f.replace('.tab', '') for f in os.listdir(self.ext_dir) if f.endswith('.tab')]
        for t in tabs:
            self.TabCombo.Items.Add(t)

        if self.TabCombo.Items.Count > 0:
            self.TabCombo.SelectedIndex = 0

    def tab_dropdown_opened(self, sender, args):
        self.populate_tabs()

    def tab_changed(self, sender, args):
        self.PanelCombo.Items.Clear()

        if self.TabCombo.SelectedItem:
            selected_tab = str(self.TabCombo.SelectedItem)
        else:
            selected_tab = str(self.TabCombo.Text)

        if not selected_tab:
            return

        tab_path = os.path.join(self.ext_dir, selected_tab + '.tab')
        if os.path.exists(tab_path):
            panels = [f.replace('.panel', '') for f in os.listdir(tab_path) if f.endswith('.panel')]
            for p in panels:
                self.PanelCombo.Items.Add(p)

            if self.PanelCombo.Items.Count > 0:
                self.PanelCombo.SelectedIndex = 0

    def toggle_group(self, sender, args):
        is_checked = self.ChkGroup.IsChecked
        self.GroupTypeCombo.IsEnabled = is_checked
        self.GroupNameText.IsEnabled = is_checked

    def browse_script(self, sender, args):
        dialog = OpenFileDialog()
        dialog.Filter = "Scripts (*.py;*.cs;*.dyn)|*.py;*.cs;*.dyn"
        if dialog.ShowDialog():
            self.ScriptPath.Text = dialog.FileName

    def browse_icon(self, sender, args):
        dialog = OpenFileDialog()
        dialog.Filter = "Image Files (*.png)|*.png"
        if dialog.ShowDialog():
            self.IconPath.Text = dialog.FileName

    def create_button(self, sender, args):
        tab_name = self.TabCombo.Text.strip()
        panel_name = self.PanelCombo.Text.strip()
        btn_name = self.BtnNameText.Text.strip()
        bundle_title = self.BundleTitleText.Text.strip()
        author = self.AuthorText.Text.strip()
        script_path = self.ScriptPath.Text.strip()
        icon_path = self.IconPath.Text.strip()
        description = self.Description.Text.strip()

        if not all([tab_name, panel_name, btn_name, script_path]):
            MessageBox.Show("Tab, Panel, Folder Name, and Script File are required.",
                            "Missing Data", MessageBoxButton.OK, MessageBoxImage.Warning)
            return

        target_dir = os.path.join(self.ext_dir, tab_name + ".tab", panel_name + ".panel")

        if self.ChkGroup.IsChecked:
            grp_name = self.GroupNameText.Text.strip()
            if not grp_name:
                MessageBox.Show("Please provide a Group Name.",
                                "Missing Data", MessageBoxButton.OK, MessageBoxImage.Warning)
                return

            # Safely extract ComboBoxItem Content
            grp_type = ".pulldown"
            if self.GroupTypeCombo.SelectedItem:
                grp_type = str(self.GroupTypeCombo.SelectedItem.Content)

            target_dir = os.path.join(target_dir, grp_name + grp_type)

        target_dir = os.path.join(target_dir, btn_name + ".pushbutton")

        try:
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            # Copy files
            _, file_ext = os.path.splitext(script_path)
            dest_script = os.path.join(target_dir, "script" + file_ext.lower())
            shutil.copy(script_path, dest_script)

            if icon_path and os.path.exists(icon_path):
                shutil.copy(icon_path, os.path.join(target_dir, "icon.png"))

            # Create YAML
            yaml_path = os.path.join(target_dir, "bundle.yaml")
            if not bundle_title:
                bundle_title = btn_name
            if not author:
                author = "pyZaid Automation"

            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write(f"title: {bundle_title}\n")
                if description:
                    clean_desc = description.replace('\r\n', '\n').replace('\r', '\n')
                    indented_desc = '\n'.join([f"  {line}" for line in clean_desc.split('\n')])
                    f.write(f"tooltip: |\n{indented_desc}\n")
                f.write(f"author: {author}\n")

            self.success = True
            self.window.Close()

        except Exception as e:
            MessageBox.Show(f"An error occurred:\n{str(e)}",
                            "Error", MessageBoxButton.OK, MessageBoxImage.Error)


# -------------------------------------------------------------
# AUTO-RELOAD
# -------------------------------------------------------------
if __name__ == '__main__':
    app = ButtonGeneratorApp()

    if app.success:
        try:
            # Reload pyRevit through its own session manager (same call the
            # ribbon's "Reload" button uses) so the new button appears.
            from pyrevit.loader import sessionmgr
            sessionmgr.reload_pyrevit()
        except Exception:
            MessageBox.Show("Button generated! Please click 'Reload' on the pyRevit ribbon.",
                            "Success", MessageBoxButton.OK, MessageBoxImage.Information)

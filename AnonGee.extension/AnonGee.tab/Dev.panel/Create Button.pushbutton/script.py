#! python3
# -*- coding: utf-8 -*-

import os
import shutil
import clr

# Load Native Windows libraries safely
clr.AddReference("System")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("RevitAPIUI")

from System.Windows.Markup import XamlReader
from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage
from Microsoft.Win32 import OpenFileDialog
from System.IO import StringReader
from System.Xml import XmlReader

from pyrevit import HOST_APP

# 1. Dynamically find your EXACT extension path
try:
    script_path = os.path.abspath(__file__)
except NameError:
    script_path = __commandpath__

ext_dir = os.path.dirname(script_path)
while ext_dir and not ext_dir.endswith('.extension'):
    parent = os.path.dirname(ext_dir)
    if parent == ext_dir:
        break
    ext_dir = parent

if not ext_dir.endswith('.extension'):
    MessageBox.Show("Could not detect root .extension folder. Place this tool inside an extension.", "Error", MessageBoxButton.OK, MessageBoxImage.Error)
    raise Exception("Extension path not found.")


class ButtonGeneratorApp:
    def __init__(self):
        self.ext_dir = ext_dir
        self.success = False

        # 2. YOUR UPDATED EMBEDDED XAML
        xaml_str = """
        <Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                Title="pyRevit Button Generator" Width="520" SizeToContent="Height"
                WindowStartupLocation="CenterScreen" Background="#F9F9F9" FontSize="11" FontFamily="Cambria">
            <Grid Margin="15">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="100"/>
                    <ColumnDefinition Width="2*"/>
                    <ColumnDefinition Width="*"/>
                </Grid.ColumnDefinitions>
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                    <RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>

                <TextBlock Text="Target Extension:" Grid.Row="0" Grid.Column="0" Margin="0,4,0,4" VerticalAlignment="Center" FontWeight="SemiBold"/>
                <TextBlock Name="ExtNameBlock" Grid.Row="0" Grid.Column="1" Grid.ColumnSpan="2" Margin="5,4,0,4" VerticalAlignment="Center" FontWeight="Bold" Foreground="#007ACC"/>

                <TextBlock Text="Tab Name:" Grid.Row="1" Grid.Column="0" Margin="0,4,0,4" VerticalAlignment="Center" FontWeight="SemiBold"/>
                <StackPanel Grid.Row="1" Grid.Column="1" Grid.ColumnSpan="2" Orientation="Horizontal" Margin="5,4,0,4">
                    <ComboBox Name="TabCombo" Width="220" IsEditable="True" Padding="3"/>
                    <TextBlock Text=".tab" VerticalAlignment="Center" Margin="5,0,0,0" Foreground="Gray"/>
                </StackPanel>

                <TextBlock Text="Panel Name:" Grid.Row="2" Grid.Column="0" Margin="0,4,0,4" VerticalAlignment="Center" FontWeight="SemiBold"/>
                <StackPanel Grid.Row="2" Grid.Column="1" Grid.ColumnSpan="2" Orientation="Horizontal" Margin="5,4,0,4">
                    <ComboBox Name="PanelCombo" Width="220" IsEditable="True" Padding="3"/>
                    <TextBlock Text=".panel" VerticalAlignment="Center" Margin="5,0,0,0" Foreground="Gray"/>
                </StackPanel>

                <CheckBox Name="ChkGroup" Content="Create inside a Group Folder" Grid.Row="3" Grid.Column="1" Grid.ColumnSpan="2" Margin="5,6,0,6" FontWeight="SemiBold"/>

                <TextBlock Text="Group Name:" Grid.Row="4" Grid.Column="0" Margin="0,4,0,4" VerticalAlignment="Center"/>
                <StackPanel Grid.Row="4" Grid.Column="1" Grid.ColumnSpan="2" Orientation="Horizontal" Margin="5,4,0,6">
                    <TextBox Name="GroupNameText" Width="220" Padding="3" IsEnabled="False"/>
                    <ComboBox Name="GroupTypeCombo" Grid.Row="4" Grid.Column="1" Margin="5,4,0,4" IsEnabled="False" Padding="3">
                        <ComboBoxItem Content=".pulldown" IsSelected="True"/>
                        <ComboBoxItem Content=".splitbutton"/>
                        <ComboBoxItem Content=".stack"/>
                    </ComboBox>
                </StackPanel>
                
                <TextBlock Text="Folder Name:" Grid.Row="5" Grid.Column="0" Margin="0,8,0,6" VerticalAlignment="Center" FontWeight="SemiBold"/>
                <StackPanel Grid.Row="5" Grid.Column="1" Grid.ColumnSpan="2" Orientation="Horizontal" Margin="5,8,0,6">
                    <TextBox Name="BtnNameText" Width="220" Padding="3" VerticalAlignment="Center"/>
                    <TextBlock Text=".pushbutton" VerticalAlignment="Center" Margin="5,0,0,0" Foreground="Gray"/>
                </StackPanel>

                <TextBlock Text="Script File:" Grid.Row="6" Grid.Column="0" Margin="0,6,0,6" VerticalAlignment="Center" FontWeight="SemiBold"/>
                <TextBox Name="ScriptPath" Grid.Row="6" Grid.Column="1" Margin="5,6,5,6" VerticalAlignment="Center" Padding="3" IsReadOnly="True"/>
                <Button Name="BrowseScriptBtn" Content="Browse" Grid.Row="6" Grid.Column="2" Margin="0,6,0,6" Padding="3"/>

                <TextBlock Text="Icon (.png):" Grid.Row="7" Grid.Column="0" Margin="0,4,0,4" VerticalAlignment="Center" FontWeight="SemiBold"/>
                <TextBox Name="IconPath" Grid.Row="7" Grid.Column="1" Margin="5,4,5,4" VerticalAlignment="Center" Padding="3" IsReadOnly="True"/>
                <Button Name="BrowseIconBtn" Content="Browse" Grid.Row="7" Grid.Column="2" Margin="0,4,0,4" Padding="3"/>

                <TextBlock Text="Bundle Title:" Grid.Row="8" Grid.Column="0" Margin="0,4,0,4" VerticalAlignment="Center" FontWeight="SemiBold"/>
                <TextBox Name="BundleTitleText" Grid.Row="8" Grid.Column="1" Grid.ColumnSpan="2" Margin="5,4,0,4" Padding="3"/>

                <TextBlock Text="Author:" Grid.Row="9" Grid.Column="0" Margin="0,4,0,4" VerticalAlignment="Center" FontWeight="SemiBold"/>
                <TextBox Name="AuthorText" Grid.Row="9" Grid.Column="1" Grid.ColumnSpan="2" Margin="5,4,0,4" Padding="3" Text="pyZaid Automation"/>

                <TextBlock Text="Description:" Grid.Row="10" Grid.Column="0" Margin="0,6,0,6" FontWeight="SemiBold"/>
                <TextBox Name="Description" Grid.Row="10" Grid.Column="1" Grid.ColumnSpan="2" Margin="5,6,0,6" TextWrapping="Wrap" AcceptsReturn="True" VerticalScrollBarVisibility="Auto" Height="48" Padding="3"/>

                <StackPanel Grid.Row="11" Grid.Column="1" Grid.ColumnSpan="2" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,10,0,0">
                    <Button Name="GenerateBtn" Content="Generate &amp; Reload" Width="140" Padding="6" Background="#007ACC" Foreground="White" FontWeight="Bold" BorderThickness="0"/>
                </StackPanel>
            </Grid>
        </Window>
        """

        # Safely parse XAML
        string_reader = StringReader(xaml_str)
        xml_reader = XmlReader.Create(string_reader)
        self.window = XamlReader.Load(xml_reader)
        xml_reader.Close()
        string_reader.Close()

        # Bind UI Elements
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

        # Wire up Event Handlers
        self.window.FindName("BrowseScriptBtn").Click += self.browse_script
        self.window.FindName("BrowseIconBtn").Click += self.browse_icon
        self.window.FindName("GenerateBtn").Click += self.create_button
        
        self.TabCombo.DropDownOpened += self.tab_dropdown_opened
        self.TabCombo.SelectionChanged += self.tab_changed
        self.ChkGroup.Click += self.toggle_group

        # Initialize Scope strictly to the current extension
        self.ExtNameBlock.Text = os.path.basename(self.ext_dir).replace('.extension', '')
        self.populate_tabs()
        self.toggle_group(None, None)

        self.window.ShowDialog()

    def populate_tabs(self, sender=None, args=None):
        self.TabCombo.Items.Clear()
        if not os.path.exists(self.ext_dir): return
        
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
            
        if not selected_tab: return
        
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
            MessageBox.Show("Tab, Panel, Folder Name, and Script File are required.", "Missing Data", MessageBoxButton.OK, MessageBoxImage.Warning)
            return

        target_dir = os.path.join(self.ext_dir, tab_name + ".tab", panel_name + ".panel")

        if self.ChkGroup.IsChecked:
            grp_name = self.GroupNameText.Text.strip()
            if not grp_name:
                MessageBox.Show("Please provide a Group Name.", "Missing Data", MessageBoxButton.OK, MessageBoxImage.Warning)
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
            MessageBox.Show(f"An error occurred:\n{str(e)}", "Error", MessageBoxButton.OK, MessageBoxImage.Error)

# -------------------------------------------------------------
# AUTO-RELOAD
# -------------------------------------------------------------
if __name__ == '__main__':
    app = ButtonGeneratorApp()
    
    if app.success:
        reload_cmd = None
        for cmd_id in HOST_APP.uiapp.GetRevitCommandIds():
            if "pyrevit" in cmd_id.Name.ToLower() and "reload" in cmd_id.Name.ToLower():
                reload_cmd = cmd_id
                break
        
        if reload_cmd:
            HOST_APP.uiapp.PostCommand(reload_cmd)
        else:
            MessageBox.Show("Button generated! Please click 'Reload' on the pyRevit ribbon.", "Success")
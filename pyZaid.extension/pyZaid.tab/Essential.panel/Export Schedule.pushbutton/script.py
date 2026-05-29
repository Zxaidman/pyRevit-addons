#! python3
# -*- coding: utf-8 -*-
# pyRevit script - Export Schedules (CPython 3)

__title__ = 'Export Schedules'
__author__ = 'ZAID'

import os
import clr
import tempfile

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import (
    FilteredElementCollector, ViewSchedule, ViewScheduleExportOptions,
    ExportTextQualifier, ExportColumnHeaders, Transaction, SectionType
)

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xaml')

import System
from System.Windows.Markup import XamlReader
from System.IO import MemoryStream
from System.Text import Encoding
from System.Windows.Controls import ListBoxItem, CheckBox
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System import Action

# Initialize Revit document
doc = __revit__.ActiveUIDocument.Document

# ----------------------------------------------------------------------
# XAML definition (OneFilterParameter light theme style)
# ----------------------------------------------------------------------
XAML = r'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Export Schedules"
        Height="650" Width="480"
        MinHeight="550" MinWidth="400"
        WindowStartupLocation="CenterScreen"
        ResizeMode="CanResize"
        Background="#F5F5F5"
        FontFamily="Segoe UI"
        FontSize="12"
        UseLayoutRounding="True">

    <Window.Resources>
        <Color x:Key="AccentColor">#3498DB</Color>
        <Color x:Key="SuccessColor">#27AE60</Color>
        <Color x:Key="DangerColor">#E74C3C</Color>
        <Color x:Key="LightBgColor">#F5F5F5</Color>
        <Color x:Key="DarkTextColor">#2C3E50</Color>
        <Color x:Key="GrayTextColor">#7F8C8D</Color>
        <Color x:Key="WhiteColor">#FFFFFF</Color>
        <Color x:Key="BorderColor">#BDC3C7</Color>
        <Color x:Key="DividerColor">#D5D8DC</Color>

        <SolidColorBrush x:Key="AccentBrush" Color="{StaticResource AccentColor}" />
        <SolidColorBrush x:Key="SuccessBrush" Color="{StaticResource SuccessColor}" />
        <SolidColorBrush x:Key="DangerBrush" Color="{StaticResource DangerColor}" />
        <SolidColorBrush x:Key="DarkTextBrush" Color="{StaticResource DarkTextColor}" />
        <SolidColorBrush x:Key="GrayTextBrush" Color="{StaticResource GrayTextColor}" />
        <SolidColorBrush x:Key="WhiteBrush" Color="{StaticResource WhiteColor}" />
        <SolidColorBrush x:Key="LightBgBrush" Color="{StaticResource LightBgColor}" />
        <SolidColorBrush x:Key="BorderBrush" Color="{StaticResource BorderColor}" />
        <SolidColorBrush x:Key="DividerBrush" Color="{StaticResource DividerColor}" />

        <Style x:Key="SectionLabel" TargetType="Label">
            <Setter Property="FontSize" Value="13" />
            <Setter Property="FontWeight" Value="SemiBold" />
            <Setter Property="Foreground" Value="{StaticResource DarkTextBrush}" />
            <Setter Property="BorderBrush" Value="{StaticResource AccentBrush}" />
            <Setter Property="BorderThickness" Value="0,0,0,2" />
            <Setter Property="Padding" Value="0,0,0,4" />
            <Setter Property="Margin" Value="0,10,0,10" />
        </Style>

        <Style x:Key="ControlBox" TargetType="TextBox">
            <Setter Property="FontSize" Value="12" />
            <Setter Property="Padding" Value="6,4" />
            <Setter Property="Margin" Value="0" />
            <Setter Property="BorderBrush" Value="{StaticResource BorderBrush}" />
            <Setter Property="BorderThickness" Value="1" />
            <Setter Property="Background" Value="{StaticResource WhiteBrush}" />
            <Setter Property="Foreground" Value="{StaticResource DarkTextBrush}" />
            <Setter Property="VerticalContentAlignment" Value="Center" />
            <Style.Triggers>
                <Trigger Property="IsFocused" Value="True">
                    <Setter Property="BorderBrush" Value="{StaticResource AccentBrush}" />
                    <Setter Property="BorderThickness" Value="1.5" />
                </Trigger>
            </Style.Triggers>
        </Style>

        <!-- Action Button (primary) -->
        <Style x:Key="ActionButton" TargetType="Button">
            <Setter Property="Background" Value="{StaticResource AccentBrush}" />
            <Setter Property="Foreground" Value="{StaticResource WhiteBrush}" />
            <Setter Property="FontSize" Value="12" />
            <Setter Property="FontWeight" Value="SemiBold" />
            <Setter Property="Padding" Value="8,4" />
            <Setter Property="Margin" Value="0" />
            <Setter Property="BorderThickness" Value="0" />
            <Setter Property="Cursor" Value="Hand" />
            <Setter Property="Height" Value="32" />
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border Background="{TemplateBinding Background}" CornerRadius="4">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center" />
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter Property="Background" Value="#2980B9" />
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter Property="Background" Value="#1A5276" />
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter Property="Background" Value="#BDC3C7" />
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <!-- Secondary Button -->
        <Style x:Key="SecondaryBtn" TargetType="Button">
            <Setter Property="Background" Value="{StaticResource WhiteBrush}" />
            <Setter Property="Foreground" Value="{StaticResource AccentBrush}" />
            <Setter Property="FontSize" Value="12" />
            <Setter Property="FontWeight" Value="SemiBold" />
            <Setter Property="Padding" Value="8,4" />
            <Setter Property="Margin" Value="0" />
            <Setter Property="BorderThickness" Value="1.5" />
            <Setter Property="BorderBrush" Value="{StaticResource AccentBrush}" />
            <Setter Property="Cursor" Value="Hand" />
            <Setter Property="Height" Value="32" />
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border Background="{TemplateBinding Background}" CornerRadius="4"
                                BorderThickness="{TemplateBinding BorderThickness}"
                                BorderBrush="{TemplateBinding BorderBrush}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center" />
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter Property="Background" Value="#EBF5FB" />
                                <Setter Property="BorderBrush" Value="#2980B9" />
                                <Setter Property="Foreground" Value="#2980B9" />
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter Property="Background" Value="#D4E6F1" />
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter Property="Foreground" Value="#BDC3C7" />
                                <Setter Property="BorderBrush" Value="#BDC3C7" />
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>

        <Style x:Key="StatusText" TargetType="TextBlock">
            <Setter Property="FontSize" Value="11" />
            <Setter Property="Foreground" Value="{StaticResource GrayTextBrush}" />
            <Setter Property="Margin" Value="0" />
        </Style>
    </Window.Resources>

    <Grid Margin="15,10">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto" />
            <RowDefinition Height="Auto" />
            <RowDefinition Height="*" />
            <RowDefinition Height="Auto" />
            <RowDefinition Height="Auto" />
            <RowDefinition Height="Auto" />
            <RowDefinition Height="Auto" />
        </Grid.RowDefinitions>

        <!-- HEADER -->
        <Border Grid.Row="0" Background="#2C3E50" Padding="12,8" Margin="0,0,0,10" CornerRadius="4">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*" />
                    <ColumnDefinition Width="Auto" />
                </Grid.ColumnDefinitions>
                <StackPanel Grid.Column="0">
                    <TextBlock Text="Export Schedules to Excel"
                               FontSize="16" FontWeight="Bold" Foreground="White" />
                    <TextBlock Text="Compile multiple schedules into one Excel file"
                               FontSize="11" Foreground="#BDC3C7" Margin="0,2,0,0" />
                </StackPanel>
                <TextBlock Grid.Column="1" x:Name="live_count" Text="0 schedules"
                           FontSize="12" Foreground="#BDC3C7" VerticalAlignment="Center" />
            </Grid>
        </Border>

        <!-- SEARCH BOX SECTION -->
        <Grid Grid.Row="1" Margin="0,5,0,5">
            <TextBox x:Name="search_box" Style="{StaticResource ControlBox}" Height="28"
                     Text="Search schedules..." Foreground="Gray" VerticalAlignment="Center" />
        </Grid>

        <!-- SCHEDULES LISTBOX -->
        <ListBox Grid.Row="2" x:Name="listbox" Background="White"
                 BorderBrush="{StaticResource BorderBrush}" BorderThickness="1"
                 Margin="0,5,0,10" Padding="2">
            <ListBox.ItemContainerStyle>
                <Style TargetType="ListBoxItem">
                    <Setter Property="Padding" Value="4,2" />
                    <Setter Property="Margin" Value="1" />
                    <Setter Property="Template">
                        <Setter.Value>
                            <ControlTemplate TargetType="ListBoxItem">
                                <Border x:Name="Bd" Background="Transparent" CornerRadius="4"
                                        Padding="{TemplateBinding Padding}">
                                    <ContentPresenter />
                                </Border>
                                <ControlTemplate.Triggers>
                                    <Trigger Property="IsMouseOver" Value="True">
                                        <Setter TargetName="Bd" Property="Background" Value="#EBF5FB" />
                                    </Trigger>
                                </ControlTemplate.Triggers>
                            </ControlTemplate>
                        </Setter.Value>
                    </Setter>
                </Style>
            </ListBox.ItemContainerStyle>
        </ListBox>

        <!-- SELECTION HELPERS -->
        <Grid Grid.Row="3" Margin="0,0,0,10">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="Auto" />
                <ColumnDefinition Width="*" />
            </Grid.ColumnDefinitions>
            <StackPanel Grid.Column="0" Orientation="Horizontal">
                <Button x:Name="btn_all" Content="All" Style="{StaticResource SecondaryBtn}"
                        Width="60" Height="26" ToolTip="Select all schedules" />
                <Button x:Name="btn_none" Content="None" Style="{StaticResource SecondaryBtn}"
                        Width="60" Height="26" Margin="5,0,0,0" ToolTip="Clear all schedules" />
            </StackPanel>
        </Grid>

        <!-- EXPORT OPTIONS CARD -->
        <Border Grid.Row="4" Background="White" BorderBrush="{StaticResource BorderBrush}"
                BorderThickness="1" CornerRadius="8" Padding="12,10" Margin="0,0,0,10">
            <StackPanel>
                <Label Content="Export Options" FontSize="11" FontWeight="SemiBold"
                       Foreground="{StaticResource DarkTextBrush}" Margin="0,0,0,5" Padding="0"/>
                <Grid>
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto" />
                        <RowDefinition Height="Auto" />
                    </Grid.RowDefinitions>
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="*" />
                        <ColumnDefinition Width="*" />
                    </Grid.ColumnDefinitions>

                    <CheckBox x:Name="chk_strip" Grid.Row="0" Grid.Column="0" Content="Strip Units (numbers only)"
                              IsChecked="True" Margin="2,4" />
                    <CheckBox x:Name="chk_hidden" Grid.Row="0" Grid.Column="1" Content="Include Hidden Columns"
                              IsChecked="False" Margin="2,4" />
                    <CheckBox x:Name="chk_shade" Grid.Row="1" Grid.Column="0" Content="Zebra Row Shading"
                              IsChecked="True" Margin="2,4" />
                    <CheckBox x:Name="chk_pdf" Grid.Row="1" Grid.Column="1" Content="Save PDF Copy"
                              IsChecked="False" Margin="2,4" />
                </Grid>
            </StackPanel>
        </Border>

        <!-- STATUS BAR -->
        <Border Grid.Row="5" Background="#E8E8E8" Padding="12,8" Margin="0,5,0,10" CornerRadius="4">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto" />
                    <ColumnDefinition Width="*" />
                    <ColumnDefinition Width="Auto" />
                </Grid.ColumnDefinitions>
                <Border x:Name="status_badge" Background="#D5F5E3"
                        BorderBrush="{StaticResource SuccessBrush}" BorderThickness="1"
                        CornerRadius="4" Padding="12,2" Margin="0">
                    <TextBlock x:Name="status_textblock" Text="Ready"
                               FontSize="11" Foreground="#1E8449" FontWeight="SemiBold" />
                </Border>
                <Border x:Name="error_badge" Background="#FADBD8"
                        BorderBrush="{StaticResource DangerBrush}" BorderThickness="1"
                        CornerRadius="4" Padding="12,2" Margin="0" Visibility="Collapsed">
                    <TextBlock x:Name="error_text" Text="Error"
                               FontSize="11" Foreground="#C0392B" FontWeight="SemiBold" />
                </Border>
                <TextBlock Grid.Column="2" Text="Export Schedules v2.0 | pyZaid"
                           Style="{StaticResource StatusText}" VerticalAlignment="Center" />
            </Grid>
        </Border>

        <!-- BUTTON BAR -->
        <Grid Grid.Row="6" Margin="0,5,0,0">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="Auto" />
                <ColumnDefinition Width="*" />
                <ColumnDefinition Width="Auto" />
            </Grid.ColumnDefinitions>
            <Button Grid.Column="0" x:Name="btn_cancel" Content="Cancel" Style="{StaticResource SecondaryBtn}"
                    Width="100" Height="28" ToolTip="Cancel and close" />
            <Button Grid.Column="2" x:Name="btn_run" Content="Export &#x2192;" Style="{StaticResource ActionButton}"
                    Width="140" Height="28" ToolTip="Start exporting selected schedules to Excel" />
        </Grid>
    </Grid>
</Window>
'''

# ═══════════════════════════════════════════════════════════════════════════
# MAIN DIALOG CLASS / RUNNER
# ═══════════════════════════════════════════════════════════════════════════
def run_dialog(schedules):
    # Load XAML & find controls
    xaml_bytes = Encoding.UTF8.GetBytes(XAML)
    stream = MemoryStream(xaml_bytes)
    window = XamlReader.Load(stream)

    live_count      = window.FindName("live_count")
    search_box      = window.FindName("search_box")
    listbox         = window.FindName("listbox")
    btn_all         = window.FindName("btn_all")
    btn_none        = window.FindName("btn_none")
    chk_strip       = window.FindName("chk_strip")
    chk_hidden      = window.FindName("chk_hidden")
    chk_shade       = window.FindName("chk_shade")
    chk_pdf         = window.FindName("chk_pdf")
    status_badge    = window.FindName("status_badge")
    status_textblock = window.FindName("status_textblock")
    error_badge     = window.FindName("error_badge")
    error_text      = window.FindName("error_text")
    btn_cancel      = window.FindName("btn_cancel")
    btn_run         = window.FindName("btn_run")

    # Populate schedules list
    from System.Windows.Controls import TextBlock
    schedules_data = sorted(schedules, key=lambda s: s.Name)
    live_count.Text = "{} schedules".format(len(schedules_data))

    for sched in schedules_data:
        item = ListBoxItem()
        chk = CheckBox()
        
        # Use a TextBlock inside CheckBox to prevent WPF from interpreting underscore (_) as an access key accelerator
        tb = TextBlock()
        tb.Text = sched.Name
        chk.Content = tb
        
        chk.IsChecked = True
        chk.Margin = System.Windows.Thickness(2, 2, 2, 2)
        item.Content = chk
        item.Tag = sched
        listbox.Items.Add(item)

    # UI helpers
    def set_status(message, is_error=False):
        status_textblock.Text = message
        if not is_error:
            status_badge.Visibility = System.Windows.Visibility.Visible
            error_badge.Visibility = System.Windows.Visibility.Collapsed
        else:
            status_badge.Visibility = System.Windows.Visibility.Collapsed
            error_badge.Visibility = System.Windows.Visibility.Visible
        error_text.Text = message if is_error else ""

    def force_ui_update():
        Dispatcher.CurrentDispatcher.Invoke(
            Action(lambda: None), DispatcherPriority.Background)

    # Search Box Placeholders & Focus behaviour
    def on_search_focus(sender, args):
        if search_box.Text == "Search schedules...":
            search_box.Text = ""
            search_box.Foreground = System.Windows.Media.Brushes.Black
    search_box.GotFocus += on_search_focus

    def on_search_blur(sender, args):
        if not search_box.Text:
            search_box.Text = "Search schedules..."
            search_box.Foreground = System.Windows.Media.Brushes.Gray
    search_box.LostFocus += on_search_blur

    # Live Filtering
    def _filter_list(sender, args):
        search_txt = search_box.Text.lower()
        if search_txt == "search schedules...":
            search_txt = ""
        for item in listbox.Items:
            chk = item.Content
            # Access the Text property of the TextBlock content
            name = chk.Content.Text.lower()
            if search_txt in name:
                item.Visibility = System.Windows.Visibility.Visible
            else:
                item.Visibility = System.Windows.Visibility.Collapsed
    search_box.TextChanged += _filter_list

    # Selection Helpers
    def on_select_all(sender, args):
        for item in listbox.Items:
            item.Content.IsChecked = True
    btn_all.Click += on_select_all

    def on_select_none(sender, args):
        for item in listbox.Items:
            item.Content.IsChecked = False
    btn_none.Click += on_select_none

    # Export Trigger
    def on_export(sender, args):
        selected = []
        for i in range(listbox.Items.Count):
            item = listbox.Items[i]
            chk = item.Content
            if chk.IsChecked:
                selected.append(item.Tag)

        if not selected:
            set_status("Please select at least one schedule.", is_error=True)
            return

        default_name = "{}_Schedules.xlsx".format(doc.Title)
        for c in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
            default_name = default_name.replace(c, '_')

        # Use native Win32 SaveFileDialog to avoid pyrevit.forms engine dependencies
        from Microsoft.Win32 import SaveFileDialog
        sfd = SaveFileDialog()
        sfd.Filter = "Excel Workbook (*.xlsx)|*.xlsx"
        sfd.FileName = default_name
        sfd.Title = "Select Export Location"
        if sfd.ShowDialog() == True:
            save_path = sfd.FileName
        else:
            return

        # Progress reporting callback
        def report_progress(current, total, name):
            set_status("Exporting {} of {}: {}...".format(current, total, name))
            force_ui_update()

        set_status("Initializing Excel...")
        force_ui_update()

        # Run Excel export logic
        success, message = export_schedules_to_excel(
            selected,
            save_path,
            chk_strip.IsChecked,
            chk_hidden.IsChecked,
            chk_shade.IsChecked,
            chk_pdf.IsChecked,
            progress_callback=report_progress
        )

        if success:
            set_status("✅ Export complete!")
            btn_cancel.Content = "Close"
            btn_run.IsEnabled = False
            
            # Auto-open the file
            try:
                os.startfile(save_path)
            except Exception as e:
                pass
        else:
            set_status(message, is_error=True)

    btn_run.Click += on_export
    btn_cancel.Click += lambda s, e: window.Close()

    set_status("Ready")
    window.ShowDialog()


# ═══════════════════════════════════════════════════════════════════════════
# EXCEL EXPORT LOGIC
# ═══════════════════════════════════════════════════════════════════════════
def export_schedules_to_excel(schedules, output_path, strip_units=True, include_hidden=False, shade_rows=True, save_pdf=False, progress_callback=None):
    """
    Exports schedules to temporary text files, then compiles them into 
    a single Excel workbook using COM Interop.
    """
    # Force close any background zombie Excel processes to release file locks and prevent COM hangs
    try:
        import subprocess
        # 0x08000000 is CREATE_NO_WINDOW to run taskkill completely silently
        subprocess.call(["taskkill", "/f", "/im", "excel.exe"], creationflags=0x08000000)
    except:
        pass

    # Using Activator and Reflection to avoid Reference/IOError and AttributeError issues
    from System import Type, Activator, Reflection
    f_get = Reflection.BindingFlags.GetProperty
    f_set = Reflection.BindingFlags.SetProperty
    f_inv = Reflection.BindingFlags.InvokeMethod

    excel_type = Type.GetTypeFromProgID("Excel.Application")
    excel_app = Activator.CreateInstance(excel_type)
    
    # Safely set app properties
    excel_type.InvokeMember("Visible", f_set, None, excel_app, System.Array[System.Object]([False]))
    excel_type.InvokeMember("DisplayAlerts", f_set, None, excel_app, System.Array[System.Object]([False]))
    
    workbooks = excel_type.InvokeMember("Workbooks", f_get, None, excel_app, None)
    workbook = excel_type.InvokeMember("Add", f_inv, None, workbooks, None)
    workbook_type = workbook.GetType()
    
    try:
        temp_dir = tempfile.gettempdir()
        sheets = workbook_type.InvokeMember("Sheets", f_get, None, workbook, None)
        sheets_type = sheets.GetType()

        # Remove default sheets except the first one safely using a bounded loop to prevent infinite looping hangs
        count = sheets_type.InvokeMember("Count", f_get, None, sheets, None)
        for _ in range(count - 1):
            try:
                sheet_to_del = sheets_type.InvokeMember("Item", f_get, None, sheets, System.Array[System.Object]([2]))
                sheet_to_del.GetType().InvokeMember("Delete", f_inv, None, sheet_to_del, None)
            except:
                break
            
        for i, sched in enumerate(schedules):
            if progress_callback:
                progress_callback(i + 1, len(schedules), sched.Name)
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
                worksheet = sheets_type.InvokeMember("Item", f_get, None, sheets, System.Array[System.Object]([1]))
            else:
                current_count = sheets_type.InvokeMember("Count", f_get, None, sheets, None)
                last_sheet = sheets_type.InvokeMember("Item", f_get, None, sheets, System.Array[System.Object]([current_count]))
                args = System.Array[System.Object]([System.Type.Missing, last_sheet])
                worksheet = sheets_type.InvokeMember("Add", f_inv, None, sheets, args)
            
            worksheet_type = worksheet.GetType()
            
            # Preserving names: Only replace characters strictly forbidden by Excel (\ / ? * [ ] :)
            sheet_name = sched.Name
            for char in [':', '\\', '/', '?', '*', '[', ']']:
                sheet_name = sheet_name.replace(char, '_')
            worksheet_type.InvokeMember("Name", f_set, None, worksheet, System.Array[System.Object]([sheet_name[:31]]))
            
            # 3. Import data from TSV into the sheet
            connection_str = "TEXT;" + temp_path
            
            qts = worksheet_type.InvokeMember("QueryTables", f_get, None, worksheet, None)
            range_obj = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[System.Object](["A1"]))
            
            qt = qts.GetType().InvokeMember("Add", f_inv, None, qts, System.Array[System.Object]([connection_str, range_obj]))
            qt_type = qt.GetType()
            
            qt_type.InvokeMember("TextFileParseType", f_set, None, qt, System.Array[System.Object]([1])) # 1 = xlDelimited
            qt_type.InvokeMember("TextFileTabDelimiter", f_set, None, qt, System.Array[System.Object]([True]))
            qt_type.InvokeMember("Refresh", f_inv, None, qt, System.Array[System.Object]([False]))
            qt_type.InvokeMember("Delete", f_inv, None, qt, None)
            
            # 4. Global Formatting (Cambria 9, Thin Borders, Row Height, Column Min Width)
            used_range = worksheet_type.InvokeMember("UsedRange", f_get, None, worksheet, None)
            ur_type = used_range.GetType()
            
            ur_font = ur_type.InvokeMember("Font", f_get, None, used_range, None)
            ur_font_type = ur_font.GetType()
            ur_font_type.InvokeMember("Name", f_set, None, ur_font, System.Array[System.Object](["Cambria"]))
            ur_font_type.InvokeMember("Size", f_set, None, ur_font, System.Array[System.Object]([9]))
            
            ur_borders = ur_type.InvokeMember("Borders", f_get, None, used_range, None)
            ur_borders_type = ur_borders.GetType()
            ur_borders_type.InvokeMember("LineStyle", f_set, None, ur_borders, System.Array[System.Object]([1]))
            ur_borders_type.InvokeMember("Weight", f_set, None, ur_borders, System.Array[System.Object]([2]))

            rows_obj = worksheet_type.InvokeMember("Rows", f_get, None, worksheet, None)
            rows_obj.GetType().InvokeMember("RowHeight", f_set, None, rows_obj, System.Array[System.Object]([20]))

            # 5. Themed Header Formatting (Rows 1-3, limited to column data)
            ur_cols = ur_type.InvokeMember("Columns", f_get, None, used_range, None)
            last_col_idx = ur_cols.GetType().InvokeMember("Count", f_get, None, ur_cols, None)
            
            r1_cell1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([1, 1]))
            r1_cell2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([1, last_col_idx]))
            r1_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[System.Object]([r1_cell1, r1_cell2]))
            r1_range.GetType().InvokeMember("Merge", f_inv, None, r1_range, None)
            r1_range.GetType().InvokeMember("HorizontalAlignment", f_set, None, r1_range, System.Array[System.Object]([-4108])) # xlCenter

            page_setup = worksheet_type.InvokeMember("PageSetup", f_get, None, worksheet, None)
            page_setup_type = page_setup.GetType()
            page_setup_type.InvokeMember("LeftHeader", f_set, None, page_setup, System.Array[System.Object]([doc.Title]))
            current_date = System.DateTime.Now.ToString("yyyy-MM-dd")
            page_setup_type.InvokeMember("RightHeader", f_set, None, page_setup, System.Array[System.Object]([current_date]))
            
            orientation = 2 if last_col_idx > 7 else 1
            page_setup_type.InvokeMember("Orientation", f_set, None, page_setup, System.Array[System.Object]([orientation]))
            page_setup_type.InvokeMember("Zoom", f_set, None, page_setup, System.Array[System.Object]([False]))
            page_setup_type.InvokeMember("FitToPagesWide", f_set, None, page_setup, System.Array[System.Object]([1]))
            page_setup_type.InvokeMember("FitToPagesTall", f_set, None, page_setup, System.Array[System.Object]([False]))

            # 6. Clean Units and Format Columns (Currency & Precision)
            if strip_units:
                ur_type.InvokeMember("NumberFormat", f_set, None, used_range, System.Array[System.Object](["General"]))
                
                units_to_strip = [" mm", " mm2", " mm3", " m", " kg", " m2", " m^2", " sq m", "sq m", 
                                  u" m\xb2", u" mÂ²", u"Â²",
                                  u" m\xb3", " m3", " m^3", " cu m", "cu m", u" mÂ³", u"Â³"]
                for unit in units_to_strip:
                    replace_args = System.Array[System.Object]([unit, "", 2])
                    ur_type.InvokeMember("Replace", f_inv, None, used_range, replace_args)

                for col_idx in range(1, last_col_idx + 1):
                    h_cell = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([3, col_idx]))
                    h_val = h_cell.GetType().InvokeMember("Value2", f_get, None, h_cell, None)
                    h_str = str(h_val).lower() if h_val else ""
                    
                    target_col = worksheet_type.InvokeMember("Columns", f_get, None, worksheet, System.Array[System.Object]([col_idx]))
                    tc_type = target_col.GetType()
                    
                    if "cost" in h_str or "price" in h_str:
                        tc_type.InvokeMember("NumberFormat", f_set, None, target_col, System.Array[System.Object](["$#,##0.00"]))
                    else:
                        d_cell = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([4, col_idx]))
                        d_val = d_cell.GetType().InvokeMember("Value2", f_get, None, d_cell, None)
                        
                        if isinstance(d_val, (int, float)):
                            if d_val % 1 == 0:
                                tc_type.InvokeMember("NumberFormat", f_set, None, target_col, System.Array[System.Object](["0"]))
                            else:
                                tc_type.InvokeMember("NumberFormat", f_set, None, target_col, System.Array[System.Object](["0.00"]))
            else:
                replace_args = System.Array[System.Object]([u"Â", "", 2])
                ur_type.InvokeMember("Replace", f_inv, None, used_range, replace_args)

            # 7. Smart Header Detection
            r2_c1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([2, 1]))
            r2_c2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([2, last_col_idx]))
            r2_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[System.Object]([r2_c1, r2_c2]))
            
            r3_c1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([3, 1]))
            r3_c2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([3, last_col_idx]))
            r3_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[System.Object]([r3_c1, r3_c2]))
            
            ws_func = excel_type.InvokeMember("WorksheetFunction", f_get, None, excel_app, None)
            count_r2 = ws_func.GetType().InvokeMember("CountA", f_inv, None, ws_func, System.Array[System.Object]([r2_range]))
            count_r3 = ws_func.GetType().InvokeMember("CountA", f_inv, None, ws_func, System.Array[System.Object]([r3_range]))
            
            h_depth = 3 if (count_r2 == 0 and count_r3 > 0) else 2

            cell1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([1, 1]))
            cell2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([h_depth, last_col_idx]))
            header_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[System.Object]([cell1, cell2]))
            hr_type = header_range.GetType()
            
            # Background: Electric Teal (C_ACCENT: 32, 200, 170 -> 11192352)
            hr_interior = hr_type.InvokeMember("Interior", f_get, None, header_range, None)
            hr_interior.GetType().InvokeMember("Color", f_set, None, hr_interior, System.Array[System.Object]([11192352]))
            
            # Text Color: Black (0)
            hr_font = hr_type.InvokeMember("Font", f_get, None, header_range, None)
            hr_font_type = hr_font.GetType()
            hr_font_type.InvokeMember("Bold", f_set, None, hr_font, System.Array[System.Object]([True]))
            hr_font_type.InvokeMember("Color", f_set, None, hr_font, System.Array[System.Object]([0]))
            
            hr_type.InvokeMember("VerticalAlignment", f_set, None, header_range, System.Array[System.Object]([-4108]))
            hr_type.InvokeMember("HorizontalAlignment", f_set, None, header_range, System.Array[System.Object]([-4108]))

            # 8. Freeze Panes below headers
            body_start_cell = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([h_depth + 1, 1]))
            body_start_cell.GetType().InvokeMember("Select", f_inv, None, body_start_cell, None)
            active_window = excel_type.InvokeMember("ActiveWindow", f_get, None, excel_app, None)
            active_window.GetType().InvokeMember("FreezePanes", f_set, None, active_window, System.Array[System.Object]([True]))

            # 9. Alternating Row Shading (Zebra Striping)
            if shade_rows:
                last_row = ur_type.InvokeMember("Rows", f_get, None, used_range, None).GetType().InvokeMember("Count", f_get, None, ur_type.InvokeMember("Rows", f_get, None, used_range, None), None)
                if last_row > h_depth:
                    b_cell1 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([h_depth + 1, 1]))
                    b_cell2 = worksheet_type.InvokeMember("Cells", f_get, None, worksheet, System.Array[System.Object]([last_row, last_col_idx]))
                    body_range = worksheet_type.InvokeMember("Range", f_get, None, worksheet, System.Array[System.Object]([b_cell1, b_cell2]))
                    
                    fcs = body_range.GetType().InvokeMember("FormatConditions", f_get, None, body_range, None)
                    fc = fcs.GetType().InvokeMember("Add", f_inv, None, fcs, System.Array[System.Object]([2, System.Type.Missing, "=MOD(ROW(),2)=0"]))
                    interior = fc.GetType().InvokeMember("Interior", f_get, None, fc, None)
                    interior.GetType().InvokeMember("Color", f_set, None, interior, System.Array[System.Object]([15921906]))

            cols = worksheet_type.InvokeMember("Columns", f_get, None, worksheet, None)
            cols.GetType().InvokeMember("AutoFit", f_inv, None, cols, None)
            
            for col_idx in range(1, last_col_idx + 1):
                col_range = worksheet_type.InvokeMember("Columns", f_get, None, worksheet, System.Array[System.Object]([col_idx]))
                current_width = col_range.GetType().InvokeMember("ColumnWidth", f_get, None, col_range, None)
                if current_width < 8:
                    col_range.GetType().InvokeMember("ColumnWidth", f_set, None, col_range, System.Array[System.Object]([8]))
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
        # Save Final Workbook
        workbook_type.InvokeMember("SaveAs", f_inv, None, workbook, System.Array[System.Object]([output_path]))
        
        # Save as PDF if requested
        if save_pdf:
            pdf_path = output_path.replace(".xlsx", ".pdf")
            workbook_type.InvokeMember("ExportAsFixedFormat", f_inv, None, workbook, System.Array[System.Object]([0, pdf_path]))

        return True, "Successfully exported {} schedules to {}".format(len(schedules), output_path)
        
    except Exception as e:
        return False, str(e)
    finally:
        if 'workbook_type' in locals():
            workbook_type.InvokeMember("Close", f_inv, None, workbook, System.Array[System.Object]([False]))
        
        excel_type.InvokeMember("Quit", f_inv, None, excel_app, None)
        System.Runtime.InteropServices.Marshal.ReleaseComObject(excel_app)

# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
def run():
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
        System.Windows.MessageBox.Show(
            "No schedules found in the current document.",
            "Export Schedules",
            System.Windows.MessageBoxButton.OK,
            System.Windows.MessageBoxImage.Warning)
        return

    # Open dialog and execute export directly from within UI
    run_dialog(exportable_schedules)

if __name__ == "__main__":
    run()
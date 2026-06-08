#! python3
# -*- coding: utf-8 -*-
# pyRevit script - Obscured Rebar (CPython 3)

import sys
import clr
import System

# Standard Revit API imports
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
# Python.NET 3.0+ requires explicit imports instead of wildcards (*)
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    ViewType,
    View,
    View3D,
    Transaction,
    ElementId,
    ViewDetailLevel
)

# Bypassing 'from pyrevit import revit' to avoid CPython interface bugs in events.py
doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

# Add WPF assemblies
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader
from System.IO import MemoryStream
from System.Text import Encoding
from System.Windows.Controls import ListBoxItem, CheckBox
from System.Collections.Generic import List
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System import Action

# ----------------------------------------------------------------------
# XAML definition (OneFilterParameter theme)
# ----------------------------------------------------------------------
XAML = r'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Obscured Rebar"
        Height="550" Width="450"
        MinHeight="450" MinWidth="350"
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
            <Setter Property="Height" Value="28" />
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
            <Setter Property="Height" Value="28" />
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
        </Grid.RowDefinitions>

        <!-- HEADER -->
        <Border Grid.Row="0" Background="#2C3E50" Padding="12,8" Margin="0,0,0,10" CornerRadius="4">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*" />
                    <ColumnDefinition Width="Auto" />
                </Grid.ColumnDefinitions>
                <TextBlock Grid.Column="0" Text="Obscured Rebar"
                           FontSize="16" FontWeight="Bold" Foreground="White" VerticalAlignment="Center" />
                <TextBlock Grid.Column="1" x:Name="live_count" Text="0 rebars"
                           FontSize="12" Foreground="#BDC3C7" VerticalAlignment="Center" />
            </Grid>
        </Border>

        <!-- TARGET VIEWS LABEL -->
        <Label Grid.Row="1" Content="Views to Apply (Solid &amp; Unobscured):" Style="{StaticResource SectionLabel}" Margin="0,5,0,5" />

        <!-- TARGET VIEWS LISTBOX -->
        <ListBox Grid.Row="2" x:Name="views_list" Background="White"
                 BorderBrush="{StaticResource BorderBrush}" BorderThickness="1"
                 Margin="0,0,0,10" Padding="2">
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

        <!-- CONTROL ROW -->
        <Grid Grid.Row="3" Margin="0,0,0,0">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="Auto" />
                <ColumnDefinition Width="*" />
                <ColumnDefinition Width="Auto" />
            </Grid.ColumnDefinitions>
            <StackPanel Grid.Column="0" Orientation="Horizontal">
                <Button x:Name="btn_all" Content="All" Style="{StaticResource SecondaryBtn}"
                        Width="60" ToolTip="Select all views" />
                <Button x:Name="btn_none" Content="None" Style="{StaticResource SecondaryBtn}"
                        Width="60" Margin="5,0,0,0" ToolTip="Clear all views" />
            </StackPanel>
            <Button Grid.Column="2" x:Name="btn_apply" Content="Apply &#x2192;"
                    Style="{StaticResource ActionButton}" Width="140"
                    ToolTip="Make rebars unobscured and fine/medium in selected views" />
        </Grid>

        <!-- STATUS BAR -->
        <Border Grid.Row="4" Background="#E8E8E8" Padding="12,8" Margin="0,15,0,10" CornerRadius="4">
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
                <TextBlock Grid.Column="2" Text="Obscured Rebar v2.0 | pyZaid"
                           Style="{StaticResource StatusText}" VerticalAlignment="Center" />
            </Grid>
        </Border>

        <!-- BUTTON BAR -->
        <Border Grid.Row="5" Background="{StaticResource LightBgBrush}">
            <Button x:Name="btn_close" Content="Close" Style="{StaticResource SecondaryBtn}"
                    Width="100" HorizontalAlignment="Right" ToolTip="Close the tool" />
        </Border>
    </Grid>
</Window>
'''

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def get_view_display_name(view):
    """Format view name with type annotation."""
    v_type = view.ViewType
    if v_type == ViewType.ThreeD:
        type_name = "3D"
    elif v_type == ViewType.EngineeringPlan:
        type_name = "Structural Plan"
    elif v_type == ViewType.FloorPlan:
        type_name = "Floor Plan"
    elif v_type == ViewType.CeilingPlan:
        type_name = "Ceiling Plan"
    else:
        type_name = str(v_type)
    return "{} [{}]".format(view.Name, type_name)


def get_id_value(eid):
    """Safely get the integer value of an ElementId across Revit API versions."""
    return getattr(eid, "Value", getattr(eid, "IntegerValue", -1))


# ----------------------------------------------------------------------
# Main UI logic
# ----------------------------------------------------------------------
def run():
    # ------------------------------------------------------------------
    # 1. Collect elements & views
    # ------------------------------------------------------------------
    # Selection logic
    selection_ids = list(uidoc.Selection.GetElementIds())
    selected_rebars = []
    for eid in selection_ids:
        el = doc.GetElement(eid)
        if el and el.Category and get_id_value(el.Category.Id) == int(BuiltInCategory.OST_Rebar):
            selected_rebars.append(el)

    is_filtered_by_selection = False
    if selected_rebars:
        rebars_to_process = selected_rebars
        is_filtered_by_selection = True
    else:
        rebars_to_process = list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_Rebar)
            .WhereElementIsNotElementType()
            .ToElements()
        )

    if not rebars_to_process:
        System.Windows.MessageBox.Show(
            "No rebars found in the document.",
            "Obscured Rebar",
            System.Windows.MessageBoxButton.OK,
            System.Windows.MessageBoxImage.Warning)
        return

    allowed_view_types = {
        ViewType.FloorPlan,
        ViewType.CeilingPlan,
        ViewType.EngineeringPlan,
        ViewType.Section,
        ViewType.Elevation,
        ViewType.ThreeD
    }

    all_views = list(
        FilteredElementCollector(doc)
        .OfClass(View)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    eligible_views = sorted(
        [v for v in all_views if not v.IsTemplate and v.ViewType in allowed_view_types],
        key=lambda x: x.Name
    )

    if not eligible_views:
        System.Windows.MessageBox.Show(
            "No eligible views found.",
            "Obscured Rebar",
            System.Windows.MessageBoxButton.OK,
            System.Windows.MessageBoxImage.Warning)
        return

    # ------------------------------------------------------------------
    # 2. Load XAML & find controls
    # ------------------------------------------------------------------
    xaml_bytes = Encoding.UTF8.GetBytes(XAML)
    stream = MemoryStream(xaml_bytes)
    window = XamlReader.Load(stream)

    live_count      = window.FindName("live_count")
    views_list      = window.FindName("views_list")
    btn_all         = window.FindName("btn_all")
    btn_none        = window.FindName("btn_none")
    btn_apply       = window.FindName("btn_apply")
    btn_close       = window.FindName("btn_close")
    status_badge    = window.FindName("status_badge")
    status_textblock = window.FindName("status_textblock")
    error_badge     = window.FindName("error_badge")
    error_text      = window.FindName("error_text")

    # ------------------------------------------------------------------
    # 3. Populate UI
    # ------------------------------------------------------------------
    if is_filtered_by_selection:
        live_count.Text = "{} rebars (Selected)".format(len(rebars_to_process))
    else:
        live_count.Text = "{} rebars (All)".format(len(rebars_to_process))

    views_data = [(v, get_view_display_name(v)) for v in eligible_views]

    # ------------------------------------------------------------------
    # 4. UI helpers
    # ------------------------------------------------------------------
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
        """Forces the WPF window to redraw so status updates show instantly."""
        Dispatcher.CurrentDispatcher.Invoke(
            Action(lambda: None), DispatcherPriority.Background)

    def update_selection_status():
        selected_count = 0
        for i in range(views_list.Items.Count):
            item = views_list.Items[i]
            chk = item.Content
            if chk.IsChecked:
                selected_count += 1
        set_status("{} of {} views selected. Ready to apply.".format(selected_count, len(views_data)))

    def on_checkbox_toggled(sender, args):
        update_selection_status()

    # Target views list
    for view, name in views_data:
        item = ListBoxItem()
        chk = CheckBox()
        chk.Content = name
        chk.IsChecked = True
        chk.Click += on_checkbox_toggled
        chk.Margin = System.Windows.Thickness(2, 2, 2, 2)
        item.Content = chk
        views_list.Items.Add(item)

    # ------------------------------------------------------------------
    # 5. Event handlers
    # ------------------------------------------------------------------
    def on_select_all(sender, args):
        for item in views_list.Items:
            item.Content.IsChecked = True
        update_selection_status()
    btn_all.Click += on_select_all

    def on_select_none(sender, args):
        for item in views_list.Items:
            item.Content.IsChecked = False
        update_selection_status()
    btn_none.Click += on_select_none

    def on_apply(sender, args):
        selected_views = []
        for i in range(views_list.Items.Count):
            item = views_list.Items[i]
            chk = item.Content
            if chk.IsChecked:
                selected_views.append(views_data[i][0])

        if not selected_views:
            set_status("Please select at least one view.", is_error=True)
            return

        set_status("Processing {} rebars...".format(len(rebars_to_process)))
        force_ui_update()

        t = Transaction(doc, "Show Rebars Unobscured & Set Detail Levels")
        t.Start()
        try:
            for view in selected_views:
                # Set detail levels
                has_view_template = get_id_value(view.ViewTemplateId) != -1
                if not has_view_template:
                    if isinstance(view, View3D):
                        if view.DetailLevel != ViewDetailLevel.Fine:
                            view.DetailLevel = ViewDetailLevel.Fine
                    elif view.ViewType in allowed_view_types:
                        if view.DetailLevel != ViewDetailLevel.Medium:
                            view.DetailLevel = ViewDetailLevel.Medium

                is_3d = isinstance(view, View3D)

                for rebar in rebars_to_process:
                    try:
                        if hasattr(rebar, "SetUnobscuredInView") and not rebar.IsUnobscuredInView(view):
                            rebar.SetUnobscuredInView(view, True)

                        if is_3d and hasattr(rebar, "SetSolidInView") and not rebar.IsSolidInView(view):
                            rebar.SetSolidInView(view, True)
                    except:
                        pass

            t.Commit()
            set_status("✅ Success! Updated {} rebar(s) across {} view(s).".format(
                len(rebars_to_process), len(selected_views)
            ))
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            set_status("Error: " + str(ex), is_error=True)

    btn_apply.Click += on_apply

    def on_close(sender, args):
        window.Close()
    btn_close.Click += on_close

    # ------------------------------------------------------------------
    # 6. Show dialog
    # ------------------------------------------------------------------
    update_selection_status()
    window.ShowDialog()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    run()

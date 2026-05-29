#! python3
# -*- coding: utf-8 -*-
# pyRevit script - OneFilterParameter (CPython 3)

import sys
import re
import clr
import System

# Standard Revit API imports
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

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

# ----------------------------------------------------------------------
# XAML definition (uniform modern styling, responsive layouts)
# ----------------------------------------------------------------------
XAML = r'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="OneFilterParameter"
        Height="700" Width="800"
        MinHeight="700" MinWidth="700"
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

        <!-- Standard card border -->
        <Style x:Key="CardBorder" TargetType="Border">
            <Setter Property="Background" Value="{StaticResource WhiteBrush}" />
            <Setter Property="BorderBrush" Value="{StaticResource BorderBrush}" />
            <Setter Property="BorderThickness" Value="1" />
            <Setter Property="CornerRadius" Value="8" />
            <Setter Property="Margin" Value="10,0,0,0" />
            <Setter Property="Padding" Value="15" />
            <Setter Property="Effect">
                <Setter.Value>
                    <DropShadowEffect Color="#000000" Opacity="0.05" BlurRadius="10" ShadowDepth="2" />
                </Setter.Value>
            </Setter>
        </Style>

        <Style x:Key="SectionLabel" TargetType="Label">
            <Setter Property="FontSize" Value="13" />
            <Setter Property="FontWeight" Value="SemiBold" />
            <Setter Property="Foreground" Value="{StaticResource DarkTextBrush}" />
            <Setter Property="BorderBrush" Value="{StaticResource AccentBrush}" />
            <Setter Property="BorderThickness" Value="0,0,0,2" />
            <Setter Property="Padding" Value="0,0,0,4" />
            <Setter Property="Margin" Value="0,10,0,10" />
        </Style>

        <!-- Standard TextBox (flat borders, reset margin) -->
        <Style x:Key="ControlBox" TargetType="TextBox">
            <Setter Property="FontSize" Value="12" />
            <Setter Property="Padding" Value="4,4" />
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

        <!-- Standard ComboBox (flat) -->
        <Style x:Key="ControlCombo" TargetType="ComboBox">
            <Setter Property="FontSize" Value="12" />
            <Setter Property="Padding" Value="4,4" />
            <Setter Property="Margin" Value="0" />
            <Setter Property="BorderBrush" Value="{StaticResource BorderBrush}" />
            <Setter Property="BorderThickness" Value="1" />
            <Setter Property="Background" Value="{StaticResource WhiteBrush}" />
            <Setter Property="Foreground" Value="{StaticResource DarkTextBrush}" />
            <Setter Property="VerticalContentAlignment" Value="Center" />
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
                        <Border Background="{TemplateBinding Background}" CornerRadius="4" BorderThickness="{TemplateBinding BorderThickness}" BorderBrush="{TemplateBinding BorderBrush}">
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
            <RowDefinition Height="*" />
            <RowDefinition Height="Auto" />
            <RowDefinition Height="Auto" />
        </Grid.RowDefinitions>

        <!-- HEADER -->
        <Border Grid.Row="0" Background="#2C3E50" Padding="12,8" Margin="0,0,0,10" CornerRadius="4">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto" />
                    <ColumnDefinition Width="*" />
                    <ColumnDefinition Width="Auto" />
                </Grid.ColumnDefinitions>
                <TextBlock Grid.Column="0" x:Name="header_title" Text="OneFilterParameter"
                           FontSize="16" FontWeight="Bold" Foreground="White" VerticalAlignment="Center" />
                <TextBlock Grid.Column="2" x:Name="live_count" Text="0 Elements"
                           FontSize="12" Foreground="#BDC3C7" VerticalAlignment="Center" />
            </Grid>
        </Border>

        <!-- BODY -->
        <Grid Grid.Row="1">
            <Grid.ColumnDefinitions>
                <ColumnDefinition Width="Auto" MinWidth="350" />
                <ColumnDefinition Width="Auto" MaxWidth="10" />
                <ColumnDefinition Width="*" MinWidth="300" />
            </Grid.ColumnDefinitions>

            <!-- LEFT COLUMN -->
            <Grid Grid.Column="0" Margin="0,0,12,0">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="*" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                    <RowDefinition Height="Auto" />
                </Grid.RowDefinitions>

                <Label Grid.Row="0" Content="Scope:" Style="{StaticResource SectionLabel}" Margin="0,0,0,5" />
                <StackPanel Grid.Row="1" Orientation="Horizontal" Margin="0,0,0,10">
                    <RadioButton x:Name="rb_whole" Content="Whole Model" GroupName="scope" IsChecked="True" Margin="0,0,15,0" Cursor="Hand" VerticalAlignment="Center"/>
                    <RadioButton x:Name="rb_view" Content="Active View" GroupName="scope" Margin="0,0,15,0" Cursor="Hand" VerticalAlignment="Center"/>
                    <RadioButton x:Name="rb_selection" Content="Current Selection" GroupName="scope" Margin="0,0,0,0" Cursor="Hand" VerticalAlignment="Center"/>
                </StackPanel>

                <Label Grid.Row="2" Content="Categories:" Style="{StaticResource SectionLabel}" Margin="0,0,0,5" />
                
                <ListBox Grid.Row="3" x:Name="category_list" Background="White" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1" Margin="0,0,0,10" Padding="2">
                    <ListBox.ItemContainerStyle>
                        <Style TargetType="ListBoxItem">
                            <Setter Property="Padding" Value="4,2"/>
                            <Setter Property="Margin" Value="1"/>
                            <Setter Property="Template">
                                <Setter.Value>
                                    <ControlTemplate TargetType="ListBoxItem">
                                        <Border x:Name="Bd" Background="Transparent" CornerRadius="4" Padding="{TemplateBinding Padding}">
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

                <Grid Grid.Row="4">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto" />
                        <ColumnDefinition Width="*" />
                        <ColumnDefinition Width="Auto" />
                    </Grid.ColumnDefinitions>
                    <StackPanel Grid.Column="0" Orientation="Horizontal">
                        <Button x:Name="btn_all_cats" Content="All" Style="{StaticResource SecondaryBtn}" Width="60" ToolTip="Select all" />
                        <Button x:Name="btn_none_cats" Content="None" Style="{StaticResource SecondaryBtn}" Width="60" Margin="5,0,0,0" ToolTip="Clear all" />
                    </StackPanel>
                    <Button Grid.Column="2" x:Name="btn_load_params" Content="Load Parameters →" Style="{StaticResource ActionButton}" Width="140" ToolTip="Load parameters &amp; proceed" />
                </Grid>

                <TextBlock Grid.Row="5" x:Name="cat_status" Text="Select scope and categories, then click Load Parameters." Style="{StaticResource StatusText}" Margin="0,5" TextWrapping="Wrap" />

                <Rectangle Grid.Row="6" Height="1" Fill="{StaticResource DividerBrush}" Margin="0,0,0,10" />

                <Label Grid.Row="7" Content="Filter by Parameter:" Style="{StaticResource SectionLabel}" />
                <Grid Grid.Row="8" Margin="0,0,0,10">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="100" />
                        <ColumnDefinition Width="*" />
                        <ColumnDefinition Width="30" />
                    </Grid.ColumnDefinitions>
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto" />
                        <RowDefinition Height="Auto" />
                        <RowDefinition Height="Auto" />
                    </Grid.RowDefinitions>

                    <TextBlock Grid.Row="0" Grid.Column="0" Text="Parameter:" FontSize="13" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" VerticalAlignment="Center" Margin="0,0,5,5" />
                    <ComboBox Grid.Row="0" Grid.Column="1" x:Name="filter_param" Style="{StaticResource ControlCombo}" IsEditable="True" Height="28" Margin="0,0,5,5" />
                    <Button Grid.Row="0" Grid.Column="2" x:Name="btn_confirm_param" Content="✓" Style="{StaticResource ActionButton}" FontSize="16" Padding="0" Height="28" Width="28" Margin="0,0,0,5" ToolTip="Load operators and values for this parameter" />

                    <TextBlock Grid.Row="1" Grid.Column="0" Text="Operator:" FontSize="13" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" VerticalAlignment="Center" Margin="0,0,5,5" />
                    <ComboBox Grid.Row="1" Grid.Column="1" Grid.ColumnSpan="2" x:Name="filter_op" Style="{StaticResource ControlCombo}" Height="28" Margin="0,0,0,5" />

                    <TextBlock Grid.Row="2" Grid.Column="0" Text="Value:" FontSize="13" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" VerticalAlignment="Center" Margin="0,0,5,0" />
                    <ComboBox Grid.Row="2" Grid.Column="1" Grid.ColumnSpan="2" x:Name="filter_val" Style="{StaticResource ControlCombo}" IsEditable="True" Height="28" Margin="0,0,0,0" />
                </Grid>

                <StackPanel Grid.Row="9" Orientation="Vertical" Margin="0">
                    <Button x:Name="btn_apply_filter" Content="Apply Filter →" Style="{StaticResource ActionButton}" Width="140" HorizontalAlignment="Right" ToolTip="Filter elements by the selected parameter, operator and value" />
                    <TextBlock x:Name="filter_status" Text="Choose parameter, operator, and value, then click Apply Filter." Style="{StaticResource StatusText}" Margin="0,5,0,0" TextWrapping="Wrap" />
                </StackPanel>
            </Grid>

            <GridSplitter Grid.Column="1" Width="5" HorizontalAlignment="Center" VerticalAlignment="Stretch" Background="{StaticResource DividerBrush}" ResizeBehavior="BasedOnAlignment" />

            <!-- RIGHT COLUMN -->
            <Border Grid.Column="2" Style="{StaticResource CardBorder}" VerticalAlignment="Stretch">
                <ScrollViewer VerticalScrollBarVisibility="Auto">
                    <StackPanel>
                        <Label Content="Edit Parameters:" Style="{StaticResource SectionLabel}" />

                        <Grid Margin="0,0,0,10">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="100" />
                                <ColumnDefinition Width="*" />
                                <ColumnDefinition Width="30" />
                            </Grid.ColumnDefinitions>
                            <Grid.RowDefinitions>
                                <RowDefinition Height="Auto" />
                                <RowDefinition Height="Auto" />
                                <RowDefinition Height="Auto" />
                                <RowDefinition Height="Auto" />
                            </Grid.RowDefinitions>

                            <TextBlock Grid.Row="0" Grid.Column="0" Text="Parameter:" FontSize="13" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" VerticalAlignment="Center" Margin="0,0,5,5" />
                            <ComboBox Grid.Row="0" Grid.Column="1" x:Name="edit_param" Style="{StaticResource ControlCombo}" IsEditable="True" Height="28" Margin="0,0,5,5" />
                            <Button Grid.Row="0" Grid.Column="2" x:Name="btn_confirm_edit" Content="✓" Style="{StaticResource ActionButton}" FontSize="16" Padding="0" Height="28" Width="28" Margin="0,0,0,10" ToolTip="Confirm parameter to edit (populates values)" />

                            <TextBlock Grid.Row="1" Grid.Column="0" Text="Operation:" FontSize="13" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" VerticalAlignment="Center" Margin="0,0,5,5" />
                            <ComboBox Grid.Row="1" Grid.Column="1" Grid.ColumnSpan="2" x:Name="edit_op" Style="{StaticResource ControlCombo}" Height="28" Margin="0,0,0,5" />

                            <TextBlock Grid.Row="2" Grid.Column="0" Text="Value:" FontSize="13" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" VerticalAlignment="Center" Margin="0,0,5,5" />
                            <ComboBox Grid.Row="2" Grid.Column="1" Grid.ColumnSpan="2" x:Name="edit_val1" Style="{StaticResource ControlCombo}" IsEditable="True" Height="28" Margin="0,0,0,5" />

                            <TextBlock Grid.Row="3" Grid.Column="0" Text="Replace Value:" FontSize="13" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" VerticalAlignment="Center" Margin="0,0,5,5" />
                            <TextBox Grid.Row="3" Grid.Column="1" Grid.ColumnSpan="2" x:Name="edit_val2" Style="{StaticResource ControlBox}" Height="28" Margin="0,0,0,5" />
                        </Grid>

                        <Button x:Name="btn_execute" Content="Execute" Style="{StaticResource ActionButton}" Width="140" Height="28" HorizontalAlignment="Right" ToolTip="Apply the edit operation to all filtered elements" />
                        <TextBlock x:Name="edit_status" Text="Apply filter first, then edit here." Style="{StaticResource StatusText}" Margin="0,5,0,0" TextWrapping="Wrap" />
                    </StackPanel>
                </ScrollViewer>
            </Border>
        </Grid>

        <!-- STATUS BAR -->
        <Border Grid.Row="2" Background="#E8E8E8" Padding="12,8" Margin="0,15,0,10" CornerRadius="4">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="Auto" />
                    <ColumnDefinition Width="*" />
                    <ColumnDefinition Width="Auto" />
                </Grid.ColumnDefinitions>
                <Border x:Name="status_badge" Background="#D5F5E3" BorderBrush="{StaticResource SuccessBrush}" BorderThickness="1" CornerRadius="4" Padding="12,2" Margin="0">
                    <TextBlock x:Name="status_textblock" Text="Ready" FontSize="11" Foreground="#1E8449" FontWeight="SemiBold" />
                </Border>
                <Border x:Name="error_badge" Background="#FADBD8" BorderBrush="{StaticResource DangerBrush}" BorderThickness="1" CornerRadius="4" Padding="12,2" Margin="0" Visibility="Collapsed">
                    <TextBlock x:Name="error_text" Text="Error" FontSize="11" Foreground="#C0392B" FontWeight="SemiBold" />
                </Border>
                <TextBlock Grid.Column="2" Text="OneFilterParameter v3.0 | pyZaid" Style="{StaticResource StatusText}" VerticalAlignment="Center" />
            </Grid>
        </Border>

        <!-- BUTTON BAR -->
        <Border Grid.Row="3" Background="{StaticResource LightBgBrush}">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*" />
                    <ColumnDefinition Width="Auto" />
                </Grid.ColumnDefinitions>
                <Button Grid.Column="0" x:Name="btn_select_elems" Content="Select in Revit" Style="{StaticResource SecondaryBtn}" Width="140" HorizontalAlignment="Right" ToolTip="Select filtered elements and close window" IsEnabled="False" />
                <Button Grid.Column="1" x:Name="btn_close" Content="Close" Style="{StaticResource SecondaryBtn}" Width="100" HorizontalAlignment="Right" ToolTip="Close the tool without selecting" Margin="10,0,0,0" />
            </Grid>
        </Border>
    </Grid>
</Window>
'''

# ----------------------------------------------------------------------
# Main UI logic
# ----------------------------------------------------------------------
def run_ui():
    # Load XAML
    bytes = Encoding.UTF8.GetBytes(XAML)
    stream = MemoryStream(bytes)
    window = XamlReader.Load(stream)

    # Find controls
    header_title      = window.FindName("header_title")
    live_count        = window.FindName("live_count")
    category_list     = window.FindName("category_list")
    btn_all_cats      = window.FindName("btn_all_cats")
    btn_none_cats     = window.FindName("btn_none_cats")
    btn_load_params   = window.FindName("btn_load_params")
    cat_status        = window.FindName("cat_status")

    rb_whole          = window.FindName("rb_whole")
    rb_view           = window.FindName("rb_view")
    rb_selection      = window.FindName("rb_selection")

    filter_param      = window.FindName("filter_param")
    filter_op         = window.FindName("filter_op")
    filter_val        = window.FindName("filter_val")
    btn_confirm_param = window.FindName("btn_confirm_param")
    btn_apply_filter  = window.FindName("btn_apply_filter")
    btn_select_elems  = window.FindName("btn_select_elems")
    filter_status     = window.FindName("filter_status")

    edit_param        = window.FindName("edit_param")
    edit_op           = window.FindName("edit_op")
    edit_val1         = window.FindName("edit_val1")
    edit_val2         = window.FindName("edit_val2")
    btn_confirm_edit  = window.FindName("btn_confirm_edit")
    btn_execute       = window.FindName("btn_execute")
    edit_status       = window.FindName("edit_status")

    status_badge      = window.FindName("status_badge")
    status_textblock  = window.FindName("status_textblock")
    error_badge       = window.FindName("error_badge")
    error_text        = window.FindName("error_text")
    btn_close         = window.FindName("btn_close")

    # State Variables
    state = {
        "filtered_ids": [],
        "filtered_elements": [],
        "all_params_cache": [],
        "val_to_num": {}
    }

    # ------------------------------------------------------------------
    # Helper functions (Revit API)
    # ------------------------------------------------------------------
    def get_categories_by_scope():
        cats = set()
        try:
            if rb_whole.IsChecked:
                for c in doc.Settings.Categories:
                    if c.CategoryType == CategoryType.Model and c.AllowsBoundParameters:
                        try:
                            filter = ElementCategoryFilter(c.Id)
                            if FilteredElementCollector(doc).WherePasses(filter).WhereElementIsNotElementType().GetElementCount() > 0:
                                cats.add(c.Name)
                        except:
                            pass
            elif rb_view.IsChecked:
                view = doc.ActiveView
                collector = FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType()
                for e in collector:
                    if e.Category:
                        cats.add(e.Category.Name)
            elif rb_selection.IsChecked:
                sel = uidoc.Selection.GetElementIds()
                for id in sel:
                    elem = doc.GetElement(id)
                    if elem and elem.Category:
                        cats.add(elem.Category.Name)
            return sorted(cats)
        except Exception as ex:
            return []

    def get_elements_by_categories(category_names, scope):
        if not category_names:
            return []
            
        cat_ids = []
        for c in doc.Settings.Categories:
            if c.Name in category_names:
                cat_ids.append(c.Id)
                
        if not cat_ids:
            return []
            
        cat_list = List[ElementId]()
        for cid in cat_ids:
            cat_list.Add(cid)
            
        multi_filter = ElementMulticategoryFilter(cat_list)
        
        if scope == "whole":
            collector = FilteredElementCollector(doc).WherePasses(multi_filter).WhereElementIsNotElementType()
            return list(collector.ToElements())
        elif scope == "view":
            view = doc.ActiveView
            collector = FilteredElementCollector(doc, view.Id).WherePasses(multi_filter).WhereElementIsNotElementType()
            return list(collector.ToElements())
        else:
            sel_ids = uidoc.Selection.GetElementIds()
            if not sel_ids:
                return []
            elements = []
            for id in sel_ids:
                e = doc.GetElement(id)
                if e and e.Category and e.Category.Name in category_names:
                    elements.append(e)
            return elements

    # --- NEW: Formats a parameter cleanly to text (Handles ElementId mapping) ---
    def get_param_val_str(param, store_numeric=False):
        if param is None:
            return None
            
        st = param.StorageType
        
        if st == StorageType.ElementId:
            eid = param.AsElementId()
            eid_val = getattr(eid, "Value", getattr(eid, "IntegerValue", -1))
            if eid_val != -1:
                ref_elem = doc.GetElement(eid)
                name = ref_elem.Name if ref_elem else (param.AsValueString() or "Unknown")
                return "[{0}] {1}".format(eid_val, name)
            else:
                return "None"
                
        val_str = param.AsValueString()
        if val_str is None:
            if st == StorageType.String:
                val_str = param.AsString()
            elif st == StorageType.Integer:
                val_str = str(param.AsInteger())
            elif st == StorageType.Double:
                val_str = str(param.AsDouble())
                
        if store_numeric and val_str is not None:
            if st == StorageType.Double:
                state["val_to_num"][val_str] = param.AsDouble()
            elif st == StorageType.Integer:
                state["val_to_num"][val_str] = float(param.AsInteger())
                
        return val_str if val_str is not None else ""

    def get_common_params(elements, writable_only=False, string_only=False):
        if not elements:
            return []
        common = None
        for e in elements[:50]:
            cur = set()
            # 1. Instance Parameters
            for p in e.Parameters:
                try:
                    if writable_only and p.IsReadOnly: continue
                    if string_only and p.StorageType != StorageType.String: continue
                    cur.add(p.Definition.Name)
                except: continue
                    
            # 2. Type Parameters (So users can batch-edit Type properties)
            tid = e.GetTypeId()
            if tid and tid != ElementId.InvalidElementId:
                te = doc.GetElement(tid)
                if te:
                    for p in te.Parameters:
                        try:
                            if writable_only and p.IsReadOnly: continue
                            if string_only and p.StorageType != StorageType.String: continue
                            cur.add(p.Definition.Name)
                        except: continue

            if common is None:
                common = cur
            else:
                common = common.intersection(cur)
            if len(common) == 0:
                break
        return sorted(common) if common else []

    def get_param_values(elements, param_name):
        values = set()
        state["val_to_num"] = {}
        for e in elements:
            try:
                param = e.LookupParameter(param_name)
                if param is None:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te:
                            param = te.LookupParameter(param_name)
                if param is not None:
                    val_str = get_param_val_str(param, store_numeric=True)
                    if val_str is not None:
                        values.add(val_str)
            except:
                continue
        return sorted(values)

    def extract_numeric(text):
        if not text: return None
        s = str(text).replace(" ", "")
        last_dot = s.rfind('.')
        last_comma = s.rfind(',')
        
        # Determine European/Continental vs Anglo Decimal
        if last_comma > last_dot:
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
            
        m = re.search(r'-?\d+(\.\d+)?', s)
        if m:
            try: return float(m.group(0))
            except: pass
        return None

    def filter_elements(elements, param_name, operator, value):
        filtered_ids = []
        if value is None:
            value = ""
            
        for e in elements:
            try:
                param = e.LookupParameter(param_name)
                if param is None:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te: param = te.LookupParameter(param_name)
                if param is None:
                    continue
                    
                cur_val_str = get_param_val_str(param) or ""
                cur_low = cur_val_str.lower()
                val_low = str(value).lower()
                
                if operator in ("equals", "does not equal", "contains", "does not contain",
                                "begins with", "does not begin with", "ends with", "does not end with"):
                    if operator == "equals" and cur_low != val_low: continue
                    elif operator == "does not equal" and cur_low == val_low: continue
                    elif operator == "contains" and val_low not in cur_low: continue
                    elif operator == "does not contain" and val_low in cur_low: continue
                    elif operator == "begins with" and not cur_low.startswith(val_low): continue
                    elif operator == "does not begin with" and cur_low.startswith(val_low): continue
                    elif operator == "ends with" and not cur_low.endswith(val_low): continue
                    elif operator == "does not end with" and cur_low.endswith(val_low): continue
                    filtered_ids.append(e.Id)
                else:
                    # Robust Numeric comparison
                    try:
                        cur_num = None
                        num_val = None
                        st = param.StorageType
                        if st not in (StorageType.Integer, StorageType.Double): continue
                            
                        if st == StorageType.Integer:
                            cur_num = float(param.AsInteger())
                        elif st == StorageType.Double:
                            cur_num = param.AsDouble()
                            
                        if value in state.get("val_to_num", {}):
                            num_val = state["val_to_num"][value]
                        else:
                            cur_num_ext = extract_numeric(cur_val_str)
                            num_val_ext = extract_numeric(value)
                            if cur_num_ext is not None and num_val_ext is not None:
                                cur_num = cur_num_ext
                                num_val = num_val_ext
                            else:
                                num_val = float(value)
                                
                        if cur_num is None or num_val is None: continue
                            
                        if operator == "is greater than" and not cur_num > num_val: continue
                        elif operator == "is greater than or equal to" and not cur_num >= num_val: continue
                        elif operator == "is less than" and not cur_num < num_val: continue
                        elif operator == "is less than or equal to" and not cur_num <= num_val: continue
                            
                        filtered_ids.append(e.Id)
                    except Exception:
                        continue
            except Exception:
                continue
        return filtered_ids

    def modify_elements(elem_ids, param_name, operation, val1, val2):
        modified = 0
        errors = []
        if not elem_ids:
            return 0, ["No elements selected."]
            
        t = Transaction(doc, "OneParameter Batch Edit")
        t.Start()
        try:
            processed_types = set() # Prevent editing the same Type Parameter 50 times in a row
            
            for eid in elem_ids:
                eid_val = getattr(eid, "Value", getattr(eid, "IntegerValue", str(eid)))
                try:
                    elem = doc.GetElement(eid)
                    if not elem: continue
                    
                    target_elem = elem
                    param = elem.LookupParameter(param_name)
                    
                    # Target Type Parameter if not found on instance
                    if param is None:
                        tid = elem.GetTypeId()
                        if tid and tid != ElementId.InvalidElementId:
                            te = doc.GetElement(tid)
                            if te:
                                param = te.LookupParameter(param_name)
                                target_elem = te
                    
                    if param is None or param.IsReadOnly:
                        errors.append("Param '{0}' not found or read-only on element {1}".format(param_name, eid_val))
                        continue
                        
                    # Skip if we already modified this Type in this batch!
                    if target_elem.Id != elem.Id:
                        target_id_val = getattr(target_elem.Id, "Value", getattr(target_elem.Id, "IntegerValue", -1))
                        if target_id_val in processed_types:
                            modified += 1 # We consider it modified for the instance
                            continue
                    
                    st = param.StorageType
                    
                    if operation == "Delete":
                        if st == StorageType.String: param.Set(System.String(""))
                        elif st == StorageType.Integer: param.Set(System.Int32(0))
                        elif st == StorageType.Double: param.Set(System.Double(0.0))
                        elif st == StorageType.ElementId: param.Set(ElementId.InvalidElementId)
                        else:
                            errors.append("Cannot delete parameter type on {0}".format(eid_val))
                            continue
                        modified += 1
                        
                    elif operation in ("Prefix", "Suffix", "Replace"):
                        if st != StorageType.String:
                            errors.append("Operation '{0}' requires a text parameter on {1}".format(operation, eid_val))
                            continue
                        cur = param.AsString() if param.AsString() else ""
                        if operation == "Prefix":
                            param.Set(System.String(val1 + cur))
                        elif operation == "Suffix":
                            param.Set(System.String(cur + val1))
                        elif operation == "Replace":
                            if not val1:
                                errors.append("Empty search string on {0}".format(eid_val))
                                continue
                            param.Set(System.String(cur.replace(val1, val2)))
                        modified += 1
                        
                    elif operation == "Set":
                        try:
                            if st == StorageType.String:
                                param.Set(System.String(val1))
                            elif st == StorageType.Integer:
                                # Handle Yes/No/True/False cleanly
                                val_lower = str(val1).strip().lower()
                                if val_lower in ("yes", "true", "1", "on"):
                                    param.Set(System.Int32(1))
                                elif val_lower in ("no", "false", "0", "off"):
                                    param.Set(System.Int32(0))
                                else:
                                    if not param.SetValueString(System.String(val1)):
                                        param.Set(System.Int32(int(float(val1))))
                            elif st == StorageType.Double:
                                if not param.SetValueString(System.String(val1)):
                                    param.Set(System.Double(float(val1)))
                            elif st == StorageType.ElementId:
                                # Extracts ID from strings like "[413341] Concrete" using regex
                                id_int = None
                                m = re.match(r'^\[(-?\d+)\]', str(val1).strip())
                                if m:
                                    id_int = int(m.group(1))
                                else:
                                    try: id_int = int(float(val1))
                                    except:
                                        errors.append("Requires ID (e.g. [4133] Mat), got '{1}' on {0}".format(eid_val, val1))
                                        continue
                                        
                                try: new_id = ElementId(System.Int64(id_int))
                                except: new_id = ElementId(System.Int32(id_int))
                                param.Set(new_id)
                                
                            else:
                                param.Set(System.String(val1))
                            modified += 1
                        except Exception as ex:
                            errors.append("Set failed on {0}: {1}".format(eid_val, str(ex)))
                    
                    # Mark Type as modified so we don't hit the DB transaction repeatedly
                    if target_elem.Id != elem.Id:
                        target_id_val = getattr(target_elem.Id, "Value", getattr(target_elem.Id, "IntegerValue", -1))
                        processed_types.add(target_id_val)
                        
                except Exception as ex:
                    errors.append("Error on element {0}: {1}".format(eid_val, str(ex)))
            t.Commit()
        except Exception as major_ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            errors.append("Transaction failed & Rolled Back: " + str(major_ex))
            
        return modified, errors

    # ------------------------------------------------------------------
    # UI helpers
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

    def update_element_count():
        try:
            selected_cats = get_selected_categories()
            if not selected_cats:
                live_count.Text = "0 elements"
                return
            scope = "whole" if rb_whole.IsChecked else "view" if rb_view.IsChecked else "selection"
            
            cat_ids = []
            for c in doc.Settings.Categories:
                if c.Name in selected_cats:
                    cat_ids.append(c.Id)
            
            if not cat_ids:
                live_count.Text = "0 elements"
                return
                
            cat_list = List[ElementId]()
            for cid in cat_ids:
                cat_list.Add(cid)
            multi_filter = ElementMulticategoryFilter(cat_list)
            
            if scope == "whole":
                count = FilteredElementCollector(doc).WherePasses(multi_filter).WhereElementIsNotElementType().GetElementCount()
            elif scope == "view":
                view = doc.ActiveView
                count = FilteredElementCollector(doc, view.Id).WherePasses(multi_filter).WhereElementIsNotElementType().GetElementCount()
            else:
                sel_ids = uidoc.Selection.GetElementIds()
                count = 0
                for id in sel_ids:
                    e = doc.GetElement(id)
                    if e and e.Category and e.Category.Name in selected_cats:
                        count += 1
            live_count.Text = str(count) + " elements"
        except Exception:
            live_count.Text = "0 elements"

    def checkbox_toggled(sender, args):
        update_element_count()

    def refresh_category_list():
        category_list.Items.Clear()
        cats = get_categories_by_scope()
        for cat_name in cats:
            item = ListBoxItem()
            chk = CheckBox()
            chk.Content = cat_name
            chk.IsChecked = False
            chk.Checked += checkbox_toggled
            chk.Unchecked += checkbox_toggled
            item.Content = chk
            item.Tag = cat_name
            category_list.Items.Add(item)
        update_element_count()

    def get_selected_categories():
        selected = []
        for item in category_list.Items:
            chk = item.Content
            if chk.IsChecked:
                selected.append(str(chk.Content))
        return selected

    def update_operators_and_values(param_name, elements):
        numeric = False
        for e in elements[:20]:
            try:
                param = e.LookupParameter(param_name)
                if param is None:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te: param = te.LookupParameter(param_name)
                if param:
                    st = param.StorageType
                    if st in (StorageType.Integer, StorageType.Double):
                        numeric = True
                    break
            except:
                continue
                
        filter_op.Items.Clear()
        if numeric:
            ops = ["equals", "does not equal", "is greater than",
                   "is greater than or equal to", "is less than",
                   "is less than or equal to"]
        else:
            ops = ["equals", "does not equal", "contains", "does not contain",
                   "begins with", "does not begin with", "ends with", "does not end with"]
        for op in ops:
            filter_op.Items.Add(op)
        if filter_op.Items.Count > 0:
            filter_op.SelectedIndex = 0
            
        filter_val.Items.Clear()
        for v in get_param_values(elements, param_name):
            filter_val.Items.Add(v)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_scope_changed(sender, args):
        refresh_category_list()
    rb_whole.Checked += on_scope_changed
    rb_view.Checked += on_scope_changed
    rb_selection.Checked += on_scope_changed

    def on_select_all(sender, args):
        for item in category_list.Items:
            chk = item.Content
            chk.IsChecked = True
        update_element_count()
        
    def on_select_none(sender, args):
        for item in category_list.Items:
            chk = item.Content
            chk.IsChecked = False
        update_element_count()
        
    btn_all_cats.Click += on_select_all
    btn_none_cats.Click += on_select_none

    def on_load_params(sender, args):
        cats = get_selected_categories()
        if not cats:
            cat_status.Text = "Please select at least one category."
            return
        cat_status.Text = "Loading parameters..."
        scope = "whole" if rb_whole.IsChecked else "view" if rb_view.IsChecked else "selection"
        elements = get_elements_by_categories(cats, scope)
        if not elements:
            cat_status.Text = "No elements found in selected categories."
            return
            
        state["filtered_elements"] = elements
        state["all_params_cache"] = get_common_params(elements)
        filter_param.Items.Clear()
        for p in state["all_params_cache"]:
            filter_param.Items.Add(p)
        cat_status.Text = "Loaded {0} parameters from {1} elements.".format(len(state["all_params_cache"]), len(elements))
    btn_load_params.Click += on_load_params

    def on_confirm_filter_param(sender, args):
        current_text = filter_param.Text.strip()
        if current_text and state["filtered_elements"] and current_text in state["all_params_cache"]:
            update_operators_and_values(current_text, state["filtered_elements"])
    btn_confirm_param.Click += on_confirm_filter_param
    
    def on_filter_param_selection_changed(sender, args):
        on_confirm_filter_param(sender, args)
    filter_param.SelectionChanged += on_filter_param_selection_changed

    def on_apply_filter(sender, args):
        if not state["filtered_elements"]:
            filter_status.Text = "Please load parameters first."
            return
        param_name = filter_param.Text
        if not param_name:
            filter_status.Text = "Please select a parameter."
            return
            
        operator = str(filter_op.SelectedItem) if filter_op.SelectedItem else "contains"
        value = filter_val.Text
        filter_status.Text = "Applying filter..."
        
        filtered_ids = filter_elements(state["filtered_elements"], param_name, operator, value)
        state["filtered_ids"] = filtered_ids
        
        msg = "Filtered: {0} elements.".format(len(filtered_ids))
        filter_status.Text = msg
        if filtered_ids:
            edit_params = get_common_params(state["filtered_elements"], writable_only=True)
            edit_param.Items.Clear()
            for p in edit_params:
                edit_param.Items.Add(p)
            if edit_params:
                edit_param.SelectedIndex = 0
            btn_select_elems.IsEnabled = True
            edit_status.Text = "Ready to edit {0} elements.".format(len(filtered_ids))
            set_status("{0} elements filtered".format(len(filtered_ids)))
        else:
            edit_param.Items.Clear()
            edit_status.Text = "No elements match the filter."
            btn_select_elems.IsEnabled = False
            filter_status.Text = "No elements match the filter. Try different values."
            set_status("No Matches Filtered", is_error=True)
    btn_apply_filter.Click += on_apply_filter

    def on_select_elements(sender, args):
        if state["filtered_ids"]:
            try:
                net_list = List[ElementId]()
                for eid in state["filtered_ids"]:
                    net_list.Add(eid)
                uidoc.Selection.SetElementIds(net_list)
                set_status("Selected {0} elements in Revit".format(len(state["filtered_ids"])))
            except Exception as ex:
                set_status("Selection failed: " + str(ex), is_error=True)
    btn_select_elems.Click += on_select_elements

    def on_confirm_edit(sender, args):
        current_text = edit_param.Text.strip()
        if current_text and state["filtered_ids"]:
            edit_status.Text = "Ready to edit parameter: " + current_text
            
            # Feature: Auto-Populate known Edit Values so user can select e.g., an existing Material directly!
            try:
                filtered_elems = [doc.GetElement(eid) for eid in state["filtered_ids"] if doc.GetElement(eid)]
                vals = get_param_values(filtered_elems, current_text)
                edit_val1.Items.Clear()
                for v in vals:
                    edit_val1.Items.Add(v)
            except:
                pass
                
    btn_confirm_edit.Click += on_confirm_edit
    edit_param.SelectionChanged += on_confirm_edit

    def on_execute(sender, args):
        if not state["filtered_ids"]:
            edit_status.Text = "Apply filter first."
            return
        if not edit_param.Text:
            edit_status.Text = "Choose a parameter to edit."
            return
            
        param_name = edit_param.Text
        operation = str(edit_op.SelectedItem) if edit_op.SelectedItem else "Set"
        val1 = edit_val1.Text
        val2 = edit_val2.Text
        
        btn_execute.IsEnabled = False
        edit_status.Text = "Modifying..."
        modified, errors = modify_elements(state["filtered_ids"], param_name, operation, val1, val2)
        
        if modified > 0:
            edit_status.Text = "Modified {0} elements.".format(modified)
            if errors:
                edit_status.Text += " ({0} partial errors detected)".format(len(errors))
            set_status("Modified {0} elements".format(modified))
        else:
            err_str = "; ".join(errors[:3]) if errors else "Unknown error"
            edit_status.Text = "No elements modified. Errors: " + err_str
            set_status("No elements modified", is_error=True)
        btn_execute.IsEnabled = True
    btn_execute.Click += on_execute

    # Setup edit operation dropdown
    edit_op.Items.Add("Prefix")
    edit_op.Items.Add("Suffix")
    edit_op.Items.Add("Replace")
    edit_op.Items.Add("Set")
    edit_op.Items.Add("Delete")
    edit_op.SelectedIndex = 3

    def on_close(sender, args):
        # Clear large lists to free up Revit memory instantly
        state["filtered_elements"] = []
        state["filtered_ids"] = []
        state["all_params_cache"] = []
        window.Close()
    btn_close.Click += on_close

    # Initial load
    refresh_category_list()
    set_status("Ready")

    # Show dialog
    window.ShowDialog()

# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    run_ui()
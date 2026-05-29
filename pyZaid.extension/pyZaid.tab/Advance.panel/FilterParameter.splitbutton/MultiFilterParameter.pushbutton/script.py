# -*- coding: utf-8 -*-
# pyRevit script - MultiFilterParameter (Revit only, Python 2.7 compatible)

import sys
import clr
import re

# Add WPF assemblies
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

# Revit API - using pyRevit's built-in access
try:
    from pyrevit import revit, DB, UI
    doc = revit.doc
    uidoc = revit.uidoc
except ImportError:
    # Fallback (should not happen inside pyRevit)
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitUIAPI")
    clr.AddReference("RevitServices")
    from RevitServices.Persistence import DocumentManager
    doc = DocumentManager.Instance.CurrentDBDocument
    uidoc = DocumentManager.Instance.CurrentUIApplication.ActiveUIDocument

from System.Windows.Markup import XamlReader
from System.IO import MemoryStream
from System.Text import Encoding
import System.Windows
from System.Windows.Controls import ListBoxItem, CheckBox
from System.Collections.Generic import List as ListT

# For type hints (no effect at runtime)
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

# ----------------------------------------------------------------------
# XAML definition (Compact Vertical layout, Tabs, modern styling)
# ----------------------------------------------------------------------
XAML = r'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="MultiFilterParameter"
        Height="700" Width="520"
        MinHeight="650" MinWidth="520"
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
        
        <Style x:Key="DangerButton" TargetType="Button">
            <Setter Property="Background" Value="{StaticResource WhiteBrush}" />
            <Setter Property="Foreground" Value="{StaticResource DangerBrush}" />
            <Setter Property="FontSize" Value="13" />
            <Setter Property="FontWeight" Value="Bold" />
            <Setter Property="BorderThickness" Value="1.5" />
            <Setter Property="BorderBrush" Value="{StaticResource DangerBrush}" />
            <Setter Property="Cursor" Value="Hand" />
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border Background="{TemplateBinding Background}" CornerRadius="4" BorderThickness="{TemplateBinding BorderThickness}" BorderBrush="{TemplateBinding BorderBrush}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center" />
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter Property="Background" Value="#FDEDEC" />
                            </Trigger>
                            <Trigger Property="IsPressed" Value="True">
                                <Setter Property="Background" Value="#F5B7B1" />
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

    <Grid Margin="10">
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
                <TextBlock Grid.Column="0" Text="MultiFilterParameter"
                           FontSize="16" FontWeight="Bold" Foreground="White" VerticalAlignment="Center" />
                <TextBlock Grid.Column="2" x:Name="live_count" Text="0 Elements"
                           FontSize="12" Foreground="#BDC3C7" VerticalAlignment="Center" />
            </Grid>
        </Border>

        <!-- TABS -->
        <TabControl x:Name="main_tabs" Grid.Row="1" Background="{StaticResource WhiteBrush}" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1">
            
            <!-- TAB 1: SCOPE & CATEGORIES -->
            <TabItem Header=" 1. Scope &amp; Categories ">
                <Grid Margin="12">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto" />
                        <RowDefinition Height="Auto" />
                        <RowDefinition Height="Auto" />
                        <RowDefinition Height="*" />
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
                </Grid>
            </TabItem>

            <!-- TAB 2: MULTI FILTER -->
            <TabItem Header=" 2. Multi Filter ">
                <ScrollViewer VerticalScrollBarVisibility="Auto">
                    <StackPanel Margin="12">
                        <Label Content="Filter Conditions:" Style="{StaticResource SectionLabel}" Margin="0,0,0,5" />
                        
                        <StackPanel Orientation="Horizontal" Margin="0,0,0,10">
                            <TextBlock Text="Match Type:" FontWeight="SemiBold" VerticalAlignment="Center" Margin="0,0,10,0" Foreground="{StaticResource DarkTextBrush}"/>
                            <RadioButton x:Name="rb_match_all" Content="All (and)" IsChecked="True" Margin="0,0,15,0" Cursor="Hand" VerticalAlignment="Center"/>
                            <RadioButton x:Name="rb_match_any" Content="Any (or)" Cursor="Hand" VerticalAlignment="Center"/>
                        </StackPanel>
                        
                        <!-- Table Headers for Filter -->
                        <Grid Margin="0,0,0,8">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="20" />
                                <ColumnDefinition Width="1.5*" />
                                <ColumnDefinition Width="28" />
                                <ColumnDefinition Width="1.5*" />
                                <ColumnDefinition Width="1.5*" />
                                <ColumnDefinition Width="28" />
                                <ColumnDefinition Width="28" />
                            </Grid.ColumnDefinitions>
                            <TextBlock Grid.Column="0" Text="#" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                            <TextBlock Grid.Column="1" Text="Filter Parameter" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                            <TextBlock Grid.Column="3" Text="Operator" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                            <TextBlock Grid.Column="4" Text="Value" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                        </Grid>
                        
                        <StackPanel x:Name="filter_rows_container" Orientation="Vertical" />

                        <StackPanel Orientation="Vertical" Margin="0,15,0,0">
                            <Button x:Name="btn_apply_filter" Content="Apply Filters →" Style="{StaticResource ActionButton}" Width="140" HorizontalAlignment="Left" ToolTip="Filter elements &amp; proceed to edit" />
                            <TextBlock x:Name="filter_status" Text="Setup conditions, then Apply." Style="{StaticResource StatusText}" Margin="0,5,0,0" TextWrapping="Wrap" />
                        </StackPanel>
                    </StackPanel>
                </ScrollViewer>
            </TabItem>

            <!-- TAB 3: MULTI EDIT -->
            <TabItem Header=" 3. Multi Edit ">
                <ScrollViewer VerticalScrollBarVisibility="Auto">
                    <StackPanel Margin="12">
                        <Label Content="Parameter Modifications:" Style="{StaticResource SectionLabel}" Margin="0,0,0,5" />
                        
                        <!-- Table Headers for Edit -->
                        <Grid Margin="0,0,0,8">
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="20" />
                                <ColumnDefinition Width="1.5*" />
                                <ColumnDefinition Width="1.2*" />
                                <ColumnDefinition Width="1.5*" />
                                <ColumnDefinition Width="1.5*" />
                                <ColumnDefinition Width="28" />
                                <ColumnDefinition Width="28" />
                            </Grid.ColumnDefinitions>
                            <TextBlock Grid.Column="0" Text="#" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                            <TextBlock Grid.Column="1" Text="Edit Parameter" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                            <TextBlock Grid.Column="2" Text="Operation" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                            <TextBlock Grid.Column="3" Text="Value" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                            <TextBlock Grid.Column="4" Text="Replace Value" FontWeight="SemiBold" Foreground="{StaticResource GrayTextBrush}"/>
                        </Grid>

                        <StackPanel x:Name="edit_rows_container" Orientation="Vertical" />

                        <StackPanel Orientation="Vertical" Margin="0,15,0,0">
                            <Button x:Name="btn_execute" Content="Execute Changes" Style="{StaticResource ActionButton}" Width="140" HorizontalAlignment="Left" ToolTip="Apply modifications to filtered elements" />
                            <TextBlock x:Name="edit_status" Text="Apply filters first, then execute." Style="{StaticResource StatusText}" Margin="0,5,0,0" TextWrapping="Wrap" />
                        </StackPanel>
                    </StackPanel>
                </ScrollViewer>
            </TabItem>
        </TabControl>

        <!-- STATUS BAR -->
        <Border Grid.Row="2" Background="#E8E8E8" Padding="10,6" Margin="0,10,0,10" CornerRadius="4">
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
                <TextBlock Grid.Column="2" Text="MultiFilterParameter v1.0 | pyZaid" Style="{StaticResource StatusText}" VerticalAlignment="Center" />
            </Grid>
        </Border>

        <!-- FOOTER BUTTONS -->
        <Border Grid.Row="3" Background="{StaticResource LightBgBrush}">
            <Grid>
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*" />
                    <ColumnDefinition Width="Auto" />
                </Grid.ColumnDefinitions>
                <Button Grid.Column="0" x:Name="btn_select_elems" Content="Select in Revit" Style="{StaticResource SecondaryBtn}" Width="120" HorizontalAlignment="Right" ToolTip="Select filtered elements and close window" IsEnabled="False" />
                <Button Grid.Column="1" x:Name="btn_close" Content="Close" Style="{StaticResource SecondaryBtn}" Width="80" HorizontalAlignment="Right" ToolTip="Close the tool without selecting" Margin="10,0,0,0" />
            </Grid>
        </Border>
    </Grid>
</Window>
'''

# ----------------------------------------------------------------------
# Main UI Logic
# ----------------------------------------------------------------------
def run_ui():
    # Load XAML
    bytes = Encoding.UTF8.GetBytes(XAML)
    stream = MemoryStream(bytes)
    window = XamlReader.Load(stream)

    # UI Element References
    main_tabs         = window.FindName("main_tabs")
    live_count        = window.FindName("live_count")
    category_list     = window.FindName("category_list")
    btn_all_cats      = window.FindName("btn_all_cats")
    btn_none_cats     = window.FindName("btn_none_cats")
    btn_load_params   = window.FindName("btn_load_params")
    
    rb_whole          = window.FindName("rb_whole")
    rb_view           = window.FindName("rb_view")
    rb_selection      = window.FindName("rb_selection")

    rb_match_all      = window.FindName("rb_match_all")
    filter_rows_container = window.FindName("filter_rows_container")
    btn_apply_filter  = window.FindName("btn_apply_filter")
    filter_status     = window.FindName("filter_status")

    edit_rows_container = window.FindName("edit_rows_container")
    btn_execute       = window.FindName("btn_execute")
    edit_status       = window.FindName("edit_status")

    status_badge      = window.FindName("status_badge")
    status_textblock  = window.FindName("status_textblock")
    error_badge       = window.FindName("error_badge")
    error_text        = window.FindName("error_text")
    btn_select_elems  = window.FindName("btn_select_elems")
    btn_close         = window.FindName("btn_close")

    # State Variables
    state = {
        "filtered_ids": [],
        "filtered_elements": [],
        "all_params_cache": [],
        "writable_params_cache": [],
        "val_to_num": {} 
    }
    
    filter_rows = []
    edit_rows = []

    # ------------------------------------------------------------------
    # Helper Functions (Revit API)
    # ------------------------------------------------------------------
    def get_categories_by_scope():
        cats = set()
        try:
            if rb_whole.IsChecked:
                for c in doc.Settings.Categories:
                    if c.CategoryType == CategoryType.Model and c.AllowsBoundParameters:
                        try:
                            f = ElementCategoryFilter(c.Id)
                            if FilteredElementCollector(doc).WherePasses(f).WhereElementIsNotElementType().GetElementCount() > 0:
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
        except Exception:
            return []

    def get_elements_by_categories(category_names, scope):
        if not category_names: return []
        cat_ids = []
        for c in doc.Settings.Categories:
            if c.Name in category_names:
                cat_ids.append(c.Id)
        if not cat_ids: return []
        
        cat_list = ListT[ElementId]()
        for cid in cat_ids: cat_list.Add(cid)
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
            elements = []
            for id in sel_ids:
                e = doc.GetElement(id)
                if e and e.Category and e.Category.Name in category_names:
                    elements.append(e)
            return elements

    def get_common_params(elements, writable_only=False):
        if not elements: return []
        common = None
        for e in elements[:50]:
            cur = set()
            for p in e.Parameters:
                try:
                    if writable_only and p.IsReadOnly: continue
                    cur.add(p.Definition.Name)
                except: continue
            if common is None: common = cur
            else: common = common.intersection(cur)
            if len(common) == 0: break
        return sorted(common) if common else []

    def get_param_values(elements, param_name):
        values = set()
        if param_name not in state["val_to_num"]:
            state["val_to_num"][param_name] = {}
            
        for e in elements:
            try:
                param = e.LookupParameter(param_name)
                if param is None:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te: param = te.LookupParameter(param_name)
                        
                if param is not None:
                    val = param.AsValueString()
                    if val is None:
                        if param.StorageType == StorageType.String: val = param.AsString()
                        elif param.StorageType == StorageType.Integer: val = str(param.AsInteger())
                        elif param.StorageType == StorageType.Double: val = str(param.AsDouble())
                    
                    if val is not None:
                        values.add(val)
                        if param.StorageType == StorageType.Double:
                            state["val_to_num"][param_name][val] = param.AsDouble()
                        elif param.StorageType == StorageType.Integer:
                            state["val_to_num"][param_name][val] = float(param.AsInteger())
            except:
                continue
        return sorted(values)

    def extract_numeric(text):
        if not text: return None
        s = str(text).replace(" ", "")
        last_dot = s.rfind('.')
        last_comma = s.rfind(',')
        if last_comma > last_dot: s = s.replace('.', '').replace(',', '.')
        else: s = s.replace(',', '')
        m = re.search(r'-?\d+(\.\d+)?', s)
        if m:
            try: return float(m.group(0))
            except: pass
        return None

    def evaluate_single_condition(e, param_name, operator, value):
        if value is None: value = ""
        try:
            param = e.LookupParameter(param_name)
            if param is None:
                tid = e.GetTypeId()
                if tid and tid != ElementId.InvalidElementId:
                    te = doc.GetElement(tid)
                    if te: param = te.LookupParameter(param_name)
            if param is None: return False

            cur_val_str = param.AsValueString()
            if cur_val_str is None:
                if param.StorageType == StorageType.String: cur_val_str = param.AsString()
                elif param.StorageType == StorageType.Integer: cur_val_str = str(param.AsInteger())
                elif param.StorageType == StorageType.Double: cur_val_str = str(param.AsDouble())
                else: cur_val_str = ""
            if cur_val_str is None: cur_val_str = ""

            cur_low = cur_val_str.lower()
            val_low = str(value).lower()

            if operator in ("equals", "does not equal", "contains", "does not contain", "begins with", "does not begin with", "ends with", "does not end with"):
                if operator == "equals": return cur_low == val_low
                elif operator == "does not equal": return cur_low != val_low
                elif operator == "contains": return val_low in cur_low
                elif operator == "does not contain": return val_low not in cur_low
                elif operator == "begins with": return cur_low.startswith(val_low)
                elif operator == "does not begin with": return not cur_low.startswith(val_low)
                elif operator == "ends with": return cur_low.endswith(val_low)
                elif operator == "does not end with": return not cur_low.endswith(val_low)
            else:
                st = param.StorageType
                if st not in (StorageType.Integer, StorageType.Double): return False
                cur_num = float(param.AsInteger()) if st == StorageType.Integer else param.AsDouble()
                
                num_val = state["val_to_num"].get(param_name, {}).get(value)
                if num_val is None:
                    c_ext = extract_numeric(cur_val_str)
                    n_ext = extract_numeric(value)
                    if c_ext is not None and n_ext is not None:
                        cur_num, num_val = c_ext, n_ext
                    else:
                        num_val = float(value)
                        
                if operator == "is greater than": return cur_num > num_val
                elif operator == "is greater than or equal to": return cur_num >= num_val
                elif operator == "is less than": return cur_num < num_val
                elif operator == "is less than or equal to": return cur_num <= num_val
        except: pass
        return False

    def apply_single_modification(elem, param_name, operation, val1, val2):
        try:
            param = elem.LookupParameter(param_name)
            if param is None or param.IsReadOnly:
                return False, "Not found or read-only"

            st = param.StorageType
            if operation == "Delete":
                if st == StorageType.String: param.Set("")
                elif st == StorageType.Integer: param.Set(0)
                elif st == StorageType.Double: param.Set(0.0)
                elif st == StorageType.ElementId: param.Set(ElementId.InvalidElementId)
                else: return False, "Cannot delete parameter type"
                return True, None

            if operation in ("Prefix", "Suffix", "Replace"):
                if st != StorageType.String: return False, "Requires text parameter"
                cur = param.AsString() if param.AsString() else ""
                if operation == "Prefix": param.Set(val1 + cur)
                elif operation == "Suffix": param.Set(cur + val1)
                elif operation == "Replace":
                    if not val1: return False, "Empty search string"
                    param.Set(cur.replace(val1, val2))
                return True, None

            if operation == "Set":
                if st == StorageType.String: param.Set(val1)
                elif st == StorageType.Integer:
                    if not param.SetValueString(val1): param.Set(int(float(val1)))
                elif st == StorageType.Double:
                    if not param.SetValueString(val1): param.Set(float(val1))
                elif st == StorageType.ElementId: return False, "Set ElementId not supported"
                else: param.Set(val1)
                return True, None
                
            return False, "Unknown operation"
        except Exception as ex:
            return False, str(ex)

    # ------------------------------------------------------------------
    # Dynamic Row UI Builders
    # ------------------------------------------------------------------
    def update_filter_rows_ui():
        for i, row in enumerate(filter_rows):
            row['lbl'].Text = str(i + 1) + "."
            row['btn_minus'].IsEnabled = len(filter_rows) > 1

    def update_edit_rows_ui():
        for i, row in enumerate(edit_rows):
            row['lbl'].Text = str(i + 1) + "."
            row['btn_minus'].IsEnabled = len(edit_rows) > 1

    def confirm_filter_row(row_dict):
        param_name = row_dict['cb_param'].Text.strip()
        if not param_name or not state["filtered_elements"]: return
        
        numeric = False
        for e in state["filtered_elements"][:20]:
            try:
                param = e.LookupParameter(param_name)
                if not param:
                    tid = e.GetTypeId()
                    if tid and tid != ElementId.InvalidElementId:
                        te = doc.GetElement(tid)
                        if te: param = te.LookupParameter(param_name)
                if param:
                    if param.StorageType in (StorageType.Integer, StorageType.Double): numeric = True
                    break
            except: continue
                
        cb_op = row_dict['cb_op']
        cb_op.Items.Clear()
        ops = ["equals", "does not equal", "is greater than", "is greater than or equal to", "is less than", "is less than or equal to"] if numeric else ["equals", "does not equal", "contains", "does not contain", "begins with", "does not begin with", "ends with", "does not end with"]
        for op in ops: cb_op.Items.Add(op)
        if cb_op.Items.Count > 0: cb_op.SelectedIndex = 0
            
        cb_val = row_dict['cb_val']
        cb_val.Items.Clear()
        for v in get_param_values(state["filtered_elements"], param_name):
            cb_val.Items.Add(v)
            
    def add_filter_row():
        row_dict = {}
        grid = System.Windows.Controls.Grid()
        grid.Margin = System.Windows.Thickness(0, 0, 0, 6)
        
        # Grid Match: 20, 1.5*, 28, 1.5*, 1.5*, 28, 28
        widths = [20, System.Windows.GridLength(1.5, System.Windows.GridUnitType.Star), 28,
                  System.Windows.GridLength(1.5, System.Windows.GridUnitType.Star),
                  System.Windows.GridLength(1.5, System.Windows.GridUnitType.Star), 28, 28]
                  
        for w in widths:
            cd = System.Windows.Controls.ColumnDefinition()
            if isinstance(w, int): cd.Width = System.Windows.GridLength(w)
            else: cd.Width = w
            grid.ColumnDefinitions.Add(cd)

        lbl = System.Windows.Controls.TextBlock()
        lbl.VerticalAlignment = System.Windows.VerticalAlignment.Center
        lbl.FontWeight = System.Windows.FontWeights.SemiBold
        lbl.Foreground = window.FindResource("DarkTextBrush")
        System.Windows.Controls.Grid.SetColumn(lbl, 0)
        grid.Children.Add(lbl)

        cb_param = System.Windows.Controls.ComboBox()
        cb_param.Style = window.FindResource("ControlCombo")
        cb_param.IsEditable = True
        cb_param.Margin = System.Windows.Thickness(0, 0, 4, 0)
        System.Windows.Controls.Grid.SetColumn(cb_param, 1)
        grid.Children.Add(cb_param)

        btn_chk = System.Windows.Controls.Button()
        btn_chk.Content = "↻"
        btn_chk.Style = window.FindResource("ActionButton")
        btn_chk.Width = 24
        btn_chk.Height = 24
        btn_chk.Margin = System.Windows.Thickness(0, 0, 4, 0)
        btn_chk.ToolTip = "Load op & val for this parameter"
        System.Windows.Controls.Grid.SetColumn(btn_chk, 2)
        grid.Children.Add(btn_chk)

        cb_op = System.Windows.Controls.ComboBox()
        cb_op.Style = window.FindResource("ControlCombo")
        cb_op.Margin = System.Windows.Thickness(0, 0, 4, 0)
        System.Windows.Controls.Grid.SetColumn(cb_op, 3)
        grid.Children.Add(cb_op)

        cb_val = System.Windows.Controls.ComboBox()
        cb_val.Style = window.FindResource("ControlCombo")
        cb_val.IsEditable = True
        cb_val.Margin = System.Windows.Thickness(0, 0, 4, 0)
        System.Windows.Controls.Grid.SetColumn(cb_val, 4)
        grid.Children.Add(cb_val)

        btn_plus = System.Windows.Controls.Button()
        btn_plus.Content = "+"
        btn_plus.Style = window.FindResource("SecondaryBtn")
        btn_plus.Width = 24
        btn_plus.Height = 24
        btn_plus.Margin = System.Windows.Thickness(0, 0, 4, 0)
        System.Windows.Controls.Grid.SetColumn(btn_plus, 5)
        grid.Children.Add(btn_plus)

        btn_minus = System.Windows.Controls.Button()
        btn_minus.Content = "-"
        btn_minus.Style = window.FindResource("DangerButton")
        btn_minus.Width = 24
        btn_minus.Height = 24
        System.Windows.Controls.Grid.SetColumn(btn_minus, 6)
        grid.Children.Add(btn_minus)

        row_dict.update({'grid': grid, 'lbl': lbl, 'cb_param': cb_param, 'btn_chk': btn_chk,
                         'cb_op': cb_op, 'cb_val': cb_val, 'btn_plus': btn_plus, 'btn_minus': btn_minus})

        def on_plus(s, a): add_filter_row()
        def on_minus(s, a): remove_filter_row(row_dict)
        def on_confirm(s, a): confirm_filter_row(row_dict)

        btn_plus.Click += on_plus
        btn_minus.Click += on_minus
        btn_chk.Click += on_confirm

        if state["all_params_cache"]:
            for p in state["all_params_cache"]: cb_param.Items.Add(p)

        filter_rows.append(row_dict)
        filter_rows_container.Children.Add(grid)
        update_filter_rows_ui()

    def remove_filter_row(row_dict):
        if len(filter_rows) > 1:
            filter_rows.remove(row_dict)
            filter_rows_container.Children.Remove(row_dict['grid'])
            update_filter_rows_ui()

    def add_edit_row():
        row_dict = {}
        grid = System.Windows.Controls.Grid()
        grid.Margin = System.Windows.Thickness(0, 0, 0, 6)
        
        # Grid Match: 20, 1.5*, 1.2*, 1.5*, 1.5*, 28, 28
        widths = [20, System.Windows.GridLength(1.5, System.Windows.GridUnitType.Star),
                  System.Windows.GridLength(1.2, System.Windows.GridUnitType.Star),
                  System.Windows.GridLength(1.5, System.Windows.GridUnitType.Star),
                  System.Windows.GridLength(1.5, System.Windows.GridUnitType.Star), 28, 28]
                  
        for w in widths:
            cd = System.Windows.Controls.ColumnDefinition()
            if isinstance(w, int): cd.Width = System.Windows.GridLength(w)
            else: cd.Width = w
            grid.ColumnDefinitions.Add(cd)

        lbl = System.Windows.Controls.TextBlock()
        lbl.VerticalAlignment = System.Windows.VerticalAlignment.Center
        lbl.FontWeight = System.Windows.FontWeights.SemiBold
        lbl.Foreground = window.FindResource("DarkTextBrush")
        System.Windows.Controls.Grid.SetColumn(lbl, 0)
        grid.Children.Add(lbl)

        cb_param = System.Windows.Controls.ComboBox()
        cb_param.Style = window.FindResource("ControlCombo")
        cb_param.IsEditable = True
        cb_param.Margin = System.Windows.Thickness(0, 0, 4, 0)
        System.Windows.Controls.Grid.SetColumn(cb_param, 1)
        grid.Children.Add(cb_param)

        cb_op = System.Windows.Controls.ComboBox()
        cb_op.Style = window.FindResource("ControlCombo")
        cb_op.Margin = System.Windows.Thickness(0, 0, 4, 0)
        for op in ["Prefix", "Suffix", "Replace", "Set", "Delete"]: cb_op.Items.Add(op)
        cb_op.SelectedIndex = 3
        System.Windows.Controls.Grid.SetColumn(cb_op, 2)
        grid.Children.Add(cb_op)

        cb_val1 = System.Windows.Controls.ComboBox()
        cb_val1.Style = window.FindResource("ControlCombo")
        cb_val1.IsEditable = True
        cb_val1.Margin = System.Windows.Thickness(0, 0, 4, 0)
        System.Windows.Controls.Grid.SetColumn(cb_val1, 3)
        grid.Children.Add(cb_val1)

        tb_val2 = System.Windows.Controls.TextBox()
        tb_val2.Style = window.FindResource("ControlBox")
        tb_val2.Margin = System.Windows.Thickness(0, 0, 4, 0)
        System.Windows.Controls.Grid.SetColumn(tb_val2, 4)
        grid.Children.Add(tb_val2)

        btn_plus = System.Windows.Controls.Button()
        btn_plus.Content = "+"
        btn_plus.Style = window.FindResource("SecondaryBtn")
        btn_plus.Width = 24
        btn_plus.Height = 24
        btn_plus.Margin = System.Windows.Thickness(0, 0, 4, 0)
        System.Windows.Controls.Grid.SetColumn(btn_plus, 5)
        grid.Children.Add(btn_plus)

        btn_minus = System.Windows.Controls.Button()
        btn_minus.Content = "-"
        btn_minus.Style = window.FindResource("DangerButton")
        btn_minus.Width = 24
        btn_minus.Height = 24
        System.Windows.Controls.Grid.SetColumn(btn_minus, 6)
        grid.Children.Add(btn_minus)

        row_dict.update({'grid': grid, 'lbl': lbl, 'cb_param': cb_param,
                         'cb_op': cb_op, 'cb_val1': cb_val1, 'cb_val2': tb_val2,
                         'btn_plus': btn_plus, 'btn_minus': btn_minus})

        def on_plus(s, a): add_edit_row()
        def on_minus(s, a): remove_edit_row(row_dict)

        btn_plus.Click += on_plus
        btn_minus.Click += on_minus

        if state["writable_params_cache"]:
            for p in state["writable_params_cache"]: cb_param.Items.Add(p)

        edit_rows.append(row_dict)
        edit_rows_container.Children.Add(grid)
        update_edit_rows_ui()

    def remove_edit_row(row_dict):
        if len(edit_rows) > 1:
            edit_rows.remove(row_dict)
            edit_rows_container.Children.Remove(row_dict['grid'])
            update_edit_rows_ui()

    # ------------------------------------------------------------------
    # Standard UI Operations
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
            selected_cats = [item.Content.Content.ToString() for item in category_list.Items if item.Content.IsChecked]
            if not selected_cats:
                live_count.Text = "0 elements"
                return
            scope = "whole" if rb_whole.IsChecked else "view" if rb_view.IsChecked else "selection"
            cat_ids = [c.Id for c in doc.Settings.Categories if c.Name in selected_cats]
            if not cat_ids:
                live_count.Text = "0 elements"
                return
            cat_list = ListT[ElementId]()
            for cid in cat_ids: cat_list.Add(cid)
            multi_filter = ElementMulticategoryFilter(cat_list)
            
            if scope == "whole": count = FilteredElementCollector(doc).WherePasses(multi_filter).WhereElementIsNotElementType().GetElementCount()
            elif scope == "view": count = FilteredElementCollector(doc, doc.ActiveView.Id).WherePasses(multi_filter).WhereElementIsNotElementType().GetElementCount()
            else:
                sel_ids = uidoc.Selection.GetElementIds()
                count = sum(1 for id in sel_ids if doc.GetElement(id) and doc.GetElement(id).Category and doc.GetElement(id).Category.Name in selected_cats)
            live_count.Text = str(count) + " elements"
        except Exception:
            live_count.Text = "0 elements"

    def checkbox_toggled(sender, args): update_element_count()

    def refresh_category_list():
        category_list.Items.Clear()
        for cat_name in get_categories_by_scope():
            item = ListBoxItem()
            chk = CheckBox()
            chk.Content = cat_name
            chk.IsChecked = False
            chk.Checked += checkbox_toggled
            chk.Unchecked += checkbox_toggled
            item.Content = chk
            category_list.Items.Add(item)
        update_element_count()

    # Events Attachments
    def on_scope_changed(s, a): refresh_category_list()
    rb_whole.Checked += on_scope_changed
    rb_view.Checked += on_scope_changed
    rb_selection.Checked += on_scope_changed

    def on_select_all(s, a):
        for item in category_list.Items: item.Content.IsChecked = True
        update_element_count()
        
    def on_select_none(s, a):
        for item in category_list.Items: item.Content.IsChecked = False
        update_element_count()
        
    btn_all_cats.Click += on_select_all
    btn_none_cats.Click += on_select_none

    def on_load_params(s, a):
        cats = [item.Content.Content.ToString() for item in category_list.Items if item.Content.IsChecked]
        if not cats:
            set_status("Please select at least one category", True)
            return
        set_status("Loading parameters...")
        scope = "whole" if rb_whole.IsChecked else "view" if rb_view.IsChecked else "selection"
        elements = get_elements_by_categories(cats, scope)
        if not elements:
            set_status("No elements found in selected categories.", True)
            return
            
        state["filtered_elements"] = elements
        state["all_params_cache"] = get_common_params(elements)
        
        for row in filter_rows:
            row['cb_param'].Items.Clear()
            for p in state["all_params_cache"]: row['cb_param'].Items.Add(p)
            
        set_status("Loaded {0} parameters from {1} elements.".format(len(state["all_params_cache"]), len(elements)))
        # Auto-jump to Filter Tab
        main_tabs.SelectedIndex = 1
    btn_load_params.Click += on_load_params

    def on_apply_filter(s, a):
        if not state["filtered_elements"]:
            filter_status.Text = "Please load parameters from Categories tab first."
            return
            
        filter_status.Text = "Applying multi-filter..."
        match_all = rb_match_all.IsChecked
        passed_elements = []

        for e in state["filtered_elements"]:
            elem_passed = match_all
            active_filters = 0
            
            for row in filter_rows:
                p_name = row['cb_param'].Text.strip()
                if not p_name: continue
                active_filters += 1
                op = str(row['cb_op'].SelectedItem) if row['cb_op'].SelectedItem else "contains"
                val = row['cb_val'].Text
                
                cond = evaluate_single_condition(e, p_name, op, val)
                if match_all:
                    if not cond:
                        elem_passed = False
                        break
                else:
                    if cond:
                        elem_passed = True
                        break
                        
            if not match_all and active_filters == 0:
                elem_passed = True # OR fallback
                
            if elem_passed:
                passed_elements.append(e)

        state["filtered_ids"] = [e.Id for e in passed_elements]
        
        if state["filtered_ids"]:
            filter_status.Text = "Filtered: {0} elements match the criteria.".format(len(passed_elements))
            set_status("{0} elements filtered".format(len(passed_elements)))
            btn_select_elems.IsEnabled = True
            
            state["writable_params_cache"] = get_common_params(passed_elements, writable_only=True)
            for row in edit_rows:
                row['cb_param'].Items.Clear()
                for p in state["writable_params_cache"]: row['cb_param'].Items.Add(p)
            edit_status.Text = "Ready to edit {0} filtered elements.".format(len(passed_elements))
            
            # Auto-jump to Edit Tab
            main_tabs.SelectedIndex = 2
        else:
            filter_status.Text = "No elements match the combination of filters."
            set_status("No Matches Filtered", is_error=True)
            btn_select_elems.IsEnabled = False
    btn_apply_filter.Click += on_apply_filter

    def on_execute(s, a):
        if not state["filtered_ids"]:
            edit_status.Text = "Apply filter first."
            return
            
        btn_execute.IsEnabled = False
        edit_status.Text = "Modifying elements in batch..."
        
        modified_count = 0
        errors = []
        
        t = Transaction(doc, "MultiFilterParameter Batch Edit")
        t.Start()
        try:
            for eid in state["filtered_ids"]:
                elem = doc.GetElement(eid)
                if not elem: continue
                
                elem_modified = False
                for row in edit_rows:
                    p_name = row['cb_param'].Text.strip()
                    if not p_name: continue
                    op = str(row['cb_op'].SelectedItem) if row['cb_op'].SelectedItem else "Set"
                    val1 = row['cb_val1'].Text
                    val2 = row['cb_val2'].Text
                    
                    success, err = apply_single_modification(elem, p_name, op, val1, val2)
                    if success: elem_modified = True
                    if err: errors.append("Element {0}: {1}".format(eid.IntegerValue, err))
                    
                if elem_modified:
                    modified_count += 1
            t.Commit()
        except Exception as ex:
            t.RollBack()
            errors.append("Transaction failed: " + str(ex))

        if modified_count > 0:
            edit_status.Text = "Modified {0} elements successfully.".format(modified_count)
            if errors: edit_status.Text += " ({0} partial errors).".format(len(errors))
            set_status("Modified {0} elements".format(modified_count))
        else:
            err_str = "; ".join(errors[:3]) if errors else "No valid parameters selected."
            edit_status.Text = "No elements modified. " + err_str
            set_status("No elements modified", is_error=True)
            
        btn_execute.IsEnabled = True
        # NOTE: Executing changes intentionally does NOT close the UI (as requested).
    btn_execute.Click += on_execute

    def on_select_elements(s, a):
        if state["filtered_ids"]:
            try:
                uidoc.Selection.SetElementIds(ListT[ElementId](state["filtered_ids"]))
                # Close the window after selecting in Revit
                window.Close()
            except Exception as ex:
                set_status("Selection failed: " + str(ex), True)
    btn_select_elems.Click += on_select_elements

    btn_close.Click += lambda s, a: window.Close()

    # Initial Setup
    refresh_category_list()
    add_filter_row()
    add_edit_row()
    set_status("Ready")

    # Launch Window
    window.ShowDialog()

# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
if __name__ == "__main__":
    run_ui()

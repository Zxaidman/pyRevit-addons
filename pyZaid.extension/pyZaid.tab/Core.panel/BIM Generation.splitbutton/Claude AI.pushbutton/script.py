#! python3
# -*- coding: utf-8 -*-
__title__ = 'BIM Generation [Merged Pro]'
__author__ = 'ZAID'
"""
INP TO BIM  —  pyRevit Push-Button Script
==========================================
Reads FRAME.inp or .txt and creates Structural Columns, Beams, 
and Floors in the active Revit document.

Architecture:
- Front-End: Modern WPF interface via System.Windows with Progress Bar
- Middleware: Robust block-based .INP coordinate parser
- Back-End: Intelligent parameter checking & Transactionally safe 
            element generator.
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

import os, re, math
from collections import OrderedDict
from Autodesk.Revit.DB import (
    FilteredElementCollector, Level, FamilySymbol, FloorType, Floor,
    BuiltInCategory, BuiltInParameter, Line, CurveLoop,
    XYZ, ElementId, Transaction, JoinGeometryUtils
)
from Autodesk.Revit.DB.Structure import StructuralType

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xml')
clr.AddReference('System.Windows.Forms')  # For UI DoEvents

import System
import System.Windows.Forms
from System.Windows import Window, Thickness, HorizontalAlignment, VerticalAlignment, \
    GridLength, GridUnitType, TextWrapping, Visibility, MessageBox
from System.Windows.Controls import (
    Grid, StackPanel, Border, Label, TextBox, Button, ComboBox,
    ComboBoxItem, TextBlock, ScrollViewer, RowDefinition, ColumnDefinition, ProgressBar
)
from System.Windows.Media import (
    SolidColorBrush, Color, LinearGradientBrush, GradientStop,
    FontFamily, Brushes
)
from System.Windows.Media.Effects import DropShadowEffect
from System.Windows.Input import Cursors
from System.Windows.Markup import XamlReader

from pyrevit import script, forms
doc = __revit__.ActiveUIDocument.Document

# ═══════════════════════════════════════════════════════════════════════════
# UNIT HELPERS & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════
def m_to_mm(v):   return int(round(float(v) * 1000.0))
def mm_to_ft(mm): return mm / 304.8
def m_to_ft(m):   return mm_to_ft(m_to_mm(m))
def clean_ft(v):  return mm_to_ft(int(round(float(v) * 304.8)))

TOL_LEVEL        = mm_to_ft(1)
BEAM_Z_TOL_M     = 1.0
BEAM_MAX_DIST_FT = 15.0

def safe_set(param, value):
    if param and not param.IsReadOnly:
        param.Set(value)

def ordinal(n):
    sfx = "TH" if 10 <= n % 100 <= 20 else {1:"ST",2:"ND",3:"RD"}.get(n%10,"TH")
    return "{}{}".format(n, sfx)

def get_num(label):
    m = re.match(r'(\d+)', label or "")
    return int(m.group(1)) if m else 1

def get_element_name(elem):
    try: return elem.Name
    except:
        p = elem.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        return p.AsString() if p and p.HasValue else "Unknown"

def distance_mm(p1, p2):
    dx = p1.X - p2.X
    dy = p1.Y - p2.Y
    dz = p1.Z - p2.Z
    return int(round(math.sqrt(dx*dx + dy*dy + dz*dz) * 1000.0))

# ═══════════════════════════════════════════════════════════════════════════
# INP PARSER LOGIC
# ═══════════════════════════════════════════════════════════════════════════
def _is_coord(s):
    try:
        pts = s.split(',')
        if len(pts) == 3: 
            [float(p) for p in pts]
            return True
    except Exception: 
        pass
    return False

def _is_skip(s):
    return s.startswith('*') or s.startswith('#') or s.startswith('-')

def _parse_section(lines, start_kw, stop_kws):
    idx = 0
    while idx < len(lines) and lines[idx] != start_kw: 
        idx += 1
    idx += 1
    if idx < len(lines):
        try: 
            int(lines[idx])
            idx += 1
        except ValueError: 
            pass
            
    blocks = []
    while idx < len(lines):
        line = lines[idx]
        if line in stop_kws or line.startswith('----------'): 
            break
        if _is_skip(line) or not line or _is_coord(line): 
            idx += 1
            continue
            
        try: 
            float(line)
            idx += 1
            continue
        except ValueError: 
            pass
        
        name = line
        idx += 1
        if idx >= len(lines): 
            break
            
        try: 
            value = float(lines[idx])
            idx += 1
        except (ValueError, IndexError): 
            continue
        
        pts = []
        while idx < len(lines) and len(pts) < 4:
            cl = lines[idx]
            if _is_coord(cl):
                x, y, z = [float(v) for v in cl.split(',')]
                pts.append((x, y, z))
                idx += 1
            elif _is_skip(cl) or not cl: 
                idx += 1
            else: 
                break
                
        while idx < len(lines) and _is_skip(lines[idx]): 
            idx += 1
            
        if len(pts) == 4: 
            blocks.append((name, value, pts))
            
    return blocks

def load_inp(file_path):
    with open(file_path, 'r') as f:
        lines = [l.strip() for l in f if l.strip()]
        
    col_raw  = _parse_section(lines, 'Columns', ['Beams', 'Slabs', 'Walls'])
    beam_raw = _parse_section(lines, 'Beams',   ['Slabs', 'Walls'])
    slab_raw = _parse_section(lines, 'Slabs',   ['Walls'])
    
    col_data  = [(n, pts[0][2], pts[0][2] + abs(h), pts) for n, h, pts in col_raw]
    beam_data = [(n, top, pts) for n, top, pts in beam_raw]
    slab_data = [(n, top, min(p[2] for p in pts), pts) for n, top, pts in slab_raw]
    
    return col_data, beam_data, slab_data

def build_level_name_map(z_values, prefix, start_label, suffix, sep):
    ordered  = sorted(z_values)
    base_num = get_num(start_label)
    
    if prefix.isdigit(): 
        prefix_num = int(prefix)
        pad = len(prefix)
    else: 
        prefix_num = None
        pad = 0
    
    result = {}
    for i, z in enumerate(ordered):
        curr  = str(prefix_num + i).zfill(pad) if prefix_num is not None else prefix
        parts = [p for p in [curr, ordinal(base_num + i), suffix] if p]
        result[z] = sep.join(parts)
        
    return result

# ═══════════════════════════════════════════════════════════════════════════
# UI DESIGN SYSTEM
# ═══════════════════════════════════════════════════════════════════════════
def rgb(r, g, b): return SolidColorBrush(Color.FromRgb(r, g, b))
def rgba(r, g, b, a): return SolidColorBrush(Color.FromArgb(a, r, g, b))

C_BG        = Color.FromRgb(13,  17,  30)
C_SURFACE   = Color.FromRgb(22,  28,  46)
C_BORDER    = Color.FromRgb(40,  50,  80)
C_ACCENT    = Color.FromRgb(32, 200, 170)
C_ACCENT2   = Color.FromRgb(20, 150, 200)
C_TEXT      = Color.FromRgb(230, 235, 245)
C_MUTED     = Color.FromRgb(120, 135, 165)
C_INPUT_BG  = Color.FromRgb(18,  23,  40)
C_HOVER     = Color.FromRgb(45,  220, 185)
C_ERROR     = Color.FromRgb(255,  80,  80)

def brush(c): return SolidColorBrush(c)

def accent_gradient():
    g = LinearGradientBrush()
    g.StartPoint = System.Windows.Point(0, 0)
    g.EndPoint   = System.Windows.Point(1, 0)
    gs1 = GradientStop(); gs1.Color = C_ACCENT; gs1.Offset = 0.0
    gs2 = GradientStop(); gs2.Color = C_ACCENT2; gs2.Offset = 1.0
    g.GradientStops.Add(gs1)
    g.GradientStops.Add(gs2)
    return g

def shadow(blur=18, opacity=0.5, depth=4):
    e = DropShadowEffect()
    e.BlurRadius, e.Opacity, e.ShadowDepth = blur, opacity, depth
    e.Color = Color.FromRgb(0, 0, 0)
    return e

def accent_shadow():
    e = DropShadowEffect()
    e.BlurRadius, e.Opacity, e.ShadowDepth, e.Color = 16, 0.6, 0, C_ACCENT
    return e

def make_label(text, size=11, bold=False, muted=False):
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = size
    tb.FontFamily = FontFamily("Segoe UI")
    tb.Foreground = brush(C_MUTED) if muted else brush(C_TEXT)
    if bold: tb.FontWeight = System.Windows.FontWeights.SemiBold
    tb.Margin = Thickness(0, 0, 0, 4)
    return tb

def make_input(default="", width=None):
    tb = TextBox()
    tb.Text = default
    tb.Background = brush(C_INPUT_BG)
    tb.Foreground = brush(C_TEXT)
    tb.BorderBrush = brush(C_BORDER)
    tb.BorderThickness = Thickness(1)
    tb.Padding = Thickness(10, 8, 10, 8)
    tb.FontSize = 12
    tb.FontFamily = FontFamily("Segoe UI")
    tb.CaretBrush = brush(C_ACCENT)
    if width: tb.Width = width
        
    def on_focus(s, e): 
        s.BorderBrush = brush(C_ACCENT)
        s.Effect = accent_shadow()
    def on_blur(s, e):  
        s.BorderBrush = brush(C_BORDER)
        s.Effect = None
        
    tb.GotFocus += on_focus
    tb.LostFocus += on_blur
    return tb

def make_combo(items, selected_idx=0):
    INPUT_BG, SURFACE, TEXT, MUTED, ACCENT, BORDER, BG, HOVER_BG = (
        "FF12172A", "FF161C2E", "FFE6EBF5", "FF788BA5", "FF20C8AA", "FF283250", "FF0D111E", "4020C8AA")

    xaml = """
    <ComboBox xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        FontSize="12" FontFamily="Segoe UI" Foreground="#{TEXT}" Background="#{INPUT_BG}" BorderBrush="#{BORDER}"
        BorderThickness="1" Padding="10,8,8,8" Height="36" VerticalContentAlignment="Center">
      <ComboBox.Resources>
        <Style TargetType="ComboBoxItem">
          <Setter Property="Foreground" Value="#{TEXT}"/><Setter Property="Background" Value="#{SURFACE}"/>
          <Setter Property="BorderThickness" Value="0"/><Setter Property="Padding" Value="10,7,10,7"/>
          <Setter Property="Template">
            <Setter.Value><ControlTemplate TargetType="ComboBoxItem">
                <Border x:Name="Bd" Background="{{TemplateBinding Background}}" Padding="{{TemplateBinding Padding}}">
                  <ContentPresenter VerticalAlignment="Center"/>
                </Border>
                <ControlTemplate.Triggers>
                  <Trigger Property="IsHighlighted" Value="True"><Setter TargetName="Bd" Property="Background" Value="#{HOVER_BG}"/><Setter Property="Foreground" Value="#{ACCENT}"/></Trigger>
                  <Trigger Property="IsSelected" Value="True"><Setter TargetName="Bd" Property="Background" Value="#{HOVER_BG}"/><Setter Property="Foreground" Value="#{ACCENT}"/></Trigger>
                </ControlTemplate.Triggers>
              </ControlTemplate></Setter.Value></Setter>
        </Style>
      </ComboBox.Resources>
      <ComboBox.Template>
        <ControlTemplate TargetType="ComboBox">
          <Grid>
            <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="28"/></Grid.ColumnDefinitions>
            <Border Grid.ColumnSpan="2" x:Name="MainBorder" Background="#{INPUT_BG}" BorderBrush="#{BORDER}" BorderThickness="1" CornerRadius="4"/>
            <ContentPresenter Grid.Column="0" Content="{{TemplateBinding SelectionBoxItem}}" Margin="10,0,0,0" VerticalAlignment="Center" IsHitTestVisible="False" TextBlock.Foreground="#{TEXT}" TextBlock.FontSize="12"/>
            <ToggleButton Grid.ColumnSpan="2" Focusable="False" IsChecked="{{Binding Path=IsDropDownOpen, Mode=TwoWay, RelativeSource={{RelativeSource TemplatedParent}}}}" ClickMode="Press" Background="Transparent" BorderThickness="0"/>
            <Path Grid.Column="1" x:Name="Arrow" HorizontalAlignment="Center" VerticalAlignment="Center" Data="M 0 0 L 5 5 L 10 0 Z" Fill="#{ACCENT}" IsHitTestVisible="False"/>
            <Popup x:Name="Popup" Placement="Bottom" IsOpen="{{TemplateBinding IsDropDownOpen}}" AllowsTransparency="True" Focusable="False" PopupAnimation="Slide">
              <Grid MinWidth="{{TemplateBinding ActualWidth}}" MaxHeight="{{TemplateBinding MaxDropDownHeight}}">
                <Border Background="#{SURFACE}" BorderBrush="#{ACCENT}" BorderThickness="1" CornerRadius="0,0,4,4"/>
                <ScrollViewer Margin="1" Background="#{SURFACE}"><StackPanel IsItemsHost="True"/></ScrollViewer>
              </Grid>
            </Popup>
          </Grid>
          <ControlTemplate.Triggers>
            <Trigger Property="IsDropDownOpen" Value="True"><Setter TargetName="MainBorder" Property="BorderBrush" Value="#{ACCENT}"/><Setter TargetName="Arrow" Property="Fill" Value="#{TEXT}"/></Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </ComboBox.Template>
    </ComboBox>
    """.format(INPUT_BG=INPUT_BG, SURFACE=SURFACE, TEXT=TEXT, MUTED=MUTED, ACCENT=ACCENT, BORDER=BORDER, BG=BG, HOVER_BG=HOVER_BG)
    
    cb = XamlReader.Parse(xaml)
    for item in items:
        cbi = ComboBoxItem()
        cbi.Content = item
        cb.Items.Add(cbi)
    if items and selected_idx < len(items): 
        cb.SelectedIndex = selected_idx
    return cb

def card(content_panel, margin=Thickness(0, 0, 0, 12)):
    b = Border()
    b.Background = brush(C_SURFACE)
    b.BorderBrush = brush(C_BORDER)
    b.BorderThickness = Thickness(1)
    b.CornerRadius = System.Windows.CornerRadius(8)
    b.Padding = Thickness(16, 14, 16, 14)
    b.Margin = margin
    b.Effect = shadow(12, 0.4, 2)
    b.Child = content_panel
    return b

def section_header(text):
    sp = StackPanel()
    sp.Orientation = System.Windows.Controls.Orientation.Horizontal
    sp.Margin = Thickness(0, 0, 0, 8)
    
    bar = Border()
    bar.Width, bar.Background, bar.CornerRadius, bar.Margin = 3, accent_gradient(), System.Windows.CornerRadius(2), Thickness(0, 2, 10, 2)
    sp.Children.Add(bar)
    
    tb = TextBlock()
    tb.Text = text
    tb.FontSize = 11
    tb.FontFamily = FontFamily("Segoe UI")
    tb.FontWeight = System.Windows.FontWeights.SemiBold
    tb.Foreground = brush(C_ACCENT)
    tb.VerticalAlignment = VerticalAlignment.Center
    
    sp.Children.Add(tb)
    return sp

# ═══════════════════════════════════════════════════════════════════════════
# FAMILY LOADERS
# ═══════════════════════════════════════════════════════════════════════════
def get_col_symbols():
    syms = list(FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralColumns))
    return OrderedDict([("{} : {}".format(doc.GetElement(s.Family.Id).Name, get_element_name(s)), s) for s in sorted(syms, key=lambda x: get_element_name(x))])

def get_beam_symbols():
    syms = list(FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralFraming))
    return OrderedDict([("{} : {}".format(doc.GetElement(s.Family.Id).Name, get_element_name(s)), s) for s in sorted(syms, key=lambda x: get_element_name(x))])

def get_floor_types():
    ftypes = list(FilteredElementCollector(doc).OfClass(FloorType))
    return OrderedDict([(get_element_name(ft), ft) for ft in sorted(ftypes, key=lambda x: get_element_name(x))])

col_symbols  = get_col_symbols()
beam_symbols = get_beam_symbols()
floor_types  = get_floor_types()

if not col_symbols: 
    MessageBox.Show("No Structural Column families loaded.", "INP to BIM")
    script.exit()
if not beam_symbols: 
    MessageBox.Show("No Structural Framing families loaded.", "INP to BIM")
    script.exit()
if not floor_types: 
    MessageBox.Show("No Floor Types loaded.", "INP to BIM")
    script.exit()

# ═══════════════════════════════════════════════════════════════════════════
# INTELLIGENT MATCHING & SLAB LOGIC
# ═══════════════════════════════════════════════════════════════════════════
def get_param_val(sym, param_names):
    for pn in param_names:
        p = sym.LookupParameter(pn)
        if p and p.HasValue: 
            return p.AsDouble()
    return None

def get_element_type(base_symbol, w_mm, d_mm):
    """ Intelligently finds matching size inside the project OR creates a new one. """
    w_ft = clean_ft(mm_to_ft(w_mm))
    d_ft = clean_ft(mm_to_ft(d_mm))
    family = base_symbol.Family
    
    # 1. Search for existing symbols in the same family that match dimensions
    for symbol_id in family.GetFamilySymbolIds():
        sym = doc.GetElement(symbol_id)
        val_b = get_param_val(sym, ["b", "Width"])
        val_h = get_param_val(sym, ["h", "Depth", "d"])
        
        if val_b is not None and val_h is not None:
            if abs(val_b - w_ft) < 0.001 and abs(val_h - d_ft) < 0.001:
                if not sym.IsActive: sym.Activate()
                return sym
                
    # 2. Not found -> Duplicate
    nm = "{}x{}mm".format(w_mm, d_mm)
    try: 
        nt = base_symbol.Duplicate(nm)
        for pn in ["b", "Width"]:
            p = nt.LookupParameter(pn)
            if p and not p.IsReadOnly: p.Set(w_ft)
        for pn in ["h", "Depth", "d"]:
            p = nt.LookupParameter(pn)
            if p and not p.IsReadOnly: p.Set(d_ft)
        return nt
    except Exception: 
        # Fallback if the name was occupied but mismatched dimensions
        for symbol_id in family.GetFamilySymbolIds():
            sym = doc.GetElement(symbol_id)
            if get_element_name(sym) == nm: 
                return sym
        return base_symbol

def get_floor_type(base_type, thickness_mm):
    """ Intelligently finds a floor type matching exact thickness OR creates one. """
    thick_ft = mm_to_ft(thickness_mm)
    nm = "{}mm RCC SLAB".format(int(round(thickness_mm)))
    
    # 1. Search for existing type matching exact thickness
    for ft in FilteredElementCollector(doc).OfClass(FloorType):
        try:
            comp = ft.GetCompoundStructure()
            if comp:
                total_w = sum(l.Width for l in comp.GetLayers())
                if abs(total_w - thick_ft) < 0.001:
                    return ft
        except: 
            pass
            
    # 2. Not found -> Duplicate
    try: 
        nft = base_type.Duplicate(nm)
        comp = nft.GetCompoundStructure()
        if comp and not comp.IsVerticallyCompound:
            layers = list(comp.GetLayers())
            for i, layer in enumerate(layers): 
                layer.Width = thick_ft if i == 0 else 0.0
            comp.SetLayers(layers)
            nft.SetCompoundStructure(comp)
        return nft
    except Exception: 
        for ft in FilteredElementCollector(doc).OfClass(FloorType):
            if get_element_name(ft) == nm: return ft
        return base_type

def get_beam_width_ft(beam):
    for pn in ["b", "Width"]:
        p = beam.Symbol.LookupParameter(pn)
        if p and p.HasValue: 
            return p.AsDouble()
    p = beam.Symbol.get_Parameter(BuiltInParameter.STRUCTURAL_SECTION_COMMON_WIDTH)
    if p and p.HasValue: 
        return p.AsDouble()
    bb = beam.get_BoundingBox(None)
    if bb: 
        return min(abs(bb.Max.X - bb.Min.X), abs(bb.Max.Y - bb.Min.Y))
    return None

def get_beam_offset_for_edge(p_start, p_end, is_horiz, z_ft):
    best_dist, best_hw = float('inf'), 0.0
    for bm in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType():
        try:
            loc = bm.Location
            if not hasattr(loc, "Curve"): continue
            c = loc.Curve
            bs, be = c.GetEndPoint(0), c.GetEndPoint(1)
            
            if abs((bs.Z + be.Z) / 2 - z_ft) > BEAM_Z_TOL_M * 3.28084: continue
            bh = abs(bs.Y - be.Y) < abs(bs.X - be.X)
            if bh != is_horiz: continue
                
            if is_horiz:
                if max(bs.X,be.X) < min(p_start.X,p_end.X) or min(bs.X,be.X) > max(p_start.X,p_end.X): continue
                dist = abs(bs.Y - p_start.Y)
            else:
                if max(bs.Y,be.Y) < min(p_start.Y,p_end.Y) or min(bs.Y,be.Y) > max(p_start.Y,p_end.Y): continue
                dist = abs(bs.X - p_start.X)
                
            if dist > BEAM_MAX_DIST_FT: continue
            w = get_beam_width_ft(bm)
            if w and dist < best_dist: 
                best_dist, best_hw = dist, w / 2.0
        except Exception: pass
    return best_hw

def offset_rectangle(pts_m, slab_top_ft):
    xs = [m_to_ft(p[0]) for p in pts_m]
    ys = [m_to_ft(p[1]) for p in pts_m]
    xmin, xmax, ymin, ymax, zv = min(xs), max(xs), min(ys), max(ys), slab_top_ft
    
    ol  = get_beam_offset_for_edge(XYZ(xmin,ymin,zv), XYZ(xmin,ymax,zv), False, zv)
    or_ = get_beam_offset_for_edge(XYZ(xmax,ymin,zv), XYZ(xmax,ymax,zv), False, zv)
    ob  = get_beam_offset_for_edge(XYZ(xmin,ymin,zv), XYZ(xmax,ymin,zv), True,  zv)
    ot  = get_beam_offset_for_edge(XYZ(xmin,ymax,zv), XYZ(xmax,ymax,zv), True,  zv)
    
    xmin += ol
    xmax -= or_
    ymin += ob
    ymax -= ot
    
    if xmin >= xmax or ymin >= ymax: return None
    return [XYZ(xmin,ymin,zv), XYZ(xmax,ymin,zv), XYZ(xmax,ymax,zv), XYZ(xmin,ymax,zv)]

# ═══════════════════════════════════════════════════════════════════════════
# MAIN DIALOG INTERFACE WITH LIVE EXECUTION
# ═══════════════════════════════════════════════════════════════════════════
class InpToBimDialog(Window):
    def __init__(self):
        self._build_ui()

    def _build_ui(self):
        self.Title = "INP to BIM Generator"
        self.Width = 520
        self.SizeToContent = System.Windows.SizeToContent.Height
        self.ResizeMode = System.Windows.ResizeMode.NoResize
        self.WindowStartupLocation = System.Windows.WindowStartupLocation.CenterScreen
        self.Background = brush(C_BG)
        self.FontFamily = FontFamily("Segoe UI")

        scroll = ScrollViewer()
        scroll.VerticalScrollBarVisibility = System.Windows.Controls.ScrollBarVisibility.Auto
        
        outer = StackPanel()
        outer.Margin = Thickness(24, 24, 24, 20)
        scroll.Content = outer
        self.Content = scroll

        # ── HEADER ──
        header = StackPanel()
        header.Margin = Thickness(0, 0, 0, 20)
        
        logo_row = StackPanel()
        logo_row.Orientation = System.Windows.Controls.Orientation.Horizontal
        logo_row.Margin = Thickness(0, 0, 0, 6)
        
        icon_border = Border()
        icon_border.Width = 36
        icon_border.Height = 36
        icon_border.CornerRadius = System.Windows.CornerRadius(8)
        icon_border.Background = accent_gradient()
        icon_border.Margin = Thickness(0, 0, 12, 0)
        icon_border.Effect = accent_shadow()
        
        icon_tb = TextBlock()
        icon_tb.Text = "B"
        icon_tb.FontSize = 18
        icon_tb.FontWeight = System.Windows.FontWeights.Bold
        icon_tb.Foreground = brush(Color.FromRgb(13, 17, 30))
        icon_tb.HorizontalAlignment = HorizontalAlignment.Center
        icon_tb.VerticalAlignment = VerticalAlignment.Center
        
        icon_border.Child = icon_tb
        logo_row.Children.Add(icon_border)

        title_stack = StackPanel()
        title_stack.VerticalAlignment = VerticalAlignment.Center
        
        t1 = TextBlock()
        t1.Text = "INP to BIM"
        t1.FontSize = 18
        t1.FontWeight = System.Windows.FontWeights.Bold
        t1.Foreground = brush(C_TEXT)
        
        t2 = TextBlock()
        t2.Text = "PLANWIN / FRAMEWIN structural import"
        t2.FontSize = 10
        t2.Foreground = brush(C_MUTED)
        t2.Margin = Thickness(0, 2, 0, 0)
        
        title_stack.Children.Add(t1)
        title_stack.Children.Add(t2)
        logo_row.Children.Add(title_stack)
        header.Children.Add(logo_row)

        accent_line = Border()
        accent_line.Height = 2
        accent_line.Background = accent_gradient()
        accent_line.Opacity = 0.5
        header.Children.Add(accent_line)
        outer.Children.Add(header)

        # ── 1: FILE ──
        file_panel = StackPanel()
        file_panel.Children.Add(section_header("INPUT FILE"))
        
        file_row = Grid()
        c0 = ColumnDefinition()
        c0.Width = GridLength(1, GridUnitType.Star)
        c1 = ColumnDefinition()
        c1.Width = GridLength.Auto
        file_row.ColumnDefinitions.Add(c0)
        file_row.ColumnDefinitions.Add(c1)

        self.tb_file = make_input("(no file selected)")
        self.tb_file.IsReadOnly = True
        self.tb_file.Foreground = brush(C_MUTED)
        Grid.SetColumn(self.tb_file, 0)
        file_row.Children.Add(self.tb_file)

        btn_browse = self._make_outline_button("  Browse…  ")
        btn_browse.Margin = Thickness(8, 0, 0, 0)
        btn_browse.Click += self._browse  
        Grid.SetColumn(btn_browse, 1)
        file_row.Children.Add(btn_browse)
        
        file_panel.Children.Add(file_row)
        outer.Children.Add(card(file_panel))

        # ── 2: LEVEL NAMING ──
        lvl_panel = StackPanel()
        lvl_panel.Children.Add(section_header("LEVEL NAMING"))
        
        hint = TextBlock()
        hint.Text = "Levels will be named: prefix + ordinal + suffix joined by separator."
        hint.FontSize = 10
        hint.Foreground = brush(C_MUTED)
        hint.TextWrapping = TextWrapping.Wrap
        hint.Margin = Thickness(0, 0, 0, 10)
        lvl_panel.Children.Add(hint)

        lvl_grid = Grid()
        for _ in range(4):
            cd = ColumnDefinition()
            cd.Width = GridLength(1, GridUnitType.Star)
            lvl_grid.ColumnDefinitions.Add(cd)
            
        lvl_grid.RowDefinitions.Add(RowDefinition())
        lvl_grid.RowDefinitions.Add(RowDefinition())

        fields = [("Prefix", "00"), ("Floor name", "0TH"), ("Suffix", "LVL."), ("Separator", " ")]
        self.lvl_inputs = []
        
        for col_i, (lbl, default) in enumerate(fields):
            sp = StackPanel()
            sp.Margin = Thickness(0 if col_i==0 else 8, 0, 0, 0)
            sp.Children.Add(make_label(lbl, muted=True))
            
            inp = make_input(default)
            sp.Children.Add(inp)
            self.lvl_inputs.append(inp)
            
            Grid.SetColumn(sp, col_i)
            Grid.SetRow(sp, 0)
            lvl_grid.Children.Add(sp)
            
        lvl_panel.Children.Add(lvl_grid)

        self.lbl_preview = TextBlock()
        self.lbl_preview.Text = "Preview: 00 1ST LVL. → 01 2ND LVL. → …"
        self.lbl_preview.FontSize = 10
        self.lbl_preview.Foreground = brush(C_ACCENT)
        self.lbl_preview.Margin = Thickness(0, 10, 0, 0)
        lvl_panel.Children.Add(self.lbl_preview)
        
        for inp in self.lvl_inputs: 
            inp.TextChanged += self._update_preview 
            
        outer.Children.Add(card(lvl_panel))

        # ── 3: FAMILY TYPES ──
        fam_panel = StackPanel()
        fam_panel.Children.Add(section_header("FAMILY TYPES"))
        
        fam_grid = Grid()
        fam_grid.RowDefinitions.Add(RowDefinition())
        fam_grid.RowDefinitions.Add(RowDefinition())
        fam_grid.RowDefinitions.Add(RowDefinition())
        
        for r in range(3): 
            fam_grid.RowDefinitions[r].Height = GridLength.Auto

        labels_combos = [
            ("Structural Column", list(col_symbols.keys())), 
            ("Structural Framing", list(beam_symbols.keys())), 
            ("Floor Type", list(floor_types.keys()))
        ]
        
        self.combos = []
        for row_i, (lbl, items) in enumerate(labels_combos):
            sp = StackPanel()
            sp.Margin = Thickness(0, 0 if row_i==0 else 10, 0, 0)
            sp.Children.Add(make_label(lbl, muted=True))
            
            cb = make_combo(items)
            sp.Children.Add(cb)
            self.combos.append(cb)
            
            Grid.SetRow(sp, row_i)
            fam_grid.Children.Add(sp)
            
        fam_panel.Children.Add(fam_grid)
        outer.Children.Add(card(fam_panel))

        # ── 4: PROGRESS & STATUS BAR ──
        self.status_panel = StackPanel()
        self.status_panel.Margin = Thickness(0, 4, 0, 12)
        self.status_panel.Visibility = Visibility.Collapsed
        
        self.status_text = TextBlock()
        self.status_text.Text = "Preparing generation..."
        self.status_text.FontSize = 11
        self.status_text.FontFamily = FontFamily("Segoe UI")
        self.status_text.Foreground = brush(C_ACCENT)
        self.status_text.Margin = Thickness(0, 0, 0, 6)
        
        self.progress_bar = ProgressBar()
        self.progress_bar.Height = 6
        self.progress_bar.Minimum = 0
        self.progress_bar.Maximum = 100
        self.progress_bar.Foreground = accent_gradient()
        self.progress_bar.Background = brush(C_INPUT_BG)
        self.progress_bar.BorderThickness = Thickness(0)
        
        self.status_panel.Children.Add(self.status_text)
        self.status_panel.Children.Add(self.progress_bar)
        outer.Children.Add(self.status_panel)

        # ── FOOTER ──
        btn_row = StackPanel()
        btn_row.Orientation = System.Windows.Controls.Orientation.Horizontal
        btn_row.HorizontalAlignment = HorizontalAlignment.Right
        btn_row.Margin = Thickness(0, 8, 0, 4)
        
        self.btn_cancel = self._make_outline_button("Cancel")
        self.btn_cancel.Width = 100
        self.btn_cancel.Margin = Thickness(0, 0, 10, 0)
        self.btn_cancel.Click += self._cancel  
        btn_row.Children.Add(self.btn_cancel)
        
        self.btn_run = self._make_primary_button("▶  Run")
        self.btn_run.Width = 120
        self.btn_run.Click += self._run  
        btn_row.Children.Add(self.btn_run)
        
        outer.Children.Add(btn_row)

        ver = TextBlock()
        ver.Text = "INP to BIM Pro · pyRevit"
        ver.FontSize = 9
        ver.Foreground = brush(C_MUTED)
        ver.Opacity = 0.5
        ver.HorizontalAlignment = HorizontalAlignment.Right
        ver.Margin = Thickness(0, 4, 0, 0)
        outer.Children.Add(ver)

    def _make_primary_button(self, text):
        b = Button()
        b.Content = text
        b.Background = accent_gradient()
        b.Foreground = brush(Color.FromRgb(10, 14, 26))
        b.BorderThickness = Thickness(0)
        b.Padding = Thickness(16, 9, 16, 9)
        b.FontSize = 12
        b.FontWeight = System.Windows.FontWeights.SemiBold
        b.FontFamily = FontFamily("Segoe UI")
        b.Cursor = Cursors.Hand
        b.Effect = accent_shadow()
        
        def enter(s, e): s.Opacity = 0.85
        def leave(s, e): s.Opacity = 1.0
        b.MouseEnter += enter
        b.MouseLeave += leave
        return b

    def _make_outline_button(self, text):
        b = Button()
        b.Content = text
        b.Background = brush(C_SURFACE)
        b.Foreground = brush(C_ACCENT)
        b.BorderBrush = brush(C_ACCENT)
        b.BorderThickness = Thickness(1)
        b.Padding = Thickness(14, 8, 14, 8)
        b.FontSize = 12
        b.FontFamily = FontFamily("Segoe UI")
        b.Cursor = Cursors.Hand
        
        def enter(s, e): 
            s.BorderBrush = brush(C_HOVER)
            s.Foreground = brush(C_HOVER)
        def leave(s, e): 
            s.BorderBrush = brush(C_ACCENT)
            s.Foreground = brush(C_ACCENT)
            
        b.MouseEnter += enter
        b.MouseLeave += leave
        return b

    def update_progress(self, percent, message):
        """ Update UI and forcefully flush the WPF event pump so window doesn't freeze """
        self.progress_bar.Value = percent
        self.status_text.Text = message
        System.Windows.Forms.Application.DoEvents()

    def _browse(self, sender, args):
        dlg = System.Windows.Forms.OpenFileDialog()
        dlg.Title  = "Select FRAME File"
        dlg.Filter = "INP/TXT files (*.inp;*.txt)|*.inp;*.txt|All files (*.*)|*.*"
        if dlg.ShowDialog() == System.Windows.Forms.DialogResult.OK:
            self.tb_file.Text = dlg.FileName
            self.tb_file.Foreground = brush(C_TEXT)

    def _update_preview(self, sender, args):
        try:
            pfx = self.lvl_inputs[0].Text.strip()
            name = self.lvl_inputs[1].Text.strip()
            sfx = self.lvl_inputs[2].Text.strip()
            sep = self.lvl_inputs[3].Text
            
            num = get_num(name)
            p0 = str(int(pfx)).zfill(len(pfx)) if pfx.isdigit() else pfx
            p1 = str(int(pfx)+1).zfill(len(pfx)) if pfx.isdigit() else pfx
            
            def fmt(p, n): 
                return sep.join([x for x in [p, n, sfx] if x])
                
            self.lbl_preview.Text = "Preview:  {}  →  {}  → …".format(fmt(p0, ordinal(num)), fmt(p1, ordinal(num+1)))
        except: 
            self.lbl_preview.Text = ""

    def _cancel(self, sender, args): 
        self.Close()

    def _run(self, sender, args):
        path = self.tb_file.Text.strip()
        if not path or not os.path.exists(path):
            self.tb_file.BorderBrush = brush(C_ERROR)
            return
            
        # Freeze UI elements for safe execution
        self.btn_run.Visibility = Visibility.Collapsed
        self.btn_cancel.IsEnabled = False
        self.status_panel.Visibility = Visibility.Visible
        
        try:
            # Gather Configuration
            col_symbol  = col_symbols[list(col_symbols.keys())[self.combos[0].SelectedIndex]]
            beam_symbol = beam_symbols[list(beam_symbols.keys())[self.combos[1].SelectedIndex]]
            floor_type  = floor_types[list(floor_types.keys())[self.combos[2].SelectedIndex]]
            prefix      = self.lvl_inputs[0].Text.strip()
            start_label = self.lvl_inputs[1].Text.strip()
            suffix      = self.lvl_inputs[2].Text.strip()
            sep         = self.lvl_inputs[3].Text
            
            self.update_progress(5, "Parsing INP File...")
            col_data, beam_data, slab_data = load_inp(path)
            
            if not col_data and not beam_data and not slab_data:
                self.update_progress(0, "Error: No valid elements found in file.")
                self.btn_cancel.Content = "Close"
                self.btn_cancel.IsEnabled = True
                return

            z_vals = set()
            for _, bz, tz, _ in col_data: z_vals.update([bz, tz])
            for _, tz, _ in beam_data: z_vals.add(tz)
            for _, tz, _, _ in slab_data: z_vals.add(tz)
            
            level_name_map = build_level_name_map(z_vals, prefix, start_label, suffix, sep)
            level_cache = {}
            for lvl in FilteredElementCollector(doc).OfClass(Level):
                level_cache[m_to_mm(lvl.Elevation / 3.28084)] = lvl

            def get_or_create_level(z_ft, z_m):
                key = m_to_mm(z_m)
                if key in level_cache: return level_cache[key]
                for lev in list(level_cache.values()):
                    if abs(lev.Elevation - z_ft) < TOL_LEVEL:
                        level_cache[key] = lev; return lev
                new_lv = Level.Create(doc, z_ft)
                nm = level_name_map.get(z_m)
                if nm:
                    try: new_lv.Name = nm
                    except Exception: pass
                level_cache[key] = new_lv
                return new_lv

            self.update_progress(10, "Setting up Revit Levels & Activating Families...")
            t1 = Transaction(doc, "INP2BIM: Initial Setup")
            t1.Start()
            for sym in (col_symbol, beam_symbol):
                if not sym.IsActive: sym.Activate()
            for z_m in sorted(z_vals):
                get_or_create_level(clean_ft(m_to_ft(z_m)), z_m)
            doc.Regenerate()
            t1.Commit()

            self.update_progress(15, "Initializing Generation...")
            t2 = Transaction(doc, "INP2BIM: Create Elements")
            t2.Start()

            # Columns Generation
            existing_cols = {}
            for c in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType():
                try:
                    cm = c.LookupParameter("Comments")
                    nm = cm.AsString() if cm and cm.HasValue else None
                    lv = doc.GetElement(c.LevelId) if c.LevelId else None
                    if nm and lv: existing_cols[(nm, lv.Id.IntegerValue)] = c
                except Exception: pass

            total_cols = len(col_data)
            for idx, (name, base_z_m, top_z_m, pts) in enumerate(col_data):
                if idx % 5 == 0: self.update_progress(15 + int((idx/max(1,total_cols))*20), "Generating Columns {}/{}...".format(idx, total_cols))
                pts_m = [XYZ(p[0], p[1], p[2]) for p in pts]
                w_mm = distance_mm(pts_m[0], pts_m[1])
                d_mm = distance_mm(pts_m[1], pts_m[2])
                if w_mm == 0: w_mm = distance_mm(pts_m[0], pts_m[3])
                if d_mm == 0: d_mm = w_mm

                base_z_ft, top_z_ft = clean_ft(m_to_ft(base_z_m)), clean_ft(m_to_ft(top_z_m))
                cx = clean_ft(m_to_ft(sum(p[0] for p in pts) / 4.0))
                cy = clean_ft(m_to_ft(sum(p[1] for p in pts) / 4.0))
                center = XYZ(cx, cy, base_z_ft)
                
                base_lv, top_lv = get_or_create_level(base_z_ft, base_z_m), get_or_create_level(top_z_ft, top_z_m)
                ctype = get_element_type(col_symbol, w_mm, d_mm)
                
                # Standardized pattern (C4 @4.0m)
                uname = "{} @{:.1f}m".format(name, base_z_m)
                key = (uname, base_lv.Id.IntegerValue)
                
                ex = existing_cols.get(key)
                if ex:
                    try:
                        if hasattr(ex.Location, "Point"): ex.Location.Point = center
                    except Exception: pass
                    if ex.GetTypeId() != ctype.Id: ex.Symbol = ctype
                    safe_set(ex.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM), top_lv.Id)
                    safe_set(ex.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM), 0.0)
                    safe_set(ex.LookupParameter("Comments"), uname)
                else:
                    col = doc.Create.NewFamilyInstance(center, ctype, base_lv, StructuralType.Column)
                    safe_set(col.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM), top_lv.Id)
                    safe_set(col.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM), 0.0)
                    safe_set(col.LookupParameter("Comments"), uname)
                    existing_cols[key] = col

            # Beams Generation
            existing_beams = {}
            for b in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType():
                try:
                    lv_id = b.LevelId
                    if not lv_id: continue
                    cm = b.LookupParameter("Comments")
                    nm = cm.AsString() if cm and cm.HasValue else None
                    if nm: existing_beams[(nm, lv_id.IntegerValue)] = b
                except Exception: pass

            total_beams = len(beam_data)
            for idx, (name, top_z_m, pts) in enumerate(beam_data):
                if idx % 5 == 0: self.update_progress(35 + int((idx/max(1,total_beams))*30), "Generating Beams {}/{}...".format(idx, total_beams))
                pts_m = [XYZ(p[0], p[1], p[2]) for p in pts]
                edges = sorted([(distance_mm(pts_m[i], pts_m[(i+1)%4]), pts_m[i], pts_m[(i+1)%4]) for i in range(4)], key=lambda e: e[0])
                
                w_mm = edges[0][0]
                if w_mm == 0: w_mm = 200 # safeguard
                d_mm = max(m_to_mm(abs(top_z_m - pts[0][2])), 1)
                if d_mm == 1: d_mm = w_mm # safeguard
                
                top_ft = clean_ft(m_to_ft(top_z_m))
                mid1 = XYZ(clean_ft(m_to_ft((edges[0][1].X+edges[0][2].X)/2)), clean_ft(m_to_ft((edges[0][1].Y+edges[0][2].Y)/2)), top_ft)
                mid2 = XYZ(clean_ft(m_to_ft((edges[1][1].X+edges[1][2].X)/2)), clean_ft(m_to_ft((edges[1][1].Y+edges[1][2].Y)/2)), top_ft)
                if mid1.DistanceTo(mid2) < 0.01: continue

                lv = get_or_create_level(top_ft, top_z_m)
                btype = get_element_type(beam_symbol, w_mm, d_mm)
                
                # Standardized pattern (B4 @4.0m) - Note: Level string removed as requested
                uname = "{} @{:.1f}m".format(name, top_z_m)
                key = (uname, lv.Id.IntegerValue)
                
                ex = existing_beams.get(key)
                if ex:
                    if ex.GetTypeId() != btype.Id: ex.Symbol = btype
                    safe_set(ex.LookupParameter("Comments"), uname)
                else:
                    nb = doc.Create.NewFamilyInstance(Line.CreateBound(mid1, mid2), btype, lv, StructuralType.Beam)
                    safe_set(nb.LookupParameter("Comments"), uname)
                    existing_beams[key] = nb

            # Slabs Generation
            existing_floors = {}
            for fl in FilteredElementCollector(doc).OfClass(Floor).WhereElementIsNotElementType():
                try:
                    cm = fl.LookupParameter("Comments")
                    nm = cm.AsString() if cm and cm.HasValue else None
                    lp = fl.get_Parameter(BuiltInParameter.LEVEL_PARAM)
                    lv = doc.GetElement(lp.AsElementId()) if lp else None
                    if nm and lv: existing_floors[(nm, lv.Id.IntegerValue)] = fl
                except Exception: pass

            total_slabs = len(slab_data)
            for idx, (name, top_z_m, base_z_m, pts) in enumerate(slab_data):
                if idx % 2 == 0: self.update_progress(65 + int((idx/max(1,total_slabs))*20), "Generating Slabs {}/{}...".format(idx, total_slabs))
                thick_mm = max((top_z_m - base_z_m) * 1000.0, 125.0)
                top_ft = clean_ft(m_to_ft(top_z_m))
                lv = get_or_create_level(top_ft, top_z_m)
                
                # Standardized pattern (S4 @4.0m)
                uname = "{} @{:.1f}m".format(name, top_z_m)
                ex = existing_floors.get((uname, lv.Id.IntegerValue))
                
                if ex:
                    try: doc.Delete(ex.Id)
                    except Exception: pass
                    
                ftype = get_floor_type(floor_type, thick_mm)
                off_pts = offset_rectangle(pts, top_ft)
                if off_pts is None: continue
                    
                loop = CurveLoop()
                for i in range(4): loop.Append(Line.CreateBound(off_pts[i], off_pts[(i+1)%4]))
                try:
                    floor = Floor.Create(doc, [loop], ftype.Id, lv.Id)
                    safe_set(floor.LookupParameter("Comments"), uname)
                    existing_floors[(uname, lv.Id.IntegerValue)] = floor
                except Exception: pass

            t2.Commit()

            # Join Geometry Execution
            self.update_progress(85, "Joining Geometry: Executing Overlap Calculations...")
            t3 = Transaction(doc, "INP2BIM: Join Geometry")
            t3.Start()
            
            all_cols   = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType().ToElements())
            all_beams  = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType().ToElements())
            all_floors = list(FilteredElementCollector(doc).OfClass(Floor).WhereElementIsNotElementType().ToElements())

            def bb(elem): return elem.get_BoundingBox(None)

            def overlaps(bb1, bb2, tol=0.08):
                if bb1 is None or bb2 is None: return False
                return not (bb1.Max.X + tol < bb2.Min.X or bb1.Min.X - tol > bb2.Max.X or
                            bb1.Max.Y + tol < bb2.Min.Y or bb1.Min.Y - tol > bb2.Max.Y or
                            bb1.Max.Z + tol < bb2.Min.Z or bb1.Min.Z - tol > bb2.Max.Z)

            def try_join_ordered(dominant, subordinate):
                try:
                    if not JoinGeometryUtils.AreElementsJoined(doc, dominant, subordinate):
                        JoinGeometryUtils.JoinGeometry(doc, dominant, subordinate)
                    try:
                        if not JoinGeometryUtils.IsCuttingElementInJoin(doc, dominant, subordinate):
                            JoinGeometryUtils.SwitchJoinOrder(doc, dominant, subordinate)
                    except Exception: pass
                except Exception: pass

            for i, col in enumerate(all_cols):
                if i % 10 == 0: self.update_progress(85 + int((i/max(1,len(all_cols)))*10), "Joining Columns...")
                bbc = bb(col)
                for beam in all_beams:
                    if overlaps(bbc, bb(beam)): try_join_ordered(col, beam)
                for floor in all_floors:
                    if overlaps(bbc, bb(floor)): try_join_ordered(col, floor)

            for i, beam in enumerate(all_beams):
                if i % 10 == 0: self.update_progress(95 + int((i/max(1,len(all_beams)))*5), "Joining Beams & Slabs...")
                bbb = bb(beam)
                for floor in all_floors:
                    if overlaps(bbb, bb(floor)): try_join_ordered(beam, floor)

            t3.Commit()
            
            # Completion sequence!
            self.update_progress(100, "100% — Generation Completed Successfully!")
            self.btn_cancel.Content = "Close"
            self.btn_cancel.IsEnabled = True

        except Exception as e:
            # Safely rollback any running transaction
            for t_fail in [t1, t2, t3]:
                try:
                    if 't_fail' in locals() and t_fail.HasStarted() and not t_fail.HasEnded(): 
                        t_fail.RollBack()
                except Exception: pass
                
            self.update_progress(0, "Error: {}".format(e))
            self.status_text.Foreground = brush(C_ERROR)
            self.btn_cancel.Content = "Close"
            self.btn_cancel.IsEnabled = True

# ═══════════════════════════════════════════════════════════════════════════
# SCRIPT ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════
dlg = InpToBimDialog()
dlg.ShowDialog()
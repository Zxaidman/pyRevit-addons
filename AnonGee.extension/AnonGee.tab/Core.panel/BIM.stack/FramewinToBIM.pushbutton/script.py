# -*- coding: utf-8 -*-
# noqa
__title__  = 'BIM Generation'
__author__ = 'ZAID'
__doc__    = ('Generate a structural RC frame (Columns / Beams / Slabs) from a '
              'PLANWIN / FRAMEWIN .inp file. A single dialog collects the input '
              'file and level-naming. Column, beam and slab TYPES are detected '
              'automatically - the script picks whichever loaded family/type is '
              'CONCRETE, so no manual type selection is required.')

# Compatible with Revit 2024 / 2025  +  pyRevit 6.10.0  (IronPython 2.7 engine).
# Keep all syntax Python-2.7 / IronPython safe (no f-strings, use .format()).

from pyrevit import forms, script
import clr, re, os, math
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import StructuralType, StructuralMaterialType
from System.Windows import Visibility

doc    = __revit__.ActiveUIDocument.Document
uidoc  = __revit__.ActiveUIDocument
output = script.get_output()

# ── Unit helpers ──────────────────────────────────────────────────────────────
# INP coords are in METRES.  Revit internal unit is always FEET.
def m_to_mm(v):   return int(round(float(v) * 1000.0))
def mm_to_ft(mm): return mm / 304.8
def m_to_ft(m):   return mm_to_ft(m_to_mm(m))
def clean_ft(v):  return mm_to_ft(int(round(float(v) * 304.8)))

TOL_LEVEL        = mm_to_ft(1)
BEAM_Z_TOL_M     = 1.0
BEAM_MAX_DIST_FT = 15.0

# Keywords used to recognise concrete from text (lower-cased, language fallback).
CONCRETE_WORDS = ('concrete', 'rcc', 'r.c.c', 'conc', 'cast-in-place', 'castinplace')

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

def get_family_name(sym):
    try: return doc.GetElement(sym.Family.Id).Name
    except Exception: return ""

def distance_mm(p1, p2):
    """Distance between two points whose coords are in metres -> result in mm."""
    dx = p1.X - p2.X; dy = p1.Y - p2.Y; dz = p1.Z - p2.Z
    return int(round(math.sqrt(dx*dx + dy*dy + dz*dz) * 1000.0))

# ── Concrete detection ─────────────────────────────────────────────────────────
# Layered, language-independent test. Order of reliability:
#   1) Structural asset -> StructuralMaterialType.Concrete  (not localized)
#   2) Material.MaterialClass / Material.Name contains a concrete keyword
#   3) Family / type name contains a concrete keyword
# Columns / beams additionally favour types exposing 'b' and 'h' params, because
# the section-resizing logic (Duplicate + set b/h) requires exactly those.

def _text_is_concrete(*chunks):
    txt = " ".join([(c or "") for c in chunks]).lower()
    return any(w in txt for w in CONCRETE_WORDS)

def _material_is_concrete(mat):
    if mat is None:
        return False
    # 1) structural asset -> enum
    try:
        asset_id = mat.StructuralAssetId
        if asset_id and asset_id != ElementId.InvalidElementId:
            pse = doc.GetElement(asset_id)
            if pse is not None:
                st = pse.GetStructuralAsset()
                if st and st.StructuralMaterialType == StructuralMaterialType.Concrete:
                    return True
    except Exception:
        pass
    # 2) material class / name text
    try:
        if _text_is_concrete(getattr(mat, "MaterialClass", ""), mat.Name):
            return True
    except Exception:
        pass
    return False

def _symbol_material(sym):
    """Resolve a FamilySymbol's structural material -> Material or None."""
    try:
        p = sym.get_Parameter(BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if p and p.HasValue:
            mid = p.AsElementId()
            if mid and mid != ElementId.InvalidElementId:
                el = doc.GetElement(mid)
                if isinstance(el, Material):
                    return el
    except Exception:
        pass
    return None

def _has_bh(sym):
    return (sym.LookupParameter("b") is not None and
            sym.LookupParameter("h") is not None)

def auto_pick_symbol(category_bic):
    """Return (best_symbol, display, score, total_loaded) or (None, '', 0, n).
    Picks the highest-scoring CONCRETE family symbol in the category."""
    syms  = list(FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(category_bic))
    total = len(syms)
    scored = []
    for s in syms:
        fam  = get_family_name(s)
        typ  = get_element_name(s)
        name_conc = _text_is_concrete(fam, typ)
        mat_conc  = _material_is_concrete(_symbol_material(s))
        if not (name_conc or mat_conc):
            continue                       # not concrete -> reject
        score = (5 if mat_conc else 0) + (3 if name_conc else 0) + (3 if _has_bh(s) else 0)
        scored.append((score, _has_bh(s), fam, typ, s))
    if not scored:
        return None, "", 0, total
    # highest score, then prefer one with b/h, then shortest name (most generic)
    scored.sort(key=lambda t: (t[0], t[1], -len(t[3])), reverse=True)
    best = scored[0]
    return best[4], "{} : {}".format(best[2], best[3]), best[0], total

def auto_pick_floor():
    """Return (best_floortype, display, is_concrete, total). Prefers a concrete,
    single-layer floor type (so thickness editing in get_floor_type works)."""
    fts = list(FilteredElementCollector(doc).OfClass(FloorType))
    total = len(fts)
    scored = []
    for ft in fts:
        nm = get_element_name(ft)
        name_conc = _text_is_concrete(nm)
        mat_conc  = False
        single    = False
        try:
            cs = ft.GetCompoundStructure()
            if cs:
                layers = list(cs.GetLayers())
                single = (not cs.IsVerticallyCompound) and len(layers) >= 1
                for layer in layers:
                    mid = layer.MaterialId
                    m   = doc.GetElement(mid) if (mid and mid != ElementId.InvalidElementId) else None
                    if _material_is_concrete(m):
                        mat_conc = True; break
        except Exception:
            pass
        conc  = name_conc or mat_conc
        score = (5 if mat_conc else 0) + (2 if name_conc else 0) + (2 if single else 0)
        scored.append((conc, score, ft, nm))
    if not scored:
        return None, "", False, 0
    # concrete first, then score
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    best = scored[0]
    return best[2], best[3], best[0], total

# ── INP parser ────────────────────────────────────────────────────────────────
def _is_coord(s):
    try:
        pts = s.split(',')
        if len(pts) == 3: [float(p) for p in pts]; return True
    except Exception: pass
    return False

def _is_skip(s):
    return s.startswith('*') or s.startswith('#') or s.startswith('-')

def _parse_section(lines, start_kw, stop_kws):
    idx = 0
    while idx < len(lines) and lines[idx] != start_kw: idx += 1
    idx += 1
    if idx < len(lines):
        try: int(lines[idx]); idx += 1
        except ValueError: pass
    blocks = []
    while idx < len(lines):
        line = lines[idx]
        if line in stop_kws or line.startswith('----------'): break
        if _is_skip(line) or not line or _is_coord(line): idx += 1; continue
        try: float(line); idx += 1; continue
        except ValueError: pass
        name = line; idx += 1
        if idx >= len(lines): break
        try: value = float(lines[idx]); idx += 1
        except (ValueError, IndexError): continue
        pts = []
        while idx < len(lines) and len(pts) < 4:
            cl = lines[idx]
            if _is_coord(cl):
                x, y, z = [float(v) for v in cl.split(',')]
                pts.append((x, y, z)); idx += 1
            elif _is_skip(cl) or not cl: idx += 1
            else: break
        while idx < len(lines) and _is_skip(lines[idx]): idx += 1
        if len(pts) == 4: blocks.append((name, value, pts))
    return blocks

def load_inp(file_path):
    with open(file_path, 'r') as f:
        lines = [l.strip() for l in f if l.strip()]
    col_raw  = _parse_section(lines, 'Columns', ['Beams', 'Slabs', 'Walls'])
    beam_raw = _parse_section(lines, 'Beams',   ['Slabs', 'Walls'])
    slab_raw = _parse_section(lines, 'Slabs',   ['Walls'])
    col_data  = [(n, pts[0][2], pts[0][2] + abs(h), pts) for n, h, pts in col_raw]
    beam_data = [(n, top, pts)                            for n, top, pts in beam_raw]
    slab_data = [(n, top, min(p[2] for p in pts), pts)   for n, top, pts in slab_raw]
    return col_data, beam_data, slab_data

# ── Single consolidated WPF dialog ──────────────────────────────────────────────
XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="INP to BIM Generator" Width="520" Height="440"
        WindowStartupLocation="CenterScreen" ResizeMode="NoResize"
        Background="#1A1D23" FontFamily="Segoe UI">
  <Window.Resources>

    <Style x:Key="Btn" TargetType="Button">
      <Setter Property="Foreground" Value="White"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="FontSize" Value="13"/>
      <Setter Property="FontFamily" Value="Segoe UI"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border x:Name="bd" Background="{TemplateBinding Background}"
                    CornerRadius="5" Padding="{TemplateBinding Padding}">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter TargetName="bd" Property="Opacity" Value="0.85"/>
              </Trigger>
              <Trigger Property="IsPressed" Value="True">
                <Setter TargetName="bd" Property="Opacity" Value="0.7"/>
              </Trigger>
              <Trigger Property="IsEnabled" Value="False">
                <Setter TargetName="bd" Property="Opacity" Value="0.4"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

    <Style x:Key="TBox" TargetType="TextBox">
      <Setter Property="Background" Value="#2D3242"/>
      <Setter Property="Foreground" Value="#E0E4EC"/>
      <Setter Property="BorderBrush" Value="#3D4560"/>
      <Setter Property="BorderThickness" Value="1"/>
      <Setter Property="Padding" Value="8,7"/>
      <Setter Property="FontSize" Value="12"/>
      <Setter Property="CaretBrush" Value="#4FC3F7"/>
      <Setter Property="SelectionBrush" Value="#0078D4"/>
    </Style>

    <Style x:Key="Lbl" TargetType="TextBlock">
      <Setter Property="Foreground" Value="#6B7280"/>
      <Setter Property="FontSize" Value="10"/>
      <Setter Property="FontWeight" Value="SemiBold"/>
      <Setter Property="Margin" Value="0,0,0,5"/>
    </Style>

  </Window.Resources>

  <Grid>
    <Grid.RowDefinitions>
      <RowDefinition Height="72"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="60"/>
    </Grid.RowDefinitions>

    <!-- ── Header ── -->
    <Border Grid.Row="0">
      <Border.Background>
        <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
          <GradientStop Color="#0063B1" Offset="0"/>
          <GradientStop Color="#0091EA" Offset="1"/>
        </LinearGradientBrush>
      </Border.Background>
      <Grid Margin="22,0">
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <StackPanel VerticalAlignment="Center">
          <TextBlock Text="INP &#x2192; Revit BIM" FontSize="18" FontWeight="Bold" Foreground="White"/>
          <TextBlock Text="Auto-detects concrete column / beam / slab types"
                     FontSize="11" Foreground="#B3D9FF" Margin="0,2,0,0"/>
        </StackPanel>
        <TextBlock Grid.Column="1" Text="&#xe8b8;" FontFamily="Segoe MDL2 Assets"
                   FontSize="28" Foreground="#FFFFFF40" VerticalAlignment="Center"/>
      </Grid>
    </Border>

    <!-- ── Content ── -->
    <StackPanel Grid.Row="1" Margin="22,16,22,0">

      <!-- File row -->
      <TextBlock Text="INPUT FILE  (.inp / .txt)" Style="{StaticResource Lbl}"/>
      <Grid Margin="0,0,0,14">
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="8"/>
          <ColumnDefinition Width="88"/>
        </Grid.ColumnDefinitions>
        <TextBox x:Name="tbFile" Grid.Column="0" Style="{StaticResource TBox}" IsReadOnly="True"/>
        <Button  Grid.Column="2" Content="Browse..." Background="#2D3242"
                 Padding="0,8" Style="{StaticResource Btn}"
                 Click="browse_click"
                 Foreground="#9EABBC" BorderBrush="#3D4560" BorderThickness="1">
          <Button.Template>
            <ControlTemplate TargetType="Button">
              <Border x:Name="bd" Background="{TemplateBinding Background}"
                      BorderBrush="{TemplateBinding BorderBrush}"
                      BorderThickness="{TemplateBinding BorderThickness}"
                      CornerRadius="5" Padding="{TemplateBinding Padding}">
                <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
              </Border>
              <ControlTemplate.Triggers>
                <Trigger Property="IsMouseOver" Value="True">
                  <Setter TargetName="bd" Property="Background" Value="#3D4560"/>
                </Trigger>
              </ControlTemplate.Triggers>
            </ControlTemplate>
          </Button.Template>
        </Button>
      </Grid>

      <!-- Level naming card -->
      <Border Background="#21253A" CornerRadius="8" Padding="16,14">
        <StackPanel>
          <TextBlock Text="LEVEL NAMING" Style="{StaticResource Lbl}" Margin="0,0,0,10"/>

          <Border Background="#191C28" CornerRadius="5" Padding="12,9" Margin="0,0,0,14">
            <StackPanel Orientation="Horizontal">
              <TextBlock Text="Preview  " Foreground="#4B5563" FontSize="12"/>
              <TextBlock x:Name="tbPreview" Text="00 0TH LVL."
                         Foreground="#4FC3F7" FontSize="13" FontWeight="SemiBold"/>
            </StackPanel>
          </Border>

          <Grid>
            <Grid.ColumnDefinitions>
              <ColumnDefinition Width="*"/>
              <ColumnDefinition Width="10"/>
              <ColumnDefinition Width="*"/>
              <ColumnDefinition Width="10"/>
              <ColumnDefinition Width="*"/>
              <ColumnDefinition Width="10"/>
              <ColumnDefinition Width="52"/>
            </Grid.ColumnDefinitions>

            <StackPanel Grid.Column="0">
              <TextBlock Text="PREFIX" Style="{StaticResource Lbl}"/>
              <TextBox x:Name="tbPrefix" Text="00" Style="{StaticResource TBox}"
                       TextChanged="update_preview"/>
            </StackPanel>
            <StackPanel Grid.Column="2">
              <TextBlock Text="NAME" Style="{StaticResource Lbl}"/>
              <TextBox x:Name="tbName" Text="0TH" Style="{StaticResource TBox}"
                       TextChanged="update_preview"/>
            </StackPanel>
            <StackPanel Grid.Column="4">
              <TextBlock Text="SUFFIX" Style="{StaticResource Lbl}"/>
              <TextBox x:Name="tbSuffix" Text="LVL." Style="{StaticResource TBox}"
                       TextChanged="update_preview"/>
            </StackPanel>
            <StackPanel Grid.Column="6">
              <TextBlock Text="SEP" Style="{StaticResource Lbl}"/>
              <TextBox x:Name="tbSep" Text=" " Style="{StaticResource TBox}"
                       TextChanged="update_preview"/>
            </StackPanel>
          </Grid>
        </StackPanel>
      </Border>

    </StackPanel>

    <!-- ── Footer ── -->
    <Border Grid.Row="2" Background="#13151C">
      <Grid Margin="22,0">
        <StackPanel Orientation="Horizontal" HorizontalAlignment="Right"
                    VerticalAlignment="Center">
          <Button Content="Cancel" Background="#252A35" Padding="24,9"
                  Style="{StaticResource Btn}" Width="90" Margin="0,0,8,0"
                  Click="cancel_click" IsCancel="True" Foreground="#9EABBC"/>
          <Button x:Name="btnRun" Content="Generate  &#x276F;" Background="#0078D4" Padding="24,9"
                  Style="{StaticResource Btn}" Width="130"
                  Click="run_click" IsDefault="True"/>
        </StackPanel>
      </Grid>
    </Border>
  </Grid>
</Window>
"""

OK_BRUSH = WARN_BRUSH = ERR_BRUSH = None  # detection is now shown only in the report

class InpToBimForm(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, XAML, literal_string=True)
        self.result = None

    def update_preview(self, sender, args):
        try:
            parts = [p for p in [self.tbPrefix.Text, self.tbName.Text, self.tbSuffix.Text] if p]
            self.tbPreview.Text = self.tbSep.Text.join(parts) if parts else "(empty)"
        except Exception:
            pass

    def browse_click(self, sender, args):
        # Use a full filter string (file_ext='inp|txt' produces an invalid filter).
        path = forms.pick_file(
            files_filter='Frame data (*.inp;*.txt)|*.inp;*.txt|All files (*.*)|*.*')
        if path:
            self.tbFile.Text = path

    def run_click(self, sender, args):
        if not self.tbFile.Text or not os.path.exists(self.tbFile.Text):
            forms.alert("Please select a valid .inp / .txt file.")
            return
        self.result = {
            'file':   self.tbFile.Text,
            'prefix': self.tbPrefix.Text,
            'name':   self.tbName.Text,
            'suffix': self.tbSuffix.Text,
            'sep':    self.tbSep.Text,
        }
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()

# ── Run auto-detection BEFORE the dialog opens ──────────────────────────────────
col_symbol, col_disp, col_score, col_total   = auto_pick_symbol(BuiltInCategory.OST_StructuralColumns)
beam_symbol, beam_disp, beam_score, beam_total = auto_pick_symbol(BuiltInCategory.OST_StructuralFraming)
floor_type, floor_disp, floor_is_conc, floor_total = auto_pick_floor()

# If no concrete floor exists, fall back to the first available floor type so the
# tool still runs (slab thickness is rebuilt anyway), but flag it for the user.
if floor_type is None and floor_total == 0:
    any_ft = list(FilteredElementCollector(doc).OfClass(FloorType))
    if any_ft:
        floor_type = any_ft[0]; floor_disp = get_element_name(floor_type); floor_is_conc = False

# Mandatory concrete column + beam families must exist (steel sections cannot be
# resized via b/h). Fail with clear guidance BEFORE opening the dialog.
if col_symbol is None or beam_symbol is None:
    _need = []
    if col_symbol is None:
        _need.append("- a concrete structural COLUMN family (e.g. 'Concrete-Rectangular-Column')")
    if beam_symbol is None:
        _need.append("- a concrete structural FRAMING / BEAM family (e.g. 'Concrete-Rectangular Beam')")
    forms.alert("No concrete family detected. Please load:\n\n{}\n\n"
                "then run the tool again.".format("\n".join(_need)),
                title="INP to BIM", exitscript=True)

if floor_disp == "":
    floor_disp = "(none)"

# ── Gather inputs (single dialog) ───────────────────────────────────────────────
form = InpToBimForm()
form.ShowDialog()
if form.result is None:
    script.exit()

cfg       = form.result
file_path = cfg['file']
prefix    = cfg['prefix']
start_lbl = cfg['name']
suffix    = cfg['suffix']
sep       = cfg['sep']

# ── Parse ───────────────────────────────────────────────────────────────────────
col_data, beam_data, slab_data = load_inp(file_path)
if not col_data and not beam_data and not slab_data:
    forms.alert("No elements found in the INP file.", exitscript=True)

z_vals = set()
for _, bz, tz, _ in col_data:  z_vals.add(bz); z_vals.add(tz)
for _, tz, _     in beam_data: z_vals.add(tz)
for _, tz, _, _  in slab_data: z_vals.add(tz)

def build_level_name_map(z_values):
    ordered  = sorted(z_values)
    base_num = get_num(start_lbl)
    prefix_num, pad = (int(prefix), len(prefix)) if prefix.isdigit() else (None, 0)
    result = {}
    for i, z in enumerate(ordered):
        curr  = str(prefix_num + i).zfill(pad) if prefix_num is not None else prefix
        parts = [p for p in [curr, ordinal(base_num + i), suffix] if p]
        result[z] = sep.join(parts)
    return result

level_name_map = build_level_name_map(z_vals)

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

# ── TX 1: Activate base symbols ──────────────────────────────────────────────────
t_act = Transaction(doc, "INP2BIM: Activate symbols")
t_act.Start()
try:
    for sym in (col_symbol, beam_symbol):
        if sym is not None and hasattr(sym, 'IsActive') and not sym.IsActive:
            sym.Activate()
    doc.Regenerate()
    t_act.Commit()
except Exception as e:
    t_act.RollBack()
    forms.alert("Failed to activate symbols:\n{}".format(e), exitscript=True)

# ── TX 2: Create levels ──────────────────────────────────────────────────────────
t1 = Transaction(doc, "INP2BIM: Create Levels")
t1.Start()
try:
    for z_m in sorted(z_vals):
        get_or_create_level(clean_ft(m_to_ft(z_m)), z_m)
    doc.Regenerate()
    t1.Commit()
except Exception as e:
    t1.RollBack()
    forms.alert("Failed to create levels:\n{}".format(e), exitscript=True)

# ── Type helpers (section auto-sizing) ────────────────────────────────────────────
def _find_symbol_by_name(category_bic, nm):
    """Recover an existing FamilySymbol by type name (handles 'name already in
    use' after a previous run created the same section)."""
    for fs in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(category_bic):
        try:
            if fs.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == nm:
                return fs
        except Exception: pass
    return None

def _ensure_active(sym):
    try:
        if sym is not None and hasattr(sym, 'IsActive') and not sym.IsActive:
            sym.Activate()
    except Exception:
        pass

col_type_lookup = {}
for fs in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralColumns):
    try: col_type_lookup[fs.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()] = fs
    except Exception: pass
col_type_cache = {}

def get_col_type(w_mm, d_mm):
    nm = "{}x{}mm".format(w_mm, d_mm)
    if nm in col_type_cache:  return col_type_cache[nm]
    if nm in col_type_lookup:
        col_type_cache[nm] = col_type_lookup[nm]; _ensure_active(col_type_lookup[nm]); return col_type_lookup[nm]
    try:
        nt = col_symbol.Duplicate(nm)
    except Exception:
        ex = _find_symbol_by_name(BuiltInCategory.OST_StructuralColumns, nm)
        nt = ex if ex is not None else col_symbol
        col_type_cache[nm] = nt; _ensure_active(nt); return nt
    safe_set(nt.LookupParameter("b"), clean_ft(mm_to_ft(w_mm)))
    safe_set(nt.LookupParameter("h"), clean_ft(mm_to_ft(d_mm)))
    _ensure_active(nt)
    col_type_cache[nm] = nt; col_type_lookup[nm] = nt; return nt

beam_type_lookup = {}
for fs in FilteredElementCollector(doc).OfClass(FamilySymbol).OfCategory(BuiltInCategory.OST_StructuralFraming):
    try: beam_type_lookup[fs.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()] = fs
    except Exception: pass
beam_type_cache = {}

def get_beam_type(w_mm, d_mm):
    nm = "{}x{}mm".format(w_mm, d_mm)
    if nm in beam_type_cache:  return beam_type_cache[nm]
    if nm in beam_type_lookup:
        beam_type_cache[nm] = beam_type_lookup[nm]; _ensure_active(beam_type_lookup[nm]); return beam_type_lookup[nm]
    try:
        nt = beam_symbol.Duplicate(nm)
    except Exception:
        ex = _find_symbol_by_name(BuiltInCategory.OST_StructuralFraming, nm)
        nt = ex if ex is not None else beam_symbol
        beam_type_cache[nm] = nt; _ensure_active(nt); return nt
    safe_set(nt.LookupParameter("b"), clean_ft(mm_to_ft(w_mm)))
    safe_set(nt.LookupParameter("h"), clean_ft(mm_to_ft(d_mm)))
    _ensure_active(nt)
    beam_type_cache[nm] = nt; beam_type_lookup[nm] = nt; return nt

floor_type_cache = {}
def get_floor_type(thickness_mm):
    nm = "{}mm RCC SLAB".format(int(round(thickness_mm)))
    if nm in floor_type_cache: return floor_type_cache[nm]
    for ft in FilteredElementCollector(doc).OfClass(FloorType):
        try:
            if get_element_name(ft) == nm: floor_type_cache[nm] = ft; return ft
        except Exception: pass
    try:
        nft = floor_type.Duplicate(nm)
    except Exception:
        floor_type_cache[nm] = floor_type; return floor_type
    try:
        comp = nft.GetCompoundStructure()
        if comp and not comp.IsVerticallyCompound:
            layers = list(comp.GetLayers())
            tw = mm_to_ft(thickness_mm)
            for i, layer in enumerate(layers): layer.Width = tw if i == 0 else 0.0
            comp.SetLayers(layers); nft.SetCompoundStructure(comp)
    except Exception: pass
    floor_type_cache[nm] = nft; return nft

# ── Slab offset helpers ───────────────────────────────────────────────────────────
def get_beam_width_ft(beam):
    for pn in ["b", "Width"]:
        p = beam.Symbol.LookupParameter(pn)
        if p and p.HasValue: return p.AsDouble()
    p = beam.Symbol.get_Parameter(BuiltInParameter.STRUCTURAL_SECTION_COMMON_WIDTH)
    if p and p.HasValue: return p.AsDouble()
    bb = beam.get_BoundingBox(None)
    if bb: return min(abs(bb.Max.X - bb.Min.X), abs(bb.Max.Y - bb.Min.Y))
    return None

def get_beam_offset_for_edge(p_start, p_end, is_horiz, z_ft):
    best_dist = float('inf'); best_hw = 0.0
    for bm in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType():
        try:
            loc = bm.Location
            if not hasattr(loc, "Curve"): continue
            c = loc.Curve; bs = c.GetEndPoint(0); be = c.GetEndPoint(1)
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
            if w and dist < best_dist: best_dist = dist; best_hw = w / 2.0
        except Exception: pass
    return best_hw

def offset_rectangle(pts_m, slab_top_ft):
    xs = [m_to_ft(p[0]) for p in pts_m]; ys = [m_to_ft(p[1]) for p in pts_m]
    xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys)
    zv = slab_top_ft
    ol  = get_beam_offset_for_edge(XYZ(xmin,ymin,zv), XYZ(xmin,ymax,zv), False, zv)
    or_ = get_beam_offset_for_edge(XYZ(xmax,ymin,zv), XYZ(xmax,ymax,zv), False, zv)
    ob  = get_beam_offset_for_edge(XYZ(xmin,ymin,zv), XYZ(xmax,ymin,zv), True,  zv)
    ot  = get_beam_offset_for_edge(XYZ(xmin,ymax,zv), XYZ(xmax,ymax,zv), True,  zv)
    xmin += ol; xmax -= or_; ymin += ob; ymax -= ot
    if xmin >= xmax or ymin >= ymax: return None
    return [XYZ(xmin,ymin,zv), XYZ(xmax,ymin,zv), XYZ(xmax,ymax,zv), XYZ(xmin,ymax,zv)]

# ── TX 3: Create columns, beams, slabs ────────────────────────────────────────────
t2 = Transaction(doc, "INP2BIM: Create Elements")
t2.Start()
msgs = []
created_col_ids   = []
created_beam_ids  = []
created_floor_ids = []

try:
    # ── Columns ──────────────────────────────────────────────────────────────────
    existing_cols = {}
    for c in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType():
        try:
            cm = c.LookupParameter("Comments"); nm = cm.AsString() if cm and cm.HasValue else None
            lv = doc.GetElement(c.LevelId) if c.LevelId else None
            if nm and lv: existing_cols[(nm, lv.Id.IntegerValue)] = c
        except Exception: pass

    col_created = col_updated = col_skipped = 0
    for name, base_z_m, top_z_m, pts in col_data:
        pts_m = [XYZ(p[0], p[1], p[2]) for p in pts]
        w_mm  = distance_mm(pts_m[0], pts_m[1])
        d_mm  = distance_mm(pts_m[1], pts_m[2])
        if w_mm == 0: w_mm = distance_mm(pts_m[0], pts_m[3])
        if d_mm == 0: d_mm = w_mm

        base_z_ft = clean_ft(m_to_ft(base_z_m))
        top_z_ft  = clean_ft(m_to_ft(top_z_m))
        cx = clean_ft(m_to_ft(sum(p[0] for p in pts) / 4.0))
        cy = clean_ft(m_to_ft(sum(p[1] for p in pts) / 4.0))
        center = XYZ(cx, cy, base_z_ft)

        base_lv = get_or_create_level(base_z_ft, base_z_m)
        top_lv  = get_or_create_level(top_z_ft,  top_z_m)
        if base_lv is None or base_lv.Id == ElementId.InvalidElementId:
            msgs.append("SKIPPED COL {} - invalid level".format(name)); col_skipped += 1; continue

        ctype = get_col_type(w_mm, d_mm)
        uname = "{} @{:.1f}m".format(name, base_z_m)
        key   = (uname, base_lv.Id.IntegerValue)
        ex    = existing_cols.get(key)
        if ex:
            try:
                if hasattr(ex.Location, "Point"): ex.Location.Point = center
            except Exception: pass
            if ex.GetTypeId() != ctype.Id: ex.Symbol = ctype
            safe_set(ex.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM), top_lv.Id)
            safe_set(ex.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM), 0.0)
            safe_set(ex.LookupParameter("Comments"), uname)
            col_updated += 1
        else:
            col = doc.Create.NewFamilyInstance(center, ctype, base_lv, StructuralType.Column)
            safe_set(col.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM), top_lv.Id)
            safe_set(col.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM), 0.0)
            safe_set(col.LookupParameter("Comments"), uname)
            existing_cols[key] = col
            created_col_ids.append(col.Id)
            col_created += 1

    msgs.append("COLUMNS   created:{:>4}  updated:{:>4}  skipped:{:>4}".format(col_created, col_updated, col_skipped))

    # ── Beams ──────────────────────────────────────────────────────────────────────
    existing_beams = {}
    for b in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType():
        try:
            lv_id = b.LevelId
            if not lv_id: continue
            cm = b.LookupParameter("Comments"); nm = cm.AsString() if cm and cm.HasValue else None
            if nm: existing_beams[(nm, lv_id.IntegerValue)] = b
        except Exception: pass

    beam_created = beam_updated = beam_skipped = 0
    for name, top_z_m, pts in beam_data:
        pts_m = [XYZ(p[0], p[1], p[2]) for p in pts]
        edges = sorted([
            (distance_mm(pts_m[0], pts_m[1]), pts_m[0], pts_m[1]),
            (distance_mm(pts_m[1], pts_m[2]), pts_m[1], pts_m[2]),
            (distance_mm(pts_m[2], pts_m[3]), pts_m[2], pts_m[3]),
            (distance_mm(pts_m[3], pts_m[0]), pts_m[3], pts_m[0]),
        ], key=lambda e: e[0])

        w_mm  = edges[0][0]
        d_mm  = max(m_to_mm(abs(top_z_m - pts[0][2])), 1)
        a1, a2 = edges[0][1], edges[0][2]
        b1, b2 = edges[1][1], edges[1][2]
        top_ft = clean_ft(m_to_ft(top_z_m))
        mid1 = XYZ(clean_ft(m_to_ft((a1.X+a2.X)/2)), clean_ft(m_to_ft((a1.Y+a2.Y)/2)), top_ft)
        mid2 = XYZ(clean_ft(m_to_ft((b1.X+b2.X)/2)), clean_ft(m_to_ft((b1.Y+b2.Y)/2)), top_ft)
        if mid1.DistanceTo(mid2) < 0.01: beam_skipped += 1; continue

        lv = get_or_create_level(top_ft, top_z_m)
        if lv is None or lv.Id == ElementId.InvalidElementId:
            msgs.append("SKIPPED BEAM {} - invalid level".format(name)); beam_skipped += 1; continue

        btype = get_beam_type(w_mm, d_mm)
        umark = "{} {} @{:.1f}m".format(level_name_map.get(top_z_m, "Lv"), name, top_z_m)
        key   = (umark, lv.Id.IntegerValue)
        ex    = existing_beams.get(key)
        if ex:
            if ex.GetTypeId() != btype.Id: ex.Symbol = btype
            safe_set(ex.LookupParameter("Comments"), umark); beam_updated += 1
        else:
            beam_line = Line.CreateBound(mid1, mid2)
            nb = doc.Create.NewFamilyInstance(beam_line, btype, lv, StructuralType.Beam)
            safe_set(nb.LookupParameter("Comments"), umark)
            safe_set(nb.LookupParameter("Mark"),     umark)
            existing_beams[key] = nb
            created_beam_ids.append(nb.Id)
            beam_created += 1

    msgs.append("BEAMS     created:{:>4}  updated:{:>4}  skipped:{:>4}".format(beam_created, beam_updated, beam_skipped))

    # ── Slabs ────────────────────────────────────────────────────────────────────────
    existing_floors = {}
    for fl in FilteredElementCollector(doc).OfClass(Floor).WhereElementIsNotElementType():
        try:
            cm = fl.LookupParameter("Comments"); nm = cm.AsString() if cm and cm.HasValue else None
            lp = fl.get_Parameter(BuiltInParameter.LEVEL_PARAM)
            lv = doc.GetElement(lp.AsElementId()) if lp else None
            if nm and lv: existing_floors[(nm, lv.Id.IntegerValue)] = fl
        except Exception: pass

    slab_created = slab_updated = slab_skipped = 0
    if floor_type is None and slab_data:
        msgs.append("SLABS     skipped - no floor type loaded in project")
    else:
        for name, top_z_m, base_z_m, pts in slab_data:
            thick_mm = max((top_z_m - base_z_m) * 1000.0, 125.0)
            top_ft   = clean_ft(m_to_ft(top_z_m))
            lv       = get_or_create_level(top_ft, top_z_m)
            uname    = "{} @{:.1f}m".format(name, top_z_m)
            ex = existing_floors.get((uname, lv.Id.IntegerValue))
            if ex:
                try: doc.Delete(ex.Id)
                except Exception: pass
                slab_updated += 1
            ftype   = get_floor_type(thick_mm)
            off_pts = offset_rectangle(pts, top_ft)
            if off_pts is None: slab_skipped += 1; continue
            loop = CurveLoop()
            for i in range(4): loop.Append(Line.CreateBound(off_pts[i], off_pts[(i+1)%4]))
            try:
                floor = Floor.Create(doc, [loop], ftype.Id, lv.Id)
                safe_set(floor.LookupParameter("Comments"), uname)
                existing_floors[(uname, lv.Id.IntegerValue)] = floor
                created_floor_ids.append(floor.Id)
                slab_created += 1
            except Exception: slab_skipped += 1

        msgs.append("SLABS     created:{:>4}  updated:{:>4}  skipped:{:>4}".format(slab_created, slab_updated, slab_skipped))

    t2.Commit()

except Exception as e:
    t2.RollBack()
    forms.alert("Error during element creation:\n{}".format(e), exitscript=True)

# ── TX 4: Geometry joining ─────────────────────────────────────────────────────────
# Separate committed transaction so all element geometry is fully resolved before
# JoinGeometryUtils runs (the key fix for column-slab / column-beam join failures).

# Loose bounding-box prefiltering occasionally joins a pair whose solids do not
# actually share volume, which makes Revit post the benign warning
# "Highlighted elements are joined but do not intersect" at commit. The join is
# harmless (geometry is correct), so this preprocessor silently dismisses join
# warnings raised inside THIS transaction only - other transactions keep Revit's
# default handling, so genuine issues elsewhere still surface.
class _JoinWarningSwallower(IFailuresPreprocessor):
    def PreprocessFailures(self, fa):
        try:
            non_intersect = BuiltInFailures.JoinElementsFailures.CannotKeepJoined
        except Exception:
            non_intersect = None
        try:
            for f in list(fa.GetFailureMessages()):
                try:
                    if f.GetSeverity() != FailureSeverity.Warning:
                        continue
                    fid = f.GetFailureDefinitionId()
                    # Match the specific join warning when available; otherwise
                    # match by description text as a language-tolerant fallback.
                    desc = (f.GetDescriptionText() or "").lower()
                    if (non_intersect is not None and fid == non_intersect) \
                       or ("joined but do not intersect" in desc) \
                       or ("do not intersect" in desc):
                        fa.DeleteWarning(f)
                except Exception:
                    pass
        except Exception:
            pass
        return FailureProcessingResult.Continue

t3 = Transaction(doc, "INP2BIM: Join Geometry")
_t3_opts = t3.GetFailureHandlingOptions()
_t3_opts.SetFailuresPreprocessor(_JoinWarningSwallower())
_t3_opts.SetClearAfterRollback(True)
t3.SetFailureHandlingOptions(_t3_opts)
t3.Start()
joined = join_failed = 0

try:
    all_cols   = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType().ToElements())
    all_beams  = list(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType().ToElements())
    all_floors = list(FilteredElementCollector(doc).OfClass(Floor).WhereElementIsNotElementType().ToElements())

    def bb(elem):
        return elem.get_BoundingBox(None)

    def overlaps(bb1, bb2, tol=0.08):
        if bb1 is None or bb2 is None: return False
        return not (bb1.Max.X + tol < bb2.Min.X or bb1.Min.X - tol > bb2.Max.X or
                    bb1.Max.Y + tol < bb2.Min.Y or bb1.Min.Y - tol > bb2.Max.Y or
                    bb1.Max.Z + tol < bb2.Min.Z or bb1.Min.Z - tol > bb2.Max.Z)

    def try_join_ordered(dominant, subordinate):
        """Join two elements ensuring dominant cuts subordinate (Column > Beam > Slab)."""
        global joined, join_failed
        try:
            if not JoinGeometryUtils.AreElementsJoined(doc, dominant, subordinate):
                JoinGeometryUtils.JoinGeometry(doc, dominant, subordinate)
                joined += 1
            try:
                if not JoinGeometryUtils.IsCuttingElementInJoin(doc, dominant, subordinate):
                    JoinGeometryUtils.SwitchJoinOrder(doc, dominant, subordinate)
            except Exception:
                pass
        except Exception:
            join_failed += 1

    for col in all_cols:
        bbc = bb(col)
        for beam in all_beams:
            if overlaps(bbc, bb(beam)): try_join_ordered(col, beam)

    for col in all_cols:
        bbc = bb(col)
        for floor in all_floors:
            if overlaps(bbc, bb(floor)): try_join_ordered(col, floor)

    for beam in all_beams:
        bbb = bb(beam)
        for floor in all_floors:
            if overlaps(bbb, bb(floor)): try_join_ordered(beam, floor)

    msgs.append("JOINS     applied:{:>4}  skipped:{:>4}".format(joined, join_failed))
    t3.Commit()

except Exception as e:
    t3.RollBack()
    msgs.append("JOIN ERROR: {}".format(e))

# ── Output ──────────────────────────────────────────────────────────────────────────
output.print_md("## INP to BIM  -  Complete")
output.print_md("    Column type : {}".format(col_disp))
output.print_md("    Beam type   : {}".format(beam_disp))
output.print_md("    Slab type   : {}{}".format(floor_disp, "" if floor_is_conc else "  (not detected as concrete)"))
for m in msgs:
    output.print_md("    " + m)

# ════════════════════════════════════════════════════════════════════════════════
#  BOQ  &  MATERIAL TAKE-OFF  ->  EXCEL
#  Read-only post-process. Does NOT touch the parsing / generation / join logic.
#  Reads the committed model geometry, then writes a multi-sheet workbook:
#     Columns | Beams | Slabs | Summary | BOQ
#  Concrete volume = NET solid volume (after joins) -> no double counting.
# ════════════════════════════════════════════════════════════════════════════════

# ── Editable rates / estimating assumptions (change here or in Excel) ────────────
RATE_CONCRETE   = 4000.0   # Rs per cubic metre
RATE_FORMWORK   = 300.0    # Rs per square metre
RATE_STEEL      = 70.0     # Rs per kilogram
STEEL_KGM3_COL  = 120.0    # reinforcement estimate, kg per m3 of column concrete
STEEL_KGM3_BEAM = 110.0    # kg per m3 of beam concrete
STEEL_KGM3_SLAB = 80.0     # kg per m3 of slab concrete
CONCRETE_ONLY   = False    # True -> export only elements whose material is concrete

# Unit conversions (Revit internal feet -> metric)
_CF_M3 = 0.028316846592    # cubic feet  -> cubic metres
_SF_M2 = 0.09290304        # square feet -> square metres
_FT_MM = 304.8             # feet -> millimetres
_FT_M  = 0.3048            # feet -> metres

try:
    from System import Activator, Type, Array, Object, DateTime

    _geo_opt = Options()
    _geo_opt.ComputeReferences = False
    try: _geo_opt.DetailLevel = ViewDetailLevel.Medium
    except Exception: pass

    # ── element read helpers ─────────────────────────────────────────────────────
    def _pdbl(el, bip):
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue: return p.AsDouble()
        except Exception: pass
        return None

    def _mark_of(el):
        for pn in (BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
                   BuiltInParameter.ALL_MODEL_MARK):
            try:
                p = el.get_Parameter(pn)
                if p and p.HasValue and p.AsString(): return p.AsString()
            except Exception: pass
        return "Id {}".format(el.Id.IntegerValue)

    def _level_of(el):
        lv = None
        try:
            lid = el.LevelId
            if lid and lid != ElementId.InvalidElementId:
                lv = doc.GetElement(lid)
        except Exception: pass
        if lv is None:
            for bip in (BuiltInParameter.LEVEL_PARAM,
                        BuiltInParameter.SCHEDULE_LEVEL_PARAM,
                        BuiltInParameter.FAMILY_LEVEL_PARAM,
                        BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                        BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM):
                try:
                    p = el.get_Parameter(bip)
                    if p and p.HasValue:
                        e = doc.GetElement(p.AsElementId())
                        if e is not None: lv = e; break
                except Exception: pass
        if lv is not None:
            try: return lv.Name, lv.Elevation
            except Exception: pass
        return "-", 0.0

    def _material_name(el):
        for src in (el, doc.GetElement(el.GetTypeId())):
            try:
                p = src.get_Parameter(BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                if p and p.HasValue:
                    m = doc.GetElement(p.AsElementId())
                    if m is not None and m.Name: return m.Name
            except Exception: pass
        return "-"

    def _is_concrete_el(el):
        for src in (el, doc.GetElement(el.GetTypeId())):
            try:
                p = src.get_Parameter(BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                if p and p.HasValue:
                    m = doc.GetElement(p.AsElementId())
                    if _material_is_concrete(m): return True
            except Exception: pass
        try:
            t = doc.GetElement(el.GetTypeId())
            if _text_is_concrete(get_family_name(t) if hasattr(t, "Family") else "",
                                 get_element_name(t)): return True
        except Exception: pass
        return False

    def _type_bh_mm(el):
        t = doc.GetElement(el.GetTypeId())
        def g(n):
            try:
                p = t.LookupParameter(n)
                if p and p.StorageType == StorageType.Double and p.HasValue:
                    return p.AsDouble() * _FT_MM
            except Exception: pass
            return None
        b, h = g("b"), g("h")
        if b is None or h is None:
            m = re.search(r'(\d+(?:\.\d+)?)\s*[xX]\s*(\d+(?:\.\d+)?)', get_element_name(t))
            if m:
                if b is None: b = float(m.group(1))
                if h is None: h = float(m.group(2))
        return (b or 0.0), (h or 0.0)

    def _solid_vol_m3(el):
        tot = 0.0
        try:
            ge = el.get_Geometry(_geo_opt)
            if ge:
                for g in ge:
                    try:
                        if isinstance(g, Solid):
                            if g.Volume > 1e-9: tot += g.Volume
                        elif isinstance(g, GeometryInstance):
                            for gg in g.GetInstanceGeometry():
                                if isinstance(gg, Solid) and gg.Volume > 1e-9: tot += gg.Volume
                    except Exception: pass
        except Exception: pass
        return tot * _CF_M3

    def _col_length_m(el):
        try:
            bl = doc.GetElement(el.get_Parameter(BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).AsElementId())
            tl = doc.GetElement(el.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).AsElementId())
            bo = _pdbl(el, BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM) or 0.0
            to = _pdbl(el, BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM) or 0.0
            if bl and tl:
                return ((tl.Elevation + to) - (bl.Elevation + bo)) * _FT_M
        except Exception: pass
        bb = el.get_BoundingBox(None)
        return abs(bb.Max.Z - bb.Min.Z) * _FT_M if bb else 0.0

    def _beam_length_m(el):
        try:
            loc = el.Location
            if hasattr(loc, "Curve"): return loc.Curve.Length * _FT_M
        except Exception: pass
        bb = el.get_BoundingBox(None)
        return max(abs(bb.Max.X - bb.Min.X), abs(bb.Max.Y - bb.Min.Y)) * _FT_M if bb else 0.0

    def _slab_thk_mm(el):
        try:
            cs = doc.GetElement(el.GetTypeId()).GetCompoundStructure()
            if cs: return cs.GetWidth() * _FT_MM
        except Exception: pass
        return 0.0

    # ── collect elements ─────────────────────────────────────────────────────────
    def _collect(coll):
        out = [e for e in coll if e is not None]
        if CONCRETE_ONLY:
            out = [e for e in out if _is_concrete_el(e)]
        return sorted(out, key=lambda e: (_level_of(e)[1], _mark_of(e)))

    col_els  = _collect(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralColumns).WhereElementIsNotElementType())
    beam_els = _collect(FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType())
    slab_els = _collect(FilteredElementCollector(doc).OfClass(Floor).WhereElementIsNotElementType())

    # ── build rows + running totals ──────────────────────────────────────────────
    col_rows = []; col_vol = col_fw = col_len = 0.0
    for i, e in enumerate(col_els, 1):
        b, h = _type_bh_mm(e); L = _col_length_m(e); v = _solid_vol_m3(e)
        fw = 2.0 * ((b/1000.0) + (h/1000.0)) * L
        col_vol += v; col_fw += fw; col_len += L
        col_rows.append([i, _mark_of(e), _level_of(e)[0], get_element_name(doc.GetElement(e.GetTypeId())),
                         _material_name(e), round(b), round(h), round(L, 3), round(v, 4), round(fw, 3)])

    beam_rows = []; beam_vol = beam_fw = beam_len = 0.0
    for i, e in enumerate(beam_els, 1):
        b, h = _type_bh_mm(e); L = _beam_length_m(e); v = _solid_vol_m3(e)
        fw = ((b/1000.0) + 2.0*(h/1000.0)) * L
        beam_vol += v; beam_fw += fw; beam_len += L
        beam_rows.append([i, _mark_of(e), _level_of(e)[0], get_element_name(doc.GetElement(e.GetTypeId())),
                          _material_name(e), round(b), round(h), round(L, 3), round(v, 4), round(fw, 3)])

    slab_rows = []; slab_vol = slab_fw = slab_area = 0.0
    for i, e in enumerate(slab_els, 1):
        thk = _slab_thk_mm(e)
        a = _pdbl(e, BuiltInParameter.HOST_AREA_COMPUTED)
        area = (a * _SF_M2) if a else 0.0
        v = _pdbl(e, BuiltInParameter.HOST_VOLUME_COMPUTED)
        vol = (v * _CF_M3) if v else _solid_vol_m3(e)
        fw = area
        slab_vol += vol; slab_fw += fw; slab_area += area
        slab_rows.append([i, _mark_of(e), _level_of(e)[0], get_element_name(doc.GetElement(e.GetTypeId())),
                          _material_name(e), round(thk), round(area, 3), round(vol, 4), round(fw, 3)])

    steel_col  = col_vol  * STEEL_KGM3_COL
    steel_beam = beam_vol * STEEL_KGM3_BEAM
    steel_slab = slab_vol * STEEL_KGM3_SLAB
    tot_vol    = col_vol + beam_vol + slab_vol
    tot_fw     = col_fw + beam_fw + slab_fw
    tot_steel  = steel_col + steel_beam + steel_slab

    if not (col_rows or beam_rows or slab_rows):
        output.print_md("    BOQ export skipped: no structural elements found.")
    else:
        # ── Excel colours / constants ────────────────────────────────────────────
        def _xc(r, g, b): return r + g*256 + b*65536
        CLR_TITLE = _xc(31, 58, 90); CLR_HEAD = _xc(0, 99, 177)
        CLR_TOT   = _xc(221, 229, 232); CLR_WHITE = _xc(255, 255, 255)
        XL_CENTER = -4108; XL_LEFT = -4131; FMT_RS = u"\u20b9#,##0.00"

        def _build_paths():
            base = os.path.dirname(file_path)
            if not base or not os.path.isdir(base):
                base = os.environ.get("TEMP") or os.path.expanduser("~")
            stamp = DateTime.Now.ToString("yyyyMMdd_HHmmss")
            root  = os.path.splitext(os.path.basename(file_path))[0] or "INP"
            return base, "{}_BOQ_{}".format(root, stamp)

        base_dir, file_root = _build_paths()

        # ── try Excel (COM, late-bound) ──────────────────────────────────────────
        try:
            xlapp = Activator.CreateInstance(Type.GetTypeFromProgID("Excel.Application"))
            xlapp.DisplayAlerts = False
            xlapp.ScreenUpdating = False
            try: xlapp.SheetsInNewWorkbook = 1
            except Exception: pass
            wb = xlapp.Workbooks.Add()
            _defaults = [wb.Worksheets[i+1] for i in range(wb.Worksheets.Count)]

            def add_ws(name):
                ws = wb.Worksheets.Add(After=wb.Worksheets[wb.Worksheets.Count])
                ws.Name = name
                return ws

            def put_block(ws, top, left, data):
                if not data: return None
                nr, nc = len(data), len(data[0])
                arr = Array.CreateInstance(Object, nr, nc)
                for ii in range(nr):
                    for jj in range(nc):
                        arr[ii, jj] = data[ii][jj]
                rng = ws.Range[ws.Cells[top, left], ws.Cells[top+nr-1, left+nc-1]]
                rng.Value2 = arr
                return rng

            def write_table(ws, title, headers, rows, fmts=None, totals=None):
                nc = len(headers)
                ws.Cells[1, 1].Value2 = title
                tr = ws.Range[ws.Cells[1, 1], ws.Cells[1, nc]]
                tr.Merge(); tr.Font.Bold = True; tr.Font.Size = 13
                tr.Interior.Color = CLR_TITLE; tr.Font.Color = CLR_WHITE
                tr.HorizontalAlignment = XL_CENTER
                put_block(ws, 2, 1, [headers])
                hr = ws.Range[ws.Cells[2, 1], ws.Cells[2, nc]]
                hr.Font.Bold = True; hr.Interior.Color = CLR_HEAD
                hr.Font.Color = CLR_WHITE; hr.HorizontalAlignment = XL_CENTER
                last = 2
                if rows:
                    put_block(ws, 3, 1, rows); last = 2 + len(rows)
                if totals:
                    put_block(ws, last+1, 1, [totals])
                    tt = ws.Range[ws.Cells[last+1, 1], ws.Cells[last+1, nc]]
                    tt.Font.Bold = True; tt.Interior.Color = CLR_TOT
                    last += 1
                if fmts:
                    for c0, f in fmts.items():
                        ws.Range[ws.Cells[3, c0+1], ws.Cells[last, c0+1]].NumberFormat = f
                tbl = ws.Range[ws.Cells[2, 1], ws.Cells[last, nc]]
                tbl.Borders.LineStyle = 1
                ws.Columns.AutoFit()
                try:
                    ws.Activate(); ws.Range["A3"].Select()
                    xlapp.ActiveWindow.FreezePanes = True
                except Exception: pass
                return last

            # Columns sheet
            ws = add_ws("Columns")
            write_table(ws, "COLUMN SCHEDULE  -  Concrete Take-Off",
                ["#", "Mark", "Level", "Type", "Material", "b (mm)", "h (mm)",
                 "Length (m)", "Concrete (m\u00b3)", "Formwork (m\u00b2)"],
                col_rows,
                fmts={5:"0", 6:"0", 7:"0.000", 8:"0.000", 9:"0.000"},
                totals=["", "TOTAL", "", "", "", "", "", round(col_len,3), round(col_vol,4), round(col_fw,3)])

            # Beams sheet
            ws = add_ws("Beams")
            write_table(ws, "BEAM SCHEDULE  -  Concrete Take-Off",
                ["#", "Mark", "Level", "Type", "Material", "b (mm)", "h (mm)",
                 "Length (m)", "Concrete (m\u00b3)", "Formwork (m\u00b2)"],
                beam_rows,
                fmts={5:"0", 6:"0", 7:"0.000", 8:"0.000", 9:"0.000"},
                totals=["", "TOTAL", "", "", "", "", "", round(beam_len,3), round(beam_vol,4), round(beam_fw,3)])

            # Slabs sheet
            ws = add_ws("Slabs")
            write_table(ws, "SLAB SCHEDULE  -  Concrete Take-Off",
                ["#", "Mark", "Level", "Type", "Material", "Thickness (mm)",
                 "Area (m\u00b2)", "Concrete (m\u00b3)", "Formwork (m\u00b2)"],
                slab_rows,
                fmts={5:"0", 6:"0.000", 7:"0.000", 8:"0.000"},
                totals=["", "TOTAL", "", "", "", "", round(slab_area,3), round(slab_vol,4), round(slab_fw,3)])

            # Summary sheet
            ws = add_ws("Summary")
            summary_rows = [
                ["Columns", len(col_rows), round(col_vol,3), round(col_fw,3), round(steel_col,1)],
                ["Beams",   len(beam_rows), round(beam_vol,3), round(beam_fw,3), round(steel_beam,1)],
                ["Slabs",   len(slab_rows), round(slab_vol,3), round(slab_fw,3), round(steel_slab,1)],
            ]
            last = write_table(ws, "PROJECT SUMMARY  -  Material Take-Off",
                ["Category", "Count", "Concrete (m\u00b3)", "Formwork (m\u00b2)", "Steel est. (kg)"],
                summary_rows,
                fmts={2:"0.000", 3:"0.000", 4:"0.0"},
                totals=["TOTAL", len(col_rows)+len(beam_rows)+len(slab_rows),
                        round(tot_vol,3), round(tot_fw,3), round(tot_steel,1)])
            notes = [
                ["", "", "", "", ""],
                ["Source file", os.path.basename(file_path), "", "", ""],
                ["Generated",   DateTime.Now.ToString("yyyy-MM-dd HH:mm"), "", "", ""],
                ["", "", "", "", ""],
                ["Assumptions", "", "", "", ""],
                ["Concrete rate (Rs/m\u00b3)", RATE_CONCRETE, "", "", ""],
                ["Formwork rate (Rs/m\u00b2)", RATE_FORMWORK, "", "", ""],
                ["Steel rate (Rs/kg)", RATE_STEEL, "", "", ""],
                ["Steel est. kg/m\u00b3 (col/beam/slab)",
                 "{}/{}/{}".format(STEEL_KGM3_COL, STEEL_KGM3_BEAM, STEEL_KGM3_SLAB), "", "", ""],
                ["Concrete volume basis", "Net solid (after joins)", "", "", ""],
                ["Note", "Formwork & steel are estimates.", "", "", ""],
            ]
            put_block(ws, last+2, 1, notes)
            ws.Columns.AutoFit()

            # BOQ sheet
            ws = add_ws("BOQ")
            boq = [
                [1, "Concrete in columns",            "Cu.m", round(col_vol,3),  RATE_CONCRETE],
                [2, "Concrete in beams",              "Cu.m", round(beam_vol,3), RATE_CONCRETE],
                [3, "Concrete in slabs",              "Cu.m", round(slab_vol,3), RATE_CONCRETE],
                [4, "Formwork to columns",            "Sq.m", round(col_fw,3),   RATE_FORMWORK],
                [5, "Formwork to beams",              "Sq.m", round(beam_fw,3),  RATE_FORMWORK],
                [6, "Formwork to slabs (soffit)",     "Sq.m", round(slab_fw,3),  RATE_FORMWORK],
                [7, "Reinforcement steel (estimated)", "kg",  round(tot_steel,1), RATE_STEEL],
            ]
            headers = ["Item", "Description", "Unit", "Quantity", "Rate (Rs)", "Amount (Rs)"]
            ws.Cells[1,1].Value2 = "BILL OF QUANTITIES"
            tr = ws.Range[ws.Cells[1,1], ws.Cells[1,6]]
            tr.Merge(); tr.Font.Bold=True; tr.Font.Size=13
            tr.Interior.Color=CLR_TITLE; tr.Font.Color=CLR_WHITE; tr.HorizontalAlignment=XL_CENTER
            put_block(ws, 2, 1, [headers])
            hr = ws.Range[ws.Cells[2,1], ws.Cells[2,6]]
            hr.Font.Bold=True; hr.Interior.Color=CLR_HEAD; hr.Font.Color=CLR_WHITE; hr.HorizontalAlignment=XL_CENTER
            put_block(ws, 3, 1, boq)             # cols A..E ; F = Amount via formula
            first_r, last_r = 3, 3 + len(boq) - 1
            ws.Range[ws.Cells[3,4], ws.Cells[last_r,4]].NumberFormat = "#,##0.000"
            ws.Range[ws.Cells[3,5], ws.Cells[last_r,6]].NumberFormat = FMT_RS   # General->set before formula
            for r in range(first_r, last_r+1):
                ws.Cells[r,6].NumberFormat = FMT_RS
                ws.Cells[r,6].Formula = "=D{0}*E{0}".format(r)
            # total row
            trow = last_r + 1
            ws.Cells[trow,2].Value2 = "GRAND TOTAL"
            ws.Cells[trow,6].NumberFormat = FMT_RS
            ws.Cells[trow,6].Formula = "=SUM(F{0}:F{1})".format(first_r, last_r)
            tt = ws.Range[ws.Cells[trow,1], ws.Cells[trow,6]]
            tt.Font.Bold=True; tt.Interior.Color=CLR_TOT
            ws.Range[ws.Cells[2,1], ws.Cells[trow,6]].Borders.LineStyle = 1
            ws.Columns.AutoFit()

            for ds in _defaults:
                try: ds.Delete()
                except Exception: pass

            xlsx_path = os.path.join(base_dir, file_root + ".xlsx")
            try:
                wb.SaveAs(xlsx_path, 51)
            except Exception:
                base_dir = os.environ.get("TEMP") or os.path.expanduser("~")
                xlsx_path = os.path.join(base_dir, file_root + ".xlsx")
                wb.SaveAs(xlsx_path, 51)

            xlapp.ScreenUpdating = True
            xlapp.DisplayAlerts = True
            try: wb.Worksheets["Summary"].Activate()
            except Exception: pass
            xlapp.Visible = True

            output.print_md("## BOQ / Material Take-Off")
            output.print_md("    Concrete (m\u00b3)  cols:{:.3f}  beams:{:.3f}  slabs:{:.3f}  total:{:.3f}".format(
                col_vol, beam_vol, slab_vol, tot_vol))
            output.print_md("    Formwork (m\u00b2)  total:{:.2f}    Steel est.(kg)  total:{:.0f}".format(tot_fw, tot_steel))
            output.print_md("    Workbook : {}".format(xlsx_path))

        except Exception as _xerr:
            # ── CSV fallback (Excel unavailable) ─────────────────────────────────
            import csv
            def _csv(name, headers, rows, totals=None):
                p = os.path.join(base_dir, "{}_{}.csv".format(file_root, name))
                with open(p, 'wb') as f:
                    w = csv.writer(f)
                    w.writerow(headers)
                    for r in rows: w.writerow([("" if x is None else x) for x in r])
                    if totals: w.writerow([("" if x is None else x) for x in totals])
                return p
            _csv("Columns", ["#","Mark","Level","Type","Material","b_mm","h_mm","Length_m","Concrete_m3","Formwork_m2"],
                 col_rows, ["","TOTAL","","","","","",round(col_len,3),round(col_vol,4),round(col_fw,3)])
            _csv("Beams", ["#","Mark","Level","Type","Material","b_mm","h_mm","Length_m","Concrete_m3","Formwork_m2"],
                 beam_rows, ["","TOTAL","","","","","",round(beam_len,3),round(beam_vol,4),round(beam_fw,3)])
            _csv("Slabs", ["#","Mark","Level","Type","Material","Thickness_mm","Area_m2","Concrete_m3","Formwork_m2"],
                 slab_rows, ["","TOTAL","","","","",round(slab_area,3),round(slab_vol,4),round(slab_fw,3)])
            sp = _csv("Summary", ["Category","Count","Concrete_m3","Formwork_m2","Steel_kg"],
                 [["Columns",len(col_rows),round(col_vol,3),round(col_fw,3),round(steel_col,1)],
                  ["Beams",len(beam_rows),round(beam_vol,3),round(beam_fw,3),round(steel_beam,1)],
                  ["Slabs",len(slab_rows),round(slab_vol,3),round(slab_fw,3),round(steel_slab,1)]],
                 ["TOTAL",len(col_rows)+len(beam_rows)+len(slab_rows),round(tot_vol,3),round(tot_fw,3),round(tot_steel,1)])
            output.print_md("## BOQ / Material Take-Off  (CSV fallback)")
            output.print_md("    Excel unavailable: {}".format(_xerr))
            output.print_md("    CSV files written next to: {}".format(sp))

except Exception as _boqerr:
    output.print_md("    BOQ export skipped: {}".format(_boqerr))


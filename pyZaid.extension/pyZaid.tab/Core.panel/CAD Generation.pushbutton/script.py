#! python3
# -*- coding: utf-8 -*-
"""
CAD to BIM Conversion Tool - Pure CPython3 Implementation
Extracts CAD geometry and generates native Revit elements.
Target: CPython 3 / Revit 2025 / PythonNet
"""

import clr
import sys
from collections import defaultdict
from dataclasses import dataclass, field

# ── SECTION 1: IMPORTS & CONSTANTS ───────────────────────────────────────────
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI
from Autodesk.Revit.UI.Selection import ObjectType
import Autodesk.Revit.Exceptions as RevitExceptions

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
import System.Windows
import System.Windows.Controls
from System.Windows.Markup import XamlReader
from System.Collections.Generic import List
from System.Collections import ArrayList

# Constants
KEYWORD_MAP = {
    "col": "Column", "column": "Column",
    "wall": "Wall", "wl": "Wall",
    "beam": "Beam", "bm": "Beam", "framing": "Beam",
    "slab": "Slab", "floor": "Slab", "fl": "Slab",
}

UNIT_MM = DB.UnitTypeId.Millimeters
MAX_WALL_THICKNESS_MM = 500.0

@dataclass
class ConversionSettings:
    cad_instance: DB.Element
    layer_mapping: dict = field(default_factory=dict)
    
    col_type_id: DB.ElementId = None
    col_base_level_id: DB.ElementId = None
    col_top_offset_ft: float = 0.0
    
    wall_type_id: DB.ElementId = None
    wall_base_level_id: DB.ElementId = None
    wall_height_ft: float = 10.0
    wall_structural: bool = False
    
    beam_type_id: DB.ElementId = None
    beam_level_id: DB.ElementId = None
    beam_z_offset_ft: float = 0.0
    beam_usage: int = DB.Structure.StructuralType.Beam
    
    floor_type_id: DB.ElementId = None
    floor_level_id: DB.ElementId = None
    floor_structural: bool = False
    
    tolerance_ft: float = 0.08
    min_length_ft: float = 0.33
    duplicate_check: bool = False
    preview_mode: bool = False

# ── SECTION 2: HELPER UTILITIES ──────────────────────────────────────────────

def convert_mm_to_ft(mm_value: float) -> float:
    return DB.UnitUtils.ConvertToInternalUnits(mm_value, UNIT_MM)

def get_all_cad_instances(doc: DB.Document):
    """Retrieves all ImportInstance files in the entire project."""
    return DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance).WhereElementIsNotElementType().ToElements()

def flatten_line_to_z(line: DB.Line, target_z: float) -> DB.Line:
    pt1 = DB.XYZ(line.GetEndPoint(0).X, line.GetEndPoint(0).Y, target_z)
    pt2 = DB.XYZ(line.GetEndPoint(1).X, line.GetEndPoint(1).Y, target_z)
    if pt1.DistanceTo(pt2) < convert_mm_to_ft(1.0):
        return None
    return DB.Line.CreateBound(pt1, pt2)

def extract_wall_centerlines(lines: list, max_thickness_ft: float) -> list:
    unprocessed = list(lines)
    centerlines = []
    
    while unprocessed:
        base_line = unprocessed.pop(0)
        base_dir = base_line.Direction
        base_mid = (base_line.GetEndPoint(0) + base_line.GetEndPoint(1)) / 2.0
        
        best_match, best_dist = None, max_thickness_ft
        
        for candidate in unprocessed:
            cand_dir = candidate.Direction
            if abs(base_dir.DotProduct(cand_dir)) > 0.98:
                dist = candidate.Distance(base_mid)
                if dist < best_dist:
                    best_dist = dist
                    best_match = candidate
                    
        if best_match:
            unprocessed.remove(best_match)
            p1_base, p2_base = base_line.GetEndPoint(0), base_line.GetEndPoint(1)
            
            if p1_base.DistanceTo(best_match.GetEndPoint(0)) < p1_base.DistanceTo(best_match.GetEndPoint(1)):
                avg_p1 = (p1_base + best_match.GetEndPoint(0)) / 2.0
                avg_p2 = (p2_base + best_match.GetEndPoint(1)) / 2.0
            else:
                avg_p1 = (p1_base + best_match.GetEndPoint(1)) / 2.0
                avg_p2 = (p2_base + best_match.GetEndPoint(0)) / 2.0
            
            try:
                centerlines.append(DB.Line.CreateBound(avg_p1, avg_p2))
            except Exception:
                pass
        else:
            centerlines.append(base_line)
            
    return centerlines

def is_duplicate(doc: DB.Document, category_id: DB.BuiltInCategory, points: list, height_ft: float, tolerance_ft: float) -> bool:
    """Safely checks if an element exists within a bounding box derived from given points."""
    xs = [p.X for p in points]
    ys = [p.Y for p in points]
    zs = [p.Z for p in points]
    
    # Pad by at least 1.0 ft to ensure the Outline is never "empty" or flat
    pad = max(tolerance_ft, 1.0)
    
    # Mathematically guarantees Max > Min in all dimensions
    min_pt = DB.XYZ(min(xs) - pad, min(ys) - pad, min(zs) - pad)
    max_pt = DB.XYZ(max(xs) + pad, max(ys) + pad, max(zs) + height_ft + pad)
    
    outline = DB.Outline(min_pt, max_pt)
    bbox_filter = DB.BoundingBoxIntersectsFilter(outline)
    
    return any(DB.FilteredElementCollector(doc).OfCategory(category_id).WherePasses(bbox_filter).ToElements())

# ── SECTION 3: CAD GEOMETRY PARSER ───────────────────────────────────────────

def extract_cad_geometry_recursively(geometry_element, transform: DB.Transform, doc: DB.Document, result_dict: dict):
    if not geometry_element:
        return
    for geom_obj in geometry_element:
        if isinstance(geom_obj, DB.GeometryInstance):
            inst_geom = geom_obj.GetInstanceGeometry()
            new_transform = transform.Multiply(geom_obj.Transform)
            extract_cad_geometry_recursively(inst_geom, new_transform, doc, result_dict)
            continue
            
        style = doc.GetElement(geom_obj.GraphicsStyleId)
        if not style or not isinstance(style, DB.GraphicsStyle):
            continue
            
        layer_name = style.GraphicsStyleCategory.Name
        if isinstance(geom_obj, DB.Line) or isinstance(geom_obj, DB.Arc):
            transformed_curve = geom_obj.CreateTransformed(transform)
            result_dict[layer_name].append(transformed_curve)

def parse_geometry_by_layer(cad_instance: DB.ImportInstance, doc: DB.Document) -> dict:
    result_dict = defaultdict(list)
    geom_elem = cad_instance.get_Geometry(DB.Options())
    extract_cad_geometry_recursively(geom_elem, DB.Transform.Identity, doc, result_dict)
    return result_dict

# ── SECTION 4: ELEMENT CREATORS ──────────────────────────────────────────────

def create_structural_column(doc: DB.Document, curve: DB.Curve, settings: ConversionSettings) -> tuple:
    if not settings.col_type_id or not settings.col_base_level_id: return False, "Missing Column settings."
    mid_point = curve.Evaluate(0.5, True)
    
    if settings.duplicate_check:
        if is_duplicate(doc, DB.BuiltInCategory.OST_StructuralColumns, [mid_point], settings.col_top_offset_ft, settings.tolerance_ft):
            return False, "Duplicate detected."

    symbol = doc.GetElement(settings.col_type_id)
    if not symbol.IsActive: symbol.Activate()
    level = doc.GetElement(settings.col_base_level_id)
    col = doc.Create.NewFamilyInstance(mid_point, symbol, level, DB.Structure.StructuralType.Column)
    
    param = col.get_Parameter(DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM)
    if param: param.Set(settings.col_top_offset_ft)
    return True, "Success"

def create_basic_wall(doc: DB.Document, line: DB.Line, settings: ConversionSettings) -> tuple:
    if line.Length < settings.min_length_ft: return False, "Short line."
    if not settings.wall_type_id or not settings.wall_base_level_id: return False, "Missing settings."

    if settings.duplicate_check:
        pts = [line.GetEndPoint(0), line.GetEndPoint(1)]
        if is_duplicate(doc, DB.BuiltInCategory.OST_Walls, pts, settings.wall_height_ft, settings.tolerance_ft):
            return False, "Duplicate."

    DB.Wall.Create(doc, line, settings.wall_type_id, settings.wall_base_level_id, settings.wall_height_ft, 0.0, False, settings.wall_structural)
    return True, "Success"

def create_structural_beam(doc: DB.Document, line: DB.Line, settings: ConversionSettings) -> tuple:
    if line.Length < settings.min_length_ft: return False, "Short line."
    symbol = doc.GetElement(settings.beam_type_id)
    if not symbol.IsActive: symbol.Activate()
    level = doc.GetElement(settings.beam_level_id)
    beam = doc.Create.NewFamilyInstance(line, symbol, level, DB.Structure.StructuralType.Beam)
    
    param = beam.get_Parameter(DB.BuiltInParameter.Z_OFFSET_VALUE)
    if param: param.Set(settings.beam_z_offset_ft)
    return True, "Success"

def create_architectural_floor(doc: DB.Document, curves: list, settings: ConversionSettings) -> tuple:
    try:
        dotnet_curves = List[DB.Curve]()
        for c in curves: dotnet_curves.Add(c)
        curve_loop = DB.CurveLoop.Create(dotnet_curves)
        
        if not curve_loop.IsOpen():
            loop_list = List[DB.CurveLoop]()
            loop_list.Add(curve_loop)
            DB.Floor.Create(doc, loop_list, settings.floor_type_id, settings.floor_level_id)
            return True, "Success"
        return False, "Loop is open."
    except Exception as e:
        return False, str(e)

# ── SECTION 5: WPF FORM & UI (PURE PYTHONNET) ────────────────────────────────

XAML_STRING = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="CAD to BIM - CPython3" Height="650" Width="700" WindowStartupLocation="CenterScreen">
    <Grid Margin="10">
        <Grid.RowDefinitions>
            <RowDefinition Height="*" />
            <RowDefinition Height="Auto" />
        </Grid.RowDefinitions>
        
        <TabControl Grid.Row="0">
            <!-- CAD SOURCE -->
            <TabItem Header="1. CAD Source">
                <StackPanel Margin="10">
                    <TextBlock Text="Select CAD Instance:" FontWeight="Bold" Margin="0,0,0,5" />
                    <Grid>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="*" />
                            <ColumnDefinition Width="Auto" />
                        </Grid.ColumnDefinitions>
                        <ComboBox x:Name="CadInstanceComboBox" Height="25" Grid.Column="0" Margin="0,0,5,0" />
                        <Button x:Name="BtnPickCad" Content="Pick in View" Width="90" Height="25" Grid.Column="1"/>
                    </Grid>
                </StackPanel>
            </TabItem>
            
            <!-- LAYER MAPPING -->
            <TabItem Header="2. Layer Mapping">
                <Grid Margin="10">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>
                    <TextBlock Text="Map CAD layers to Revit Categories:" FontWeight="Bold" Margin="0,0,0,5" Grid.Row="0"/>
                    <Border BorderBrush="Gray" BorderThickness="1" Grid.Row="1">
                        <ScrollViewer VerticalScrollBarVisibility="Auto">
                            <StackPanel x:Name="LayerMapPanel" Margin="5"/>
                        </ScrollViewer>
                    </Border>
                </Grid>
            </TabItem>
            
            <!-- ELEMENT SETTINGS -->
            <TabItem Header="3. Element Settings">
                <ScrollViewer>
                    <StackPanel Margin="10">
                        <TextBlock Text="Please ensure target Families are already loaded." Foreground="Gray" Margin="0,0,0,10"/>
                        <GroupBox Header="Columns" Margin="0,0,0,10">
                            <UniformGrid Columns="2" Margin="5">
                                <TextBlock Text="Column Type:" VerticalAlignment="Center"/>
                                <ComboBox x:Name="ColTypeCombo" DisplayMemberPath="Name"/>
                                <TextBlock Text="Base Level:" VerticalAlignment="Center"/>
                                <ComboBox x:Name="ColLevelCombo" DisplayMemberPath="Name"/>
                                <TextBlock Text="Top Offset (mm):" VerticalAlignment="Center"/>
                                <TextBox x:Name="ColTopOffset" Text="0"/>
                            </UniformGrid>
                        </GroupBox>

                        <GroupBox Header="Walls" Margin="0,0,0,10">
                            <UniformGrid Columns="2" Margin="5">
                                <TextBlock Text="Wall Type:" VerticalAlignment="Center"/>
                                <ComboBox x:Name="WallTypeCombo" DisplayMemberPath="Name"/>
                                <TextBlock Text="Base Level:" VerticalAlignment="Center"/>
                                <ComboBox x:Name="WallLevelCombo" DisplayMemberPath="Name"/>
                                <TextBlock Text="Height (mm):" VerticalAlignment="Center"/>
                                <TextBox x:Name="WallHeight" Text="3000"/>
                            </UniformGrid>
                        </GroupBox>
                        
                        <GroupBox Header="Beams" Margin="0,0,0,10">
                            <UniformGrid Columns="2" Margin="5">
                                <TextBlock Text="Beam Type:" VerticalAlignment="Center"/>
                                <ComboBox x:Name="BeamTypeCombo" DisplayMemberPath="Name"/>
                                <TextBlock Text="Level:" VerticalAlignment="Center"/>
                                <ComboBox x:Name="BeamLevelCombo" DisplayMemberPath="Name"/>
                            </UniformGrid>
                        </GroupBox>
                        
                        <GroupBox Header="Slabs / Floors">
                            <UniformGrid Columns="2" Margin="5">
                                <TextBlock Text="Floor Type:" VerticalAlignment="Center"/>
                                <ComboBox x:Name="FloorTypeCombo" DisplayMemberPath="Name"/>
                                <TextBlock Text="Level:" VerticalAlignment="Center"/>
                                <ComboBox x:Name="FloorLevelCombo" DisplayMemberPath="Name"/>
                            </UniformGrid>
                        </GroupBox>
                    </StackPanel>
                </ScrollViewer>
            </TabItem>
            
            <!-- OPTIONS -->
            <TabItem Header="4. Options">
                <StackPanel Margin="10">
                    <CheckBox x:Name="CheckDuplicates" Content="Skip Duplicate Elements (Bounding Box)" IsChecked="True" Margin="0,0,0,10"/>
                    <CheckBox x:Name="CheckPreview" Content="Preview Mode (No elements created)" IsChecked="False" Margin="0,0,0,10"/>
                    <TextBlock Text="Minimum Line Length (mm):"/>
                    <TextBox x:Name="TxtMinLength" Text="100" Margin="0,0,0,10"/>
                </StackPanel>
            </TabItem>
        </TabControl>
        
        <StackPanel Grid.Row="1" Orientation="Horizontal" HorizontalAlignment="Right" Margin="0,10,0,0">
            <Button x:Name="BtnCancel" Content="Cancel" Width="80" Margin="5,0" />
            <Button x:Name="BtnRun" Content="Run Conversion" Width="120" Margin="5,0" Background="#FF007ACC" Foreground="White" FontWeight="Bold"/>
        </StackPanel>
    </Grid>
</Window>
"""

class CadToBimForm:
    def __init__(self, doc, uidoc):
        self.doc = doc
        self.uidoc = uidoc
        self.layer_combos = {}  
        self.cad_dict = {}
        
        self.window = XamlReader.Parse(XAML_STRING)
        
        self.CadInstanceComboBox = self.window.FindName("CadInstanceComboBox")
        self.LayerMapPanel = self.window.FindName("LayerMapPanel")
        
        self.ColTypeCombo = self.window.FindName("ColTypeCombo")
        self.ColLevelCombo = self.window.FindName("ColLevelCombo")
        self.ColTopOffset = self.window.FindName("ColTopOffset")
        self.WallTypeCombo = self.window.FindName("WallTypeCombo")
        self.WallLevelCombo = self.window.FindName("WallLevelCombo")
        self.WallHeight = self.window.FindName("WallHeight")
        self.BeamTypeCombo = self.window.FindName("BeamTypeCombo")
        self.BeamLevelCombo = self.window.FindName("BeamLevelCombo")
        self.FloorTypeCombo = self.window.FindName("FloorTypeCombo")
        self.FloorLevelCombo = self.window.FindName("FloorLevelCombo")
        
        self.CheckDuplicates = self.window.FindName("CheckDuplicates")
        self.CheckPreview = self.window.FindName("CheckPreview")
        self.TxtMinLength = self.window.FindName("TxtMinLength")
        
        # Bind Events
        self.CadInstanceComboBox.SelectionChanged += self.OnCadSelected
        self.window.FindName("BtnPickCad").Click += self.OnPickCadClick
        self.window.FindName("BtnCancel").Click += self.OnCancelClick
        self.window.FindName("BtnRun").Click += self.OnRunClick
        
        self.setup_ui()

    def to_dotnet_array(self, py_list):
        arr = ArrayList()
        for item in py_list: arr.Add(item)
        return arr

    def setup_ui(self):
        cad_instances = get_all_cad_instances(self.doc)
        for cad in cad_instances:
            name = cad.Category.Name if cad.Category else cad.Name
            if not name: name = "Unknown CAD"
            display_name = f"{name} [ID: {cad.Id.IntegerValue}]"
            self.cad_dict[display_name] = cad
            
        self.CadInstanceComboBox.ItemsSource = self.to_dotnet_array(list(self.cad_dict.keys()))
        if self.cad_dict: self.CadInstanceComboBox.SelectedIndex = 0
        
        levels = list(DB.FilteredElementCollector(self.doc).OfClass(DB.Level).ToElements())
        levels.sort(key=lambda l: l.Elevation)
        dotnet_levels = self.to_dotnet_array(levels)
        
        for combo in [self.ColLevelCombo, self.WallLevelCombo, self.BeamLevelCombo, self.FloorLevelCombo]:
            combo.ItemsSource = dotnet_levels
            if levels: combo.SelectedIndex = 0

        self.populate_type_dropdown(self.ColTypeCombo, DB.BuiltInCategory.OST_StructuralColumns, DB.FamilySymbol)
        self.populate_type_dropdown(self.WallTypeCombo, DB.BuiltInCategory.OST_Walls, DB.WallType)
        self.populate_type_dropdown(self.BeamTypeCombo, DB.BuiltInCategory.OST_StructuralFraming, DB.FamilySymbol)
        self.populate_type_dropdown(self.FloorTypeCombo, DB.BuiltInCategory.OST_Floors, DB.FloorType)

    def populate_type_dropdown(self, combobox, category, class_type):
        types = list(DB.FilteredElementCollector(self.doc).OfClass(class_type).OfCategory(category).ToElements())
        combobox.ItemsSource = self.to_dotnet_array(types)
        if types: combobox.SelectedIndex = 0

    def OnPickCadClick(self, sender, e):
        self.window.Visibility = System.Windows.Visibility.Hidden
        try:
            ref = self.uidoc.Selection.PickObject(ObjectType.Element, "Select a CAD File")
            elem = self.doc.GetElement(ref)
            
            if isinstance(elem, DB.ImportInstance):
                name = elem.Category.Name if elem.Category else elem.Name
                if not name: name = "Unknown CAD"
                display_name = f"{name} [ID: {elem.Id.IntegerValue}]"
                
                if display_name not in self.cad_dict:
                    self.cad_dict[display_name] = elem
                    self.CadInstanceComboBox.ItemsSource = self.to_dotnet_array(list(self.cad_dict.keys()))
                    
                self.CadInstanceComboBox.SelectedItem = display_name
            else:
                UI.TaskDialog.Show("Invalid Selection", "The selected element is not a CAD ImportInstance.")
        except RevitExceptions.OperationCanceledException:
            pass 
        except Exception as ex:
            UI.TaskDialog.Show("Error", str(ex))
        finally:
            self.window.Visibility = System.Windows.Visibility.Visible

    def OnCadSelected(self, sender, e):
        selected_name = self.CadInstanceComboBox.SelectedItem
        if not selected_name: return
        
        selected_cad = self.cad_dict.get(selected_name)
        if not selected_cad: return
        
        geometry_by_layer = parse_geometry_by_layer(selected_cad, self.doc)
        
        self.LayerMapPanel.Children.Clear()
        self.layer_combos.clear()
        
        for layer_name in sorted(geometry_by_layer.keys()):
            hint = "Ignore"
            layer_lower = layer_name.lower()
            for key, val in KEYWORD_MAP.items():
                if key in layer_lower:
                    hint = val
                    break
                    
            panel = System.Windows.Controls.StackPanel()
            panel.Orientation = System.Windows.Controls.Orientation.Horizontal
            panel.Margin = System.Windows.Thickness(0, 2, 0, 2)
            
            tb = System.Windows.Controls.TextBlock()
            tb.Text = layer_name
            tb.Width = 250
            tb.VerticalAlignment = System.Windows.VerticalAlignment.Center
            
            cb = System.Windows.Controls.ComboBox()
            cb.Width = 150
            
            for opt in ["Ignore", "Column", "Wall", "Beam", "Slab"]:
                cb.Items.Add(opt)
            cb.SelectedItem = hint
            
            panel.Children.Add(tb)
            panel.Children.Add(cb)
            
            self.LayerMapPanel.Children.Add(panel)
            self.layer_combos[layer_name] = cb

    def OnCancelClick(self, sender, e):
        self.window.Close()

    def OnRunClick(self, sender, e):
        selected_name = self.CadInstanceComboBox.SelectedItem
        if not selected_name:
            UI.TaskDialog.Show("Error", "Please select a CAD Instance first.")
            return

        selected_cad = self.cad_dict.get(selected_name)
        
        mapping = {}
        for layer_name, cb in self.layer_combos.items():
            if cb.SelectedItem != "Ignore":
                mapping[layer_name] = cb.SelectedItem

        settings = ConversionSettings(
            cad_instance=selected_cad,
            layer_mapping=mapping,
            col_type_id=self.ColTypeCombo.SelectedItem.Id if self.ColTypeCombo.SelectedItem else None,
            col_base_level_id=self.ColLevelCombo.SelectedItem.Id if self.ColLevelCombo.SelectedItem else None,
            col_top_offset_ft=convert_mm_to_ft(float(self.ColTopOffset.Text)),
            wall_type_id=self.WallTypeCombo.SelectedItem.Id if self.WallTypeCombo.SelectedItem else None,
            wall_base_level_id=self.WallLevelCombo.SelectedItem.Id if self.WallLevelCombo.SelectedItem else None,
            wall_height_ft=convert_mm_to_ft(float(self.WallHeight.Text)),
            beam_type_id=self.BeamTypeCombo.SelectedItem.Id if self.BeamTypeCombo.SelectedItem else None,
            beam_level_id=self.BeamLevelCombo.SelectedItem.Id if self.BeamLevelCombo.SelectedItem else None,
            floor_type_id=self.FloorTypeCombo.SelectedItem.Id if self.FloorTypeCombo.SelectedItem else None,
            floor_level_id=self.FloorLevelCombo.SelectedItem.Id if self.FloorLevelCombo.SelectedItem else None,
            min_length_ft=convert_mm_to_ft(float(self.TxtMinLength.Text)),
            duplicate_check=self.CheckDuplicates.IsChecked,
            preview_mode=self.CheckPreview.IsChecked
        )
        
        self.window.Hide()
        run_conversion(self.doc, settings)
        self.window.Close()

    def ShowDialog(self):
        self.window.ShowDialog()

# ── SECTION 6: CONVERSION ENGINE ─────────────────────────────────────────────

def run_conversion(doc: DB.Document, settings: ConversionSettings):
    parsed_geometry = parse_geometry_by_layer(settings.cad_instance, doc)
    results = {"Column": [0,0], "Wall": [0,0], "Beam": [0,0], "Slab": [0,0]}
    
    t = DB.Transaction(doc, "CAD to BIM Conversion")
    t.Start()
    
    try:
        for layer, geom_list in parsed_geometry.items():
            mapped_category = settings.layer_mapping.get(layer)
            if not mapped_category: continue
                
            valid_lines = [c for c in geom_list if isinstance(c, DB.Line)]
            
            if mapped_category == "Wall":
                level_z = doc.GetElement(settings.wall_base_level_id).Elevation
                flat_lines = [flatten_line_to_z(l, level_z) for l in valid_lines if flatten_line_to_z(l, level_z)]
                centerlines = extract_wall_centerlines(flat_lines, convert_mm_to_ft(MAX_WALL_THICKNESS_MM))
                
                for line in centerlines:
                    if settings.preview_mode:
                        results["Wall"][0] += 1
                        continue
                    success, _ = create_basic_wall(doc, line, settings)
                    results["Wall"][0 if success else 1] += 1

            elif mapped_category == "Beam":
                level_z = doc.GetElement(settings.beam_level_id).Elevation
                flat_lines = [flatten_line_to_z(l, level_z) for l in valid_lines if flatten_line_to_z(l, level_z)]
                
                for line in flat_lines:
                    if settings.preview_mode:
                        results["Beam"][0] += 1
                        continue
                    success, _ = create_structural_beam(doc, line, settings)
                    results["Beam"][0 if success else 1] += 1

            elif mapped_category == "Column":
                for curve in geom_list:
                    if settings.preview_mode:
                        results["Column"][0] += 1
                        continue
                    success, _ = create_structural_column(doc, curve, settings)
                    results["Column"][0 if success else 1] += 1

            elif mapped_category == "Slab":
                if len(geom_list) > 2:
                    if settings.preview_mode:
                        results["Slab"][0] += 1
                        continue
                    level_z = doc.GetElement(settings.floor_level_id).Elevation
                    flat_curves = [flatten_line_to_z(c, level_z) for c in geom_list if isinstance(c, DB.Line)]
                    flat_curves = [c for c in flat_curves if c is not None]
                    
                    success, _ = create_architectural_floor(doc, flat_curves, settings)
                    results["Slab"][0 if success else 1] += 1

        if settings.preview_mode:
            t.RollBack()
        else:
            t.Commit()
            
    except Exception as e:
        t.RollBack()
        UI.TaskDialog.Show("Error", f"Fatal Error during transaction: {str(e)}")
        return
    
    report = []
    if settings.preview_mode:
        report.append("--- PREVIEW MODE: NO ELEMENTS CREATED ---\n")
    else:
        report.append("--- CONVERSION COMPLETE ---\n")
        
    for cat in ["Column", "Wall", "Beam", "Slab"]:
        report.append(f"{cat}s -> Created: {results[cat][0]} | Skipped/Failed: {results[cat][1]}")
        
    UI.TaskDialog.Show("CAD to BIM Results", "\n".join(report))

# ── MAIN EXECUTION ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    try:
        active_uidoc = __revit__.ActiveUIDocument
        active_doc = active_uidoc.Document
        
        window = CadToBimForm(active_doc, active_uidoc)
        window.ShowDialog()
    except Exception as ex:
        import traceback
        UI.TaskDialog.Show("Execution Error", traceback.format_exc())
#!python3
"""
AnonGee BIM Tools – Single‑Column Brand Diagnostic Window (CPython 3)
Loads the full brand theme from Resources/ and shows all elements in a vertical stack.
Footer is now scrollable, so nothing gets cut off.
Works with pyRevit 6.10.0 on Revit 2025, CPython 3.12.3.
"""

import os
import re
import clr

# ---------------------------------------------------------------------------
# 1. Load required .NET assemblies
# ---------------------------------------------------------------------------
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xaml')

from System.Windows import (
    Application, Window, WindowStartupLocation,
    Thickness, HorizontalAlignment, VerticalAlignment,
    ResourceDictionary, Visibility, ResizeMode, ShutdownMode
)
from System.Windows.Controls import (
    Button, TextBox, ComboBox, TextBlock, StackPanel, DockPanel,
    ScrollViewer, GroupBox, Border, WrapPanel,
    Dock, Orientation, ScrollBarVisibility
)
from System.Windows.Shapes import Path, Rectangle
from System.Windows.Markup import XamlReader
from System.Windows.Media import Stretch
from System.IO import MemoryStream
from System.Text import Encoding

# ---------------------------------------------------------------------------
# 2. Locate the Resources folder by walking up from the script directory
# ---------------------------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))

def find_extension_root(start_dir):
    current = start_dir
    for _ in range(10):
        candidate = os.path.join(current, 'Resources', 'AnonGeeTheme.xaml')
        if os.path.isfile(candidate):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None

extension_root = find_extension_root(script_dir)
if not extension_root:
    raise FileNotFoundError(
        "Could not locate extension root containing Resources/AnonGeeTheme.xaml"
    )

resources_folder = os.path.join(extension_root, 'Resources')

# ---------------------------------------------------------------------------
# 3. Ensure a WPF Application exists
# ---------------------------------------------------------------------------
if Application.Current is None:
    app = Application()
    app.ShutdownMode = ShutdownMode.OnExplicitShutdown
else:
    app = Application.Current

# ---------------------------------------------------------------------------
# 4. Flatten all sub-dictionaries into a single ResourceDictionary
# ---------------------------------------------------------------------------
sub_files = [
    'Colors.xaml',
    'Typography.xaml',
    'Controls.xaml',
    'Panels.xaml',
    'Icons.xaml'
]

def extract_inner_xaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'<ResourceDictionary[^>]*>', content)
    if not match:
        raise ValueError(f"No <ResourceDictionary> tag found in {file_path}")
    start_idx = match.end()
    end_idx = content.rfind('</ResourceDictionary>')
    if end_idx == -1:
        raise ValueError(f"No </ResourceDictionary> tag found in {file_path}")
    return content[start_idx:end_idx].strip()

master_xaml_parts = []
for fname in sub_files:
    full_path = os.path.join(resources_folder, fname)
    inner = extract_inner_xaml(full_path)
    master_xaml_parts.append(inner)

master_xaml = (
    '<ResourceDictionary\n'
    '    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"\n'
    '    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">\n'
    + '\n'.join(master_xaml_parts) +
    '\n</ResourceDictionary>'
)

stream = MemoryStream(Encoding.UTF8.GetBytes(master_xaml))
try:
    theme = XamlReader.Load(stream)
finally:
    stream.Close()

# ---------------------------------------------------------------------------
# 5. Build a diagnostic single‑column window (footer inside scroll)
# ---------------------------------------------------------------------------
window = Window()
window.Title = "AnonGee · Theme Diagnostic"
window.Width = 600
window.Height = 800          # increased to avoid cutoff
window.WindowStartupLocation = WindowStartupLocation.CenterOwner
window.ResizeMode = ResizeMode.CanResize
window.Resources.MergedDictionaries.Add(theme)

# Outer vertical stack (header, accent bar, scroll area)
main_stack = StackPanel()
main_stack.Orientation = Orientation.Vertical
main_stack.Margin = Thickness(0)

# ---------- HEADER ----------
header = Border()
header.Background = theme['BrushBackgroundDark']
header.Padding = Thickness(16, 12, 16, 12)
header_text = TextBlock()
header_text.Text = "AnonGee · Theme Diagnostic"
header_text.Style = theme['TextH2']
header_text.Foreground = theme['BrushBackgroundLight']
header.Child = header_text
main_stack.Children.Add(header)

# Accent bar
accent = Border()
accent.Height = 3
accent.Background = theme['BrushAccentBlue']
main_stack.Children.Add(accent)

# Scrollable area (contains everything else, including footer)
scroll = ScrollViewer()
scroll.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
scroll.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled

content = StackPanel()
content.Orientation = Orientation.Vertical
content.Margin = Thickness(24, 16, 24, 16)

# ========== DIAGNOSTIC BANNER ==========
diag_border = Border()
diag_border.Background = theme['BrushNeutral100']
diag_border.Padding = Thickness(12)
diag_border.Margin = Thickness(0, 0, 0, 16)
diag_stack = StackPanel()
diag_title = TextBlock()
diag_title.Text = "Color & Font Check"
diag_title.Style = theme['TextH3']
diag_stack.Children.Add(diag_title)

def add_color_swatch(label, brush_key):
    panel = WrapPanel()
    panel.Margin = Thickness(0, 4, 0, 0)
    swatch = Rectangle()
    swatch.Width = 20
    swatch.Height = 20
    swatch.Fill = theme[brush_key]
    swatch.Stroke = theme['BrushBorder']
    swatch.StrokeThickness = 1
    swatch.Margin = Thickness(0, 0, 8, 0)
    panel.Children.Add(swatch)
    txt = TextBlock()
    txt.Text = f"{label} ({brush_key})"
    txt.Style = theme['TextBody']
    panel.Children.Add(txt)
    diag_stack.Children.Add(panel)

add_color_swatch("Deep Space", "BrushBackgroundDark")
add_color_swatch("Cloud White", "BrushBackgroundLight")
add_color_swatch("Blueprint Blue", "BrushAccentBlue")
add_color_swatch("Steel Teal", "BrushAccentTeal")
add_color_swatch("Amber Warning", "BrushAccentAmber")
add_color_swatch("Error Red", "BrushAccentRed")
add_color_swatch("Slate text", "BrushTextMuted")

font_sample = TextBlock()
font_sample.Text = "Font: Inter (fallback Segoe UI) – H1 Bold 24pt"
font_sample.Style = theme['TextH1']
font_sample.Margin = Thickness(0, 8, 0, 0)
diag_stack.Children.Add(font_sample)

font_sample2 = TextBlock()
font_sample2.Text = "Font: Inter – Body 12pt"
font_sample2.Style = theme['TextBody']
diag_stack.Children.Add(font_sample2)

diag_border.Child = diag_stack
content.Children.Add(diag_border)

# ========== SECTION GROUP with INPUTS ==========
section = GroupBox()
section.Header = "Input Controls"
section.Style = theme['SectionGroup']
section.Margin = Thickness(0, 0, 0, 16)
section_stack = StackPanel()

label_name = TextBlock()
label_name.Text = "Element Name"
label_name.Style = theme['TextBody']
label_name.Margin = Thickness(0, 0, 0, 4)
section_stack.Children.Add(label_name)

input_name = TextBox()
input_name.Style = theme['InputTextBox']
input_name.Width = 260
input_name.Text = "Sample text..."
section_stack.Children.Add(input_name)

label_type = TextBlock()
label_type.Text = "Type"
label_type.Style = theme['TextBody']
label_type.Margin = Thickness(0, 12, 0, 4)
section_stack.Children.Add(label_type)

combo_type = ComboBox()
combo_type.Style = theme['InputComboBox']
combo_type.Width = 260
combo_type.Items.Add("Beam")
combo_type.Items.Add("Column")
combo_type.Items.Add("Brace")
combo_type.Items.Add("Wall")
combo_type.SelectedIndex = 0
section_stack.Children.Add(combo_type)

error_text = TextBlock()
error_text.Text = "This is an inline error message"
error_text.Style = theme['TextError']
error_text.Visibility = Visibility.Visible
section_stack.Children.Add(error_text)

section.Content = section_stack
content.Children.Add(section)

# ========== BUTTONS ==========
button_header = TextBlock()
button_header.Text = "Buttons"
button_header.Style = theme['TextH3']
button_header.Margin = Thickness(0, 0, 0, 8)
content.Children.Add(button_header)

button_panel = WrapPanel()
button_panel.Margin = Thickness(0, 0, 0, 12)

btn_primary = Button()
btn_primary.Content = "Primary"
btn_primary.Style = theme['ButtonPrimary']
btn_primary.Width = 100
btn_primary.Margin = Thickness(0, 0, 8, 8)
button_panel.Children.Add(btn_primary)

btn_secondary = Button()
btn_secondary.Content = "Secondary"
btn_secondary.Style = theme['ButtonSecondary']
btn_secondary.Width = 100
btn_secondary.Margin = Thickness(0, 0, 8, 8)
button_panel.Children.Add(btn_secondary)

btn_ghost = Button()
btn_ghost.Content = "Ghost"
btn_ghost.Style = theme['ButtonGhost']
btn_ghost.Width = 80
btn_ghost.Margin = Thickness(0, 0, 8, 8)
button_panel.Children.Add(btn_ghost)

btn_danger = Button()
btn_danger.Content = "Danger"
btn_danger.Style = theme['ButtonDanger']
btn_danger.Width = 100
btn_danger.Margin = Thickness(0, 0, 8, 8)
button_panel.Children.Add(btn_danger)

content.Children.Add(button_panel)

# ========== ICONS ==========
icon_header = TextBlock()
icon_header.Text = "Icons"
icon_header.Style = theme['TextH3']
icon_header.Margin = Thickness(0, 0, 0, 8)
content.Children.Add(icon_header)

icons_panel = WrapPanel()
icon_size = 24
for icon_name, icon_key in [
    ("Structural", "IconLayers"),
    ("Export", "IconDownload"),
    ("AI", "IconZap"),
    ("Warning", "IconAlertTriangle")
]:
    stack = StackPanel()
    stack.Margin = Thickness(0, 0, 24, 12)
    icon = Path()
    icon.Data = theme[icon_key]
    icon.Fill = theme['BrushAccentBlue']
    icon.StrokeThickness = 1.5
    icon.Stretch = Stretch.Uniform
    icon.Width = icon_size
    icon.Height = icon_size
    stack.Children.Add(icon)
    txt = TextBlock()
    txt.Text = icon_name
    txt.Style = theme['TextCaption']
    txt.HorizontalAlignment = HorizontalAlignment.Center
    stack.Children.Add(txt)
    icons_panel.Children.Add(stack)

content.Children.Add(icons_panel)

# ========== FOOTER (inside scrollable area) ==========
footer = Border()
footer.Background = theme['BrushNeutral100']
footer.Padding = Thickness(12)
footer.Margin = Thickness(0, 16, 0, 0)
footer_stack = StackPanel()
footer_stack.Orientation = Orientation.Horizontal
footer_stack.HorizontalAlignment = HorizontalAlignment.Right

footer_text = TextBlock()
footer_text.Text = "Ready"
footer_text.Style = theme['TextCaption']
footer_text.VerticalAlignment = VerticalAlignment.Center
footer_text.Margin = Thickness(0, 0, 16, 0)
footer_stack.Children.Add(footer_text)

btn_close = Button()
btn_close.Content = "Close"
btn_close.Style = theme['ButtonGhost']
btn_close.Click += lambda s, e: window.Close()
footer_stack.Children.Add(btn_close)

footer.Child = footer_stack
content.Children.Add(footer)        # now inside scrollable content

scroll.Content = content
main_stack.Children.Add(scroll)

window.Content = main_stack

# ---------------------------------------------------------------------------
# 6. Show the diagnostic window
# ---------------------------------------------------------------------------
window.ShowDialog()
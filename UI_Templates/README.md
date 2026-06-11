# UI_Templates — Reusable WPF Window Framework for pyRevit

## Overview

This directory provides a **three-tier architecture** for building WPF-based tools in pyRevit:

```
UI_Templates/
├── icons/          # PNG icon assets (18 icons available)
├── python/         # Python scripts that load and drive XAML windows
│   └── MainWindowLoader.py
└── xaml/           # WPF XAML layout files
    └── MainWindowTemplate.xaml
```

## Architecture

| Directory | Purpose |
|-----------|---------|
| `icons/` | PNG files for UI controls (close, minimize, maximize/restore, search, settings, etc.) |
| `python/` | IronPython-compatible scripts that load XAML from disk, wire event handlers, and interact with Revit API |
| `xaml/` | WPF window layouts defined in pure XAML — no code-behind, no embedded strings |

## Why Separate XAML from Python?

The existing pyRevit pattern embeds XAML as raw strings inside Python scripts (e.g., `OneFilterParameter.pushbutton/script.py`). This works but has drawbacks:

- **No syntax highlighting** for XAML inside Python strings
- **Hard to maintain** — UI changes require editing a massive string literal
- **No designer preview** — XAML must be loaded in Revit to see changes
- **Poor reuse** — each tool duplicates the same header/control setup

Separating XAML into `.xaml` files solves all of these. You can open the XAML in Visual Studio, Blend, or any XAML editor for real-time design preview, and the Python loader handles window chrome (close/minimize/maximize) automatically.

## Using the Template

### 1. Reference the Loader in Your pyRevit Script

```python
# -*- coding: utf-8 -*-
import sys
import os
import clr

# Add WPF assemblies
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from pyrevit import revit, DB, UI
doc = revit.doc
uidoc = revit.uidoc

# Import the template loader
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "UI_Templates", "python"))
from MainWindowLoader import run_ui


def run_my_tool():
    # Load the template with your custom XAML
    xaml_path = os.path.join(os.path.dirname(__file__), "MyCustomUI.xaml")

    # run_ui loads the window, wires header buttons, and shows modal
    window = run_ui(xaml_path=xaml_path, title="My Custom Tool")

    # After window.ShowDialog() returns, access results from window
    # (your tool logic continues here)


if __name__ == "__main__":
    run_my_tool()
```

### 2. Loading a Custom XAML (Not the Template)

You don't have to use `MainWindowTemplate.xaml`. You can create your own `.xaml` file and pass its path to `run_ui()`:

```python
window = run_ui(xaml_path="path/to/MyForm.xaml", title="My Form")
```

The loader will still wire up `btn_minimize`, `btn_maximize_restore`, `btn_close`, and `btn_dismiss` if they exist in your XAML.

### 3. Referencing Icons from XAML

Icons are loaded programmatically in Python (not via XAML `Image.Source` paths) to avoid filesystem path resolution issues inside Revit's sandbox. The `MainWindowLoader.py` script does this automatically for the header button icons.

To use an icon in your own controls, use the same pattern:

```python
from System.Windows.Media import Imaging

def load_icon(icons_dir, filename):
    path = os.path.join(icons_dir, filename)
    uri = System.Uri(path)
    img = Imaging.BitmapImage()
    img.BeginInit()
    img.UriSource = uri
    img.CacheOption = Imaging.BitmapCacheOption.OnLoad
    img.EndInit()
    img.Freeze()
    return img
```

### 4. pyRevit Bundle Structure

To create a new pyRevit pushbutton using this template:

```
YourTool.pushbutton/
├── bundle.yaml
├── icon.png              # 32x32 pushbutton icon
└── script.py             # Your tool script (see example above)
```

**bundle.yaml:**
```yaml
title: Your Tool
author: Zaid Shaikh
tooltip: |
  Description of your tool.
  Uses the UI_Templates framework.
```

**script.py** — see the usage example in section 1 above.

## Available Icons

| Icon File | Purpose |
|-----------|---------|
| `icons8-close-window-96.png` | Close button |
| `icons8-minimize-window-96.png` | Minimize button |
| `icons8-maximize-window-96.png` | Maximize button |
| `icons8-restore-window-96.png` | Restore (windowed) button |
| `icons8-search-96.png` | Search / filter |
| `icons8-filter-96.png` | Filter |
| `icons8-edit-96.png` | Edit / modify |
| `icons8-delete-96.png` | Delete / remove |
| `icons8-remove-96.png` | Remove |
| `icons8-save-as-96.png` | Save / export |
| `icons8-settings-96.png` | Settings / configuration |
| `icons8-menu-96.png` | Menu / hamburger |
| `icons8-color-swatch-96.png` | Color picker |
| `icons8-paint-palette-96.png` | Paint / appearance |
| `icons8-python-96.png` | Python branding |
| `icons8-ai-96.png` | AI / intelligence |
| `icons8-dwg-96.png` | DWG / CAD |
| `icons8-toggle-full-screen-96.png` | Full screen toggle |

## API Reference

### `run_ui(xaml_path=None, title="pyRevit Tool")`

Loads a WPF XAML window and displays it as a modal dialog.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `xaml_path` | `str` or `None` | `../xaml/MainWindowTemplate.xaml` | Absolute or relative path to the `.xaml` file |
| `title` | `str` | `"pyRevit Tool"` | Window title displayed in the header bar |

**Returns:**

| Return Value | Type | Description |
|-------------|------|-------------|
| `window` | `System.Windows.Window` | The loaded WPF window instance with attached helpers |

**Returned Window Attached Helpers:**

| Helper | Type | Description |
|--------|------|-------------|
| `window.set_status(msg, is_error=False)` | callable | Update the status bar text and badge color |
| `window.live_count` | `TextBlock` | Reference to the live count badge |
| `window.content_panel` | `StackPanel` | The main content area for adding custom controls |
| `window.header_title` | `TextBlock` | The header title text block |

### Example with Custom Controls

```python
from MainWindowLoader import run_ui

window = run_ui(title="My Tool")

# Add custom controls to the content panel
from System.Windows.Controls import TextBox, Button, StackPanel
from System.Windows import HorizontalAlignment

tb = TextBox()
tb.Text = "Enter value..."
window.content_panel.Children.Add(tb)

btn = Button()
btn.Content = "Run"
btn.HorizontalAlignment = HorizontalAlignment.Right
window.content_panel.Children.Add(btn)

# window.ShowDialog() is called inside run_ui()
```

## Compatibility

- **Revit**: 2019+ (any version supporting pyRevit)
- **pyRevit**: 4.x+
- **IronPython**: 2.7 (standard pyRevit engine)
- **Python**: CPython 3.x (for development/testing outside Revit)

## Notes

- The `MainWindowTemplate.xaml` uses `WindowStyle="None"` and `AllowsTransparency="True"` for a modern frameless look. Window dragging (if needed) can be added via `MouseLeftButtonDown` on the header bar.
- All `.NET` types accessed via `clr` are invisible to static Python analyzers — this is expected and does not affect runtime.
- The template includes a `DropShadowEffect` for modern appearance. Disable it on older systems if performance is a concern.
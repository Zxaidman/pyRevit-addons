# Implementation Plan

Create a reusable WPF window template framework for pyRevit tools that separates XAML UI definition, Python logic, and icon assets into distinct directories within `UI_Templates/`, featuring a custom window chrome with minimize, maximize/restore, and close buttons sourced from PNG icons.

The `UI_Templates/` directory currently has three empty subdirectories (`icons/`, `python/`, `xaml/`) and 18 icon PNG files already placed in `icons/`. The existing pyRevit codebase pattern embeds XAML directly as raw strings inside Python scripts (see `OneFilterParameter.pushbutton/script.py`). This proposal refactors that approach into a proper three-tier architecture: XAML files define UI layout independently in `xaml/`, Python scripts load and drive those XAML files in `python/`, and PNG icons are referenced from `icons/`. The template will use a custom window header bar with window control buttons (close, minimize, maximize/restore), matching the look-and-feel of modern desktop applications while remaining compatible with Revit's modal dialog hosting via pyRevit's IronPython engine.

[Types]

No new Python types, interfaces, enums, or data structures are introduced. The implementation uses only built-in .NET/WPF types accessed via Python.NET (`clr`): `System.Windows.Window`, `System.Windows.Markup.XamlReader`, `System.Windows.Controls.Button`, `System.Windows.Media.ImageSource`, etc. A single state dictionary will be used inside the Python script, matching the existing pattern in `OneFilterParameter/script.py` — no formal type definitions required.

[Files]

Three new files will be created; no existing files are modified, deleted, or moved.

| Action | File Path | Purpose |
|--------|-----------|---------|
| CREATE | `UI_Templates/xaml/MainWindowTemplate.xaml` | WPF Window XAML defining the full UI layout: custom header bar with icon-driven window control buttons (close, minimize, maximize/restore), a content area placeholder, and a status bar. Resources define color palette, button styles, and reusable brushes. |
| CREATE | `UI_Templates/python/MainWindowLoader.py` | Python script (IronPython 2.7 compatible, pyRevit-compliant) that loads the XAML file from disk using `XamlReader.Load()`, finds named controls, wires event handlers for window control buttons (Close → `window.Close()`, Minimize → `window.WindowState = Minimized`, Maximize/Restore → toggle `window.WindowState`), and provides a `run_ui()` entry point. |
| CREATE | `UI_Templates/python/MainWindowStandalone.py` | Standalone Python script (CPython + pythonnet) that runs the same WPF template outside Revit with demo controls populated programmatically. Entry point via `main()`. |
| CREATE | `UI_Templates/README.md` | Documentation explaining the template architecture, how to reference icons from XAML using relative paths, how to load the XAML from Python, and how to integrate with pyRevit's bundle.yaml pushbutton structure. |

[Functions]

One new function will be created; no existing functions are modified or removed.

| Function | File | Signature | Purpose |
|----------|------|-----------|---------|
| `run_ui()` | `UI_Templates/python/MainWindowLoader.py` | `def run_ui(xaml_path=None, title="pyRevit Tool"):` | Loads `MainWindowTemplate.xaml` from the sibling `../xaml/` directory via `XamlReader.Load(FileStream)`, wires all window control button handlers (minimize, maximize/restore, close), updates the maximize/restore icon on state change, and calls `window.ShowDialog()`. Follows the identical boilerplate pattern used in `OneFilterParameter/script.py:run_ui()`. |
| `main()` | `UI_Templates/python/MainWindowStandalone.py` | `def main():` | Standalone entry point that loads the XAML, wires controls, populates content area with demo UI, disables Revit-specific buttons, and shows the window. Called via `if __name__ == "__main__": main()`. |

Additionally, three inline event handler closures inside `run_ui()`:
- `on_minimize(sender, args)` — sets `window.WindowState = WindowState.Minimized`
- `on_maximize_restore(sender, args)` — toggles between `Normal` and `Maximized`, switches the button icon between `icons8-maximize-window-96.png` and `icons8-restore-window-96.png`
- `on_close(sender, args)` — calls `window.Close()`

[Classes]

No new classes are created. The implementation uses only procedural Python code, .NET WPF classes accessed via `clr`, and existing pyRevit wrapper APIs (`pyrevit.revit`, `pyrevit.DB`, `pyrevit.UI`).

[Dependencies]

No new packages or external dependencies. Required .NET assemblies are already referenced in the existing pyRevit pattern:
- `PresentationFramework`
- `PresentationCore`
- `WindowsBase`
- `System.Xaml`

All icons referenced are already present in `UI_Templates/icons/` — no new image assets are needed.

[Testing]

Manual validation through Revit: the template script can be executed as a standalone pyRevit pushbutton after creating a minimal `bundle.yaml` and `icon.png` in a test pushbutton folder. Validation checklist:
- Window opens centered on screen with custom header bar visible
- Minimize button sets window to `Minimized` state
- Maximize/Restore button toggles between `Normal` and `Maximized` and swaps icon
- Close button dismisses the window
- No Python stack traces in Revit journal or pyRevit output

[Implementation Order]

1. Create `UI_Templates/xaml/MainWindowTemplate.xaml` — the complete WPF window layout with all resource dictionaries, styles, header bar with icon buttons, content placeholder, and status bar.
2. Create `UI_Templates/python/MainWindowLoader.py` — the Python script that loads the XAML, wires all window control event handlers, and exposes `run_ui()`.
3. Create `UI_Templates/python/MainWindowStandalone.py` — the standalone Python script with `main()` for CPython + pythonnet execution outside Revit.
4. Create `UI_Templates/README.md` — documentation explaining the template architecture, icon referencing, XAML loading, and pyRevit integration instructions.
5. Verify the files are syntactically correct and the icon paths resolve relative to the expected runtime working directory.

# AnonGee BIM Tools — pyRevit Extension for Autodesk Revit

A professional suite of structural and architectural BIM automation tools for **Autodesk Revit (2022+)** , delivered through the **pyRevit** framework. All tools run cleanly out-of-the-box with zero manual dependency installation for end users — dependencies are bundled inside the extension.

![Revit](https://img.shields.io/badge/Autodesk%20Revit-2022%2B-blue)
![pyRevit](https://img.shields.io/badge/pyRevit-6.10.0%2B-brightgreen)
![Python](https://img.shields.io/badge/Python-CPython3%20%7C%20IronPython2-yellow)

---

## ✨ Tools Overview

The extension adds an **AnonGee** tab inside Revit with four panels:

### 🟢 Essential Panel


| Tool                      | Description                                                                                                                 |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Obscured Rebar**        | Set rebars as unobscured and solid across selected views. Adjusts view detail level (Fine for 3D, Medium for plan/section). |
| **Copy Rebar Visibility** | Copy rebar visibility / graphic settings from one view to others.                                                           |
| **Export Schedule**       | Export Revit schedules to Excel / CSV format.                                                                               |
| **Bulk Rename**           | Rename multiple elements (views, sheets, families, etc.) with naming patterns.                                              |
| **Bulk Delete**           | Bulk-delete unused categories: fill patterns, line patterns, line styles, and more.                                         |
| **Auto Level Manager**    | Modeless level manager with smart text detection. Reads level marks out of drawing text ("FFL +3.500", "TOS -1.200", "TERRACE +14'-6\"") from the active view, the Revit selection, a DXF, or a paste box; works out the drawing's unit from the storey heights and cross-checks each text against where it sits on the sheet. Adds, renames, re-spaces and deletes levels, and commits as one undo step. The stack is drawn to scale and is editable in place — click to select, drag to move, double-click to rename, wheel to zoom. |

### 🔵 Advance Panel


| Tool                       | Description                                                                                                                                                |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **One Filter Parameter**   | Filter Revit elements by a single parameter condition, preview matches in a table, then batch-edit a parameter (Set / Prefix / Suffix / Replace / Delete). |
| **Multi Filter Parameter** | Filter Revit elements by multiple parameter conditions (All/Any logic), then batch-edit parameters in one transaction.                                     |
| **Parameter Combine**      | Combine or split parameter values across multiple elements.                                                                                                |

### 🔴 Core Panel


| Tool               | Description                                                                                                                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **BIM Generation** | Build a structural Revit model from a PLANWIN / FRAMEWIN**INP** file. Creates levels, columns, beams, and floors with auto-sized type duplicates.                                                     |
| **CAD2BIM**        | Import a**DXF** file, link it with unit + positioning settings, then auto-generate Revit grids, columns, and beams from the DXF geometry and text marks. Uses hybrid extraction (Revit link + ezdxf). |
| **FramewinToBIM**  | Convert FRAMEWIN structural data directly into Revit elements.                                                                                                                                        |

### 🟠 Dev Panel


| Tool                 | Description                                                                                                                                                                                                                                                  |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **BBS Generator**    | **Bar Bending Schedule** generator. Reads native `DB.Rebar` elements and exports formatted Excel workbooks (BBS, Calculation, Summary sheets). Supports **IS 2502:2019**, **BS 8666:2020**, and **ACI 318-19 / CRSI** standards. Includes revision tracking. |
| **Brand Guidelines** | Live component gallery showing the AnonGee design system — brand colors, typography, buttons, inputs, toggles, and status badges.                                                                                                                           |
| **CPython3 engine**  | Check / test the CPython 3 engine configuration.                                                                                                                                                                                                             |
| **Create Button**    | Quick scaffolding utility for creating new pyRevit buttons.                                                                                                                                                                                                  |

---

## 🎨 Design System

All tools use a **custom WPF design system** with:

- Brand color palette & theming (`Colors.xaml`, `AnonGeeTheme.xaml`)
- Reusable WPF controls (`Controls.xaml`)
- SVG/vector icons (`Icons.xaml`)
- Consistent typography (`Typography.xaml`)
- Panel layout templates (`Panels.xaml`)

Preview the full system in Revit via **AnonGee > Dev > Brand Guidelines**.

---

## 📦 Installation (End User)

### Prerequisites

- **Autodesk Revit** 2022 or newer
- **pyRevit** 6.10.0 or newer ([Download pyRevit](https://github.com/eirannejad/pyRevit/releases))

### Step-by-Step

1. **Clone or download** this repository:

   ```bash
   git clone https://github.com/Zxaidman/pyRevit-addons.git
   ```
2. **Add the extension to pyRevit:**

   - Open Revit → click the **pyRevit** tab → **pyRevit** → **Extensions** → **Add Extension**.
   - Browse to the cloned folder (`pyRevit-addons`) and select it.
   - *Alternatively*, use the CLI:
     ```bash
     pyrevit extend add pyRevit-addons
     ```
3. **Restart Revit.**
   The **AnonGee** tab will now appear in the Revit ribbon with all tools ready to use.

> ✅ **No additional Python packages or dependency setup required.** All libraries are pre-bundled in the extension.

---

## 🛠️ Development (For Contributors)

If you're modifying or extending the tools, you may need to install or update Python dependencies:

```bash
# From the repository root
cd tools
pip install -r requirements.txt
python auto_provision.py
```

This installs `numpy`, `openpyxl`, `pythonnet`, and `ezdxf` into the extension's bundled library folders (`lib/py3/` and `lib/py2/`).

### Tests

Some tools keep their Revit-free logic in plain Python modules so it can be exercised without opening Revit. Run them from the repository root:

```bash
python -m unittest discover -s tests -v
```

`tests/test_autolevel.py` covers the Auto Level Manager's text detection, naming and plan model; `tests/test_autolevel_ui.py` is a static check of its XAML against the delivery rules in §12.7–§12.9 of the brand guidelines (every `FindName` lookup resolves, every `{Binding}` path has a matching slot, no `re`, no pyRevit imports, no `StaticResource` on the root `Window`).

### Project Structure

```
AnonGee.extension/
├── AnonGee.tab/           # Revit ribbon tab definition
│   ├── Essential.panel/   # Essential panel tools
│   ├── Advance.panel/     # Advance panel tools
│   ├── Core.panel/        # Core panel tools
│   └── Dev.panel/         # Dev panel tools
├── lib/                   # Bundled Python libraries
│   ├── py2/               # IronPython 2 libraries
│   └── py3/               # CPython 3 libraries
├── Resources/             # WPF design system (XAML)
│   ├── AnonGeeTheme.xaml  # Main theme
│   ├── Colors.xaml        # Brand colors
│   ├── Controls.xaml      # Reusable controls
│   ├── Icons.xaml         # SVG icons
│   ├── Panels.xaml        # Panel templates
│   └── Typography.xaml    # Typography styles
└── path_resolver.py       # Library path resolver
```

---

## 🤝 Contributing

1. Fork this repository.
2. Create a feature branch (`git checkout -b feature/NewTool`).
3. Commit your changes (`git commit -m 'Add new Revit tool'`).
4. Push to the branch (`git push origin feature/NewTool`).
5. Open a Pull Request.

---

## 🪪 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<p align="center">Built with ❤️ for the Revit BIM community</p>

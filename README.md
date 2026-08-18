# AnonGee BIM Tools — pyRevit Extension for Autodesk Revit

A professional suite of structural and architectural BIM automation tools for **Autodesk Revit (2022+)** , delivered through the **pyRevit** framework. All tools run cleanly out-of-the-box with zero manual dependency installation for end users — dependencies are bundled inside the extension.

![Revit](https://img.shields.io/badge/Autodesk%20Revit-2022%2B-blue)
![pyRevit](https://img.shields.io/badge/pyRevit-6.10.0%2B-brightgreen)
![Python](https://img.shields.io/badge/Python-CPython3%20%7C%20IronPython2-yellow)

---

## ✨ Tools Overview

The extension adds an **AnonGee** tab to the Revit ribbon with four panels and 29 tools.

### 🟢 Essential Panel

Everyday modelling and clean-up work.

**Auto Level Manager** *(v2.0.0 · [changelog](AnonGee.extension/AnonGee.tab/Essential.panel/AutoLevel.pushbutton/CHANGELOG.md))*


| Tool                   | Description                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Auto Level Manager** | Every level in the model from one**modeless** window — Revit stays interactive while it is open. Reads level marks out of drawing text ("FFL +3.500", "TOS -1.200", "TERRACE +14'-6\"") from the active view, the Revit selection, a DXF, or a paste box; infers the drawing's unit from the storey heights and cross-checks each text against where it sits on the sheet. Adds, renames, re-spaces and deletes levels. The stack is drawn to scale and editable in place — click to select, drag to move, double-click to rename, wheel to zoom. Undo/redo over staged changes; nothing reaches the model until Apply, which lands as one undo step. |

**StrucBIM** — structural slabs and setting-out


| Tool                     | Description                                                                                                                                                                                                            |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Round Element Dist**   | Check element distances against one correct datum element or point and round them to a design value. Reports every deviation first; you approve each fix before anything moves. Skips pinned, grouped and linked elements. |
| **Draw Floor**           | Click inside a closed region formed by structural framing and columns in a plan view; a structural floor or foundation slab is created with its boundary on the**inner faces** of those elements. Pick a type, click regions, repeat. |
| **Convert Slab**         | Convert Structural Floor ⇄ Structural Foundation (slab). Works on a pre-selection or lets you pick in plan, 3D, section or elevation, and shows a pre-flight list of every element with its resolved target type before committing. |

**Bulk Tool** — model-wide clean-up


| Tool                      | Description                                                                                                             |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Bulk Delete**           | Bulk-delete**Fill Patterns**, **Line Patterns** or **Line Styles**. Search and tick what to remove, with All / None helpers. |
| **Bulk Rename**           | Bulk find-and-replace across all**Fill Pattern**, **Line Pattern** or **Line Style** names.                            |
| **Obscured Rebar**        | Set rebars as Unobscured and Solid across selected views. Uses the pre-selection if there is one, otherwise every rebar in the document. |
| **Copy Rebar Visibility** | Copy rebar visibility from one view to many: hidden/unhidden state, the Unobscured flag, and the Solid flag for 3D → 3D pairs. |

**Action** — annotation and placement


| Tool                | Description                                                                                                                                                                        |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **AutoDIM**         | *Self Dimension.* Dimension a selected element's own extents, measured along the element's**own** orientation, on whichever axes lie in the active view's plane. Placement is tuned per category so dimensions stay clear of the geometry. |
| **Export Schedule** | Export Revit schedules to a single Excel workbook (`.xlsx`) with borders, fonts and header styling. Lists every project schedule with checkboxes.                                 |
| **Rotate Column**   | Rotate selected columns sequentially by a dynamically calculated step angle. Pure Revit API through Python.NET.                                                                    |

**Modify** — joins and link visibility


| Tool                    | Description                                                                                                        |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Join Priority**       | Enforce a category-based join order on selected elements, so higher-priority categories cut lower-priority ones.  |
| **Unjoin by Category**  | Unjoin the selected elements from everything they are joined to in the categories you choose.                      |
| **Toggle Linked**       | Toggle the visibility of linked Revit categories in the current view.                                              |

### 🔵 Advance Panel

Parameter work across many elements, always with a preview before anything is written.


| Tool                       | Description                                                                                                                                                |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **One Filter Parameter**   | Filter elements by a single parameter condition, preview the matches in a table, then batch-change a parameter on everything that passes (Set / Prefix / Suffix / Replace / Delete). |
| **Multi Filter Parameter** | Filter by multiple parameter conditions (All / Any logic), then batch-edit a parameter on everything that matches.                                        |
| **Parameter Combination**  | Write a value into a target parameter across model elements, built from one of four operations, with a live per-element preview before you apply.          |

### 🔴 Core Panel

Build a model from an external source.


| Tool               | Description                                                                                                                                                                                           |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **BIM Generation** | Build a structural Revit model from a PLANWIN / FRAMEWIN**INP** file. Creates levels, structural columns, beams and floors with auto-sized type duplicates.                                          |
| **FramewinToBIM**  | Generate a structural RC frame (columns / beams / slabs) from FRAMEWIN data.                                                                                                                          |
| **cad2bim**        | Pick a**DXF**, link it with unit and positioning settings, then build Revit grids, columns, beams, slabs and stairs from it. Hybrid extraction — the Revit link's geometry plus ezdxf for geometry and text — with layer classification and size refinement from text marks ("C1 400x400"). |

### 🟠 Dev Panel

Generators, the design system, and the reference patterns new tools are built from.


| Tool                    | Description                                                                                                                                                                                                                     |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **BBS Generator**       | **Bar Bending Schedule** generator. Reads native `DB.Rebar` elements and exports formatted Excel workbooks (BBS, Calculation, Summary sheets). Supports **IS 2502:2019**, **BS 8666:2020** and **ACI 318-19 / CRSI**, with revision tracking. |
| **Brand Guidelines**    | Living component gallery for the design system — brand colours, typography, buttons, inputs, selection controls, lists and status badges, exactly as they render inside Revit.                                                  |
| **CPython3 engine**     | Engine health check. Reports whether the CPython 3 engine is a fresh load or a reused instance (and how many runs this session), which third-party libraries resolve, and whether the Revit API bridge responds.                |
| **Create Button**       | Scaffold a new pyRevit pushbutton: collects the tab / panel / group / metadata in a brand-themed dialog, writes the folder, script, icon and `bundle.yaml`, then asks pyRevit to reload.                                        |
| **RC Automation**       | Reads an Excel reinforcement schedule, checks it against **BS 8666:2020**, and reports what the open model would give it — levels, rebar bar types, and whether the footings and columns it would host into can take reinforcement at all. **Read-only**: opens no transaction, creates nothing. Works out what the schedule would build, including whether a layer ships as one Revit element or has to be individual bars. |
| **Modeless Window**     | Reference implementation of the modeless (non-blocking) window pattern — `window.Show()`, an `IExternalEventHandler` bridge marshalling every Revit call onto Revit's primary thread, and the session-state rules that go with it. |

---

## 🏷️ Versioning

The extension carries one version in `extension.json`, recorded in the [root changelog](CHANGELOG.md).

A tool that changes often enough for "which build am I running" to be a real question carries **its own version and its own changelog**, beside its `bundle.yaml`. Those move independently — `AnonGee BIM Tools 1.1.0` ships `Auto Level Manager 2.0.0`, and neither number is wrong. The version shown in a tool's own window is the build actually running; quote it when reporting anything.

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

`tests/test_repo_docs.py` holds this README and the [root changelog](CHANGELOG.md) to what is actually on the ribbon — every `.pushbutton` on disk has to be documented, every panel has to be declared in `extension.json`, and the changelog has to lead with the version `extension.json` states. `tests/test_autolevel.py` covers the Auto Level Manager's text detection, naming, plan model and stack-drawing camera. `tests/test_autolevel_ui.py` checks its XAML and Python wiring statically, against the delivery rules in §12.7–§12.9 of the brand guidelines and against the failures that are expensive to find inside Revit:

- every `FindName` lookup resolves and every named control is used;
- every `{Binding}` path has a matching `__slots__` entry;
- no `re`, no pyRevit imports, no `StaticResource` on the root `Window`;
- **no attribute value is mistaken for a markup extension** — a literal starting with `{` must be escaped `{}`, or `XamlReader.Load` throws and the window never opens;
- every `{StaticResource}` names a key that exists, no `x:Key` is defined twice, every `Style` matches the element it is applied to, and every trigger `TargetName` exists in its own template;
- every interactive control carries a tooltip;
- the tool's version agrees across `__init__.py`, `bundle.yaml`, `CHANGELOG.md` and the window header.

`tests/test_rc_automation.py` covers the RC Automation workbook layer — cell
coercion, header detection beneath a title block, column-name aliases, pad
outlines, every validation rule the schedule is held to before a transaction is
opened, and the reconciliation that decides whether the workbook or the model
wins where they disagree. It also holds
`anongee_toolkit/rc_automation/standards.py` to the BS 8666:2020 module the BBS
Generator ships, so the bar sizes and shape codes in the two cannot drift apart.
The sample schedule it reads is in `tests/fixtures/rc_automation/`, one CSV per
sheet, and doubles as the worked example of the workbook format.

Most of that suite needs nothing installed. The handful of tests that open a real
`.xlsx` need `openpyxl` importable and skip themselves when it is not — the copy
vendored in `lib/py3` is a Windows build, so `pip install openpyxl` first if you
want the file layer covered on Linux or macOS.

### Project Structure

```
pyRevit-addons/
├── CHANGELOG.md               # the extension's own version history
├── README.md
├── extension.json             # extension name, version, panel order
├── tests/                     # Revit-free tests, run with plain unittest
├── tools/                     # dependency provisioning for contributors
├── AnonGee_BIM_Tools_Brand_Guidelines.md
└── AnonGee.extension/
    ├── AnonGee.tab/           # Revit ribbon tab definition
    │   ├── Essential.panel/   # Auto Level Manager, StrucBIM, Bulk Tool, Action, Modify
    │   ├── Advance.panel/     # parameter filtering and combination
    │   ├── Core.panel/        # BIM Generation, FramewinToBIM, cad2bim
    │   └── Dev.panel/         # BBS, design system, engine check, scaffolding, patterns
    ├── lib/                   # bundled Python libraries
    │   ├── py2/               # IronPython 2
    │   └── py3/               # CPython 3, incl. the anongee_toolkit package
    ├── Resources/             # WPF design system (XAML)
    │   ├── AnonGeeTheme.xaml  # main theme (merges the five below)
    │   ├── Colors.xaml        # brand colours
    │   ├── Controls.xaml      # reusable controls
    │   ├── Icons.xaml         # vector icons
    │   ├── Panels.xaml        # panel templates
    │   └── Typography.xaml    # type styles
    └── path_resolver.py       # library path resolver
```

A tool bundle is a folder ending in `.pushbutton`, holding `bundle.yaml` (title, author, tooltip), `icon.png`, `script.py`, and — for anything with a window — a sibling `ui.xaml`. A tool with its own version adds a `CHANGELOG.md` and keeps its logic in a package beside the script, so the parts that do not touch Revit can be tested:

```
AutoLevel.pushbutton/
├── bundle.yaml
├── CHANGELOG.md            # this tool's own version history
├── icon.png
├── script.py               # window, event wiring, the Revit-thread bridge
├── ui.xaml                 # WPF layout, theme inlined per §12.7.B
└── anongee_autolevel/      # the thinking parts, importable without Revit
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

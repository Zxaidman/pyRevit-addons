# CAD to BIM — Implemented Features

## Overview

The CAD to BIM tool reads linked CAD (DWG) files, classifies their curves by layer convention, and creates Revit elements (grids, columns, beams) from the classified geometry. All modules live under `AnonGee.extension/lib/py2/cad2bim/`.

---

## 1. Pushbutton Entry Point

**Location:** `AnonGee.extension/AnonGee.tab/Core.panel/CAD to BIM.pushbutton/`

| File | Purpose |
|------|---------|
| `bundle.yaml` | Button metadata: title, tooltip, author (RCC BIM Tools), min Revit 2022 |
| `script.py` | Main entry point — path bootstrapping, WPF dialog, orchestration of all read/write passes |
| `ui.xaml` | WPF UI layout (AnonGee branded theme) — layer mapping grid, build options, sizing limits |
| `icon.png` | Button icon |
| `bundle.yaml` | Extension manifest |

### Path Bootstrapping (`_bootstrap_lib_path`)
- Attempts `import path_resolver` → `update_paths()` (pyRevit adds `lib/` to sys.path)
- Falls back to climbing directory tree from `__file__` to find `lib/py2`
- Supports both py2/py3 subfolders

### Dialog Flow (CadToBimWindow — WPF)
- **Layer mapping section:** Dynamic rows per CAD layer with category combo (grid/column/beam/slab_edge/unmapped)
- **Build options:** Checkboxes for grids, columns, beams, export JSON
- **Family/Level combos:** Column family, circular column family, base level, top level, beam family
- **Sizing limits:** Beam width min/max, column b min/max, column h min/max — paired sliders + text boxes, two-way linked
- **Standard sizes:** Columns (b×h pairs, comma-separated), beam widths (comma-separated)
- **No Revit API in event handlers** — all model writes happen after `show_dialog()` returns

### Creation Passes
| Pass | Function | Elements | Transaction |
|------|----------|----------|-------------|
| Grids | `_create_grids()` | `Grid` from grid-category lines/arcs | TransactionGroup + Transaction + rollback |
| Columns | `_create_columns()` | `FamilyInstance` (structural columns) — rectangular + circular | TransactionGroup + Transaction + rollback |
| Beams | `_create_beams()` | `FamilyInstance` (structural framing) along centerlines | TransactionGroup + Transaction + rollback |
| Export | `_export()` | JSON file with full report + outcomes | N/A (file write) |

---

## 2. Library Modules (`cad2bim`)

### `__init__.py`
- Package version: `0.12.0`
- Module documentation listing all submodules with responsibilities

### `model.py` — Plain Data Holders
- `CurveRecord`: `kind`, `points` (internal ft), `layer`, `length_ft`, mutable `category`, `layer_key` property
- `ReadResult`: `source_name`, `records`, `layer_names` (sorted), `is_empty()`

### `units.py` — Unit Conversion
- `mm_to_internal(value_mm)` → decimal feet via `UnitUtils.ConvertToInternalUnits(UnitTypeId.Millimeters)`
- `internal_to_mm(value_ft)` → mm via `UnitUtils.ConvertFromInternalUnits(UnitTypeId.Millimeters)`
- Uses **ForgeTypeId** (`UnitTypeId`), never deprecated `DisplayUnitType`
- Geometry from linked CAD is **never rescaled** — already in project coordinates

### `compat.py` — Revit Version Compatibility
- `element_id_value()`: `Value` (2024+) falls back to `IntegerValue` (2023-)
- `get_element_name()`: `Element.Name.GetValue(el)` with `.Name` fallback
- `runtime_summary()`: `sys.version` for IronPython loader diagnostics

### `cad_links.py` — Find Linked DWGs
- `find_cad_links(doc)`: Collects `ImportInstance` where `IsLinked == True` (excludes embedded imports)
- `describe_link(doc, import_instance)`: Human-readable label from `CADLinkType.Name`

### `geometry_reader.py` — Extract Curves from Linked CAD
- **Method:** Recursive walk of nested `GeometryInstance` with `GetInstanceGeometry()` (returns **project coordinates** — transform already applied)
- **Extracts:** `Line` (2 endpoints), `Arc` (start/mid/end), `PolyLine` (all vertices)
- **Ignores:** Solids, meshes, points, text
- **Unbound curves:** Closed → tessellate; open infinite → skip
- **Layer resolution:** `GraphicsStyle.GraphicsStyleCategory.Name` with full null guards
- **No re-scaling** — coordinates stored verbatim in internal feet

### `layers.py` — Layer → Category Classification
- **Categories:** `grid`, `column`, `beam`, `slab_edge`, `unmapped`
- **Exclusion patterns** (annotation layers never inherit structural): `iden`, `anno`, `text`, `dim`, `defpoint`, `hdln`, `hidden`
- **Default convention** (regex, first match wins): `grid|axis` → grid, `col` → column, `beam|girder|joist` → beam, `slab` → slab_edge
- **Precedence:** Explicit override > exclusion > convention > unmapped
- `classify_layer()`, `build_default_mapping()`, `apply_mapping()` — full pipeline

### `shapes.py` — 2D Shape Parsing (Revit-free, Unit-testable)
- **`Rectangle`**: Axis-aligned, centre + size, mm convenience
- **`OrientedRect`**: Rotated rectangle via minimum-area bounding box (rotating calipers), `long_axis_deg`
- **`Circle`**: Centre + diameter for circular columns
- **Pipeline:** `simplify_ring()` → `is_rectilinear()` → `decompose_to_rectangles()` (grid-partition + greedy merge, exact cover)
- `parse_column_polyline()` → status: rectangle / composite / oriented_rect / degenerate
- `min_area_rect()` → minimum-area oriented box for rotated columns
- `build_line_spines()` — bare lines + leg edges → spine rectangles
- `build_circular_columns()` — 3-point circumcircle from arcs, clustered by centre+radius, diameter 150–2000mm
- `beam_centerline_from_quad()` / `beam_centerline_from_rect()` — derived centerlines
- `pair_parallel_lines()` — parallel edge lines → beam segments on midline

### `report.py` — Reporting & JSON Export
- **DEFAULT_LIMITS:** beam width 150–600mm, column b 150–1500mm, column h 150–20000mm
- `build_layer_counts()`, `build_category_counts()`
- `build_column_sections()` — decomposes polylines, derives circles/spines, filters by limits, snaps to standards (60mm tolerance)
- `build_beam_segments()` — 3 sources: closed outlines, parallel line pairs, arc pairs; width filtering
- `format_console()` — short copy-friendly summary
- `build_report_payload()` — full run report dict
- `export_json()` — intermediate JSON (contract for future ezdxf external validator)
- Standard size parsing: `parse_standard_sizes()` and `parse_standard_widths()`

### `grids.py` — Create Revit Grids
- `GridNamer`: Convention naming — constant-X lines lettered A,B,C...; constant-Y numbered 1,2,3...
- Coordinate suffix convention (see future_plan.md for text-reading upgrade path)
- `create_grids()` — batch creation in caller's transaction, skips duplicate names

### `columns.py` — Place Structural Columns
- Collects `OST_StructuralColumns` family symbols + levels
- `place_columns()` — per distinct (b, h) creates type "300 x 900", places at centre, rotates landscape rectangles
- `place_circular_columns()` — per diameter creates type "600 dia"
- Type caching per session; top level set via `FAMILY_TOP_LEVEL_PARAM`
- Skips rectangles with smaller side > 1500mm (lift/stair regions)

### `beams.py` — Place Structural Framing Beams
- Collects `OST_StructuralFraming` family symbols
- `place_beams()` — per width creates type "300 wide", places along line on level elevation
- `StructuralType.Beam`; skips segments < 50mm
- Width parameter names: `b, width, w, Width, B, W`

### `transactions.py` — Warning Suppression
- `WarningSwallower` (`IFailuresPreprocessor`) — deletes `FailureSeverity.Warning` messages
- `attach_warning_swallower(transaction)` — attaches to failure handling options

### `ui.py` — Stock pyRevit Dialogs (Secondary Path)
- `pick_link()` — `SelectFromList` for multiple links
- `prompt_mapping_override()` — `SelectFromList` + `CommandSwitchWindow` for layer reassignment
- (Note: Primary dialog is WPF-based `CadToBimWindow`; `prompt_mapping_override()` is a fallback not called in the main flow)

---

## 3. Key Design Decisions

1. **No blocking in UI** — All model writes after `show_dialog()` on Revit API thread
2. **Rollback safety** — TransactionGroup + Transaction per pass, rollback on exception
3. **Warning suppression** — Prevents modal dialogs from stalling batch creation
4. **Type duplication** — Per-size types created on-the-fly, cached by dimension
5. **Revit-free shapes** — `shapes.py` is pure 2D math, testable outside Revit
6. **Coordinate integrity** — Linked CAD geometry NEVER rescaled (link transform bakes in DWG scale)
7. **Version compatibility** — `compat.py` isolates Revit 2024/2025 API differences
8. **JSON contract** — Export designed as interface with future external CPython + ezdxf validator
9. **Rectilinear decomposition** — Grid-partition + greedy rectangle merge for exact cover
10. **Arc-based circle detection** — 3-point circumcircle from arc start/mid/end
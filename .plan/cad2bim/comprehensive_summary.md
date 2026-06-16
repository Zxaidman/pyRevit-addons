# CAD to BIM (cad2bim) — Comprehensive Summary

> Consolidated from: `.plan/cad2bim/*.md` + `CAD to BIM.pushbutton/.md/*.md`
> Version: `v0.12.0` | Updated: 2026-06-16

---

## 1. Project Identity & Purpose

| Field | Value |
|-------|-------|
| **Name** | AnonGee CAD to BIM (cad2bim) |
| **Type** | pyRevit Extension — Pushbutton Tool |
| **Version** | `v0.12.0` |
| **Author** | RCC BIM Tools (AnonGee) |
| **Min Revit** | 2022 (target: 2024/2025) |
| **Runtime** | IronPython 2.7.12 (in-Revit); CPython 3.10+ (planned external validator) |
| **Engine** | pyRevit 6.x (.NET 8 on Revit 2025+; .NET Framework on older) |

**Purpose:** Read a linked CAD (DWG), classify curves by layer into structural categories (grid / column / beam / slab-edge), decompose geometry into Revit elements, and create Grids, Structural Columns, and Structural Framing (Beams) — all inside a single undo-able TransactionGroup with warning suppression.

---

## 2. Repository Layout

```
AnonGee.extension/
├── lib/
│   ├── path_resolver.py
│   └── py2/cad2bim/                      ← 14 modules (the cad2bim package)
│       ├── __init__.py    (__version__ = "0.12.0")
│       ├── units.py       compat.py      model.py
│       ├── cad_links.py   geometry_reader.py
│       ├── shapes.py      layers.py
│       ├── ui.py          report.py
│       ├── transactions.py
│       ├── grids.py       columns.py     beams.py
└── AnonGee.tab/Core.panel/CAD to BIM.pushbutton/
    ├── bundle.yaml        script.py      ui.xaml      icon.png
    ├── .json/             .md/                           ← tracking docs
.plan/cad2bim/
    ├── implemented.md     progress.md    project_summary.md
    ├── future_plan.md     comprehensive_summary.md       ← this file
```

---

## 3. Architecture & Data Pipeline (4 Stages)

```
Stage 1: Discovery & Reading
────────────────────────────────────────────────────────────────────
Linked DWG (ImportInstance)
    │
    ▼
cad_links.find_cad_links(doc)   →  List of linked ImportInstances
    │                                (excludes embedded imports)
    ▼
ui.pick_link(doc, links)        →  User selects (or auto-pick if 1)
    │
    ▼
geometry_reader.read_link(doc, import_instance)
    │
    ├─ Walk GeometryInstance tree (GetInstanceGeometry → project coords)
    ├─ Extract: Line (2 pts), Arc (3 pts: start/mid/end), PolyLine
    ├─ Ignores: Solids, meshes, points, text
    ├─ Layer: GraphicsStyle.GraphicsStyleCategory.Name (null-guarded)
    ├─ Unbound curves: Closed → tessellate; Open infinite → skip
    └─ Return: ReadResult (source_name + CurveRecord[])
    ※ Coordinates in Revit internal feet — NEVER rescaled

Stage 2: Classification
────────────────────────────────────────────────────────────────────
ReadResult.records (CurveRecord[])
    │
    ▼
layers.build_default_mapping(layer_names)   →  {layer: category}
    │  Convention regex (first match wins):
    │    grid|axis → grid | col → column | beam|girder|joist → beam | slab → slab_edge
    │  Exclusion patterns force unmapped: iden, anno, text, dim, defpoint, hdln, hidden
    ▼
layers.apply_mapping(records, mapping)      →  stamps .category on each record
    │  Precedence: Explicit override > Exclusion > Convention > Unmapped
    └─ User can override any layer in the WPF dialog

Stage 3: Shape Decomposition
────────────────────────────────────────────────────────────────────
Column-category records                   Beam-category records
    │                                            │
    ▼                                            ▼
report.build_column_sections()           report.build_beam_segments()
    │                                            │
    ├─ Polyline outlines:                       ├─ Closed outlines →
    │  simplify_ring() →                        │  beam_centerline_from_quad()
    │  is_rectilinear()?                        │  or decompose_to_rectangles()
    │  ├─ Yes → decompose_to_rectangles()      ├─ Parallel line pairs →
    │  └─ No → min_area_rect() (oriented)       │  pair_parallel_lines()
    ├─ Arc records →                           ├─ Concentric arc pairs →
    │  build_circular_columns()                │  (detected, NOT placed)
    ├─ Bare lines →                             └─ Width filtering via limits/standards
    │  build_line_spines() (≥2 legs)
    └─ Filtering: limits + standard-size snap (60mm tolerance)

    Column handling:
    ─ Rectilinear (axis-aligned) → exact rectangle decomposition
      (grid-partition + greedy merge: L/C/U/E → N rectangles)
    ─ Rotated (non-axis-aligned) → minimum-area oriented bounding box
      (convex hull + rotating calipers → true size + angle)
    ─ Circular → 3-point circumcircle from arcs, clustered by centre+radius
    ─ Line-spine → bare lines + leg edges → spine rectangles
    ─ Lift/stair blocks (min side > 1500mm) → skipped

    Beam handling (3 sources):
    ─ Source 1: Closed thin outlines → centerline along long axis
    ─ Source 2: Parallel edge lines (~300mm gap) → midline centerline
    ─ Source 3: Concentric arc pairs → detected, reviewed, NOT placed

Stage 4: Element Creation (TransactionGroup + Transaction + rollback)
────────────────────────────────────────────────────────────────────
User selections from WPF dialog
    │
    ├─ Create grids?
    │  └─ grids.create_grids(doc, grid_records, GridNamer)
    │      ├─ Grid.Create(curve) per record
    │      ├─ Convention naming: constant-X → A,B,C...; constant-Y → 1,2,3...
    │      └─ Skip duplicate names (reads existing grid names first)
    │
    ├─ Create columns?
    │  └─ columns.place_columns(doc, sections, family_id, base, top)
    │      ├─ Per distinct (b,h): duplicate type → "300 x 900" (small x big)
    │      ├─ Place at centre, set top level via FAMILY_TOP_LEVEL_PARAM
    │      ├─ Rotate landscape rectangles (long_axis_deg - 90)
    │      └─ Also: place_circular_columns() for circles ("600 dia")
    │
    ├─ Create beams?
    │  └─ beams.place_beams(doc, segments, beam_id, level_id)
    │      ├─ Per width: duplicate type → "300 wide"
    │      ├─ Line.CreateBound → StructuralType.Beam at level elevation
    │      └─ Skip segments < 50mm
    │
    └─ Export JSON?
        └─ report.export_json(path, ...)
            └─ Full payload: curves + mapping + column_sections + beam_segments + outcomes

    ※ Each pass: TransactionGroup + Transaction + WarningSwallower(IFailuresPreprocessor)
    ※ Rollback on any exception; group.Assimilate() on success → single undo step
```

---

## 4. UI Architecture (WPF — CadToBimWindow)

| Section | Controls | Purpose |
|---------|----------|---------|
| Header | Title + version badge | AnonGee brand: charcoal (#141414) + vivid red (#E02020) |
| Source | TextBlock | Selected DWG name |
| Layer mapping | Dynamic Grid rows | Layer → category combo (grid/column/beam/slab_edge/unmapped) |
| Build options | CheckBox × 4 | Grids, columns, beams, export JSON (slab: disabled, "coming soon") |
| Family/Level | ComboBox × 5 | Column family, circular family, base level, top level, beam family |
| Sizing limits | TextBox + Slider × 6 pairs | Beam width min/max, column b min/max, column h min/max (two-way linked) |
| Standard sizes | TextBox × 2 | Column "b×h, ..." and beam widths "w, ..." |

**Design rule:** No Revit API in event handlers — all writes after `show_dialog()`.

---

## 5. Library Modules (14 in `cad2bim/`)

| Module | Lines | Status | Responsibility |
|--------|-------|--------|----------------|
| `__init__.py` | ~30 | Stable | Version + module docs |
| `model.py` | ~70 | Stable | CurveRecord, ReadResult data holders |
| `units.py` | ~30 | Stable | mm ↔ feet (UnitTypeId.Millimeters, never DisplayUnitType) |
| `compat.py` | ~50 | Stable | Revit version shims (ElementId, Element.Name, runtime summary) |
| `cad_links.py` | ~50 | Stable | Find/describe linked DWGs |
| `geometry_reader.py` | ~140 | Stable | Curve extraction from linked CAD |
| `layers.py` | ~80 | Stable | Layer→category classification |
| `shapes.py` | ~450 | Stable | 2D shape decomposition (Revit-free) |
| `report.py` | ~280 | Stable | Section building, console summary, JSON export |
| `grids.py` | ~120 | Stable | Grid creation + convention naming |
| `columns.py` | ~150 | Stable | Rectangular + circular column placement |
| `beams.py` | ~100 | Stable | Beam placement along centerlines |
| `transactions.py` | ~30 | Stable | Warning swallowing via IFailuresPreprocessor |
| `ui.py` | ~80 | Stable | Stock pyRevit dialogs (secondary path; WPF is primary) |

**~2,000 lines total.**

---

## 6. Version History Highlights

| Version | Feature |
|---------|---------|
| `v0.1-0.4` | Reader, layer classification, column polyline decomposition, grids pass (A–H × 1–8) |
| `v0.5` | WPF main window (AnonGee theme) |
| `v0.6` | Columns pass (rectangular, per-size type duplication, family/level pickers) |
| `v0.7` | Line-spine columns (bare lines → spine rectangles) |
| `v0.8` | Circular columns, small×big naming + 90° rotation, lift/stair block skipping |
| `v0.9` | Beam pass (closed outlines + L/U decomposition, structural framing) |
| `v0.10` | Rotated columns (min-area oriented rect), concise console, report in JSON |
| `v0.11` | Parallel-line beams (grid-9 perimeter beams), arc-junction classification |
| `v0.12` | **Current.** Sizing limits + standard-size snapping (min/max sliders + inputs). Validated: drops junction-clipped 1064mm beam; keeps 300×12300 spine. |

---

## 7. Key Design Principles

1. **No blocking in UI** — All writes on API thread after dialog closes
2. **Rollback safety** — TransactionGroup + Transaction per pass; full rollback on failure
3. **Warning suppression** — `IFailuresPreprocessor` prevents modal dialogs
4. **Type duplication** — Per-size types on-the-fly ("300×900", "600 dia", "300 wide"), cached per session
5. **Revit-free core** — `shapes.py` is pure 2D math, testable outside Revit
6. **Coordinate integrity** — Linked CAD geometry NEVER rescale
7. **Version compat** — `compat.py` isolates API diff across Revit 2023→2026
8. **JSON contract** — Export format designed for external CPython + ezdxf validator
9. **Extensibility** — Each creation pass is independent; new passes slot in alongside

---

## 8. Current Status & Completion

| Milestone | Status |
|-----------|--------|
| Geometry reader | ✅ 100% |
| Layer classification | ✅ 95% (convention may need tuning per real DWG) |
| Column shape decomposition | ✅ 100% |
| Beam derivation (3 sources) | ✅ 100% |
| Grid creation | ✅ 100% |
| Column placement (rect + circ) | ✅ 100% |
| Beam placement (straight only) | ✅ 100% |
| WPF Dialog UI | ✅ 100% |
| JSON export | ✅ 100% |
| Warning suppression | ✅ 100% |
| Parallel-line beams | ✅ 100% |
| Sizing limits + standards | ✅ 100% |
| Unit tests for shapes | ⬜ Planned |
| External ezdxf validator | ⬜ Planned |
| Slab creation | ⬜ Planned (UI disabled) |
| Curved beam placement | ⬜ Planned (detected, not placed) |
| Text-based grid labels | ⬜ Planned |

---

## 9. Open Issues & Planned Fixes

### Root Cause (Shared)
At round/angled columns, the CAD's **junction geometry** (extra arcs + short lines at beam/column intersections) clips the neighbouring outlines. A 600×750 column reads as 463×750; a 750×900 as 300×900; a clean beam becomes a 1064mm blob.

### Fixed in v0.12.0
- Grid-9 perimeter beams → parallel-line pairing (8 beams recovered)
- False beams at round columns → arc-junction classification (0 false beams)
- Spurious 1064mm beam → width limit (150-600mm default) drops it
- Rotated columns oversized → min-area oriented rectangle recovers true size+angle

### Open
| Issue | Cause | Planned Fix |
|-------|-------|-------------|
| Angled columns F/G (500×900) missing | Outlines clipped by junction | Reconstruct from parallel edge-lines (broken segments merged before pairing) |
| Two vertical beams missing (grid A & F, rows 8-9) | Junction clipping | Same fix as above — comes for free |
| Curved beam placement | Arc framing not implemented | Deferred until test case available |
| Beam-to-column end gaps | Beams stop at column face | Optional: extend centerline to column centre at round/angled columns |

### Tuning Controls Added (v0.12.0)
- Beam width: 150–600mm (default; adjustable)
- Column b (short side): 150–1500mm
- Column h (long side): 150–20000mm
- Standard sizes: columns "b×h, ..." and beam widths "w, ..." — snapped to nearest within ~60mm

---

## 10. Future Roadmap

| Version | Target | Major Features |
|---------|--------|---------------|
| `v0.13.0` | Q3 2026 | Unit tests for shapes.py; layer convention tuning |
| `v0.14.0` | Q3 2026 | Slab edge creation pass |
| `v0.15.0` | Q4 2026 | Curved beam placement |
| `v0.16.0` | Q4 2026 | Grid label text extraction |
| `v1.0.0` | Q1 2027 | External CPython + ezdxf validator |
| `v1.1.0` | Q2 2027 | Performance, UI polish, user docs |

**Key deferred features:**
- **Text extraction (hybrid method):** Capture Revit transform matrix → background DWG/DXF read (ASCII DXF group codes) → extract raw text strings with local CAD coordinates → map through transform into Revit coordinates → match to nearest column/beam → set true sizes and marks (e.g. "C1 400×400", "B1 230×500").
- **Slab creation:** `slab_edge` category classified; `chk_slabs` checkbox exists but disabled.
- **Extensible Storage batch stamp:** For idempotent re-runs (find/skip prior output).
- **Beam-graph planar-face slab derivation:** Minimal-cycle face traversal for floor boundaries.

---

## 11. Technical Reference — Revit API Cheat Sheet

| Operation | Method | Notes |
|-----------|--------|-------|
| Find linked DWGs | `FilteredElementCollector(doc).OfClass(ImportInstance)` where `IsLinked == True` | Excludes embedded imports |
| Read geometry | `GetInstanceGeometry()` → project coords | NEVER double-transform |
| Layer name | `doc.GetElement(geom.GraphicsStyleId).GraphicsStyleCategory.Name` | Null-guard; can be InvalidElementId |
| Unit conversion | `UnitUtils.ConvertToInternalUnits(val, UnitTypeId.Millimeters)` | Never `DisplayUnitType` (deprecated 2021) |
| Grid creation | `Grid.Create(doc, line)` / `Grid.Create(doc, arc)` | Line/arc must be horizontal |
| Column placement | `doc.Create.NewFamilyInstance(XYZ, symbol, level, StructuralType.Column)` | `symbol.Activate()` + `doc.Regenerate()` first |
| Beam placement | `doc.Create.NewFamilyInstance(curve, symbol, level, StructuralType.Beam)` | Z-justification for height |
| Slab creation | `Floor.Create(doc, curveLoops, floorTypeId, levelId)` | Since 2022; `FLOOR_HEIGHTABOVELEVEL_PARAM` for elevation |
| Type duplication | `baseType.Duplicate("Name")` | Always check existing first; throws if duplicate name |
| Transaction safety | `TransactionGroup` + inner `Transaction` + `IFailuresPreprocessor` | `Assimilate()` for single undo; `RollBack()` on failure |
| Extensible Storage | `SchemaBuilder` → `AddSimpleField` → `Entity` → `SetEntity` | Hidden batch stamp for re-runs |
| Warning suppression | `IFailuresPreprocessor.PreprocessFailures` → `DeleteWarning()` → `FailureProcessingResult.Continue` | Deletes only warnings, not errors |
| Runtime | IronPython 2.7.12 (default); CPython 3.10+ (for external ezdxf) | .NET 8 split at Revit 2025 — pyRevit 6.x fixed this |

---

## 12. Installation Notes

1. Delete any stale `lib/cad2bim` (root level) — only ONE copy under `lib/py2/cad2bim/`
2. Delete old `lib/py2/cad2bim/` and replace with new version (don't merge)
3. Delete `*.pyc` / `__pycache__` under cad2bim
4. Run `pyrevit reload` (or restart Revit) — editing `cad2bim/*.py` requires reload
5. Verify version on run: `cad2bim {ver} loaded from ...\lib\py2\cad2bim`
6. Embedded DWGs (imported, not linked) are ignored — only linked CADs are read

---

*Consolidated from 11 source documents across `.plan/cad2bim/` and `CAD to BIM.pushbutton/.md/`*
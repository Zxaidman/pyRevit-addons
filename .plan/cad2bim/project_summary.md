# CAD to BIM — Project Summary

## Project Identity

| Field | Value |
|-------|-------|
| **Name** | AnonGee CAD to BIM |
| **Type** | pyRevit Extension — Pushbutton Tool |
| **Version** | `cad2bim v0.12.0` |
| **Author** | RCC BIM Tools (AnonGee) |
| **Min Revit** | 2022 |
| **Runtime** | IronPython 2.7 (in-Revit) + CPython 3.x (external validator, planned) |
| **Repository** | [github.com/Zxaidman/pyRevit-addons](https://github.com/Zxaidman/pyRevit-addons) |
| **License** | MIT (inferred) |

---

## Purpose

Read a **linked CAD (DWG)** file in Revit, classify its curves by **layer convention** into structural categories (grid / column / beam / slab-edge), and **create Revit elements** from the classified geometry.

The tool handles the full pipeline:
1. **Discover** linked DWGs in the active Revit document
2. **Read** all curves (lines, arcs, polylines) in project coordinates
3. **Classify** each curve by its CAD layer into a structural category
4. **Decompose** column outlines into rectangular sections (handles L/C/U/E shapes, rotated columns, circles)
5. **Derive** beam centerlines from closed outlines, parallel line pairs, and arc pairs
6. **Create** Revit Grids, Structural Columns, and Structural Framing (Beams)
7. **Report** the results in the pyRevit output window
8. **Export** an intermediate JSON file (contract for a future external validator)

---

## Architecture Overview

```
                    ┌─────────────────────────────────────┐
                    │      CAD to BIM.pushbutton          │
                    │  (script.py + ui.xaml + bundle.yaml) │
                    └──────────────┬──────────────────────┘
                                   │ imports
                    ┌──────────────▼──────────────────────┐
                    │         cad2bim package             │
                    │        (lib/py2/cad2bim/)           │
                    │                                     │
                    │  ┌──────────┐  ┌───────────────┐   │
                    │  │ model.py │  │  units.py      │   │
                    │  │ compat.py│  │  transactions  │   │
                    │  └──────────┘  └───────┬───────┘   │
                    │                         │           │
                    │  ┌──────────┐  ┌───────▼───────┐   │
                    │  │cad_links │  │ geometry_reader│   │
                    │  └────┬─────┘  └───────┬───────┘   │
                    │       │                │            │
                    │  ┌────▼────────────────▼───────┐   │
                    │  │        layers.py             │   │
                    │  │   (classification engine)    │   │
                    │  └────────────┬─────────────────┘   │
                    │               │                     │
                    │  ┌────────────▼─────────────────┐   │
                    │  │         shapes.py             │   │
                    │  │  (2D decomposition engine)    │   │
                    │  └────────────┬─────────────────┘   │
                    │               │                     │
                    │  ┌────────────▼─────────────────┐   │
                    │  │         report.py             │   │
                    │  │  (section building + export)  │   │
                    │  └──┬──────────┬──────────┬──────┘   │
                    │     │          │          │          │
                    │  ┌──▼──┐  ┌────▼────┐ ┌──▼───┐      │
                    │  │grids│  │columns  │ │beams │      │
                    │  └─────┘  └─────────┘ └──────┘      │
                    └─────────────────────────────────────┘
```

---

## System Architecture & Data Flow

### Stage 1: Discovery & Reading

```
Linked DWG (ImportInstance)
       │
       ▼
cad_links.find_cad_links(doc)    ──►  List of linked ImportInstances
       │
       ▼
ui.pick_link(doc, links)         ──►  User selects one link (or auto-pick if 1)
       │
       ▼
geometry_reader.read_link(doc, import_instance)
       │
       ├─► Walk GeometryInstance tree (GetInstanceGeometry)
       ├─► Extract: Line (2 pts), Arc (3 pts), PolyLine (all vertices)
       ├─► Resolve layer from GraphicsStyleCategory.Name
       └─► Return: ReadResult (source_name + CurveRecord[])
```

**Key property:** All coordinates are in **Revit internal feet** with the DWG drawing-unit scale already baked in by the link transform. **Never rescaled.**

### Stage 2: Classification

```
ReadResult.records (CurveRecord[])
       │
       ▼
layers.build_default_mapping(layer_names)    ──►  {layer: category} from convention
       │
       ▼
layers.apply_mapping(records, mapping)       ──►  stamps .category on each record
       │
       └─► Classification precedence:
            1. Explicit override (from dialog)
            2. Exclusion pattern (annotation → unmapped)
            3. Convention regex match (grid|axis, col, beam|girder|joist, slab)
            4. Unmapped
```

### Stage 3: Shape Decomposition

```
Column-category records                  Beam-category records
       │                                        │
       ▼                                        ▼
report.build_column_sections()          report.build_beam_segments()
       │                                        │
       ├─► Polyline outlines:                   ├─► Closed outlines →
       │   simplify_ring() →                    │   beam_centerline_from_quad() or
       │   is_rectilinear()?                   │   decompose_to_rectangles()
       │   ├─ Yes → decompose_to_rectangles()  ├─► Parallel line pairs →
       │   └─ No → min_area_rect()              │   pair_parallel_lines()
       ├─► Arc records →                       ├─► Arc pairs →
       │   build_circular_columns()            │   circle_from_three_points()
       ├─► Bare lines →                         └─► Return: beam segments
       │   build_line_spines()
       └─► Return: sections + circles
```

**Column handling:**
- **Rectilinear** (axis-aligned L/C/U/E) → exact rectangle decomposition (grid-partition + greedy merge)
- **Rotated** (non-axis-aligned) → minimum-area oriented bounding box (rotating calipers)
- **Circular** → 3-point circumcircle from arc start/mid/end, clustered by centre+radius
- **Line-spine** → bare lines paired with ≥2 leg edges at consistent offset

**Beam handling:**
- **Closed thin outlines** → centerline along long axis
- **Multi-segment outlines** → decompose to straight beam segments
- **Parallel line pairs** → centerline on midline of paired edges
- **Arc pairs** → concentric curved beams (detected, reviewed, NOT yet placed)

### Stage 4: Element Creation

```
User selections from WPF dialog
       │
       ├─► Create grids?
       │   └─► grids.create_grids(doc, grid_records, GridNamer)
       │       ├─► Grid.Create(curve) per record
       │       ├─► Name via convention (A,B,C / 1,2,3)
       │       └─► Skip duplicate names
       │
       ├─► Create columns?
       │   └─► columns.place_columns(doc, sections, family_id, levels)
       │       ├─► Per distinct (b,h): duplicate type → "300 x 900"
       │       ├─► Place at centre, set top level, rotate if landscape
       │       └─► Also: place_circular_columns() for circles
       │
       ├─► Create beams?
       │   └─► beams.place_beams(doc, segments, beam_id, level_id)
       │       ├─► Per width: duplicate type → "300 wide"
       │       ├─► Create along line at level elevation
       │       └─► Skip segments < 50mm
       │
       └─► Export JSON?
           └─► report.export_json(path, ...)
```

**Transaction safety:** Each pass runs inside a `TransactionGroup` + `Transaction` with:
- `WarningSwallower` attached to suppress modal warnings (coincident grids, etc.)
- Full rollback on any exception
- `group.Assimilate()` on success (merges into single undo step)

---

## UI Architecture (WPF)

The `CadToBimWindow` in `script.py` uses `ui.xaml` with:

| Section | Controls | Purpose |
|---------|----------|---------|
| Header | Title + version badge | Brand identity |
| Source display | TextBlock | Shows selected DWG name |
| Layer mapping | Dynamic Grid rows | Layer → category assignment |
| Build options | CheckBox × 4 | Toggle grids/columns/beams/export |
| Family selection | ComboBox × 5 | Column family, circular, base level, top level, beam family |
| Sizing limits | TextBox + Slider × 6 pairs | Beam width, column b, column h (min/max) |
| Standard sizes | TextBox × 2 | Column b×h pairs, beam widths |

**Theme:** AnonGee brand — charcoal black header (#141414), vivid red accent (#E02020), JetBrains Mono font, silver steel neutrals (#C0C8D8).

---

## Key Design Principles

1. **Separation of concerns** — Each `cad2bim` module has a single responsibility
2. **No blocking in UI** — All Revit writes happen after dialog closes
3. **Revit-free core math** — `shapes.py` is pure 2D geometry, testable outside Revit
4. **Fail-fast with rollback** — TransactionGroups ensure no partial model state
5. **Warning suppression** — Modal dialogs never stall batch creation
6. **Version compatibility** — `compat.py` isolates API differences across Revit versions
7. **Coordinate integrity** — Linked CAD geometry NEVER manually rescaled
8. **Type caching** — Per-size family types created once per session, cached by dimension
9. **JSON contract** — Export format is designed for external CPython + ezdxf validator
10. **Extensibility** — Each creation pass is independent; new passes (slabs) can be added alongside existing ones

---

## Current Limitations

- **No slab creation** — `slab_edge` category is classified but no creation pass exists
- **No curved beam placement** — Detected arc pairs are reviewed but not placed
- **No text-based grid labels** — Grid naming follows positional convention (no DWG text reading)
- **No automated tests** — `shapes.py` is designed for unit testing but no test suite exists
- **Layer convention is a placeholder** — Default regex patterns need tuning per real CAD sources
- **Family parameter names** — b/h/width fallback lists may not cover all family conventions
- **Non-rectilinear shapes are approximated** — Fallback to oriented bounding box; review recommended

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Revit API | `Autodesk.Revit.DB` (2022+) |
| UI Framework | WPF (XAML + IronPython binding via pyRevit) |
| Python Runtime | IronPython 2.7 (in-Revit) |
| Package Manager | pyRevit (no pip dependencies inside Revit) |
| External Validation | CPython 3.x + ezdxf (planned, consumes JSON export) |
| Unit Testing | Python `unittest` (planned, for `shapes.py`) |
| Version Control | Git + GitHub |
| Brand Guidelines | AnonGee BIM Tools (see `AnonGee_BIM_Tools_Brand_Guidelines.md`) |

---

## Repository Structure (relevant paths)

```
AnonGee.extension/
├── AnonGee.tab/
│   └── Core.panel/
│       └── CAD to BIM.pushbutton/
│           ├── bundle.yaml
│           ├── icon.png
│           ├── script.py
│           └── ui.xaml
└── lib/
    └── py2/
        └── cad2bim/
            ├── __init__.py
            ├── beams.py
            ├── cad_links.py
            ├── columns.py
            ├── compat.py
            ├── geometry_reader.py
            ├── grids.py
            ├── layers.py
            ├── model.py
            ├── report.py
            ├── shapes.py
            ├── transactions.py
            ├── ui.py
            └── units.py
.plan/
├── implemented.md
├── progress.md
├── project_summary.md
└── future_plan.md
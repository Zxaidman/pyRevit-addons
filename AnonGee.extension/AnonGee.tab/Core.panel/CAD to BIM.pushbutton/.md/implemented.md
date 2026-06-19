# Implemented — CAD to BIM

Live inventory of completed, working features. Updated after every change.

## v0.1.0 — Pass 1: Skeleton + lib + linked-CAD geometry reader

Scope locked to a reader-only vertical slice. **No Revit elements are created.**
Targets `AnonGee.extension` → `AnonGee.tab` → `Core.panel` → `CAD to BIM.pushbutton`.

### Bundle / skeleton
- Files drop into the existing `Core.panel/CAD to BIM.pushbutton/` folder:
  `bundle.yaml` + `script.py` (thin entry; all logic in `lib/cad2bim`).
- Startup self-check logs the runtime + host Revit version (surfaces the
  Revit-2025 IronPython loader situation — a pyRevit 5.1-line issue reworked in
  the 6.x line — if it ever recurs).

### Shared library (`lib/cad2bim/`, beside `path_resolver.py`)
| Module | Responsibility |
| --- | --- |
| `units.py` | mm ↔ internal feet via `UnitTypeId` only (never `DisplayUnitType`). |
| `compat.py` | `ElementId.Value`/`IntegerValue` + `Element.Name` version-robustness; runtime summary. |
| `model.py` | `CurveRecord` / `ReadResult` data holders (IronPython 2.7 safe). |
| `cad_links.py` | Find linked DWGs (`IsLinked == True`); describe via `CADLinkType`. |
| `geometry_reader.py` | Extract Line/Arc/PolyLine/other curves; uniform `GetInstanceGeometry()` recursion (no double-transform); layer via `GraphicsStyleCategory.Name`. |
| `layers.py` | Convention-based layer→category classification + exclusion of ID/annotation layers + `apply_mapping`. |
| `shapes.py` | Pure-Python (Revit-free) rectilinear shape simplify + decompose C/L/E/U columns into rectangles. |
| `ui.py` | pyRevit `forms` dialogs: link picker + hybrid mapping-override loop. |
| `transactions.py` | `IFailuresPreprocessor` warning swallower + attach helper for batch creation. |
| `grids.py` | Create Revit grids from grid lines/arcs; convention naming (letters × numbers). |
| `report.py` | Text summary + column-section decomposition + line-member report + JSON export. |

### Behaviour delivered
- Detects and lets the user pick among multiple linked DWGs.
- Reads curves in project coordinates, **not rescaled** (CAD units preserved).
- Captures CAD layer per curve with full null-guarding.
- Classifies layers by a default convention; user can override any mapping.
- Prints per-layer and per-category summaries to the pyRevit output window.
- Optional JSON export of the parsed curves (QA + groundwork for the validator).

### Verified
- All modules pass `py_compile` (syntax clean, no py3-only constructs).
- Engine target confirmed: IronPython 2.7.12 default on pyRevit (Revit 2025).
- Import path fixed: `cad2bim` lives in `lib/py2/`; `script.py` calls the repo's
  `path_resolver.update_paths()` (with a defensive fallback) before importing it,
  resolving the initial `ImportError: No module named cad2bim`.
- **Live test 1 (column-only DWG): PASS.** 61 closed-quad polylines on `S-COLS`
  classified as `column`; JSON export verified — `units: internal_feet` (not
  rescaled), quads closed (first == last), dimensions metric-sane (e.g. ~230 mm
  widths). Output is directly usable for the column-placement pass.
- **Unbound-curve crash fixed:** full-layer DWG raised "curve is not bound" on an
  unbound curve. `_curve_points` now checks `curve.IsBound` first — closed
  unbound curves (circles) are tessellated, open ones (infinite/xlines) skipped.
- **Live test 2 (all layers): PASS** — 319 curves, 17 layers read through.
- **Convention refined & verified** against the real 17-layer set: ID/annotation
  layers (`-IDEN`, `-ANNO`, `-TEXT`, `-DIMS`, `Defpoints`) now force `unmapped`,
  fixing `S-GRID-IDEN` (grid bubbles) → grid; `floor` dropped as a slab token so
  `A-FLOR` (architectural) no longer mis-reads as `slab_edge`.
- **C/L/E/U lift-core decomposition added & validated** on real S-COLS data:
  collinear vertices simplified (raw 6/8-corner counts were inflated), then
  rectilinear shapes split into rectangles. Result: 52 plain columns, 1 composite
  U lift-core → two 300×3300 mm legs, 1 rotated column flagged for review. Each
  rectangle (centre + size) is reported and written to JSON under
  `column_sections` for the placement pass.
- **Validated across 3 test DWGs (Level-1/Level-2).** Both lift-core conventions
  handled: adjacent-rectangle E (spine + 4 legs as 5 abutting rectangles, each
  captured) and open-loop E (legs captured via decomposition + bbox fallback).
- **Line-drawn members surfaced:** bare lines on a column layer (e.g. a lift
  spine drawn as a 12300 mm centreline) are reported as `line_member` candidates
  (count + lengths, in console and JSON) pending a width rule.
- **Convention:** `hdln`/`hidden` excluded (S-BEAM-HDLN → unmapped); A-FLOR
  dual-source slab via user override confirmed working.

### Grids pass (NEW — first element creation)
- `Grid.Create` from classified `S-GRID` lines/arcs, inside a `TransactionGroup`
  + inner `Transaction` with `WarningSwallower` (`IFailuresPreprocessor`); both
  roll back on any failure so the model is never half-written.
- Convention naming validated on the 16 real grid lines → `A`–`H` (8 vertical)
  × `1`–`8` (8 horizontal). Existing grid names are read first to avoid clashes.
- **Known limitation:** real DWG grid *label text* is not exposed by the Revit
  geometry API (only curves/arcs come through), so names are convention-based;
  the namer is structured to accept a text-derived mapping later if available.
- Not yet tested inside Revit (no Revit in this environment) — syntax verified.

### WPF main window (NEW — v0.5.0)
- `CAD to BIM.pushbutton/ui.xaml` + a `CadToBimWindow(forms.WPFWindow)` in
  `script.py`. One window following the AnonGee BIM Tools theme: charcoal header
  with `AnonGee · CAD to BIM` + version badge, 3px Vivid Red rule, layer-mapping
  table (per-layer category ComboBox), build checkboxes (grids on; columns/beams/
  slabs shown-but-disabled per the "don't hide disabled controls" rule), JSON
  export toggle, off-white footer with status badge + Run / Cancel.
- Capture-only: the window holds no Revit API references and writes nothing. It
  gathers selections into `self.result` and closes; reading happens before it and
  all model writes happen after `show_dialog()` returns, on the API thread.
- Replaces the former stock `forms` mapping-override + grid/export prompts.
- XAML is well-formed; needs in-Revit render test (no Revit in this environment).

### Columns pass (NEW — v0.6.0)
- `columns.py`: places a rectangular structural column for every decomposed
  rectangle (plain, composite legs, and bbox-approximated non-rectilinear).
  Cross-section from the rectangle (b = X-extent, h = Y-extent, placed un-rotated);
  height from the chosen base/top levels.
- Per-size type duplication with a session cache: types named "b x h"
  (e.g. "300 x 900", "300 x 3300"); b/h set via type params with fallbacks
  (`b`/`width`/`W` and `h`/`depth`/`D`). Existing same-named types are reused.
- Window now reads the model's loaded **structural-column families** and **levels**
  and offers them as dropdowns (Family/Type, Base level, Top level) — no hardcoded
  family names. If no column family is loaded, the option disables itself with a
  "load a structural column family first" message (fail loud, fail useful).
- Writes run in a `TransactionGroup` + `Transaction` with warning suppression and
  rollback. NOT yet placing the line-drawn spine (Core A) — deferred to the
  line-spine rule. Syntax + XAML verified; needs in-Revit test.

### Not yet implemented (by design — see progress_report.md)
- Element creation (grids, columns, beams, slabs).
- External ezdxf validator process.
- Extensible Storage batch stamp / re-run idempotency.
- Beam-graph planar-face slab derivation.

### Line-spine columns (NEW — v0.7.0)
- `shapes.build_line_spines`: turns a bare column-layer line into a rectangle by
  measuring the perpendicular gap to the legs that meet it (>= 2 legs at a
  consistent edge on the same side). Width = measured gap (no assumed value);
  length = line extent. Validated: the 12300 mm lift line -> one 300x12300 column;
  the 3000 mm edge line (one leg only) -> correctly ignored.
- Spines flow through `build_column_sections` as a `line_spine` entry, so the
  columns pass places them automatically (total sections 57 -> 58).

### Column refinements + circular columns (v0.8.0)
- Type naming is always smaller-side b x bigger-side h ("300 x 900"); landscape
  rectangles are rotated 90 deg at placement, so b/h-swapped duplicates collapse
  to one type while the footprint/orientation stays correct.
- Lift/stair region blocks (smaller side > 1500 mm, e.g. 2700x3300, 5700x3300)
  are skipped and reported, not placed as columns.
- Circular columns: arcs on the column layer are fitted to exact circles
  (3-point circumcircle) and clustered (a circle drawn as several arcs collapses
  to one). Each becomes a column from a user-picked circular family, diameter set
  via d/diameter/D fallbacks ("600 dia" type). Validated: 17 arcs -> two 600 mm
  circular columns. Window has a separate "Circular family" picker.

### Circle-artifact fix + beam pass (v0.9.0)
- Circle artifact: a polyline whose centre falls inside a detected circle is
  discarded (status circle_artifact), so arc fragments of a round column captured
  as polylines no longer become spurious rectangles. Fixed the 150x260 overlapping
  a 600 mm circular column; the real 300x3300 slanted leg is kept.
- Beams: centerline = long axis of each thin outline (rotated quads handled via
  short-edge midpoints, so diagonal beams work); L/U outlines decompose into one
  straight beam per rectangle. Placed as structural framing along the centerline at
  the columns' TOP level, no offset. Width (b) set from the outline; depth (h)
  inherited from the user-picked type (2D plan carries no per-beam depth). Type
  duplicated per width ("300 wide"). Window has a Beam family picker.
- Validated on Level-3: 93 rect + 3 L (6 segs) = 99 beams, all 300 wide; 5 curved
  + 3 bare-line beams surfaced for review (not placed).

### Rotated columns + concise console/JSON (v0.10.0)
- Rotated rectangular columns: non-axis-aligned column outlines now use a
  minimum-area oriented bounding rectangle (convex hull + rotating calipers), so a
  600x750 drawn at 45/60 deg is recovered as 600x750 at its true angle (status
  oriented_rect) and placed rotated, instead of an oversized axis-aligned bbox.
  Placement rotation unified: rotate by (long_axis_deg - 90), covering axis-aligned
  landscape and rotated columns with one formula. Validated: both rotated columns
  recovered as exactly 600x750 (rotate 30 and -45 deg).
- Console trimmed to a short 4-line summary; the full run report (categories,
  layers, column/beam breakdowns, creation outcomes, console text) is embedded in
  the exported JSON under "report" so the console no longer needs to be copied.

### Parallel-line beams + arc junctions (v0.11.0)
- Beams drawn as two parallel ~300 mm edge lines (perimeter / grid-line beams) are
  now paired into a centerline (width = measured gap) via shapes.pair_parallel_lines.
  Validated on Test10: 8 grid-9 beams recovered (were missing), all 300 wide.
- Arcs on the beam layer that are centred on a detected round column are classified
  as junction fillets and ignored; non-junction concentric arc pairs are detected as
  curved beams (placement to follow). Test10: all 14 arcs = junctions, 0 false beams.
- Fix: script.py now hands the detected circles to build_beam_segments so junction
  classification actually runs (previously arcs were not matched to round columns).

### Known, still open (junction-clipped angled columns) -- NEXT
- G9 600x750 reads as 463x750 (outline clipped by the beam/column junction);
  F9 angled column skipped; E9 750x900 read as 300x900. Root cause: junction arcs/
  lines cut the angled-column outlines. Candidate fix: reconstruct angled columns
  from their parallel edge-lines (same parallel-pair idea), or strip junction
  geometry before parsing. To be designed with AnonGee.

### Sizing limits + standard sizes (v0.12.0)
- Window "Sizing limits & standards (mm)" section: min/max for beam width, column b
  (short side) and column h (long side), each a slider two-way linked to a numeric
  input; plus standard-size fields (columns as "b x h, ...", beam widths as "w, ...").
- build_beam_segments / build_column_sections now take limits + standards: each
  measurement is snapped to the nearest standard (within ~60 mm) and rejected if it
  falls outside the band. This drops junction-clipped blobs while keeping real
  members. Defaults: beam width 150-600, col b 150-1500, col h 150-20000.
- Validated on Test11: the spurious 1064 mm-wide beam at the F-G junction is dropped
  by the default beam-width limit (raising the max to 1200 lets it back in), and the
  spine (300 x 12300) still passes because h_max is generous.

### DXF-pick entry + ezdxf hybrid extraction + text sizing (v0.13.0)
Major remodel of the trigger and the data pipeline (see plan + findings docs).

- **New entry point — CAD-free model is the normal case.** The button no longer
  requires a pre-linked DWG. It asks the user to pick a `.dxf`, choose its drawing
  unit (mm/cm/dm/m/ft/in) and positioning (Auto Center-to-Center / Origin-to-Origin
  / By Shared Coordinates), then **links it programmatically** via
  `dxf_linker.link_dxf` (`Document.Link` + `DWGImportOptions`, own Transaction).
  The old `cad_links.find_cad_links` / `ui.pick_link` entry is removed.
- **Engine moved to pyRevit CPython3** (`#! python3`). `cad2bim` now lives in
  `lib/py3/` (was `lib/py2/`); the code was already py3-clean. This lets `ezdxf`
  import in-process from `lib/py3` — no external interpreter, no subprocess.
  Provisioned via `tools/auto_provision.py` (added `ezdxf`; fixed its stale
  `pyZaid.extension` path to `AnonGee.extension`).
- **Hybrid extraction.** `geometry_reader.read_link` still reads the Revit link
  (internal feet). `dxf_reader.read_dxf` reads the *same* DXF with ezdxf for
  geometry **and TEXT** (TEXT/MTEXT + block INSERT/ATTRIB tags), ascii **and
  binary**. `transform.build_dxf_to_internal` maps DXF coords to internal feet from
  the link's `GetTotalTransform()`, validated against the two geometry bboxes with
  an empirical scale+translation fallback on a gross mismatch.
- **Compare + auto-correct.** `compare.diff` aligns Revit-link vs DXF geometry and
  reports problem geometry (members the Revit import drops/merges/clips at
  junctions). Element creation builds from the cleaner **DXF geometry**, so the
  junction-clipping issues are corrected at source; the comparison is logged to the
  console + JSON for audit.
- **Text-driven sizing.** `marks.parse_mark` parses "C1 400x400" / "B1 230x500";
  `report.build_column_sections` / `build_beam_segments` refine each member from the
  nearest sized mark — including beam **depth**, which 2D geometry cannot give.
  `beams.place_beams` now sets both width and depth (type "{w} x {h}") when a depth
  is present, else keeps width-only.
- **UI de-themed to stock.** `ui.xaml` stripped of the AnonGee brand resources to
  default WPF controls (all `x:Name`s preserved); branding to return when the tool
  is production-ready.
- **Verified (standalone, no Revit):** all modules `py_compile`; `ui.xaml`
  well-formed with every bound control present; integration test confirms a 500 mm
  square column re-sized to 600x600 (mark C1) and a 250 mm parallel-line beam
  re-sized to 230 wide x 500 deep (mark B1) from text, and JSON export carries the
  `texts` + `comparison` blocks. **Still needs the in-Revit pass** (CPython3 WPF
  render, `Document.Link` out-param, transform alignment under both placements).

### CPython3 engine compliance (v0.13.0, follow-up)
Brought the button in line with the Brand Guidelines CPython3 rules (12.1 / 12.8.4
/ 12.9 / 17), which the first cut violated by importing `pyrevit.forms` and using
`forms.WPFWindow` (the IronPython-only `wpf` module crashes the CPython3 engine).

- **Removed all pyRevit IronPython imports.** No `from pyrevit import ...` anywhere
  in the button or the cad2bim package (verified by grep).
- **Windows load via `XamlReader.Load`** from `.xaml` files (mirrors the shipping
  BIM Generation tool): `clr.AddReference` for PresentationFramework/Core/
  WindowsBase, bind controls with `window.FindName`, wire events with `+=`, show
  with `ShowDialog()`.
- **Active document from `__revit__.ActiveUIDocument.Document`** (not `pyrevit.revit`).
- **Dialogs use `System.Windows.MessageBox`** and `System.Windows.Forms`
  Open/Save file dialogs; console output via `print()`. No `script.get_output`.
- **New `link_options.xaml`** is a small "Link DXF" dialog (file + unit + positioning)
  replacing the stock `forms` pickers; deleted `cad2bim/ui.py` (pyRevit-forms based).
- Root `<Window>` attributes are literals only (no `StaticResource`) per 12.7.A.
- Re-verified: `script.py`, `link_options.xaml` + `ui.xaml`, and all cad2bim modules
  compile / are well-formed; text-sizing integration test still passes.

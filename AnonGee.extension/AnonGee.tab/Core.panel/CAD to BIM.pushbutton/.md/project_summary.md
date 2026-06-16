# CAD to BIM (cad2bim) — Project Summary

_A running summary of the tool, its history, conventions, and what's next.
Companion docs: `implemented.md` (feature inventory), `progress_report.md`
(status), `findings_report.md` (issues + fixes), `PLACEMENT.md` (install),
`CAD_Data_Extraction.md` (text-extraction method)._

## 1. What it is
A pyRevit pushbutton, **"CAD to BIM"**, in `AnonGee.extension`. It reads a
*linked* DWG, classifies curves by CAD layer, and generates RCC structural
elements (grids, columns, beams) directly in Revit via the Revit API.

- Target: Revit 2025/2024, pyRevit 6.x on **IronPython 2.7.12** / .NET 8
  (confirmed in-console; the old IP-2.7.12 / Revit-2025 IOError was a pyRevit
  5.1-only bug, not present on the 6.x line).
- The window is **modal & capture-only**: it reads the model and collects the
  user's choices, then closes; all Revit writes run afterward on the API thread,
  inside `TransactionGroup` + `Transaction` with a warning swallower + rollback.
- Console prints a concise 4-line summary; the full report (categories, layers,
  column/beam detail, creation outcomes) is embedded in the exported JSON.

## 2. Repo layout
```
AnonGee.extension/
|-- lib/
|   |-- path_resolver.py
|   \-- py2/cad2bim/        <- the package lives here (IronPython 2.7)
|       |-- __init__.py (__version__), units, compat, model, cad_links,
|       |-- geometry_reader, layers, shapes, ui, report, transactions,
|       |-- grids, columns, beams
\-- AnonGee.tab/Core.panel/CAD to BIM.pushbutton/
    |-- script.py, ui.xaml, bundle.yaml
Tracking docs: PLACEMENT.md, implemented.md, progress_report.md,
               findings_report.md, project_summary.md, CAD_Data_Extraction.md
```

## 3. Version history
- **0.1-0.4** — Reader (linked-DWG curve extraction, project coords, never
  rescaled, unbound-curve safe), layer classification with exclusions
  (`-IDEN/-ANNO/-TEXT/-DIMS/Defpoints/HDLN`), column-polyline decomposition into
  rectangles, and the **grids pass** (`Grid.Create`, A-H x 1-8, warning swallower,
  rollback). Grids verified in Revit.
- **0.5** — **WPF main window** in the AnonGee house theme (charcoal header, Vivid
  Red rule, version badge, layer-mapping table, build toggles). Verified working.
- **0.6** — **Columns pass**: structural columns from rectangles; family + base/top
  levels read from the model and picked in the window (no hardcoded names);
  per-size type duplication ("300 x 900"); b/h via type params with fallbacks.
  57 columns, 0 errors. (`StructuralType` imported from
  `Autodesk.Revit.DB.Structure`.)
- **0.7** — **Line-spine columns**: a bare line on the column layer becomes a
  rectangle from the measured gap to the legs meeting it (12300 lift spine ->
  300x12300; coincident 3000 line correctly ignored).
- **0.8** — **Circular columns** (arcs -> exact circumcircle + clustering ->
  user-picked round family), **small x big naming + 90-deg rotation** for
  landscape columns, **skip lift/stair region blocks** (min side > 1500 mm).
- **0.9** — **Beam pass**: centerline = long axis of each thin outline (rotated
  quads + L/U decomposition), placed as framing at columns' top level; width b
  from the outline, depth from the picked type.
- **0.10** — **Rotated rectangular columns** via minimum-area oriented rectangle
  (recovers a 600x750 @45/60 deg at true size + angle); **concise console**;
  **report embedded in JSON**.
- **0.11** — **Parallel-line beams**: grid/perimeter beams drawn as two ~300 mm
  edge lines are paired into a centerline (fixed the missing grid-9 beams);
  **arc-junction classification** (arcs on a round column are ignored, not turned
  into false curved beams). Fixed `script.py` to pass the detected circles to the
  beam builder.
- **0.12 (current)** — **Sizing limits + standard sizes** in the window: min/max
  sliders+inputs for beam width, column b, column h, plus standard-size fields;
  measurements snap to the nearest standard and are rejected outside the band.
  Drops the junction-clipped 1064 mm beam while keeping real members + the spine.

## 4. Key technical learnings
- Reads before the window; all writes after it closes, on the API thread, in a
  transaction group with rollback.
- `StructuralType` is in `Autodesk.Revit.DB.Structure`; column/beam dimensions are
  type params (duplicate per size, cache).
- 3-point circumcircle + clustering recovers circular columns drawn as multiple
  arcs; a minimum-area oriented rectangle robustly reads rotated columns.
- Grid label TEXT is not exposed by the Revit geometry API -> convention naming.
- Beams/columns are often drawn as two parallel edge lines, not closed rectangles
  -> parallel-line pairing is essential.

## 5. Conventions
- Column type naming always smaller-side **b x bigger-side h**; columns rotated to
  match footprint.
- Beams at the columns' top level, no offset (slabs too).
- Delivery: file-scoped change -> updated file(s) only; one-function/few-line
  change -> git-style line diff; full archive (zip) only for major updates.
- Always `pyrevit reload` after editing `lib/cad2bim`; keep one cad2bim under
  `lib/py2`.

## 6. Open issues (see findings_report.md)
The remaining cluster shares one root cause: **at round/angled columns the CAD's
junction geometry clips the neighbouring column and beam outlines** (F/G angled
columns 500x900 missing; G9 reads 463x750; E9 reads 300x900; A/F verticals
missing). Next build: **reconstruct those members from their parallel edge-lines**
(edges exist, possibly broken into segments) -> recovers the angled columns and the
missing verticals together. Then: curved-beam placement, optional beam-to-column
junction trim, and the Extensible Storage batch stamp for idempotent re-runs.

## 7. Next major capability — text extraction (method now provided)
`CAD_Data_Extraction.md` describes the hybrid workflow that unblocks the deferred
items (**beam depth from the beam text layer**, and column/beam **marks/sizes** like
`C1 400x400`, `B1 230x500`). Summary of the method:
1. Capture the CAD link's **Transform Matrix** from the Revit API (position, scale,
   rotation; available even if the link is broken).
2. Path health check via `os.path.exists`; if missing, a file-picker fallback.
3. Read the DWG/DXF **directly off disk** as a background stream (ASCII DXF group
   codes) to pull layer name + raw text string + local CAD coordinates -- this is
   how we get text that the Revit API cannot read from inside a link.
4. Map each local text coordinate through the Transform Matrix into Revit internal
   coordinates so the text lines up with the geometry we already parse.
5. Structure {text, layer, global coord} and use it to drive exact family types,
   dimensions, and levels.

Planned integration: match each extracted text label to the nearest column/beam by
mapped coordinate, parse `name BxH` -> set the member's true size (e.g. real beam
**depth**), overriding/refining the geometry-derived size and the type name. This
runs as a sidecar reader feeding the same intermediate JSON contract.

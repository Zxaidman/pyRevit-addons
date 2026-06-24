# Findings — cad2bim Column Session

## Repository / Environment
- Primary dir: `/home/user/pyRevit-addons`
- Toolkit root on sys.path: `AnonGee.extension/lib/py3`
- cad2bim package: `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/`
- The pyRevit button entry: `AnonGee.extension/AnonGee.tab/Core.panel/CAD to BIM.pushbutton/script.py`
- Version string: `anongee_toolkit/cad2bim/__init__.py` line ~38 (`__version__ = "0.25.0"`).

## Critical environment gotcha (for running anything locally)
- The vendored `numpy` and `ezdxf` under `lib/py3` are **Windows wheels** and FAIL to
  import on Linux: `numpy/__init__.py` calls `os.add_dll_directory` (Windows-only) →
  `AttributeError: module 'os' has no attribute 'add_dll_directory'`; ezdxf then fails
  importing `ezdxf.math.Vec3`.
- FIX used: `pip install --target /tmp/pylibs ezdxf` (installs ezdxf 1.4.4 + a Linux
  numpy) and put `/tmp/pylibs` FIRST on `sys.path` so the Linux versions win.
- The top-level package `anongee_toolkit/__init__.py` imports the Revit/.NET layer
  (`import System`, etc.) which is absent on Linux. FIX: pre-register `anongee_toolkit`
  as a bare namespace package in `sys.modules` (pointing `__path__` at the dir) so its
  `__init__.py` never runs; the `cad2bim` subpackage itself is Revit-free.
- These harness bootstrap snippets were saved to `/tmp/boot.py` and `/tmp/pipe.py`
  (NOT committed; will be gone next session — recreate from progress.md instructions).

## How a column flows through the pipeline (data shapes)
- `readers/dxf_reader.read_dxf(path)` → `DxfReadResult(records, texts)` in DXF coords
  (Test19 fixtures are in **mm**). Records are `model.CurveRecord(kind, points, layer,
  length_ft)`; `.category` is stamped later via `classify/layers.apply_mapping`.
- `model.TextRecord` has `.text`, `.layer`, `.point`, `.point_internal` (Revit feet),
  `.mark`, `.b_mm`, `.h_mm` (set by `classify/marks.parse_texts`).
- Internal units: feet. mm→ft = `/304.8` (`config.MM_PER_FT`, exposed as `_MM` in report.py).
- `report.build_column_sections(records, limits, standards, texts, tolerances)` filters
  `record.category == CATEGORY_COLUMN`, and produces `sections["entries"]`, each entry =
  `{"layer","status","approx","rectangles":[rect.to_dict(), ...]}`.
- `Rectangle.to_dict()` (geom/shapes.py:55-63) → `{center:[cx,cy,cz], width_ft, height_ft,
  width_mm, height_mm}` — NO long_axis_deg, NO mark.
- Entry statuses seen: `rectangle`, `composite`, `recovered_strip`, `recovered_rect`,
  `recovered_core_wall`, `line_spine`, `text_corrected`, `label_recovered`,
  `label_core_wall` (NEW this session).

## Pipeline call order (script.py ~line 636-690)
1. `report.build_column_sections(...)`
2. route text by layer: `column_texts` (layer routes via `classify_text_layer`; column
   text layer = `S-COLS-IDEN`), `schedule` from `marks.parse_schedule`.
3. **NEW: `report.recover_core_walls_from_labels(sections, column_texts, schedule)`**
   (added ~line 672-680, prints "columns: re-tiled N fused core(s) from labels").
4. `report.correct_columns_with_text(sections, column_texts, mark_radius_ft, schedule=,
   grid_x=, grid_y=, grid_snap_ft=)`
5. `report.apply_circle_marks(...)`
6. `report.recover_unplaced_labeled_columns(sections, column_texts, schedule, limits=)`

## Test19 fixture facts (the driving test case)
File: `.../tests/fixtures/cad/StructuralPlan-Test19 without Schedule.dxf`
- Coords in mm. Column geometry layer = `S-COLS` (drawn as LINE segments, mostly NOT
  closed polylines → handled by `recover_rectilinear_columns`, status `recovered_strip`).
- Grid lines on `S-GRID`; grid intersections at x/y = {-300, 3000, 8000, 11000}.
- `config.DEFAULTS["grid_snap_mm"] = 300`.
- Labels use underscore `mark_size` format e.g. `C16_300 X 600`, `C12_900 X 3000`
  (parsed by the 0.23.3 fix). Circular columns labelled `C7_750D`, `C13_900D`.
- Column labels (mark, b_mm, h_mm, pos_mm):
  - C6 300x5300 @(4891,8423); C8 300x3300 @(3337,6111); C9 600x900 @(3214,5663);
    C10 300x5300 @(8337,5058); C12 900x3000 @(6008,3663)  [these 5 = the lift core]
  - C15 600x900 @(2711,363); C16 300x600 @(2629,-2285); C17 600x900 @(7711,363)
  - markless "300 X 600" @(8187,-1887)  [the stub under C17]
  - plus C1,C2,C3,C4,C5,C11,C14,C18 (normal), C7/C13 (circular).

### Lift-core blob (status recovered_strip, 5 mis-cut pieces BEFORE the fix), mm:
- C12 piece center(6500,3000) 3300x900  (over-long: 3300 vs true 3000)
- C10 piece center(8000,5800) 300x4700  (clipped: 4700 vs true 5300, 600 low)
- C9 block center(3300,5000) 900x900     (C9 fused with a C8 corner)
- C8 piece center(3000,6800) 300x2700    (clipped + low)
- C6 piece center(5500,8000) 4700x300    (clipped: 4700 vs true 5300; centre already right)
Cell grid: xs edges = {2850,3150,3750,4850,7850,8150}; ys = {2550,3450,4550,5450,7850,8150}.
TRUE tiling the carve recovers:
- C6 = top row r4 (all cols) → (5500,8000) 5300x300
- C10 = right col c4 r0..r3 → (8000,5200) 300x5300
- C8 = left col c0 r2..r3   → (3000,6200) 300x3300
- C12 = bottom row r0 c3    → (6350,3000) 3000x900
- C9 = c1 r2                → (3450,5000) 600x900

### C15/C16 blob (2 pieces): left (2850,-300)300x900 + tall (3150,-600)300x1500
TRUE: C15 = (3000,-300) 600x900 ; C16 = (3150,-1050) 300x600.

### C17/markless blob (2 pieces): right (8150,-300)300x900 + tall (7850,-600)300x1500
TRUE: C17 = (8000,-300) 600x900 ; markless = (7850,-1050) 300x600 (placed UNNAMED).

## BUGS found & root causes
1. **Lift-core walls mis-placed (Phase 1).** `recover_rectilinear_columns` assembles the
   loose lines into a closed ring then `decompose_to_rectangles` greedily cuts it. The
   greedy cut steals shared corners, so each wall is right-thickness but clipped/extended
   and offset; `correct_columns_with_text` then resizes to the label but keeps the wrong
   centre. ROOT: greedy decomposition can't resolve corner ownership without labels.
2. **C16 vanishes (Phase 2).** C15(600x900)+C16(300x600 stacked below) fuse; decompose →
   2 strips; `correct_columns_with_text._is_split_pair` treats them as one clipped column
   and `_merge_to_label` merges BOTH into C15, consuming C16's geometry. Then
   `recover_unplaced_labeled_columns` finds no leftover geometry for C16 → C16 unplaced.
3. **markless stub vanishes (Phase 3, by-design until user asked to place it).** Same as
   #2 but the lower member is markless; merged into C17. Initially DESIRED (leave markless
   unplaced); user later asked to draw it.

## Solutions evaluated & why chosen/rejected
- **Pure-geometry better decomposition** (assign each cell to its longest strip): tested
  by hand on Test19 — reduced error 600→150mm but NOT exact (top-right corner ambiguous
  between two equal-length walls). REJECTED: can't reach true positions; corners are
  genuinely ambiguous without labels.
- **Anchor resized wall to blob outer edge**: REJECTED — walls are bounded by
  perpendicular neighbours, not the hull; rule doesn't generalize.
- **Label-guided greedy-by-longest carve**: CHOSEN. Reconstructs Test19's true cover
  exactly (verified by hand AND by harness). Generalizes to stacked pairs.
- **Where to run it**: chose a NEW pass BEFORE `correct_columns_with_text` (so the latter
  just names the already-correct walls) rather than rewriting decompose (no labels there)
  or rewriting text-correction (too entangled).
- **mark-required filter**: first added (Phase 1) to avoid touching markless cores; in
  Phase 3 moved from a global filter to a PER-BLOB "has >=1 marked label" gate so the
  Test19 markless stub (in a marked blob) places while Test9/Messy markless-only cores
  stay untouched.

## Builder orientation convention (verified — important for correctness)
`builders/columns.py:85-119`: `small=min(w,h)`, `big=max(w,h)`; type is `small x big`
with big along family Y (long axis 90°). `long_axis_deg` (if None → `0 if width>=height
else 90`); `rotation_deg = long_axis_deg - 90`. So `_wall_rect`'s convention (width=x,
height=y, long_axis_deg=90 if h>=w else 0) is provably identical to the auto-derivation
→ the C6/C12 width/height "swap" in dumps is physically identical placement.

## Key functions added (all in report.py, immediately after _merge_to_label / before
## correct_columns_with_text, around lines 444-620 in the committed version)
- `recover_core_walls_from_labels(sections, column_texts, schedule=None)` — orchestrator.
- `_rect_bounds_mm(rect)` — (x0,y0,x1,y1) mm from a rect dict.
- `_connected_blobs(rects)` — union-find on bbox adjacency (eps=1.0mm).
- `_labels_for_blob(comp, labels)` — (mark,small,big,lx,ly) for sized labels in grown bbox.
- `_unique_edges(values)` — merge edges closer than `_CORE_EDGE_EPS_MM` (2.0).
- `_dims_match(w,h,b,h)` — match cell-rect dims to label in either orientation, tol
  `_CORE_DIM_TOL_MM` (80).
- `_carve_blob_from_labels(comp, comp_labels)` — the cell-grid greedy carve; returns walls
  or None (must fully tile).
- `_cells_free(inside,claimed,r0,r1,c0,c1)` ; `_wall_rect(x0,y0,x1,y1,z,mark)`.
- Constants: `_CORE_LABEL_MARGIN_MM = 1100.0`, `_CORE_DIM_TOL_MM = 80.0`,
  `_CORE_EDGE_EPS_MM = 2.0`.

## Tests
- New file: `anongee_toolkit/cad2bim/tests/test_core_wall_labels.py` (9 tests, all pass):
  true-position tiling, long-axis orientation, consumed-pieces-removed,
  incomplete-labels-fallback, markless-size-labels-do-not-retile (single),
  lone-strip-not-a-blob, stacked-pair-both-placed, markless-lower-both-placed,
  markless-ONLY-core-left-untouched.
- Loader pattern (no Revit): see top of `test_label_recovery.py` / `test_core_wall_labels.py`
  — `_load_report()` uses `importlib.util.spec_from_file_location` to load config.py,
  geom/shapes.py, classify/marks.py, classify/layers.py, report.py by file path under a
  synthetic `_cwl` package.
- `python3 tools/verify_toolkit.py` → "126 passed, 3 failed". The 3 failures are
  PRE-EXISTING and unrelated (import-path quirks: `cannot import name 'marks' from
  anongee_toolkit.cad2bim`, `No module named anongee_toolkit.cad2bim.layers`). Confirmed
  identical on baseline.

---

# BEAMS — Investigation Findings (this session, post-column)

## Beam pipeline locations
- `report.build_beam_segments(records, circles, limits, standards, texts, tolerances)`
  at `report.py:1155`. Sources: (1) closed thin outlines → centerline; (2) PARALLEL LINE
  PAIRS ~one width apart → midline beam (`shapes.pair_parallel_lines`); (3) arcs: junction
  fillets centred on a detected circle are dropped, concentric arc pairs = curved beams
  (DETECTED ONLY, "placement to follow" — NOT placed).
- A beam segment dict = `{start,end,length_mm,width_mm,layer,status}` (NO depth by default).
  `_beam_segment()` at report.py ~ (search "def _beam_segment").
- `report._apply_beam_marks(segments, texts, radius_ft)` adds `depth_mm`/`mark`: matches each
  segment's MIDPOINT to nearest `marks.sized_texts` within `mark_radius_mm`. width=min(b,h),
  depth=max(b,h). ONLY runs if texts passed.
- `report._filter_beam_segments(...)` snaps width to standard, drops widths outside
  `beam_width_min_mm`..`beam_width_max_mm`.
- Builder: `builders/beams.py:40 place_beams(doc, segments, base_symbol_id, level_id)`;
  `_resolve_beam_symbol` makes a type "{w} X {d}" (or "{w}" if depth None → family default
  depth). Width param names `("b","width","w","Width","B","W")`; depth `_DEPTH_PARAM_NAMES`.
- Beam text layer routes via `classify_text_layer` → `CATEGORY_BEAM_TEXT` (contains "beam"/
  "girder"/"joist"). Test19 beam text layer = `S-BEAM-IDEN`. Geometry layer = `S-BEAM`.

## ROOT-CAUSE BUG #1 — FIXED in 5a (this session): beam text never routed
`script.py:638` calls `report.build_beam_segments(revit_result.records,
sections.get("circles"), limits, standards, texts=None, tolerances=tolerances)` — **texts=None**.
And script.py routes `column_texts`, `grid_texts`, `schedule_texts` but NOT `beam_texts`.
=> No beam gets depth or mark; all placed beams use the family's DEFAULT depth.
FIX (analogous to columns): route `beam_texts = [t for t in dxf_result.texts if
text_mapping.get(t.layer_key) == layers.CATEGORY_BEAM_TEXT]` and pass to build_beam_segments
(or add a post-pass). Low risk, but only helps DETECTED beams.

## ROOT-CAUSE BUG #2 (big): straight beams not detected (drawn as single lines)
Test19 S-BEAM geometry = **15 lines + 76 arcs, 0 polylines** (no closed outlines).
Faithful run (circles passed): `{line_pair:1, bare_line_unpaired:13, arc_junction:36,
curved_pair:1, arc_lone:38}` → **only B23 placed (1/23)**.
The 13 bare lines have no parallel partner, so `pair_parallel_lines` rejects them. The beams
are drawn as SINGLE edge lines (perimeter) / centerlines, a source the detector doesn't handle.

### Test19 beam-line inventory (15 lines, mm)
Perimeter edges:
- Left x=-500: V (-46..2550)=B15, V (3450..7775)=B14, V (8225..10538)=B13
- Right x=11200: V (46..2596)=B16, V (8317..10917)=B17
- Top y≈11200: H (104..2750)=B11, H (3250..7700)=B21, H (8300..10917)=B12
- Bottom y=-450: H (-40..2700)=B1?, H (8300..10567)=B2?
- Bottom interior: H y=-600 (3300..7700)=B20/B6 area, H y=-1050 (3300..7700)=B23 (the 1 placed),
  H y=-1350 (3300..7700)
- Interior: H (3150..4850) y=3450 =B4, V (3150,3450)->(3150,4550)

### Arc clusters (76 arcs → circle fits)
- center (11000,8000) r≈375 ×22  = fillets around round col C7 (750 dia) → junction, ignored
- center (11000,3000) r≈450 ×14  = fillets around round col C13 (900 dia) → junction, ignored
- center (11000,5500) r≈2300 ×39 = a GENUINE CURVED BEAM (concentric inner/outer) → B18/B19,
  detected as curved_pair:1 but NOT placed.

### Beam label→nearest-line distances (convention is MIXED / unclear)
Close (<600mm, likely single-line beams): B4(274) B11(550) B12(550) B13/14/15(221)
  B16/17(621) B21(221) B23(221).
Far (1200–2800mm, geometry implied or curved): B3(2392) B5(1162) B6(1312) B7(1287) B8(2263)
  B9(2541) B10(2541) B18(2778) B19(2298) B22(1490) B20(821).
=> NOT a clean 1-line-per-beam mapping. Perimeter beams = single edge line; interior beams
   often have NO close line (implied spans) — EXPECTED OUTPUT IS AMBIGUOUS, needs user input.

## Approaches considered for beams (none implemented yet)
- Reuse the column label-guided carve? Only if beams were closed fused outlines — they are
  NOT (lines+arcs). Likely not directly reusable.
- Single-line-to-beam: needs the EDGE-vs-CENTERLINE distinction + inward offset direction;
  ambiguous without ground truth.
- Curved beam placement: place along arc midline (radius = mean of concentric pair), width =
  gap, depth from label. Builder needs a curved-framing creation path (not yet present).

## Harness for beams (this session, in /tmp — NOT committed)
- `/tmp/beams2.py` = faithful: build_column_sections → circles → build_beam_segments(records,
  circles, None, None, texts=beam_texts). Prints status_counts + placed segments.
- `/tmp/beamarc.py` = fits arcs to circles, clusters by center/radius; dumps all lines.
- `/tmp/beammap.py` = maps each beam label to nearest beam-line distance.
- All depend on /tmp/boot.py + /tmp/pylibs (see progress.md to recreate).

---

# 5c IMPLEMENTED — Curved beam detection + placement (this session)
- Curved beam = two concentric arc EDGES, each a chain of short arc fragments, one beam
  width apart. Old code fit each fragment to a circle and counted concentric PAIRS crudely
  (curved_pair) but discarded them ("placement to follow"), leaving most arcs `arc_lone`.
- NEW (report.py): arc fits now keep endpoint angles + z. `_group_arc_edges` clusters
  fragments into edges (centre tol 250mm, radius tol 60mm -- tight on radius so inner/outer
  never merge). `_curved_beams_from_edges` pairs concentric edges whose radius gap is in the
  beam width band (pair_min..pair_max = 80..700mm), biggest edges first. `_arc_span` finds
  the swept angle as the complement of the LARGEST circular gap in endpoint angles (handles
  wraparound; end_deg may exceed 360 so end>start = CCW sweep). `_curved_segment` dict:
  {kind:curved, center:[cx,cy,z]ft, radius_mm, radius_ft, start_deg, end_deg, width_mm,
  length_mm, layer, status:curved}. `_apply_curved_marks` sets depth=max(label)+mark from
  nearest sized label to the mid-arc point; WIDTH stays the geometric edge gap.
  `build_beam_segments` returns NEW key `curved_segments` (+ width-band filtered).
- Builder (builders/beams.py): `place_curved_beams` mirrors place_beams but the curve is
  `Arc.Create(XYZ(cx,cy,elev), radius_ft, start, start+sweep, XYZ.BasisX, XYZ.BasisY)`
  (start normalised into [0,2pi)). script.py `_create_beams` now places straight + curved
  and merges created/skipped/errors tallies. NOT runtime-verified (no Revit on Linux).
- Test19 curved beam (B18): center(11000,5500), centreline R=2500mm, width=400 (edges
  r2300 inner / r2700 outer), depth 900, span 279->443 deg (164 deg CCW, right side
  connecting round cols C13 bottom & C7 top), length 7160mm.
- Regression: straight-beam counts byte-identical on all 15 fixtures; 3 Messy plans also
  gain curved beams (one +9); arc_lone collapses to ~0. tests/test_curved_beams.py (4 tests).

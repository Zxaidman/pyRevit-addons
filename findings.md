# Findings — cad2bim Column Session

## BEAM-ERA FINDINGS (added after the beam campaign closed at v0.35.0)
- **Beam detection is a Revit-LINK-POLYLINE phenomenon.** The DXF draws beams as loose
  LINES; Revit's link reader merges them into POLYLINES (snakes/quads). The DXF harness
  places ZERO beams — offline debugging needs `beams.raw_geometry` from the JSON export,
  replayed via `tests/replay_beams.py`. Every beam bug was pinned this way.
- **simplify_ring implicitly CLOSES every polyline** (wraps the vertex list). Open snakes
  gain a fabricated closing edge → collinear legs silently deleted (8e), phantom quads
  between grids (8b), whole bays swallowed as 2950-wide bboxes (0.32.0). Cure: explode a
  ring that loses a real vertex / is too wide / is skew >2° into the pair pool.
- **Labels run ALONG their beam** (drafting convention). MTEXT rotation is the
  `text_direction` VECTOR ((0,1,0)=vertical), NOT `dxf.rotation`. Label→beam matching is
  ownership-based (label claims nearest centreline) + orientation-gated (±20°).
- **Snap ends ALONG the beam axis** to the NEAREST round/rotated column's station —
  never onto the centre point (off-axis columns would drag the beam sideways), never
  first-match (two columns in reach collapsed B648 to zero).
- **DXF→Revit text alignment**: grid-anchored bbox fit; when no grid layer exists,
  anchor on ALL shared geometry. NEVER trust GetTotalTransform alone — Revit can bake
  the unit scale into imported geometry and report an identity instance transform.
- **pythonnet gotcha**: Revit API IList<T> parameters do NOT accept Python lists —
  Floor.Create needs System.Collections.Generic.List[CurveLoop].
- **Stress fixture**: `tests/fixtures/make_stress_plan.py` regenerates Test20
  ("StructuralPlan-Test20-Beam Stress test.dxf", $INSUNITS=mm); asserted by
  `tests/test_beam_stress.py` (14 tests).

## SLAB PIPELINE (current state at v0.36.0)
- `slabs_proto.py`: loops from A-FLOR rings (chained if loose), else the beam-perimeter
  GRAPH (ends healed ≤600mm onto carriers, split at X/T crossings, max-CCW face walk,
  bounded faces ≥1 m²). `apply_slab_labels`: "S1 150 THK"/"150 THK." inside the loop;
  mark-only via schedule.
- `builders/slabs.py`: Floor.Create(List[CurveLoop]); nested loops → holes
  (_nest_openings); type duplicated per thickness ("150 THK"); structural flag; Mark.
- `script.py::_create_slabs`: gated on chk_slabs + cb_floor_type picker; level = top
  level; own transaction group; "slabs" in console + JSON export.
- QUEUED: curved beams as graph edges; slab level picker; slab schedule; dedicated
  slab-text layer routing.

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

---

# BEAMS 0.27.0 Revit-run analysis (Phase 6 input)
0.27.0 JSONs: .json/0.27.0_beam_test{15,18_*,19}_with_textmode.json
Test19: created 21 (edge_pair 19). Test18 redrawn/fragmented: created 21 (edge_pair 9).
Test15: created 315 (line_pair 301, bare_line_unpaired 133, degenerate 255, width_oor 23).

## Bug 6b — B4/B5 mark SWAP (ownership)
Test19: placed "B4" beam mid (3000,1350). B4 label (3318,3176) dist 1853; B5 label
(2629,712) dist 738 -> beam is B5's, mismarked B4. Real B4 (label near core y~3450)
unplaced; B5 unplaced. ROOT: `_edge_pair_beams` iterates LABELS, each claims nearest
unused candidate (first-come). Two same-width labels (B4,B5 both 300x600) -> B4 grabs
B5's nearer candidate. NEED candidate owned by NEAREST label (like column `owner` map),
not label-claims-first. Same likely in `_apply_beam_marks` (segment->nearest label) but
that's segment-centric; swap mainly from edge_pair label-centric claiming.

## Bug 6c — B22 missing (900x900)
B22 label 900x900. width 900 > beam_width_max_mm=600 AND > pair_max_width_mm=700 ->
never paired, and filtered. Held earlier; user now wants it.

## Bug 6e — Test18 B20 wrong
Test18 redrawn: B20 (600x900) NOT placed; a None 300x900 beam at (5115,-2624). So B20's
location got a 300-wide unmarked beam instead of 600x900 B20. (Test19 B20 600x900 OK.)
Likely B20's 600-wide edge pair lost to a 300 line_pair + dedup cleared mark.

## Feature 6a — beam end -> rotated/round column centre
Beam end at a ROTATED column (oriented_rect) or ROUND column leaves a gap (beam stops at
bbox/tangent, not centre). Want: snap beam END to column CENTRE when its end is at/near
such a column. Needs column centres + rotated/round flags passed into beam building
(currently build_beam_segments gets only `circles`, not oriented/rect column centres).
Placement-time extend in builders/beams.py OR segment-time in report.py.

## Test15 (analyze fully — most beams, 315 placed)
by_category: beam 1027 curves, column 360. status: line_pair 301, bare_line_unpaired 133,
degenerate 255, width_oor 23, NO edge_pair (slab_edge 0 -> floors not mapped/!present).
255 degenerate + 133 unpaired = many beams missed. Marks up to B680. TODO: full case sweep.

## v0.40.0 — beam-over-column split: the junction/crossing discriminator (durable)
The overlap test8 complained about has THREE shapes, found by a polygon-intersection
census (beam body rect ∩ column footprint) on the export items — the centreline-only
view missed two of them:
1. strict interior crossing (both crossing points inside the span) → split at faces;
2. segment BURIED face-to-face inside one column: the column's own 350×1800 outline
   mis-read as a beam (pair detection). Interval = [0, L], touches BOTH ends, so any
   "skip end-touching intervals" guard silently keeps it → must be DROPPED;
3. end drawn to the column's FAR face: interval touches ONE end; junction vs drawn-across
   is decided by the column CENTRE's station along the beam — beams legitimately end AT
   centres (CAD centrelines + snap_beam_ends_to_columns put them there), so only an end
   >100mm PAST the centre is trimmed back to the near face.
Guards that made it regression-free (0 changes on every non-test8 fixture ever exported):
midpoint must penetrate ≥10mm inside every face (grazing a shared face line never
counts); leftover pieces <100mm dropped; split rebuilds the list REUSING untouched dicts
(so script.py's pre-split snapshot for slabs stays valid); mark → longest piece only.
Column footprint convention (matches builders/columns.py): extent along long_axis_deg =
max(w,h), across = min(w,h); deg None → 0 if width≥height else 90.

## v0.40.0 — slab chain tolerance trap (durable)
Any piece SHORTER than the chain tolerance (150mm) matches the ring end with BOTH of its
own ends; greedy first-match can glue the wrong one and walk the piece out-and-back →
pinch vertex → "self-intersecting outline" skip (test6/7 S8's 142mm junction fillet arc).
Chaining must score all four attach modes (tail/head × fwd/rev) over ALL unused pieces
and take the globally closest. Sibling trap: adjacent panels re-draw shared edges →
duplicate pieces → spurs; dedupe by 10mm-grid fingerprint (min/max endpoint + mid) first.

## v0.41.0 — grid-cell rounding is not node identity (durable)
`round(x/snap)` node keys have a blind spot: two endpoints 44mm apart straddling a cell
boundary stay separate while 49mm-apart points in one cell merge. In the member-edge
face walk that turned a beam edge tip near a column ring corner into a dangling chain →
pruned → the bay face flooded over the beam body (test4/5's slab-beam misalignment, 24
faces). Node identity must be proximity CLUSTERING (union-find over 3×3 neighbour
cells). But cap the cluster spread (~1.5×snap): union-find is transitive, and a run of
closely-spaced vertices (a small fillet's 25mm arc chords) chain-collapses into one node
otherwise — that silently deleted a real bay (caught only by diffing member faces
against slab-edge ground truth). Companion rule: tessellation must never emit chords
shorter than ~2×snap.

## v0.41.0 — unplaced columns still exist (durable)
Column detection's size limits reject blade columns (250×3250) — but the CAD still draws
them and the beam layer may re-trace their outlines. Everything downstream that asks
"is this inside a column?" (beam split, slab member edges) must use DRAWN closed
rectangular column-layer outlines as footprints too (column_outline_footprints), not
just placed sections. Placed-only footprints made split_beams_at_columns blind exactly
where test8's client complaint was (AC19-24/BC23-28).

## v0.42.0 — round columns are drawn as fragment soup (durable)
CAD round columns arrive from the Revit link as DOZENS of tiny arc fragments (2-30mm)
plus quarter arcs plus a many-chord polyline — never one circle record. Any graph pass
that consumes raw column linework must treat the circle like the rects: swallow
everything inside r+pad and emit ONE clean ring. Swallowed fragments must ALSO be kept
out of the arc-triple registry, or they come back as phantom micro-arcs on slab
boundaries ("This curve will make the loop discontinuous" from Floor.Create).

## v0.42.0 — perimeter tests cannot catch member-body faces (durable)
A beam BODY face passes every boundary-based filter when the beam is wide (900 body >
500 mean-width floor, beam fraction 1.0) or when corridors fuse into crosses. Only an
AREA test works: fraction of the face's area covered by placed beam-body rectangles
(grid sampling; >0.5 = member). Real bays measure <0.2 (trim slivers only).

## v0.42.0 — closed outlines are authority for out-of-band columns (durable)
Size limits protect against junk, but a CLOSED 4-corner column-layer outline with a plan
mark beside it is a real column regardless of size (blade/wall columns 250x3250). Place
it at drawn size/position/angle (no grid/size snapping), dedupe against placed
footprints, and attach the nearest unclaimed mark. Fragmented outlines stay unplaced —
closedness IS the safety gate.

## v0.43.0 — placed geometry beats drawn linework for slab outlines (durable)
Slabs are created AFTER beams/columns, so their outlines can be SYNTHESIZED from what was
placed (beam centreline ± w/2 + end caps, column footprint rings) instead of parsing the
drawn linework again — alignment becomes exact by construction and the graph is half the
size. But drawn edges still win where detection is incomplete (test8's unlabelled beams):
run both, pick by covered area. Cluster nodes must PREFER beam-edge points or junction
centroids tilt long straight boundaries; arc spans must emit from FINAL welded ring
positions or adjacent arcs leave "loop discontinuous" gaps.

## v0.43.0 — all-pairs geometry passes do not survive real plans (durable)
_heal_endpoints/_split_at_crossings at O(n²) took 45.6s on test4's ~4k edges (CPython;
worse under pyRevit). Grid-bucket candidate pairs (3m cells, bbox prefilter): 2.1s. Any
future pass touching pairwise segment geometry starts bucketed.

## v0.44.0 — junction caps vs free-end caps (durable)
Synthesized beam end caps are only needed at FREE ends (cantilever tips) to keep the
boundary watertight. At junctions the neighbouring member's edges already bound the
face, and a cap there just deposits corner vertices 40-50mm from ring corners that the
node snap welds into ~24mm jogs. Cap ends only when no column footprint and no other
beam body contains the endpoint.

## v0.44.0 — Project1 + staircase conventions (reference)
LayoutPlan-Project1: same office as test8 (ARCH BEAM / COLUMN / COLUMN NO._ASC +
COLUMN SIZE_ASC text pairs); plus A-STAIR-Steps, A-WALL-CUT-Brick, PARAPET WALL,
RAILING- 1, S-RCC-COL, PT SLAB HATCH (hatch only); NO grid layer. Offline detection:
327 column rects, 661 beams (150-400mm widths, 230 dominant).
StaircasePlan-Test1: S-STRS flights = boundary pair + equidistant riser lines (300mm
treads, 1500mm wide), landings = rects, 'DN' on S-STRS-IDEN, 'ST-n' marks on
G-ANNO-TEXT, SW1..6 shear walls (300x3300/6300) as closed outlines on S-COLS with
S-COLS-IDEN size labels -- the blade-column recovery already handles that shape.

## v0.45.0 — cluster centroids are approximations; carriers are authority (durable)
The face-walk graph welds nodes within snap (50mm): a node is a CENTROID, so every
junction vertex is up to snap/2 off its true position — invisible on plain bays,
glaring where geometry must meet (a wrap arc endpoint 14.4mm off the beam edge). The
walk decides TOPOLOGY only; positions must be re-derived from the authoritative input
CARRIERS afterwards: two-line crossing at corners, line×circle at wrap ends (gate the
intersection to snap distance or mid-wrap chord vertices collapse into the wrap end and
kill the arc run), radial for mid-wrap, carrier foot along edges. Never let tessellated
arc chords into the carrier set — short angled chords near junctions hijack the
two-line branch with garbage intersections.

## v0.45.2 — nearest-two carriers is wrong; ring-edge direction is right (durable)
The exactness pass must pick each vertex's carriers by TOPOLOGY, not proximity: the
vertex belongs to its two ring edges, so it snaps to the crossing of the carriers
PARALLEL to those edges (10° match). Nearest-two grabbed a diamond column's two 45°
ring edges at a junction (both closer than the beam edge) and welded long boundaries
onto the column apex — 24-60mm tilts that axis-aligned plans never show because their
ring edges are collinear with the beam edges and dedupe into one carrier.

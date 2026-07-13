# Progress Log — cad2bim Column Session

## MILESTONE: GRID + COLUMN + BEAM = 100% of known issues SOLVED (user confirmed at 0.35.0)
Fixtures complete: Test9–Test19 + Test20 (the generated stress plan) all clean for
grids, columns and beams. Messy plans intentionally untested for now. The insurance
for future field bugs: beams.raw_geometry in every JSON export + tests/replay_beams.py
(offline replay), the Test20 stress suite (tests/test_beam_stress.py, 14 tests), and a
regression test left behind by every fix.

## v0.41.0 — 0.40.0 feedback: slab/beam alignment root cause + blade columns
- **test4/5 slab-over-beam SOLVED (the "misalignment" since round 1).** A beam edge tip
  44mm from a column ring corner rounded into a different 50mm grid cell → never merged →
  dangled → pruned → bay face flooded over the beam corridor. Node identity is now
  neighbour-cell union-find clustering (any pair ≤50mm merges, cluster spread capped 75mm
  so chains can't swallow geometry). Beam-swallowing faces 24→0; clean bays 249→323; the
  user's two screenshot regions replay pixel-clean.
- Columns are now TRIM geometry in the member-edge source (user's proposal): raw
  column-layer linework inside a placed/derived footprint replaced by the exact ring;
  walls stay (shafts still bounded). Adaptive arc tessellation (chords ≥2×snap) after the
  ground-truth diff caught clustering chain-collapsing a fillet and losing a real bay.
- test1-3 stair wells: beam fraction 0.33 vs real panels ≥0.44 → threshold 0.3→0.35.
  Wall-fraction ceiling tried and rejected (ate real core-adjacent bays).
- test8 double beams: blades 250×3250 (dropped by limits, unplaced) re-traced on the beam
  layer → dedupe_beam_segments (exact twins + contained collinear fragments) +
  column_outline_footprints (closed rectangular column-layer outlines become split
  obstacles even unplaced). Blade-body beams gone, inter-blade connectors kept, 0 solid
  overlaps. Only 3 degenerate cleanups across every other fixture + archives.

## v0.40.0 — test8 beam-over-column (client priority) + SLABS round 6 (0.39.0 feedback, 4 items)
- **split_beams_at_columns** (report.py, after the end snap): a beam outline drawn straight
  ACROSS a column no longer places a beam on top of it. Crossing strictly inside the span →
  split at the column faces; segment buried face-to-face in one column (the column's own
  outline mis-read as a beam — test8's 350×1800 AC6/AC10/BC6 exact matches) → dropped;
  terminal end >100mm past the column CENTRE (drawn to the far face) → trimmed to the near
  face. Ends AT the centre (junction convention = the snap pass target) never move; grazing
  a shared face (<10mm penetration) never counts; <100mm leftovers vanish; mark stays on the
  longest piece. Offline census (beam body ∩ column footprint polygons): test8 29 solid
  overlaps → 0 (233→211 segments); test1-7 and ALL .archive_fixtures exports → ZERO changes.
  Slabs get a PRE-SPLIT snapshot so beam-graph bay loops still run over columns.
  tests/test_beam_split.py (11 cases). Suite now 15 files, all OK.
- test4/5 blank bays: degree-1 stub pruning before the member-edge face walk (96 pinched
  rings were silently filtered = blank areas) → 249 clean faces, 0 non-simple.
- test1-3 without floor layer: _beam_fraction ≥0.3 filter drops wall-bounded lift/stair
  shaft faces (test1 → 47 faces).
- test6/7 S8 curved slab: 142mm fillet arc < 150mm chain tol glued at the WRONG end by
  greedy first-match (out-and-back pinch). Chaining now takes the globally-closest of all
  four attach modes over all unused pieces; duplicate shared edges deduped by 10mm-grid
  fingerprint. 9 rings, 0 non-simple on both tests.

## v0.39.0 — SLABS round 5: two live arc bugs found by mirroring the builder offline
- 0.37→0.38 audit: beams/cols identical on every test; slabs nearly unchanged → the 0.38
  arc fixes shipped two NEW bugs instead:
  (A) arcs attached to NEIGHBOUR rings via shared junction corners → straight panel edges
  bulged into arcs ("something wrong I can't point out"); ring must now TRAVERSE the arc.
  (B) rings traversing an arc BACKWARD skipped up to 97% of their boundary (0.45m loop on
  a 14.5m ring ×3 = the persistent test6/7 error). Circle-side run detection + walk-order
  keying + walk-oriented Arc. Offline: all rings on test1/2/3/6/7 close at ratio 1.000.
- Member-edge source now registers arcs too (real curved edges without a slab layer).
- Diagnostics: cad2bim_version stamped in export; raw_geometry at 0.1mm (Revit built 255
  loops where int-mm replay built 230); slab error/skip strings exported; pinch-vertex
  rings filtered (pass the crossing test, fail Revit).

## v0.38.0 — SLABS round 4: true curved edges + valid member-edge faces
- Slab arcs = 3-point circle fits; were 2 chords (S8 D-slab failed, curves = line strings).
  Now tessellated for geometry + true (start,mid,end) carried; builder emits genuine
  Arc.Create per curved stretch. test6/7 offline: 9/9 rings simple, D-slab whole.
- test4/5's 99 errors: faces threading round-column arc chords (columns in the Revit run,
  missing from the export). Member-edge graph tessellates arcs; simple-ring filter; builder
  skips instead of erroring. raw_geometry now dumps column records for full offline replay.
- Pending: "slab misaligned with beam outline in places" — diagnose from the 0.38.0 export.

## v0.37.0 — SLABS round 3: three outline sources + schedule/label fixes (Test0-7 set)
- Fixture reset: Test0 (messy) + Test1-7; column-only fixtures culled; stress DXF
  regenerated from its generator after the rename removed it.
- Slab-beam overlap (test4/5): beam-graph faces inset per edge by that beam's HALF WIDTH.
- Three sources: slab_edges -> member_edges (drawn beam+column outlines = exact panel
  boundary; body strips filtered) -> beam_graph_inset. test4/5 -> 243 face-true panels.
- test6: combined-layer schedule's slab table (Mark|H|Volume) parsed; S1..S9 size from it.
- test7: "S7_150 THK." underscore labels parse.
- test6/7 Floor.Create error: neighbour panel swallowed as HOLE via on-boundary
  point-in-polygon -> strict 50mm interior clearance + ring sanitation.

## v0.36.0 — SLABS round 2: Floor.Create fixed + UI pickers + openings (+ compact UI)
- Floor.Create failed everywhere: pythonnet does NOT convert a Python list to
  IList<CurveLoop>. Loops now packed into System.Collections.Generic.List[CurveLoop];
  floors flagged structural (best-effort).
- UI: chk_slabs is LIVE with a cb_floor_type picker (auto-disabled if the model has no
  floor type); slab creation gated on its own checkbox, uses the picked type.
- OPENINGS: a loop fully inside another becomes the enclosing floor's inner CurveLoop
  (stair/lift void), not a stacked slab (builders/slabs._nest_openings).
- UI COMPACTED (user request): window 780x600→640x560, tighter margins/rows (22px
  combos, 24px tolerance rows), helper captions small+gray, shorter layer scroll boxes.

## v0.35.0 — Test20 text-anchor fix + SLABS step 1 wired
- Test20 lost ALL label sizing/marks (+ B7/B8, the label-required beams): text alignment
  is GRID-anchored and Test20 has no grid layer → fell back to the link transform, which
  Revit reported as IDENTITY (scale baked into geometry) → labels 304.8x off. Alignment
  now anchors on ALL shared geometry when no grids ("geometry_anchored"); link transform
  only when both anchors empty. Stress DXF declares $INSUNITS=4 (mm).
- SLABS step 1: _create_slabs after beams — A-FLOR rings, else beam-perimeter-graph
  faces; thickness/mark from "S1 150 THK"/"150 THK." notes inside the loop; progress 8
  phases; "slabs" in console + JSON export.

## v0.32.0–0.34.0 — BEAM feedback rounds (all offline-verified via replay)
- 0.34.0: sloped 4° grid-I beams no longer flattened (skew non-rect outlines explode →
  angled edges pair); STRESS FIXTURE created (make_stress_plan.py → Test20, 8 zones + 14
  tests incl. polyline snakes).
- 0.33.0: snap slides ends ALONG the beam axis (no sideways drift to off-axis columns);
  each end snaps to its NEAREST column (B648 stub stretches across the full bay; fixed
  identically-markless Test14).
- 0.32.0: MTEXT rotation = text_direction VECTOR (not dxf.rotation) → orientation-gated
  label matching (labels run ALONG their beam; ±20°) fixed Test15's wrong/missing marks
  (682/682 perfect); too-wide outlines explode from ALL 3 branches (undrawn perimeter
  bays recovered); B22 continuation EXTENDS the placed beam (one piece, no phantom gap).

## v0.31.0 — BEAM bug batch part 2 (8b/8c/8d/8e ALL FIXED offline) + SLAB prototype
All four bugs were diagnosed and fixed OFFLINE from the user's 0.30.0 raw-geometry
exports (replayed via tests/replay_beams.py; every fix stash-diffed old-vs-new on
identical input — no guess-and-check Revit cycles):
- **8e** Test10 grid-6 H→I beam (grid 6 = x=20000, H→I = y 26300..27700): simplify_ring
  closes every polyline, deleting an open snake's last leg (collinear with the fabricated
  closing edge). Ring rejected when it drops a real vertex → polyline explodes → pairs.
- **8b** Test15 phantom beams midway between J/K + S/T: U-polyline chaining two grid
  beams' facing edges ring-closed into an 1800-wide "quad"; label rewrote width→300.
  Too-wide quads explode (real on-grid beams re-pair; rows E/F+Q/R repaired too,
  584→642 segments); a label can never rescue an out-of-range width.
- **8d** Test18 B20 600x900 placed unmarked 300x900: B23's label (between the stacked
  pair) beat B20's off-midspan label on midpoint distance. Marks now label-OWNS-segment
  by centreline distance (B4/B5 cure), midpoint fallback for unclaimed segments.
- **8c** B22 stops at B4/B5 instead of reaching C12: new label-free CONTINUATION pass —
  leftover beam+slab edge pairs (≥1 beam edge) that collinearly continue a placed
  same-width beam across ≤1200mm; depth inherited. Test18 both variants + Test19 now
  run B22's far piece to C12's face.
- **SLAB PROTOTYPE (held)**: slabs_proto.py + builders/slabs.py + 10 tests — see
  task_plan Phase 9. A-FLOR rings, or beam-perimeter-graph fallback (endpoint-healed
  planar faces). Test15 (no usable A-FLOR): 233 panels from 642 beams. Not wired.
- **NEXT:** user re-runs v0.31.0 in Revit on Test10/15/18/19 to confirm in-model.

## v0.30.0 — BEAM bug batch part 1 (8a) + raw-geometry diagnostic
- **8a SHORT-CURVE crash FIXED.** `snap_beam_ends_to_columns` pulls a beam end onto a column
  centre AFTER `length_mm` is stored, so a beam whose ends collapse onto one column kept a
  stale long length, passed the <50 mm filter, and `Line.CreateBound(start==end)` threw
  "Curve length too small" (2x Test15). `builders/beams.place_beams` now recomputes length
  from the LIVE endpoints and skips the collapsed sliver. Builder-only; 12/12 tests pass.
- **DIAGNOSTIC: `beams.raw_geometry` added to the JSON export** (`report._beam_geometry_dump`).
  Beam detection is a Revit-LINK-POLYLINE phenomenon: the DXF source draws beams as loose
  LINES, so the DXF harness places ZERO beams (Test10/15/18/19 all -> 0 segments) and cannot
  reproduce 8b-8e. The export now dumps the exact beam/slab-edge geometry (mm) the link reader
  returned. `tests/replay_beams.py <export.json> [mark]` rebuilds CurveRecords + re-runs the
  real `build_beam_segments` OFFLINE -> the remaining beam misses are diagnosable from ONE run.
- **NEXT:** user runs v0.30.0 on Test10/Test15/Test18 in text mode, shares the JSON; replay it
  to fix 8b (between-grid), 8c (B22->C12), 8d (B20 600x900), 8e (Test10 grid-6 H->I).

---


## NEXT SESSION SETUP — RUN THESE GIT COMMANDS FIRST, BEFORE ANYTHING ELSE
```
git fetch origin
git checkout claude/ecstatic-dijkstra-rmvyl7
git pull origin claude/ecstatic-dijkstra-rmvyl7
```
The branch `claude/ecstatic-dijkstra-rmvyl7` is the working branch and MUST be kept.
PR #4 was merged to `main` via merge commit, but continue ALL new work on this branch.

### To run the verification harness again (it is NOT committed — recreate it):
1. `pip install --target /tmp/pylibs ezdxf` (vendored win wheels don't work on Linux).
2. `/tmp/boot.py` contents:
```
import sys, types, os
sys.path.insert(0, "/tmp/pylibs")
ROOT = "/home/user/pyRevit-addons/AnonGee.extension/lib/py3"
sys.path.append(ROOT)
pkg = types.ModuleType("anongee_toolkit")
pkg.__path__ = [os.path.join(ROOT, "anongee_toolkit")]
sys.modules["anongee_toolkit"] = pkg
```
3. `/tmp/pipe.py` runs the full column pipeline per fixture: read_dxf → mm/304.8 to feet
   on records+texts → classify_layer → build_column_sections → route column_texts +
   schedule → recover_core_walls_from_labels → correct_columns_with_text (with grid_x/
   grid_y computed from S-GRID lines, grid_snap) → apply_circle_marks →
   recover_unplaced_labeled_columns; dumps (mark,cx_mm,cy_mm,w_mm,h_mm,long_axis_deg).
   (Full source is reconstructable from findings.md "pipeline call order" + Test19 facts.)
4. Regression method: run all 15 DXF fixtures, `git stash` report.py for the baseline,
   diff outputs. Goal = only intended fixture changes.

---

## Chronological log of THIS session

### Context at start
Prior session(s) had built cad2bim columns up to 0.23.3. This session opened with the
user wanting: "fix the core-wall now, label-guided; leave the markless unplaced." So the
work was Test19's fused lift core + (later) C16 + (later) the markless stub.

### Step 1 — Diagnose where core walls live
- Read `geom/shapes.py:660` `parse_column_polyline` (composite path).
- Found Test19 core is drawn as LOOSE LINE SEGMENTS on `S-COLS`, not closed polylines →
  assembled by `shapes.recover_rectilinear_columns` → entry status `recovered_strip`
  (NOT `composite` as first assumed).
- Confirmed the 5 mis-cut pieces (see findings.md). Root cause = greedy decompose steals
  corners.

### Step 2 — Built Revit-free harness
- Hit `ModuleNotFoundError: No module named 'System'` (package __init__ imports Revit).
- Hit Windows-numpy `os.add_dll_directory` AttributeError.
- Solved both via /tmp/pylibs (Linux ezdxf) + /tmp/boot.py namespace-package shim.
- Reproduced baseline Test19 output (15 columns; core walls mis-placed).

### Step 3 — Implemented `recover_core_walls_from_labels` (Phase 1)
- Added orchestrator + helpers to `report.py` (see findings.md function list).
- Greedy-by-longest carve on a cell grid; clean-full-tiling gate; marked-label filter.
- Wired into `script.py` before `correct_columns_with_text`.
- Initial gates: `len(comp) >= 3`, margin 600, MARKED labels only.
- RESULT: Test19 core C8(3000,6200) C9(3450,5000) C10(8000,5200) C12(6350,3000) all TRUE;
  C6 unchanged (already correct).
- First full diff showed Test9 + a Messy plan had markless 300x3300 walls flip
  long_axis_deg 0→90 (geometrically identical). To be safe, added the MARK-REQUIRED
  filter → those reverted; then ONLY Test19 changed.
- Removed unused `snap_tol_ft` param; made `schedule` meaningful via `_label_size`.
- Added `tests/test_core_wall_labels.py` (6 tests). Bumped 0.23.3 → 0.24.0.
- COMMIT `d5c02ea` "cad2bim 0.24.0: place fused core walls from their labels". Pushed.

### Step 4 — C16 investigation (Phase 2)
- User: "C16 and C17 not drawn." Investigated:
  - C17 IS drawn correctly at (8000,-300) — user's report was partly mistaken.
  - C16 genuinely missing. Root cause = C15+C16 fused 2-strip blob; text-correction
    `_is_split_pair` + `_merge_to_label` merge both into C15, consuming C16's geometry;
    `recover_unplaced_labeled_columns` returns 0 (no leftover) → C16 dropped.
  - The blob is only 2 pieces (blocked by `>=3` gate) and C16's label is ~935mm below
    the blob (blocked by margin 600).
- FIX: gate `>=3`→`>=2`; margin 600→1100.
- RESULT: C16 placed at TRUE (3150,-1050) 300x600; full 15-fixture diff shows ONLY
  Test19 changes (TOTAL per fixture identical except Test19 15→16).
- Added stacked-pair test + markless-lower-FALLBACK test (8 tests total).
- COMMIT `4eb7b2a` "cad2bim: recover a marked column swallowed by an abutting neighbour".
- Push rejected (remote advanced by fixture commit 52ba959); `git pull --rebase` then
  pushed `4eb7b2a`. Verified knobs survived rebase; tests pass.

### Step 5 — Markless stub (Phase 3)
- User confirmed: yes, draw the markless 300x600 IF no regression.
- Found: if markless sized labels join the carve, C17 blob tiles into C17 + markless.
- FIX: changed label pool to include markless sized labels; added PER-BLOB gate
  `if not any(lbl[0] for lbl in blob_labels): continue` (require >=1 marked label).
  Updated docstring + version note (the note's "left as-is" line was now outdated).
- RESULT: markless placed UNNAMED at TRUE (7850,-1050) 300x600; full diff shows ONLY
  Test19 (TOTAL 16→17). Tests9-18 + Messy byte-identical.
- Updated test (stacked-pair-both-placed) + added markless-only-core-no-op test (9 tests).
- COMMIT `25100af` "cad2bim: place a sized markless stub packed into a marked fused blob".
  `git pull --rebase` (up to date) then pushed.

### Step 6 — PR + merge (Phase 4)
- No existing PR for the branch. Base = `main`. Branch was 51 commits ahead.
- Created PR #4 "CAD to BIM: column detection & placement (cad2bim 0.24.0)".
- Subscribed to PR activity. Checked: 0 review comments, 0 reviews, 0 general comments,
  0 CI check runs (status "pending"/total_count 0 = no CI configured), mergeable_state
  "clean". Nothing to fix/flag.
- Merged via MERGE COMMIT (sha `9d52313`) so main contains all column commits as ancestors
  (chosen over squash so future beam PR won't re-surface column commits). Branch PRESERVED.
- Auto-unsubscribed on merge.

## Tests passed/failed
- `tests/test_core_wall_labels.py`: 9/9 PASS.
- All 8 cad2bim test files: PASS (test_circle_marks, test_core_detection,
  test_label_recovery, test_oriented_circle_recovery, test_rectilinear_recovery,
  test_schedule_parsing, test_text_correction_ownership, test_core_wall_labels).
- `tools/verify_toolkit.py`: 126 passed, 3 FAILED — the 3 are PRE-EXISTING import-path
  failures, confirmed identical on baseline (NOT caused by our work). Do not chase them
  unless asked.
- Full 15-fixture geometry diff: byte-identical on Tests 9-18 + 3 Messy plans; only
  Test19 changed (the intended fixes).

## EXACT STATE WHERE WE STOPPED
- COLUMNS: COMPLETE. PR #4 MERGED to main (merge commit 9d52313). Branch
  `claude/ecstatic-dijkstra-rmvyl7` preserved and pushed (head = 25100af before the merge;
  after pulling, head will reflect main's merge state via the branch).
- Working tree: clean (all column work committed + pushed). Planning files (this set) are
  new and uncommitted — commit them if desired.
- Final Test19 result: 16 rect columns (C1,C2,C3,C4,C5,C6,C8,C9,C10,C11,C12,C14,C15,C16,
  C17,C18) + 2 circles (C7,C13) + 1 markless 300x600 @(7850,-1050) = every column lands.

## BEAM session (continuation, same session as columns)
Investigated the beam pipeline + Test19 beams. Findings appended to findings.md "BEAMS".
- Built beam harnesses in /tmp: `beams2.py` (faithful pipeline), `beamarc.py` (arc→circle
  clustering), `beammap.py` (label→nearest-line). All use /tmp/boot.py + /tmp/pylibs.
- KEY RESULT: Test19 places only **1 of 23 beams** (B23). status_counts (circles passed):
  `{line_pair:1, bare_line_unpaired:13, arc_junction:36, curved_pair:1, arc_lone:38}`.
- Test19 S-BEAM geometry = 15 lines + 76 arcs, 0 closed outlines.
  - 36 arcs = junction fillets around round cols C7/C13 (correctly ignored).
  - 39 arcs = a real CURVED beam (center 11000,5500 r2300) = B18/B19, detected but NOT placed.
  - 15 lines = mostly perimeter single edge-lines (B11–B17,B20–B23) + a couple interior.
- TWO root-cause gaps identified (see findings.md): (1) beam text NEVER routed in script.py
  (`build_beam_segments(..., texts=None)`) so no depth/mark; (2) single-line / perimeter
  beams not detected (only closed-outline + parallel-pair + curved-arc-pair are handled).
- Updated task_plan.md Phase 5 with sub-phases 5a–5d.
- NO beam CODE changed yet. Working tree only has the 3 updated .md files (uncommitted).

## 5a DONE (beam text routing) — committed this session
User answered: first target = "Wire beam labels first"; convention = "Not sure / mixed"
(I will infer the convention per-line from geometry + label position, verify vs harness).
- `script.py`: moved `build_beam_segments` call BELOW the text-routing block; added
  `beam_texts = [t for t in dxf_result.texts if text_mapping.get(t.layer_key) ==
  layers.CATEGORY_BEAM_TEXT]`; pass `texts=beam_texts`; print "beams: sized N segment(s)".
  (Reorder is safe — build_beam_segments has no forward dep on the moved-past code.)
- Added `tests/test_beam_text_sizing.py` (3 tests, pass): depth+mark applied; no-label →
  no depth; far-label (> mark_radius 1300mm) not applied.
- Verified end-to-end via /tmp/beams2.py: B23 now 300x900 + mark (was family default).
- All 9 test files pass. `script.py` py_compile OK. (script.py can't be import-run on Linux.)
- `classify_text_layer("S-BEAM-IDEN")` -> CATEGORY_BEAM_TEXT (default mapping auto-detects).

## 5c DONE (curved beam placement, B18) — committed this session
User picked curved beams next (before 5b). Implemented end-to-end:
- report.py: arc collection now stores endpoint angles+z. New helpers `_group_arc_edges`
  (cluster fragments by centre+radius; consts `_ARC_EDGE_CENTER_TOL_MM=250`,
  `_ARC_EDGE_RADIUS_TOL_MM=60`), `_curved_beams_from_edges` (pair inner/outer edges, gap in
  beam width band), `_arc_span` (swept angle via largest circular gap), `_curved_segment`,
  `_apply_curved_marks` (depth+mark from nearest label to mid-arc; width stays geometric).
  `build_beam_segments` now returns `curved_segments`; `format_beam_segments` shows them.
- builders/beams.py: `place_curved_beams` places each along `Arc.Create(center, radius,
  start, start+sweep, BasisX, BasisY)`. script.py `_create_beams` calls it + folds tallies.
- VERIFIED: Test19 B18 center(11000,5500) R2500 width400 depth900 span279->443 len7160.
  Straight-beam counts BYTE-IDENTICAL across all 15 fixtures (regression diff: only curved
  added). 3 Messy plans also gain curved beams; arc_lone -> ~0. 10 test files pass;
  verify_toolkit 128 passed/3 pre-existing fails. Added tests/test_curved_beams.py (4).
- NOTE: place_curved_beams is Revit API (Arc) -- syntax-checked (py_compile) but NOT
  runtime-verified (no Revit on Linux). Watch the Arc.Create angle convention if issues.

## THE VERY NEXT ACTION = 5b: single-line / perimeter beam detection
Goal: turn the 13 `bare_line_unpaired` single lines into placed beams. Convention is
"mixed" so INFER per line: is the line an EDGE (beam body offset inward by its label width)
or a CENTRELINE (width straddles it)? Use the line's label (nearest beam_text gives width)
and the line's position relative to the plan interior / nearby columns to decide offset
direction. Implement in `build_beam_segments` (a new source branch for unpaired bare lines)
or a follow-on pass. THEN verify with /tmp/beams2.py that Test19 placed count rises toward
~22 straight beams, and regression-check other fixtures. Curved beam (5c, B18/B19) and
implied beams (5d) come after.
Recreate harness first if /tmp is gone (see top of this file): /tmp/boot.py, /tmp/pylibs,
and rebuild /tmp/beams2.py per findings.md "Harness for beams".

## 5b DONE (perimeter / floor-clipped beam recovery) + v0.26.0 — committed this session
User's domain insight: Revit clips a perimeter beam's inner edge against the A-FLOR floor
outline, so only ONE beam edge survives on S-BEAM; the floor edge is the other edge. Verified
ALL 23 Test19 beam labels match a parallel pair (gap == label width exactly) from the combined
S-BEAM + A-FLOR pool (BF perimeter, FF interior, BB = B23).
- layers.py: `flor|floor` -> CATEGORY_SLAB_EDGE (was an unused placeholder category; the old
  comment deliberately excluded floor -- replaced).
- report.py: build_beam_segments collects floor_lines (CATEGORY_SLAB_EDGE). New pass (4)
  `_edge_pair_beams(leftover_beam, floor, texts, placed_marks, existing, ...)`: pair the
  combined pool via shapes.pair_parallel_lines, keep a candidate ONLY where an unplaced beam
  label of matching width (snap_tol) is within mark_radius of the centreline
  (`_point_to_segment_dist`). Spatial dedup `_coincides_with_a_beam` (parallel + midpoint
  within `_EDGE_DUP_TOL_MM`=250 of a placed beam) drops floor re-traces of existing beams.
  Each label + each candidate used once. status key `edge_pair`.
- CRITICAL BUG caught + fixed during dev: without spatial dedup, Test9/10/11 (floor outline
  traces the beams) DOUBLED 52 beams (edge_pair on top of line_pair). Dedup -> those plans
  now add 0 edge beams (correct). Final regression: existing line_pair/curved BYTE-IDENTICAL
  on ALL fixtures; only Test19 (+19 -> 21/23) and Raheja (+4) gain beams. No geometric dups.
- 11 test files pass (added test_perimeter_beams.py, 5). verify_toolkit 129 passed/3 pre-existing.
- KNOWN remaining (Test19): B20 unplaced (its y=-600 edge consumed by B23's line_pair, which
  the user validated as correct) and B22 unplaced (900x900: width 900 > beam_width_max 600 AND
  > pair_max 700). Both are edge cases, noted for user.

## THE VERY NEXT ACTION = optional 5d (B20/B22) OR confirm beams done
- B22: raise `beam_width_max_mm` (600 -> ~1000) AND `pair_max_width_mm` (700 -> ~1000) in
  config.py to admit 900-wide beams; re-run beam regression (risk: wider false pairs).
- B20: would need label-width-aware pairing in pass (2) so beam-beam greedy pairing doesn't
  steal an edge a floor pairing needs; low priority / ambiguous.
- If user is happy at 21/23, beams are effectively done -> consider a PR or continue.
Harness (recreate if /tmp gone): /tmp/boot.py + /tmp/pylibs; /tmp/beamall.py (per-fixture
status line), /tmp/beam5b.py (Test19 placed beams + missing), /tmp/dup.py (over-gen check).

## 5e DONE (Revit-run beam fixes from JSON) + v0.27.0 — committed this session
User ran 0.26.0 in Revit on Test18 redrawn/fragmented + Test19, pushed JSON exports
(.json/beam_test*_0.26.0_with_textmode.json). Found via the JSON (totals.by_category +
beams.status_counts):
- Revit `column`=57 but DXF reader sees 138 S-COLS -> the LINK READER returns geometry as
  POLYLINES (geometry_reader.py:82 emits kind="polyline"). slab_edge=17 polylines (~55
  segments). My floor_lines only took kind=="line" -> floor pool empty -> edge_pair=1, only
  3 beams placed. FIX A: explode slab_edge line+polyline into segments.
- Test18 beam labels are mark-only (b/h None); size is in the schedule (G-ANNO-SCHD). beam
  sizing used inline-only sized_texts -> unsized. FIX B: pass `schedule` to build_beam_segments;
  resolve via `_label_size`. SUB-BUG: beam schedule is Mark|W|H|L (H=depth, L=span) but
  parse_schedule read (W,L) [role "l"=l/d/depth/length], giving depth=span(2960). Fixed
  `_read_table` to read a BEAM mark's row as W x H (`_is_beam_mark`); columns stay W x L.
- place_beams/place_curved_beams never set Mark. FIX C: `_set_mark` in beams.py (BuiltInParameter
  .ALL_MODEL_MARK), called in both placers. Surfaced duplicate marks (B23 x2 in both Test18)
  -> `_dedupe_marks` keeps mark on the segment nearest the label, clears others.
- VERIFIED (DXF harness): Test19 21 beams all sized+marked (edge_pair 19 via DXF lines);
  Test18 22 beams all sized from schedule W x H + marked, no duplicate marks. Columns
  BYTE-IDENTICAL (shared parse_schedule change only affects B-marks). 11 test files pass;
  verify_toolkit 129/3 pre-existing. Added schedule W x H tests + polyline/schedule/dedup
  beam tests.
- CAVEAT: A (polyline explode) and C (set mark) run on the Revit link path / Revit API -
  verified by logic + DXF-line harness, NOT runtime in Revit. User should re-run 0.27.0 in
  Revit to confirm Test19 places ~21 beams with correct marks/depths.
- HELD per user: B20, B22.

## Phase 6 partial (v0.28.0) — committed this session
0.27.0 Revit JSON analysis -> 3 fixes done (6a,6b,6c); 6d/6e/6f pending.
- 6a snap_beam_ends_to_columns(beam_segments, sections, circles): beam END within
  round-radius / rotated-rect half-diagonal + 250mm pad -> moved to column centre. Wired in
  script.py after recover_unplaced. Test19: 14 ends snapped (2 round, 4 rotated). Midspan
  never moves; axis-aligned cols skipped. test_beam_snap.py (4).
- 6b _edge_pair_beams now OWNERSHIP: each candidate owned by NEAREST matching-width label;
  each label takes its nearest owned candidate. Fixes B4/B5 swap (Revit). DXF harness +
  all edge counts BYTE-IDENTICAL. test_perimeter_beams ownership test added.
- 6c beam_width_max_mm 600->1000 (config); edge pass pairs up to beam_width_max (label-
  confirmed, safe) while line_pair stays pair_max 700. B22 (900x900) now placed in Test19 +
  Test18; line_pair counts unchanged; only width_oor->kept deltas. Columns byte-identical.
- 12 test files pass. verify_toolkit 130/3 pre-existing (expected).
- PENDING: 6d real B4 near core (likely 6b helps; Revit-verify), 6e Test18 B20 -> 300x900
  unmarked (Revit-polyline specific, can't repro in DXF harness), 6f Test15 full sweep
  (255 degenerate, 133 unpaired, slab_edge 0 -> floors absent/unmapped there).
- CAVEAT: 6a snap + 6b swap are Revit-link-geometry effects; verified by logic + DXF harness
  + unit tests, NOT runtime in Revit. Re-run 0.28.0 in Revit to confirm.

## 6f (v0.28.1) — beam open-polyline edges; Test15 root cause
Test15 Revit: 315 placed but 255 DEGENERATE. Root: link reader gives a beam's surviving edge
as a short OPEN polyline; build_beam_segments dropped ring<4 as degenerate. FIX: explode such
polylines into bare_lines (the pairing pool). Regression: ONLY Mahalaxmi changed (placed 0->49;
its beams are polylines too); all other fixtures byte-identical. 12 test files pass. Added
open-beam-polyline test. This is the main Test15/Revit-polyline lever (can't run Revit; verify
on re-run). DXF Test15 already placed 682 (its beams are lines), so DXF count unchanged there.
PENDING still: 6d/6e (Revit-link-specific B4-near-core / B20-600->300; 6b+6c+6f may resolve --
needs Revit re-run to confirm).

## ERROR LOG — 0.29.0 features "not working" (reported 2x)
| Attempt | Action | Result |
|---|---|---|
| 1 | Implemented A (disallow join) + B (deferred console+bar), committed 0.29.0, verified buffer/bar standalone, 12 tests pass | User: console still opens pre-Run, no bar, no disallow |
| 2 | Diagnosed STALE build (HEAD==origin, no real print outside buffer); told user pull + RELOAD pyRevit (beams.py is cached imported module) | User: SAME symptom |
| 3 | RETHINK: verified script.py:287 already sets window `version_text` = cad2bim.__version__ (xaml default "v0.13" is overridden). So the MAIN WINDOW already DISPLAYS the loaded version -> decisive stale-vs-fresh check. Likely root cause: Revit runs the extension from a DIFFERENT path than the git clone the user pulls (pyRevit extensions often live in %APPDATA%/pyRevit, not the repo). ACTION: ask user what version the window shows. |

Key facts: all 3 features (disallow + deferred console + bar) absent together == none of 0.29.0 active == stale code, NOT a partial bug. script.py is re-read each click (no reload needed) yet console-defer absent -> the RUNNING script.py is not the committed one -> wrong/shadow copy path.

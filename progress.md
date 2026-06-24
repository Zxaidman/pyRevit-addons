# Progress Log — cad2bim Column Session

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

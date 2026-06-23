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

## THE VERY NEXT ACTION
**Awaiting a user scope decision** (asked at end of beam investigation): confirm the beam
drawing convention (perimeter beams = single EDGE lines extending inward by width? vs
centrelines), expected #beams to place, and which sub-phase to do first.
Recommended sequence once confirmed:
1. **5a** wire beam-text routing in `script.py` (route `CATEGORY_BEAM_TEXT` → pass to
   `build_beam_segments`; mirrors `column_texts`). Low risk, but verify against the
   beam harness (only helps detected beams).
2. **5b** single-line/perimeter beam detection (the 13 `bare_line_unpaired`).
3. **5c** curved-beam placement (B18/B19).
4. **5d** implied/far-label beams.
Each step: implement → run /tmp/beams2.py (recreate harness first if /tmp is gone) →
verify no regression on other fixtures → commit → push → update these 3 .md files.
NOTE: the column label-guided carve is likely NOT reusable for beams (beams are lines+arcs,
not fused closed outlines).

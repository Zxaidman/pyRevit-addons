# Task Plan — CAD to BIM (cad2bim) Column & Beam Work

## Main Goal
Build out the `cad2bim` toolkit inside the pyRevit extension so a structural CAD plan
(DXF / linked CAD) is read, every structural member is recovered/sized/named from its
label or schedule, and placed in Revit. **Columns are the focus that is now COMPLETE.
Beams are the NEXT major area of work** (to continue on the same branch).

- Repo: `Zxaidman/pyRevit-addons`
- Working branch (KEEP — do not delete): `claude/ecstatic-dijkstra-rmvyl7`
- Default/base branch: `main`
- cad2bim version after this session: **0.24.0**

## Key Architectural Decisions
1. **Label-guided re-tiling of fused outlines** (the core innovation of this session).
   When abutting members share one drawn outline (a lift/stair core drawn as loose wall
   lines, OR one column cast hard against another), the existing greedy decomposition
   mis-cuts the shared corners/edges. Instead of fixing the geometry-only decomposition
   (ambiguous, can't be solved without labels), we re-tile each fused blob FROM ITS
   LABELS, BEFORE text-correction runs.
2. **New pass = `report.recover_core_walls_from_labels(sections, column_texts, schedule)`**,
   called in `script.py` right before `correct_columns_with_text`.
3. **Algorithm = greedy-by-longest carve on a cell grid.** The blob's exact-cover pieces
   define a cell grid (unique x/y edges). Members are carved LONGEST-dimension first;
   each label claims the label-sized run of still-unclaimed inside-cells nearest its
   label point. Proven to reconstruct the true cover.
4. **Safety gates (critical for zero regression):**
   - Only blobs of `status in ("composite","recovered_strip")` are candidates.
   - Connected component must have `>= 2` pieces.
   - The blob must contain `>= 1` MARKED label (so a working markless-only core is never
     touched).
   - The carve must achieve a CLEAN FULL TILING (every inside cell claimed) or the blob
     is left exactly as decomposed (fallback = current behavior).
   - Once firing, it uses ALL sized labels (marked AND markless-but-sized), so a sized
     stub packed into a marked blob is placed (unnamed).
5. **Do NOT grid-snap carved walls** — they sit at true drawn positions; snapping would
   move them off. The "just name it" path in `correct_columns_with_text` keeps them.
6. **width/height convention** of carved rects matches the column builder:
   `width_mm` = x-extent, `height_mm` = y-extent, `long_axis_deg = 90 if height>=width
   else 0`. Builder (`builders/columns.py:112-115`) auto-derives the same when absent, so
   placement is provably identical.

## Phases

### Phase 1 — Fused CORE walls (Test19 lift core) — ✅ DONE (committed d5c02ea)
- [x] Diagnose: core drawn as loose lines on `S-COLS`, assembled by
      `recover_rectilinear_columns` into a `recovered_strip` entry of 5 mis-cut strips.
- [x] Implement `recover_core_walls_from_labels` + helpers in `report.py`.
- [x] Wire into `script.py` before `correct_columns_with_text`.
- [x] Verify: C8/C9/C10/C12 move to TRUE centres; C6 already correct.
- [x] Zero regression on Tests 9–18 + 3 Messy plans (byte-identical).
- [x] Regression test `tests/test_core_wall_labels.py`.
- [x] Version bump 0.23.3 → 0.24.0.

### Phase 2 — C16 swallowed by C15 (stacked adjacent columns) — ✅ DONE (committed 4eb7b2a)
- [x] Diagnose: same fused-outline bug between 2 stacked columns; C15+C16 fuse into 2
      strips; text-correction merges both into C15, consuming C16's geometry → C16 dropped.
- [x] Relax gate `len(comp) < 3` → `len(comp) < 2`.
- [x] Widen `_CORE_LABEL_MARGIN_MM` 600 → 1100 (C16's label sits ~935mm below its column).
- [x] Verify C16 placed at true (3150,-1050); zero regression elsewhere.
- [x] Add stacked-pair + markless-lower-fallback tests.

### Phase 3 — Draw the markless 300×600 under C17 — ✅ DONE (committed 25100af)
- [x] Diagnose: markless-but-sized stub fused under C17; carve skipped markless labels.
- [x] Allow markless sized labels into the carve, BUT only inside a blob holding >=1
      marked label (per-blob `any(lbl[0] for lbl in blob_labels)` gate).
- [x] Verify markless placed at true (7850,-1050) UNNAMED; zero regression elsewhere.
- [x] Update tests: stacked-pair-both-placed + markless-only-core no-op.

### Phase 4 — PR + merge — ✅ DONE
- [x] PR #4 created (`claude/ecstatic-dijkstra-rmvyl7` → `main`).
- [x] No review comments, no CI configured, mergeable_state clean.
- [x] Merged via MERGE COMMIT (sha 9d52313) so main has all 50 column commits as
      ancestors → branch stays cleanly ahead for beams. Branch PRESERVED.

### Phase 5 — BEAMS — ⏳ NOT STARTED (next session)
- [ ] Assess current beam pipeline (`build_beam_segments` in `report.py`,
      `builders/beams.py`, beam text layer `S-BEAM-IDEN`).
- [ ] Identify beam fixtures/failures analogous to the column work.
- [ ] Plan + implement beam detection/placement improvements on the SAME branch.
- (No specific beam tasks were defined yet this session — this is greenfield.)

## Status: COLUMNS COMPLETE. Every column on Test19 (18 marked + 1 markless) now lands.
Next focus is BEAMS.

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

### Phase 5 — BEAMS — ⏳ IN PROGRESS (investigation done; implementation NOT started)

**Current state (Test19): only 1 of 23 beams (B23) is placed.** Beam detection is the
big gap. Investigation found a MIXED drawing convention (see findings.md "BEAMS").

Sub-phases (priority order TBD with user):
- [x] **5a. Wire beam-text routing** — DONE. `script.py` now routes `beam_texts =
      [...CATEGORY_BEAM_TEXT]` and passes them to `build_beam_segments(texts=beam_texts)`
      (moved the beam call below the text-routing block). Each detected segment gets
      width=min(label), depth=max(label), mark via `_apply_beam_marks` (midpoint→nearest
      sized label within mark_radius). Verified: Test19 B23 now sized 300x900 + mark
      (was family-default depth). Added `tests/test_beam_text_sizing.py` (3 tests).
      NOTE: only helps DETECTED beams — Test19 still 1/23 until 5b lands.
- [x] **5b. Perimeter / floor-clipped beam detection** — DONE (the user's A-FLOR insight).
      Revit clips a perimeter beam's inner edge against the floor (A-FLOR) outline, so only
      ONE beam edge survives on S-BEAM; the other edge IS the floor edge. Fix: classify
      `flor|floor` -> CATEGORY_SLAB_EDGE (was unmapped placeholder); `build_beam_segments`
      collects floor_lines; new `_edge_pair_beams` pass pairs leftover beam lines + slab
      edges into width-band candidates and keeps one ONLY where an unplaced beam label of
      matching width sits across it (`_point_to_segment_dist` < mark_radius). Spatial dedup
      (`_coincides_with_a_beam`, tol `_EDGE_DUP_TOL_MM=250`) drops an edge pair that
      re-traces an already-placed beam (fixes Test9/10/11 where the floor outline duplicates
      beams). Verified: existing line_pair/curved BYTE-IDENTICAL on all fixtures; Test19 1->21
      of 23; Raheja +4. Added tests/test_perimeter_beams.py (5). KNOWN gaps: B20 (its -600
      edge is consumed by B23's line_pair, validated correct) and B22 (900 wide > 600 limit).
- [x] **5c. Curved beam placement** (B18) — DONE. Was detected (`curved_pair`) but discarded
      ("placement to follow"). Now: arc fragments are clustered into concentric EDGES
      (`_group_arc_edges`), inner/outer edge pairs become curved beam segments
      (`_curved_beams_from_edges`) with centreline radius, width=gap, swept angle via
      `_arc_span` (largest-gap), depth+mark from nearest label (`_apply_curved_marks`).
      `build_beam_segments` now returns a `curved_segments` list. Builder
      `beams.place_curved_beams` places each along an `Arc` (wired into script.py
      `_create_beams`). Verified: Test19 B18 = center(11000,5500) R2500 width400 depth900
      span 279->443 deg; straight-beam counts byte-identical on ALL fixtures; 3 Messy plans
      also gain curved beams; arc_lone drops to ~0. Added `tests/test_curved_beams.py` (4).
- [ ] **5d. Implied/spanning beams + far labels**. Several labels (B3,B5,B7,B8,B9,B10,B22,
      B18,B19) sit 1200–2800 mm from any beam line — geometry may be implied (span between
      columns) or drawn in a way not yet matched. Needs ground-truth clarification.

**DECISION NEEDED FROM USER**: the expected beam output / drawing convention is ambiguous
(unlike columns where the user gave ground truth per step). Confirm: are perimeter beams
single EDGE lines (extend inward by width) or centrelines? How many beams should place?
Which sub-phase first? (Recommended start: 5a infra, then 5b detection.)

- [x] **5e. Revit-run beam fixes (v0.27.0)** from the user's 0.26.0 JSON exports (3 issues):
      (A) Revit link reader returns floor outlines as POLYLINES not lines -> floor pool empty,
      only ~1 beam placed; now slab_edge polylines are exploded into segments. (B) mark-only
      beam labels never sized -> build_beam_segments now takes `schedule`, sizes via
      `_label_size`; beam schedule is Mark|W|H|L (H=depth, L=span) so `parse_schedule` reads a
      BEAM row as W x H (columns stay W x L). (C) placed beams had no Mark -> both placers now
      `_set_mark`; duplicate marks de-named to nearest (`_dedupe_marks`). Columns byte-identical;
      added tests (schedule W x H, polyline floor, schedule sizing, dedup). NOTE: A/C are Revit
      API / link-geometry paths -- verified by logic + DXF harness, not runtime in Revit.



### Phase 7 — Pushbutton features (v0.29.0) + XAML hotfix — DONE (verified in Revit; bar kept simple, WPF circular later)
- [x] ui.xaml hotfix: missing space `IsChecked="True"Margin=` broke XamlReader.Load (window
      failed to open after Link). One-char fix, committed separately.
- [x] FEATURE A disallow beam end-joins: builders/beams.py `_disallow_joins(instance)` calls
      StructuralFramingUtils.DisallowJoinAtEnd(inst,0/1), best-effort; called in both placers.
- [x] FEATURE B deferred console + [####------] progress: script.py `_DeferredOut`/`_say`
      buffer (all print()->_say), `_OUT.flush()` only AFTER main-window Run, `_progress(i,7,..)`
      per phase (link, read, columns, beams, create x3). No pyrevit import. Buffer/bar verified
      standalone; 12 test files pass. NOTE: Revit-API/UI paths -- verify on re-run.
- Brainstorming spec: docs/superpowers/specs/2026-06-26-beam-join-and-deferred-console-design.md
- NEXT (deferred bug batch): B22->C12, B20 300x900, Test10 grid-6, Test15 between-grid +
  short-curve (zero-len) errors.


### Phase 8 — BEAM BUG BATCH (from 0.28.1 Revit run) — IN PROGRESS (v0.30.0)
- [x] 8a SHORT-CURVE errors (Test15, 2x "Curve length too small"). Cause: snap_beam_ends_to_columns
      moves a beam END but does NOT recompute length_mm; a beam whose ends collapse onto one
      column passes the <50mm filter (stale length) then Line.CreateBound(start==end) throws.
      FIXED v0.30.0: place_beams recomputes length from the LIVE start/end (post-snap) and skips
      the collapsed sliver. Builder-only change; 12/12 unit tests pass.

  **DIAGNOSTIC (v0.30.0): beams.raw_geometry added to the JSON export.** The DXF source
  carries beams as loose LINES, not the polylines Revit's link reader builds, so the DXF
  harness places ZERO beams (verified: Test10/15/18/19 all -> 0 segments, every beam is
  bare_line_unpaired) and CANNOT reproduce 8b-8e. The export now dumps the exact beam- and
  slab-edge-layer geometry (mm) the link reader returned. `tests/replay_beams.py` rebuilds
  CurveRecords from it and re-runs the real build_beam_segments OFFLINE -> 8b-8e diagnosable
  from ONE export, no guess-and-check Revit runs.
  >> NEXT RUN: user runs v0.30.0 on Test10/Test15/Test18 (text mode), shares JSON; then
     `python3 tests/replay_beams.py <export.json> [mark]` reproduces each miss locally.

  Symptom notes gathered from the 0.28.1 OUTPUT exports (pre-geometry-dump):
  - 8e Test10: grid X-lines [-300,3000,8000,11000,14000,17000,20000,25000,28300]=grids 1..9
    (grid 6 = x=17000). x=17000 verticals cover y up to 22850 then resume at 26450 -- the
    y~=23000->24500 (H->I) bay segment is the miss; some neighbour lines share that gap.
- [x] 8b FIXED v0.31.0. Cause: U-polyline chains two grid beams' facing edges; simplify_ring
      closed it into an 1800-wide "quad" on the midline; nearest label rewrote width->300
      (laundering past the width filter + stealing the mark). Fix: too-wide quads explode into
      the pair pool (real on-grid beams re-pair); label can't rescue out-of-range width.
      Offline replay: 14 phantoms (y=30650 J/K, y=60675 S/T) gone; rows E/F+Q/R repaired too.
- [x] 8c FIXED v0.31.0. B22's far piece has no label (label sits over near piece) + its inner
      edge survives only as floor outline. New label-free CONTINUATION pass: leftover beam+slab
      edge pairs (>=1 beam edge) that collinearly continue a placed same-width beam across a
      crossing member (<=1200mm gap); depth inherited. Verified: Test18 both variants
      (2765..4465,676) + Test19 (3150..4850,3000) reach C12's face; nothing else changes.
- [x] 8d FIXED v0.31.0. B23's label (drawn between stacked B20/B23) out-scored B20's own
      off-midspan label by MIDPOINT distance. Marks now label-OWNS-segment by centreline
      distance (edge-pair B4/B5 cure), midpoint fallback for unclaimed. B20=600x900 both
      Test18s, all B1-B23 marks correct; Test15 marks redistribute only where provably wrong
      (B101 sits 6mm ON the horizontal it now names).
- [x] 8e FIXED v0.31.0 (was: grid 6 = x=20000, H->I = y 26300..27700). simplify_ring wraps the
      vertex list, so the open snake's last leg (vertical beam edge, collinear with the
      fabricated closing edge) was deleted. Ring rejected when it loses a real vertex ->
      polyline explodes -> beam pairs. Only Test10 changes; +grid-6 beam.

  ALL FIXES VERIFIED OFFLINE against the five 0.30.0 raw-geometry exports via
  tests/replay_beams.py + stash-diff (old vs new on identical input).
  >> NEXT: user re-runs v0.31.0 in Revit on Test10/15/18/19 to confirm in-model.

### Phase 6 — BEAM refinements from 0.27.0 Revit run — IN PROGRESS
Source: user 0.27.0 JSON exports + report (Test19, Test18 redrawn/fragmented, Test15).
- [x] **6a. FEATURE: beam end -> rotated/round column CENTRE.** When a beam END junctions a
      ROTATED column (oriented_rect) or ROUND column, beam end leaves a gap. Snap/extend the
      beam endpoint to the column centre. Needs column centres + rotated/round flags into beam
      step. Plan: new report pass `snap_beam_ends_to_columns(beam_segments, sections, circles)`
      called in script.py after build_beam_segments (both available there).
- [x] **6b. BUG: B4/B5 mark swap (ownership).** `_edge_pair_beams` labels claim nearest
      candidate first-come; two same-width labels (B4,B5 300x600) -> B4 grabs B5's nearer
      beam. Fix: candidate owned by NEAREST label (compute owner map), each label takes only
      owned candidates. Real B4 (near core) then places; B5 keeps its own.
- [x] **6c. BUG: B22 (900x900) missing.** width 900 > beam_width_max 600 & pair_max 700.
      Raise limits to admit ~900-wide beams; re-check regression (wider false pairs risk).
- [ ] **6d. BUG: real B4 near core unplaced** (likely resolved by 6b; verify).
- [ ] **6e. BUG: Test18 B20 -> 300x900 unmarked** instead of 600x900 B20. Investigate
      (600 edge pair lost to a 300 line_pair; dedup cleared mark).
- [x] **6f. Test15 FULL analysis** (315 placed, 255 degenerate, 133 unpaired, 23 width_oor,
      slab_edge 0). Sweep all beam cases; find systemic misses.

## Status: COLUMNS COMPLETE (PR #4 merged). BEAMS: 5a+5c+5b+5e DONE (v0.27.0).
Order done: 5a (text), 5c (curved), 5b (perimeter/floor-clipped). Test19 = 21/23 beams.
NEXT (optional): 5d the 2 stragglers -- B22 (raise beam_width_max 600 -> ~1000 AND
pair_max 700 to allow 900-wide beams; check regression) and B20 (shares its -600 edge with
B23; needs a smarter pairing that respects label widths -- low priority). Otherwise beams
are effectively done; confirm scope with user.

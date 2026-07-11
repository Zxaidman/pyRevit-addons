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

### Phase 8+ — 0.31.0 Revit feedback round (v0.32.0) — DONE, AWAITING REVIT CONFIRM
User's 0.31.0 run: Test10 PERFECT; Test15 rows fixed but marks wrong/missing + some beams
undrawn (user screenshots = exactly the missing set); Test18/19 B20 fixed, B22 = two pieces
with phantom 300 gap.
- [x] MARKS: beam labels are MTEXT whose rotation is the text_direction VECTOR ((0,1,0) =
      vertical), not dxf.rotation -- all 682 labels read rot=0, so rotated (vertical) labels
      (anchor at one END of the text run, often ~60-210mm from the crossing row's centreline)
      claimed horizontal beams row after row. Reader now captures rotation; ownership/fallback/
      edge-pair label matching is orientation-gated (+-20 deg, labels run ALONG their beam);
      dedupe keeps by centreline distance. texts_sized exports "rot".
- [x] UNDRAWN BEAMS: whole bays traced as nearly-closed 5-pt snakes -> skew closing edge ->
      non_rectilinear bbox 2950 wide -> width-filtered, real edges CONSUMED. Too-wide outlines
      now explode from ALL 3 branches (quad/composite/non-rect). Test15 offline: 682 labels ->
      682 segments, 100% marked correct, 0 undrawn, 0 mismatch.
- [x] B22 ONE PIECE: continuation now EXTENDS the placed beam across the crossing (was: second
      piece + gap). Test18 x2 + Test19 verified single span to C12's face.
- [x] Regression: Test10/18 byte-identical; 13/13 unit tests.
>> 0.32.0 Revit run: Test10/18/19 CLEAN. Two new items -> fixed in v0.33.0:

### Phase 8++ — 0.32.0 feedback (v0.33.0) — DONE, AWAITING REVIT CONFIRM
- [x] SNAP DRIFT (Test11, verticals H->I): snap moved the end ONTO the column centre; grid-I
      columns are deliberately OFF the beam axis -> beam skewed off its CAD outline. End now
      slides ALONG THE BEAM'S AXIS to the station abeam of the centre (projection). Replay:
      22 snaps, all axial, 0 lateral drift. New unit test (off-axis column).
- [x] B648 UNDRAWN (Test15 + same beam markless in Test14): bay between C315/C319 (750x1200
      rotated) leaves a 301mm edge-overlap stub; BOTH ends inside BOTH columns' reach and
      first-match sent both to the SAME centre -> zero length -> skipped. Ends now snap to
      the NEAREST column each -> stub stretches to the full bay (B648 = 1500, S->O). Zero
      collapsed segments post-snap; detection byte-identical everywhere; 13/13 tests.
>> 0.33.0 run: ALL tests good except one regression -> fixed in v0.34.0:

### Phase 8+++ — 0.33.0 feedback + STRESS SUITE (v0.34.0) — DONE
- [x] SLOPED BEAMS FLATTENED (Test11 grid-I 6->7, 7->8): the 4-deg bays arrive as ONE
      non-rectilinear snake (two angled edges + diamond-face jogs); the bbox fallback
      flattened them horizontal. 0.32.0 only looked right because teleport-snap dragged ends
      to the centres. FIX: non-rect ring with longest edge >2 deg off-axis explodes
      (skew_outline_explode); angled edges pair -> sloped beam; axial snap runs it
      centre-to-centre. Replay: both bays 4.00 deg; ONLY those 2 segments change anywhere.
- [x] STRESS FIXTURE (user request): fixtures/make_stress_plan.py -> cad/StressPlan-Beams.dxf.
      Zones: Z1 baseline ring + ROTATED vertical labels; Z2 4-deg sloped; Z3 45-deg diagonal;
      Z4 900-wide + crossing + continuation MERGE (one piece); Z5 floor-clipped perimeter
      (A-FLOR partner edge); Z6 stacked-label mark-theft (B20/B23 trap); Z7 curved arc chains;
      Z8 junk (duplicate line, zero-length line, 20mm sliver, orphan label, "125 THK." note) --
      must fabricate NOTHING. tests/test_beam_stress.py: 14 tests = full DXF pipeline asserts
      + link-reader POLYLINE snakes (U-snake, collinear-leg open snake, skew snake) fed
      straight into build_beam_segments. ALL PASS. Suite now 14 files, all green.
>> 0.34.0 run: fixtures COMPLETE (stress plan renamed Test20). Test20 revealed one
   infrastructure bug -> fixed in v0.35.0, which also ships SLABS STEP 1:

### Phase 10 — Test20 text-anchor fix + SLABS wired (v0.35.0) — DONE
- [x] Test20: NO label sizing/marks at all + B7/B8 (the label-required beams) undrawn.
      Cause: text alignment is GRID-anchored; Test20 has no grid layer -> fell back to the
      link's GetTotalTransform, which Revit reported as IDENTITY (unit scale baked into the
      imported geometry, not the instance transform) -> every label 304.8x off -> nothing
      within mark_radius. FIX: anchor on ALL shared geometry when no grids (method
      "geometry_anchored"); link transform only when both anchors empty. Stress DXF now
      declares $INSUNITS=4 (mm) + regenerated under its Test20 name.
- [x] SLABS STEP 1 (user request): _create_slabs wired after beams (runs when beams run).
      Outlines: closed A-FLOR rings, else beam-perimeter-graph faces. Thickness/mark from
      "S1 150 THK"/"150 THK." notes INSIDE the loop (content-driven, any text layer).
      Floor type: model's first, duplicated per thickness ("150 THK"); level = beams' level.
      Own transaction group; console line + "slabs" in the JSON export; progress bar 7->8
      phases. KNOWN step-1 limits: no UI pickers (type/level), no openings, curved beams not
      in the graph, no slab schedule.
>> 0.35.0 run: GRID+COLUMN+BEAM = 100% of known issues SOLVED (user confirmed).
   Slabs failed to place -> fixed in v0.36.0:

### Phase 11 — SLABS round 2 (v0.36.0) — DONE, AWAITING REVIT CONFIRM
- [x] Floor.Create "No method matches given arguments (Document, list, ElementId,
      ElementId)": pythonnet does NOT convert a Python list to IList<CurveLoop>. Loops now
      packed into System.Collections.Generic.List[CurveLoop] (Revit 2025 API sig:
      Floor.Create(doc, IList<CurveLoop>, floorTypeId, levelId)). Floors flagged structural
      (FLOOR_PARAM_IS_STRUCTURAL, best-effort).
- [x] UI pickers (queued item): chk_slabs is LIVE ("Create slabs (from slab outline or beam
      layout)", auto-disabled when the model has no floor type) + cb_floor_type combo; slab
      creation gated on its own checkbox; uses selections["floor_type_id"].
- [x] OPENINGS (queued item): _nest_openings -- a loop fully inside another becomes the
      enclosing floor's inner CurveLoop (hole), not a stacked slab.
- Remaining queued: curved beams as slab-graph edges; slab schedule; slab level picker
  (currently the beams' top level); slab marks S1/S2 from a dedicated slab-text layer.
>> 0.36.0 run over the RENAMED fixture set (Test0=Messy, Test1-Test7; column-only
   fixtures culled; old fixtures considered good through beam v0.34.0):

### Phase 12 — SLABS round 3 (v0.37.0) — DONE, AWAITING REVIT CONFIRM
- [x] test4/5 slab-beam OVERLAP: graph faces sat on beam CENTRELINES. Faces now inset
      per-edge by that beam's half width (width carried through healing/splitting;
      corners rebuilt by intersecting offset carriers).
- [x] THREE-SOURCE CHAIN (user request): slab_edges -> NEW member_edges (faces of the
      DRAWN beam+column outlines = true face-line boundary, member bodies filtered by
      mean width 2A/P) -> beam_graph_inset. test4/5: member_edges 243 panels.
- [x] test6 schedule: combined one-layer schedule's SLAB table (Mark|H|Volume) now parsed
      (S-mark thickness-only blocks); slab pass receives the schedule (S1..S9 sized).
      Category renamed "schedule (column/beam/slab)"; multiple layers can map to it.
- [x] test7 inline labels: "S7_150 THK." underscore convention now parses.
- [x] test6/7 Floor.Create error on the curved slab: adjacent panel (shared edge) was
      swallowed as a HOLE (point-in-polygon arbitrary ON the boundary). _ring_inside now
      demands 50mm strict interior clearance; rings sanitized (short/collinear merged).
- [x] Stress DXF regenerated (culled by the rename); 14/14 test files pass.
>> 0.37.0 run: test4/5 member_edges 158 created / 99 ERRORS; arcs drawn as line strings;
   test6 D-slab (S8) missing; some slabs misaligned with beam outlines.

### Phase 13 — SLABS round 4 (v0.38.0) — DONE, AWAITING REVIT CONFIRM
- [x] ARC-AWARE SLAB EDGES: slab-layer arcs are 3-POINT circle fits; rings previously took
      them as two straight chords (S8's D-ring broken; curves drawn as line strings). Now:
      tessellate for geometry (16 chords) + carry (start,mid,end); builder emits ONE real
      Arc.Create per curved stretch (welded endpoints, walk-oriented, consumed once).
      Offline test6/7: 9/9 rings form and are simple; D-slab = 7.3 m2 with 3 arcs.
- [x] MEMBER-EDGE 99 ERRORS: faces threading round-column arc CHORDS (columns present in
      the Revit run, absent from the old export dump). Arc records now tessellated in the
      member-edge graph; faces must be SIMPLE rings; builder SKIPS (never errors) any
      self-intersecting outline.
- [x] DIAG: raw_geometry now also dumps COLUMN-layer records -> full member-edge replay
      offline next round.
- [ ] PENDING DIAGNOSIS (needs the 0.38.0 export with column records): "slab not aligned
      with beam outline in some places" -- suspect junction healing (350mm) fabricating
      edges where drawn edges merely end.
>> 0.38.0 run: numbers ~unchanged (test4/5 97 errors, test6/7 D-slab error persists);
   arcs real on test1-3 slab_edges but chorded elsewhere; "something wrong, can't point out".

### Phase 14 — SLABS round 5 (v0.39.0) — DONE, AWAITING REVIT CONFIRM
- [x] Regression audit 0.37 vs 0.38 per test: beams/columns identical everywhere; slabs
      test1-3 identical counts (arcs now real), test4/5 99->97 errors, test6/7 error:1 stays.
- [x] LIVE BUG A (the un-pinpointable wrongness): _ring_arcs attached arcs to NEIGHBOUR
      panels via shared junction corners -> straight edges replaced by bulging arcs. Ring
      must now TRAVERSE the arc (mid point on ring path).
- [x] LIVE BUG B: ring traversing an arc BACKWARD made the walk jump the wrong way,
      skipping up to 97% of the boundary (0.45m loop on 14.5m perimeter x3 = test6/7 error
      + micro-slab debris). Chord run now detected by circle-side test; span keyed at the
      run's walk-order start; Arc oriented to the walk. Offline: test1/2/3/6/7 rings ALL
      close at ratio 1.000, 0 gaps.
- [x] Member-edge source registers arc triples too (real curved edges without slab layer).
- [x] Diagnostics for test4/5's remaining ~97 errors: export stamps cad2bim_version;
      raw_geometry at 0.1mm (int-mm rounding made replay diverge: 255 vs 230 loops);
      slabs outcome carries error_details/skip_details; PINCH rings (repeated vertex,
      passes crossing test, fails Revit) filtered in proto + builder.
>> NEXT: user runs v0.39.0 (pull + RESTART Revit). test4/5's error_details in the export
   will name the exact Revit failure for the remaining loops; alignment issue diagnosis
   follows from the 0.1mm replay.

### Phase 15 — v0.40.0: test8 beam-over-column (CLIENT PRIORITY) + SLABS round 6 — DONE,
###            AWAITING REVIT CONFIRM (user feedback on the 0.39.0 run, 4 items)
- [x] **test8 (item 4, client): no beam drawn ON TOP of a column.** New report pass
      `split_beams_at_columns(beam_segments, sections, circles)` in script.py right after
      the end snap. Per column footprint (rects incl. rotated via long_axis_deg, circles):
      * centreline crossing strictly inside the span -> SPLIT at the faces (2 pieces);
      * segment buried face-to-face in one column (column outline mis-read as a beam,
        e.g. AC6/AC10/BC6 350x1800 exact-coextensive "beams") -> DROPPED;
      * terminal end >100mm PAST the column centre (drawn to the far face) -> TRIMMED
        back to the near face; an end AT/BEFORE the centre = junction convention (what
        snap_beam_ends_to_columns produces) -> never moves;
      * grazing a shared face line (<10mm penetration at interval midpoint) never counts;
      * leftover pieces <100mm (drafting overshoot / sliver between adjacent columns)
        are dropped; mark stays on the LONGEST piece (one-segment-per-mark invariant).
      VERIFIED offline (replay_split/verify_post_split on export items): test8 29 solid
      overlaps -> 0 (28 segments changed); test1-7 AND every .archive_fixtures export
      (0.16.1-0.39.0, tests 10-20): ZERO segments changed. 11-case tests/test_beam_split.py.
      Slabs receive a PRE-SPLIT snapshot (split reuses untouched dicts, never mutates)
      so the beam-graph slab source still closes its bay loops over the columns.
- [x] **test4/5 blank bays (item 1).** Dangling degree-1 stubs (edges ending mid-air)
      pinched 96 member-edge faces -> silently filtered = blank areas. Iterative stub
      pruning before the face walk: 158+96 -> 249 clean faces, 0 non-simple (test4+5).
- [x] **test1-3 shaft slabs (item 2).** Without a floor layer, lift/stair shafts became
      slab faces. New _beam_fraction filter: a member-edge face needs >=30% of its
      perimeter ON beam-layer edges; wall-bounded shaft faces are dropped. test1: 47 faces.
- [x] **test6/7 S8 curved slab missing (item 3).** The 142mm junction fillet arc is
      SHORTER than the 150mm chain tolerance -> greedy first-match glued its WRONG end
      (out-and-back pinch = "self-intersecting outline" skip). _chain_into_rings now
      scores all four attach modes across all unused pieces and takes the globally
      closest; _piece_fingerprint dedupes re-drawn shared edges first. 9 rings, 0 bad.
- [x] Suite: 15 test files OK (incl. new test_beam_split.py); slab checks re-verified on
      0.39.0 exports after all edits.
>> NEXT: user runs v0.40.0 in Revit on test1-8 (+ archives if wanted). Expected: test8
   beams stop at column faces everywhere; test4/5 blank bays fill; test1-3 no shaft
   slabs without floor layer; test6/7 S8 curved slab appears. Watch beam counts:
   test8 233 -> 211 segments (28 split/trimmed/dropped) is INTENDED.

### Phase 9 — SLAB PROTOTYPE (held; wire in AFTER beams close) — PROTO DONE v0.31.0
- [x] slabs_proto.py (Revit-free): TWO outline sources -- (1) A-FLOR slab-edge rings as
      drawn (closed polylines taken directly; loose lines chained into rings); (2) FALLBACK
      when no slab layer: BEAM PERIMETER GRAPH -- beam centrelines endpoint-HEALED (each end
      extended <=600mm onto the nearest carrier, so centrelines meet at column centres),
      split at X/T crossings, planar faces walked half-edge (max-CCW turn); bounded faces
      >=1 m2 = slab panels. Labels/sizing like columns+beams: "S1 150 THK" inside the loop
      names+sizes it; mark-only "S3" resolves thickness via schedule; unlabelled -> type default.
- [x] builders/slabs.py skeleton: Floor.Create(CurveLoop) per loop, type duplicated per
      thickness ("150 THK") + cached, Mark stamped. NOT imported by script.py.
- [x] tests/test_slabs_proto.py (10 tests, all pass).
- [x] Proven on real 0.30.0 exports: Test10 46 loops (A-FLOR) / 40 (graph); Test18/19 9 / 3-5
      (graph loses outer bays where the CURVED beam breaks the ring -- known proto limit);
      Test15: A-FLOR unusable (0 loops) but graph -> 233 panels from 642 beams = exactly the
      fallback case. Demo: /tmp/demo_slabs.py pattern in progress.md.
- [ ] LATER (when wiring): include curved beams as arc edges in the graph; slab openings
      (stair/lift voids as inner loops); slab text layer routing in the UI; level/offset.

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

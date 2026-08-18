# Task Plan — cad2bim after v0.68.0

**Roadmap:** `docs/superpowers/specs/2026-08-13-cad2bim-post-v0.68-roadmap.md`
(the sequencing decision and its reasoning; this file is the working checklist).

**Branch:** `claude/cad2bim`, off `main` at `12224b7`.

**Non-negotiable from here on:** `tests/run_regressions.py` green before every
release. A number that moves is not automatically a bug, but it gets explained in
the commit that moves it and the baseline re-blessed on purpose, never silently.

---

## Phase 0.5 — "The name is already in use for this element type"

**Status:** complete, shipped as v0.68.1

Reported against columns. The pre-check for "does this type already exist?" used
`==`; Revit matches type names case- and whitespace-insensitively. Reaching
`Duplicate()` at all proved the check was stricter than Revit's own rule. See
findings.md #1.

- [x] 0.5.1 `type_names.py` — `key()`, `find()`, `resolve_type()`, `record()`.
      Revit-free, so it is unit-testable outside Revit.
- [x] 0.5.2 Columns (rect + round), beams, slabs — the four that threw.
- [x] 0.5.3 Footings, stairs, stair waist — the three that swallowed it and
      built the wrong geometry in silence. They still fall back; they report now.
- [x] 0.5.4 Grids and view filters — name reuse missed on a case difference.
- [x] 0.5.5 Floor-type lookup scoped to the base type's own system family.
      Floors and Foundation Slabs share `FloorType` but are different system
      families, so a Floor named "PAD 600 THK" could be returned for a pad.
- [x] 0.5.6 `naming.validate` refuses a template that drops a size (`"{b}"`),
      which names a 300x900 and a 300x450 alike.
- [x] 0.5.7 Two AST checks over the package: no bare `.Duplicate(` outside the
      helper, no element name compared with `==`.

**Confirmed by the user in Revit:** the duplication error is gone.

---

## Phase 0 — rebuild the lost regression harnesses

**Status:** complete

Three of the four legs named in the old findings.md were written into an
uncommitted scratchpad and lost with it. Rebuilt as committed code under
`tests/`, driven by `tests/run_regressions.py` (~3 min).

- [x] 0.1 `tests/_golden.py` — baseline load/compare/save, `CAD2BIM_BLESS=1` to
      re-record. 12 unit tests, because it is the only part with logic in it.
- [x] 0.2 `regression_slab_fingerprints` — 29 archived exports, newest per
      drawing. Wider than the 22 it replaces; five of its drawings (test14,
      test15, test18, test19, test20) have no surviving DXF.
- [x] 0.3 `regression_dxf_sweep` — 17 DXFs through the full pipeline, note
      recovery and slab labels included.
- [x] 0.4 `regression_storeys` — 4 storey stacks, per-storey, roof called out.
- [x] 0.5 `tests/README.md` — the two tiers and why they are kept apart.
- [x] 0.6 Gate proved to bite: a perturbed baseline produced three named
      failures. Full verify pass green against the committed baselines.

Baselines are v0.68.1 measurements, not the lost v0.67.3 ones — those cannot be
reproduced. Drift from here is what they defend.

---

## Phase 1 — hatch/region reader + foundations from CAD

**Status:** complete

Two together, because the second cannot be verified without the first.

Today: `footing_plan.pads_for` reads only column rectangles and circles and grows
them by a projection — nothing comes from the drawing. `builders/footings.py`
`_MAX_COLUMN_MIN_SIDE_MM` discards anything bigger than a column, so a raft
cannot be produced at all. And `readers/dxf_reader.py::_geometry_record` has no
HATCH branch, so every hatch in every fixture is discarded (276 in test10, 360
each in test4/test5, 228 in Project1).

Fixture in the repo as of 2026-08-13 — test10 now carries its foundation level:

| Layer | Content | Meaning |
|-------|---------|---------|
| `S-FND` | 12 LWPOLYLINE + 8 LINE | footing and raft outlines |
| `S-FND-IDEN` | 19 MTEXT | `F3_1500MM THK\P2000MM FOLD` |
| `S-FND-FOLD` | 6 HATCH (ANSI37) + 6 LINE | fold regions |
| `S-FND-SUNK` | 1 HATCH (ANSI37) | sunk region |

- [x] 1.1 HATCH in the DXF reader: boundary paths as rings, pattern name kept.
      Reader-level, so P2 and P4 inherit it. Only the EXTERNAL path is the
      region — AutoCAD clips a hatch around any label drawn over it.
- [x] 1.2 Layer categories: foundation outline, foundation text, fold, sunk.
      Fold and sunk match BEFORE foundation, or `S-FND-FOLD` (which contains
      "fnd") is swallowed. Found on the way: Test0's `S-FNDN`, 187 entities
      ignored since the day it was added.
- [x] 1.3 Parse `F<n>_<t>MM THK` and the `\P<d>MM FOLD|SUNK` continuation.
      All 19 of test10's labels parse: F1–F6, 800/1000/1200/1500/2000.
- [x] 1.4 Footings and rafts placed from the CAD outline, thickness from the
      label. `foundation_plan.py` reads the outlines, `place_footings(outlines=)`
      builds them, and the column-offset derivation is now the fallback for a
      drawing with no foundation layer. The Revit-side wiring is pinned by AST
      checks in `test_dialog_wiring.py` — every link in it degrades silently
      back to invented pads, and no offline harness can reach `builders/`.
- [x] 1.5 Quality, riding along: the size discard now REPORTS the region it
      declined to invent a pad for instead of dropping it in silence; and
      `col_region_max_side_mm` was read from `selections["limits"]`, where the
      dialog never writes it, so the user's setting had never once reached the
      footing pass.
- [x] 1.6 Regression: the sweep gains ten foundation/region counts. test10
      measures 13 outlines, 13 sized, 6 fold + 1 sunk regions.

**How an outline is recovered.** Ten of test10's thirteen are closed polylines,
taken exactly as drawn. The other three — two 5500x11900 pads with a 3500x5900
sunk strip between them — share their long edges, each drawn once, so a chainer
that consumes a segment as it goes closes none of them. A planar face walk reads
a shared edge from both sides; that is why it is there.

**A drawing has to prove it uses the convention.** `plan_foundations` returns
nothing unless at least one outline carries a foundation note. Test0 is the
reason: its `S-FNDN` linework closes into four accidental faces that no label
names anywhere in the drawing, and placing those would be worse than the guess
they replaced. Refusing costs nothing — the caller falls back.

---

## Phase 2 — folds and sunk

**Status:** complete (2.4 shipped as v0.73.0, with a recorded remainder).

**The open question is closed.** The user gave the rule from their own detail:
the fold support's offset is the **thickness of the top slab** — `-200` on a
200 mm slab. Generalised from that, taking the parent's top as 0:

| | |
|-|-|
| parent soffit | `-T_parent` |
| dropped slab top | `-d` |
| dropped slab soffit | `-(d + T_dropped)` |

A support exists only where the drop leaves a **void** — `d > T_parent`, the
dropped slab's top below the parent's soffit. Where it does, it is cast soffit
to soffit: `offset = -T_parent`, `depth = d + T_dropped - T_parent`, plan width
`T_parent`. The user's detail is the equal-thickness case (`350 + 200 - 200 =
350` at `-200`).

**The existence condition was corrected once, against the corridor** (findings
#7): "soffit gap > 0" measured 250 on the 250-sunk-in-500-block bay and cast
two phantom footings inside solid concrete — the dropped slab's own side face
already closed that section. `d > T_parent` is the test; the original F6's
`1000 + 1000 - 2000 = 0` was that drawing's coincidence, not the rule.

- [x] 2.1 Fold/sunk regions from the hatch rings of 1.1, paired to their label.
      Each region takes the note that sits INSIDE it, so test10's three fold
      notes per F3 raft pair exactly rather than by proximity.
- [x] 2.2 The three parts placed: the parent with the region cut out of it, the
      support between the soffits, the dropped slab at the step depth.
      **Corrected twice per the user's Revit tests:** first, the support is ONE
      slab per stepped run, not a strip per edge — a collar, an L, or a strip.
      Then, neighbouring collars POOL: same host, same thickness and offset,
      touching outers → one slab wrapping the whole group, every fold in it a
      hollow. test10's row of three folds per raft = one support per raft.
- [x] 2.3 Magnitude threshold: over 3000 mm is a storey, not a step. Test9's
      `+6250` is refused and named; test10's folds still build.
- [x] 2.4 Legend-driven mapping for Test9-style drawings (swatch pattern →
      legend text → meaning), auto-proposed into the override dialog.
      `legend.py`, Revit-free; v0.73.0.

**Measured on test9 (the numbers that drove every 2.4 rule):** 14 legend rows
("HATCH INDICATE ...", layer `PI_TEXT 25`) across THREE tower legends plus a
standalone cutout entry — the sheet is three plans (3 Boundary + 3 Origin
records). Swatches are 807x484 / 1001x601 / 1100x400 rectangles (the old
~600x500 estimate was wrong), texts 657–947 mm from the swatch centre (not
~2600), rows stacked 617–640 mm so the WRONG row's swatch is 839–1020 mm out
— hence MUTUAL-nearest pairing. The nearest PLAN hatch to any legend text is
6622 mm (worst 16140): the measured form of the "mispairs at 5000 mm+"
warning, and why meaning travels by pattern. The same pattern means different
things per tower (ZIGZAG: `+50MM` / `COMPENSATORY STRIP` / `+6250`; STARS and
SOLID likewise), so the whole-sheet read refuses those patterns loudly — two
meanings, no proposal, a note. What survives: **ONE proposal**, ASPHALT →
cutout on `PI_SHEAR WALL CUTOUT` (9 plan hatches, all on that one layer),
overriding the name convention's "structural wall" ("shear") — visibly
marked in the dialog row, printed to the console, still editable. Three
report-only meanings (AR-CONC, ANSI32, ANSI37) ride along verbatim.

**2.4 remainder, recorded rather than half-wired:** `legend.legend_steps()`
delivers the per-pattern step DEPTH behind the same `max_step_mm` threshold
plan_steps applies (+6250 is refused and named wherever depths flow), but no
pass consumes it yet — stepping a SLAB from a legend depth is P2-on-slabs
territory (plan_steps only runs for foundations today). And a per-tower read
(after the multi-storey split, one legend block per plan) would disambiguate
what the whole-sheet read rightly refuses; it needs the split to hand regions
per plan to the mapping stage, which happens before the split today. The
SIGN question is open in findings #6: every step value on test9 is "+", so
step proposals go to CATEGORY_FOLD rather than guessing raised-vs-dropped.

**Test10 was redrawn by the user 2026-08-14** — the old F5/F6 middle (1000 sunk
between 2000 pads) was a design error on the drawing side. The new foundation
level: eight closed pads (F1/F2/F4), one big F3 raft 750 thick whose boundary
closes through two long seams, and a 500-thick corridor block NESTED inside it
whose sides are completed by the drawn sunk rectangle. That drawing drove three
recovery upgrades: segments split where another segment's endpoint lands on
them (the right seam overshoots a corner by 400 mm), step-layer lines join the
face graph and are then dissolved (they mark where a foundation steps, not
where one ends), and a nested outline becomes a hole in its parent, one level,
like slab openings.

**Measured on the redrawn test10 (v0.69.1):** 10 outlines, 10 sized; 7 steps
planned, 0 skipped; **2 supports total**. Each raft's three folds pool into one
13200 x 4500 slab, 1500 deep at `-750`, with the three folds as its hollows.
The sunk bay gets **none** — `250 < 500`, no void — while still dropping: the
corridor is cut and the dropped slab cast 500 thick at `-250`.

**The corridor, third pass — the X-cross cutouts.** v0.69.5's step-note rule
dissolved the corridor zone and the raft was then cast SOLID over the whole
strip; the drawing crosses its north and south parts out (two diagonals
corner-to-corner on `A-DETL`, the opening symbol — findings, "An X across a
part means no concrete there"). An X-marked NESTED face is now a CUTOUT: never
an element, excluded from the step-line stitch, its ring a hole of the plan
containing it; and `split_profile` fuses tangent holes first, so the raft
casts around ONE corridor hole with the sunk slab dropped into its middle.
Measured: 9 outlines + 2 cutouts, the raft one piece with 7 holes
(corridor + 6 folds), 18 foundation-level elements in all; the sweep gains
`foundation_cutouts`.

---

## Phase 2 — the representation it was built from

Applies to slabs AND rafts.

P1 leaves the evidence assembled: each foundation plan carries a `steps` list
holding every FOLD/SUNK note inside its outline (test10: three folds in each of
the two F3 rings, one sunk in the middle strip), and the fold and sunk hatch
regions are read and counted. Nothing is stepped yet — the builder reports the
regions it found and places flat concrete.

**Representation, corrected 2026-08-13 by the user's own Revit detail.** The
earlier plan was two floors — a dropped floor plus a hole in the parent. The
office actually builds a fold from **three** floors:

1. the normal slab, on the level, running up to where the fold starts;
2. a **fold support** along the fold line — plan width = the slab thickness,
   depth = the sunk value — which is the vertical face between the two levels;
3. the folded/sunk slab at the dropped level.

The three together are one folded slab. The middle element is the part the
two-floor plan had no answer for: without it the step is a gap, not concrete.

Still no `SlabShapeEditor` — all three are ordinary `Floor.Create` calls, so the
whole construction stays visible to the offline harnesses.

- [ ] 2.1 Fold/sunk regions from the hatch rings of 1.1, paired to their label
      (already proven 1:1 on test10 — 6 folds, 1 sunk).
- [ ] 2.2 Place the three floors per region: parent, fold support, dropped slab.
- [ ] 2.3 Magnitude threshold. Test9's legend has `T.O.S. +50MM`, `+400MM` and
      `+6250`. 6250 is a storey, not a fold: route to its own level or report.
- [x] 2.4 Legend-driven mapping for Test9-style drawings (swatch pattern → legend
      text → meaning), auto-proposed into the override dialog, never silent.
      (Shipped v0.73.0 — the measured numbers live in the Phase 2 block above.)

**Open question before 2.2 can be written:** the exact vertical placement of the
fold support. In the supplied detail the slab is `350 THK RCC SLAB`, the two
levels read 0.000 and -350.000, and the selected floor sits at
`Height Offset From Level = -200.000` with a 200 dimension against it. With slab
thickness and sunk value both 350 in that example, the image alone cannot say
which of the two drives the support's offset.

---

## Phase 3 — walls as real `DB.Wall`

**Status:** P3a (the Revit-free plan) shipped as v0.75.0; P3b (builder +
dialog) shipped as v0.76.0, awaiting the user's Revit validation. P3c holds
the two deferred decisions below.

- [x] 3a.1 Classification: `rcc` token added to the structural-wall row, so
      test8's `S-RCC-WALL` (29 records) stops reading as an arch wall.
      Measured against the full corpus layer dump (72 distinct names across
      the 17 DXFs + archived exports): exactly ONE layer moves — the other
      rcc layers (`PI_RCC BEAM`, `S-RCC-COL`) are claimed by the beam and
      column rows above it.
- [x] 3a.2 `wall_plan.py` — `plan_walls(records, texts, tolerances)` →
      `{"segments", "skipped"}`, Revit-free. Closed thin rings read as
      outlines (quads at any rotation, rectilinear L/U rings decomposed; a
      U open by one wall width closed first); loose faces merged collinear
      across door gaps and paired smallest-gap-first with union spans —
      `recover_core_walls`' three refinements, generalised off the axes
      because the corpus is angled (10.3° runs in Project1 and test8).
      Cutout-layer linework refused by name; every refusal lands in
      `skipped` with a reason.
- [x] 3a.3 22 unit tests (679 → 701), the fixture pins on EXACT record
      coordinates from test8/test9/Project1; sweep gains six wall metrics
      per fixture, all other numbers unmoved (the re-blessed baseline diff
      is those 102 lines and nothing else).

**Measured for P3a (the numbers behind every constant — findings #12):**
wall layers exist in 3 of 17 drawings. Real widths 100–495 mm (empty below
100 down to the ~5 mm re-traces, empty 495–565, door artifacts from 565);
band set 90..520. Collinear face gaps: 150–200 (crossing walls), 750–1310
(doors: 27×750, 10×1000, 12×1150, 12×1200), room-scale from 1350; bridge
set 1300. Planned: Project1 17 segments / 11 skips, test8 178 / 110, test9
19 / 39 (10 of those the door cutouts, 3 the zero-length stone lines).

- [x] 3b Builder + dialog (v0.76.0). `builders/walls.py` places one
      line-based `Wall.Create` per planned centreline: width through the
      type's compound structure (no instance parameter exists), duplicated
      per (kind, width) off a per-kind base type — a refused width (membrane
      layer, curtain/stacked base) is a red console error and the wall still
      places at the base type's own width; top constrained to the level
      above via WALL_HEIGHT_TYPE after Create (the column builder's
      pattern), unconnected at the storey height when no top exists; the
      `structural` bool on Create is the kind. `run_builders._create_walls`
      plans ONCE for both kinds (tolerances passed through), places each
      kind against its own type, groups the planner's refusals on the
      console. Dialog: Structure gains the structural-wall group,
      Architecture its first real content (arch group + roofs note); naming
      rows "RCC WALL {t} THK" / "BRICK WALL {t} THK", {t} required (the
      raft precedent — a collision is a silent reuse and widths are
      measured, not noted); selections keys create_struct_walls /
      create_arch_walls / struct_wall_type_id / arch_wall_type_id; settings
      and preset ride the name-driven capture, no schema change. Walls run
      per storey, step 8 of the build. Tests 701 → 714; gate green with
      ZERO baseline movement (no planning change).

- [ ] 3c The two deferred decisions, taken against the user's Revit run of
      P3b — recorded here rather than guessed:
      * **Walls from core recovery.** `recover_core_walls` still places
        lift-core walls as thin COLUMNS (`recovered_core_wall`), untouched
        by P3b — column counts did not move and must not until this
        decides. Moving them to `DB.Wall` changes column and wall counts
        together and wants the user's verdict on the P3b walls first.
      * **One wall drawn on both conventions.** test8's 250 `S-RCC-WALL`
        quad carries a 150 arch `wall` trace 50 mm off its centreline
        (shared face, findings #12): both kinds plan and both now BUILD,
        overlapping. Which side wins — and whether the loser is dropped in
        the planner or the builder — is the user's call once they see the
        pair in Revit.

---

## Phase 4-7

Detail in the roadmap document; opened when the phase starts.

- [ ] 4 Openings — doors, windows, shafts. Needs 1.1 and phase 3's hosts.
- [ ] 5 Round-trip QA — built model vs source DXF delta.
- [ ] 6 Annotation — dimensions, tags, views, sheets.
- [ ] 7 Rebar feeding `Dev.panel/BBS Generator.pushbutton`.

---

## Decisions

| # | Decision | Why |
|---|----------|-----|
| 1 | Harnesses (P0) before any feature | The next release changes geometry in every domain; without the legs, "no regressions" is an assertion |
| 2 | Foundations before walls | Today's foundations are invented from column offsets and rafts are impossible; and P1 builds the hatch machinery P2 and P4 both need |
| 3 | Folds/sunk as a separate floor at an offset | Reuses `_nest_openings`, which is already covered by the harnesses; `SlabShapeEditor` cannot be verified offline |
| 4 | Regression legs named `regression_*`, not `test_*` | Keeps the inner loop at ~1s; a gate that slows the inner loop stops being run, which is how the last set was lost |
| 5 | Baselines re-measured at v0.68.1 | The v0.67.3 originals cannot be reproduced; the scripts that made them are gone |
| 6 | Type-name clash becomes a REUSE, never a rename | The name encodes the size, so an existing type of that name is the right type; inventing "400 X 600 (2)" would pollute the model |
| 7 | `modules_plan.md` superseded | Older toolkit-wide plan, overtaken by the v0.68.0 refactor and this roadmap |

## Errors encountered

| Error | Resolution |
|-------|------------|
| `The name is already in use for this element type` (v0.68.0, columns) | Phase 0.5: match names the way Revit matches them |

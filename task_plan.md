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

**Status:** next. Applies to slabs AND rafts.

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
- [ ] 2.4 Legend-driven mapping for Test9-style drawings (swatch pattern → legend
      text → meaning), auto-proposed into the override dialog, never silent.

**Open question before 2.2 can be written:** the exact vertical placement of the
fold support. In the supplied detail the slab is `350 THK RCC SLAB`, the two
levels read 0.000 and -350.000, and the selected floor sits at
`Height Offset From Level = -200.000` with a 200 dimension against it. With slab
thickness and sunk value both 350 in that example, the image alone cannot say
which of the two drives the support's offset.

---

## Phase 3-7

Detail in the roadmap document; opened when the phase starts.

- [ ] 3 Walls as real `DB.Wall`. Today `geom/shapes.py::recover_core_walls`
      emits them as column entries, so a wall is placed as a long thin column.
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

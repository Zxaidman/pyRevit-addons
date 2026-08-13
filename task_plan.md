# Task Plan — cad2bim after v0.68.0

**Roadmap:** `docs/superpowers/specs/2026-08-13-cad2bim-post-v0.68-roadmap.md`
(the sequencing decision and its reasoning; this file is the working checklist).

**Branch:** `claude/cad2bim-roadmap-continuation-ynszsk`, off `main` at `12224b7`.

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

**Status:** starting

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

- [ ] 1.1 HATCH in the DXF reader: boundary paths as rings, pattern name kept.
      Reader-level, so P2 and P4 inherit it.
- [ ] 1.2 Layer categories: foundation outline, foundation text, fold, sunk.
      `S-FND` currently classifies as unmapped; `S-FND-IDEN` is excluded from
      geometry by the `iden` rule (correct) and ignored as text (not correct).
- [ ] 1.3 Parse `F<n>_<t>MM THK` and the `\P<d>MM FOLD|SUNK` continuation.
      Marks F1–F6, thicknesses 800/1000/1200/1500/2000.
- [ ] 1.4 Footings and rafts placed from the CAD outline, thickness from the
      label. Column-offset derivation becomes the fallback for a drawing with no
      foundation layer, not the only path.
- [ ] 1.5 Quality, riding along: the `col_region_max_side_mm` discard that makes
      rafts impossible.
- [ ] 1.6 Regression: the sweep gains foundation counts; test10 is the case.

---

## Phase 2 — folds and sunk

**Status:** not started. Applies to slabs AND rafts.

Representation decided: a separate floor at an offset, with the region cut as a
hole in the parent. `builders/slabs.py::_nest_openings` already nests a
ring-inside-a-ring; `builders/footings.py::_zero_offset` already drives the
height parameter. `SlabShapeEditor` was rejected — it has no offline
representation, so the P0 harnesses could not see it.

- [ ] 2.1 Fold/sunk regions from the hatch rings of 1.1, paired to their label.
- [ ] 2.2 Depth applied as a height offset; parent gets the hole.
- [ ] 2.3 Magnitude threshold. Test9's legend has `T.O.S. +50MM`, `+400MM` and
      `+6250`. 6250 is a storey, not a fold: route to its own level or report.
- [ ] 2.4 Legend-driven mapping for Test9-style drawings (swatch pattern → legend
      text → meaning), auto-proposed into the override dialog, never silent.

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

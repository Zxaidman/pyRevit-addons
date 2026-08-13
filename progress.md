# Progress Log — cad2bim

Earlier sessions (v0.36 → v0.68.0) are in main's history; this log restarts on
the post-v0.68.0 roadmap.

## Session 2026-08-13 — roadmap, v0.68.1, phase 0

### Context on entry

- `main` at `12224b7`, cad2bim v0.68.0. Branch
  `claude/cad2bim-roadmap-continuation-ynszsk` created off it.
- v0.68.0 was a pure refactor, confirmed in Revit against v0.67.5.
- Brief said the session harness would name the branch `...-osh3jm`; it created
  `...-ynszsk` and binds to that. Same base commit, same purpose. The branch was
  invisible on GitHub at first because nothing had been pushed to it yet.

### Roadmap agreed

Two open questions closed with the user:

1. **Harnesses before features.** Three of the four regression legs were lost with
   an uncommitted scratchpad, so P0 rebuilds them before any feature lands.
2. **Foundations before walls.** The original recommendation was walls first.
   Displaced: foundations is where the output is most wrong today, and P1's
   hatch/region machinery is a prerequisite for both folds/sunk and openings.

Sequence: P0 harnesses → P1 hatch reader + foundations from CAD → P2 folds/sunk
(slabs and rafts) → P3 walls → P4 openings → P5 round-trip QA → P6 annotation →
P7 rebar. Per-domain quality fixes ride inside the release that touches them.

Written up in `docs/superpowers/specs/2026-08-13-cad2bim-post-v0.68-roadmap.md`.

### Phase 0.5 — type-name matching (v0.68.1)

User hit `The name is already in use for this element type.` on columns.

- Root cause: the "does this type exist?" pre-check used `==`; Revit matches type
  names case- and whitespace-insensitively. Reaching `Duplicate()` at all proved
  the check was stricter than Revit's rule (findings.md #1).
- Audited every site before writing any fix. Seven had the same shape. Beams and
  slabs would have thrown identically. Footings, stairs and the stair waist
  swallowed it and built the wrong geometry in silence.
- `type_names.py`: `key()` normalises, `resolve_type()` returns
  `(type, created, note)`. `created` is the licence to write dimensions, so a
  type the model owns is never resized under the user.
- Also fixed: floor-type lookup scoped to the base type's own system family
  (Floors and Foundation Slabs share `FloorType`); `naming.validate` refuses a
  template that drops a size.
- Tests 419 → 440: unit tests against a fake enforcing Revit's rule, plus two AST
  checks (no bare `.Duplicate(`, no element name compared with `==`).
- Shipped v0.68.1. **User confirmed in Revit: the error is gone.**

### Phase 0 — regression harnesses rebuilt

- `tests/_golden.py` + 12 unit tests — the compare step, the only part with logic.
- `regression_slab_fingerprints`: 29 archived exports, newest per drawing,
  discovered not hard-listed. Wider than the 22 it replaces; five of its drawings
  have no surviving DXF and nothing else watches them.
- `regression_dxf_sweep`: 17 DXFs, full pipeline. Extended mid-build to carry the
  whole slab chain — an export drops the raw text, so note recovery and labels
  can only be driven from a DXF.
- `regression_storeys`: 4 stacks (test9 ×11, test10 ×10, test12 ×5, test13 ×5),
  per-storey, roof called out. test10's roof records `edges=0` — the no-A-FLOR
  case behind the v0.67.2 bug.
- `run_regressions.py` runs all three (~3 min); `tests/README.md` documents the
  two tiers. Legs are `regression_*` so the inner loop stays 452 tests / ~1s.
- Gate proved to bite: a perturbed baseline produced three named failures
  (`StructuralPlan-Test1.dxf.column_rectangles: 62 -> 61`, a moved beam count, a
  dropped fixture). Then a full bless + verify pass: **all 3 legs green against
  the committed baselines.**
- Corroboration that the harness reproduces the real pipeline: the old findings
  recorded "test10 +6 noted bays"; the sweep measures 6.
- Follow-up commit pinned the fingerprint storey by identity rather than index,
  so a re-ordered export cannot silently change what is measured.

### Foundation fixture landed

The user added the foundation level to test10: `S-FND` (12 LWPOLYLINE + 8 LINE),
`S-FND-IDEN` (19 MTEXT, `F3_1500MM THK\P2000MM FOLD`), `S-FND-FOLD` (6 ANSI37
hatches), `S-FND-SUNK` (1). Marks F1–F6, thicknesses 800–2000 mm. Fold and sunk
hatch counts match their label counts exactly. P1's entry gate is met.

### Planning files reset

`task_plan.md`, `findings.md` and `progress.md` closed out on v0.68 and rewritten
onto the new roadmap. `modules_plan.md` left in place but recorded as superseded.

### Phase 1 — the drawing's own foundations

Branch note: the work continues on `claude/cad2bim`, which the session harness
bound to the same commit the `...-ynszsk` and `...-y4s34n` branches held. Same
history, one name from here.

**P1.1 — HATCH in the reader.** Hatches go into a NEW `result.regions`, not into
`records`: a hatch is a region, not a curve, and a curve pipeline handed a few
hundred closed rings would try to make columns out of them. The practical value
of that choice is that the P0 baselines, which count `records`, became a
corpus-wide proof that the change moved nothing. Only the EXTERNAL boundary is
the region — AutoCAD clips a hatch around any label drawn over it, so test10's
folds arrive as three paths each, two of them textbox islands.

**P1.2/P1.3 — layers and labels.** Fold and sunk are matched before foundation,
or `S-FND-FOLD` (which contains "fnd") is swallowed by it. `foundation_labels`
takes `on_foundation_layer` because a BARE thickness is a raft note there and a
slab note anywhere else; the text cannot separate them and must not guess.

**P1.4 — foundations placed from the outline.** `foundation_plan.py` reads the
rings and sizes each from the note inside it; `place_footings(outlines=)` builds
them; the column-offset derivation is now the fallback for a drawing that has no
foundation layer.

Two things drove the design, both discovered by measuring rather than assuming:

- Three of test10's thirteen outlines SHARE their edges (two pads flanking a
  sunk strip, inner edges drawn once). The slab chainer recovers 0 of the three
  because it consumes each segment as it goes. A planar face walk reads a shared
  edge from both sides and returns all three.
- Test0's `S-FNDN` closes into four accidental faces and carries no label
  anywhere in the drawing. So a drawing has to PROVE it uses the convention:
  nothing is planned unless at least one outline carries a note. Test0 falls
  back to the old path untouched.

Cross-checked on the real fixture from two independent directions: 13 outlines,
13 sized, 19 notes every one of them inside a ring, and 6 fold + 1 sunk notes
matching 6 fold + 1 sunk hatch regions exactly.

**P1.5 — the silent discard.** `pads_for` dropped any footprint wider than a
column without a word. The filter is right for the column-derived path; the
silence was not, and it now reports. Bigger find alongside it: the pass read
`col_region_max_side_mm` from `selections["limits"]`, where the dialog never
writes it — so the user's setting had never once reached the footings (findings
#7). Read from `tolerances` now, the same dict the column pass uses.

**P1.6 — the gate.** Ten foundation/region counts added to the DXF sweep. The
baseline diff is **170 pure insertions and zero changed lines** across 17
drawings: every pre-existing measurement is identical, which is the evidence
that reading foundations altered nothing that already worked. Unit tests
486 → 514.

The last four of those are static wiring checks, because the Revit-side half of
P1.4 fails QUIETLY: drop `records`/`texts` at the call and `plan_foundations`
reads an empty drawing, drop `outlines=` and the builder falls back to invented
pads — and either way the run still reports "footings created". `builders/`
imports Revit at module level, so no offline harness can reach it; the check is
an AST read of the call sites, the same way the dialog bindings are pinned.
Proved to bite: breaking each of the four links fails its own test.

### Open

- P2 next: folds and sunk, on slabs and rafts. P1 leaves each foundation plan
  carrying its `steps` notes, and the fold/sunk hatch regions read and counted;
  nothing is stepped yet. The open number is still the fold support's vertical
  placement — slab thickness and sunk value are both 350 in the supplied detail,
  so the image cannot say which drives it.
- Foundation outlines that NEST (a pad drawn inside a raft) are placed as two
  overlapping floors. Not present in this corpus; slabs solve it with
  `_nest_openings`, which is the obvious source to borrow from if a drawing
  turns one up.
- `graphify-out/` is 18 versions stale (built at `56c2d6a`, v0.50.0) and contains
  none of the twenty post-refactor modules. Documentation, not a gate.

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

### Open

- P1 starting: HATCH support in the DXF reader first, then the foundation layer
  and text mapping, then footings/rafts placed from the CAD outline.
- `graphify-out/` is 18 versions stale (built at `56c2d6a`, v0.50.0) and contains
  none of the twenty post-refactor modules. Documentation, not a gate.

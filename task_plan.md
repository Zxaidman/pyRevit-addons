# Task Plan — cad2bim v0.68: CLR type fix, modular refactor, merge to main

**Goal:** clear the "Duplicate type name within an assembly" crash introduced by the
v0.67.3 module reload, break the four oversized modules into small focused ones with
zero behaviour change, prove no regressions across the fixture suite, then merge this
branch into main and archive it.

**Branch:** `claude/ecstatic-dijkstra-rmvyl7` → merge into `main` at the end.

**Non-negotiable through every phase:** the 403-test suite stays green, the 22 stored
slab fingerprints stay byte-identical, and the DXF fixture sweep (columns / beams /
slabs per fixture) stays unchanged unless a change is intended and explained.

---

## Phase 1 — "Duplicate type name within an assembly" (BLOCKER)

**Status:** complete

Root cause is understood and confirmed by reading the code (see findings.md #1).
Python.NET builds a real CLR type for every Python class that derives from a .NET
interface. The AppDomain rejects a second type with the same name, and v0.67.3's
`_drop_stale_modules()` makes those modules re-import on every click:

| Site | Kind | Re-created because |
|------|------|--------------------|
| `cad2bim/builders/txn_failures.py` `WarningSwallower(IFailuresPreprocessor)` | module level | purged + re-imported each run |
| `revit/transactions.py` `SuppressWarningsPreprocessor(IFailuresPreprocessor)` | module level | purged + re-imported each run |
| `cad2bim.pushbutton/script.py` `_wrap_selection_filter._Filter(ISelectionFilter)` | inside a function | re-created on every CALL (latent since long before v0.67.3) |

Run 1 in a fresh Revit session builds the types; run 2 purges, re-imports and tries to
build them again → the crash the user saw.

**Approach:** keep the reload (it fixes the whole stale-library class of bugs) and make
CLR type creation idempotent instead. A tiny purge-proof registry module holds each
created type; every site asks the registry first and only builds the class on a miss.

- [x] 1.1 `lib/py3/anongee_clr.py` — top-level (outside `anongee_toolkit`, so the purge
      never touches it): `get_or_create(name, factory)` + `registered()`. Pure Python,
      unit-testable without Revit.
- [x] 1.2 `txn_failures.py` — class body moves into a factory, module attribute comes
      from the registry. Public name `WarningSwallower` unchanged.
- [x] 1.3 `revit/transactions.py` — same treatment for `SuppressWarningsPreprocessor`.
- [x] 1.4 `script.py` `_wrap_selection_filter` — build through the registry, which also
      fixes picking stair outlines twice in one session.
- [x] 1.5 Tests: registry unit tests + a static test asserting no module under
      `anongee_toolkit` declares a CLR-derived class at import time outside the registry.
- [x] 1.6 Ship as v0.67.4 for the user to confirm two consecutive runs in one session.
- [x] 1.7 (from the v0.67.3 export) `drop_nested_columns`: the roof's 12300 wall was
      placed alongside two 2700 lengths of itself. Wholly inside + same thickness +
      parallel; shipped as v0.67.5.

**Exit criteria:** user runs the button twice in one Revit session without the crash.

---

## Phase 2 — Refactor: smaller, focused modules

**Status:** in_progress — library splits under way while the user tests v0.67.5

Current sizes (the four the user is reacting to):

| File | Lines | Split into |
|------|-------|-----------|
| `cad2bim/report.py` | 3039 | `columns/sections.py`, `columns/recovery.py`, `columns/text_fit.py`, `beams/segments.py`, `beams/cleanup.py`, `export.py`, keep `report.py` as the facade |
| `cad2bim.pushbutton/script.py` | 2956 | `dialog/` (window + tabs), `run/` (phases), `progress.py`, `console.py`; `script.py` becomes the entry point |
| `cad2bim/stair_layout.py` | 1683 | `stairs/runs.py`, `stairs/landings.py`, `stairs/fan.py`, `stairs/plan.py` |
| `cad2bim/slab_outlines.py` | 1550 | `slabs/edges.py`, `slabs/graph.py`, `slabs/exactness.py`, `slabs/labels.py` |

**Rules for this phase (regression discipline):**
1. One module extracted per commit — never two at once.
2. Pure moves. No logic edits, no renames of public functions, no "while I'm here".
3. The old module keeps its public API by re-exporting, so no call site changes in the
   same commit as a move.
4. After EVERY extraction: full unit suite + slab fingerprint replay + fixture sweep.
   Any diff at all stops the commit until it is explained.
5. `script.py` last — it is the riskiest and cannot be unit-tested outside Revit beyond
   the static wiring checks.

- [x] 2.1 Target layout agreed by default (user did not pick; all four files, library
      first, script.py last). Merge style still open, decided at merge time.
- [x] 2.2 Baseline captured: `scratchpad/refactor_base_fingerprints.json` (22 exports)
      and `scratchpad/refactor_base_sweep.txt` (17 DXFs)
- [x] 2.3a `export.py` — console summary + JSON export (400 lines)
- [x] 2.3b `columns_recovery.py` — the five recovery passes (747 lines)
- [x] 2.3c `column_geom.py` (188) + `limits.py` (67) — the shared primitives
- [x] 2.3d `tests/_loader.py` — one dependency graph instead of twenty hand-rolled
      loaders; the scratchpad harnesses use it too
- [ ] 2.3e `report.py` (1931) → split the BEAM half (build_beam_segments, splitting,
      dedupe, snapping) from column SECTIONS
- [ ] 2.4 `slab_outlines.py` → slabs/
- [ ] 2.5 `stair_layout.py` → stairs/
- [ ] 2.6 `script.py` → dialog/ + run/ (+ keep the static wiring tests passing)
- [ ] 2.7 Delete the facades if (and only if) every call site has moved cleanly

---

## Phase 3 — Review pass

**Status:** pending

- [ ] 3.1 `/code-review` over the whole branch diff vs main
- [ ] 3.2 Fix what the review turns up (correctness first, then simplification)
- [ ] 3.3 Re-run: unit suite, fingerprints, sweep, and a real Revit run by the user

---

## Phase 4 — Merge and archive

**Status:** pending

- [ ] 4.1 User confirms a clean Revit run on the refactored build (no regressions)
- [ ] 4.2 Squash/merge `claude/ecstatic-dijkstra-rmvyl7` → `main`
- [ ] 4.3 Push main, archive the branch
- [ ] 4.4 Final version bump + version-history entry

**Gate:** nothing merges until the user reports a clean run. This is their call, not mine.

---

## Decisions

| # | Decision | Why |
|---|----------|-----|
| 1 | Keep the v0.67.3 module reload; fix the CLR types instead | Reverting reintroduces "no attribute next_level_names" after every update |
| 2 | Registry module lives OUTSIDE `anongee_toolkit` | Anything inside is purged by design, so it could not hold the cache |
| 3 | Refactor is pure moves, one module per commit | The only way to prove "no regressions" on a codebase whose tests are mostly end-to-end replays |
| 4 | Facade modules stay until every caller is migrated | Keeps each commit independently revertable |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| `naming has no attribute next_level_names` (v0.67.1) | 1 | v0.67.3 purges `anongee_toolkit` from `sys.modules` each run |
| `Duplicate type name within an assembly` (v0.67.3, 2nd run) | 1 | Phase 1: purge-proof CLR type registry |

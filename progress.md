# Progress Log — cad2bim

## Session 2026-08-11 — planning + Phase 1

### Context on entry
- Branch `claude/ecstatic-dijkstra-rmvyl7`, HEAD at v0.67.3 (`6a1f153`).
- Shipped this session before planning: v0.67.0 (beam material ids, combined columns,
  noted slabs, saved settings), v0.67.1 (level naming), v0.67.2 (roof slabs + doubled
  wall, from the user's own v0.67.0 export), v0.67.3 (stale module reload).
- User report: v0.67.3 crashes on the SECOND run in one Revit session with
  `Duplicate type name within an assembly`.

### Planning
- Created `task_plan.md`, `findings.md`, `progress.md`.
- Investigated the crash before writing the plan (3 greps): root cause confirmed as
  Python.NET CLR type re-creation caused by the v0.67.3 module purge. Details in
  findings.md #1.
- Phases agreed: 1 CLR fix (blocker) → 2 modular refactor → 3 review → 4 merge+archive.

### Phase 1 — CLR type registry (v0.67.4)
- Added `lib/py3/anongee_clr.py`: purge-proof `get_or_create(name, factory)`.
- `txn_failures.WarningSwallower`, `revit.transactions.SuppressWarningsPreprocessor` and
  `script._wrap_selection_filter._Filter` now build through it.
- Tests: 8 registry unit tests + a static check that no `anongee_toolkit` module declares
  a CLR-derived class at import time outside the registry.
- Suite: 412 tests green. Fixture sweep and slab fingerprints untouched by this change
  (no geometry code in the diff).
- Shipped v0.67.4, pushed.

### Phase 1b — a wall placed whole AND in pieces (v0.67.5)
- The user's v0.67.3 export (pushed as c31830f) confirms the roof slab fix landed in
  Revit (6 bays via "placed_members + beam graph") but shows 12 roof columns: the
  12300x300 wall plus two 2700x300 lengths of it, placed as composite outlines.
- Added `report.drop_nested_columns`: wholly inside + same thickness + parallel.
- First cut used containment alone: -48 columns on test12, -16 on test9, all real
  members swallowed by a bigger blob's bounding box. Narrowed to the three conditions;
  the fixture sweep now drops only genuine duplicates (verified pair by pair:
  2540x450 inside 2800x450, 2380x200 inside 2610x200, a literal 300x1400 twice).
- Suite 416 green. Sweep: test12 -9, Project1 -6, test9 -3, test8 -2, others 0.

### Phase 2 — modular refactor (in progress)
- Defaults taken (user did not answer the scope question): all four files, library
  first, `script.py` last, nothing merged until they confirm a clean Revit run.
- Baseline captured before any move: 22 slab fingerprints + the 17-DXF sweep.
- Move 1: `export.py` (console + JSON). Move 2: `columns_recovery.py`. Move 3:
  `column_geom.py` + `limits.py`. report.py 3039 -> 1931 lines.
- `tests/_loader.py` replaces twenty hand-rolled loaders: the dependency graph is in
  one place, so the next split touches one file instead of thirteen.
- After EVERY move: 416 tests green, 22 fingerprints identical, fixture sweep
  identical line for line. Two commits pushed.

### Next
- Split the beam half out of report.py, then slab_outlines.py, stair_layout.py, and
  script.py last.

### Waiting on
- User to run v0.67.5 twice in ONE Revit session and confirm the crash is gone, then
  push the JSON export. Phase 2 (refactor) does not start until that lands.

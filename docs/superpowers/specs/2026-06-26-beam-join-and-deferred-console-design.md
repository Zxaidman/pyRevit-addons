# Design — Beam end-join control + deferred console with progress bar

Date: 2026-06-26
Scope: cad2bim CAD-to-BIM pushbutton. **Features only** (user chose features-first);
the reported beam bugs (B22->C12, B20 300x900, Test10 grid-6 miss, Test15 between-grid +
short-curve errors) are a SEPARATE follow-up, not in this spec.

Branch: `claude/ecstatic-dijkstra-rmvyl7`. Version after this work: 0.29.0.

---

## Feature A — Disallow beam end-joins

### Goal
Every placed beam (straight AND curved), at BOTH ends, has its structural end-join
disallowed, so Revit does not auto-join/extend a beam into neighbouring framing.

### Design
- Revit API: `Autodesk.Revit.DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(member, end)`
  with `end` = 0 and `end` = 1.
- Apply in `builders/beams.py`:
  - `place_beams`: after `NewFamilyInstance` + `_set_mark`, call `_disallow_joins(instance)`.
  - `place_curved_beams`: same.
- New helper `_disallow_joins(instance)`:
  ```
  for end in (0, 1):
      try:
          StructuralFramingUtils.DisallowJoinAtEnd(instance, end)
      except Exception:
          pass   # best-effort; never fail placement over a join setting
  ```
- Import `StructuralFramingUtils` from `Autodesk.Revit.DB.Structure` (next to `StructuralType`).
- Runs inside the existing beam Transaction (DisallowJoinAtEnd is a model edit).

### Test / verification
- Cannot run Revit here -> syntax check + logic review. `DisallowJoinAtEnd` is a documented
  Revit API. Verify on a Revit re-run (beam ends no longer auto-join).

---

## Feature B — Console appears only after Run, with a [####----] progress bar

### Goal
1. No pyRevit output window content until the user clicks Run on the MAIN window
   (`CadToBimWindow`). The earlier link-options dialog and geometry read must not print.
2. After Run: flush all buffered output (including the version/host banner), then show a
   text progress bar `[####------]` advancing per build phase, then the normal summary.

### Constraints
- Toolkit forbids `pyrevit` module imports (Brand Guidelines). The bar is plain `print()`,
  one line per phase update (pyRevit output appends; no in-place carriage-return needed).

### Design — buffer + flush (chosen approach)
- New tiny output sink in `script.py` (module-level), e.g. `_OUT`:
  - `_OUT.log(msg)` -> append to an internal list (does NOT print).
  - `_OUT.flush()` -> print every buffered line, then clear the buffer.
  - `_OUT.live` flag: once flushed (post-Run), `log()` prints immediately (live mode) so
    build-phase + summary output appears in real time.
- Replace `print(...)` calls along the `main()` pipeline with `_OUT.log(...)`:
  - version/host banner, "columns: ...", "beams: ...", compare/report console blocks.
- Progress helper `_progress(i, n, label)`:
  - prints `"[%s] %3d%%  %s" % (bar, pct, label)` where `bar` is 10 cells:
    `"#" * fill + "-" * (10 - fill)`, `fill = round(i / n * 10)`.
- Phase sequence (n = 7), each calls `_progress` then does the work:
  1 link DXF, 2 read link geometry, 3 build columns, 4 build beams,
  5 create grids, 6 create columns, 7 create beams -> then summary.
  (Phases the user did not enable, e.g. beams off, advance the bar without work.)
- Phase timing vs the main window: phases 1-2 (link DXF, read link geometry) run BEFORE the
  main window (their output populates the mapping). Phases 3-7 (build columns, build beams,
  create grids/columns/beams) run AFTER `CadToBimWindow.show()` returns (they consume the
  user's selections). Sequence:
  - Phases 1-2: `_progress` + `log` are buffered (nothing on screen yet).
  - `CadToBimWindow.show()` returns (Run set `self.result`, window closed).
  - `main()` calls `_OUT.flush()` -> banner + the buffered phase 1-2 bar lines print now,
    in order, then `_OUT` switches to live mode.
  - Phases 3-7 run with `_progress`/`log` printing LIVE, then the summary.
  - Console reads top-to-bottom: banner -> [#---] link -> [###-] read -> ... -> summary.
- `try/finally`: wrap the post-link body so an exception still calls `_OUT.flush()` (buffered
  logs are not lost on a crash). Pre-Run hard errors keep using `_alert`/`_error` MessageBox.

### Why buffer-list over sys.stdout redirect
- Explicit and local: only the toolkit's own messages are deferred; we never swallow or
  re-order unrelated engine output. A global stdout redirect risks capturing/holding output
  from other code and is harder to reason about on the pyRevit CPython engine.

### Edge cases
- User cancels at the link dialog or main window: nothing was flushed -> console stays
  empty (correct: they never hit Run).
- Beams/columns disabled: their phase still advances the bar (labelled "skipped").

### Test / verification
- `report.py`/builders are unit-testable; `script.py` is not (needs Revit). Add a small
  standalone unit test for the pure bits: the `_progress` bar string and the `_OUT`
  buffer/flush/live behaviour (move them into a tiny importable helper or test via a stub).
- Verify console-gating + bar on a Revit re-run.

---

## Out of scope (separate follow-up, after these features)
- B22 should attach to C12 (extend wide beam end to the core column).
- B20 placed as 300x900 unmarked (Test18) instead of 600x900.
- Test10: vertical beam H->I on grid 6 missing.
- Test15: beams drawn BETWEEN grids K/J and T/S instead of on grid; 2 short-curve
  (zero/near-zero length) beam errors at create. Likely regressions from 0.28.x
  (snap making zero-length ends; degenerate-explode making mid-grid/short segments).

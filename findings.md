# Findings — cad2bim v0.68 work

## 1. "Duplicate type name within an assembly" — root cause (confirmed by reading code)

Python.NET emits a REAL CLR type into a dynamic assembly for every Python class that
derives from a .NET interface. `__namespace__ = "CadToBim"` (required for Python.NET 3
to build the derived type at all) fixes that type's full name. Creating the same full
name twice in one AppDomain raises `Duplicate type name within an assembly`. A Revit
session is one AppDomain and the CPython3 engine keeps it alive across clicks.

Sites in this repo (grep: `IFailuresPreprocessor|ISelectionFilter|IExternalEventHandler|IUpdater`):

```
lib/py3/anongee_toolkit/cad2bim/builders/txn_failures.py:14
    class WarningSwallower(IFailuresPreprocessor):     __namespace__ = "CadToBim"

lib/py3/anongee_toolkit/revit/transactions.py:26
    class SuppressWarningsPreprocessor(IFailuresPreprocessor):

AnonGee.tab/Core.panel/cad2bim.pushbutton/script.py  (_wrap_selection_filter)
    class _Filter(ISelectionFilter, _CurveElementFilter):  __namespace__ = "CadToBim"
```

Why it appeared only now: before v0.67.3 those modules were imported ONCE per Revit
session and cached, so the type was built once. v0.67.3's `_drop_stale_modules()` (the
fix for `naming has no attribute next_level_names`) deletes `anongee_toolkit*` from
`sys.modules` on every run, so the module bodies execute again → second type → crash.

Timeline matches the report exactly: a fresh session's run 1 has nothing to purge and
builds the types; run 2 purges, re-imports and crashes.

`_wrap_selection_filter` is worse and predates v0.67.3: it defines `_Filter` INSIDE the
function, so a second call in the same session (pick stair outlines twice) crashes on
its own. Nobody had hit it because the flow is rarely used twice per session.

**Fix shape:** cache the created type outside the purge. A module that is not under
`anongee_toolkit` survives `_drop_stale_modules()`, so a tiny `anongee_clr.py` at the
top of `lib/py3` can hold `{name: type}` and hand the same type back on re-import.

Rejected alternatives:
- Revert the reload → brings back the stale-library bug on every future release.
- Exempt those two modules from the purge → they then go stale silently; a future edit
  to either would need a Revit restart and would look like the bug we just fixed.
- Version-gated purge (only reload when the on-disk version differs) → still creates the
  type a second time on the first run after any update, i.e. the crash just moves.

## 2. Module sizes driving the refactor (lines, current branch)

```
3039  cad2bim/report.py
2956  cad2bim.pushbutton/script.py
1683  cad2bim/stair_layout.py
1550  cad2bim/slab_outlines.py
1310  cad2bim/geom/shapes.py
1310  cad2bim/__init__.py          (mostly the version history block)
 896  cad2bim/floor_plans.py
```

`report.py` holds four unrelated jobs: column sectioning, column recovery/text fitting,
beam segmentation/cleanup, and the JSON export. `script.py` holds the console, the
progress bars, two dialogs, the storey stack and the whole run pipeline.

## 3. Regression harnesses that must be re-run after every extraction

- Unit suite: `cd lib/py3/anongee_toolkit/cad2bim/tests && python -m unittest discover -s . -p "test_*.py"` (403 tests)
- Slab fingerprints: `scratchpad/slabbase.py <out.json>` → diff against `base_after.json`
  (22 stored exports; all 22 currently byte-identical)
- Fixture sweep: `scratchpad/sweep67.py` → columns before/after face recovery, slab
  loops + note recovery, beam count, per DXF (17 fixtures)
- Storey/roof replays: `scratchpad/t10_full.py`, `t10_cols.py`

Current sweep baseline (v0.67.3): test1/2/3 +2 face columns each, test10 +15 faces and
+6 noted bays, test13 +195 noted bays, every other fixture unchanged.

## 4. Test10 / test12 fixtures were updated by the user on 2026-08-06 (commit 89bdae2)

The roof of test10 now has NO A-FLOR layer at all, which is what exposed the
"note recovery only ran when edges were found" bug fixed in v0.67.2. Any offline replay
result quoted before that commit is stale.

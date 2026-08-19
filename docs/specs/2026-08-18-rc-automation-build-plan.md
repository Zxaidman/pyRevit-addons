# RC Automation — build plan

Three phases, each a mode the user picks in the window rather than a release
they wait for. Decisions behind them are in
[`2026-08-18-rc-automation-feasibility-review.md`](2026-08-18-rc-automation-feasibility-review.md) §7.

| Phase | Mode | Model | Reinforcement | Needs placement |
| --- | --- | --- | --- | --- |
| **1** | `MODE_CREATE_ALL` | create | create | **yes** |
| **2** | `MODE_REBAR_ONLY` | exists | create | no |
| **3** | `MODE_RECONCILE` | exists | exists | no |

Phase 1 leads because it is the pitch: an empty model, a schedule, and a
reinforced structure at the end of it. Phases 2 and 3 are the same machinery
with progressively more of the answer already in the model.

---

## 1. What each phase adds

**Phase 1 — new model, new rebar.** Read the schedule, place footings and
columns where the placement sheets say, then reinforce them. The model may be
empty, so positions come from `X`/`Y` millimetres as readily as from grid
references; a project with no grids in it yet cannot use grid references at all.

**Phase 2 — existing model, new rebar.** The structure is modelled. Match each
schedule row to its element and reinforce it. Placement is ignored — the host
supplies its own geometry, which is the whole reason this phase needs no
coordinates. This is also the phase that closes the loop with BBS Generator.

**Phase 3 — existing model, existing rebar.** Both exist. Compare them with the
schedule field by field and let the user settle each disagreement.

Parsing is mode-independent: the workbook is read once and every sheet it has is
kept, so switching mode in the window never re-reads the file. Only *which
absences are errors* depends on the mode.

---

## 2. Excel workbook

Six sheets. `●` marks the ones a mode cannot run without.

```
   Phase       1  2  3
FOOTING_TYPES      ●  ●  ●    TypeMark Length Width Thickness
                              CoverTop CoverBottom CoverSide [Concrete] [Comments]

FOOTING_PLACEMENT  ●  ·  ·    Mark TypeMark GridX GridY [X] [Y]
                              Level [TopOffset] [Rotation] [Outline]

FOOTING_REBAR      ●  ●  ●    TypeMark Layer Direction [BarType] Diameter
                              [Count] [Spacing] ShapeCode [EndCover] [Comments]

COLUMN_TYPES       ●  ●  ●    TypeMark Width Depth Cover [Concrete] [Comments]

COLUMN_PLACEMENT   ●  ·  ·    Mark TypeMark GridX GridY [X] [Y]
                              BaseLevel [BaseOffset] TopLevel [TopOffset] [Rotation]

COLUMN_REBAR       ●  ●  ●    TypeMark BarRole [BarType] Diameter [Count] [Spacing]
                              ShapeCode [SpacingEnd] [ConfinementLength] [Comments]
```

Rules the workbook is held to:

- **All lengths are millimetres**, declared by a `UNITS` row above the header.
  Declared as anything else is an error; undeclared is a warning and mm is
  assumed.
- **Position** is `GridX` + `GridY`, or `X` + `Y` in millimetres. Half of either
  is an error, and so is neither. Given both, the grid reference wins.
- **`Outline`** is optional and is what earns footings being floors rather than
  family instances: `"0,0; 4500,0; 4500,3000; 2250,4200; 0,3000"` places a
  five-sided pad instead of the type's Length × Width rectangle. Points are
  millimetres relative to the placement point, before rotation.
- **Columns have no Height.** They run base level to top level, offsets
  included; a height column would be a second source of truth that disagrees the
  moment a level moves.
- `Count` **or** `Spacing`, either or both — the pair chooses the Revit layout
  rule (`NumberWithSpacing` / `FixedNumber` / `MaximumSpacing`) so the schedule
  never has to name one.
- `ShapeCode` must exist in `BS_8666_2020.SHAPE_MAP`. Phase 1 builds geometry for
  `00`, `11`, `21` and `51`; anything else validates, warns, and is skipped with
  a reason rather than silently substituted.
- Original spec names still load — `FootingMark`, `ColumnMark`, `Dia`, `Nos`,
  `Shape` are aliases.

---

## 3. Reconciliation

Once an element exists, the workbook stops being an instruction and becomes a
second opinion. Every comparable field is checked and each difference is shown
with both values side by side.

**Excel wins by default.** The schedule is the controlled document and the model
is usually what drifted. The user flips any row to `Model`, per row, and the tool
records whether a row was decided or merely defaulted — a report that cannot tell
one from the other is not an audit trail.

Deliberate behaviours, each with a test:

- Rounding noise is not a disagreement (0.5 mm tolerance; bar counts and
  diameters are exact).
- A field the model cannot report is *unknown*, not zero — treating it as a
  difference would bury the real ones.
- Choosing `Model` still falls back to the schedule for fields the model has no
  opinion on.
- Differences are reported as **Info**, not warnings. Disagreeing with the model
  is the normal reason to run this; grading it as a problem trains people to
  ignore the colour that means something is actually wrong.
- Geometric differences are separated from parameter ones. A cover mismatch can
  be resolved by setting a value; a length mismatch means changing the element,
  which is governed by the rules below and is report-only today.

### Phase 3 — resolving a geometric difference

**Decided 2026-08-18. Recorded now, implemented later.** Today every geometric
difference is reported and nothing in the model changes.

Deciding that the schedule wins is cheap; acting on it is not. Changing a footing
that is already modelled means changing a `Floor`'s sketch, and anything hosted in
or measuring that footing is downstream of the change. The rule, in order:

| | Condition | Action |
| --- | --- | --- |
| **1** | Nothing depends on the element — no rebar hosted in it, no dimension or annotation referencing it | **Edit the sketch in place.** The element keeps its id, so nothing downstream notices. |
| **2** | Something does depend on it | **Do not delete it first.** Create the corrected element alongside, move each dependent onto it so the dependent re-measures itself against the new geometry, and retire the old one last. |
| **3** | Neither is safe | **Report only.** Say what differs, leave the model alone. |

Rule 3 is also the whole of today's behaviour, and it is enforced in code rather
than left as an intention: `reconcile.GEOMETRY_CHANGES_ARE_DEFERRED` is set,
`reconcile.strategy_for()` returns `STRATEGY_REPORT_ONLY` for every case while it
is, and the report says *"Reported only — length would have to change in the
model, which this release does not do"* rather than "using the schedule". A
report that implies a change nobody made is the kind of sentence someone signs a
drawing off against. Tests pin both the current behaviour and the rule beneath
it, so switching it on is one deliberate edit that the suite notices.

**What rule 2 actually costs.** Revit has no re-host. There is no
`Rebar.SetHostId`, and a `Dimension`'s references cannot be re-pointed at another
element. "Move each dependent onto it" is therefore *capture → recreate →
verify*: read the dependent's defining curves, bar type and layout rule, build
the equivalent against the new element, confirm it, and only then remove the
original. Lossless where everything can be captured faithfully; where it cannot,
the case falls to rule 3 rather than guessing. Revit also deletes a dimension
whose reference disappears — which is exactly why the old element is retired
last rather than first.

Non-geometric differences are unaffected. Cover, and anything else that is a
parameter rather than a shape, resolves by setting a value and is actionable now.

---

## 4. Module layout

Revit-free code lives in the toolkit so it runs under
`python -m unittest discover -s tests` with no Revit. Nothing is imported from
`cad2bim` — it belongs to its own pushbutton.

```
anongee_toolkit/rc_automation/          no Revit — 423 tests, all green
    models.py            DTOs, modes, severities, layout rules       ✅
    standards.py         the BS 8666 subset validation needs         ✅
    excel_engine.py      read_grid (openpyxl) + parse_grid (pure)    ✅
    validation.py        rules → Error / Warning / Info              ✅
    reconcile.py         field-by-field comparison, Excel default    ✅
    rebar_spec.py        workbook row → bar centrelines, sets vs bars ✅
    reporting_engine.py  hand-rolled CSV (no `csv` module), JSON, XLSX

anongee_toolkit/structural/             Revit-touching, statically checked
    rebar_types.py       bar / hook / cover TYPE resolution, match never create ✅
    rebar_hosts.py       key-parameter matching, IsValidHost, why-not messages  ✅
    rebar_geometry.py    local mm → world-feet List[Curve], array vector = normal ✅
    rebar_factory.py     Rebar.CreateFromCurves, layout rules, sets, stamping    ✅
    footings.py          Floor.Create from an outline, on a level
    columns.py           FamilyInstance between two levels

RC Automation.pushbutton/               Revit + WPF — READ-ONLY build shipped
    script.py            modeless window, FIFO queue, read-only probe ✅
    ui.xaml              inlined theme, findings grid, probe panel    ✅
    bundle.yaml  icon.png  CHANGELOG.md                               ✅
    preview_engine.py    OverrideGraphicSettings + DirectShape
```

---

## 5. Matching (phases 2 and 3)

A `Key Parameter` dropdown, default `Mark`, read off the host category, with
`Level` as tie-breaker. Choosing `Type Mark` makes one workbook row drive every
instance of that type. Statuses:

| Status | Condition | Default action |
| --- | --- | --- |
| `INVALID` | no host, or `RebarHostData.IsValidHost()` is false — most often a floor without `FLOOR_PARAM_IS_STRUCTURAL` | reported |
| `CREATE` | host found, carries no rebar | Create |
| `MATCHED` | existing bars agree with the schedule | Skip |
| `DIFFERS` | they disagree | resolve — Excel unless the user says otherwise |

---

## 6. Rebar creation

- **Sets, not individual bars** — `SetLayoutAsNumberWithSpacing` /
  `SetLayoutAsMaximumSpacing` / `SetLayoutAsFixedNumber`. ~2,000 elements
  instead of ~50,000 at the 500-element target, and what a detailer expects to
  edit. Compatible with BBS Generator, which reads
  `REBAR_ELEM_QUANTITY_OF_BARS`.
- **Cover** is a `RebarCoverType` element, not a number. Resolved against
  existing cover types by value; no match is a mapping error, not a silent
  creation.
- **Footing bars** are built from the floor's sketch outline inset by side
  cover, at the z of bottom cover plus layer offset. Because the outline is
  arbitrary, bar lengths come from intersecting the run direction with the inset
  outline — never from assuming a rectangle.
- **Column ties** are shape `51` closed links, `RebarStyle.StirrupTie`.
  Confinement produces three sets per column when `SpacingEnd` and
  `ConfinementLength` are given.
- **Column mains** are straight shape `00`. **Laps and starter bars are out of
  scope** and the report says so per column, so nobody mistakes the output for a
  complete cage.

---

## 7. Execution and safety

- All Revit work inside `IExternalEventHandler.Execute()`, through the FIFO
  request queue of §12.8.7.3.
- Chunked at ~25 elements per `Raise()`, each chunk its own `Transaction`, all
  inside one `TransactionGroup` that is `Assimilate()`d — one undo step for the
  whole run. Cancellation is checked between chunks, which is the only point it
  can be honest.
- A fresh `IFailuresPreprocessor` swallows batch warnings, with the same
  `__namespace__` / no-`__init__` / once-per-session treatment as the event
  handler.
- `try/finally` on every transaction, gated on
  `if t.HasStarted() and not t.HasEnded(): t.RollBack()`.
- Worksharing checked with `WorksharingUtils.GetCheckoutStatus`; "owned by
  another user" is a skipped row, not an exception.

---

## 8. UI

Modeless, built on `Dev.panel/Modeless.pushbutton`: `window.Show()`,
`WindowInteropHelper.Owner` set **after** Show, handler class and window ref on a
session-state module in `sys.modules`.

Sections: Workbook · Mode · Mapping (Level, Bar Type, Cover) · Validation
Results · Preview Grid · Preview Controls · Execution Log · Actions.

**No MVVM, no `ObservableCollection`, no INPC** — §12.7 G. Rows are a `__slots__`
class in a `System.Collections.ArrayList`, assigned `ItemsSource = None` first.
Only int element ids cross the thread boundary.

---

## 9. Delivery gates

`tests/test_repo_docs.py` fails until the pushbutton is documented in
`README.md`, recorded in `CHANGELOG.md`, and its panel declared in
`extension.json`. Part of the work, not follow-up.

---

## 10. Build order

1. ✅ `models` · `standards` · `excel_engine` · `validation` — schedule in, objects out.
2. ✅ `reconcile` — field-by-field comparison with the Excel default.
3. ✅ `rebar_spec` — workbook row to bar centrelines, and whether a run is a set.
4. ✅ **Read-only pushbutton, v0.1.0** — the window opens, the workbook loads and
   validates, the model is probed, and nothing is written. Everything below is
   downstream of questions only Revit can answer, so this build answers them
   first: does the CPython 3 engine import the toolkit, does the bundled
   openpyxl load, does the modeless bridge hold, are the levels and bar types
   present, and can the matched elements host reinforcement at all.
5. ✅ `rebar_types` · `rebar_hosts` · `rebar_geometry` · `rebar_factory` — bar
   specs to `Rebar.CreateFromCurves`, held statically to opening no transaction,
   marshalling `List[Curve]` with `Add`, and naming only toolkit functions that
   exist. Not yet wired to the window: the next thing to do is put a Create
   button behind it, inside a `TransactionGroup` the pushbutton owns.
6. `structural/footings` + `structural/columns` — Phase 1 creation.
7. `preview_engine` — overrides and DirectShape.
8. Phase 2 matching, then Phase 3 reconciliation wiring.
9. Chunked execution, cancellation, failure preprocessor, worksharing.
10. `reporting_engine`, then re-check the delivery gates.

Steps 1–3 are the entire data model and testable off-Revit; step 4 proves the
Revit half without risking a model; step 5 is where the real risk sits, which is
why everything else is proven first.

# RC Automation — P0 build plan

**Scope: rebar only, onto footings and columns that already exist in the model.**
Structure creation is P1 and is deliberately not in this plan.

Decisions this plan implements are recorded in
[`2026-08-18-rc-automation-feasibility-review.md`](2026-08-18-rc-automation-feasibility-review.md) §7.

---

## 1. Why this slice first

It is the only part of the spec that is unblocked today: the host already exists,
so nothing depends on the missing coordinate columns. It also closes the loop
that makes the whole feature worth building —

    Excel schedule → RC Automation → DB.Rebar → BBS Generator → Excel BBS

and it ships a second capability almost for free: because P0 compares existing
rebar against the workbook (decision 8), the same window verifies a model that
someone else detailed.

---

## 2. Excel workbook

The full template is authored now so P1 does not break it. **P0 requires only the
sheets marked ●**; the placement sheets may be absent, and are ignored if present.

```
● FOOTING_TYPES     TypeMark  Length  Width  Thickness
                    CoverTop  CoverBottom  CoverSide  [Concrete]  [Comments]

  FOOTING_PLACEMENT Mark  TypeMark  GridX  GridY  [X]  [Y]
                    Level  [TopOffset]  [Rotation]                     (P1)

● FOOTING_REBAR     TypeMark  Layer  Direction  BarType  Diameter
                    [Count]  [Spacing]  ShapeCode  [EndCover]  [Comments]

● COLUMN_TYPES      TypeMark  Width  Depth  Cover  [Concrete]  [Comments]

  COLUMN_PLACEMENT  Mark  TypeMark  GridX  GridY  [X]  [Y]
                    BaseLevel  [BaseOffset]  TopLevel  [TopOffset]  [Rotation]   (P1)

● COLUMN_REBAR      TypeMark  BarRole  BarType  Diameter  [Count]  [Spacing]
                    ShapeCode  [SpacingEnd]  [ConfinementLength]  [Comments]
```

Rules the validation engine enforces:

- **All lengths are millimetres.** Asserted by a `UNITS` cell on `FOOTING_TYPES`;
  anything else is a hard error. The toolkit is mm-native (`revit/units.py`).
- `Layer` ∈ `B1 B2 T1 T2` — B1 is the bottom outermost layer. Layer order sets the
  z-offset: B2 sits one bar diameter above B1.
- `Direction` ∈ `X Y` (model X/Y). A footing needs at least one bottom layer.
- `BarRole` ∈ `Main Tie`. Two `Main` rows per column are legal and expected
  (corner bars + face bars at different diameters).
- **`Count` or `Spacing` is required, either or both.** Both → `NumberWithSpacing`.
  Count only → `FixedNumber`. Spacing only → `MaximumSpacing`.
- `ShapeCode` must exist in `BS_8666_2020.SHAPE_MAP`. **P0 builds geometry for
  `00`, `11`, `21` (footing bars) and `51` (ties)**; any other listed code parses
  and validates but is reported as `INVALID — shape not yet supported`, never
  silently dropped.
- `.xlsx` / `.xlsm` only — openpyxl cannot open legacy `.xls`. A formula cell that
  reads as `None` under `data_only=True` (the file was last written by something
  other than Excel) is a named error, not a traceback.

---

## 3. Module layout

Revit-free code lives in the toolkit so it runs under
`python -m unittest discover -s tests` with no Revit. Nothing is imported from
`cad2bim` — it belongs to its own pushbutton.

```
anongee_toolkit/rc_automation/          no Revit imports — unit-tested
    models.py            __slots__ DTOs: FootingType, ColumnType, RebarRow, MatchRow
    excel_engine.py      openpyxl load, header resolution, normalisation to mm
    validation.py        rule engine → Error / Warning / Info, each with sheet+row
    rebar_spec.py        workbook row → abstract BarSpec (shape, dims, layout, offsets)
    comparison.py        BarSpec vs observed bars → MATCHED / CONFLICT, with tolerance
    reporting_engine.py  hand-rolled CSV (no `csv` module), JSON, XLSX via openpyxl

anongee_toolkit/structural/             Revit-touching, reusable
    rebar_hosts.py       host validity, RebarHostData, cover-type resolution
    rebar_types.py       RebarBarType / RebarHookType collection and name matching
    rebar_factory.py     Rebar.CreateFromCurves wrappers, layout rules, set creation
    rebar_geometry.py    BarSpec + host bounding geometry → IList<Curve> in feet

RCAutomation.pushbutton/                Revit + WPF
    script.py            modeless window, session-state module, run()
    ui.xaml
    external_events.py   IExternalEventHandler + FIFO request queue
    preview_items.py     __slots__ row objects + ArrayList refresh
    preview_engine.py    OverrideGraphicSettings + DirectShape preview
    bundle.yaml  icon.png  CHANGELOG.md
```

---

## 4. Matching and comparison

**Host resolution.** A `Key Parameter` dropdown (default `Mark`) is read off the
host category; `Level` disambiguates when one key value appears more than once.
Choosing `Type Mark` makes a single workbook row drive every instance of that type
— the payoff of the type/placement split.

**Status assignment**, per host × workbook row:

| Status | Condition | Default action |
| --- | --- | --- |
| `INVALID` | no host for the key, **or** `RebarHostData.GetRebarHostData(host).IsValidHost()` is false — most often a floor without `FLOOR_PARAM_IS_STRUCTURAL` | none, reported |
| `CREATE` | host found, carries no rebar | Create |
| `MATCHED` | host found, existing bars agree within tolerance | Skip |
| `CONFLICT` | host found, existing bars differ | Skip, user may opt into Replace |

Comparison is on diameter, spacing, count, layer and direction, with a
configurable tolerance (default 1 mm on spacing, exact on diameter and count) —
3000 vs 3000.4 mm must not read as a conflict. `revit/units.clean_ft` already
rounds to the nearest millimetre.

---

## 5. Rebar creation

- **Sets, not individual bars** — one `Rebar` per layer via
  `SetLayoutAsNumberWithSpacing` / `SetLayoutAsMaximumSpacing` /
  `SetLayoutAsFixedNumber`. ~2,000 elements instead of ~50,000 at target scale,
  and it is what a detailer expects to edit.
- **Cover** is a `RebarCoverType` element, not a number. Resolve the workbook's
  cover value against existing cover types by value; if none matches, that is a
  mapping error surfaced beside the bar-type mapping — same policy as decision 6,
  no silent creation.
- **Footing bars** are built in the host's plan from the floor's sketch outline
  inset by side cover, at the z of (bottom cover + layer offset). Because the host
  is a `Floor` with an arbitrary outline, bar lengths are computed by intersecting
  the run direction with the inset outline — not by assuming a rectangle.
- **Column ties** are shape `51` closed links, `RebarStyle.StirrupTie`, inset from
  the column section by cover. Confinement is honoured when `SpacingEnd` and
  `ConfinementLength` are given: three sets per column (end, middle, end).
- **Column mains** are shape `00` straight in P0. **Laps and starter bars are
  explicitly out of scope** and the report says so per column, so nobody mistakes
  P0 output for a complete cage.
- `SetSolidInView(view, false)` on creation to keep the model workable.

---

## 6. Execution and safety

- Everything Revit-side runs in `IExternalEventHandler.Execute()`, reached through
  the FIFO request queue from §12.8.7.3 — not the single-slot dict.
- Work is **chunked**: ~25 hosts per `ExternalEvent.Raise()`, each chunk its own
  `Transaction`, all chunks inside one `TransactionGroup` that is `Assimilate()`d
  so the whole run is **one undo step**. The cancel flag is checked between
  chunks, which is the only point where cancellation is honest.
- A fresh `IFailuresPreprocessor` swallows the warnings a 500-element batch
  generates. It needs the same `__namespace__` / no-`__init__` / defined-once
  treatment as the event handler (§12.9.4).
- `try/finally` on every transaction, gated on
  `if t.HasStarted() and not t.HasEnded(): t.RollBack()`.
- Worksharing: check `WorksharingUtils.GetCheckoutStatus` before writing and
  report "owned by another user" as a skipped row rather than an exception.

---

## 7. UI

Modeless, built on `Dev.panel/Modeless.pushbutton` verbatim: `window.Show()`,
`WindowInteropHelper.Owner` set **after** Show, handler class cached on a
session-state module in `sys.modules`, window ref held there too.

Sections: Workbook · Mapping (Level, Bar Type, Cover) · Validation Results ·
Preview Grid · Preview Controls · Execution Log · Actions.

**No MVVM, no `ObservableCollection`, no INPC** — §12.7 G. Grid rows are a
`__slots__` class in a `System.Collections.ArrayList`, assigned with
`ItemsSource = None` first to force row containers to rebuild. Slot names match
`{Binding}` paths exactly, which `tests/test_rc_automation_ui.py` asserts
statically.

Only int element ids cross the thread boundary; the id → Element map stays on the
handler (§12.8.7.2).

---

## 8. Tests

Following the repo's existing split — Revit-free logic tested from the root.

- `tests/test_rc_automation.py` — header resolution, unit assertion, every
  validation rule, layout-rule selection, layer z-offsets, `BarSpec` geometry
  against a non-rectangular outline, comparison tolerance, CSV/JSON writers.
- `tests/test_rc_automation_ui.py` — mirrors `test_autolevel_ui.py`: every
  `FindName` resolves and is used, every `{Binding}` has a `__slots__` entry, no
  `re`, no pyRevit imports, no `StaticResource` on the root `Window`, every
  `{StaticResource}` key exists, literals starting with `{` are escaped, every
  interactive control has a tooltip, versions agree across `bundle.yaml`,
  `CHANGELOG.md` and the window header.

---

## 9. Delivery gates

`tests/test_repo_docs.py` **fails** until all three are done, so they are part of
the work, not follow-up:

1. `README.md` documents the new pushbutton in its panel table.
2. `CHANGELOG.md` leads with the version `extension.json` declares.
3. `extension.json` declares the panel the button ships in.

---

## 10. Build order

1. `models.py` + `excel_engine.py` + `validation.py`, with tests and a sample workbook.
2. `rebar_spec.py` + `comparison.py`, with tests. **Still no Revit.**
3. `rebar_hosts.py` / `rebar_types.py` — read-only Revit; prove host validity and
   type collection against a real model before writing anything.
4. `ui.xaml` + `script.py` + `external_events.py` + `preview_items.py` — window
   opens, workbook loads, grid populates, still zero writes.
5. `preview_engine.py` — overrides and DirectShape.
6. `rebar_geometry.py` + `rebar_factory.py` — first writes, footings before columns.
7. Chunked execution, cancellation, failure preprocessor, worksharing.
8. `reporting_engine.py`, then the three delivery gates.

Steps 1–2 are the whole data model and are fully testable off-Revit; step 6 is
where the real risk sits, which is why everything else is proven first.

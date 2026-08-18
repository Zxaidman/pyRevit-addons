# RC Automation — feasibility review of FEATURE_SPECIFICATION v1.0

Excel → Revit RC Automation (footings, columns, rebar), reviewed against the
repository as it actually stands on `claude/anongee-pyrevit-pushbutton-bjttbg`.

Status: **review only. No implementation started.** Four blocking decisions are
listed at the end; the schema redesign in §3 is the one that changes the most.

---

## 1. What the spec assumes about this repo, and what is actually here

The spec opens by listing what the repository "already contains". Three of
those five claims do not survive contact with the code.

| Spec claim | Reality | Consequence |
| --- | --- | --- |
| "Modeless Window implementation" | **True.** `Dev.panel/Modeless.pushbutton` (339 lines) is a complete reference: `ExternalEvent`, session-state module in `sys.modules`, `WindowInteropHelper` anchoring, dispatcher marshalling. `MultiFilterParameter.pushbutton` is the production-scale version with a serialized FIFO request queue. | Solid foundation. Copy it. |
| "Reusable WPF/XAML framework" | **Partly.** `anongee_toolkit/ui/` has `theme`, `xaml`, `forms`, `dialogs`, `progressbar`, `pump`, `checklist`, `hostwnd`. But there is no view-model layer and no binding infrastructure. | See §2 — the spec's MVVM requirement is prohibited by the repo's own rules. |
| "Structural utility modules" | **Misleading.** Footing and column creation exist, but inside `anongee_toolkit/cad2bim/builders/`, coupled to cad2bim's own `sections` dict format and `footing_plan.plan_pads()`. There is no generic structural creation API. | Reuse means extracting and generalising, not importing. Budget for it. |
| "Rebar utility modules" | **False.** `anongee_toolkit/structural/rebars.py` is 46 lines and only *collects* existing rebar. Searched the whole tree: **zero** occurrences of `Rebar.CreateFromCurves`, `Rebar.CreateFromRebarShape`, `RebarHostData`, or `RebarShapeDrivenAccessor`. | **Rebar creation is 100% greenfield.** It is the highest-risk deliverable in the spec and the spec assumes it is already scaffolded. |
| "Toolkit architecture" | **True.** `anongee_toolkit` is a real, layered package (`revit/`, `ui/`, `io/`, `structural/`, `operations/`, `cad2bim/`), ~28k lines. | Good. |

### The spec also misfiles work that already ships

"FUTURE PHASES → Phase 3: BBS Auto Generation, BBS Verification, Rebar Revision
Tracking" is **already built**. `Dev.panel/BBS Generator.pushbutton` is ~3,400
lines with `standards/BS_8666_2020.py`, `standards/ACI_315_2018.py`,
`standards/IS_2502_2019.py`, a bar-mark manager, a shape resolver, a revision
tracker, and Excel + PDF export.

This changes the product argument. BBS Generator reads `DB.Rebar` and produces a
schedule. RC Automation would *create* `DB.Rebar`. Together they close the loop:

    Excel schedule → Revit rebar → BBS back out to Excel

That round trip is the strongest reason to build this feature, and the spec
never mentions it. It also imposes a constraint the spec misses: **the rebar RC
Automation creates must carry the parameters BBS Generator reads** — shape code,
bar mark, host mark, bar type name. `core/rebar_reader.py` and
`core/shape_resolver.py` define exactly what those are. Build to that contract or
the two tools will not talk.

---

## 2. Faults in the architecture section

### 2.1 `viewmodels.py` / "MVVM support / Observable collections" is PR-blocked

The spec's instruction 6 ("Use MVVM-style separation") contradicts its own
instruction 4 ("Follow existing toolkit patterns"), and the repo's design system
settles it. Brand guidelines **§12.7 G**:

> DataTemplate bindings to Python `@property` objects on classes that implement
> `INotifyPropertyChanged` **fail silently** in CPython 3 / Python.NET 3 —
> bindings return empty strings or the template instantiates without errors but
> with blank cells.

The mandated pattern is a plain `__slots__` class, a `System.Collections.ArrayList`,
and `DataGrid.ItemsSource`, re-assigned via `ItemsSource = None` first to force
row containers to be rebuilt. Confirmed in code: `MultiFilterParameter` (1,257
lines) and `AutoLevel` contain **no** `ObservableCollection`, no INPC, no
`DataContext`. Every dynamic row is built imperatively.

§13.4 marks these enforcement rules PR-blocking, and `tests/test_autolevel_ui.py`
statically asserts that every `{Binding}` path has a matching `__slots__` entry.

**Fix:** delete `viewmodels.py` from the module list. Replace with
`preview_items.py` — `__slots__` row objects, an `ArrayList` refresh function.

### 2.2 The engine's stdlib is stripped — `csv` and `re` are missing

§12.9.3, confirmed by a code comment in `MultiFilterParameter/script.py`
("no `re` module in this engine"), which hand-rolls a numeric extractor.

- "Export Formats: CSV" needs a hand-rolled writer. `Export Schedule.pushbutton`
  already has `_parse_tsv_row()` to copy.
- Any mark/level pattern matching must be written without `re`.
- Given `openpyxl` is vendored and the audience is Excel-first, **XLSX should be
  the default report format**, not TXT.

### 2.3 Module placement is unspecified, and the repo has a strong convention

Revit-free logic goes in `anongee_toolkit/` so it can be unit-tested from the
repo root (`python -m unittest discover -s tests`); Revit-touching and UI code
stays in the `.pushbutton` folder (BBS Generator's `core/ / output/ / ui/ /
standards/` layout). Proposed split:

    anongee_toolkit/rc_automation/        # no Revit imports — unit-testable
        models.py  excel_engine.py  matching_rules.py  reporting_engine.py

    RCAutomation.pushbutton/              # Revit + WPF
        script.py  ui.xaml
        creation_engine.py  preview_engine.py
        external_events.py  preview_items.py

### 2.4 Two Excel paths exist; the spec does not choose

`anongee_toolkit/io/excel.py` is a COM **writer** (needs Excel installed).
Vendored `openpyxl` reads and writes with no Excel dependency and is already used
by Export Schedule and BBS Generator. **Use openpyxl for reading.** Two caveats
to validate for: `openpyxl` cannot open legacy `.xls`, and with
`data_only=True` a formula cell returns `None` unless Excel itself last saved the
file — a schedule full of formulas written by a non-Excel tool reads as empty.
Both must be caught by the validation engine with a clear message, not a
traceback.

---

## 3. The Excel format is the biggest problem — and it is structural, not cosmetic

The spec's own reviewer noted the format "lacks data for real world examples".
It is worse than incomplete: as specified, **it cannot place an element**, and its
uniqueness rule contradicts how schedules are actually written.

### 3.1 There are no coordinates. Anywhere.

`FOOTINGS` is Mark, Length, Width, Depth, Level, Offset, Cover. `COLUMNS` is
Mark, Width, Depth, Height, BaseLevel, TopLevel. No X, no Y, no rotation, no grid
reference.

Revit cannot create a `Floor` or a `FamilyInstance` without a location.
Therefore, exactly as written:

- **Creation Mode 3 (Full Creation) is impossible.**
- **Creation Mode 2 (Create Missing) is impossible for the "missing" half.**
- **Creation Mode 1 (Rebar Only) is fine** — the host already exists and supplies
  the geometry.

### 3.2 "No Duplicate Marks" is the wrong rule for a real schedule

A footing schedule row `F1 — 3000×3000×900, cover 50` describes a **type** that
appears forty times on the plan. It is not one instance. Revit's `Mark` is an
instance parameter, non-unique by design, and frequently blank. Enforcing
uniqueness on Mark forces the user to write forty near-identical rows and breaks
the moment two footings legitimately share a type.

### 3.3 Both problems have one fix: split type from placement

This is the single largest recommended change. It resolves §3.1 and §3.2 at once
and matches how engineers actually issue schedules.

```
SHEET: FOOTING_TYPES        one row per footing TYPE
    TypeMark   Length  Width  Thickness  CoverTop  CoverBottom  CoverSide  Concrete

SHEET: FOOTING_PLACEMENT    one row per INSTANCE
    Mark  TypeMark  GridX  GridY  [X]  [Y]  Level  TopOffset  Rotation

SHEET: COLUMN_TYPES
    TypeMark  Width  Depth  Cover  Concrete

SHEET: COLUMN_PLACEMENT
    Mark  TypeMark  GridX  GridY  [X]  [Y]  BaseLevel  BaseOffset  TopLevel  TopOffset  Rotation
```

`GridX`/`GridY` name grid lines ("A", "3") and the tool intersects them — that is
how the position appears on a real drawing. `X`/`Y` in millimetres are the
fallback when a project is not on a regular grid; one pair or the other is
required, and the validation engine says which is missing. Note this also gives
the matching engine a much stronger key than Mark alone: grid intersection +
level is genuinely unique.

`cad2bim/builders/columns.py` already duplicates a `FamilySymbol` per distinct
size and names it via `cad2bim/naming.py` ("300 x 900"). `TypeMark` should feed
that same convention rather than inventing a second one.

### 3.4 Other schema defects

| Field | Problem | Fix |
| --- | --- | --- |
| Footing `Depth` | Means *thickness*; `COLUMNS.Depth` means cross-section *h*. Same word, two meanings, one workbook. | Rename to `Thickness` on footings. |
| Footing `Offset` | Meaningless until §4.1 is decided — a foundation slab offsets *above* its level, a footing family hangs *below* it. | Decide the element type first. |
| Footing `Cover` | One number. Real footings have distinct top / bottom / side cover, and Revit stores cover as a **`RebarCoverType` element reference**, not a number — the tool must resolve or create a matching cover type. | Three columns; add a cover-type resolution step. |
| Column `Height` **and** `BaseLevel`/`TopLevel` | Contradictory. `builders/columns.py` states outright: "HEIGHT comes from the chosen base/top levels". | Drop `Height`; add `BaseOffset` / `TopOffset`. |
| Column cover | Footings have a `Cover` column; columns have none. | Add it. |
| Level names | Matched by string. Real models use "Level 1" / "L1" / "GF" / "+0.000". No mapping step exists. | Add an explicit **Level Mapping** section to the UI (Excel name → Revit `Level`). This is the number-one real-world failure mode. |
| Units | Never stated. The toolkit is millimetre-native (`FT_TO_MM`, `mm_to_internal`). | Pin to **mm**, assert it in a header cell, reject anything else. |

### 3.5 `FOOTING_REBAR` cannot build a real bar

Required columns are FootingMark, Layer, Diameter, Spacing, Direction. Missing:

- **`BarType`** — Revit needs a `RebarBarType` element. Projects name them "16",
  "T16", "#5", "Ø16". The spec says "Must use valid RebarBarType" but provides no
  column and no mapping UI to get there.
- **`Count` and `LayoutRule`** — Revit's layout rules are Single, FixedNumber,
  MaximumSpacing, NumberWithSpacing, MinimumClearSpacing. Spacing alone maps to
  MaximumSpacing, which silently recomputes the count. A real schedule says
  "12 T16 @ 200 c/c B1" — count *and* spacing.
- **Hooks / shape code** — a footing bottom bar has 90° end hooks in nearly every
  detail. No `HookType`, `HookOrientation`, or `ShapeCode`. BBS Generator already
  speaks BS 8666 shape codes; the sheet should too, or the two tools disagree.
- **`Direction` is free text.** Needs a controlled vocabulary. And layer order is
  geometric: B1 sits one bar diameter below B2, so the z-offsets differ.

### 3.6 `COLUMN_REBAR` is under-determined

Required columns are ColumnMark, MainBarDiameter, MainBarCount, TieDiameter,
TieSpacing.

- **`MainBarCount` alone does not define an arrangement.** Eight bars in a
  300×600 column can be laid out several ways. Revit will not infer it — every
  bar's position must be computed. Real schedules give two bar sets
  ("4T20 corners + 6T16 faces"), which needs two rows per column, not one.
- **No lap / splice / starter-bar data.** A column main bar physically starts as a
  starter out of the footing and laps above floor level. Without it the tool
  produces bars that float, disconnected — wrong in the model and wrong in the BBS.
- **A single `TieSpacing` produces non-code-compliant reinforcement.** Confinement
  zones (closer tie spacing over `lo` at each end) are mandatory under IS 13920,
  ACI 318 Ch. 18 and EC8 alike. Needs `TieSpacingEnd`, `TieSpacingMid`,
  `ConfinementLength`. An engineer will reject the output otherwise.
- **No cross-tie / link configuration** beyond a single perimeter tie.

---

## 4. Technical verdicts: possible, hard, impossible

### 4.1 Footings: the repo builds them as floors, the spec implies families

`cad2bim/builders/footings.py` uses `Floor.Create` against a Structural
Foundation `FloorType`, deliberately, and says why in its docstring: a sketched
outline the user can edit, sitting *on* the level, "where a foundation FAMILY
hangs its own depth below the level it is hosted on".

But an isolated pad from a schedule with Length × Width × Depth is naturally a
`FamilyInstance` — `NewFamilyInstance(point, symbol, level, StructuralType.Footing)`
on `M_Footing-Rectangular`.

These are different elements with different depth semantics, different `Offset`
meaning, and different rebar-hosting behaviour. **This must be decided before any
code is written**, because rebar hosting depends on it. Recommendation: family
instances for RC Automation (a schedule describes discrete pads), and leave the
cad2bim floor approach alone rather than trying to unify them.

### 4.2 "Temporary graphics" for model preview is not achievable as written

> MODEL PREVIEW — Use temporary graphics. DO NOT create permanent elements.

Revit's API has no mechanism for drawing arbitrary temporary 3D geometry:

| Mechanism | Why it fails here |
| --- | --- |
| `TemporaryGraphicsManager` | Accepts only `InCanvasControlData` — a 2D bitmap pinned at a point. Cannot draw a 3000×3000×900 box. |
| Analysis Visualisation Framework (`SpatialFieldManager`) | Draws shaded result surfaces. Creates a real element, needs a Transaction and an AVF-enabled view, and is a poor fit for outlines. |
| `DirectShape` | Works and is easy — but is a **permanent element** requiring a Transaction, so it violates the spec's own constraint and lands in undo history. |
| `View.SetElementOverrides` | Genuinely temporary and free — but colours **existing** elements only. Useless for CREATE rows, where nothing exists to colour. |

Confirmed: the repo has no temporary-graphics code at all. The only related use
is `OverrideGraphicSettings` in `cad2bim/builders/view_filters.py`.

**Workable alternative — split the preview by match status:**

- FOUND / CONFLICT → `OverrideGraphicSettings` in the active view (green/orange),
  plus `uidoc.ShowElements`. Truly temporary, instant, no document change.
- CREATE → either `DirectShape` in a dedicated "RC Preview" subcategory, created
  in a named transaction and removed by one "Clear Preview" transaction (honest
  about being a document change), **or** no 3D preview in the MVP at all — the
  grid plus a highlighted grid intersection is enough to review against.

The four-colour scheme in the spec survives either way; only the mechanism changes.

### 4.3 The performance target fights the External Event model

"500+ footings, 500+ columns, without UI freezing, allow cancellation."

All Revit work runs inside `IExternalEventHandler.Execute()` on Revit's main
thread. The WPF window lives on another thread so it keeps repainting — but
**Revit itself is frozen for the whole batch**, and a transaction cannot be
cancelled part-way and left half-applied. The repo's own `ui/pump.py` warns that
pumping at Input priority inside a transaction risks a reentrant API call.

Achievable version: chunk the work into repeated external-event round trips
(≈25 elements per raise), each its own `Transaction`, all inside one
`TransactionGroup`, with a cancel flag checked *between* chunks. Progress and
cancellation then become truthful.

**Element-count warning the spec misses.** 500 footings + 500 columns with rebar,
modelled one `Rebar` per bar, is 50,000+ elements — at roughly 10–50 ms per
`Rebar.CreateFromCurves`, that is 8–40 minutes and a model that is painful to
open. Use **rebar sets**: one `Rebar` element with a `NumberWithSpacing` layout
represents thirty bars. That turns ~50,000 elements into ~2,000, and it is also
how a detailer expects to see it. Also default `SetSolidInView(false)` and leave
unobscured display off.

### 4.4 "Never crash Revit" is not a testable criterion

The repo's own §12.9.1 says so directly: a genuine engine crash is a
`System.AccessViolationException` / Corrupted-State Exception that **bypasses
every managed handler** — no `except Exception`, no `try/finally`. Reword the
Definition of Done to something falsifiable: "no unhandled exception reaches the
user; every transaction is rolled back or assimilated; no orphaned transaction
survives a failure".

### 4.5 Verdict table

| Spec item | Verdict |
| --- | --- |
| Modeless window + External Event | **Possible** — reference implementation exists, copy it |
| Excel load + validate (openpyxl) | **Possible** |
| Preview grid (`__slots__` + ArrayList) | **Possible** — not as MVVM |
| Matching modes 1–4 | **Possible**; Mode 1 (Mark) is weak — see §3.2 |
| Conflict detection | **Possible**; needs a rounding tolerance the spec omits |
| Create footings | **Possible only after §3.3** — no coordinates today |
| Create columns | **Possible only after §3.3**; drop `Height` |
| Footing rebar | **Hard, greenfield** — needs cover types, hooks, layer offsets, bar types |
| Column rebar | **Hard, greenfield** — arrangement, laps and confinement are all undefined |
| Temporary-graphics 3D preview | **Not achievable as written** — see §4.2 |
| Creation Mode 1 (Rebar Only) | **Possible today** — the highest-value, lowest-risk slice |
| Creation Modes 2 and 3 | **Blocked** on the schema redesign |
| 500+ elements, no freeze, cancellable | **Partly** — chunked, cancellable between chunks; Revit still blocks |
| CSV export | **Possible** — hand-rolled; `csv` is missing from the engine |
| "Never crash Revit" | **Not testable** — reword |

---

## 5. Gaps the spec never mentions

1. **Undo.** One "Create" click should be one undo step — wrap everything in a
   `TransactionGroup` and `Assimilate()`. Not mentioned anywhere.
2. **Worksharing.** Element ownership, "cannot edit — owned by another user",
   borrowing. A showstopper on any live project; absent from the spec.
3. **Failure handling.** Revit warning dialogs will interrupt a 500-element batch.
   The repo already has `cad2bim/builders/txn_failures.py` (`WarningSwallower`,
   an `IFailuresPreprocessor`) — reuse it, and note it needs the same
   `__namespace__` / no-`__init__` / once-per-session treatment as the event handler.
4. **Idempotency.** Running the tool twice on the same workbook must not duplicate
   everything. Needs a "created by RC Automation" stamp (shared parameter or a
   Comments convention) and a re-run policy.
5. **Conflict tolerance.** 3000 mm vs 3000.4 mm is not a conflict. Needs a
   configurable tolerance; the toolkit already rounds to the nearest millimetre
   via `revit/units.clean_ft`.
6. **Type-not-found policy.** The spec says "Assign Type" but never says what
   happens when it does not exist. `cad2bim` duplicates and names per size —
   follow that.
7. **Delivery gate.** `tests/test_repo_docs.py` **will fail** until the new
   pushbutton is documented in `README.md`, recorded in `CHANGELOG.md`, and its
   panel declared in `extension.json`. Plan for it rather than discovering it in CI.
8. **Ribbon placement.** Unspecified. `Core.panel/BIM.stack` sits with cad2bim and
   BIM Generation; `Dev.panel` is where unproven tools live first.

---

## 6. Recommended scope, re-cut

The MVP as written is six engines, full rebar generation, live 3D preview and a
500-element performance target. That is three or four releases, not an MVP. A
phasing that ships value early and defers everything blocked on a decision:

**P0 — Rebar Only on existing elements.** Excel load, validation, matching,
preview grid, level and bar-type mapping, footing + column rebar onto hosts that
already exist. Needs no coordinates, so it is unblocked by §3.3. Ships the
round trip with BBS Generator, which is the strongest reason to build any of this.

**P1 — Create missing structure.** Footings and columns, after the type/placement
schema lands and the footing element type is chosen.

**P2 — Preview graphics and conflict resolution UI.** Overrides for existing,
`DirectShape` (or nothing) for new.

**P3 — Scale.** Chunked execution, cancellation, rebar sets, 500+ elements.

---

## 7. Decisions taken

Settled 2026-08-18. These supersede the corresponding parts of the spec.

| # | Decision | Consequence |
| --- | --- | --- |
| 1 | **Excel schema splits type from placement** (§3.3). | One `*_REBAR` row can drive every instance of a type. Placement sheets are defined in the template now but only consumed from P1. |
| 2 | **Three phases, in order: new model + new rebar, then existing model + new rebar, then existing model + existing rebar.** *(Revised 2026-08-18: the first cut put rebar-only first to dodge the missing coordinates. The schema split in decision 1 supplies them, so creating everything leads instead — it is the pitch, and it is what an empty model needs.)* | The placement sheets are required in phase 1 and ignored in the other two, so requiredness follows the mode rather than the release. |
| 3 | **Footings are `Floor.Create` on a Structural Foundation `FloorType`** — chosen so an arbitrary outline can be footed, not just a rectangle. `cad2bim` is *not* imported; anything reusable is written fresh into `anongee_toolkit`. | `Thickness` is the floor's compound-structure thickness; the pad sits **on** its level. The host must have `FLOOR_PARAM_IS_STRUCTURAL` set or it is not a legal rebar host — validation must check this and say so. |
| 4 | **Preview = overrides for existing + `DirectShape` for new.** | Green/orange via `OverrideGraphicSettings`; blue CREATE volumes as `DirectShape` in an "RC Preview" subcategory, wiped by one Clear transaction. |
| 5 | **BS 8666:2020 leads.** | Hooks, bend radii and cutting lengths come from `BBS Generator/standards/BS_8666_2020.py`. Its `SHAPE_MAP` covers codes 00, 11, 12, 13, 14, 15, 21, 31, 32, 41, 51, 60, 77. |
| 6 | **Bar types are mapped in the UI; unmapped is an error.** | A Bar Type Mapping section pairs each workbook diameter with a `RebarBarType` from the model, auto-matching on name. No silent type creation. |
| 7 | **Host key is a user-selected parameter, defaulting to `Mark`, with `Level` as tie-breaker.** | Folds the spec's Matching Modes 1, 3 and 4 into one mechanism. Choosing `Type Mark` makes one workbook row drive all instances of that type. |
| 8 | **Anything that already exists is compared with the schedule field by field, and the user picks which side wins — Excel by default.** | Statuses: `CREATE`, `MATCHED`, `DIFFERS`, `INVALID`. A differing row shows both values and resolves to the workbook unless the user flips it to the model, per row; the tool records whether a row was decided or merely defaulted. This makes it a **checker** as well as a generator. |

### Decided without asking

**Rebar sets, not one element per bar.** A single `Rebar` with
`SetLayoutAsNumberWithSpacing` (or `SetLayoutAsMaximumSpacing` when only spacing
is given) represents a whole layer, turning ~50,000 elements into ~2,000 at the
500-element target (§4.3). Verified compatible with the existing BBS: 
`core/rebar_reader.py:241` reads `BuiltInParameter.REBAR_ELEM_QUANTITY_OF_BARS`,
which reports a set's bar count correctly.

| 9 | **A geometric difference on an existing element is resolved by what depends on it: nothing depends on it → edit the sketch in place; something does → create the corrected element, move the dependents across, retire the old one last, never delete first; neither is safe → report only.** Report-only is in force for the whole of this release. | Recorded in `reconcile.py` beside the code that will implement it, guarded by `GEOMETRY_CHANGES_ARE_DEFERRED`, and pinned by tests on both sides of the switch. Revit has no re-host, so "move the dependents across" means capture → recreate → verify, and whatever cannot be captured faithfully falls to report-only rather than being guessed. |

### Still open

**Ribbon placement.** `Dev.panel` matches the README's convention for a tool that
has not yet proven itself; `Core.panel/BIM.stack` is where it belongs once it has.

The build plan is in
[`2026-08-18-rc-automation-build-plan.md`](2026-08-18-rc-automation-build-plan.md).

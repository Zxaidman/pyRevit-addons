# Convert Slab — v1.4.1

pyRevit pushbutton. Converts **Structural Floor ↔ Structural Foundation (slab)**
on a pre-selection or an interactive pick, in plan, 3D, section or elevation.

Engine: **CPython 3** (`#! python3`). Revit **2022+**, developed against 2025.

---

## Install

```
AnonGee.extension/
  lib/
    path_resolver.py             <- yours; injects py3 or py2 by engine
    py3/
      anongee_toolkit/
        ui/
          progressbar.py         <- new
          hostwnd.py             <- new
          pump.py                <- new
          theme.py               <- new
          checklist.py           <- new
          dialogs.py forms.py xaml.py __init__.py   <- yours, untouched
  MyTab.tab/
    Structure.panel/
      Convert Slab.pushbutton/
        script.py
        bundle.yaml
        slab_convert_config.json
```

pyRevit puts each extension's `lib` folder on `sys.path`, so `import cpyforms`
works from every button in the extension. The script also appends its own folder
to `sys.path`, so dropping `cpyforms.py` next to `script.py` works as a fallback.

Then pyRevit → Reload.

---

## Why it recreates instead of retyping

Floors are `OST_Floors`, foundation slabs are `OST_StructuralFoundation`. Different
categories, so neither the Type Selector nor `Element.ChangeTypeId` will cross over.
The only route is: read everything → create the counterpart → replay → delete the
original. That means **the ElementId changes**, and everything bound to the old id
is at risk. The tool's job is to tell you exactly what that costs *before* it acts.

## Run order

1. Reads the pre-selection, or prompts you to pick (filtered to slabs).
2. Builds a plan per element: resolved target type, what survives, what doesn't.
3. Shows the checklist — untick anything you don't want, blocked rows come pre-unticked.
4. Choose **Convert** or **Report only**.
5. One `TransactionGroup`, one `Transaction` per element, so a single failure
   rolls back that element only and the rest of the batch continues.
6. Prints a result table with a geometry delta per element.

## What survives

| | |
|---|---|
| Sketch boundary + sketched openings | rebuilt loop-by-loop from `Sketch.Profile`, curves re-ordered head-to-tail so arcs and mixed loops don't break |
| Level + Height Offset From Level | copied explicitly, then verified against the bounding box |
| Slope arrow | passed to the `Floor.Create` slope overload, then the Slope parameter is cross-checked |
| Slab shape edits | vertex offsets matched by XY, added points via `DrawPoint`, creases via `DrawSplitLine` |
| Structural flag, phase, workset, pin state | explicit |
| All writable instance + shared parameters | matched by BuiltInParameter → shared GUID → name; anything without a counterpart in the target category is listed by name in the report |
| Geometry joins **and join order** | recorded before deletion, re-joined after, `SwitchJoinOrder` applied to restore cutting priority |
| Hosted reinforcement | `Rebar.SetHostId` onto the new slab *before* the original is deleted |
| `Opening` elements | boundary curves recreated on the new slab |

## What is lost (reported per element, you confirm)

Tags · dimensions · face-hosted family instances · parts · slab edges ·
analytical associations · the ElementId itself.

## Blocked (never attempted)

- Element inside a multi-instance or nested model group (see Model groups)
- Element inside an assembly
- Element in a design option that isn't the active one — activate it and rerun
- No editable sketch, or a non-horizontal sketch
- Target category has zero types to seed from (create one Foundation Slab type first)
- Isolated footings and wall foundations — those are `FamilyInstance` / `WallFoundation`,
  not sketch-based slabs, and are out of scope

## Type resolution

`type_name_mode: "same"` (default) — the target type carries the **source type
name verbatim**. If a type of that name already exists in the target category it
is reused; otherwise it is created by duplicating a seed type of that category
and applying the source's compound structure (same thickness, same materials).

There is deliberately no thickness or structure fallback in this mode: silently
matching an existing type under a *different* name is exactly what 1:1 naming
exists to prevent.

Floors and Foundation Slabs are separate system families, so both can hold a
type of the same name without collision — uniqueness is checked **within the
target category only**.

`type_name_mode: "convention"` restores the older behaviour: prefix/suffix
rewriting, then identical-compound-structure, then thickness within
`thickness_tolerance_mm`, then create.

## Model groups

There is no API to edit a group definition in place, so the only route is
ungroup → convert → regroup. The run becomes three phases inside one
`TransactionGroup`: ungroup every affected group, convert, then rebuild each
group from its recorded members with converted ids substituted in. Phase three
runs even if the conversion was cancelled or elements failed — leaving the model
ungrouped would be worse than a partial conversion.

| Group | Behaviour |
|---|---|
| **One placed instance** | Clean round-trip. Members, name and pin state restored; the orphaned GroupType is removed so the original name can be reclaimed. |
| **Several instances** | **Blocked by default.** Ungrouping one instance leaves the others full of floors, and regrouping makes a *new* type — the group type splits. Set `groups.multi_instance: "split"` to accept that; each affected element is flagged in the pre-flight list. |
| **Nested** | Blocked. Ungroup manually first. |

Attached detail groups do not survive ungrouping and are reported per group.
Set `groups.enabled: false` to go back to skipping grouped elements entirely.

## Verification

Every converted element reports `area / volume / z` delta against the original.
Anything over 0.1 % area or 0.1 mm in Z is flagged `GEOMETRY DELTA — verify manually`.
That's the regression check — it should read as zeros.

---

### 1.4.1
- Dropped the `lib/cpyforms.py` and `lib/netclass.py` fallback imports; the
  toolkit package is the only source now.
- Toolkit import failures are recorded and reported at the top of the run
  output instead of silently degrading to no progress bar.

### 1.4.0
- Type naming is now 1:1 with the source type name (`type_name_mode: "same"`).
- Fixed: the new-type uniqueness check scanned every `FloorType` in the model
  rather than the target category, so 1:1 naming would have produced
  `FLR_200 THK RCC SLAB 2` — the source floor type already held the name.
- Model group support via ungroup → convert → regroup, single-instance groups
  round-tripping cleanly and multi-instance blocked by default.
- Requires the ui modules at 1.6.0.

### 1.3.0
- Message boxes now go through `anongee_toolkit.ui.forms.alert`. That takes
  `(title, message)` — the reverse of `pyrevit.forms.alert` — so all call sites
  go through a local `notify()` wrapper rather than calling it directly.
- Added an explicit Yes/No gate (`forms.confirm`) naming every element whose
  dependents will be destroyed, shown after the checklist and before the first
  transaction opens.
- The duplicate-.NET-type guard is inlined here instead of living in
  `anongee_toolkit.revit`, which is left untouched.
- All Revit-API helpers stay local to this button by design.
- Requires the ui modules at 1.5.0.

### 1.2.0
- Imports repointed at the real package layout: `anongee_toolkit.ui` (not `ui1`).
- Imports target submodules directly rather than package `__init__`, so the
  button runs before you have edited `ui/__init__.py`.

### 1.1.1
- Imports now go through the extension's `path_resolver` instead of walking up
  the folder tree to find `lib/py3`.
- Requires `anongee_toolkit >= 1.3.1`.

### 1.1.0
- Moved the shared modules into `lib/py3/anongee_toolkit/ui1/`; imports now come
  from `anongee_toolkit.ui1`, with the old flat imports kept as a fallback.
- Progress titles reworded to read like pyRevit's native bar
  (`Converting slabs... 41/117`).
- Requires `anongee_toolkit >= 1.3.0`.

### 1.0.2
- Fixed: `Duplicate type name within an assembly.` on the second run in a Revit
  session. The two classes implementing Revit interfaces (`ISelectionFilter`,
  `IFailuresPreprocessor`) were defined at module level; pythonnet emits a real
  .NET type for each, and pyRevit re-executes the script module on every click,
  so the second run tried to emit the same type names again. Both are now built
  through `netclass.define`, which emits once per session.
- Requires `netclass >= 1.0.0` (a self-contained fallback is inlined, so the
  button still runs if the lib file is missing).
- `cpyforms >= 1.2.0` for the pyRevit-style progress strip.

### 1.0.1
- Fixed: crashed on the CPython engine with
  `"pyrevit.forms.ProgressBar" is not currently supported under CPython`.
- All three XAML-backed dialogs (`ProgressBar`, `SelectFromList`,
  `CommandSwitchWindow`) now route through `cpyforms`, with the pyRevit versions
  kept as a fallback so the button still runs under IronPython.
- Requires `cpyforms >= 1.1.0`.

### 1.0.0
- Initial release: bidirectional conversion, pre-flight confirmation list,
  dry-run mode, type auto-resolution + creation, join/rebar/opening preservation,
  geometry verification.

# Convert Slab — v1.0.1

pyRevit pushbutton. Converts **Structural Floor ↔ Structural Foundation (slab)**
on a pre-selection or an interactive pick, in plan, 3D, section or elevation.

Engine: **CPython 3** (`#! python3` shebang). Revit **2022+**, developed against 2025.

---

## Install

```
MyTools.extension/
  lib/
    cpyforms.py                  <- reusable, shared by all your CPython scripts
  MyTab.tab/
    Structure.panel/
      Convert Slab.pushbutton/
        script.py
        bundle.yaml
        slab_convert_config.json
```

Then pyRevit → Reload.

`lib/` is automatically on `sys.path` for every script in the extension, so any
other `#! python3` button can just `from cpyforms import ProgressBar`. If you'd
rather not touch `lib/`, dropping `cpyforms.py` next to `script.py` also works —
the script appends its own folder to `sys.path`.

### Why cpyforms exists

`pyrevit.forms.ProgressBar`, `SelectFromList` and `CommandSwitchWindow` are built
with `wpf.LoadComponent`, which is IronPython-only; under the CPython engine they
raise `PyRevitCPythonNotSupported`. `cpyforms.py` builds the same three widgets in
code instead of XAML, with a call-compatible API:

```python
from cpyforms import ProgressBar, CheckList, pick_option

with ProgressBar(title='Working {value}/{max_value}  {percent}%',
                 cancellable=True) as pb:
    for i, item in enumerate(items):
        if pb.cancelled:
            break
        pb.update_progress(i + 1, len(items))
        pb.status = item.name          # optional second line

# or just wrap the loop
for item in ProgressBar.track(items, title='Working {value}/{max_value}'):
    ...

picked = CheckList.show(rows, title='Pick', name_attr='name',
                        checked_predicate=lambda r: r.ok)
answer = pick_option(['Run', 'Dry run'], message='Ready.')
```

Title placeholders: `{value}` `{max_value}` `{percent}` `{eta}`.

One detail worth knowing: repainting a window from the Revit UI thread means
pumping the WPF dispatcher, and pumping at Input priority inside an open
transaction lets keystrokes reach Revit and can cause a reentrant API call.
`cpyforms.pump()` therefore defaults to `DispatcherPriority.Render`, which
flushes layout and render but stops short of the Input queue. `forms.alert` is
left alone throughout — it wraps Revit's own `TaskDialog` and is already
CPython-safe.

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
3. Shows the checklist — untick anything you don't want, blocked rows are dropped.
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

- Element inside a model group or assembly
- Element in a design option that isn't the active one — activate it and rerun
- No editable sketch, or a non-horizontal sketch
- Target category has zero types to seed from (create one Foundation Slab type first)
- Isolated footings and wall foundations — those are `FamilyInstance` / `WallFoundation`,
  not sketch-based slabs, and are out of scope

## Type resolution

Configured in `slab_convert_config.json` (auto-created next to the script if missing):

1. Exact name match against the naming convention (`FLR_Slab 200` → `FND_Slab 200`)
2. Identical compound structure (layer widths, materials, functions)
3. Same total thickness within `thickness_tolerance_mm`
4. Otherwise duplicate a seed type of the target category and apply the source's
   compound structure — same thickness and materials, named by the convention

Set `require_identical_layers: true` to forbid step 3, or `create_missing_types: false`
to block instead of creating.

## Verification

Every converted element reports `area / volume / z` delta against the original.
Anything over 0.1 % area or 0.1 mm in Z is flagged `GEOMETRY DELTA — verify manually`.
That's the regression check — it should read as zeros.

---

## Changelog

### 1.0.1
- Fix: `pyrevit.forms.ProgressBar` raised `PyRevitCPythonNotSupported` on the
  CPython engine. All three IronPython-only dialogs now route through
  `cpyforms` (new, `lib/cpyforms.py` v1.0.0), with the pyRevit versions kept as
  a fallback and a silent no-op progress bar as a last resort — the button can't
  die on a UI import again.
- The progress window now opens before the `TransactionGroup` rather than inside
  it, so the initial dispatcher pump happens with no transaction open.
- Rollback guarded with `HasStarted()` / `HasEnded()` so a failure inside
  `convert_one` can't raise a second time on the rollback itself.

### 1.0.0
- Initial release: bidirectional conversion, pre-flight confirmation list,
  dry-run mode, type auto-resolution + creation, join/rebar/opening preservation,
  geometry verification.

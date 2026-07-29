# Convert Slab — v1.0.0

pyRevit pushbutton. Converts **Structural Floor ↔ Structural Foundation (slab)**
on a pre-selection or an interactive pick, in plan, 3D, section or elevation.

Engine: **CPython 3** (`#! python3` shebang). Revit **2022+**, developed against 2025.

---

## Install

Drop the whole `Convert Slab.pushbutton` folder into a panel of your extension:

```
MyTools.extension/
  MyTab.tab/
    Structure.panel/
      Convert Slab.pushbutton/
        script.py
        bundle.yaml
        slab_convert_config.json
```

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

### 1.0.0
- Initial release: bidirectional conversion, pre-flight confirmation list,
  dry-run mode, type auto-resolution + creation, join/rebar/opening preservation,
  geometry verification.

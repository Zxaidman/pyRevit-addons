# Revit API research — reinforcement

Findings from the Revit 2025/2026 API reference, gathered after a real run
reported:

```
Constrained rebar isn't a free form rebar element. Parameter name: handle
   at Autodesk.Revit.DB.Structure.RebarConstraint.Create(
      RebarConstrainedHandle handle, IList`1 targetReferences,
      Boolean isConstraintToCover, Double offsetValue)
```

That message is the whole story: **`RebarConstraint.Create` is for free-form
rebar only.** Every bar RC Automation places is shape-driven, so the call could
never have worked, and the constraint code written for it was aimed at the wrong
half of the API. What follows is what the documentation actually says, and what
of it is worth using.

Sources:
[RebarConstraintsManager](https://www.revitapidocs.com/2026/32fe1ec6-ddb3-feac-f18c-8683b054f639.htm) ·
[RebarConstraint members](https://www.revitapidocs.com/2023/3a2afe27-b578-5d23-611e-ceb2be08c0b4.htm) ·
[RebarShapeDrivenAccessor](https://rvtdocs.com/2025/6d2f77e7-bbe2-5bd5-723a-bf27c3df1a65) ·
[RebarConstrainedHandle](https://www.revitapidocs.com/2025/08b4c4a3-3bb9-0801-9cc8-cd5420a306d9.htm) ·
[Revit API Developers Guide — Rebar](https://help.autodesk.com/view/RVT/2025/ENU/?guid=Revit_API_Revit_API_Developers_Guide_Discipline_Specific_Functionality_Structural_Engineering_Structural_Model_Elements_Reinforcement_Rebar_html)

---

## 1. Shape-driven and free-form are two different APIs

Almost every confusing thing about rebar constraints comes from this split.

| | Shape-driven (what we create) | Free-form |
| --- | --- | --- |
| Created by | `Rebar.CreateFromCurves` / `CreateFromRebarShape` | `Rebar.CreateFreeForm` |
| Constraints are | **chosen from candidates Revit offers** | **constructed** with `RebarConstraint.Create` |
| `GetConstraintCandidatesForHandle` | returns the possibilities | returns an **empty list** |
| "current" vs "preferred" | different things — preferred overrides Revit's default pick | the same thing |

So for our bars the sequence is *ask, then pick* — never *build*:

```python
manager = rebar.GetRebarConstraintsManager()
for handle in manager.GetAllHandles():
    for candidate in manager.GetConstraintCandidatesForHandle(handle, host.Id):
        if candidate.IsToCover():
            manager.SetPreferredConstraint(candidate)
            break
manager.ApplyRebarConstraints()
```

`SetPreferredConstraint` takes **the constraint alone** — it already knows its
handle. The earlier code passed `(handle, constraint)`, which is the free-form
signature.

### `RebarConstraintsManager` — the useful members

| Member | Why it matters |
| --- | --- |
| `GetAllHandles()` | every handle on the bar — ends, plane, faces |
| `GetAllConstrainedHandles()` | only the ones already tied to something |
| `GetConstraintCandidatesForHandle(handle, ElementId)` | **the one to use** — everything on that host the handle could be tied to |
| `GetConstraintCandidatesForHandle(handle, Reference)` | narrower: candidates against one face |
| `GetCurrentConstraintOnHandle(handle)` | what is acting now |
| `GetPreferredConstraintOnHandle(handle)` | what we asked for |
| `SetPreferredConstraint(constraint)` | override Revit's default pick |
| `SetPreferredConstraintsToSurfaceForHandles(...)` | bulk form, worth trying for a whole face |
| `RemovePreferredConstraintFromHandle(handle)` | back to Revit's own choice |
| `ApplyRebarConstraints()` | commit the picks |
| `HasValidRebar()` | the bar survived whatever else happened |
| `HighlightHandleConstraintPairInAllViews(...)` | **diagnostic gold** — shows on screen what a handle is tied to |

### `RebarConstraint` — how to recognise the right candidate

| Member | Use |
| --- | --- |
| `IsToCover()` | **the test that matters** — this candidate follows the cover, not a bare face |
| `IsToHostFaceOrCover()` / `IsFixedDistanceToHostFace()` | the weaker alternatives |
| `GetTargetCoverType()` | which `RebarCoverType` it follows — lets us verify we tied to the cover we set |
| `GetTargetElement()` | confirm it is our footing and not a neighbour |
| `GetRebarConstraintTargetHostFaceType()` | Top / Bottom / Side, so ends and plane can be told apart |
| `SetDistanceToTargetCover(d)` | an offset from the cover, for a layer that sits behind another |
| `GetConstraintType()` | the enum, for reporting |
| `IsValid()` | before relying on any of it |

---

## 2. Varying-length sets are a property, not a method

The ribbon's **Varying Rebar Set** — "allows varying lengths of individual bars
within a host … will snap to the host cover in both variable distribution
applications and skewed orientations" — is one flag:

```python
accessor = rebar.GetShapeDrivenAccessor()
accessor.UseRebarConstraintsToProduceVaryingBars = True
```

It only does anything once the handles are constrained, which is why it belongs
*after* the constraint step. The name says it: the constraints produce the
variation.

### `RebarShapeDrivenAccessor` — the rest of it

| Member | Note |
| --- | --- |
| `UseRebarConstraintsToProduceVaryingBars` | the varying-set flag |
| `SetLayoutAsMaximumSpacing(spacing, arrayLength, barsOnNormalSide, includeFirst, includeLast)` | what the manual workflow uses — Revit fills the span |
| `SetLayoutAsNumberWithSpacing(count, spacing, …)` | when the schedule states both |
| `SetLayoutAsFixedNumber(count, arrayLength, …)` | count only |
| `SetLayoutAsMinimumClearSpacing(spacing, arrayLength, …)` | clear distance rather than centres — closer to how detailers think |
| `SetLayoutAsSingle()` | one bar |
| `ArrayLength` | the distribution length — **readable after constraining**, which is how to check Revit filled what we expected |
| `Normal`, `BarsOnNormalSide` | the plane, and which side bars sit |
| `GetDistributionPath()` → `Line` | where the set actually runs; a good assertion |
| `GetBarPositionTransform(i)` | where bar *i* ended up — the way to verify a varying set from code |
| `ComputeDrivingCurves()` | the curves Revit derived, versus the ones we handed it |
| `ScaleToBox(origin, xVec, yVec)` | fit a shape to a box |
| `FlipRebarSet()` | when the normal came out backwards |

`GetBarPositionTransform` and `ArrayLength` together are how a run can *check
itself* after writing, instead of trusting that a set landed correctly.

---

## 3. The manual workflow, mapped to the API

The sequence a detailer follows by hand, and what each step is in code:

| # | By hand | In the API |
| --- | --- | --- |
| 1 | Sketch the foundation to the schedule | `Floor.Create(doc, loops, typeId, levelId)`, then `FLOOR_PARAM_IS_STRUCTURAL = 1` |
| 2 | Create the cover, apply it to the footing | `RebarCoverType.Create(doc, name, distance)`; set `CLEAR_COVER_TOP` / `_BOTTOM` / `_OTHER` |
| 3 | Model the bar in section, constrain each face to its cover line | `CreateFromCurves`, then candidates → `IsToCover()` → `SetPreferredConstraint` |
| 4 | Set the set to maximum spacing; Revit fills the span cover to cover | `SetLayoutAsMaximumSpacing`; `ArrayLength` reads back what it filled |
| 5 | Turn on obscured rebar in all views | `SetSolidInView(view, True)` / `SetUnobscuredInView(view, True)` per view |

Step 4 is the one that changes our design: **once the ends are constrained to
cover, Revit derives the length.** We currently compute every bar's extent
ourselves by intersecting the outline. That still matters for planning and for
the bending schedule, but the model should be told the constraint and allowed to
do its own arithmetic — that is what makes the bars follow a later edit.

---

## 4. One set per distribution region

From the ribbon help and the manual workflow: a varying set covers **one**
region of varying depth. A pad that tapers one way and is orthogonal elsewhere
needs a set per region — varying **on** for the tapered one, **off** for the
orthogonal ones — not one set spanning both.

Consequence for `rebar_spec`: a layer is not always one distribution. Where the
scan extents change along the run, the layer has to be cut into regions of
constant behaviour, each becoming its own set. This is the largest outstanding
change and is not yet implemented.

---

## 5. Other API worth having in the toolkit

Found while reading, useful beyond the immediate bugs:

| API | What it would give us |
| --- | --- |
| `RebarHostData.GetCoverType(face)` / `SetCoverType` | read and set cover **through the host** rather than by hunting built-in parameters per category — one call that works for floors, walls and family instances alike |
| `RebarHostData.GetRebarsInHost()` | already used; also the way to find what a re-run must leave alone |
| `Rebar.GetShapeDrivenAccessor().GetBarPositionTransform(i)` | verify placement after writing |
| `RebarBarType.GetBendData()` / `RebarBendData` | bend radii and hook geometry **from the model**, instead of recomputing BS 8666 ourselves — worth reconciling against `standards/BS_8666_2020.py` |
| `RebarShape` + `RebarShapeDefinitionBySegments` | define a shape once and place by shape rather than by curves; the BBS reads shape codes off the shape element, so this is how a placed bar gets the right code without inference |
| `Rebar.CreateFromRebarShape` | placement by shape, which pairs with the above |
| `RebarContainer` | group a footing's bars into one element — fewer things in the browser, and a natural unit for "everything this tool made for F1-A1" |
| `RebarRoundingManager` | project rounding for bar lengths, so our numbers agree with the schedule Revit prints |
| `FabricSheet` / `FabricArea` | mesh reinforcement, for slabs later |
| `RebarUpdateCurvesData` | for free-form bars driven by our own rules — a possible route for genuinely arbitrary pad shapes |
| `Rebar.SetHostId(doc, hostId)` | **exists after all** — worth verifying, because it would change the phase 3 plan, which assumes a bar cannot be re-hosted and has to be recreated |

That last row matters most: the phase 3 note in the feasibility review states
flatly that Revit has no re-host. If `SetHostId` does what it appears to, the
"capture → recreate → verify" dance for dependent rebar can be replaced by
moving the bar, and the reasoning recorded there needs revisiting before phase 3
is built.

---

## 6. What this changes in RC Automation

1. **Constraints**: stop calling `RebarConstraint.Create`; ask for candidates,
   pick `IsToCover()`, `SetPreferredConstraint`, `ApplyRebarConstraints`.
2. **Varying sets**: set `UseRebarConstraintsToProduceVaryingBars` after
   constraining, per distribution region.
3. **Layout**: prefer `SetLayoutAsMaximumSpacing` and let Revit fill between the
   constrained ends, rather than computing the span ourselves.
4. **Cover**: use `RebarHostData` for get/set instead of per-category built-ins.
5. **Regions**: cut a varying layer into one set per region of constant
   behaviour.
6. **Verification**: read `ArrayLength` and `GetBarPositionTransform` back after
   writing, so a run can check itself rather than reporting what it intended.

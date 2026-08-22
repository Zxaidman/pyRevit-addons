# RC Automation — todo list

The queue. Everything that is wanted, wrong, or waiting, in one file, so the state of the tool can
be read without asking anybody.

## How this file works

| § | Section | What belongs in it |
| --- | --- | --- |
| 1 | **Critical** | Blocks the other implementation. Nothing ships until every one is closed or deliberately deferred. |
| 2 | **Errors and bugs** | Something is wrong now. Each carries how it was found and whether it is reproduced. |
| 3 | **Features** | New capability. Each is separable and can be scheduled on its own. |
| 4 | **Working now** | What is built and verified, so nobody rebuilds it and nobody claims more than was measured. |
| 5 | **Pending scope** | Agreed direction, not yet started. |
| 6 | **Owner's list** | Reserved for what the project owner sends next, and everything after. |

**Every entry has an ID** (`CRIT-1`, `BUG-3`, `FEAT-7`) so it can be referred to in one word.

**Every entry carries a phase**, so the state of the queue is readable without asking:

| Phase | Meaning |
| --- | --- |
| `pending` | Not started. |
| `building` | Being written now. |
| `testing` | Built and in a build the project owner can test; waiting for in Revit result. |
| `superseded` | It worked, and something else replaced it. Recorded rather than deleted — what it cost to build is part of the record. |
| `done` | Confirmed on the in Revit, and copied into `done-list.md` with what was done. |

An item leaves this file only by reaching `done`, and it is described in `done-list.md` when it
does. Nothing is deleted to make the list look shorter.

**Anything new is recorded here first.** A requirement, a bug, an idea — it gets an ID in this file
before it is built, argued about, or written into any other document. Standing instruction from the
project owner, and it is what keeps this list the queue rather than a summary of one.

**Verified means one thing here:** the project owner ran it in Revit and the report or the screenshot
says so. A green test suite is not verification — every bug in §2 that reached a model passed the
suite on the way there.

Current build: **0.7.0** (extension 1.8.0), 575 tests green, no in-Revit result yet.

---

## 1. Critical

### CRIT-1 — no constraint has ever been confirmed applied in Revit · `testing`

**Found:** the owner's 0.5.0 report claimed *"66 bar handle(s) tied to the host's cover"* and the
0.6.0 report claimed 78, while the model showed none. Reported twice in the owner's own words —
*"not constraint applied still"* (msg 18), *"varied rebar set constrain is not assign to proper
slope edge"* (msg 19).

**Reproduced:** yes, in two separate runs.

**Cause, found in 0.7.0:** two API mistakes, both visible in the 0.6.0 report. `SetPreferredConstraint`
(the handle-less 2025 form) returned without error and changed nothing, so the counter counted
successes that were not. `ApplyRebarConstraints()` does not exist with no arguments — the report
line *"No method matches given arguments"* was the tool's own call failing, filed as though a
constraint had failed.

**Fix shipped, unconfirmed:** `SetPreferredConstraintForHandle(handle, constraint)`, verified rather
than trusted, with the handle-less form as fallback; no `Apply` call.

**Why critical:** every claim the tool makes about surviving a host edit rests on this, and so does
CRIT-2. Until one report shows a constraint in **Edit Constraints**, the feature is unbuilt.

**How to close:** run 0.7.0, select one footing bar, open Edit Constraints, and say what it shows.
The exported report now names the face each varying set's ends found.

### CRIT-2 — varying rebar sets do not vary · `testing`

**Found:** owner's image 3 (msg 18) and image 1 (msg 19). Bars in a varying region are all the same
length in the model.

**Reproduced:** yes.

**Depends on CRIT-1.** `UseRebarConstraintsToProduceVaryingBars` is set, but the flag does nothing
until the ends are actually constrained — the constraints are what produce the variation.

**Second cause, fixed in 0.7.0 and unconfirmed:** the candidate was chosen as the first that
answered `IsToCover()`, which on a tapered pad is never the sloping edge. Now chosen by smallest
absolute `GetDistanceToTargetCover()`.

**How to close:** F3-P1 in the sample. The gable bars should shorten toward the apex.

### CRIT-3 — column reinforcement is planned, counted, and never placed · `pending`

**Found:** reading the run against its own report. Every run says *"Placing 6 footings and 5
columns"* and every run creates zero columns and zero column bars. `anongee_toolkit/structural/`
has no `columns.py`; `rebar_run` plans footings only.

**Reproduced:** yes, in all three of the owner's reports.

**Why critical:** it is the first line a user reads, and it is wrong. Either the run places them or
the sentence stops claiming it. The honest interim is the second, and the real fix is SCOPE-3.

**Smallest closing move:** make the count sentence say what will actually be built, and add one
Skipped line per column saying columns have no creation path yet. Half an hour, and it stops the
tool lying about its own scope.

---

## 2. Errors and bugs

### BUG-1 — Other Faces took the top face's cover type · `testing`

**Found:** owner's image 2, msg 19 — *"see the Other face is also taking top footing cover which is
not acceptable in BIM Standard."* The footing read `Top Face: FOOTING TOP <50mm>` /
`Bottom: FOOTING BOTTOM <75mm>` / `Other Faces: FOOTING TOP <50mm>`.

**Reproduced:** yes. **Cause:** the cache that stops three identical cover types being created was
keyed on the rounded value alone, so top 50 and side 50 collided.

**Fix shipped, unconfirmed:** cache keyed by `(face, value)`; an existing type has to match the
face's name as well as its distance; the report now names which type landed on which face.

### BUG-2 — bend legs went outside the rebar cover · `testing`

**Found:** owner, msg 19 — *"bend length values are not proper it is going outside of rebar cover."*

**Reproduced:** yes, by arithmetic. A T16 U-bar in a 3000 pad with 50 mm side cover put its bend
corner on the cover plane at ±1450, so the outside of each vertical leg sat at ±1458 — 8 mm past it.

**Fix shipped, unconfirmed:** a bend sits half a diameter inside the cover plane, a straight end on
it. Independent of bend radius. The leg tip now lands on the top cover plane rather than half a bar
under it.

### BUG-3 — a set was told to fill a span its bars did not cover · `testing`

**Found:** the owner's 0.6.0 report, by the tool's own read-back: *"F3 B1X from 3000: asked for a
1200 mm distribution, Revit made it 1000 mm."*

**Reproduced:** yes, off-Revit, from the sample workbook.

**Cause:** the region's length was measured across every position it considered, including one whose
scan line falls outside the pad once side cover comes off and so produces no bar. One phantom
position stretched the distribution by a whole spacing. The read-back was right; the number it
checked was ours.

**Fix shipped, unconfirmed:** measured across the positions that produced a bar.

### BUG-4 — F3 schedules more bars than the pad has room for · `pending`

**Found:** while fixing BUG-3. F3 B1 says 22 bars at 200 mm, which need 4200 mm; the P1 pad offers
4100 mm between its side cover. Revit lays that out past the cover regardless and nothing about the
model looks wrong.

**Reproduced:** yes. 0.7.0 reports the overhang as a plan note; the workbook is still wrong.

**Open question for the owner:** fix the sample workbook, or keep it as the case that demonstrates
the warning? Not fixed either way until that is answered.

### BUG-5 — the tool has no icon of its own · `pending`

**Found:** `icon.png` is byte-identical to `Modeless.pushbutton/icon.png` (md5 `61c3609…`). Two
buttons on the same panel are indistinguishable on the ribbon.

**Reproduced:** yes, trivially.

### BUG-6 — `ID_LIC` may be derived wrongly · `testing`

**Found:** the owner's images 3 and 4 (msg 19) show `ID_LIC = C-1` on the host and `ID_LIC = C1` on
the bar. 0.7.0 writes the grid intersection (`C-1`) to both, on the reasoning that a bar and its
host must not disagree.

**Not reproduced** — it is a question, not a defect, until the owner says which is right. One line
in `rc_automation/identity.py` either way.

### BUG-7 — the sample LEVELS sheet maps to levels the owner's model does not have · `pending`

**Found:** every one of the owner's reports carries two fallback notes — `Foundation` mapped to
`00 Ground Lvl.`, which that model does not have, so matching found `00 FOUNDATION LVL.` instead.

**Reproduced:** yes, three times. The matching is doing exactly what it should; the fixture is
describing a different project. Noise in every report until the fixture is corrected.

### BUG-8 — a U-bar's turned-up legs cross the top mat · `pending`

**Found:** while fixing BUG-2. In F1 the B1 leg tip reaches z = 850 at x = ±1442, and T1 runs to
x = ±1450 at z = 844. The two occupy the same space.

**Reproduced:** yes, off-Revit. 0.7.0 reports it as a plan note and does nothing about it, because
the resolution is a detailing decision — shorten the top mat's end cover, or stop the leg below the
mat. **Needs the owner's rule before it is coded.**

### BUG-9 — the probe describes the first element it finds as though it were the model · `pending`

**Found:** reading `_cover_support` and `_constraint_support`. Both return after the first footing
or bar. In a model where one footing has cover and forty do not, the probe says the model has cover.

**Reproduced:** not yet — it needs a mixed model. Real regardless: the code returns unconditionally.

---

## 3. Features

### FEAT-1 — map an unmapped bar type in the window · `pending`

Recorded decision, msg 3: *"Map in UI, error if unmapped."* Only the error half exists — a run with
an unresolvable bar size stops with a message naming the sizes, and the user has to leave and load
types. The mapping half was specified and never built.

### FEAT-2 — a Key Parameter dropdown · `pending`

Recorded decision, msg 3: *"Mark with Level as tie breaker, but Mark Parameter can change with
user-selected parameter as user could have utilized other parameter."* The handler already reads
`self.data["key_parameter"]` and falls back to `Mark`; **nothing ever sets it**, because there is no
control. The plumbing is done and the control is missing.

### FEAT-3 — accept existing reinforcement as matching · `pending`

Recorded decision, msg 3: *"flag as conflict, skip by default but give user option to delete
existing rebar and replace **or match if already existing ones are right according to excel**."*
Skip is built, Replace is built, accept-as-matching is not. A footing whose steel is already correct
still reads as a conflict every run.

### FEAT-4 — preview before writing · `pending`

`OverrideGraphicSettings` on matched hosts and a `DirectShape` preview of the bars, from the
feasibility decision (msg 2, "Overrides + DirectShape"). Nothing built.

### FEAT-5 — `reporting_engine` · `pending`

Findings out as CSV, JSON and XLSX rather than only the text report. Note the constraint: the
CPython 3 engine ships no `csv` module, so the CSV writer is hand-rolled — same as BBS Generator's.

### FEAT-6 — cancel between chunks · `pending`

A 500-footing run is currently all-or-nothing once Create is pressed. The chunk loop is the natural
place to check a flag.

### FEAT-7 — worksharing checkout · `pending`

`WorksharingUtils.GetCheckoutStatus` before touching an element, so *"owned by somebody else"*
becomes a skip with a name on it rather than a failed chunk.

### FEAT-8 — read `.xls` and `.xlsb` · `pending`

Both are recognised and refused today, with a message saying to save as `.xlsx`. The owner supplied
a real `.xls` (`sample_schedule-R1.xls`) as ground truth, so the fixture for this is already in the
repository.

### FEAT-9 — place by `RebarShape`, not by curves · `pending`

`Rebar.CreateFromCurves` leaves Revit to infer the shape, so the shape code on the placed bar is
whatever it matched — not necessarily the `21` the schedule said. `RebarShapeDefinitionBySegments`
plus `CreateFromRebarShape` puts the scheduled code on the element, which is what BBS Generator
reads. **This is the one that makes the bending schedule agree with the model.**

### FEAT-10 — `RebarContainer` grouping · `pending`

One element per footing's reinforcement. Fewer things in the browser, and a natural unit for
"everything this tool made for F1-A1".

### FEAT-11 — `RebarRoundingManager` · `pending`

Project rounding for bar lengths, so the tool's numbers agree with the schedule Revit prints.

### FEAT-12 — let Revit derive the length from the constraints · `pending`

`SetLayoutAsMaximumSpacing` between two constrained ends, rather than computing the span here. Step
4 of the owner's manual workflow (msg 17). Blocked behind CRIT-1: it is only safe once constraints
are known to apply.

---

## 4. Working now

Built, and confirmed by the project owner in Revit. Described in `done-list.md`.

| ID | What | Confirmed by | Phase | Record |
| --- | --- | --- | --- | --- |
| WORK-1 | Reads a schedule from `.xlsx`, `.xlsm`, a folder of `.csv`/`.txt` sheets, or one file with `#SHEET` rows | owner's screenshot (msg 8) and three run reports | `done` | DONE-1 |
| WORK-2 | Validates the workbook against BS 8666:2020 before any transaction | *"0 errors, 0 warnings, 2 notes"* in the 0.6.0 report | `done` | DONE-2 |
| WORK-3 | Matches schedule level names to the model's, with a `LEVELS` sheet for what matching cannot reach | 0.6.0 report — `Foundation → 00 FOUNDATION LVL.` | `done` | DONE-3 |
| WORK-4 | Resolves a grid crossing to a point | six pads placed, five of them by grid | `done` | DONE-4 |
| WORK-5 | Creates footings as floors flagged structural, from an arbitrary outline | *"Created 6 footing(s)"* | `done` | DONE-5 |
| WORK-6 | Places reinforcement as sets | *"26 set(s) — 317 bar(s)"* | `done` | DONE-6 |
| WORK-7 | Bends bars to their shape code | owner reported the fault at 0.3.x and has not repeated it since 0.4.0 | `done` | DONE-7 |
| WORK-8 | Cuts a layer at the outline's vertices, one set per region | owner, msg 19 — *"now F3 rebar set placement is correct"* | `done` | DONE-8 |
| WORK-9 | Creates cover types and writes them onto the footing | owner, msg 19 — *"now Rebar cover is getting assign properly"* | `done` | DONE-9 |
| WORK-10 | The whole run is one undo step, chunked so one failure does not lose the rest | reported by every run; not independently exercised by the owner | `done` | DONE-10 |
| WORK-11 | Modeless window — Revit stays interactive, requests serialised through one external event | owner's screenshot (msg 8) | `done` | DONE-11 |
| WORK-12 | Exports the findings and the probe as a text report beside the workbook | the three reports in this repository are its output | `done` | DONE-12 |

---

## 5. Pending scope

Agreed direction. Not started, and not scheduled.

### SCOPE-1 — Phase 3, resolving a geometric difference · `pending`

Report-only today, by the owner's decision (msg 6), with the three rules recorded in
`reconcile.py` behind `GEOMETRY_CHANGES_ARE_DEFERRED`:

1. no dependents (rebar, dimension, annotation) → edit the sketch in place;
2. dependents exist → do not delete; create the new element, then re-host each dependent onto it;
3. otherwise → report, take no action.

### SCOPE-2 — verify `Rebar.SetHostId` · `pending`

The feasibility review states flatly that Revit has no re-host, and rule 2 above is built on that.
`Rebar.SetHostId(doc, hostId)` appears to exist. **If it does what it looks like, SCOPE-1's rule 2
is replaced by moving the bar, and the reasoning in the review needs revisiting before anything is
built on it.** One read-only probe answers this.

### SCOPE-3 — create columns · `pending`

`FamilyInstance` between two levels, then the mains and ties that are already planned. Closes CRIT-3
properly.

### SCOPE-4 — laps and starter bars · `pending`

Explicitly out of scope and reported as such per column, so nobody mistakes the output for a
complete cage. Recorded here so the exclusion is a decision rather than an omission.

### SCOPE-5 — fabric reinforcement · `pending`

`FabricSheet` / `FabricArea` for slabs.

### SCOPE-6 — free-form rebar · `pending`

`RebarUpdateCurvesData` for pad shapes that shape-driven bars cannot follow. A different constraint
API from the one this tool uses, which is why it is scope and not a feature.

---

## 6. Owner's list

Reserved for what the project owner sends next, and everything after. Nothing is written here by
anybody else.

> The owner has said a 0.7.0 test found *"few bugs and errors"*, to be reported after this file
> exists. Those become `OWN-1` onward, and anything of theirs that turns out to be critical is
> promoted to §1 with its `OWN-` ID kept as a cross-reference.

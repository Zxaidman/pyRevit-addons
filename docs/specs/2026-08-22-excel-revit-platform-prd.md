# Excel–Revit Platform — product requirements

**Status:** draft for review · **Date:** 2026-08-22 · **Supersedes nothing** — RC Automation
becomes one module of this, not a thing this replaces.

Working name: **AnonGee Bridge**. Provisional.

---

## 1. What is being asked for

One `.xlsm` workbook drives a whole RCC job in Revit. Its first sheet is a control panel: a button
per operation, each sending a command and its data into Revit, where a pyRevit tool reads it and
does the work. The workbook covers the full chain —

> Levels · Grids · Types · Views · Structure Model · Rebar Model · Revit Schedules for quantity
> take-off · Costing · Sheets · Tagging · Shop Drawings

— and before any of it, two templates ship: a `.rvt` Revit template and the `.xlsm` itself, each
carrying what the other end requires.

---

## 2. The honest answer: what is possible

**All of it is possible. None of it is quick, and three of the eleven are much harder than the other
eight.** Nothing on the list is blocked by a missing API. What separates them is how much
*judgement* each needs — and judgement is what takes the versions.

The grading below is against one bar: **the owner opens Revit, presses a button in Excel, and the
model is right without touching it afterwards.**

| # | Capability | What Revit gives you | Realistic verdict |
| --- | --- | --- | --- |
| 1 | **Levels** | `Level.Create(doc, elevation)`, name, level type, story flag | **Straightforward.** Name matching is already built and proven. The only real care is that deleting a level deletes everything hosted on it — so this is sync-and-modify, never delete-and-recreate. |
| 2 | **Grids** | `Grid.Create` (line and arc), `CreateMultiSegment`, per-view extents and bubbles | **Straightforward, with a fiddly tail.** Creating them is an afternoon. Getting bubbles and 3D extents right *per view* is where the time goes. |
| 3 | **Types** | Duplicate a type and set parameters: easy. `doc.LoadFamily` from a library: easy. **Authoring a new family from scratch: a project of its own.** | **Partly.** Duplicate, parameterise and load — yes, and that covers most of a real job. Drawing new families from a spreadsheet — no, and it should not be attempted. The template carries the families. |
| 4 | **Views** | `ViewPlan.Create`, `ViewSection.CreateSection`, `View3D`, duplication, view templates, scope boxes, crop regions, filters | **Yes, medium.** Everything is reachable. The workbook supplies the judgement (which template, which crop, which scope box) so the code does not have to guess. |
| 5 | **Structure Model** | Footings **already done**. Columns and beams: `NewFamilyInstance`. Walls: `Wall.Create`. Slabs: `Floor.Create`, already done | **Yes, staged per element type.** Each element type is its own creation path with its own edge cases — beam joins and cutbacks, sloped and stepped slabs, openings. Add them one at a time, each shipping. |
| 6 | **Rebar Model** | Shape-driven rebar, constraints, varying sets — the subject of `REVIT_API_RESEARCH.md` | **Yes, and it is the slowest item on the list.** Footings alone have taken seven versions and their constraints are still unconfirmed in a model. Beams, columns and walls each need their own layout engine on top. Plan in quarters, not weeks. |
| 7 | **Schedules for QTO** | `ViewSchedule.CreateSchedule`, `AddField`, filters, sorting, grouping, formatting, `ScheduleSheetInstance` | **Yes — and the easiest win on the list.** Highly API-friendly, no geometry, no judgement calls. Worth doing early for the morale and for the feedback loop it gives every other item. |
| 8 | **Costing** | Not a Revit problem. Rate × quantity | **Yes, by not doing it in Revit.** Revit's calculated-value expressions are weak, and a rate library belongs in a spreadsheet where a QS can see it. Quantities come *out* of Revit, costing happens in Excel. Anything else fights the tool. |
| 9 | **Sheets** | `ViewSheet.Create`, `Viewport.Create`, sheet parameters, schedule instances | **Yes, medium.** Placing a viewport where you want it is arithmetic, not research. |
| 10 | **Tagging** | `IndependentTag.Create` | **Partly, and the gap matters.** Tagging *everything* is a morning's work. Tagging so that nothing overlaps, leaders read sensibly and the drawing is issuable is genuinely hard — it is where every auto-tagging tool on the market underdelivers. Expect "tags placed, then adjusted by hand", improving over releases. |
| 11 | **Shop Drawings** | The union of 4, 5, 6, 7, 9, 10 **plus dimensioning** | **The hardest thing on the list, by a distance.** `Dimension.Create` needs stable geometric `Reference`s, and obtaining them for rebar and for element faces is fragile and moves between Revit versions. Realistic target: the sheet, the views, the crops, the schedules and most tags placed automatically; dimensions and final annotation by hand at first. |

### Three things that are *not* possible, stated plainly

1. **A `.rvt` file cannot be authored outside Revit.** No library writes one. The template has to be
   produced by a Revit session — see §5.
2. **A working `.xlsm` cannot be generated from nothing.** `openpyxl` can *preserve* an existing
   VBA project but cannot create one. One manual step in Excel, once — see §5.
3. **Revit cannot be driven while it is busy.** The API runs on Revit's UI thread and only when
   Revit is idle with no modal dialog open. An Excel button is therefore *queue a job*, never
   *remote-control the application*. This shapes the whole architecture and is not negotiable.

---

## 3. What the workbook actually is

Not a form. A **project database with a dispatcher on the front**.

| Sheet | Holds |
| --- | --- |
| `CONTROL` | The panel. One row per operation: button, mode, dry-run toggle, last-run status, last-run time, findings count. |
| `INFO` | Project, units, standard, template paths. Already built. |
| `LEVELS` `GRIDS` | Datum. |
| `TYPES` | Which family types the job uses, and their parameters. |
| `VIEWS` `SHEETS` | What drawings exist and what goes on them. |
| `FOOTING_*` `COLUMN_*` `BEAM_*` `WALL_*` `SLAB_*` | Structure: one type sheet and one placement sheet each, the pattern already proven. |
| `*_REBAR` | Reinforcement per element type. |
| `SCHEDULES` | Which Revit schedules to build, with fields, filters and sorting. |
| `RATES` | The cost library. Excel's job, not Revit's. |
| `QTO` | Quantities written back out of Revit. |
| `LOG` | Every job: id, command, when, what happened, how many findings. Append-only. |

The control panel is the only sheet with macros. Everything else is a table.

---

## 4. Non-negotiables

Carried forward from RC Automation because each was learned the hard way.

1. **Nothing is written until the user says so.** Every command has a dry run that reports exactly
   what a real run would do.
2. **One undo step per job.** A `TransactionGroup` the tool owns, chunked so one failure does not
   lose the run, assimilated so Ctrl+Z reverses all of it.
3. **Sync, never create-blindly.** Every command matches first, then creates, modifies, skips or
   reports. Pressing the button twice must not build the job twice.
4. **The workbook wins by default, and the user can say otherwise.** Already the reconcile rule.
5. **Every finding names its cell.** Sheet, row, column — so a problem can be typed into Excel's
   Name Box.
6. **Never delete what the tool did not create.** Every element carries its identity fields and a
   job stamp.
7. **The report is the witness.** Two of the last three bugs were found by reading a report against
   a model, not by anyone testing anything.

---

## 5. The two templates

### `template.rvt`

**Cannot be generated here.** The deliverable is two things:

1. **A written specification** of what the template must contain: the families the workbook can
   name, the view templates, the title blocks, the shared parameter file bound to the right
   categories, the object styles, the schedule templates, the filters.
2. **A pyRevit tool, `Build Template`**, that runs *inside Revit* against an out-of-the-box template
   and produces the rest — binding parameters, creating view templates, loading families from a
   named folder. The owner runs it once and does a Save As.

Everything the tool needs from the template can be checked before a run, and the probe already does
this for levels, bar types and cover types. That check becomes the template's acceptance test.

### `template.xlsm`

**One manual step, once.** `openpyxl` writes sheets, tables, named ranges, data validation and
formatting, and preserves an existing `vbaProject.bin` with `keep_vba=True` — but it cannot create
one. So:

1. The VBA lives in the repository as `.bas` source, reviewable in a diff like everything else.
2. The owner creates a blank `.xlsm` once and imports the modules.
3. From then on, a build script regenerates every sheet into it and the macros survive.

The VBA itself is small — perhaps 200 lines. It posts a job, polls for the result, and writes the
log. It does not contain business logic, and it must not: anything it knows is a thing that has to
be kept in step with Python.

---

## 6. Staging

Each stage ends with something the owner can use. Nothing is started until the stage before it is
confirmed in a model.

| Stage | What ships | Why here |
| --- | --- | --- |
| **0 · Bridge spike** | One command — `ping`. Excel button → Revit → a result row in `LOG`. Nothing else. | If the transport does not work, nothing above it matters. Two days, and it de-risks the entire programme. |
| **1 · Datum** | `template.rvt` spec + `Build Template`; `template.xlsm`; `levels.sync`; `grids.sync` | First real value: open a blank model, press two buttons, get a co-ordinated datum. Also proves the envelope against two genuinely different commands. |
| **2 · Setup** | `types.sync`, `views.sync`, `sheets.sync` | The half of a project that is tedious and entirely mechanical. High value per line of code. |
| **3 · Structure** | `columns.sync`, `beams.sync`, `walls.sync`, `slabs.sync`; footings fold in from RC Automation | The model itself. One element type at a time, each shipping. |
| **4 · Numbers** | `schedules.sync`, QTO write-back to the workbook, costing in Excel | Closes the loop back to the spreadsheet. Cheap, and it makes every earlier stage measurable. |
| **5 · Reinforcement** | RC Automation grows up: beams, columns, walls | The deep one. Deliberately after the loop is closed, so its output can be measured. |
| **6 · Drawings** | `tags.sync`, shop drawing assembly, and an MCP layer over the same commands | The hardest, and it needs everything below it to exist first. |

RC Automation's own open items (`AnonGee.extension/AnonGee.tab/Dev.panel/RC Automation.pushbutton/todo-list.md`)
run alongside stage 0–1 and fold into stage 5.

---

## 7. Should this be C#?

**No — not now, and the reasons are specific rather than sentimental.**

| For C# | Against, in this project |
| --- | --- |
| Real tooling, real debugger, real WPF | The whole toolkit is Python and works. A rewrite buys a debugger and costs the programme. |
| No pythonnet marshalling traps | Those traps are already found, written down in the brand guidelines, and covered by tests. |
| Ships as a `.addin` without pyRevit | True, and it matters *if this is ever sold*. It is not a reason to rewrite before stage 1. |
| Faster on very large models | Unmeasured. Measure before believing it. |

**pyRevit already provides the one thing C# was going to be needed for** — a server inside Revit
that receives commands from outside (§ architecture). That was the strongest argument for a C#
add-in, and it is answered.

**Two conditions would change this answer**, and both should be checked rather than assumed:

1. The tool has to run on a machine where pyRevit cannot be installed.
2. A stage-3 or stage-5 run on a real project model is measurably too slow, *after* profiling.

If either lands, the right move is a **small** C# add-in that hosts the listener and the hot loops
and calls into nothing else — not a second implementation of the toolkit in a second repository.

---

## 8. What success looks like

Stage 1, verbatim, because a vague target cannot be missed:

> Open Revit on a blank model made from `template.rvt`. Open `Project.xlsm`. Press **Create
> Levels**. Within ten seconds the `LOG` sheet gains a row saying how many levels were created,
> modified and left alone, and the model has them. Press it again: the log says every level matched
> and nothing changed. Change one elevation in the sheet and press it again: the log names that one
> level and the model moves it.

Idempotence is the acceptance test, not creation. Anything can create. Only a tool that can be run
twice is a tool anybody trusts with a live model.

# AnonGee Bridge — todo list

The programme queue: one `.xlsm` driving a whole RCC job in Revit. See
[`docs/specs/2026-08-22-excel-revit-platform-prd.md`](docs/specs/2026-08-22-excel-revit-platform-prd.md)
for what is being built and how much of it is realistic, and
[`…-architecture.md`](docs/specs/2026-08-22-excel-revit-platform-architecture.md) for how a button in
Excel becomes a transaction in Revit.

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

### Two queues, and which is which

| File | Scope |
| --- | --- |
| **this file** | The programme — the bridge, the templates, and every command from `levels.sync` to shop drawings. |
| `AnonGee.extension/AnonGee.tab/Dev.panel/RC Automation.pushbutton/todo-list.md` | RC Automation only. It becomes a module of this programme; its queue stays where the tool is. |

**An ID is unique within its file.** A reference across files is written in full —
*RC Automation · BUG-4*. Same rules, same phases, both files.

**Verified means one thing in both:** the project owner ran it in Revit and said so. A green test
suite is not verification — every bug this repository has shipped passed the suite on the way to a
model.

---

## 1. Critical

### CRIT-1 — the Excel → Revit round trip is unproven · `testing`

**Every estimate in the PRD is conditional on this, and nothing above it starts until it answers.**

pyRevit ships an HTTP server that runs inside the Revit process on `localhost:48884`, and a route
handler that declares `uiapp`, `uidoc` or `doc` is executed as an External Event — which is exactly
the marshalling problem the modeless window already solves by hand. On paper it is the whole
transport. It has never been run on the owner's machine.

**Built and waiting on a Revit run** (extension 1.9.0). Three pieces, and the running instructions
are in [`bridge/README.md`](bridge/README.md):

| | |
| --- | --- |
| `AnonGee.extension/startup.py` | Two routes. `/anongee/ping` takes **no** Revit argument and answers even while Revit is busy; `/anongee/status` declares `uiapp`, so pyRevit runs it as an External Event. |
| **Bridge Check** pushbutton | Calls the same two URLs from inside Revit, so when Excel gets no answer the network is out of the question. |
| `bridge/excel/modAnonGeeBridge.bas` | The Excel end. Import once, `Alt+F8`, run. |

**Two routes rather than one, deliberately.** If ping answers and status hangs, the server is fine
and the marshalling is not. One route cannot tell you that, and the difference is a day.

**What it settles:** the server starts; the port is reachable from Excel; a handler declaring
`uiapp` really is marshalled; and — the answer that matters most — **which Python engine runs a
pyRevit startup script, and whether it can see the toolkit**. `/ping` reports `engine.version`,
`engine.implementation` and `toolkit.importable`. pyRevit's core engine is IronPython and the
toolkit is CPython 3 in `lib/py3`; if those do not meet, commands have to be dispatched to a CPython
script rather than handled in the route, and that is a fork in the architecture far better known now
than during stage 1.

**To close it:** run the four steps in `bridge/README.md` and push both raw responses. Also try it
with no document open, and with a modal dialog up — the second is the one a real user hits first.

**If it fails**, the file drop (CRIT-3) becomes the primary transport and the programme continues —
slower at the edge, identical everywhere else. Which is the reason for two transports behind one
envelope.

**Known unknowns to answer in the same spike:** the server is off by default and enabled in pyRevit
Settings — confirm where; confirm whether a second Revit session takes a second port; confirm the
behaviour when no document is open and when a modal dialog is up.

### CRIT-2 — neither template exists, and neither can be generated from here · `pending`

**`template.rvt`.** No library outside Revit writes a `.rvt`. The deliverable is a written
specification of what it must contain — families, view templates, title blocks, the shared parameter
file bound to the right categories, object styles, filters — plus a pyRevit tool, **Build Template**,
that runs *inside* Revit against an out-of-the-box template and produces the rest. The owner runs it
once and does a Save As.

**`template.xlsm`.** `openpyxl` preserves an existing `vbaProject.bin` with `keep_vba=True` and
cannot create one. So the VBA lives in the repository as `.bas` source, reviewable in a diff; the
owner imports it into a blank `.xlsm` **once**; from then on a build script regenerates every sheet
into it and the macros survive.

Both are one manual step each, once. Neither is a limitation that can be coded around, and pretending
otherwise wastes a session.

### CRIT-3 — one envelope, two transports, one registry · `pending`

If the HTTP route and the pushbutton do not call the same handler through the same envelope, every
command gets two implementations and one of them is always behind. The symptom is a button that
works in Revit and not from Excel, and it is unfixable once there are twelve commands.

Build `anongee_toolkit/bridge/` — `envelope.py`, `registry.py`, `jobs.py`, `filedrop.py` — before
the first command, not after the third. `envelope.py` and `registry.py` have no Revit in them and
are unit-testable here.

**A command is declared once, in `registry.py`**, with its name, handler, sheet and whether it
writes. Nothing hard-codes a command name anywhere else.

---

## 2. Errors and bugs

Nothing here yet — the programme has shipped nothing to be wrong. `CRIT-1` is built but unrun, so
anything it turns up lands here with an ID rather than being fixed in passing.

Nine open bugs live in *RC Automation · §2*, and two of them (`CRIT-1`, `CRIT-2` there — constraints
never confirmed applied, varying sets not varying) are the deepest technical risk in the whole
programme, because stage 5 is built on them.

---

## 3. Features

Each carries the verdict from the PRD, so the queue and the estimate cannot drift apart.

### The workbook and the bridge

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-1 | `CONTROL` sheet — a button per operation, with mode, dry-run, last-run status and findings count | Straightforward | `pending` |
| FEAT-2 | VBA: post a job, poll for the result, write the `LOG` row, colour the source rows | Straightforward — and it must stay small. Anything it knows has to be kept in step with Python. **VBA has no JSON parser**, so one has to be written; the spike module ships a deliberately-named `JsonValue` that is *not* one, so nobody mistakes it for the real thing | `pending` |
| FEAT-3 | **Build Template** pyRevit tool, and the written `.rvt` specification | Medium. The specification is the harder half | `pending` |
| FEAT-4 | `template.xlsm` build script — sheets, tables, named ranges, validation, `keep_vba=True` | Straightforward | `pending` |

### Datum and setup

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-5 | `levels.sync` | **Straightforward.** Matching already built and proven. Sync-and-modify only — deleting a level deletes everything hosted on it | `pending` |
| FEAT-6 | `grids.sync` | **Straightforward, with a fiddly tail.** Creating them is an afternoon; per-view bubbles and 3D extents are where the time goes | `pending` |
| FEAT-7 | `types.sync` — duplicate, parameterise, load from a library | **Partly possible, and the boundary matters.** Duplicating and loading covers most of a real job. **Authoring a family from a spreadsheet is not on the table** — the template carries the families | `pending` |
| FEAT-8 | `views.sync` — plans, sections, 3D, templates, scope boxes, crops, filters | **Yes, medium.** The workbook supplies the judgement so the code does not guess | `pending` |
| FEAT-9 | `sheets.sync` — sheets, viewports, title block parameters | **Yes, medium.** Placing a viewport is arithmetic, not research | `pending` |

### Structure

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-10 | `columns.sync` — `NewFamilyInstance` between two levels | Straightforward. Closes *RC Automation · CRIT-3*, where every run claims to place columns and places none | `pending` |
| FEAT-11 | `beams.sync` | Medium. Creation is easy; joins and cutbacks are fiddly | `pending` |
| FEAT-12 | `walls.sync` | Medium | `pending` |
| FEAT-13 | `slabs.sync` — the footing path generalised | Straightforward. `Floor.Create` from an outline already ships | `pending` |

### Numbers

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-14 | `schedules.sync` — build Revit schedules with fields, filters, sorting, formatting | **The easiest win on the list.** No geometry, no judgement. Worth doing early for the feedback loop it gives everything else | `pending` |
| FEAT-15 | QTO write-back — Revit writes `qto.json`, the macro loads it into the `QTO` sheet | Straightforward. **Revit must never write into the open `.xlsm`** | `pending` |
| FEAT-16 | Costing — rates and totals in Excel, quantities from Revit | **Yes, by not doing it in Revit.** Calculated-value expressions are weak and a rate library belongs where a QS can see it | `pending` |

### Reinforcement, drawings, and after

| ID | What | Verdict | Phase |
| --- | --- | --- | --- |
| FEAT-17 | Rebar beyond footings — beams, columns, walls | **Yes, and the slowest item in the programme.** Footings alone have taken seven versions and their constraints are still unconfirmed. Each element type needs its own layout engine. Quarters, not weeks | `pending` |
| FEAT-18 | `tags.sync` | **Partly, and the gap matters.** Tagging everything is a morning. Tagging so nothing overlaps and the drawing is issuable is where every auto-tagging tool underdelivers. Expect placed-then-adjusted, improving per release | `pending` |
| FEAT-19 | Shop drawing assembly | **The hardest thing on the list, by a distance.** `Dimension.Create` needs stable geometric `Reference`s, and getting them for rebar and element faces is fragile and moves between Revit versions. Realistic first target: sheets, views, crops, schedules and most tags automatic; dimensions by hand | `pending` |
| FEAT-20 | MCP layer over the same `/anongee/jobs` endpoints | Straightforward **because it is deliberately last.** A solved shape — `revit-mcp-python` is a FastMCP server forwarding to pyRevit Routes. Costs nothing today beyond keeping the command surface small and named | `pending` |

---

## 4. Working now

What the programme inherits, already confirmed in Revit. Described in *RC Automation · done-list.md*.

| ID | What | Why it matters here | Phase |
| --- | --- | --- | --- |
| WORK-1 | The pure / Revit split — `rc_automation/` has no Revit in it and carries 575 tests; `structural/` touches Revit and is checked statically | **The reason this programme is affordable.** Every new command follows the same seam: parse and plan in the pure half, write in the Revit half | `done` |
| WORK-2 | External-event marshalling with a FIFO queue, proven in a modeless window | The bridge reuses it rather than inventing a second one. It is the answer to the constraint everything else is built around | `done` |
| WORK-3 | A workbook reader across six formats | The envelope carries *which sheet*, not the data, because this exists | `done` |
| WORK-4 | Validation that names the cell it came from | The finding shape the result envelope uses unchanged | `done` |
| WORK-5 | One undo step per run — chunked, assimilated | Extends to every command with no change | `done` |
| WORK-6 | Identity fields on everything built, plus never deleting what the tool did not create | Extends to every element type with no change | `done` |
| WORK-7 | A text report as the tool's only witness | Two of the last three bugs were found by reading one against a model | `done` |

---

## 5. Pending scope

### SCOPE-1 — the staging, in order · `pending`

Each stage ends with something the owner can use. Nothing starts until the stage before it is
confirmed in a model.

| Stage | Ships | Items |
| --- | --- | --- |
| 0 · Bridge spike | `ping` and `status`, end to end | CRIT-1 `testing` · CRIT-3 |
| 1 · Datum | Both templates; levels; grids | CRIT-2, FEAT-1..6 |
| 2 · Setup | Types, views, sheets | FEAT-7, 8, 9 |
| 3 · Structure | Columns, beams, walls, slabs | FEAT-10..13 |
| 4 · Numbers | Schedules, QTO, costing | FEAT-14, 15, 16 |
| 5 · Reinforcement | RC Automation grows up | FEAT-17, and RC Automation's own queue |
| 6 · Drawings | Tags, shop drawings, MCP | FEAT-18, 19, 20 |

### SCOPE-2 — C#, and the two conditions that would change the answer · `pending`

**Recommendation: no, and not now.** The toolkit is Python and works; the pythonnet traps are found,
written down and covered by tests; and **pyRevit already provides the one thing a C# add-in was
going to be needed for** — a server inside Revit that receives commands from outside. That was the
strongest argument for C#, and CRIT-1 answers it.

Two conditions would change this, and both should be **checked rather than assumed**:

1. The tool has to run somewhere pyRevit cannot be installed — which matters if this is ever sold.
2. A stage-3 or stage-5 run on a real project model is measurably too slow, *after profiling*.

If either lands, the move is a **small** C# add-in hosting the listener and the hot loops — not a
second implementation of the toolkit in a second repository.

### SCOPE-3 — round-trip conflict rules beyond the workbook · `pending`

Stage 4 sends numbers back from the model. The reconcile rule (workbook wins by default, the user
can say otherwise) covers a disagreement about an input. It does not yet say what happens when the
model has elements the workbook has never heard of, which is the normal state of a live project.

### SCOPE-4 — multi-user and worksharing · `pending`

Two people with the same workbook open, or one central model. `WorksharingUtils.GetCheckoutStatus`
is already queued as *RC Automation · FEAT-7*; the workbook-level version of the question — who owns
the sheet — has not been asked.

---

## 6. Owner's list

Reserved for what the project owner sends next, and everything after. Nothing is written here by
anybody else.

> **Settled.** Check `CRIT-1` first, then build the `.xlsm` control sheet and the templates.
> Both templates minimal and datum-only. The owner has an existing project `.rvt` and will describe
> it, with what needs adding — so `CRIT-2`'s template specification waits for that rather than being
> guessed at, and `FEAT-3` starts from a real template instead of an out-of-the-box one.
>
> **Waiting on:** the `CRIT-1` run (`bridge/README.md`), and the RC Automation 0.7.0 bugs the owner
> found but has not sent.

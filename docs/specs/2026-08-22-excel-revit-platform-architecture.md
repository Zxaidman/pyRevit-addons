# Excel–Revit Platform — architecture

**Status:** draft for review · **Date:** 2026-08-22 · Companion to
`2026-08-22-excel-revit-platform-prd.md`.

This document answers one question: **how does a button in Excel become a transaction in Revit, and
what happens when that goes wrong.** Everything else follows from it.

---

## 1. The constraint everything is built around

**The Revit API runs on Revit's UI thread, and only when Revit is idle with no modal dialog open.**

A request arriving from outside cannot execute where it lands. It has to be handed to Revit and
picked up when Revit is ready. That is not a limitation to work around — it is the shape of the
system, and pretending otherwise is what produces tools that hang Excel and corrupt models.

Three consequences, all load-bearing:

1. **An Excel button queues a job. It does not control Revit.** The user may be mid-sketch, in a
   dialog, or in another document. The job waits.
2. **The call must be asynchronous.** A synchronous HTTP call that waits for a 5,000-element run
   will time out and leave Excel hung with the job still running. Post, get an id back, poll.
3. **The marshalling is already built.** RC Automation's `IExternalEventHandler` with its FIFO
   queue is exactly this mechanism, working, in production. The bridge reuses it rather than
   inventing a second one.

---

## 2. Transport: two of them, one envelope

### Primary — pyRevit Routes

pyRevit ships an HTTP server that runs **inside the Revit process**, on `localhost:48884`. Routes
are registered in an extension's `startup.py`:

```python
from pyrevit import routes
api = routes.API("anongee")

@api.route("/jobs", methods=["POST"])
def submit(request, doc):        # naming `doc` is what makes it run as an External Event
    ...
```

**A handler that declares `uiapp`, `uidoc` or `doc` is executed by pyRevit as an External Event** —
which is the whole reason this is the right transport rather than a clever one. The threading
problem in §1 is solved by the framework, the same way the modeless window solves it today.

Excel reaches it with `MSXML2.XMLHTTP` or `WinHttp.WinHttpRequest.5.1`. No add-in, no COM, no
registry.

**Verify before building on it** (`SPIKE-1` in the queue): the server is off by default and is
enabled in pyRevit Settings. Confirm on the owner's machine that it starts, that the port is
reachable from Excel, and that a handler declaring `doc` really is marshalled. Half a day. **No
stage-1 work starts until this is confirmed.**

### Fallback — file drop

```
<workbook folder>/.anongee/
    outbox/  <jobId>.job.json        Excel writes, Revit reads
    inbox/   <jobId>.result.json     Revit writes, Excel reads
```

Not a lesser option — a **required** one, for four reasons that will each happen:

- Routes has to be enabled on every machine, and somebody will not have done it.
- It is localhost-only; some corporate builds block local listeners.
- If Revit is not running there is nothing to receive the post.
- A job can be prepared on one machine and run on another.

Degraded behaviour is the behaviour RC Automation already has: the user presses the button in the
Revit window instead. That is not a failure mode, it is the current product.

### Why one envelope matters

**The HTTP route and the pushbutton call the same handler with the same envelope.** The transport
is a detail at the edge; the command registry, the job store and every handler are transport-blind.
Get this wrong and there are two implementations of every command, one of which is always behind.

```
Excel button ─┬─ HTTP POST ──────────► routes/startup.py ─┐
              └─ writes .job.json ───► filedrop poller ───┤
                                                          ├─► bridge.registry
Revit window ─── pushbutton ──────────────────────────────┘         │
                                                                    ▼
                                            command handler ─► toolkit ─► Revit
                                                                    │
                                                      result.json ◄─┘
```

---

## 3. The envelope

Versioned from day one, because the workbook and the tool will be on different versions in the
field the first week.

```json
{
  "envelope": "1.0",
  "jobId": "20260822-140311-0007",
  "command": "levels.sync",
  "workbook": "C:/Jobs/Riverside/Riverside.xlsm",
  "sheet": "LEVELS",
  "options": { "dryRun": true, "onConflict": "workbook", "keyParameter": "Mark" }
}
```

### The data is not in the envelope, and that is deliberate

The envelope says **which sheet and what to do**. Revit opens the workbook and reads it.

| Reason | |
| --- | --- |
| The reader exists | Six formats, tested, in `rc_automation/excel_engine.py`. Putting rows in JSON means a second reader that will disagree with the first. |
| One source of truth | A payload can say one thing while the saved sheet says another. Whoever debugs that loses a day. |
| Size | 5,000 placement rows through an HTTP body is silly. |
| Excel's VBA stays small | It marshals nothing. It cannot get the data model wrong because it never holds it. |

**The exception:** the workbook must be **saved** before a job is posted. The VBA does that, and
the handler reports plainly if the file on disk is older than the job.

### The result

```json
{
  "envelope": "1.0",
  "jobId": "20260822-140311-0007",
  "status": "done",
  "started": "2026-08-22T14:03:11Z",
  "finished": "2026-08-22T14:03:19Z",
  "summary": { "created": 4, "modified": 1, "matched": 7, "skipped": 0 },
  "findings": [
    { "severity": "Warning", "sheet": "LEVELS", "row": 12, "column": "Elevation",
      "message": "…" }
  ]
}
```

`findings` is the shape `rc_automation.models.Issue` already has. `status` is one of `queued`,
`running`, `done`, `failed`, `rejected`.

---

## 4. Job lifecycle

```
Excel                          Revit
  │ save workbook
  │ POST /jobs ────────────────►  validate envelope
  │ ◄──────── 202 {jobId}         queue on the external event
  │                               ├─ read workbook
  │ GET /jobs/<id>  (poll)        ├─ plan (match / create / modify / skip)
  │ ◄──────── running             ├─ dry run? write result, stop
  │                               ├─ TransactionGroup, chunked
  │ GET /jobs/<id>                └─ assimilate → one undo step
  │ ◄──────── done + summary      write <jobId>.result.json
  │ write LOG row, colour rows
```

**Revit never writes into the `.xlsm`.** Excel has it open and locked, and a tool that fights that
lock loses. Revit writes a JSON file; the VBA reads it and writes the sheet. QTO write-back (stage 4)
works the same way — Revit produces `qto.json`, the macro loads it.

**Polling, not callbacks.** Excel cannot host a listener without a great deal of unpleasantness.
Poll every 500 ms, give up after a configurable timeout, and leave the job running — a timed-out
poll is Excel's problem, not the job's, and the result file will be there when it finishes.

---

## 5. Every command is a sync

There is no `create` command. `levels.sync` means:

1. **Read** the sheet.
2. **Validate** it — errors block, warnings do not. Nothing is opened yet.
3. **Match** what the model already has, on the key parameter.
4. **Plan** each row: create · modify · matched · skip · invalid, each with a reason.
5. **Report** — and stop here if `dryRun`.
6. **Act**, in one `TransactionGroup`, chunked, assimilated.
7. **Verify** — read back what was built and report the difference, not the intention.

Steps 1–5 open no transaction and can be run against a live model at any time. **This is the whole
safety story**, and it is the pattern already shipping.

Step 7 is not optional. RC Automation's read-back is what caught a distribution the tool asked for
wrongly; without it the run would have reported success.

---

## 6. Module map

New packages beside the existing ones. Nothing existing moves.

```
AnonGee.extension/
  startup.py                          NEW — registers the HTTP routes. Thin.
  lib/py3/anongee_toolkit/
    bridge/                           NEW — transport-agnostic, mostly pure
      envelope.py    command + result schema, versioned, no Revit
      registry.py    command name → handler; the one place a command is declared
      jobs.py        job store, status, result files
      filedrop.py    outbox/inbox polling
      excel_out.py   JSON for the workbook to read back (QTO, logs)
    datum/                            NEW
      levels.py      grows out of structural/levels.py, which reads only today
      grids.py       grows out of structural/grids.py
    viewsheets/                       NEW
      views.py  sheets.py  schedules.py  tags.py
    rc_automation/                    EXISTS — pure workbook layer, no Revit
      grows to parse every sheet, not just the six it reads now
    structural/                       EXISTS — the Revit writers
      grows: columns.py  beams.py  walls.py  slabs.py
```

**The existing split holds and is the reason this is affordable.** `rc_automation/` has no Revit in
it and is unit-tested on any machine — 575 tests today. `structural/` touches Revit and is checked
statically. Every new command follows the same seam: parsing and planning in the pure half, writing
in the Revit half.

### One rule for the registry

A command is declared **once**, in `registry.py`, with its name, its handler, the sheet it reads and
whether it writes. The HTTP route, the file-drop poller and the pushbutton all read that registry.
Nothing hard-codes a command name anywhere else — the alternative is three lists that drift, and
the symptom is a button that works in one place and not another.

---

## 7. Identity, and running twice

Already built in RC Automation 0.7.0 and it generalises unchanged:

| Field | Holds |
| --- | --- |
| `ID` | The type mark — what a schedule groups on. |
| `ID_LIC` | Location in context: the grid intersection. |
| `ID_V` | The variant: the instance mark on a host, the layer and direction on a bar. |
| `ITEM` | What it is, as the schedule prints it. |
| `LEVEL_V` | The level, spelled the way the **model** spells it. |

Plus a job stamp, so a second run recognises its own work and **never touches anything else**.
Bars added by hand are never deleted; that rule extends to every element type without change.

---

## 8. Failure model

| Failure | What happens |
| --- | --- |
| Routes not running | Excel's post fails immediately; the macro falls back to writing the job file and tells the user to press the button in Revit. |
| Revit busy or modal | The job sits queued. Excel polls, then times out; the job still completes and the result file is there. |
| No document open | `rejected`, with a message. Nothing queued. |
| Workbook unsaved | `rejected` — the file on disk is older than the job. |
| Validation errors | `done` with findings and nothing written. This is a successful dry run, not a failure. |
| One chunk fails | That chunk rolls back, the rest continues, the result names what was lost. Already built. |
| Revit crashes mid-job | No result file. Excel's poll times out. The next run is a sync, so it picks up wherever the model actually got to — which is why every command is a sync. |

---

## 9. Where MCP fits

**Not as the transport.** A button press does not need a language model between it and a function
call, and putting one there adds latency, cost and a failure mode for no gain.

**As a layer over the same endpoints, later.** `POST /anongee/jobs` is already a clean tool surface.
An MCP server in front of it lets Claude drive the same commands from a sentence — and this is a
solved shape: `revit-mcp-python` is exactly a FastMCP server forwarding to pyRevit Routes on
`localhost:48884`.

The design consequence today is small and worth honouring: **keep the command surface small,
named, and described**, because that is what makes it a good tool surface later. It costs nothing
now and saves a redesign at stage 6.

---

## 10. What gets built first

`SPIKE-1`, and nothing else until it answers.

1. `startup.py` with one route: `GET /anongee/ping` returning the document title.
2. A three-line VBA sub that calls it and puts the answer in a cell.

That confirms, in half a day: the server starts, Excel can reach it, a handler gets a real `doc`,
and the External Event marshalling is real. **Every estimate in the PRD is conditional on this.**
If it fails, the file drop becomes the primary transport and the programme continues — slower at the
edge, identical everywhere else, which is the reason for designing two transports behind one
envelope in the first place.

# The bridge

An Excel button, a command, and a Revit model that changes because of it.

This folder holds the **Excel end**. The Revit end is
[`AnonGee.extension/startup.py`](../AnonGee.extension/startup.py) and the
[Bridge Check](../AnonGee.extension/AnonGee.tab/Dev.panel/Bridge%20Check.pushbutton)
pushbutton. The design is in
[`docs/specs/2026-08-22-excel-revit-platform-architecture.md`](../docs/specs/2026-08-22-excel-revit-platform-architecture.md).

```
bridge/
  excel/
    modAnonGeeBridge.bas    the VBA. Import it into a workbook once.
```

---

## What this is right now

**The spike, and only the spike** — `CRIT-1` in the repository's
[`todo-list.md`](../todo-list.md). It proves the wire exists. It does not post a
job, it does not read a sheet, and it changes nothing in any model.

Every estimate in the PRD is conditional on this working, which is why it is
built before anything that would sit on top of it.

---

## Running it

### 1. Turn the Routes server on

pyRevit ships an HTTP server that runs inside the Revit process. **It is off by
default.**

pyRevit tab → **Settings** → find the Routes / server section → turn it on →
**restart Revit**.

> Confirming exactly where that switch is on your build is part of this spike.
> Note what you had to click; it goes in the report and then into this file.

### 2. Check it from inside Revit first

AnonGee tab → Dev → **Bridge Check**.

This calls the same two URLs Excel will call, from the machine Revit is on. Doing
it here first takes the network out of the question — and when Excel later gets
no answer, this is how you tell "the bridge is down" from "Excel cannot reach
it".

### 3. Then from Excel

1. Open any workbook (a blank one is fine).
2. `Alt+F11` → **File → Import File…** → `bridge/excel/modAnonGeeBridge.bas`
3. `Alt+F8` → **AnonGeeBridge_Ping** → Run.
4. `Alt+F8` → **AnonGeeBridge_Status** → Run.

Each writes a row to a `BRIDGE_SPIKE` sheet and shows the raw response.

---

## What the two calls mean

| Route | Declares | Answers when | Proves |
| --- | --- | --- | --- |
| `/anongee/ping` | nothing | always, even mid-command | the server is up and the port is reachable |
| `/anongee/status` | `uiapp` | only once Revit is idle | pyRevit really did marshal the handler onto Revit's thread |

**Two routes rather than one, deliberately.** If ping answers and status hangs,
the server is fine and the marshalling is not. One route cannot tell you that,
and the difference is a day.

---

## What to send back

Paste both raw responses into the report. Four things in them decide the next
stage:

1. **`engine.implementation` and `engine.version`.** Which Python runs a pyRevit
   startup script. The toolkit is CPython 3 and lives in `lib/py3`; pyRevit's
   core engine is IronPython. If they are not the same, route handlers cannot
   import the toolkit directly and commands have to be dispatched to a CPython
   script instead — a fork in the architecture much better known now than during
   stage 1.
2. **`toolkit.importable`.** The same question, answered directly.
3. **Whether `status` answered at all**, and how long it took.
4. **What happened with no document open**, and with a modal dialog up. Try
   both — the second is the one a real user will hit first.

---

## What this is not

Not the product. The real bridge **posts a job and polls for a result**:

```
POST /anongee/jobs   {command, workbook, sheet, options}  → 202 {jobId}
GET  /anongee/jobs/<jobId>                                → status, summary, findings
```

Because Revit cannot be driven while it is busy, an Excel button **queues a job**
— it does not remote-control the application. A synchronous call that waits for a
5,000-element run will time out and leave Excel hung while the job is still
going.

Two other rules from the architecture, worth knowing before reading the VBA and
wondering why it is so short:

- **The envelope carries which sheet, not the data.** Revit opens the workbook
  itself, with the reader that already handles six formats. A JSON payload would
  be a second reader that eventually disagrees with the first.
- **Revit never writes into the open `.xlsm`.** Excel has it locked. Revit writes
  a JSON result file; the macro reads it and writes the sheet.

Which is why the macro must stay small. Anything it knows has to be kept in step
with Python by hand.

---

## When the wire is not there

The bridge is designed with **two transports behind one envelope**, and the
second one already exists in spirit: it is what RC Automation does today.

```
<workbook folder>/.anongee/
    outbox/  <jobId>.job.json     Excel writes, Revit reads
    inbox/   <jobId>.result.json  Revit writes, Excel reads
```

If Routes cannot be turned on — a locked-down machine, a blocked local port,
Revit not running when the button is pressed — the macro writes the job file and
the user presses the button in Revit instead. Same envelope, same handler, same
result. Slower at the edge, identical everywhere else.

That is not a fallback bolted on afterwards. It is the reason the transport is
kept at the edge and the command registry knows nothing about it.

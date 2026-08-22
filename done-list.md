# AnonGee Bridge — done list

What the programme has built and confirmed working in Revit, and what it took.

**Nothing yet.** The programme is at stage 0 and has shipped no command. The first entry will be
`CRIT-1`, the Excel → Revit round trip, and it arrives here when the owner has pressed a button in
Excel and seen a Revit document title come back.

**An entry arrives here only when the project owner has run it in Revit and said it works.** A green
test suite is not confirmation — every bug this repository has shipped passed the suite on the way
to a model. Where the evidence is weaker than that, the entry says so in its own words rather than
rounding up.

Nothing is deleted from here. An item later replaced stays, marked `superseded`, with what replaced
it — what a thing cost to build is part of the record even when it no longer runs.

| Column | Meaning |
| --- | --- |
| **Confirmed** | The report, screenshot or sentence from the owner that closed it. |
| **Shipped in** | The version it first worked in. |
| **Cost** | What it took, including the wrong turns — those are the expensive part and the part worth remembering. |

---

## What this programme inherits

Not entries — these were built and confirmed under **RC Automation**, and they are described in
`AnonGee.extension/AnonGee.tab/Dev.panel/RC Automation.pushbutton/done-list.md`. They are listed
here because the programme is built on them and nobody should rebuild them.

| Inherited | Recorded as | Why it matters to the bridge |
| --- | --- | --- |
| The pure / Revit split | *RC Automation · DONE-1, DONE-2* | 575 tests run on any machine. Every new command follows the same seam. |
| External-event marshalling, FIFO queue, modeless window | *RC Automation · DONE-11* | The answer to the one constraint the whole architecture is built around: the Revit API runs on Revit's thread, when Revit is idle. |
| A workbook reader across six formats | *RC Automation · DONE-1* | Why the command envelope carries *which sheet*, not the data. |
| Validation that names its cell | *RC Automation · DONE-2* | The finding shape the result envelope uses unchanged. |
| Level and grid name matching | *RC Automation · DONE-3, DONE-4* | `levels.sync` and `grids.sync` start from working code, not from nothing. |
| One undo step, chunked and assimilated | *RC Automation · DONE-10* | Extends to every command without change. |
| Identity fields, and never deleting what the tool did not create | RC Automation 0.7.0 | Extends to every element type without change. |
| A text report as the tool's only witness | *RC Automation · DONE-12* | Two of the last three bugs were found by reading one against a model rather than by anyone testing anything. |

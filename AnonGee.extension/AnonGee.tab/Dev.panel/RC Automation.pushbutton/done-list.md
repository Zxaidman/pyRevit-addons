# RC Automation — done list

What was built and confirmed working in Revit, and what it took. One entry per item that reached
`done` in `todo-list.md`.

**An entry arrives here only when the project owner has run it in Revit and said it works.** A green
test suite is not confirmation — every bug this tool has shipped passed the suite on the way to the
model. Where the evidence is weaker than that, the entry says so in its own words rather than
rounding up.

Nothing is deleted from here. An item that is later replaced stays, marked `superseded`, with what
replaced it — what a thing cost to build is part of the record even when it no longer runs.

| Column | Meaning |
| --- | --- |
| **Confirmed** | The report, screenshot or sentence from the owner that closed it. |
| **Shipped in** | The tool version it first worked in. |
| **Cost** | What it took, including the wrong turns — those are the expensive part and the part worth remembering. |

---

## DONE-1 — read a schedule in any of six shapes

**Shipped in** 0.1.0 · **Confirmed** owner's screenshot of the loaded window (msg 8) and three run
reports since.

`.xlsx` and `.xlsm` through the bundled openpyxl; a folder holding one `.csv` or `.txt` per sheet,
which is the shape Revit's own schedule export writes; and a single `.csv` or `.txt` carrying every
sheet, separated by `#SHEET,<name>` rows. Only `read_grid` touches openpyxl; `parse_grid` is pure,
so the whole of parsing is testable on any machine.

An `INFO` cover sheet carries the project, the units and the standard. Keeping those off the data
sheets leaves them as pure tables, so Excel's own filter and sort still work on them — a title block
wedged above a header breaks both, and one arriving that way is still read.

**Cost.** Three things were got wrong first.

*`.xlsm` was a lie.* openpyxl writes xlsx content types under any filename, so the generated `.xlsm`
was byte-identical to the `.xlsx` — same md5 — and Excel refused it. The owner found it, saved real
`.xls` and `.xlsm` files by hand and pushed them as ground truth. Fixed by rewriting
`[Content_Types].xml` to `application/vnd.ms-excel.sheet.macroEnabled.main+xml`; their file confirmed
the fix matches Excel's own output.

*A fixture claimed something false.* `not_a_workbook.xls` was committed with a comment saying "Excel
will refuse it". The owner's screenshot showed Excel opening it perfectly well through text import.
Deleted, and replaced by their real `.xls`.

*The report was written in cp1252.* Mojibake in the file, and it broke the folder reader that had to
read it back. Now written as UTF-8 explicitly and decoded leniently (utf-8 → cp1252 → latin-1), and
the folder reader only opens files named after a sheet.

---

## DONE-2 — validate before opening a transaction

**Shipped in** 0.1.0 · **Confirmed** *"0 errors, 0 warnings, 2 notes"* against the sample, in the
0.6.0 report.

Error / Warning / Info against BS 8666:2020 — bar sizes, shape codes, cover that leaves room for
steel, spacing wider than the bar, ties that are actually closed links, confinement zones, cages
that fit the column they are drawn in. Every finding names the sheet, row and column it came from,
so a problem can be typed straight into Excel's Name Box.

`standards.py` is held to BBS Generator's `BS_8666_2020.py` by a test that fails if the diameters or
shape codes drift apart, which is what makes a small local copy tolerable instead of an import
between two pushbuttons.

**Cost.** The first parser keyed rows into a `_by_type_mark` dict as it read them, which collapsed
duplicates before validation ever saw them — destroying the evidence the duplicate-mark rule needed.
Lists are the source of truth now; the dicts are lookups built afterwards.

---

## DONE-3 — match level names instead of demanding them

**Shipped in** 0.3.0 · **Confirmed** 0.6.0 report — `Foundation → 00 FOUNDATION LVL.` and
`Level 1 → 01 GROUND LVL.` in a model that spells neither the way the workbook does.

Four passes, each of which must resolve unambiguously or hand on: exact, folded, significant-word,
and storey number — so `Level 1` and `L1` both find `01 1st Floor Lvl.`. Two candidates are named
rather than picked between. An optional `LEVELS` sheet settles what matching cannot reach, and a
stale override falls back to matching with a note saying it did.

The matching itself is in `rc_automation/naming.py` with no Revit in it; `structural/levels.py` is a
thin adapter that reads the model's names and hands them over.

---

## DONE-4 — resolve a grid crossing to a point

**Shipped in** 0.3.0 · **Confirmed** five of the six sample pads are placed by grid reference and
all six arrived.

Grid names matched through the same `naming.py` passes as levels. A placement carrying both a grid
reference and X/Y falls back to the coordinates when the grid does not resolve, because a workbook
carrying both has already said where the pad goes. Coordinates alone are the only route that works
in a model with no grids in it yet, which is exactly the model this tool is pointed at first.

---

## DONE-5 — create footings as structural floors

**Shipped in** 0.3.0 · **Confirmed** *"Created 6 footing(s)"*, 0.6.0 report.

`Floor.Create` from a `CurveLoop`, which is why an `Outline` column in the placement sheet can be
sketched as drawn — a combined pad, a cut corner, a pad worked around a pile cap. The owner's
decision (msg 2): *"use `Floor.Create` for Structural Foundation Footing because we can create any
shaped footing with it."*

Every pad is flagged structural, **without which Revit accepts no reinforcement at all and nothing
about the model looks wrong**. A floor type is duplicated per thickness and reused, so a second run
adds no types. A mark already on a foundation is left alone rather than duplicated.

**Cost.** The bars were planned from the type's rectangle and placed against the element's
bounding-box centre — two different frames. On the one sample pad that is not a rectangle they
landed 2.25 m outside the concrete, because its outline runs from the placement point rather than
around it. Both halves now use the pad's own outline and its own placement point. The test that
should have caught it had pinned the buggy behaviour instead.

---

## DONE-6 — place reinforcement as sets

**Shipped in** 0.2.0 · **Confirmed** *"26 set(s) — 317 bar(s)"*, 0.6.0 report.

One `Rebar` element standing for a whole run, through `SetLayoutAsNumberWithSpacing` /
`SetLayoutAsMaximumSpacing` / `SetLayoutAsFixedNumber` — roughly 2,000 elements instead of 50,000 at
the stated scale, and what a detailer expects to select and edit. Compatible with BBS Generator,
which reads `REBAR_ELEM_QUANTITY_OF_BARS`.

Every bar is stamped as this tool's work, so a later run can tell its own steel from somebody's
hand-modelled bar and **only ever deletes the former**.

---

## DONE-7 — bend the bar its shape code describes

**Shipped in** 0.4.0 · **Confirmed** the owner reported the fault at 0.3.x — *"rebar is 00 shape
code only there is not shape 21 is used"* — and has not repeated it in the three reports since.

`00` runs straight, `11` turns one end up, `21` turns both — the U-bar a footing bottom mat is
detailed as almost everywhere. A layer with no room to bend is placed straight **and says so**,
rather than being quietly straightened: a bar drawn straight where the schedule said bent is wrong
in the model and wrong in the bending schedule, and looks right in neither.

**Cost.** The shape code was carried through parsing, validation and planning as a label and never
used to build anything — `plan_footing_layer` emitted two points whatever it said. Found by the
owner in the model, not by any of the 400 tests passing at the time.

**Caveat, recorded honestly:** the *placement* is confirmed. What Revit writes as the shape code on
the finished element has never been read back in a report, because `CreateFromCurves` leaves Revit
to match a shape. FEAT-9 is the fix for that and is still open.

---

## DONE-8 — one set per distribution region

**Shipped in** 0.6.0 · **Confirmed** owner, msg 19 — *"now F3 rebar set placement is correct"*.

A varying set covers **one** region of varying depth. Told to vary across a change of slope, Revit
interpolates straight through the corner and fans bars out past the concrete — which is what a run
against the house-shaped pad produced, and what the owner's annotated images (msg 18, images 4 and 5)
showed the right answer to.

Between two consecutive vertices of the outline the edges are straight, so a bar's length varies
linearly and one set describes the stretch. At a vertex it cannot. Positions are computed once
across the whole layer and then assigned to regions, so the spacing stays uniform and the split only
decides where one set ends.

For the sample's five-sided pad:

```
B1X  up to 3000   15 bars   plain set
B1X  from 3000     6 bars   varying set
B2Y  up to 2250    7 bars   varying set
B2Y  from 2250     8 bars   varying set
```

**Cost.** 0.5.0 shipped one set for the whole layer with varying turned on, which is the thing that
produced the fan. The owner's images are what made the rule obvious.

---

## DONE-9 — write cover onto the footing

**Shipped in** 0.6.0 · **Confirmed** owner, msg 19 — *"now Rebar cover is getting assign properly"*.

Cover in Revit is an element reference, not a number, so a schedule saying 50 mm needs a
`RebarCoverType` to point at. Matched if the project has one, created if not, named for the face it
belongs to — `FOOTING TOP`, `FOOTING BOTTOM`, `FOOTING ALL SIDE` — because the owner asked for
element-specific names rather than `RC 50 mm`.

**Cost.** Three wrong turns, each silent.

*`RebarCoverFaceType` does not exist.* It was guessed at for `RebarHostData.SetCoverType`, which
actually takes a face `Reference`. The guess failed without raising, so cover types were created and
nothing was written.

*The parameters were not there yet.* A floor has no rebar-cover parameters until it is structural
**and the document has regenerated**. Both the floor and every newly created bar are regenerated
before anything asks them for parameters or handles.

*Three duplicate `RC 50 mm` types.* A type created inside an open transaction is invisible to a fresh
`FilteredElementCollector`, so each face created another. Fixed with a per-run cache — which then
introduced BUG-1 by being keyed on the value alone, still open at the time of writing.

---

## DONE-10 — one undo step, and one failure does not lose the run

**Shipped in** 0.2.0 · **Confirmed** reported by every run (*"One undo step — Ctrl+Z reverses the
whole run"*). **Not independently exercised by the owner** — recorded as working on the strength of
the code and the reports, not on a Ctrl+Z anybody watched.

A `TransactionGroup` the pushbutton owns, chunked 25 hosts at a time so a failure rolls back that
chunk and the rest continues, then `Assimilate()` so the user gets one step rather than twenty. A
failure preprocessor absorbs the warning-per-element a batch raises and leaves errors alone.

Creating the footings and reinforcing them sit in the *same* group, so somebody who does not like
the result reverses both rather than being left with bare pads.

---

## DONE-11 — a modeless window that does not deadlock Revit

**Shipped in** 0.1.0 · **Confirmed** owner's screenshot of the working window (msg 8), and every run
since has been driven from it.

`window.Show()` with `WindowInteropHelper.Owner` set, all Revit work inside
`IExternalEventHandler.Execute()`, and a FIFO queue so two clicks serialise instead of racing. Only
ints and strings cross the thread bridge.

**Cost.** The engine's constraints are unforgiving and each was learned the hard way somewhere in
this repository: no `__init__` on a class inheriting a Revit interface; the handler type defined
once per session and cached in `sys.modules`, because re-running the class statement raises
*"Duplicate type name within an assembly"*; `List[T]` marshalled with `.Add()`, since a raw Python
list across pythonnet is a fatal fault rather than a catchable `TypeError`; the DataGrid bound
through `__slots__` and an `ArrayList`, because INPC fails silently.

**And one that was ours alone.** `BUILDABLE_MODES` was written above the import that defines
`models`, so the script raised `NameError` before a line of it ran — and every test passed, because
they all *parse* the file and none of them *executes* it. `ModuleScopeTests` now checks that
everything read at import time is defined by then, and was verified by reintroducing the fault.

---

## DONE-12 — export what happened

**Shipped in** 0.1.0 · **Confirmed** the three reports in `docs/captures/` and
`tests/fixtures/rc_automation/sample_schedule_rc_report.txt` are its output — the owner runs it and
pushes the file, and that loop is how most of this list got confirmed.

Findings and probe, written beside the workbook. One builder for the panel and the file both, so a
failure the window mentions and the exported file leaves out cannot happen.

The report is the tool's only witness. Two bugs in `todo-list.md` (BUG-3, CRIT-1) were found by
reading it against the model rather than by anybody testing anything, which is the argument for
making it say more rather than less.

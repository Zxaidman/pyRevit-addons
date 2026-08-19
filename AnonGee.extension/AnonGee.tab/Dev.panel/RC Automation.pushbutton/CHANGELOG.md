# RC Automation — changelog

## 0.3.1 — 2026-08-19

0.3.0 built footings and then told the user it could not.

- **"Create structure and reinforcement is not built yet" was false.** Shipping
  Phase 1 updated the gate on planning and left four other comparisons reading
  "anything but reinforce-existing is unsupported", so the report and the status
  bar denied a mode the button beside them would have built. Which modes can
  build is decided in one place now, and the only one that cannot is Reconcile —
  which resolves differences rather than building anything.
- **The probe called levels missing that the run would have matched.** It was
  doing a plain set difference where the run uses the name matcher, so a model
  whose lowest level is `00 FOUNDATION LVL.` was reported as not having
  `Foundation`. It now resolves them the same way the run does, and shows what
  each one landed on.
- **A stale LEVELS mapping no longer blocks.** Levels get renamed and the sheet
  does not follow; a mapping pointing at a name the model no longer has is
  reported and then the matching runs anyway. Blocking a run on an out-of-date
  mapping, when the name it was written for is sitting right there, helps
  nobody.

## 0.3.0 — 2026-08-19

Phase 1: create the footings, then reinforce them.

"Create structure and reinforcement" builds now. Both halves land in one
`TransactionGroup`, so a user who reverses the run does not end up holding bare
pads.

- **Footings are placed as floors**, which is what lets a pad that is not
  rectangular be scheduled rather than approximated — the `Outline` column is
  sketched as drawn. A type is duplicated per thickness and reused, so a second
  run over the same schedule adds no types.
- **Every pad is flagged structural on creation.** A floor that is not carries no
  reinforcement, refuses every bar, and looks identical in every view. The first
  probe of a real model found exactly that waiting.
- **New pads are measured before they are reinforced**, against their own
  bounding box, so a pad that came out anywhere other than where it was asked
  for still gets bars that fit its concrete.
- **Level names are matched, not demanded.** A schedule saying `Ground` finds
  `00 Ground Lvl.`; `Level 1` and `L1` find `01 1st Floor Lvl.` by storey number
  even though neither has a word in common with it. Two candidates are named
  rather than picked between — a guess that puts a foundation on the second
  floor is worse than a question.
- **An optional `LEVELS` sheet** settles the ones matching cannot reach. Two
  columns: the name the schedule uses, the name this model uses. `Foundation`
  resembles nothing in a model whose lowest level is `00 Ground Lvl.`, and being
  told beats being clever.
- **Grid references resolve to points.** `GridX`/`GridY` cross two grid lines,
  as infinite lines rather than drawn segments, because a grid bubble stops
  where the drawing needed it to. A row carrying coordinates as well falls back
  to them when a grid name does not resolve.
- A mark already on a foundation is left alone rather than placed twice.

## 0.2.1 — 2026-08-19

Everything here came out of one report exported from a real model.

- **Reports are written as UTF-8.** `open(path, "w")` uses the platform encoding,
  and on Windows that wrote cp1252 — every dash in the report came back as a byte
  nothing could decode.
- **The report no longer calls itself a "read-only report".** It writes now, and
  a report saying otherwise tells the reader something false about what just
  happened to their model.
- **A folder of sheets tolerates what else is in it.** The exported report,
  dropped beside the sheets, was read as one and failed the whole workbook. Only
  files named after a sheet are read now, and text is decoded UTF-8 then cp1252
  then latin-1, because a schedule exported from Excel is not UTF-8 and refusing
  it on that account is the tool's problem presented as the user's.
- **The probe states its conclusion.** "Structural foundations: 0" and a list of
  bar types left the reader to work out that there was nothing to reinforce. It
  now says so, names the levels the workbook asks for that the model does not
  have, and says when no foundation can host a bar.
- **An unsupported mode is said when the workbook loads**, not only when Plan is
  pressed — and the status bar, the report and the probe now share one sentence
  so they cannot drift apart.

## 0.2.0 — 2026-08-19

It writes.

Phase 2 only: reinforcement into footings that already exist. Creating the
structure itself needs the placement sheets and is not in this build, so Create
is reachable only in "Reinforce existing structure".

- **Plan reinforcement** matches every footing, works out its bars, and says per
  host why anything is being skipped — still without opening a transaction. The
  plan is what Create acts on, so what is about to happen can be read and
  refused first.
- **Create rebar** places it, after a confirmation naming the counts. The run is
  one `TransactionGroup`, assimilated into **a single undo step**, so one
  Ctrl+Z reverses the whole run rather than four hundred of them. Inside
  that, work is chunked so a failure rolls back its chunk and the rest carries
  on, and a failure preprocessor absorbs the warning-per-host a batch generates
  while leaving errors to roll the chunk back.
- **A host that already carries reinforcement is left alone**, so running the
  same workbook twice does not double the steel. "Replace mine" rebuilds only
  the bars this tool stamped; bars added by hand are never touched.
- **A pad that is not the size it was scheduled is skipped and reported.** Bars
  are planned from the schedule and placed against the host's bounding box, so a
  footing that was modelled differently — or rotated, which makes its box bigger
  than itself — would get steel that does not fit its concrete.
- Bar types are resolved once per run, by name then by diameter. A size with no
  `RebarBarType` loaded blocks Create and is named, rather than being invented.
- **Single-file delimited schedules**: a `.csv` or `.txt` holding every sheet,
  separated by `#SHEET,<name>` rows, as well as a folder of one file per sheet.

## 0.1.0 — 2026-08-18

First build, and deliberately a read-only one.

Everything hard about this feature is downstream of questions nobody had
answered inside Revit yet: whether the CPython 3 engine imports the toolkit,
whether the vendored openpyxl loads, whether the modeless bridge holds, whether
the levels and bar types a schedule names are present, and whether the elements
it matches can host reinforcement at all. Finding any of that out during a
four-hundred element write is the expensive way round.

So this build opens no transaction and creates nothing.

- Loads a schedule workbook and validates it — bar sizes and shape codes against
  BS 8666:2020, cover that leaves room for steel, spacing wider than the bar it
  spaces, ties that are closed links, confinement zones given whole rather than
  half, and cages that fit the column they are scheduled in. Every finding names
  the cell it came from.
- Three modes, because what a workbook must contain depends on the job: creating
  a structure needs the placement sheets, reinforcing one that already exists
  does not.
- Works out what the schedule would build without building it, including whether
  each layer can ship as one Revit element or has to be individual bars — a
  tapered pad's bars are not all the same length, and a set repeats one shape.
- Probes the model read-only: levels, rebar bar types, how many footings and
  columns exist, and how many of them Revit will actually let a bar into.
- Exports the findings and the probe to a text file beside the workbook.

Known and intended limits: no geometry is written, laps and starter bars are out
of scope, and shape codes outside 00 / 11 / 21 / 51 validate but are reported
rather than built.

# RC Automation — changelog

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

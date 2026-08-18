# RC Automation — changelog

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

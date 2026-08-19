# Sample RC Automation schedule

The same schedule in every format the tool has to cope with. `test_rc_automation.py`
asserts they all parse to the **same objects**, so a format cannot quietly drift
away from the others.

| What | Why it is here |
| --- | --- |
| `*.csv` — one per sheet | **The source of truth.** A schema change gets reviewed in a diff of these, and everything else is generated from them. Also a working input: point the tool at this folder. |
| `sample_schedule.xlsx` | The normal case, with the `INFO` cover sheet. |
| `sample_schedule.xlsm` | Macro-enabled, which is what a firm's real template usually is. openpyxl **cannot** write one from scratch — `Workbook().save("x.xlsm")` writes an ordinary xlsx under an xlsm name, which openpyxl reads back happily and Excel refuses outright. The generator re-declares the workbook part afterwards; a macro-enabled workbook with no macros is valid, and what makes it xlsm is the content type, not a `vbaProject.bin`. |
| `not_a_workbook.xls` | **Not a real `.xls`**, and named so nobody wastes a double-click finding out. openpyxl cannot write BIFF and faking it would be worse than useless; this exists so the legacy-format refusal is tested against a file that is actually present, because "not found" and "cannot read this format" are different problems needing different sentences. |
| `txt_sheets/` | Tab-separated, one file per sheet. Revit's own schedule export writes this, so a folder of them is a first-class input. |
| `all-in-one xlsx sheet needed like this example.xlsx` | The workbook from the first real run inside Revit. It has no `INFO` sheet and no title block, which is exactly why it warns about units — kept because a real file that exercises the fallback is worth more than one written to pass. |

Regenerate everything but the CSVs and the pushed workbook with:

    python tests/fixtures/rc_automation/build_fixtures.py

## Reading a file back is not proof it is valid

The `.xlsm` here was, for one commit, a byte-for-byte copy of the `.xlsx` with a
different name. Every test passed — openpyxl goes by content and ignores the
extension — and Excel would not open it at all.

So `WorkbookFormatTests` does not read the files. It opens the archive and checks
what `[Content_Types].xml` *declares* the workbook part to be, against what the
extension promises, which is the same comparison Excel makes. Whatever writes
these fixtures next, that check is what holds it honest.

## What the sample is showing

**Metadata lives on its own sheet.** `INFO` carries the project, the units and
the standard, so the data sheets stay pure tables and Excel's own filter and sort
keep working on them. A title block above the header still reads — that is how a
real schedule arrives, and `FOOTING_TYPES.csv` keeps one to prove it — but the
cover sheet wins where both exist.

**Type and placement are separate.** One `FOOTING_TYPES` row describes a footing;
`FOOTING_PLACEMENT` says where each one goes. That is why one `FOOTING_REBAR` row
can reinforce every F1 in the building.

**Position comes two ways.** Grid references for the pads on an intersection,
X/Y millimetres for the one that is not — which is the only thing that works in a
model with no grids in it yet.

**The last footing placement carries an `Outline`.** A five-sided pad, and the
reason footings are floors rather than family instances. Its bars are genuinely
different lengths, so that layer cannot ship as one Revit element and the tool
says so instead of quietly placing the wrong steel.

**`C1` has two main-bar rows.** "4T20 corners + 6T16 faces" is one column and two
rows — the shape a single-row `COLUMN_REBAR` sheet could not express.

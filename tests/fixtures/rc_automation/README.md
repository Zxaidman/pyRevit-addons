# Sample RC Automation workbook

The six sheets the tool reads, one CSV each, holding a schedule that is meant to look
like one an engineer would actually issue — a title block above the table, two
main-bar groups in a column, ties that tighten at the ends, and a footing with
two mats.

They are CSVs rather than an `.xlsx` for two reasons: a diff of a schema change
is readable, and the test suite can load them on a machine where the extension's
vendored (Windows) openpyxl will not import. `parse_grid` takes the raw grid
either way, so these exercise the same code the real workbook does.

`FOOTING_TYPES.csv` carries the title block on purpose. Finding the header row
rather than assuming row 1 is what lets a real schedule load unedited.

`FOOTING_PLACEMENT.csv` shows both ways of saying where something goes: grid
references for the pads that sit on an intersection, and X/Y millimetres for the
one that does not. Its last row also carries an `Outline` — the five-sided pad
that is the reason footings are floors rather than family instances.

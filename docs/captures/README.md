# Captures

Output taken off a real Revit session and kept because it changed the code.

Not fixtures — nothing loads these, and they are deliberately not in
`tests/fixtures/`, where the folder reader would try to read them as sheets.

## `2026-08-19-rc-automation-empty-model-report.txt`

The first RC Automation report exported from a live model. It found four things
in one page:

1. The report called itself a **"read-only report"** from a build that writes.
2. It was written in **cp1252**, so the em-dash came out as a byte nothing could
   decode. `open(path, "w")` without an encoding does that on Windows.
3. Dropped in the fixtures folder, it **broke the folder reader** — which read
   every `.txt` beside the sheets and failed the whole workbook on one it could
   not decode. A folder is somebody's working directory as often as a workbook.
4. It reported `Structural foundations: 0` and `Rebar bar types (8)` and left the
   reader to work out that the model was empty and the mode unsupported, which is
   the tool failing to explain itself rather than the user failing to read.

Kept in its original encoding. Fixing the file would remove the evidence.

## `2026-08-19-rc-automation-0.3.0-stale-mode-message.txt`

Exported from 0.3.0, the release that created footings. It says:

> 'Create structure and reinforcement' is not built yet

which was false — that release built exactly that. When Phase 1 shipped, the
gate on planning was updated and **four other comparisons were not**: they still
read "anything but reinforce-existing is unsupported", so the report told the
user a mode was not built while the button beside it would have built it.

The test that should have caught it made it worse. It asserted the sentence
appeared *at least three times*, which passed happily while all three said the
wrong thing — a count is not a condition. It now checks that which modes can
build is decided in one place.

The same report also called `Foundation` a level the model does not have, in a
model whose lowest level is `00 FOUNDATION LVL.` The probe was doing a plain set
difference where the run uses the name matcher, so the two disagreed about a
level the run would have matched and built on.

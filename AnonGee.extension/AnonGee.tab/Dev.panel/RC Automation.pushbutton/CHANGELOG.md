# RC Automation — changelog

## 0.6.0 — 2026-08-19

One set per distribution region, and two reasons cover was never applied.

- **A layer is cut at the outline's vertices, one set per stretch.** Told to
  vary across a change of slope, Revit interpolates straight through the corner
  and fans bars out past the concrete — which is what the tapered pad produced.
  Between two consecutive vertices the edges are straight, so one set describes
  the stretch; at a vertex it cannot. A house-shaped pad now gives, for X bars,
  one plain set across the rectangle and one varying set over the gable; and for
  Y bars, two varying sets, one rising to the apex and one falling from it.
  Positions are computed once across the whole layer and then assigned to
  regions, so the spacing stays uniform and the split only decides where one set
  ends.
- **Cover: `RebarCoverFaceType` does not exist.** The previous version guessed
  at it for `RebarHostData.SetCoverType`, which actually takes a face
  `Reference`. The guess failed silently, so cover types were created and
  nothing was written.
- **Cover: the parameters were not there yet.** A floor has no rebar-cover
  parameters until it is structural *and the document has regenerated*. Both
  the floor and, separately, every newly created bar are now regenerated before
  anything asks them for parameters or constraint handles — a thing Revit has
  not caught up with has neither.
- **`SetCommonCoverType` as a fallback**, for a host that will not take faces
  one at a time.
- **The run reads back what Revit did.** A set's `ArrayLength` is compared with
  what was asked for, and a disagreement over 25 mm is reported. A distribution
  that arrayed the wrong way or filled past the pad now says so in the report
  rather than in a screenshot.
- **The probe reports the host's actual cover parameters** — which exist, which
  are read-only — so the next report says which of the possible reasons applied.

## 0.5.0 — 2026-08-19

The constraint error from a real run named the mistake exactly: *"Constrained
rebar isn't a free form rebar element."*

- **Constraints use the shape-driven API.** `RebarConstraint.Create` is
  free-form only, so against a bar from `CreateFromCurves` it could never have
  worked. Shape-driven bars ask Revit for **candidates** and pick one:
  `GetConstraintCandidatesForHandle` → `IsToCover()` → `SetPreferredConstraint`
  → `ApplyRebarConstraints`. A cover candidate is preferred over a bare face,
  because a bar tied to a face ignores a cover change.
- **A varied area is one varying set, not loose bars.** The ribbon's Varying
  Rebar Set is one property — `UseRebarConstraintsToProduceVaryingBars` — set
  after constraining, because the constraints are what produce the variation.
  Orthogonal areas get their own set with it off. The tapered pad went from 71
  single bars to 4 sets.
- **Cover types are named for the element, not the number.** `FOOTING TOP`,
  `FOOTING BOTTOM`, `FOOTING ALL SIDE` — the way a project names them. And they
  are created **once**: a type made inside an open transaction is invisible to a
  fresh collector until the document regenerates, which is why a run produced
  three identical 50 mm types and used none of them.
- **Cover is applied through `RebarHostData.SetCoverType`**, with the built-in
  parameters as fallback — one route that works for a floor, a wall and a family
  instance alike.
- **Placed bars are shown, not hidden.** Step five of the manual workflow turns
  obscured rebar *on*; the first version set both view flags to `False` and hid
  every bar it had just placed.
- **The report carries what the window said.** Constraint failures were being
  shown in a dialog and left out of the exported file — the one place they would
  be read later. Panel and report now share one builder.

`REVIT_API_RESEARCH.md` in the repository root records where all of this comes
from, and what else in the reinforcement API is worth having.

## 0.4.0 — 2026-08-19

The first build that placed steel placed it straight, and some of it outside
the concrete.

- **Shape codes now bend the bar.** Every footing bar was a straight line
  whatever its shape code said — the code was carried through parsing,
  validation and planning as a label and never used to build anything, so a
  bottom mat scheduled as a U-bar arrived as shape 00. `21` turns both ends up,
  `11` turns one, and the leg reaches the underside of the top cover less half a
  bar. A layer with no room to bend is placed straight **and says so**, rather
  than quietly pretending.
- **Bars stay inside the pad.** New footings were reinforced from the *type's
  rectangle* and placed against the element's *bounding-box centre* — two
  different frames. On the one pad in the sample that is not a rectangle, whose
  outline runs from the placement point rather than around it, that put the bars
  2.25 m out of the concrete. Bars are now planned from the outline the pad was
  built from and placed at the point it was placed at, turned by the same angle.
  Measured across every pad in the sample: zero overhang.
- **The scheduled cover goes onto the element.** Top, bottom and side, as
  `RebarCoverType` references — created when the project has none, because
  cover is a distance with a name and inventing one carries none of the baggage
  that inventing a bar type would. The model now carries the number, not just
  the bars.
- **Placed bars are constrained to that cover**, so editing a footing updates
  its reinforcement instead of leaving it where it was put. Written without a
  Revit to try it against: every call is probed first, a constraint that cannot
  be made is counted and reported rather than raised, and the probe now reports
  what this Revit build actually offers so the next pass can stop guessing. The
  bars are in the right place either way; what is lost is the updating.

## 0.3.2 — 2026-08-19

0.3.1 did not load.

- **`NameError: name 'models' is not defined`.** The constant deciding which
  modes can build was written above the import that provides `models`, so the
  script raised before a line of it ran. Moved below the imports.
- **The tests could not have caught it.** All of them parse this file and none
  executes it — importing it is not an option, since it imports Revit at module
  scope. There is now a check that reads the module top to bottom and reports
  any name used before something binds it, across the pushbutton and every
  toolkit module. It is itself tested against the fault it was written for,
  because a check that reports nothing looks exactly like a broken one.

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

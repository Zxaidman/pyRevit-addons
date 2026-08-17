# Findings — cad2bim after v0.68.0

## 1. "The name is already in use for this element type" — root cause

Reported against the column pass at v0.68.0. `builders/columns.py::_resolve_symbol`:

```python
existing = _find_type_in_family(base_symbol.Family, type_name)   # get_element_name(s) == type_name
if existing is not None: ... return existing
new_symbol = base_symbol.Duplicate(type_name)                    # threw here
```

`Duplicate` was reached **only because the pre-check had just reported the name
free**. Both statements concern the same family at the same moment, so the
pre-check was provably stricter than Revit's own uniqueness rule. That holds
whichever normalisation detail differs, and is the whole diagnosis.

The specific difference is case. Revit matches type names case-insensitively;
Python `==` does not. The default template is `"{b} X {h}"` (capital X,
`naming.py`), Revit's stock concrete column families ship `300 x 450`-style
lowercase names, and the user's settings fixture has `naming: null`, so defaults
were in force. A family already holding `400 x 600` was asked for `400 X 600`.

Ruled out on evidence, not assumption:

- **Rounding collision** (two cache keys, one name) — impossible. `place_columns`
  rounds to `int` before forming the cache key, so key ⇔ name is 1:1. Same in
  beams, slabs, footings.
- **A template that collapses sizes** (`"{b}"`) — not this user, `naming` is
  null. Still a live hazard for anyone editing the Naming tab, so `validate` now
  refuses it.
- **Stale `GetFamilySymbolIds()` across storeys** — each storey commits its own
  transaction before the next begins, so the family is current.

### Every site that had the shape

| Site | Guarded | Consequence before the fix |
|------|---------|----------------------------|
| `columns.py` rect + round | no | **the reported crash**; every column of that size lost |
| `beams.py` | no | would have thrown identically |
| `slabs.py` | no | would have thrown identically |
| `footings.py` | yes → base type | **silent**: pad cast at the picked type's depth, not the computed one |
| `stairs.py` | yes → base id | **silent**: stair built at stock riser/tread/width |
| `stairs.py` `_apply_waist` | yes | **silent**: waist never applied |
| `grids.py` | yes | grid keeps Revit's auto name instead of its CAD bubble |
| `view_filters.py` | yes | filter dropped |

The three silent ones were arguably worse than the crash: no error, wrong
geometry. Fixed in v0.68.1; they still fall back, but they report.

Second defect found in the same sweep: `slabs.py` and `footings.py` searched
**every `FloorType` in the document**. Floors and Foundation Slabs share the
`FloorType` class but are different system families, and Revit scopes type-name
uniqueness to the family — so a Floor named `PAD 600 THK` could be handed back
for a foundation pad, filing it under the wrong category. Now scoped to the base
type's own system family.

## 2. Regression harness state

Three of the four legs were never committed and are gone
(`scratchpad/slabbase.py`, `base_after.json`, `sweep67.py`, `t10_full.py`,
`t10_cols.py`). Rebuilt in P0 under `tests/`:

| Leg | Corpus | Runtime |
|-----|--------|---------|
| `regression_slab_fingerprints` | 29 archived exports, newest per drawing | ~50s |
| `regression_dxf_sweep` | 17 fixture DXFs, full pipeline | ~110s |
| `regression_storeys` | 4 storey stacks | ~29s |

Two constraints discovered while rebuilding them:

- **An export cannot drive slab labelling.** The export format stores texts as
  parsed marks (`{"mark", "b", "h"}`) and drops the string. Both
  `apply_slab_labels` and `loops_for_unclaimed_notes` re-parse `text.text`.
  test13's export has 211 texts, every one with `mark: None`. Note recovery is
  therefore measured by the DXF leg, where the text survives.
- **The baselines are v0.68.1 measurements.** The v0.67.3 originals cannot be
  reproduced. One independent check that the harness reproduces the real
  pipeline: the old findings recorded "test10 +6 noted bays", and the sweep
  measures `slab_loops_recovered_from_notes = 6` on test10.

## 3. The DXF reader discards every hatch — fixed in P1.1

`readers/dxf_reader.py::_geometry_record` handles LINE, ARC, CIRCLE, POINT,
LWPOLYLINE, POLYLINE, ELLIPSE and SPLINE. There is no HATCH branch. Hatches per
fixture: test4 360, test5 360, test10 276, Project1 228, test9 147. All dropped.

This is the shared prerequisite for foundations (P1), folds/sunk (P2) and
openings (P4).

## 4. Foundations are invented, and rafts are impossible — fixed in P1.4

`footing_plan.pads_for(sections, projection_mm, region_max_side_mm)` reads only
`sections["entries"][*]["rectangles"]` and `sections["circles"]` — column
geometry — grows each by a projection and merges overlaps. Nothing is read from
the drawing.

`builders/footings.py` `_MAX_COLUMN_MIN_SIDE_MM = config.DEFAULTS["col_region_max_side_mm"]`
discards any footprint whose smaller side exceeds a column's, commented "a
lift/stair region, not a column". A raft is larger than a column by definition,
so it cannot be produced.

### What the outline recovery has to survive

Measured on test10 with the package's own reader. `S-FND` holds 20 records that
resolve into **13 outlines**, and they do not all arrive the same way:

| | Count | How it is drawn |
|-|-------|-----------------|
| Closed polylines | 10 | a rectangle each, taken exactly as drawn |
| Open polylines + loose lines | 3 | two 5500x11900 pads flanking a 3500x5900 sunk strip |

The three share edges. The strip's two long sides ARE the pads' inner sides,
drawn once, so the assembly has four degree-3 nodes. **Anything that consumes a
segment as it chains closes at most one of the three, and in practice closes
none** — `slab_outlines._chain_into_rings` recovers 0 of them. A planar face
walk reads a shared edge from both sides and returns all three. That is the
whole reason `foundation_plan._faces` exists rather than reusing the slab
chainer.

Two consequences worth keeping:

- The face walk stops wherever the linework was split, so a pad's inner edge
  arrives as two collinear segments and the ring carries a corner the
  foundation does not have. `shapes.simplify_ring` removes those and only those.
- The same machinery covers the Revit-side import, which explodes closed
  polylines into separate lines. The "drawn closed" path is an optimisation for
  the DXF reader, not a dependency.

### Test0 is why a drawing has to prove the convention

Its `S-FNDN` layer holds 187 records of arcs and angled linework that happen to
close into **four** faces, and the drawing carries no foundation note anywhere —
no text layer in it even contains "FND". Placing those four as foundations would
be a worse model than the column-derived guess they replaced. So
`plan_foundations` returns nothing unless at least one outline carries a note,
and Test0 falls back to the old path untouched. One labelled outline vouches for
the rest of the layer, which is what a partially-annotated drawing needs.

## 5. The foundation convention (test10, supplied 2026-08-13; superseded by #8)

| Layer | Content |
|-------|---------|
| `S-FND` | 12 LWPOLYLINE + 8 LINE — footing and raft outlines |
| `S-FND-IDEN` | 19 MTEXT — `F1_1200MM THK` … `F3_1500MM THK\P2000MM FOLD` |
| `S-FND-FOLD` | 6 HATCH (ANSI37) + 6 LINE |
| `S-FND-SUNK` | 1 HATCH (ANSI37) |

Marks F1–F6; thicknesses 800, 1000, 1200, 1500, 2000 mm. A stepped foundation
carries a second MTEXT paragraph after `\P`: `2000MM FOLD`, `1000MM SUNK`.
**6 fold hatches to 6 FOLD labels, 1 sunk hatch to 1 SUNK label** — the
correspondence is exact, so region-to-label pairing is verifiable.

Current classification of these layers:

- `S-FND` → `CATEGORY_UNMAPPED` (no convention pattern matches "fnd").
- `S-FND-IDEN` → excluded from geometry by the `iden` rule, which is right, and
  `classify_text_layer` returns `CATEGORY_TEXT_IGNORE`, which is not.
- `S-FND-FOLD`, `S-FND-SUNK` → unmapped.

No collision with existing categories, so these are additions rather than
changes.

## 6. A second, legend-driven convention exists (test9) — measured in P2.4

The earlier estimate here (600x500 swatches, texts ~2600 mm away) was wrong in
both numbers. Measured with the package's own reader (v0.73.0):

**The sheet is THREE tower plans (3 Boundary + 3 Origin records), and each
carries its own legend block** — 14 rows in all on `PI_TEXT 25`, every one
reading `HATCH INDICATE ...`, plus one near-miss (`*A- INDICATE 20mm CAMBER
TO BE PROVIDED IN BEAM`) that lacks the HATCH prefix and is rightly no row.

| | |
|-|-|
| Swatch rectangles | 807x484 (towers 1–2), 1001x601 (tower 3), 1100x400 (cutout) |
| Text anchor to own swatch centre | 657–947 mm |
| Rows stacked | 617–640 mm apart, so the WRONG row's swatch is 839–1020 mm |
| Nearest PLAN hatch to any legend text | 6622 mm (worst 16140) |
| Nearest non-swatch smalls | 83x83 level markers, 600x75 / 600x125 slivers |

The ~200 mm margin between "own swatch" and "next row's swatch" is why the
pairing is MUTUAL nearest (a missing swatch unpairs its row instead of
stealing the neighbour's), and the 6622 mm floor is the measured form of the
old "mispairs at 5000 mm+" observation — meaning travels by PATTERN, never by
proximity.

**The same pattern means different things per tower**, which the whole-sheet
read must refuse rather than resolve:

| Pattern | Tower 1 | Tower 2 | Tower 3 | Plan hatches (excl. swatches) |
|---------|---------|---------|---------|-------------------------------|
| ZIGZAG | `T.O.S. +50MM.` | `COMPENSATORY STRIP.` | `TOS. +6250.` | 9, all `PI_HATCH` |
| STARS | `T.O.S. +400MM.` | `NON TOWER AREA.` | — | 0 (swatches only) |
| SOLID | three wordings of `.. THROUGH FOUNDATION TO TERMINATION.` | | | 63 `PI_COLUMN HATCH` + 14 `PI_LEVEL` |
| AR-CONC | `COLUMN/SHEAR WALL TERMINATE.` (identical, 3x) | | | 26 `PI_COLUMN HATCH` + 8 `PI_RETAINING WALL HATCH` |
| ANSI32 | — | — | `NON STRUCTURE SHEAR WALL` | 9, all `PI_COLUMN HATCH` |
| ANSI37 | — | — | `STUB SHEAR WALL.` | 0 (its swatch is the only one) |
| ASPHALT | `CUTOUT FOR DOOR ABOVE` (standalone entry) | | | 9, all `PI_SHEAR WALL CUTOUT` |

So `legend.py` reads 14 entries and exactly **one proposal survives** the
ambiguity rule (two meanings for a pattern → no proposal, a loud note) and
the one-layer rule (a proposal is per LAYER, so every plan hatch of the
pattern must sit on one): ASPHALT → cutout on `PI_SHEAR WALL CUTOUT`,
overriding the name convention's "structural wall" (it matches "shear").
That override is a marked, editable row in the dialog and a console line —
never a silent application. AR-CONC/ANSI32/ANSI37 agree with themselves but
carry no actionable kind: kept verbatim, report-only. Reading the legend
PER TOWER (each block is internally coherent) needs the multi-storey split
to happen before the mapping stage; today it happens after, and the refusal
is the honest whole-sheet answer.

**The sign question is OPEN.** Every step value on the sheet is `+` — the
`VIN_LEVEL` spot levels read `+50`, `+400`, `+950`, `+6250`, `+6450`, all
`(T.O.S.)` — and a plan cannot say what the parent slab's own level is, so
`+` cannot be proven to mean raised-above-parent rather than a drop. Step
proposals therefore go to CATEGORY_FOLD whatever the sign, and this entry
records the question instead of the code guessing. A drawing that pairs a
legend step with a section, or uses both signs, would close it.

`+6250` is not a fold — it is a different storey. `legend.legend_steps()`
refuses it through the same `max_step_mm` threshold `fold_plan.plan_steps`
applies (2.3), so the storey case cannot leak in through the legend path
either.

One trap carried over from #7: a saved settings file restores layer combos
by name AFTER the legend proposal seeds them, so an old mapping silently
outvotes the proposal exactly as it outvotes the foundation convention. The
row's `*` marker and tooltip survive; the selection does not.

## 7. A fold support's depth is arithmetic, not a setting

The open question from P1 was which number drives the support's vertical
placement: in the detail first supplied, the slab thickness and the sunk value
were both 350, so the image could not say. The user closed it against a second
detail — a 200 mm slab whose support reads `Height Offset From Level = -200`.
The offset is the **parent's thickness**.

Everything else follows from taking the parent's top as 0:

```
parent soffit         -T_parent
dropped slab top      -d                     (the fold/sunk value)
dropped slab soffit   -(d + T_dropped)
```

A support exists only where there is a **void**: the drop deeper than the
parent is thick (`d > T_parent`), so the dropped slab's top sits below the
parent's soffit and daylight shows between them. Where it does exist it is cast
full height, soffit to soffit — the user's detail shows the 350 drop off a 200
slab cast as one 350-deep support, overlapping the dropped slab's edge:

```
exists  only when  d > T_parent
offset = -T_parent
depth  =  d + T_dropped - T_parent
width  =  T_parent                           (in plan, under the parent)
```

**The condition was wrong once, in an instructive way.** The first cut used
"soffit gap > 0" — `d + T_dropped - T_parent > 0` — which is the same test only
when the dropped slab is thinner than the void is deep. The redrawn corridor
broke it: a 250 sunk bay in a 500 block has a soffit gap of 250, but the
dropped slab's top (−250) sits *above* the block's soffit (−500) — its own side
face already closes the section. The old condition cast two phantom 250 mm
footings inside that solid concrete, and the user found them in Revit against
a drawing that showed nothing there.

Both sunk cases land right under the corrected rule, each for its own reason.
The original F6 (1000 thick, sunk 1000, pads 2000): `1000 < 2000`, no void —
its soffit arithmetic happening to land on exactly zero was that drawing's
coincidence, not the rule. The corridor: `250 < 500`, no void, gap 250 and
still nothing to fill.

Two consequences that fall out of the same reasoning:

- **The parent is read per EDGE, not per region.** A region cut out of its host
  steps down from that host; a region that IS its host steps down from the
  neighbours it abuts, and they can be a different thickness. Reading the host
  in the second case says the strip steps down from itself, which invented the
  support the arithmetic above says is not there.
- **An edge with nothing beyond it gets no support.** F6 abuts a pad on its two
  long sides and open ground on its two short ones. Wrapping concrete round all
  four would hold up nothing on two of them.

### Neighbouring folds pool one support

test10 draws three fold rectangles in a row inside each raft, 300 mm apart. A
collar reaches one parent-thickness past its region, so three separate collars
overlap heavily — Revit reads three intersecting floors where the cast is one
piece. Collars in the same host at the same thickness and offset whose outers
touch therefore pool into ONE slab: its outer edge wraps the whole group (a
rectilinear union walked over a compressed grid, coordinates snapped to the
millimetre so float noise in the drawn corners cannot leave nanometre jogs),
and every fold in the group is a hollow of that one slab. The concrete between
folds belongs to it. test10 builds exactly **two** fold supports — one per
raft — where it built six.

### An opening at the boundary divides the outline

The user's Revit run of v0.69.1: 18 created, 1 error — `Floor.Create` refusing
"curve loops intersect with each other". Validating all 19 planned profiles
offline named the culprit exactly: the corridor block, whose sunk bay spans the
block's **full width**. Its "hole" shares its left and right edges with the
block's own boundary, and two loops sharing edges is not a slab with a hole —
it is two slabs. `split_profile` now subtracts any opening that reaches its
outline's boundary (compressed-grid walk, same machinery as the collar union):
the block arrives as a north piece and a south piece with the dropped slab
between them, all three verified against Revit's own profile rules offline.
Openings strictly inside stay holes; the big raft's seven pass through
untouched.

### Three ways pooling could fail, found by adversarial review

An independent review executed the pooling code against inputs the corpus does
not carry, and confirmed three defects by reproduction; each fix keeps the
review's own scenario as a test.

- **A corner-pinched union spliced its loops.** Four collars whose union
  encloses a courtyard and necks to a point had a degree-4 boundary vertex;
  the ring walk took whichever continuation was listed first, and 6 of the 24
  hatch draw orders spliced the outer ring and the courtyard pocket into one
  figure-eight — net area still positive, so the single-outer guard passed it,
  and Revit would have rejected the sketch, losing the whole support on a
  draw-order lottery. The walk now takes the sharpest RIGHT turn (staying on
  the face it is tracing), corner-only contact no longer counts as touching,
  and a union that still necks to a point is refused with a note — the
  collars stay separate floors, which is what concrete meeting at a corner is.
- **A rectangle with a mid-edge vertex was silently unpoolable.** CAD
  polylines routinely land a vertex mid-edge; the 5-point collar failed the
  4-point rectangle test and dropped out of pooling with no note — quietly
  reintroducing the overlapping-collar defect. Collinear vertices are now
  dropped before the test, and a genuinely non-rectangular collar says so.
- **Pooled hollows were concatenated, not merged.** Two folds drawn
  edge-to-edge arrived as two hole loops sharing a full segment — a tangent
  pair Revit rejects wholesale; a duplicated hatch arrived as two coincident
  holes. Pooled holes now run through the same grid union, dissolving shared
  edges and duplicates into one hollow per connected piece.

### A step note never names an element

The redrawn test10's corridor closed the loop on what a step note means. The
raft is one full rectangle; inside it the engineer drew the corridor's seams
and caps, and the face walk duly returned that interior zone as an outline of
its own. Its only label is `F3_500MM THK / 250MM SUNK` — a STEP note. Read as
an element, it cast two 500 slabs at zero offset over concrete the 750 raft
already provides; the user found them in Revit against a drawing that shows
one raft.

The rule that falls out: **a step note describes the hatched region it sits
in, never the outline round it.** A NESTED outline whose only labels are step
notes dissolves — its ring holes nothing, and its step notes move to the
outline that contains it, which is the element they step. Two boundaries hold
the rule in place: a nested outline with a plain THK note is a real block and
keeps nesting, and a TOP-LEVEL outline with only a step note (the original
F6, which IS its own sunk region) stays the element it always was.

The note's THK field is the DROPPED slab's own thickness — the folds repeat
their raft's 750, but the sunk bay says 500 against a 750 raft, and only the
note can say so. The dropped slab now takes its thickness from its paired
note first, its host second.

### An X across a part means no concrete there

The step-note rule left the corridor half right. Dissolving the zone returned
its strip to the raft — and the raft was then cast SOLID over the whole strip.
The user found the filled corridor in Revit against a drawing that voids most
of it: measured on test10, the strip's north part (10533,15950)–(14033,21650)
and south part (10533,4350)–(14033,10050) each carry TWO diagonal LINEs on
`A-DETL` spanning exactly corner-to-corner — the standard opening symbol —
with the sunk bay between them. The right model: the raft has ONE
corridor-shaped hole, the sunk slab drops into the middle of it, and the
crossed-out parts get nothing.

The rule: a face carrying the X is a CUTOUT — never an element, never a
completer of neighbours through the step-line dissolve, only a hole in the
plan whose ring contains it. Its boundaries:

- **Both diagonals, corner-to-corner** (each end within 50 mm of its corner).
  One slash is a section mark or a leader; an X floating short of the corners
  belongs to whatever detail it is actually drawn over.
- **The strokes are read from the full record set, any layer.** The cross is
  annotation — `A-DETL` maps to no category — so the strokes prove themselves
  by landing on a face's corners, not by where they live.
- **Only a nested face voids.** A top-level outline with an X stays the
  element it is: voiding a whole foundation on the strength of two loose
  lines would delete elements this pass owns on ones it does not.
- **Detection runs BEFORE the step-line dissolve.** The X spans the PART it
  voids, never the merged whole; and with the crossed parts pulled out first,
  the sunk bay between them is left bounded entirely by step linework, which
  the existing refusal already declines to make an outline of. The bay then
  steps the raft the ordinary way — cut, dropped 500 at −250, no support.

Two consequences surfaced on the same drawing. With the corridor cells gone,
the sunk note lands in the raft's own ring almost at its centre — so a plain
note now outranks a step note in sizing (`_size_from`): a step note's THK is
the dropped slab's thickness and must not size the 750 raft, while it still
sizes the original F6, whose only note it is, because there the outline IS
the dropped region. And the raft's profile then carries three tangent loops —
north cutout, sunk opening, south cutout share edges — which Revit rejects
wholesale, so `split_profile` fuses touching holes first (the same
`_merged_holes` walk the collar pooling uses, rectilinear-only for the same
reason): the raft casts as one piece around one corridor hole, seven holes in
all with the six folds.

### A placed footing was never structural

The user compared a placed footing with a hand-sketched twin of it: the
placed one shows blank read-only Width/Length dimensions, the sketched one
reports both -- and BOQ schedules read those fields. Autodesk's help pins the
foundation slab's Width/Length to "if rectangular"; the twins differ not in
their rectangles but in their ROLE. `Floor.Create` places a NON-structural
floor, the Structure tab's tools place structural ones, and the foundation
dimensions belong to the structural element. Every placed footing now sets
FLOOR_PARAM_IS_STRUCTURAL -- which it should have carried anyway, or the
analytical model is missing its foundations -- and hands Revit its sketch the
way the rectangle tool draws one: counter-clockwise from the lowest-left
corner. To be confirmed on the user's next Revit run; if Width/Length still
stay blank, the fallback is schedulable parameters of our own, written from
the rings this tool already measures exactly.

### A storey is not a step

Test9's legend lists `T.O.S. +50MM`, `+400MM` and `+6250` together. The first
two are steps; 6250 is the next floor. A step deeper than 3000 mm is refused and
named — the limit sits above test10's real folds and far below a storey.

### The support is one slab, not a strip per edge (user review, 2026-08-14)

The first cut emitted a support strip per stepped edge — four butting floors
around a mid-footing fold. The office casts ONE collar: a closed band around
the region with the region itself as its hollow; at a corner, one L-shaped
slab around the two inner edges; only a lone stepped edge is a plain strip.
Contiguous stepped edges (same parent thickness, same remaining depth) now
merge into one ring — mitred where it turns, closed with the region's own
edge — and the full cycle closes into the collar with the region as a hole.

### The saved dialog settings can starve the foundation pass

Why the user's Revit run left F6 flat: their saved settings predated the
foundation categories, so the restore carried `S-FND: unmapped` and
`S-FND-IDEN: ignore` over the convention's proposal — no notes were routed,
`plan_foundations` had nothing to vouch for the layer, and the whole pass fell
back to column-derived pads. A saved mapping older than a category silently
wins over the convention that now recognises the layer. The user re-saved
their settings with the foundation rows mapped; the trap remains open for any
other pre-P1 settings file.

## 8. The redrawn foundation level (test10, 2026-08-14)

The user replaced test10's foundation level — the F5/F6 middle was a design
error on the drawing side. The new level:

| What | Drawn as |
|------|----------|
| 8 pads F1/F2/F4 | closed polylines, as before |
| 1 raft F3, 750 thk | boundary closing through two long seams; 6 fold hatches, `1500MM FOLD` |
| 1 corridor block F3, 500 thk | NESTED inside the raft; sides completed by the sunk rectangle; `250MM SUNK` |

Three properties of that linework broke the first recovery, and each got its
own machinery:

- **A seam overshoots a corner by 400 mm.** The junction is a vertex of one
  piece and the middle of the other, so endpoint clustering never unifies it,
  the far end dangles, and pruning removed the whole seam. Segments now split
  wherever another segment's endpoint lands on their body.
- **The block closes only through the SUNK rectangle's sides.** Step-layer
  lines join the face graph — and are then dissolved: two real faces separated
  only by step linework merge, because a fold line marks where a foundation
  steps, never where one ends. A face bounded entirely by step lines is
  refused: that is a step mark, not a footing.
- **The block nests inside the raft.** The inner ring becomes a hole of its
  parent (one level, like slab openings), the parent is cast around it, and
  the block casts as its own slab. A note sizes the SMALLEST ring containing
  it, or the block's `F3_500` note would have sized the raft too.

The sunk arithmetic on the new drawing lands on zero exactly as F6's did on
the old one: the strip's long edges abut the 750 raft, `250 + 500 − 750 = 0`,
no support — while its short edges abut the 500 block and get `250` deep
strips at `−500`. Two drawings, both confirming the soffit-aligned convention.


## 9. The user's region-size setting had never reached the footings

Found while wiring P1.4. `run_builders._create_footings` read
`col_region_max_side_mm` from `selections["limits"]`; the dialog writes it to
`selections["tolerances"]`, which is where the COLUMN pass correctly reads it
from. So the lookup returned None on every run since the setting existed, and
`place_footings` silently fell back to the module default of 1500 mm. Anyone who
changed that number on the Tolerances tab changed their columns and not their
footings, with nothing said either way.

Now read from `tolerances`. Two notes on the consequence:

- For a user who never touched the field the behaviour is identical — the
  dialog seeds it with the same 1500 mm default the fallback used.
- The discard it controls is still right for the column-derived path (a lift
  shaft grown by a projection is not a pad), but it used to discard in silence.
  It now reports the footprint it declined to invent a pad for. A drawing that
  carries its own foundation layer never reaches that path at all, which is the
  real answer to "a raft is bigger than a column".

## 10. Constants an advanced override cannot reach (v0.71.0 registry audit)

`advanced.py` registers only constants their consumers read LIVE — a
module-global looked up at call time, which `advanced.apply` can rebind.
Three candidates from the audit failed that test and are EXCLUDED, not
converted (making them live is its own change with its own regression risk):

- **`slab_graph._COLUMN_RECT_PAD_MM`** — `slab_outlines.py` imports the NAME
  (`from .slab_graph import ... _COLUMN_RECT_PAD_MM`) and consumes the frozen
  copy at both its call sites. Rebinding slab_graph's attribute would change
  nothing anywhere; the exact trap foundation_plan.py warns about beside its
  own tolerances. test_advanced's frozen-import scan now fails any registered
  name that grows such a copy.
- **`slab_labels._ORPHAN_MIN_AREA_M2`** — frozen at function DEFINITION as
  the default of `loops_for_unclaimed_notes(min_area_m2=...)`. The live knob
  already exists: the dialog's `slab_note_min_area_m2`, which run_builders
  passes explicitly.
- **`builders/beams._MIN_BEAM_LENGTH_MM`, `builders/grids._GRID_TEXT_MAX_FT`**
  (and every other builders/* constant) — builders/ imports Revit at module
  level, so the Revit-free registry cannot import them to rebind, and no
  offline test could prove the wiring. Making them tunable means first giving
  them a Revit-free home.

## 11. Test environment

The suite runs green on Linux only after `pip install ezdxf`. The bundled
`lib/py3/numpy` is a Windows wheel whose import calls `os.add_dll_directory`,
absent on Linux, so the bundled `ezdxf` will not load. The DXF regression leg
skips with that message rather than failing.

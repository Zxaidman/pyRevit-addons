# Progress Log — cad2bim

Earlier sessions (v0.36 → v0.68.0) are in main's history; this log restarts on
the post-v0.68.0 roadmap.

## Session 2026-08-13 — roadmap, v0.68.1, phase 0

### Context on entry

- `main` at `12224b7`, cad2bim v0.68.0. Branch
  `claude/cad2bim-roadmap-continuation-ynszsk` created off it.
- v0.68.0 was a pure refactor, confirmed in Revit against v0.67.5.
- Brief said the session harness would name the branch `...-osh3jm`; it created
  `...-ynszsk` and binds to that. Same base commit, same purpose. The branch was
  invisible on GitHub at first because nothing had been pushed to it yet.

### Roadmap agreed

Two open questions closed with the user:

1. **Harnesses before features.** Three of the four regression legs were lost with
   an uncommitted scratchpad, so P0 rebuilds them before any feature lands.
2. **Foundations before walls.** The original recommendation was walls first.
   Displaced: foundations is where the output is most wrong today, and P1's
   hatch/region machinery is a prerequisite for both folds/sunk and openings.

Sequence: P0 harnesses → P1 hatch reader + foundations from CAD → P2 folds/sunk
(slabs and rafts) → P3 walls → P4 openings → P5 round-trip QA → P6 annotation →
P7 rebar. Per-domain quality fixes ride inside the release that touches them.

Written up in `docs/superpowers/specs/2026-08-13-cad2bim-post-v0.68-roadmap.md`.

### Phase 0.5 — type-name matching (v0.68.1)

User hit `The name is already in use for this element type.` on columns.

- Root cause: the "does this type exist?" pre-check used `==`; Revit matches type
  names case- and whitespace-insensitively. Reaching `Duplicate()` at all proved
  the check was stricter than Revit's rule (findings.md #1).
- Audited every site before writing any fix. Seven had the same shape. Beams and
  slabs would have thrown identically. Footings, stairs and the stair waist
  swallowed it and built the wrong geometry in silence.
- `type_names.py`: `key()` normalises, `resolve_type()` returns
  `(type, created, note)`. `created` is the licence to write dimensions, so a
  type the model owns is never resized under the user.
- Also fixed: floor-type lookup scoped to the base type's own system family
  (Floors and Foundation Slabs share `FloorType`); `naming.validate` refuses a
  template that drops a size.
- Tests 419 → 440: unit tests against a fake enforcing Revit's rule, plus two AST
  checks (no bare `.Duplicate(`, no element name compared with `==`).
- Shipped v0.68.1. **User confirmed in Revit: the error is gone.**

### Phase 0 — regression harnesses rebuilt

- `tests/_golden.py` + 12 unit tests — the compare step, the only part with logic.
- `regression_slab_fingerprints`: 29 archived exports, newest per drawing,
  discovered not hard-listed. Wider than the 22 it replaces; five of its drawings
  have no surviving DXF and nothing else watches them.
- `regression_dxf_sweep`: 17 DXFs, full pipeline. Extended mid-build to carry the
  whole slab chain — an export drops the raw text, so note recovery and labels
  can only be driven from a DXF.
- `regression_storeys`: 4 stacks (test9 ×11, test10 ×10, test12 ×5, test13 ×5),
  per-storey, roof called out. test10's roof records `edges=0` — the no-A-FLOR
  case behind the v0.67.2 bug.
- `run_regressions.py` runs all three (~3 min); `tests/README.md` documents the
  two tiers. Legs are `regression_*` so the inner loop stays 452 tests / ~1s.
- Gate proved to bite: a perturbed baseline produced three named failures
  (`StructuralPlan-Test1.dxf.column_rectangles: 62 -> 61`, a moved beam count, a
  dropped fixture). Then a full bless + verify pass: **all 3 legs green against
  the committed baselines.**
- Corroboration that the harness reproduces the real pipeline: the old findings
  recorded "test10 +6 noted bays"; the sweep measures 6.
- Follow-up commit pinned the fingerprint storey by identity rather than index,
  so a re-ordered export cannot silently change what is measured.

### Foundation fixture landed

The user added the foundation level to test10: `S-FND` (12 LWPOLYLINE + 8 LINE),
`S-FND-IDEN` (19 MTEXT, `F3_1500MM THK\P2000MM FOLD`), `S-FND-FOLD` (6 ANSI37
hatches), `S-FND-SUNK` (1). Marks F1–F6, thicknesses 800–2000 mm. Fold and sunk
hatch counts match their label counts exactly. P1's entry gate is met.

### Planning files reset

`task_plan.md`, `findings.md` and `progress.md` closed out on v0.68 and rewritten
onto the new roadmap. `modules_plan.md` left in place but recorded as superseded.

### Phase 1 — the drawing's own foundations

Branch note: the work continues on `claude/cad2bim`, which the session harness
bound to the same commit the `...-ynszsk` and `...-y4s34n` branches held. Same
history, one name from here.

**P1.1 — HATCH in the reader.** Hatches go into a NEW `result.regions`, not into
`records`: a hatch is a region, not a curve, and a curve pipeline handed a few
hundred closed rings would try to make columns out of them. The practical value
of that choice is that the P0 baselines, which count `records`, became a
corpus-wide proof that the change moved nothing. Only the EXTERNAL boundary is
the region — AutoCAD clips a hatch around any label drawn over it, so test10's
folds arrive as three paths each, two of them textbox islands.

**P1.2/P1.3 — layers and labels.** Fold and sunk are matched before foundation,
or `S-FND-FOLD` (which contains "fnd") is swallowed by it. `foundation_labels`
takes `on_foundation_layer` because a BARE thickness is a raft note there and a
slab note anywhere else; the text cannot separate them and must not guess.

**P1.4 — foundations placed from the outline.** `foundation_plan.py` reads the
rings and sizes each from the note inside it; `place_footings(outlines=)` builds
them; the column-offset derivation is now the fallback for a drawing that has no
foundation layer.

Two things drove the design, both discovered by measuring rather than assuming:

- Three of test10's thirteen outlines SHARE their edges (two pads flanking a
  sunk strip, inner edges drawn once). The slab chainer recovers 0 of the three
  because it consumes each segment as it goes. A planar face walk reads a shared
  edge from both sides and returns all three.
- Test0's `S-FNDN` closes into four accidental faces and carries no label
  anywhere in the drawing. So a drawing has to PROVE it uses the convention:
  nothing is planned unless at least one outline carries a note. Test0 falls
  back to the old path untouched.

Cross-checked on the real fixture from two independent directions: 13 outlines,
13 sized, 19 notes every one of them inside a ring, and 6 fold + 1 sunk notes
matching 6 fold + 1 sunk hatch regions exactly.

**P1.5 — the silent discard.** `pads_for` dropped any footprint wider than a
column without a word. The filter is right for the column-derived path; the
silence was not, and it now reports. Bigger find alongside it: the pass read
`col_region_max_side_mm` from `selections["limits"]`, where the dialog never
writes it — so the user's setting had never once reached the footings (findings
#7). Read from `tolerances` now, the same dict the column pass uses.

**P1.6 — the gate.** Ten foundation/region counts added to the DXF sweep. The
baseline diff is **170 pure insertions and zero changed lines** across 17
drawings: every pre-existing measurement is identical, which is the evidence
that reading foundations altered nothing that already worked. Unit tests
486 → 514.

The last four of those are static wiring checks, because the Revit-side half of
P1.4 fails QUIETLY: drop `records`/`texts` at the call and `plan_foundations`
reads an empty drawing, drop `outlines=` and the builder falls back to invented
pads — and either way the run still reports "footings created". `builders/`
imports Revit at module level, so no offline harness can reach it; the check is
an AST read of the call sites, the same way the dialog bindings are pinned.
Proved to bite: breaking each of the four links fails its own test.

### Phase 2 — folds and sunk (2.1–2.3)

**The open question closed.** The user supplied a second Revit detail: a 200 mm
slab whose fold support reads `Height Offset From Level = -200`. So the offset
is the PARENT's thickness, and the rest is arithmetic from the two soffits —
`depth = d + T_dropped - T_parent`, plan width `T_parent` (findings #7). The
earlier detail could not settle it because its slab thickness and sunk value
were both 350.

**The fixture then proved the formula from the other end.** test10's sunk strip
F6: 1000 thick, drops 1000, flanked by 2000-thick F5 pads. `1000 + 1000 - 2000
= 0`, so no support — and none is wanted, because a pad that deep already IS the
vertical face where they abut. Three numbers off the drawing landing exactly on
zero is what says the convention is soffit-aligned rather than assumed. A first
cut that read the thickness off the HOST rather than per edge invented a
1000-deep strip inside solid pad concrete; the fixture caught it immediately.

Two rules fell out of that and both earn their keep on this one drawing:

- The parent is read **per edge**. A region cut out of its host steps down from
  the host; a region that IS its host steps down from its neighbours, which are
  a different thickness.
- An edge with **nothing beyond it** gets no support. The sunk strip abuts pads
  on two sides and open ground on the other two.

`fold_plan.py` plans the three parts; `builders/footings.py` places the dropped
slab and the supports and cuts the region out of its parent. Regions now travel
the pipeline like records: transformed, classified, and split per storey (a fold
belongs to the plan it was drawn on, not to the sheet).

**Measured on test10:** 7 step regions → 7 planned, 0 skipped; 6 folds cut out of
the two F3 rafts with 4 supports each at 2000 deep / `-1500` offset, and the one
sunk strip placed with no cut and no support. Test9's `+6250` is refused by name
as a storey rather than a step. Unit tests 514 → 536.

## Session 2026-08-14 — user review, redrawn fixture, v0.69.0

Four corrections from the user's Revit test, all landed:

1. **Version now moves with every commit.** `__version__` had sat at 0.68.1
   across five commits — a tracking number that doesn't track. 0.69.0 now, and
   the policy is written next to it: bump on every commit that changes the
   package; it is not a release or a tag.
2. **The support is ONE slab, not a strip per edge.** A mid-footing fold gets a
   closed collar with the region as its hollow; a corner fold one L-shaped
   slab; only a lone stepped edge stays a strip. Contiguous stepped edges
   (same parent, same depth) merge, mitred where the run turns.
3. **Why F6 never dropped in Revit:** the user's saved dialog settings predated
   the foundation categories — the restore carried `S-FND: unmapped` /
   `S-FND-IDEN: ignore` over the convention, no notes were routed, and the pass
   fell back to column pads (findings #7). The user re-saved their settings.
4. **Test10's foundation level was redrawn** (the F5/F6 middle was a drawing
   design error). The new level nests a 500-thick corridor block inside a
   750-thick raft, closes the block through the drawn sunk rectangle's sides,
   and overshoots one seam by 400 mm. Three recovery upgrades came out of it:
   split segments where another segment's endpoint lands on them; take step-
   layer lines into the face graph and dissolve them after (they mark where a
   foundation steps, not where one ends — and a face bounded entirely by step
   lines is refused); nest an inner outline as a hole in its parent, with a
   note sizing only the SMALLEST ring containing it.

The redrawn drawing confirms the soffit arithmetic from a second direction:
the sunk strip's long edges abut the 750 raft — `250 + 500 − 750 = 0`, no
support — while its short edges abut the 500 block and get 250-deep strips.
Measured end to end: 10 outlines, 10 sized, 7 steps, 0 skipped. 541 tests.
All three baselines re-blessed — the fixture AND its export changed under
them, so every moved number is the redraw plus the new counts, explained in
the commit.

### Session 2026-08-14 (later) — v0.69.1, the user's Revit test of v0.69.0

Two corrections from the model itself, both structural:

**The phantom 250 footings.** The corridor's sunk bay produced two 250-deep
supports at `-500` that the drawing shows nothing for. The support condition
was "soffit gap > 0" — but with the drop (250) shallower than the block (500),
the dropped slab's top sits ABOVE the block's soffit and its own side face
closes the section; the "gap" the formula measured lies inside solid concrete.
Corrected to the void test: a support exists only when `d > T_parent`. The
original F6's zero was that drawing's coincidence, not the rule — exactly as
the user put it: right convention, "but not always the gap would be zero"
(findings #7).

**Collars pool per group.** Each raft draws its three folds 300 mm apart;
three separate collars reaching 1500 past their regions overlap into three
intersecting floors. Now collars in the same host at the same thickness and
offset whose outers touch merge into ONE slab — outer edge wrapping the whole
group (rectilinear union on a compressed grid, coordinates snapped to the mm
so float noise in the drawn corners cannot leave sub-tolerance jogs), each
fold a hollow of it. test10: **2 fold supports, one per raft**, as the user
specified. Dropped slabs and parent openings are untouched by the pooling.

Support schema `hole` → `holes` (a pooled slab carries several); the builder
adds every hollow as its own CurveLoop. Tests 541 → 549; the sweep's
`step_supports` moves 8 → 2 — six collars pooled into two, the two phantom
strips gone — with every other number identical.

**The 0.69.0 export, and the roof metric it re-pointed.** The user's Revit
test export became the newest test10 export, and its storey stack came back
with the last two entries swapped — `[..., Roof, Terrace]` where every earlier
export had `[..., Terrace, Roof]`. Every per-storey number was identical; only
the positions moved. But the storey leg's roof callout indexed `[-1]`, so it
silently started measuring the terrace and reported `7 → 30` as if the roof
had changed. Same disease the fingerprint leg cured in P0 (`de55430`): an
index where an identity belongs. The roof is now found by its label, the
transposed lists blessed as the export's stored order, and the roof metrics
stayed 0 and 7 — the true statement about the drawing.

### Session 2026-08-14 (later still) — v0.69.3, the corridor's rejected profile

The user's Revit run of v0.69.1/2: 18 created, 1 error, `Floor.Create`
refusing a profile. Offline validation of all 19 planned profiles against
Revit's own rules (closed, planar, non-intersecting loops) isolated it in one
pass: the corridor block, whose sunk bay spans its full width — a "hole"
sharing two edges with its outline's boundary is two slabs, not a slab with a
hole. `fold_plan.split_profile` now divides an outline wherever an opening
reaches its boundary (the collar-union grid machinery, reused); the block
places as north + south pieces around the dropped slab, and all 20 profiles
validate. Interior openings still nest as holes — the raft's seven pass
untouched.

Also per the user's request: builder ERROR lines now print in red
(`_say_error`, an HTML span pyRevit's output window renders), separated from
the skip/note lines that used to share their formatting, across all six
creators. Tests 549 → 553; the sweep gains `foundation_profiles` /
`foundation_outlines_divided` (test10: 11 profiles, 1 divided).

### Session 2026-08-14 (continued) — v0.69.4, the review's three finds

An adversarial review ran the pooling code against inputs the corpus never
draws and confirmed three defects by executing the module (findings, "Three
ways pooling could fail"). All three fixed; each review reproduction is now a
test, including the 24-permutation pinch case proved deterministic. The walk
takes the sharpest right turn at a pinch, corner contact no longer groups,
necked unions are refused with a note, collinear vertices no longer disqualify
a rectangle, and pooled hollows merge through the same grid union instead of
arriving as tangent or coincident loops. Tests 553 → 558; test10's output is
bit-identical (2 supports, 4-point rings) and every baseline stands untouched.

### Session 2026-08-15 — v0.69.5, the corridor was never an element

The user's Revit run of v0.69.4: the raft is right, and two 500 mm slabs at
zero offset flank the sunk bay where the drawing shows plain raft. The
redrawn labels settle it: the corridor's only note is `F3_500MM THK / 250MM
SUNK` — a STEP note, the same family as the fold notes — and a step note
describes the hatched region it sits in, never the outline round it. A nested
outline whose only labels are step notes now DISSOLVES: its ring holes
nothing, its step notes move to the containing element, and the dropped
slab's thickness comes from the note's own THK field (500 out of a 750 raft)
rather than from whichever host happened to contain it. The original F6 —
top-level, its own sunk region — still places, and a nested block with a
plain note still nests; both are pinned by test.

test10 now models as the user specified: one full raft with 7 openings, 8
pads, 6 fold drops, 2 pooled supports, 1 sunk slab at −250 — 18 elements, no
phantom pieces. Tests 558 → 560; the sweep's foundation_planned/profiles move
10→9/11→9 and outlines_divided 1→0, all the dissolved corridor.

### v0.69.6 — placed footings become structural

The Width/Length investigation (findings, "A placed footing was never
structural"): `Floor.Create` defaults to non-structural, the hand-sketched
twin is structural, and the foundation slab's read-only dimensions follow the
structural element. Footings now set FLOOR_PARAM_IS_STRUCTURAL and normalise
their sketch loops. Awaiting the user's Revit confirmation; the declared
fallback is our own schedulable width/length parameters.

### v0.70.0 — the dialog redesigned on the audit's findings

A full audit of the configuration surface (config keys, module constants,
every control and consumer) drove two commits. v0.69.7 fixed its four plain
defects; v0.70.0 is the redesign the user asked for:

Eight tabs, each owning its subject: Layers / Elements / **Foundations**
(new — the footing controls that lived under "Structure", plus the fold-vs-
storey threshold and the minimum outline area, neither of which had a control
at all) / Stairs (Architecture and Staircase merged) / Multi-storey /
Tolerances (gaining the five formerly-unreachable knobs: grid snap, beam pair
overlap, parallel angle, junction and concentric arc tolerances) / Output &
Graphics (materials, grades, filters, JSON export, the compare diagnostic) /
Naming. Every existing control keeps its x:Name, so saved settings files
restore unchanged.

The draw-stairs round trip now carries the WHOLE dialog through
`preset_payload` — it used to silently revert ~45 controls (every tolerance,
limit, material, grade and footing box) to the previous session's snapshot.

Tests 560 → 569, including: eight-tabs-in-order pinned, per-control tab
homes asserted, the seven new tolerance keys seeded-and-emitted (the
max_step_mm dead wire can never come back), and the round-trip payload.
Regression gate green with every baseline untouched.

Still open before the phase closes: brand-guidelines styling, after the user
reviews the layout in Revit.

### Session 2026-08-17 — v0.71.0, raft naming + gated Advanced settings

Two user requests, both landed. Tests 599 → 640; all three regression legs
green against the committed baselines (no measurement moved).

**Raft naming template.** The user asked for "different naming scheme to
Footing and Raft in Naming tabs". `naming.DEFAULTS` gains `raft` ("RAFT {t}
THK") with `raft_type_name()` beside the footing's; validate REFUSES a raft
template that drops {t} (since v0.68.1 a collision is a silent reuse — two
rafts noted 500 and 750 rendering one name would cast the second at the
first's depth; the template is new, so the trap is closed from day one where
the older single-field templates keep their saved latitude). What IS a raft
is decided in the Revit-free layer: `plan_foundations` plans carry `kind` —
"raft" at or above `config.DEFAULTS["raft_min_area_m2"]` (60 m2; test10's
raft ~450, largest pad ~35) OR when the outline carries holes (a footing with
openings cut into it is a raft by construction; judged after `_nest` and
`_hole_cutouts`, which supply the evidence). Column-derived pads are always
"pad". `builders/footings._resolve_type` routes the template on kind and
keys its cache by (kind, thickness); step supports and dropped slabs keep the
footing template (templates of their own are a later item). The Naming tab
gains the "Raft (t)" row; static checks pin the Revit-side routing the same
way P1.6 pinned the call sites.

**v0.71.1 — the storey Level pick means TOP, not base.** v0.70.4 shipped the
Multi-storey table's per-row Level as the storey's BASE; for one version the
pick landed a storey too high. The user's convention is the opposite:
structural elements are drawn below the slab level they support, on the model
and on site, so a storey plan titled "Ground Floor" holds the structure whose
TOP is Ground Floor. The pick now lands as the top; the base is the nearest
model level below it by elevation (test10: the Foundation Level under Ground
Floor), and a pick with nothing below gets a base CREATED one storey height
down, through the ladder's own Level.Create/naming path. "(auto)" rows keep
the positional ladder, and propose_level's name match is unchanged — what it
proposes just lands as the top. Tests 640 → 642.

**Advanced settings, gated and persistent.** New Revit-free `advanced.py`: a
REGISTRY of 19 module tunables (fold_plan probe/same-area, footing_plan depth
step/factors, slab_graph heal/face-area/arc/chamfer/coverage/joint/cell,
floor_plans region/origin/coverage/elevation-cutoff), each with unit, default,
label and a one-sentence `effect` a newcomer can read. Only constants their
consumers read LIVE are registered — the liveness test pins
`effective() == defaults()` (existence + drift) and an ast scan proves no
module froze a copy of a registered name at import. Excluded and noted
(findings #10): slab_graph._COLUMN_RECT_PAD_MM (import-frozen in
slab_outlines), slab_labels._ORPHAN_MIN_AREA_M2 (def-time default; the live
knob is the dialog's slab_note_min_area_m2), and every builders/* constant
(Revit imports at module level). Overrides persist under prefs "advanced",
apply at pushbutton start BEFORE storey detection (floor_plans is a consumer)
and again from the dialog's result so an edit binds on the run it was made
for; they also ride the explicit settings file (schema 1 → 2, optional
section, old files load unchanged). UI: an "Advanced..." button on Output &
Graphics behind a Yes/No gate that states the risk; the window renders the
registry (rows code-built like the layer table) under a warning header, with
Reset-all.

**v0.72.1 — the per-storey level mapping is REMOVED.** The user's Revit test
showed the v0.70.4/v0.71.1 feature destroying the model: with the name-match
auto-assign, a plan whose title matches a ladder-CREATED level name re-anchors
the stack a rung down, and every re-run compounds the shift. Pulled out
entirely — the Multi-storey table's Level column, propose_level,
FloorRegion.level_id and the pick handling in _storey_level_pairs are all
gone (git history keeps them); the positional ladder stands exactly as it
worked before v0.70.4 (`_storey_level_pairs` is byte-identical to the
v0.70.3 version). Tests 648 → 632. A revisit needs a design that survives
re-runs.

### Session 2026-08-17 (later) — v0.73.0, the legend read (P2.4)

**Measured first, built after.** test9 is THREE tower plans on one sheet,
each with its own legend block — 14 `HATCH INDICATE ...` rows on `PI_TEXT
25`. The old findings estimate was wrong twice: swatches are 807x484 /
1001x601 / 1100x400 (not ~600x500) and texts anchor 657–947 mm from the
swatch centre (not ~2600). Rows stack 617–640 mm, so the wrong row's swatch
is 839–1020 mm out — pairing is MUTUAL nearest within a 2500 mm reach and a
200..1500 mm size band, all four numbers drawn from the measurement. The
nearest PLAN hatch to any legend text is 6622 mm: meaning travels by
PATTERN, never proximity.

**`legend.py` (Revit-free): read → propose → legend_steps.** read() pairs
rows; propose() translates to per-LAYER category proposals under two loud
refusals — two meanings for one pattern is ambiguity (test9's ZIGZAG means
`+50MM` / `COMPENSATORY STRIP` / `+6250` across the towers; SOLID and STARS
likewise) and a pattern whose plan hatches span two layers (AR-CONC) cannot
ride a per-layer table. Exactly ONE proposal survives on test9: ASPHALT →
cutout on `PI_SHEAR WALL CUTOUT` (9 hatches, one layer), overriding the
name convention's "structural wall". The pushbutton seeds it into
`default_mapping` BEFORE the dialog, marks the row (`*` + tooltip via
`_build_rows(row_notes=)`), and prints every proposal, report-only meaning
and refusal to the console — proposed, never silent. New CATEGORY_CUTOUT is
consumed like the fold/sunk region categories: a cutout-routed hatch holes
the plan containing it (`plan_foundations(regions=)`, same `_hole_cutouts`
walk as the X-marked faces), and run_builders hands the regions over.

**The storey case cannot leak in through the legend.** `legend_steps()`
returns the per-pattern step depth behind the SAME `max_step_mm` threshold
plan_steps applies; +6250 is refused and named. Depths stop at that
accessor by design — stepping a SLAB from a legend depth is P2-on-slabs,
recorded in task_plan.md rather than half-wired. The sign question (is
`+50` raised or dropped?) is recorded open in findings #6 — every value on
the sheet is `+`, so step proposals go to CATEGORY_FOLD, not to a guess.

Tests 632 → 664 (26 legend, 3 cutout-region, 3 dialog-wiring pins); sweep
gains `legend_entries` / `legend_proposals` (test9: 14 / 1, all else 0 —
the re-blessed baseline moved exactly those 34 lines); full gate green.

### Session 2026-08-18 — v0.74.0, hatches map on their own table

**The user's explicit instruction: HATCH layers get a mapping of their own,
apart from geometry and text.** v0.69.7 had merged hatch-only layers into
the GEOMETRY rows, so routing a hatch could re-route linework on a
like-named layer. Now the Layers tab carries a third table ("Hatch layers →
region meaning", `hatch_rows`, same brand-styled row builder), fed ONLY
from `dxf_result.regions`; the geometry rows are records-only again.
`classify/layers.py` gains `HATCH_CATEGORIES` (column fill / fold / sunk /
cutout / unmapped), `classify_hatch_layer` (exclusions first, then
fold/sunk/cutout/col tokens — a cutout token is SAFE here because routing a
hatch layer never moves linework, the exact fear that kept it out of the
geometry convention) and `build_default_hatch_mapping`; `classify_layer` is
untouched. LEGEND proposals seed the HATCH mapping now (a legend describes
hatches) and their `*`-marked rows moved with them; the run applies
`selections["hatch_mapping"]` to regions — regions never consult the
geometry mapping. Settings schema 2 → 3 adds the optional `"hatches"`
section (own accessor `hatch_mappings()`, the advanced precedent: the
`sections()` three-tuple keeps its shape; older files load unchanged) and
the draw-stairs preset round-trips it via the same capture/restore path.
The sweep classifies regions through the hatch convention now.

Tests 664 → 679 (7 hatch-convention, 5 hatch-table wiring, 3 settings);
full gate green with NO baseline movement — fold 6 / sunk 1 (test10) and
every other count identical, the fold/sunk/cutout/col tokens carry over
exactly.

### Open

- P2.4 remainder: `legend.legend_steps()` has no consumer yet (legend-driven
  slab stepping is P2-on-slabs), and a per-tower legend read — each block is
  internally coherent — needs the multi-storey split to run before the
  mapping stage. The step-sign question is open in findings #6.
- The fold construction is unverified in Revit since the support rework — the
  collar/L representation and the redrawn corridor both await the user's next
  run on the real model.
- A saved settings file from before P1 silently unroutes the foundation layers
  (findings #7). The user's own copy is fixed; the dialog does not yet warn
  when a restored mapping downgrades a layer the convention recognises. The
  same restore now also outvotes a LEGEND proposal (it lands after the
  seeding — findings #6): the row's marker survives, the selection does not.
- `graphify-out/` is 18 versions stale (built at `56c2d6a`, v0.50.0) and contains
  none of the twenty post-refactor modules. Documentation, not a gate.

# cad2bim — todo list

The queue. Everything not yet confirmed in Revit lives here, and nothing leaves except by
reaching `done` — at which point it is written into `done-list.md` with what was actually done.
Nothing is deleted to make the list look shorter.

**Anything new is recorded here first.** A requirement, a bug, an idea — it gets an ID in this
file before it is built, argued about, or written into any other document. Standing instruction
from the project owner, and it is what keeps this list the queue rather than a summary of one.

Current build: **v0.76.0** (`85205db`, branch `claude/cad2bim`). 714 unit tests, 3 regression
legs green. Longer records: `../../../../../task_plan.md`, `findings.md`, `progress.md` at the
repository root.

## Sections

| § | Section | What belongs in it |
| --- | --- | --- |
| 1 | **Critical** | Blocks the other implementation. Nothing ships until every one is closed or deliberately deferred. |
| 2 | **Errors and bugs** | Something is wrong now. Each carries how it was found and whether it is reproduced. |
| 3 | **Features** | New capability. Each is separable and can be scheduled on its own. |
| 4 | **Working now** | What is built and verified, so nobody rebuilds it and nobody claims more than was measured. |
| 5 | **Pending scope** | Agreed direction, not yet started. |
| 6 | **Owner's list** | Reserved for what the project owner sends next, and everything after. |

**Every entry has an ID** (`CRIT-1`, `BUG-3`, `FEAT-7`) so it can be referred to in one word.

## Phases

| Phase | Meaning |
| --- | --- |
| `pending` | Not started. |
| `building` | Being written now. |
| `testing` | Built and in a build the project owner can test; waiting for the in-Revit result. |
| `superseded` | It worked, and something else replaced it. Recorded rather than deleted — what it cost to build is part of the record. |
| `done` | Confirmed in Revit, and copied into `done-list.md` with what was done. |

---

## 1. Critical

### CRIT-1 — One wall is drawn on two conventions, and both now build · `pending`

**Found:** measured in the P3a corpus survey, findings #12. **Reproduced:** offline, in the
planner. test8's 250 mm `S-RCC-WALL` quad carries a 150 mm arch `wall` trace 50 mm off its
centreline (250/2 − 150/2 = 50) — the two drawings share one face and disagree about the other.
The two kinds are planned by separate passes that cannot see each other, so since v0.76.0 both
plan **and both place**: two overlapping walls at that spot in Revit.

**Blocks:** P4 openings (a door needs one host, not two), and any wall count the owner reports
from test8.

**Needs from the owner:** which convention wins when both name the same wall — and whether the
loser is dropped in the planner (never planned) or the builder (planned, reported, not placed).
The only same-kind coincidences in the corpus are three drawn nibs (100–151 wide, 250–410 long
closed rings sitting on longer runs); those are drawn geometry and stay.

### CRIT-2 — Lift/stair core walls still place as thin COLUMNS · `pending`

**Found:** carried deliberately from P3b. `report.py` → `shapes.recover_core_walls` pairs the
opposing faces of a fragmented core and emits `recovered_core_wall` rectangles, which
`builders/columns.py` places as long thin columns — the stand-in P3 exists to replace. P3b did
not move it: **column counts have not moved and must not until this is decided**, because moving
them changes column and wall counts together.

**Blocks:** P4 (an opening in a core wall has no wall to host it), and the element counts of every
drawing whose core is fragmented (test18-era drawings, Project1).

**Needs from the owner:** the verdict on P3b's walls in Revit first. If the placed walls are right,
the core recovery feeds `wall_plan` instead of the column pass and both baselines move in one
commit, attributed.

### CRIT-3 — A saved settings file silently outvotes the conventions · `pending`

**Found:** the owner's Revit run left F6 flat against a drawing that labels it. **Reproduced and
root-caused** (findings #7): the dialog restores layer combos by name **after** the convention
proposes, so a mapping saved before a category existed (`S-FND: unmapped`, `S-FND-IDEN: ignore`)
wins; no notes are routed, `plan_foundations` has nothing to vouch for the layer, and the whole
foundation pass falls back to column-derived pads. Since v0.73.0 the same restore also outvotes a
**legend** proposal — the row's `*` marker and tooltip survive, the selection does not
(findings #6).

**Blocks:** trusting any bug report from a machine carrying an old settings file. The symptom is a
silently wrong model with no error printed — the failure mode this project treats as worse than a
crash.

**Needs:** FEAT-1 (the warning). Until then: when a foundation or legend result looks wrong, check
the settings file before the code. The owner's own copy was re-saved and is fixed; the trap is open
for every other pre-P1 file.

---

## 2. Errors and bugs

### BUG-1 — Placed footings' Width/Length: fixed, unconfirmed · `testing`

**How found:** the owner compared a placed footing against a hand-sketched twin — the placed one
showed blank read-only Width/Length, the sketched one reported both, and BOQ schedules read those
fields. **Reproduced:** yes, in Revit by the owner. Root cause: `Floor.Create` places a
NON-structural floor; the foundation dimensions belong to the structural element.

**Fix shipped v0.69.6** — every placed footing sets `FLOOR_PARAM_IS_STRUCTURAL` and hands Revit its
sketch the way the rectangle tool draws one (counter-clockwise from the lowest-left corner).
**Waiting on:** the owner's next Revit run. If the fields stay blank, the fallback is schedulable
parameters of our own, written from the rings this tool already measures exactly.

### BUG-2 — The bundled `lib/py3` ezdxf will not import on Linux · `pending`

**How found:** running the regression gate outside Windows. **Reproduced:** every run. The bundled
`numpy` is a Windows wheel whose import calls `os.add_dll_directory`, which does not exist on Linux,
so the bundled `ezdxf` cannot load. The DXF leg **skips with that message** rather than failing, and
`pip install ezdxf` restores it. Windows/pyRevit — the actual target — is unaffected, which is why
this is recorded rather than fixed (findings #11).

### BUG-3 — `graphify-out/` is 18 versions stale · `pending`

**How found:** the v0.76.0 documentation sweep. **Reproduced:** yes — it was generated at
`56c2d6a` (v0.50.0) and contains none of the twenty modules the v0.68.0 refactor created, nor any
of the P1–P3 modules. Documentation only; no build reads it, so it is not a gate.

---

## 3. Features

### FEAT-1 — Warn when a restored mapping downgrades what the convention recognises · `pending`
Closes CRIT-3's silent path. The dialog knows both the proposal and the restored value at the moment
it overwrites one with the other; today it says nothing. A marked row and a console line would make
a stale settings file visible instead of mysterious. Covers the legend case too (a proposal that is
seeded and then overwritten keeps its `*` and loses its selection).

### FEAT-2 — Folds and sunk on SLABS, not only foundations · `pending`
`fold_plan.plan_steps` runs for foundations only. A fold or sunk hatch drawn over a slab is read,
classified and counted, and then nothing steps it. The machinery is shared and Revit-free, so this
is wiring plus a regression pass rather than new geometry.

### FEAT-3 — Consume `legend.legend_steps()` · `pending`
2.4 delivers the per-pattern step DEPTH behind the same 3000 mm threshold `plan_steps` applies
(test9's `+6250` is refused and named wherever depths flow), and **no pass reads it yet**. Depends
on FEAT-2: stepping a slab from a legend depth is P2-on-slabs territory.

### FEAT-4 — Read the legend per tower, after the multi-storey split · `pending`
test9's sheet is three tower plans, each with its own legend block, and each block is internally
coherent. The whole-sheet read rightly refuses the patterns that mean different things per tower
(ZIGZAG, STARS, SOLID) — a per-tower read would resolve them honestly. It needs the split to hand
regions per plan to the mapping stage; today the mapping runs before the split.

### FEAT-5 — Naming templates for the step support and the dropped slab · `pending`
Both take their host's name today. Footings and rafts got their own templates in v0.71.0 on exactly
this argument — a name that encodes a size must be able to differ when the size does.

### FEAT-6 — Per-storey level mapping (name-match auto-assign, base below top) · `superseded`
Built v0.70.4, corrected v0.71.1 to the owner's convention (structure is drawn BELOW the slab it
supports, so a plan named "Ground Floor" TOPS OUT there and the base sits below). **Removed at
v0.72.1 on the owner's order** — "our level mapping in storey is destroying the model" — because
name-match auto-assign re-anchored the stack onto ladder-created levels and re-runs compounded the
damage. What replaced it is the plain positional ladder it had displaced, verified byte-identical
to its pre-feature form. Recorded, not deleted: the convention it encoded is still right, and
FEAT-7 is the way back.

### FEAT-7 — Re-run-safe redesign of the storey level mapping · `pending`
The requirement stands (the owner stated the convention twice); only the implementation was wrong.
A redesign has to be idempotent: running the tool twice on the same model must produce the same
levels, not a second ladder anchored to the first.

### FEAT-8 — Architecture beyond walls · `pending`
The Architecture sub-tab carries arch walls and a roofs note. Roofs, and whatever else the owner
wants under it, are unbuilt.

### FEAT-9 — The module constants the Advanced door still cannot reach · `pending`
`advanced.py` registers the 19 constants whose consumers read them LIVE, which is what makes an
override provable. findings #10 names three that failed that test and were excluded on purpose:
`slab_graph._COLUMN_RECT_PAD_MM` (imported by name, so the consumer holds a frozen copy),
`slab_labels._ORPHAN_MIN_AREA_M2` (frozen at function definition; a live dialog knob already
exists), and every `builders/*` constant (that package imports Revit at module level, so no
Revit-free registry can rebind it and no offline test could prove the wiring). Each needs its own
change with its own regression risk.

### FEAT-10 — The eight-tab dialog · `superseded`
Shipped v0.70.0 after the dialog audit, replaced within the day by the owner's own layout: a Build
tab with element sub-tabs (v0.70.1), fixed at exactly five — General / Structure / Architecture /
Foundation / Staircase, grids inside General (v0.70.4). Six top-level tabs today. The audit work it
carried (roughly forty settings that existed in code and nowhere in the dialog) survived into the
current layout and into FEAT-9.

---

## 4. Working now

What is built and verified. Nothing here claims more than was measured.

| ID | Capability | Phase | What was actually verified |
| --- | --- | --- | --- |
| WORK-1 | Columns — rect, round, rotated, blade, fused, clipped, schedule- and label-sized | `done` | The owner's Revit rounds v0.14–v0.24; every recovery answers a named case in a real drawing |
| WORK-2 | Beams — sized from labels, curved, sloped, split at columns, perimeter recovery | `done` | The owner's Revit rounds v0.25–v0.34 |
| WORK-3 | Slabs — drawn edges, placed-member faces, note recovery, openings, arcs | `done` | The owner's Revit rounds v0.35–v0.45; the 14.4 mm misalignment closed at v0.45.0 |
| WORK-4 | Staircases — dog-leg, L, circular, winders, drawn linework or text, waist, landings | `done` | The owner's Revit rounds v0.46–v0.62 |
| WORK-5 | Grids, levels, naming templates, standard sizes | `done` | v0.61–v0.62; naming re-checked at v0.67.1 |
| WORK-6 | Materials, grades, view filters, progress bars, JSON export | `done` | v0.63–v0.67 |
| WORK-7 | Multi-storey from one DXF, storey stack, per-storey build | `done` | v0.51, v0.66.1; the roof leg pinned by label at v0.69.2 |
| WORK-8 | Type names matched the way Revit matches them | `done` | The owner confirmed the duplication error gone (v0.68.1); two AST checks keep the shape from returning |
| WORK-9 | Regression gate — 3 legs, 714 unit tests | `done` | 29 archived exports, 17 fixture DXFs, 4 storey stacks; proved to bite (a perturbed baseline produced three named failures) |
| WORK-10 | Foundations from the drawing — outlines, notes, rafts, pads, nested blocks | `done` | The owner in Revit: "good we made proper raft on test10". Measured: 9 outlines + 2 cutouts, the raft one piece with 7 holes, 18 foundation-level elements |
| WORK-11 | X-cross cutouts — an X across a nested face means no concrete there | `done` | The owner's Revit run drove it; the corridor now voids where it is crossed out |
| WORK-12 | Folds and sunk — parent cut, dropped slab, pooled support collars | `testing` | Arithmetic given by the owner and twice corrected against their Revit runs (void rule `d > T_parent`; one support per fold GROUP — test10 measures exactly 2). The collar/L representation and the redrawn corridor have not been re-checked in Revit since the rework |
| WORK-13 | Legend reading — swatch pattern → legend text → meaning, proposed never silent | `testing` | Measured offline on test9: 14 rows across three tower legends, exactly ONE proposal survives the ambiguity and one-layer rules (ASPHALT → cutout on `PI_SHEAR WALL CUTOUT`) |
| WORK-14 | Hatch mapping on its own table, apart from geometry and text | `testing` | 495 regions across the owner's test9 + test10 exports, 0 degenerate rings; gate moved nothing (fold, sunk and column routing identical under both conventions) |
| WORK-15 | Walls — planner and builder | `testing` | Planned offline: Project1 17 segments / 11 skips, test8 178 / 110, test9 19 / 39; the other 14 fixtures pin zeros. Placed as `DB.Wall` since v0.76.0, **not yet seen in Revit** |
| WORK-16 | The dialog — six tabs, five Build sub-tabs, AnonGee brand, gated Advanced, saved settings | `done` | The owner in Revit: "tested all good, apply the AnonGee Brand Guidelines design to all cad2bim dialog now", then applied and re-confirmed |
| WORK-17 | Errors print red on the console; skips are named, never silent | `done` | The owner's instruction, shipped v0.69.3 and extended to all six creators |

---

## 5. Pending scope

Agreed direction, not yet started. Detail lives in
`docs/superpowers/specs/2026-08-13-cad2bim-post-v0.68-roadmap.md`.

| ID | Scope | Phase | Depends on |
| --- | --- | --- | --- |
| SCOPE-1 | **P4 Openings** — doors, windows, shafts | `pending` | The hatch reader (done, P1.1) and P3's hosts — CRIT-1 and CRIT-2 first |
| SCOPE-2 | **P5 Round-trip QA** — the built model against the source DXF, delta reported | `pending` | Enough of the model to be worth diffing |
| SCOPE-3 | **P6 Annotation** — dimensions, tags, views, sheets | `pending` | P5 |
| SCOPE-4 | **P7 Rebar** — feeding `Dev.panel/BBS Generator.pushbutton` | `pending` | P4 |
| SCOPE-5 | **The step SIGN question** | `pending` | A drawing. Every step value on test9 is `+` (`+50`, `+400`, `+950`, `+6250`, `+6450`, all `T.O.S.`), and a plan cannot say what the parent slab's own level is — so `+` cannot be proven to mean raised rather than dropped. Step proposals go to fold whatever the sign, and the question stays recorded instead of guessed. A drawing that pairs a legend step with a section, or uses both signs, closes it |

---

## 6. Owner's list

Reserved for what the project owner sends next, and everything after. Each item gets its own ID
here as it arrives, then moves into §1, §2 or §3 once it is understood well enough to be worked.

| ID | Item | Phase |
| --- | --- | --- |
| OWN-1 | The owner's report on the v0.76.0 build — "this test still have few bugs and errors", not yet sent in detail. Nothing is guessed at in advance; each reported symptom is filed here first, with how it was found, then triaged | `pending` |

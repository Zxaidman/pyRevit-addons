# cad2bim roadmap after v0.68.0

Agreed 2026-08-13. This is the durable record of the sequencing decision; the
working checklist lives in `task_plan.md`.

## Where this starts

v0.68.0 was a pure refactor — four oversized modules became twenty, no behaviour
change, verified in Revit against v0.67.5. Every element domain (columns, beams,
slabs/footings, stairs/levels/naming) is workable and none is at 100%. Four new
capabilities are wanted: walls as real `DB.Wall`, openings, annotation, and
round-trip QA plus rebar feeding the BBS Generator. Foundations from CAD and
folds/sunk were added to that list during this session.

## The sequencing decision

Two questions were open. Both are now closed.

**Harnesses before features.** Three of the four regression legs named in the old
`findings.md` had been written into an uncommitted scratchpad and were lost.
Without them "no regressions" is an assertion, not a measurement — and the very
next release changes geometry across every domain. Rebuilding them is P0.

**Foundations before walls.** The original recommendation was walls first, on the
grounds that they unblock openings. It was displaced because foundations is where
today's output is most wrong: footings are invented from column offsets rather
than read from the drawing, and rafts cannot exist at all — `builders/footings.py`
explicitly discards any footprint too large to be a column. Foundations also
builds the hatch/region/legend machinery that folds/sunk and openings both need,
so doing it first shortens the two phases after it.

Per-domain quality fixes ride inside the release that touches that domain, rather
than being collected into a separate quality phase.

## Phases

| # | Release | State |
|---|---------|-------|
| P0.5 | Type-name matching fix | **shipped v0.68.1** |
| P0 | Regression harnesses rebuilt as committed code | **done** |
| P1 | Hatch/region reader + foundations from CAD | next |
| P2 | Folds and sunk, on slabs and rafts | |
| P3 | Walls as real `DB.Wall` | |
| P4 | Openings — doors, windows, shafts | |
| P5 | Round-trip QA — built model vs source DXF delta | |
| P6 | Annotation — dimensions, tags, views, sheets | |
| P7 | Rebar feeding the BBS Generator | |

### P0.5 — type-name matching (shipped)

The "does this type exist?" pre-check compared names with `==`; Revit compares
them case- and whitespace-insensitively. A family holding Revit's own
`400 x 600` asked for the toolkit's default `400 X 600` therefore duplicated,
and Revit refused. Seven sites had the shape. Columns, beams and slabs threw;
footings, stairs and the stair waist swallowed it and built the wrong geometry in
silence. `type_names.py` normalises the comparison, turning a clash into a reuse.

### P0 — regression harnesses (done)

Three legs, committed under `tests/`, ~3 minutes total, run by
`tests/run_regressions.py`:

- `regression_slab_fingerprints` — 29 archived Revit exports, newest per drawing.
  Five of those drawings have no surviving DXF; this is all that watches them.
- `regression_dxf_sweep` — the 17 fixture DXFs through the full pipeline,
  including note recovery and slab labels.
- `regression_storeys` — 4 storey stacks, per-storey numbers, roof called out.

The unit suite stays the inner loop at 452 tests / ~1s.

Baselines were measured at v0.68.1, not recovered — the originals cannot be
reproduced. What they defend is drift from here.

### P1 — hatch/region reader + foundations from CAD

Two things at once because the second cannot be tested without the first.

**The reader gap.** `readers/dxf_reader.py::_geometry_record` handles
LINE/ARC/CIRCLE/POINT/LWPOLYLINE/POLYLINE/ELLIPSE/SPLINE. There is no HATCH
branch, so every hatch in every fixture is discarded today — 276 in test10, 360
each in test4/test5, 228 in Project1. Hatch reading is the shared prerequisite
for P1, P2 and P4.

**Foundations today are invented.** `footing_plan.pads_for(sections, ...)` reads
only column rectangles and circles, grows them by a projection, and merges
overlaps. Nothing is read from the drawing. `builders/footings.py`
`_MAX_COLUMN_MIN_SIDE_MM` discards anything larger than a column, so a raft is
structurally impossible to produce.

**What the drawing actually provides** (test10, foundation level, supplied
2026-08-13):

| Layer | Content | Meaning |
|-------|---------|---------|
| `S-FND` | 12 LWPOLYLINE + 8 LINE | footing and raft outlines |
| `S-FND-IDEN` | 19 MTEXT | `F3_1500MM THK\P2000MM FOLD` |
| `S-FND-FOLD` | 6 HATCH (ANSI37) + 6 LINE | fold regions |
| `S-FND-SUNK` | 1 HATCH (ANSI37) | sunk region |

Marks run F1–F6 with thicknesses 800/1000/1200/1500/2000 mm. Where a foundation
steps, the MTEXT carries a second paragraph after `\P` giving the depth and the
word FOLD or SUNK. The hatch count matches the label count exactly — 6 folds, 1
sunk — so region-to-label pairing is verifiable rather than assumed.

Scope:

1. HATCH support in the DXF reader — boundary paths as rings, pattern name kept.
2. New layer categories: foundation outline, foundation text, fold, sunk.
3. Parse `F<n>_<t>MM THK` and the `\P<d>MM FOLD|SUNK` continuation.
4. Footings and rafts placed from the CAD outline, thickness from the label —
   replacing the column-offset derivation, which becomes the fallback for a
   drawing with no foundation layer.
5. Quality fixes riding along: the `col_region_max_side_mm` discard that makes
   rafts impossible, and the silent footing fallbacks reported in P0.5.

Entry gate: the fixture is in the repo, so P1 is unblocked.

### P2 — folds and sunk

Applies to slabs **and** rafts.

Representation, decided: **a separate floor at an offset, with the region cut as
a hole in the parent.** `builders/slabs.py::_nest_openings` already turns a
ring-inside-a-ring into an inner `CurveLoop`, and `builders/footings.py`
`_zero_offset` already drives the height parameter, so this reuses code that is
already fingerprinted rather than introducing `SlabShapeEditor` — which has no
offline representation and therefore cannot be covered by the P0 harnesses.

A magnitude threshold is required regardless of representation: Test9's legend
carries `T.O.S. +50MM`, `+400MM` and `+6250`. 6250 mm is not a fold, it is a
different storey, and must route to its own level or be reported and skipped.

Legend-driven mapping, for drawings that use Test9's convention rather than
test10's explicit layers: a legend swatch's pattern maps to a meaning via the
nearest legend text, and every plan hatch of that pattern inherits it. Proximity
alone mispairs at distance, so this must auto-propose into the existing override
dialog rather than apply silently.

### P3–P7

- **P3 walls.** Today `geom/shapes.py::recover_core_walls` emits walls as column
  entries — status `recovered_core_wall` — so a wall is placed as a long thin
  column. Replacing that with real `DB.Wall` is the largest single correctness
  gain left, and it gives openings something to host.
- **P4 openings.** Doors, windows, shafts. Needs P1's hatch reader and P3's
  hosts. Test9 already carries `PI_CUTOUT` (174 entities) and a legend entry
  reading `HATCH INDICATE CUTOUT FOR DOOR ABOVE`.
- **P5 round-trip QA.** Built model versus source DXF, as a delta report. Runs
  inside Revit, so it complements the P0 harnesses rather than replacing them.
- **P6 annotation.** Dimensions, tags, views, sheets.
- **P7 rebar.** Feeding the existing BBS Generator at
  `Dev.panel/BBS Generator.pushbutton`.

## Standing constraints

- Every release runs `tests/run_regressions.py` before shipping. A moved number
  is not automatically a bug, but it must be explained in the commit that moves
  it, and the baseline re-blessed deliberately.
- `pip install ezdxf` is needed on Linux. The bundled `lib/py3` copy is a Windows
  build whose numpy calls `os.add_dll_directory`.
- `graphify-out/` was last built at `56c2d6a` (v0.50.0) and contains none of the
  twenty post-refactor modules. Refresh with `/graphify . --update --wiki` when
  convenient; it is documentation, not a gate.
- `modules_plan.md` is an older toolkit-wide refactor plan, superseded by this
  document and by the v0.68.0 refactor it describes.

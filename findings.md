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

## 5. The foundation convention (test10, supplied 2026-08-13)

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

## 6. A second, legend-driven convention exists (test9)

Test9's `PI_TEXT 25` layer carries a legend whose entries read:

```
HATCH INDICATE T.O.S. +50MM.
HATCH INDICATE T.O.S. +400MM.
HATCH INDICATE TOS. +6250.
HATCH INDICATE CUTOUT FOR DOOR ABOVE
HATCH INDICATE COLUMN/SHEAR WALL THROUGH FOUNDATION TO TERMINATION.
```

Legend swatches are 600x500 hatch rectangles sitting ~2600 mm from their text, so
the mapping is swatch pattern → legend text → meaning, inherited by every plan
hatch of that pattern. Nearest-text pairing mispairs at distance (observed at
5000 mm+), so it must auto-propose into the override dialog rather than apply
silently.

`+6250` is not a fold — it is a different storey. A magnitude threshold is
required in P2 whatever the representation.

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

The support is the concrete between the two soffits:

```
offset = -T_parent
depth  =  d + T_dropped - T_parent           (nothing to fill when <= 0)
width  =  T_parent                           (in plan, under the parent)
```

**The fixture proves the formula from the other end.** test10's sunk strip F6
is 1000 thick, drops 1000, and is flanked by F5 pads 2000 thick:

```
1000 + 1000 - 2000 = 0
```

No support — and none is wanted, because a pad 2000 deep is already the whole
vertical face where the two abut. Three numbers taken off the drawing landing
exactly on zero is not luck; it is the drawing telling us the convention is
soffit-aligned. Had the rule been "the support is always `d` deep", F6 would
have been given a 1000-deep strip inside solid pad concrete.

Two consequences that fall out of the same reasoning:

- **The parent is read per EDGE, not per region.** A region cut out of its host
  steps down from that host; a region that IS its host steps down from the
  neighbours it abuts, and they can be a different thickness. Reading the host
  in the second case says the strip steps down from itself, which invented the
  support the arithmetic above says is not there.
- **An edge with nothing beyond it gets no support.** F6 abuts a pad on its two
  long sides and open ground on its two short ones. Wrapping concrete round all
  four would hold up nothing on two of them.

### A storey is not a step

Test9's legend lists `T.O.S. +50MM`, `+400MM` and `+6250` together. The first
two are steps; 6250 is the next floor. A step deeper than 3000 mm is refused and
named — the limit sits above test10's real 2000 mm fold and far below a storey.

## 8. The user's region-size setting had never reached the footings

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

## 9. Test environment

The suite runs green on Linux only after `pip install ezdxf`. The bundled
`lib/py3/numpy` is a Windows wheel whose import calls `os.add_dll_directory`,
absent on Linux, so the bundled `ezdxf` will not load. The DXF regression leg
skips with that message rather than failing.

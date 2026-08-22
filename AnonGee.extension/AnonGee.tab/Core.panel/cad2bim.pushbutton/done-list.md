# cad2bim — done list

What was built and confirmed, from the first CAD-to-BIM commit to **v0.76.0**. An item arrives here
only by reaching `done` in `todo-list.md`, and it is described here with what was actually done.

**How "confirmed" is used below.** Before v0.68.0 there was no regression gate: each version answers
the previous version's Revit feedback from the project owner, and that round IS the confirmation —
it cannot be re-run today. From v0.68.1 on, every entry is additionally held by
`tests/run_regressions.py` (3 legs) and the unit suite, so a claim here can be re-checked. Where an
entry says *measured*, the number is reproducible from the fixtures in the repository.

Version numbers are tracking numbers, not releases: the stamp in
`lib/py3/anongee_toolkit/cad2bim/__init__.py` moves with every commit that changes the package, so
"v0.69.2 did X" names exactly one commit.

---

## A. Groundwork — the tool exists at all

| ID | What was done | Version / commit | Confirmed by |
| --- | --- | --- | --- |
| DONE-1 | CAD-to-BIM conversion tool with its own UI, inside the AnonGee extension | `052d732` | The owner's first runs |
| DONE-2 | DXF-pick entry point, ezdxf hybrid extraction, text-driven sizing | `6b7482f` | Owner round |
| DONE-3 | Made CPython3-compliant per the Brand Guidelines — no pyRevit IronPython modules anywhere in the library; windows built with `XamlReader.Load` | `6768414` | Runs on the pyRevit CPython3 engine |
| DONE-4 | CPython3 crash fixes: `WarningSwallower` needs `__namespace__`; the attach hardened against engine quirks; ezdxf imported lazily so the real import error surfaces; health-check detects namespace/partial installs | `1d02d0d`, `618ae73`, `cc0ccce`, `4be5c40` | Owner rounds |
| DONE-5 | Stage-gated the build to grids-only and wrote the staged rebuild roadmap — nothing else placed until each stage was proven | `25238e2` | Owner agreed the sequencing |
| DONE-6 | Tabbed dialog with a Units & Tolerances tab, compact JSON export, link view options | `57fb3bf` | Owner round |
| DONE-7 | Build from the Revit LINK geometry and use the DXF for text only — the source split the rest of the tool still rests on | `9f762d4` | Owner round |
| DONE-8 | Grid-anchored text transform; text layers exposed in the dialog and kept out of sizing | `fbb0c49` | Owner round |
| DONE-9 | Verify a commit actually persisted, and report silent rollbacks truthfully instead of claiming success | `c5cef06` | Owner round; the honesty rule the console still follows |
| DONE-10 | `anongee_toolkit` subpackage structure with a public API, and a 92-test mock-based verification suite — the first tests in the project | `f7bfef0`, `16836fe` | 92 tests, 0 failures |

## B. Columns (v0.14 → v0.24)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-11 | Layer-routed text correction for columns, plus a text-layer mapping UI | `eb88be9` | Owner round |
| DONE-12 | Snap text-corrected columns to the grid; extract grid names from text | `aacd8a3` | Owner round |
| DONE-13 | Generalised correction to mark-only labels, with a schedule, stamping the Mark parameter | `e218f04` | Owner round |
| DONE-14 | DXF column-schedule parser — inline sizes and tabular `Mark｜W｜L｜H` schedules | `8ae8fa1`, `352b090` | Owner round |
| DONE-15 | Stopped fusing separate columns sitting on grids ~1500 mm apart | `e66fe0e` | Owner round (the bug it answers) |
| DONE-16 | Recovered beam-column junction columns instead of forging slivers (cases I5/I7); junction-clipped columns recovered from fragmented outlines (F9) | `71be987`, `31cae35` | Owner round |
| DONE-17 | Recovered fused wall+leg column outlines by rectilinear assembly; triangular columns kept as oriented boxes rather than dropped (case C) | `8055881`, `acb73d4` | Owner round |
| DONE-18 | Modules renamed to stop clashing with toolkit names; reorganised into role-based subpackages and documented in `API.md` | v0.14.1–0.14.2 | Import health |
| DONE-19 | Circular columns named from the nearest label mark (Test18 #5) | v0.14.3 | Owner round |
| DONE-20 | Fragmented lift/stair cores DETECTED (advisory), then the detection fixed to the real in-Revit signal | v0.16.0–0.16.1 | Owner round |
| DONE-21 | Fragmented core walls recovered and placed; then made faithful, with nearest-label ownership; then door openings BRIDGED so one wall stops splitting into two members | v0.17.0, v0.18.0, v0.19.0 | Owner rounds. (An earlier attempt, v0.15.0, was reverted at v0.15.1 for a Test10 rotated-column regression — the cost is part of the record) |
| DONE-22 | Clipped rotated CORNER columns recovered; a clipped column snapped up to its authoritative label size | v0.20.0, v0.21.0 | Owner round |
| DONE-23 | A mark with no size falls back to GEOMETRY — plan labels are not a schedule table, so no cross-label sizing | v0.22.0 | Owner round |
| DONE-24 | A labelled column the geometry absorbed into a neighbour is recovered; placed by ABUTMENT rather than grid-snap; a stacked text-correction deferred to the abutment pass; a mark joined to its size by an underscore parsed (Test19) | v0.23.0–0.23.3 | Owner rounds |
| DONE-25 | Fused core walls placed from their labels; a marked column swallowed by an abutting neighbour recovered; a sized markless stub packed into a marked fused blob placed | v0.24.0 | Owner round; merged as PR #4 |

## C. Beams (v0.25 → v0.34)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-26 | Beams sized from labels; curved beams placed | v0.25.0 | Owner round |
| DONE-27 | Perimeter and floor-clipped beams recovered from the slab edge | v0.26.0 | Owner round |
| DONE-28 | Three issues from the link run fixed; a beam END snapped to a round or rotated column; open-polyline beam edges handled | v0.27.0–0.28.1 | Owner round |
| DONE-29 | Beam end-joins disallowed at both ends where the drawing says so | v0.29.0 | Owner request |
| DONE-30 | Beam bug batches 1 and 2 — the short-curve crash in `place_beams` and all four remaining reported bugs | v0.30.0, v0.31.0 | Owner rounds |
| DONE-31 | Test15 marks and missing perimeter beams; B22 placed as a single piece; end-snap corrections (Test11, B648) | v0.32.0, v0.33.0 | Owner rounds |
| DONE-32 | Sloped beams keep their slope, with a stress-test fixture | v0.34.0 | Owner round |

## D. Slabs (v0.35 → v0.45.4)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-33 | Test20 text-anchor fix; slabs wired into the pushbutton | v0.35.0 | Owner round |
| DONE-34 | `Floor.Create` fixed, UI pickers, openings | v0.36.0 | Owner round |
| DONE-35 | Slab rounds 3–5: the renamed Test0–Test7 set, real curved edges, valid member-edge faces, two live arc bugs (phantom neighbour arcs, backward arc walks) fixed | v0.37.0–0.39.0 | Owner rounds |
| DONE-36 | Never draw a beam on top of a column (test8, the client's priority) plus slab round 6 | v0.40.0 | Owner round |
| DONE-37 | Slab/beam alignment root cause found; blade-column double beams fixed; round-column trim, member-body slab filter, blade columns PLACED | v0.41.0, v0.42.0 | Owner rounds |
| DONE-38 | Placed-geometry slab source (the owner's own proposal) — and 13–22× faster graph passes | v0.43.0 | Owner round |
| DONE-39 | Two-source slab chain (owner directive), free-end junction caps, Project1 support | v0.44.0 | Owner round |
| DONE-40 | **The 14.4 mm slab/beam misalignment solved** — the exactness pass, verified against paired exports with and without the slab layer | v0.45.0 | Owner round |
| DONE-41 | Trims restored with the real culprit fixed (topology-aware carrier choice, test4/test5); `slabs_proto` renamed `slab_outlines` | v0.45.2, v0.45.4 | Owner round. (v0.45.1 was a deliberate diagnostic build and v0.45.3's body-clip trims were reverted after the owner's Revit run showed no improvement — recorded, not hidden) |

## E. Staircases (v0.46 → v0.62)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-42 | Staircase option 1 — a parametric dog-leg located by plan text | v0.46.0 | Owner spec, owner round |
| DONE-43 | Staircase option 2 — the stair-layer LINEWORK drives the layout | v0.47.0 | Owner spec, owner round |
| DONE-44 | Hotfix: `StairsEditScope` import namespace, and run base elevations | v0.47.1 | The owner's pushbutton run |
| DONE-45 | Riser count sync, a stair type picker, the arrival landing | v0.48.0 | Owner's three items after the first stairs placed |
| DONE-46 | Winding stairs, full-width arrival landing, source toggle, waist | v0.49.0 | Owner round |
| DONE-47 | Railings removed; L, circular and winder stair shapes | v0.50.0 | Owner round |
| DONE-48 | MULTI-STOREY from one DXF, plus generic stair shapes | v0.51.0 | Owner round |
| DONE-49 | The missing stair lines found in the v0.50.0 export; one JSON per multi-storey run; stair outlines DRAWN rather than picked | v0.52.0–0.54.0 | Owner rounds |
| DONE-50 | test7 drawn-outline stair and test10 grids; KEYED size schedules (test9's `B20(c)`) | v0.55.0, v0.56.0 | Owner rounds |
| DONE-51 | StaircasePlan-Test2 from the fixture the owner pushed mid-round; the SW10/SW11 shift hotfix; stair 1's 3100 width fixed | v0.57.0–0.58.0 | Owner rounds |
| DONE-52 | C17's sloped slab corners (a 400-wide column on the corner); the dialog open-crash hotfix | v0.59.0, v0.59.1 | Owner rounds |
| DONE-53 | Arc stairs, angled risers, multi-storey auto-detection | v0.60.0 | Owner round |
| DONE-54 | Naming tab, per-element tolerances, sketched winders, SW10 again | v0.61.0 | Owner round |
| DONE-55 | Level and grid naming, shipped standard sizes, landings that meet | v0.62.0 | Owner round; merged as PR #5 |

## F. Materials, footings, multi-storey, saved settings (v0.63 → v0.67.5)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-56 | Progress bar, materials and view filters, footings, skip details printed instead of swallowed | v0.63.0 | Owner round |
| DONE-57 | The export crash fixed; footings placed as foundation SLABS; two progress bars; materials | v0.64.0 | Owner round |
| DONE-58 | test12 prep: combined footings, a Graphics tab, light filters | v0.65.0 | Owner round |
| DONE-59 | test13's skewed beams; one progress bar; the storey stack; grades | v0.66.0 | Owner round |
| DONE-60 | The storey stack made selectable | v0.66.1 | Owner round |
| DONE-61 | Beam material, combined columns, noted slabs, saved settings | v0.67.0 | Owner round |
| DONE-62 | Hotfix: new levels ignored the Naming tab entirely | v0.67.1 | The owner's run |
| DONE-63 | The roof's slabs and its doubled wall, diagnosed from the v0.67.0 run's own export | v0.67.2 | Owner round |
| DONE-64 | Hotfix: the engine kept last session's library — a stale-library guard so an old copy reports instead of misbehaving | v0.67.3 | The owner's run |
| DONE-65 | Hotfix: "Duplicate type name within an assembly" on the second run | v0.67.4 | The owner's run |
| DONE-66 | A wall placed whole AND again in pieces — fixed | v0.67.5 | The owner's run |

## G. The refactor and the name rule (v0.68.0 → v0.68.1)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-67 | **Same behaviour, twenty modules instead of four** — report/export, column recovery, shared primitives, the beam half, `slab_outlines` into engine/sources/labels, `stair_layout` into text/runs/landings/tolerances, the console and progress bars, window and dialog plumbing, both dialogs, element creation and the interactive pickers all moved out of the pushbutton and into the library, in reviewable steps | v0.68.0 | A Phase-3 review pass whose four findings were fixed before the merge |
| DONE-68 | **"The name is already in use for this element type."** Root-caused (findings #1): the pre-check used Python `==`; Revit matches type names case- and whitespace-insensitively, so `Duplicate()` was reached only because the check had just called the name free. Fixed in `type_names.py` (`key`/`find`/`resolve_type`/`record`), Revit-free and unit-testable. All eight sites swept — the four that threw (columns rect + round, beams, slabs) and the four that swallowed it and built the wrong geometry in SILENCE (footings at the picked type's depth, stairs at stock riser/tread/width, the stair waist never applied, view filters dropped). They still fall back; they report now | v0.68.1 | **The owner confirmed in Revit that the duplication error is gone** |
| DONE-69 | Floor-type lookup scoped to the base type's own system family — Floors and Foundation Slabs share `FloorType` but are different system families, so a Floor named `PAD 600 THK` could be handed back for a pad and filed under the wrong category | v0.68.1 | Unit tests + the sweep |
| DONE-70 | `naming.validate` refuses a template that drops a size (`"{b}"`, which names a 300x900 and a 300x450 alike); two AST checks over the package forbid a bare `.Duplicate(` outside the helper and any element name compared with `==` | v0.68.1 | The AST checks run in the unit suite |

## H. The regression gate (Phase 0)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-71 | Three of the four regression legs had been written into an uncommitted scratchpad and lost with it. Rebuilt as committed code: `_golden.py` (baseline load/compare/save, `CAD2BIM_BLESS=1` to re-record), `regression_slab_fingerprints` (29 archived exports, newest per drawing), `regression_dxf_sweep` (17 DXFs through the whole offline pipeline), `regression_storeys` (4 storey stacks), driven by `run_regressions.py` | `7635e51` | **The gate was proved to bite**: a perturbed baseline produced three named failures, then a full verify pass ran green against the committed baselines |
| DONE-72 | The fingerprint storey pinned by IDENTITY rather than position, and re-recorded on the v0.68.1 export | `de55430` | Re-run |
| DONE-73 | The two tiers documented and kept apart — the everyday suite stays about a second so it is actually run; the gate is `regression_*`, about three minutes, run before a release. That separation is why the last set was lost, and why this one is committed | `tests/README.md` | Standing practice since |
| DONE-74 | The corpus taught to recognise every element word an export can emit (`slab｜beam｜stair｜footing｜column｜grid｜Layout`), after a `footing_test10` export registered as a phantom new drawing in two legs | v0.71.2 | The re-measured export was identical — no bless needed |

## I. Foundations from the drawing (Phase 1)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-75 | **The DXF reader keeps HATCH regions.** There was no HATCH branch at all, so every hatch in every fixture was discarded — 360 in test4 and test5, 276 in test10, 228 in Project1, 147 in test9. Only the EXTERNAL boundary path is the region, because AutoCAD clips a hatch around any label drawn over it. The shared prerequisite for P1, P2 and P4 | P1.1 (`e802e80`) | Measured against every fixture |
| DONE-76 | Foundation layer categories — outline, text, fold, sunk — with fold and sunk matched BEFORE foundation, or `S-FND-FOLD` (which contains "fnd") is swallowed. Found on the way: Test0's `S-FNDN`, 187 entities ignored since the day it was added | P1.2 | The sweep |
| DONE-77 | `F<n>_<t>MM THK` parsed, with the `\P<d>MM FOLD｜SUNK` continuation. All 19 of test10's labels parse: F1–F6, 800/1000/1200/1500/2000 | P1.3 | Measured |
| DONE-78 | **Footings and rafts placed from the CAD outline, thickness from the label.** Rafts were impossible before: `builders/footings.py` discarded any footprint wider than a column. The outline recovery has to survive linework that no chainer closes — ten of test10's thirteen outlines are closed polylines, the other three share their long edges (drawn once), giving four degree-3 nodes, so a planar FACE WALK reads each shared edge from both sides | P1.4–1.5 (`4365332`) | The owner's Revit run |
| DONE-79 | **A drawing has to prove it uses the convention.** `plan_foundations` returns nothing unless at least one outline carries a foundation note. Test0's `S-FNDN` closes into four accidental faces that no label names anywhere in the drawing; placing those would be worse than the guess they replaced. One labelled outline vouches for the rest of the layer | P1.4 | Test0 pinned in the sweep |
| DONE-80 | The size discard now REPORTS the region it declined to invent a pad for instead of dropping it in silence — and `col_region_max_side_mm` was read from `selections["limits"]`, where the dialog never writes it, so **the owner's setting had never once reached the footing pass** (findings #9) | P1.5 | Root-caused and fixed; behaviour identical for anyone who never touched the field |
| DONE-81 | The redrawn test10 (the owner replaced the foundation level after finding a design error in it) drove three recovery upgrades: segments split where another segment's endpoint lands on their body (a seam overshoots a corner by 400 mm); step-layer lines join the face graph and are then dissolved (a fold line marks where a foundation steps, never where one ends); a nested outline becomes a hole in its parent, one level, like slab openings | v0.69.0 | Measured on the new drawing |

## J. Folds and sunk (Phase 2)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-82 | Fold and sunk regions paired to the note that sits INSIDE them, so test10's three fold notes per raft pair exactly rather than by proximity | P2.1 (`9b999ea`) | Measured: 6 folds → 6 FOLD labels, 1 sunk → 1 SUNK label |
| DONE-83 | **The support arithmetic, given by the owner from their own detail** (findings #7): the offset is the PARENT's thickness. Taking the parent's top as 0 — `offset = -T_parent`, `depth = d + T_dropped - T_parent`, plan width `T_parent` | v0.69.0 | The owner's detail; two drawings independently confirm the soffit-to-soffit convention |
| DONE-84 | **A support exists only where the drop leaves a VOID** (`d > T_parent`). The first cut used "soffit gap > 0", which cast two phantom 250 mm footings inside solid concrete — the owner found them in Revit against a drawing showing nothing there. The corridor's `250 < 500` and the original F6's `1000 < 2000` both land right under the corrected rule; F6's arithmetic landing on exactly zero was that drawing's coincidence, not the rule | v0.69.1 | The owner's Revit run drove the correction |
| DONE-85 | **One support per fold GROUP, not per edge and not per region.** The first cut emitted a strip per stepped edge — four butting floors around a mid-footing fold. The office casts one collar: a closed band with the region as its hollow, an L at a corner, a strip along a lone edge. Then neighbouring collars POOL — same host, thickness and offset, touching outers → one slab wrapping the whole group with every fold as a hollow. **test10 builds exactly two fold supports where it built six** | v0.69.0, v0.69.1 | The owner's instruction, then measured |
| DONE-86 | **A boundary-reaching opening divides its outline.** The owner's v0.69.1 run: 18 created, 1 error — `Floor.Create` refusing "curve loops intersect with each other". Validating all 19 profiles offline named the culprit exactly: the corridor block's sunk bay spans its full width, so the "hole" shares two edges with the boundary — that is two slabs, not a slab with a hole. `split_profile` now subtracts any opening that reaches its outline's boundary | v0.69.3 | The owner's error, reproduced and closed offline |
| DONE-87 | Pooling hardened against three defects an adversarial review confirmed by reproduction: a corner-pinched union spliced its loops on 6 of 24 hatch draw orders (the ring walk now takes the sharpest RIGHT turn, corner-only contact is not touching, and a union that still necks to a point is refused with a note); a rectangle with a mid-edge vertex was silently unpoolable; pooled hollows were concatenated rather than merged. Each fix keeps the review's own scenario as a test | v0.69.4 | Reproduced, fixed, pinned |
| DONE-88 | **A step note never names an element.** `F3_500MM THK \ 250MM SUNK` read as an element cast two 500 slabs at zero offset over concrete the 750 raft already provides — the owner found them in Revit. A nested outline whose only labels are step notes now dissolves, and its notes move to the outline containing it. The note's THK is the DROPPED slab's own thickness | v0.69.5 | The owner's Revit run |
| DONE-89 | **An X across a part means no concrete there.** Dissolving the corridor left the raft cast SOLID over a strip the drawing voids: its north and south parts each carry two `A-DETL` diagonals spanning corner-to-corner — the standard opening symbol. An X-marked NESTED face is a CUTOUT: never an element, excluded from the step-line stitch, its ring a hole of the plan containing it. Both diagonals must reach within 50 mm of their corners; the strokes are read from the full record set, any layer; only a nested face voids; detection runs before the step-line dissolve | v0.70.2 | **The owner confirmed the raft in Revit.** Measured: 9 outlines + 2 cutouts, the raft one piece with 7 holes (corridor + 6 folds), 18 foundation-level elements |
| DONE-90 | A plain note outranks a step note in sizing, and `split_profile` fuses tangent holes first — the raft's north cutout, sunk opening and south cutout share edges, which Revit rejects wholesale | v0.70.2 | Measured |
| DONE-91 | **A storey is not a step**: over 3000 mm is refused and named. test9's `+6250` is refused; test10's folds still build | P2.3 | Measured |
| DONE-92 | The storey regression leg finds the roof by LABEL, not by position | v0.69.2 | Re-run |

## K. The dialog, the brand, and the settings (v0.69.6 → v0.72.1)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-93 | Placed footings marked structural so Width/Length can report, and the sketch handed to Revit the way the rectangle tool draws one — CCW from the lowest-left corner (see BUG-1, still awaiting the owner's confirmation) | v0.69.6 | Root-caused; in the owner's build |
| DONE-94 | Four defects surfaced by the dialog audit, fixed ahead of the redesign | v0.69.7 | The audit |
| DONE-95 | **The dialog redesigned so every knob is reachable** — the audit found roughly forty settings that existed in code and nowhere in the dialog. Then rebuilt to the owner's own layout: a Build tab with element sub-tabs, fixed at exactly five — General / Structure / Architecture / Foundation / Staircase, with grids inside General. Six top-level tabs today; help prose made readable | v0.70.0, v0.70.1, v0.70.4 | **The owner in Revit: "tested all good"** |
| DONE-96 | The JSON export file name says "footing" before "stair" | v0.70.3 | Owner request |
| DONE-97 | Rafts get their own naming template, separate from footings (`RAFT {t} THK`, `{t}` required) — a name that encodes a size must differ when the size does | v0.71.0 | Owner request |
| DONE-98 | **The Advanced door**: 19 module constants that their consumers read LIVE, behind a warning, persisted across Revit sessions. Three candidates failed the live-lookup test and were excluded on purpose rather than converted (findings #10), and a frozen-import scan now fails any registered name that grows a frozen copy | v0.71.0 | Unit tests; the scan |
| DONE-99 | **The dialogs wear the AnonGee brand** — the theme inlined verbatim, header band, one primary button, readable help text, pinned by drift tests so the theme cannot quietly diverge | v0.72.0 | Owner request, applied to all cad2bim dialogs |
| DONE-100 | Errors print RED on the console, isolated from the rest, across all six creators | v0.69.3 | Owner request |
| DONE-101 | The per-storey level mapping REMOVED and the positional ladder restored, verified byte-identical to its pre-feature form, after the owner reported it was destroying the model. See `todo-list.md` FEAT-6 (superseded) and FEAT-7 (the redesign) | v0.72.1 | **The owner's Revit run**; the removal verified line-for-line |

## L. Legends and hatch mapping (v0.73.0 → v0.74.0)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-102 | **Legends read** — swatch pattern → legend text → meaning, proposed into the dialog, never silent. `legend.py`, Revit-free. Pairing is MUTUAL nearest, because the measurement demands it: swatches are 807x484 / 1001x601 / 1100x400 (the earlier ~600x500 estimate was wrong), a text sits 657–947 mm from its own swatch while rows stack 617–640 mm apart, leaving only ~200 mm of margin. Meaning travels by PATTERN, never by proximity — the nearest PLAN hatch to any legend text is 6622 mm (worst 16140) | v0.73.0 | Measured on test9 with the package's own reader |
| DONE-103 | The ambiguity rule and the one-layer rule, both refusing loudly. test9's sheet is three tower plans and the same pattern means different things per tower (ZIGZAG: `+50MM` / `COMPENSATORY STRIP` / `+6250`), so those patterns get no proposal and a note. **Exactly one proposal survives**: ASPHALT → cutout on `PI_SHEAR WALL CUTOUT`, overriding the name convention's "structural wall" — marked in the dialog row, printed to the console, still editable | v0.73.0 | Measured: 14 entries, 1 proposal |
| DONE-104 | `legend.legend_steps()` delivers per-pattern step depths behind the same 3000 mm threshold, so the storey case cannot leak in through the legend path (no consumer yet — `todo-list.md` FEAT-3) | v0.73.0 | Unit tests |
| DONE-105 | Baselines re-recorded to follow the owner's own 0.73.0 exports (test9 exported 3 storeys where the corpus held 11 — repeats not expanded in their run); the DXF sweep did NOT move, proving the pipeline's reading was unchanged | v0.73.1 | Attributed before blessing |
| DONE-106 | **Hatches map on their own table, apart from geometry and text** — the owner's instruction. A third Layers-tab table (hatch layer → region meaning) fed only by the regions the reader keeps out of `records`, with its own convention (`classify_hatch_layer`: column, fold, sunk, cutout, unmapped) and its own default. Geometry rows are records-only again; legend proposals seed the HATCH mapping, which is where a swatch's meaning belongs; settings schema 3 adds a `hatches` section and old files load unchanged | v0.74.0 | 664 → 679 tests; **the gate moved nothing** — fold, sunk and column routing measure identical under both conventions |
| DONE-107 | The hatch reader checked end to end against the owner's exports: 495 regions across test9 + test10, 0 degenerate rings, legend mapping test9 → `{PI_SHEAR WALL CUTOUT: cutout}`, test10 → `{}` | v0.74.0 | Measured |

## M. Walls (v0.75.0 → v0.76.0)

| ID | What was done | Version | Confirmed by |
| --- | --- | --- | --- |
| DONE-108 | **The wall survey** (findings #12): wall layers exist in 3 of 17 drawings and between them use three drawing conventions — all three in test8 alone. Real widths 100–495 mm, empty below 100 down to the ~5 mm re-traces, empty 495–565, door artifacts from 565 (37 candidates at exactly 750 are jamb strokes across 750 doorways). Collinear gaps: 150–200 at tee'd walls, 750–1310 at doors (27×750, 10×1000, 12×1150, 12×1200), room-scale blur from 1350 | v0.75.0 | Measured across the corpus |
| DONE-109 | Classification: an `rcc` token on the structural row, so test8's `S-RCC-WALL` (29 records) stops reading as an ARCH wall. Checked against the full corpus layer dump — 72 distinct names across the 17 DXFs and the archived exports — **exactly one layer moves**; `PI_RCC BEAM` and `S-RCC-COL` are already claimed by the beam and column rows above it | v0.75.0 | Measured before the edit, pinned in tests |
| DONE-110 | **`wall_plan.py`** — `plan_walls(records, texts, tolerances)` → `{segments, skipped}`, Revit-free. Closed thin rings read as outlines (quads at any rotation, rectilinear L/U rings decomposed, a U open by one wall width closed first); loose faces merged collinear across door gaps and paired smallest-gap-first with union spans — `recover_core_walls`' three refinements generalised OFF the axes, because the corpus is angled (10.3° runs in Project1 and test8). Constants from the histogram: `_WALL_MIN_MM = 90`, `_WALL_MAX_MM = 520`, `_COLLINEAR_BRIDGE_MM = 1300`, each sitting in a measured desert | v0.75.0 | 679 → 701 tests, fixture pins on exact record coordinates |
| DONE-111 | A cutout layer's rings are holes, not walls: test9's `PI_SHEAR WALL CUTOUT` carries ten closed quads 240–500 mm wide — inside the width band, so no width rule can refuse them — whose legend row reads "CUTOUT FOR DOOR ABOVE". A planner that walls them shut casts concrete in every doorway, so the refusal lives in `wall_plan` and lands in `skipped` with the reason spelled out | v0.75.0 | Measured; test9 skips 10 door cutouts and 3 zero-length stone lines |
| DONE-112 | Nothing drops silently: every unpairable record lands in `skipped` with a reason. Planned per drawing — Project1 17 segments / 11 skips, test8 178 (25 structural + 153 arch) / 110, test9 19 / 39; **the other fourteen fixtures pin zeros**, which is the guard against leakage | v0.75.0 | The sweep gained six wall metrics per fixture; the blessed diff was those 102 lines and nothing else |
| DONE-113 | **`builders/walls.py`** — one line-based `Wall.Create` per planned centreline. Width set through the type's COMPOUND STRUCTURE (no instance parameter exists), duplicated per (kind, width) off a per-kind base type; a refused width (membrane layer, no core, curtain/stacked base) is a red console error and the wall still places at the base type's own width. Top constrained to the level above via `WALL_HEIGHT_TYPE` after Create (the column builder's pattern), unconnected at the storey height when there is no level above; the `structural` bool on Create is the kind | v0.76.0 | 701 → 714 tests, ten static AST pins on the wiring |
| DONE-114 | `run_builders._create_walls` plans ONCE for both kinds (tolerances passed through), places each kind against its own type inside one transaction group with the warning swallower, routes errors through the red channel and groups the planner's refusals by reason | v0.76.0 | AST pins |
| DONE-115 | Dialog: Structure gains the structural-wall group, **Architecture gains its first real content**; naming rows `RCC WALL {t} THK` and `BRICK WALL {t} THK` with `{t}` required (the raft precedent — widths are measured, so a collision would be a silent reuse); selections keys `create_struct_walls` / `create_arch_walls` / `struct_wall_type_id` / `arch_wall_type_id`; settings and presets ride the name-driven capture with no schema change. Walls run per storey as build step 8 | v0.76.0 | **The gate moved nothing** — no planning code changed |

---

## Standing rules this record keeps

1. **The version moves with every commit** that changes the package. It is a tracking number, not a
   release or a tag — three commits all answering "v0.68.1" name nothing.
2. **A number that moves gets explained in the commit that moves it**, and the baseline is
   re-blessed on purpose, never silently.
3. **A wrong result that says nothing is worse than a crash.** Three of the eight type-name sites
   swallowed their error and built the wrong geometry; the console prints errors in red and names
   every skip because of what those three cost.
4. **The drawing decides, not the tool.** A drawing has to prove it uses a convention before the
   convention is applied to it (Test0), and a measurement — never an estimate — sets every constant.

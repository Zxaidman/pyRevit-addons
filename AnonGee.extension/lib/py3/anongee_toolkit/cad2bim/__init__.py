# -*- coding: utf-8 -*-
"""cad2bim -- shared library for the CAD-to-BIM toolset.

This package holds the reusable, button-agnostic logic so each pushbutton stays
thin. Modules are grouped by role (subpackage names avoid clashing with the
sibling anongee_toolkit packages):

    config.py            central tunables (acceptance limits, tolerances)
    model.py             plain data holders (CurveRecord, TextRecord, results)
    compat.py            Revit 2024/2025 version-robustness helpers
    unit_convert.py      mm <-> Revit internal feet (the ONLY place units convert)
    report.py            human summary + JSON export; column/beam sectioning

    geom/        Revit-free geometry
        shapes.py        rectilinear parsing, decomposition + column recovery
        transform.py     map DXF coords -> internal feet (+ bbox validation)
        compare.py       diff Revit-link vs DXF geometry (problem geometry)
    classify/    Revit-free text + layer interpretation
        marks.py         parse "C1 400x400" labels and column schedules
        layers.py        layer -> element-category classification (convention)
    readers/     pull geometry + text from a DXF or a linked CAD
        dxf_reader.py    ezdxf: geometry + text from a DXF (CPython3, binary+ascii)
        geometry_reader.py  curves from a linked CAD in the model (project coords)
        cad_links.py     find/describe linked-DWG ImportInstances
        dxf_linker.py    link a picked DXF programmatically (Link CAD dialog)
    builders/    create Revit structural elements
        columns.py / beams.py / grids.py   element creation from parsed members
        txn_failures.py  swallow batch-creation warnings (no modal stalls)

This package runs on the pyRevit CPython3 engine (ezdxf needs CPython >=3.10) and
imports NO pyRevit IronPython modules (pyrevit.forms / pyrevit.revit), per the
AnonGee Brand Guidelines 12.1 / 12.8.4 / 12.9. The pushbutton builds its windows
with XamlReader.Load and uses System.Windows dialogs directly. The pure modules
(geom/, classify/, report.py) import no Revit assemblies, so they can be
statically inspected and unit-tested outside Revit.
"""

__version__ = "0.35.0"  # Test20 text-anchor fix + SLABS step 1 wired into the pushbutton.
#                         (A) Test20 lost ALL label sizing/marks (and the two label-required
#                         beams B7/B8): the DXF->Revit text alignment is GRID-anchored, and the
#                         stress plan has no grid layer, so it fell back to the link's own
#                         transform -- which Revit reported as identity (unit scale baked into
#                         the geometry), throwing every label 304.8x away. The alignment now
#                         anchors on ALL shared geometry when there are no grids (same drawing
#                         on both sides), and only trusts the link transform when both anchors
#                         are empty. The stress DXF also now declares $INSUNITS=mm.
#                         (B) SLABS, step 1: after the beams, the pushbutton now derives slab
#                         outlines -- closed A-FLOR rings as drawn, else the bounded faces of
#                         the placed beam centreline graph (endpoint-healed planar faces) --
#                         sizes/names each loop from "S1 150 THK"/"150 THK." notes lying inside
#                         it (any text layer), duplicates the model's first floor type per
#                         thickness, and places one floor per loop at the beams' level
#                         (builders/slabs.place_slabs, own transaction group; slab outcome
#                         joins the console report and the JSON export as "slabs").

# 0.34.0  BEAM: sloped beams keep their slope + a stress-test fixture.
#                         (A) Test11 grid-I regression from 0.33.0: the 4-degree bays between
#                         rotated columns arrive as ONE non-rectilinear snake holding the beam's
#                         two angled edges; the bbox fallback flattened them onto the horizontal
#                         axis (0.32.0 only LOOKED right because the old teleport-snap dragged
#                         the ends to the column centres). A non-rectilinear ring whose longest
#                         edge is >2 deg off the axes now explodes into the pair pool, where the
#                         two angled edges pair into the correctly SLOPED beam; the axial snap
#                         then runs it centre-to-centre. Replay: both bays at 4.00 deg, only
#                         those two segments change across all six exports.
#                         (B) STRESS FIXTURE: fixtures/make_stress_plan.py generates
#                         cad/StressPlan-Beams.dxf -- one synthetic plan packing every failure
#                         mode found in Test9-19 (baseline ring w/ rotated labels, 4-deg sloped,
#                         45-deg diagonal, 900-wide + continuation merge, floor-clipped
#                         perimeter, stacked-label mark theft, curved arc chains, junk that must
#                         fabricate nothing) + tests/test_beam_stress.py (14 asserts incl. the
#                         link-reader polyline snakes fed straight into detection). 14/14 files.

# 0.33.0  BEAM end-snap corrections from the 0.32.0 run (Test11 + B648).
#                         (A) NO MORE SIDEWAYS DRIFT: snap_beam_ends_to_columns moved a beam end
#                         ONTO the round/rotated column's centre point -- a column deliberately
#                         drawn OFF the beam's axis (Test11's grid-I columns) dragged the end
#                         sideways and skewed the whole beam off its CAD outline. The end now
#                         slides ALONG THE BEAM'S OWN AXIS to the station abeam of the column
#                         centre (projection), so the beam stays on its outline and still meets
#                         the column. Test11 replay: 22 snaps, all axial, zero lateral drift.
#                         (B) B648 (Test15+Test14): the bay between two large rotated columns
#                         (C315/C319, 750x1200) leaves only a 301 mm edge-overlap stub, and BOTH
#                         stub ends fell inside BOTH columns' reach -- first-match sent both ends
#                         to the SAME column, collapsing the beam to zero (skipped as a sliver).
#                         Each end now snaps to its NEAREST column, stretching the stub across
#                         the full bay (B648 = 1500 span, S->O). Same fix recovers the identical
#                         markless beam in Test14. Zero collapsed segments after snap; detection
#                         byte-identical on every export; 13/13 test files.

# 0.32.0  BEAM: Test15 marks + missing perimeter beams; B22 single piece.
#                         From the user's 0.31.0 Revit run (Test10 perfect; Test15 rows fixed
#                         but many marks wrong/missing and some beams undrawn; B22 placed as two
#                         pieces with a phantom 300 gap):
#                         (A) WRONG/MISSING MARKS -- a beam label is written ALONG its beam, but
#                         a rotated (vertical) label's MTEXT anchor sits at one end of its text
#                         run, often nearer the crossing row's centreline than its own beam, so
#                         vertical labels claimed horizontal beams row after row. The DXF reader
#                         now reads MTEXT text_direction (a vertical label is the (0,1,0) vector,
#                         NOT rotation=90) into TextRecord.rotation_deg, and every label-to-beam
#                         assignment (ownership, fallback, edge-pair) is orientation-gated: a
#                         label only matches a beam it runs parallel to (+-20 deg). The duplicate-
#                         mark sweep now keeps by CENTRELINE distance (same metric as ownership).
#                         (B) UNDRAWN BEAMS (B120/B672/B256/B270 bay; B123-B126; B675-B677; edge
#                         rows) -- a whole BAY traced as one nearly-closed snake has a slightly
#                         skew closing edge, defeating is_rectilinear; the bbox segment it became
#                         (2950 wide) was silently width-filtered and the REAL beam edges inside
#                         it were consumed. Too-wide outlines now explode into the pair pool from
#                         ALL three outline branches (quad/composite/non-rectilinear), so the
#                         edges re-pair. Offline replay of Test15: 682 labels -> 682 segments,
#                         every one marked with its own label, zero undrawn, zero mismatches.
#                         (C) B22 ONE PIECE -- a continuation now EXTENDS the placed beam over
#                         the crossing (mark/size kept) instead of adding a second piece with a
#                         gap that read like a column that isn't there. Test18 both variants:
#                         B22 -385..4465; Test19: -100..4850 (to C12's face). Test10/18 byte-
#                         identical throughout; 13/13 unit tests.

# 0.31.0  BEAM bug batch, part 2 -- all four remaining bugs, fixed from the
#                         0.30.0 raw-geometry exports OFFLINE (replayed, not guessed):
#                         (8e) Test10 grid-6 H-I beam: simplify_ring closes every polyline, so an
#                         open snake's last leg (the vertical beam's edge, collinear with the
#                         fabricated closing edge) was silently deleted. A ring that loses a real
#                         vertex is now rejected and the polyline explodes into the pair pool.
#                         (8b) Test15 phantom beams MIDWAY between grids J/K, S/T: a U-polyline
#                         chaining two grid beams' facing edges ring-closed into an 1800-wide
#                         "quad" whose label then rewrote the width to 300. Too-wide quads now
#                         explode (the real on-grid beams re-pair from the freed edges; also
#                         repaired rows E/F + Q/R in both towers, 584->642 segments) and a label
#                         can never rescue an out-of-range width.
#                         (8d) Test18 B20 600x900 placed as unmarked 300x900: B23's label sits
#                         between the stacked B20/B23, out-scoring B20's own off-midspan label by
#                         midpoint distance. Marks now assign label-OWNS-segment (nearest
#                         centreline), with the midpoint rule as fallback for unclaimed segments.
#                         (8c) B22 (900 wide) stopped at the B4/B5 crossing instead of reaching
#                         the C12 core: the far piece's only label sits over the near piece, and
#                         its inner edge may survive only as the floor outline. A new label-free
#                         CONTINUATION pass pairs leftover beam+slab edges (>=1 beam edge) and
#                         keeps a pair that collinearly continues a placed beam of the same width
#                         across a crossing member (<=1200 mm); depth inherited, mark left empty.
#                         (Also: texts_sized in the JSON export now includes mark-only labels.)
#                         PLUS (held prototype, not wired): slabs_proto.py + builders/slabs.py --
#                         slab outlines from the A-FLOR layer when present, else from the BEAM
#                         PERIMETER GRAPH (endpoint-healed planar faces of the placed beam
#                         centrelines); mark+thickness from "S1 150 THK" labels / schedule, like
#                         columns and beams. Proven on real exports: Test15 has NO usable A-FLOR
#                         loops but yields 233 slab panels from its 642 beams. Beams stay the
#                         active workstream; slabs get wired after the beam case study closes.

# 0.30.0  BEAM bug batch, part 1. (8a) SHORT-CURVE crash fixed: place_beams
#                         filtered on the STORED length_mm, but snap_beam_ends_to_columns pulls a
#                         beam END onto a column centre AFTER that length is stored -- a beam whose
#                         ends collapse onto one column kept its stale (long) length, slipped past
#                         the <50 mm filter, and Line.CreateBound(start==end) threw "Curve length
#                         too small" (2x in Test15). place_beams now recomputes length from the LIVE
#                         endpoints and skips the collapsed sliver. (DIAG) the JSON export now carries
#                         beams.raw_geometry -- the exact beam- and slab-edge-layer polylines/lines/
#                         arcs (mm) the link reader returned -- so a MISSED beam (8b between-grid,
#                         8c B22->C12, 8d B20, 8e Test10 grid-6) can be replayed and diagnosed offline
#                         from one export. The DXF source carries beams as loose LINES, not the
#                         polylines Revit's link reader builds, so the DXF harness places ZERO beams
#                         and cannot reproduce these -- the raw dump is the only offline window in.

# 0.29.0  Two pushbutton features. (A) DISALLOW beam end-joins: both ends of
#                         every placed beam (straight + curved) get StructuralFramingUtils.
#                         DisallowJoinAtEnd so Revit no longer auto-extends a beam into its
#                         neighbours. (B) DEFERRED console + progress: the pyRevit output no
#                         longer opens before Run -- all output is buffered and flushed only
#                         after the main-window Run, after which a 10-cell [####------] bar
#                         advances per phase (link, read, columns, beams, create x3). Plain
#                         print() (no pyrevit import). (Also: ui.xaml missing-space hotfix that
#                         broke window load.)

# 0.28.1  BEAM open-polyline edges. The link reader returns a beam's
#                         surviving edge as a short OPEN polyline (not a closed quad), which hit
#                         the ring<4 "degenerate" branch and was dropped -- so a plan whose beams
#                         are polylines placed ZERO beams (Messy/Mahalaxmi: 0->49; Revit Test15
#                         had 255 degenerate). Those polylines now explode into the line pool and
#                         pair like any beam edge. Only that one fixture changes; rest identical.

# 0.28.0  BEAM polish: (6a) snap a beam END to a ROUND or ROTATED column
#                         centre so the junction has no gap (axis-aligned cols untouched, mids
#                         never move) via report.snap_beam_ends_to_columns. (6b) edge-pair
#                         beams now own their candidate by NEAREST label, so two same-width
#                         labels (B4,B5) no longer swap (the first no longer steals the other's
#                         nearer beam). (6c) admit wide beams: beam_width_max 600->1000 and the
#                         LABEL-CONFIRMED edge pass pairs up to that width (geometric line_pair
#                         stays at pair_max 700), so a 900-wide B22 places without flooding
#                         line_pair. Columns byte-identical; only intended beams added.

# 0.27.0  BEAMS in Revit: fix three issues found in the 0.26.0 link run.
#                         (A) The link reader returns the slab/floor outline as ONE polyline,
#                         not loose lines, so the floor-edge pool was empty and only ~1 beam
#                         placed -- slab edges are now exploded into segments. (B) A mark-only
#                         beam label ("B1") was never sized: build_beam_segments now takes the
#                         schedule and resolves each beam's size via _label_size (inline ->
#                         schedule). The beam schedule is Mark|W|H|L (H = depth, L = span), so
#                         parse_schedule now reads a BEAM row as W x H (was W x L = the span);
#                         columns stay W x L. (C) Placed beams never carried their Mark -- both
#                         beam placers now stamp it, and duplicate marks (two members sharing
#                         one label between them) are de-named to the nearest. Columns are
#                         byte-identical; beam geometry unchanged, now sized + named correctly.

# 0.26.0  BEAMS: recover perimeter / floor-clipped beams from the slab edge.
#                         Revit clips a perimeter beam's inner edge against the floor (A-FLOR)
#                         outline, so only ONE beam edge survives on the beam layer -- the
#                         parallel-pair detector saw a lone line and dropped it (Test19 placed
#                         1 of 23 beams). Floor layers now classify as slab_edge; a new pass
#                         pairs each leftover beam line AND each slab edge into width-band
#                         candidates and KEEPS one only where a beam label of matching width
#                         sits across it (a slab edge alone never becomes a beam). An edge pair
#                         that merely re-traces an already-placed beam is dropped (no doubles).
#                         Existing line_pair/curved beams are byte-identical on every fixture;
#                         Test19 goes from 1 to 21 of 23 placed (B20 shares its edge with B23;
#                         B22 is 900 wide, past the 600 mm beam-width limit).

# 0.25.0  BEAMS: size them from labels + place curved beams. (1) The push-
#                         button called build_beam_segments with texts=None and never routed
#                         the beam text layer, so beam DEPTH (the larger label dimension a 2D
#                         plan can't supply) and the mark were dropped -- every beam used the
#                         family's default depth. script.py now routes beam_texts and passes
#                         them in (width=min(label)/depth=max(label)/mark per nearest label).
#                         (2) A curved beam is drawn as two concentric arc-fragment edges one
#                         width apart; they were only COUNTED ("placement to follow"). Now the
#                         fragments are clustered into edges, an inner/outer pair becomes one
#                         curved segment (centreline radius, width=gap, swept angle from the
#                         largest angular gap, depth+mark from the nearest label), and
#                         builders.beams.place_curved_beams places it along an Arc. Straight-beam
#                         geometry is byte-identical on all fixtures; Test19 sizes B23 (300x900)
#                         and places the B18 (400x900) curved beam.

# 0.24.0  place fused-outline columns from their labels. When abutting
#                         members share an outline -- Test19's lift core drawn as loose wall
#                         lines, or one column cast hard against another (C16 under C15) -- the
#                         pieces are assembled into one blob and decomposed greedily; the greedy
#                         cut mis-assigns the shared corners/edges, so each member keeps its
#                         thickness but is clipped/extended and offset by the stolen cell (the
#                         5300 wall placed as 4700, 600 mm low; C16's footprint swallowed whole
#                         into C15). report.recover_core_walls_from_labels now re-tiles each fused
#                         blob from its mark+size labels BEFORE text-correction: the blob's
#                         exact-cover pieces give a cell grid, and members are carved longest-first,
#                         each claiming the label-sized run of unclaimed cells nearest its label.
#                         A blob is re-tiled only when it holds at least one MARKED label and its
#                         labels -- marked and markless-but-sized alike -- tile it cleanly, so a
#                         working markless-only core is never touched; a sized stub packed into a
#                         marked blob (C17's "300x600") is placed unnamed instead of swallowed.
#                         Geometry is byte-identical on Tests9-18 and the messy plans; in Test19
#                         C8/C9/C10/C12 move to true centres, C16 (swallowed by C15) is placed, and
#                         the 300x600 under C17 is placed -- every column on the plan now lands.

# 0.23.3  parse a column MARK joined to its size by an underscore. Test19's
#                         plan labels read "C16_300 X 600"; an underscore is a regex word
#                         char, so the mark token's trailing \b never fired and EVERY mark on
#                         the plan came back empty -- silently disabling mark-driven recovery
#                         and column naming. The mark token now ends on a negative lookahead
#                         (not another letter/digit) instead of \b, so "_", a space or end all
#                         close it. Geometry is byte-identical on Tests9-18 (space-format marks
#                         already parsed); Test19 goes from 0 to 15 marks parsed.

# 0.23.2  defer a STACKED text-correction to the abutment pass. In the
#                         redrawn Test18, C17 (300x600 cast against C9, a 600x900) survives
#                         Revit's import only as a mis-centred sliver; text-correction resized
#                         that sliver to the schedule size and kept its centre, landing C17
#                         INSIDE C9 -- two stacked columns, 450 mm off. Text-correction now
#                         detects a corrected column whose centre falls inside a larger placed
#                         neighbour, drops the absorbed sliver and leaves the mark unplaced so
#                         the proven abutment recovery places it edge-to-edge (as it already
#                         did for the same column in the fragmented DXF, and for C16). Redrawn
#                         C17 goes from 150 mm right + 450 mm up to Y-exact, ~50 mm in X. The
#                         centre-inside-larger test fires on exactly this one case across every
#                         Test1-19 output, so no good placement is disturbed.

# 0.23.1  place the recovered column by ABUTMENT, not grid-snap. The 0.23.0
#                         recovery landed C16/C17 but grid-snapped them onto the neighbour's
#                         axis (200-450 mm out) -- wrong, because an absorbed column sits
#                         deliberately off-axis against its partner. It now abuts the nearest
#                         placed neighbour edge-to-edge: the across-face coordinate is taken
#                         from the abutment (exact), the other from the leftover centroid
#                         clamped to stay against the neighbour, with no grid-snap. On Test18
#                         this lands fragmented C16/C17 exactly and redrawn-fix within 50 mm
#                         (Y exact); the residual cross-offset is unrecoverable because the
#                         small column's geometry is tucked entirely under its partner.

# 0.23.0  recover a labelled column the geometry ABSORBED into a neighbour. A small column
#         cast hard against a bigger one (C16/C17, 300x600, beside a 600x900) fragments so
#         badly that recovery folds its pieces into the neighbour and drops the rest,
#         orphaning its label. A last-resort pass replaces it from its SCHEDULE size + the
#         leftover fragments not already inside a placed column. Heavily gated -- needs a
#         placed neighbour, hard geometry evidence, in-range size, and zero overlap -- so a
#         stray label can never fabricate a column (feeding all 43 Test18 labels recovers
#         only C16 and C17). Revert with the cad2bim-v0.22.0-known-good checkpoint if needed.


# Historic notes:
# 0.22.0  mark with no size -> fall back to GEOMETRY. Plan labels are not a schedule table:
#         a markless size label and an unrelated mark sharing a row Y are different columns a
#         bay apart, so split-pairing is OFF when reading plan labels (inline sizes still apply).
# 0.21.0  a label's SIZE is authoritative for clipped columns. A column drawn short of its
#         scheduled/labelled size by 20-80 mm (e.g. C14, a 270 mm sliver of a 300 mm column)
#         now snaps UP to the label size, keeping orientation+centre; columns already at size
#         (within 20 mm noise) are left exactly as drawn.
# 0.20.0  recover clipped rotated CORNER columns. A rotated corner column
#                         clipped at a beam junction comes through as one open outline left
#                         ~600-800 mm open -- just past the 600 mm lone-fragment close gap,
#                         so it was dropped. The lone-fragment close gap widens to 900 mm,
#                         BUT only for few-vertex (<= 6) polygons, so a many-vertex round
#                         column tessellated as a polyline is never rect-fitted into a
#                         phantom; recovered rects are also deduped against placed columns
#                         and each other, so a fragment cannot double an existing column.
#                         Isolation-checked: this adds only the two clipped corners and
#                         leaves Test10 untouched.
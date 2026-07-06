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

__version__ = "0.31.0"  # BEAM bug batch, part 2 -- all four remaining bugs, fixed from the
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
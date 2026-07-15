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

__version__ = "0.45.2"  # TRIMS RESTORED with the culprit fixed. The 0.45.1 isolation run was
#                         conclusive: beam-edges-only had ZERO misalignment on every fixture, so
#                         the trim INTERACTION was the fault. Offline audit found it: the
#                         exactness pass picked each vertex's two NEAREST distinct-direction
#                         carriers -- at a rotated (diamond) column junction the column's two
#                         45-degree ring edges out-crowd the beam edge, so the long boundary's
#                         endpoint welded onto the column APEX (129 off-carrier edges on test4,
#                         long edges tilted 24-60mm -- the "new place" misalignment; test1-3's
#                         axis-aligned columns dodge it, which is why they were clean).
#                         FIX: TOPOLOGY-AWARE carrier choice -- a vertex belongs to its two
#                         ring edges, so it snaps to the crossing of the carriers PARALLEL to
#                         those edges (in/out direction match, 10 degrees); wrap ends keep
#                         line x circle, mid-wrap chords stay radial. test4 audit: 129 -> 33
#                         off-carrier edges, all 190mm apex shaves at column corners with
#                         EXACT junction endpoints (24mm cosmetic clip of the column corner);
#                         every long boundary sits at 0mm on its beam edge. The 0.45.1 missing
#                         slabs (7 on test4/5, GH/AB bays on test1-3, 5 on test6) return with
#                         the trims. Truth match test1-3: 137/137 bays, unchanged.
#
# 0.45.1                  DIAGNOSTIC build (user-requested isolation of the remaining test4/5
#                         misalignment): the placed-members slab source runs with
#                         trim_columns=False -- boundaries from the placed BEAM edges ALONE.
#                         No column footprint rings, no round-column wraps, no column-layer
#                         linework in the graph (caps still suppressed at column junctions so
#                         beam ends do not grow cap slivers). Expected while diagnosing: slab
#                         corners run square through column corners, no arcs at round columns,
#                         shaft faces not wall-bounded. If the test4/5 misalignment persists in
#                         this build it is NOT the column trimming; if it vanishes, the trim
#                         interaction is the culprit and 0.45.2 will fix it surgically.
#
# 0.45.0                  THE 14.4mm MISALIGNMENT SOLVED (paired with/without-slab-layer exports
#                         made it exactly measurable -- thank you for those):
#                         (A) ROOT CAUSE: a walk node is a weld-cluster centroid, which can sit
#                         up to snap/2 off the true junction; the wrap-arc endpoint projection
#                         then kept it on the circle but OFF the beam edge line -- the user
#                         measured 14.413mm. FIX = the EXACTNESS PASS (_snap_ring_to_carriers):
#                         every output vertex snaps to its authoritative geometry -- the
#                         crossing of its two nearest CARRIER lines (beam edge x beam edge /
#                         x column ring edge), the nearest line's intersection with a circle
#                         footprint at a round-column wrap (gated to snap distance so mid-wrap
#                         chord vertices stay radial), the foot on a single carrier otherwise.
#                         Carriers = straight input lines only (synthesized beam edges + caps,
#                         wall lines, rect rings) -- NEVER tessellated arc chords, which had
#                         polluted the candidate set and hijacked junctions.
#                         MEASURED against the slab-layer ground truth: test1 max deviation
#                         3.4mm, test2 5.5mm, test3 3.3mm (chord sag at wraps; Revit gets true
#                         arcs there), all 137 bays matched, most at exactly 0.0mm. test1's
#                         (-40.2, 27550.0) junction reproduces the drawn boundary EXACTLY.
#                         test6's one 29.8mm bay = the slab meeting the PLACED chamfer column's
#                         face (the column's own size-snap vs drawing; edges coincide in model).
#                         (B) Export default name per user convention:
#                         [version]_[element]_[testN]_[textmode].json via _export_name.
#                         (C) The Test20 stress DXF is regenerated into a TEMP dir when absent
#                         (the repo copy stays archived in .old_fixture as the user keeps it).
#                         Builder mirror: every ring contiguous on every fixture; suite 15 OK.
#
# 0.44.0                  0.43.0 feedback: two-source slab chain (user directive), junction caps,
#                         Project1 + staircase groundwork:
#                         (A) SOURCE CHAIN = slab_edges -> placed_members ONLY. The drawn-linework
#                         fallbacks (member_edges, beam_graph_inset) are retired from the chain
#                         per the user's directive: the placed beams' edge lines form the
#                         boundary, column footprint rings inside it trim the corners -- beams
#                         are placed aligned, so slabs align by construction. (Functions retained
#                         for the offline harness/tests.)
#                         (B) MISALIGNMENT AUDIT (every face edge measured against its carrier):
#                         long edges sit at 0mm on all fixtures; the residual was end-CAP corner
#                         welds at junctions (56 x ~24mm jogs on test4). Caps are now added only
#                         at FREE beam ends (cantilever tips) -- at a junction the neighbouring
#                         member's edges provide the boundary. Remaining: ~24mm corner shortcuts
#                         where a column ring apex welds into a beam crossing node (50mm snap,
#                         endpoints exact).
#                         (C) NEW LAYER CATEGORIES for the roadmap: "structural wall", "arch
#                         wall", "stair" (+ default conventions: stair|strs|step, shear|retain,
#                         wall|parapet) -- the override dialog lists them via ALL_CATEGORIES, so
#                         LayoutPlan-Project1's A-WALL-CUT-Brick / PARAPET WALL / A-STAIR-Steps
#                         and StaircasePlan-Test1's S-STRS route correctly from day one.
#                         (D) PROJECT1 ASSESSED offline (DXF path, mm->ft): default mapping
#                         covers every structural layer (ARCH BEAM, COLUMN, S-RCC-COL, the _ASC
#                         text layers); columns 327 rects detected, beams 661 segments (widths
#                         150-400); NO grid layer (gridless path already supported). Staircase
#                         fixture decoded: flights = equidistant riser lines (300mm treads,
#                         1500 wide), landings = rects, DN direction, ST-n marks, SW1..6 shear
#                         walls (300x3300/6300) on the column layer with closed outlines --
#                         next round: stair pass design + structural wall placement.
#
# 0.43.0                  0.42.0 feedback: PLACED-GEOMETRY slab source (user proposal), 13-22x
#                         faster, and the 0.42.0 regressions fixed at the root:
#                         (A) NEW SOURCE slab_loops_from_placed_members: slabs run AFTER beams
#                         and columns, so their outlines come from what was PLACED -- each
#                         straight beam contributes its two edge lines (centreline +/- w/2, plus
#                         end caps), every column its exact footprint ring; only beam-layer ARCS
#                         (curved edges/fillets) and wall linework survive from the drawing.
#                         Alignment with placed members is exact BY CONSTRUCTION. _create_slabs
#                         runs BOTH this and the drawn-edge source and keeps the one covering
#                         more area (placed wins near-ties): placed on test1-7 (test7 member
#                         fallback 1 -> 9 faces!), drawn on test8 (1070 vs 871 m2 -- its beam
#                         detection misses unlabelled members, exactly as the user noted).
#                         (B) PERF (test4/5 "stuck"): _heal_endpoints and _split_at_crossings
#                         were all-pairs O(n^2) -- 45.6s offline on test4's ~4k edges; spatial
#                         grid buckets cut that to 2.1s (drawn) / 3.6s (placed). The doubled
#                         footprints (placed + outline fits of the SAME columns) also doubled
#                         cost AND jagged every rect trim -- 0.42.0's "rotated column not right"
#                         regression: recover_outline_columns already placed every usable
#                         outline, so only column_trim_footprints(sections) is passed now.
#                         (C) ROUND-COLUMN ARCS (0.42.0 turned wraps into chords): the boundary
#                         run along a circle footprint synthesizes a (start, mid, end) triple
#                         with endpoints PROJECTED onto the circle -> genuine Arc.Create again.
#                         (D) CLUSTER NODES PREFER BEAM-EDGE POINTS: the centroid of a beam tip
#                         + ring vertices tilted long straight boundaries by up to 40mm (the
#                         residual "misalignment with beam"); a node with any beam-edge member
#                         now sits ON the beam edge; the circle side self-corrects via (C).
#                         (E) BUILDER: adjacent arc spans share a ring vertex; emitting the
#                         span's own endpoint left a gap when the neighbour re-welded it
#                         ("loop discontinuous") -- arcs now emit from the FINAL ring points.
#                         Verified: builder mirror contiguous on ALL fixtures/sources; test1-3
#                         6/7 match slab-layer ground truth exactly; suite 15 files (23 slab
#                         cases). Roadmap accepted: structural walls, arch walls, stairs.
#
# 0.42.0                  0.41.0 feedback: round columns, member-body slabs, blade columns PLACED.
#                         Verified offline against the 0.41.0 exports (renders, builder-walk
#                         mirror, ground-truth diff); all quiet fixtures unchanged:
#                         (A) ROUND-COLUMN TRIM (test1-3/4/5 "slab edge misalignment"): round
#                         columns arrive as DOZENS of tiny drawn arc fragments (2-30mm) -- after
#                         tessellation+clustering the boundary walk wandered (slanted bay edges,
#                         notches). Circle footprints now swallow ALL column linework inside
#                         r+pad (incl. fragment arcs, which no longer register phantom arc
#                         triples) and add one clean polygon ring (chords >= 2x snap). Bay edges
#                         at circles run straight+wrap cleanly; test3's "loop discontinuous"
#                         builder error gone (mirror: every ring contiguous on every fixture).
#                         (B) MEMBER-BODY SLABS (test6 slabs ON B21/B20 + merged B22/B4/B5
#                         cross): a 900-wide beam's body strip beats the mean-width floor and a
#                         fused corridor cross passes every perimeter test. New AREA test: a
#                         face >50% covered by placed beam bodies (grid-sampled) is a member,
#                         not a panel. test6: 12 faces -> 9 clean bays (8 grid + D-slab).
#                         (C) BLADE COLUMNS PLACED (test8 "most columns not drawn"): closed
#                         4-corner column-layer outlines beyond the size limits now become REAL
#                         columns at drawn size/position/angle via recover_outline_columns --
#                         19 on test8, every one named by its plan mark (AC19-24, BC23/24/26/27,
#                         AC2/3/4/15/18, BC2/17/18/19); zero on every other fixture (dedupe
#                         against placed footprints). The "missing beams" on the strips were
#                         these columns' bodies re-traced on the beam layer -- now they are
#                         columns, which is what the drawing means.
#                         Suite: 15 files (22 beam-split cases, 20 slab cases). NOTE: the
#                         member-edge source reads the REVIT LINK geometry (revit_result
#                         records); the DXF is the TEXT source only.
#
# 0.41.0                  0.40.0 feedback round: slab/beam alignment + blade columns, verified
#                         offline against the 0.40.0 exports (leak census, ground-truth diff,
#                         renders of the exact reported regions):
#                         (A) test4/5 SLAB-OVER-BEAM ROOT CAUSE (the reported misalignment /
#                         "slab made over beam from one side"): a beam edge tip landing within
#                         50mm of a column ring corner rounded into a DIFFERENT 50mm grid cell,
#                         never merged, dangled, was pruned -- and the bay face flooded over the
#                         beam-body corridor. Node identity is now NEIGHBOUR-CELL CLUSTERING
#                         (union-find, any pair <=50mm merges) with cluster spread capped at
#                         ~75mm so transitive chains cannot swallow real geometry. Census on the
#                         0.40.0 exports: faces that swallow a beam body 24 -> 0 on test4/5;
#                         249 -> 323 clean bays (the fused corridor monsters split apart).
#                         (B) COLUMNS = TRIM GEOMETRY (user proposal): with column_rects passed,
#                         raw column-layer linework inside a placed/derived footprint (fragments,
#                         rotated corners, diagonal marker strokes) is REPLACED by the footprint's
#                         exact 4-edge ring; walls stay. Beam outlines stay the primary graph.
#                         (C) ARC CHORDS >= 2x SNAP: a small fillet at 16 fixed chords put its
#                         vertices ~25mm apart -- clustering would chain-collapse them (lost a
#                         real bay on test2/3/6). Tessellation is now adaptive (2..16 chords).
#                         (D) test1-3 STAIR WELLS without a floor layer: measured beam fraction
#                         0.33 (lift shafts <0.3, real panels >=0.44) -> _MIN_BEAM_FRACTION
#                         0.3 -> 0.35 drops the wells; a wall-fraction ceiling was tried and
#                         REJECTED (it ate real bays nestled into the core's L).
#                         (E) test8 DOUBLE BEAMS on the blade-column strips (AC19-24/BC23-28):
#                         the 250x3250 blades exceed column limits (dropped, unplaced), yet the
#                         beam layer re-traces their outlines -- dedupe_beam_segments removes
#                         exact twins AND contained collinear fragments (12 on test8, 0 on all
#                         other fixtures/archives except 3 genuine degenerate cleanups), and
#                         column_outline_footprints turns closed rectangular column-layer
#                         outlines into split obstacles even when unplaced: beams along the
#                         blade bodies are dropped, the real connectors between blades stay.
#                         test8: 29 remaining solid overlaps -> 0. Suite: 15 files, 20+18 new
#                         beam-split/slab cases.
#
# 0.40.0                  BEAM/COLUMN OVERLAP (test8, client priority) + SLABS round 6, all
#                         verified offline against the 0.39.0 exports AND every archived fixture:
#                         (A) split_beams_at_columns (report.py, runs after the end snap): a beam
#                         OUTLINE drawn straight across a column no longer places a beam on top of
#                         it. Per column footprint (rects incl. rotated, circles): a crossing
#                         strictly inside the span SPLITS the beam at the column faces; a segment
#                         buried face-to-face inside one column (the column's own outline mis-read
#                         as a beam) is DROPPED; a terminal end poking >100mm PAST the column
#                         centre (drawn to the far face) is TRIMMED back to the near face. Ends AT
#                         the column centre (junction convention, the snap pass target) never
#                         move; grazing a shared face line never counts; leftovers <100mm are
#                         drafting overshoot and vanish. test8: 29 solid overlaps -> 0; ALL other
#                         fixtures incl. .archive_fixtures: zero segments changed. Slabs build
#                         from a PRE-SPLIT snapshot so bay loops still run over the columns.
#                         (B) test4/5 blank bays: member-edge faces PRUNE dangling degree-1 stubs
#                         iteratively before the face walk -- 96 pinched rings became 91 extra
#                         clean bays (158 kept+96 dropped -> 249 clean faces, zero non-simple).
#                         (C) test1-3 without a floor layer put slabs on lift shafts/stair wells:
#                         member-edge faces now need >=30% of their perimeter ON beam-layer edges
#                         (_beam_fraction); wall-bounded shaft faces fail it and are dropped.
#                         (D) test6/7 curved slab S8 missing: the junction fillet arc (~142mm) is
#                         SHORTER than the 150mm chain tolerance, so both its ends matched and
#                         greedy first-match glued the wrong one (out-and-back pinch). Slab-edge
#                         chaining now scores all four attach modes for every unused piece and
#                         takes the globally closest; duplicate re-drawn shared edges are deduped
#                         by a 10mm-grid fingerprint first. test6/7: 9 rings, 0 non-simple.
#
# 0.39.0                  SLABS round 5: the 0.38.0 arc plumbing had TWO live bugs, both fixed
#                         offline against the 0.38.0 exports (mirrored walk, every ring checked
#                         for closure + full perimeter coverage):
#                         (A) PHANTOM NEIGHBOUR ARCS: _ring_arcs attached an arc to any ring
#                         whose vertices touched the arc's ENDPOINTS -- but those are junction
#                         corners SHARED with the adjacent rectangular panel, so the neighbour's
#                         straight edge got replaced by a bulging arc (the un-pinpointable
#                         wrongness). A ring now must also TRAVERSE the arc (its mid point on
#                         the ring path).
#                         (B) BACKWARD ARC WALK: when a ring traverses an arc opposite to its
#                         recorded direction, the loop walk jumped the wrong way and skipped up
#                         to 97% of the boundary (three rings emitted 0.45m loops on a 14.5m
#                         perimeter = the persisting test6/7 error + micro-slab debris). The
#                         span logic now detects the chord run by testing which SIDE lies on the
#                         arc's circle, keys it at the run's walk-order start, and orients the
#                         emitted Arc to the walk. Verified: test1/2/3/6/7 -- every ring closes
#                         at ratio 1.000, zero gaps.
#                         (C) MEMBER-EDGE ARCS (user request): curved beam/column edges register
#                         their triples in the member-edge source too, so a face running a whole
#                         arc gets a genuine curved edge (partial runs fall back to chords).
#                         (D) DIAGNOSTICS for the remaining test4/5 failures: the export stamps
#                         cad2bim_version, raw_geometry carries 0.1mm precision (int-mm rounding
#                         made replays diverge: Revit built 255 loops where the replay built 230),
#                         slab outcomes carry error_details/skip_details strings, and a PINCH
#                         ring (same vertex twice -- passes the crossing test, fails Revit) is
#                         now caught by both the proto filter and the builder guard.

# 0.38.0  SLABS round 4: real curved edges + valid member-edge faces.
#                         (A) ARC-AWARE BOUNDARIES: a slab-layer ARC arrives as a 3-point circle
#                         fit; the ring previously took those points as TWO straight chords --
#                         the D-shaped S8 slab failed and every curve showed as line strings.
#                         Arcs are now tessellated (16 chords) for the geometry passes (labels,
#                         nesting, areas) while the true (start, mid, end) triple rides along,
#                         and the builder emits ONE genuine Arc.Create per curved stretch --
#                         welded to its neighbours, oriented to the ring walk, consumed once.
#                         Test6/7 offline: all 9 rings form (D-slab = 7.3 m2, 3 arcs), all simple.
#                         (B) MEMBER-EDGE FACES: the 99 Floor.Create errors on test4/5 come from
#                         faces threading ROUND COLUMNS' 3-point arc chords (columns exist in the
#                         Revit run but not the old export). Arc records are now tessellated in
#                         the member-edge graph (watertight), every face must be a SIMPLE ring,
#                         and the builder skips (not errors) any self-intersecting outline.
#                         (C) DIAG: raw_geometry now includes COLUMN-layer records ("cat":
#                         "column") so the member-edge source replays fully offline next round
#                         (the remaining "slab not aligned with beam outline" spots need it).

# 0.37.0  SLABS round 3, from the 0.36.0 run over the renamed Test0-Test7 set.
#                         (A) THREE outline sources, in order: slab-edge rings; NEW member-edge
#                         faces (the DRAWN beam+column outlines bound each panel with true face
#                         lines -- exact boundary, member-body strips filtered by mean width);
#                         and the beam-centreline graph whose face edges are now INSET by each
#                         beam's half width (test4/5 slabs no longer overlap the beams).
#                         (B) SLAB LABELS: "S7_150 THK." (underscore join, the fixtures' real
#                         convention) parses; the combined schedule's slab table (Mark|H|Volume,
#                         S-marks, thickness-only) is read by parse_schedule and passed into the
#                         slab pass -- test6's mark-only S1..S9 now size from their table, and
#                         one schedule LAYER may carry all three tables (category renamed
#                         "schedule (column/beam/slab)"); several layers may map to it too.
#                         (C) Floor.Create "curve loops intersect" on the curved slab: adjacent
#                         panels SHARE edges, and a shared-edge vertex sits ON the boundary where
#                         point-in-polygon is arbitrary -- a neighbour panel was swallowed as a
#                         HOLE. _ring_inside now demands strict interior clearance (50 mm), and
#                         rings are sanitized (sub-tolerance edges + collinear stops merged, the
#                         tessellated-arc boundary included) before Floor.Create.

# 0.36.0  SLABS round 2: Floor.Create fixed + UI pickers + openings.
#                         (A) "No method matches given arguments for Floor.Create": the API
#                         needs a .NET IList<CurveLoop>; a CPython3/pythonnet Python list does
#                         not convert. Loops are now packed into System.Collections.Generic.
#                         List[CurveLoop] (per the Revit 2025 API signature Floor.Create(doc,
#                         IList<CurveLoop>, floorTypeId, levelId)); placed floors are flagged
#                         structural (FLOOR_PARAM_IS_STRUCTURAL, best-effort).
#                         (B) UI: the "Create slabs" checkbox is live (auto-disabled when the
#                         model has no floor type) with a FLOOR TYPE picker; slab creation is
#                         gated on its own checkbox and uses the picked type -- no longer the
#                         model's first type behind beams' back.
#                         (C) OPENINGS: a loop lying fully inside another loop is now that
#                         floor's HOLE (stair/lift void) -- appended as an inner CurveLoop of
#                         the enclosing slab instead of stacking a second floor over it.

# 0.35.0  Test20 text-anchor fix + SLABS step 1 wired into the pushbutton.
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
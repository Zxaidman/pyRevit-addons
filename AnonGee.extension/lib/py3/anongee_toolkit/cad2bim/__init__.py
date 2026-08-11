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

__version__ = "0.68.0"  # Same behaviour, twenty modules instead of four.
#
#                         No feature and no fix: every commit in this release is a
#                         MOVE, made because four files had grown past the point where
#                         a change could be made confidently -- report.py 3039 lines,
#                         script.py 2956, stair_layout 1683, slab_outlines 1550.
#
#                             report.py       -> beam_segments, beam_cleanup,
#                                                columns_recovery, column_geom,
#                                                export, limits      (888 left)
#                             script.py       -> ui_window, run_builders, run_picking,
#                                                run_console, ui_dialogs  (962 left)
#                             stair_layout.py -> stair_runs, stair_landings,
#                                                stair_text, stair_tolerances (721)
#                             slab_outlines.py-> slab_graph, slab_labels    (445)
#
#                         The old modules re-export everything they used to define, so
#                         no call site changed. Each split was proved a no-op FOUR ways
#                         before it was committed: the unit suite, the 22 stored slab
#                         fingerprints, a stair replay over every fixture DXF, and a
#                         sweep of all 17 DXFs comparing columns, faces, nested drops,
#                         slabs, note recoveries and beams. Not one number moved.
#
#                         Two things could not be pure moves and were done deliberately.
#                         The mutable TOLERANCES are read through their owning module
#                         (slab_graph._SNAP_MM, tol._TREAD_MIN_MM) rather than
#                         from-imported, because a from-import freezes the default and
#                         silently ignores the Tolerances tab. And the pushbutton's
#                         imports of its new modules are GUARDED: they run before main()
#                         can catch anything, so a stale library would have shown a raw
#                         traceback instead of the "library out of date" dialog.
#
#                         The test loader was rebuilt too: its throwaway package now
#                         carries a real __path__, so modules import siblings by file
#                         exactly as they do in Revit -- import cycles included. Twenty
#                         hand-rolled loaders became one.
#
# 0.67.5                  A wall placed whole AND in pieces.
#
#                         The v0.67.3 export shows the roof still carrying 12 columns
#                         where its labels name 10: the 12300x300 perimeter wall plus
#                         two 2700x300 LENGTHS of that same wall. In the Revit records
#                         those pieces are closed outlines of their own, so they are
#                         placed by the ordinary path and v0.67.2's face-recovery
#                         cleanup -- which only runs when a face IS recovered -- never
#                         saw them.
#
#                         drop_nested_columns runs after every recovery pass and removes
#                         a rectangle that is a LENGTH of another: wholly inside it, the
#                         same thickness, and parallel. All three conditions matter --
#                         "inside a bigger rectangle" alone drops a 400x660 column that
#                         merely abuts a 5630x400 wall, which cost 48 real members on
#                         test12 before the rule was narrowed. With them, every drop
#                         across the fixtures is a wall drawn twice (2540x450 inside
#                         2800x450) or a literal duplicate at the same centre.
#
# 0.67.4                  HOTFIX: "Duplicate type name within an assembly".
#
#                         v0.67.3's reload has a sting: Python.NET does not merely
#                         subclass a .NET interface, it EMITS a real CLR type into a
#                         dynamic assembly, and an AppDomain -- one per Revit session --
#                         refuses a second type of the same name. Re-importing the
#                         library therefore ran those class bodies again, so the SECOND
#                         click in a session crashed. Three such classes existed:
#                         WarningSwallower, SuppressWarningsPreprocessor, and the
#                         ISelectionFilter behind "draw stair outlines" -- that last one
#                         was declared inside its own function and so had been crashing
#                         on a second PICK since long before the reload existed.
#
#                         lib/py3/anongee_clr.py now owns them. It sits OUTSIDE
#                         anongee_toolkit, so the reload cannot touch it, and it hands
#                         back the type it built the first time: the factory runs once
#                         per session however often the module is imported. Verified
#                         against a stand-in for Python.NET that raises on a duplicate
#                         name exactly as the CLR does -- three consecutive runs, one
#                         type emitted.
#
#                         A static test now walks the whole toolkit for a module-level
#                         class deriving from a Revit interface, which is the shape of
#                         this bug, so a new one cannot be added quietly.
#
# 0.67.3                  HOTFIX: the engine kept last session's library.
#
#                         "module 'naming' has no attribute 'next_level_names'" on a
#                         function that is in the file, exported, and unit-tested. The
#                         CPython3 engine outlives a run: script.py is re-read on every
#                         click, but a module it imported stays in sys.modules for the
#                         whole Revit session -- so a session that had already run
#                         v0.67.0 kept v0.67.0's naming module and the new button ran
#                         against the old library. Only restarting Revit cleared it.
#
#                         Every run now drops anongee_toolkit from sys.modules before
#                         importing, so the files on disk are what runs. The parent
#                         package's attribute goes with it: `from anongee_toolkit import
#                         cad2bim` reads that attribute and never consults sys.modules,
#                         so clearing one without the other changes nothing (verified
#                         against a simulated stale session). ezdxf and numpy are left
#                         alone -- they are the expensive imports and they do not change.
#
#                         And if a library older than the button is ever on sys.path for
#                         real -- a shadow copy of anongee_toolkit -- the run now says
#                         so up front, naming what is missing and where it loaded from,
#                         instead of failing an hour into a build.
#
# 0.67.2                  The roof's slabs, from the v0.67.0 run's own export.
#
#                         SLABS: the note recovery only ran when the slab-edge layer
#                         had ALREADY found something. On the roof of the updated test10
#                         there is no slab edge at all, so the run fell to the placed
#                         members, found no face (a bay walled on one side reads as a
#                         shaft) and built 0 slabs. The recovery now runs whatever the
#                         source found -- a note no outline covers gets its bay, with the
#                         note itself as the keep_point. Roof: 0 -> 6.
#
#                         COLUMNS: the run placed the 12300 wall AND two 2700-long pieces
#                         of that same wall, which came in as closed outlines of their
#                         own. A placed column now blocks a recovered face only while it
#                         is a fair LIKENESS of it, and any rectangle lying wholly inside
#                         a face -- however it was found -- is a piece of that member and
#                         goes. Roof: 12 columns, 2 of them doubled -> 10, one per label.
#
# 0.67.1                  HOTFIX: new levels ignored the Naming tab entirely.
#
#                         _storey_level_pairs hard-coded `"CAD Level {0}".format(...)`
#                         at the Level.Create call -- naming.level_name existed, was
#                         tested, and was never called by anything. Whatever the Naming
#                         tab said, every level created came out "CAD Level 11".
#
#                         It renders the template now, and the level template gained {o}:
#                         the level number written as an ordinal, so "{o} Floor Level"
#                         gives "3rd Floor Level" instead of the "3th" that "{n}th" makes.
#                         {label} is the plan title that storey came from.
#
#                         Better still, a model usually knows its own convention. When
#                         the levels it already has are numbered -- 00 GROUND LVL, 01 1ST
#                         FLOOR LVL., 02 2ND FLOOR LVL. -- a level this run adds now reads
#                         like the next line of that list (03 3RD FLOOR LVL.), continuing
#                         the number at its own width and moving the body's ordinal on in
#                         its own case. This is ON by default, with a tick on the Naming
#                         tab to turn it off; a model with no such pattern falls straight
#                         through to the template.
#
# 0.67.0                  Beam material, combined columns, noted slabs, saved settings.
#
#                         STRUCTURAL FRAMING TOOK NO MATERIAL. The beams outcome carried
#                         counts only: every other creator records the ids it placed under
#                         the private _element_ids key, and _create_beams did not. The
#                         material pass therefore found no beam elements and said "nothing of
#                         this kind was built" on every run with beams in it. It records them
#                         now, and a static test walks each creator's returns so a kind can
#                         never again be built without being reachable.
#
#                         COMBINED COLUMNS (test10's new roof). A wall-column carrying four
#                         columns, every piece exploded to bare lines, closes into no ring at
#                         all -- the wall's own top edge runs THROUGH each column root, so
#                         the single-cycle assembly gives up and the leftover-fragment pass
#                         guesses 45-degree blobs. The roof placed 6 members, 4 of them junk,
#                         where its labels name 10. shapes.recover_face_columns treats the
#                         soup as a planar graph -- weld, split at every T, walk the bounded
#                         faces -- and each face IS one drawn member. report.recover_face_
#                         columns keeps a face only where the plan's own size label agrees
#                         with it ("300 X 12300" within reach, dimensions matching), so no
#                         label means no column; the size limits do not apply, because the
#                         drawing and its label agreeing is better evidence than a size band.
#                         Any approximate rectangle a recovered face covers is dropped, but
#                         only when it was a FRAGMENT: a guess of the right size is the same
#                         member and keeps its place. Roof: 10 of 10. Test1/2/3 each gain the
#                         two wall-columns they were missing; every other fixture: no change.
#
#                         SLABS NOTED BUT NEVER DRAWN. The outline sources were either/or:
#                         finding ANY slab-edge ring ended the search. Test10's roof draws
#                         rings over its south bays and a single line over the north ones,
#                         yet all six carry "200 THK." -- so three slabs went missing in
#                         silence. slab_outlines.loops_for_unclaimed_notes makes the two
#                         sources additive exactly where the drawing asks: a face of the
#                         placed members is taken ONLY when it holds a thickness note that no
#                         drawn ring covers, and only when it overlaps none of them. The note
#                         doubles as the keep_point, so a bay whose fourth side is a WALL is
#                         no longer dropped as a shaft. Roof: 6 slabs. Test13, whose A-FLOR
#                         layer holds nothing but four slivers per storey, gains 47 real bays
#                         per storey. Fixtures whose notes are all covered: unchanged.
#
#                         SETTINGS THAT LAST. Only the naming templates and standard sizes
#                         survived a Revit session; everything else started from defaults
#                         each morning. The whole dialog is now captured -- driven by
#                         ui.xaml's own x:Names, so a control added tomorrow is saved the day
#                         it appears -- and restored on the next run, with Save/Load buttons
#                         in the footer for a settings file the office can share. Combos are
#                         stored by LABEL, never by ElementId, so a file reloads into another
#                         model; a control this drawing owns (the multi-storey tick and its
#                         two layers, which auto-detection answers) is saved but never
#                         restored, and a disabled control is left alone.
#
#                         TEST12's STOREYS. Four of its five captions name no ordinal
#                         ("LAYOUT AT REFUGE FLOOR LVL."), so those storeys came out unnamed
#                         AND were pushed to the bottom of the stack. A caption that names no
#                         ordinal still NAMES the storey; only its position comes from the
#                         sheet, and it now holds its place BETWEEN the titled plans either
#                         side of it. Reading order groups plans into rows by overlapping y
#                         extents (test12's five plans differ in height by 7 m and were read
#                         as five rows). Elevations are read from a note of their own
#                         ("+8.600M LVL."), not just from the title, which gives test12 its
#                         storey heights. Also: the Naming tab's footing row was never bound,
#                         so the box came up blank -- ten template keys, nine bound.
#
#                         The rows were a StackPanel of Grids with a click handler on the
#                         Grid, so the combo box and text boxes INSIDE each row swallowed the
#                         mouse before the handler ever fired -- there was nothing to click
#                         and nothing looked selected, which is exactly what the user found.
#                         They are ListBoxItems in a ListBox now: selection is native, so the
#                         row highlights, the arrow keys walk the stack and SelectedIndex is
#                         what Move/Add/Remove act on. The click is a PREVIEW handler, which
#                         tunnels to the row BEFORE its children can take it, so clicking
#                         anywhere on a row -- including on its dropdown -- selects it.
#                         Each row now shows its build number, the buttons grey out when they
#                         would do nothing (top row cannot move up), and a line beside them
#                         says "storey 2 of 5 selected".
#
# 0.66.0                  Test13's skewed beams, one progress bar, storey stack, grades.
#
#                         SKEWED BEAMS. Test13 is orthogonal throughout, yet 14 members per
#                         storey came out tilted -- one by 44 degrees -- at widths no beam
#                         has (634.9, 444.9). All came from the `rect` path: a 4-corner ring
#                         that is a TRAPEZOID, two members' edges closed into one quad by the
#                         link reader. beam_centerline_from_quad read a centreline off it
#                         anyway, taking whichever end width came first. A beam outline is a
#                         parallelogram, so a quad is refused unless its long edges run
#                         parallel AND its two end widths agree; a refused quad is exploded
#                         so its legs re-pair as the real beams they are. Test13: 14 skewed
#                         -> 0, and 193 members instead of 182. Test11 loses 4 "beams" that
#                         tapered 202mm to 60mm, which were never beams. pair_parallel_lines
#                         gained the same rule: the gap is measured at BOTH ends of the
#                         overlap now, so two converging edges cannot pair.
#
#                         ONE PROGRESS BAR for a multi-storey run: the storey is an offset
#                         into a single 0-100 over storeys x steps, captioned "storey 2/5",
#                         instead of restarting per floor.
#
#                         THE STOREY TABLE IS THE STACK. Each row picks WHICH detected plan
#                         it builds, so one typical drawing can build five floors; Move
#                         up/down reorders the stack; Add/Remove change how many storeys
#                         there are. Reused storeys SHARE their records rather than copying
#                         a whole floor's geometry five times.
#
#                         CONCRETE GRADE per element on the Materials tab, written to a
#                         parameter of its own or appended to the element's name (C12 ->
#                         "C12 (M30)"), never doubling up on a re-run.
#
#                         STAIR MATERIALS: a Stairs type holds no material -- it points at
#                         Stairs: Runs and Stairs: Landings types, and THOSE carry the tread,
#                         riser and monolithic materials. Walking to them is what was
#                         missing. SLAB TEXT is a routable layer category now; leaving it
#                         unmapped keeps the old "find notes anywhere" behaviour.
#
# 0.65.0                  Test12 prep: combined footings, Materials & Graphics tab, light
#                         filters, and the note that was naming four storeys "GROUND".
#
#                         TEST12. Four of its five storeys came out named "GROUND" from a
#                         general NOTE -- "2) THE BEAM & COLUMN SIZES MAY VARY AT GROUND &
#                         PODIUM LEVEL." mentions a storey, so every boxed plan that could
#                         see it took order 0. A note is numbered, or a whole sentence; a
#                         plan caption is neither, and is never that long. Test12's storeys
#                         now fall back to sheet order (correct -- it has no captions), while
#                         Test9 and Test10 keep every real title they had.
#
#                         COMBINED FOOTINGS. Pads that OVERLAP fuse into one footing instead
#                         of stacking two floors on each other: merging is transitive, so
#                         three columns in a row give one pad, and it repeats because a
#                         merged pad is bigger than its parents and can reach one neither
#                         touched. A group sharing an orientation keeps it. Depth follows
#                         plan AREA around the dialog's figure (the depth at one square
#                         metre), clamped to half and twice it and rounded to a buildable
#                         50mm. Footings are ON by default at 300mm minimum projection and
#                         600mm depth. The pad type is named by THICKNESS alone now that it
#                         is a floor type -- naming it after a plan size gave "F 0 X 0 X 300"
#                         and would have invented one type per column.
#
#                         MATERIALS & GRAPHICS is its own tab (anything graphical lands there
#                         from now on), and every writable material parameter is set rather
#                         than just the first -- a family can expose both the built-in
#                         structural material and its own shared one, and setting only the
#                         first leaves the visible one untouched. The pass now says when a
#                         kind had nothing built rather than reporting a silent no-op.
#
#                         VIEW FILTERS use light tints, since the fill is what identifies an
#                         element and a saturated fill over a floor plate is unreadable.
#                         Transparency is on the tab (0 = solid) and colouring the LINES is
#                         now opt-in -- the patterns alone are what was wanted.
#
# 0.64.0                  HOTFIX plus: footings as foundation SLABS, two bars, materials
#                         on instances too.
#
#                         THE CRASH first, and it was mine: 0.63.0 put live ElementIds into
#                         `outcomes` so the material pass could reach the created elements,
#                         but outcomes are JSON-exported and an ElementId is not
#                         serialisable. json.dump raised AFTER the model was built, losing
#                         the report and reporting a crash for a run that had worked -- and
#                         taking the view-filter pass, which runs later, down with it. The
#                         ids now ride under a private key that _strip_ids() removes before
#                         anything is written, and both exports carry a last-resort encoder
#                         so a stray Revit object can never fail a finished run again.
#
#                         FOOTINGS are Floor.Create against a Structural Foundation floor
#                         type -- the same call the slabs use -- instead of a foundation
#                         FAMILY instance. That is what removes the -3000 offset: a family
#                         hangs its own depth below the level it is hosted on, while a
#                         sketched pad sits ON the level, and its height offset is explicitly
#                         zeroed. The pad is still the column footprint grown by the
#                         projection and turned to the column's long axis, and it is now an
#                         editable sketch like everything else this tool places.
#
#                         TWO PROGRESS BARS. Linking and reading the CAD happens BEFORE the
#                         dialog opens, so one bar sat at whatever percent the read reached
#                         while the user filled the dialog in, then looked like it RESET when
#                         the build started. The read bar now closes as the dialog opens and
#                         a separate build bar opens when Run is pressed, each captioned and
#                         each running 0-100 over its own phase.
#
#                         MATERIALS are written to the INSTANCE as well as the type. Where a
#                         material lives is entirely up to how the family was built, and
#                         setting only the type leaves an instance-parameter family
#                         untouched -- which is what the user saw. Stairs get their own
#                         route: a stair type spreads its materials over tread, riser,
#                         landing and support parameters, none of which is the built-in
#                         structural one, which is why stairs reported 0 set.
#
# 0.63.0                  Progress bar, materials + view filters, footings, skip details.
#
#                         PROGRESS BAR. The run reported itself only into the deferred
#                         console, which a successful run never shows -- a big drawing looked
#                         like Revit had hung. The toolkit's CPython-safe ProgressBar (the one
#                         ConvertFloor uses; pyrevit.forms.ProgressBar is IronPython-only) now
#                         strips across the top of the Revit window with the stage, count and
#                         ETA, and comes down in a finally so it can never be left behind.
#                         Imported defensively: an older ui/ folder, or no host window, falls
#                         back to a no-op and the run continues.
#
#                         MATERIALS. One picker per element kind on the Structure tab, written
#                         onto the TYPES this run creates -- that is where Revit keeps a
#                         structural member's material, and every element of one size already
#                         shares a duplicated type. A floor is the exception: its material
#                         lives in the compound structure, so it goes on the structural layer.
#                         A family that exposes no material parameter is counted, not fatal.
#
#                         VIEW FILTERS. One reusable ParameterFilterElement per category,
#                         colour-coded (columns blue, beams red, slabs green, stairs purple,
#                         footings amber, grids grey), added to every OPEN view. Made once and
#                         found by name afterwards, so repeated runs do not litter the project.
#                         Template-driven views are skipped -- the template owns their filters.
#
#                         FOOTINGS. A Structural Foundation under each column on the columns'
#                         BASE level, sized column + 2 x projection and turned to the column's
#                         long axis, one type per distinct size. Round columns get a square
#                         pad. In a multi-storey run only the LOWEST storey lays them: a
#                         building has one set of foundations, not one per floor.
#
#                         SKIP DETAILS reach the export for every element kind, GROUPED by
#                         reason with a count and one example (digits masked when grouping, so
#                         900 "C##: no symbol" skips are one line, not eight truncated ones).
#                         Test2 reported 9 skipped stairs with no way to see why.
#
# 0.62.0                  Level/grid naming, shipped standard sizes, landings that meet.
#
#                         CONVENTION: anything this tool invents -- a name, a tolerance, a
#                         size -- belongs on the main dialog, never buried in code. Levels
#                         and grids were the two that had been missed: a level was always
#                         "CAD Level {n}" and a grid took its bubble text raw. Both are
#                         templates now ({n} {e} {label} for a level, {name} for a grid, so
#                         "1st Floor (L2 @3000)" or "G-A" are a typing job, not a code
#                         change), and every remaining invented name is on the tab. A grid
#                         the drawing never labelled still goes out unnamed rather than
#                         becoming a bare prefix.
#
#                         STANDARD SIZES ship with the common RC set (10 column b x h, 7 beam
#                         widths) instead of an empty box, so a drawing whose members are a
#                         couple of millimetres off round onto the size they mean out of the
#                         box. The Tolerances tab still remembers whatever is typed over them.
#
#                         LANDINGS now MEET the flight. An arrival landing was squared to the
#                         run axis, which against a fanned flight's angled outermost riser
#                         left a wedge of daylight -- the drawn riser is the landing's near
#                         edge instead. Between two flights where either is fanned, a BRIDGE
#                         landing is sketched through the four ends of the two drawn risers
#                         it joins, so it shares an edge with each exactly, in place of
#                         Revit's automatic landing (which is left to serve square flights,
#                         where it is already right).
#
#                         And a landing no longer runs through a column: notch_landings cuts
#                         the overlap out as a rectilinear STEP -- Test2 stair 1's mid landing
#                         now steps 250mm round C38 and C40, exactly as drawn. A cut that
#                         would hole the landing or take most of it away is refused, since
#                         Revit's landing sketch takes one simple loop.
#
# 0.61.0                  Naming tab, per-element tolerances, sketched winders, SW10 again.
#
#                         NAMING. Every auto-created family type was named by a hard-coded
#                         format at its Duplicate() call ("400 X 600", "200 THK"). The new
#                         Naming tab owns those as templates -- one per type, with a live
#                         preview and a validity check -- and naming.py renders them. A
#                         malformed template falls back to its default and says so rather
#                         than failing a build halfway through. Templates and the standard
#                         beam/column sizes are office conventions, not per-drawing numbers,
#                         so prefs.py keeps them in %APPDATA%/AnonGee/cad2bim.json and the
#                         dialog opens with them already filled in, session after session.
#
#                         TOLERANCES are now grouped by the element each number affects --
#                         General, Columns, Beams, Slabs, Staircase -- with each element's
#                         standard sizes sitting with its own limits instead of in a separate
#                         block at the top.
#
#                         MULTI-STOREY. Each detected plan has a checkbox: untick one and
#                         that storey is left out of the model.
#
#                         STAIRS. The spiral now gets an arrival landing -- it ended on its
#                         last riser with nothing to step onto. And a fanned flight is built
#                         with CreateSketchedRun from the DRAWN riser lines (they are the
#                         risers, the chains through their ends the boundaries, the chain
#                         through their midpoints the path), so the angled treads come out as
#                         drawn instead of being squared off by a straight run.
#
#                         SW10/SW11, third time. _anchor_growth needs exactly one end of a
#                         carved wall to be free, and Test2's has SW9 crossing below AND a
#                         900x900 column sitting on top -- so no end was ever pinned. The end
#                         to pin is the one whose neighbour merely BUTTS; the carve came from
#                         the member that runs ACROSS the wall (SW9 reaches 6000mm past it,
#                         the column only 250mm). Verified by replaying the production chain
#                         on the REVIT records in the pushed export, which is what the two
#                         earlier fixes missed: the DXF path re-tiles the core instead and
#                         was already right.
#
# 0.60.0                  Arc stairs, angled risers, multi-storey auto-detection.
#
#                         STAIRS. StaircasePlan-Test2 built 4 of its 6 stairs; the two that
#                         failed are the ones drawn with ARCS and with ANGLED risers.
#                         (a) The spiral: _spiral_run DEMANDED every line in the cluster be
#                         radial, so the stairwell walls drawn on the same layer killed it on
#                         the first line. It now SELECTS the radial lines and asks instead
#                         that they dominate the cluster and turn at an even pitch. Its 24
#                         risers are each drawn twice, which halved the going, so equal
#                         angles now merge; and the going is read across the MIDDLE when the
#                         usual walk line (300mm off a 300mm inner radius) reads an
#                         implausible 139mm for treads that are exactly 300 wide.
#                         (b) The winders: a balanced winder keeps the going constant on the
#                         walk line, so its risers ROTATE and their ends spread unevenly --
#                         the parallel detector sees a different direction per riser and
#                         finds nothing. _fan_runs recovers the flight from what is still
#                         true: the riser MIDPOINTS lie one tread apart on a straight line
#                         and the risers turn monotonically by a real angle. Test2 now plans
#                         all six stairs with no notes; across all ten DXF fixtures nothing
#                         else changed at all.
#
#                         MULTI-STOREY. The tab no longer waits to be told: autodetect_storeys
#                         reads the drawing and answers it. Layers are found by SHAPE, not by
#                         name -- the boundary layer is the one whose big disjoint boxes
#                         ENCLOSE most of the drawing (measured 1.00 on Test9 and 0.67 on
#                         Test10 against 0.28 for the best impostor, a layer of shear walls
#                         that used to be read as 24 floor plans), and the origin layer the
#                         one with exactly one small mark inside each box. The checkbox, both
#                         combos and one row per plan are filled in from that, each row
#                         carrying its OWN storey height and a repeat count auto-read from a
#                         title like "TYPICAL FLOOR PLAN (2ND TO 8TH FLOOR)". Titles that
#                         quote an elevation ("1st Floor @3.00+ Level") state the rise to the
#                         plan above, so those heights fill themselves in; a typical plan
#                         splits the rise it covers. New levels are created at each storey's
#                         own height. Test10's four boxed plans come out named and ordered
#                         Ground / 1st / (unnamed) / Terrace with the ground rise read as
#                         3000mm; Test9's three come out Upper Basement / Ground / First.
#
# 0.59.1                  HOTFIX: the dialog crashed on open with
#                         "'CadToBimWindow' object has no attribute 'tb_slab_step'" -- 0.59.0
#                         added the Min corner step box to ui.xaml and read it in both
#                         _init_tolerances and _read_tolerances, but never BOUND it with
#                         find(). Bound now, plus test_dialog_wiring.py, which parses
#                         script.py and both .xaml files statically and fails when a control
#                         is bound-but-absent or used-but-unbound -- the class of slip that
#                         only ever surfaces when the window opens inside Revit.
#
# 0.59.0                  C17's slab corners came out SLOPED: the column is 400 wide on a
#                         300 beam, so its face sits 50mm past the beam edge -- exactly the
#                         50mm node-weld slop. Two tolerances collided there. _split_at_crossings
#                         judged the beam tip's touch as "at the end" of the 400mm column face
#                         (50/400 = the slop in parameter space) so no T was cut, and the weld
#                         then pulled the column's corner onto the beam tip -- collapsing the
#                         step into a diagonal. The INTERIOR test now uses a step tolerance
#                         (slab_min_step_mm, 20mm) instead of the junction slop, and the weld
#                         refuses to merge two PINNED junctions (a T plus a corner) further
#                         apart than that -- drafting slop is a FREE TIP meeting a junction, and
#                         still welds. All four corners round C17 now step; every fixture keeps
#                         its face count and area bar the corner slivers that used to overlap
#                         the columns, and test9's third storey recovers a 18.5 m2 bay.
#
# 0.58.0                  StaircasePlan-Test2 stair 1 came out 3100 wide with its centreline
#                         300mm off. Its ten risers span x 11200..13700 (2500, the flight) but
#                         the bottom LANDING EDGE is drawn 11200..14300, straight across the
#                         600 well between the flights -- and the run's width was the UNION of
#                         its members' ends, so that one line stretched the flight over the well.
#                         A flight's span is now the MODAL riser span (the extent most of its
#                         lines actually have, always a real drawn one) instead of the union:
#                         stair 1 lands on 11200..13700 and 14300..16800 with the 600 well
#                         between, exactly as drawn. This also corrects StaircasePlan-Test1's
#                         ST-2 from 1500 to 1450 -- 16 of its risers are 1450 long and only the
#                         few boundary lines were 1500, so the union had been over-reading it.
#
# 0.57.1                  HOTFIX for the SW10/SW11 shift the user spotted after 0.57.0 -- a
#                         REGRESSION from making that fixture's schedule readable. A wall
#                         crossed by another wall is decomposed into pieces, so SW10's drawn
#                         piece stops at SW9's face: y 100..7550, 7450 long, centred 3825. Once
#                         the schedule could be read it supplied the true 7850, which was applied
#                         about the PIECE's centre -- so the wall kept centre 3825 and grew 200mm
#                         past its free end instead of growing back over the carve. _anchor_growth
#                         now pins the FREE end when a resized column grows and exactly one end
#                         abuts another rectangle: SW10 lands on y -300..7550, centre 3625, which
#                         is exactly what is drawn. A column that is already its scheduled length
#                         keeps its centre, so nothing else moves.
#
# 0.57.0                  StaircasePlan-Test2, from the fixture the user pushed mid-round.
#                         (1) ITS SCHEDULE READ NOTHING: the table is a Revit export whose mark
#                         column is headed "Comments", not "Mark", so no header was recognised
#                         and no table was found. "comments"/"comment"/"name" now head a mark
#                         column: 0 -> 119 schedule entries on that fixture (C1..C15 300x900,
#                         B1..B* 300x600), with the Height/Length columns ignored as before.
#                         (2) MOST RISERS WERE LOST, two independent causes. A line's direction
#                         is UNSIGNED, but the bucket key did not wrap, so a flight with some
#                         risers drawn end-for-end split across a "0 degrees" and a "180 degrees"
#                         bucket and lost most of its lines. And a gap of exactly TWO treads --
#                         one riser simply not drawn, a break line over it -- ended the flight,
#                         because only a gap inside the tread range continued it; such a gap now
#                         counts as k treads and the missing riser lines are rebuilt, so the
#                         count stays right. Test2 stair 1: 4+4 -> 10+10 risers; stair 6: one
#                         10-riser run -> 10+8. StaircasePlan-Test1 and StructuralPlan-Test1
#                         replay byte-identical.
#                         STILL OPEN on Test2: two stairs are drawn with ARCS (62 on S-STRS) and
#                         the riser pass reads straight lines only, so they find no flight; one
#                         more resolves a single 3-riser run. The reversed orientation of stair 2
#                         needs its DN note read for the climb direction -- next round.
#
# 0.56.0                  (1) KEYED SIZE SCHEDULES (test9's "B20(c)"): a label may carry a
#                         parenthesised KEY instead of a size, with a MARK/SIZE table
#                         ("SCHEDULE OF BEAM SIZE": (a) = 200x600) holding the sections.
#                         marks.size_key parses the key onto every text, the table reader
#                         accepts "(a)" as a mark, and _label_size resolves inline size ->
#                         schedule[mark] -> schedule[key], so columns, beams and slabs all
#                         understand the convention. On test9: 140 of 174 beam labels now size
#                         (0 before). Each storey also reads its OWN schedule first -- test9's
#                         floors disagree about what (a) means -- with the whole file as the
#                         fallback for a schedule that lives on one sheet.
#                         (2) NAME PARAMETER: the CAD mark went into Mark, full stop. The
#                         Structure tab now has an editable "Name parameter" combo (Mark,
#                         Comments, Type Mark, Type Comments, or anything typed); compat
#                         .set_element_mark writes there and falls back to Mark when a family
#                         has no such parameter, so nothing is ever lost.
#                         (3) SLOPED TRIM AT COLUMN CORNERS: the face walk can leave a short
#                         stub across a corner and the exactness pass kept it (both ends sit on
#                         real carriers), so the slab sloped where it should step.
#                         _square_off_chamfers extends the two neighbouring edges to their own
#                         crossing and replaces the stub with that corner -- but only when the
#                         stub lies along NO carrier, so a genuinely chamfered column survives.
#                         test7: 1 sloped corner -> 0, face counts unchanged (45 / 9).
#
# 0.55.0                  0.54.0 feedback (test7 drawn-outline stair + test10 grids).
#                         (1) A stair built inside a DRAWN outline came out stretched: the two
#                         flights were pushed to the bay's edges, so their width followed
#                         whatever rectangle was drawn instead of the 1250 asked for, the half
#                         landing spanned the whole bay, and the arrival landing shrank to a
#                         stub. The flights now sit SIDE BY SIDE, centred across the bay, each
#                         exactly the dialog run width; the half landing is a rectangle of the
#                         landing depth spanning the pair (2 x run width) at the turn; and the
#                         arrival landing spans the same pair. (2) The half landing was also
#                         MISSING in the model: Revit's automatic landing did not fill the turn,
#                         so the planned ring is now SKETCHED (CreateSketchedLanding at the
#                         elevation after the first flight, rounded to a riser by the API) with
#                         the automatic landing kept as the fallback and a note when it is used.
#                         (3) GRIDS ONCE PER PROJECT: a grid is a datum spanning every level, so
#                         a multi-storey run repeating the same grid per floor stacked copies.
#                         create_grids now fingerprints each line by direction + perpendicular
#                         offset (50mm), skips anything already in the model, and reports it as
#                         skipped -- which also stops a re-run duplicating the first run's grids.
#
# 0.54.0                  0.53.0 feedback. (1) DRAW the stair outlines instead of picking
#                         existing lines: "Pick detail lines in Revit" only ever offered
#                         already-drawn CurveElements, and a CAD link's lines are not
#                         selectable, so the pick looked broken. The Staircase tab now carries a
#                         "Draw stair outlines in Revit..." button -- the window CLOSES, the view
#                         comes back, and PickPoint (with Revit's real snapping to the CAD link
#                         and the model) collects corner after corner, drawing a detail line as
#                         the outline grows and closing the loop on Escape; Escape on an empty
#                         outline ends the session and the window REOPENS with every setting
#                         restored (_apply_preset). Run then builds the stairs inside those
#                         outlines. Revit forbids running its own line command from a modal
#                         dialog and the API cannot resume a posted command, which is why the
#                         outline is drawn by the script rather than by the Detail Line tool.
#                         (2) MULTI-STOREY ALIGNMENT: every storey was shifted so its origin
#                         marker landed on (0, 0), which put the model at REVIT's origin, far
#                         from the drawing. Storeys now anchor on the BASE storey's marker, so
#                         the lowest (left-most) plan does not move at all -- the model is built
#                         straight on top of its CAD -- and the upper storeys stack onto that
#                         same marker. Verified on test9/test10: base storey shift exactly
#                         0.0 mm, all three storeys split as before.
#
# 0.53.0                  0.52.0 feedback, four items. (1) ONE JSON per multi-storey run: the
#                         payload builder is split out of export_json, so the storeys collect
#                         into a single file with a `storeys` array (shared source/version/units
#                         lifted into the header, each section tagged with its storey) instead
#                         of one file per floor. (2) STAIR REGIONS FROM DETAIL LINES: a drag-box
#                         is only as accurate as the drag, so the "Draw region" source becomes
#                         "Pick detail lines in Revit" -- the user draws the outline with Revit's
#                         own tools (snapping to the CAD link and the model), picks the lines,
#                         and they chain end-to-end into closed rings of ANY shape (arcs
#                         tessellated). (3) THE SHIFTED-MODEL BUG: the layer table was built from
#                         the REVIT records alone, and Revit's import drops a bare POINT -- the
#                         floor-ORIGIN convention -- so the Origin layer never appeared in the
#                         Layers tab or the Multi-storey combos and every storey built off a
#                         guessed centre. The table is now the UNION of the Revit and DXF layers
#                         (DXF-only ones are listed in the log) and the chosen mapping is applied
#                         to both record sets. Verified on test9/test10: Origin (3 POINTs) and
#                         Boundary (3 polylines) both surface and route by convention.
#                         (4) UI: the Build tab splits into STRUCTURE (grids, columns, beams,
#                         slabs, levels, export) and ARCHITECTURE (staircases); every stair
#                         setting -- type, source, shape, dimensions -- now lives on the
#                         Staircase tab; and the Tolerances tab gains the slab and stair tunables
#                         that were module constants (node weld, edge heal, chain gap, min bay
#                         width, stair cluster gap, drawn tread min/max, arrival landing merge),
#                         pushed into the modules by apply_tolerances at run start.
#
# 0.52.0                  (1) THE MISSING STAIR LINES, found in the 0.50.0 test9 export's new
#                         stairs OUTCOME: four clusters reported "no riser lines" although they
#                         held 22-23 riser lines at a clean 300mm. Cause: a flight's positions
#                         run 300, 300, ... and then jump 800mm to the LANDING and the boundary
#                         line past it -- the group was rejected whole for being non-uniform.
#                         FIX: gaps outside the tread range now SEGMENT the group into maximal
#                         equidistant chains (_equidistant_chains), so each flight survives its
#                         own landing. test9: 5 -> 7 stairs, zero notes; test10 (6) and project1
#                         (6) unchanged; StaircasePlan/test1 replays byte-identical. Clusters
#                         smaller than 1.5m (arrow glyphs) no longer emit a note.
#                         (2) CONSOLE ON FAILURE ONLY (user request): the run is buffered from
#                         start to end and the pyRevit console is only opened when something
#                         actually goes wrong -- an exception, a rollback, or an outcome with
#                         errors. A clean run prints nothing at all; a failed one flushes the
#                         whole log (progress bar, per-phase counts, notes) for diagnosis.
#
# 0.51.0                  MULTI-STOREY from ONE dxf + generic stair SHAPES (0.50.0 feedback).
#                         (1) New Multi-storey tab: the user boxes each floor plan on a
#                         BOUNDARY layer and drops one marker per plan on an ORIGIN layer;
#                         both layers are picked BY NAME in the tab (names differ per
#                         drawing), floor_plans.split_floors turns them into one record set
#                         per storey, each SHIFTED so its marker lands on the model origin,
#                         and the build loop runs the whole pipeline once per storey on its
#                         own level pair (levels created at the tab's storey height when the
#                         model runs out). Storeys order by the plan title inside the box
#                         ("GROUND FLOOR PLAN", "LEVEL 2", "TERRACE"), else by sheet layout;
#                         a shared schedule is read from the WHOLE file, and each storey
#                         exports its own JSON. Verified on test1+test2 laid side by side:
#                         2376/2376 records routed, both storeys aligned to 0.0mm.
#                         (2) Staircase tab gains a SHAPE picker with drawn icons -- U,
#                         straight, L, C and circular -- used whenever the CAD has no stair
#                         linework to measure; L/C wrap the bay's sides, circular becomes a
#                         spiral run sized on the walk line. (3) New stair source "Draw
#                         region in Revit": the window closes, PickBox collects one box per
#                         stair from the view (Esc ends), and the chosen shape is built in
#                         each. Suite 17 files (12 floor-plan + 31 stair tests).
#                         VERIFIED on the user's new StructuralPlan-Test9/Test10: both split
#                         into their 3 storeys, every record routed, each storey aligned onto
#                         its origin POINT. Two reader fixes came out of them -- a bare POINT
#                         is now read (it is the origin convention, and was being dropped),
#                         and the markers are taken from the DXF records while the REVIT
#                         records are what gets split, because Revit's import does not always
#                         carry a POINT through. Test10's own titles order correctly
#                         ("Ground Floor @0.00+ Level" -> 0, "1st Floor @3.00+ Level" -> 1,
#                         "Typical Floor @7.00+..." -> sheet order).
#
# 0.50.0                  STAIRCASE round 4 (0.49.0 feedback): (1) RAILINGS auto-hosted on each
#                         new stair are deleted after placement (user request) -- own transaction
#                         after the edit scopes; (2) SHAPES: an L stair (two flights, one corner)
#                         places via the winding path (relaxed to 2+ multi-direction runs); a
#                         CIRCULAR stair is detected when the riser lines RADIATE from a common
#                         centre (consistent radial band; tread measured on the walk line 300mm
#                         off the inner edge) and places as one StairsRun.CreateSpiralRun; WINDER
#                         corners -- angled risers drawn in a turn instead of a flat landing --
#                         are detected (leftover riser-length lines pointing BETWEEN the flights,
#                         all inside the corner square; ST-2's break-line diagonals proved the
#                         endpoint rule necessary) and placed as a SKETCHED run through the
#                         corner (boundary/riser/path chains per the CreateSketchedRun contract),
#                         falling back to the automatic landing with a note if Revit refuses;
#                         (3) riser positions closer than a tread merge as strays instead of
#                         voiding the whole flight; (4) exports now carry the stairs OUTCOME
#                         (created/skipped/errors + notes) for offline diagnosis -- the 0.49.0
#                         project1 export replays all six stairs with every drawn line consumed,
#                         so item 1 of the feedback ("not all lines picked") needs the outcome
#                         data from a 0.50.0 run to pin down.
#
# 0.49.0                  STAIRCASE round 3 (0.48.0 feedback, four items): (1) the ARRIVAL
#                         landing now spans the parallel flights like the half landing does --
#                         runs parallel to the last one within 800mm across join its width (a
#                         U stair gets the full ~3000; a winding stair's opposite flight sits
#                         across the WELL, so there it stays one run wide); (2) WINDING stairs
#                         (Project1's squares): the riser-line pass keeps EVERY direction
#                         bucket, so a four-flight stair around a well comes back whole --
#                         flights ordered counterclockwise around the well centre, each climbing
#                         tangentially, corner landings between every consecutive pair (the
#                         builder now bridges ALL pairs, not just the first two). All six
#                         Project1 stairs replay as 4-run spirals (5/7/3/7 risers etc.);
#                         (3) an explicit STAIR SOURCE toggle on the Staircase tab -- Auto
#                         (linework, else text) / Drawn stair linework / Text + numbers -- so
#                         the two options are user-selectable instead of implicit; (4) the riser
#                         count now DEFAULTS to storey / max riser rounded up (20 for 3000/150,
#                         live-refreshed on level changes; typing a count makes it absolute as
#                         before), and a WAIST THICKNESS field (default 200) pushes the
#                         structural depth onto duplicated run + landing types.
#
# 0.48.0                  STAIRCASE round 2 (user's three items after the first stairs placed):
#                         (1) Staircase tab gains RISER COUNT (0 = auto) + a live FLOOR HEIGHT
#                         readout -- the count is ABSOLUTE: riser height syncs to storey / count
#                         (level combo changes re-sync it), and the layout uses the count over
#                         the max-riser rule; (2) Build tab gains a STAIR TYPE picker (defaults
#                         to the type containing "cast" -- Cast-In-Place), the user's numbers
#                         duplicate the PICKED type, and "Create staircases" is checked by
#                         default (disabled only when the model has no stair type); (3) the
#                         ARRIVAL landing: every plan now carries a top_landing rectangle
#                         continuing past the last run's top end (depth = landing depth, width =
#                         run width), placed via StairsLanding.CreateSketchedLanding at the full
#                         storey elevation (relative to the stairs base per the API contract).
#
# 0.47.1                  HOTFIX (user's pushbutton run): "cannot import name 'StairsEditScope'
#                         from 'Autodesk.Revit.DB.Architecture'" -- StairsEditScope lives in
#                         Autodesk.Revit.DB (verified against revitapidocs.com/2025); only
#                         StairsRun / StairsLanding / StairsRunJustification are in the
#                         .Architecture namespace. Two more fixes from the same API check:
#                         (1) a run's location line carries its BASE ELEVATION in Z (was 0) --
#                         run 1 starts on the base level, run 2 at base + run 1's rise; (2) the
#                         stairs type (user's riser/tread/width) now switches BEFORE the runs
#                         are created, because CreateStraightRun derives riser/tread counts from
#                         the type at creation time. Transaction rollback added before
#                         scope.Cancel on failure.
#
# 0.47.0                  STAIRCASE OPTION 2 (user's spec): the stair-layer LINEWORK drives the
#                         layout. Riser lines cluster into stairs (bbox union-find), the dominant
#                         parallel direction is the riser direction (same-length filter keeps the
#                         drawn landing boundary from bridging the runs), overlapping spans group
#                         the lines into RUNS: tread = drawn spacing, run width = drawn riser
#                         length, riser count = drawn line count (deduped -- each riser is drawn
#                         once per panel), riser height = storey / drawn total, landing = the
#                         drawn leftover next to the riser extent, first run climbs INTO the
#                         landing edge and the second climbs out (180 turn). The chain prefers
#                         linework and falls back to option 1 (text + dialog numbers) when the
#                         plan has no usable stair layer -- console prints the source. Replays:
#                         StaircasePlan ST-1/ST-2 and test1 both reproduce the DRAWN stair
#                         exactly (turn edge 12650, tread 300, width 1500, landing 1500,
#                         10+10 risers @ 150); test4 (no stair layer) falls back to text.
#
# 0.46.0                  STAIRCASE OPTION 1 (user's spec): a generic DOG-LEG stair from dialog
#                         numbers, located by plan TEXT -- no stair linework read. New Staircase
#                         tab (riser height max, tread depth, run width, landing depth; landing 0
#                         = run width) + "Create staircases" in Build. A STAIRCASE / ST-n text
#                         marks the stair; its bay comes from the placed-members faces with the
#                         new keep_points relaxation (a wall-bounded stair bay is dropped as a
#                         shaft by the slab chain -- keep_points bypasses the beam-fraction and
#                         body-coverage filters for the face under the text). Riser count =
#                         storey height / riser, rounded up; actual riser recomputed; risers
#                         split across two runs anchored at the landing edge; a DN/UP note picks
#                         the landing end. stair_layout.py (Revit-free, tested) plans;
#                         builders/stairs.py places -- one StairsEditScope per stair, runs via
#                         StairsRun.CreateStraightRun, automatic landing between them, user
#                         numbers pushed onto a duplicated stairs type. Exports now carry stair/
#                         wall-layer raw geometry (cat "stair"/"wall") and STAIRCASE/ST-n/DN/UP
#                         notes in texts_sized, so stair runs replay offline. Option 2 (stair
#                         LINEWORK drives the layout) is next. Offline: fixture replays plan 2
#                         stairs on test1 and both ST-1/ST-2 on the staircase plan (turn edge
#                         exactly landing-depth from the DN wall); slab counts/truth unchanged.
#
# 0.45.4                  REVERT to the 0.45.2 slab logic (the user's Revit run showed 0.45.3's
#                         body-clip did NOT fix the intended 50mm-offset gap, so per the agreed
#                         fallback the current-best behavior returns) + RENAME: the slab pipeline
#                         is production now, so slabs_proto.py -> slab_outlines.py (test file
#                         follows), and the "prototype" naming is retired from the pushbutton
#                         console line ("Slabs -- source: ...") and every comment/docstring.
#                         Replay counts identical to 0.45.2 (45/50/50/323/323/9, truth 137/137).
#
# 0.45.3                  (reverted in 0.45.4 -- no improvement in the Revit run)
#                         BODY-CLIP column trims (user's algorithm). Residual test4/5 defect:
#                         when a column edge sits ~50mm from a beam edge, the 50mm graph weld
#                         collapses the two nodes into one -- the step vanishes and the slab
#                         jumps from the column end straight to the beam corner, leaving a gap
#                         against the placed elements. The user's read was right: the snap
#                         tolerance eats the offset. FIX: before the column footprint ring
#                         enters the edge graph, each ring edge (and round-column chord) is
#                         CLIPPED against every placed beam BODY rectangle
#                         (_beam_body_rects + _clip_out_bodies); only the parts protruding
#                         beyond the beams survive, and their endpoints land EXACTLY on the
#                         beam edge line -- no near-miss node pair, nothing for the weld to
#                         collapse. Column edges buried inside a beam body (the 47mm bulges
#                         old code pushed INTO the beam) disappear outright. Carriers keep the
#                         full unclipped rect edges so the exactness pass still has the true
#                         column lines. Offline: counts unchanged (45/50/50/323/323/9),
#                         truth 137/137 on the 0.44.0 paired exports, 55 test4/5 faces
#                         corrected by 10-47mm, builder mirror fully contiguous.
#
# 0.45.2                  TRIMS RESTORED with the culprit fixed. The 0.45.1 isolation run was
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
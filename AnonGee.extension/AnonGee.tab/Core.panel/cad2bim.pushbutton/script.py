#! python3
# -*- coding: utf-8 -*-
"""CAD to BIM -- pick a DXF, link it, and build Revit structure from it.

Workflow (CAD-free model is the normal case):
  1. Pick a .dxf, choose its drawing unit and positioning (Link DXF dialog).
  2. Link it programmatically (like Revit's Link CAD dialog).
  3. Hybrid extraction: read the Revit link's geometry (internal feet) AND read the
     same DXF with ezdxf for geometry + TEXT; align them with the link transform.
  4. Compare the two to find problem geometry (Revit clips/merges at junctions) and
     build from the cleaner ezdxf geometry.
  5. Classify layers, refine sizes from text marks ("C1 400x400"), and create grids,
     columns and beams in a TransactionGroup with warning suppression.

CPython3 engine compliance (AnonGee Brand Guidelines 12.1 / 12.8.4 / 12.9):
  * `#! python3` shebang on line 1; explicit imports only.
  * NO pyRevit IronPython modules (pyrevit.forms / pyrevit.revit) -- they crash the
    CPython3 engine. Windows load via XamlReader.Load from a .xaml file; the active
    document comes from `__revit__`; dialogs use System.Windows.MessageBox and
    System.Windows.Forms file dialogs (mirrors the shipping BIM Generation tool).
  * Model writes happen after the modal window closes, on the Revit API thread.

The cad2bim package lives in lib/py3/anongee_toolkit; path_resolver puts lib/py3
on sys.path. If the banner's version/path is not what you expect, a stale shadow
copy is on sys.path.
"""

__title__ = "CAD to BIM"
__author__ = "AnonGee"
__min_revit_ver__ = 2022

import os
import re
import sys
import traceback

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xml")
clr.AddReference("System.Windows.Forms")

# The dialogs and their WPF plumbing live in the library now (cad2bim.ui_window,
# cad2bim.ui_dialogs); the CLR references stay because pyRevit resolves them per
# script and the library modules are imported through this one.


def _bootstrap_lib_path():
    """Put the engine-appropriate lib subfolder (py2/py3) on sys.path.

    Primary: the repo's own path_resolver, which pyRevit makes importable by
    adding the extension `lib/` folder to sys.path. Fallback: climb from this
    file to find the `lib` dir and inject py2/py3 directly.
    """
    try:
        import path_resolver
        path_resolver.update_paths()
        return
    except ImportError:
        pass

    sub = "py3" if sys.version_info[0] == 3 else "py2"
    try:
        cursor = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return

    for _ in range(8):  # bounded: button -> panel -> tab -> extension -> lib
        candidate = os.path.join(cursor, "lib", sub)
        if os.path.isdir(candidate):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return
        cursor = parent


def _drop_stale_modules():
    """Forget any anongee_toolkit modules the ENGINE is still holding.

    The CPython3 engine outlives a run: this file is re-read every click, but a
    module it imported stays in sys.modules for the whole Revit session. Update
    the extension and the new script runs against the OLD library -- v0.67.1's
    `naming.next_level_names` was on disk, in the file, tested, and missing at
    runtime, because a session that had already run v0.67.0 kept v0.67.0's
    naming module. Nothing short of restarting Revit fixed it.

    So each run starts from the files on disk. The parent package's attribute
    goes too: `from anongee_toolkit import cad2bim` reads the attribute off the
    already-imported parent and never consults sys.modules, so clearing one
    without the other changes nothing. ezdxf, numpy and the rest are untouched
    -- they are the expensive imports, and they do not change under us.
    """
    stale = [name for name in list(sys.modules)
             if name == "anongee_toolkit" or name.startswith("anongee_toolkit.")]
    parent = sys.modules.get("anongee_toolkit")
    for name in stale:
        del sys.modules[name]
    if parent is not None:
        for attribute in ("cad2bim", "revit", "ui"):
            try:
                delattr(parent, attribute)
            except AttributeError:
                pass


_bootstrap_lib_path()
_drop_stale_modules()

# NOT purged above, and deliberately: it holds the CLR types Python.NET emitted
# for this Revit session. Rebuilding one of those raises "Duplicate type name
# within an assembly", so the registry has to outlive the reload.
import anongee_clr                      # noqa: F401  (imported for its lifetime)

from anongee_toolkit import cad2bim
from anongee_toolkit.cad2bim import (advanced, compat, config, floor_plans,
                                     foundation_plan, naming, prefs, report,
                                     settings, slab_outlines, stair_layout)
from anongee_toolkit.cad2bim.geom import transform, compare
from anongee_toolkit.cad2bim.classify import layers, marks
from anongee_toolkit.cad2bim.readers import geometry_reader, dxf_reader, dxf_linker
# The console and the progress bars moved to the library; the names keep their
# underscores so every call site here reads exactly as it did.
# The modules this button was split into. A library OLDER than the button will
# not have them at all, and an ImportError here -- at module level, before main()
# can catch anything -- is a raw traceback instead of the explanation
# _library_mismatch exists to give. So the failure is caught and DEFERRED: the
# names are stubbed, and main() reports it properly on the first line it runs.
_MISSING_MODULE = None
try:
    from anongee_toolkit.cad2bim import ui_window
    from anongee_toolkit.cad2bim.run_builders import (   # noqa: F401
        _create_grids, _create_columns, _create_beams, _create_footings,
        _create_slabs, _create_stairs, _apply_materials, _colour_open_views,
        _strip_ids)
    from anongee_toolkit.cad2bim.run_picking import _draw_stair_outlines
    from anongee_toolkit.cad2bim.ui_window import (CadToBimWindow,
                                                   LinkOptionsDialog)
    from anongee_toolkit.cad2bim.ui_dialogs import _alert, _error, _save_json
    from anongee_toolkit.cad2bim.run_console import (      # noqa: F401
        _OUT, _say, _progress, _open_progress, _close_progress, _storey_span,
        _READ_STEPS, _BUILD_STEPS)
except ImportError as import_error:
    _MISSING_MODULE = str(import_error)

    # Fallbacks, so the run can still SAY what went wrong: every one of these
    # names is used before -- and by -- the mismatch report itself.
    def _say(message=""):
        print(message)

    def _alert(title, message):
        from System.Windows import MessageBox
        MessageBox.Show(message, title)

    def _error(title, message, detail=None):
        from System.Windows import MessageBox
        MessageBox.Show("{0}\n\n{1}".format(message, detail or ""), title)

    def _close_progress():
        pass

    class _StubOut(object):
        """Enough of the deferred console for the failure path to report."""
        live = True

        def say(self, message=""):
            print(message)

        def fail(self):
            pass

        def flush(self):
            pass

        def finish(self, outcomes=None):
            pass

    _OUT = _StubOut()
from anongee_toolkit.cad2bim.builders import (beams, columns, footings,
                                              materials, slabs, stairs,
                                              txn_failures)

_HERE = os.path.dirname(os.path.abspath(__file__))
_XAML = os.path.join(_HERE, "ui.xaml")
_LINK_XAML = os.path.join(_HERE, "link_options.xaml")
_ADVANCED_XAML = os.path.join(_HERE, "advanced.xaml")
# the windows live in the library; their .xaml lives here, beside the button
if _MISSING_MODULE is None:
    ui_window.use_xaml(_XAML, _LINK_XAML, _ADVANCED_XAML)

# What this button needs the library to have. Checked once, up front, so a
# library older than the button says so plainly instead of failing an hour into
# a build with "module has no attribute" (0.67.1, mid multi-storey run).
_REQUIRED = ((naming, ("level_name", "next_level_names", "ordinal")),
             (report, ("recover_face_columns", "build_beam_segments")),
             (slab_outlines, ("loops_for_unclaimed_notes",)),
             (settings, ("payload", "restorable")),
             (materials, ("apply", "apply_grade")))


def _library_mismatch():
    """A sentence naming what is missing and where the library came from, or None."""
    missing = ["{0}.{1}".format(module.__name__.rsplit(".", 1)[-1], attribute)
               for module, attributes in _REQUIRED for attribute in attributes
               if not hasattr(module, attribute)]
    if _MISSING_MODULE:
        missing.insert(0, _MISSING_MODULE)   # a module that is not there at all
    if not missing:
        return None
    return ("This button needs a newer cad2bim library.\n\nMissing: {0}\n\n"
            "Loaded from:\n{1}\n\nVersion: {2}\n\nThe copy on sys.path is older "
            "than the button. Check for a second anongee_toolkit folder "
            "shadowing the extension's lib/py3.".format(
                ", ".join(missing), getattr(cad2bim, "__file__", "?"),
                getattr(cad2bim, "__version__", "?")))





























# A size label within this distance of a member refines it; also the proximity the
# comparison uses to decide "this is the same member" (~half a column).
_COMPARE_TOL_FT = 300.0 / 304.8



# --- dialogs / messaging (System.Windows only -- no pyRevit) -----------------





























# --- Link DXF dialog (file + unit + positioning) -----------------------------



# --- main mapping / build window (capture-only) ------------------------------



def _layer_names(records):
    """Distinct layer keys present in a record list, sorted for stable display."""
    return sorted(set(r.layer_key for r in records))


def _grid_axis_positions(records):
    """(grid_x, grid_y) lists in internal feet from the grid lines: a vertical
    grid contributes its x, a horizontal grid its y. Used to snap columns."""
    grid_x, grid_y = set(), set()
    for record in records:
        if layers.classify_layer(record.layer_key) != layers.CATEGORY_GRID:
            continue
        if record.kind != "line" or len(record.points) < 2:
            continue
        p0, p1 = record.points[0], record.points[-1]
        if abs(p1[0] - p0[0]) <= abs(p1[1] - p0[1]):
            grid_x.add((p0[0] + p1[0]) / 2.0)   # vertical grid -> constant x
        else:
            grid_y.add((p0[1] + p1[1]) / 2.0)   # horizontal grid -> constant y
    return sorted(grid_x), sorted(grid_y)


def main():
    uidoc = getattr(__revit__, "ActiveUIDocument", None)
    if uidoc is None or uidoc.Document is None:
        _alert("No document", "Open a Revit project before running CAD to BIM.")
        return
    doc = uidoc.Document

    module_dir = os.path.dirname(os.path.abspath(report.__file__))
    _say("cad2bim {0} loaded from {1}".format(cad2bim.__version__, module_dir))
    mismatch = _library_mismatch()
    if mismatch:
        _say(mismatch)
        _error("cad2bim library out of date", mismatch)
        return
    _say(compat.runtime_summary())
    try:
        _say("Host: Revit {0}".format(__revit__.Application.VersionNumber))
    except Exception:
        pass

    if not dxf_reader.ezdxf_available():
        _error("ezdxf not available",
               "ezdxf could not be imported on this engine.\n\nIf you just "
               "provisioned it, run the button again (or fully restart Revit). "
               "Otherwise run tools/auto_provision.py to install it into lib/py3.",
               detail=str(dxf_reader._EZDXF_ERROR))
        return

    # 1. Pick the DXF + its unit + positioning, then link it (own transaction).
    active_view_name = getattr(getattr(doc, "ActiveView", None), "Name", "-")
    options = LinkOptionsDialog(active_view_name)
    options.show()
    if not options.result:
        return
    path = options.result["path"]
    _open_progress("read")
    _progress(1, _READ_STEPS, "link DXF")
    try:
        instance = dxf_linker.link_dxf(doc, path, options.result["unit"],
                                       options.result["placement"],
                                       this_view_only=options.result["this_view_only"])
    except Exception:
        _error("Link failed", "Could not link the DXF.", traceback.format_exc())
        _OUT.finish()
        return

    # 2. Hybrid read: Revit link geometry is the BUILD source (already in Revit
    #    coordinates and pre-merged into polylines). The DXF (ezdxf) supplies TEXT
    #    only, mapped into Revit coordinates by the link's own exact transform.
    _progress(2, _READ_STEPS, "read link geometry")
    revit_result = geometry_reader.read_link(doc, instance)
    if revit_result.is_empty():
        _alert("Empty link", "The linked DXF produced no readable geometry in "
               "Revit. Check the link is visible in the active view.")
        _OUT.fail()
        _OUT.finish()
        return
    try:
        dxf_result = dxf_reader.read_dxf(path)
    except Exception:
        _error("DXF read failed", "Could not read the DXF for text.", traceback.format_exc())
        _OUT.finish()
        return

    # Map DXF coords -> Revit feet using the GRID lines as anchors: they are the
    # same lines in both the Revit and DXF extractions, so aligning their bounding
    # boxes is exact (no symbol-space unit guessing). A plan with NO grid layer
    # (Test20 stress plan) anchors on ALL shared geometry instead -- the two reads
    # are the same drawing, so their overall bboxes align the same way. Only when
    # both anchors are empty do we trust the link's own transform: Revit can bake
    # the unit scale into the imported geometry and report an identity instance
    # transform, which threw every Test20 label 304.8x off and killed all sizing.
    rev_grids = [r for r in revit_result.records
                 if layers.classify_layer(r.layer_key) == layers.CATEGORY_GRID]
    dxf_grids = [r for r in dxf_result.records
                 if layers.classify_layer(r.layer_key) == layers.CATEGORY_GRID]
    rev_bbox = transform.bbox_of_records(rev_grids)
    dxf_bbox = transform.bbox_of_records(dxf_grids)
    rev_all = transform.bbox_of_records(revit_result.records)
    dxf_all = transform.bbox_of_records(dxf_result.records)
    if rev_bbox and dxf_bbox:
        text_affine = transform.empirical_affine(dxf_bbox, rev_bbox)
        transform_method = "grid_anchored"
    elif rev_all and dxf_all:
        text_affine = transform.empirical_affine(dxf_all, rev_all)
        transform_method = "geometry_anchored"
    else:
        text_affine = transform.from_link(instance)
        transform_method = "link_GetTotalTransform"
    transform.apply_to_texts(text_affine, dxf_result.texts)
    marks.parse_texts(dxf_result.texts)
    # Map a copy of the DXF geometry the same way, only to report problem geometry.
    transform.apply_to_records(text_affine, dxf_result.records)
    # HATCH regions come from the DXF only -- the Revit API cannot read a hatch
    # inside a link any more than it can read text -- so they take the same
    # affine the texts do. A region carries `points` like a record, which is
    # what lets apply_to_records move it.
    transform.apply_to_records(text_affine, dxf_result.regions)

    # Build the window from the REVIT records (the build source) UNIONED with the
    # DXF-only layers. Revit's import drops some entity types outright -- a bare
    # POINT is the floor-ORIGIN convention and never survives it -- so a layer
    # that exists only in the DXF was invisible in this table and unmappable,
    # which left multi-storey runs without an origin and every storey shifted.
    layer_counts = report.build_layer_counts(revit_result.records)
    dxf_counts = report.build_layer_counts(dxf_result.records)
    # HATCH-only layers get a row too. A hatch is a region, not a record, so a
    # layer carrying nothing else (Project1's COLUMN HATCH_ASC, test9's legend
    # swatches) had no row, no combo, and no route to fold/sunk -- the P2
    # categories were unreachable exactly where they are needed.
    region_counts = {}
    for region in dxf_result.regions:
        region_counts[region.layer_key] = region_counts.get(region.layer_key,
                                                            0) + 1
    names = sorted(set(layer_counts) | set(dxf_counts) | set(region_counts))
    layer_rows = []
    for name in names:
        revit_n = layer_counts.get(name, {}).get("count", 0)
        dxf_n = dxf_counts.get(name, {}).get("count", 0)
        layer_rows.append((name, revit_n or dxf_n or region_counts.get(name, 0)))
    dxf_only = [name for name in names if not layer_counts.get(name)]
    if dxf_only:
        _say("Layers present in the DXF but not in the Revit link (still "
             "mappable): {0}".format(", ".join(dxf_only)))
    default_mapping = layers.build_default_mapping(names)
    column_symbols = columns.structural_column_symbols(doc)
    level_options = columns.levels(doc)
    beam_symbols = beams.structural_framing_symbols(doc)
    floor_type_options = slabs.floor_types(doc)
    stair_type_options = stairs.stairs_types(doc)
    footing_type_options = footings.foundation_types(doc)
    material_options = materials.materials(doc)
    level_elevations = {label: doc.GetElement(level_id).Elevation
                        for label, level_id in level_options}

    # Text layers (size marks) come from the DXF, routed separately from geometry.
    text_layer_counts = {}
    for text in dxf_result.texts:
        text_layer_counts[text.layer_key] = text_layer_counts.get(text.layer_key, 0) + 1
    text_names = sorted(text_layer_counts.keys())
    text_layer_rows = [(name, text_layer_counts[name]) for name in text_names]
    default_text_mapping = layers.build_default_text_mapping(text_names)

    # Preferences come BEFORE any planning: the saved ADVANCED overrides
    # rebind module constants, and the storey detection a few lines down is
    # already a consumer (floor_plans reads its region and coverage
    # thresholds at call time). Naming templates and standard sizes are
    # office conventions, not per-drawing numbers, so they come back from the
    # preferences file the last run wrote.
    saved_naming = naming.load()
    _saved_prefs = prefs.load()
    saved_standards = _saved_prefs.get("standards") or {}
    # ... and the rest of the dialog comes back too: every tolerance, tick and
    # dropdown the last run finished with, restored by name
    saved_settings = _saved_prefs.get("dialog") or None
    advanced.apply(_saved_prefs.get("advanced") or {})
    for problem in advanced.problems():
        _say("advanced: {0}".format(problem))

    # Is this ONE plan or a sheet of storeys? Read off the DXF (its bare origin
    # POINTs do not always survive Revit's import) so the Multi-storey tab opens
    # already answered instead of waiting for the user to guess two layer names.
    storey_detection = floor_plans.autodetect_storeys(dxf_result.records,
                                                      dxf_result.texts)
    _say("Storeys: {0}".format(storey_detection.reason))
    for note in storey_detection.notes:
        _say("  storey: {0}".format(note))

    # The dialog can hand the view back so the user DRAWS the stair outlines:
    # it closes, the outlines are picked in the model, and it reopens with every
    # setting restored. Anything else falls straight through to the build.
    preset = None
    stair_regions = []
    _close_progress()          # the read is done: the dialog is the user's turn
    while True:
        window = CadToBimWindow(dxf_result.source_name, layer_rows,
                                list(layers.ALL_CATEGORIES), default_mapping,
                                column_symbols, level_options, beam_symbols,
                                floor_type_options,
                                text_layer_rows, list(layers.TEXT_CATEGORIES),
                                default_text_mapping,
                                stair_type_options=stair_type_options,
                                level_elevations=level_elevations,
                                stair_regions=stair_regions, preset=preset,
                                storey_detection=storey_detection,
                                saved_naming=saved_naming,
                                saved_standards=saved_standards,
                                footing_type_options=footing_type_options,
                                material_options=material_options,
                                saved_settings=saved_settings)
        window.show()
        if not window.result:
            return   # cancelled -- nothing was flushed, console stays closed
        if window.result.get("action") != "draw_stairs":
            break
        preset = window.result
        drawn = _draw_stair_outlines(doc)
        if drawn:
            stair_regions = drawn
        preset["stair_regions"] = stair_regions

    selections = window.result
    _open_progress("build")
    layers.apply_mapping(revit_result.records, selections["mapping"])
    # the DXF records carry the markers a Revit import drops, so they get the
    # SAME mapping -- otherwise a DXF-only layer stays uncategorised
    layers.apply_mapping(dxf_result.records, selections["mapping"])
    # ...and so do the hatches, which is what tells a fold region from a sunk
    # one and both from the column fill on the layer next to them.
    layers.apply_mapping(dxf_result.regions, selections["mapping"])
    # The Multi-storey tab picks the boundary/origin layers BY NAME (they differ
    # per drawing), so route them here -- after the layer table, so an explicit
    # pick always wins over the naming convention.
    for layer_name, category in ((selections.get("boundary_layer"),
                                  layers.CATEGORY_FLOOR_BOUNDARY),
                                 (selections.get("origin_layer"),
                                  layers.CATEGORY_FLOOR_ORIGIN)):
        if not layer_name:
            continue
        for record in list(revit_result.records) + list(dxf_result.records):
            if record.layer_key == layer_name:
                record.category = category
    limits = selections.get("limits")
    standards = selections.get("standards")
    tolerances = selections.get("tolerances") or {}
    # the dialog owns every tunable, including the ones that used to be module
    # constants in the slab, stair and foundation geometry
    slab_outlines.apply_tolerances(tolerances)
    stair_layout.apply_tolerances(tolerances)
    foundation_plan.apply_tolerances(tolerances)
    # ...and the Advanced window's overrides bind for THIS run too, or an edit
    # made behind the gate would only take effect next session
    advanced.apply(selections.get("advanced") or {})
    for problem in advanced.problems():
        _say("advanced: {0}".format(problem))
    # every element writes its CAD mark into the parameter chosen on the
    # Build > General sub-tab (Mark stays the fallback when a family lacks it)
    compat.set_name_parameter(selections.get("name_parameter"))
    # every auto-created family type is named from the Naming tab's templates
    naming.apply(selections.get("naming"))
    for problem in naming.problems():
        _say("naming: {0}".format(problem))

    # Diagnostic only: how much Revit's import dropped/clipped vs the raw DXF.
    compare_tol_ft = config.mm_to_ft(tolerances.get("compare_tol_mm",
                                                    config.DEFAULTS["compare_tol_mm"]))
    comparison = compare.diff(revit_result.records, dxf_result.records, compare_tol_ft)
    comparison["transform"] = {"method": transform_method}

    # MULTI-STOREY: one dxf holding several floor plans, each boxed on the
    # boundary layer with an origin marker inside. Each storey is built by the
    # SAME pipeline below, on its own level pair, from records shifted so its
    # marker lands on the model origin.
    storeys = None
    if selections.get("multistorey"):
        # the boundary rectangle and origin POINT come from the DXF read (a
        # bare POINT does not always survive Revit's import), and the RECORDS
        # split by them are the Revit ones the pipeline builds from
        regions, floor_notes = floor_plans.split_floors(
            revit_result.records, dxf_result.texts,
            marker_records=dxf_result.records,
            boundary_layer=selections.get("boundary_layer"),
            origin_layer=selections.get("origin_layer"),
            hatches=dxf_result.regions)
        for note in floor_notes:
            _say("  storey: {0}".format(note))
        regions = floor_plans.apply_storey_settings(
            regions, selections.get("storey_settings"))
        if len(regions) > 1:
            _say("Multi-storey: {0} floor plan(s) found -- {1}".format(
                len(regions),
                ", ".join((r.label or "storey {0}".format(i + 1))
                          for i, r in enumerate(regions))))
            storeys = regions
        elif regions:
            _say("Multi-storey: only one floor plan found -- building it alone.")
        else:
            _say("Multi-storey: no floor boundaries found -- building the whole "
                 "drawing as one storey.")

    if storeys:
        # A TYPICAL plan builds once per repeat, each on its own level pair, so
        # the ladder is sized from the EXPANDED list, not the plan count.
        built = floor_plans.expand_repeats(storeys)
        level_pairs = _storey_level_pairs(doc, selections, built)
        storey_payloads = []
        all_outcomes = {}
        for index, (region, label) in enumerate(built):
            base_id, top_id = level_pairs[index]
            _storey_span(index, len(built))
            _say("")
            _say("=== {0} ({1} records) ===".format(label, len(region.records)))
            storey_selections = dict(selections)
            storey_selections["base_level_id"] = base_id
            storey_selections["top_level_id"] = top_id
            # a building has ONE set of foundations: only the lowest storey
            # lays them, on its own base level
            storey_selections["build_footings"] = (index == 0)
            storey_result = _StoreyResult(revit_result, region.records)
            outcomes = _build_one_storey(
                doc, storey_result, region.texts, storey_selections,
                schedule_source=dxf_result.texts, path=path,
                comparison=comparison, transform_method=transform_method,
                storey_label=label, collect=storey_payloads,
                hatches=region.regions)
            all_outcomes["{0}".format(label)] = outcomes
        if storey_payloads:
            _export_storeys(storey_payloads, revit_result.source_name,
                            _export_name(path, selections))
        _colour_open_views(doc, uidoc, selections)
        _OUT.finish(all_outcomes)
        return

    outcomes = _build_one_storey(doc, revit_result, dxf_result.texts, selections,
                                 schedule_source=dxf_result.texts, path=path,
                                 comparison=comparison,
                                 transform_method=transform_method,
                                 hatches=dxf_result.regions)
    _colour_open_views(doc, uidoc, selections)
    _OUT.finish(outcomes)


class _StoreyResult(object):
    """One storey's read result: the parent result with its records swapped."""

    def __init__(self, base_result, records):
        self.__dict__.update(base_result.__dict__)
        self.records = records


def _storey_level_pairs(doc, selections, built):
    """[(base_level_id, top_level_id)] for the storeys in `built`, lowest first.

    `built` is [(region, label)] with typical plans already repeated. The lowest
    storey sits on the chosen base level and each one above it moves up a level.
    When the model runs out, new levels are created -- each at ITS OWN storey's
    height (the Multi-storey tab's per-plan Height column), falling back to the
    single storey height when a row was left blank.
    """
    from Autodesk.Revit.DB import Level, Transaction, FilteredElementCollector

    count = len(built)
    default_mm = (selections.get("storey_height_mm")
                  or config.DEFAULTS["storey_height_mm"])
    heights_mm = [(getattr(region, "storey_height_mm", None) or default_mm)
                  for region, _label in built]

    existing = sorted(FilteredElementCollector(doc).OfClass(Level).ToElements(),
                      key=lambda lv: lv.Elevation)
    base_id = selections.get("base_level_id")
    start = 0
    for i, level in enumerate(existing):
        if level.Id == base_id:
            start = i
            break
    ladder = existing[start:]
    needed = count + 1
    # How the new levels are NAMED: either continue what the model already calls
    # its levels ("02 2ND FLOOR LVL." -> "03 3RD FLOOR LVL."), which is what an
    # office template arrives with, or render the Naming tab's level template.
    convention = None
    if selections.get("level_follow_existing", True):
        convention = naming.next_level_names(
            [compat.get_element_name(level) for level in existing],
            max(needed - len(ladder), 0))
        if convention:
            _say("Multi-storey: naming new levels after the model's own "
                 "convention ({0} ...)".format(convention[0]))
    if len(ladder) < needed:
        transaction = Transaction(doc, "CAD to BIM: storey levels")
        transaction.Start()
        try:
            txn_failures.attach_warning_swallower(transaction)
            created = 0
            while len(ladder) < needed:
                # the level being ADDED tops the storey whose height it takes
                storey = min(len(ladder) - 1, count - 1)
                rise_mm = heights_mm[storey]
                elevation = ladder[-1].Elevation + config.mm_to_ft(rise_mm)
                new_level = Level.Create(doc, elevation)
                if convention:
                    name = convention[created] if created < len(convention) else None
                else:
                    name = naming.level_name(
                        len(ladder) + 1, elevation * config.MM_PER_FT,
                        label=built[storey][1] if storey < len(built) else None)
                try:
                    if name:
                        new_level.Name = name
                except Exception:
                    pass          # a name clash keeps Revit's default name
                ladder.append(new_level)
                created += 1
            transaction.Commit()
            spacing = sorted(set(int(h) for h in heights_mm))
            _say("Multi-storey: created {0} level(s) at {1} mm".format(
                created, ", ".join(str(value) for value in spacing)))
        except Exception as level_error:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
            _say("Multi-storey: could not create levels ({0}) -- storeys will "
                 "share the chosen pair".format(str(level_error)[:120]))
            return [(selections.get("base_level_id"),
                     selections.get("top_level_id"))] * count
    return [(ladder[i].Id, ladder[i + 1].Id) for i in range(count)]


def _build_one_storey(doc, revit_result, texts, selections, schedule_source=None,
                      path=None, comparison=None, transform_method=None,
                      storey_label=None, collect=None, hatches=None):
    """Build ONE storey: columns, beams, slabs and stairs from its records.

    `collect` is the multi-storey accumulator: when it is a list this storey
    appends (label, payload) to it instead of writing its own JSON, so the run
    ends with ONE file holding a section per storey.
    """
    limits = selections.get("limits")
    standards = selections.get("standards")
    tolerances = selections.get("tolerances") or {}
    dxf_texts = texts

    _progress(1, _BUILD_STEPS, "build columns")
    sections = report.build_column_sections(revit_result.records, limits, standards,
                                            texts=None, tolerances=tolerances)

    # Route text labels by their (user-confirmed) layer.
    text_mapping = selections.get("text_mapping") or {}
    column_texts = [t for t in dxf_texts
                    if text_mapping.get(t.layer_key) == layers.CATEGORY_COLUMN_TEXT]
    grid_texts = [t for t in dxf_texts
                  if text_mapping.get(t.layer_key) == layers.CATEGORY_GRID_TEXT]
    # THIS storey's own schedule first: a keyed table ("(a) = 200x600") is per
    # sheet, and test9's floors disagree on what (a) means, so reading the whole
    # file would size a beam off the wrong floor's table. A shared schedule that
    # lives on ONE sheet still works -- the whole file is the fallback below.
    own_schedule_texts = [t for t in dxf_texts
                          if text_mapping.get(t.layer_key)
                          == layers.CATEGORY_COLUMN_SCHEDULE]
    schedule_texts = own_schedule_texts or [
        t for t in (schedule_source or dxf_texts)
        if text_mapping.get(t.layer_key) == layers.CATEGORY_COLUMN_SCHEDULE]
    beam_texts = [t for t in dxf_texts
                  if text_mapping.get(t.layer_key) == layers.CATEGORY_BEAM_TEXT]
    # Slab notes are found by CONTENT anywhere, so routing is OPTIONAL: map a
    # layer to "slab text" to narrow the search, otherwise every text is offered
    # exactly as before.
    slab_texts = [t for t in dxf_texts
                  if text_mapping.get(t.layer_key) == layers.CATEGORY_SLAB_TEXT]
    if not slab_texts:
        slab_texts = dxf_texts
    else:
        _say("slabs: reading notes from {0} routed label(s)".format(
            len(slab_texts)))
    # Foundation notes are NOT found by content the way slab notes are: a bare
    # "1200MM THK" is a raft on the foundation layer and a slab note anywhere
    # else, and only the routing says which. So no fall back to every text --
    # an unrouted drawing simply has no drawn foundations.
    foundation_texts = [t for t in dxf_texts
                        if text_mapping.get(t.layer_key)
                        == layers.CATEGORY_FOUNDATION_TEXT]

    # The schedule (mark -> size) sizes MARK-ONLY plan labels (columns AND beams). The
    # table is authoritative; any sized plan label supplements a mark the table omits.
    schedule = marks.parse_schedule(schedule_texts)
    # Plan labels are NOT a table: only adopt an INLINE size ("C9 400x600") from one,
    # never split-pair a markless size label with a far mark sharing its row (which
    # mis-sized C5 from a neighbour's 350x750 a bay away).
    for mark, size in marks.parse_schedule(column_texts, allow_split=False).items():
        schedule.setdefault(mark, size)
    if schedule:
        _say("columns: parsed {0} schedule size(s) from text".format(len(schedule)))

    # Beam DEPTH (the larger label dimension) cannot be read from a 2D plan outline, so a
    # beam is sized from its label -- an inline "B1 300x600" OR a mark-only "B1" via the
    # schedule. Pass beam labels + the schedule so each segment gets its width/depth + mark.
    _progress(2, _BUILD_STEPS, "build beams")
    beam_segments = report.build_beam_segments(revit_result.records,
                                               sections.get("circles"),
                                               limits, standards,
                                               texts=beam_texts, tolerances=tolerances,
                                               schedule=schedule)
    sized_beams = beam_segments["status_counts"].get("text_sized", 0)
    if sized_beams:
        _say("beams: sized {0} segment(s) from labels (width + depth)".format(sized_beams))

    # Grid-line axis positions (internal feet) -> snap text-corrected column
    # centres onto the grid (columns sit on grid intersections).
    grid_x, grid_y = _grid_axis_positions(revit_result.records)

    # Column-text labels (one per real column) resize clipped columns (G9) and
    # merge grid-crossing-split pieces (E9), snapped to the grid intersection.
    mark_radius_ft = config.mm_to_ft(tolerances.get("mark_radius_mm",
                                                    config.DEFAULTS["mark_radius_mm"]))
    grid_snap_ft = config.mm_to_ft(tolerances.get("grid_snap_mm",
                                                  config.DEFAULTS["grid_snap_mm"]))

    # A fused lift/stair core (loose wall lines blobbed + greedily decomposed) mis-cuts
    # its shared corners, so each wall is the right thickness but offset along its length.
    # Re-tile each such blob from its mark+size labels first, so text-correction then just
    # names the now-correctly-placed walls instead of resizing a mis-centred piece.
    retiled = report.recover_core_walls_from_labels(sections, column_texts, schedule)
    if retiled:
        _say("columns: re-tiled {0} fused core(s) from labels".format(retiled))
    fixed = report.correct_columns_with_text(sections, column_texts, mark_radius_ft,
                                             schedule=schedule,
                                             grid_x=grid_x, grid_y=grid_y,
                                             grid_snap_ft=grid_snap_ft)
    if fixed:
        _say("columns: text-corrected {0} (clipped/merged from size labels)".format(fixed))
    named_circles = report.apply_circle_marks(sections, column_texts, mark_radius_ft)
    if named_circles:
        _say("columns: named {0} circular column(s) from labels".format(named_circles))

    # Last resort: a small column cast against a bigger one can fragment so badly that
    # recovery folds it into the neighbour, orphaning its label. Recover it from its
    # schedule size + leftover geometry (never overlapping an already-placed column).
    recovered_labeled = report.recover_unplaced_labeled_columns(
        sections, column_texts, schedule, limits=limits)
    if recovered_labeled:
        _say("columns: recovered {0} absorbed labelled column(s) from "
              "schedule+geometry".format(recovered_labeled))

    # Blade / wall-columns beyond the size limits (dropped by detection) whose
    # outlines are drawn CLOSED on the column layer: place them at drawn size,
    # position and angle (test8's AC19..BC28 strips).
    recovered_outline = report.recover_outline_columns(
        sections, revit_result.records, column_texts)
    if recovered_outline:
        _say("columns: placed {0} blade/outline column(s) beyond the size "
             "limits".format(recovered_outline))

    # COMBINED columns -- a wall-column carrying several columns, exploded to
    # bare lines -- close into no ring at all, because the wall's own edge runs
    # through each column root. Walk the FACES of that line soup instead; a
    # rectangle is kept only where the plan's own size label agrees with it.
    recovered_faces = report.recover_face_columns(
        sections, revit_result.records, column_texts,
        mark_reach_mm=tolerances.get("face_label_reach_mm",
                                     config.DEFAULTS["face_label_reach_mm"]),
        size_tol_mm=tolerances.get("face_size_tol_mm",
                                   config.DEFAULTS["face_size_tol_mm"]))
    if recovered_faces:
        _say("columns: recovered {0} combined column(s) from the outline "
             "graph".format(recovered_faces))

    # Last: a column WHOLLY inside another is a length of that same member read
    # twice (test10's roof: the 12300 wall plus two 2700 pieces of it). Two
    # solids cannot share ground, so the contained one goes.
    nested = report.drop_nested_columns(sections)
    if nested:
        _say("columns: dropped {0} column(s) contained by a larger one".format(
            nested))

    # Close the junction gap where a beam end meets a ROUND or ROTATED column: run the beam
    # end to the column centre (columns are now final). Axis-aligned columns are untouched.
    snapped_ends = report.snap_beam_ends_to_columns(
        beam_segments, sections, sections.get("circles"))
    if snapped_ends:
        _say("beams: snapped {0} end(s) to round/rotated column centres".format(snapped_ends))

    # A messy beam outline that RETRACES its own edges decomposes into the same
    # centreline twice -> two beams z-fighting in Revit (test8's column strips).
    deduped_beams = report.dedupe_beam_segments(beam_segments)
    if deduped_beams:
        _say("beams: removed {0} duplicate segment(s)".format(deduped_beams))

    # A beam outline drawn straight ACROSS a column would bury a beam inside it: split
    # such beams at the column faces so they frame IN, not through (client request).
    # Obstacles include closed rectangular column-LAYER outlines the detector dropped
    # (blade columns beyond the size limits are still real columns). Slabs keep the
    # PRE-SPLIT centrelines -- the beam-graph slab source needs its bay loops to run
    # continuously over the columns (split never mutates kept dicts).
    slab_beam_segments = dict(beam_segments)
    slab_beam_segments["segments"] = list(beam_segments["segments"])
    # recover_outline_columns has PLACED every usable closed outline, so the placed
    # footprints cover everything -- passing the outline fits AS WELL doubled every
    # ring (two slightly-offset squares per column = 0.42.0's jagged diamond trims)
    # and doubled the slab graph cost.
    column_footprints = report.column_trim_footprints(sections)
    split_beams = report.split_beams_at_columns(
        beam_segments, sections, sections.get("circles"))
    if split_beams:
        _say("beams: split {0} beam(s) drawn across column footprints".format(split_beams))

    if storey_label is None:
        _say("### CAD to BIM {0}".format(cad2bim.__version__))
    for line in compare.format_console(comparison or {}):
        _say(line)
    for line in report.format_console(revit_result, selections["mapping"],
                                      sections, beam_segments):
        _say(line)

    outcomes = {}
    _progress(3, _BUILD_STEPS, "create grids")
    if selections["create_grids"]:
        outcomes["grids"] = _create_grids(doc, revit_result.records, grid_texts)
    _progress(4, _BUILD_STEPS, "create columns")
    if selections["create_columns"]:
        outcomes["columns"] = _create_columns(doc, sections, selections)
    _progress(5, _BUILD_STEPS, "create beams")
    if selections["create_beams"]:
        outcomes["beams"] = _create_beams(doc, beam_segments, selections)
    # SLABS: outlines from the slab-edge (A-FLOR) rings, falling back to the
    # PLACED beams + column footprints when the DWG has no slab layer;
    # thickness/mark from "S1 150 THK" / "150 THK." notes anywhere in the text.
    _progress(6, _BUILD_STEPS, "create slabs")
    if selections["create_slabs"]:
        outcomes["slabs"] = _create_slabs(doc, revit_result.records, slab_beam_segments,
                                          slab_texts, selections, schedule,
                                          column_rects=column_footprints)
    # STAIRS (option 1, parametric): a STAIRCASE / ST-n text marks the bay; a
    # generic dog-leg from the Staircase tab numbers is laid out inside it.
    _progress(7, _BUILD_STEPS, "create stairs")
    if selections.get("create_stairs"):
        outcomes["stairs"] = _create_stairs(doc, revit_result.records,
                                            slab_beam_segments, dxf_texts,
                                            selections,
                                            column_rects=column_footprints)
    # FOOTINGS: the outlines the drawing carries, else one pad per column. Both
    # go on the columns' BASE level, and in a multi-storey run only the lowest
    # storey builds them -- a building has one set of foundations, not one per
    # floor.
    _progress(8, _BUILD_STEPS, "create footings")
    if selections.get("create_footings") and selections.get("build_footings", True):
        outcomes["footings"] = _create_footings(doc, sections, selections,
                                                records=revit_result.records,
                                                texts=foundation_texts,
                                                regions=hatches)
    _progress(_BUILD_STEPS, _BUILD_STEPS, "materials")
    applied = _apply_materials(doc, outcomes, selections)
    if applied:
        outcomes["materials"] = applied
    if selections["export"]:
        exported = _strip_ids(outcomes)
        if collect is not None:
            collect.append((storey_label or "storey",
                            report.build_export_payload(
                                revit_result, selections["mapping"], sections,
                                beam_segments, exported, texts=dxf_texts,
                                comparison=comparison)))
        else:
            _export(revit_result, selections["mapping"], sections, beam_segments,
                    exported, dxf_texts, comparison,
                    default_name=_export_name(path, selections,
                                              storey_label=storey_label))
    return _strip_ids(outcomes)


























def _export_name(cad_path, selections, storey_label=None):
    """Default export file name (user convention):
    [version]_[main element]_[testN from the CAD name]_[textmode].json
    e.g. "0.44.0_slab_test1_with_textmode.json"."""
    element = ("footing" if selections.get("create_footings")
               else "stair" if selections.get("create_stairs")
               else "slab" if selections.get("create_slabs")
               else "beam" if selections.get("create_beams")
               else "column" if selections.get("create_columns")
               else "grid")
    stem = os.path.splitext(os.path.basename(cad_path or ""))[0]
    m = re.search(r"(test|project)\s*-?_?(\d+)", stem, re.IGNORECASE)
    plan = "{0}{1}".format(m.group(1).lower(), m.group(2)) if m else (stem or "plan")
    text_mapping = selections.get("text_mapping") or {}
    routed = any(cat and cat != layers.CATEGORY_TEXT_IGNORE
                 for cat in text_mapping.values())
    mode = "with_textmode" if routed else "no_text"
    if storey_label:
        plan = "{0}-{1}".format(plan, re.sub(r"[^a-z0-9]+", "",
                                             storey_label.lower())[:12])
    return "{0}_{1}_{2}_{3}.json".format(cad2bim.__version__, element, plan, mode)


def _export_storeys(storey_payloads, source_name, default_name):
    """Write ONE JSON for a multi-storey run -- a section per storey."""
    target = _save_json(default_name)
    if not target:
        return
    try:
        report.export_storeys_json(target, storey_payloads,
                                   source_name=source_name)
        _say("Exported JSON ({0} storeys in one file) -> {1}".format(
            len(storey_payloads), target))
    except (IOError, OSError) as write_error:
        _error("JSON export failed", "Could not write the JSON file.",
               str(write_error))


def _export(read_result, mapping, sections, beam_segments, outcomes, texts, comparison,
            default_name="cad_to_bim_read.json"):
    """Write the intermediate JSON (the user opted in via the window)."""
    target = _save_json(default_name)
    if not target:
        return
    try:
        report.export_json(target, read_result, mapping, sections, beam_segments,
                           outcomes, texts=texts, comparison=comparison)
        _say("Exported JSON (with report) -> {0}".format(target))
    except (IOError, OSError) as write_error:
        _error("JSON export failed", "Could not write the JSON file.", str(write_error))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _error("Unexpected error",
               "An unexpected error occurred. The CPython3 engine is still running "
               "-- you do not need to restart Revit.", traceback.format_exc())
        _OUT.finish()
    finally:
        # the bar must come down whatever happened, or it sits over Revit
        _close_progress()

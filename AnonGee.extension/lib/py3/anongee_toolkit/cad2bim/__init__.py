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

__version__ = "0.23.0"  # recover a labelled column the geometry ABSORBED into a neighbour.
#                         A small column cast hard against a bigger one (C16/C17, 300x600,
#                         beside a 600x900) fragments so badly that recovery folds its pieces
#                         into the neighbour and drops the rest, orphaning its label. A new
#                         last-resort pass replaces it from its SCHEDULE size + the leftover
#                         fragments not already inside a placed column, grid-snapped beside
#                         the neighbour. Heavily gated -- needs a placed neighbour, hard
#                         geometry evidence, in-range size, and zero overlap -- so a stray
#                         label can never fabricate a column (verified: feeding all 43 Test18
#                         labels recovers only C16 and C17). EXPERIMENTAL: validate in Revit;
#                         revert with the cad2bim-v0.22.0-known-good checkpoint if needed.


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
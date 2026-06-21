# -*- coding: utf-8 -*-
"""cad2bim -- shared library for the CAD-to-BIM toolset.

This package holds the reusable, button-agnostic logic so each pushbutton
stays thin. It is intentionally split by single responsibility:

    unit_convert.py     mm <-> Revit internal feet (the ONLY place units convert)
    compat.py           Revit 2024/2025 + IronPython version-robustness helpers
    model.py            plain data holders (CurveRecord, TextRecord, results)
    cad_links.py        find/describe linked-DWG ImportInstances
    dxf_linker.py       link a picked DXF programmatically (Link CAD dialog)
    geometry_reader.py  extract curves from a linked CAD (project coords)
    dxf_reader.py       ezdxf: geometry + text from a DXF (CPython3, binary+ascii)
    transform.py        map DXF coords -> internal feet (+ bbox validation)
    compare.py          diff Revit-link vs DXF geometry (problem geometry)
    marks.py            parse "C1 400x400" text and match it to members
    layers.py           layer -> element-category classification (convention)
    report.py           human summary + JSON export (feeds future ezdxf validator)

This package runs on the pyRevit CPython3 engine (ezdxf needs CPython >=3.10) and
imports NO pyRevit IronPython modules (pyrevit.forms / pyrevit.revit), per the
AnonGee Brand Guidelines 12.1 / 12.8.4 / 12.9. The pushbutton builds its windows
with XamlReader.Load and uses System.Windows dialogs directly. The pure-geometry
modules (shapes, transform, compare, marks) import no Revit assemblies, so they can
be statically inspected and unit-tested outside Revit.
"""

__version__ = "0.14.1"  # 0.14.0 column hardening + internal cleanup: renamed
#                         units.py -> unit_convert.py, transactions.py ->
#                         txn_failures.py (no name clash with toolkit modules);
#                         behaviour unchanged
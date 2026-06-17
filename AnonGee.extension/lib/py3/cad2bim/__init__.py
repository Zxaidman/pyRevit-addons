# -*- coding: utf-8 -*-
"""cad2bim -- shared library for the CAD-to-BIM toolset.

This package holds the reusable, button-agnostic logic so each pushbutton
stays thin. It is intentionally split by single responsibility:

    units.py            mm <-> Revit internal feet (the ONLY place units convert)
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
    ui.py               pyRevit forms dialogs (file/unit/placement pickers)
    report.py           human summary + JSON export (feeds future ezdxf validator)

This package now runs on the pyRevit CPython3 engine (ezdxf needs CPython >=3.10).
The pure-geometry/parsing modules (shapes, transform, compare, marks) import no
Revit assemblies, so they can be statically inspected and unit-tested outside Revit.
"""

__version__ = "0.13.0"  # DXF-pick entry + ezdxf hybrid extraction + text-driven sizing
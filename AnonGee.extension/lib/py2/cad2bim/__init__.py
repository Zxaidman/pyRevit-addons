# -*- coding: utf-8 -*-
"""cad2bim -- shared library for the CAD-to-BIM toolset.

This package holds the reusable, button-agnostic logic so each pushbutton
stays thin. It is intentionally split by single responsibility:

    units.py            mm <-> Revit internal feet (the ONLY place units convert)
    compat.py           Revit 2024/2025 + IronPython version-robustness helpers
    model.py            plain data holders (IronPython 2.7 safe; no dataclasses)
    cad_links.py        find/describe linked-DWG ImportInstances
    geometry_reader.py  extract curves from a linked CAD (project coords)
    layers.py           layer -> element-category classification (convention)
    ui.py               pyRevit forms dialogs (link picker, mapping override)
    report.py           human summary + JSON export (feeds future ezdxf validator)

Nothing here imports Revit assemblies at package-import time; the Revit-dependent
modules import Autodesk.Revit.DB only when they are themselves imported, so this
package can be statically inspected outside Revit.
"""

__version__ = "0.12.0"  # + sizing limits (min/max) + standard-size snapping in the window
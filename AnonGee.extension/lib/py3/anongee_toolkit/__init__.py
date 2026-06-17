# -*- coding: utf-8 -*-
"""
AnonGee Toolkit
~~~~~~~~~~~~~~~
A CPython3-focused toolkit for pyRevit extensions targeting Revit 2024/2025.

Package layout::

    anongee_toolkit/
    ├── revit/          Revit API abstraction (app, elements, parameters, …)
    ├── structural/     Structural domain helpers (rebars, …)
    ├── ui/             WPF dialogs, XAML loading, native message boxes
    ├── io/             External I/O integrations (Excel COM, …)
    ├── operations/     Bulk delete / rename dialog engines
    └── utils/          General-purpose utilities (COM arrays, TSV, numerics)

Typical import patterns::

    from anongee_toolkit.revit import get_current_doc, RevitTransaction
    from anongee_toolkit.ui import WpfDialogBase, load_xaml
    from anongee_toolkit.operations import GenericBulkDeleteDialog
"""

__version__ = "1.0.0"
__author__  = "AnonGee"

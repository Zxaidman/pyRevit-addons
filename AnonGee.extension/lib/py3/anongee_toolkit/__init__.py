# -*- coding: utf-8 -*-
"""
AnonGee Toolkit
~~~~~~~~~~~~~~~
A CPython3-focused toolkit for pyRevit extensions targeting Revit 2024/2025.

Public API — everything importable directly from ``anongee_toolkit``:

**Revit layer**
  :func:`get_app`, :func:`get_current_uidoc`, :func:`get_current_doc`
  :class:`RevitTransaction`, :class:`RevitTransactionGroup`
  :func:`get_parameter`, :func:`get_parameter_value`, :func:`set_parameter_value`
  :func:`get_selected_elements`, :func:`set_selection`
  :func:`get_family_name`, :func:`get_type_name`
  :func:`get_elements_by_categories`
  :func:`get_eligible_views`, :func:`get_view_label`
  :func:`get_solid_volume_m3`, :func:`bounding_boxes_overlap`
  :func:`m_to_mm`, :func:`mm_to_ft`, :func:`m_to_ft`, :func:`ft_to_mm`,
  :func:`clean_ft`, :func:`strip_unit`
  :func:`create_element_id`, :func:`get_element_id_value`

**Structural layer**
  :func:`get_rebars`

**UI layer**
  :class:`WpfDialogBase`, :class:`DebounceTimer`
  :func:`load_xaml`, :func:`fill_combo`, :func:`select_combo_containing`
  :func:`alert`, :func:`error`, :func:`info`, :func:`confirm`,
  :func:`pick_file`, :func:`save_file`

**I/O layer**
  :class:`ExcelComWriter`

**Operations layer**
  :class:`GenericBulkDeleteDialog`, :class:`GenericBulkRenameDialog`

**Utilities layer**
  :func:`create_com_array`, :func:`parse_tsv_row`, :func:`read_tsv`,
  :func:`extract_numeric`, :func:`extract_bracket_int`

Package layout::

    anongee_toolkit/
    ├── revit/          Revit API abstraction (app, elements, parameters, …)
    ├── structural/     Structural domain helpers (rebars, …)
    ├── ui/             WPF dialogs, XAML loading, native message boxes
    ├── io/             External I/O integrations (Excel COM, …)
    ├── operations/     Bulk delete / rename dialog engines
    └── utils/          General-purpose utilities (COM arrays, TSV, numerics)
"""

__version__ = "1.0.0"
__author__  = "AnonGee"

# ---------------------------------------------------------------------------
# Revit — application access
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.application import (
    get_app,
    get_current_uidoc,
    get_current_doc,
)

# ---------------------------------------------------------------------------
# Revit — transactions
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.transactions import (
    RevitTransaction,
    RevitTransactionGroup,
    SuppressWarningsPreprocessor,
)

# ---------------------------------------------------------------------------
# Revit — element parameters
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.parameters import (
    get_parameter,
    get_parameter_value,
    set_parameter_value,
)

# ---------------------------------------------------------------------------
# Revit — selection
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.selection import (
    get_selected_elements,
    set_selection,
)

# ---------------------------------------------------------------------------
# Revit — element identity
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.elements import (
    get_family_name,
    get_type_name,
)

# ---------------------------------------------------------------------------
# Revit — collection / filtering
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.filtering import get_elements_by_categories

# ---------------------------------------------------------------------------
# Revit — geometry
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.geometry import (
    get_solid_volume_m3,
    bounding_boxes_overlap,
)

# ---------------------------------------------------------------------------
# Revit — unit conversion
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.units import (
    CF_TO_M3,
    SF_TO_M2,
    FT_TO_MM,
    FT_TO_M,
    m_to_mm,
    mm_to_ft,
    m_to_ft,
    ft_to_mm,
    clean_ft,
    strip_unit,
)

# ---------------------------------------------------------------------------
# Revit — views
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.views import (
    get_eligible_views,
    get_view_label,
    ALLOWED_VIEW_TYPES,
)

# ---------------------------------------------------------------------------
# Revit — API version compatibility
# ---------------------------------------------------------------------------
from anongee_toolkit.revit.compatibility import (
    create_element_id,
    get_element_id_value,
)

# ---------------------------------------------------------------------------
# Structural domain
# ---------------------------------------------------------------------------
from anongee_toolkit.structural.rebars import get_rebars

# ---------------------------------------------------------------------------
# UI — WPF base classes and timer
# ---------------------------------------------------------------------------
from anongee_toolkit.ui.dialogs import WpfDialogBase, DebounceTimer

# ---------------------------------------------------------------------------
# UI — XAML and ComboBox helpers
# ---------------------------------------------------------------------------
from anongee_toolkit.ui.xaml import (
    load_xaml,
    fill_combo,
    select_combo_containing,
)

# ---------------------------------------------------------------------------
# UI — native message boxes and file dialogs
# ---------------------------------------------------------------------------
from anongee_toolkit.ui.forms import (
    alert,
    error,
    info,
    confirm,
    pick_file,
    save_file,
)

# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
from anongee_toolkit.io.excel import ExcelComWriter

# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------
from anongee_toolkit.operations.bulk_delete import GenericBulkDeleteDialog
from anongee_toolkit.operations.bulk_rename import GenericBulkRenameDialog

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
from anongee_toolkit.utils.helpers import (
    create_com_array,
    parse_tsv_row,
    read_tsv,
    extract_numeric,
    extract_bracket_int,
)

# ---------------------------------------------------------------------------
# Explicit public surface
# ---------------------------------------------------------------------------
__all__ = [
    # ── revit.application ──────────────────────────────────────────────────
    "get_app",
    "get_current_uidoc",
    "get_current_doc",
    # ── revit.transactions ─────────────────────────────────────────────────
    "RevitTransaction",
    "RevitTransactionGroup",
    "SuppressWarningsPreprocessor",
    # ── revit.parameters ───────────────────────────────────────────────────
    "get_parameter",
    "get_parameter_value",
    "set_parameter_value",
    # ── revit.selection ────────────────────────────────────────────────────
    "get_selected_elements",
    "set_selection",
    # ── revit.elements ─────────────────────────────────────────────────────
    "get_family_name",
    "get_type_name",
    # ── revit.filtering ────────────────────────────────────────────────────
    "get_elements_by_categories",
    # ── revit.geometry ─────────────────────────────────────────────────────
    "get_solid_volume_m3",
    "bounding_boxes_overlap",
    # ── revit.units ────────────────────────────────────────────────────────
    "CF_TO_M3",
    "SF_TO_M2",
    "FT_TO_MM",
    "FT_TO_M",
    "m_to_mm",
    "mm_to_ft",
    "m_to_ft",
    "ft_to_mm",
    "clean_ft",
    "strip_unit",
    # ── revit.views ────────────────────────────────────────────────────────
    "get_eligible_views",
    "get_view_label",
    "ALLOWED_VIEW_TYPES",
    # ── revit.compatibility ────────────────────────────────────────────────
    "create_element_id",
    "get_element_id_value",
    # ── structural.rebars ──────────────────────────────────────────────────
    "get_rebars",
    # ── ui.dialogs ─────────────────────────────────────────────────────────
    "WpfDialogBase",
    "DebounceTimer",
    # ── ui.xaml ────────────────────────────────────────────────────────────
    "load_xaml",
    "fill_combo",
    "select_combo_containing",
    # ── ui.forms ───────────────────────────────────────────────────────────
    "alert",
    "error",
    "info",
    "confirm",
    "pick_file",
    "save_file",
    # ── io.excel ───────────────────────────────────────────────────────────
    "ExcelComWriter",
    # ── operations ─────────────────────────────────────────────────────────
    "GenericBulkDeleteDialog",
    "GenericBulkRenameDialog",
    # ── utils.helpers ──────────────────────────────────────────────────────
    "create_com_array",
    "parse_tsv_row",
    "read_tsv",
    "extract_numeric",
    "extract_bracket_int",
    # ── package metadata ───────────────────────────────────────────────────
    "__version__",
    "__author__",
]

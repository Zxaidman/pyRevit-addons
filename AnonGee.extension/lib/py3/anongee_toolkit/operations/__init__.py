# -*- coding: utf-8 -*-
"""
anongee_toolkit.operations
~~~~~~~~~~~~~~~~~~~~~~~~~~
Bulk element operations — generic dialog engines for deleting and renaming
Revit fill patterns, line patterns, and line styles.
"""
from anongee_toolkit.operations.bulk_delete import GenericBulkDeleteDialog
from anongee_toolkit.operations.bulk_rename import GenericBulkRenameDialog

__all__ = ["GenericBulkDeleteDialog", "GenericBulkRenameDialog"]

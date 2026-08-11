# -*- coding: utf-8 -*-
"""
Context-manager wrappers for Revit transactions and transaction groups.

Usage::

    with RevitTransaction("My Operation") as txn:
        element.LookupParameter("Mark").Set("A1")

    with RevitTransactionGroup("Batch"):
        with RevitTransaction("Step 1"):
            ...
        with RevitTransaction("Step 2"):
            ...
"""
from Autodesk.Revit.DB import (
    Transaction,
    TransactionGroup,
    IFailuresPreprocessor,
    FailureProcessingResult,
    FailureSeverity,
)
import anongee_clr

from anongee_toolkit.revit.application import get_current_doc


def _build_suppress_warnings_preprocessor():
    """Emit the CLR type. Called ONCE per Revit session, by the registry.

    Python.NET emits a real CLR type from this class body and the AppDomain
    refuses a second type of the same name, so it must not run at import time:
    a button that re-imports its library on every run would crash on the second
    click. See anongee_clr.
    """

    class SuppressWarningsPreprocessor(IFailuresPreprocessor):
        """
        IFailuresPreprocessor that silently discards all warnings so they never
        surface as modal dialogs during batch operations.
        """

        def PreprocessFailures(self, failures_accessor):
            try:
                for failure in list(failures_accessor.GetFailureMessages()):
                    if failure.GetSeverity() == FailureSeverity.Warning:
                        failures_accessor.DeleteWarning(failure)
            except Exception:
                pass
            return FailureProcessingResult.Continue

    return SuppressWarningsPreprocessor


SuppressWarningsPreprocessor = anongee_clr.get_or_create(
    "SuppressWarningsPreprocessor", _build_suppress_warnings_preprocessor)


class RevitTransaction:
    """
    Context manager for a single Revit Transaction.

    Commits on clean exit; rolls back automatically if an exception is raised
    inside the ``with`` block, then re-raises the exception.

    Args:
        name (str): Transaction name shown in the Revit undo stack.
        doc (Document, optional): Target document; defaults to the active document.
        suppress_warnings (bool): When ``True``, attaches
            :class:`SuppressWarningsPreprocessor` to silence geometry warnings.
    """

    def __init__(self, name="AnonGee Transaction", doc=None, suppress_warnings=False):
        self._doc = doc or get_current_doc()
        self._name = name
        self._suppress_warnings = suppress_warnings
        self._txn = None

    def __enter__(self):
        self._txn = Transaction(self._doc, self._name)
        if self._suppress_warnings:
            opts = self._txn.GetFailureHandlingOptions()
            opts.SetFailuresPreprocessor(SuppressWarningsPreprocessor())
            opts.SetClearAfterRollback(True)
            self._txn.SetFailureHandlingOptions(opts)
        self._txn.Start()
        return self._txn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._txn is None:
            return False
        if exc_type is not None:
            if self._txn.HasStarted() and not self._txn.HasEnded():
                self._txn.RollBack()
            return False
        if self._txn.HasStarted() and not self._txn.HasEnded():
            status = self._txn.Commit()
            if status != Transaction.TransactionStatus.Committed:
                raise RuntimeError(
                    "Transaction '{}' failed to commit.".format(self._name)
                )
        return True


class RevitTransactionGroup:
    """
    Context manager for a Revit TransactionGroup.

    Assimilates all child transactions on clean exit; rolls back on exception.

    Args:
        name (str): Group name shown in the Revit undo stack.
        doc (Document, optional): Target document; defaults to the active document.
    """

    def __init__(self, name="AnonGee Transaction Group", doc=None):
        self._doc = doc or get_current_doc()
        self._name = name
        self._group = None

    def __enter__(self):
        self._group = TransactionGroup(self._doc, self._name)
        self._group.Start()
        return self._group

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._group is None:
            return False
        if exc_type is not None:
            if self._group.HasStarted() and not self._group.HasEnded():
                self._group.RollBack()
            return False
        if self._group.HasStarted() and not self._group.HasEnded():
            self._group.Assimilate()
        return True

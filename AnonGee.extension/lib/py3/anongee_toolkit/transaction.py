# -*- coding: utf-8 -*-
from Autodesk.Revit.DB import (
    Transaction, TransactionGroup, IFailuresPreprocessor, 
    FailureProcessingResult, BuiltInFailures, FailureSeverity
)
from anongee_toolkit.core import get_current_doc
import traceback

class SuppressWarningsPreprocessor(IFailuresPreprocessor):
    """
    A failure preprocessor that silently clears all warnings (like geometry join issues)
    so they don't interrupt the user during batch processing.
    """
    def PreprocessFailures(self, failures_accessor):
        try:
            for failure in list(failures_accessor.GetFailureMessages()):
                if failure.GetSeverity() == FailureSeverity.Warning:
                    failures_accessor.DeleteWarning(failure)
        except Exception:
            pass
        return FailureProcessingResult.Continue

class RevitTransaction:
    """
    Context manager for safe Revit Transactions.
    """
    def __init__(self, transaction_name="AnonGee Transaction", doc=None, suppress_warnings=False):
        self.doc = doc if doc else get_current_doc()
        self.transaction_name = transaction_name
        self.transaction = None
        self.suppress_warnings = suppress_warnings

    def __enter__(self):
        self.transaction = Transaction(self.doc, self.transaction_name)
        
        if self.suppress_warnings:
            options = self.transaction.GetFailureHandlingOptions()
            options.SetFailuresPreprocessor(SuppressWarningsPreprocessor())
            options.SetClearAfterRollback(True)
            self.transaction.SetFailureHandlingOptions(options)
            
        self.transaction.Start()
        return self.transaction

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.transaction is None:
            return False

        # If an exception occurred within the 'with' block, roll back
        if exc_type is not None:
            if self.transaction.HasStarted() and not self.transaction.HasEnded():
                self.transaction.RollBack()
            return False # Let the exception propagate

        # Happy path: Commit the transaction
        if self.transaction.HasStarted() and not self.transaction.HasEnded():
            status = self.transaction.Commit()
            if status != Transaction.TransactionStatus.Committed:
                raise RuntimeError("Failed to commit transaction: {}".format(self.transaction_name))
        return True

class RevitTransactionGroup:
    """Context manager for safe Revit Transaction Groups."""
    def __init__(self, group_name="AnonGee Transaction Group", doc=None):
        self.doc = doc if doc else get_current_doc()
        self.group_name = group_name
        self.group = None

    def __enter__(self):
        self.group = TransactionGroup(self.doc, self.group_name)
        self.group.Start()
        return self.group

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.group is None:
            return False

        if exc_type is not None:
            if self.group.HasStarted() and not self.group.HasEnded():
                self.group.RollBack()
            return False

        if self.group.HasStarted() and not self.group.HasEnded():
            self.group.Assimilate()
        return True
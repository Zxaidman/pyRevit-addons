# -*- coding: utf-8 -*-
"""Transaction failure handling for batch element creation.

Batch creation from imperfect CAD geometry routinely raises Revit *warnings*
(e.g. "grids are nearly coincident"). Left unhandled, each one pops a modal
dialog and stalls the run. This swallows warnings so the batch proceeds, while
leaving genuine *errors* to surface normally.
"""

from Autodesk.Revit.DB import (IFailuresPreprocessor, FailureProcessingResult,
                               FailureSeverity)


class WarningSwallower(IFailuresPreprocessor):
    """Deletes warning-severity failures during a transaction; errors untouched."""

    def PreprocessFailures(self, failures_accessor):
        for failure in failures_accessor.GetFailureMessages():
            if failure.GetSeverity() == FailureSeverity.Warning:
                failures_accessor.DeleteWarning(failure)
        return FailureProcessingResult.Continue


def attach_warning_swallower(transaction):
    """Attach the warning swallower to an already-created (not yet started) or
    started transaction's failure-handling options."""
    options = transaction.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(WarningSwallower())
    transaction.SetFailureHandlingOptions(options)

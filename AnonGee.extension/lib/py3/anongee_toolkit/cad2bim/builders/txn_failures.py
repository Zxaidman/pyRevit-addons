# -*- coding: utf-8 -*-
"""Transaction failure handling for batch element creation.

Batch creation from imperfect CAD geometry routinely raises Revit *warnings*
(e.g. "grids are nearly coincident"). Left unhandled, each one pops a modal
dialog and stalls the run. This swallows warnings so the batch proceeds, while
leaving genuine *errors* to surface normally.
"""

import anongee_clr

from Autodesk.Revit.DB import (IFailuresPreprocessor, FailureProcessingResult,
                               FailureSeverity)


def _build_warning_swallower():
    """Emit the CLR type. Called ONCE per Revit session, by the registry.

    The class body cannot live at module level: Python.NET emits a real CLR
    type from it, the AppDomain refuses a second type of the same name, and the
    buttons re-import this module on every run so the files on disk are what
    runs. See anongee_clr for the whole story.
    """

    class WarningSwallower(IFailuresPreprocessor):
        """Deletes warning-severity failures during a transaction; errors untouched.

        `__namespace__` is required by Python.NET 3 to build a real derived CLR
        type from a .NET interface -- without it, `WarningSwallower()` routes to
        the interface's one-arg cast and raises "interface takes exactly one
        argument".
        """

        __namespace__ = "CadToBim"

        def PreprocessFailures(self, failures_accessor):
            for failure in failures_accessor.GetFailureMessages():
                if failure.GetSeverity() == FailureSeverity.Warning:
                    failures_accessor.DeleteWarning(failure)
            return FailureProcessingResult.Continue

    return WarningSwallower


WarningSwallower = anongee_clr.get_or_create("WarningSwallower",
                                             _build_warning_swallower)


def attach_warning_swallower(transaction):
    """Attach the warning swallower to a started transaction's failure options.

    Degrades gracefully: if this engine cannot build the preprocessor, the batch
    still runs (Revit may surface warning dialogs) -- this never crashes the run.
    Returns True if the swallower was attached.
    """
    try:
        options = transaction.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(WarningSwallower())
        transaction.SetFailureHandlingOptions(options)
        return True
    except Exception:
        return False

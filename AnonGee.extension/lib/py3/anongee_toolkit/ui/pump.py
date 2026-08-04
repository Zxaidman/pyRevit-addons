# -*- coding: utf-8 -*-
"""pump - flush the WPF dispatcher so a window repaints mid-loop.

Split out because both the progress bar and the modal dialogs need it, and
because the priority choice has a real consequence (see ProgressBar._refresh).
"""

__version__ = "1.5.0"
__all__ = ["pump"]

try:
    import clr
    for _asm in ("PresentationFramework", "PresentationCore", "WindowsBase"):
        try:
            clr.AddReference(_asm)
        except Exception:
            pass
except ImportError:
    pass

from System import Action
from System.Windows.Threading import (Dispatcher, DispatcherFrame,
                                      DispatcherPriority,
                                      DispatcherOperationCallback)


# ---------------------------------------------------------------------------
# dispatcher pumping
# ---------------------------------------------------------------------------

_PUMP_STRATEGY = None


def _exit_frame(frame):
    frame.Continue = False
    return None


def pump(priority=None):
    """Flush the WPF dispatcher queue so the UI repaints mid-loop.

    Defaults to ``DispatcherPriority.Render``, which processes the layout and
    render passes but stops *before* the Input queue. That matters inside a
    Revit transaction: pumping Input priority lets keystrokes and clicks reach
    Revit while your transaction is open, which can trigger a reentrant API
    call. Render priority avoids that.
    """
    global _PUMP_STRATEGY
    if priority is None:
        priority = DispatcherPriority.Render

    if _PUMP_STRATEGY in (None, "frame"):
        try:
            frame = DispatcherFrame()
            Dispatcher.CurrentDispatcher.BeginInvoke(
                priority, DispatcherOperationCallback(_exit_frame), frame)
            Dispatcher.PushFrame(frame)
            _PUMP_STRATEGY = "frame"
            return
        except Exception:
            _PUMP_STRATEGY = "invoke"

    if _PUMP_STRATEGY == "invoke":
        try:
            Dispatcher.CurrentDispatcher.Invoke(Action(lambda: None), priority)
            return
        except Exception:
            _PUMP_STRATEGY = "none"

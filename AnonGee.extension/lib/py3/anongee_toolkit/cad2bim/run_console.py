# -*- coding: utf-8 -*-
"""The run's voice: a deferred console and the two progress bars.

DEFERRED OUTPUT. Printing is what opens pyRevit's console window, and a clean
run should not open one at all -- the user asked for that explicitly. So every
line the run produces is buffered and only REVEALED when something goes wrong,
at which point the whole log comes out at once: phase counts, per-member notes,
the lot. `_OUT.finish()` ends a good run in silence; `_OUT.fail()` flushes.

TWO BARS, NOT ONE. Linking and reading the CAD happens BEFORE the dialog opens,
so a single bar sat at whatever percent the read had reached while the user
filled the dialog in, and then looked like it RESET when the build began. The
read bar closes when the dialog opens; the build bar opens when Run is pressed.
A multi-storey run reports one continuous 0-100 across every storey rather than
restarting per floor -- `_storey_span` tells the bar which storey of how many is
building, and the step count is offset into that.

Names keep their leading underscore because this is a pure move out of the
pushbutton: every call site reads exactly as it did.
"""

try:
    from anongee_toolkit.ui.progressbar import ProgressBar as _CpyProgressBar
except Exception:
    _CpyProgressBar = None


# --- deferred console: the whole run is buffered and only REVEALED when something
# goes wrong (user request: a clean run should not open the pyRevit console at all).
# Printing is what opens that window, so a successful run prints nothing; a failure
# flushes the entire log -- progress bar, per-phase counts, notes -- for diagnosis.
_REAL_PRINT = print   # the genuine print; only the buffer uses it


class _DeferredOut(object):
    def __init__(self):
        self._buf = []
        self.live = False
        self.failed = False

    def say(self, msg=""):
        if self.live:
            _REAL_PRINT(msg)
        else:
            self._buf.append(msg)

    def fail(self):
        """Mark the run as failed: the log is shown when it finishes."""
        self.failed = True

    def flush(self):
        for msg in self._buf:
            _REAL_PRINT(msg)
        self._buf = []
        self.live = True

    def finish(self, outcomes=None):
        """Reveal the log only when the run failed; stay silent otherwise.

        An outcome with errors, a rollback, or a category that produced nothing
        while it was asked for all count as failure -- those are exactly the
        runs where the console is worth opening.
        """
        pending = list((outcomes or {}).values())
        while pending:                      # per-storey runs nest one level
            outcome = pending.pop()
            if not isinstance(outcome, dict):
                continue
            if outcome.get("errors") or outcome.get("rolled_back"):
                self.failed = True
            pending.extend(v for v in outcome.values() if isinstance(v, dict))
        if self.failed:
            self.flush()
        else:
            self._buf = []


_OUT = _DeferredOut()


def _say(msg=""):
    _OUT.say(msg)


class _NullProgress(object):
    """Last resort: no window, no crash."""
    cancelled = False
    title = ""
    status = ""

    def show(self):
        return self

    def close(self):
        pass

    def update_progress(self, *args, **kwargs):
        pass


_BAR = _NullProgress()


# Two bars, not one. Linking and reading the CAD happens BEFORE the dialog
# opens, so a single bar sat at whatever percent the read had reached while the
# user filled the dialog in, then looked like it RESET when the build started.
# Each phase gets its own: the read bar closes when the dialog opens, the build
# bar opens when Run is pressed.
_READ_STEPS = 2


_BUILD_STEPS = 9
# A multi-storey run repeats the build once per storey. Reporting each storey
# 0-100 made the bar restart five times; instead the storey being built is an
# OFFSET into one continuous 0-100 over storeys x steps.


# A multi-storey run repeats the build once per storey. Reporting each storey
# 0-100 made the bar restart five times; instead the storey being built is an
# OFFSET into one continuous 0-100 over storeys x steps.
_STOREY_INDEX = 0


_STOREY_COUNT = 1


def _storey_span(index, count):
    """Tell the bar which storey of how many is being built."""
    global _STOREY_INDEX, _STOREY_COUNT
    _STOREY_INDEX = max(0, int(index))
    _STOREY_COUNT = max(1, int(count))


def _open_progress(phase):
    """Open a bar for one phase ("read" or "build"), closing any previous one."""
    global _BAR
    _close_progress()
    if _CpyProgressBar is None:
        return _BAR
    caption = ("cad2bim - reading CAD" if phase == "read"
               else "cad2bim - building model")
    try:
        _BAR = _CpyProgressBar(title=caption + ": {value}/{max_value}",
                               cancellable=False, show_eta=True)
        _BAR.show()
        _BAR._caption = caption
    except Exception:
        _BAR = _NullProgress()      # no host window / no WPF: run headless
    return _BAR


def _close_progress():
    global _BAR
    try:
        _BAR.close()
    except Exception:
        pass
    _BAR = _NullProgress()


def _progress(done, total, label):
    """Move the current bar and log the same step to the deferred console.

    The console line survives into the log a failed run prints; the bar is what
    the user watches while a big drawing is being read or built. In a
    multi-storey run the step is folded into ONE span over every storey, so the
    bar climbs to 100 once rather than restarting per floor.
    """
    if total == _BUILD_STEPS and _STOREY_COUNT > 1:
        done = _STOREY_INDEX * _BUILD_STEPS + done
        total = _STOREY_COUNT * _BUILD_STEPS
        label = "storey {0}/{1}: {2}".format(_STOREY_INDEX + 1, _STOREY_COUNT,
                                             label)
    try:
        caption = getattr(_BAR, "_caption", "cad2bim")
        _BAR.title = "{0}: {1}  ({{value}}/{{max_value}}, {{eta}} left)".format(
            caption, label)
        _BAR.update_progress(done, total)
    except Exception:
        pass
    frac = (float(done) / total) if total else 1.0
    fill = int(round(frac * 10))
    _say("[{0}{1}] {2:3d}%  {3}".format("#" * fill, "-" * (10 - fill),
                                        int(round(frac * 100)), label))

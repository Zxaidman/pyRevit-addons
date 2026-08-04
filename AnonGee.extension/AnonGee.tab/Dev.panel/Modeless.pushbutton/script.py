#! python3
# -*- coding: utf-8 -*-
"""
AnonGee · Modeless Window — Reference Pattern
---------------------------------------------
Reference implementation of the modeless (non-blocking) window architecture
defined in the AnonGee design system (§12.8). While the window is open Revit
stays fully interactive; every Revit API read/write is marshalled onto
Revit's primary thread through a mandatory IExternalEventHandler bridge.

Architecture summary
  • window.Show()  -> runs WPF on a separate thread.
  • ModelessHandler (IExternalEventHandler) -> all Revit DB/UI work inside
    Execute(), queued via ExternalEvent.Raise() from the WPF thread.
  • WindowInteropHelper.Owner anchors the window to Revit's main handle.
  • The handler class + live window ref live in a dedicated session-state
    module kept in sys.modules. The CPython 3 persistent engine re-executes
    this script on every button press, so:
      - Python.NET 3 emits __namespace__ interface subclasses as real CLR
        types; re-running the class statement after the first press raises
        "Duplicate type name within an assembly". The class is therefore
        defined exactly once per Revit session (§12.9.2).
      - The window ref survives run() returning, so re-launch activates the
        existing window instead of stacking a new one.
  • No pyRevit modules are imported (§12.8.4) — Autodesk.* + System.* only.
"""

import os
import sys
import types
import clr

# ── Revit API ──────────────────────────────────────────────────────────────
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import FilteredElementCollector  # noqa: E402
from Autodesk.Revit.DB import BuiltInCategory            # noqa: E402
from Autodesk.Revit.DB import ElementId                  # noqa: E402  (typed List member)
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent  # noqa: E402
from Autodesk.Revit.UI import TaskDialog                 # noqa: E402

# ── .NET / WPF ─────────────────────────────────────────────────────────────
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')
clr.AddReference('System')
clr.AddReference('System.Xaml')

from System.Windows.Markup import XamlReader            # noqa: E402
from System.IO import FileStream, FileMode, FileAccess   # noqa: E402
from System.Windows.Interop import WindowInteropHelper   # noqa: E402
from System.Windows.Media import Color, SolidColorBrush  # noqa: E402
from System.Collections.Generic import List              # noqa: E402

# ── Brand brushes (runtime status colors — theme brushes stay in XAML) ─────
def _make_brush(r, g, b):
    brush = SolidColorBrush(Color.FromRgb(r, g, b))
    brush.Freeze()
    return brush

BRUSH_TEXT    = _make_brush(0x14, 0x14, 0x14)   # Charcoal Black — default text
BRUSH_MUTED   = _make_brush(0x6B, 0x72, 0x80)   # Mid Grey — neutral status
BRUSH_SUCCESS = _make_brush(0x16, 0xA3, 0x4A)   # Success Green — completed reads
BRUSH_ERROR   = _make_brush(0xDC, 0x26, 0x26)   # Error Red — failures


def _fmt(n):
    """Thousands-separated integer, mono-status friendly."""
    return "{:,}".format(int(n or 0))


# ── Persistent session state ───────────────────────────────────────────────
# pyRevit's persistent CPython 3 engine re-executes this script module on
# every button press, but the interpreter, sys.modules and the CLR AppDomain
# outlive any single execution. Two consequences are handled here:
#
#   1. Python.NET 3 emits a __namespace__ interface subclass (below) as a
#      real CLR type in a dynamic assembly. Re-running the class statement
#      on a later press tries to re-emit the same type name and raises
#      "Duplicate type name within an assembly". The class is therefore
#      defined exactly once per Revit session and cached here.
#
#   2. The live window would otherwise be GC'd / forgotten when run()
#      returns and the ephemeral script namespace is dropped. Holding the
#      reference here lets a re-launch activate the existing window instead
#      of stacking a second one (§12.9.2).
_STATE_MODULE = "AnonGee_ModelessState"
_state = sys.modules.get(_STATE_MODULE)
if _state is None:
    _state = types.ModuleType(_STATE_MODULE)
    _state.handler_cls = None
    _state.window_ref = None
    sys.modules[_STATE_MODULE] = _state


if _state.handler_cls is None:
    # Defined only on the FIRST execution of this script per Revit session.
    # See the session-state comment above for why this guard is mandatory.
    class ModelessHandler(IExternalEventHandler):
        """
        Runs on Revit's primary thread. The WPF thread writes `data`, Raise()
        queues Execute(), and results are marshalled back to the WPF thread via
        the window's Dispatcher.
        """

        # __namespace__ is required by Python.NET 3 to build a real derived CLR
        # type from a .NET interface -- without it, ModelessHandler() routes to
        # the interface's one-arg cast and raises
        # "TypeError: interface takes exactly one argument" (see
        # anongee_toolkit/cad2bim/builders/txn_failures.py, WarningSwallower).
        __namespace__ = "AnonGee"

        # NOTE — deliberately no __init__ here.
        # Defining __init__ on a Python class that inherits a Revit interface
        # trips pythonnet's interface __new__ in the CPython 3 engine and raises
        # "TypeError: interface takes exactly one argument" at instantiation.
        # Per-instance state is reset explicitly in run() right after
        # construction (handler.data = {}) — same behaviour, no interface trap.
        data = {}    # per-instance state dict (rebound in run())
        app = None   # ModelessApp — set after it is created

        # ── IExternalEventHandler contract ────────────────────────────
        def Execute(self, app):
            req = self.data.get("request")
            uidoc = app.ActiveUIDocument

            if req == "query_doc" or req == "refresh_doc":
                self._query_doc(req, uidoc)
            elif req == "select_walls":
                self._select_walls(uidoc)

            self.data["request"] = None

        def GetName(self):
            return "AnonGee_ModelessHandler"

        # ── Revit-thread work ─────────────────────────────────────────
        def _query_doc(self, req, uidoc):
            result = {"request": req}
            if uidoc is None:
                result["error"] = "Open a Revit model to query."
            else:
                doc = uidoc.Document
                result["title"] = doc.Title
                result["total"] = FilteredElementCollector(doc).GetElementCount()
                view = doc.ActiveView
                if view is not None:
                    result["view"] = view.Name
                    result["walls_in_view"] = FilteredElementCollector(doc, view.Id) \
                        .OfCategory(BuiltInCategory.OST_Walls) \
                        .WhereElementIsNotElementType().GetElementCount()
            self.data["result"] = result
            self._marshal_to_ui()

        def _select_walls(self, uidoc):
            result = {"request": "select_walls"}
            if uidoc is None:
                result["error"] = "No active document opened."
            else:
                doc = uidoc.Document
                view = doc.ActiveView
                if view is None:
                    result["error"] = "No active view to select walls in."
                else:
                    walls = FilteredElementCollector(doc, view.Id) \
                        .OfCategory(BuiltInCategory.OST_Walls) \
                        .WhereElementIsNotElementType().ToElements()
                    ids = List[ElementId]()          # List[T] via .Add() — §12.9.4
                    for w in walls:
                        ids.Add(w.Id)
                    uidoc.Selection.SetElementIds(ids)
                    result["selected"] = ids.Count
                    result["view"] = view.Name
            self.data["result"] = result
            self._marshal_to_ui()

        # ── WPF-thread marshal ────────────────────────────────────────
        def _marshal_to_ui(self):
            """Queue the UI-update callback onto the window's WPF dispatcher."""
            try:
                from System import Action
                from System.Windows.Threading import DispatcherPriority
                self.app.window.Dispatcher.BeginInvoke(
                    DispatcherPriority.Normal, Action(self.app._on_handler_done))
            except Exception:
                pass

    _state.handler_cls = ModelessHandler
else:
    # Later press: the Python.NET 3 CLR type is already emitted and cached —
    # reuse it instead of re-running the class statement (which would raise
    # "Duplicate type name within an assembly").
    ModelessHandler = _state.handler_cls


class ModelessApp(object):
    """The modeless window. Fresh instance per launch — subscriptions are
    never made at module scope (§12.9.2 handler accumulation)."""

    def __init__(self, xaml_path, handler, ext_event):
        self.handler = handler
        self.ext_event = ext_event

        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        self.window = XamlReader.Load(stream)
        stream.Close()

        self.DocNameText    = self.window.FindName("DocNameText")
        self.CountText      = self.window.FindName("CountText")
        self.CountBadge     = self.window.FindName("CountBadge")
        self.StatusBar      = self.window.FindName("StatusBar")
        self.QueryBtn       = self.window.FindName("QueryBtn")
        self.SelectWallsBtn = self.window.FindName("SelectWallsBtn")
        self.RefreshDocBtn  = self.window.FindName("RefreshDocBtn")
        self.CloseBtn       = self.window.FindName("CloseBtn")

        self.wire_events()

    # ── UI wiring ─────────────────────────────────────────────────────
    def wire_events(self):
        self.QueryBtn.Click       += self._on_query
        self.SelectWallsBtn.Click += self._on_select_walls
        self.RefreshDocBtn.Click  += self._on_refresh
        self.CloseBtn.Click       += self._on_close
        self.window.Closed        += self._on_closed

    # ── WPF thread: request -> raise external event ───────────────────
    def _on_query(self, sender, args):
        self.handler.data["request"] = "query_doc"
        self.set_status("Querying model on the Revit thread…")
        self._raise_event()

    def _on_select_walls(self, sender, args):
        self.handler.data["request"] = "select_walls"
        self.set_status("Selecting walls in the active view…")
        self._raise_event()

    def _on_refresh(self, sender, args):
        self.handler.data["request"] = "refresh_doc"
        self.set_status("Re-reading document…")
        self._raise_event()

    def _raise_event(self):
        if self.ext_event is None:
            self.set_status("ExternalEvent unavailable — not launched by pyRevit.", True)
            return
        try:
            self.ext_event.Raise()
        except Exception as e:
            self.set_status("Could not raise event: {}".format(e), True)

    # ── WPF thread: results back from the Revit thread ────────────────
    def _on_handler_done(self):
        result = self.handler.data.get("result") or {}
        self.handler.data["result"] = None

        if "error" in result:
            self.set_status(result["error"], True)
            return

        req = result.get("request")
        if req in ("query_doc", "refresh_doc"):
            title = result.get("title", "—")
            total = _fmt(result.get("total"))
            walls = _fmt(result.get("walls_in_view"))
            view_name = result.get("view", "Active View")
            self.DocNameText.Text = title
            self.CountText.Text = total
            if req == "refresh_doc":
                self.set_status("Document re-read — {} elements total.".format(total))
            else:
                self.set_status("Queried — {} elements total · {} walls in '{}'.".format(
                    total, walls, view_name))
        elif req == "select_walls":
            n = result.get("selected", 0)
            self.set_status("Selected {} wall{} in '{}'.".format(
                n, "" if n == 1 else "s", result.get("view", "Active View")))

    # ── Status helpers ────────────────────────────────────────────────
    def set_status(self, message, is_error=False):
        self.StatusBar.Text = message
        self.StatusBar.Foreground = BRUSH_ERROR if is_error else BRUSH_SUCCESS

    def _on_close(self, sender, args):
        self.set_status("Closing…")
        self.window.Close()

    def _on_closed(self, sender, args):
        if _state.window_ref is self:
            _state.window_ref = None

    # ── Show modeless + anchor to Revit ───────────────────────────────
    def show(self):
        self.window.Show()
        # Anchor AFTER Show() so the window stays above Revit without blocking
        helper = WindowInteropHelper(self.window)
        helper.Owner = __revit__.MainWindowHandle


def run():
    # Re-opening while an instance is alive: activate instead of stacking.
    ref = _state.window_ref
    if ref is not None:
        try:
            if ref.window.IsVisible:
                ref.window.Activate()
                return
        except Exception:
            _state.window_ref = None

    script_dir = os.path.dirname(__file__)
    xaml_path = os.path.join(script_dir, "ui.xaml")

    handler = ModelessHandler()
    handler.data = {}          # per-instance state (no __init__ — see class note)
    ext_event = ExternalEvent.Create(handler)
    app = ModelessApp(xaml_path, handler, ext_event)
    handler.app = app
    _state.window_ref = app    # survives run() → re-launch activates it
    app.show()


def main():
    run()


if __name__ == "__main__":
    # Module-level guard: report a logic error cleanly instead of leaving the
    # persistent engine in a half-state (§12.9.4).
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            TaskDialog.Show(
                "AnonGee · Modeless Window",
                "Failed to launch: {}".format(e))
        except Exception:
            pass
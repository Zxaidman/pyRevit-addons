#! python3
# -*- coding: utf-8 -*-
"""
AnonGee · RC Automation — read-only build
-----------------------------------------
Reads an Excel schedule, validates it, and probes the open model for what the
schedule would need from it. **It opens no transaction and writes nothing.**

That is the point of this build. Every hard part of the feature is downstream of
questions this answers: does the CPython 3 engine import the toolkit, does the
vendored openpyxl actually load inside Revit, does the modeless bridge hold up,
are the levels and bar types the workbook names present, and can the elements it
matches host reinforcement at all. Finding any of that out during a four-hundred
element write is the expensive way.

Architecture is the reference pattern (§12.8):
  • window.Show() runs WPF on its own thread; the Revit API is reached only
    through an IExternalEventHandler.
  • A serialized FIFO queue means one Revit-thread request at a time, in order
    (§12.8.7.3) rather than a single slot that drops presses.
  • Only ints and strings cross the bridge; the id -> Element map stays on the
    handler, on Revit's thread (§12.8.7.2).
  • The handler class and the live window are cached on a session-state module
    in sys.modules, because the persistent engine re-runs this file on every
    press and re-emitting a __namespace__ CLR type raises "Duplicate type name
    within an assembly" (§12.9.2).
  • No pyRevit imports, no `re` — the engine ships neither (§12.8.4, §12.9.3).
"""

import os
import sys
import types

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import BuiltInCategory                 # noqa: E402
from Autodesk.Revit.DB import BuiltInParameter                # noqa: E402
from Autodesk.Revit.DB import FilteredElementCollector        # noqa: E402
from Autodesk.Revit.DB import Level                           # noqa: E402
from Autodesk.Revit.DB.Structure import RebarHostData         # noqa: E402
from Autodesk.Revit.UI import ExternalEvent                   # noqa: E402
from Autodesk.Revit.UI import IExternalEventHandler           # noqa: E402
from Autodesk.Revit.UI import TaskDialog                      # noqa: E402

clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System")
clr.AddReference("System.Xaml")

from System import Action                                     # noqa: E402
from System.Collections import ArrayList                       # noqa: E402
from System.IO import FileAccess, FileMode, FileStream        # noqa: E402
from System.Windows import MessageBox                          # noqa: E402
from System.Windows.Interop import WindowInteropHelper        # noqa: E402
from System.Windows.Markup import XamlReader                  # noqa: E402
from System.Windows.Media import Color, SolidColorBrush       # noqa: E402
from System.Windows.Threading import DispatcherPriority       # noqa: E402

__version__ = "0.1.0"

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Toolkit import
# ---------------------------------------------------------------------------

def _bootstrap_lib_path():
    """Put the engine's lib subfolder on sys.path.

    Primary: the extension's own path_resolver, which pyRevit makes importable
    by adding `lib/` to sys.path. Fallback: climb to find `lib/py3` directly, so
    the tool still loads if the button is run from an unusual working directory.
    """
    try:
        import path_resolver
        path_resolver.update_paths()
        return
    except ImportError:
        pass

    sub = "py3" if sys.version_info[0] == 3 else "py2"
    cursor = LOCAL_DIR
    for _ in range(8):
        candidate = os.path.join(cursor, "lib", sub)
        if os.path.isdir(candidate):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return
        cursor = parent


_bootstrap_lib_path()

from anongee_toolkit.rc_automation import excel_engine         # noqa: E402
from anongee_toolkit.rc_automation import models               # noqa: E402
from anongee_toolkit.rc_automation import rebar_spec           # noqa: E402
from anongee_toolkit.rc_automation import validation           # noqa: E402


# ---------------------------------------------------------------------------
# Brand brushes for runtime status (theme brushes stay in the XAML)
# ---------------------------------------------------------------------------

def _brush(r, g, b):
    brush = SolidColorBrush(Color.FromRgb(r, g, b))
    brush.Freeze()
    return brush


BRUSH_MUTED = _brush(0x6B, 0x72, 0x80)
BRUSH_SUCCESS = _brush(0x16, 0xA3, 0x4A)
BRUSH_ERROR = _brush(0xDC, 0x26, 0x26)


class FindingRow(object):
    """A grid row.

    Plain ``__slots__``, no INotifyPropertyChanged: DataTemplate bindings to
    Python properties on an INPC class fail silently under Python.NET 3 and
    render blank cells (§12.7.G). Slot names match the XAML binding paths
    exactly, which ``tests/test_rc_automation_ui.py`` asserts.
    """

    __slots__ = ["Severity", "Sheet", "RowNumber", "Column", "Message"]

    def __init__(self, severity, sheet, row_number, column, message):
        self.Severity = severity
        self.Sheet = sheet or ""
        self.RowNumber = "" if row_number is None else str(row_number)
        self.Column = column or ""
        self.Message = message


# ---------------------------------------------------------------------------
# Session state — see the module docstring for why this is mandatory
# ---------------------------------------------------------------------------
_STATE_MODULE = "AnonGee_RCAutomationState"
_state = sys.modules.get(_STATE_MODULE)
if _state is None:
    _state = types.ModuleType(_STATE_MODULE)
    _state.handler_cls = None
    _state.window_ref = None
    sys.modules[_STATE_MODULE] = _state


if _state.handler_cls is None:
    class RCAutomationHandler(IExternalEventHandler):
        """Runs on Revit's primary thread. Reads only — never writes.

        There is no Transaction anywhere in this class and there is not meant to
        be one: this build exists to prove the reads are right before anything
        is written.
        """

        # Required by Python.NET 3 to emit a real derived CLR type from a .NET
        # interface. Without it, construction routes to the interface's one-arg
        # cast and raises "interface takes exactly one argument".
        __namespace__ = "AnonGee"

        # No __init__ on purpose — defining one on a class inheriting a Revit
        # interface trips pythonnet's interface __new__ in the CPython 3 engine.
        # Per-instance state is set in run() straight after construction.
        data = {}
        app = None

        # -- IExternalEventHandler ---------------------------------------
        def Execute(self, uiapp):
            request = self.data.get("request")
            try:
                if request == "probe":
                    self.data["result"] = self._probe(uiapp)
                else:
                    self.data["result"] = {"error": "Unknown request."}
            except Exception as probe_error:
                self.data["result"] = {"error": str(probe_error)}
            self.data["request"] = None
            self._marshal_to_ui()

        def GetName(self):
            return "AnonGee_RCAutomationHandler"

        # -- Revit-thread reads -------------------------------------------
        def _probe(self, uiapp):
            """What the model has that the workbook is going to want."""
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                return {"error": "Open a Revit model first."}
            doc = uidoc.Document

            result = {"title": doc.Title}
            result["levels"] = sorted(
                _name_of(level)
                for level in FilteredElementCollector(doc)
                .OfClass(Level).ToElements())

            bar_types = []
            for element in (FilteredElementCollector(doc)
                            .OfCategory(BuiltInCategory.OST_Rebar)
                            .WhereElementIsElementType().ToElements()):
                if element.GetType().Name == "RebarBarType":
                    bar_types.append(_name_of(element))
            result["bar_types"] = sorted(bar_types)

            result["footings"], result["footing_hosts"] = self._hosts(
                doc, BuiltInCategory.OST_StructuralFoundation)
            result["columns"], result["column_hosts"] = self._hosts(
                doc, BuiltInCategory.OST_StructuralColumns)
            result["marks"] = self._marks(
                doc, BuiltInCategory.OST_StructuralFoundation)
            return result

        def _hosts(self, doc, category):
            """``(count, valid_host_count)`` for one category.

            A floor is only a legal rebar host once it is flagged structural, so
            the count that matters is not how many footings exist but how many
            of them Revit will actually let a bar into.
            """
            total = 0
            valid = 0
            for element in (FilteredElementCollector(doc).OfCategory(category)
                            .WhereElementIsNotElementType().ToElements()):
                total += 1
                try:
                    host_data = RebarHostData.GetRebarHostData(element)
                    if host_data is not None and host_data.IsValidHost():
                        valid += 1
                except Exception:
                    pass
            return total, valid

        def _marks(self, doc, category):
            marks = []
            for element in (FilteredElementCollector(doc).OfCategory(category)
                            .WhereElementIsNotElementType().ToElements()):
                parameter = element.get_Parameter(
                    BuiltInParameter.ALL_MODEL_MARK)
                if parameter is not None and parameter.HasValue:
                    value = parameter.AsString()
                    if value:
                        marks.append(value)
            return sorted(set(marks))

        # -- back to the WPF thread ---------------------------------------
        def _marshal_to_ui(self):
            try:
                self.app.window.Dispatcher.BeginInvoke(
                    DispatcherPriority.Normal, Action(self.app.on_handler_done))
            except Exception:
                pass

    _state.handler_cls = RCAutomationHandler
else:
    # Later press: the CLR type is already emitted. Re-running the class
    # statement would raise "Duplicate type name within an assembly".
    RCAutomationHandler = _state.handler_cls


def _name_of(element):
    try:
        return element.Name
    except Exception:
        return "?"


class RCAutomationApp(object):
    """The window. A fresh instance per launch — never subscribe at module
    scope, or every press adds another handler to the same event (§12.9.2)."""

    def __init__(self, xaml_path, handler, ext_event):
        self.handler = handler
        self.ext_event = ext_event
        self.workbook = None
        self.issues = []
        self.probe = None
        self._queue = []
        self._busy = False

        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        self.window = XamlReader.Load(stream)
        stream.Close()

        self.WorkbookPathText = self.window.FindName("WorkbookPathText")
        self.BrowseBtn = self.window.FindName("BrowseBtn")
        self.ModeCombo = self.window.FindName("ModeCombo")
        self.LoadBtn = self.window.FindName("LoadBtn")
        self.ProbeBtn = self.window.FindName("ProbeBtn")
        self.ExportBtn = self.window.FindName("ExportBtn")
        self.ClearBtn = self.window.FindName("ClearBtn")
        self.CloseBtn = self.window.FindName("CloseBtn")
        self.FindingsGrid = self.window.FindName("FindingsGrid")
        self.ProbeText = self.window.FindName("ProbeText")
        self.StatusBar = self.window.FindName("StatusBar")
        self.ErrorCount = self.window.FindName("ErrorCount")
        self.WarningCount = self.window.FindName("WarningCount")
        self.InfoCount = self.window.FindName("InfoCount")
        self.VersionText = self.window.FindName("VersionText")

        self.VersionText.Text = "{0} · read-only".format(__version__)
        self._fill_modes()
        self._wire_events()

    # -- setup -----------------------------------------------------------
    def _fill_modes(self):
        for mode in models.MODES:
            self.ModeCombo.Items.Add(models.MODE_LABELS[mode])
        self.ModeCombo.SelectedIndex = 0

    def _wire_events(self):
        self.BrowseBtn.Click += self._on_browse
        self.LoadBtn.Click += self._on_load
        self.ProbeBtn.Click += self._on_probe
        self.ExportBtn.Click += self._on_export
        self.ClearBtn.Click += self._on_clear
        self.CloseBtn.Click += self._on_close
        self.window.Closed += self._on_closed

    def selected_mode(self):
        index = self.ModeCombo.SelectedIndex
        return models.MODES[index if 0 <= index < len(models.MODES) else 0]

    # -- WPF thread ------------------------------------------------------
    def _on_browse(self, sender, args):
        path = _pick_workbook()
        if path:
            self.WorkbookPathText.Text = path
            self.set_status("Selected {0}".format(os.path.basename(path)))

    def _on_load(self, sender, args):
        path = (self.WorkbookPathText.Text or "").strip()
        mode = self.selected_mode()
        self.set_status("Reading the workbook…")
        try:
            self.workbook, issues = excel_engine.load(path, mode=mode)
            if not models.has_errors(issues):
                issues = issues + validation.validate(self.workbook, mode=mode)
            self.issues = models.sort_issues(issues)
        except Exception as load_error:
            # A traceback in a modeless window is a support call. Anything the
            # engine throws becomes a row like every other finding.
            self.workbook = None
            self.issues = [models.Issue(
                models.SEVERITY_ERROR,
                "The workbook could not be read: {0}".format(load_error))]

        self._refresh_grid()
        self._describe_plan()

    def _on_probe(self, sender, args):
        self._enqueue("probe")
        self.set_status("Reading the model on Revit's thread…")

    def _on_export(self, sender, args):
        if not self.issues:
            self.set_status("Nothing to export yet — load a workbook first.",
                            True)
            return
        path = (self.WorkbookPathText.Text or "").strip()
        target = os.path.join(
            os.path.dirname(path) or LOCAL_DIR,
            "{0}_rc_report.txt".format(
                os.path.splitext(os.path.basename(path))[0] or "workbook"))
        try:
            with open(target, "w") as handle:
                handle.write(self._report_text())
            self.set_status("Report written to {0}".format(target))
        except Exception as write_error:
            self.set_status("Could not write the report: {0}".format(
                write_error), True)

    def _on_clear(self, sender, args):
        self.workbook = None
        self.issues = []
        self.probe = None
        self.FindingsGrid.ItemsSource = None
        self.ProbeText.Text = "Load a workbook, then Probe model."
        self._refresh_counts()
        self.set_status("Cleared.")

    def _on_close(self, sender, args):
        self.window.Close()

    def _on_closed(self, sender, args):
        if _state.window_ref is self:
            _state.window_ref = None

    # -- serialized request queue (§12.8.7.3) ----------------------------
    def _enqueue(self, request):
        self._queue.append(request)
        self._pump()

    def _pump(self):
        if self._busy or not self._queue:
            return
        if self.ext_event is None:
            self.set_status("No ExternalEvent — not launched by pyRevit.", True)
            self._queue = []
            return
        self._busy = True
        self.handler.data["request"] = self._queue.pop(0)
        try:
            self.ext_event.Raise()
        except Exception as raise_error:
            self._busy = False
            self.set_status("Could not reach Revit: {0}".format(raise_error),
                            True)

    def on_handler_done(self):
        """Marshalled back from the Revit thread by the handler."""
        self._busy = False
        result = self.handler.data.get("result") or {}
        self.handler.data["result"] = None

        if "error" in result:
            self.set_status(result["error"], True)
        else:
            self.probe = result
            self.ProbeText.Text = self._probe_text(result)
            self.set_status("Model read. Nothing was written.")
        self._pump()

    # -- rendering -------------------------------------------------------
    def _refresh_grid(self):
        rows = ArrayList()
        for issue in self.issues:
            rows.Add(FindingRow(issue.severity, issue.sheet, issue.row,
                                issue.column, issue.message))
        # Cleared first so WPF destroys the row containers instead of reusing
        # them against stale values (§12.7.G).
        self.FindingsGrid.ItemsSource = None
        self.FindingsGrid.ItemsSource = rows
        self._refresh_counts()

    def _refresh_counts(self):
        counts = models.count_by_severity(self.issues)
        self.ErrorCount.Text = "{0} errors".format(
            counts[models.SEVERITY_ERROR])
        self.WarningCount.Text = "{0} warnings".format(
            counts[models.SEVERITY_WARNING])
        self.InfoCount.Text = "{0} notes".format(counts[models.SEVERITY_INFO])

    def _describe_plan(self):
        """Say what the schedule would build, without building any of it."""
        if self.workbook is None or self.workbook.is_empty():
            self.set_status("Nothing was read from the workbook.", True)
            return

        bars = 0
        elements = 0
        varying = 0
        for footing in self.workbook.footing_types:
            rows = self.workbook.footing_rebar_for(footing.type_mark)
            for plan in rebar_spec.plan_footing(footing, rows):
                bars += plan.count
                elements += plan.element_count
                if plan.bars and not plan.uniform:
                    varying += 1

        summary = self.workbook.summary()
        note = (" {0} layer(s) vary in length and would be placed as individual "
                "bars.".format(varying) if varying else "")
        blocked = models.has_errors(self.issues)
        self.set_status(
            "{0} footing types, {1} column types. {2} footing bars would be "
            "placed as {3} element(s).{4}{5}".format(
                summary["footing_types"], summary["column_types"], bars,
                elements, note,
                "  Errors must be fixed before a run." if blocked else ""),
            blocked)

    def _probe_text(self, result):
        lines = ["Model: {0}".format(result.get("title", "?")), ""]
        lines.append("Levels ({0})".format(len(result.get("levels", []))))
        for name in result.get("levels", []):
            lines.append("  {0}{1}".format(name, self._level_flag(name)))
        lines.append("")
        lines.append("Rebar bar types ({0})".format(
            len(result.get("bar_types", []))))
        for name in result.get("bar_types", []) or ["  none loaded"]:
            lines.append("  {0}".format(name))
        lines.append("")
        footings, footing_hosts = result.get("footings", 0), result.get(
            "footing_hosts", 0)
        columns, column_hosts = result.get("columns", 0), result.get(
            "column_hosts", 0)
        lines.append("Structural foundations: {0} ({1} can host rebar)".format(
            footings, footing_hosts))
        if footings and footing_hosts < footings:
            lines.append("  {0} cannot — a floor has to be flagged structural"
                         .format(footings - footing_hosts))
        lines.append("Structural columns: {0} ({1} can host rebar)".format(
            columns, column_hosts))
        lines.append("")
        lines.append(self._mark_report(result.get("marks", [])))
        return "\n".join(lines)

    def _level_flag(self, name):
        """Mark the levels the workbook actually asks for."""
        if self.workbook is None:
            return ""
        wanted = set()
        for row in self.workbook.footing_placement:
            wanted.add(row.level)
        for row in self.workbook.column_placement:
            wanted.add(row.base_level)
            wanted.add(row.top_level)
        return "   <- named by the workbook" if name in wanted else ""

    def _mark_report(self, model_marks):
        """Which scheduled marks the model already has, and which it does not."""
        if self.workbook is None:
            return "Load a workbook to compare marks."
        scheduled = set(row.mark for row in self.workbook.footing_placement
                        if row.mark)
        if not scheduled:
            return "No footing placement marks in the workbook to compare."
        found = sorted(scheduled & set(model_marks))
        missing = sorted(scheduled - set(model_marks))
        lines = ["Footing marks: {0} of {1} scheduled marks are in the model"
                 .format(len(found), len(scheduled))]
        if missing:
            lines.append("  not in the model: {0}".format(
                ", ".join(missing[:12])))
            if len(missing) > 12:
                lines.append("  ... and {0} more".format(len(missing) - 12))
        return "\n".join(lines)

    def _report_text(self):
        lines = ["AnonGee RC Automation — read-only report",
                 "Workbook: {0}".format(
                     (self.WorkbookPathText.Text or "").strip()),
                 "Mode: {0}".format(models.MODE_LABELS[self.selected_mode()]),
                 ""]
        counts = models.count_by_severity(self.issues)
        lines.append("{0} errors, {1} warnings, {2} notes".format(
            counts[models.SEVERITY_ERROR], counts[models.SEVERITY_WARNING],
            counts[models.SEVERITY_INFO]))
        lines.append("")
        for issue in self.issues:
            lines.append("[{0}] {1}".format(issue.severity, issue))
        if self.probe:
            lines.append("")
            lines.append(self._probe_text(self.probe))
        lines.append("")
        lines.append("Nothing in the model was changed.")
        return "\n".join(lines)

    def set_status(self, message, is_error=False):
        self.StatusBar.Text = message
        self.StatusBar.Foreground = BRUSH_ERROR if is_error else BRUSH_SUCCESS

    # -- show ------------------------------------------------------------
    def show(self):
        self.window.Show()
        # Anchor AFTER Show(), or the window opens behind Revit (§12.8.3).
        helper = WindowInteropHelper(self.window)
        helper.Owner = __revit__.MainWindowHandle


def _pick_workbook():
    """Ask for a workbook with the .NET dialog — no pyRevit forms in CPython 3."""
    try:
        clr.AddReference("Microsoft.Win32.Primitives")
    except Exception:
        pass
    try:
        from Microsoft.Win32 import OpenFileDialog
        dialog = OpenFileDialog()
        dialog.Title = "AnonGee · RC Automation — select a schedule"
        dialog.Filter = "Excel workbook (*.xlsx;*.xlsm)|*.xlsx;*.xlsm"
        if dialog.ShowDialog():
            return dialog.FileName
    except Exception as dialog_error:
        MessageBox.Show("Could not open the file dialog: {0}".format(
            dialog_error), "AnonGee · RC Automation")
    return None


def run():
    ref = _state.window_ref
    if ref is not None:
        try:
            if ref.window.IsVisible:
                ref.window.Activate()
                return
        except Exception:
            _state.window_ref = None

    handler = RCAutomationHandler()
    handler.data = {}
    ext_event = ExternalEvent.Create(handler)
    app = RCAutomationApp(os.path.join(LOCAL_DIR, "ui.xaml"), handler,
                          ext_event)
    handler.app = app
    _state.window_ref = app
    app.show()


def main():
    run()


if __name__ == "__main__":
    # Report a logic error cleanly instead of leaving the persistent engine in
    # a half-state (§12.9.4).
    try:
        main()
    except Exception as launch_error:
        import traceback
        traceback.print_exc()
        try:
            TaskDialog.Show("AnonGee · RC Automation",
                            "Failed to launch: {0}".format(launch_error))
        except Exception:
            pass

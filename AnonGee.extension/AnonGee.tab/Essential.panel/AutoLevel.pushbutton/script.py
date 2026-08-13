#! python3
# -*- coding: utf-8 -*-
"""
AnonGee · Auto Level Manager — modeless, with smart text detection
------------------------------------------------------------------
One window for everything you do to levels: see the stack drawn to scale,
read the levels out of a drawing's own annotation, add or renumber them, and
commit the lot as a single undo step.

Why modeless (§12.8.1): the workflow is "open the section, scan it, look at
the model, fix a row, look again". Revit has to stay interactive, so the
window runs on the WPF thread and every Revit call is marshalled onto Revit's
primary thread through an IExternalEventHandler bridge (§12.8.2).

Architecture
  • window.Show()  -> WPF on its own thread; Revit stays live.
  • AutoLevelHandler (IExternalEventHandler) -> every DB read/write inside
    Execute(), fed by a serialized FIFO request queue (§12.8.7.3) so a burst
    of clicks can't swallow a request.
  • The handler class, the failure preprocessor and the live window reference
    live on a session-state module in sys.modules: the persistent CPython 3
    engine re-executes this file on every press, and re-running a
    `__namespace__` interface subclass raises "Duplicate type name within an
    assembly" on the second one (§12.8.7.1).
  • The tool's own package is purged from sys.modules on every run, so editing
    a module and pressing the button again runs the new code — the stale-cache
    trap cad2bim hit in v0.67.1.
  • No pyRevit modules (§12.8.4) — Autodesk.* and System.* only.

The thinking parts (parsing, naming, the plan) are Revit-free and covered by
tests/test_autolevel.py.
"""

__title__ = "Auto Level\nManager"
__author__ = "AnonGee"
__min_revit_ver__ = 2022

import os
import sys
import traceback
import types

import clr

# ── Revit API ──────────────────────────────────────────────────────────────
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (FailureProcessingResult,          # noqa: E402
                               IFailuresPreprocessor)
from Autodesk.Revit.UI import (ExternalEvent,                    # noqa: E402
                               IExternalEventHandler, TaskDialog)

# ── .NET / WPF ─────────────────────────────────────────────────────────────
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System")
clr.AddReference("System.Xaml")

from Microsoft.Win32 import OpenFileDialog                        # noqa: E402
from System import Action                                         # noqa: E402
from System.Collections import ArrayList                          # noqa: E402
from System.IO import FileAccess, FileMode, FileStream            # noqa: E402
from System.Windows import (MessageBox, MessageBoxButton,         # noqa: E402
                            MessageBoxImage, MessageBoxResult,
                            Thickness, Visibility)
from System.Windows.Controls import (Canvas, CheckBox,            # noqa: E402
                                     DataGridCellInfo,
                                     DataGridEditAction, TextBlock)
from System.Windows.Interop import WindowInteropHelper            # noqa: E402
from System.Windows.Markup import XamlReader                      # noqa: E402
from System.Windows.Media import (Color, FontFamily,              # noqa: E402
                                  SolidColorBrush)
from System.Windows.Shapes import Line, Rectangle                 # noqa: E402
from System.Windows.Threading import DispatcherPriority           # noqa: E402


# ── the tool's own package ─────────────────────────────────────────────────

def _bootstrap_package():
    """Make ``anongee_autolevel`` importable, and always from disk.

    The persistent engine keeps every module it has ever imported. Editing one
    and pressing the button again would otherwise run the previous session's
    code — the failure mode that cost cad2bim a release. Dropping the package
    from sys.modules each run costs one cheap re-import (these are small, pure
    Python files) and removes the whole class of bug.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    stale = [name for name in list(sys.modules)
             if name == "anongee_autolevel"
             or name.startswith("anongee_autolevel.")]
    for name in stale:
        del sys.modules[name]


def _bootstrap_lib_path():
    """Put the extension's ``lib/py3`` on sys.path so ezdxf can be found."""
    try:
        import path_resolver
        path_resolver.update_paths()
        return
    except ImportError:
        pass
    cursor = os.path.dirname(os.path.abspath(__file__))
    subfolder = "py3" if sys.version_info[0] == 3 else "py2"
    for _ in range(8):          # button -> stack -> panel -> tab -> extension
        candidate = os.path.join(cursor, "lib", subfolder)
        if os.path.isdir(candidate):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
            return
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return
        cursor = parent


_bootstrap_package()
_bootstrap_lib_path()

from anongee_autolevel import VERSION                             # noqa: E402
from anongee_autolevel import (compat, dxf_text, naming,          # noqa: E402
                               planner, revit_ops, settings, stackview,
                               textparse)


# ── brushes for the runtime-drawn stack ────────────────────────────────────

def _brush(r, g, b):
    brush = SolidColorBrush(Color.FromRgb(r, g, b))
    brush.Freeze()
    return brush


BRUSH_TEXT = _brush(0x14, 0x14, 0x14)      # Charcoal Black
BRUSH_MUTED = _brush(0x6B, 0x72, 0x80)     # Mid Grey
BRUSH_SUCCESS = _brush(0x16, 0xA3, 0x4A)   # Success Green
BRUSH_ERROR = _brush(0xDC, 0x26, 0x26)     # Error Red
BRUSH_NEW = _brush(0xE0, 0x20, 0x20)       # Vivid Red
BRUSH_EDIT = _brush(0x1D, 0x4E, 0xD8)      # Info Blue
BRUSH_GHOST = _brush(0xC0, 0xC8, 0xD8)     # Silver Steel
BRUSH_RULE = _brush(0xE2, 0xE4, 0xEA)      # Light Border

STATE_BRUSHES = {
    planner.STATE_EXISTING: BRUSH_TEXT,
    planner.STATE_NEW: BRUSH_NEW,
    planner.STATE_RENAME: BRUSH_EDIT,
    planner.STATE_MOVE: BRUSH_EDIT,
    planner.STATE_EDIT: BRUSH_EDIT,
    planner.STATE_DELETE: BRUSH_GHOST,
}

FONT_MONO = FontFamily("JetBrains Mono, Consolas, Courier New")

SOURCE_ACTIVE = 0
SOURCE_SELECTION = 1
SOURCE_DOCUMENT = 2
SOURCE_DXF_FILE = 3
SOURCE_FIRST_CAD = 4

UNIT_CHOICES = (None, "mm", "cm", "m", "ft")
CASE_CHOICES = ("keep", "upper", "lower", "title")
SNAP_CHOICES = ("1 mm", "5 mm", "10 mm", "25 mm", "50 mm", "100 mm")
SNAP_DEFAULT_INDEX = 2

TAB_HINTS = (
    ("TabDetect",
     "Pick where the levels are written, then press Scan for levels. Nothing "
     "reaches the model — everything lands in the table first."),
    ("TabGenerate",
     "No drawing to read? Say how many levels and how tall they are; they get "
     "named to match what this model already calls its levels."),
    ("TabRename",
     "Tick rows in the table, then set a rule. The preview shows what every "
     "name becomes before anything is staged."),
    ("TabViews",
     "Optionally give each new level its plan views, then read the summary of "
     "what Apply changes is about to do."),
    ("TabGuide",
     "The whole tool on one page. Come back here whenever something is unclear."),
)


# ── persistent session state ───────────────────────────────────────────────
# See the module docstring: the CLR types below may be emitted exactly once
# per Revit session, and the window reference has to outlive run().
_STATE_MODULE = "AnonGee_AutoLevelState"
_state = sys.modules.get(_STATE_MODULE)
if _state is None:
    _state = types.ModuleType(_STATE_MODULE)
    _state.handler_cls = None
    _state.preprocessor_cls = None
    _state.window_ref = None
    sys.modules[_STATE_MODULE] = _state


if _state.handler_cls is None:
    class AutoLevelHandler(IExternalEventHandler):
        """Runs on Revit's primary thread; the only place Revit is touched.

        The WPF thread writes ``data``, raises the external event, and gets the
        answer back through the window's dispatcher. Nothing but plain data
        crosses in either direction (§12.8.7.2).
        """

        # Required by Python.NET 3 to emit a real derived CLR type; without it
        # AutoLevelHandler() routes to the interface's one-arg cast and raises
        # "TypeError: interface takes exactly one argument" (§12.8.7.1).
        __namespace__ = "AnonGee"

        # No __init__ — a constructor on an interface subclass trips the same
        # pythonnet trap. Per-instance state is set in run() after construction.
        data = {}
        app = None
        preprocessor = None

        def Execute(self, uiapp):
            request = self.data.get("request")
            payload = self.data.get("payload") or {}
            result = {"request": request}
            try:
                uidoc = uiapp.ActiveUIDocument
                doc = uidoc.Document if uidoc is not None else None
                if doc is None:
                    result["error"] = "Open a Revit model first."
                else:
                    self._dispatch(request, payload, doc, uidoc, result)
            except Exception as error:
                traceback.print_exc()
                result["error"] = "{0}: {1}".format(
                    type(error).__name__, str(error)[:240])
            self.data["result"] = result
            self.data["request"] = None
            self._marshal_to_ui()

        def GetName(self):
            return "AnonGee_AutoLevelHandler"

        # ── Revit-thread work ─────────────────────────────────────────
        def _dispatch(self, request, payload, doc, uidoc, result):
            if request == "snapshot":
                result.update(revit_ops.snapshot(doc))
                result["cad"] = revit_ops.list_cad_links(doc)
            elif request == "scan":
                result.update(revit_ops.collect_texts(
                    doc, uidoc, payload.get("scope") or "active_view"))
            elif request == "apply":
                result["report"] = revit_ops.apply_operations(
                    doc, payload, self.preprocessor)
                result.update(revit_ops.snapshot(doc))
                result["cad"] = revit_ops.list_cad_links(doc)
            elif request == "select":
                result["selected"] = revit_ops.select_levels(
                    uidoc, payload.get("ids") or [])
            elif request == "open_plan":
                ok, message = revit_ops.open_level_plan(uidoc,
                                                        payload.get("id"))
                result["ok"] = ok
                result["message"] = message
            else:
                result["error"] = "Unknown request: {0}".format(request)

        # ── WPF-thread marshal ────────────────────────────────────────
        def _marshal_to_ui(self):
            try:
                self.app.window.Dispatcher.BeginInvoke(
                    DispatcherPriority.Normal, Action(self.app._on_handler_done))
            except Exception:
                pass

    _state.handler_cls = AutoLevelHandler
else:
    # Later press: reuse the CLR type pythonnet already emitted.
    AutoLevelHandler = _state.handler_cls


if _state.preprocessor_cls is None:
    class WarningSwallower(IFailuresPreprocessor):
        """Delete Revit's warnings so a batch doesn't stall on a dialog.

        Warnings only — anything Revit rates as an error still stops the
        transaction and is reported back to the user.
        """

        __namespace__ = "AnonGee"

        def PreprocessFailures(self, accessor):
            try:
                for failure in accessor.GetFailureMessages():
                    accessor.DeleteWarning(failure)
            except Exception:
                pass
            return FailureProcessingResult.Continue

    _state.preprocessor_cls = WarningSwallower
else:
    WarningSwallower = _state.preprocessor_cls


# ── the window ─────────────────────────────────────────────────────────────

class AutoLevelApp(object):
    """The modeless window. A fresh instance per launch — subscriptions are
    never made at module scope (§12.9.2 handler accumulation)."""

    def __init__(self, xaml_path, handler, ext_event):
        self.handler = handler
        self.ext_event = ext_event

        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        try:
            self.window = XamlReader.Load(stream)
        finally:
            stream.Close()

        self.plan = planner.LevelPlan()
        self.snapshot = {}
        self.cad_links = []
        self.source_paths = {}
        self.dxf_path = ""
        self.project_format = {}

        self._queue = []
        self._busy = False
        self._callback = None
        self._refreshing = False
        self._scanned_once = False

        # the stack drawing's camera — zoom, pan and the elevation-to-pixel
        # mapping all live in stackview so they can be tested without WPF
        self.stack = stackview.StackView()
        self._stack_hits = []
        self._drag_row = None
        self._drag_start_y = 0.0
        self._drag_start_mm = 0.0
        self._pan_start_y = None
        self._pan_start_center = None

        self.settings, note = settings.load()

        self._bind_controls()
        self._fill_static_lists()
        self._apply_settings(self.settings)
        self._wire_events()
        self.SettingsHint.Text = note or "Using the built-in defaults."

    # ── control lookup ────────────────────────────────────────────────
    def _bind_controls(self):
        find = self.window.FindName
        names = (
            "VersionText",
            "StackCanvas", "StackHint", "HeightBadgeText",
            "ZoomInBtn", "ZoomOutBtn", "ZoomFitBtn", "SnapCombo",
            "TabDetect", "TabGenerate", "TabRename", "TabViews", "TabGuide",
            "TabHint",
            "PanelDetect", "PanelGenerate", "PanelRename", "PanelViews",
            "PanelGuide",
            "SourceCombo", "BrowseBtn", "SourcePathText", "UnitCombo",
            "DatumInput", "ToleranceInput", "LayerInput", "EvidenceToggle",
            "PositionToggle", "AdoptToggle", "PasteInput", "ScanBtn",
            "ParsePasteBtn", "DetectSummary",
            "CountInput", "HeightInput", "BaseCombo", "FollowRadio",
            "TemplateRadio", "TemplateInput", "StartInput", "NamePreview",
            "GenerateBtn", "RespaceBtn", "PushAboveToggle",
            "PrefixInput", "SuffixInput", "FindInput", "ReplaceInput",
            "CaseCombo", "ScopeSelectedRadio", "ScopeAllRadio",
            "RenameTemplateToggle", "RenameTemplateInput", "RenameStartInput",
            "RenamePreview", "ApplyRenameBtn",
            "CreateViewsToggle", "ViewTypeList", "ViewTemplateCombo",
            "ChangeSummary", "ResetBtn",
            "SaveSettingsBtn", "ForgetSettingsBtn", "SettingsHint",
            "UndoBtn", "RedoBtn",
            "SelectAllBtn", "ClearBtn", "SelectRevitBtn", "OpenPlanBtn",
            "RestoreBtn", "DeleteBtn", "GridHint", "LevelGrid",
            "StatusBar", "LiveCount", "RefreshBtn", "ApplyBtn", "CloseBtn",
        )
        for name in names:
            setattr(self, name, find(name))

    def _fill_static_lists(self):
        self.VersionText.Text = "v{0}".format(VERSION)

        for label in ("Auto-detect", "Millimetres (mm)", "Centimetres (cm)",
                      "Metres (m)", "Feet (ft)"):
            self.UnitCombo.Items.Add(label)
        self.UnitCombo.SelectedIndex = 0

        for label in ("Keep the case", "UPPERCASE", "lowercase", "Title Case"):
            self.CaseCombo.Items.Add(label)
        self.CaseCombo.SelectedIndex = 0

        for label in SNAP_CHOICES:
            self.SnapCombo.Items.Add(label)
        self.SnapCombo.SelectedIndex = SNAP_DEFAULT_INDEX

        self._fill_source_combo()

    def _fill_source_combo(self):
        """Rebuild the source list, keeping whatever the user had chosen.

        This runs again after every apply, and losing the chosen source each
        time would be its own small annoyance.
        """
        previous = None
        if self.SourceCombo.SelectedIndex >= 0:
            previous = str(self.SourceCombo.SelectedItem)

        self.SourceCombo.Items.Clear()
        self.source_paths = {}
        for label in ("Active view — text notes + spot elevations",
                      "Current selection in Revit",
                      "Whole model — every text note",
                      "DXF file on disk…"):
            self.SourceCombo.Items.Add(label)
        index = SOURCE_FIRST_CAD
        for link in self.cad_links:
            path = link.get("path") or ""
            if not path or os.path.splitext(path)[1].lower() != ".dxf":
                continue
            self.SourceCombo.Items.Add("CAD · {0}".format(link.get("name")))
            self.source_paths[index] = path
            index += 1

        restored = -1
        if previous is not None:
            for position in range(self.SourceCombo.Items.Count):
                if str(self.SourceCombo.Items[position]) == previous:
                    restored = position
                    break
        if restored < 0:
            # Only the fixed entries are safe to restore by index: a CAD slot
            # holds a different file in the next model, and silently scanning
            # the wrong drawing is worse than starting on the active view.
            saved = self.settings.get("source_index", 0)
            if 0 <= saved < min(SOURCE_FIRST_CAD, self.SourceCombo.Items.Count):
                restored = saved
        self.SourceCombo.SelectedIndex = restored if restored >= 0 else 0

    # ── event wiring ──────────────────────────────────────────────────
    def _wire_events(self):
        for tab in (self.TabDetect, self.TabGenerate, self.TabRename,
                    self.TabViews, self.TabGuide):
            tab.Checked += self._on_tab_changed

        self.SourceCombo.SelectionChanged += self._on_source_changed
        self.BrowseBtn.Click += self._on_browse
        self.ScanBtn.Click += self._on_scan
        self.ParsePasteBtn.Click += self._on_parse_paste

        self.GenerateBtn.Click += self._on_generate
        self.RespaceBtn.Click += self._on_respace
        for control in (self.CountInput, self.HeightInput, self.TemplateInput,
                        self.StartInput):
            control.TextChanged += self._on_generate_input_changed
        self.FollowRadio.Checked += self._on_generate_input_changed
        self.TemplateRadio.Checked += self._on_generate_input_changed

        self.RenameTemplateToggle.Checked += self._on_rename_mode_changed
        self.RenameTemplateToggle.Unchecked += self._on_rename_mode_changed
        for control in (self.PrefixInput, self.SuffixInput, self.FindInput,
                        self.ReplaceInput, self.RenameTemplateInput,
                        self.RenameStartInput):
            control.TextChanged += self._on_rename_input_changed
        self.CaseCombo.SelectionChanged += self._on_rename_input_changed
        self.ScopeSelectedRadio.Checked += self._on_rename_input_changed
        self.ScopeAllRadio.Checked += self._on_rename_input_changed
        self.ApplyRenameBtn.Click += self._on_apply_rename

        self.ResetBtn.Click += self._on_reset
        self.SaveSettingsBtn.Click += self._on_save_settings
        self.ForgetSettingsBtn.Click += self._on_forget_settings

        self.UndoBtn.Click += self._on_undo
        self.RedoBtn.Click += self._on_redo
        self.window.PreviewKeyDown += self._on_key_down

        self.SelectAllBtn.Click += self._on_select_all
        self.ClearBtn.Click += self._on_clear_selection
        self.SelectRevitBtn.Click += self._on_select_in_revit
        self.OpenPlanBtn.Click += self._on_open_plan
        self.RestoreBtn.Click += self._on_restore
        self.DeleteBtn.Click += self._on_mark_delete

        self.LevelGrid.SelectionChanged += self._on_grid_selection_changed
        self.LevelGrid.CellEditEnding += self._on_cell_edit_ending

        self.StackCanvas.SizeChanged += self._on_canvas_resized
        self.StackCanvas.MouseLeftButtonDown += self._on_canvas_down
        self.StackCanvas.MouseMove += self._on_canvas_move
        self.StackCanvas.MouseLeftButtonUp += self._on_canvas_up
        self.StackCanvas.MouseWheel += self._on_canvas_wheel
        self.ZoomInBtn.Click += self._on_zoom_in
        self.ZoomOutBtn.Click += self._on_zoom_out
        self.ZoomFitBtn.Click += self._on_zoom_fit

        self.RefreshBtn.Click += self._on_refresh
        self.ApplyBtn.Click += self._on_apply
        self.CloseBtn.Click += self._on_close
        self.window.Closed += self._on_closed

    # ── the request queue (§12.8.7.3) ─────────────────────────────────
    def _enqueue(self, request, payload=None, callback=None):
        self._queue.append((request, payload or {}, callback))
        self._pump()

    def _pump(self):
        if self._busy or not self._queue:
            return
        if self.ext_event is None:
            self.set_status("ExternalEvent unavailable — relaunch the tool "
                            "from the ribbon.", True)
            return
        self._busy = True
        request, payload, callback = self._queue.pop(0)
        self._callback = callback
        self.handler.data["request"] = request
        self.handler.data["payload"] = payload
        try:
            self.ext_event.Raise()
        except Exception as error:
            self._busy = False
            self._callback = None
            self.set_status("Couldn't reach Revit: {0}".format(
                str(error)[:120]), True)

    def _on_handler_done(self):
        """Back on the WPF thread with whatever Execute() produced."""
        self._busy = False
        result = self.handler.data.get("result") or {}
        self.handler.data["result"] = None
        callback = self._callback
        self._callback = None
        try:
            if result.get("error"):
                self.set_status(result["error"], True)
                self.update_counts()    # a failed apply left the button off
            elif callback is not None:
                callback(result)
        except Exception as error:
            traceback.print_exc()
            self.set_status("UI error: {0}".format(str(error)[:160]), True)
        self._pump()

    # ── initial + refresh load ────────────────────────────────────────
    def initial_load(self):
        self.set_status("Reading the model's levels…")
        self._enqueue("snapshot", callback=self._on_snapshot)

    def _on_snapshot(self, result):
        self.snapshot = result
        self.cad_links = result.get("cad") or []
        self.project_format = dict(
            (round(level["elev_mm"], 3), level.get("elev_project") or "")
            for level in result.get("levels") or [])
        self.plan = planner.LevelPlan()
        self.plan.project_formatter = self._format_project
        self.plan.load_existing(result.get("levels") or [])
        self.stack.fit()                    # a new stack starts fitted
        self._fill_source_combo()
        self._fill_base_combo()
        self._fill_view_lists()
        self.refresh_grid()
        levels = len(self.plan.rows)
        self.set_status("{0} level{1} in \"{2}\".".format(
            levels, "" if levels == 1 else "s", result.get("title", "the model")))

    def _format_project(self, millimetres):
        """Project-unit text for a level, from the snapshot where possible.

        Revit does the formatting on its own thread; anything the user has
        moved since then falls back to plain metres rather than a stale string.
        """
        known = self.project_format.get(round(millimetres, 3))
        if known:
            return known
        return textparse.format_metres(millimetres)

    def _fill_base_combo(self):
        self.BaseCombo.Items.Clear()
        self.BaseCombo.Items.Add("Top of the stack")
        for row in self.plan.live_rows():
            self.BaseCombo.Items.Add("{0}  ({1:.0f})".format(row.Name, row.ElevMm))
        self.BaseCombo.SelectedIndex = 0

    def _fill_view_lists(self):
        """Rebuild the view-type ticks and template list, keeping the ticks.

        These are real .NET CheckBoxes rather than bound items — reading
        IsChecked off a CheckBox avoids the Python-bool binding trap entirely
        (§12.7.Q).
        """
        previously_ticked = set(self._checked_view_type_ids())
        first_fill = self.ViewTypeList.Children.Count == 0

        self.ViewTypeList.Children.Clear()
        for view_type in self.snapshot.get("view_types") or []:
            box = CheckBox()
            box.Content = "{0}  ·  {1}".format(view_type["name"],
                                               view_type["family"])
            box.Tag = view_type["id"]
            box.Margin = Thickness(6, 3, 6, 3)
            if not first_fill:
                box.IsChecked = view_type["id"] in previously_ticked
            elif self.settings.get("view_type_names"):
                # Remembered by NAME: a view family type id means nothing in
                # the next project, but "Structural Plan" still does.
                box.IsChecked = str(box.Content) in self.settings["view_type_names"]
            else:
                box.IsChecked = view_type["family"] == "FloorPlan"
            self.ViewTypeList.Children.Add(box)

        previous = None
        if self.ViewTemplateCombo.SelectedIndex > 0:
            previous = str(self.ViewTemplateCombo.SelectedItem)
        self.ViewTemplateCombo.Items.Clear()
        self.ViewTemplateCombo.Items.Add("(no template)")
        for template in self.snapshot.get("view_templates") or []:
            self.ViewTemplateCombo.Items.Add(template["name"])
        wanted = previous or self.settings.get("view_template_name") or None
        restored = 0
        if wanted:
            for position in range(self.ViewTemplateCombo.Items.Count):
                if str(self.ViewTemplateCombo.Items[position]) == wanted:
                    restored = position
                    break
        self.ViewTemplateCombo.SelectedIndex = restored

    # ── the grid ──────────────────────────────────────────────────────
    def refresh_grid(self):
        """Rebuild the grid from the plan, keeping the ticked rows ticked.

        Re-assigning ItemsSource is what makes WPF re-read the Python objects
        (§12.7.G); it also clears the selection, so the ticks are restored
        afterwards behind the _refreshing guard (§12.7.Q).
        """
        ticked = set()
        try:
            for item in list(self.LevelGrid.SelectedItems):
                ticked.add(id(item))
        except Exception:
            pass

        self.plan.refresh_display(self._format_project)

        self._refreshing = True
        try:
            items = ArrayList()
            for row in self.plan.rows:
                items.Add(row)
            self.LevelGrid.ItemsSource = None
            self.LevelGrid.ItemsSource = items
            self.LevelGrid.SelectedItems.Clear()
            for row in self.plan.rows:
                if id(row) in ticked:
                    self.LevelGrid.SelectedItems.Add(row)
        finally:
            self._refreshing = False

        self._sync_selection_flags()
        self.draw_stack()
        self.update_counts()
        self.update_previews()

    def _sync_selection_flags(self):
        selected = set()
        try:
            for item in list(self.LevelGrid.SelectedItems):
                selected.add(id(item))
        except Exception:
            pass
        for row in self.plan.rows:
            row.IsSelected = id(row) in selected

    def selected_rows(self):
        self._sync_selection_flags()
        return [row for row in self.plan.rows if row.IsSelected]

    def _on_grid_selection_changed(self, sender, args):
        if self._refreshing:
            return
        self._sync_selection_flags()
        self.draw_stack()
        self.update_counts()
        self.update_previews()

    def _on_cell_edit_ending(self, sender, args):
        """Commit an inline edit through the planner, not through the binding.

        CellEditEnding fires before WPF writes the binding back, so the typed
        text is read off the TextBox and put through LevelPlan — that is what
        enforces unique names, reads "3.5 m" as readily as "3500", and keeps
        the pending-change state honest. A rejected edit cancels the commit so
        the raw text never reaches the row, and the deferred refresh rewrites
        every cell from the plan afterwards.
        """
        if args.EditAction != DataGridEditAction.Commit:
            return
        row = args.Row.Item
        editor = args.EditingElement
        text = None
        try:
            text = editor.Text
        except Exception:
            return
        header = str(args.Column.Header or "")

        if header.startswith("Level name"):
            self._checkpoint("rename \"{0}\"".format(row.Name))
            ok, message = self.plan.rename(row, text)
        elif header.startswith("Elevation"):
            push = bool(self.PushAboveToggle.IsChecked)
            self._checkpoint("move \"{0}\"".format(row.Name))
            ok, message = self.plan.set_elevation(row, text, push_above=push)
            if ok and push:
                message = "Moved \"{0}\" and everything above it.".format(row.Name)
        else:
            return

        if ok:
            if message:
                self.set_status(message)
            else:
                self.set_status("Updated \"{0}\".".format(row.Name))
        else:
            args.Cancel = True          # keep the raw text out of the row
            self.plan.drop_checkpoint() # a rejected edit is not a history step
            self.set_status(message, True)

        # The grid is mid-commit; rebuilding ItemsSource now would throw.
        self.window.Dispatcher.BeginInvoke(DispatcherPriority.Background,
                                           Action(self.refresh_grid))

    # ── the stack drawing ─────────────────────────────────────────────
    def _on_canvas_resized(self, sender, args):
        self.draw_stack()

    def _elevations(self):
        return [row.ElevMm for row in self.plan.rows]

    def _stack_window(self):
        """The (lo, hi) elevation band currently on screen, in millimetres."""
        return self.stack.window(self._elevations())

    def _canvas_metrics(self):
        """(width, height, usable) or None when the canvas is too small."""
        width = self.StackCanvas.ActualWidth or 0.0
        height = self.StackCanvas.ActualHeight or 0.0
        usable = height - stackview.TOP_PAD - stackview.BOTTOM_PAD
        if width < 20 or usable < 10:
            return None
        return width, height, usable

    def draw_stack(self):
        """Draw the level stack to scale — the reason this window is wide.

        A table tells you the numbers; the drawing tells you the shape of the
        building, which is how you spot the level someone typed as 35000
        instead of 3500.

        Names are dropped rather than overprinted when levels crowd together,
        and the count of what was dropped goes in the hint — the fix is to
        zoom, and the user should be told that is what is happening.
        """
        canvas = self.StackCanvas
        canvas.Children.Clear()
        self._stack_hits = []

        metrics = self._canvas_metrics()
        if metrics is None:
            return
        width, height, usable = metrics

        rows = list(self.plan.rows)
        if not rows:
            self._canvas_message(canvas, width, height, "No levels yet.")
            self.HeightBadgeText.Text = "—"
            self.StackHint.Text = ("Nothing to draw. Add levels on the Generate "
                                   "tab, or detect them from a drawing.")
            return

        window = self._stack_window()
        lo, hi = window
        bounds = self.stack.bounds(self._elevations())

        # ground line, when zero is in view
        if lo <= 0.0 <= hi:
            ground = Line()
            ground.X1, ground.X2 = 4.0, width - 4.0
            ground.Y1 = ground.Y2 = self.stack.y_at(0.0, window, usable)
            ground.Stroke = BRUSH_RULE
            ground.StrokeThickness = 6.0
            canvas.Children.Add(ground)

        previous_y = None
        previous_elevation = None
        last_label_y = None
        hidden = 0

        for row in rows:
            y = self.stack.y_at(row.ElevMm, window, usable)
            if not self.stack.visible(y, height):
                previous_y, previous_elevation = y, row.ElevMm
                continue

            brush = STATE_BRUSHES.get(row.State, BRUSH_TEXT)
            selected = bool(row.IsSelected)
            self._stack_hits.append((row, y))

            line = Line()
            line.X1, line.X2 = 8.0, width - 8.0
            line.Y1 = line.Y2 = y
            line.Stroke = brush
            line.StrokeThickness = 2.5 if (row.is_new or selected) else 1.2
            if row.State == planner.STATE_DELETE:
                line.StrokeDashArray.Add(3.0)
                line.StrokeDashArray.Add(2.0)
            canvas.Children.Add(line)

            if selected:
                marker = Rectangle()
                marker.Width, marker.Height = 3.0, 12.0
                marker.Fill = BRUSH_NEW
                canvas.Children.Add(marker)
                Canvas.SetLeft(marker, 0.0)
                Canvas.SetTop(marker, y - 6.0)

            room = last_label_y is None or (last_label_y - y) >= stackview.LABEL_GAP
            if room or selected:
                label = TextBlock()
                label.Text = row.Name or "(unnamed)"
                label.FontSize = 8.5
                label.FontFamily = FONT_MONO
                label.Foreground = brush
                label.MaxWidth = max(60.0, width - 78.0)
                canvas.Children.Add(label)
                Canvas.SetLeft(label, 10.0)
                Canvas.SetTop(label, y - 11.0)

                value = TextBlock()
                value.Text = textparse.format_metres(row.ElevMm)
                value.FontSize = 8.5
                value.FontFamily = FONT_MONO
                value.Foreground = BRUSH_MUTED
                canvas.Children.Add(value)
                Canvas.SetLeft(value, max(10.0, width - 56.0))
                Canvas.SetTop(value, y - 11.0)
                last_label_y = y
            else:
                hidden += 1

            # the gap to the level below, written in the middle of it
            if (previous_y is not None and previous_elevation is not None
                    and previous_y - y > 16.0):
                gap = TextBlock()
                gap.Text = "{0:.0f}".format(row.ElevMm - previous_elevation)
                gap.FontSize = 7.5
                gap.FontFamily = FONT_MONO
                gap.Foreground = BRUSH_GHOST
                canvas.Children.Add(gap)
                Canvas.SetLeft(gap, 12.0)
                Canvas.SetTop(gap, (y + previous_y) / 2.0 - 5.0)
            previous_y, previous_elevation = y, row.ElevMm

        if self.stack.zoom > stackview.ZOOM_MIN + 0.001:
            self.HeightBadgeText.Text = "{0:.3f} m · {1:.1f}×".format(
                (hi - lo) / 1000.0, self.stack.zoom)
        else:
            self.HeightBadgeText.Text = "{0:.3f} m".format(
                (bounds[1] - bounds[0]) / 1000.0)

        hint = "Drag a level to move it · double-click to rename · wheel to zoom."
        if hidden:
            hint += "  {0} name{1} hidden — zoom in to separate them.".format(
                hidden, "" if hidden == 1 else "s")
        self.StackHint.Text = hint

    # ── zoom ──────────────────────────────────────────────────────────
    def _zoom_about(self, y, factor):
        """Zoom keeping the elevation under *y* pinned where it is."""
        metrics = self._canvas_metrics()
        usable = metrics[2] if metrics else 0.0
        if self.stack.zoom_about(y, factor, self._elevations(), usable):
            self.draw_stack()

    def _on_zoom_in(self, sender, args):
        metrics = self._canvas_metrics()
        middle = (metrics[1] / 2.0) if metrics else 0.0
        self._zoom_about(middle, stackview.ZOOM_STEP)

    def _on_zoom_out(self, sender, args):
        metrics = self._canvas_metrics()
        middle = (metrics[1] / 2.0) if metrics else 0.0
        self._zoom_about(middle, 1.0 / stackview.ZOOM_STEP)

    def _on_zoom_fit(self, sender, args):
        self.stack.fit()
        self.draw_stack()
        self.set_status("Showing the whole stack.")

    def _on_canvas_wheel(self, sender, args):
        from System.Windows.Input import Keyboard, ModifierKeys
        window = self._stack_window()
        if window is None:
            return
        if bool(Keyboard.Modifiers & ModifierKeys.Shift):
            self.stack.nudge(0.15 if args.Delta > 0 else -0.15, window)
            self.draw_stack()
        else:
            point = args.GetPosition(self.StackCanvas)
            self._zoom_about(point.Y, stackview.ZOOM_STEP if args.Delta > 0
                             else 1.0 / stackview.ZOOM_STEP)
        args.Handled = True

    # ── clicking and dragging levels ──────────────────────────────────
    def _snap_mm(self):
        return _as_float(str(self.SnapCombo.SelectedItem or "10 mm"), 10.0)

    def _row_at(self, y):
        """The level drawn nearest *y*, if the click is close enough to it."""
        return stackview.nearest(self._stack_hits, y)

    def _select_only(self, row):
        self._refreshing = True
        try:
            self.LevelGrid.SelectedItems.Clear()
            self.LevelGrid.SelectedItems.Add(row)
        except Exception:
            pass
        finally:
            self._refreshing = False
        self._sync_selection_flags()
        try:
            self.LevelGrid.ScrollIntoView(row)
        except Exception:
            pass
        self.update_counts()
        self.update_previews()

    def _begin_name_edit(self, row):
        """Put the grid into edit mode on this level's name.

        Double-clicking the drawing edits in the table rather than floating an
        editor over the canvas: one editing path, one set of validation rules.
        """
        try:
            column = None
            for candidate in self.LevelGrid.Columns:
                if str(candidate.Header or "").startswith("Level name"):
                    column = candidate
                    break
            if column is None:
                return
            self.LevelGrid.ScrollIntoView(row)
            self.LevelGrid.CurrentCell = DataGridCellInfo(row, column)
            self.LevelGrid.Focus()
            self.LevelGrid.BeginEdit()
            self.set_status("Editing \"{0}\" — press Enter to keep it.".format(
                row.Name))
        except Exception:
            self.set_status("Edit that one in the table on the right.", True)

    def _on_canvas_down(self, sender, args):
        point = args.GetPosition(self.StackCanvas)
        row = self._row_at(point.Y)

        if args.ClickCount >= 2:
            if row is not None:
                self._select_only(row)
                self.draw_stack()
                self._begin_name_edit(row)
            args.Handled = True
            return

        if row is not None:
            self._select_only(row)
            if row.State != planner.STATE_DELETE:
                # One history step for the whole drag, not one per mouse-move.
                self._checkpoint("move \"{0}\"".format(row.Name))
                self._drag_row = row
                self._drag_start_y = point.Y
                self._drag_start_mm = row.ElevMm
                self.StackCanvas.CaptureMouse()
            self.draw_stack()
        else:
            window = self._stack_window()
            if window is not None:
                self._pan_start_y = point.Y
                self._pan_start_center = self.stack.center_mm
                self.StackCanvas.CaptureMouse()
        args.Handled = True

    def _on_canvas_move(self, sender, args):
        if self._drag_row is None and self._pan_start_y is None:
            return
        metrics = self._canvas_metrics()
        window = self._stack_window()
        if metrics is None or window is None:
            return
        _width, _height, usable = metrics
        mm_per_px = self.stack.mm_per_pixel(window, usable)
        point = args.GetPosition(self.StackCanvas)

        if self._drag_row is not None:
            from System.Windows.Input import Keyboard, ModifierKeys
            value = self._drag_start_mm - (point.Y - self._drag_start_y) * mm_per_px
            if not bool(Keyboard.Modifiers & ModifierKeys.Shift):
                value = stackview.snap(value, self._snap_mm())
            push = bool(self.PushAboveToggle.IsChecked)
            ok, message = self.plan.set_elevation(self._drag_row, float(value),
                                                  push_above=push)
            if ok:
                moved = self._drag_row.ElevMm - self._drag_start_mm
                self.set_status("{0} → {1} mm ({2}{3:.0f}){4}".format(
                    self._drag_row.Name,
                    textparse.format_mm(self._drag_row.ElevMm),
                    "+" if moved >= 0 else "", moved,
                    ", pushing the levels above" if push else ""))
            else:
                self.set_status(message, True)
            self.draw_stack()
        else:
            self.stack.pan_pixels(point.Y - self._pan_start_y, window, usable,
                                  start_center=self._pan_start_center)
            self.draw_stack()

    def _on_canvas_up(self, sender, args):
        dragged = self._drag_row
        self._drag_row = None
        self._pan_start_y = None
        self._pan_start_center = None
        try:
            self.StackCanvas.ReleaseMouseCapture()
        except Exception:
            pass
        if dragged is not None:
            moved = abs(dragged.ElevMm - self._drag_start_mm) >= 0.5
            if not moved:
                self.plan.drop_checkpoint()     # a click, not a move
            # The grid only catches up at the end of the drag — rebuilding
            # ItemsSource on every mouse move would make it crawl. It also
            # redraws the history buttons, so the checkpoint is settled first.
            self.refresh_grid()
            if not moved:
                self.set_status("\"{0}\" selected.".format(dragged.Name))
            else:
                self.set_status("Moved \"{0}\" to {1} mm — staged, not applied."
                                .format(dragged.Name,
                                        textparse.format_mm(dragged.ElevMm)))
        args.Handled = True

    def _canvas_message(self, canvas, width, height, message):
        label = TextBlock()
        label.Text = message
        label.FontSize = 9.0
        label.Foreground = BRUSH_MUTED
        canvas.Children.Add(label)
        Canvas.SetLeft(label, 12.0)
        Canvas.SetTop(label, height / 2.0 - 8.0)

    # ── counts, previews, status ──────────────────────────────────────
    def update_counts(self):
        counts = self.plan.summary()
        ticked = len(self.selected_rows())
        self.LiveCount.Text = "{0} level(s) · {1} change(s) · {2} ticked".format(
            counts["total"], counts["changes"], ticked)
        self.ApplyBtn.IsEnabled = counts["changes"] > 0
        self.GridHint.Text = self._next_step(counts)
        self._refresh_history_buttons()

        if counts["changes"]:
            parts = []
            for key, label in (("new", "create"), ("rename", "rename"),
                               ("move", "move"), ("edit", "rename + move"),
                               ("delete", "delete")):
                if counts.get(key):
                    parts.append("{0} to {1}".format(counts[key], label))
            summary = " · ".join(parts)
            blocking = [message for severity, _row, message in self.plan.issues
                        if severity == "error"]
            if blocking:
                summary += "\n\nFix first: {0}".format(blocking[0])
            self.ChangeSummary.Text = summary
        else:
            self.ChangeSummary.Text = "No changes pending."

    def _next_step(self, counts):
        """One line above the table saying what to do next.

        The tool has four tabs and a dozen options; without this the first
        question is always "so what do I press". It answers that from the
        state of the plan rather than making the user work it out.
        """
        if not self.plan.rows:
            return ("Next — this model has no levels. Add some on 2 · Generate, "
                    "or read the Guide tab.")
        blocking = [message for severity, _row, message in self.plan.issues
                    if severity == "error"]
        if blocking:
            return "Next — fix this, then Apply: {0}".format(blocking[0])
        if counts["changes"]:
            return ("Next — press Apply changes to write {0} staged change(s) "
                    "to the model.".format(counts["changes"]))
        if not self._scanned_once:
            return ("Next — on 1 · Detect pick a source and press Scan for "
                    "levels. Nothing reaches the model until you Apply.")
        return ("Nothing staged. Detect, Generate or Rename to stage a change "
                "— or drag a level in the drawing.")

    def update_previews(self):
        self._update_generate_preview()
        self._update_rename_preview()

    def _update_generate_preview(self):
        count = _as_int(self.CountInput.Text, 0)
        if count <= 0:
            self.NamePreview.Text = "Set how many levels to add."
            return
        height = _as_float(self.HeightInput.Text, planner.DEFAULT_STOREY_MM)
        base = self._base_elevation()
        rows = self.plan.live_rows()
        start = _as_int(self.StartInput.Text, None)

        names = None
        note = ""
        if bool(self.FollowRadio.IsChecked):
            convention = naming.learn_convention([row.Name for row in rows])
            if convention is not None:
                names = convention.next_names(min(count, 6), start)
                note = convention.describe()
            else:
                note = "no pattern in the model — the template is used"
        if names is None:
            template = self.TemplateInput.Text or "Level {n}"
            first = start if start is not None else len(rows) + 1
            names = [naming.render_template(template, first + i,
                                            base + height * (i + 1))
                     for i in range(min(count, 6))]

        lines = []
        for i, name in enumerate(names):
            lines.append("{0:<26}{1:>10.0f}".format(
                name[:26], base + height * (i + 1)))
        if count > len(names):
            lines.append("… and {0} more".format(count - len(names)))
        self.NamePreview.Text = "\n".join(lines) + ("\n\n" + note if note else "")

    def _base_elevation(self):
        rows = self.plan.live_rows()
        index = self.BaseCombo.SelectedIndex
        if index > 0 and index - 1 < len(rows):
            return rows[index - 1].ElevMm
        return rows[-1].ElevMm if rows else 0.0

    def _rename_targets(self):
        if bool(self.ScopeAllRadio.IsChecked):
            return self.plan.live_rows()
        return [row for row in self.selected_rows()
                if row.State != planner.STATE_DELETE]

    def _update_rename_preview(self):
        targets = self._rename_targets()
        if not targets:
            self.RenamePreview.Text = ("Tick the rows to rename, or switch "
                                       "\"Apply to\" to every level.")
            return
        use_template = bool(self.RenameTemplateToggle.IsChecked)
        template = self.RenameTemplateInput.Text or ""
        start = _as_int(self.RenameStartInput.Text, 1)
        case_mode = CASE_CHOICES[max(0, self.CaseCombo.SelectedIndex)]

        lines = []
        for offset, row in enumerate(targets[:8]):
            if use_template and template:
                proposed = naming.render_template(template, start + offset,
                                                  row.ElevMm, row.Name)
            else:
                proposed = naming.apply_affixes(
                    row.Name, self.PrefixInput.Text, self.SuffixInput.Text,
                    self.FindInput.Text, self.ReplaceInput.Text, case_mode)
            arrow = "→" if proposed != row.Name else "="
            lines.append("{0:<22} {1} {2}".format(row.Name[:22], arrow,
                                                  proposed[:22]))
        if len(targets) > 8:
            lines.append("… and {0} more".format(len(targets) - 8))
        self.RenamePreview.Text = "\n".join(lines)

    def set_status(self, message, is_error=False):
        self.StatusBar.Text = message or ""
        self.StatusBar.Foreground = BRUSH_ERROR if is_error else BRUSH_SUCCESS

    # ── tabs ──────────────────────────────────────────────────────────
    def _on_tab_changed(self, sender, args):
        panels = ((self.TabDetect, self.PanelDetect),
                  (self.TabGenerate, self.PanelGenerate),
                  (self.TabRename, self.PanelRename),
                  (self.TabViews, self.PanelViews),
                  (self.TabGuide, self.PanelGuide))
        for tab, panel in panels:
            panel.Visibility = (Visibility.Visible if bool(tab.IsChecked)
                                else Visibility.Collapsed)
        for name, hint in TAB_HINTS:
            if bool(getattr(self, name).IsChecked):
                self.TabHint.Text = hint
                break
        self.update_previews()

    # ── detect ────────────────────────────────────────────────────────
    def _on_source_changed(self, sender, args):
        index = self.SourceCombo.SelectedIndex
        is_file = index == SOURCE_DXF_FILE
        is_cad = index in self.source_paths
        self.BrowseBtn.Visibility = (Visibility.Visible if is_file
                                     else Visibility.Collapsed)
        if is_file:
            self.SourcePathText.Text = (self.dxf_path or
                                        "Pick a DXF with Browse…")
        elif is_cad:
            self.dxf_path = self.source_paths[index]
            self.SourcePathText.Text = self.dxf_path
        elif index == SOURCE_SELECTION:
            self.SourcePathText.Text = ("Select the level tags in Revit — the "
                                        "window stays open while you do.")
        elif index == SOURCE_DOCUMENT:
            self.SourcePathText.Text = ("Reads every text note in the model. "
                                        "Slower, and noisier.")
        else:
            self.SourcePathText.Text = ("Scans text notes and spot elevations "
                                        "in the active view.")

    def _on_browse(self, sender, args):
        dialog = OpenFileDialog()
        dialog.Title = "Pick a DXF to read levels from"
        dialog.Filter = "DXF drawings (*.dxf)|*.dxf|All files (*.*)|*.*"
        if self.dxf_path and os.path.isfile(self.dxf_path):
            dialog.InitialDirectory = os.path.dirname(self.dxf_path)
        if dialog.ShowDialog():
            self.dxf_path = dialog.FileName
            self.SourcePathText.Text = self.dxf_path

    def _detect_options(self):
        return {
            "unit_hint": UNIT_CHOICES[max(0, self.UnitCombo.SelectedIndex)],
            "require_evidence": bool(self.EvidenceToggle.IsChecked),
            "use_positions": bool(self.PositionToggle.IsChecked),
            "datum_offset_mm": _as_float(self.DatumInput.Text, 0.0),
            "tolerance_mm": _as_float(self.ToleranceInput.Text,
                                      planner.DEFAULT_MATCH_TOLERANCE_MM),
            "adopt_names": bool(self.AdoptToggle.IsChecked),
        }

    def _on_scan(self, sender, args):
        index = self.SourceCombo.SelectedIndex
        if index == SOURCE_DXF_FILE or index in self.source_paths:
            self._scan_dxf()
            return
        scope = {SOURCE_SELECTION: "selection",
                 SOURCE_DOCUMENT: "document"}.get(index, "active_view")
        self.set_status("Reading the model's annotation…")
        self._enqueue("scan", {"scope": scope}, self._on_scan_result)

    def _scan_dxf(self):
        path = self.dxf_path
        if not path:
            self.set_status("Pick a DXF first.", True)
            return
        if not dxf_text.available():
            self.set_status("ezdxf isn't loaded — this needs the CPython 3 "
                            "engine.", True)
            return
        layers = [chunk.strip() for chunk in (self.LayerInput.Text or "").split(",")
                  if chunk.strip()]
        self.set_status("Reading {0}…".format(os.path.basename(path)))
        read = dxf_text.read_texts(path, layers)
        if read["error"]:
            self.set_status(read["error"], True)
            return
        self._absorb(read["entries"], [],
                     "{0} · {1}".format(os.path.basename(path), read["note"]))

    def _on_scan_result(self, result):
        self._absorb(result.get("entries") or [], result.get("exact") or [],
                     "{0} · {1}".format(result.get("view", "model"),
                                        result.get("note", "")))

    def _on_parse_paste(self, sender, args):
        text = self.PasteInput.Text or ""
        lines = [line for line in text.replace("\r", "\n").split("\n")
                 if line.strip()]
        if not lines:
            self.set_status("The paste box is empty.", True)
            return
        entries = [{"text": line, "source": "Pasted"} for line in lines]
        self._absorb(entries, [], "pasted text · {0} line(s)".format(len(lines)))

    def _absorb(self, entries, exact, origin):
        """Run detection over the entries and fold the result into the plan."""
        options = self._detect_options()
        result = textparse.detect(
            entries,
            unit_hint=options["unit_hint"],
            require_evidence=options["require_evidence"],
            datum_offset_mm=options["datum_offset_mm"],
            use_positions=options["use_positions"])

        candidates = list(result.candidates)
        for item in exact or []:
            candidate = textparse.Candidate(
                name="", elevation_mm=item["elev_mm"] - options["datum_offset_mm"],
                raw=item.get("text") or "", confidence=100,
                reasons=["read straight from Revit"],
                source=item.get("source") or "Spot elevation")
            candidates.append(candidate)
        candidates = textparse.merge_candidates(candidates)

        if not candidates:
            self.DetectSummary.Text = (
                "Nothing that looked like a level in {0}.\n\n"
                "Try turning off \"Need a level word or a sign\", or set the "
                "drawing unit by hand.".format(origin))
            self.set_status("No levels detected.", True)
            return

        self._checkpoint("read {0} level(s) from {1}".format(
            len(candidates), origin.split(" · ")[0]))
        created, matched, renamed = self.plan.add_candidates(
            candidates,
            tolerance_mm=options["tolerance_mm"],
            adopt_names=options["adopt_names"])
        self._scanned_once = True
        self.refresh_grid()

        lines = ["{0}".format(origin),
                 "{0} level(s) detected — {1} new, {2} already in the model"
                 .format(len(candidates), created, matched)]
        if renamed:
            lines.append("{0} existing level(s) took the drawing's name".format(
                renamed))
        lines.extend(result.notes)
        low = [c for c in candidates if c.confidence < 45]
        if low:
            lines.append("{0} low-confidence row(s) — check them before "
                         "applying".format(len(low)))
        self.DetectSummary.Text = "\n".join(lines)
        self.set_status("Detected {0} level(s): {1} new, {2} matched.".format(
            len(candidates), created, matched))

    # ── generate ──────────────────────────────────────────────────────
    def _on_generate_input_changed(self, sender, args):
        self._update_generate_preview()

    def _on_generate(self, sender, args):
        count = _as_int(self.CountInput.Text, 0)
        if count <= 0:
            self.set_status("How many levels? Put a number in.", True)
            return
        if count > 200:
            self.set_status("That's more than 200 levels — narrow it down.", True)
            return
        height = _as_float(self.HeightInput.Text, planner.DEFAULT_STOREY_MM)
        if height <= 0:
            self.set_status("A storey height has to be more than zero.", True)
            return
        mode = "follow" if bool(self.FollowRadio.IsChecked) else "template"
        self._checkpoint("add {0} level(s)".format(count))
        added, note = self.plan.generate(
            count, height_mm=height, base_mm=self._base_elevation(),
            mode=mode, template=self.TemplateInput.Text or "Level {n}",
            start_index=_as_int(self.StartInput.Text, None))
        self.refresh_grid()
        self.set_status("Added {0} level(s) — {1}.".format(added, note))

    def _on_respace(self, sender, args):
        height = _as_float(self.HeightInput.Text, planner.DEFAULT_STOREY_MM)
        if height <= 0:
            self.set_status("A storey height has to be more than zero.", True)
            return
        rows = self.plan.live_rows()
        index = self.BaseCombo.SelectedIndex
        base_row = rows[index - 1] if (index > 0 and index - 1 < len(rows)) else None
        self._checkpoint("re-space the stack at {0:.0f} mm".format(height))
        changed = self.plan.respace(height, base_row)
        if not changed:
            self.plan.drop_checkpoint()
        self.refresh_grid()
        if changed:
            self.set_status("Re-spaced {0} level(s) at {1:.0f} mm.".format(
                changed, height))
        else:
            self.set_status("The stack is already at that spacing.")

    # ── rename ────────────────────────────────────────────────────────
    def _on_rename_mode_changed(self, sender, args):
        enabled = bool(self.RenameTemplateToggle.IsChecked)
        self.RenameTemplateInput.IsEnabled = enabled
        self.RenameStartInput.IsEnabled = enabled
        for control in (self.PrefixInput, self.SuffixInput, self.FindInput,
                        self.ReplaceInput):
            control.IsEnabled = not enabled
        self._update_rename_preview()

    def _on_rename_input_changed(self, sender, args):
        self._update_rename_preview()

    def _on_apply_rename(self, sender, args):
        targets = self._rename_targets()
        if not targets:
            self.set_status("Tick the rows to rename first.", True)
            return
        self._checkpoint("rename {0} level(s)".format(len(targets)))
        changed, collisions = self.plan.batch_rename(
            targets,
            prefix=self.PrefixInput.Text, suffix=self.SuffixInput.Text,
            find=self.FindInput.Text, replace=self.ReplaceInput.Text,
            case_mode=CASE_CHOICES[max(0, self.CaseCombo.SelectedIndex)],
            template=self.RenameTemplateInput.Text,
            start_index=_as_int(self.RenameStartInput.Text, 1),
            use_template=bool(self.RenameTemplateToggle.IsChecked))
        if not changed:
            self.plan.drop_checkpoint()
        self.refresh_grid()
        if collisions:
            self.set_status(
                "Renamed {0}; skipped {1} that would have clashed ({2}).".format(
                    changed, len(collisions), collisions[0]), True)
        elif changed:
            self.set_status("Renamed {0} level(s) in the plan — "
                            "Apply changes writes them to the model.".format(changed))
        else:
            self.set_status("Nothing to change with that rule.")

    # ── undo / redo over the staged plan ──────────────────────────────
    def _checkpoint(self, label):
        """Take a history step before changing the plan."""
        self.plan.checkpoint(label)

    def _after_history_move(self, label, direction):
        self.plan.project_formatter = self._format_project
        self.refresh_grid()
        if label:
            self.set_status("{0}: {1}.".format(direction, label))
        else:
            self.set_status("Nothing to {0}.".format(direction.lower()))

    def _on_undo(self, sender, args):
        label = self.plan.undo()
        self._after_history_move(label, "Undone")

    def _on_redo(self, sender, args):
        label = self.plan.redo()
        self._after_history_move(label, "Redone")

    def _on_key_down(self, sender, args):
        """Ctrl+Z / Ctrl+Y — but not while a text box has the caret.

        Inside an input the user means the TextBox's own undo, and taking that
        away to rewind the whole plan would be a nasty surprise.
        """
        from System.Windows.Controls import TextBox
        from System.Windows.Input import Key, Keyboard, ModifierKeys
        if not bool(Keyboard.Modifiers & ModifierKeys.Control):
            return
        if isinstance(Keyboard.FocusedElement, TextBox):
            return
        if args.Key == Key.Z:
            self._on_undo(sender, args)
            args.Handled = True
        elif args.Key == Key.Y:
            self._on_redo(sender, args)
            args.Handled = True

    def _refresh_history_buttons(self):
        undo_label = self.plan.undo_label()
        redo_label = self.plan.redo_label()
        self.UndoBtn.IsEnabled = undo_label is not None
        self.RedoBtn.IsEnabled = redo_label is not None
        self.UndoBtn.ToolTip = (
            "Nothing staged to undo yet." if undo_label is None
            else "Undo: {0}. Ctrl+Z. Nothing has reached the model yet."
                 .format(undo_label))
        self.RedoBtn.ToolTip = (
            "Nothing to redo." if redo_label is None
            else "Redo: {0}. Ctrl+Y.".format(redo_label))

    # ── settings ──────────────────────────────────────────────────────
    def _collect_settings(self):
        """Every option on every tab, as plain data (§ no ids — see settings)."""
        return {
            "source_index": self.SourceCombo.SelectedIndex,
            "unit_index": self.UnitCombo.SelectedIndex,
            "datum_mm": self.DatumInput.Text,
            "tolerance_mm": self.ToleranceInput.Text,
            "layers": self.LayerInput.Text,
            "require_evidence": bool(self.EvidenceToggle.IsChecked),
            "cross_check_positions": bool(self.PositionToggle.IsChecked),
            "adopt_names": bool(self.AdoptToggle.IsChecked),
            "count": self.CountInput.Text,
            "storey_height_mm": self.HeightInput.Text,
            "naming_follow": bool(self.FollowRadio.IsChecked),
            "template": self.TemplateInput.Text,
            "start_index": self.StartInput.Text,
            "push_above": bool(self.PushAboveToggle.IsChecked),
            "snap_index": self.SnapCombo.SelectedIndex,
            "prefix": self.PrefixInput.Text,
            "suffix": self.SuffixInput.Text,
            "find": self.FindInput.Text,
            "replace": self.ReplaceInput.Text,
            "case_index": self.CaseCombo.SelectedIndex,
            "scope_selected": bool(self.ScopeSelectedRadio.IsChecked),
            "rename_use_template": bool(self.RenameTemplateToggle.IsChecked),
            "rename_template": self.RenameTemplateInput.Text,
            "rename_start": self.RenameStartInput.Text,
            "create_views": bool(self.CreateViewsToggle.IsChecked),
            "view_type_names": self._checked_view_type_names(),
            "view_template_name": (str(self.ViewTemplateCombo.SelectedItem)
                                   if self.ViewTemplateCombo.SelectedIndex > 0
                                   else ""),
        }

    def _apply_settings(self, data):
        """Push saved preferences into the controls. Model-specific lists —
        view types, view templates — are matched by name in _fill_view_lists."""
        def combo(control, index):
            if 0 <= index < control.Items.Count:
                control.SelectedIndex = index

        combo(self.UnitCombo, data.get("unit_index", 0))
        combo(self.CaseCombo, data.get("case_index", 0))
        combo(self.SnapCombo, data.get("snap_index", SNAP_DEFAULT_INDEX))
        self.DatumInput.Text = data.get("datum_mm", "0")
        self.ToleranceInput.Text = data.get("tolerance_mm", "25")
        self.LayerInput.Text = data.get("layers", "")
        self.EvidenceToggle.IsChecked = bool(data.get("require_evidence", True))
        self.PositionToggle.IsChecked = bool(
            data.get("cross_check_positions", True))
        self.AdoptToggle.IsChecked = bool(data.get("adopt_names", True))
        self.CountInput.Text = data.get("count", "4")
        self.HeightInput.Text = data.get("storey_height_mm", "3000")
        follow = bool(data.get("naming_follow", True))
        self.FollowRadio.IsChecked = follow
        self.TemplateRadio.IsChecked = not follow
        self.TemplateInput.Text = data.get("template", "Level {n}")
        self.StartInput.Text = data.get("start_index", "")
        self.PushAboveToggle.IsChecked = bool(data.get("push_above", False))
        self.PrefixInput.Text = data.get("prefix", "")
        self.SuffixInput.Text = data.get("suffix", "")
        self.FindInput.Text = data.get("find", "")
        self.ReplaceInput.Text = data.get("replace", "")
        selected_scope = bool(data.get("scope_selected", True))
        self.ScopeSelectedRadio.IsChecked = selected_scope
        self.ScopeAllRadio.IsChecked = not selected_scope
        self.RenameTemplateToggle.IsChecked = bool(
            data.get("rename_use_template", False))
        self.RenameTemplateInput.Text = data.get("rename_template",
                                                 "{nn} {ORDINAL} FLOOR")
        self.RenameStartInput.Text = data.get("rename_start", "1")
        self.CreateViewsToggle.IsChecked = bool(data.get("create_views", False))
        self._on_rename_mode_changed(None, None)

    def _checked_view_type_names(self):
        names = []
        for child in self.ViewTypeList.Children:
            try:
                if bool(child.IsChecked):
                    names.append(str(child.Content))
            except Exception:
                continue
        return names

    def _on_save_settings(self, sender, args):
        self.settings = self._collect_settings()
        ok, message = settings.save(self.settings)
        self.SettingsHint.Text = message
        self.set_status(message, not ok)

    def _on_forget_settings(self, sender, args):
        ok, message = settings.forget()
        if ok:
            self.settings = settings.defaults()
            self._apply_settings(self.settings)
            self._fill_view_lists()
        self.SettingsHint.Text = message
        self.set_status(message, not ok)

    # ── grid toolbar ──────────────────────────────────────────────────
    def _on_select_all(self, sender, args):
        self._refreshing = True
        try:
            self.LevelGrid.SelectAll()
        finally:
            self._refreshing = False
        self._sync_selection_flags()
        self.draw_stack()
        self.update_counts()
        self.update_previews()

    def _on_clear_selection(self, sender, args):
        self._refreshing = True
        try:
            self.LevelGrid.UnselectAll()
        finally:
            self._refreshing = False
        self._sync_selection_flags()
        self.draw_stack()
        self.update_counts()
        self.update_previews()

    def _on_select_in_revit(self, sender, args):
        ids = [row.IdInt for row in self.selected_rows() if row.IdInt is not None]
        if not ids:
            self.set_status("Tick some levels that already exist in the model.",
                            True)
            return
        self._enqueue("select", {"ids": ids}, self._on_selected)

    def _on_selected(self, result):
        self.set_status("Selected {0} level(s) in Revit.".format(
            result.get("selected", 0)))

    def _on_open_plan(self, sender, args):
        rows = [row for row in self.selected_rows() if row.IdInt is not None]
        if not rows:
            self.set_status("Tick one level that exists in the model.", True)
            return
        self._enqueue("open_plan", {"id": rows[0].IdInt}, self._on_plan_opened)

    def _on_plan_opened(self, result):
        self.set_status(result.get("message") or "Done.",
                        not result.get("ok", False))

    def _on_mark_delete(self, sender, args):
        rows = self.selected_rows()
        if not rows:
            self.set_status("Tick the levels to remove.", True)
            return
        hosted = sum(row.Elements for row in rows if not row.is_new)
        if hosted:
            answer = MessageBox.Show(
                "{0} element(s) are hosted on the level(s) you ticked.\n\n"
                "Deleting a level in Revit deletes what sits on it and the "
                "views that belong to it. Mark them for deletion anyway?"
                .format(hosted),
                "AnonGee · Auto Level Manager",
                MessageBoxButton.YesNo, MessageBoxImage.Warning)
            if answer != MessageBoxResult.Yes:
                self.set_status("Left alone.")
                return
        self._checkpoint("mark {0} level(s) for delete".format(len(rows)))
        count = self.plan.mark_delete(rows)
        self.refresh_grid()
        self.set_status("{0} level(s) marked — Apply changes carries it out."
                        .format(count))

    def _on_restore(self, sender, args):
        rows = [row for row in self.plan.rows
                if row.IsSelected and row.State == planner.STATE_DELETE]
        if not rows:
            self.set_status("Nothing ticked that is marked for deletion.")
            return
        self._checkpoint("restore {0} level(s)".format(len(rows)))
        self.plan.mark_delete(rows, deleted=False)
        self.refresh_grid()
        self.set_status("Restored {0} level(s).".format(len(rows)))

    def _on_reset(self, sender, args):
        counts = self.plan.summary()
        if not counts["changes"]:
            self.set_status("There is nothing pending to discard.")
            return
        answer = MessageBox.Show(
            "Discard {0} pending change(s) and go back to what the model "
            "actually has?".format(counts["changes"]),
            "AnonGee · Auto Level Manager",
            MessageBoxButton.YesNo, MessageBoxImage.Question)
        if answer != MessageBoxResult.Yes:
            return
        self._checkpoint("discard {0} change(s)".format(counts["changes"]))
        self.plan.remove_proposed()
        self.refresh_grid()
        self.DetectSummary.Text = "Plan reset to the model."
        self.set_status("Back to the model's own levels.")

    # ── apply ─────────────────────────────────────────────────────────
    def _checked_view_type_ids(self):
        ids = []
        for child in self.ViewTypeList.Children:
            try:
                if bool(child.IsChecked):
                    ids.append(child.Tag)
            except Exception:
                continue
        return ids

    def _selected_view_template_id(self):
        index = self.ViewTemplateCombo.SelectedIndex
        templates = self.snapshot.get("view_templates") or []
        if index > 0 and index - 1 < len(templates):
            return templates[index - 1]["id"]
        return None

    def _on_apply(self, sender, args):
        self.plan.refresh_display(self._format_project)
        if self.plan.has_blocking_issues():
            blocking = [message for severity, _row, message in self.plan.issues
                        if severity == "error"]
            self.set_status("Fix this first — {0}".format(blocking[0]), True)
            return

        counts = self.plan.summary()
        if not counts["changes"]:
            self.set_status("Nothing to apply.")
            return

        create_views = bool(self.CreateViewsToggle.IsChecked)
        view_type_ids = self._checked_view_type_ids() if create_views else []
        if create_views and not view_type_ids:
            self.set_status("Tick at least one view type, or turn plan views "
                            "off.", True)
            return

        lines = []
        for key, label in (("new", "create"), ("rename", "rename"),
                           ("move", "move"), ("edit", "rename and move"),
                           ("delete", "DELETE")):
            if counts.get(key):
                lines.append("  {0} level(s) to {1}".format(counts[key], label))
        if create_views:
            lines.append("  plan views for every new level "
                         "({0} type(s))".format(len(view_type_ids)))
        warnings = [message for severity, _row, message in self.plan.issues
                    if severity == "warn"]
        body = "Apply to the model?\n\n" + "\n".join(lines)
        if warnings:
            body += "\n\nWorth a look:\n  " + "\n  ".join(warnings[:4])
        body += "\n\nIt lands as one undo step."

        answer = MessageBox.Show(body, "AnonGee · Auto Level Manager",
                                 MessageBoxButton.OKCancel,
                                 MessageBoxImage.Question)
        if answer != MessageBoxResult.OK:
            self.set_status("Nothing applied.")
            return

        operations = self.plan.to_operations(
            create_views=create_views,
            view_type_ids=view_type_ids,
            view_template_id=self._selected_view_template_id())
        self.ApplyBtn.IsEnabled = False
        self.set_status("Writing to the model…")
        self._enqueue("apply", operations, self._on_applied)

    def _on_applied(self, result):
        report = result.get("report") or {}
        self._on_snapshot(result)          # rebuild from what the model now has
        self.plan.clear_history()          # those steps described the old model
        self.DetectSummary.Text = "Applied. Scan again to detect more levels."

        parts = []
        for key, label in (("created", "created"), ("renamed", "renamed"),
                           ("moved", "moved"), ("deleted", "deleted"),
                           ("views", "plan views")):
            if report.get(key):
                parts.append("{0} {1}".format(report[key], label))
        summary = ", ".join(parts) if parts else "no changes landed"

        errors = report.get("errors") or []
        warnings = report.get("warnings") or []
        if errors:
            self.set_status("{0}. {1} problem(s): {2}".format(
                summary, len(errors), errors[0]), True)
            MessageBox.Show("\n".join(errors[:8]),
                            "AnonGee · Auto Level Manager — problems",
                            MessageBoxButton.OK, MessageBoxImage.Warning)
        elif warnings:
            self.set_status("{0}. {1}".format(summary, warnings[0]))
        else:
            self.set_status("Done — {0}.".format(summary))

    def _on_refresh(self, sender, args):
        counts = self.plan.summary()
        if counts["changes"]:
            answer = MessageBox.Show(
                "Re-reading the model discards {0} pending change(s). "
                "Carry on?".format(counts["changes"]),
                "AnonGee · Auto Level Manager",
                MessageBoxButton.YesNo, MessageBoxImage.Question)
            if answer != MessageBoxResult.Yes:
                return
        self.set_status("Re-reading the model…")
        self._enqueue("snapshot", callback=self._on_snapshot)

    # ── lifecycle ─────────────────────────────────────────────────────
    def _on_close(self, sender, args):
        self.window.Close()

    def _on_closed(self, sender, args):
        if _state.window_ref is self:
            _state.window_ref = None

    def show(self):
        self.window.Show()
        # Anchor AFTER Show() so the window sits above Revit without blocking.
        helper = WindowInteropHelper(self.window)
        helper.Owner = __revit__.MainWindowHandle
        # First load goes through the dispatcher, or the handler's callbacks
        # marshal onto the wrong thread and the results never arrive (§12.8.7.4).
        self.window.Dispatcher.BeginInvoke(DispatcherPriority.Background,
                                           Action(self.initial_load))


# ── small helpers ──────────────────────────────────────────────────────────

def _as_int(text, default):
    try:
        return int(str(text).strip())
    except Exception:
        return default


def _as_float(text, default):
    value = textparse.parse_elevation_input(text, "mm")
    return default if value is None else value


# ── entry point ────────────────────────────────────────────────────────────

def run():
    # Re-opening while an instance is alive: activate instead of stacking.
    existing = _state.window_ref
    if existing is not None:
        try:
            if existing.window.IsVisible:
                existing.window.Activate()
                return
        except Exception:
            _state.window_ref = None

    xaml_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "ui.xaml")

    handler = AutoLevelHandler()
    handler.data = {}                  # per-instance state (no __init__)
    handler.preprocessor = WarningSwallower()
    ext_event = ExternalEvent.Create(handler)

    app = AutoLevelApp(xaml_path, handler, ext_event)
    handler.app = app
    _state.window_ref = app            # survives run() returning
    app.show()


def main():
    run()


if __name__ == "__main__":
    # Module-level guard: report a logic error cleanly instead of leaving the
    # persistent engine in a half-state (§12.9.4).
    try:
        main()
    except Exception as error:
        traceback.print_exc()
        try:
            TaskDialog.Show("AnonGee · Auto Level Manager",
                            "Failed to launch: {0}".format(error))
        except Exception:
            pass

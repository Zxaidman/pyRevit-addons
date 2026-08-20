#! python3
# -*- coding: utf-8 -*-
"""
AnonGee · RC Automation
-----------------------
Reads an Excel schedule, checks it, works out what each existing footing would
get, and — on Create — places the reinforcement.

Everything before Create is read-only, and deliberately so: a plan is worked out
and shown in full before a transaction exists, so what is about to happen can be
read and refused. Create then does exactly what the plan said and nothing else.

What guards the model:
  • Create is only reachable in "Reinforce existing structure". The other two
    modes create or reconcile structure, which this build does not do.
  • A plan runs first. Create is disabled until one exists and has something in
    it, and it re-plans on the Revit thread rather than trusting a stale one.
  • The whole run is one TransactionGroup, assimilated, so it is one undo step.
    Each chunk is its own Transaction, so a failure rolls back that chunk only.
  • A host that already carries reinforcement is left alone unless Replace is
    ticked, and even then only bars this tool stamped are removed.
  • Every bar is stamped, so a later run can tell its own work from a
    detailer's.

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

import io
import os
import sys
import types

import clr

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import BuiltInCategory                 # noqa: E402
from Autodesk.Revit.DB import BuiltInParameter                # noqa: E402
from Autodesk.Revit.DB import FilteredElementCollector        # noqa: E402
from Autodesk.Revit.DB import IFailuresPreprocessor           # noqa: E402
from Autodesk.Revit.DB import Level                           # noqa: E402
from Autodesk.Revit.DB import Transaction                     # noqa: E402
from Autodesk.Revit.DB import TransactionGroup                # noqa: E402
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
from System.Windows import MessageBoxButton                    # noqa: E402
from System.Windows import MessageBoxImage                     # noqa: E402
from System.Windows import MessageBoxResult                    # noqa: E402
from System.Windows.Interop import WindowInteropHelper        # noqa: E402
from System.Windows.Markup import XamlReader                  # noqa: E402
from System.Windows.Media import Color, SolidColorBrush       # noqa: E402
from System.Windows.Threading import DispatcherPriority       # noqa: E402

__version__ = "0.5.0"

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

#: Hosts written per Transaction. Revit's thread is blocked for the whole of
#: one, so this is the granularity at which a long run can be given up on and
#: the size of what a single failure rolls back.
CHUNK_SIZE = 25


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
from anongee_toolkit.rc_automation import naming               # noqa: E402
from anongee_toolkit.rc_automation import rebar_spec           # noqa: E402
from anongee_toolkit.rc_automation import validation           # noqa: E402
from anongee_toolkit.structural import rebar_hosts             # noqa: E402
from anongee_toolkit.structural import rebar_run               # noqa: E402
from anongee_toolkit.structural import footings as footing_api  # noqa: E402
from anongee_toolkit.structural import structure_run            # noqa: E402


# These name `models`, so they live below the import that provides it. Putting
# them up with the other constants is what broke the script on load — every
# test parses this file rather than running it, so a NameError at module scope
# sailed through all of them and only appeared as a traceback in Revit.
#: The modes that can actually write. One set rather than a comparison repeated
#: in five places: when Phase 1 shipped, four of those still read "anything but
#: reinforce-existing is unsupported", and the report went on denying a mode the
#: button beside it would have built.
BUILDABLE_MODES = (models.MODE_CREATE_ALL, models.MODE_REBAR_ONLY)


def can_build(mode):
    return mode in BUILDABLE_MODES


#: Said by the status bar, the report and the probe alike, so the three cannot
#: drift into telling the user different things.
_MODE_NOT_BUILT = (
    "'{0}' is not built yet — it resolves differences against a model rather "
    "than building anything, and acting on them is deliberately report-only. "
    "Use 'Create structure and reinforcement' or 'Reinforce existing "
    "structure' to build.")


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


if getattr(_state, "failures_cls", None) is None:
    class RebarWarningSwallower(IFailuresPreprocessor):
        """Absorb the warnings a batch of reinforcement generates.

        Placing several hundred bars raises a dialog per host otherwise, and a
        modeless tool that stops on each one is unusable. Only *warnings* are
        deleted; an error is left for Revit to roll the chunk back on, because
        suppressing those would let the run write something invalid and call it
        a success.

        Same three rules as the event handler: ``__namespace__``, no
        ``__init__``, and defined once per session (§12.9.4).
        """

        __namespace__ = "AnonGee"

        def PreprocessFailures(self, accessor):
            from Autodesk.Revit.DB import FailureProcessingResult
            from Autodesk.Revit.DB import FailureSeverity
            deleted = False
            for failure in accessor.GetFailureMessages():
                if failure.GetSeverity() == FailureSeverity.Warning:
                    accessor.DeleteWarning(failure)
                    deleted = True
            return (FailureProcessingResult.ProceedWithCommit if deleted
                    else FailureProcessingResult.Continue)

    _state.failures_cls = RebarWarningSwallower
else:
    RebarWarningSwallower = _state.failures_cls


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
                elif request == "plan":
                    self.data["result"] = self._plan(uiapp)
                elif request == "create":
                    self.data["result"] = self._create(uiapp)
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
            result["constraints"] = self._constraint_support(doc)
            return result

        def _constraint_support(self, doc):
            """What this Revit build offers for rebar constraints.

            Written blind: the shape of that API moves between releases, and a
            report from a real model is the only way to replace guessing with
            knowing. Reads one existing bar if there is one.
            """
            from anongee_toolkit.structural import rebar_constraints
            for element in (FilteredElementCollector(doc)
                            .OfCategory(BuiltInCategory.OST_Rebar)
                            .WhereElementIsNotElementType().ToElements()):
                return rebar_constraints.describe(element)
            return "no rebar in the model yet to read constraints from"

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

        # -- planning (reads only) ----------------------------------------
        def _plan(self, uiapp):
            """Work out what would be built. No writes, whichever mode."""
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                return {"error": "Open a Revit model first."}
            doc = uidoc.Document
            workbook = self.data.get("workbook")
            if workbook is None:
                return {"error": "Load a workbook first."}
            if self.data.get("mode") == models.MODE_CREATE_ALL:
                return self._plan_structure(doc, workbook)

            key_parameter = self.data.get("key_parameter") or \
                rebar_hosts.DEFAULT_KEY_PARAMETER
            replace = bool(self.data.get("replace"))
            plans = rebar_run.plan_footings(doc, workbook, key_parameter,
                                            replace)
            bar_type_ids, missing = rebar_run.resolve_bar_types(doc, workbook)

            # The plan is kept on the handler, on Revit's thread. Only the
            # description of it crosses back (§12.8.7.2).
            self.data["plans"] = plans
            self.data["bar_type_ids"] = bar_type_ids
            return {
                "request": "plan",
                "summary": rebar_run.summarise(plans),
                "rows": [_plan_row(plan) for plan in plans],
                "missing_bar_types": [
                    "{0:g} mm{1}".format(diameter or 0,
                                         " ({0})".format(name) if name else "")
                    for diameter, name in missing],
            }

        def _plan_structure(self, doc, workbook):
            """Phase 1: every pad the schedule places, resolved. No writes."""
            key_parameter = self.data.get("key_parameter") or \
                rebar_hosts.DEFAULT_KEY_PARAMETER
            plans, notes, blockers = structure_run.plan(
                doc, workbook, key_parameter)
            bar_type_ids, missing = rebar_run.resolve_bar_types(doc, workbook)

            self.data["footing_plans"] = plans
            self.data["bar_type_ids"] = bar_type_ids
            self.data["plans"] = []
            summary = structure_run.summarise(plans)
            summary["bars"] = 0
            summary["elements"] = 0
            for item in plans:
                if not item.will_create:
                    continue
                footing = workbook.footing_type(item.type_mark)
                rows = workbook.footing_rebar_for(item.type_mark)
                for layer in rebar_spec.plan_footing(footing, rows):
                    summary["bars"] += layer.count
                    summary["elements"] += layer.element_count

            return {
                "request": "plan",
                "structure": True,
                "summary": summary,
                "notes": notes,
                "blockers": blockers,
                "rows": [{
                    "key": item.mark,
                    "type_mark": item.type_mark,
                    "category": "Footing",
                    "status": item.status,
                    "reason": item.reason,
                    "bars": 0,
                    "elements": 0,
                    "level": item.level_name,
                } for item in plans],
                "missing_bar_types": [
                    "{0:g} mm{1}".format(diameter or 0,
                                         " ({0})".format(name) if name else "")
                    for diameter, name in missing],
            }

        # -- creation (the only thing here that writes) --------------------
        def _create(self, uiapp):
            """Build what the plan described, and nothing else."""
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                return {"error": "Open a Revit model first."}
            doc = uidoc.Document
            if self.data.get("mode") == models.MODE_CREATE_ALL:
                return self._create_structure(doc)
            workbook = self.data.get("workbook")
            plans = [p for p in (self.data.get("plans") or []) if p.will_create]
            bar_type_ids = self.data.get("bar_type_ids") or {}
            if not plans:
                return {"error": "Nothing to create — plan first."}
            if doc.IsReadOnly:
                return {"error": "The model is read-only."}

            view = doc.ActiveView
            replace = bool(self.data.get("replace"))
            created = 0
            bars = 0
            errors = []
            skipped = []
            done = 0

            group = TransactionGroup(doc, "AnonGee · RC Automation")
            group.Start()
            try:
                for start in range(0, len(plans), CHUNK_SIZE):
                    chunk = plans[start:start + CHUNK_SIZE]
                    transaction = Transaction(
                        doc, "Reinforce footings {0}-{1}".format(
                            start + 1, start + len(chunk)))
                    transaction.Start()
                    try:
                        options = transaction.GetFailureHandlingOptions()
                        options.SetFailuresPreprocessor(
                            RebarWarningSwallower())
                        transaction.SetFailureHandlingOptions(options)

                        for plan in chunk:
                            outcome = rebar_run.place_footing(
                                doc, plan, workbook, bar_type_ids, view,
                                replace)
                            created += outcome.elements
                            bars += outcome.bars
                            errors.extend(outcome.errors)
                            skipped.extend(outcome.skipped)
                            done += 1
                        transaction.Commit()
                    except Exception as chunk_error:
                        errors.append("chunk rolled back: {0}".format(
                            chunk_error))
                        if transaction.HasStarted() and not transaction.HasEnded():
                            transaction.RollBack()
                # Assimilate so the whole run is a single undo step rather than
                # one per chunk.
                group.Assimilate()
            except Exception as run_error:
                if group.HasStarted() and not group.HasEnded():
                    group.RollBack()
                return {"error": "The run was rolled back: {0}".format(
                    run_error)}

            self.data["plans"] = []
            return {
                "request": "create",
                "hosts": done,
                "elements": created,
                "bars": bars,
                "errors": errors,
                "skipped": skipped,
            }

        def _create_structure(self, doc):
            """Phase 1: build the pads, then reinforce the ones that took.

            Both halves live in one TransactionGroup, so a user who does not
            like the result reverses the footings and their reinforcement
            together rather than being left with bare pads.
            """
            workbook = self.data.get("workbook")
            plans = [p for p in (self.data.get("footing_plans") or [])
                     if p.will_create]
            bar_type_ids = self.data.get("bar_type_ids") or {}
            if not plans:
                return {"error": "Nothing to create — plan first."}
            if doc.IsReadOnly:
                return {"error": "The model is read-only."}

            base_type_id = footing_api.default_type_id(doc)
            if base_type_id is None:
                return {"error": "This project has no floor type to make a "
                                 "foundation from."}

            view = doc.ActiveView
            type_cache = {}
            cover_cache = {}
            made = []
            errors = []
            skipped = []
            notes = []

            group = TransactionGroup(doc, "AnonGee · RC Automation")
            group.Start()
            try:
                for start in range(0, len(plans), CHUNK_SIZE):
                    chunk = plans[start:start + CHUNK_SIZE]
                    transaction = Transaction(
                        doc, "Create footings {0}-{1}".format(
                            start + 1, start + len(chunk)))
                    transaction.Start()
                    try:
                        _swallow_warnings(transaction)
                        for item in chunk:
                            try:
                                element, item_notes = structure_run.create_one(
                                    doc, item, base_type_id, type_cache,
                                    cover_cache)
                                made.append((item, element.Id))
                                notes.extend(item_notes)
                            except Exception as pad_error:
                                errors.append("{0}: {1}".format(
                                    item.mark, pad_error))
                        transaction.Commit()
                    except Exception as chunk_error:
                        errors.append("chunk rolled back: {0}".format(
                            chunk_error))
                        if transaction.HasStarted() and not transaction.HasEnded():
                            transaction.RollBack()

                # The pads exist now, so they can host. Reinforcing them is the
                # same code Phase 2 runs, against elements a moment old.
                created_bars = 0
                created_elements = 0
                constrained = 0
                constraint_notes = []
                if made:
                    transaction = Transaction(doc, "Reinforce new footings")
                    transaction.Start()
                    try:
                        _swallow_warnings(transaction)
                        for item, element_id in made:
                            outcome = _reinforce_new(
                                doc, workbook, item, element_id, bar_type_ids,
                                view)
                            created_bars += outcome.bars
                            created_elements += outcome.elements
                            constrained += outcome.constrained
                            errors.extend(outcome.errors)
                            skipped.extend(outcome.skipped)
                            for note in outcome.constraint_notes:
                                if note not in constraint_notes:
                                    constraint_notes.append(note)
                        transaction.Commit()
                    except Exception as rebar_error:
                        errors.append("reinforcement rolled back: {0}".format(
                            rebar_error))
                        if transaction.HasStarted() and not transaction.HasEnded():
                            transaction.RollBack()
                group.Assimilate()
            except Exception as run_error:
                if group.HasStarted() and not group.HasEnded():
                    group.RollBack()
                return {"error": "The run was rolled back: {0}".format(
                    run_error)}

            self.data["footing_plans"] = []
            return {
                "request": "create",
                "structure": True,
                "footings": len(made),
                "hosts": len(made),
                "elements": created_elements,
                "bars": created_bars,
                "constrained": constrained,
                "constraint_notes": constraint_notes,
                "errors": errors,
                "skipped": skipped,
                "notes": notes,
            }

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


def _swallow_warnings(transaction):
    """Absorb the warning-per-element a batch raises, leaving errors alone."""
    options = transaction.GetFailureHandlingOptions()
    options.SetFailuresPreprocessor(RebarWarningSwallower())
    transaction.SetFailureHandlingOptions(options)


def _reinforce_new(doc, workbook, item, element_id, bar_type_ids, view):
    """Reinforce a pad this run just made, in the pad's own frame.

    The bars are planned from **the outline the pad was built from** and placed
    at **the point the pad was placed at**, turned by the same angle. Anything
    else and the two drift apart: planning from the type's rectangle and placing
    against the element's bounding-box centre put the bars 2.25 m outside the
    concrete on the one pad in the sample that is not a rectangle, because its
    outline runs from the placement point rather than around it.

    Only the height is measured off the element, because that is the one thing
    the frame does not give: the level, the offset and the type's thickness all
    feed it, and reading it back is cheaper than reproducing that sum.
    """
    from anongee_toolkit.structural import rebar_factory
    from anongee_toolkit.structural import rebar_geometry

    result = rebar_factory.PlacementResult()
    element = doc.GetElement(element_id)
    if element is None:
        result.errors.append("{0}: the pad vanished".format(item.mark))
        return result
    if not rebar_hosts.is_valid_host(element):
        result.skipped.append("{0}: {1}".format(
            item.mark, rebar_hosts.why_not_a_host(element)))
        return result

    footing = workbook.footing_type(item.type_mark)
    rows = workbook.footing_rebar_for(item.type_mark)
    if footing is None or not rows:
        result.skipped.append("{0}: nothing scheduled to reinforce it with"
                              .format(item.mark))
        return result

    bottom = rebar_hosts.bottom_elevation_mm(element)
    if bottom is None:
        result.errors.append("{0}: could not measure the new pad".format(
            item.mark))
        return result

    position = item.position_mm or (0.0, 0.0)
    origin = rebar_geometry.origin_xyz(position[0], position[1], bottom)
    rotation = item.rotation_deg or 0.0

    for layer in rebar_spec.plan_footing(footing, rows,
                                         outline=item.outline_mm):
        key = (layer.row.diameter_mm, (layer.row.bar_type or "").strip())
        bar_type_id = bar_type_ids.get(key)
        if bar_type_id is None:
            result.skipped.append("{0} {1}: no bar type for {2:g} mm".format(
                item.mark, layer.row.layer, layer.row.diameter_mm or 0))
            continue
        result.merge(rebar_factory.place_layer(
            doc, element, layer, bar_type_id, origin, rotation, view))
    return result


def _plan_row(plan):
    """One host plan as scalars. Revit objects never cross the bridge."""
    return {
        "key": plan.key,
        "type_mark": plan.type_mark,
        "category": plan.category,
        "status": plan.status,
        "reason": plan.reason,
        "bars": plan.bars,
        "elements": plan.elements,
        "level": plan.level,
    }


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
        self.plan = None
        self.created_anything = False
        self.last_result = None
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
        self.PlanBtn = self.window.FindName("PlanBtn")
        self.CreateBtn = self.window.FindName("CreateBtn")
        self.ReplaceCheck = self.window.FindName("ReplaceCheck")
        self.SidePanelTitle = self.window.FindName("SidePanelTitle")
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

        self.VersionText.Text = __version__
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
        self.PlanBtn.Click += self._on_plan
        self.CreateBtn.Click += self._on_create
        self.ModeCombo.SelectionChanged += self._on_mode_changed
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

        self.plan = None
        self._update_create_button()
        self._refresh_grid()
        self._describe_plan()

    def _on_mode_changed(self, sender, args):
        # A plan belongs to the mode it was made in; changing mode invalidates
        # it rather than leaving a Create button armed with the wrong answer.
        self.plan = None
        self._update_create_button()

    def _on_probe(self, sender, args):
        self._enqueue("probe")
        self.set_status("Reading the model on Revit's thread…")

    def _on_plan(self, sender, args):
        if not self._ready_to_plan():
            return
        self.handler.data["workbook"] = self.workbook
        self.handler.data["mode"] = self.selected_mode()
        self.handler.data["replace"] = bool(self.ReplaceCheck.IsChecked)
        self._enqueue("plan")
        self.set_status(
            "Working out what would be built…"
            if self.selected_mode() == models.MODE_CREATE_ALL
            else "Working out what each footing would get…")

    def _ready_to_plan(self):
        if self.workbook is None or self.workbook.is_empty():
            self.set_status("Load a workbook first.", True)
            return False
        if models.has_errors(self.issues):
            self.set_status(
                "The workbook has errors — fix those before planning.", True)
            return False
        mode = self.selected_mode()
        if mode == models.MODE_RECONCILE:
            self.set_status(_MODE_NOT_BUILT.format(models.MODE_LABELS[mode]),
                            True)
            return False
        return True

    def _on_create(self, sender, args):
        if self.plan is None or not self.plan.get("summary", {}).get("creating"):
            self.set_status("Plan first — there is nothing to create.", True)
            return
        if self.plan.get("missing_bar_types"):
            self.set_status(
                "These bar sizes have no RebarBarType in the model: {0}. Load "
                "them and plan again.".format(
                    ", ".join(self.plan["missing_bar_types"])), True)
            return

        summary = self.plan["summary"]
        if self.plan.get("structure"):
            question = ("Create {0} footing(s) and reinforce them?\n\n"
                        "{1} bar(s) as {2} Revit element(s).\n"
                        "A footing whose mark is already in the model is left "
                        "alone.".format(summary["creating"], summary["bars"],
                                        summary["elements"]))
        else:
            question = ("Place reinforcement into {0} footing(s)?\n\n"
                        "{1} bar(s) as {2} Revit element(s).\n{3}".format(
                            summary["creating"], summary["bars"],
                            summary["elements"],
                            "Bars this tool placed earlier will be replaced."
                            if self.ReplaceCheck.IsChecked
                            else "Footings that already carry reinforcement "
                                 "are left alone."))
        answer = MessageBox.Show(
            question + "\n\nThis lands as a single undo step.",
            "AnonGee · RC Automation",
            MessageBoxButton.OKCancel, MessageBoxImage.Question)
        if answer != MessageBoxResult.OK:
            self.set_status("Nothing was written.")
            return

        self.handler.data["replace"] = bool(self.ReplaceCheck.IsChecked)
        self.handler.data["mode"] = self.selected_mode()
        self._enqueue("create")
        self.set_status("Building — Revit is busy until it is done…")

    def _update_create_button(self):
        creating = 0
        if self.plan:
            creating = self.plan.get("summary", {}).get("creating", 0)
        blocked = bool(self.plan and (self.plan.get("missing_bar_types")
                                      or self.plan.get("blockers")))
        self.CreateBtn.IsEnabled = bool(creating) and not blocked

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
            # Explicit UTF-8: open() without one uses the platform encoding, and
            # on Windows that writes cp1252, which mangles every dash in the
            # report and makes the file undecodable by anything expecting UTF-8.
            handle = io.open(target, "w", encoding="utf-8")
            try:
                handle.write(self._report_text())
            finally:
                handle.close()
            self.set_status("Report written to {0}".format(target))
        except Exception as write_error:
            self.set_status("Could not write the report: {0}".format(
                write_error), True)

    def _on_clear(self, sender, args):
        self.workbook = None
        self.issues = []
        self.probe = None
        self.plan = None
        self.handler.data["plans"] = []
        self.FindingsGrid.ItemsSource = None
        self.SidePanelTitle.Text = "Model probe"
        self.ProbeText.Text = "Load a workbook, then Probe model."
        self._refresh_counts()
        self._update_create_button()
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
        elif result.get("request") == "plan":
            self._on_plan_done(result)
        elif result.get("request") == "create":
            self._on_create_done(result)
        else:
            self.probe = result
            self.SidePanelTitle.Text = "Model probe"
            self.ProbeText.Text = self._probe_text(result)
            self.set_status("Model read. Nothing was written.")
        self._update_create_button()
        self._pump()

    def _on_plan_done(self, result):
        self.plan = result
        summary = result["summary"]
        self._show_plan_rows(result["rows"])
        self.SidePanelTitle.Text = "Plan"
        self.ProbeText.Text = self._plan_text(result)

        if result.get("blockers"):
            # One of these stops everything, so it is said before the counts.
            self.set_status(result["blockers"][0], True)
        elif result["missing_bar_types"]:
            self.set_status(
                "{0} footing(s) ready, but these bar sizes are not loaded: "
                "{1}.".format(summary["creating"],
                              ", ".join(result["missing_bar_types"])), True)
        elif summary["creating"]:
            self.set_status(
                "{0} of {1} footing(s) would be {2} with {3} bar(s) as {4} "
                "element(s). Nothing written yet.".format(
                    summary["creating"],
                    summary.get("footings", summary.get("hosts", 0)),
                    "created and reinforced" if result.get("structure")
                    else "reinforced",
                    summary["bars"], summary["elements"]))
        else:
            self.set_status(
                "Nothing is ready to build — the panel says why for each.",
                True)

    def _on_create_done(self, result):
        self.plan = None
        self.created_anything = True
        # Kept so Export report carries what the panel said. Constraint
        # failures were being shown in the window and left out of the file,
        # which is the one place they would be read later.
        self.last_result = result
        parts = [
            "Created {0} footing(s) with {1} element(s) — {2} bar(s).".format(
                result["footings"], result["elements"], result["bars"])
            if result.get("structure") else
            "Placed {0} element(s) — {1} bar(s) — into {2} footing(s).".format(
                result["elements"], result["bars"], result["hosts"])]
        if result["skipped"]:
            parts.append("{0} skipped.".format(len(result["skipped"])))
        if result["errors"]:
            parts.append("{0} failed.".format(len(result["errors"])))
        self.set_status(" ".join(parts), bool(result["errors"]))

        self.SidePanelTitle.Text = "Result"
        self.ProbeText.Text = "\n".join(self._result_lines(result))

    def _result_lines(self, result):
        """What the run did, as the panel and the report both show it.

        One builder, because a failure the window mentions and the exported
        file leaves out is a failure nobody reads twice.
        """
        lines = [("Created {0} footing(s), and {1} set(s) — {2} bar(s) — "
                  "in them.".format(result.get("footings", 0),
                                    result.get("elements", 0),
                                    result.get("bars", 0))
                  if result.get("structure") else
                  "Placed {0} set(s) — {1} bar(s) — into {2} footing(s)."
                  .format(result.get("elements", 0), result.get("bars", 0),
                          result.get("hosts", 0))),
                 "", "One undo step — Ctrl+Z reverses the whole run.", ""]

        constrained = result.get("constrained")
        if constrained:
            lines.append("{0} bar handle(s) tied to the host's cover — editing "
                         "a footing updates its reinforcement.".format(
                             constrained))
            lines.append("")
        for label, entries in (
                ("Not constrained", result.get("constraint_notes") or []),
                ("Notes", result.get("notes") or []),
                ("Skipped", result.get("skipped") or []),
                ("Failed", result.get("errors") or [])):
            if not entries:
                continue
            lines.append("{0} ({1})".format(label, len(entries)))
            for entry in entries[:20]:
                lines.append("  " + str(entry))
            if len(entries) > 20:
                lines.append("  ... and {0} more".format(len(entries) - 20))
            lines.append("")
        if result.get("constraint_notes"):
            lines.append("The bars are placed correctly either way; what is "
                         "lost is the automatic updating.")
        return lines

    def _show_plan_rows(self, rows):
        """The plan in the grid, worst first — what needs attention is on top."""
        order = {"Invalid": 0, "Has rebar": 1, "Skip": 2, "Create": 3}
        items = ArrayList()
        for row in sorted(rows, key=lambda r: (order.get(r["status"], 9),
                                               r["key"])):
            message = row["reason"] or "{0} bar(s) as {1} element(s)".format(
                row["bars"], row["elements"])
            items.Add(FindingRow(row["status"], row["category"], None,
                                 row["type_mark"],
                                 "{0} — {1}".format(row["key"], message)))
        self.FindingsGrid.ItemsSource = None
        self.FindingsGrid.ItemsSource = items

    def _plan_text(self, result):
        summary = result["summary"]
        lines = []
        if result.get("blockers"):
            lines.append("Blocked")
            for entry in result["blockers"]:
                lines.append("  " + entry)
            lines.append("")
        lines.append("{0} footing(s) {1}".format(
            summary.get("footings", summary.get("hosts", 0)),
            "scheduled" if result.get("structure") else "matched"))
        lines.append("")
        for status in ("Create", "Exists", "Has rebar", "Skip", "Invalid"):
            count = summary["by_status"].get(status, 0)
            if count:
                lines.append("  {0:<10} {1}".format(status, count))
        lines.append("")
        lines.append("Would place {0} bar(s) as {1} Revit element(s).".format(
            summary["bars"], summary["elements"]))
        if result.get("notes"):
            lines.append("")
            lines.append("Resolved for you")
            for entry in result["notes"][:12]:
                lines.append("  " + entry)
        if result["missing_bar_types"]:
            lines.append("")
            lines.append("No RebarBarType loaded for:")
            for entry in result["missing_bar_types"]:
                lines.append("  " + entry)
            lines.append("")
            lines.append("Load these into the project and plan again.")
        lines.append("")
        lines.append("Nothing has been written.")
        return "\n".join(lines)

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
        mode = self.selected_mode()
        tail = ""
        if blocked:
            tail = "  Errors must be fixed before a run."
        elif not can_build(mode):
            tail = "  " + _MODE_NOT_BUILT.format(models.MODE_LABELS[mode])
        self.set_status(
            "{0} footing types, {1} column types. {2} footing bars would be "
            "placed as {3} element(s).{4}{5}".format(
                summary["footing_types"], summary["column_types"], bars,
                elements, note, tail),
            blocked or not can_build(mode))

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
        lines.extend(self._missing_level_lines(result.get("levels", [])))
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
        if result.get("constraints"):
            lines.append("")
            lines.append("Rebar constraints on this build")
            lines.append(result["constraints"])

        # The conclusion, spelled out. A reader should not have to infer "there
        # is nothing to reinforce" from a pair of zeroes.
        verdict = self._verdict(footings, columns, footing_hosts)
        if verdict:
            lines.append("")
            lines.append(verdict)
        return "\n".join(lines)

    def _verdict(self, footings, columns, footing_hosts):
        """What all of the above adds up to, in a sentence."""
        mode = self.selected_mode()
        if not footings and not columns:
            if mode == models.MODE_CREATE_ALL:
                return ("This model has no footings or columns yet — "
                        "which is what this mode is for. Plan, and it "
                        "will say what it would build.")
            if mode == models.MODE_REBAR_ONLY:
                return ("This model has no footings or columns, so there is "
                        "nothing to reinforce. Model the structure first, or "
                        "wait for the release that creates it from the "
                        "placement sheets.")
            return _MODE_NOT_BUILT.format(models.MODE_LABELS[mode])
        if not can_build(mode):
            return _MODE_NOT_BUILT.format(models.MODE_LABELS[mode])
        if footings and not footing_hosts:
            return ("None of the {0} foundation(s) can host reinforcement — a "
                    "floor has to be flagged structural before Revit will put "
                    "a bar in it.".format(footings))
        return ""

    def _missing_level_lines(self, model_levels):
        """Say which of the workbook's levels resolve, and which do not.

        Through the same matcher the run uses. A plain set difference reported
        "Foundation" as missing from a model containing "00 FOUNDATION LVL."
        — the run would have matched it and built the footing, and the probe
        beside it said it could not.
        """
        if self.workbook is None:
            return []
        wanted = set()
        for row in self.workbook.footing_placement:
            if row.level:
                wanted.add(row.level)
        for row in self.workbook.column_placement:
            for name in (row.base_level, row.top_level):
                if name:
                    wanted.add(name)
        if not wanted:
            return []

        resolved, notes, missing = naming.build_name_map(
            model_levels, wanted, self.workbook.level_map)
        lines = []
        if resolved:
            lines.append("")
            lines.append("Levels the workbook asks for")
            for name in sorted(resolved):
                lines.append("  {0} → {1}".format(name, resolved[name]))
        if notes:
            for note in notes:
                if "mapped to" in note or "does not have" in note:
                    lines.append("  " + note)
        if missing:
            lines.append("")
            lines.append("Could not be matched ({0})".format(len(missing)))
            for entry in missing:
                lines.append("  " + entry)
            lines.append("  (add a LEVELS sheet, or rename the level)")
        return lines

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
        mode = self.selected_mode()
        lines = ["AnonGee RC Automation {0}".format(__version__),
                 "Workbook: {0}".format(
                     (self.WorkbookPathText.Text or "").strip()),
                 "Mode: {0}".format(models.MODE_LABELS[mode]),
                 ""]
        if not can_build(mode):
            lines.append(_MODE_NOT_BUILT.format(models.MODE_LABELS[mode]))
            lines.append("")
        counts = models.count_by_severity(self.issues)
        lines.append("{0} errors, {1} warnings, {2} notes".format(
            counts[models.SEVERITY_ERROR], counts[models.SEVERITY_WARNING],
            counts[models.SEVERITY_INFO]))
        lines.append("")
        for issue in self.issues:
            lines.append("[{0}] {1}".format(issue.severity, issue))
        if self.last_result:
            lines.append("")
            lines.append("What the run did")
            for entry in self._result_lines(self.last_result):
                lines.append(entry)
        if self.probe:
            lines.append("")
            lines.append(self._probe_text(self.probe))
        lines.append("")
        lines.append("Nothing in the model was changed."
                     if not self.created_anything
                     else "Reinforcement was placed. Ctrl+Z reverses the run.")
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
    """Ask for a workbook with the .NET dialog — no pyRevit forms in CPython 3.

    Only files are offered here. A folder of tab-separated sheets is a valid
    input too, but ``OpenFileDialog`` cannot select one, so that path is typed
    into the box rather than browsed to.
    """
    try:
        clr.AddReference("Microsoft.Win32.Primitives")
    except Exception:
        pass
    try:
        from Microsoft.Win32 import OpenFileDialog
        dialog = OpenFileDialog()
        dialog.Title = "AnonGee · RC Automation — select a schedule"
        dialog.Filter = ("Excel workbook (*.xlsx;*.xlsm)|*.xlsx;*.xlsm"
                         "|All files (*.*)|*.*")
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

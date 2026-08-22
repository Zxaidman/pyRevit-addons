# -*- coding: utf-8 -*-
"""The bridge's front door: HTTP routes pyRevit serves from inside Revit.

pyRevit runs an HTTP server **in the Revit process**. A route handler that
declares ``uiapp``, ``uidoc`` or ``doc`` is executed by pyRevit as an External
Event — which is the marshalling problem the modeless window solves by hand,
solved by the framework instead. That is the whole reason this is the right
transport for an Excel button rather than merely a clever one.

    http://localhost:48884/anongee/ping      the server, no Revit involved
    http://localhost:48884/anongee/status    the model, through an External Event

**This file is the spike** (`CRIT-1` in the repository's ``todo-list.md``). It
answers four questions that every estimate in the PRD is conditional on, and it
writes nothing to any model:

1. Does the Routes server start, and is the port reachable from Excel?
2. Does a handler declaring ``uiapp`` really get marshalled onto Revit's thread?
3. **Which Python engine runs a startup script**, and can it see the toolkit?
   pyRevit's startup runs on the core engine, which is IronPython; the toolkit
   is CPython 3 and lives in ``lib/py3``. If routes cannot reach it, commands
   have to be dispatched to a CPython script rather than handled here, and that
   is a fork in the architecture worth knowing about before stage 1 rather than
   during it.
4. What happens with no document open, and with a modal dialog up.

``/ping`` deliberately takes **no** Revit argument and ``/status`` does. If
``/ping`` answers and ``/status`` hangs, the server is fine and the marshalling
is not — which is the difference between a spike that answers and one that just
fails.

**Nothing here may raise.** A startup script that throws takes pyRevit's load
with it, and a broken bridge must never cost the user their other tools.

Written for IronPython 2.7 as well as CPython 3: no f-strings, no ``pathlib``,
nothing newer than 2.7, because which one runs this is question 3.
"""

import os
import sys

__version__ = "0.1.0"

#: The API name, and therefore the first path segment: ``/anongee/...``.
#: The Excel macro in ``bridge/excel/`` names the same string, and a test holds
#: the two together — a URL that disagrees with its route costs an afternoon and
#: looks like a network problem the whole time.
API_NAME = "anongee"

#: What pyRevit's Routes server listens on by default. Recorded here for the
#: macro and the documentation to agree with; the server decides its own port
#: and ``/ping`` reports the truth rather than this.
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 48884


def _engine():
    """Which Python is running this, in as much detail as it will give.

    Question 3, and the single most valuable thing the spike returns: it decides
    whether a route handler can import the toolkit or has to hand off to a
    CPython script.
    """
    facts = {
        "version": sys.version.replace("\n", " "),
        "platform": sys.platform,
    }
    try:
        import platform
        facts["implementation"] = platform.python_implementation()
    except Exception:
        # IronPython's platform module has been known to be partial. The
        # version string above still names it.
        facts["implementation"] = "unknown"
    return facts


def _toolkit():
    """Whether this engine can see ``anongee_toolkit``, and where from.

    Reported rather than judged. ``lib/py3`` is added to the path for CPython
    engines only, so the honest answer here may well be "no" — which is a
    finding, not a fault.
    """
    found = {"importable": False, "path_entries": [], "error": ""}
    for entry in sys.path:
        try:
            if "lib" in entry and ("py3" in entry or "py2" in entry):
                found["path_entries"].append(entry)
        except Exception:
            continue
    try:
        import anongee_toolkit
        found["importable"] = True
        found["location"] = getattr(anongee_toolkit, "__file__", "")
    except Exception as error:
        found["error"] = "{0}".format(error)
    return found


def _extension_root():
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return ""


def register():
    """Register the routes. ``(api, note)`` — never raises.

    Separate from the module body so a test can call it and so the failure has
    somewhere to be reported rather than being swallowed at import.
    """
    try:
        from pyrevit import routes
    except Exception as error:
        return None, "pyrevit.routes is not available: {0}".format(error)

    try:
        api = routes.API(API_NAME)
    except Exception as error:
        return None, "could not create the {0} API: {1}".format(API_NAME, error)

    @api.route("/ping", methods=["GET"])
    def ping():
        """The server, with no Revit in the question.

        No ``uiapp`` argument on purpose: this answers whether the server is up
        and reachable **even when Revit is busy**, which is exactly when a user
        will first suspect the bridge is broken.
        """
        return {
            "ok": True,
            "api": API_NAME,
            "bridge": __version__,
            "engine": _engine(),
            "toolkit": _toolkit(),
            "extension": _extension_root(),
            "revit_context": False,
        }

    @api.route("/status", methods=["GET"])
    def status(uiapp):
        """The model, through Revit's own thread.

        Declaring ``uiapp`` is what asks pyRevit to run this as an External
        Event. Everything below touches the API and so could only ever run
        there — if this returns, the marshalling is real.

        ``uidoc`` is read defensively rather than declared, so that *no document
        open* comes back as an answer instead of an error. A bridge that cannot
        say "nothing is open" is a bridge that looks broken every morning.
        """
        answer = {
            "ok": True,
            "api": API_NAME,
            "bridge": __version__,
            "revit_context": True,
            "document": None,
        }
        try:
            answer["revit"] = "{0} {1}".format(
                uiapp.Application.VersionName, uiapp.Application.VersionBuild)
            answer["user"] = uiapp.Application.Username
        except Exception as error:
            answer["revit"] = "could not be read: {0}".format(error)

        try:
            uidoc = uiapp.ActiveUIDocument
        except Exception as error:
            answer["document_error"] = "{0}".format(error)
            return answer

        if uidoc is None:
            answer["note"] = "no document is open"
            return answer

        try:
            doc = uidoc.Document
            answer["document"] = {
                "title": doc.Title,
                "path": doc.PathName,
                "workshared": bool(doc.IsWorkshared),
                "read_only": bool(doc.IsReadOnly),
            }
        except Exception as error:
            answer["document_error"] = "{0}".format(error)
        return answer

    return api, ""


#: What happened when this module loaded. Read by the **Bridge Check**
#: pushbutton, because a startup script that fails silently is a startup script
#: nobody can debug from inside Revit.
REGISTRATION_NOTE = ""

try:
    _api, REGISTRATION_NOTE = register()
except Exception as _error:            # never take pyRevit's load down with us
    _api = None
    REGISTRATION_NOTE = "the bridge did not register: {0}".format(_error)

# -*- coding: utf-8 -*-
"""Ask the bridge whether it is there, from inside Revit.

The bridge's routes are served by pyRevit from **inside this Revit process**
(see ``AnonGee.extension/startup.py``). When a button in Excel gets no answer,
there are five reasons and they look identical from Excel: the Routes server is
off, the startup script did not register, Revit is busy, no document is open, or
something between the two is blocking a local port.

This tool calls the same two URLs Excel calls, from the machine Revit is on, and
shows exactly what comes back. It removes the network from the question, which
is the one thing Excel cannot do for itself.

Read-only. No transaction, no model change, nothing written anywhere.

    /anongee/ping      the server, with no Revit in the question
    /anongee/status    the model, through an External Event

**If ping answers and status does not**, the server is fine and the External
Event marshalling is not — which is the whole reason there are two routes rather
than one.
"""

__title__ = "Bridge\nCheck"
__author__ = "AnonGee"
__doc__ = """Ask the AnonGee Bridge whether it is running.

Calls the two routes pyRevit serves from inside this Revit session — the same
URLs an Excel button calls — and shows what comes back.

  ping    the Routes server, answered even while Revit is busy
  status  the open model, answered only once Revit is idle

If ping answers and status does not, the server is up and the External Event
marshalling is not. If neither answers, the Routes server is off: turn it on in
pyRevit Settings and restart Revit.

Read-only. Nothing is written to the model."""

__version__ = "0.1.0"

HOST = "localhost"
PORT = 48884
API = "anongee"

#: Long enough for a busy Revit, short enough that the dialog is not a hang.
TIMEOUT_SECONDS = 15


def url_for(route):
    """The same string the Excel macro builds, from the same three parts."""
    return "http://{0}:{1}/{2}/{3}".format(HOST, PORT, API, route)


def fetch(url):
    """``(body, error)``. Never raises.

    .NET first, deliberately. The CPython 3 engine ships a partial standard
    library — ``re`` and ``csv`` are both absent — so betting the diagnostic
    tool on ``urllib`` being complete is betting the one thing that has to work
    when nothing else does. ``System.Net`` is in the process already.
    """
    try:
        from System.Net import WebClient
        client = WebClient()
        return client.DownloadString(url), ""
    except Exception as dotnet_error:
        first = "{0}".format(dotnet_error)

    try:
        from urllib.request import urlopen
        response = urlopen(url, timeout=TIMEOUT_SECONDS)
        return response.read().decode("utf-8", "replace"), ""
    except Exception as urllib_error:
        return "", "{0} / {1}".format(first, urllib_error)


def describe(route):
    body, error = fetch(url_for(route))
    if error:
        return "{0}\n  no answer — {1}".format(url_for(route), error)
    return "{0}\n  {1}".format(url_for(route), body)


def main():
    lines = [describe("ping"), "", describe("status")]

    from Autodesk.Revit.UI import TaskDialog
    dialog = TaskDialog("AnonGee · Bridge Check")
    dialog.MainInstruction = "The bridge, as Excel would see it"
    dialog.MainContent = "\n".join(lines)
    dialog.ExpandedContent = (
        "Neither answered? The Routes server is off. Turn it on in pyRevit "
        "Settings and restart Revit.\n\n"
        "Ping answered and status did not? The server is up and the External "
        "Event marshalling is not — that is the finding CRIT-1 exists to "
        "produce, and it belongs in the report.")
    dialog.Show()


main()

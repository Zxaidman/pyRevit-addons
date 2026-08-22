# Bridge Check — changelog

## 0.1.0 — 2026-08-22

The diagnostic half of the bridge spike (`CRIT-1`).

- Calls `/anongee/ping` and `/anongee/status` — the same URLs an Excel button
  calls — from inside the Revit session, and shows what came back.
- **Two routes, on purpose.** `ping` takes no Revit argument and answers even
  while Revit is busy; `status` declares `uiapp` and so runs as an External
  Event. If ping answers and status does not, the server is up and the
  marshalling is not, which is a finding rather than a failure.
- Reaches the wire through `System.Net.WebClient` before `urllib`. The CPython 3
  engine ships a partial standard library — `re` and `csv` are both missing — so
  the tool that has to work when nothing else does should not bet on it.
- Read-only. No transaction, nothing written, no undo step.

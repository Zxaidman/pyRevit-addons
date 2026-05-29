#! python3
# -*- coding: utf-8 -*-
"""
BBS Generator — Bar Bending Schedule Generator
pyRevit CPython 3 push-button script.
"""

import sys
import os
import clr

# ── Native Revit TaskDialog for CPython alerts ────────────────────────────────
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.UI import TaskDialog

def show_alert(message, title="BBS Generator"):
    """Shows a Revit message box."""
    TaskDialog.Show(title, message)

def main():
    # ── Ensure all sub-packages are importable ────────────────────────────────
    _TOOL_ROOT = os.path.dirname(os.path.abspath(__file__))
    for _sub in ["core", "standards", "output", "ui", os.path.join("ui", "xaml")]:
        _p = os.path.join(_TOOL_ROOT, _sub)
        if _p not in sys.path:
            sys.path.insert(0, _p)

    # ── openpyxl: auto-discover from your local Python 3.12 install ───────────
    def _ensure_openpyxl():
        try:
            import openpyxl  # noqa
            return True
        except ImportError:
            pass

        import glob
        appdata = os.environ.get("APPDATA", "")
        localappdata = os.environ.get("LOCALAPPDATA", "")

        candidate_paths = []
        patterns = [
            os.path.join(appdata, "pyRevit*", "bin", "cengines", "CPY*", "Lib", "site-packages"),
            os.path.join(appdata, "pyRevit*", "bin", "cengines", "CPY*", "Lib"),
            os.path.join(localappdata, "Programs", "Python", "Python*", "Lib", "site-packages"),
            os.path.join(localappdata, "Programs", "Python", "Python*", "Lib")
        ]
        
        for pattern in patterns:
            candidate_paths.extend(glob.glob(pattern))

        pythonpath = os.environ.get("PYTHONPATH", "")
        candidate_paths.extend([p for p in pythonpath.split(os.pathsep) if p])

        for sp_path in candidate_paths:
            if not os.path.isdir(sp_path):
                continue
            if sp_path not in sys.path:
                sys.path.insert(0, sp_path)
            try:
                import openpyxl  # noqa
                return True
            except ImportError:
                continue

        return False

    if not _ensure_openpyxl():
        appdata     = os.environ.get("APPDATA", "")
        cpy_lib     = os.path.join(appdata, "pyRevit-Master", "bin", "cengines", "CPY3123", "Lib")
        sp_dir      = os.path.join(cpy_lib, "site-packages")
        system_pip  = "pip" 

        install_cmd = f'{system_pip} install openpyxl --target "{sp_dir}"'

        msg = (
            "BBS Generator requires openpyxl.\n\n"
            "We could not find it in your local Python or pyRevit engine.\n"
            "Step 1 — Create the folder if it does not exist:\n"
            f'    mkdir "{sp_dir}"\n\n'
            "Step 2 — Install openpyxl:\n"
            f"    {install_cmd}\n\n"
            "Step 3 — Restart Revit."
        )
        show_alert(msg, title="Install openpyxl")
        return # Replaces sys.exit() to avoid CPython tracebacks

    # ── Native Revit Document Access (Bypass pyrevit wrapper bug) ────────────
    try:
        # __revit__ is a global variable automatically injected by pyRevit
        uidoc = __revit__.ActiveUIDocument
        doc = uidoc.Document if uidoc else None
    except Exception as e:
        show_alert(f"Could not access Revit application natively.\n\n{e}", title="BBS Generator Error")
        return

    if doc is None:
        show_alert(
            "No active Revit document found.\n"
            "Please open a project before running BBS Generator.",
            title="BBS Generator Notice"
        )
        return

    # ── WinForms for dialogs ─────────────────────────────────────────────────
    clr.AddReference("System.Windows.Forms")
    import System.Windows.Forms  # noqa

    # ── Launch UI ────────────────────────────────────────────────────────────
    from main_window import run_ui
    run_ui(doc, uidoc)


if __name__ == "__main__":
    main()
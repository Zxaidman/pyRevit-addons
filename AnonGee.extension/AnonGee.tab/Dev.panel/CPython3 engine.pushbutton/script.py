#! python3
# -*- coding: utf-8 -*-
"""
CPython3 Engine Health Check
----------------------------
Reports whether the pyRevit CPython3 engine is alive, whether it is a FRESH
load or a REUSED instance (and how many times it has been run this session),
which third-party libs resolve, and whether the Revit API bridge responds.

A crashed engine cannot run this script at all — so if you see ANY output,
the engine is alive. The 'reuse count' tells you if stale state may have
accumulated across runs.
"""

import sys
import os


def main():
    # ── 1. Resolve lib paths (idempotent) ────────────────────────────────────
    try:
        import path_resolver
        path_resolver.update_paths()
        resolver_ok = True
    except Exception as e:
        resolver_ok = "FAILED: {}".format(e)

    # ── 2. Engine reuse detection ────────────────────────────────────────────
    # sys persists for the engine's lifetime, so an attribute stashed on it
    # survives across button clicks but resets when the engine restarts.
    run_count = getattr(sys, "_anongee_run_count", 0) + 1
    sys._anongee_run_count = run_count
    is_fresh = (run_count == 1)

    print("============================================================")
    print("CPYTHON3 ENGINE HEALTH CHECK")
    print("============================================================\n")

    print("ENGINE STATE")
    if is_fresh:
        print("   * FRESH engine — first run since (re)load. Clean state.")
    else:
        print("   * REUSED engine — run #{} this session.".format(run_count))
        print("     Stale globals / leaked event handlers may persist.")
        print("     Re-load the engine if a tool starts misbehaving.")
    print("   Python      : {}".format(sys.version.split()[0]))
    print("   Executable  : {}".format(getattr(sys, "executable", "n/a")))
    print("   path_resolver: {}".format(
        "OK" if resolver_ok is True else resolver_ok))
    print("")

    # ── 3. Module availability ───────────────────────────────────────────────
    print("DEPENDENCIES")
    modules_to_test = ["numpy", "openpyxl", "pythonnet", "clr", "ezdxf"]
    for mod_name in modules_to_test:
        try:
            module = __import__(mod_name)
            path = getattr(module, "__file__", None)
            version = getattr(module, "__version__", "?")
            if path is None and mod_name not in ("clr",):
                # A third-party package with no __file__ is a namespace/partial
                # install (e.g. ezdxf wiped by `git clean`) -- it imports but is
                # broken. clr legitimately has no __file__.
                print("   [WARN] {:<10} -> namespace/partial install (no __file__) "
                      "-- reinstall into lib/py3".format(mod_name))
            else:
                print("   [OK]   {:<10} v{:<8} -> {}".format(
                    mod_name, version, path or "Built-in / Embedded"))
        except ImportError as e:
            print("   [FAIL] {:<10} -> {}".format(mod_name, e))

    # ezdxf deep check: a namespace folder imports fine but has no submodules,
    # which is exactly what breaks CAD to BIM ("cannot import name 'recover'").
    try:
        import ezdxf as _ezdxf_probe
        from ezdxf import recover as _recover_probe  # noqa: F401
        print("   [OK]   ezdxf deep-check: recover import works (v{})".format(
            getattr(_ezdxf_probe, "__version__", "?")))
    except Exception as deep_error:
        print("   [FAIL] ezdxf deep-check: {} -- reinstall ezdxf into lib/py3 "
              "(tools/auto_provision.py)".format(deep_error))
    print("")

    # ── 4. Stdlib probe (this engine has a stripped stdlib path) ──────────────
    print("STDLIB PROBE")
    for mod_name in ["traceback", "tempfile", "csv", "re", "zipfile", "json"]:
        try:
            __import__(mod_name)
            print("   [OK]   {}".format(mod_name))
        except ImportError:
            print("   [MISS] {}  (use an inline fallback if a tool needs it)".format(mod_name))
    print("")

    # ── 5. Live Revit API bridge probe ───────────────────────────────────────
    # If the .NET marshaling layer were damaged, this would throw or crash.
    print("REVIT API BRIDGE")
    try:
        import clr
        clr.AddReference("RevitAPI")
        from Autodesk.Revit.DB import FilteredElementCollector, ViewSchedule
        import System

        doc = __revit__.ActiveUIDocument.Document
        n = FilteredElementCollector(doc).OfClass(ViewSchedule).GetElementCount()
        print("   [OK]   Bridge responsive — {} schedule(s) in '{}'".format(
            n, doc.Title))
    except System.Exception as net_err:          # .NET-side failure
        print("   [FAIL] .NET exception: {}".format(net_err))
    except Exception as py_err:                   # Python-side failure
        print("   [FAIL] Python exception: {}".format(py_err))
    print("")

    print("============================================================")
    print("ENGINE IS ALIVE  (you are seeing this output)")
    print("============================================================")


if __name__ == "__main__":
    # Full guard: a logic error here reports cleanly instead of risking
    # the engine. (Native faults still cannot be caught — by design.)
    try:
        main()
    except Exception as e:
        print("HEALTH CHECK ERROR: {}".format(e))

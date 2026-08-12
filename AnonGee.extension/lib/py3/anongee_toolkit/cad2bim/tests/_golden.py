# -*- coding: utf-8 -*-
"""Stored-baseline comparison for the regression legs.

The unit suite proves the pieces. It does not prove that a change to a geometry
pass left the WHOLE corpus alone -- for that you need the numbers a real drawing
produces, recorded, and re-checked after every edit. Three harnesses did that
job before v0.68 and all three were lost, because they were written into a
scratchpad instead of the repo. This module is the shared half of their
replacement, so the next one is a corpus and a fingerprint function, not another
bespoke script.

Shape: a baseline is {fixture: {metric: value}}. `differences()` says exactly
what moved, one line per number, so a diff can be read and judged rather than
stared at. Nothing here decides whether a difference is ALLOWED -- a change is
often intended. It only refuses to let one pass unnoticed.

Re-blessing is deliberate and explicit: set CAD2BIM_BLESS=1 to write the current
numbers over the stored ones. It is off by default because a harness that
silently updates its own baseline measures nothing at all.

Revit-free, and it is the one part of the regression machinery with logic in it,
so it carries its own unit tests (test_golden.py).
"""

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE_DIR = os.path.join(_HERE, "baselines")

# JSON has one number type; a count round-trips exactly, a rounded area may come
# back as 9.0 where 9 went in. Compare numbers as numbers.
_EPSILON = 1e-9


def baseline_path(name):
    """Where the baseline called `name` is stored."""
    return os.path.join(BASELINE_DIR, "{0}.json".format(name))


def load(path):
    """The stored baseline, or None when there is not one yet.

    A missing baseline is not an error: the first run of a new leg writes one.
    """
    if not os.path.exists(path):
        return None
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def save(path, data):
    """Write a baseline that reads well and diffs cleanly.

    Sorted keys and a trailing newline: a baseline is reviewed in a pull request
    like any other file, and a re-ordered dump would bury the one number that
    actually moved under three hundred that did not.
    """
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))


def blessing():
    """True when this run is meant to REPLACE the baselines (CAD2BIM_BLESS=1)."""
    return str(os.environ.get("CAD2BIM_BLESS", "")).strip().lower() in (
        "1", "true", "yes", "on")


def differences(baseline, current):
    """Every number that moved, one readable line each, in a stable order.

    Fixtures and metrics that appeared or vanished count as differences too: a
    fixture silently dropping out of a sweep is exactly the kind of "no
    regressions" that is really "nothing was measured".
    """
    lines = []
    for fixture in sorted(set(baseline or {}) | set(current or {})):
        was = (baseline or {}).get(fixture)
        now = (current or {}).get(fixture)
        if was is None:
            lines.append("{0}: not in the baseline (new fixture)".format(fixture))
            continue
        if now is None:
            lines.append("{0}: in the baseline but not measured".format(fixture))
            continue
        lines.extend(_metric_differences(fixture, was, now))
    return lines


def _metric_differences(fixture, was, now):
    lines = []
    for metric in sorted(set(was) | set(now)):
        if metric not in was:
            lines.append("{0}.{1}: not in the baseline (now {2})".format(
                fixture, metric, now[metric]))
        elif metric not in now:
            lines.append("{0}.{1}: no longer measured (was {2})".format(
                fixture, metric, was[metric]))
        elif not _same(was[metric], now[metric]):
            lines.append("{0}.{1}: {2} -> {3}".format(
                fixture, metric, was[metric], now[metric]))
    return lines


def _same(was, now):
    """Equality that does not trip over JSON's single number type."""
    if isinstance(was, bool) or isinstance(now, bool):
        return was == now
    if isinstance(was, (int, float)) and isinstance(now, (int, float)):
        return abs(float(was) - float(now)) <= _EPSILON
    if isinstance(was, (list, tuple)) and isinstance(now, (list, tuple)):
        return (len(was) == len(now)
                and all(_same(a, b) for a, b in zip(was, now)))
    return was == now

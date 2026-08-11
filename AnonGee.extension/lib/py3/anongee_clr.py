# -*- coding: utf-8 -*-
"""One home for the CLR types this toolkit derives from .NET interfaces.

Python.NET does not merely subclass a .NET interface: it EMITS a real CLR type
into a dynamic assembly, named by the class and its `__namespace__`. An
AppDomain refuses a second type with the same full name --

    Duplicate type name within an assembly

-- and a Revit session is one AppDomain that outlives every button click. So a
class body like `class WarningSwallower(IFailuresPreprocessor)` may execute at
most ONCE per session, however many times its module is imported.

That collides with how the buttons load their library: each run drops
`anongee_toolkit` from `sys.modules` so the files on disk are what runs (without
that, a release adding a function is invisible until Revit restarts). The module
body therefore executes again on every click -- and the second click crashed.

This module is the way out. It lives OUTSIDE `anongee_toolkit`, so the reload
never touches it, and it hands back the type it built the first time:

    WarningSwallower = anongee_clr.get_or_create(
        "WarningSwallower", _build_warning_swallower)

The factory runs at most once per session; every later import gets the same
type object, which is also what Revit wants -- one type, one handler identity.

Pure Python, no Revit imports of its own, so it can be unit-tested outside
Revit. Keep it dependency-free and boring: everything else depends on it.
"""

_TYPES = {}


def get_or_create(name, factory):
    """The CLR type registered as `name`, building it once via `factory`.

    `factory` is called only on the first miss, so the class body -- and the
    CLR type emission inside it -- happens exactly once per session. A factory
    that raises is not remembered: the next call tries again rather than
    caching a broken half-state.
    """
    existing = _TYPES.get(name)
    if existing is not None:
        return existing
    created = factory()
    if created is None:
        raise ValueError("factory for {0!r} produced nothing".format(name))
    _TYPES[name] = created
    return created


def registered():
    """The names built so far, sorted -- for diagnostics and the tests."""
    return sorted(_TYPES)


def forget(name=None):
    """Drop one entry, or all of them. For tests only.

    Never call this from a button: forgetting a type does not unload it from
    the AppDomain, so the next factory run would hit the very duplicate-name
    error this module exists to prevent.
    """
    if name is None:
        _TYPES.clear()
    else:
        _TYPES.pop(name, None)

# -*- coding: utf-8 -*-
"""netclass - define .NET-derived Python classes exactly once per session.

The problem
-----------
Under pythonnet (pyRevit's CPython engine), a Python class that subclasses a
.NET class or implements a .NET interface is not just a Python object. pythonnet
emits a **real .NET type** for it at runtime with Reflection.Emit, into a single
dynamic assembly shared by the whole process. The emitted type's name comes from
the Python class name, plus ``__namespace__`` if you set one.

pyRevit keeps one Python runtime alive for the entire Revit session and
re-executes your script module on every button click. So a module-level::

    class MySelFilter(ISelectionFilter):
        __namespace__ = "MyExt"
        ...

emits ``MyExt.MySelFilter`` on the first click, and on the second click tries to
emit it again into the same assembly. .NET refuses::

    Duplicate type name within an assembly.

First run works, every run after it fails until Revit restarts. Which is exactly
what it looks like.

This does **not** happen on IronPython, which is why the pattern is everywhere in
older pyRevit scripts and why porting them to CPython surfaces it.

The fix
-------
Emit the type on the first run and reuse it afterwards::

    from netclass import define

    @define("MyExt.MySelFilter")
    def MySelFilter():
        class MySelFilter(ISelectionFilter):
            __namespace__ = "MyExt"

            def AllowElement(self, element):
                return element.Category.Name == "Walls"

            def AllowReference(self, reference, position):
                return False
        return MySelFilter

    # MySelFilter is now the class itself, ready to instantiate
    uidoc.Selection.PickObjects(ObjectType.Element, MySelFilter())

The decorator has to wrap a *factory function* rather than the class directly:
by the time a class decorator runs, the class body has already executed and the
.NET type has already been emitted, which is the very thing being avoided.

The registry lives in ``sys.modules`` under a fixed key rather than in this
module's globals, so it survives this module being reloaded or a second copy of
it being imported from another extension's lib folder. Both would otherwise
reset a module-level dict and let the collision back in.

Affects any .NET interface you implement: ``ISelectionFilter``,
``IFailuresPreprocessor``, ``IExternalEventHandler``, ``IUpdater``,
``IDockablePaneProvider``, ``IExportContext``, and so on.

Install: drop in your extension's ``lib`` folder next to cpyforms.py.

Author  : AnonGee
Version : 1.0.0
Engines : CPython 3 (where it is required), IronPython 2.7 (harmless no-op)
"""

import sys
import types

__version__ = "1.0.0"
__all__ = ["once", "define", "keys", "is_defined"]

#: Versioned so a future incompatible change can use a fresh registry without
#: colliding with types emitted by the old one.
_REGISTRY_KEY = "_netclass_registry_v1"


def _registry():
    holder = sys.modules.get(_REGISTRY_KEY)
    if holder is None or not hasattr(holder, "classes"):
        holder = types.ModuleType(_REGISTRY_KEY)
        holder.classes = {}
        sys.modules[_REGISTRY_KEY] = holder
    return holder.classes


def once(key, factory):
    """Return the .NET-derived class registered under ``key``.

    ``factory`` is called only the first time, and must return the class.

    ``key`` should match the emitted type name (``__namespace__`` + class name)
    so two extensions defining a class of the same name don't share an entry.
    """
    reg = _registry()
    cls = reg.get(key)
    if cls is None:
        cls = factory()
        reg[key] = cls
    return cls


def define(key):
    """Decorator form of :func:`once`, applied to a zero-argument factory."""
    def decorator(factory):
        return once(key, factory)
    return decorator


def is_defined(key):
    return key in _registry()


def keys():
    """Every key emitted so far this session. Debugging aid."""
    return sorted(_registry().keys())


# There is deliberately no clear()/reset(). A .NET type cannot be un-emitted
# from a dynamic assembly, so dropping an entry from the registry would only
# make the next run collide again - the exact failure this module exists to
# prevent. If you change the body of a .NET-derived class you have to restart
# Revit for it to take effect.

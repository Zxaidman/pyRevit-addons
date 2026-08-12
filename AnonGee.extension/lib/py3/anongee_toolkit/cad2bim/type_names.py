# -*- coding: utf-8 -*-
"""Match a type name the way REVIT matches it, not the way Python does.

Every builder that duplicates a type asks the same question first: "is there a
type of this name already?". Asking it with a plain `==` is stricter than the
rule Revit enforces -- Revit calls two type names the same when they differ only
in case, or in surrounding/repeated whitespace.

That gap is not cosmetic. A column family carrying Revit's own "400 x 600" was
asked for the toolkit's default "400 X 600"; `==` reported no such type, the
builder called Duplicate, and Revit answered

    The name is already in use for this element type.
    Parameter name: name

...losing every column of that size. The same shape sat unguarded in the beam
and slab builders, and swallowed (so the wrong geometry was built in silence) in
the footing and stair ones.

`key()` is the whole fix: normalise before comparing, and a name Revit already
holds becomes a REUSE instead of a failed duplication. `resolve_type()` wraps the
duplication itself, so a clash the pre-check could not see still returns a usable
type, and a clash that cannot be resolved returns a sentence the console can
print instead of a .NET stack trace.

Revit-free, so all of it is unit-testable outside Revit.
"""


def key(name):
    """A type name reduced to what Revit compares: case-folded, trimmed, and
    with runs of inner whitespace collapsed to one space.

    "  400  x 600 " and "400 X 600" are ONE name to Revit, and now to us.
    """
    return " ".join((name or "").split()).lower()


def find(pairs, wanted):
    """The object from `pairs` whose name Revit would call `wanted`, or None.

    `pairs` is an iterable of (name, object) -- whatever the caller's scope is:
    a family's symbols, the floor types of one system family, a collector.
    A candidate with no readable name never matches, so an element whose name
    could not be resolved cannot be handed back in place of a real one.
    """
    target = key(wanted)
    if not target:
        return None
    for name, obj in pairs:
        if name is not None and key(name) == target:
            return obj
    return None


def resolve_type(base, wanted, scan, rescan=None):
    """A type named `wanted`: the existing one when there is one, else a
    duplicate of `base`. Returns (type, created, note).

    `scan` returns the (name, object) pairs to search -- it is a callable, not a
    list, because it has to be re-read AFTER a failed duplication. `rescan`
    widens that search for the second look, for the callers whose first scope is
    narrower than Revit's uniqueness rule.

    `created` is True only for a type THIS call made. It is the caller's licence
    to write dimensions: a type that was already in the model belongs to the
    model, and resizing someone's "400 x 600" under them would be a far worse
    bug than the one this module exists to fix.

    `note` is None when nothing needs saying, and a plain sentence when the name
    had to be reused unexpectedly or could not be created at all. A caller that
    gets (None, ...) must skip that element and report the note -- never place it
    against the base type, which is how a footing used to end up cast at the
    wrong depth without a word.
    """
    found = find(scan(), wanted)
    if found is not None:
        return found, False, None
    try:
        return base.Duplicate(wanted), True, None
    except Exception as clash:
        found = find((rescan or scan)(), wanted)
        if found is not None:
            return found, False, ("type name '{0}' already existed -- reused it"
                                  .format(wanted))
        return None, False, ("type name '{0}' is already taken by a type that "
                             "cannot be reused ({1})"
                             .format(wanted, _first_line(clash)))


def record(result, note):
    """Put a resolve note on a builder's result dict, at most once.

    One type serves every member of its size, so a note belongs to the TYPE, not
    to each of the ninety columns that share it.
    """
    if not note:
        return
    notes = result.setdefault("notes", [])
    if note not in notes:
        notes.append(note)


def _first_line(error):
    """The decisive line of a Revit exception, without the .NET stack trace."""
    text = str(error).replace("\r", "\n").strip()
    return text.split("\n")[0].strip() if text else error.__class__.__name__

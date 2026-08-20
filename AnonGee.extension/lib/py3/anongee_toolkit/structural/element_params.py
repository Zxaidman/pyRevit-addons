# -*- coding: utf-8 -*-
"""Write the project's own identity parameters onto what this tool builds.

A footing that carries no ``ID``, no ``LEVEL_V`` and no ``ITEM`` is a footing
that falls out of every schedule the project already has. The geometry being
right is not the deliverable; appearing correctly in the drawings and the
quantities is, and on a real project that is a handful of **shared parameters**
whose names the office fixed years ago.

Three things make this awkward enough to deserve its own module:

**A shared parameter is a document-level binding, not a value.** ``ID`` cannot
be written onto a footing at all unless somebody has bound a definition of that
name to Structural Foundations. So the question "can this be filled in?" has to
be asked of the *document* before a run, not discovered per element in the
middle of one.

**The project may not have them, and inventing them is a decision.** Creating a
shared parameter puts a definition in a file and a binding in someone's model,
which is exactly the kind of thing a tool should not do behind a user's back.
:data:`MODES` is that choice, and the default is the conservative one.

**The API for creating them moved.** ``ParameterType.Text`` became
``SpecTypeId.String.Text`` and ``BuiltInParameterGroup`` became
``GroupTypeId``; both spellings are tried, newest first, so this works either
side of the change.

Nothing here opens a transaction. :func:`ensure` and :func:`write` both need one
the caller owns, for the same reason the rest of the creation layer does.
"""

import os

from Autodesk.Revit.DB import BuiltInCategory
from Autodesk.Revit.DB import ExternalDefinitionCreationOptions

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# What gets written
# ---------------------------------------------------------------------------
#: On the footing itself.
HOST_PARAMETERS = ("ID", "ID_LIC", "ID_V", "ITEM", "LEVEL_V")

#: On every bar. The last two say what the bar belongs to, which a rebar
#: schedule cannot otherwise show without a shared-parameter round trip.
REBAR_PARAMETERS = ("ID", "ID_LIC", "ID_V", "ITEM", "LEVEL_V",
                    "Host Category", "Host Mark")

#: All of them, once. What :func:`ensure` binds and what the probe checks.
ALL_PARAMETERS = tuple(HOST_PARAMETERS) + tuple(
    name for name in REBAR_PARAMETERS if name not in HOST_PARAMETERS)

#: Which categories each name has to reach. Both, for the shared ones — one
#: definition bound to two categories, which is how a project would do it by
#: hand rather than two parameters that happen to share a name.
CATEGORIES = (BuiltInCategory.OST_StructuralFoundation,
              BuiltInCategory.OST_Rebar)

#: The group the created definitions land in, in the shared parameter file.
GROUP_NAME = "AnonGee RC Automation"

#: Where definitions are written when the project has no shared parameter file
#: of its own. Beside the model, so it travels with the job rather than
#: living in one machine's temp folder.
FILE_NAME = "AnonGee_Shared_Parameters.txt"

# ---------------------------------------------------------------------------
# What the user chose
# ---------------------------------------------------------------------------
#: Fill the ones the project already has and say nothing about the rest.
MODE_FILL = "Fill where present"
#: Create the missing definitions, bind them, then fill everything.
MODE_CREATE = "Create missing, then fill"
#: Touch none of them.
MODE_SKIP = "Skip"

MODES = (MODE_FILL, MODE_CREATE, MODE_SKIP)


# ---------------------------------------------------------------------------
# Asking the document
# ---------------------------------------------------------------------------

def _category_ids(doc, categories=CATEGORIES):
    """The ids of *categories* in this document, as a set. Empty if unknown."""
    ids = set()
    for builtin in categories:
        try:
            category = doc.Settings.Categories.get_Item(builtin)
        except Exception:
            category = None
        if category is None:
            continue
        value = _id_value(category.Id)
        if value is not None:
            ids.add(value)
    return ids


def _id_value(element_id):
    """An ``ElementId`` as a plain number. ``Value`` from 2024, else the old one."""
    for attribute in ("Value", "IntegerValue"):
        try:
            value = getattr(element_id, attribute)
        except Exception:
            continue
        if value is not None:
            return int(value)
    return None


def bound_names(doc, names=ALL_PARAMETERS, categories=CATEGORIES):
    """Which of *names* this document can store **on these categories**.

    ``(present, missing)``. Read-only, and the answer the probe shows before
    anything is built.

    Bound is not the same as bound *here*: a project whose ``ID`` reaches only
    Walls has the parameter and still cannot put it on a footing, and calling
    that present would mean writing nothing and saying nothing. Where the
    categories on a binding cannot be read, the name alone decides -- a
    conservative answer beats an exception in a probe.
    """
    present = []
    missing = []
    try:
        bindings = doc.ParameterBindings
    except Exception:
        return present, list(names)

    wanted = _category_ids(doc, categories)
    known = {}
    try:
        iterator = bindings.ForwardIterator()
        iterator.Reset()
        while iterator.MoveNext():
            definition = iterator.Key
            if definition is None:
                continue
            known[definition.Name] = _bound_category_ids(iterator.Current)
    except Exception:
        pass

    for name in names:
        if name not in known:
            missing.append(name)
            continue
        reached = known[name]
        if reached is None or not wanted or wanted.issubset(reached):
            present.append(name)
        else:
            missing.append(name)
    return present, missing


def _bound_category_ids(binding):
    """Which categories a binding reaches, or ``None`` if it will not say."""
    try:
        found = set()
        for category in binding.Categories:
            value = _id_value(category.Id)
            if value is not None:
                found.add(value)
        return found
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Creating them
# ---------------------------------------------------------------------------

def _shared_parameter_file(app, doc):
    """The application's shared parameter file, creating one if there is none.

    Revit hands back ``None`` both when no file is set and when the file that
    is set has no header, so a file this makes is written with the header
    already in it rather than left empty and hoped over.
    """
    try:
        existing = app.OpenSharedParameterFile()
        if existing is not None:
            return existing, ""
    except Exception:
        pass

    path = _file_path(doc)
    if path is None:
        return None, "there is nowhere to write a shared parameter file"
    if not os.path.exists(path):
        try:
            handle = open(path, "w")
            try:
                handle.write(_HEADER)
            finally:
                handle.close()
        except Exception as error:
            return None, "could not write {0}: {1}".format(path, error)
    try:
        app.SharedParametersFilename = path
        return app.OpenSharedParameterFile(), "using {0}".format(path)
    except Exception as error:
        return None, "could not open {0}: {1}".format(path, error)


#: The header Revit expects. Tab separated, and the tabs are load-bearing: a
#: file without it opens as ``None`` and every definition then fails to create
#: with nothing said about why.
_HEADER = (
    "# This is a Revit shared parameter file.\n"
    "# Do not edit manually.\n"
    "*META\tVERSION\tMINVERSION\n"
    "META\t2\t1\n"
    "*GROUP\tID\tNAME\n"
    "*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\t"
    "DESCRIPTION\tUSERMODIFIABLE\n")


def _file_path(doc):
    """Beside the model if it has been saved, else the user's temp folder."""
    try:
        model = doc.PathName
    except Exception:
        model = ""
    if model:
        folder = os.path.dirname(model)
        if folder and os.path.isdir(folder):
            return os.path.join(folder, FILE_NAME)
    for variable in ("TEMP", "TMP", "USERPROFILE", "HOME"):
        folder = os.environ.get(variable)
        if folder and os.path.isdir(folder):
            return os.path.join(folder, FILE_NAME)
    return None


def _group(definition_file, name=GROUP_NAME):
    """The named group in the file, made if it is not there."""
    for group in definition_file.Groups:
        if group.Name == name:
            return group
    return definition_file.Groups.Create(name)


def _text_definition(group, name):
    """A text ``ExternalDefinition`` called *name*, reused if it exists.

    ``SpecTypeId.String.Text`` from 2022, ``ParameterType.Text`` before it.
    Reusing an existing definition matters more than it looks: a shared
    parameter is identified by its GUID, so creating a second one of the same
    name would give two different projects two different parameters that read
    the same on screen.
    """
    for definition in group.Definitions:
        if definition.Name == name:
            return definition

    try:
        from Autodesk.Revit.DB import SpecTypeId
        options = ExternalDefinitionCreationOptions(name, SpecTypeId.String.Text)
    except Exception:
        from Autodesk.Revit.DB import ParameterType
        options = ExternalDefinitionCreationOptions(name, ParameterType.Text)
    return group.Definitions.Create(options)


def _category_set(app, doc, categories=CATEGORIES):
    """A ``CategorySet`` — never a Python list, which would be fatal (§12.9.4)."""
    category_set = app.Create.NewCategorySet()
    for builtin in categories:
        try:
            category = doc.Settings.Categories.get_Item(builtin)
        except Exception:
            category = None
        if category is not None:
            category_set.Insert(category)
    return category_set


def _identity_group():
    """Where the parameters appear in the properties palette."""
    try:
        from Autodesk.Revit.DB import GroupTypeId
        return GroupTypeId.IdentityData
    except Exception:
        from Autodesk.Revit.DB import BuiltInParameterGroup
        return BuiltInParameterGroup.PG_IDENTITY_DATA


def ensure(doc, names, categories=CATEGORIES):
    """Bind *names* to *categories* as instance shared parameters.

    ``(created, notes)``. **Requires a transaction the caller owns.** Only ever
    called when the user has asked for it: this writes a definition file and
    changes the project's parameter bindings, which is not something to do
    because it would be convenient.
    """
    created = []
    notes = []
    if not names:
        return created, notes

    app = doc.Application
    definition_file, note = _shared_parameter_file(app, doc)
    if note:
        notes.append(note)
    if definition_file is None:
        notes.append("no shared parameter file, so nothing could be created")
        return created, notes

    try:
        group = _group(definition_file)
    except Exception as error:
        notes.append("could not make the parameter group: {0}".format(error))
        return created, notes

    category_set = _category_set(app, doc, categories)
    if category_set.IsEmpty:
        notes.append("none of the categories these parameters need are in "
                     "this project")
        return created, notes

    binding = app.Create.NewInstanceBinding(category_set)
    parameter_group = _identity_group()
    for name in names:
        try:
            definition = _text_definition(group, name)
        except Exception as error:
            notes.append("{0}: {1}".format(name, error))
            continue
        try:
            if not doc.ParameterBindings.Insert(definition, binding,
                                                parameter_group):
                # Already bound, to some other set of categories: widen it
                # rather than leaving half the run unable to write.
                doc.ParameterBindings.ReInsert(definition, binding,
                                               parameter_group)
            created.append(name)
        except Exception as error:
            notes.append("{0} could not be bound: {1}".format(name, error))
    return created, notes


# ---------------------------------------------------------------------------
# Writing them
# ---------------------------------------------------------------------------

def write(element, values):
    """Set what the element will take. ``(written, notes)``.

    Missing is not an error and never stops a bar: the project either has the
    parameter or it does not, the user has already said what to do about that,
    and a run that failed four hundred bars over a text field would be worse
    than one that says which fields it could not fill.
    """
    written = []
    notes = []
    for name in sorted(values):
        value = values[name]
        if value is None or value == "":
            continue
        try:
            parameter = element.LookupParameter(name)
        except Exception:
            parameter = None
        if parameter is None:
            notes.append("{0}: this project has no such parameter".format(name))
            continue
        if parameter.IsReadOnly:
            notes.append("{0}: read-only here".format(name))
            continue
        try:
            parameter.Set(str(value))
            written.append(name)
        except Exception as error:
            notes.append("{0}: {1}".format(name, error))
    return written, notes

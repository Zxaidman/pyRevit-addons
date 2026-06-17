# -*- coding: utf-8 -*-
"""Link a DXF into the model programmatically, like Revit's 'Link CAD' dialog.

The remodelled tool starts from a CAD-free model: the user picks a .dxf, chooses
its drawing unit and positioning, and this module links it with DWGImportOptions so
a normal linked-CAD ImportInstance appears -- which the existing geometry_reader can
then read, and whose GetTotalTransform() ties the raw DXF coordinates to Revit feet.

Runs its own Transaction (linking must be transacted) and returns the ImportInstance.
Under the pyRevit CPython3 engine, Document.Link's `out ElementId` is returned as a
tuple, which this module unpacks.
"""

from Autodesk.Revit.DB import (DWGImportOptions, ImportUnit, ImportPlacement,
                               ImportInstance, Transaction)


def _choices(enum_type, names):
    """[(label, enum_value)] for the enum members that exist on this Revit version."""
    out = []
    for label, member in names:
        value = getattr(enum_type, member, None)
        if value is not None:
            out.append((label, value))
    return out


# Drawing-unit options, mm first (the common structural case).
UNIT_CHOICES = _choices(ImportUnit, [
    ("Millimeter", "Millimeter"),
    ("Centimeter", "Centimeter"),
    ("Decimeter", "Decimeter"),
    ("Meter", "Meter"),
    ("Foot", "Foot"),
    ("Inch", "Inch"),
])

# Positioning options, labelled like the Revit dialog.
PLACEMENT_CHOICES = _choices(ImportPlacement, [
    ("Auto - Center to Center", "Centered"),
    ("Auto - Origin to Origin", "Origin"),
    ("Auto - By Shared Coordinates", "Shared"),
])

_UNIT_BY_LABEL = dict(UNIT_CHOICES)
_PLACEMENT_BY_LABEL = dict(PLACEMENT_CHOICES)


def link_dxf(doc, path, unit_label, placement_label, view=None,
             this_view_only=False):
    """Link `path` into doc with the chosen unit + placement; return ImportInstance.

    `this_view_only` mirrors the Link CAD "Current view only" checkbox. Owns a
    Transaction. Fail-loud if the unit/placement are unknown, the link call fails,
    or the result is not an ImportInstance.
    """
    if doc is None or not path:
        raise ValueError("link_dxf requires a document and a DXF path")
    unit = _UNIT_BY_LABEL.get(unit_label)
    placement = _PLACEMENT_BY_LABEL.get(placement_label)
    if unit is None or placement is None:
        raise ValueError("unknown DXF unit/placement: {0} / {1}".format(
            unit_label, placement_label))

    view = view or doc.ActiveView
    options = DWGImportOptions()
    options.Unit = unit
    options.Placement = placement
    options.ThisViewOnly = bool(this_view_only)

    transaction = Transaction(doc, "Link DXF")
    transaction.Start()
    try:
        result = doc.Link(path, options, view)
        link_id = _unpack_out(result)
        if link_id is None:
            raise RuntimeError("Revit reported the DXF link failed (no element id)")
        doc.Regenerate()
        transaction.Commit()
    except Exception:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.RollBack()
        raise

    instance = doc.GetElement(link_id)
    if not isinstance(instance, ImportInstance):
        raise RuntimeError("Linked element is not an ImportInstance: {0}".format(instance))
    return instance


def _unpack_out(result):
    """Normalise Document.Link's return across engines.

    pythonnet (CPython3) returns (success_bool, ElementId) for the `out` param;
    a defensive path also handles a bare ElementId or a (id,) tuple.
    """
    if isinstance(result, tuple):
        if len(result) == 2:
            success, link_id = result
            return link_id if success else None
        if len(result) == 1:
            return result[0]
        return None
    return result

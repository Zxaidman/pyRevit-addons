# -*- coding: utf-8 -*-
"""Find and describe linked CAD (DWG) instances.

A linked DWG surfaces as an ImportInstance whose IsLinked == True and whose type
is a CADLinkType. An ImportInstance with IsLinked == False is an *embedded*
(imported) DWG, which we deliberately exclude -- linking is the supported source
for this tool because only links carry a stable, reversible reference.
"""

from Autodesk.Revit.DB import FilteredElementCollector, ImportInstance

from ..compat import element_id_value, get_element_name


def find_cad_links(doc):
    """Return all linked CAD ImportInstances in the document (possibly empty).

    Fail-fast on a missing document instead of returning a misleading [].
    """
    if doc is None:
        raise ValueError("find_cad_links received no document")

    instances = FilteredElementCollector(doc).OfClass(ImportInstance).ToElements()
    return [inst for inst in instances if inst.IsLinked]


def describe_link(doc, import_instance):
    """Human-readable label for a linked CAD instance via its CADLinkType.

    Never raises; falls back to the element id so the picker always has a label.
    """
    if import_instance is None:
        return "Unknown CAD link"

    fallback = "CAD link (id {0})".format(element_id_value(import_instance.Id))

    link_type = doc.GetElement(import_instance.GetTypeId())
    if link_type is None:
        return fallback

    name = get_element_name(link_type)
    return name if name else fallback

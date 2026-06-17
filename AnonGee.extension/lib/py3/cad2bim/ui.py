# -*- coding: utf-8 -*-
"""pyRevit forms dialogs for the CAD-to-BIM reader.

Only stock pyrevit.forms widgets are used (SelectFromList, CommandSwitchWindow,
alert) so there is no custom WPF/XAML to ship or maintain. Every dialog can be
cancelled, and cancellation is reported back so the caller can fail-fast.
"""

from pyrevit import forms

from cad2bim.cad_links import describe_link
from cad2bim.layers import ALL_CATEGORIES


def pick_dxf_file():
    """Open a file picker for a .dxf; return the path or None if cancelled."""
    return forms.pick_file(file_ext="dxf", multi_file=False,
                           title="Pick a DXF to link and convert")


def pick_import_unit(unit_labels):
    """Pick the DXF drawing unit from the given labels; return it or None."""
    if not unit_labels:
        return None
    return forms.CommandSwitchWindow.show(
        list(unit_labels), message="DXF drawing unit:")


def pick_import_placement(placement_labels):
    """Pick the DXF positioning from the given labels; return it or None."""
    if not placement_labels:
        return None
    return forms.CommandSwitchWindow.show(
        list(placement_labels), message="DXF positioning:")


def pick_link(doc, links):
    """Let the user pick one linked CAD when several exist. Returns it or None."""
    if not links:
        return None
    if len(links) == 1:
        return links[0]

    label_to_link = {}
    for link in links:
        label_to_link[describe_link(doc, link)] = link

    chosen = forms.SelectFromList.show(
        sorted(label_to_link.keys()),
        title="Select a linked CAD to read",
        multiselect=False,
        button_name="Read",
    )
    if not chosen:
        return None
    return label_to_link[chosen]


def prompt_mapping_override(default_mapping):
    """Show the convention mapping and let the user reassign layers.

    Returns the (possibly edited) {layer_key: category} dict. If the user opts
    out of editing, the default mapping is returned unchanged.
    """
    if not default_mapping:
        return default_mapping

    if not forms.alert("Adjust the layer -> element mapping before reporting?",
                       title="Layer mapping", yes=True, no=True):
        return default_mapping

    mapping = dict(default_mapping)
    while True:
        label_to_layer = {}
        labels = []
        for layer in sorted(mapping.keys()):
            label = "{0}   [{1}]".format(layer, mapping[layer])
            labels.append(label)
            label_to_layer[label] = layer

        picked = forms.SelectFromList.show(
            labels,
            title="Pick layers to reassign (Cancel to finish)",
            multiselect=True,
            button_name="Reassign",
        )
        if not picked:
            break

        target = forms.CommandSwitchWindow.show(
            list(ALL_CATEGORIES),
            message="Assign the selected layers to:",
        )
        if target:
            for label in picked:
                mapping[label_to_layer[label]] = target

        if not forms.alert("Reassign more layers?", yes=True, no=True):
            break

    return mapping

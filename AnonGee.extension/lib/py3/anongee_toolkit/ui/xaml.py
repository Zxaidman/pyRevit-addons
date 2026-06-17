# -*- coding: utf-8 -*-
"""
WPF / XAML loading utilities and ComboBox helpers.

Keeps XAML loading logic separate from dialog classes so it can be reused
without pulling in the full WpfDialogBase hierarchy.
"""
import os
import clr
clr.AddReference("PresentationFramework")

from System.IO import FileStream, FileMode, FileAccess
from System.Windows.Markup import XamlReader


def load_xaml(xaml_path):
    """
    Load and return a WPF Window from a ``.xaml`` file.

    The FileStream is closed immediately after parsing so the file is never
    held open while the dialog is running.

    Args:
        xaml_path (str): Absolute path to the XAML file.

    Returns:
        System.Windows.Window

    Raises:
        IOError: If the file does not exist.
    """
    if not os.path.exists(xaml_path):
        raise IOError("XAML file not found: {}".format(xaml_path))

    stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
    try:
        return XamlReader.Load(stream)
    finally:
        stream.Close()


def fill_combo(combo, label_id_pairs):
    """
    Populate a WPF ComboBox and return a ``{label: ElementId}`` mapping.

    Auto-selects the first item when the list is non-empty.

    Args:
        combo: WPF ComboBox control.
        label_id_pairs (iterable[tuple[str, ElementId]]): Items to add.

    Returns:
        dict[str, ElementId]
    """
    mapping = {}
    for label, element_id in label_id_pairs:
        combo.Items.Add(label)
        mapping[label] = element_id
    if combo.Items.Count > 0:
        combo.SelectedIndex = 0
    return mapping


def select_combo_containing(combo, keywords):
    """
    Select the first ComboBox item whose label contains any of *keywords*.

    Args:
        combo: WPF ComboBox control.
        keywords (iterable[str]): Lowercase search terms.

    Returns:
        bool: ``True`` if a match was found and selected.
    """
    for index in range(combo.Items.Count):
        label = str(combo.Items[index]).lower()
        if any(kw in label for kw in keywords):
            combo.SelectedIndex = index
            return True
    return False

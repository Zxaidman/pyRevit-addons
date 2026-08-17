# -*- coding: utf-8 -*-
"""The window and dialog plumbing the pushbutton needs, and nothing else.

Loading a .xaml into a live Window, asking the user for a file, showing a
message, reading a value off a control and putting one back. It is all
Revit-adjacent rather than Revit: no model is touched here, which is why it can
live in the library instead of the button.

CPython3 rules apply (AnonGee Brand Guidelines 12.1 / 12.8.4 / 12.9): no pyRevit
IronPython modules -- windows load through XamlReader, message boxes come from
System.Windows and file dialogs from System.Windows.Forms.

`_control_value` / `_set_control_value` are the two halves of saved settings. A
DISABLED control is deliberately left alone on restore: the dialog turns those
off because this model cannot do the thing (no beam family loaded, say), and a
saved tick must not talk it back into trying.
"""

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xml")
clr.AddReference("System.Windows.Forms")

from System.Windows.Markup import XamlReader
from System.IO import FileStream, FileMode, FileAccess
from System.Windows import (MessageBox, MessageBoxButton, MessageBoxImage,
                            MessageBoxResult)
from System.Windows.Controls import (ComboBox, TextBox, CheckBox, RadioButton,
                                     Slider)
import System.Windows.Forms

from . import settings
from .run_console import _OUT, _say


def _alert(title, message):
    MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Warning)


def _confirm(title, message):
    """A Yes/No question. True only on an explicit Yes.

    The gate in front of the Advanced window: closing the box, Esc and No all
    read as No, because the risky path must be the one that takes a decision.
    """
    return MessageBox.Show(message, title, MessageBoxButton.YesNo,
                           MessageBoxImage.Warning) == MessageBoxResult.Yes


def _error(title, message, detail=None):
    _OUT.fail()
    body = message
    if detail:
        body += "\n\n--- technical detail ---\n{0}".format(detail)
    MessageBox.Show(body, title, MessageBoxButton.OK, MessageBoxImage.Error)


def _persisted(tstatus, gstatus):
    """True only if both the inner transaction and the group actually committed."""
    from Autodesk.Revit.DB import TransactionStatus
    return (tstatus == TransactionStatus.Committed
            and gstatus == TransactionStatus.Committed)


def _rollback_alert(label, tstatus, gstatus):
    """Report a silent commit rollback truthfully instead of faking success."""
    message = (
        "{0} were computed but the Revit transaction did NOT persist (commit "
        "status: {1}, group: {2}).\n\nThis usually means error-severity failures "
        "at commit -- most often running into a project that already contains "
        "these elements. Try a fresh/empty project (or undo the previous run), "
        "then run again.".format(label, tstatus, gstatus))
    _OUT.fail()
    _say(message)
    _error("{0} not saved".format(label), message)


def _load_window(xaml_path):
    """Load a WPF Window from a .xaml file via XamlReader (CPython3-safe)."""
    stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
    try:
        return XamlReader.Load(stream)
    finally:
        stream.Close()


def _control_value(control):
    """A control's value as plain JSON, or None when it holds nothing to save."""
    if control is None:
        return None
    if isinstance(control, ComboBox):
        item = control.SelectedItem
        return str(item) if item is not None else (control.Text or "")
    if isinstance(control, (CheckBox, RadioButton)):
        return bool(control.IsChecked)
    if isinstance(control, Slider):
        return float(control.Value)
    if isinstance(control, TextBox):
        return control.Text or ""
    return None


def _set_control_value(control, value):
    """Put a saved value back on a control. True when it landed.

    A DISABLED control is left alone: the dialog turns those off because this
    model cannot do the thing (no beam family loaded, say), and a saved tick
    must not talk it back into trying.
    """
    if control is None or value is None:
        return False
    try:
        if not control.IsEnabled:
            return False
    except Exception:
        pass
    try:
        if isinstance(control, ComboBox):
            index = settings.pick_index(control.Items, value)
            if index >= 0:
                control.SelectedIndex = index
                return True
            if control.IsEditable:
                control.Text = str(value)
                return True
            return False
        if isinstance(control, (CheckBox, RadioButton)):
            control.IsChecked = bool(value)
            return True
        if isinstance(control, Slider):
            control.Value = float(value)
            return True
        if isinstance(control, TextBox):
            control.Text = str(value)
            return True
    except Exception:
        return False
    return False


def _open_settings_file():
    dialog = System.Windows.Forms.OpenFileDialog()
    dialog.Title = "Load cad2bim settings"
    dialog.Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*"
    if dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK:
        return dialog.FileName
    return None


def _save_settings_file():
    dialog = System.Windows.Forms.SaveFileDialog()
    dialog.Title = "Save cad2bim settings"
    dialog.Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*"
    dialog.FileName = "cad2bim_settings.json"
    if dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK:
        return dialog.FileName
    return None


def _open_dxf():
    dialog = System.Windows.Forms.OpenFileDialog()
    dialog.Title = "Pick a DXF to link and convert"
    dialog.Filter = "DXF files (*.dxf)|*.dxf|All files (*.*)|*.*"
    if dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK:
        return dialog.FileName
    return None


def _save_json(default_name):
    dialog = System.Windows.Forms.SaveFileDialog()
    dialog.Title = "Export parsed curves to JSON"
    dialog.Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*"
    dialog.FileName = default_name
    if dialog.ShowDialog() == System.Windows.Forms.DialogResult.OK:
        return dialog.FileName
    return None


def _select_containing(combo, keywords):
    """Select the first combo item whose label contains any keyword (lowercased).

    Returns True if a match was selected, leaving the prior selection otherwise.
    """
    for index in range(combo.Items.Count):
        label = str(combo.Items[index]).lower()
        if any(keyword in label for keyword in keywords):
            combo.SelectedIndex = index
            return True
    return False

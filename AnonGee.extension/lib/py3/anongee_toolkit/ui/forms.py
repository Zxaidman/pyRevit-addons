# -*- coding: utf-8 -*-
"""
Native .NET message boxes and file dialogs.

Bypasses ``pyrevit.forms`` entirely to avoid CPython3 engine crashes.
All functions are thin wrappers around System.Windows.MessageBox and
System.Windows.Forms file dialogs.
"""
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("System.Windows.Forms")

from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage, MessageBoxResult
import System.Windows.Forms as WinForms


def alert(title, message):
    """Show a warning message box with an OK button."""
    MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Warning)


def error(title, message, detail=None):
    """
    Show a critical error message box.

    Args:
        title (str): Dialog title.
        message (str): User-facing error description.
        detail (str, optional): Technical details appended below a separator.
    """
    body = message
    if detail:
        body += "\n\n--- technical detail ---\n{}".format(detail)
    MessageBox.Show(body, title, MessageBoxButton.OK, MessageBoxImage.Error)


def info(title, message):
    """Show an information message box with an OK button."""
    MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Information)


def confirm(title, message):
    """
    Show a Yes/No confirmation dialog.

    Returns:
        bool: ``True`` if the user clicked Yes.
    """
    result = MessageBox.Show(
        message, title, MessageBoxButton.YesNo, MessageBoxImage.Warning
    )
    return result == MessageBoxResult.Yes


def pick_file(title="Select File", file_filter="All files (*.*)|*.*"):
    """
    Open a native Windows OpenFileDialog.

    Returns:
        str | None: Absolute path to the selected file, or ``None`` if cancelled.
    """
    dialog = WinForms.OpenFileDialog()
    dialog.Title = title
    dialog.Filter = file_filter
    if dialog.ShowDialog() == WinForms.DialogResult.OK:
        return dialog.FileName
    return None


def save_file(title="Save File", file_filter="All files (*.*)|*.*", default_name=""):
    """
    Open a native Windows SaveFileDialog.

    Returns:
        str | None: Chosen save path, or ``None`` if cancelled.
    """
    dialog = WinForms.SaveFileDialog()
    dialog.Title = title
    dialog.Filter = file_filter
    dialog.FileName = default_name
    if dialog.ShowDialog() == WinForms.DialogResult.OK:
        return dialog.FileName
    return None

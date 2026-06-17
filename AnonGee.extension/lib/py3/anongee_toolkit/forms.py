# -*- coding: utf-8 -*-
"""
Pure .NET CPython3-safe UI forms and dialogs.
Bypasses `pyrevit.forms` to prevent CPython3 engine crashes.
"""
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("System.Windows.Forms")

from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage
import System.Windows.Forms as WinForms

def alert(title, message):
    """Shows a standard warning message box."""
    MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Warning)

def error(title, message, detail=None):
    """Shows a critical error message box, optionally with technical details."""
    body = message
    if detail:
        body += "\n\n--- technical detail ---\n{0}".format(detail)
    MessageBox.Show(body, title, MessageBoxButton.OK, MessageBoxImage.Error)

def info(title, message):
    """Shows a standard information message box."""
    MessageBox.Show(message, title, MessageBoxButton.OK, MessageBoxImage.Information)

def pick_file(title="Select File", file_filter="All files (*.*)|*.*"):
    """
    Opens a native Windows OpenFileDialog.
    Returns the selected file path, or None if canceled.
    """
    dialog = WinForms.OpenFileDialog()
    dialog.Title = title
    dialog.Filter = file_filter
    if dialog.ShowDialog() == WinForms.DialogResult.OK:
        return dialog.FileName
    return None

def save_file(title="Save File", file_filter="All files (*.*)|*.*", default_name=""):
    """
    Opens a native Windows SaveFileDialog.
    Returns the chosen save path, or None if canceled.
    """
    dialog = WinForms.SaveFileDialog()
    dialog.Title = title
    dialog.Filter = file_filter
    dialog.FileName = default_name
    if dialog.ShowDialog() == WinForms.DialogResult.OK:
        return dialog.FileName
    return None

def confirm(title, message):
    """
    Shows a Yes/No confirmation dialog.
    Returns True if the user clicks Yes, False otherwise.
    """
    result = MessageBox.Show(
        message, title, MessageBoxButton.YesNo, MessageBoxImage.Warning
    )
    return result == System.Windows.MessageBoxResult.Yes
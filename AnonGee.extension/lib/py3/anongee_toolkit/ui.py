# -*- coding: utf-8 -*-
import os

import System
import clr
clr.AddReference("PresentationFramework")
from System.Windows.Threading import DispatcherTimer, Dispatcher, DispatcherPriority
from System.IO import FileStream, FileMode, FileAccess
from System.Windows.Markup import XamlReader
import os
from System import Action, Uri, UriKind
from System.Windows import Visibility
from System.Windows.Media.Imaging import BitmapImage

class WpfDialogBase(object):
    """
    Base class for AnonGee WPF dialogs. 
    Automatically handles XAML loading, window icons, UI flushing, and the Badge feedback system.
    """
    def __init__(self, ui_dir):
        xaml_path = os.path.join(ui_dir, "ui.xaml")
        self.window = load_xaml(xaml_path)

        # Set Window Icon
        icon_path = os.path.join(ui_dir, "icon.png")
        if os.path.exists(icon_path):
            self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

        # Map Common Brand Controls
        self._badge_info    = self.window.FindName("BadgeInfo")
        self._badge_success = self.window.FindName("BadgeSuccess")
        self._badge_error   = self.window.FindName("BadgeError")
        self._info_text     = self.window.FindName("InfoText")
        self._success_text  = self.window.FindName("SuccessText")
        self._error_text    = self.window.FindName("ErrorText")
        self._btn_close     = self.window.FindName("BtnClose")

        if self._btn_close:
            self._btn_close.Click += lambda s, e: self.window.Close()

    def show_info(self, message):
        if self._info_text: self._info_text.Text = message
        if self._badge_info: self._badge_info.Visibility = Visibility.Visible
        if self._badge_success: self._badge_success.Visibility = Visibility.Collapsed
        if self._badge_error: self._badge_error.Visibility = Visibility.Collapsed

    def show_success(self, message):
        if self._success_text: self._success_text.Text = message
        if self._badge_info: self._badge_info.Visibility = Visibility.Collapsed
        if self._badge_success: self._badge_success.Visibility = Visibility.Visible
        if self._badge_error: self._badge_error.Visibility = Visibility.Collapsed

    def show_error(self, message):
        if self._error_text: self._error_text.Text = message
        if self._badge_info: self._badge_info.Visibility = Visibility.Collapsed
        if self._badge_success: self._badge_success.Visibility = Visibility.Collapsed
        if self._badge_error: self._badge_error.Visibility = Visibility.Visible

    def flush_ui(self):
        """Forces the WPF window to repaint immediately."""
        Dispatcher.CurrentDispatcher.Invoke(Action(lambda: None), DispatcherPriority.Background)

    def show(self):
        self.window.ShowDialog()



class DebounceTimer:
    """
    A WPF DispatcherTimer wrapper for debouncing rapid UI events 
    (e.g., text changing in a search box) to prevent Revit UI freezing.
    """
    def __init__(self, callback, delay_ms=300):
        if not callable(callback):
            raise TypeError("DebounceTimer requires a callable function.")
            
        self._timer = DispatcherTimer()
        self._timer.Interval = System.TimeSpan.FromMilliseconds(delay_ms)
        self._timer.Tick += self._on_tick
        self._callback = callback

    def _on_tick(self, sender, args):
        self._timer.Stop()
        self._callback()

    def reset(self):
        self._timer.Stop()
        self._timer.Start()

    def stop(self):
        self._timer.Stop()

# --- WPF Helpers ---

def load_xaml(xaml_path):
    """
    Safely loads a WPF Window from a .xaml file via XamlReader.
    Ensures the FileStream is closed immediately to prevent file locking.
    Fail-Fast: Raises IOError if the file does not exist.
    """
    import os
    if not os.path.exists(xaml_path):
        raise IOError("XAML file not found at: {}".format(xaml_path))
        
    stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
    try:
        return XamlReader.Load(stream)
    finally:
        stream.Close()

def fill_combo(combo, label_id_pairs):
    """
    Populates a WPF ComboBox with labels and returns a {label: ElementId} dictionary.
    Auto-selects the first item if the list is populated.
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
    Selects the first ComboBox item whose label contains any of the provided keywords.
    Keywords should be lowercase.
    Returns True if a match was selected.
    """
    for index in range(combo.Items.Count):
        label = str(combo.Items[index]).lower()
        if any(keyword in label for keyword in keywords):
            combo.SelectedIndex = index
            return True
    return False
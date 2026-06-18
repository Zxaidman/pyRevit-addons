# -*- coding: utf-8 -*-
"""
WPF dialog base class and debounce timer.

``WpfDialogBase`` wires the common AnonGee window chrome (close button, badge
feedback strip) so subclasses only need to add their own controls.

``DebounceTimer`` prevents rapid search-box changes from hammering the Revit
API on every keystroke.
"""
import os
import clr
clr.AddReference("PresentationFramework")

import System
from System import Action, Uri, UriKind
from System.Windows import Visibility
from System.Windows.Media.Imaging import BitmapImage
from System.Windows.Threading import Dispatcher, DispatcherPriority, DispatcherTimer

from anongee_toolkit.ui.xaml import load_xaml


class WpfDialogBase(object):
    """
    Base class for AnonGee WPF dialogs.

    Subclass and call ``super().__init__(ui_dir)`` to get:

    * XAML loaded from ``<ui_dir>/ui.xaml``
    * Window icon loaded from ``<ui_dir>/icon.png`` (if present)
    * Badge feedback strip wired up (``show_info``, ``show_success``,
      ``show_error``)
    * Close button (``BtnClose``) connected automatically
    * ``flush_ui()`` helper for immediate repaints
    """

    def __init__(self, ui_dir):
        xaml_path = os.path.join(ui_dir, "ui.xaml")
        self.window = load_xaml(xaml_path)

        icon_path = os.path.join(ui_dir, "icon.png")
        if os.path.exists(icon_path):
            self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

        self._badge_info    = self.window.FindName("BadgeInfo")
        self._badge_success = self.window.FindName("BadgeSuccess")
        self._badge_error   = self.window.FindName("BadgeError")
        self._info_text     = self.window.FindName("InfoText")
        self._success_text  = self.window.FindName("SuccessText")
        self._error_text    = self.window.FindName("ErrorText")

        btn_close = self.window.FindName("BtnClose")
        if btn_close:
            btn_close.Click += lambda s, e: self.window.Close()

    def show_info(self, message):
        """Display *message* in the info badge."""
        if self._info_text:    self._info_text.Text = message
        if self._badge_info:   self._badge_info.Visibility   = Visibility.Visible
        if self._badge_success: self._badge_success.Visibility = Visibility.Collapsed
        if self._badge_error:  self._badge_error.Visibility  = Visibility.Collapsed

    def show_success(self, message):
        """Display *message* in the success badge."""
        if self._success_text:  self._success_text.Text = message
        if self._badge_info:    self._badge_info.Visibility    = Visibility.Collapsed
        if self._badge_success: self._badge_success.Visibility = Visibility.Visible
        if self._badge_error:   self._badge_error.Visibility   = Visibility.Collapsed

    def show_error(self, message):
        """Display *message* in the error badge."""
        if self._error_text:    self._error_text.Text = message
        if self._badge_info:    self._badge_info.Visibility    = Visibility.Collapsed
        if self._badge_success: self._badge_success.Visibility = Visibility.Collapsed
        if self._badge_error:   self._badge_error.Visibility   = Visibility.Visible

    def flush_ui(self):
        """Force the WPF dispatcher to process pending render work immediately."""
        Dispatcher.CurrentDispatcher.Invoke(
            Action(lambda: None), DispatcherPriority.Background
        )

    def show(self):
        """Open the dialog as a modal window."""
        self.window.ShowDialog()


class DebounceTimer:
    """
    Wrap a WPF ``DispatcherTimer`` so rapid events (e.g. text-box changes)
    only trigger *callback* once, after *delay_ms* milliseconds of silence.

    Args:
        callback (callable): Function to call when the debounce period expires.
        delay_ms (int): Quiet period in milliseconds before *callback* fires.
    """

    def __init__(self, callback, delay_ms=300):
        if not callable(callback):
            raise TypeError("DebounceTimer requires a callable.")

        self._callback = callback
        self._timer = DispatcherTimer()
        self._timer.Interval = System.TimeSpan.FromMilliseconds(delay_ms)
        self._timer.Tick += self._on_tick

    def _on_tick(self, sender, args):
        self._timer.Stop()
        self._callback()

    def reset(self):
        """Restart the debounce countdown."""
        self._timer.Stop()
        self._timer.Start()

    def stop(self):
        """Cancel any pending callback."""
        self._timer.Stop()

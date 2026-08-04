# -*- coding: utf-8 -*-
"""progressbar - CPython-safe progress bar matching pyRevit's native one.

``pyrevit.forms.ProgressBar`` is built with ``wpf.LoadComponent`` and raises
``PyRevitCPythonNotSupported`` under the CPython engine. This builds the same
thing without that module: the control templates come from pyRevit's own
ProgressBar.xaml parsed via ``XamlReader``, the window is docked across the top
of the Revit window, and the events are wired in code.

Two styles:

``pyrevit`` (default)
    Full-width strip flush with the top of the Revit window, over the title
    bar. Borderless, never activates, follows Revit if the window is moved.

``dialog``
    Standalone centred window with a separate status line. Useful when there is
    no Revit host, or when the strip is too easy to miss.
"""

import time

__version__ = "1.5.0"
__all__ = ["ProgressBar"]

from System.Windows import (Window, Thickness, WindowStyle, ResizeMode,
                            SizeToContent, WindowStartupLocation,
                            HorizontalAlignment, VerticalAlignment,
                            TextWrapping, TextAlignment, FontWeights,
                            SystemParameters)
from System.Windows.Controls import (StackPanel, TextBlock, Button, Grid,
                                     ProgressBar as WpfProgressBar)
from System.Windows.Media import Brushes
from System.Windows.Threading import DispatcherPriority

from anongee_toolkit.ui import theme
from anongee_toolkit.ui import hostwnd
from anongee_toolkit.ui.pump import pump

#: WindowStyle.None is unreachable by attribute access - None is a keyword.
_WINDOW_STYLE_NONE = getattr(WindowStyle, "None")


def _fmt_eta(sec):
    if sec is None or sec < 0:
        return "--"
    sec = int(sec)
    if sec < 60:
        return "{0}s".format(sec)
    m, s = divmod(sec, 60)
    if m < 60:
        return "{0}m {1:02d}s".format(m, s)
    h, m = divmod(m, 60)
    return "{0}h {1:02d}m".format(h, m)


class ProgressBar(object):
    """Call-compatible with ``pyrevit.forms.ProgressBar``.

        with ProgressBar(title='Reading beams and columns... {value}/{max_value}',
                         cancellable=True) as pb:
            for i, x in enumerate(items):
                if pb.cancelled:
                    break
                pb.update_progress(i + 1, len(items))

    Title placeholders: ``{value}``, ``{max_value}``, ``{percent}``, ``{eta}``.

    In ``pyrevit`` style the bar shows the rendered title and nothing else, to
    match the native bar. Percentage and ETA are still available - put
    ``{percent}`` or ``{eta}`` in the title if you want them.
    """

    def __init__(self, title="{value}/{max_value}", cancellable=False,
                 step=0, indeterminate=False, width=None, height=None,
                 topmost=True, min_refresh_ms=80, show_eta=False,
                 parent_handle=None, style="pyrevit", bar_height=26,
                 top_offset=0, follow_host=True):
        self.title_template = title or "{value}/{max_value}"
        self.cancellable = cancellable
        self.step = int(step or 0)
        self.indeterminate = indeterminate
        self.style = (style or "pyrevit").lower()
        self.width = width or (600 if self.style == "pyrevit" else 460)
        self.bar_height = height or bar_height
        self.top_offset = top_offset
        self.follow_host = follow_host
        self.topmost = topmost
        self.min_refresh_ms = min_refresh_ms
        self.show_eta = show_eta
        self.parent_handle = parent_handle

        self.value = 0
        self.max_value = 100
        self._status = ""
        self._cancelled = False
        self._closed = False
        self._start = None
        self._last_refresh = 0.0
        self._placed = False

        self._window = None
        self._bar = None
        self._title_block = None
        self._status_block = None
        self._cancel_btn = None

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self):
        self.show()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def show(self):
        self._start = time.time()
        try:
            self._build()
            self._window.Show()
            # Placement needs a PresentationSource for the DPI factors, which
            # only exists once shown. Place twice: the first move may land the
            # window on a differently-scaled monitor, the second corrects for
            # that monitor's factors.
            self._place()
            self._place()
            pump(DispatcherPriority.Background)
        except Exception:
            self._window = None
        return self

    def close(self):
        self._closed = True
        if self._window is None:
            return
        try:
            self._window.Close()
        except Exception:
            pass
        try:
            pump(DispatcherPriority.Background)
        except Exception:
            pass
        self._window = None

    def _place(self):
        if self._window is None or self.style != "pyrevit":
            return
        ok = hostwnd.place_over_host(self._window, self.bar_height,
                                     handle=self.parent_handle,
                                     top_offset=self.top_offset)
        if not ok and not self._placed:
            try:
                area = SystemParameters.WorkArea
                self._window.Width = self.width
                self._window.Left = area.Left + (area.Width - self.width) / 2.0
                self._window.Top = area.Top + self.top_offset
            except Exception:
                pass
        self._placed = True

    # -- construction ------------------------------------------------------

    def _build(self):
        if self.style == "pyrevit":
            self._build_strip()
        else:
            self._build_dialog()

    def _build_strip(self):
        w = Window()
        w.Title = "Progress"
        w.Width = self.width
        w.Height = self.bar_height
        w.WindowStyle = _WINDOW_STYLE_NONE
        w.ResizeMode = ResizeMode.NoResize
        w.ShowInTaskbar = False
        # Matches pyRevit: the bar must never take focus away from Revit.
        w.ShowActivated = False
        w.Topmost = bool(self.topmost)
        w.WindowStartupLocation = WindowStartupLocation.Manual
        w.Background = None
        w.Closing += self._on_closing

        resources = theme.bar_resources()
        if resources is not None:
            try:
                w.Resources = resources
            except Exception:
                resources = None

        dark = theme.brush("pyRevitDarkBrush", theme.DARK_FALLBACK)
        accent = theme.brush("pyRevitAccentBrush", theme.ACCENT_FALLBACK)

        grid = Grid()
        if dark is not None:
            grid.Background = dark

        self._bar = WpfProgressBar()
        self._bar.Minimum = 0
        self._bar.Maximum = 100
        self._bar.Value = 0
        self._bar.IsIndeterminate = bool(self.indeterminate)
        if resources is None:
            # No parsed template: approximate it so the bar still reads right.
            self._bar.BorderThickness = Thickness(0)
            self._bar.Background = dark or Brushes.Transparent
            if accent is not None:
                self._bar.Foreground = accent
        grid.Children.Add(self._bar)

        self._title_block = TextBlock()
        self._title_block.Text = self._render_title()
        self._title_block.TextWrapping = TextWrapping.Wrap
        self._title_block.TextAlignment = TextAlignment.Center
        self._title_block.VerticalAlignment = VerticalAlignment.Center
        self._title_block.Foreground = Brushes.White
        grid.Children.Add(self._title_block)

        # Strip style shows one overlaid line only.
        self._status_block = None

        if self.cancellable:
            self._cancel_btn = Button()
            self._cancel_btn.Content = "Cancel"
            self._cancel_btn.Height = 18
            self._cancel_btn.HorizontalAlignment = HorizontalAlignment.Left
            self._cancel_btn.VerticalAlignment = VerticalAlignment.Center
            self._cancel_btn.Margin = Thickness(12, 0, 0, 0)
            self._cancel_btn.Padding = Thickness(10, 0, 10, 0)
            self._cancel_btn.Click += self._on_cancel
            grid.Children.Add(self._cancel_btn)

        w.Content = grid
        self._window = w

    def _build_dialog(self):
        w = Window()
        w.Title = "Progress"
        w.Width = self.width
        w.SizeToContent = SizeToContent.Height
        w.WindowStyle = WindowStyle.ToolWindow
        w.ResizeMode = ResizeMode.NoResize
        w.WindowStartupLocation = WindowStartupLocation.CenterScreen
        w.ShowInTaskbar = False
        w.Topmost = bool(self.topmost)
        w.Closing += self._on_closing

        root = StackPanel()
        root.Margin = Thickness(14)

        self._title_block = TextBlock()
        self._title_block.Text = self._render_title()
        self._title_block.FontWeight = FontWeights.SemiBold
        self._title_block.TextWrapping = TextWrapping.NoWrap
        self._title_block.Margin = Thickness(0, 0, 0, 8)
        root.Children.Add(self._title_block)

        self._bar = WpfProgressBar()
        self._bar.Height = 18
        self._bar.Minimum = 0
        self._bar.Maximum = 100
        self._bar.Value = 0
        self._bar.IsIndeterminate = bool(self.indeterminate)
        root.Children.Add(self._bar)

        self._status_block = TextBlock()
        self._status_block.Text = ""
        self._status_block.Foreground = Brushes.Gray
        self._status_block.TextWrapping = TextWrapping.NoWrap
        self._status_block.Margin = Thickness(0, 8, 0, 0)
        root.Children.Add(self._status_block)

        if self.cancellable:
            self._cancel_btn = Button()
            self._cancel_btn.Content = "Cancel"
            self._cancel_btn.Width = 90
            self._cancel_btn.Height = 26
            self._cancel_btn.HorizontalAlignment = HorizontalAlignment.Right
            self._cancel_btn.Margin = Thickness(0, 12, 0, 0)
            self._cancel_btn.Click += self._on_cancel
            root.Children.Add(self._cancel_btn)

        w.Content = root
        self._window = w

    # -- events ------------------------------------------------------------

    def _on_cancel(self, sender, args):
        self._cancelled = True
        try:
            self._cancel_btn.Content = "Cancelling..."
            self._cancel_btn.IsEnabled = False
        except Exception:
            pass

    def _on_closing(self, sender, args):
        self._cancelled = True

    # -- state -------------------------------------------------------------

    @property
    def cancelled(self):
        return self._cancelled

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, text):
        self._status = text or ""
        self._refresh(force=False)

    @property
    def title(self):
        return self.title_template

    @title.setter
    def title(self, text):
        self.title_template = text or ""
        self._refresh(force=True)

    def reset(self):
        self.value = 0
        self._start = time.time()
        self._refresh(force=True)

    def hide(self):
        if self._window is not None:
            try:
                self._window.Hide()
            except Exception:
                pass

    def unhide(self):
        if self._window is not None:
            try:
                self._window.Show()
            except Exception:
                pass

    # -- the call you make in the loop ------------------------------------

    def update_progress(self, new_value, max_value=100):
        self.value = new_value
        self.max_value = max_value or 1
        final = new_value >= self.max_value
        if self.step > 0 and not final and (int(new_value) % self.step) != 0:
            return
        self._refresh(force=final)

    def _percent(self):
        if not self.max_value:
            return 0
        return max(0, min(100, int(round(100.0 * self.value / self.max_value))))

    def _eta(self):
        if not self._start or self.value <= 0:
            return None
        elapsed = time.time() - self._start
        rate = self.value / elapsed if elapsed > 0 else 0
        if rate <= 0:
            return None
        return (self.max_value - self.value) / rate

    def _render_title(self):
        try:
            return self.title_template.format(
                value=self.value, max_value=self.max_value,
                percent=self._percent(), eta=_fmt_eta(self._eta()))
        except Exception:
            return self.title_template

    def _refresh(self, force=False):
        if self._window is None or self._closed:
            return
        now = time.time()
        if not force and (now - self._last_refresh) * 1000.0 < self.min_refresh_ms:
            return
        self._last_refresh = now
        try:
            if not self.indeterminate:
                self._bar.Value = self._percent()

            if self._status_block is None:
                text = self._render_title()
                if self._status:
                    text = "{0}   -   {1}".format(text, self._status)
                self._title_block.Text = text
            else:
                self._title_block.Text = self._render_title()
                bits = ["{0}%".format(self._percent())]
                if self.show_eta:
                    eta = self._eta()
                    if eta is not None:
                        bits.append("~{0} left".format(_fmt_eta(eta)))
                if self._status:
                    bits.append(self._status)
                self._status_block.Text = "   |   ".join(bits)

            if self.follow_host:
                self._place()

            self._window.UpdateLayout()
            # Render priority sits ABOVE Input, so pumping there repaints the
            # bar but never dispatches the Cancel click - the button looks
            # alive and does nothing. A cancellable bar has to pump at
            # Background (below Input) and accept that host-app clicks go
            # through too. Non-cancellable stays at the safer Render.
            pump(DispatcherPriority.Background if self.cancellable else None)
        except Exception:
            pass

    # -- convenience -------------------------------------------------------

    @classmethod
    def track(cls, items, title="{value}/{max_value}", cancellable=True,
              **kwargs):
        """Wrap any sequence: ``for x in ProgressBar.track(items): ...``"""
        seq = list(items)
        total = len(seq) or 1
        with cls(title=title, cancellable=cancellable, **kwargs) as pb:
            for i, item in enumerate(seq):
                if pb.cancelled:
                    break
                pb.update_progress(i + 1, total)
                yield item

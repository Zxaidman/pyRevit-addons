# -*- coding: utf-8 -*-
"""cpyforms - CPython (pythonnet) replacements for the pyRevit forms that are
IronPython-only.

pyRevit builds most of its dialogs with `wpf.LoadComponent`, which only exists
in IronPython. Under the CPython engine those classes raise
`PyRevitCPythonNotSupported`. This module builds the same widgets in code
instead of XAML, so it works on either engine.

Drop this file in your extension's ``lib`` folder:

    MyTools.extension/
        lib/
            cpyforms.py
        MyTab.tab/...

Then in any ``#! python3`` script::

    from cpyforms import ProgressBar, CheckList, pick_option

    with ProgressBar(title='Working {value}/{max_value}', cancellable=True) as pb:
        for i, item in enumerate(items):
            if pb.cancelled:
                break
            pb.update_progress(i + 1, len(items))
            do_work(item)

The ProgressBar API is deliberately call-compatible with
``pyrevit.forms.ProgressBar`` so existing code needs only the import swapped.

Author  : AnonGee
Version : 1.2.0
Engines : CPython 3 (primary), IronPython 2.7 (works too)
"""

import time

__version__ = "1.2.0"

__all__ = ["ProgressBar", "CheckList", "pick_option", "alert", "ask_yes_no",
           "theme_brush",
           "pump", "revit_handle"]

# ---------------------------------------------------------------------------
# CLR bootstrap
# ---------------------------------------------------------------------------

for _asm in ("PresentationFramework", "PresentationCore", "WindowsBase",
             "System.Xaml", "System.Windows.Forms"):
    try:
        import clr
        clr.AddReference(_asm)
    except Exception:
        pass

from System import Action, IntPtr                                   # noqa: E402
from System.Windows import (Window, Thickness, WindowStyle,          # noqa: E402
                            ResizeMode, SizeToContent,
                            WindowStartupLocation, HorizontalAlignment,
                            VerticalAlignment, TextWrapping,
                            FontWeights, Visibility, TextAlignment,
                            SystemParameters,
                            MessageBox, MessageBoxButton, MessageBoxImage,
                            MessageBoxResult)
from System.Windows.Controls import (StackPanel, TextBlock, Button,  # noqa: E402
                                     ProgressBar as WpfProgressBar,
                                     CheckBox, ScrollViewer, TextBox,
                                     DockPanel, Dock, Orientation, Grid,
                                     ScrollBarVisibility)
from System.Windows.Media import Brushes, FontFamily                 # noqa: E402
from System.Windows.Threading import (Dispatcher, DispatcherFrame,   # noqa: E402
                                      DispatcherPriority,
                                      DispatcherOperationCallback)
from System.Windows.Interop import WindowInteropHelper               # noqa: E402


# ---------------------------------------------------------------------------
# dispatcher pumping
# ---------------------------------------------------------------------------

_PUMP_STRATEGY = None


def _exit_frame(frame):
    frame.Continue = False
    return None


def pump(priority=None):
    """Flush the WPF dispatcher queue so the UI repaints mid-loop.

    Defaults to ``DispatcherPriority.Render``, which processes the layout and
    render passes but stops *before* the Input queue. That matters inside a
    Revit transaction: pumping Input priority lets keystrokes and clicks reach
    Revit while your transaction is open, which can trigger a reentrant API
    call. Render priority avoids that.
    """
    global _PUMP_STRATEGY
    if priority is None:
        priority = DispatcherPriority.Render

    if _PUMP_STRATEGY in (None, "frame"):
        try:
            frame = DispatcherFrame()
            Dispatcher.CurrentDispatcher.BeginInvoke(
                priority, DispatcherOperationCallback(_exit_frame), frame)
            Dispatcher.PushFrame(frame)
            _PUMP_STRATEGY = "frame"
            return
        except Exception:
            _PUMP_STRATEGY = "invoke"

    if _PUMP_STRATEGY == "invoke":
        try:
            Dispatcher.CurrentDispatcher.Invoke(Action(lambda: None), priority)
            return
        except Exception:
            _PUMP_STRATEGY = "none"


def revit_handle():
    """Revit's main window handle, for parenting dialogs. None if unavailable."""
    try:
        from pyrevit import HOST_APP
        h = HOST_APP.uiapp.MainWindowHandle
        if h is not None and h != IntPtr.Zero:
            return h
    except Exception:
        pass
    try:
        import __main__
        h = __main__.__revit__.MainWindowHandle
        if h is not None and h != IntPtr.Zero:
            return h
    except Exception:
        pass
    try:
        from System.Diagnostics import Process
        return Process.GetCurrentProcess().MainWindowHandle
    except Exception:
        return None


def _own(window):
    try:
        h = revit_handle()
        if h is not None and h != IntPtr.Zero:
            WindowInteropHelper(window).Owner = h
            return True
    except Exception:
        pass
    return False


def theme_brush(resource_key, fallback):
    """Resolve a WPF resource brush by key, falling back to a hex string.

    pyRevit registers ``pyRevitDarkBrush`` / ``pyRevitAccentBrush`` in the
    application resources, so inside pyRevit this picks up the real palette.
    Outside it (bare add-in, no WPF Application) the fallback is used - a
    neutral dark/amber pair chosen to look reasonable, not a claim about
    pyRevit's exact values.
    """
    try:
        from System.Windows import Application
        app = Application.Current
        if app is not None:
            found = app.TryFindResource(resource_key)
            if found is not None:
                return found
    except Exception:
        pass
    try:
        from System.Windows.Media import BrushConverter
        return BrushConverter().ConvertFromString(fallback)
    except Exception:
        return None


DARK_FALLBACK = "#FF2C3E50"
ACCENT_FALLBACK = "#FFF39C12"


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


# ---------------------------------------------------------------------------
# ProgressBar
# ---------------------------------------------------------------------------


class ProgressBar(object):
    """Modeless progress window that repaints from the Revit UI thread.

    Call-compatible with ``pyrevit.forms.ProgressBar``:

        with ProgressBar(title='{value} of {max_value}', cancellable=True) as pb:
            for i, x in enumerate(items):
                if pb.cancelled:
                    break
                pb.update_progress(i + 1, len(items))

    Title placeholders: ``{value}``, ``{max_value}``, ``{percent}``, ``{eta}``.

    Extras beyond the pyRevit version: ``status`` for a second line,
    ``min_refresh_ms`` throttling, ETA, and :meth:`track`.
    """

    def __init__(self, title="{value} of {max_value}", cancellable=False,
                 step=0, indeterminate=False, width=460, height=None,
                 topmost=True, min_refresh_ms=80, show_eta=True,
                 parent_handle=None, style="pyrevit", bar_height=24,
                 bar_top_margin=10):
        self.title_template = title or "{value} of {max_value}"
        self.cancellable = cancellable
        self.step = int(step or 0)
        self.indeterminate = indeterminate
        self.style = (style or "pyrevit").lower()
        self.width = 600 if (self.style == "pyrevit" and width == 460) else width
        self.bar_height = bar_height
        self.bar_top_margin = bar_top_margin
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
            _own(self._window)
            # Background priority for the first paint: Loaded handlers sit
            # below Render and the window would otherwise show up blank.
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

    # -- construction ------------------------------------------------------

    def _build(self):
        if self.style == "pyrevit":
            self._build_bar()
        else:
            self._build_dialog()

    def _build_bar(self):
        """Thin borderless strip near the top of the screen.

        Mirrors pyRevit's own ProgressBar.xaml: WindowStyle=None, no taskbar
        entry, ShowActivated=False so it never steals focus from Revit, and a
        single Grid holding the bar with the text overlaid on top of it and
        Cancel pinned left.
        """
        dark = theme_brush("pyRevitDarkBrush", DARK_FALLBACK)
        accent = theme_brush("pyRevitAccentBrush", ACCENT_FALLBACK)

        w = Window()
        w.Title = "Progress"
        w.Width = self.width
        w.Height = self.bar_height
        w.WindowStyle = getattr(WindowStyle, "None")
        w.ResizeMode = ResizeMode.NoResize
        w.ShowInTaskbar = False
        w.ShowActivated = False
        w.Topmost = bool(self.topmost)
        w.WindowStartupLocation = WindowStartupLocation.Manual
        if dark is not None:
            w.Background = dark
        w.Closing += self._on_closing

        # SystemParameters.WorkArea is in device-independent units, unlike
        # Screen.WorkingArea, so this stays correct on scaled displays.
        try:
            area = SystemParameters.WorkArea
            w.Left = area.Left + (area.Width - self.width) / 2.0
            w.Top = area.Top + self.bar_top_margin
        except Exception:
            w.WindowStartupLocation = WindowStartupLocation.CenterScreen

        grid = Grid()
        if dark is not None:
            grid.Background = dark

        self._bar = WpfProgressBar()
        self._bar.Minimum = 0
        self._bar.Maximum = 100
        self._bar.Value = 0
        self._bar.IsIndeterminate = bool(self.indeterminate)
        self._bar.BorderThickness = Thickness(0)
        self._bar.Background = Brushes.Transparent
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

        self._status_block = None      # single line: text is composed together

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
        # X on the titlebar reads as cancel; never block the close.
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
            bits = ["{0}%".format(self._percent())]
            if self.show_eta:
                eta = self._eta()
                if eta is not None:
                    bits.append("~{0} left".format(_fmt_eta(eta)))
            if self._status:
                bits.append(self._status)
            status_text = "   |   ".join(bits)

            if self._status_block is None:
                # strip style: one overlaid line, so merge the two
                self._title_block.Text = "{0}   -   {1}".format(
                    self._render_title(), status_text)
            else:
                self._title_block.Text = self._render_title()
                self._status_block.Text = status_text

            self._window.UpdateLayout()
            # Render priority sits ABOVE Input, so pumping at Render never
            # dispatches the Cancel click and the button looks dead. A
            # cancellable bar therefore has to pump at Background (below
            # Input) and accept that host-app clicks go through too; a
            # non-cancellable one stays at the safer Render default.
            pump(DispatcherPriority.Background if self.cancellable else None)
        except Exception:
            pass

    # -- convenience -------------------------------------------------------

    @classmethod
    def track(cls, items, title="{value} of {max_value}", cancellable=True,
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


# ---------------------------------------------------------------------------
# CheckList  (stand-in for forms.SelectFromList with multiselect=True)
# ---------------------------------------------------------------------------


class CheckList(object):
    """Modal checkbox list with a live filter. Returns the picked items."""

    def __init__(self, items, title="Select", name_attr=None,
                 button_name="OK", width=900, height=600,
                 checked_predicate=None, monospace=True):
        self.items = list(items)
        self.title = title
        self.name_attr = name_attr
        self.button_name = button_name
        self.width = width
        self.height = height
        self.checked_predicate = checked_predicate
        self.monospace = monospace

        self.result = None
        self._rows = []          # (CheckBox, item, label_lower)
        self._window = None
        self._panel = None
        self._filter = None
        self._count = None

    def _label(self, item):
        if self.name_attr:
            try:
                v = getattr(item, self.name_attr)
                return v() if callable(v) else str(v)
            except Exception:
                pass
        return str(item)

    def _build(self):
        w = Window()
        w.Title = self.title
        w.Width = self.width
        w.Height = self.height
        w.WindowStartupLocation = WindowStartupLocation.CenterScreen
        w.ShowInTaskbar = False

        dock = DockPanel()
        dock.LastChildFill = True
        dock.Margin = Thickness(12)

        # --- top: filter
        top = StackPanel()
        top.Orientation = Orientation.Horizontal
        top.Margin = Thickness(0, 0, 0, 8)
        lbl = TextBlock()
        lbl.Text = "Filter:"
        lbl.VerticalAlignment = VerticalAlignment.Center
        lbl.Margin = Thickness(0, 0, 6, 0)
        top.Children.Add(lbl)
        self._filter = TextBox()
        self._filter.Width = 320
        self._filter.TextChanged += self._on_filter
        top.Children.Add(self._filter)
        for text, handler in (("All", self._check_all),
                              ("None", self._check_none),
                              ("Invert", self._check_invert)):
            b = Button()
            b.Content = text
            b.Width = 60
            b.Margin = Thickness(6, 0, 0, 0)
            b.Click += handler
            top.Children.Add(b)
        self._count = TextBlock()
        self._count.VerticalAlignment = VerticalAlignment.Center
        self._count.Foreground = Brushes.Gray
        self._count.Margin = Thickness(12, 0, 0, 0)
        top.Children.Add(self._count)
        DockPanel.SetDock(top, Dock.Top)
        dock.Children.Add(top)

        # --- bottom: buttons
        bottom = StackPanel()
        bottom.Orientation = Orientation.Horizontal
        bottom.HorizontalAlignment = HorizontalAlignment.Right
        bottom.Margin = Thickness(0, 10, 0, 0)
        ok = Button()
        ok.Content = self.button_name
        ok.Width = 130
        ok.Height = 28
        ok.IsDefault = True
        ok.Click += self._on_ok
        cancel = Button()
        cancel.Content = "Cancel"
        cancel.Width = 90
        cancel.Height = 28
        cancel.IsCancel = True
        cancel.Margin = Thickness(8, 0, 0, 0)
        cancel.Click += self._on_cancel
        bottom.Children.Add(ok)
        bottom.Children.Add(cancel)
        DockPanel.SetDock(bottom, Dock.Bottom)
        dock.Children.Add(bottom)

        # --- middle: the list
        sv = ScrollViewer()
        sv.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        sv.HorizontalScrollBarVisibility = ScrollBarVisibility.Auto
        self._panel = StackPanel()
        mono = FontFamily("Consolas") if self.monospace else None
        for item in self.items:
            label = self._label(item)
            cb = CheckBox()
            cb.Content = label
            cb.Margin = Thickness(2)
            if mono is not None:
                cb.FontFamily = mono
            checked = True
            if self.checked_predicate is not None:
                try:
                    checked = bool(self.checked_predicate(item))
                except Exception:
                    checked = True
            cb.IsChecked = checked
            cb.Checked += self._on_toggle
            cb.Unchecked += self._on_toggle
            self._panel.Children.Add(cb)
            self._rows.append((cb, item, label.lower()))
        sv.Content = self._panel
        dock.Children.Add(sv)

        w.Content = dock
        self._window = w
        self._update_count()

    # -- events ------------------------------------------------------------

    def _on_filter(self, sender, args):
        q = (self._filter.Text or "").strip().lower()
        for cb, _item, low in self._rows:
            cb.Visibility = (Visibility.Visible if (not q or q in low)
                             else Visibility.Collapsed)

    def _visible_rows(self):
        return [(cb, i, l) for cb, i, l in self._rows
                if cb.Visibility == Visibility.Visible]

    def _check_all(self, sender, args):
        for cb, _i, _l in self._visible_rows():
            cb.IsChecked = True

    def _check_none(self, sender, args):
        for cb, _i, _l in self._visible_rows():
            cb.IsChecked = False

    def _check_invert(self, sender, args):
        for cb, _i, _l in self._visible_rows():
            cb.IsChecked = not bool(cb.IsChecked)

    def _on_toggle(self, sender, args):
        self._update_count()

    def _update_count(self):
        try:
            n = sum(1 for cb, _i, _l in self._rows if bool(cb.IsChecked))
            self._count.Text = "{0} of {1} checked".format(n, len(self._rows))
        except Exception:
            pass

    def _on_ok(self, sender, args):
        self.result = [item for cb, item, _l in self._rows
                       if bool(cb.IsChecked)]
        self._window.DialogResult = True
        self._window.Close()

    def _on_cancel(self, sender, args):
        self.result = None
        self._window.Close()

    # -- entry point -------------------------------------------------------

    @classmethod
    def show(cls, items, title="Select", name_attr=None, button_name="OK",
             width=900, height=600, checked_predicate=None, monospace=True,
             **_ignored):
        if not items:
            return None
        dlg = cls(items, title=title, name_attr=name_attr,
                  button_name=button_name, width=width, height=height,
                  checked_predicate=checked_predicate, monospace=monospace)
        dlg._build()
        _own(dlg._window)
        try:
            dlg._window.ShowDialog()
        except Exception:
            dlg._window.Show()
            pump(DispatcherPriority.Background)
        return dlg.result


# ---------------------------------------------------------------------------
# pick_option  (stand-in for forms.CommandSwitchWindow)
# ---------------------------------------------------------------------------


def pick_option(options, message="Pick one", title="Options", width=460):
    """One button per option. Returns the chosen string, or None."""
    options = list(options)
    if not options:
        return None

    state = {"choice": None}

    w = Window()
    w.Title = title
    w.Width = width
    w.SizeToContent = SizeToContent.Height
    w.WindowStyle = WindowStyle.ToolWindow
    w.ResizeMode = ResizeMode.NoResize
    w.WindowStartupLocation = WindowStartupLocation.CenterScreen
    w.ShowInTaskbar = False

    root = StackPanel()
    root.Margin = Thickness(16)

    if message:
        tb = TextBlock()
        tb.Text = message
        tb.TextWrapping = TextWrapping.Wrap
        tb.Margin = Thickness(0, 0, 0, 12)
        root.Children.Add(tb)

    def make_handler(opt):
        def handler(sender, args):
            state["choice"] = opt
            w.DialogResult = True
            w.Close()
        return handler

    for i, opt in enumerate(options):
        b = Button()
        b.Content = str(opt)
        b.Height = 32
        b.Margin = Thickness(0, 0, 0, 6)
        b.Click += make_handler(opt)
        if i == 0:
            b.IsDefault = True
        root.Children.Add(b)

    cancel = Button()
    cancel.Content = "Cancel"
    cancel.Height = 28
    cancel.Margin = Thickness(0, 8, 0, 0)
    cancel.IsCancel = True
    cancel.Click += lambda s, a: w.Close()
    root.Children.Add(cancel)

    w.Content = root
    _own(w)
    try:
        w.ShowDialog()
    except Exception:
        w.Show()
        pump(DispatcherPriority.Background)
    return state["choice"]


# ---------------------------------------------------------------------------
# message boxes  (stand-in for forms.alert)
# ---------------------------------------------------------------------------


def alert(message, title="Message", warning=False):
    """Blocking OK box. WPF MessageBox, so no Revit dependency."""
    icon = MessageBoxImage.Warning if warning else MessageBoxImage.Information
    try:
        MessageBox.Show(u"{0}".format(message), u"{0}".format(title),
                        MessageBoxButton.OK, icon)
    except Exception:
        pass


def ask_yes_no(message, title="Confirm"):
    """Blocking Yes/No box. Returns True only on Yes."""
    try:
        r = MessageBox.Show(u"{0}".format(message), u"{0}".format(title),
                            MessageBoxButton.YesNo, MessageBoxImage.Question)
        return r == MessageBoxResult.Yes
    except Exception:
        return False

# -*- coding: utf-8 -*-
"""checklist - CPython-safe replacements for the modal pyRevit forms.

``forms.SelectFromList`` and ``forms.CommandSwitchWindow`` are XAML-backed the
same way ProgressBar is, so they fail on the CPython engine too. These are
built in code.

Named ``checklist`` rather than ``dialogs`` because ``dialogs.py`` in this
package is the ``WpfDialogBase`` hierarchy - different concern, same obvious
filename.

Deliberately contains no message boxes: ``forms.alert`` / ``forms.confirm``
already cover those. Note that they take ``(title, message)``, the opposite
order to pyrevit's ``forms.alert``.
"""

__version__ = "1.5.0"
__all__ = ["CheckList", "pick_option"]

try:
    import clr
    for _asm in ("PresentationFramework", "PresentationCore", "WindowsBase",
                 "System.Windows.Forms"):
        try:
            clr.AddReference(_asm)
        except Exception:
            pass
except ImportError:
    pass

from System.Windows import (Window, Thickness, WindowStyle, ResizeMode,
                            SizeToContent, WindowStartupLocation,
                            HorizontalAlignment, VerticalAlignment,
                            TextWrapping, FontWeights, Visibility)
from System.Windows.Controls import (StackPanel, TextBlock, Button, CheckBox,
                                     ScrollViewer, TextBox, DockPanel, Dock,
                                     Orientation, ScrollBarVisibility)
from System.Windows.Media import Brushes, FontFamily
from System.Windows.Threading import DispatcherPriority

from anongee_toolkit.ui.pump import pump
from anongee_toolkit.ui.hostwnd import revit_handle


def _own(window):
    """Parent a dialog to Revit so it cannot hide behind the main window."""
    try:
        from System import IntPtr
        from System.Windows.Interop import WindowInteropHelper
        h = revit_handle()
        if h is not None and h != IntPtr.Zero:
            WindowInteropHelper(window).Owner = h
            return True
    except Exception:
        pass
    return False


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

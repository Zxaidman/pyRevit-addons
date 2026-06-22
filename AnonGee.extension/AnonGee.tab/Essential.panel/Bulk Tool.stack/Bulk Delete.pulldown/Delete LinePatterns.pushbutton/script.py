#! python3
# -*- coding: utf-8 -*-

# ── Per-button config — the ONLY line that differs between the three Bulk
#    Delete pushbuttons. Valid values: "fillpattern" | "linepattern" | "linestyle"
TARGET = "linepattern"

import os
import clr
import System

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (
    FilteredElementCollector, FillPatternElement, LinePatternElement,
    BuiltInCategory, Transaction
)

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import BitmapImage
from System.IO import FileStream, FileMode, FileAccess
from System.Windows.Controls import ListBoxItem, CheckBox, TextBlock
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System import Action, Uri, UriKind
from System.Windows import (
    Visibility, Thickness, MessageBox, MessageBoxButton, MessageBoxImage, MessageBoxResult
)

doc       = __revit__.ActiveUIDocument.Document
LOCAL_DIR = os.path.dirname(__file__)

# ── traceback fallback (stripped CPython3 stdlib) ─────────────────────────────
try:
    import traceback as _tb
    def _fmt_exc():
        return _tb.format_exc()
except ImportError:
    import sys
    def _fmt_exc():
        t, v, _ = sys.exc_info()
        return "{}: {}".format(t.__name__ if t else "Error", v)


# ── Target providers — collect returns [(name, ElementId)] ────────────────────
def _collect_fillpatterns():
    items = []
    for el in FilteredElementCollector(doc).OfClass(FillPatternElement).ToElements():
        if el is None:
            continue
        try:
            nm = el.Name
        except Exception:
            continue
        if nm:
            items.append((nm, el.Id))
    return items


def _collect_linepatterns():
    items = []
    for el in FilteredElementCollector(doc).OfClass(LinePatternElement).ToElements():
        if el is None:
            continue
        try:
            nm = el.Name
        except Exception:
            continue
        if nm:
            items.append((nm, el.Id))
    return items


def _collect_linestyles():
    items = []
    cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    for sub in cat.SubCategories:
        if sub is None:
            continue
        try:
            nm = sub.Name
        except Exception:
            continue
        if nm:
            items.append((nm, sub.Id))
    return items


PROVIDERS = {
    "fillpattern": {
        "title":   "Delete Fill Patterns",
        "noun":    "fill pattern",
        "txn":     "AnonGee · Delete Fill Patterns",
        "collect": _collect_fillpatterns,
    },
    "linepattern": {
        "title":   "Delete Line Patterns",
        "noun":    "line pattern",
        "txn":     "AnonGee · Delete Line Patterns",
        "collect": _collect_linepatterns,
    },
    "linestyle": {
        "title":   "Delete Line Styles",
        "noun":    "line style",
        "txn":     "AnonGee · Delete Line Styles",
        "collect": _collect_linestyles,
    },
}

CFG = PROVIDERS[TARGET]


# ──────────────────────────────────────────────────────────────────────────────
# Dialog
# ──────────────────────────────────────────────────────────────────────────────
class BulkDeleteDialog(object):

    def __init__(self):
        xaml_path = os.path.join(LOCAL_DIR, "ui.xaml")
        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        try:
            self.window = XamlReader.Load(stream)
        finally:
            stream.Close()
        self._set_window_icon()
        self._bind()
        self._populate()

    def _set_window_icon(self):
        icon_path = os.path.join(LOCAL_DIR, "icon.png")
        if os.path.exists(icon_path):
            self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

    def _bind(self):
        w = self.window
        self._search        = w.FindName("SearchBox")
        self._search_ph     = w.FindName("SearchPlaceholder")
        self._items_list    = w.FindName("ItemsList")
        self._btn_all       = w.FindName("BtnAll")
        self._btn_none      = w.FindName("BtnNone")
        self._btn_delete    = w.FindName("BtnDelete")
        self._btn_close     = w.FindName("BtnClose")
        self._badge_info    = w.FindName("BadgeInfo")
        self._badge_success = w.FindName("BadgeSuccess")
        self._badge_error   = w.FindName("BadgeError")
        self._info_text     = w.FindName("InfoText")
        self._success_text  = w.FindName("SuccessText")
        self._error_text    = w.FindName("ErrorText")
        self._live_count    = w.FindName("LiveCount")

        self._search.TextChanged += self._on_search_changed
        self._search.GotFocus    += lambda s, e: self._set_ph(False)
        self._search.LostFocus   += lambda s, e: self._set_ph(not self._search.Text)
        self._btn_all.Click      += self._on_all
        self._btn_none.Click     += self._on_none
        self._btn_delete.Click   += self._on_delete
        self._btn_close.Click    += lambda s, e: self.window.Close()

    def _populate(self):
        self._targets = CFG["collect"]()
        self.window.Title = CFG["title"]
        self._fill_list()
        self._update_count()
        self._show_info("{} {}s — none selected".format(len(self._targets), CFG["noun"]))

    def _fill_list(self):
        self._items_list.Items.Clear()
        for name, handle in sorted(self._targets, key=lambda p: p[0].lower()):
            tb = TextBlock()
            tb.Text = name
            chk = CheckBox()
            chk.Content   = tb
            chk.IsChecked = False
            chk.Margin    = Thickness(2)
            chk.Click    += lambda s, e: self._update_count()
            item = ListBoxItem()
            item.Content = chk
            item.Tag     = handle
            self._items_list.Items.Add(item)

    # ── search ──
    def _set_ph(self, visible):
        self._search_ph.Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def _on_search_changed(self, sender, args):
        self._set_ph(not self._search.Text)
        q = (self._search.Text or "").lower()
        for item in self._items_list.Items:
            name = item.Content.Content.Text.lower()
            item.Visibility = Visibility.Visible if q in name else Visibility.Collapsed

    # ── all / none (visible items only) ──
    def _on_all(self, sender, args):
        for item in self._items_list.Items:
            if item.Visibility == Visibility.Visible:
                item.Content.IsChecked = True
        self._update_count()

    def _on_none(self, sender, args):
        for item in self._items_list.Items:
            item.Content.IsChecked = False
        self._update_count()

    def _checked_items(self):
        out = []
        for item in self._items_list.Items:
            if item.Content.IsChecked:
                out.append((item.Content.Content.Text, item.Tag))
        return out

    def _update_count(self):
        sel = sum(1 for item in self._items_list.Items if item.Content.IsChecked)
        self._live_count.Text = "{} of {} selected".format(sel, self._items_list.Items.Count)

    # ── badges ──
    def _show_info(self, msg):
        self._info_text.Text           = msg
        self._badge_info.Visibility    = Visibility.Visible
        self._badge_success.Visibility = Visibility.Collapsed
        self._badge_error.Visibility   = Visibility.Collapsed

    def _show_success(self, msg):
        self._success_text.Text        = msg
        self._badge_info.Visibility    = Visibility.Collapsed
        self._badge_success.Visibility = Visibility.Visible
        self._badge_error.Visibility   = Visibility.Collapsed

    def _show_error(self, msg):
        self._error_text.Text          = msg
        self._badge_info.Visibility    = Visibility.Collapsed
        self._badge_success.Visibility = Visibility.Collapsed
        self._badge_error.Visibility   = Visibility.Visible

    def _flush_ui(self):
        Dispatcher.CurrentDispatcher.Invoke(
            Action(lambda: None), DispatcherPriority.Background)

    # ── delete ──
    def _on_delete(self, sender, args):
        try:
            self._do_delete()
        except Exception:
            tb = _fmt_exc().strip().splitlines()
            self._show_error(tb[-1] if tb else "Unknown error")
            self._btn_delete.IsEnabled = True

    def _do_delete(self):
        selected = self._checked_items()
        if not selected:
            self._show_error("Select at least one {} to delete.".format(CFG["noun"]))
            return

        confirm = MessageBox.Show(
            "Permanently delete {} {}(s)?\n\nThis cannot be undone (other than Ctrl+Z).".format(
                len(selected), CFG["noun"]),
            CFG["title"], MessageBoxButton.YesNo, MessageBoxImage.Warning)
        if confirm != MessageBoxResult.Yes:
            return

        self._show_info("Deleting {} {}(s)...".format(len(selected), CFG["noun"]))
        self._btn_delete.IsEnabled = False
        self._flush_ui()

        done = skipped = 0
        t = Transaction(doc, CFG["txn"])
        t.Start()
        try:
            for _name, handle in selected:
                try:
                    doc.Delete(handle)
                    done += 1
                except Exception:
                    skipped += 1   # system-locked / in-use
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise

        msg = "Deleted {} {}(s)".format(done, CFG["noun"])
        if skipped:
            msg += " ({} skipped — locked/in-use)".format(skipped)
        self._show_success(msg)

        # Refresh list + count to drop the removed items
        self._targets = CFG["collect"]()
        self._fill_list()
        self._update_count()
        self._btn_delete.IsEnabled = True

    def show(self):
        self.window.ShowDialog()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
def run():
    if not CFG["collect"]():
        MessageBox.Show(
            "No {}s found in this document.".format(CFG["noun"]),
            CFG["title"], MessageBoxButton.OK, MessageBoxImage.Warning)
        return
    BulkDeleteDialog().show()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        MessageBox.Show(
            _fmt_exc()[-3000:],
            "Bulk Delete — Unhandled Error",
            MessageBoxButton.OK, MessageBoxImage.Error)

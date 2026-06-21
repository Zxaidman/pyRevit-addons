#! python3
# -*- coding: utf-8 -*-

# ── Per-button config — the ONLY line that differs between the three Bulk
#    Rename pushbuttons. Valid values: "fillpattern" | "linepattern" | "linestyle"
TARGET = "linestyle"

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
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System import Action, Uri, UriKind
from System.Windows import Visibility, MessageBox, MessageBoxButton, MessageBoxImage

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


# ── Case-insensitive replace (no re module in this engine) ────────────────────
def _replace_cs(text, find, repl):
    """Case-sensitive replace-all. Returns (new_text, changed)."""
    if find in text:
        return text.replace(find, repl), True
    return text, False


def _replace_ci(text, find, repl):
    """Case-insensitive replace-all. Returns (new_text, changed)."""
    low_t, low_f, n = text.lower(), find.lower(), len(find)
    out, i, changed = [], 0, False
    while True:
        j = low_t.find(low_f, i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        out.append(repl)
        i = j + n
        changed = True
    return "".join(out), changed


# ── Target providers ──────────────────────────────────────────────────────────
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
            items.append((nm, el))
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
            items.append((nm, el))
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
            items.append((nm, sub.Id))   # handle = subcategory ElementId
    return items


def _apply_element(handle, new_name):
    handle.Name = new_name


def _apply_linestyle(handle, new_name):
    el = doc.GetElement(handle)
    if el is not None:
        el.Name = new_name


PROVIDERS = {
    "fillpattern": {
        "title":   "Rename Fill Patterns",
        "noun":    "fill pattern",
        "txn":     "AnonGee · Rename Fill Patterns",
        "collect": _collect_fillpatterns,
        "apply":   _apply_element,
    },
    "linepattern": {
        "title":   "Rename Line Patterns",
        "noun":    "line pattern",
        "txn":     "AnonGee · Rename Line Patterns",
        "collect": _collect_linepatterns,
        "apply":   _apply_element,
    },
    "linestyle": {
        "title":   "Rename Line Styles",
        "noun":    "line style",
        "txn":     "AnonGee · Rename Line Styles",
        "collect": _collect_linestyles,
        "apply":   _apply_linestyle,
    },
}

CFG = PROVIDERS[TARGET]


# ──────────────────────────────────────────────────────────────────────────────
# Dialog
# ──────────────────────────────────────────────────────────────────────────────
class BulkRenameDialog(object):

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
        self._find          = w.FindName("FindBox")
        self._find_ph       = w.FindName("FindPlaceholder")
        self._replace       = w.FindName("ReplaceBox")
        self._replace_ph    = w.FindName("ReplacePlaceholder")
        self._match_case    = w.FindName("ChkMatchCase")
        self._names_combo   = w.FindName("NamesCombo")
        self._btn_rename    = w.FindName("BtnRename")
        self._btn_close     = w.FindName("BtnClose")
        self._badge_info    = w.FindName("BadgeInfo")
        self._badge_success = w.FindName("BadgeSuccess")
        self._badge_error   = w.FindName("BadgeError")
        self._info_text     = w.FindName("InfoText")
        self._success_text  = w.FindName("SuccessText")
        self._error_text    = w.FindName("ErrorText")
        self._live_count    = w.FindName("LiveCount")

        self._find.TextChanged       += self._on_find_changed
        self._find.GotFocus          += lambda s, e: self._set_ph(self._find_ph, False)
        self._find.LostFocus         += lambda s, e: self._sync_ph(self._find, self._find_ph)
        self._replace.TextChanged    += lambda s, e: self._sync_ph(self._replace, self._replace_ph)
        self._replace.GotFocus       += lambda s, e: self._set_ph(self._replace_ph, False)
        self._replace.LostFocus      += lambda s, e: self._sync_ph(self._replace, self._replace_ph)
        self._match_case.Click       += lambda s, e: self._update_count()
        self._btn_rename.Click       += self._on_rename
        self._btn_close.Click        += lambda s, e: self.window.Close()

    def _populate(self):
        self._targets = CFG["collect"]()
        self.window.Title = CFG["title"]
        self._fill_names_combo()
        self._update_count()
        self._show_info("{} {}s in model".format(len(self._targets), CFG["noun"]))

    def _fill_names_combo(self):
        """Reference-only list of every current name, sorted, for the user to
        browse while deciding what to find/replace."""
        self._names_combo.Items.Clear()
        for nm in sorted((nm for nm, _ in self._targets), key=lambda s: s.lower()):
            self._names_combo.Items.Add(nm)
        self._names_combo.SelectedIndex = -1

    # ── placeholders ──
    def _set_ph(self, ph, visible):
        ph.Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def _sync_ph(self, box, ph):
        self._set_ph(ph, not box.Text)

    def _on_find_changed(self, sender, args):
        self._sync_ph(self._find, self._find_ph)
        self._update_count()

    # ── live match count ──
    def _match_count(self):
        find = self._find.Text or ""
        if not find:
            return None
        if self._match_case.IsChecked:
            return sum(1 for nm, _ in self._targets if find in nm)
        low = find.lower()
        return sum(1 for nm, _ in self._targets if low in nm.lower())

    def _update_count(self):
        n = self._match_count()
        if n is None:
            self._live_count.Text = "{} {}s".format(len(self._targets), CFG["noun"])
        else:
            self._live_count.Text = "{} match{}".format(n, "" if n == 1 else "es")

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

    # ── rename ──
    def _on_rename(self, sender, args):
        try:
            self._do_rename()
        except Exception:
            tb = _fmt_exc().strip().splitlines()
            self._show_error(tb[-1] if tb else "Unknown error")
            self._btn_rename.IsEnabled = True

    def _do_rename(self):
        find = self._find.Text or ""
        repl = self._replace.Text or ""
        if not find:
            self._show_error("Enter the text to find.")
            return

        match_case = bool(self._match_case.IsChecked)
        replace = _replace_cs if match_case else _replace_ci

        pending = []
        for name, handle in self._targets:
            new_name, changed = replace(name, find, repl)
            if changed and new_name and new_name != name:
                pending.append((handle, name, new_name))

        if not pending:
            self._show_error("No {} names match '{}'.".format(CFG["noun"], find))
            return

        self._show_info("Renaming {} {}(s)...".format(len(pending), CFG["noun"]))
        self._btn_rename.IsEnabled = False
        self._flush_ui()

        done = skipped = 0
        t = Transaction(doc, CFG["txn"])
        t.Start()
        try:
            for handle, _old, new_name in pending:
                try:
                    CFG["apply"](handle, new_name)
                    done += 1
                except Exception:
                    skipped += 1   # system-locked or duplicate name
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise

        msg = "Renamed {} {}(s)".format(done, CFG["noun"])
        if skipped:
            msg += " ({} skipped — locked/duplicate)".format(skipped)
        self._show_success(msg)

        # Refresh cached targets + reference list + live count to reflect new names
        self._targets = CFG["collect"]()
        self._fill_names_combo()
        self._update_count()
        self._btn_rename.IsEnabled = True

    def show(self):
        self.window.ShowDialog()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
def run():
    targets = CFG["collect"]()
    if not targets:
        MessageBox.Show(
            "No {}s found in this document.".format(CFG["noun"]),
            CFG["title"], MessageBoxButton.OK, MessageBoxImage.Warning)
        return
    BulkRenameDialog().show()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        MessageBox.Show(
            _fmt_exc()[-3000:],
            "Bulk Rename — Unhandled Error",
            MessageBoxButton.OK, MessageBoxImage.Error)

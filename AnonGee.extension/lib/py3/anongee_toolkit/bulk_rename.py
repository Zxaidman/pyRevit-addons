# -*- coding: utf-8 -*-
import os
import System
from System import Action, Uri, UriKind
from System.Windows import Visibility
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System.Windows.Media.Imaging import BitmapImage

from Autodesk.Revit.DB import (
    FilteredElementCollector, FillPatternElement, LinePatternElement, BuiltInCategory
)

from anongee_toolkit.core import get_current_doc
from anongee_toolkit.ui import load_xaml
from anongee_toolkit.forms import error, info
from anongee_toolkit.transaction import RevitTransaction

# --- Case-Insensitive String Utilities ---

def replace_cs(text, find, repl):
    """Case-sensitive replace-all. Returns (new_text, changed)."""
    if find in text:
        return text.replace(find, repl), True
    return text, False

def replace_ci(text, find, repl):
    """Case-insensitive replace-all without using the unavailable 're' module."""
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

# --- Target Collectors & Appliers ---

def collect_fillpatterns(doc):
    return [(el.Name, el) for el in FilteredElementCollector(doc).OfClass(FillPatternElement).ToElements() if el and el.Name]

def collect_linepatterns(doc):
    return [(el.Name, el) for el in FilteredElementCollector(doc).OfClass(LinePatternElement).ToElements() if el and el.Name]

def collect_linestyles(doc):
    items = []
    cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    if cat:
        for sub in cat.SubCategories:
            if sub and sub.Name:
                items.append((sub.Name, sub.Id))
    return items

def apply_element(doc, handle, new_name):
    handle.Name = new_name

def apply_linestyle(doc, handle, new_name):
    el = doc.GetElement(handle)
    if el is not None:
        el.Name = new_name

PROVIDERS = {
    "fillpattern": {
        "title": "Rename Fill Patterns",
        "noun": "fill pattern",
        "txn": "AnonGee · Rename Fill Patterns",
        "collect": collect_fillpatterns,
        "apply": apply_element,
    },
    "linepattern": {
        "title": "Rename Line Patterns",
        "noun": "line pattern",
        "txn": "AnonGee · Rename Line Patterns",
        "collect": collect_linepatterns,
        "apply": apply_element,
    },
    "linestyle": {
        "title": "Rename Line Styles",
        "noun": "line style",
        "txn": "AnonGee · Rename Line Styles",
        "collect": collect_linestyles,
        "apply": apply_linestyle,
    },
}

class GenericBulkRenameDialog(object):
    """
    A generic UI engine for Bulk Rename operations.
    """
    def __init__(self, target_type, ui_dir, doc=None):
        self.doc = doc if doc else get_current_doc()
        self.cfg = PROVIDERS.get(target_type)
        if not self.cfg:
            raise ValueError("Invalid target_type. Must be one of: {}".format(list(PROVIDERS.keys())))

        # Load UI
        xaml_path = os.path.join(ui_dir, "ui.xaml")
        self.window = load_xaml(xaml_path)

        icon_path = os.path.join(ui_dir, "icon.png")
        if os.path.exists(icon_path):
            self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

        self._bind()
        self._populate()

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
        self._targets = self.cfg["collect"](self.doc)
        self.window.Title = self.cfg["title"]
        self._fill_names_combo()
        self._update_count()
        self._show_info("{} {}s in model".format(len(self._targets), self.cfg["noun"]))

    def _fill_names_combo(self):
        self._names_combo.Items.Clear()
        for nm in sorted((nm for nm, _ in self._targets), key=lambda s: s.lower()):
            self._names_combo.Items.Add(nm)
        self._names_combo.SelectedIndex = -1

    def _set_ph(self, ph, visible):
        ph.Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def _sync_ph(self, box, ph):
        self._set_ph(ph, not box.Text)

    def _on_find_changed(self, sender, args):
        self._sync_ph(self._find, self._find_ph)
        self._update_count()

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
            self._live_count.Text = "{} {}s".format(len(self._targets), self.cfg["noun"])
        else:
            self._live_count.Text = "{} match{}".format(n, "" if n == 1 else "es")

    def _show_info(self, msg):
        self._info_text.Text = msg
        self._badge_info.Visibility = Visibility.Visible
        self._badge_success.Visibility = Visibility.Collapsed
        self._badge_error.Visibility = Visibility.Collapsed

    def _show_success(self, msg):
        self._success_text.Text = msg
        self._badge_info.Visibility = Visibility.Collapsed
        self._badge_success.Visibility = Visibility.Visible
        self._badge_error.Visibility = Visibility.Collapsed

    def _show_error(self, msg):
        self._error_text.Text = msg
        self._badge_info.Visibility = Visibility.Collapsed
        self._badge_success.Visibility = Visibility.Collapsed
        self._badge_error.Visibility = Visibility.Visible

    def _flush_ui(self):
        Dispatcher.CurrentDispatcher.Invoke(Action(lambda: None), DispatcherPriority.Background)

    def _on_rename(self, sender, args):
        find = self._find.Text or ""
        repl = self._replace.Text or ""
        if not find:
            self._show_error("Enter the text to find.")
            return

        match_case = bool(self._match_case.IsChecked)
        replace_func = replace_cs if match_case else replace_ci

        pending = []
        for name, handle in self._targets:
            new_name, changed = replace_func(name, find, repl)
            if changed and new_name and new_name != name:
                pending.append((handle, name, new_name))

        if not pending:
            self._show_error("No {} names match '{}'.".format(self.cfg["noun"], find))
            return

        self._show_info("Renaming {} {}(s)...".format(len(pending), self.cfg["noun"]))
        self._btn_rename.IsEnabled = False
        self._flush_ui()

        done = 0
        skipped = 0

        # Using our fail-safe transaction context manager
        with RevitTransaction(self.cfg["txn"], self.doc) as t:
            for handle, _old, new_name in pending:
                try:
                    self.cfg["apply"](self.doc, handle, new_name)
                    done += 1
                except Exception as e:
                    print("Failed to rename element to '{}': {}".format(new_name, str(e)))
                    skipped += 1 # system-locked or duplicate name

        msg = "Renamed {} {}(s)".format(done, self.cfg["noun"])
        if skipped:
            msg += " ({} skipped — locked/duplicate)".format(skipped)
            
        self._show_success(msg)
        self._targets = self.cfg["collect"](self.doc)
        self._fill_names_combo()
        self._update_count()
        self._btn_rename.IsEnabled = True

    def show(self):
        if not self._targets:
            error(self.cfg["title"], "No {}s found in this document.".format(self.cfg["noun"]))
            return
        self.window.ShowDialog()
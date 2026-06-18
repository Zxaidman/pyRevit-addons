# -*- coding: utf-8 -*-
"""
Generic bulk-rename dialog engine for Revit graphic style elements.

Supports fill patterns, line patterns, and line styles through a single
parameterised dialog class driven by a provider configuration dictionary.
"""
import os

import System
from System import Action, Uri, UriKind
from System.Windows import Visibility
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System.Windows.Media.Imaging import BitmapImage

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FillPatternElement,
    LinePatternElement,
    BuiltInCategory,
)

from anongee_toolkit.revit.application import get_current_doc
from anongee_toolkit.revit.transactions import RevitTransaction
from anongee_toolkit.ui.xaml import load_xaml
from anongee_toolkit.ui.forms import error


# ---------------------------------------------------------------------------
# String replacement helpers
# ---------------------------------------------------------------------------

def replace_case_sensitive(text, find, replacement):
    """
    Replace all occurrences of *find* in *text* (case-sensitive).

    Returns:
        tuple[str, bool]: ``(new_text, was_changed)``
    """
    if find in text:
        return text.replace(find, replacement), True
    return text, False


def replace_case_insensitive(text, find, replacement):
    """
    Replace all occurrences of *find* in *text* (case-insensitive), without
    using the ``re`` module so it works under IronPython 2 as well.

    Returns:
        tuple[str, bool]: ``(new_text, was_changed)``
    """
    lower_text, lower_find, n = text.lower(), find.lower(), len(find)
    parts, i, changed = [], 0, False
    while True:
        j = lower_text.find(lower_find, i)
        if j < 0:
            parts.append(text[i:])
            break
        parts.append(text[i:j])
        parts.append(replacement)
        i = j + n
        changed = True
    return "".join(parts), changed


# ---------------------------------------------------------------------------
# Element collectors and name appliers
# ---------------------------------------------------------------------------

def _collect_fillpatterns(doc):
    return [
        (el.Name, el)
        for el in FilteredElementCollector(doc).OfClass(FillPatternElement).ToElements()
        if el and el.Name
    ]


def _collect_linepatterns(doc):
    return [
        (el.Name, el)
        for el in FilteredElementCollector(doc).OfClass(LinePatternElement).ToElements()
        if el and el.Name
    ]


def _collect_linestyles(doc):
    items = []
    cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    if cat:
        for sub in cat.SubCategories:
            if sub and sub.Name:
                items.append((sub.Name, sub.Id))
    return items


def _apply_element_name(doc, handle, new_name):
    handle.Name = new_name


def _apply_linestyle_name(doc, handle, new_name):
    el = doc.GetElement(handle)
    if el is not None:
        el.Name = new_name


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "fillpattern": {
        "title":   "Rename Fill Patterns",
        "noun":    "fill pattern",
        "txn":     "AnonGee · Rename Fill Patterns",
        "collect": _collect_fillpatterns,
        "apply":   _apply_element_name,
    },
    "linepattern": {
        "title":   "Rename Line Patterns",
        "noun":    "line pattern",
        "txn":     "AnonGee · Rename Line Patterns",
        "collect": _collect_linepatterns,
        "apply":   _apply_element_name,
    },
    "linestyle": {
        "title":   "Rename Line Styles",
        "noun":    "line style",
        "txn":     "AnonGee · Rename Line Styles",
        "collect": _collect_linestyles,
        "apply":   _apply_linestyle_name,
    },
}


# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------

class GenericBulkRenameDialog(object):
    """
    Reusable WPF dialog for bulk-renaming graphic style elements via
    find-and-replace.

    Args:
        target_type (str): One of ``"fillpattern"``, ``"linepattern"``,
            ``"linestyle"``.
        ui_dir (str): Directory containing ``ui.xaml`` and ``icon.png``.
        doc (Document, optional): Defaults to the active document.

    Raises:
        ValueError: If *target_type* is not a registered provider key.
    """

    def __init__(self, target_type, ui_dir, doc=None):
        self._doc = doc or get_current_doc()
        self._cfg = _PROVIDERS.get(target_type)
        if not self._cfg:
            raise ValueError(
                "Unknown target_type '{}'. Choose from: {}".format(
                    target_type, list(_PROVIDERS)
                )
            )

        self.window = load_xaml(os.path.join(ui_dir, "ui.xaml"))

        icon_path = os.path.join(ui_dir, "icon.png")
        if os.path.exists(icon_path):
            self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

        self._bind_controls()
        self._populate()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _bind_controls(self):
        w = self.window
        self._find_box      = w.FindName("FindBox")
        self._find_ph       = w.FindName("FindPlaceholder")
        self._replace_box   = w.FindName("ReplaceBox")
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

        self._find_box.TextChanged    += self._on_find_changed
        self._find_box.GotFocus       += lambda s, e: self._set_placeholder(self._find_ph, False)
        self._find_box.LostFocus      += lambda s, e: self._sync_placeholder(self._find_box, self._find_ph)
        self._replace_box.GotFocus    += lambda s, e: self._set_placeholder(self._replace_ph, False)
        self._replace_box.LostFocus   += lambda s, e: self._sync_placeholder(self._replace_box, self._replace_ph)
        self._replace_box.TextChanged += lambda s, e: self._sync_placeholder(self._replace_box, self._replace_ph)
        self._match_case.Click        += lambda s, e: self._update_count()
        self._btn_rename.Click        += self._on_rename
        self._btn_close.Click         += lambda s, e: self.window.Close()

    def _populate(self):
        self._targets = self._cfg["collect"](self._doc)
        self.window.Title = self._cfg["title"]
        self._rebuild_names_combo()
        self._update_count()
        self._show_info("{} {}s in model".format(len(self._targets), self._cfg["noun"]))

    def _rebuild_names_combo(self):
        self._names_combo.Items.Clear()
        for name, _ in sorted(self._targets, key=lambda t: t[0].lower()):
            self._names_combo.Items.Add(name)
        self._names_combo.SelectedIndex = -1

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _set_placeholder(self, placeholder, visible):
        placeholder.Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def _sync_placeholder(self, box, placeholder):
        self._set_placeholder(placeholder, not box.Text)

    def _on_find_changed(self, sender, args):
        self._sync_placeholder(self._find_box, self._find_ph)
        self._update_count()

    def _on_rename(self, sender, args):
        find = self._find_box.Text or ""
        replacement = self._replace_box.Text or ""
        if not find:
            self._show_error("Enter the text to find.")
            return

        replace_fn = (
            replace_case_sensitive if self._match_case.IsChecked
            else replace_case_insensitive
        )

        pending = []
        for name, handle in self._targets:
            new_name, changed = replace_fn(name, find, replacement)
            if changed and new_name and new_name != name:
                pending.append((handle, name, new_name))

        if not pending:
            self._show_error(
                "No {} names match '{}'.".format(self._cfg["noun"], find)
            )
            return

        self._show_info("Renaming {} {}(s)…".format(len(pending), self._cfg["noun"]))
        self._btn_rename.IsEnabled = False
        self._flush_ui()

        done, skipped = 0, 0
        with RevitTransaction(self._cfg["txn"], self._doc):
            for handle, _old_name, new_name in pending:
                try:
                    self._cfg["apply"](self._doc, handle, new_name)
                    done += 1
                except Exception as exc:
                    print("Failed to rename to '{}': {}".format(new_name, exc))
                    skipped += 1

        msg = "Renamed {} {}(s)".format(done, self._cfg["noun"])
        if skipped:
            msg += " ({} skipped — locked/duplicate name)".format(skipped)
        self._show_success(msg)

        self._targets = self._cfg["collect"](self._doc)
        self._rebuild_names_combo()
        self._update_count()
        self._btn_rename.IsEnabled = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _count_matches(self):
        find = self._find_box.Text or ""
        if not find:
            return None
        if self._match_case.IsChecked:
            return sum(1 for name, _ in self._targets if find in name)
        lower_find = find.lower()
        return sum(1 for name, _ in self._targets if lower_find in name.lower())

    def _update_count(self):
        n = self._count_matches()
        if n is None:
            self._live_count.Text = "{} {}s".format(
                len(self._targets), self._cfg["noun"]
            )
        else:
            self._live_count.Text = "{} match{}".format(n, "" if n == 1 else "es")

    def _show_info(self, msg):
        self._info_text.Text = msg
        self._badge_info.Visibility    = Visibility.Visible
        self._badge_success.Visibility = Visibility.Collapsed
        self._badge_error.Visibility   = Visibility.Collapsed

    def _show_success(self, msg):
        self._success_text.Text = msg
        self._badge_info.Visibility    = Visibility.Collapsed
        self._badge_success.Visibility = Visibility.Visible
        self._badge_error.Visibility   = Visibility.Collapsed

    def _show_error(self, msg):
        self._error_text.Text = msg
        self._badge_info.Visibility    = Visibility.Collapsed
        self._badge_success.Visibility = Visibility.Collapsed
        self._badge_error.Visibility   = Visibility.Visible

    def _flush_ui(self):
        Dispatcher.CurrentDispatcher.Invoke(
            Action(lambda: None), DispatcherPriority.Background
        )

    def show(self):
        """Open the dialog, or show an alert if no targets exist in the document."""
        if not self._targets:
            error(
                self._cfg["title"],
                "No {}s found in this document.".format(self._cfg["noun"]),
            )
            return
        self.window.ShowDialog()

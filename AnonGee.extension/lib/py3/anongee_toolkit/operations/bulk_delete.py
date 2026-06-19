# -*- coding: utf-8 -*-
"""
Generic bulk-delete dialog engine for Revit graphic style elements.

Supports fill patterns, line patterns, and line styles through a single
parameterised dialog class driven by a provider configuration dictionary.
"""
import os

import System
from System import Action, Uri, UriKind
from System.Windows import Visibility, Thickness
from System.Windows.Controls import ListBoxItem, CheckBox, TextBlock
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
from anongee_toolkit.ui.forms import confirm, error


# ---------------------------------------------------------------------------
# Element collectors
# ---------------------------------------------------------------------------

def _collect_fillpatterns(doc):
    return [
        (el.Name, el.Id)
        for el in FilteredElementCollector(doc).OfClass(FillPatternElement).ToElements()
        if el and el.Name
    ]


def _collect_linepatterns(doc):
    return [
        (el.Name, el.Id)
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


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_PROVIDERS = {
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


# ---------------------------------------------------------------------------
# Dialog class
# ---------------------------------------------------------------------------

class GenericBulkDeleteDialog(object):
    """
    Reusable WPF dialog for bulk-deleting graphic style elements.

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
        self._search.GotFocus    += lambda s, e: self._set_placeholder(False)
        self._search.LostFocus   += lambda s, e: self._set_placeholder(not self._search.Text)
        self._btn_all.Click      += self._on_select_all
        self._btn_none.Click     += self._on_select_none
        self._btn_delete.Click   += self._on_delete
        self._btn_close.Click    += lambda s, e: self.window.Close()

    def _populate(self):
        self._targets = self._cfg["collect"](self._doc)
        self.window.Title = self._cfg["title"]
        self._rebuild_list()
        self._update_count()
        self._show_info(
            "{} {}s — none selected".format(len(self._targets), self._cfg["noun"])
        )

    def _rebuild_list(self):
        self._items_list.Items.Clear()
        for name, handle in sorted(self._targets, key=lambda p: p[0].lower()):
            label = TextBlock()
            label.Text = name
            chk = CheckBox()
            chk.Content = label
            chk.IsChecked = False
            chk.Margin = Thickness(2)
            chk.Click += lambda s, e: self._update_count()
            item = ListBoxItem()
            item.Content = chk
            item.Tag = handle
            self._items_list.Items.Add(item)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _set_placeholder(self, visible):
        self._search_ph.Visibility = (
            Visibility.Visible if visible else Visibility.Collapsed
        )

    def _on_search_changed(self, sender, args):
        self._set_placeholder(not self._search.Text)
        query = (self._search.Text or "").lower()
        for item in self._items_list.Items:
            name = item.Content.Content.Text.lower()
            item.Visibility = (
                Visibility.Visible if query in name else Visibility.Collapsed
            )

    def _on_select_all(self, sender, args):
        for item in self._items_list.Items:
            if item.Visibility == Visibility.Visible:
                item.Content.IsChecked = True
        self._update_count()

    def _on_select_none(self, sender, args):
        for item in self._items_list.Items:
            item.Content.IsChecked = False
        self._update_count()

    def _on_delete(self, sender, args):
        selected = self._checked_items()
        if not selected:
            self._show_error(
                "Select at least one {} to delete.".format(self._cfg["noun"])
            )
            return

        prompt = "Permanently delete {} {}(s)?\n\nThis cannot be undone (other than Ctrl+Z)."
        if not confirm(self._cfg["title"], prompt.format(len(selected), self._cfg["noun"])):
            return

        self._show_info("Deleting {} {}(s)…".format(len(selected), self._cfg["noun"]))
        self._btn_delete.IsEnabled = False
        self._flush_ui()

        done, skipped = 0, 0
        with RevitTransaction(self._cfg["txn"], self._doc):
            for name, handle in selected:
                try:
                    deleted = self._doc.Delete(handle)
                    if deleted and len(deleted) > 0:
                        done += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    print("Failed to delete '{}': {}".format(name, exc))
                    skipped += 1

        msg = "Deleted {} {}(s)".format(done, self._cfg["noun"])
        if skipped:
            msg += " ({} skipped — locked/in-use)".format(skipped)
        self._show_success(msg)
        self._populate()
        self._btn_delete.IsEnabled = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _checked_items(self):
        return [
            (item.Content.Content.Text, item.Tag)
            for item in self._items_list.Items
            if item.Content.IsChecked
        ]

    def _update_count(self):
        selected = sum(1 for item in self._items_list.Items if item.Content.IsChecked)
        self._live_count.Text = "{} of {} selected".format(
            selected, self._items_list.Items.Count
        )

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

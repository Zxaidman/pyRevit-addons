# -*- coding: utf-8 -*-
import os
import System
from System import Action, Uri, UriKind
from System.Windows import Visibility, Thickness
from System.Windows.Controls import ListBoxItem, CheckBox, TextBlock
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System.Windows.Media.Imaging import BitmapImage

from Autodesk.Revit.DB import (
    FilteredElementCollector, FillPatternElement, LinePatternElement, BuiltInCategory
)

from anongee_toolkit.core import get_current_doc
from anongee_toolkit.ui import load_xaml
from anongee_toolkit.forms import confirm, error
from anongee_toolkit.transaction import RevitTransaction

# --- Element Collectors ---

def collect_fillpatterns(doc):
    return [(el.Name, el.Id) for el in FilteredElementCollector(doc).OfClass(FillPatternElement).ToElements() if el and el.Name]

def collect_linepatterns(doc):
    return [(el.Name, el.Id) for el in FilteredElementCollector(doc).OfClass(LinePatternElement).ToElements() if el and el.Name]

def collect_linestyles(doc):
    items = []
    cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_Lines)
    if cat:
        for sub in cat.SubCategories:
            if sub and sub.Name:
                items.append((sub.Name, sub.Id))
    return items

# Configuration Dictionary
PROVIDERS = {
    "fillpattern": {
        "title": "Delete Fill Patterns",
        "noun": "fill pattern",
        "txn": "AnonGee · Delete Fill Patterns",
        "collect": collect_fillpatterns,
    },
    "linepattern": {
        "title": "Delete Line Patterns",
        "noun": "line pattern",
        "txn": "AnonGee · Delete Line Patterns",
        "collect": collect_linepatterns,
    },
    "linestyle": {
        "title": "Delete Line Styles",
        "noun": "line style",
        "txn": "AnonGee · Delete Line Styles",
        "collect": collect_linestyles,
    },
}

class GenericBulkDeleteDialog(object):
    """
    A generic UI engine for Bulk Delete operations.
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
        self._targets = self.cfg["collect"](self.doc)
        self.window.Title = self.cfg["title"]
        self._fill_list()
        self._update_count()
        self._show_info("{} {}s — none selected".format(len(self._targets), self.cfg["noun"]))

    def _fill_list(self):
        self._items_list.Items.Clear()
        for name, handle in sorted(self._targets, key=lambda p: p[0].lower()):
            tb = TextBlock()
            tb.Text = name
            chk = CheckBox()
            chk.Content = tb
            chk.IsChecked = False
            chk.Margin = Thickness(2)
            chk.Click += lambda s, e: self._update_count()
            
            item = ListBoxItem()
            item.Content = chk
            item.Tag = handle
            self._items_list.Items.Add(item)

    def _set_ph(self, visible):
        self._search_ph.Visibility = Visibility.Visible if visible else Visibility.Collapsed

    def _on_search_changed(self, sender, args):
        self._set_ph(not self._search.Text)
        q = (self._search.Text or "").lower()
        for item in self._items_list.Items:
            name = item.Content.Content.Text.lower()
            item.Visibility = Visibility.Visible if q in name else Visibility.Collapsed

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
        return [(item.Content.Content.Text, item.Tag) for item in self._items_list.Items if item.Content.IsChecked]

    def _update_count(self):
        sel = sum(1 for item in self._items_list.Items if item.Content.IsChecked)
        self._live_count.Text = "{} of {} selected".format(sel, self._items_list.Items.Count)

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

    def _on_delete(self, sender, args):
        selected = self._checked_items()
        if not selected:
            self._show_error("Select at least one {} to delete.".format(self.cfg["noun"]))
            return

        msg = "Permanently delete {} {}(s)?\n\nThis cannot be undone (other than Ctrl+Z)."
        if not confirm(self.cfg["title"], msg.format(len(selected), self.cfg["noun"])):
            return

        self._show_info("Deleting {} {}(s)...".format(len(selected), self.cfg["noun"]))
        self._btn_delete.IsEnabled = False
        self._flush_ui()

        done = 0
        skipped = 0
        
        # Using our toolkit's fail-safe transaction
        with RevitTransaction(self.cfg["txn"], self.doc) as t:
            for _name, handle in selected:
                try:
                    # Attempt to delete
                    deleted_ids = self.doc.Delete(handle)
                    if deleted_ids and len(deleted_ids) > 0:
                        done += 1
                    else:
                        skipped += 1
                except Exception as e:
                    # Print the error to the pyRevit output window for debugging
                    print("Failed to delete '{}': {}".format(_name, str(e)))
                    skipped += 1 # system-locked / in-use

        msg = "Deleted {} {}(s)".format(done, self.cfg["noun"])
        if skipped:
            msg += " ({} skipped — locked/in-use)".format(skipped)
            
        self._show_success(msg)
        self._populate() # Refresh UI
        self._btn_delete.IsEnabled = True

    def show(self):
        if not self._targets:
            error(self.cfg["title"], "No {}s found in this document.".format(self.cfg["noun"]))
            return
        self.window.ShowDialog()
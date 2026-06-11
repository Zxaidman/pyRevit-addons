#! python3
# -*- coding: utf-8 -*-

import os
import clr
import System

clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    BuiltInCategory,
    ViewType,
    View,
    View3D,
    Transaction,
)
from System.Collections.Generic import List
from Autodesk.Revit.DB import ElementId

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import BitmapImage
from System.IO import FileStream, FileMode, FileAccess
from System.Windows.Controls import ListBoxItem, CheckBox
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System import Action, Uri, UriKind
from System.Windows import Visibility, Thickness, MessageBox, MessageBoxButton, MessageBoxImage

doc   = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument

LOCAL_DIR = os.path.dirname(__file__)

ALLOWED_VIEW_TYPES = {
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.EngineeringPlan,
    ViewType.Section,
    ViewType.Elevation,
    ViewType.ThreeD,
}

VIEW_TYPE_LABELS = {
    ViewType.ThreeD:          "3D",
    ViewType.EngineeringPlan: "Structural Plan",
    ViewType.FloorPlan:       "Floor Plan",
    ViewType.CeilingPlan:     "Ceiling Plan",
    ViewType.Section:         "Section",
    ViewType.Elevation:       "Elevation",
}


def _id_value(eid):
    return getattr(eid, "Value", getattr(eid, "IntegerValue", -1))


def _view_label(view):
    label = VIEW_TYPE_LABELS.get(view.ViewType, str(view.ViewType))
    return "{} [{}]".format(view.Name, label)


class CopyRebarVisibilityDialog(object):

    def __init__(self, rebars, views):
        self._rebars     = rebars
        self._views_data = [(v, _view_label(v)) for v in views]

        xaml_path = os.path.join(LOCAL_DIR, "ui.xaml")
        stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
        try:
            self.window = XamlReader.Load(stream)
        finally:
            stream.Close()

        self._set_window_icon()
        self._bind()
        self._populate()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _set_window_icon(self):
        icon_path = os.path.join(LOCAL_DIR, "icon.png")
        if os.path.exists(icon_path):
            self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

    def _bind(self):
        w = self.window
        self._live_count    = w.FindName("LiveCount")
        self._source_combo  = w.FindName("SourceCombo")
        self._views_list    = w.FindName("ViewsList")
        self._btn_all       = w.FindName("BtnAll")
        self._btn_none      = w.FindName("BtnNone")
        self._btn_apply     = w.FindName("BtnApply")
        self._btn_close     = w.FindName("BtnClose")
        self._badge_info    = w.FindName("BadgeInfo")
        self._badge_success = w.FindName("BadgeSuccess")
        self._badge_error   = w.FindName("BadgeError")
        self._info_text     = w.FindName("InfoText")
        self._success_text  = w.FindName("SuccessText")
        self._error_text    = w.FindName("ErrorText")

        self._btn_all.Click   += self._on_all
        self._btn_none.Click  += self._on_none
        self._btn_apply.Click += self._on_apply
        self._btn_close.Click += lambda s, e: self.window.Close()

    def _populate(self):
        self._live_count.Text = "{} rebars".format(len(self._rebars))

        # Source ComboBox — default to active view
        active_id = _id_value(doc.ActiveView.Id)
        default_idx = 0
        for i, (view, name) in enumerate(self._views_data):
            self._source_combo.Items.Add(name)
            if _id_value(view.Id) == active_id:
                default_idx = i
        self._source_combo.SelectedIndex = default_idx

        # Target list — all unchecked by default
        for _view, name in self._views_data:
            chk = CheckBox()
            chk.Content   = name
            chk.IsChecked = False
            chk.Margin    = Thickness(2)

            item = ListBoxItem()
            item.Content = chk
            self._views_list.Items.Add(item)

        self._show_info("Select a source view and check target views")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _checked_views(self):
        result = []
        for i in range(self._views_list.Items.Count):
            chk = self._views_list.Items[i].Content
            if chk.IsChecked:
                result.append(self._views_data[i][0])
        return result

    def _set_all_checked(self, value):
        for item in self._views_list.Items:
            item.Content.IsChecked = value

    def _show_info(self, message):
        self._info_text.Text           = message
        self._badge_info.Visibility    = Visibility.Visible
        self._badge_success.Visibility = Visibility.Collapsed
        self._badge_error.Visibility   = Visibility.Collapsed

    def _show_success(self, message):
        self._success_text.Text        = message
        self._badge_info.Visibility    = Visibility.Collapsed
        self._badge_success.Visibility = Visibility.Visible
        self._badge_error.Visibility   = Visibility.Collapsed

    def _show_error(self, message):
        self._error_text.Text          = message
        self._badge_info.Visibility    = Visibility.Collapsed
        self._badge_success.Visibility = Visibility.Collapsed
        self._badge_error.Visibility   = Visibility.Visible

    def _flush_ui(self):
        Dispatcher.CurrentDispatcher.Invoke(
            Action(lambda: None), DispatcherPriority.Background)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_all(self, sender, args):
        self._set_all_checked(True)

    def _on_none(self, sender, args):
        self._set_all_checked(False)

    def _on_apply(self, sender, args):
        src_idx = self._source_combo.SelectedIndex
        if src_idx < 0:
            self._show_error("Select a source view first.")
            return

        source_view  = self._views_data[src_idx][0]
        source_id    = _id_value(source_view.Id)
        target_views = [v for v in self._checked_views() if _id_value(v.Id) != source_id]

        if not target_views:
            self._show_error("Check at least one target view (different from source).")
            return

        self._show_info("Processing {} rebar(s) across {} view(s)...".format(
            len(self._rebars), len(target_views)))
        self._btn_apply.IsEnabled = False
        self._flush_ui()

        source_is_3d = isinstance(source_view, View3D)

        t = Transaction(doc, "Copy Rebar Visibility")
        t.Start()
        try:
            for t_view in target_views:
                t_is_3d = isinstance(t_view, View3D)
                to_hide   = List[ElementId]()
                to_unhide = List[ElementId]()

                for rebar in self._rebars:
                    # Hidden status
                    try:
                        if rebar.IsHidden(source_view):
                            if not rebar.IsHidden(t_view) and rebar.CanBeHidden(t_view):
                                to_hide.Add(rebar.Id)
                        else:
                            if rebar.IsHidden(t_view) and rebar.CanBeHidden(t_view):
                                to_unhide.Add(rebar.Id)
                    except Exception:
                        pass

                    # Unobscured status
                    try:
                        if hasattr(rebar, "IsUnobscuredInView"):
                            src_val = rebar.IsUnobscuredInView(source_view)
                            if rebar.IsUnobscuredInView(t_view) != src_val:
                                rebar.SetUnobscuredInView(t_view, src_val)
                    except Exception:
                        pass

                    # Solid status (3D → 3D only)
                    try:
                        if source_is_3d and t_is_3d and hasattr(rebar, "IsSolidInView"):
                            src_val = rebar.IsSolidInView(source_view)
                            if rebar.IsSolidInView(t_view) != src_val:
                                rebar.SetSolidInView(t_view, src_val)
                    except Exception:
                        pass

                if to_hide.Count > 0:
                    try:
                        t_view.HideElements(to_hide)
                    except Exception:
                        pass
                if to_unhide.Count > 0:
                    try:
                        t_view.UnhideElements(to_unhide)
                    except Exception:
                        pass

            t.Commit()
            self._show_success("Copied from '{}' to {} view(s).".format(
                source_view.Name, len(target_views)))
            self._flush_ui()
            self.window.Close()

        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            self._show_error("Transaction failed: {}".format(str(ex)))
            self._btn_apply.IsEnabled = True

    def show(self):
        self.window.ShowDialog()


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
def run():
    rebars = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_Rebar)
        .WhereElementIsNotElementType()
        .ToElements()
    )

    if not rebars:
        MessageBox.Show(
            "No rebars found in the document.",
            "Copy Rebar Visibility",
            MessageBoxButton.OK,
            MessageBoxImage.Warning)
        return

    all_views = list(
        FilteredElementCollector(doc)
        .OfClass(View)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    eligible_views = sorted(
        [v for v in all_views if not v.IsTemplate and v.ViewType in ALLOWED_VIEW_TYPES],
        key=lambda v: v.Name,
    )

    if not eligible_views:
        MessageBox.Show(
            "No eligible views found in the document.",
            "Copy Rebar Visibility",
            MessageBoxButton.OK,
            MessageBoxImage.Warning)
        return

    CopyRebarVisibilityDialog(rebars, eligible_views).show()


if __name__ == "__main__":
    run()

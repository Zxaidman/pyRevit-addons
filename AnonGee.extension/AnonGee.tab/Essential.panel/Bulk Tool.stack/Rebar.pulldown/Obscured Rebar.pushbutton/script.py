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
    ViewDetailLevel,
)

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import BitmapImage
from System.IO import FileStream, FileMode, FileAccess
from System import Uri, UriKind
from System.Windows.Controls import ListBoxItem, CheckBox
from System.Windows.Threading import Dispatcher, DispatcherPriority
from System import Action
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
    ViewType.ThreeD:           "3D",
    ViewType.EngineeringPlan:  "Structural Plan",
    ViewType.FloorPlan:        "Floor Plan",
    ViewType.CeilingPlan:      "Ceiling Plan",
    ViewType.Section:          "Section",
    ViewType.Elevation:        "Elevation",
}


def _id_value(eid):
    return getattr(eid, "Value", getattr(eid, "IntegerValue", -1))


def _view_label(view):
    label = VIEW_TYPE_LABELS.get(view.ViewType, str(view.ViewType))
    return "{} [{}]".format(view.Name, label)


class ObscuredRebarDialog(object):

    def __init__(self, rebars, views, is_selection):
        self._rebars      = rebars
        self._views_data  = [(v, _view_label(v)) for v in views]
        self._is_selection = is_selection

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
        suffix = "(Selection)" if self._is_selection else "(All)"
        self._live_count.Text = "{} rebars {}".format(len(self._rebars), suffix)

        for _view, name in self._views_data:
            chk = CheckBox()
            chk.Content   = name
            chk.IsChecked = True
            chk.Margin    = Thickness(2)
            chk.Click    += lambda s, e: self._refresh_status()

            item = ListBoxItem()
            item.Content = chk
            self._views_list.Items.Add(item)

        self._refresh_status()

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
        self._refresh_status()

    def _refresh_status(self):
        selected = len(self._checked_views())
        total    = len(self._views_data)
        self._show_info("{} of {} views selected".format(selected, total))

    def _show_info(self, message):
        self._info_text.Text    = message
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
        target_views = self._checked_views()
        if not target_views:
            self._show_error("Select at least one view before applying.")
            return

        self._show_info("Processing {} rebar(s) across {} view(s)...".format(
            len(self._rebars), len(target_views)))
        self._btn_apply.IsEnabled = False
        self._flush_ui()

        t = Transaction(doc, "Obscured Rebar — Set Unobscured & Solid")
        t.Start()
        try:
            for view in target_views:
                has_template = _id_value(view.ViewTemplateId) != -1
                if not has_template:
                    if isinstance(view, View3D):
                        if view.DetailLevel != ViewDetailLevel.Fine:
                            view.DetailLevel = ViewDetailLevel.Fine
                    elif view.ViewType in ALLOWED_VIEW_TYPES:
                        if view.DetailLevel != ViewDetailLevel.Medium:
                            view.DetailLevel = ViewDetailLevel.Medium

                is_3d = isinstance(view, View3D)
                for rebar in self._rebars:
                    try:
                        if hasattr(rebar, "SetUnobscuredInView") and not rebar.IsUnobscuredInView(view):
                            rebar.SetUnobscuredInView(view, True)
                        if is_3d and hasattr(rebar, "SetSolidInView") and not rebar.IsSolidInView(view):
                            rebar.SetSolidInView(view, True)
                    except Exception:
                        pass

            t.Commit()
            self._show_success("Updated {} rebar(s) across {} view(s).".format(
                len(self._rebars), len(target_views)))
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
    # Collect rebars (prefer active selection)
    sel_ids = list(uidoc.Selection.GetElementIds())
    rebars  = [
        doc.GetElement(eid) for eid in sel_ids
        if doc.GetElement(eid) is not None
        and doc.GetElement(eid).Category is not None
        and _id_value(doc.GetElement(eid).Category.Id) == int(BuiltInCategory.OST_Rebar)
    ]
    is_selection = bool(rebars)

    if not rebars:
        rebars = list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_Rebar)
            .WhereElementIsNotElementType()
            .ToElements()
        )

    if not rebars:
        MessageBox.Show(
            "No rebars found in the document.",
            "Obscured Rebar",
            MessageBoxButton.OK,
            MessageBoxImage.Warning)
        return

    # Collect eligible views
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
            "Obscured Rebar",
            MessageBoxButton.OK,
            MessageBoxImage.Warning)
        return

    ObscuredRebarDialog(rebars, eligible_views, is_selection).show()


if __name__ == "__main__":
    run()

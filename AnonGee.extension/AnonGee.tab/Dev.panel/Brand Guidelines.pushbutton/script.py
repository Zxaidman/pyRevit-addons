#! python3
# -*- coding: utf-8 -*-
"""
AnonGee Brand Guidelines — living component gallery.

Renders the canonical design system (colors, typography, buttons, inputs,
selection controls, list, badges) straight from a brand-themed ui.xaml, so the
tool always matches what the shipping WPF tools produce. Keep ui.xaml in sync
with AnonGee_BIM_Tools_Brand_Guidelines.md whenever the system changes.
"""

import os
import clr

clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xaml")

from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import BitmapImage
from System.IO import FileStream, FileMode, FileAccess
from System import Uri, UriKind
from System.Windows import MessageBox, MessageBoxButton, MessageBoxImage

LOCAL_DIR = os.path.dirname(__file__)

try:
    import traceback as _tb
    def _fmt_exc():
        return _tb.format_exc()
except ImportError:
    import sys
    def _fmt_exc():
        t, v, _ = sys.exc_info()
        return "{}: {}".format(t.__name__ if t else "Error", v)


def run():
    xaml_path = os.path.join(LOCAL_DIR, "ui.xaml")
    stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
    try:
        window = XamlReader.Load(stream)
    finally:
        stream.Close()

    icon_path = os.path.join(LOCAL_DIR, "icon.png")
    if os.path.exists(icon_path):
        window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))

    btn_close = window.FindName("BtnClose")
    if btn_close is not None:
        btn_close.Click += lambda s, e: window.Close()

    window.ShowDialog()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        MessageBox.Show(
            _fmt_exc()[-3000:],
            "Brand Guidelines — Unhandled Error",
            MessageBoxButton.OK, MessageBoxImage.Error)

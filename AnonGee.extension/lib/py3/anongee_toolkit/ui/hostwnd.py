# -*- coding: utf-8 -*-
"""hostwnd - locate the Revit main window so overlays can dock to it.

pyRevit's progress bar spans the full width of the Revit window and sits over
its title bar. Reproducing that needs the host window's screen rectangle, which
WPF does not expose for a non-WPF window - Revit's main window is native Win32,
so ``HwndSource.FromHwnd`` returns null and ``Control.FromHandle`` returns null.

Three ways out, tried in order:

1. ``ctypes`` -> ``user32.GetWindowRect``. Real CPython under pythonnet has a
   working ctypes, and this is the direct answer.
2. UI Automation ``AutomationElement.FromHandle(...).Current.BoundingRectangle``.
   Fully managed, so it also works on IronPython where ctypes is unreliable.
3. Nothing - caller falls back to centring on the work area.

Coordinates from Win32 are physical device pixels; WPF positions windows in
device-independent units. The conversion factor comes from the overlay window's
own PresentationSource, which means the overlay has to be shown before it can be
placed accurately. On a mixed-DPI multi-monitor setup the first placement can
therefore be off by the ratio between the two monitors' scaling; calling
:func:`place_over_host` a second time after the move corrects it.
"""

__version__ = "1.6.0"
__all__ = ["revit_handle", "host_rect_px", "device_to_diu",
           "place_over_host", "caption_height"]

try:
    import clr
    for _asm in ("PresentationFramework", "PresentationCore", "WindowsBase",
                 "System.Windows.Forms", "System.Drawing"):
        try:
            clr.AddReference(_asm)
        except Exception:
            pass
except ImportError:
    pass

from System import IntPtr


def revit_handle():
    """Revit's main window handle, or None."""
    try:
        from pyrevit import HOST_APP
        h = HOST_APP.uiapp.MainWindowHandle
        if h is not None and h != IntPtr.Zero:
            return h
    except Exception:
        pass
    try:
        import __main__
        h = __main__.__revit__.MainWindowHandle
        if h is not None and h != IntPtr.Zero:
            return h
    except Exception:
        pass
    try:
        from System.Diagnostics import Process
        h = Process.GetCurrentProcess().MainWindowHandle
        if h is not None and h != IntPtr.Zero:
            return h
    except Exception:
        pass
    return None


def _hwnd_int(handle):
    try:
        return handle.ToInt64()
    except Exception:
        pass
    try:
        return int(handle)
    except Exception:
        return None


def _rect_ctypes(handle):
    try:
        import ctypes
    except Exception:
        return None
    hwnd = _hwnd_int(handle)
    if not hwnd:
        return None
    try:
        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        user32 = ctypes.windll.user32
        r = RECT()
        if not user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r)):
            return None
        return (float(r.left), float(r.top), float(r.right), float(r.bottom))
    except Exception:
        return None


def _rect_automation(handle):
    try:
        import clr
        for _asm in ("UIAutomationClient", "UIAutomationTypes"):
            try:
                clr.AddReference(_asm)
            except Exception:
                pass
        from System.Windows.Automation import AutomationElement
        el = AutomationElement.FromHandle(handle)
        if el is None:
            return None
        b = el.Current.BoundingRectangle
        if b is None or b.Width <= 0:
            return None
        return (float(b.Left), float(b.Top), float(b.Right), float(b.Bottom))
    except Exception:
        return None


def _clamp_to_screen(handle, rect):
    """Trim a maximised window's invisible border overhang.

    Win32 reports a maximised window as roughly (-8, -8, W+8, H+8): the resize
    border sits off-screen. Docking to that raw rect puts the left edge of the
    bar past the edge of the monitor. Intersecting with the monitor bounds
    gives the rect the user actually sees.
    """
    try:
        from System.Windows.Forms import Screen
        b = Screen.FromHandle(handle).Bounds
        left, top, right, bottom = rect
        return (max(left, float(b.Left)), max(top, float(b.Top)),
                min(right, float(b.Right)), min(bottom, float(b.Bottom)))
    except Exception:
        return rect


def host_rect_px(handle=None, clamp=True):
    """Revit main window rect in device pixels as (left, top, right, bottom)."""
    handle = handle or revit_handle()
    if handle is None:
        return None
    rect = _rect_ctypes(handle) or _rect_automation(handle)
    if rect is None:
        return None
    if clamp:
        rect = _clamp_to_screen(handle, rect)
    if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
        return None
    return rect


def caption_height(fallback=26.0):
    """Height of the host title bar, in WPF units.

    Why this exists: WPF sizes windows in device-independent units, so a bar
    declared 26 units tall is 26 physical pixels at 100% scaling and 39 at
    150%. The bar therefore scales correctly across DPI settings on its own -
    a fixed number is NOT a DPI bug.

    What a fixed number does miss is the title bar it is meant to cover, whose
    height depends on the Windows version and the user's text-size setting,
    not on DPI. SystemParameters reports both pieces in WPF units, so this
    derives the value instead of assuming it. Clamped, because an unusual
    text-size setting can return something too small to fit the label.
    """
    try:
        from System.Windows import SystemParameters
        h = float(SystemParameters.WindowCaptionHeight)
        b = float(SystemParameters.ResizeFrameHorizontalBorderHeight)
        if h > 0:
            return max(22.0, min(48.0, h + b))
    except Exception:
        pass
    return fallback


def device_to_diu(window):
    """(x, y) factors converting device pixels to WPF units for this window.

    Requires the window to have been shown - an unshown window has no
    PresentationSource. Returns (1.0, 1.0) at 96 DPI or on failure.
    """
    try:
        from System.Windows import PresentationSource
        src = PresentationSource.FromVisual(window)
        if src is not None and src.CompositionTarget is not None:
            m = src.CompositionTarget.TransformFromDevice
            if m.M11 > 0 and m.M22 > 0:
                return m.M11, m.M22
    except Exception:
        pass
    return 1.0, 1.0


def place_over_host(window, height, handle=None, top_offset=0):
    """Dock ``window`` across the top edge of the Revit window.

    Returns True if it was placed, False if the caller should fall back.
    """
    rect = host_rect_px(handle)
    if rect is None:
        return False
    sx, sy = device_to_diu(window)
    left, top, right, _bottom = rect
    try:
        window.Left = left * sx
        window.Top = top * sy + top_offset
        window.Width = (right - left) * sx
        window.Height = height
        return True
    except Exception:
        return False

# -*- coding: utf-8 -*-
"""The stack drawing's camera — zoom, pan, and elevation-to-pixel mapping.

Kept apart from the drawing code because it is pure arithmetic with a property
worth pinning down: zooming with the wheel must leave the elevation under the
cursor exactly under the cursor. That is easy to get subtly wrong and painful
to notice by eye, so it lives here and is tested without Revit or WPF.

Screen y grows downward, elevation grows upward, so every mapping in this file
inverts. Zoom 1.0 means "the whole stack fits"; there is deliberately no
zooming out past it, and panning is clamped so the view can never leave the
building.
"""

TOP_PAD = 16.0
BOTTOM_PAD = 20.0
LABEL_GAP = 13.0          # px — closer than this and a level's name is dropped
HIT_TOLERANCE = 6.0       # px — how near a click counts as "on that level"

ZOOM_MIN = 1.0
ZOOM_MAX = 60.0
ZOOM_STEP = 1.4

# What a lone level (or several at one elevation) gets drawn against.
EMPTY_MARGIN_MM = 1000.0


class StackView(object):
    """Where the camera is looking, and how that maps to the canvas."""

    __slots__ = ("zoom", "center_mm")

    def __init__(self):
        self.zoom = ZOOM_MIN
        self.center_mm = None       # None == "centre it on the whole stack"

    # ── the camera ────────────────────────────────────────────────────
    def fit(self):
        """Back to the whole stack in one screen."""
        self.zoom = ZOOM_MIN
        self.center_mm = None

    def bounds(self, elevations):
        """(lowest, highest) with a margin when there is nothing to span."""
        values = list(elevations or ())
        if not values:
            return None
        low, high = min(values), max(values)
        if high - low < 1.0:
            return low - EMPTY_MARGIN_MM, high + EMPTY_MARGIN_MM
        return low, high

    def window(self, elevations):
        """The (lo, hi) band on screen, clamping the centre into the stack.

        Also settles ``center_mm`` so a later pan starts from a real number
        rather than from ``None``.
        """
        bounds = self.bounds(elevations)
        if bounds is None:
            return None
        low, high = bounds
        half = (high - low) / self.zoom / 2.0
        center = self.center_mm
        if center is None:
            center = (low + high) / 2.0
        if low + half >= high - half:
            center = (low + high) / 2.0     # nothing to pan at this zoom
        else:
            center = min(max(center, low + half), high - half)
        self.center_mm = center
        return center - half, center + half

    # ── mapping ───────────────────────────────────────────────────────
    def y_at(self, elevation, window, usable):
        low, high = window
        if high - low <= 0 or usable <= 0:
            return TOP_PAD + max(usable, 0.0) / 2.0
        return TOP_PAD + (high - elevation) / (high - low) * usable

    def elevation_at(self, y, window, usable):
        low, high = window
        if usable <= 0:
            return low
        return high - (y - TOP_PAD) / usable * (high - low)

    def mm_per_pixel(self, window, usable):
        low, high = window
        if usable <= 0:
            return 0.0
        return (high - low) / usable

    # ── gestures ──────────────────────────────────────────────────────
    def zoom_about(self, y, factor, elevations, usable):
        """Zoom by *factor*, pinning the elevation under *y* where it is.

        Returns True when the zoom actually changed — at the limits it does
        not, and the caller can skip a redraw.
        """
        target = min(ZOOM_MAX, max(ZOOM_MIN, self.zoom * factor))
        if abs(target - self.zoom) < 1e-9:
            return False
        window = self.window(elevations)
        bounds = self.bounds(elevations)
        if window is None or bounds is None or usable <= 0:
            self.zoom = target
            return True
        low, high = window
        anchor = self.elevation_at(y, window, usable)
        fraction = (high - anchor) / (high - low) if high > low else 0.5
        span = (bounds[1] - bounds[0]) / target
        self.zoom = target
        # Put the anchor back at the same fraction of the new window.
        self.center_mm = (anchor + fraction * span) - span / 2.0
        return True

    def pan_pixels(self, pixels, window, usable, start_center=None):
        """Drag the view by *pixels*, so the drawing follows the hand."""
        base = self.center_mm if start_center is None else start_center
        if base is None:
            low, high = window
            base = (low + high) / 2.0
        self.center_mm = base + pixels * self.mm_per_pixel(window, usable)
        return self.center_mm

    def nudge(self, fraction, window):
        """Shift the view by a fraction of what is on screen — wheel panning."""
        low, high = window
        if self.center_mm is None:
            self.center_mm = (low + high) / 2.0
        self.center_mm += (high - low) * fraction
        return self.center_mm

    def visible(self, y, height, margin=20.0):
        """Is a level at this y worth drawing at all?"""
        return -margin <= y <= height + margin


def nearest(hits, y, tolerance=HIT_TOLERANCE):
    """The entry drawn closest to *y*, or None when the click missed.

    *hits* is [(payload, y)] as recorded while drawing, so hit-testing costs
    nothing extra and matches exactly what is on screen.
    """
    best = None
    best_gap = None
    for payload, row_y in hits or ():
        gap = abs(row_y - y)
        if gap <= tolerance and (best_gap is None or gap < best_gap):
            best, best_gap = payload, gap
    return best


def snap(value, step):
    """Round a dragged elevation to the snap step. Step 0 means no rounding."""
    if not step or step <= 0:
        return value
    return round(value / step) * step

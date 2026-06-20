# -*- coding: utf-8 -*-
"""Generate a column stress-test DXF for the cad2bim pipeline.

Lays out, on a labelled structural grid (mm), one region per column-detection path
the toolkit must survive. Run with a CPython that has ezdxf installed:

    python3 generate_stress_columns_dxf.py  ->  stress_columns.dxf

Layers follow the AnonGee convention used by Test10:
    S-GRID / S-GRID-IDEN   grid lines + bubbles
    S-COLS                 column geometry
    S-COLS-IDEN            column size text (C_<b> X <h>) and marks
"""

import ezdxf

DOC = ezdxf.new("R2000")
DOC.units = ezdxf.units.MM
MSP = DOC.modelspace()
for name, color in (("S-GRID", 8), ("S-GRID-IDEN", 8),
                    ("S-COLS", 1), ("S-COLS-IDEN", 3)):
    DOC.layers.add(name, color=color)


def box(cx, cy, b, h, layer="S-COLS"):
    """Closed rectangle centred at (cx, cy), width b (x) x height h (y)."""
    x0, x1, y0, y1 = cx - b / 2.0, cx + b / 2.0, cy - h / 2.0, cy + h / 2.0
    MSP.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
                       close=True, dxfattribs={"layer": layer})


def poly(points, close=False, layer="S-COLS"):
    MSP.add_lwpolyline(points, close=close, dxfattribs={"layer": layer})


def line(a, b, layer="S-COLS"):
    MSP.add_line(a, b, dxfattribs={"layer": layer})


def circle(cx, cy, dia, layer="S-COLS"):
    MSP.add_circle((cx, cy), dia / 2.0, dxfattribs={"layer": layer})


def label(cx, cy, text, layer="S-COLS-IDEN"):
    MSP.add_mtext(text, dxfattribs={"layer": layer, "char_height": 200,
                                    "insert": (cx, cy)})


def rotated_box(cx, cy, b, h, deg):
    """Closed rectangle rotated deg degrees about its centre."""
    import math
    r = math.radians(deg)
    cos, sin = math.cos(r), math.sin(r)
    pts = []
    for sx, sy in ((-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)):
        pts.append((cx + sx * cos - sy * sin, cy + sx * sin + sy * cos))
    poly(pts, close=True)


# --- structural grid (8 x 6), bubbles -------------------------------------
XS = [0, 5000, 10000, 15000, 20000, 25000, 30000, 35000]   # grids 1..8
YS = [0, 5000, 10000, 15000, 20000, 25000]                 # grids A..F
for i, x in enumerate(XS):
    line((x, -2500), (x, 27500), layer="S-GRID")
    label(x - 100, -3200, str(i + 1), layer="S-GRID-IDEN")
for j, y in enumerate(YS):
    line((-2500, y), (37500, y), layer="S-GRID")
    label(-3600, y - 100, chr(ord("A") + j), layer="S-GRID-IDEN")


# === Region 1: plain closed rectangles (rectangle / decompose=1) ===========
box(5000, 5000, 400, 400);   label(5300, 5300, "C_400 X 400")
box(10000, 5000, 300, 900);  label(10300, 5500, "C_300 X 900")
box(15000, 5000, 900, 300);  label(15300, 5300, "C_900 X 300")

# === Region 2: rotated rectangle (oriented_rect) ===========================
rotated_box(20000, 5000, 600, 900, 30);  label(20400, 5500, "C_600 X 900")

# === Region 3: composite L lift-core (decompose -> 2 rects) ================
# L = 1500x1500 outer with a 900x900 bite out of the top-right corner.
poly([(24250, 4250), (25750, 4250), (25750, 5150),
      (24850, 5150), (24850, 5750), (24250, 5750)],
     close=True);            label(24300, 4400, "L-core")

# === Region 4: round column (arc/circle path) ==============================
circle(30000, 5000, 700);    label(30400, 5400, "C_700 DIA")

# === Region 5: junction-fragmented ROTATED column (oriented recovery) ======
# A 600x800 column at 25 deg, sliced by a beam into two disconnected L-pieces.
import math as _m
_r = _m.radians(25); _c, _s = _m.cos(_r), _m.sin(_r)
def _p(sx, sy):
    return (5000 + sx * _c - sy * _s, 10000 + sx * _s + sy * _c)
line(_p(-300, -400), _p(300, -400)); line(_p(300, -400), _p(300, -50))    # lower L
line(_p(-300, 400), _p(-300, -400))                                       # left side
line(_p(-300, 400), _p(300, 400)); line(_p(300, 400), _p(300, 50))        # upper L
label(5400, 10500, "C_600 X 800")

# === Region 6: fused comb -- long wall + 3 perpendicular legs ==============
# 6000-long, 300-wide base at y~10000 with three 300x2400 legs (grids 3,4,5).
# Drawn as ONE open comb outline (no closed ring) -> rectilinear assembly.
line((16000, 9850), (22000, 9850))                                        # base far edge
poly([(16000, 10150), (16000, 12550), (16300, 12550), (16300, 10150),
      (18850, 10150), (18850, 12550), (19150, 12550), (19150, 10150),
      (21700, 10150), (21700, 12550), (22000, 12550), (22000, 10150)])    # near edge + teeth
line((16000, 10150), (16000, 9850)); line((22000, 10150), (22000, 9850))  # the two end caps
label(18600, 9400, "C_300 X 6000 wall + legs")

# === Region 7: clipped wall, far end cap missing (bbox-shell completion) ====
# 4500x300 wall: bottom edge + left cap + top edge, but the RIGHT cap is gone.
poly([(32250, 19850), (27750, 19850), (27750, 20150), (32250, 20150)])    # 3 sides, open
label(28000, 19200, "C_300 X 4500 (clipped)")

# === Region 8: mark-only columns + a column schedule table =================
box(5000, 20000, 500, 500);  label(5300, 20300, "C9")     # mark only, size from schedule
box(10000, 20000, 650, 650); label(10300, 20300, "C10")   # mark only, size from schedule
# Schedule: header row then two data rows, each cell its own MTEXT (Test15 style).
sx, sy = 14000, 22000
for k, (m, w, l, ht) in enumerate(
        [("Mark", "W", "L", "H"), ("C9", "500", "500", "4000"),
         ("C10", "650", "650", "4000")]):
    for c, val in enumerate((m, w, l, ht)):
        label(sx + c * 1200, sy - k * 700, val, layer="S-COLS-IDEN")

DOC.saveas("stress_columns.dxf")
print("wrote stress_columns.dxf")

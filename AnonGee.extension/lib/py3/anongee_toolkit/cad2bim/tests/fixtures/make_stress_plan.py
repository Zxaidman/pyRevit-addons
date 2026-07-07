# -*- coding: utf-8 -*-
"""Generate StressPlan-Beams.dxf -- a synthetic beam torture plan.

Run with:  PYTHONPATH=/tmp/pylibs python3 make_stress_plan.py
(regenerates cad/StressPlan-Beams.dxf; tests/test_beam_stress.py asserts against it)

One drawing packing every beam failure mode found across Test9-19 / the Messy plans,
plus hazards a real-world CAD file plausibly adds. Everything is drawn the DXF way
(loose LINEs for edges, MTEXT labels with text_direction) so the whole read->classify->
detect->size->name pipeline runs for real. Coordinates in mm.

Zones (all beams 300 wide unless said otherwise; label format "B<n>_<W> X <H>"):
  Z1 baseline   two horizontal + two vertical line-pair beams on a 8x5 m bay,
                horizontal labels above the beam, VERTICAL labels written along
                the beam (rotated MTEXT -- the Test15 wrong-mark trap).
  Z2 sloped     a 4-degree beam (Test11 grid-I: bbox once flattened it horizontal).
  Z3 diagonal   a 45-degree beam (worst-case for any axis-aligned assumption).
  Z4 wide+cont  a 900-wide beam interrupted by a 300 crossing; its ONE label sits
                over the near piece (B22: label-confirmed edge pair + continuation
                merge into a single beam).
  Z5 perimeter  a beam with only ONE edge on the beam layer; the partner edge is
                the floor outline on A-FLOR (Test19 clipped-perimeter case).
  Z6 stacked    a 600-wide and a 300-wide beam stacked 700 apart; the 300's label
                sits BETWEEN them (B20/B23 mark-theft trap).
  Z7 curved     two concentric arc chains one width apart + a label (B18 case).
  Z8 junk       duplicated line, zero-length line, a 20 mm sliver outline, an
                orphan label with no geometry, a "125 THK." slab note on the beam
                text layer -- none of it may fabricate a beam.
"""

import math
import os
import sys

sys.path.insert(0, "/tmp/pylibs")
import ezdxf

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "cad", "StressPlan-Beams.dxf")

doc = ezdxf.new("R2013")
msp = doc.modelspace()
for name, color in (("S-BEAM", 1), ("A-FLOR", 8), ("S-BEAM-IDEN", 2)):
    doc.layers.add(name, color=color)


def line(x1, y1, x2, y2, layer="S-BEAM"):
    msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": layer})


def pair(x1, y1, x2, y2, width, layer="S-BEAM"):
    """Two edge lines `width` apart around centreline (x1,y1)->(x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    nx, ny = -dy / length * width / 2.0, dx / length * width / 2.0
    line(x1 + nx, y1 + ny, x2 + nx, y2 + ny, layer)
    line(x1 - nx, y1 - ny, x2 - nx, y2 - ny, layer)


def label(text, x, y, angle_deg=0.0):
    rad = math.radians(angle_deg)
    msp.add_mtext(text, dxfattribs={
        "layer": "S-BEAM-IDEN", "char_height": 125.0,
        "insert": (x, y, 0.0),
        "text_direction": (math.cos(rad), math.sin(rad), 0.0)})


# Z1 -- baseline bay: 8 m x 5 m ring of 300-wide line pairs
pair(0, 0, 8000, 0, 300)               # B1 bottom
pair(0, 5000, 8000, 5000, 300)         # B2 top
pair(0, 150, 0, 4850, 300)             # B3 left  (clipped at the corners)
pair(8000, 150, 8000, 4850, 300)       # B4 right
label("B1_300 X 600", 3600, 350)
label("B2_300 X 600", 3600, 5350)
label("B3_300 X 600", -350, 2000, 90.0)     # rotated: runs ALONG the beam
label("B4_300 X 600", 8350, 2000, 90.0)

# Z2 -- sloped 4-degree beam (12000,0) -> (19980,558)
_ang = math.radians(4.0)
_ex, _ey = 12000 + 8000 * math.cos(_ang), 8000 * math.sin(_ang)
pair(12000, 0, _ex, _ey, 300)
label("B5_300 X 600", 15800, 500, 4.0)

# Z3 -- diagonal 45-degree beam (12000,3000) -> (17000,8000)
pair(12000, 3000, 17000, 8000, 300)
label("B6_300 X 600", 14200, 5800, 45.0)

# Z4 -- 900-wide beam y=10000, x 0..20000, broken by a 300 crossing at x=16000;
# the one label sits over the NEAR piece only
pair(0, 10000, 15850, 10000, 900)
pair(16150, 10000, 20000, 10000, 900)
pair(16000, 9450, 16000, 14000, 300)        # the crossing beam
label("B7_900 X 900", 7000, 10600)
label("B12_300 X 600", 16350, 12200, 90.0)  # names the crossing vertical

# Z5 -- perimeter beam y=14000, x 0..6000: ONE edge on S-BEAM, partner on A-FLOR
line(0, 13850, 6000, 13850)                                     # beam edge
msp.add_lwpolyline([(0, 14150), (6000, 14150), (6000, 17000)],
                   dxfattribs={"layer": "A-FLOR"})              # floor outline
label("B8_300 X 600", 3000, 13500)

# Z6 -- stacked pair, labels adversarial: B10 600-wide (edges 17000/17600),
# B11 300-wide below (edges 16000/16300); B11's label sits BETWEEN them
pair(22000, 17300, 27000, 17300, 600)
pair(22000, 16150, 27000, 16150, 300)
label("B10_600 X 900", 24500, 17750)        # above B10 (off-midspan)
label("B11_300 X 600", 24300, 16500)        # between B10 and B11: nearer B10's mid
# the third stacked row far below keeps dedupe honest
pair(22000, 14000, 27000, 14000, 300)
label("B13_300 X 600", 24500, 14350)

# Z7 -- curved beam: concentric arc chains r=2850/3150 about (25000,5000), 0..90 deg
for radius in (2850.0, 3150.0):
    for a0, a1 in ((0, 30), (30, 60), (60, 90)):     # chains of arc fragments
        msp.add_arc((25000, 5000), radius, a0, a1, dxfattribs={"layer": "S-BEAM"})
_mid = math.radians(45.0)
label("B9_300 X 600", 25000 + 3350 * math.cos(_mid), 5000 + 3350 * math.sin(_mid), 0.0)

# Z8 -- junk that must fabricate NOTHING
line(30000, 0, 34000, 0)                    # lone edge, no partner
line(30000, 0, 34000, 0)                    # exact duplicate of it
line(31000, 2000, 31000, 2000)              # zero-length line
msp.add_lwpolyline([(30000, 4000), (33000, 4000), (33000, 4020), (30000, 4020),
                    (30000, 4000)], dxfattribs={"layer": "S-BEAM"})   # 20 mm sliver
label("B99_300 X 600", 31000, 6000)         # orphan label, no geometry near it
label("125 THK.", 31000, 8000)              # slab thickness note on the text layer

doc.saveas(OUT)
print("wrote", OUT)

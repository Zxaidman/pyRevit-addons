# Findings Report — CAD to BIM (as of v0.12.0)

Issues observed across Test10 / Test11, their root cause, status, and the planned
fix. "Fixed" = shipped + validated on the test JSON; "Open" = not yet addressed.

## Root cause shared by most open issues
At round and angled (rotated) columns, the CAD draws beam/column **junction**
geometry (extra arcs + short lines) that overlaps and **clips** the neighbouring
column and beam outlines. The reader faithfully returns the clipped polylines, so a
600x750 column comes back as 463x750, a 750x900 as 300x900, a clean beam becomes a
1064 mm-wide blob, etc. Fixing this means reconstructing the affected members from
their surviving parallel edge-lines rather than trusting the clipped outline.

## FIXED
1. Grid-9 / perimeter beams missing.
   - Cause: drawn as two parallel ~300 mm edge lines, not closed rectangles; the old
     reader dropped bare lines.
   - Fix: parallel-line pairing (shapes.pair_parallel_lines) -> centreline + width.
     Also fixed script.py to pass the detected circles so arc-junction logic runs.
   - Validated Test11: 8 grid-9 beams recovered.
2. False beams at round columns.
   - Cause: junction fillet arcs treated as curved beams.
   - Fix: arcs centred on a detected round column are classified as junctions and
     ignored. Validated: all arcs = junctions, 0 false beams.
3. Spurious 1064 mm-wide beam at the F-G junction.
   - Cause: junction-clipped beam polyline bbox'd to 1064 wide.
   - Fix: beam-width limit (default 150-600 mm) drops it; raising the max re-admits
     it. Validated Test11.
4. Rotated columns oversized / wrong (earlier).
   - Fix: minimum-area oriented rectangle (recovers true size + angle). Confirmed good
     by AnonGee.

## OPEN (next)
1. Angled columns at F and G (500x900) not created.
   - Cause: outlines clipped by the junction -> degenerate / wrong size, so detection
     drops or mis-sizes them.
   - Planned fix: reconstruct angled columns from their two parallel edge-lines
     (AnonGee confirmed they exist, though possibly broken into segments). Pair the
     edges (like beams), then form the oriented rectangle from the paired edges +
     end caps. Use the column b/h limits to validate the result.
2. Two vertical beams missing (grid A and grid F, rows 8-9).
   - Cause: same junction clipping consumes/*distorts* the beam outline near the
     angled column, so neither a closed outline nor a clean parallel pair survives.
   - Planned fix: comes largely for free with (1) -- once junction geometry is handled
     and broken parallel segments are merged before pairing, these beams pair up.
3. Curved-beam placement not implemented.
   - Status: detection (concentric non-junction arc pairs) is in place; no genuine
     curved beam exists in the current CADs, so placement (arc framing via an Arc
     curve) is deferred until there is a case to test against.
4. Beam-to-column gaps at junctions.
   - Beams stop at the column face; the stub into the column is the junction we skip.
   - Planned fix (optional): extend a beam centreline to the column centre when its
     end meets a round/angled column (AnonGee: only at such ends, not every beam).

## Tuning knobs now available (v0.12.0)
- Beam width min/max, column b min/max, column h min/max (window sliders + inputs).
- Standard sizes for columns ("b x h, ...") and beam widths ("w, ..."); measurements
  snap to the nearest standard within ~60 mm.

# CAD to BIM -- staged rebuild roadmap

Disciplined, one-element-at-a-time rebuild on the new DXF (ezdxf) source. We do
NOT advance a stage until every listed case works and is verified in Revit.

## Root cause that reset this (v0.13.0 in-Revit test, Test10)
The old flow read the *Revit link*, whose importer MERGES connected segments into
closed polylines -- so columns arrived as closed quads ready to decompose. The new
flow reads the *raw DXF with ezdxf*, which returns the **un-merged LINE segments**.
Consequences seen in Test10:
- `columns: rect 0 ... 403 line-member` -- column outlines are loose lines, never
  assembled into closed loops, so `parse_column_polyline` builds nothing.
- Column rectangle sides (two parallel lines) get grabbed by the beam parallel-line
  pairing -> beams created where columns should be ("beams in place of columns").

**The foundational fix (Stage 2 prerequisite):** assemble loose DXF line-soup into
closed loops per layer BEFORE classification/decomposition -- restoring what the
Revit importer did for free. Snap endpoints with tolerance, walk connected edges
into rings, keep open chains aside. Only then run the existing shapes pipeline.

## Stage gate
Build is now defaulted to **grids only** (columns/beams/slabs unchecked) so the
model stays clean while we validate each stage. Opt a stage in only when its
predecessor is signed off.

## Stage 1 -- GRIDS  (in progress)
- [ ] Orthogonal grids (H + V) land in the right place, correct count.
- [ ] Angled / rotated grid lines created correctly (Grid.Create on a horizontal
      plane; naming may be approximate -- acceptable until text-driven names).
- [ ] Arc grids created.
- [ ] No duplicate/overlapping grids; existing-name clashes handled.
- Verify: build grids only; compare to the DXF; report any wrong/missing grid.

## Stage 2 -- COLUMNS  (blocked on the line-assembly foundation)
- [ ] Line-soup -> closed-loop assembly per column layer (the prerequisite above).
- [ ] Orthogonal rectangle.
- [ ] Rotated / angled rectangle (min-area oriented rect).
- [ ] Round (circle from arcs/segments).
- [ ] Lift / staircase comb: decompose into legs, each placed as its own rect.
- [ ] Column sides must NOT be consumed by the beam pass (resolve column regions
      first, then exclude them from beam pairing).

## Stage 3 -- BEAMS
- [ ] Single-line and parallel-pair beams, width from gap, depth from text mark.
- [ ] Beam <-> column junctions (trim/extend at the column face; no false beams
      from column outlines).

## Stage 4 -- SLAB
- [ ] Derive slab loops from the beam graph (planar-face traversal) -> Floor.Create.

## Working agreement
Each stage: implement -> user tests in Revit on the real DXF -> report per-case
result -> fix -> re-verify -> sign off -> next stage. Keep the build checkboxes as
the per-stage switch.

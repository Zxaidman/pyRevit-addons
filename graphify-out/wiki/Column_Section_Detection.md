# Column Section Detection

> 19 nodes · cohesion 0.11

## Key Concepts

- **build_column_sections()** (9 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **detect_fragmented_cores()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_filter_column_entries()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_find_core_outlines()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_inside_rectangles()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_apply_column_marks()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_pts_mm()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_ring_closed()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_standard_dims_mm()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_polyline_length_ft()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Snap each rectangle's b/h to standard sizes and drop out-of-range ones.      Sna** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Refine each column rectangle from the nearest sized DXF mark, in place.      Ado** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Locate large UNCLOSED outlines (likely fragmented lift/stair cores) among the** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Flag a likely fragmented lift/stair core: a large UNCLOSED outline left on the** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Decompose every column-category polyline into rectangular sections, and     deri** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **True if a polyline's first and last vertices coincide (a closed ring).      Both** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **[(x,y,z) feet ...] -> [[x_mm, y_mm], ...] integer pairs, for debug dumps.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **True if (cx, cy) falls within any rectangle's axis-aligned bbox.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Flatten standard (b, h) pairs into the set of distinct dimensions.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`

## Relationships

- [[cad2bim Report Builder]] (10 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`

## Audit Trail

- EXTRACTED: 48 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
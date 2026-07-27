# _carve_blob_from_labels()

> 18 nodes · cohesion 0.12

## Key Concepts

- **_carve_blob_from_labels()** (8 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **recover_core_walls_from_labels()** (6 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_rect_bounds_mm()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_connected_blobs()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_labels_for_blob()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_cells_free()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_dims_match()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_unique_edges()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_wall_rect()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Re-place fused-outline columns from their size labels, before text-correction.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **(x_min, y_min, x_max, y_max) of an axis-aligned rect dict, in mm.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Group rectangles into edge-adjacent components (a fused outline = one blob).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **(mark, small, big, lx, ly) for each sized label inside the blob's grown bbox.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Sorted grid edges with near-duplicates (float noise) merged.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **True when a w x h cell-rectangle matches the (b, h) label in either orientation.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Re-tile one fused blob into label-sized walls, or None if labels can't tile it.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **True when every cell in the range is inside the blob and not yet claimed.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **A wall rect dict (mm bounds -> internal-feet centre + mm size), long axis set.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`

## Relationships

- [[report.py]] (9 shared connections)
- [[_label_size()]] (1 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`

## Audit Trail

- EXTRACTED: 48 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
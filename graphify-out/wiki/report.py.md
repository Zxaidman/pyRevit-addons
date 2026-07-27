# report.py

> 22 nodes · cohesion 0.13

## Key Concepts

- **report.py** (67 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **export_json()** (7 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_mm()** (6 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_compact_columns()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_compact_beams()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_compact_circles()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_compact_texts()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **apply_circle_marks()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **format_beam_segments()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **format_column_sections()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **parse_standard_sizes()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **parse_standard_widths()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **snap_beam_ends_to_columns()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Plain-text lines summarising the column decomposition (no markup).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Pull a beam END onto a ROUND or ROTATED column's centre to close the junction ga** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Plain-text lines summarising beam derivation (no markup).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Internal feet -> whole mm (positions/sizes are integers for brevity).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **One compact dict per placed column rectangle: mark, b, h, position, angle.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Write a COMPACT run report (mm). No raw per-curve point dump -- just the     pla** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Parse '300x600, 300x750' -> [(300.0, 600.0), ...] (b<=h). Tolerant of junk.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Stamp the nearest column label's MARK onto each circular column.      correct_co** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Parse '300, 450, 600' -> [300.0, 450.0, 600.0]. Tolerant of junk.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`

## Relationships

- [[build_column_sections()]] (10 shared connections)
- [[_carve_blob_from_labels()]] (9 shared connections)
- [[correct_columns_with_text()]] (8 shared connections)
- [[build_beam_segments()]] (7 shared connections)
- [[build_category_counts()]] (5 shared connections)
- [[_bbox_half()]] (4 shared connections)
- [[_apply_beam_marks()]] (4 shared connections)
- [[_curved_beams_from_edges()]] (3 shared connections)
- [[_label_size()]] (2 shared connections)
- [[marks.py]] (1 shared connections)
- [[shapes.py]] (1 shared connections)
- [[columns.py]] (1 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`

## Audit Trail

- EXTRACTED: 114 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
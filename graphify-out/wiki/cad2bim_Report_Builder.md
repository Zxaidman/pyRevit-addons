# cad2bim Report Builder

> 28 nodes · cohesion 0.10

## Key Concepts

- **report.py** (67 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **export_json()** (7 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_mm()** (6 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **build_category_counts()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_compact_columns()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **format_summary()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **build_layer_counts()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_compact_beams()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_compact_circles()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **_compact_texts()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **format_console()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **apply_circle_marks()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **format_beam_segments()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **format_column_sections()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **parse_standard_sizes()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **parse_standard_widths()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **{layer_key: {'count': int, 'kinds': {kind: int}}} for the summary table.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Plain-text lines summarising the column decomposition (no markup).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **{category: count}, including unmapped, so nothing is silently dropped.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Return a list of plain-text lines describing the read (no markup).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Plain-text lines summarising beam derivation (no markup).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Short, copy-friendly console summary. Full detail goes into the JSON.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Internal feet -> whole mm (positions/sizes are integers for brevity).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **One compact dict per placed column rectangle: mark, b, h, position, angle.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- **Write a COMPACT run report (mm). No raw per-curve point dump -- just the     pla** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`
- *... and 3 more nodes in this community*

## Relationships

- [[Column Section Detection]] (10 shared connections)
- [[Blob/Label Column Carving]] (9 shared connections)
- [[Column Text Correction]] (8 shared connections)
- [[Beam Segment Building]] (7 shared connections)
- [[Bounding Box Overlap]] (4 shared connections)
- [[Curved Beam Marks]] (4 shared connections)
- [[Curved Beam Detection]] (3 shared connections)
- [[Beam Centerline Geometry]] (2 shared connections)
- [[Beam Label Sizing]] (2 shared connections)
- [[Layer Classification & Mapping]] (1 shared connections)
- [[Schedule Mark Parsing]] (1 shared connections)
- [[cad2bim Config]] (1 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/report.py`

## Audit Trail

- EXTRACTED: 130 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
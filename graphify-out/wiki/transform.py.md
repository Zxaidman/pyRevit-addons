# transform.py

> 25 nodes · cohesion 0.11

## Key Concepts

- **transform.py** (9 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Affine** (7 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **build_dxf_to_internal()** (7 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **.apply()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **.from_basis()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **_bbox_after()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **empirical_affine()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **.scale_translate()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **apply_to_records()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **apply_to_texts()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **bbox_of_records()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **from_link()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **_size_mismatch()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **.__init__()** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Largest per-axis fractional size difference between two bboxes (0 = same).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Exact DXF-coords -> Revit-internal-feet affine from the link's OWN transform.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Return (affine, diagnostics) mapping DXF coords -> Revit internal feet.      Pri** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Rewrite every record's points through the affine (in place); return records.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Fill each text's point_internal from its DXF point; return texts.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **A 3x4 affine map: p' = M * (x, y, z) + t. Plain floats; Revit-free.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Build from Revit-style basis vectors + origin (each an (x, y, z)).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Uniform scale + translation, no rotation (the empirical fallback).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Axis-aligned (xmin, ymin, xmax, ymax) over every point, or None if empty.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Transform the four corners of a 2D bbox and return the new aligned bbox.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`
- **Uniform scale+translation aligning the DXF bbox onto the Revit bbox.      Scale** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`

## Relationships

- [[object]] (1 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/geom/transform.py`

## Audit Trail

- EXTRACTED: 69 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
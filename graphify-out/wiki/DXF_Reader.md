# DXF Reader

> 29 nodes · cohesion 0.15

## Key Concepts

- **dxf_reader.py** (21 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_geometry_record()** (10 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_walk()** (10 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_xyz()** (10 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **DxfReadResult** (7 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/model.py`
- **_read_insert()** (7 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_arc_points()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_insert_point()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **read_dxf()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_to_wcs()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_add_text()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_circle_points()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_ensure_ezdxf()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_layer()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_flatten()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_lwpolyline_points()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_polyline_points()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **_safe()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **ezdxf_available()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **.__init__()** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/model.py`
- **.is_empty()** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/model.py`
- **Geometry + text extracted from a DXF file by the ezdxf reader.      `records` ar** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/model.py`
- **Explode a block reference: nested geometry (WCS) + its ATTRIB tag text.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **[start, mid, end] of an ARC in WCS (matches the Revit reader's convention).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- **Best text anchor: insertion point, falling back to alignment point.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`
- *... and 4 more nodes in this community*

## Relationships

- [[CAD/DXF Data Model]] (6 shared connections)
- [[Beam Text Sizing Tests]] (1 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/model.py`
- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/dxf_reader.py`

## Audit Trail

- EXTRACTED: 125 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
# Family Symbol Loaders

> 18 nodes · cohesion 0.14

## Key Concepts

- **get_element_name()** (11 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/compat.py`
- **compat.py** (6 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/compat.py`
- **cad_links.py** (6 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/cad_links.py`
- **describe_link()** (6 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/cad_links.py`
- **element_id_value()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/compat.py`
- **structural_framing_symbols()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/beams.py`
- **levels()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **structural_column_symbols()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **runtime_summary()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/compat.py`
- **find_cad_links()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/cad_links.py`
- **[(label, ElementId)] of loaded structural-framing (beam) family types.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/beams.py`
- **[(label, ElementId)] of loaded structural-column family types, sorted.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **[(name, ElementId)] of levels, sorted by elevation (lowest first).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **Return the integer value of an ElementId across Revit versions.      Fail-fast o** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/compat.py`
- **Best-effort element name; returns None instead of raising on odd subtypes.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/compat.py`
- **One-line description of the live Python/IronPython runtime.      Used by the sta** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/compat.py`
- **Return all linked CAD ImportInstances in the document (possibly empty).      Fai** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/cad_links.py`
- **Human-readable label for a linked CAD instance via its CADLinkType.      Never r** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/cad_links.py`

## Relationships

- [[Column Placement]] (5 shared connections)
- [[Beam Placement]] (4 shared connections)
- [[DXF Geometry Reader]] (3 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/beams.py`
- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/compat.py`
- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/readers/cad_links.py`

## Audit Trail

- EXTRACTED: 54 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
# Column Placement

> 21 nodes · cohesion 0.15

## Key Concepts

- **columns.py** (16 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **mm_to_internal()** (6 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/unit_convert.py`
- **place_circular_columns()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **place_columns()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **_resolve_circular_symbol()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **_resolve_symbol()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **_set_dimension()** (5 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **_find_type_in_family()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **_set_mark()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **_set_top_level()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **unit_convert.py** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/unit_convert.py`
- **internal_to_mm()** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/unit_convert.py`
- **Place a circular column for every detected circle, sizing its diameter.      Mir** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **Return a FamilySymbol sized b_mm x h_mm, duplicating+caching as needed.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **Return a FamilySymbol of the given diameter, duplicating+caching as needed.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **Set the first writable matching type parameter to value_mm; True if set.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **Stamp the instance 'Mark' parameter (e.g. C1) when a mark was resolved.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **Attach the column top to top_level with zero offsets (base set at placement).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **Place a rectangular column for every section rectangle.      Conventions (per th** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- **Convert a millimetre value to Revit internal units (decimal feet).      Raises V** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/unit_convert.py`
- **Convert a Revit internal-unit (feet) value to millimetres.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/unit_convert.py`

## Relationships

- [[Family Symbol Loaders]] (5 shared connections)
- [[Beam Placement]] (3 shared connections)
- [[Beam Centerline Geometry]] (1 shared connections)
- [[cad2bim Config]] (1 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/builders/columns.py`
- `AnonGee.extension/lib/py3/anongee_toolkit/cad2bim/unit_convert.py`

## Audit Trail

- EXTRACTED: 74 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
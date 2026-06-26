# Revit Application Access

> 18 nodes · cohesion 0.14

## Key Concepts

- **get_current_doc()** (15 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/application.py`
- **get_current_uidoc()** (7 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/application.py`
- **get_selected_elements()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/selection.py`
- **get_rebars()** (4 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/structural/rebars.py`
- **application.py** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/application.py`
- **get_app()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/application.py`
- **get_elements_by_categories()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/filtering.py`
- **set_selection()** (3 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/selection.py`
- **selection.py** (2 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/selection.py`
- **Return the active Revit UIApplication (``__revit__``).** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/application.py`
- **Return the active UIDocument, or raise RuntimeError if none is open.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/application.py`
- **Return the active Document, or raise RuntimeError if none is open.** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/application.py`
- **filtering.py** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/filtering.py`
- **Collect all non-type elements that belong to the given category names.      Args** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/filtering.py`
- **Return the currently selected elements as a Python list.      Returns an empty l** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/selection.py`
- **Highlight *element_ids* in the active Revit UI.      Args:         element_ids (** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/revit/selection.py`
- **rebars.py** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/structural/rebars.py`
- **Return rebars from the active selection, or all rebars in the document.      Arg** (1 connections) — `AnonGee.extension/lib/py3/anongee_toolkit/structural/rebars.py`

## Relationships

- [[Element Family/Type Names]] (2 shared connections)
- [[Parameter Get/Set]] (2 shared connections)
- [[Generic Bulk Delete Dialog]] (1 shared connections)
- [[Generic Bulk Rename Dialog]] (1 shared connections)
- [[Revit Transaction Context]] (1 shared connections)
- [[Revit Transaction Group]] (1 shared connections)
- [[View Utilities]] (1 shared connections)

## Source Files

- `AnonGee.extension/lib/py3/anongee_toolkit/revit/application.py`
- `AnonGee.extension/lib/py3/anongee_toolkit/revit/filtering.py`
- `AnonGee.extension/lib/py3/anongee_toolkit/revit/selection.py`
- `AnonGee.extension/lib/py3/anongee_toolkit/structural/rebars.py`

## Audit Trail

- EXTRACTED: 32 (60%)
- INFERRED: 21 (40%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*
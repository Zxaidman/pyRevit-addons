# AnonGee Toolkit — Public API Reference

**Version:** 1.1.0  
**Runtime:** CPython 3 (pyRevit engine)  
**Target:** Autodesk Revit 2024 / 2025  

---

## Table of Contents

1. [Overview](#overview)
2. [Import Patterns](#import-patterns)
3. [revit — Revit API Abstraction](#revit)
   - [application](#revitapplication)
   - [transactions](#revittransactions)
   - [parameters](#revitparameters)
   - [selection](#revitselection)
   - [elements](#revitelements)
   - [filtering](#revitfiltering)
   - [geometry](#revitgeometry)
   - [units](#revitunits)
   - [views](#revitviews)
   - [compatibility](#revitcompatibility)
4. [structural — Domain Helpers](#structural)
5. [ui — User Interface](#ui)
   - [dialogs](#uidialogs)
   - [xaml](#uixaml)
   - [forms](#uiforms)
6. [io — External I/O](#io)
7. [operations — Bulk Operations](#operations)
8. [utils — Utilities](#utils)
9. [cad2bim — CAD-to-BIM Pipeline](#cad2bim)
   - [Root modules](#cad2bim-root)
   - [geom — geometry](#cad2bimgeom)
   - [classify — text & layers](#cad2bimclassify)
   - [readers — extraction](#cad2bimreaders)
   - [builders — Revit elements](#cad2bimbuilders)

---

## Overview

`anongee_toolkit` is the shared library layer for all AnonGee pyRevit tools. It
abstracts away the parts of the Revit API and pythonnet that are most likely to
crash or require boilerplate in CPython 3:

- **Revit document access** without touching `pyrevit.revit` (which causes CPython 3
  event-handler crashes)
- **Transaction context managers** with automatic rollback on exception
- **Parameter I/O** that handles all four `StorageType` variants
- **WPF base class** with a pre-wired badge feedback strip and close button
- **Native .NET dialogs** instead of `pyrevit.forms` (which also crashes under CPython 3)
- **Revit 2024 compatibility shims** for the `ElementId` Int32 → Int64 change

Everything in this document is importable directly from `anongee_toolkit` **or**
from the specific subpackage. Both styles are supported.

---

## Import Patterns

```python
# ── Flat import from the package root (recommended for scripts) ──────────────
from anongee_toolkit import get_current_doc, RevitTransaction, alert

# ── Subpackage import (preferred inside library code) ────────────────────────
from anongee_toolkit.revit import get_current_doc, RevitTransaction
from anongee_toolkit.ui import WpfDialogBase, load_xaml

# ── Deep import (always valid, most explicit) ─────────────────────────────────
from anongee_toolkit.revit.application import get_current_doc
from anongee_toolkit.revit.transactions import RevitTransaction
```

---

## `revit`

All functions here are also importable as `from anongee_toolkit.revit import …`
or directly as `from anongee_toolkit import …`.

### `revit.application`

Safe access to the Revit host application. Bypasses `pyrevit.revit` to avoid
CPython 3 crashes in event callbacks.

---

#### `get_app()`

```python
def get_app() -> UIApplication
```

Return the active `UIApplication` (`__revit__`).

Checks `__main__` first, then `builtins` as a fallback.

**Raises:** `RuntimeError` — if `__revit__` cannot be resolved (i.e. the code
is running outside a pyRevit script context).

---

#### `get_current_uidoc()`

```python
def get_current_uidoc() -> UIDocument
```

Return the active `UIDocument`.

**Raises:** `RuntimeError` — if no document is open in the Revit UI.

---

#### `get_current_doc()`

```python
def get_current_doc() -> Document
```

Return the active `Document`.

**Raises:** `RuntimeError` — if no project or family is open.

**Example:**

```python
from anongee_toolkit import get_current_doc

doc = get_current_doc()
print(doc.Title)
```

---

### `revit.transactions`

Context managers that automatically commit on success and roll back on any
unhandled exception.

---

#### `RevitTransaction`

```python
class RevitTransaction:
    def __init__(
        self,
        name: str = "AnonGee Transaction",
        doc: Document = None,
        suppress_warnings: bool = False,
    )
```

Context manager for a single Revit `Transaction`.

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Label shown in the Revit undo stack. |
| `doc` | `Document` | Target document. Defaults to the active document. |
| `suppress_warnings` | `bool` | Attach `SuppressWarningsPreprocessor` to silence geometry warnings during batch operations. |

**Behaviour:**
- `__enter__` starts the transaction and returns the `Transaction` object.
- `__exit__` commits on a clean exit.
- `__exit__` rolls back and re-raises if an exception occurred inside the block.

**Raises:** `RuntimeError` — if the transaction fails to commit.

**Example:**

```python
from anongee_toolkit import RevitTransaction, get_current_doc

doc = get_current_doc()
with RevitTransaction("Set Mark", doc):
    for elem in elements:
        elem.LookupParameter("Mark").Set("A1")
```

---

#### `RevitTransactionGroup`

```python
class RevitTransactionGroup:
    def __init__(
        self,
        name: str = "AnonGee Transaction Group",
        doc: Document = None,
    )
```

Context manager for a Revit `TransactionGroup`. Assimilates all child
transactions into one undo step on clean exit; rolls back the entire group on
exception.

**Example:**

```python
from anongee_toolkit import RevitTransaction, RevitTransactionGroup

with RevitTransactionGroup("Batch Place"):
    with RevitTransaction("Place Columns"):
        ...
    with RevitTransaction("Place Beams"):
        ...
```

---

#### `SuppressWarningsPreprocessor`

```python
class SuppressWarningsPreprocessor(IFailuresPreprocessor)
```

`IFailuresPreprocessor` that silently discards all `FailureSeverity.Warning`
messages. Pass it to `RevitTransaction(suppress_warnings=True)` or attach it
manually via `Transaction.GetFailureHandlingOptions()`.

---

### `revit.parameters`

---

#### `get_parameter(element, param_name)`

```python
def get_parameter(element, param_name: str) -> Parameter | None
```

Return the `Parameter` named `param_name` from `element`.

Resolution order: **instance** → **ElementType**. Returns `None` if not found.

---

#### `get_parameter_value(element, param_name, as_string=True)`

```python
def get_parameter_value(
    element,
    param_name: str,
    as_string: bool = True,
) -> str | int | float | ElementId | None
```

Read a parameter value, handling all four `StorageType` variants.

| `StorageType` | `as_string=True` | `as_string=False` |
|---|---|---|
| `String` | raw string | raw string |
| `Integer` | formatted string | `int` |
| `Double` | formatted string | `float` |
| `ElementId` | `"[<id>] <element name>"` | `ElementId` |

Returns `None` if the parameter does not exist.

**Example:**

```python
from anongee_toolkit import get_parameter_value

mark = get_parameter_value(column, "Mark")            # → "C1"
area = get_parameter_value(floor, "Area", as_string=False)  # → 42.5 (float, sq ft)
```

---

#### `set_parameter_value(element, param_name, value)`

```python
def set_parameter_value(element, param_name: str, value) -> bool
```

Set a parameter value. Tries `SetValueString` first (honours Revit unit
formatting), then falls back to the native setter.

Returns `False` if the parameter is read-only, not found, or if an exception
occurs; `True` on success.

> Must be called inside a `RevitTransaction`.

---

### `revit.selection`

---

#### `get_selected_elements(uidoc=None, doc=None)`

```python
def get_selected_elements(
    uidoc: UIDocument = None,
    doc: Document = None,
) -> list
```

Return the currently highlighted elements as a Python list. Returns `[]` if
nothing is selected.

---

#### `set_selection(element_ids, uidoc=None)`

```python
def set_selection(
    element_ids: Iterable[ElementId],
    uidoc: UIDocument = None,
) -> bool
```

Highlight `element_ids` in the active Revit UI. Handles the
`System.Collections.Generic.List[ElementId]` mapping internally.

Returns `True` if at least one element was selected; `False` otherwise.

---

### `revit.elements`

---

#### `get_family_name(element)`

```python
def get_family_name(element) -> str
```

Return the Family Name, trying three fallback levels:

1. `FamilyInstance.Symbol.Family.Name`
2. `ElementType.Name` (for system families such as Walls)
3. `Category.Name` (last resort)

Returns `"N/A"` if the element is `None` or no name can be found.

---

#### `get_type_name(element)`

```python
def get_type_name(element) -> str
```

Return the Type Name of `element`, or `"N/A"` if it cannot be resolved.

---

### `revit.filtering`

---

#### `get_elements_by_categories(category_names, view_id=None, doc=None)`

```python
def get_elements_by_categories(
    category_names: list[str],
    view_id: ElementId = None,
    doc: Document = None,
) -> list
```

Collect all non-type elements belonging to the given Revit category names using
`ElementMulticategoryFilter`.

| Parameter | Description |
|---|---|
| `category_names` | List of category names, e.g. `["Structural Columns", "Structural Framing"]`. |
| `view_id` | When provided, restricts collection to elements visible in that view. |
| `doc` | Target document; defaults to the active document. |

Returns an empty list if no matching categories are found.

**Example:**

```python
from anongee_toolkit import get_elements_by_categories

columns = get_elements_by_categories(["Structural Columns"])
```

---

### `revit.geometry`

---

#### `get_solid_volume_m3(element)`

```python
def get_solid_volume_m3(element) -> float
```

Return the total net solid volume of `element` in cubic metres.

Iterates through all `Solid` and `GeometryInstance` objects at medium detail
level. Returns `0.0` on any geometry error instead of raising.

---

#### `bounding_boxes_overlap(bb1, bb2, tol=0.08)`

```python
def bounding_boxes_overlap(
    bb1: BoundingBoxXYZ,
    bb2: BoundingBoxXYZ,
    tol: float = 0.08,
) -> bool
```

Return `True` if two `BoundingBoxXYZ` objects overlap in 3-D space.

`tol` is the expansion tolerance in decimal feet (default 0.08 ft ≈ 1 inch).
Returns `False` if either box is `None`.

---

### `revit.units`

All Revit lengths are stored in **decimal feet** internally. These helpers
convert to/from the engineering units used in AnonGee tools (metres and
millimetres).

#### Constants

| Name | Value | Description |
|---|---|---|
| `FT_TO_MM` | `304.8` | Feet → millimetres |
| `FT_TO_M` | `0.3048` | Feet → metres |
| `CF_TO_M3` | `0.028316846592` | Cubic feet → cubic metres |
| `SF_TO_M2` | `0.09290304` | Square feet → square metres |

#### Converters

| Function | Signature | Returns |
|---|---|---|
| `m_to_mm` | `(meters) → int` | Metres → mm, rounded to nearest integer |
| `mm_to_ft` | `(mm) → float` | Millimetres → decimal feet |
| `m_to_ft` | `(meters) → float` | Metres → decimal feet |
| `ft_to_mm` | `(feet) → float` | Decimal feet → millimetres |
| `clean_ft` | `(feet) → float` | Round feet to nearest mm then back to feet |

---

#### `strip_unit(value)`

```python
def strip_unit(value) -> int | float | original_value
```

Convert `"<number><known unit>"` strings to a native Python number.

Only strips recognised engineering unit suffixes (mm, m, kg, kN, MPa, …).
Strings with unknown suffixes (e.g. `"10-20"`, `"TYPE-A"`) are returned
unchanged.

**Example:**

```python
strip_unit("500mm")     # → 500   (int)
strip_unit("2.5 m")     # → 2.5  (float)
strip_unit("10-20")     # → "10-20"  (unchanged)
strip_unit(304.8)       # → 304.8   (non-string, unchanged)
```

---

### `revit.views`

---

#### `get_eligible_views(doc=None)`

```python
def get_eligible_views(doc: Document = None) -> list[View]
```

Return a name-sorted list of non-template views whose `ViewType` is one of:
`FloorPlan`, `CeilingPlan`, `EngineeringPlan`, `Section`, `Elevation`, `ThreeD`.

Use this to populate a "Select View" ComboBox.

---

#### `get_view_label(view)`

```python
def get_view_label(view: View) -> str
```

Return `"<view name> [<type label>]"`, e.g. `"Level 1 [Floor Plan]"`.

---

#### `ALLOWED_VIEW_TYPES`

`frozenset` of the six `ViewType` values considered eligible by
`get_eligible_views`.

---

### `revit.compatibility`

Shims for the `ElementId` integer-type change introduced in Revit 2024.

---

#### `create_element_id(id_value)`

```python
def create_element_id(id_value: int) -> ElementId
```

Create an `ElementId` from an integer, automatically using `System.Int64` on
Revit 2024+ and `int` on Revit 2023.

**Raises:** `TypeError` — if `id_value` is not an integer.

---

#### `get_element_id_value(element_id)`

```python
def get_element_id_value(element_id: ElementId) -> int
```

Extract the integer value from an `ElementId`, using `.Value` on Revit 2024+
and `.IntegerValue` on Revit 2023.

**Raises:** `TypeError` — if `element_id` is not an `ElementId`.

---

## `structural`

Also importable as `from anongee_toolkit.structural import …`.

---

#### `get_rebars(doc=None, uidoc=None)`

```python
def get_rebars(
    doc: Document = None,
    uidoc: UIDocument = None,
) -> tuple[list, bool]
```

Return rebars from the active selection, or all rebars in the document as a
fallback.

**Returns:** `(rebars, is_from_selection)` where `is_from_selection` is `True`
when the list came from the UI selection and `False` when it came from a
whole-document collect.

**Example:**

```python
from anongee_toolkit import get_rebars

rebars, from_selection = get_rebars()
if not from_selection:
    print("No selection — processing all {} rebars".format(len(rebars)))
```

---

## `ui`

Also importable as `from anongee_toolkit.ui import …`.

### `ui.dialogs`

---

#### `WpfDialogBase`

```python
class WpfDialogBase:
    def __init__(self, ui_dir: str)
```

Base class for all AnonGee WPF dialogs.

Subclass it and call `super().__init__(ui_dir)` to get:

- XAML loaded from `<ui_dir>/ui.xaml`
- Window icon loaded from `<ui_dir>/icon.png` (silently skipped if absent)
- Badge feedback strip pre-wired (`BadgeInfo`, `BadgeSuccess`, `BadgeError` and
  their associated `*Text` TextBlocks found by name)
- `BtnClose` connected to `window.Close()` automatically

**Instance attributes:**

| Attribute | Type | Description |
|---|---|---|
| `window` | `Window` | The loaded WPF `Window` object. Bind additional controls to it. |

**Methods:**

| Method | Description |
|---|---|
| `show_info(message)` | Display message in the info (blue) badge. |
| `show_success(message)` | Display message in the success (green) badge. |
| `show_error(message)` | Display message in the error (red) badge. |
| `flush_ui()` | Force the WPF dispatcher to process pending render work immediately. Use before long operations to keep the UI responsive. |
| `show()` | Open the dialog as a modal window (`ShowDialog()`). |

**Minimal subclass example:**

```python
import os
from anongee_toolkit import WpfDialogBase, RevitTransaction, get_current_doc

class MyDialog(WpfDialogBase):
    def __init__(self):
        ui_dir = os.path.dirname(__file__)
        super().__init__(ui_dir)

        self._btn_run = self.window.FindName("BtnRun")
        self._btn_run.Click += self._on_run

    def _on_run(self, sender, args):
        self.show_info("Running…")
        self.flush_ui()
        with RevitTransaction("My Operation"):
            ...  # Revit API calls
        self.show_success("Done.")

MyDialog().show()
```

---

#### `DebounceTimer`

```python
class DebounceTimer:
    def __init__(self, callback: callable, delay_ms: int = 300)
```

Wrap a WPF `DispatcherTimer` so rapid UI events (e.g. text-box changes) only
trigger `callback` once, after `delay_ms` milliseconds of silence.

**Methods:**

| Method | Description |
|---|---|
| `reset()` | Restart the countdown. Call this on every input event. |
| `stop()` | Cancel any pending callback. |

**Example:**

```python
from anongee_toolkit import DebounceTimer

def _on_filter_changed():
    self._rebuild_list(self._search_box.Text)

self._debounce = DebounceTimer(_on_filter_changed, delay_ms=250)

def _search_changed(sender, args):
    self._debounce.reset()

self._search_box.TextChanged += _search_changed
```

---

### `ui.xaml`

---

#### `load_xaml(xaml_path)`

```python
def load_xaml(xaml_path: str) -> Window
```

Load a WPF `Window` from a `.xaml` file on disk.

The `FileStream` is closed immediately after parsing so the file is never
locked while the dialog is open. Used internally by `WpfDialogBase`.

**Raises:** `IOError` — if the file does not exist.

---

#### `fill_combo(combo, label_id_pairs)`

```python
def fill_combo(
    combo,
    label_id_pairs: Iterable[tuple[str, ElementId]],
) -> dict[str, ElementId]
```

Populate a WPF `ComboBox` and return a `{label: ElementId}` mapping. The first
item is auto-selected.

**Example:**

```python
from anongee_toolkit import fill_combo, get_eligible_views, get_view_label

pairs = [(get_view_label(v), v.Id) for v in get_eligible_views()]
view_map = fill_combo(self._combo_views, pairs)

# Later, on ComboBox selection:
selected_id = view_map[self._combo_views.SelectedItem]
```

---

#### `select_combo_containing(combo, keywords)`

```python
def select_combo_containing(
    combo,
    keywords: Iterable[str],
) -> bool
```

Select the first `ComboBox` item whose label contains any of `keywords`
(case-insensitive). Returns `True` if a match was found.

**Example:**

```python
# Auto-select a "Level 1" view if present
select_combo_containing(self._combo_views, ["level 1", "ground"])
```

---

### `ui.forms`

Native .NET message boxes and file dialogs that bypass `pyrevit.forms` to avoid
CPython 3 crashes.

---

#### `alert(title, message)`

Show a warning `MessageBox` with an OK button. No return value.

---

#### `error(title, message, detail=None)`

Show a critical error `MessageBox`. When `detail` is provided it is appended
below a `--- technical detail ---` separator.

---

#### `info(title, message)`

Show an information `MessageBox` with an OK button. No return value.

---

#### `confirm(title, message)`

```python
def confirm(title: str, message: str) -> bool
```

Show a Yes/No `MessageBox`. Returns `True` if the user clicked **Yes**.

---

#### `pick_file(title="Select File", file_filter="All files (*.*)|*.*")`

```python
def pick_file(title: str = ..., file_filter: str = ...) -> str | None
```

Open a native `OpenFileDialog`. Returns the absolute file path, or `None` if
cancelled.

**Example:**

```python
from anongee_toolkit import pick_file

path = pick_file("Select DXF", "DXF files (*.dxf)|*.dxf|All files (*.*)|*.*")
if path:
    process(path)
```

---

#### `save_file(title="Save File", file_filter="All files (*.*)|*.*", default_name="")`

```python
def save_file(
    title: str = ...,
    file_filter: str = ...,
    default_name: str = "",
) -> str | None
```

Open a native `SaveFileDialog`. Returns the chosen path, or `None` if cancelled.

---

## `io`

Also importable as `from anongee_toolkit.io import …`.

---

### `ExcelComWriter`

```python
class ExcelComWriter:
    def __init__(self, visible: bool = False)
```

Late-bound COM wrapper for Microsoft Excel. Uses `System.Reflection` as a
fallback for method calls that strict pythonnet bindings reject, making the
class robust across Excel versions.

**Raises:** `RuntimeError` — if Excel is not installed or COM instantiation fails.

#### Methods

---

##### `add_sheet(name) → Worksheet`

Add a new worksheet named `name` after the last existing sheet.

---

##### `write_array(ws, top_row, left_col, data) → Range | None`

Write a 2-D Python list to an Excel range in a single COM call.

| Parameter | Description |
|---|---|
| `ws` | Excel Worksheet COM object. |
| `top_row` | 1-based row index of the top-left cell. |
| `left_col` | 1-based column index of the top-left cell. |
| `data` | `list[list]` — rows of values. |

---

##### `autofit_columns(ws)`

Auto-fit all column widths on `ws`.

---

##### `format_page_landscape(ws)`

Set the worksheet to landscape orientation, fit-to-1-page-wide.

---

##### `export_as_pdf(pdf_path)`

Export the active workbook as a PDF to `pdf_path`.

---

##### `save_and_show(filepath)`

Save the workbook as `.xlsx`, release COM locks, then make Excel visible.

**Raises:** `IOError` — if saving fails.

---

##### `close_without_saving()`

Discard the workbook and terminate the Excel process silently.

---

**Full example:**

```python
from anongee_toolkit import ExcelComWriter

writer = ExcelComWriter(visible=False)
try:
    ws = writer.add_sheet("Schedule")
    writer.write_array(ws, 1, 1, [
        ["Mark", "Level", "Width", "Depth"],
        ["C1",   "L1",   400,     400],
        ["C2",   "L1",   600,     400],
    ])
    writer.autofit_columns(ws)
    writer.format_page_landscape(ws)
    writer.save_and_show(r"C:\output\schedule.xlsx")
except Exception as exc:
    writer.close_without_saving()
    raise
```

---

## `operations`

Also importable as `from anongee_toolkit.operations import …`.

Both classes follow the same constructor signature and provide a `.show()`
method that opens a modal WPF dialog.

---

### `GenericBulkDeleteDialog`

```python
class GenericBulkDeleteDialog:
    def __init__(
        self,
        target_type: str,
        ui_dir: str,
        doc: Document = None,
    )
```

Reusable WPF dialog for bulk-deleting graphic style elements.

| `target_type` | Deletes |
|---|---|
| `"fillpattern"` | Fill Pattern Elements |
| `"linepattern"` | Line Pattern Elements |
| `"linestyle"` | Line Style sub-categories |

**Raises:** `ValueError` — if `target_type` is not one of the three keys above.

**UI features:**
- Live search box (filters list as you type)
- Select All / Select None buttons
- Live count badge showing `"N of M selected"`
- Confirmation dialog before deleting
- Badge feedback (info / success / error) after the operation
- Locked / in-use elements are skipped and counted separately

**Example (from a pushbutton `script.py`):**

```python
import os
from anongee_toolkit import GenericBulkDeleteDialog

GenericBulkDeleteDialog(
    target_type="fillpattern",
    ui_dir=os.path.dirname(__file__),
).show()
```

---

### `GenericBulkRenameDialog`

```python
class GenericBulkRenameDialog:
    def __init__(
        self,
        target_type: str,
        ui_dir: str,
        doc: Document = None,
    )
```

Reusable WPF dialog for bulk-renaming graphic style elements via find-and-replace.

Accepts the same `target_type` values as `GenericBulkDeleteDialog`.

**UI features:**
- Find / Replace text boxes with placeholder text
- Case-sensitive toggle checkbox
- Live match count badge
- Names ComboBox showing all current names in the model
- Badge feedback after the operation
- Locked / duplicate-name items are skipped and counted separately

**Example:**

```python
import os
from anongee_toolkit import GenericBulkRenameDialog

GenericBulkRenameDialog(
    target_type="linestyle",
    ui_dir=os.path.dirname(__file__),
).show()
```

---

## `utils`

Also importable as `from anongee_toolkit.utils import …`.

---

#### `create_com_array(*items)`

```python
def create_com_array(*items) -> System.Array[System.Object]
```

Build a `System.Object[]` from Python arguments.

Fixes the `"type expected"` error that CPython 3 / pythonnet raises when
passing a variable number of arguments to COM `InvokeMember` calls.

---

#### `parse_tsv_row(line)`

```python
def parse_tsv_row(line: str) -> list[str]
```

Parse one tab-delimited row, honouring RFC-4180-style double-quoted fields
(including escaped `""` inside quoted fields).

---

#### `read_tsv(path)`

```python
def read_tsv(path: str) -> list[list[str]]
```

Read a TSV file, trying `utf-8-sig`, `cp1252`, and `latin-1` encodings in that
order. Returns all rows as a list of field lists, or `[]` on failure.

Useful for reading native Revit Schedule exports (`.txt` TSV format).

**Example:**

```python
from anongee_toolkit import read_tsv

rows = read_tsv(r"C:\exports\schedule.txt")
header, *data = rows
for row in data:
    print(row[0], row[1])
```

---

#### `extract_numeric(text)`

```python
def extract_numeric(text) -> float | None
```

Extract the first valid floating-point number from a mixed string. Handles
European comma-as-decimal-separator notation. Regex-free.

**Example:**

```python
extract_numeric("W=300mm")     # → 300.0
extract_numeric("2,5 m")       # → 2.5
extract_numeric("no number")   # → None
```

---

#### `extract_bracket_int(text)`

```python
def extract_bracket_int(text: str) -> int | None
```

Parse a leading `[<int>]` prefix and return the integer. Used to unpack the
`"[<id>] <name>"` format emitted by `get_parameter_value` for `ElementId`
parameters.

**Example:**

```python
extract_bracket_int("[123456] Concrete - 30MPa")  # → 123456
extract_bracket_int("no bracket")                 # → None
```

---

## `cad2bim`

The pipeline behind the **CAD to BIM** pushbutton: read a DXF (or a linked CAD),
classify layers, parse member outlines and size labels, then create Revit grids,
columns and beams. Unlike the rest of the toolkit it is a single-consumer
pipeline, but its pure modules are Revit-free and unit-tested (`cad2bim/tests/`).

Modules are grouped by role; subpackage names avoid clashing with the sibling
toolkit packages.

```
cad2bim/
  config.py  model.py  compat.py  unit_convert.py  report.py   # root (shared)
  geom/        shapes.py  transform.py  compare.py             # Revit-free geometry
  classify/    marks.py  layers.py                             # Revit-free text/layers
  readers/     dxf_reader.py  geometry_reader.py               # extraction
               cad_links.py  dxf_linker.py
  builders/    columns.py  beams.py  grids.py  txn_failures.py # Revit element creation
```

Import the pure modules anywhere; the `readers`/`builders` modules require the
Revit API (run under the pyRevit CPython 3 engine):

```python
from anongee_toolkit.cad2bim.geom import shapes
from anongee_toolkit.cad2bim.classify import marks, layers
from anongee_toolkit.cad2bim.readers import dxf_reader
from anongee_toolkit.cad2bim.builders import columns, grids
```

<a name="cad2bim-root"></a>
### Root modules

| Module | Public API | Purpose |
|---|---|---|
| `config` | `DEFAULTS`, `mm_to_ft(mm)`, `merged(overrides)` | Central tunables — acceptance limits (`col_b_min_mm`, …) and tolerances. `merged()` overlays caller overrides on `DEFAULTS`. |
| `model` | `CurveRecord`, `TextRecord`, `DxfReadResult`, `ReadResult` | Plain data holders shared by readers, geometry and report. |
| `compat` | `element_id_value(id)`, `get_element_name(el)`, `runtime_summary()` | Revit 2024/2025 version-robustness helpers (the `ElementId` Int32→Int64 change, etc.). |
| `unit_convert` | `mm_to_internal(mm)`, `internal_to_mm(ft)` | mm ↔ Revit internal feet via `ForgeTypeId`/`UnitTypeId`. |
| `report` | `build_column_sections`, `correct_columns_with_text`, `build_beam_segments`, `format_console`, `export_json`, … | Orchestration: turn parsed records into placed/dropped sections, refine sizes from text, and emit the console summary + JSON report. |

<a name="cad2bimgeom"></a>
### `cad2bim.geom` — Revit-free geometry

`shapes.py` parses and recovers column footprints; `transform.py` maps DXF
coordinates to internal feet; `compare.py` diffs Revit-link vs DXF geometry.

**Shape classes:** `Rectangle` (axis-aligned), `OrientedRect` (rotated), and
`min_area_rect(ring, z=0.0) -> OrientedRect` (minimum-area enclosing box).

#### `parse_column_polyline(points)`

```python
def parse_column_polyline(points) -> dict
# -> {"status": "rectangle"|"composite"|"oriented_rect"|"degenerate",
#     "rectangles": [Rectangle|OrientedRect, ...], "approx": bool}
```

Parse one closed column outline. Axis-aligned rings are decomposed into
rectangles (`rectangle`/`composite`); rotated or irregular rings (incl. triangles)
are boxed as a single `oriented_rect`; outlines under 3 corners are `degenerate`.

#### `recover_oriented_columns(fragments, gap_ft, min_fragments=2, close_gap_ft=None)`

```python
def recover_oriented_columns(fragments, gap_ft,
                             min_fragments=2, close_gap_ft=None) -> list  # [OrientedRect]
```

Recover columns whose outline the CAD import broke into pieces at a junction:
clusters fragments within `gap_ft` and fits a min-area box. A lone fragment is
recovered only when its own ends nearly meet (within `close_gap_ft`).

#### `recover_rectilinear_columns(paths, z=0.0)`

```python
def recover_rectilinear_columns(paths, z=0.0, snap_ft=..., bridge_ft=...) -> tuple
# -> (rectangles, consumed_ids)
```

Recover columns from fused/unclosed **axis-aligned** wall outlines (a long wall
drawn as one comb with its perpendicular legs, or a clipped wall): stitches the
pieces into closed rectilinear rings and decomposes them. Returns the rectangles
plus the indices of consumed input paths (so the oriented pass cannot re-use them).

#### `build_circular_columns(arc_records, min_dia_ft=None, max_dia_ft=None)`

```python
def build_circular_columns(arc_records,
                           min_dia_ft=None, max_dia_ft=None) -> list  # [Circle]
```

Fit circular columns from arc/circle records (3-point circumcircle; handles a
full circle imported as a closed tessellation). Diameters outside the range drop.

Other helpers: `decompose_to_rectangles(ring, z=0.0)`, `assemble_rectilinear_rings`,
`build_line_spines`, `simplify_ring`, `is_rectilinear`, `snap_to_standard`.

<a name="cad2bimclassify"></a>
### `cad2bim.classify` — text & layers

#### `marks.parse_schedule(texts)`

```python
def parse_schedule(texts) -> dict   # {mark: (b_mm, h_mm)}
```

Build a `mark → size` lookup from a column schedule's text cells so a plan label
carrying only a mark (`"C9"`) can be sized. Co-located column/beam/slab tables on
one layer are read as **independent** tables (each header owns the rows beneath it).

Other `marks` API: `parse_mark(text) -> (name, b_mm, h_mm)`, `parse_texts(texts)`
(stamps `.mark/.b_mm/.h_mm` in place), `sized_texts(texts)`,
`nearest_sized_text(cx, cy, candidates, radius_ft)`.

#### `layers.classify_layer(layer_name, overrides=None)`

```python
def classify_layer(layer_name, overrides=None) -> str   # CATEGORY_*
def classify_text_layer(layer_name) -> str              # CATEGORY_*_TEXT / SCHEDULE / IGNORE
```

Convention-based routing of a geometry or text layer to a category. Geometry
categories: `CATEGORY_GRID/COLUMN/BEAM/SLAB_EDGE/UNMAPPED`. Text categories:
`CATEGORY_COLUMN_TEXT/BEAM_TEXT/GRID_TEXT/COLUMN_SCHEDULE/TEXT_IGNORE`.
`build_default_mapping(keys)` / `build_default_text_mapping(keys)` pre-fill the
override dialog.

<a name="cad2bimreaders"></a>
### `cad2bim.readers` — extraction (Revit/ezdxf)

| Function | Purpose |
|---|---|
| `dxf_reader.read_dxf(path) -> DxfReadResult` | Read geometry + text from a DXF with ezdxf (ASCII/binary, OCS→WCS, MTEXT, block ATTRIBs). `ezdxf_available()` probes the import. |
| `geometry_reader.read_link(...) -> ReadResult` | Extract curves + text from a linked CAD `ImportInstance` in the Revit model (project coordinates), mirroring the DXF reader's record shape. |
| `cad_links.find_cad_links(doc)` / `describe_link(doc, inst)` | Locate and describe linked-DWG import instances. |
| `dxf_linker.link_dxf(...)` | Link a picked DXF programmatically (the Link CAD dialog), with `UNIT_CHOICES` / `PLACEMENT_CHOICES`. |

<a name="cad2bimbuilders"></a>
### `cad2bim.builders` — Revit element creation

Each `place_*` / `create_*` runs inside a Revit transaction and returns an
outcome summary (created / skipped / errors).

| Function | Creates |
|---|---|
| `columns.place_columns(...)` / `columns.place_circular_columns(...)` | Rectangular and circular structural columns (with `structural_column_symbols`, `levels`). |
| `beams.place_beams(...)` | Structural framing (beams), via `structural_framing_symbols`. |
| `grids.create_grids(...)` | Revit grids, named through `build_grid_namer` (`GridNamer` / `TextGridNamer` recover the drawing's own grid labels). |
| `txn_failures.attach_warning_swallower(txn)` | Attaches `WarningSwallower` so batch creation does not stall on modal warning dialogs. |

---

*AnonGee Toolkit v1.1.0 — © AnonGee BIM Tools*

## Analysis Complete - Full Code Review & Refactoring Plan

### 📁 Toolkit Modules Available (`anongee_toolkit`)

| Module | Functions/Classes | Purpose |
|--------|------------------|---------|
| `revit/application` | `get_app()`, `get_current_uidoc()`, `get_current_doc()` | Document access |
| `revit/transactions` | `RevitTransaction`, `RevitTransactionGroup`, `SuppressWarningsPreprocessor` | Context-manager transactions |
| `revit/parameters` | `get_parameter()`, `get_parameter_value()`, `set_parameter_value()` | Parameter reading/writing |
| `revit/selection` | `get_selected_elements()`, `set_selection()` | Element selection |
| `revit/elements` | `get_family_name()`, `get_type_name()` | Element identity |
| `revit/filtering` | `get_elements_by_categories()` | Filtered element collection |
| `revit/geometry` | `get_solid_volume_m3()`, `bounding_boxes_overlap()` | Geometry utilities |
| `revit/units` | `CF_TO_M3`, `SF_TO_M2`, `FT_TO_MM`, `FT_TO_M`, `m_to_mm()`, `mm_to_ft()`, `m_to_ft()`, `ft_to_mm()`, `clean_ft()`, `strip_unit()` | Unit conversion |
| `revit/views` | `get_eligible_views()`, `get_view_label()`, `ALLOWED_VIEW_TYPES` | View filtering/labeling |
| `revit/compatibility` | `create_element_id()`, `get_element_id_value()` | API version compat |
| `structural/rebars` | `get_rebars()` | Rebar collection |
| `ui/dialogs` | `WpfDialogBase`, `DebounceTimer` | WPF dialog base class |
| `ui/xaml` | `load_xaml()`, `fill_combo()`, `select_combo_containing()` | XAML loading & combo helpers |
| `ui/forms` | `alert()`, `error()`, `info()`, `confirm()`, `pick_file()`, `save_file()` | Native dialogs |
| `io/excel` | `ExcelComWriter` | COM Excel automation |
| `operations/bulk_delete` | `GenericBulkDeleteDialog(target_type, ui_dir, doc)` | Reusable bulk delete dialog |
| `operations/bulk_rename` | `GenericBulkRenameDialog(target_type, ui_dir, doc)` | Reusable bulk rename dialog |
| `utils/helpers` | `create_com_array()`, `parse_tsv_row()`, `read_tsv()`, `extract_numeric()`, `extract_bracket_int()` | General utilities |

---

### 🔴 REPEATED CODE PATTERNS Identified

#### Pattern 1: XAML File Loading (6+ files)
Every script that uses WPF does this manually:
```python
stream = FileStream(xaml_path, FileMode.Open, FileAccess.Read)
try:
    self.window = XamlReader.Load(stream)
finally:
    stream.Close()
```
**Toolkit replacement:** `load_xaml(path)` from `anongee_toolkit.ui.xaml`

**Affected:** BIM Generation, CAD to BIM, Copy Rebar Visibility, Export Schedule, Obscured Rebar, Bulk Delete (3x), Bulk Rename (3x)

---

#### Pattern 2: Window Icon Setting (6+ files)
Every WPF script does this:
```python
icon_path = os.path.join(LOCAL_DIR, "icon.png")
if os.path.exists(icon_path):
    self.window.Icon = BitmapImage(Uri(icon_path, UriKind.Absolute))
```
**Toolkit replacement:** Could be added to a base class or `load_xaml()` helper.

---

#### Pattern 3: Badge UI Pattern (5+ files)
Identical info/success/error badge visibility pattern repeated in:
- **Copy Rebar Visibility** (lines 152-170)
- **Export Schedule** (lines 285-305)
- **Obscured Rebar** (lines 151-167)
- **Bulk Delete** (lines 220-240)
- **Bulk Rename** (lines 303-324)
- **Toolkit's own GenericBulkDeleteDialog** (lines 258-279) and **GenericBulkRenameDialog** (lines 303-324) already use a badge pattern

This is a prime candidate for a **base dialog mixin class**.

---

#### Pattern 4: Error/Alert Helper Functions (3+ files)
Each script defines its own `_error()`, `_alert()` etc.:
- **BIM Generation**: `_show_error(title, message, detail)`
- **CAD to BIM**: `_alert(title, message)`, `_error(title, message, detail)`
- **FramewinToBIM**: Uses `forms.alert()` from pyRevit (IronPython only)
- **Copy Rebar**: Inline MessageBox calls
- **Export Schedule**: Inline MessageBox calls

**Toolkit replacement:** `alert()`, `error()`, `info()`, `confirm()` from `anongee_toolkit.ui.forms`

---

#### Pattern 5: Transaction Pattern (4+ files)
Manual Start/Commit/RollBack pattern:
```python
t = Transaction(doc, "My Operation")
t.Start()
try:
    # ... work ...
    t.Commit()
except:
    if t.HasStarted() and not t.HasEnded():
        t.RollBack()
    raise
```
**Toolkit replacement:** `RevitTransaction("My Operation")` context manager

**Affected:** FramewinToBIM, Copy Rebar Visibility, Obscured Rebar, Export Schedule, Bulk Delete, Bulk Rename

---

#### Pattern 6: View Type Filtering (IDENTICAL CODE)
**Copy Rebar Visibility** (lines 39-55) and **Obscured Rebar** (lines 39-55) contain **IDENTICAL**:
```python
ALLOWED_VIEW_TYPES = {
    ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.EngineeringPlan,
    ViewType.Section, ViewType.Elevation, ViewType.ThreeD,
}
VIEW_TYPE_LABELS = { ... }
def _id_value(eid): ...
def _view_label(view): ...
```
**Toolkit replacement:** `ALLOWED_VIEW_TYPES`, `get_view_label()`, `get_eligible_views()` from `anongee_toolkit.revit.views`

---

#### Pattern 7: Unit Conversion (IDENTICAL CODE)
**FramewinToBIM** (lines 27-30) defines its own:
```python
def m_to_mm(v): return int(round(float(v) * 1000.0))
def mm_to_ft(mm): return mm / 304.8
def m_to_ft(m): return mm_to_ft(m_to_mm(m))
def clean_ft(v): return mm_to_ft(int(round(float(v) * 304.8)))
```
**Toolkit replacement:** `m_to_mm()`, `mm_to_ft()`, `m_to_ft()`, `clean_ft()` from `anongee_toolkit.revit.units`

---

#### Pattern 8: TSV Parsing & Unit Stripping (DUPLICATED IN PUSH BUTTON & TOOLKIT)
**Export Schedule** (lines 86-189) duplicates functions that **already exist** in:
- `anongee_toolkit.utils.helpers.parse_tsv_row()`
- `anongee_toolkit.utils.helpers.read_tsv()`
- `anongee_toolkit.revit.units.strip_unit()`

---

#### Pattern 9: `_fmt_exc` Traceback Fallback (3+ files)
Identical try/except traceback fallback:
```python
try:
    import traceback as _tb
    def _fmt_exc(): return _tb.format_exc()
except ImportError:
    import sys
    def _fmt_exc():
        t, v, _ = sys.exc_info()
        return "{}: {}".format(t.__name__, v)
```
**Found in:** Export Schedule, Bulk Delete (3x), Bulk Rename (3x)

---

### 🚀 Which Pushbuttons Can Immediately Use Toolkit Modules

| Pushbutton | Can Use | What to Replace |
|---|---|---|
| **Bulk Delete** (all 3) | ✅ **YES** - Direct replacement | Replace entire `script.py` with `GenericBulkDeleteDialog("fillpattern"\|"linepattern"\|"linestyle", ui_dir)` |
| **Bulk Rename** (all 3) | ✅ **YES** - Direct replacement | Replace entire `script.py` with `GenericBulkRenameDialog("fillpattern"\|"linepattern"\|"linestyle", ui_dir)` |
| **Copy Rebar Visibility** | ✅ **YES** | Replace `ALLOWED_VIEW_TYPES`, `_view_label()`, `_id_value()` with `revit.views`; use `RevitTransaction`; use `load_xaml()` |
| **Obscured Rebar** | ✅ **YES** | Same as Copy Rebar Visibility + use `structural.rebars.get_rebars()` |
| **Export Schedule** | ✅ **YES** | Replace `_parse_tsv_row()`, `_read_tsv()` with `utils.helpers`; replace `_strip_unit()` with `revit.units.strip_unit()`; use `RevitTransaction`; use `load_xaml()` |
| **BIM Generation** | ⚠️ **Partial** | Use `load_xaml()`; use `ui.forms` for error dialogs; but core parsing logic stays |
| **CAD to BIM** | ⚠️ **Partial** | Use `load_xaml()`; use `ui.forms` for error dialogs; but `cad2bim` package is separate |
| **FramewinToBIM** | ⚠️ **Partial** | **CRITICAL:** This is IronPython (uses `pyrevit.forms`). Must be migrated to CPython3 first. Can then use `RevitTransaction`, `revit.units`, `load_xaml()` |
| **Brand Guidelines** | ⚠️ **Partial** | Need to read this script first |
| **CPython3 engine** | ⚠️ **Unknown** | Need to read this script |

---

### 📊 Priority Refactoring Plan

#### Phase 1: Low-hanging fruit (minimal risk)
1. **Bulk Delete pushbuttons** → Replace with `GenericBulkDeleteDialog` from toolkit (the 3 scripts are 318 lines each, the toolkit version is the same but shared)
2. **Bulk Rename pushbuttons** → Replace with `GenericBulkRenameDialog` from toolkit
3. **Export Schedule** → Use `utils.helpers.parse_tsv_row/read_tsv` and `revit.units.strip_unit` (eliminate ~100 lines of inlined code)

#### Phase 2: Structural improvements (safe)
4. **Copy Rebar Visibility** → Use `revit.views` for view types/labels, `RevitTransaction`, `load_xaml()`
5. **Obscured Rebar** → Same as above + `structural.rebars.get_rebars()`
6. **BIM Generation** → Use `load_xaml()`, `ui.forms` helpers

#### Phase 3: Foundation work (needs base class)
7. Create a `WpfDialogBase` subclass with built-in badge UI pattern (info/success/error) and window icon setting
8. Create a `_fmt_exc()` utility in `utils/helpers.py`

#### Phase 4: Major refactor (needs IronPython→CPython3 migration)
9. **FramewinToBIM** → Full migration to CPython3 engine, then use `RevitTransaction`, `revit.units`, `load_xaml()`, etc.

---

### 💡 Recommendation

**Immediately actionable (low risk):** The Bulk Delete and Bulk Rename pushbuttons are the biggest win. They already have corresponding `GenericBulkDeleteDialog` and `GenericBulkRenameDialog` classes in the toolkit that accept `(target_type, ui_dir, doc)` parameters - the pushbuttons just need a thin wrapper script.

**Medium effort:** Cleaning up Copy Rebar Visibility, Obscured Rebar, and Export Schedule to use shared toolkit code reduces redundancy and makes maintenance easier.

**Notable:** The toolkit already contains `strip_unit()` in `revit/units.py` AND `parse_tsv_row()/read_tsv()` in `utils/helpers.py`, yet Export Schedule has its own inlined versions - this is the clearest case of code that could have been shared but wasn't.

Would you like me to proceed with implementing these refactoring changes? I'd recommend starting with Phase 1 (Bulk Delete/Rename + Export Schedule) as the highest-impact, lowest-risk changes.
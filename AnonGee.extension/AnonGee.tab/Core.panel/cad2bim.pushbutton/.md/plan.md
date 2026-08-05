# CAD to RCC BIM Automator — Verified Revit API & pyRevit Implementation Reference (Revit 2023–2026, IronPython 2.7.12)

## TL;DR
- Every API you proposed is current and correct for Revit 2023–2026: linked-DWG geometry extraction via `ImportInstance.get_Geometry(Options())` with recursive `GeometryInstance.Transform` compounding; `UnitTypeId` (ForgeTypeId) instead of the deprecated `DisplayUnitType`; `Grid.Create`, `Floor.Create`, and `NewFamilyInstance` for structural columns/beams. The signatures are stable across all four versions — the one true breaking change you must code around is the **runtime split at Revit 2025 (.NET 8)**, not the document API.
- Geometry from a linked CAD comes back already in Revit internal units (decimal feet) with the DWG drawing-unit scale baked in by the link transform, so do NOT re-scale CAD coordinates; only convert your own input dimensions (mm → feet) with `UnitUtils.ConvertToInternalUnits(value, UnitTypeId.Millimeters)`.
- Package as a single `.extension` with a `lib/` folder for shared modules; pin IronPython 2.7.12 (pyRevit's documented default) but ship a known-good fallback because pyRevit 5.1 throws `IOError: [Errno 2] Could not load file or assembly 'IronPython, Version=2.7.12.0…'` on Revit 2025 only (works on 2026). Use the external CPython 3 + ezdxf 1.4.4 (requires Python ≥3.10) validator as a separate process consuming JSON, and find/skip prior runs with Extensible Storage plus a `FilteredElementCollector`.

## Key Findings

1. **Linked CAD geometry** is reached through `ImportInstance` (`IsLinked == true`, type `CADLinkType`). Call `get_Geometry(Options())`, recurse into `GeometryInstance`, and compound transforms via `parentTransform.Multiply(gi.Transform)`. Layer name = `doc.GetElement(geomObj.GraphicsStyleId)` cast to `GraphicsStyle`, then `.GraphicsStyleCategory.Name`.
2. **Units**: `DisplayUnitType` was deprecated in Revit 2021 in favor of `ForgeTypeId`/`UnitTypeId`. Use `UnitTypeId.Millimeters` for 2023–2026. Linked-CAD geometry is already in internal feet.
3. **Grids**: `Grid.Create(Document, Line)` and `Grid.Create(Document, Arc)` are the current static factories (documented from RevitAPI.dll v18.0.0.0). The old `doc.Create.NewGrid` is the obsolete pattern. Set `.Name` to rename the bubble.
4. **Structural columns**: `doc.Create.NewFamilyInstance(XYZ, FamilySymbol, Level, StructuralType.Column)`. Must call `symbol.Activate()` first. Set base/top via `FAMILY_BASE_LEVEL_PARAM`/`FAMILY_TOP_LEVEL_PARAM` + offsets.
5. **Structural beams/framing**: `doc.Create.NewFamilyInstance(Curve, FamilySymbol, Level, StructuralType.Beam)`. Justification through `Y_JUSTIFICATION`/`Z_JUSTIFICATION`/`YZ_JUSTIFICATION` + start/end level offsets.
6. **Floors/slabs**: `Floor.Create(Document, IList<CurveLoop>, ElementId floorTypeId, ElementId levelId)` plus the structural overload with `bool isStructural, Line slopeArrow, double slope` — all "Since 2022", unchanged 2023–2026. `NewFloor`/`NewSlab` deprecated in 2022. Inner `CurveLoop`s = holes.
7. **Duplicate-type-on-demand**: find by name; else `ElementType.Duplicate(name)`; edit floor thickness via `GetCompoundStructure()` → `SetLayerWidth` → `SetCompoundStructure`.
8. **Extensible Storage**: `SchemaBuilder` → `AddSimpleField` → `Finish`; `Entity` → `Set`; `Element.SetEntity`; later `Schema.Lookup(guid)` + `Element.GetEntity`. Collect prior runs by reading the entity in a `FilteredElementCollector` loop.
9. **Transactions / failures**: `TransactionGroup` wrapping multiple `Transaction`s; `Assimilate()` to merge into one undo, `RollBack()` on failure. Suppress dialogs via `IFailuresPreprocessor.PreprocessFailures` returning `FailureProcessingResult.Continue`.
10. **Beam-graph face finding**: this is the planar-graph minimal-cycle / face-traversal problem; the practical pure-Python approach is the sorted-by-polar-angle "next clockwise edge" traversal (O(n log n)).
11. **pyRevit packaging**: `MyExt.extension/{lib/, *.tab/*.panel/*.pushbutton/script.py}`; `lib/` is the shared module location.
12. **ezdxf** validator: external CPython 3 process, ezdxf 1.4.4, requires Python ≥3.10.

## Details

### 1. Linked CAD geometry extraction
A linked DWG is an `ImportInstance` element; `ii.IsLinked == true` distinguishes a link from an import, and its type is `CADLinkType`. Collect with `FilteredElementCollector(doc).OfClass(ImportInstance)`. The Autodesk DevBlog confirms: "Through the ImportInstance.Geometry property we can get the objects' coordinates in the coordinates of the DWG coordinate system, and also the transform of how to convert the objects' coordinates to the current Revit model coordinates system."

The geometry of a CAD link is wrapped in a single `GeometryInstance` (blocks add nested `GeometryInstance`s). The canonical recursion:

```python
opt = Options()
geo = import_inst.get_Geometry(opt)            # GeometryElement
for obj in geo:
    if isinstance(obj, GeometryInstance):
        # compound parent transform with the instance transform
        xf = parent_xf.Multiply(obj.Transform)
        for g in obj.GetInstanceGeometry():    # geometry already in project coords
            process(g, xf)
```

Two methods exist on `GeometryInstance`:
- `GetSymbolGeometry()` returns geometry in the symbol's own (definition) coordinate space; you then apply `GeometryInstance.Transform` yourself.
- `GetInstanceGeometry()` returns geometry already transformed into the project coordinate system.

⚠️ **Do not double-transform.** The Building Coder documents that applying a transform to geometry already returned by `GetInstanceGeometry()` (or via `GetTransformed`) produces a double transformation. For nested blocks, compound transforms with `gi.Transform.Multiply(parentTransform)` only when you recurse through `GetSymbolGeometry()`. The cleanest pattern for a CAD link is: use `GetInstanceGeometry()` at the top level (already in project coordinates) and, for nested blocks, recurse using `SymbolGeometry` + compounded transforms.

**Layer name** of any `GeometryObject`:
```python
gstyle = doc.GetElement(geom_obj.GraphicsStyleId)   # GraphicsStyle
layer  = gstyle.GraphicsStyleCategory.Name
```
This is confirmed by both the official `GraphicsStyleId` property sample and The Building Coder ("The layer name is provided by gStyle.GraphicsStyleCategory.Name"). Wrap in a null-check/try because `GraphicsStyleId` can be `InvalidElementId` for some primitives (a known gotcha that returns null gStyle).

**Enumerating all layers in a linked CAD**: DWG layers surface in Revit as subcategories of the import's category. Enumerate them via `Category.SubCategories` of the import's `OST_ImportObjectStyles` category, or simply harvest the distinct `GraphicsStyleCategory.Name` values while walking the geometry. Layer visibility is controlled through `GraphicsStyleCategory.Id` with `View.GetCategoryHidden(catId)` / `SetCategoryHidden`.

No API differences 2023–2026 for any of the above. `GraphicsStyle` is still present in the 2026 API (assembly `RevitAPI.dll` version 25.3.0.0 in the 2026 docs).

### 2. Unit conversion
`DisplayUnitType`, `UnitType`, and `UnitSymbolType` enums were **deprecated in Revit 2021** in favor of the extensible `ForgeTypeId` class; the decompiled obsolete attribute reads: "This enumeration is deprecated in Revit 2021 and may be removed in a future version of Revit. Please use the `ForgeTypeId` class instead. Use constant members of the `UnitTypeId` class…". The deprecated→replacement map:
- `ConvertToInternalUnits(double, DisplayUnitType)` → `ConvertToInternalUnits(double, ForgeTypeId unitTypeId)`
- `ConvertFromInternalUnits(double, DisplayUnitType)` → `ConvertFromInternalUnits(double, ForgeTypeId unitTypeId)`

**Correct for 2023–2026:**
```python
internal = UnitUtils.ConvertToInternalUnits(300.0, UnitTypeId.Millimeters)   # mm → feet
mm       = UnitUtils.ConvertFromInternalUnits(length_ft, UnitTypeId.Millimeters)
```
`UnitTypeId.Millimeters`, `.Meters`, `.Feet`, `.Radians`, `.Degrees` are constant `ForgeTypeId` properties. The deprecated enum still compiles in 2023–2026 (emits a warning) but should not be used in new code. `UnitTypeId` is the correct choice for all four target versions.

**Linked-CAD geometry units**: Confirmed — geometry returned by `get_Geometry` on a linked CAD is already in Revit internal units (decimal feet), with the DWG's drawing-unit scale already applied by the link transform. The Autodesk DevBlog confirms the returned transform converts "the DWG internal coordinates to the Revit model coordinates," and the Dynamo Python primer confirms "any length value using Revit's API … will automatically be returned in decimal feet." Therefore: never re-scale CAD coordinates; only convert your own mm inputs.

### 3. Grid creation
Current static factories (RevitAPI.dll v18.0.0.0, "Creates a new grid line"):
```python
lineGrid = Grid.Create(document, geomLine)   # Line, must be on a horizontal plane
arcGrid  = Grid.Create(document, geomArc)    # Arc, must be on a horizontal plane
lineGrid.Name = "A"                          # sets the bubble/label
```
- `Grid.Create(Document, Line)` and `Grid.Create(Document, Arc)` exist and are stable across 2023–2026.
- The line/arc must lie in a horizontal plane (Z constant); the docs note explicitly "The line should be on a horizontal plane."
- `doc.Create.NewGrid(line/arc)` is the old instance-method pattern; prefer the static `Grid.Create`.
- Renaming via `grid.Name`; Revit auto-numbers grids sequentially if you don't set names, and will throw if you assign a duplicate name.

### 4. Structural column placement
```python
if not symbol.IsActive:
    symbol.Activate()
    doc.Regenerate()
col = doc.Create.NewFamilyInstance(origin, symbol, baseLevel, StructuralType.Column)
col.get_Parameter(BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).Set(baseLevel.Id)
col.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(topLevel.Id)
col.get_Parameter(BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM).Set(baseOffset_ft)
col.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM).Set(topOffset_ft)
```
- The overload `NewFamilyInstance(XYZ, FamilySymbol, Level, StructuralType)` is "the most commonly used … since there are a large number of elements that use levels, such as Walls, Columns."
- **`symbol.Activate()` is required** before placing if the symbol is not active; otherwise placement fails silently or throws. Follow with `doc.Regenerate()` so the offset/level parameters become accessible.
- Setting base/top levels turns a single-level column into a proper vertical column. A Revit 2023 forum thread documents the exact gotcha: placing a column with a single-level overload makes "the columns … coming in one level only (Horizontal) instead of starting at base level and ending at top level (Vertical)" — you must set `FAMILY_TOP_LEVEL_PARAM` to make it span. The offset params (`FAMILY_BASE_LEVEL_OFFSET_PARAM`, `FAMILY_TOP_LEVEL_OFFSET_PARAM`) may be null until the instance is regenerated/level-associated.
- Rotation: `ElementTransformUtils.RotateElement(doc, col.Id, axis, angleRadians)` with a vertical axis `Line.CreateBound(p, p+Z)` through the column origin. Positive radians = counter-clockwise. (Pinned elements cannot be rotated.)
- No signature differences 2023–2026.

### 5. Structural beam / framing placement
```python
if not symbol.IsActive: symbol.Activate(); doc.Regenerate()
beam = doc.Create.NewFamilyInstance(curve, symbol, refLevel, StructuralType.Beam)
```
- The curve overload `NewFamilyInstance(Curve, FamilySymbol, Level, StructuralType.Beam)` is the canonical beam factory (docs version 23.x verified for 2023; same in 2024–2026).
- **You must specify a structural type and a location curve** — using `StructuralType.NonStructural` for a beam produces a null instance, and a beam created from only a point (no curve) "cannot be selected" / is unusable.
- Reference level: set via the `SCHEDULE_LEVEL_PARAM`/reference-level association at creation (per the forum, `SCHEDULE_LEVEL_PARAM` "can be accessed at the time of creating Instance. Once Instance is created, it will not [be] accessed").
- **Z / hanging below a level**: use `Z_JUSTIFICATION` (enum `ZJustification`, namespace `Autodesk.Revit.DB.Structure`, since 2014) and `Z_OFFSET_VALUE`; for sloped/independent ends set `YZ_JUSTIFICATION` to Independent and use `STRUCTURAL_BEAM_END0_ELEVATION` / `STRUCTURAL_BEAM_END1_ELEVATION` (or Start/End Level Offset). `Y_JUSTIFICATION` (enum `YJustification`) handles lateral. Beams default to hanging with their top at the level; adjust z-justification/offset to drop them.
- Known gotcha: `ElementTransformUtils.RotateElement` to roll a beam about its own axis **works for vertical members but not horizontal ones** (the rotation axis parallel to a horizontal location line is a documented no-op); for cross-section rotation of horizontal beams set `STRUCTURAL_BEND_DIR_ANGLE` instead.
- `INSTANCE_STRUCT_USAGE_PARAM` sets Girder/Joist/Purlin (ints 3/4/5/6/8); "Automatic" is not settable through the API.
- No signature differences 2023–2026.

### 6. Floor / slab creation
**Primary signature (Since 2022, unchanged through 2026):**
```python
Floor.Create(document, IList<CurveLoop> profile, ElementId floorTypeId, ElementId levelId)
```
**Structural / sloped overload (Since 2022):**
```python
Floor.Create(document, profile, floorTypeId, levelId, bool isStructural, Line slopeArrow, double slope)
```
Verified present in the 2022, 2024 (RevitAPI 24.0), and 2025 (RevitAPI 25.0) API docs with identical parameter lists; the 2026 floor docs show the same family of methods. Migration map from Revit 2022 "What's New": `NewFloor` → `Floor.Create(doc, profile, floorTypeId, levelId)`; `NewSlab`/`NewFoundationSlab` → the structural overload. **`Document.Create.NewFloor`/`NewSlab` are obsolete since Revit 2022** ("this method is deprecated in Revit 2022 and may be removed in the future version of Revit").

Key usage facts:
- You must pass a **valid floor type and level** (unlike the old `NewFloor`); use `Floor.GetDefaultFloorType(doc, isFoundation)` if needed.
- **The elevation of the curve loops is NOT taken into account** (unlike old `NewFloor`/`NewSlab`). To place at the right height, after creation set `floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM).Set(offset)`.
- Validate with `BoundaryValidation`; the common runtime error is `ArgumentException: The input curve loops cannot compose a valid boundary` (loops must be closed, planar, non-self-intersecting, properly ordered).
- **Openings / holes**: pass multiple `CurveLoop`s in the `IList` — the first is the outer boundary, additional inner loops become holes. (Alternatively `doc.Create.NewOpening` after the fact.)
- There is no documented Floor.Create overload taking a SketchPlane (that overload pattern belongs to `FilledRegion.Create`, since 2023); floor slope is controlled by the `slopeArrow` + `slope` arguments.

### 7. Duplicate-type-on-demand
Pattern (works for `FamilySymbol` and `FloorType`, both `ElementType` subclasses):
```python
existing = next((t for t in FilteredElementCollector(doc).OfClass(FloorType)
                 if Element.Name.GetValue(t) == target_name), None)
if existing is None:
    new_type = base_type.Duplicate(target_name)     # ElementType.Duplicate
```
- Always check for an existing type with the target name first; `Duplicate` throws if the name already exists.
- **Floor thickness via CompoundStructure** (must round-trip get→modify→set):
```python
cs = new_floor_type.GetCompoundStructure()
cs.SetLayerWidth(0, UnitUtils.ConvertToInternalUnits(thickness_mm, UnitTypeId.Millimeters))
new_floor_type.SetCompoundStructure(cs)             # required; GetCompoundStructure returns a copy
```
The Autodesk forum confirms the trap: editing the structure returned by `GetCompoundStructure()` alone "can create new floor type, but can't change floor thickness" — you must call `SetCompoundStructure(compound)`. For a single-layer slab, layer index 0 is the structural layer; use `GetFirstCoreLayerIndex()` / `StructuralMaterialIndex` for multi-layer types. `CompoundStructureLayer.Width` is in feet.
- **Parametric column/beam b/h dimensions**: set the family instance/type parameters (e.g. `LookupParameter("b")` / `"h"`) on the duplicated `FamilySymbol`. These are family-defined parameters, not BuiltInParameters — you cannot create BuiltInParameters, only set existing ones.
- No API differences 2023–2026.

### 8. Extensible Storage for a re-run "batch stamp"
```python
guid = Guid("....")               # fixed, hard-coded GUID for your schema
schema = Schema.Lookup(guid)
if schema is None:
    sb = SchemaBuilder(guid)
    sb.SetReadAccessLevel(AccessLevel.Public)
    sb.SetWriteAccessLevel(AccessLevel.Public)     # or Vendor + SetVendorId("YourId")
    sb.SetSchemaName("CadToRccBatchStamp")
    sb.AddSimpleField("BatchId", str)              # field names: alphanumeric, no spaces
    sb.AddSimpleField("SourceLayer", str)
    schema = sb.Finish()

ent = Entity(schema)
ent.Set[str](schema.GetField("BatchId"), batch_id)
element.SetEntity(ent)
```
Read back / find prior runs:
```python
for el in FilteredElementCollector(doc).OfClass(FamilyInstance):
    ent = el.GetEntity(schema)
    if ent.IsValid():
        if ent.Get[str](schema.GetField("BatchId")) == batch_id:
            ids_to_delete.Add(el.Id)
```
- One entity per schema per element (re-setting overwrites). Use `Element.GetEntitySchemaGuids()` + `Schema.Lookup` to discover, `Element.DeleteEntity(schema)` to remove.
- Field name must satisfy the naming rule (no spaces/illegal chars) or `AddSimpleField` throws `ArgumentException`.
- Keep payload small (Autodesk guidance: a few kB/element, a few MB/file max).
- **Alternative: a project/shared parameter** (e.g. a text "BatchId" instance parameter bound to your categories) is easier to schedule/inspect in the UI and survives even if the schema isn't loaded; trade-off is it's user-visible and editable. For an unattended re-run tool, Extensible Storage is the more robust "hidden stamp." Either way, collect previous elements with a `FilteredElementCollector` filtered by category, then test the stamp.
- Extensible Storage API is unchanged 2023–2026 (note: very old samples use `Entity.Set<XYZ>(field, val, DisplayUnitType...)`; in 2023–2026 the unit-bearing overloads take a `ForgeTypeId`).

### 9. Transaction management & failure handling
**TransactionGroup pattern** (one undo for the whole batch):
```python
tg = TransactionGroup(doc, "CAD→RCC Batch")
tg.Start()
try:
    # grids
    with Transaction(doc, "Grids") as t:
        t.Start(); ...; t.Commit()
    # columns, beams, floors each in their own Transaction ...
    tg.Assimilate()       # merge all inner transactions into a single undo step
except:
    tg.RollBack()         # undo everything committed in the group
    raise
```
- `Commit` keeps inner transactions as separate undo entries; **`Assimilate` merges them into one** — preferred for a clean single-undo batch. `RollBack` discards all committed inner transactions.
- A `TransactionGroup` can only start when no transaction is active and must close after its last inner transaction finishes. Always wrap in `using`/try-finally so it never out-lives scope (the destructor auto-rolls-back otherwise). Use `doc.IsModifiable` to test for an open transaction.
- pyRevit gives you `pyrevit.revit.Transaction` / `TransactionGroup` context managers as ergonomic wrappers.

**Suppressing warnings (`IFailuresPreprocessor`)** so dialogs never block an unattended run:
```python
class SuppressWarnings(IFailuresPreprocessor):
    def PreprocessFailures(self, fa):
        for f in fa.GetFailureMessages():
            if f.GetSeverity() == FailureSeverity.Warning:
                fa.DeleteWarning(f)
        return FailureProcessingResult.Continue

opts = t.GetFailureHandlingOptions()
opts.SetFailuresPreprocessor(SuppressWarnings())
opts.SetClearAfterRollback(True)
t.SetFailureHandlingOptions(opts)
```
- Return `FailureProcessingResult.Continue` after deleting warnings; for resolvable errors use `failure.SetCurrentResolutionType(...)` + `fa.ResolveFailure(f)` and return `ProceedWithRollBack`/`ProceedWithCommit`.
- This is the right tool for auto-join, duplicate-mark ("DuplicateValue"), and overlap warnings that bulk creation throws. `BuiltInFailures.GeneralFailures.DuplicateValue` is the typical id to target. Note `FailuresAccessor.DeleteWarning` only works on **warnings**, not errors.
- The interface and pattern are unchanged 2023–2026.

### 10. Beam-graph face finding (deriving slab boundaries)
This is the classic **planar-graph face enumeration / minimal cycle basis** problem: given beam centerlines as a planar straight-line graph (PSLG), find the minimal enclosed cycles to use as floor boundaries. Practical pipeline for pure Python (IronPython 2.7-compatible — pure-Python, no numpy needed):

1. **Build the planar graph**: snap endpoints with a tolerance, compute all pairwise segment intersections (Bentley–Ottmann, or brute-force O(n²) which is fine for the modest beam counts in one floor plate), and split segments at intersections so edges only meet at shared vertices.
2. **Find faces by angular next-edge traversal** (the standard algorithm, e.g. cp-algorithms "Finding faces of a planar graph"): for each vertex sort incident edges by polar angle; for each directed half-edge, repeatedly take the "next clockwise (or most counter-clockwise) edge" at the arriving vertex until you return to the start. Each such walk yields one face. Complexity is **O(n log n)** dominated by the angular sort; without sorting it is O(n). The minimal interior cycles (counter-clockwise) are your slab loops; the single clockwise cycle is the unbounded outer face — discard it.
3. **Handle nesting/holes**: a disconnected component drawn inside a face becomes a hole; resolve with point-in-polygon tests to re-parent interior cycles (this is exactly the "area tree" output of the David Eberly *Constructing a Cycle Basis for a Planar Graph* algorithm, GeometricTools, and the JS `planar-face-discovery` port of it).
4. Convert each cycle of vertices into a Revit `CurveLoop` for `Floor.Create`.

Recommended references to implement against: the Eberly GeometricTools paper *MinimalCycleBasis* (depth-first component split, filament removal, clockwise/counter-clockwise traversal) and the cp-algorithms planar-faces writeup. For arcs, approximate them as polylines before face extraction (winding order is undefined for arcs). This is computational geometry done in your own code — there is no Revit API for it.

### 11. pyRevit library packaging & IronPython 2.7.12
**Bundle structure** (directories named `name.type`):
```
MyExt.extension/
├── extension.json          # metadata
├── startup.py              # optional
├── hooks/                  # optional event hooks
├── lib/                    # ← shared Python modules (importable from every button)
│   └── cad2rcc/__init__.py
└── MyTab.tab/
    └── MyPanel.panel/
        └── DoImport.pushbutton/
            ├── bundle.yaml # (or script metadata in script.py __title__/__doc__)
            ├── icon.png
            └── script.py
```
- The **`lib/` folder at the extension root is the correct place for reusable shared modules**; pyRevit adds it to `sys.path` so any pushbutton can `import cad2rcc`. (A `lib/` can also exist at lower bundle levels.) "Library extensions are created to share IronPython modules between all extensions" — for sharing across *multiple* extensions, make a separate `.lib` extension.
- The first file ending in `script.py` under a `.pushbutton` is the command body. `bundle.yaml` carries title/tooltip/context.
- Use pyRevit metadata dunders (`__title__`, `__doc__`, `__min_revit_ver__`, etc.) and `from pyrevit import revit, DB, forms`.

**IronPython 2.7.12 engine status:**
- IronPython 2.7.12 is the **current default engine** in pyRevit. pyRevit's own repository documentation states: "It allows users to create automation tools and add-ins using Python (IronPython 2.7.12 default, CPython 3.12.3, or IronPython 3.4.0)." (Other pyRevit-adjacent write-ups describe the shipped experimental IronPython 3 engine as "3.4.2" and label it "expect bugs" — sources disagree on the exact patch level; treat IronPython 3 as experimental either way.) IronPython 2.7.12 itself was released 2022-01-21. Only one IronPython engine can run at a time; switching requires editing the `.addin` manifest (pyRevit does this for you) and a Revit restart.
- **Known Revit 2025-specific issue**: pyRevit 5.1 fails to load IronPython 2.7.12 on Revit 2025. The forum report ("pyRevit 5.1 fails loading IronPython 2.7 on Revit 2025") gives the verbatim error: "I noticed this error while loading IronPython: `IOError: [Errno 2] Could not load file or assembly 'IronPython, Version=2.7.12.0, Culture=neutral, PublicKeyToken=7f709c5b713576e1'… Surprisingly, this only happens in Revit 25 and works in all other versions, including 26.`" Root cause is the **.NET 8 runtime split**: per pyRevit's architecture docs, "There are multiple versions of pyRevitLoader.dll… One for Revit 2025 and newer, built with .NET 8. Another for older Revit versions, built with the .NET Framework… Since we cannot have multiple IronPython engines running at the same time, if the user switches the engine… pyRevit will change the .addin manifest." The 2025 .NET 8 transition is the one true breaking environment change across your target range.
- **Mitigation**: pin a known-good pyRevit build per Revit version; if 2.7.12 fails to load on 2025, fall back to the 2.7.11/279 engine or run `pyrevit attach` to repair the manifest. Test the extension on each of 2023, 2024, 2025, 2026 separately because the loader/runtime (not your document code) is what changes.

### 12. ezdxf external CPython 3 validator
- **Confirmed (subagent + PyPI verification):** latest ezdxf is **1.4.4** (released May 14, 2026) and it **requires Python ≥ 3.10** — PyPI states verbatim "Requires: Python >=3.10" with classifiers Python 3.10–3.14, and the ezdxf Introduction docs state "Ezdxf requires at least Python 3.10 and will be tested with the latest stable CPython version and the latest stable release of pypy3." (The old "Python 3.6" requirement is obsolete; an interim "3.9" requirement was also superseded.)
- This runs as a **separate CPython 3 process outside Revit** (IronPython 2.7 cannot run ezdxf), consuming your JSON intermediate file and emitting/validating a DXF.
- Core API (current 1.4.4 docs):
```python
import ezdxf
doc = ezdxf.new("R2010")          # or default latest; units kwarg default 6 = meters
msp = doc.modelspace()
msp.add_line((0, 0), (10, 0))                              # LINE
msp.add_lwpolyline([(0,0), (3,0), (6,3), (6,6)], close=True)  # LWPOLYLINE (R2000+)
msp.add_arc(center=(0,0), radius=5, start_angle=0, end_angle=90)  # ARC, angles in degrees
msp.add_circle(center=(0,0), radius=2)                     # CIRCLE
doc.saveas("out.dxf")
```
Signatures: `add_line(start, end, dxfattribs=None)`; `add_lwpolyline(points, format='xyseb', *, close=False, dxfattribs=None)`; `add_arc(center, radius, start_angle, end_angle, is_counter_clockwise=True, dxfattribs=None)` (angles in degrees, CCW by default); `add_circle(center, radius, dxfattribs=None)`. All coords are WCS points (2- or 3-tuples). All factory methods accept an optional `dxfattribs` dict (e.g. `{"layer": "GRID", "color": 2}`). For maximum speed/low memory there is also `ezdxf.addons.r12writer` (LINE, CIRCLE, ARC, TEXT, POINT, SOLID, 3DFACE, POLYLINE only).

## Recommendations

**Stage 1 — Foundation & environment (do first):**
1. Build the `.extension` skeleton with a `lib/cad2rcc/` package; put all geometry/units/graph helpers there so each pushbutton stays thin.
2. Centralize unit handling in one module using `UnitUtils.ConvertToInternalUnits(value, UnitTypeId.Millimeters)`. Never touch `DisplayUnitType`. Add one helper `mm(x)` / `to_mm(x)`.
3. Pin the engine to IronPython 2.7.12 but write a startup self-check that detects the Revit 2025 `IOError` load failure and logs a clear message; validate the build on each of 2023/2024/2025/2026 in isolation. **Threshold to change plan:** if 2.7.12 won't load on 2025 in your target pyRevit build, fall back to the prior 2.7.x engine for 2025 only, or upgrade to the pyRevit build that fixes it.

**Stage 2 — Read & parse:**
4. Implement linked-CAD extraction with `GetInstanceGeometry()` at the top level (project coords; do NOT rescale), recursing into nested blocks with compounded `SymbolGeometry` transforms only. Classify curves by `GraphicsStyleCategory.Name` and let the user map layers → element type (grid/column/beam/slab-edge).
5. Build the external CPython 3 + ezdxf 1.4.4 validator as a sidecar that reads your JSON dump of parsed curves and writes a round-trip DXF for visual QA. Require Python ≥3.10 on the machine.

**Stage 3 — Create elements (wrap everything in one TransactionGroup, assimilate):**
6. Grids → `Grid.Create`; Columns → `NewFamilyInstance(...Column)` with `Activate()`+`Regenerate()` then set base/top level params; Beams → `NewFamilyInstance(curve,...Beam)` then z-justification/offset. Duplicate types on demand via `ElementType.Duplicate` + `CompoundStructure` for slab thickness.
7. Derive slabs from the beam graph using the planar-face traversal (Stage-2 helper), convert cycles to `CurveLoop`s (outer + inner holes), and call `Floor.Create(doc, loops, floorTypeId, levelId)`, then set `FLOOR_HEIGHTABOVELEVEL_PARAM`.
8. Stamp every created element with an Extensible Storage `BatchId`. On re-run, collect+test the stamp with a `FilteredElementCollector` and skip or delete prior output.
9. Attach an `IFailuresPreprocessor` that deletes warnings (target `DuplicateValue`, auto-join) to every transaction so the run is truly unattended.

**Thresholds that change the approach:** if beam graphs routinely exceed a few thousand segments per plate, replace brute-force intersection with Bentley–Ottmann; if CAD links contain hatch/text noise, filter by layer before graph-building; if you need UI-visible/scheduleable tracking instead of a hidden stamp, switch from Extensible Storage to a bound project parameter.

## Caveats
- **The only hard breaking change across 2023–2026 is the runtime, not the document API**: Revit 2025 moved to .NET 8, which is why pyRevit ships separate loaders and why IronPython 2.7.12 has a documented 2025-only load failure in pyRevit 5.1. All the document-level signatures (`Grid.Create`, `Floor.Create`, `NewFamilyInstance`, Extensible Storage, `UnitTypeId`) are stable across all four versions.
- Several code snippets in the cited sources are C#/VB and from older API docs (2015–2024); the *signatures* are verified current, but transcribe carefully to IronPython (e.g. generic calls `Entity.Set[str](...)`, `get_Parameter` vs `LookupParameter`).
- `Floor.Create` ignores curve-loop elevation — you must set the height parameter explicitly; the most common failure is the "curve loops cannot compose a valid boundary" `ArgumentException` from open/unordered/non-planar loops.
- `ElementTransformUtils.RotateElement` about a horizontal beam's own axis is a documented no-op; use `STRUCTURAL_BEND_DIR_ANGLE` for horizontal-beam cross-section rotation.
- Beam/column offset BuiltInParameters can be null until the instance is regenerated and level-associated; always `doc.Regenerate()` before reading/setting them, and never attempt to *create* BuiltInParameters (only set existing ones).
- Planar-face derivation is your own computational-geometry code (no Revit API); budget for tolerance tuning and degenerate-case handling (collinear overlaps, dangling beam "filaments," nested holes).
- Extensible Storage schemas persist in memory across documents in a session; always `Schema.Lookup` before `SchemaBuilder` to avoid duplicate-GUID exceptions, and keep stored data small.
- Source disagreement noted: the shipped experimental IronPython 3 engine is referred to as both "3.4.0" (pyRevit repo docs) and "3.4.2" (third-party write-ups); confirm the exact engine list in your installed build via `pyrevit env`/Settings before relying on it. IronPython 3 remains experimental — keep IronPython 2.7.12 as the production engine.
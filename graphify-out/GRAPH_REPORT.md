# Graph Report - .  (2026-07-07)

## Corpus Check
- 51 files · ~0 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1988 nodes · 3080 edges · 144 communities (116 shown, 28 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 112 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Cad To Bim
- Framewintobim
- Element Builders (columns/beams/slabs)
- Shared WPF Forms Layer
- Rebar Core Parser
- Bulk Delete Dialogs
- Rebar Shape Resolver
- cad2bim Campaign Planning & Findings
- Parameter Combine
- Slab Prototype & Layer Classify
- Brand Guidelines & Module Plans
- Schedule Parsing Tests
- Toolkit Bundles & API Docs
- Module Bundle Plans
- cad2bim Report Pipeline
- Excel Helpers
- Mark/Label Parsing
- Beam Stress Suite (Test20)
- Export Schedule
- Rename Fillpatterns
- Rename Linepatterns
- Rename Linestyles
- Test Rectilinear Recovery
- Verify Toolkit
- Transform
- Delete Fillpatterns
- Delete Linepatterns
- Delete Linestyles
- Report
- Dxf Reader
- Test Core Detection
- Test Label Recovery
- Verify Toolkit
- Grids
- Report
- Report
- Test Perimeter Beams
- Copy Rebar Visibility
- Report
- Test Core Wall Labels
- Excel Writer
- Geometry Reader
- Test Curved Beams
- Bulk Rename
- Verify Toolkit
- Shapes
- Shapes
- Test Oriented Circle Recovery
- Test Text Correction Ownership
- Parameter Combine
- Application
- Units
- Rotate Column
- Shapes
- Onefilterparameter
- Test Beam Snap
- Test Beam Text Sizing
- Revision Tracker
- Verify Toolkit
- Main Window
- Shapes
- Model
- Compat
- Generate Stress Columns Dxf
- Test Slabs Proto
- Dispatching-Parallel-Agents
- Create Button
- Bulk Rename
- Shapes
- Shapes
- Test Circle Marks
- Transactions
- Compare
- Shapes
- Report
- Report
- Verify Toolkit
- Txn Failures
- Model
- Dxf Linker
- Pdf Exporter
- Parameters
- Is 2502 2019
- Verify Toolkit
- Shapes
- Model
- Report
- Replay Beams
- Test Slabs Proto
- Test Slabs Proto
- Using-Superpowers
- Aci 315 2018
- Verify Toolkit
- Dxf Reader
- Generate Stress Columns Adversarial
- Make Stress Plan
- Brainstorming
- Verification-Before-Completion
- Compatibility
- Elements
- Geometry
- Transactions
- Views
- Bs 8666 2020
- Verify Toolkit
- Config
- Report
- Demo Slabs
- Bbs Generator
- Verify Toolkit
- Brand Guidelines
- Path Resolver
- Filtering
- Verify Toolkit
- Verify Toolkit
- Verify Toolkit
- Anongee Bim Tools Brand Guidelines
- Writing-Plans
- Findings
- Verify Toolkit
- Placement
- Bundle

## God Nodes (most connected - your core abstractions)
1. `ParameterCombinerApp` - 29 edges
2. `BulkDeleteDialog` - 20 edges
3. `BulkDeleteDialog` - 20 edges
4. `BulkDeleteDialog` - 20 edges
5. `BulkRenameDialog` - 19 edges
6. `BulkRenameDialog` - 19 edges
7. `BulkRenameDialog` - 19 edges
8. `GenericBulkDeleteDialog` - 19 edges
9. `ExportScheduleDialog` - 18 edges
10. `GenericBulkRenameDialog` - 18 edges

## Surprising Connections (you probably didn't know these)
- `WpfDialogBase` --semantically_similar_to--> `Separate XAML from Python Pattern`  [INFERRED] [semantically similar]
  AnonGee.extension/lib/py3/anongee_toolkit/API.md → UI_Templates/README.md
- `run_ui Loader` --semantically_similar_to--> `WpfDialogBase`  [INFERRED] [semantically similar]
  UI_Templates/README.md → AnonGee.extension/lib/py3/anongee_toolkit/API.md
- `Voice & Tone (Error Message Contract)` --semantically_similar_to--> `Caveman terse response mode`  [INFERRED] [semantically similar]
  AnonGee_BIM_Tools_Brand_Guidelines.md → .claude/commands/caveman.md
- `RevitTransaction context manager` --semantically_similar_to--> `CPython 3 Engine Stability (native crash, persistent engine)`  [INFERRED] [semantically similar]
  modules_plan.md → AnonGee_BIM_Tools_Brand_Guidelines.md
- `FramewinToBIM IronPython to CPython3 migration` --conceptually_related_to--> `CPython 3 Engine Stability (native crash, persistent engine)`  [INFERRED]
  modules_plan.md → AnonGee_BIM_Tools_Brand_Guidelines.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Label-guided core-wall re-tiling pipeline** — findings_recover_core_walls_from_labels, findings_correct_columns_with_text, findings_recover_unplaced_labeled_columns, task_plan_label_guided_retiling [EXTRACTED 1.00]
- **Beam detection-to-placement flow** — findings_build_beam_segments, findings_edge_pair_beams, findings_curved_beams_from_edges, findings_place_beams, findings_place_curved_beams [INFERRED 0.85]
- **Deferred console + progress-bar mechanism** — 2026_06_26_beam_join_and_deferred_console_design_deferred_console_progress, 2026_06_26_beam_join_and_deferred_console_design_out_sink, 2026_06_26_beam_join_and_deferred_console_design_progress_helper, 2026_06_26_beam_join_and_deferred_console_design_cadtobimwindow [EXTRACTED 1.00]

## Communities (144 total, 28 thin omitted)

### Community 0 - "Cad To Bim"
Cohesion: 0.06
Nodes (42): _alert(), _bootstrap_lib_path(), CadToBimWindow, _create_beams(), _create_columns(), _create_grids(), _create_slabs(), _DeferredOut (+34 more)

### Community 1 - "Framewintobim"
Cohesion: 0.05
Nodes (48): auto_pick_floor(), auto_pick_symbol(), build_level_name_map(), clean_ft(), _col_length_m(), _collect(), distance_mm(), _ensure_active() (+40 more)

### Community 2 - "Element Builders (columns/beams/slabs)"
Cohesion: 0.06
Nodes (58): _disallow_joins(), _find_type_in_family(), place_beams(), place_curved_beams(), Place a curved beam for each concentric-arc-pair segment, driven by an Arc., Return a framing FamilySymbol of the given size, duplicating+caching.      With, Set the first writable matching type parameter to value_mm; True if set., Disallow the structural end-join at BOTH ends so Revit does not auto-extend the (+50 more)

### Community 3 - "Shared WPF Forms Layer"
Cohesion: 0.06
Nodes (23): InpToBimDialog, Validate only — no model writes, no transactions.         On success: capture se, Display a user-facing error message box.     If detail is provided (e.g. a trace, _show_error(), _id_value(), ObscuredRebarDialog, run(), _view_label() (+15 more)

### Community 4 - "Rebar Core Parser"
Cohesion: 0.07
Nodes (49): _activate_if_family_symbol(), _bounding_boxes_overlap(), _build_curve_loop_from_quad(), _build_level_cache(), _collect_family_symbols(), execute_generation_protocol(), _find_structural_layer_index(), get_floor_types() (+41 more)

### Community 5 - "Bulk Delete Dialogs"
Cohesion: 0.05
Nodes (19): GenericBulkDeleteDialog, Reusable WPF dialog for bulk-deleting graphic style elements.      Args:, DebounceTimer, Restart the debounce countdown., Cancel any pending callback., Base class for AnonGee WPF dialogs.      Subclass and call ``super().__init__(ui, Display *message* in the info badge., Display *message* in the success badge. (+11 more)

### Community 6 - "Rebar Shape Resolver"
Cohesion: 0.07
Nodes (30): AutoMarkGenerator, _member_prefix(), Extracts a short prefix from a structural member name.     Pass 1: single letter, read_bar_mark(), read_bar_type_name(), BarRecord, _collect_rebars(), _determine_best_param() (+22 more)

### Community 7 - "cad2bim Campaign Planning & Findings"
Cohesion: 0.06
Nodes (43): Deferred beam bug batch (out of scope of the features spec): B22->C12, B20 300x900, Test10 grid-6 miss, Test15 between-grid + short-curve errors, Feature A: disallow beam end-joins via StructuralFramingUtils.DisallowJoinAtEnd at both ends of every placed beam (best-effort), Feature B: deferred console (buffer + flush after Run) with a plain-print [####----] progress bar over 7 phases; buffer-list chosen over stdout redirect, Snap rule: move beam ends along the beam axis to the NEAREST column's station, never onto the centre point, never first-match, Bug 6b: B4/B5 mark swap; _edge_pair_beams let labels claim nearest candidate first-come instead of candidate-owned-by-nearest-label, Root-cause bug #1: script.py called build_beam_segments with texts=None, so no beam got depth or mark, Bug: C16 vanishes; _is_split_pair + _merge_to_label merge the fused C15+C16 blob into C15, consuming C16's geometry, Rationale: pure-geometry decomposition rejected; corner ownership in fused blobs is genuinely ambiguous without labels (+35 more)

### Community 8 - "Parameter Combine"
Cohesion: 0.09
Nodes (12): convert_to_display_units(), convert_to_internal_units(), evaluate_parameter(), extract_parameter_value(), get_element_parameters_dict(), get_unit_type(), is_yesno_parameter(), _make_brush() (+4 more)

### Community 9 - "Slab Prototype & Layer Classify"
Cohesion: 0.08
Nodes (36): apply_mapping(), build_default_mapping(), build_default_text_mapping(), classify_layer(), classify_text_layer(), Pre-fill {layer_key: category} from the convention for the override dialog., Stamp each record's .category from the (possibly overridden) mapping., Default routing for a TEXT layer: column / beam / grid / schedule, or ignore. (+28 more)

### Community 10 - "Brand Guidelines & Module Plans"
Cohesion: 0.07
Nodes (36): Accessibility Standards (WCAG 2.1 AA), AnonGeeTheme.xaml (master merge dictionary), Audience Profiles (Engineer, Architect, Modeler), Brand Identity (Precision, Authority, Clarity), Color System (Vivid Red, Charcoal Black, Silver Steel), CPython 3 Engine Stability (native crash, persistent engine), DataGrid __slots__/ArrayList/DataTrigger pattern, Design Principles (Native not novel, Fail loud) (+28 more)

### Community 11 - "Schedule Parsing Tests"
Cohesion: 0.08
Nodes (12): _Cell, FallbackLayouts, MarkToken, PlanLabelsAreNotATable, Test17 C5: on the PLAN, a markless size label and an unrelated mark share a, parse_mark must read the mark even when it butts straight against the size     w, Minimal TextRecord stand-in: text at a planar point., Cells for one row: (x, text) pairs at height y. (+4 more)

### Community 12 - "Toolkit Bundles & API Docs"
Cohesion: 0.07
Nodes (34): Bulk Delete Pulldown, Delete FillPatterns Tool, Delete LinePatterns Tool, Delete LineStyles Tool, Bulk Rename Pulldown, Rename FillPatterns Tool, Rename LinePatterns Tool, Rename LineStyles Tool (+26 more)

### Community 13 - "Module Bundle Plans"
Cohesion: 0.09
Nodes (33): Advance Panel Bundle, FilterParameter Split Button Bundle, Multi Filter Parameter Button, One Filter Parameter Button, Parameter Combination Button, AnonGee Tab Bundle, BIM Generation Button, Core Panel Bundle (+25 more)

### Community 14 - "cad2bim Report Pipeline"
Cohesion: 0.08
Nodes (33): _apply_beam_marks(), _beam_segment(), build_beam_segments(), _coincides_with_a_beam(), _collinear_continuation(), _continuation_beams(), _dedupe_marks(), _edge_pair_beams() (+25 more)

### Community 15 - "Excel Helpers"
Cohesion: 0.07
Nodes (21): ExcelComWriter, Auto-fit all column widths on *ws*, with a Reflection fallback., Set *ws* to landscape orientation, fit-to-1-page-wide., Export the active workbook as a PDF to *pdf_path*., Save the workbook as ``.xlsx``, release COM locks, then show Excel.          Arg, Drive Excel via COM automation to build and export workbooks.      Args:, Discard the workbook and terminate the Excel process silently., Add a new worksheet named *name* after the last existing sheet. (+13 more)

### Community 16 - "Mark/Label Parsing"
Cohesion: 0.09
Nodes (31): _cell_at(), _cluster_rows(), _header_role(), _is_beam_mark(), _is_header_row(), _median(), nearest_sized_text(), _number() (+23 more)

### Community 17 - "Beam Stress Suite (Test20)"
Cohesion: 0.12
Nodes (12): _angle(), _by_mark(), _mm_pt(), PolylineSnakes, The Revit link reader's polyline shapes, fed straight into detection., Z1Baseline, Z2Z3Angled, Z4WideContinuation (+4 more)

### Community 18 - "Export Schedule"
Cohesion: 0.11
Nodes (15): _excel_polish(), export_schedules_to_excel(), ExportScheduleDialog, _fmt_exc(), _norm_unit(), _obj_arr(), _parse_tsv_row(), Normalize a unit token: lowercase, map superscripts (² ³) and the     'Â' UTF-8/ (+7 more)

### Community 19 - "Rename Fillpatterns"
Cohesion: 0.12
Nodes (8): BulkRenameDialog, _fmt_exc(), Reference-only list of every current name, sorted, for the user to         brows, Case-sensitive replace-all. Returns (new_text, changed)., Case-insensitive replace-all. Returns (new_text, changed)., _replace_ci(), _replace_cs(), run()

### Community 20 - "Rename Linepatterns"
Cohesion: 0.12
Nodes (8): BulkRenameDialog, _fmt_exc(), Reference-only list of every current name, sorted, for the user to         brows, Case-sensitive replace-all. Returns (new_text, changed)., Case-insensitive replace-all. Returns (new_text, changed)., _replace_ci(), _replace_cs(), run()

### Community 21 - "Rename Linestyles"
Cohesion: 0.12
Nodes (8): BulkRenameDialog, _fmt_exc(), Reference-only list of every current name, sorted, for the user to         brows, Case-sensitive replace-all. Returns (new_text, changed)., Case-insensitive replace-all. Returns (new_text, changed)., _replace_ci(), _replace_cs(), run()

### Community 22 - "Test Rectilinear Recovery"
Cohesion: 0.11
Nodes (11): AssemblyGuards, BboxShellCompletion, CombDecomposition, DecomposeSanity, IrregularProfiles, A wall whose far end cap was clipped at a junction (the Grid H 12300 wall):, parse_column_polyline keeps a triangular column (3 corners) as an oriented     b, Point path (feet, 3D) from (x_mm, y_mm) corners. (+3 more)

### Community 23 - "Verify Toolkit"
Cohesion: 0.08
Nodes (18): _BoundingBoxXYZ, _Dispatcher, _ElementId, _ElementMulticategoryFilter, _FillPatternElement, _GeometryInstance, _LinePatternElement, _mock_class() (+10 more)

### Community 24 - "Transform"
Cohesion: 0.11
Nodes (20): Affine, apply_to_records(), apply_to_texts(), _bbox_after(), bbox_of_records(), build_dxf_to_internal(), empirical_affine(), from_link() (+12 more)

### Community 25 - "Delete Fillpatterns"
Cohesion: 0.16
Nodes (3): BulkDeleteDialog, _fmt_exc(), run()

### Community 26 - "Delete Linepatterns"
Cohesion: 0.16
Nodes (3): BulkDeleteDialog, _fmt_exc(), run()

### Community 27 - "Delete Linestyles"
Cohesion: 0.16
Nodes (3): BulkDeleteDialog, _fmt_exc(), run()

### Community 28 - "Report"
Cohesion: 0.12
Nodes (23): apply_circle_marks(), _beam_geometry_dump(), _compact_beams(), _compact_circles(), _compact_columns(), _compact_texts(), export_json(), format_beam_segments() (+15 more)

### Community 29 - "Dxf Reader"
Cohesion: 0.22
Nodes (21): _add_text(), _arc_points(), _circle_points(), _flatten(), _geometry_record(), _insert_point(), _layer(), _lwpolyline_points() (+13 more)

### Community 30 - "Test Core Detection"
Cohesion: 0.12
Nodes (6): CoreWallRecovery, FragmentedCoreDetection, _open_path(), shapes.recover_core_walls rebuilds the real fragmented Test18 core's FIVE member, Minimal placed-column stand-in (feet) for the centroid guard., _Rect

### Community 31 - "Test Label Recovery"
Cohesion: 0.16
Nodes (6): LabelRecovery, _Lbl, Redrawn-Test18 C17: a 300x600 cast hard against a 600x900 (C9) survives Revit's, _rect(), _sections(), StackedSliverDeferredToAbutment

### Community 32 - "Verify Toolkit"
Cohesion: 0.24
Nodes (21): check(), fail(), load_module(), ok(), Load a toolkit module by its relative path (e.g. 'revit/units.py')., section(), test_all_completeness(), test_application() (+13 more)

### Community 33 - "Grids"
Cohesion: 0.15
Nodes (14): build_grid_namer(), create_grids(), _curve_from_record(), existing_grid_names(), GridNamer, Convention namer, upgraded to text-derived names when grid labels exist., 0->A, 1->B, ... 25->Z, 26->AA, ..., Create grids inside an already-open transaction. Returns a result dict.      Cal (+6 more)

### Community 34 - "Report"
Cohesion: 0.11
Nodes (19): _apply_column_marks(), build_column_sections(), detect_fragmented_cores(), _filter_column_entries(), _find_core_outlines(), _inside_rectangles(), _polyline_length_ft(), _pts_mm() (+11 more)

### Community 35 - "Report"
Cohesion: 0.11
Nodes (19): _copy_rect(), correct_columns_with_text(), _fills_size(), _is_clipped(), _is_split_pair(), _label_size(), _merge_to_label(), Snap value to the nearest grid position within tol_ft, else return value. (+11 more)

### Community 36 - "Test Perimeter Beams"
Cohesion: 0.27
Nodes (5): _edge_beams(), _Lbl, _line(), PerimeterBeams, _Rec

### Community 37 - "Copy Rebar Visibility"
Cohesion: 0.20
Nodes (4): CopyRebarVisibilityDialog, _id_value(), run(), _view_label()

### Community 38 - "Report"
Cohesion: 0.12
Nodes (18): _carve_blob_from_labels(), _cells_free(), _connected_blobs(), _dims_match(), _labels_for_blob(), Re-place fused-outline columns from their size labels, before text-correction., (x_min, y_min, x_max, y_max) of an axis-aligned rect dict, in mm., Group rectangles into edge-adjacent components (a fused outline = one blob). (+10 more)

### Community 39 - "Test Core Wall Labels"
Cohesion: 0.31
Nodes (5): _core_pieces(), CoreWallLabels, _Lbl, _rect(), _sections()

### Community 40 - "Excel Writer"
Cohesion: 0.28
Nodes (16): _align(), _auto_fit_columns(), _build_bbs_row(), _fill(), _font(), Sets all populated row heights to default_height (points)., Groups BarRecord list by organization mode.     Returns nested dict:       "both, Build one BBS data row with dynamic Excel formula column references.      Column (+8 more)

### Community 41 - "Geometry Reader"
Cohesion: 0.22
Nodes (15): _curve_kind(), _curve_points(), _curve_to_record(), _layer_name(), _polyline_to_record(), Tessellate to (x, y, z) tuples; return [] on any failure (caller skips it)., CAD layer name via GraphicsStyle.GraphicsStyleCategory.Name.      GraphicsStyleI, Read one linked CAD instance into a ReadResult.      Fail-fast on bad inputs; re (+7 more)

### Community 42 - "Test Curved Beams"
Cohesion: 0.20
Nodes (8): _arc_fragments(), _curved_beam_records(), CurvedBeams, _Lbl, _pt(), n short 3-point arc records sampling radius r from deg_from..deg_to., _Rec, object

### Community 45 - "Shapes"
Cohesion: 0.19
Nodes (14): beam_centerline_from_quad(), beam_centerline_from_rect(), _distance(), _midpoint(), pair_parallel_lines(), Snap a measurement to the nearest standard size if within tolerance., Centerline of a 4-corner (possibly rotated) thin quad.      Returns (start, end,, Centerline of an axis-aligned Rectangle along its long axis (start, end, width_f (+6 more)

### Community 46 - "Shapes"
Cohesion: 0.13
Nodes (10): _convex_hull(), min_area_rect(), _min_dist2(), OrientedRect, Andrew's monotone-chain convex hull; returns hull vertices CCW., Minimum-area oriented bounding rectangle of a ring (rotating calipers).      Ret, Smallest squared distance between any point of a and any point of b., Recover oriented columns from clipped/fragmented outlines.      Revit's CAD impo (+2 more)

### Community 47 - "Test Oriented Circle Recovery"
Cohesion: 0.19
Nodes (4): CircularRecovery, OrientedRecovery, _ring(), _short_long()

### Community 48 - "Test Text Correction Ownership"
Cohesion: 0.30
Nodes (6): ClippedSizeSnap, _Lbl, Ownership, A label's size is authoritative: a clipped column is resized up to it, but an, _rect(), _run()

### Community 49 - "Parameter Combine"
Cohesion: 0.21
Nodes (3): run_ui(), First-stage popup: pick a scope (Active View / Whole Model) and the     element, ScopePickerApp

### Community 50 - "Application"
Cohesion: 0.21
Nodes (11): get_app(), get_current_doc(), get_current_uidoc(), Return the active Revit UIApplication (``__revit__``)., Return the active UIDocument, or raise RuntimeError if none is open., get_selected_elements(), Return the currently selected elements as a Python list.      Returns an empty l, Highlight *element_ids* in the active Revit UI.      Args:         element_ids ( (+3 more)

### Community 51 - "Units"
Cohesion: 0.20
Nodes (13): clean_ft(), ft_to_mm(), m_to_ft(), m_to_mm(), mm_to_ft(), _normalise_unit(), Convert metres to millimetres (rounded to nearest integer)., Convert millimetres to decimal feet. (+5 more)

### Community 52 - "Rotate Column"
Cohesion: 0.21
Nodes (13): filter_columns(), get_element_location_point(), get_selected_elements(), main(), Retrieve currently selected elements from the active document., Fail-Fast: Filter the selection to strictly Structural and Architectural columns, Safely extract the XYZ location of an element, handling slanted columns., Sort columns predictably by Y coordinate, then X coordinate. (+5 more)

### Community 53 - "Shapes"
Cohesion: 0.18
Nodes (13): _close(), _collinear(), _dedup(), is_rectilinear(), parse_column_polyline(), Recover columns from fused/unclosed axis-aligned wall outlines.      Assembles `, Project (x, y, z) tuples to 2D (x, y), returning (xy_list, z)., Return a closed ring as a vertex list with duplicates/collinear removed.      In (+5 more)

### Community 54 - "Onefilterparameter"
Cohesion: 0.18
Nodes (8): _bracket_int(), DebounceTimer, load_xaml_window(), PreviewItem, Parse a leading '[<int>]' prefix to an int (else None). Replaces     re.match —, One row in the live preview DataGrid. __slots__ is required for     Python.NET 3, Read ui.xaml — fully self-contained inline theme, no runtime injection needed., run_ui()

### Community 55 - "Test Beam Snap"
Cohesion: 0.39
Nodes (4): BeamEndSnap, _circle(), _rect(), _seg()

### Community 56 - "Test Beam Text Sizing"
Cohesion: 0.26
Nodes (5): _beam_record(), BeamTextSizing, _Lbl, Minimal beam CurveRecord stand-in (build_beam_segments reads these attrs only)., _Rec

### Community 57 - "Revision Tracker"
Cohesion: 0.20
Nodes (11): build_diff_summary(), compare_revisions(), load_previous_revision(), load_previous_revision_from_sidecar(), Loads a .bbs_rev sidecar directly by path., Returns count summary of each change type., Saves a JSON sidecar next to the xlsx.     records: list of BarRecord, Loads previous revision sidecar.     Returns None if not found. (+3 more)

### Community 58 - "Verify Toolkit"
Cohesion: 0.17
Nodes (4): _ns(), Create a simple namespace mock that also supports attribute access via __getitem, _register_mocks(), _Transaction

### Community 59 - "Main Window"
Cohesion: 0.21
Nodes (8): _XamlReader, BarVM, DiaVM, _get_all_rebar_params(), open_param_editor(), Extracts all parameter names from a sample rebar in the model., Opens the Parameter Editor Popup., run_ui()

### Community 60 - "Shapes"
Cohesion: 0.18
Nodes (6): bounding_rectangle(), An axis-aligned rectangle in feet (centre + size), with mm convenience., Recover a fragmented lift/stair core's columns by pairing opposing faces.      A, Axis-aligned bounding Rectangle of a ring (used as a non-rectilinear fallback)., recover_core_walls(), Rectangle

### Community 61 - "Model"
Cohesion: 0.18
Nodes (4): DxfReadResult, One text entity read from the DXF (TEXT / MTEXT / block ATTRIB).      The Revit, Geometry + text extracted from a DXF file by the ezdxf reader.      `records` ar, TextRecord

### Community 62 - "Compat"
Cohesion: 0.24
Nodes (8): element_id_value(), Return the integer value of an ElementId across Revit versions.      Fail-fast o, One-line description of the live Python/IronPython runtime.      Used by the sta, runtime_summary(), describe_link(), find_cad_links(), Return all linked CAD ImportInstances in the document (possibly empty).      Fai, Human-readable label for a linked CAD instance via its CADLinkType.      Never r

### Community 63 - "Generate Stress Columns Dxf"
Cohesion: 0.22
Nodes (5): box(), poly(), Closed rectangle centred at (cx, cy), width b (x) x height h (y)., Closed rectangle rotated deg degrees about its centre., rotated_box()

### Community 65 - "Dispatching-Parallel-Agents"
Cohesion: 0.27
Nodes (10): Dispatching Parallel Agents, Executing Plans, Finishing a Development Branch, /graphify (knowledge graph pipeline), Code Review Reception, Requesting Code Review, Subagent-Driven Development, Systematic Debugging (root-cause-first) (+2 more)

### Community 67 - "Bulk Rename"
Cohesion: 0.20
Nodes (4): Replace all occurrences of *find* in *text* (case-sensitive).      Returns:, Replace all occurrences of *find* in *text* (case-insensitive), without     usin, replace_case_insensitive(), replace_case_sensitive()

### Community 68 - "Shapes"
Cohesion: 0.22
Nodes (6): build_circular_columns(), Circle, circle_from_three_points(), A circular column footprint: centre + diameter, in feet., Exact circumcircle (cx, cy, r) of three 2D points, or None if collinear., Recover circular columns from arc records on the column layer.      Each arc sto

### Community 69 - "Shapes"
Cohesion: 0.22
Nodes (9): decompose_to_rectangles(), _extend_columns(), _extend_rows(), _point_in_polygon(), Ray-casting test; ring is a list of (x, y) with no closing duplicate., Greedily extend a run rightward along row r; return the last column index., Greedily extend the [c..c_end] band upward; return the last row index., Partition a rectilinear ring into axis-aligned Rectangles (exact cover).      Ca (+1 more)

### Community 70 - "Test Circle Marks"
Cohesion: 0.39
Nodes (3): ApplyCircleMarks, _circle(), _Txt

### Community 71 - "Transactions"
Cohesion: 0.25
Nodes (4): IFailuresPreprocessor that silently discards all warnings so they never     surf, Context manager for a single Revit Transaction.      Commits on clean exit; roll, RevitTransaction, SuppressWarningsPreprocessor

### Community 72 - "Compare"
Cohesion: 0.39
Nodes (7): diff(), format_console(), _length_mm(), _midpoint(), _per_layer(), Short console lines summarising the comparison., Return a structured comparison of the two geometry sets (internal feet).      Ma

### Community 73 - "Shapes"
Cohesion: 0.25
Nodes (8): assemble_rectilinear_rings(), _bbox_shell_ring(), _edges_of(), 2D edges of a point path. Returns (edges, all_axis_aligned)., Walk a simple cycle (all vertices degree 2) from start; return (ring, pids)., Close a partial rectangle outline to its bounding box, or return None.      `edg, Stitch open, axis-aligned fragments into closed rectilinear rings.      Revit's, _walk_cycle()

### Community 74 - "Report"
Cohesion: 0.29
Nodes (8): _aabb_overlaps(), _bbox_half(), _center_inside_larger(), True when rect's centre sits INSIDE a strictly larger placed rectangle.      A r, Axis-aligned half-extents (hx, hy) in feet of a possibly-rotated column rect., True if the box with half-extents (hx, hy) at (cx, cy) overlaps any rect., Place a labelled column that geometry recovery ABSORBED into a larger neighbour., recover_unplaced_labeled_columns()

### Community 75 - "Report"
Cohesion: 0.25
Nodes (8): build_category_counts(), build_layer_counts(), format_console(), format_summary(), {layer_key: {'count': int, 'kinds': {kind: int}}} for the summary table., {category: count}, including unmapped, so nothing is silently dropped., Return a list of plain-text lines describing the read (no markup)., Short, copy-friendly console summary. Full detail goes into the JSON.

### Community 76 - "Verify Toolkit"
Cohesion: 0.25
Nodes (3): _DispatcherTimer, _EventSlot, Supports `timer.Tick += handler` and `timer.Tick -= handler` idioms.

### Community 77 - "Txn Failures"
Cohesion: 0.33
Nodes (5): attach_warning_swallower(), Deletes warning-severity failures during a transaction; errors untouched.      `, Attach the warning swallower to a started transaction's failure options.      De, WarningSwallower, IFailuresPreprocessor

### Community 78 - "Model"
Cohesion: 0.29
Nodes (3): CurveRecord, One extracted curve from a linked CAD., Stable dictionary key, collapsing a missing layer to NO_LAYER.

### Community 79 - "Dxf Linker"
Cohesion: 0.33
Nodes (6): _choices(), link_dxf(), [(label, enum_value)] for the enum members that exist on this Revit version., Link `path` into doc with the chosen unit + placement; return ImportInstance., Normalise Document.Link's return across engines.      pythonnet (CPython3) retur, _unpack_out()

### Community 80 - "Pdf Exporter"
Cohesion: 0.38
Nodes (6): export_pdf(), _export_via_com(), _export_via_fpdf2(), Exports xlsx to PDF. Returns (success, message, pdf_path|None).     Tries COM fi, Export via Excel COM Interop (.NET). Requires Excel installed., Export via fpdf2 — pure Python fallback.     Reads the BBS sheet from the xlsx a

### Community 81 - "Parameters"
Cohesion: 0.38
Nodes (6): get_parameter(), get_parameter_value(), Return the Parameter named *param_name* from *element*.      Checks the element, Return the value of *param_name* on *element*.      For ElementId parameters the, Set *param_name* on *element* to *value*.      Returns ``False`` if the paramete, set_parameter_value()

### Community 82 - "Is 2502 2019"
Cohesion: 0.29
Nodes (6): bend_deduction_per_bend(), bend_diameter_mm(), cutting_length_formula(), Returns a multi-line formula string for the Calculation Sheet.     phi = bar dia, Returns minimum mandrel/bend diameter in mm.     Links/stirrups (is_link=True):, Deduction = multiplier * phi per individual bend.

### Community 84 - "Shapes"
Cohesion: 0.33
Nodes (6): build_line_spines(), _consistent_edge(), _near_edges(), Turn bare lines on the column layer into spine Rectangles.      A line becomes a, Collect leg edges (perpendicular coord) that lie within the gap band and     ove, Return the leg-edge coordinate shared by >= 2 legs nearest the line, else None.

### Community 85 - "Model"
Cohesion: 0.33
Nodes (3): The full outcome of reading one linked CAD., Distinct layer keys present, sorted for stable display., ReadResult

### Community 86 - "Report"
Cohesion: 0.33
Nodes (6): _arc_span(), _curved_beams_from_edges(), _curved_segment(), Pair concentric inner/outer edges into curved beam segments.      Two edges shar, (start_deg, end_deg) of the populated arc, sweeping CCW across the LARGEST gap., A placeable curved beam: centre, centreline radius, swept angle, width (mm/ft).

### Community 87 - "Replay Beams"
Cohesion: 0.47
Nodes (3): main(), records_from_raw(), T

### Community 90 - "Using-Superpowers"
Cohesion: 0.33
Nodes (6): Instruction Priority (user > skills > system), Skill Priority (process before implementation), Using Superpowers / Using Skills, Match the Form to the Failure, Skill Discovery Optimization (SDO), Writing Skills

### Community 93 - "Dxf Reader"
Cohesion: 0.40
Nodes (5): _ensure_ezdxf(), ezdxf_available(), Import ezdxf on demand; cache the module once it succeeds. Returns bool., Read one DXF into a DxfReadResult(records, texts), in DXF coordinates.      Fail, read_dxf()

### Community 95 - "Make Stress Plan"
Cohesion: 0.50
Nodes (3): line(), pair(), Two edge lines `width` apart around centreline (x1,y1)->(x2,y2).

### Community 96 - "Brainstorming"
Cohesion: 0.40
Nodes (5): Brainstorming Ideas Into Designs, /plan command (init planning files), Planning with Files (disk-as-working-memory), /status command (read task_plan.md), test command (brainstorm-mode stub)

### Community 97 - "Verification-Before-Completion"
Cohesion: 0.40
Nodes (5): Iron Law: No Completion Claims Without Fresh Verification Evidence, Verification Before Completion, Writing Plans, RED-GREEN-REFACTOR for Skills, Writing Skills IS TDD for Process Documentation

### Community 98 - "Compatibility"
Cohesion: 0.40
Nodes (4): create_element_id(), get_element_id_value(), Create an ElementId from an integer, handling the Int32→Int64 change in     Revi, Extract the integer value from an ElementId, handling the .Value / .IntegerValue

### Community 99 - "Elements"
Cohesion: 0.40
Nodes (4): get_family_name(), get_type_name(), Return the Family Name of *element*.      Resolution order:       1. FamilyInsta, Return the Type Name of *element*, or ``"N/A"`` if it cannot be resolved.

### Community 100 - "Geometry"
Cohesion: 0.40
Nodes (4): bounding_boxes_overlap(), get_solid_volume_m3(), Return the total net solid volume of *element* in cubic metres.      Iterates th, Return ``True`` if two BoundingBoxXYZ objects overlap in 3-D space.      Args:

### Community 102 - "Views"
Cohesion: 0.40
Nodes (4): get_eligible_views(), get_view_label(), Return ``"<view name> [<type label>]"`` for a given View., Return a name-sorted list of non-template views of allowed types.      Args:

### Community 106 - "Report"
Cohesion: 0.50
Nodes (4): _apply_curved_marks(), _nearest_sized_label(), Size each curved beam from the nearest beam label to its mid-arc point.      Dep, Nearest (text, small, big) within radius_ft of (cx, cy), or None.

### Community 108 - "Bbs Generator"
Cohesion: 0.67
Nodes (3): main(), Shows a pyRevit alert dialog., show_alert()

## Knowledge Gaps
- **57 isolated node(s):** `_Visibility`, `_Dispatcher`, `_UriKind`, `_Solid`, `_FillPatternElement` (+52 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_Array` connect `Excel Helpers` to `Verify Toolkit`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `load_xaml()` connect `Bulk Delete Dialogs` to `Main Window`, `Bulk Rename`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `put_block()` connect `Framewintobim` to `Excel Helpers`?**
  _High betweenness centrality (0.034) - this node is a cross-community bridge._
- **What connects `Parse a leading '[<int>]' prefix to an int (else None). Replaces     re.match —`, `One row in the live preview DataGrid. __slots__ is required for     Python.NET 3`, `Read ui.xaml — fully self-contained inline theme, no runtime injection needed.` to the rest of the system?**
  _452 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Cad To Bim` be split into smaller, more focused modules?**
  _Cohesion score 0.058173076923076925 - nodes in this community are weakly interconnected._
- **Should `Framewintobim` be split into smaller, more focused modules?**
  _Cohesion score 0.051923076923076926 - nodes in this community are weakly interconnected._
- **Should `Element Builders (columns/beams/slabs)` be split into smaller, more focused modules?**
  _Cohesion score 0.05552617662612375 - nodes in this community are weakly interconnected._
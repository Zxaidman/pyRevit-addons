# Graph Report - .  (2026-07-16)

## Corpus Check
- 274 files · ~3,875,697 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2647 nodes · 4087 edges · 166 communities (137 shown, 29 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 132 edges (avg confidence: 0.74)
- Token cost: 140,870 input · 0 output

## Community Hubs (Navigation)
- CAD-to-BIM Dialog Window
- BIM Generation Helpers
- CAD-to-BIM Dialog XAML
- Beam Sizing & Marks Tests
- INP-to-BIM Dialog & Bulk Tools
- BIM Generation Core Protocol
- Element Builders (Beams/Columns)
- Bulk Tool XAML A
- Bulk Tool XAML B
- Bulk Tool XAML C
- Stress Plan & Stair Tests
- Slab Outline Tests
- Rebar Mark Toolkit
- Bulk Tool XAML D
- Parameter Utilities
- Bulk Tool XAML E
- Beam Split Tests
- Brand & Docs Corpus
- Schedule Parsing Tests
- Stair Layout Engine
- Text Mark Classification
- Beam Stress Suite
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 127
- Community 128
- Community 129
- Community 130
- Community 131
- Community 132
- Community 133
- Community 136
- Community 137
- Community 138
- Community 139
- Community 140
- Community 144
- Community 145
- Community 147
- Community 155
- Community 156
- Community 157

## God Nodes (most connected - your core abstractions)
1. `Window` - 51 edges
2. `Window` - 31 edges
3. `Window` - 30 edges
4. `Window` - 30 edges
5. `Window` - 30 edges
6. `ParameterCombinerApp` - 29 edges
7. `Window` - 26 edges
8. `Window` - 24 edges
9. `Window` - 24 edges
10. `Window` - 24 edges

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
- **Bulk Tool Ribbon Stack Hierarchy** — anongee_extension_anongee_tab_essential_panel_bulktool_stack_bundle_bulk_tool, anongee_extension_anongee_tab_essential_panel_bulktool_stack_bulk_delete_pulldown_bundle_bulk_delete, anongee_extension_anongee_tab_essential_panel_bulktool_stack_bulk_rename_pulldown_bundle_bulk_rename, anongee_extension_anongee_tab_essential_panel_bulktool_stack_bundle_rebar_pulldown [EXTRACTED 1.00]
- **cad2bim Structural Member Recovery Pipeline** — findings_cad2bim_pipeline, findings_recover_core_walls_from_labels, findings_build_beam_segments, findings_slab_outlines, progress_staircase_pipeline [EXTRACTED 1.00]
- **Revit-Free Offline Verification Workflow** — progress_harness_bootstrap, findings_replay_beams_harness, findings_test19_fixture, findings_test20_stress_fixture [INFERRED 0.85]
- **Deferred console + progress-bar mechanism** — 2026_06_26_beam_join_and_deferred_console_design_deferred_console_progress, 2026_06_26_beam_join_and_deferred_console_design_out_sink, 2026_06_26_beam_join_and_deferred_console_design_progress_helper, 2026_06_26_beam_join_and_deferred_console_design_cadtobimwindow [EXTRACTED 1.00]

## Communities (166 total, 29 thin omitted)

### Community 0 - "CAD-to-BIM Dialog Window"
Cohesion: 0.05
Nodes (48): _alert(), _bootstrap_lib_path(), CadToBimWindow, _create_beams(), _create_columns(), _create_grids(), _create_slabs(), _create_stairs() (+40 more)

### Community 1 - "BIM Generation Helpers"
Cohesion: 0.05
Nodes (48): auto_pick_floor(), auto_pick_symbol(), build_level_name_map(), clean_ft(), _col_length_m(), _collect(), distance_mm(), _ensure_active() (+40 more)

### Community 2 - "CAD-to-BIM Dialog XAML"
Cohesion: 0.06
Nodes (58): btn_cancel, btn_run, cb_base_level, cb_beam_family, cb_circular_family, cb_family, cb_floor_type, cb_stair_source (+50 more)

### Community 3 - "Beam Sizing & Marks Tests"
Cohesion: 0.07
Nodes (21): _beam_record(), BeamTextSizing, _Lbl, Minimal beam CurveRecord stand-in (build_beam_segments reads these attrs only)., _Rec, ApplyCircleMarks, _circle(), _Txt (+13 more)

### Community 4 - "INP-to-BIM Dialog & Bulk Tools"
Cohesion: 0.05
Nodes (21): InpToBimDialog, Validate only — no model writes, no transactions.         On success: capture se, Display a user-facing error message box.     If detail is provided (e.g. a trace, _show_error(), GenericBulkDeleteDialog, Open the dialog, or show an alert if no targets exist in the document., Reusable WPF dialog for bulk-deleting graphic style elements.      Args:, Open the dialog, or show an alert if no targets exist in the document. (+13 more)

### Community 5 - "BIM Generation Core Protocol"
Cohesion: 0.07
Nodes (49): _activate_if_family_symbol(), _bounding_boxes_overlap(), _build_curve_loop_from_quad(), _build_level_cache(), _collect_family_symbols(), execute_generation_protocol(), _find_structural_layer_index(), get_floor_types() (+41 more)

### Community 6 - "Element Builders (Beams/Columns)"
Cohesion: 0.07
Nodes (42): _disallow_joins(), _find_type_in_family(), place_beams(), place_curved_beams(), Place a curved beam for each concentric-arc-pair segment, driven by an Arc., Return a framing FamilySymbol of the given size, duplicating+caching.      With, Set the first writable matching type parameter to value_mm; True if set., Disallow the structural end-join at BOTH ends so Revit does not auto-extend the (+34 more)

### Community 7 - "Bulk Tool XAML A"
Cohesion: 0.06
Nodes (44): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnClose, BtnRename, ChkMatchCase (+36 more)

### Community 8 - "Bulk Tool XAML B"
Cohesion: 0.06
Nodes (44): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnClose, BtnRename, ChkMatchCase (+36 more)

### Community 9 - "Bulk Tool XAML C"
Cohesion: 0.06
Nodes (44): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnClose, BtnRename, ChkMatchCase (+36 more)

### Community 10 - "Stress Plan & Stair Tests"
Cohesion: 0.08
Nodes (15): line(), pair(), Two edge lines `width` apart around centreline (x1,y1)->(x2,y2)., DoglegNumbers, FullPipeline, KeepPointsFace, _linework_stair(), LineworkStairs (+7 more)

### Community 11 - "Slab Outline Tests"
Cohesion: 0.08
Nodes (10): BeamGraphFaces, InsetGraph, MemberEdgeFaces, PlacedMemberFaces, Faces synthesized from the PLACED beams/columns (the user-proposed source)., _Rec, _Record, SlabEdgeLoops (+2 more)

### Community 12 - "Rebar Mark Toolkit"
Cohesion: 0.07
Nodes (30): AutoMarkGenerator, _member_prefix(), Extracts a short prefix from a structural member name.     Pass 1: single letter, read_bar_mark(), read_bar_type_name(), BarRecord, _collect_rebars(), _determine_best_param() (+22 more)

### Community 13 - "Bulk Tool XAML D"
Cohesion: 0.07
Nodes (42): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnAll, BtnClose, BtnExport (+34 more)

### Community 14 - "Parameter Utilities"
Cohesion: 0.09
Nodes (12): convert_to_display_units(), convert_to_internal_units(), evaluate_parameter(), extract_parameter_value(), get_element_parameters_dict(), get_unit_type(), is_yesno_parameter(), _make_brush() (+4 more)

### Community 15 - "Bulk Tool XAML E"
Cohesion: 0.07
Nodes (37): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnAll, BtnApply, BtnClose (+29 more)

### Community 16 - "Beam Split Tests"
Cohesion: 0.13
Nodes (11): BeamSplitAtColumns, _circle(), ColumnOutlineFootprints, DedupeBeamSegments, _ends_mm(), Retraced beam outlines emit the same centreline twice (test8's strips)., Closed rectangular column-layer outlines become obstacles even unplaced., _Rec (+3 more)

### Community 17 - "Brand & Docs Corpus"
Cohesion: 0.07
Nodes (36): Accessibility Standards (WCAG 2.1 AA), AnonGeeTheme.xaml (master merge dictionary), Audience Profiles (Engineer, Architect, Modeler), Brand Identity (Precision, Authority, Clarity), Color System (Vivid Red, Charcoal Black, Silver Steel), CPython 3 Engine Stability (native crash, persistent engine), DataGrid __slots__/ArrayList/DataTrigger pattern, Design Principles (Native not novel, Fail loud) (+28 more)

### Community 18 - "Schedule Parsing Tests"
Cohesion: 0.08
Nodes (12): _Cell, FallbackLayouts, MarkToken, PlanLabelsAreNotATable, Test17 C5: on the PLAN, a markless size label and an unrelated mark share a, parse_mark must read the mark even when it butts straight against the size     w, Minimal TextRecord stand-in: text at a planar point., Cells for one row: (x, text) pairs at height y. (+4 more)

### Community 19 - "Stair Layout Engine"
Cohesion: 0.09
Nodes (34): _arrival_landing(), _cluster_lines(), direction_label(), _dogleg_run_dicts(), find_direction_texts(), find_stair_texts(), _oriented_extents(), plan_dogleg_stair() (+26 more)

### Community 20 - "Text Mark Classification"
Cohesion: 0.09
Nodes (33): _cell_at(), _cluster_rows(), _header_role(), _is_beam_mark(), _is_header_row(), _is_slab_mark(), _median(), nearest_sized_text() (+25 more)

### Community 21 - "Beam Stress Suite"
Cohesion: 0.11
Nodes (14): _angle(), _by_mark(), _mm_pt(), PolylineSnakes, The Revit link reader's polyline shapes, fed straight into detection., The generated stress-plan DXF; built into a TEMP dir when not present.      The, _stress_dxf(), Z1Baseline (+6 more)

### Community 22 - "Community 22"
Cohesion: 0.09
Nodes (33): Advance Panel Bundle, FilterParameter Split Button Bundle, Multi Filter Parameter Button, One Filter Parameter Button, Parameter Combination Button, AnonGee Tab Bundle, BIM Generation Button, Core Panel Bundle (+25 more)

### Community 23 - "Community 23"
Cohesion: 0.09
Nodes (32): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnAll, BtnClose, BtnDelete (+24 more)

### Community 24 - "Community 24"
Cohesion: 0.09
Nodes (32): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnAll, BtnClose, BtnDelete (+24 more)

### Community 25 - "Community 25"
Cohesion: 0.09
Nodes (32): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnAll, BtnClose, BtnDelete (+24 more)

### Community 26 - "Community 26"
Cohesion: 0.07
Nodes (21): ExcelComWriter, Auto-fit all column widths on *ws*, with a Reflection fallback., Set *ws* to landscape orientation, fit-to-1-page-wide., Export the active workbook as a PDF to *pdf_path*., Save the workbook as ``.xlsx``, release COM locks, then show Excel.          Arg, Drive Excel via COM automation to build and export workbooks.      Args:, Discard the workbook and terminate the Excel process silently., Add a new worksheet named *name* after the last existing sheet. (+13 more)

### Community 27 - "Community 27"
Cohesion: 0.11
Nodes (15): _excel_polish(), export_schedules_to_excel(), ExportScheduleDialog, _fmt_exc(), _norm_unit(), _obj_arr(), _parse_tsv_row(), Normalize a unit token: lowercase, map superscripts (² ³) and the     'Â' UTF-8/ (+7 more)

### Community 28 - "Community 28"
Cohesion: 0.12
Nodes (8): BulkRenameDialog, _fmt_exc(), Reference-only list of every current name, sorted, for the user to         brows, Case-sensitive replace-all. Returns (new_text, changed)., Case-insensitive replace-all. Returns (new_text, changed)., _replace_ci(), _replace_cs(), run()

### Community 29 - "Community 29"
Cohesion: 0.12
Nodes (8): BulkRenameDialog, _fmt_exc(), Reference-only list of every current name, sorted, for the user to         brows, Case-sensitive replace-all. Returns (new_text, changed)., Case-insensitive replace-all. Returns (new_text, changed)., _replace_ci(), _replace_cs(), run()

### Community 30 - "Community 30"
Cohesion: 0.12
Nodes (8): BulkRenameDialog, _fmt_exc(), Reference-only list of every current name, sorted, for the user to         brows, Case-sensitive replace-all. Returns (new_text, changed)., Case-insensitive replace-all. Returns (new_text, changed)., _replace_ci(), _replace_cs(), run()

### Community 31 - "Community 31"
Cohesion: 0.11
Nodes (11): AssemblyGuards, BboxShellCompletion, CombDecomposition, DecomposeSanity, IrregularProfiles, A wall whose far end cap was clipped at a junction (the Grid H 12300 wall):, parse_column_polyline keeps a triangular column (3 corners) as an oriented     b, Point path (feet, 3D) from (x_mm, y_mm) corners. (+3 more)

### Community 32 - "Community 32"
Cohesion: 0.07
Nodes (17): DebounceTimer, Restart the debounce countdown., Cancel any pending callback., Base class for AnonGee WPF dialogs.      Subclass and call ``super().__init__(ui, Display *message* in the info badge., Display *message* in the success badge., Display *message* in the error badge., Force the WPF dispatcher to process pending render work immediately. (+9 more)

### Community 33 - "Community 33"
Cohesion: 0.11
Nodes (27): BadgeError, BadgeInfo, BadgeSuccess, Bd, Bg, BtnAll, BtnApply, BtnClose (+19 more)

### Community 34 - "Community 34"
Cohesion: 0.11
Nodes (27): _arc_spans(), _curve_loop(), _find_type(), floor_types(), _nearest_index(), _nest_openings(), place_slabs(), _point_in_ring() (+19 more)

### Community 35 - "Community 35"
Cohesion: 0.08
Nodes (28): Label-Owns-Segment Mark Matching, build_beam_segments (Beam Detection), cad2bim CAD-to-BIM Pipeline, correct_columns_with_text (Column Text Correction), Curved Beam Detection and Placement, _edge_pair_beams (Floor-Clipped Perimeter Beam Recovery), Greedy Decomposition Corner-Stealing Bug, Grid-Bucketed Pairwise Geometry Passes (+20 more)

### Community 36 - "Community 36"
Cohesion: 0.08
Nodes (18): _BoundingBoxXYZ, _Dispatcher, _ElementId, _ElementMulticategoryFilter, _FillPatternElement, _GeometryInstance, _LinePatternElement, _mock_class() (+10 more)

### Community 37 - "Community 37"
Cohesion: 0.10
Nodes (25): apply_circle_marks(), _beam_geometry_dump(), _compact_beams(), _compact_circles(), _compact_columns(), _compact_texts(), dedupe_beam_segments(), export_json() (+17 more)

### Community 38 - "Community 38"
Cohesion: 0.11
Nodes (25): apply_slab_labels(), _beam_fraction(), _centroid(), _in_rect_footprint(), _inset_ring(), _is_simple_ring(), _line_x_line(), _next_ccw() (+17 more)

### Community 39 - "Community 39"
Cohesion: 0.16
Nodes (3): BulkDeleteDialog, _fmt_exc(), run()

### Community 40 - "Community 40"
Cohesion: 0.16
Nodes (3): BulkDeleteDialog, _fmt_exc(), run()

### Community 41 - "Community 41"
Cohesion: 0.16
Nodes (3): BulkDeleteDialog, _fmt_exc(), run()

### Community 42 - "Community 42"
Cohesion: 0.12
Nodes (24): bbox_center(), bic(), build_dim_line(), classify(), datum_curve(), dimension_datums(), dimension_element(), element_frame() (+16 more)

### Community 43 - "Community 43"
Cohesion: 0.11
Nodes (21): _apply_waist(), _create_winder_run(), _delete_auto_railings(), _line_x_line(), place_stairs(), Set the first existing BuiltInParameter from `builtin_names` (the enum     membe, Create one dog-leg stair per plan. Returns created/skipped/errors lists.      Ea, Remove the railings Revit auto-hosts on each new stair (user request:     no rai (+13 more)

### Community 44 - "Community 44"
Cohesion: 0.11
Nodes (20): Affine, apply_to_records(), apply_to_texts(), _bbox_after(), bbox_of_records(), build_dxf_to_internal(), empirical_affine(), from_link() (+12 more)

### Community 45 - "Community 45"
Cohesion: 0.10
Nodes (25): _apply_beam_marks(), _beam_segment(), build_beam_segments(), _coincides_with_a_beam(), _dedupe_marks(), _edge_pair_beams(), _filter_beam_segments(), _group_arc_edges() (+17 more)

### Community 46 - "Community 46"
Cohesion: 0.14
Nodes (21): element_id_value(), Return the integer value of an ElementId across Revit versions.      Fail-fast o, describe_link(), find_cad_links(), Return all linked CAD ImportInstances in the document (possibly empty).      Fai, Human-readable label for a linked CAD instance via its CADLinkType.      Never r, _curve_kind(), _curve_points() (+13 more)

### Community 47 - "Community 47"
Cohesion: 0.12
Nodes (6): CoreWallRecovery, FragmentedCoreDetection, _open_path(), shapes.recover_core_walls rebuilds the real fragmented Test18 core's FIVE member, Minimal placed-column stand-in (feet) for the centroid guard., _Rect

### Community 48 - "Community 48"
Cohesion: 0.16
Nodes (6): LabelRecovery, _Lbl, Redrawn-Test18 C17: a 300x600 cast hard against a 600x900 (C9) survives Revit's, _rect(), _sections(), StackedSliverDeferredToAbutment

### Community 49 - "Community 49"
Cohesion: 0.24
Nodes (21): check(), fail(), load_module(), ok(), Load a toolkit module by its relative path (e.g. 'revit/units.py')., section(), test_all_completeness(), test_application() (+13 more)

### Community 50 - "Community 50"
Cohesion: 0.20
Nodes (4): _id_value(), ObscuredRebarDialog, run(), _view_label()

### Community 51 - "Community 51"
Cohesion: 0.20
Nodes (4): CopyRebarVisibilityDialog, _id_value(), run(), _view_label()

### Community 52 - "Community 52"
Cohesion: 0.15
Nodes (14): build_grid_namer(), create_grids(), _curve_from_record(), existing_grid_names(), GridNamer, Convention namer, upgraded to text-derived names when grid labels exist., 0->A, 1->B, ... 25->Z, 26->AA, ..., Create grids inside an already-open transaction. Returns a result dict.      Cal (+6 more)

### Community 53 - "Community 53"
Cohesion: 0.11
Nodes (19): _apply_column_marks(), build_column_sections(), detect_fragmented_cores(), _filter_column_entries(), _find_core_outlines(), _inside_rectangles(), _polyline_length_ft(), _pts_mm() (+11 more)

### Community 54 - "Community 54"
Cohesion: 0.11
Nodes (19): _copy_rect(), correct_columns_with_text(), _fills_size(), _is_clipped(), _is_split_pair(), _label_size(), _merge_to_label(), Snap value to the nearest grid position within tol_ft, else return value. (+11 more)

### Community 55 - "Community 55"
Cohesion: 0.14
Nodes (18): AnonGee Toolkit Public API, cad2bim CAD-to-BIM Pipeline, CPython 3 Crash Avoidance Pattern, GenericBulkDeleteDialog, GenericBulkRenameDialog, marks.parse_schedule, Revit 2024 ElementId Int32-to-Int64 Compatibility Shim, RevitTransaction Context Manager (+10 more)

### Community 56 - "Community 56"
Cohesion: 0.12
Nodes (18): _carve_blob_from_labels(), _cells_free(), _connected_blobs(), _dims_match(), _labels_for_blob(), Re-place fused-outline columns from their size labels, before text-correction., (x_min, y_min, x_max, y_max) of an axis-aligned rect dict, in mm., Group rectangles into edge-adjacent components (a fused outline = one blob). (+10 more)

### Community 57 - "Community 57"
Cohesion: 0.15
Nodes (18): _append_footprint_rings(), _chain_into_rings(), _dedup_ring(), _dist(), _piece_fingerprint(), Slab boundary rings straight from the slab-edge layer, [(ring, z, arcs), ...]., Orientation-free identity of a drawn piece (10 mm grid, endpoint-sorted)., Greedily join open polylines end-to-end; yield the ones that close. (+10 more)

### Community 58 - "Community 58"
Cohesion: 0.31
Nodes (5): _core_pieces(), CoreWallLabels, _Lbl, _rect(), _sections()

### Community 59 - "Community 59"
Cohesion: 0.28
Nodes (16): _align(), _auto_fit_columns(), _build_bbs_row(), _fill(), _font(), Sets all populated row heights to default_height (points)., Groups BarRecord list by organization mode.     Returns nested dict:       "both, Build one BBS data row with dynamic Excel formula column references.      Column (+8 more)

### Community 60 - "Community 60"
Cohesion: 0.16
Nodes (16): Bulk Delete Pulldown, Delete Fill Patterns Tool, Delete Line Patterns Tool, Delete Line Styles Tool, Bulk Rename Pulldown, Rename Fill Patterns Tool, Rename Line Patterns Tool, Rename Line Styles Tool (+8 more)

### Community 61 - "Community 61"
Cohesion: 0.12
Nodes (16): _clip_slab(), _column_footprints(), column_outline_footprints(), column_trim_footprints(), _distinct_ring_corners(), _footprint_interval(), Place columns from CLOSED rectangular column-layer outlines the size     limits, First-visit distinct vertices of a (possibly retraced) closed polyline. (+8 more)

### Community 64 - "Community 64"
Cohesion: 0.19
Nodes (14): beam_centerline_from_quad(), beam_centerline_from_rect(), _distance(), _midpoint(), pair_parallel_lines(), Snap a measurement to the nearest standard size if within tolerance., Centerline of a 4-corner (possibly rotated) thin quad.      Returns (start, end,, Centerline of an axis-aligned Rectangle along its long axis (start, end, width_f (+6 more)

### Community 65 - "Community 65"
Cohesion: 0.13
Nodes (10): _convex_hull(), min_area_rect(), _min_dist2(), OrientedRect, Andrew's monotone-chain convex hull; returns hull vertices CCW., Minimum-area oriented bounding rectangle of a ring (rotating calipers).      Ret, Smallest squared distance between any point of a and any point of b., Recover oriented columns from clipped/fragmented outlines.      Revit's CAD impo (+2 more)

### Community 66 - "Community 66"
Cohesion: 0.19
Nodes (4): CircularRecovery, OrientedRecovery, _ring(), _short_long()

### Community 67 - "Community 67"
Cohesion: 0.30
Nodes (6): ClippedSizeSnap, _Lbl, Ownership, A label's size is authoritative: a clipped column is resized up to it, but an, _rect(), _run()

### Community 68 - "Community 68"
Cohesion: 0.21
Nodes (13): filter_columns(), get_element_location_point(), get_selected_elements(), main(), Retrieve currently selected elements from the active document., Fail-Fast: Filter the selection to strictly Structural and Architectural columns, Safely extract the XYZ location of an element, handling slanted columns., Sort columns predictably by Y coordinate, then X coordinate. (+5 more)

### Community 69 - "Community 69"
Cohesion: 0.21
Nodes (11): get_app(), get_current_doc(), get_current_uidoc(), Return the active Revit UIApplication (``__revit__``)., Return the active UIDocument, or raise RuntimeError if none is open., get_selected_elements(), Return the currently selected elements as a Python list.      Returns an empty l, Highlight *element_ids* in the active Revit UI.      Args:         element_ids ( (+3 more)

### Community 70 - "Community 70"
Cohesion: 0.20
Nodes (13): clean_ft(), ft_to_mm(), m_to_ft(), m_to_mm(), mm_to_ft(), _normalise_unit(), Convert metres to millimetres (rounded to nearest integer)., Convert millimetres to decimal feet. (+5 more)

### Community 71 - "Community 71"
Cohesion: 0.18
Nodes (13): _close(), _collinear(), _dedup(), is_rectilinear(), parse_column_polyline(), Recover columns from fused/unclosed axis-aligned wall outlines.      Assembles `, Project (x, y, z) tuples to 2D (x, y), returning (xy_list, z)., Return a closed ring as a vertex list with duplicates/collinear removed.      In (+5 more)

### Community 72 - "Community 72"
Cohesion: 0.18
Nodes (13): _body_coverage(), _carrier_index(), _circle_wrap_arcs(), _cluster_nodes(), _faces_from_edge_graph(), _point_in_ring(), Shared face machinery: heal -> split -> cluster -> prune -> walk -> filter., Precomputed spatial lookup for the exactness pass (shared per source run). (+5 more)

### Community 73 - "Community 73"
Cohesion: 0.18
Nodes (8): _bracket_int(), DebounceTimer, load_xaml_window(), PreviewItem, Parse a leading '[<int>]' prefix to an int (else None). Replaces     re.match —, One row in the live preview DataGrid. __slots__ is required for     Python.NET 3, Read ui.xaml — fully self-contained inline theme, no runtime injection needed., run_ui()

### Community 74 - "Community 74"
Cohesion: 0.39
Nodes (4): BeamEndSnap, _circle(), _rect(), _seg()

### Community 75 - "Community 75"
Cohesion: 0.20
Nodes (11): build_diff_summary(), compare_revisions(), load_previous_revision(), load_previous_revision_from_sidecar(), Loads a .bbs_rev sidecar directly by path., Returns count summary of each change type., Saves a JSON sidecar next to the xlsx.     records: list of BarRecord, Loads previous revision sidecar.     Returns None if not found. (+3 more)

### Community 77 - "Community 77"
Cohesion: 0.17
Nodes (4): _ns(), Create a simple namespace mock that also supports attribute access via __getitem, _register_mocks(), _Transaction

### Community 78 - "Community 78"
Cohesion: 0.22
Nodes (10): apply_mapping(), build_default_mapping(), build_default_text_mapping(), classify_layer(), classify_text_layer(), Pre-fill {text_layer: text_category} from the convention for the dialog., Return a category for one layer.      Precedence: explicit override > exclusion, Pre-fill {layer_key: category} from the convention for the override dialog. (+2 more)

### Community 79 - "Community 79"
Cohesion: 0.18
Nodes (6): bounding_rectangle(), An axis-aligned rectangle in feet (centre + size), with mm convenience., Recover a fragmented lift/stair core's columns by pairing opposing faces.      A, Axis-aligned bounding Rectangle of a ring (used as a non-rectilinear fallback)., recover_core_walls(), Rectangle

### Community 80 - "Community 80"
Cohesion: 0.18
Nodes (4): DxfReadResult, One text entity read from the DXF (TEXT / MTEXT / block ATTRIB).      The Revit, Geometry + text extracted from a DXF file by the ezdxf reader.      `records` ar, TextRecord

### Community 81 - "Community 81"
Cohesion: 0.44
Nodes (10): _arc_points(), _circle_points(), _flatten(), _geometry_record(), _lwpolyline_points(), _polyline_points(), [start, mid, end] of an ARC in WCS (matches the Revit reader's convention)., Normalise an ezdxf Vec3 / tuple to a plain (x, y, z) float tuple. (+2 more)

### Community 82 - "Community 82"
Cohesion: 0.27
Nodes (11): _add_text(), _insert_point(), _layer(), Explode a block reference: nested geometry (WCS) + its ATTRIB tag text., Text rotation in degrees (0 = horizontal); best-effort, defaults to 0.      MTEX, Best text anchor: insertion point, falling back to alignment point., Process an entity container, recursing one level into block INSERTs., _read_insert() (+3 more)

### Community 83 - "Community 83"
Cohesion: 0.22
Nodes (7): BarVM, DiaVM, _get_all_rebar_params(), open_param_editor(), Extracts all parameter names from a sample rebar in the model., Opens the Parameter Editor Popup., run_ui()

### Community 84 - "Community 84"
Cohesion: 0.22
Nodes (5): box(), poly(), Closed rectangle centred at (cx, cy), width b (x) x height h (y)., Closed rectangle rotated deg degrees about its centre., rotated_box()

### Community 85 - "Community 85"
Cohesion: 0.27
Nodes (10): Dispatching Parallel Agents, Executing Plans, Finishing a Development Branch, /graphify (knowledge graph pipeline), Code Review Reception, Requesting Code Review, Subagent-Driven Development, Systematic Debugging (root-cause-first) (+2 more)

### Community 86 - "Community 86"
Cohesion: 0.20
Nodes (4): Replace all occurrences of *find* in *text* (case-sensitive).      Returns:, Replace all occurrences of *find* in *text* (case-insensitive), without     usin, replace_case_insensitive(), replace_case_sensitive()

### Community 87 - "Community 87"
Cohesion: 0.22
Nodes (6): build_circular_columns(), Circle, circle_from_three_points(), A circular column footprint: centre + diameter, in feet., Exact circumcircle (cx, cy, r) of three 2D points, or None if collinear., Recover circular columns from arc records on the column layer.      Each arc sto

### Community 88 - "Community 88"
Cohesion: 0.22
Nodes (9): decompose_to_rectangles(), _extend_columns(), _extend_rows(), _point_in_polygon(), Ray-casting test; ring is a list of (x, y) with no closing duplicate., Greedily extend a run rightward along row r; return the last column index., Greedily extend the [c..c_end] band upward; return the last row index., Partition a rectilinear ring into axis-aligned Rectangles (exact cover).      Ca (+1 more)

### Community 89 - "Community 89"
Cohesion: 0.25
Nodes (9): _heal_endpoints(), _line_intersection(), _param_along(), (grid, boxes): cell -> segment indices whose padded bbox covers the cell., Extend each segment endpoint (up to heal_ft) to the nearest carrier crossing., Split segments where they cross or touch: X crossings AND T-junctions.      A T-, ((x, y), t, u) where the two segments' carrier LINES meet, or None if parallel., _seg_grid() (+1 more)

### Community 91 - "Community 91"
Cohesion: 0.25
Nodes (4): IFailuresPreprocessor that silently discards all warnings so they never     surf, Context manager for a single Revit Transaction.      Commits on clean exit; roll, RevitTransaction, SuppressWarningsPreprocessor

### Community 92 - "Community 92"
Cohesion: 0.39
Nodes (7): diff(), format_console(), _length_mm(), _midpoint(), _per_layer(), Short console lines summarising the comparison., Return a structured comparison of the two geometry sets (internal feet).      Ma

### Community 93 - "Community 93"
Cohesion: 0.25
Nodes (8): assemble_rectilinear_rings(), _bbox_shell_ring(), _edges_of(), 2D edges of a point path. Returns (edges, all_axis_aligned)., Walk a simple cycle (all vertices degree 2) from start; return (ring, pids)., Close a partial rectangle outline to its bounding box, or return None.      `edg, Stitch open, axis-aligned fragments into closed rectilinear rings.      Revit's, _walk_cycle()

### Community 94 - "Community 94"
Cohesion: 0.29
Nodes (8): _aabb_overlaps(), _bbox_half(), _center_inside_larger(), True when rect's centre sits INSIDE a strictly larger placed rectangle.      A r, Axis-aligned half-extents (hx, hy) in feet of a possibly-rotated column rect., True if the box with half-extents (hx, hy) at (cx, cy) overlaps any rect., Place a labelled column that geometry recovery ABSORBED into a larger neighbour., recover_unplaced_labeled_columns()

### Community 95 - "Community 95"
Cohesion: 0.25
Nodes (8): build_category_counts(), build_layer_counts(), format_console(), format_summary(), {layer_key: {'count': int, 'kinds': {kind: int}}} for the summary table., {category: count}, including unmapped, so nothing is silently dropped., Return a list of plain-text lines describing the read (no markup)., Short, copy-friendly console summary. Full detail goes into the JSON.

### Community 96 - "Community 96"
Cohesion: 0.25
Nodes (8): _collinear_continuation(), _continuation_beams(), _extend_segment_over(), _pair_has_beam_edge(), Recover the far piece of a beam interrupted by a crossing member, label-free., Stretch `existing` along its own axis so its span also covers `seg`'s., True if one of the pair's two edges lies along a BEAM-layer line.      An edge s, True when candidate `seg` continues `existing` along the SAME centreline.      P

### Community 97 - "Community 97"
Cohesion: 0.25
Nodes (3): _DispatcherTimer, _EventSlot, Supports `timer.Tick += handler` and `timer.Tick -= handler` idioms.

### Community 98 - "Community 98"
Cohesion: 0.38
Nodes (6): Toggles visibility of Revit links on current view., Check if a view template controls RVT Links visibility., Set the RVT Links V/G parameter as not controlled by template., release_links_from_template(), template_controls_links(), toggle_links()

### Community 99 - "Community 99"
Cohesion: 0.29
Nodes (3): CurveRecord, One extracted curve from a linked CAD., Stable dictionary key, collapsing a missing layer to NO_LAYER.

### Community 100 - "Community 100"
Cohesion: 0.33
Nodes (6): _choices(), link_dxf(), [(label, enum_value)] for the enum members that exist on this Revit version., Link `path` into doc with the chosen unit + placement; return ImportInstance., Normalise Document.Link's return across engines.      pythonnet (CPython3) retur, _unpack_out()

### Community 101 - "Community 101"
Cohesion: 0.38
Nodes (6): export_pdf(), _export_via_com(), _export_via_fpdf2(), Exports xlsx to PDF. Returns (success, message, pdf_path|None).     Tries COM fi, Export via Excel COM Interop (.NET). Requires Excel installed., Export via fpdf2 — pure Python fallback.     Reads the BBS sheet from the xlsx a

### Community 102 - "Community 102"
Cohesion: 0.38
Nodes (6): get_parameter(), get_parameter_value(), Return the Parameter named *param_name* from *element*.      Checks the element, Return the value of *param_name* on *element*.      For ElementId parameters the, Set *param_name* on *element* to *value*.      Returns ``False`` if the paramete, set_parameter_value()

### Community 103 - "Community 103"
Cohesion: 0.29
Nodes (6): bend_deduction_per_bend(), bend_diameter_mm(), cutting_length_formula(), Returns a multi-line formula string for the Calculation Sheet.     phi = bar dia, Returns minimum mandrel/bend diameter in mm.     Links/stirrups (is_link=True):, Deduction = multiplier * phi per individual bend.

### Community 105 - "Community 105"
Cohesion: 0.33
Nodes (6): build_line_spines(), _consistent_edge(), _near_edges(), Turn bare lines on the column layer into spine Rectangles.      A line becomes a, Collect leg edges (perpendicular coord) that lie within the gap band and     ove, Return the leg-edge coordinate shared by >= 2 legs nearest the line, else None.

### Community 106 - "Community 106"
Cohesion: 0.33
Nodes (3): The full outcome of reading one linked CAD., Distinct layer keys present, sorted for stable display., ReadResult

### Community 107 - "Community 107"
Cohesion: 0.33
Nodes (6): _arc_span(), _curved_beams_from_edges(), _curved_segment(), Pair concentric inner/outer edges into curved beam segments.      Two edges shar, (start_deg, end_deg) of the populated arc, sweeping CCW across the LARGEST gap., A placeable curved beam: centre, centreline radius, swept angle, width (mm/ft).

### Community 108 - "Community 108"
Cohesion: 0.47
Nodes (3): main(), records_from_raw(), T

### Community 110 - "Community 110"
Cohesion: 0.33
Nodes (6): Instruction Priority (user > skills > system), Skill Priority (process before implementation), Using Superpowers / Using Skills, Match the Form to the Failure, Skill Discovery Optimization (SDO), Writing Skills

### Community 113 - "Community 113"
Cohesion: 0.50
Nodes (5): Half-Filled Circle Glyph, RVT Links Toggle Icon (Dark Theme Variant), pyRevit Dark UI Theme, RVTLinked Pushbutton (Toggle Revit Links Visibility), Visibility Toggle Concept

### Community 114 - "Community 114"
Cohesion: 0.40
Nodes (5): _ensure_ezdxf(), ezdxf_available(), Import ezdxf on demand; cache the module once it succeeds. Returns bool., Read one DXF into a DxfReadResult(records, texts), in DXF coordinates.      Fail, read_dxf()

### Community 116 - "Community 116"
Cohesion: 0.40
Nodes (5): Brainstorming Ideas Into Designs, /plan command (init planning files), Planning with Files (disk-as-working-memory), /status command (read task_plan.md), test command (brainstorm-mode stub)

### Community 117 - "Community 117"
Cohesion: 0.40
Nodes (5): Iron Law: No Completion Claims Without Fresh Verification Evidence, Verification Before Completion, Writing Plans, RED-GREEN-REFACTOR for Skills, Writing Skills IS TDD for Process Documentation

### Community 119 - "Community 119"
Cohesion: 0.40
Nodes (4): create_element_id(), get_element_id_value(), Create an ElementId from an integer, handling the Int32→Int64 change in     Revi, Extract the integer value from an ElementId, handling the .Value / .IntegerValue

### Community 120 - "Community 120"
Cohesion: 0.40
Nodes (4): get_family_name(), get_type_name(), Return the Family Name of *element*.      Resolution order:       1. FamilyInsta, Return the Type Name of *element*, or ``"N/A"`` if it cannot be resolved.

### Community 121 - "Community 121"
Cohesion: 0.40
Nodes (4): bounding_boxes_overlap(), get_solid_volume_m3(), Return the total net solid volume of *element* in cubic metres.      Iterates th, Return ``True`` if two BoundingBoxXYZ objects overlap in 3-D space.      Args:

### Community 123 - "Community 123"
Cohesion: 0.40
Nodes (4): get_eligible_views(), get_view_label(), Return ``"<view name> [<type label>]"`` for a given View., Return a name-sorted list of non-template views of allowed types.      Args:

### Community 127 - "Community 127"
Cohesion: 0.50
Nodes (4): _apply_curved_marks(), _nearest_sized_label(), Size each curved beam from the nearest beam label to its mid-arc point.      Dep, Nearest (text, small, big) within radius_ft of (cx, cy), or None.

### Community 129 - "Community 129"
Cohesion: 0.67
Nodes (3): main(), Shows a pyRevit alert dialog., show_alert()

### Community 131 - "Community 131"
Cohesion: 0.67
Nodes (3): ExcelComWriter, get_rebars, BBS Generator Tool

## Knowledge Gaps
- **118 isolated node(s):** `_Visibility`, `_Dispatcher`, `_UriKind`, `_Solid`, `_FillPatternElement` (+113 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Rectangle` connect `Community 79` to `Community 64`, `Community 105`, `Community 88`, `Beam Sizing & Marks Tests`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Why does `Circle` connect `Community 87` to `Community 64`, `Beam Sizing & Marks Tests`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `OrientedRect` connect `Community 65` to `Community 64`, `Beam Sizing & Marks Tests`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **What connects `Parse a leading '[<int>]' prefix to an int (else None). Replaces     re.match —`, `One row in the live preview DataGrid. __slots__ is required for     Python.NET 3`, `Read ui.xaml — fully self-contained inline theme, no runtime injection needed.` to the rest of the system?**
  _598 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `CAD-to-BIM Dialog Window` be split into smaller, more focused modules?**
  _Cohesion score 0.05153153153153153 - nodes in this community are weakly interconnected._
- **Should `BIM Generation Helpers` be split into smaller, more focused modules?**
  _Cohesion score 0.051923076923076926 - nodes in this community are weakly interconnected._
- **Should `CAD-to-BIM Dialog XAML` be split into smaller, more focused modules?**
  _Cohesion score 0.05902980713033314 - nodes in this community are weakly interconnected._
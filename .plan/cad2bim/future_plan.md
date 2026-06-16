# CAD to BIM — Future Plan & Roadmap

## Overview

This document outlines the planned development roadmap for the CAD to BIM tool beyond the current `v0.12.0` release. Priorities are organized by development phase.

---

## Phase 1: Core Stability & Testing (Next)

### 1.1 Unit Tests for `shapes.py`

**Priority:** High
**Effort:** Medium
**Why:** `shapes.py` is the mathematical core of the tool (450+ lines) and is already Revit-free — perfectly set up for unit testing outside Revit.

**Tasks:**
- [ ] Set up Python `unittest` or `pytest` test suite under `tests/`
- [ ] Test `simplify_ring()` with collinear, duplicate, and degenerate inputs
- [ ] Test `is_rectilinear()` with axis-aligned, rotated, and mixed rings
- [ ] Test `decompose_to_rectangles()` with L, C, U, E, T, and plain rectangle shapes
- [ ] Test `min_area_rect()` with rotated rectangles at various angles
- [ ] Test `parse_column_polyline()` with all status outputs (rectangle, composite, oriented_rect, degenerate)
- [ ] Test `build_circular_columns()` with single arcs, multi-segment circles, and noise
- [ ] Test `beam_centerline_from_quad()` with axis-aligned and rotated quads
- [ ] Test `pair_parallel_lines()` with parallel, non-parallel, and multi-line scenarios
- [ ] Test `snap_to_standard()` with exact matches, near misses, and no standards
- [ ] Test `circle_from_three_points()` with collinear (should return None) and valid inputs
- [ ] Add CI via GitHub Actions to run tests on push

### 1.2 Layer Convention Tuning

**Priority:** High
**Effort:** Low
**Why:** Default regex patterns are placeholders. Real CAD sources use varied layer naming standards.

**Tasks:**
- [ ] Collect sample CAD layer names from real structural DWGs
- [ ] Update `DEFAULT_CONVENTION` patterns in `layers.py`
- [ ] Update `EXCLUSION_PATTERNS` for annotation/identification layers
- [ ] Consider configurable layer mapping via external YAML/JSON file

### 1.3 Error Handling & Edge Case Hardening

**Priority:** Medium
**Effort:** Medium

**Tasks:**
- [ ] Add robust handling for DWGs with no geometry (graceful exit, not crash)
- [ ] Handle extremely large DWGs with progress reporting
- [ ] Improve error messages for failed family type resolution
- [ ] Handle Revit warnings that may fire despite `WarningSwallower`
- [ ] Add logging for parameter name fallback attempts (debug level)

---

## Phase 2: Feature Completion (Near-term)

### 2.1 Slab Edge Creation Pass

**Priority:** High
**Effort:** Medium
**Dependencies:** Requires understanding of slab edge creation API

**Tasks:**
- [ ] Create `slabs.py` module in `cad2bim`
- [ ] Implement slab edge creation from `CATEGORY_SLAB_EDGE` classified curves
- [ ] Wire slab pass into `script.py` main orchestration
- [ ] Add slab level selection to WPF dialog
- [ ] Re-enable `chk_slabs` checkbox in `ui.xaml`
- [ ] Add slab outcomes to report + JSON export
- [ ] Test with slab-edge layer data

### 2.2 Curved Beam Placement

**Priority:** Medium
**Effort:** Medium
**Dependencies:** Arc pair detection already implemented in `report.py` → `build_beam_segments()`

**Tasks:**
- [ ] Create `beams.place_curved_beams()` function
- [ ] Accept concentric arc pairs as input (start/end radii, subtended angle)
- [ ] Create structural framing instance along arc centerline
- [ ] Wire curved beam placement into `script.py` after straight beams
- [ ] Add curved beam outcomes to report + JSON export
- [ ] Remove "placement to follow" note from `build_beam_segments()`

### 2.3 Text-Based Grid Labels

**Priority:** Medium
**Effort:** High
**Why:** Currently grids are named by positional convention (A,B,C / 1,2,3). Real grid labels from DWG text would be far more useful.

**Approach considerations:**
- Revit geometry API (`get_Geometry()`) does NOT expose TextNote elements
- Alternative approach: Use `FilteredElementCollector` for embedded text elements in the linked CAD
- Alternative approach: Pre-process the DWG using `ezdxf` (external, CPython) to extract text + coordinates, then pass labels via JSON import
- Alternative approach: Accept text coordinate data as an additional file during the dialog

**Tasks:**
- [ ] Research feasibility of DWG text extraction via Revit API
- [ ] Fallback: Plan external text-extraction step
- [ ] Implement label override mechanism in `GridNamer`
- [ ] Add text-label mapping UI to the dialog (or accept as JSON)

---

## Phase 3: External Validator (Mid-term)

### 3.1 JSON Export → CPython + ezdxf Validator

**Priority:** Medium
**Effort:** High
**Why:** The JSON export was explicitly designed as the contract for this validator. It will allow offline validation of the extracted geometry against the original DWG.

**Architecture:**
```
[Revit + IronPython 2.7]                     [External CPython 3.x]
  CAD to BIM tool                                  validator.py
       │                                                ▲
       ▼                                                │
  export_json(path) ──────────────────►  read JSON + DWG
  (cad2bim v0.12+)                      compare curves
                                         report discrepancies
```

**Tasks:**
- [ ] Create `tools/validator/` directory
- [ ] Implement `validator.py` using `ezdxf` library
- [ ] Read JSON export + original DWG file
- [ ] Match curves by layer, category, and position
- [ ] Report: curves in JSON but missing in DWG (and vice versa)
- [ ] Report: geometric discrepancies (position, length, curvature)
- [ ] Add CLI interface with pass/fail summary
- [ ] Add configuration via YAML

---

## Phase 4: Enhancement & Polish (Long-term)

### 4.1 Performance Optimization

- [ ] Profile shape decomposition on large DWGs (5000+ curves)
- [ ] Optimize `decompose_to_rectangles()` grid scan for large shapes
- [ ] Add incremental progress reporting during reading pass
- [ ] Consider caching layer mappings per document session

### 4.2 Family Parameter Name Configuration

- [ ] Make parameter name fallbacks configurable via YAML file
- [ ] Allow per-project parameter name mapping
- [ ] Add diagnostic output showing which parameter name was matched

### 4.3 Undo Support

- [ ] Each creation pass already uses `TransactionGroup` with `Assimilate()`
- [ ] Consider grouping ALL passes into a single undo step (current: one per pass)
- [ ] Add cancel-with-undo on any single-pass failure

### 4.4 UI Improvements

- [ ] Add search/filter to layer mapping list (for large DWGs with many layers)
- [ ] Show estimated element counts before running (grids: X, columns: Y, beams: Z)
- [ ] Add option to save/reload layer mapping presets
- [ ] Add dark theme toggle (AnonGee brand supports both)
- [ ] Show preview of decomposed shapes (simplified plan view)

### 4.5 Multi-Language Support

- [ ] Externalize strings to YAML resource files
- [ ] Add English as default
- [ ] Prepare for additional language support

### 4.6 User Documentation

- [ ] Write user guide with screenshots
- [ ] Document the layer naming convention with examples
- [ ] Create troubleshooting guide for common CAD issues
- [ ] Record video walkthrough of the full workflow

---

## Release Roadmap

| Version | Target | Major Features |
|---------|--------|---------------|
| `v0.12.x` | Current | Core pipeline, WPF dialog, grids/columns/beams |
| `v0.13.0` | Q3 2026 | Unit tests for shapes, layer convention tuning |
| `v0.14.0` | Q3 2026 | Slab edge creation pass |
| `v0.15.0` | Q4 2026 | Curved beam placement |
| `v0.16.0` | Q4 2026 | Grid label text extraction |
| `v1.0.0` | Q1 2027 | External validator, all core features stable |
| `v1.1.0` | Q2 2027 | Performance, UI polish, documentation |

---

## Backlog (Ideas for Future Consideration)

- **Multi-CAD batch processing** — Run the tool across multiple linked DWGs in one session
- **Column offset detection** — Detect and apply column offsets from grid lines
- **Auto-detection of grid bubble layer** — Separate grid lines from grid annotation
- **Beam system creation** — Create Revit Beam Systems instead of individual beams
- **Foundation placement** — Extend column drops to foundation footings
- **Structural wall detection** — Identify and create walls from thick outlines on column/beam layers
- **Reinforcement detection** — Read rebar schedules from DWG tables (requires text reading)
- **Round-trip with Revit** — Export modified layout back to DWG for consultant coordination

---

## How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make changes following existing code conventions:
   - IronPython 2.7 compatible (no dataclasses, no type hints)
   - Revit API imported at call time, not module level
   - Functions documented with docstrings
4. Run tests for `shapes.py` (if applicable)
5. Submit a pull request

**Priority areas for contribution:**
- Testing on real CAD files and reporting layer name patterns
- Unit tests for `shapes.py`
- Slab edge creation module
- Curved beam placement
- External `ezdxf` validator

---

*Last updated: 2026-06-16*
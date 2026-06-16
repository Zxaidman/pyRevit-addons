# CAD to BIM — Progress Report

## Project Status: **ALPHA — Core Pipeline Complete**

> Current version: `cad2bim v0.12.0`
> Last updated: 2026-06-16

---

## Milestone Summary

| Milestone | Status | Notes |
|-----------|--------|-------|
| M1 — Geometry reader | ✅ Complete | Extracts lines, arcs, polylines from linked CAD; project-coordinate transform handled |
| M2 — Layer classification | ✅ Complete | Convention-based + override dialog; exclusion patterns for annotation layers |
| M3 — Column shape decomposition | ✅ Complete | Rectilinear L/C/U/E → rectangles; oriented rect for rotated; circle from arcs |
| M4 — Beam derivation | ✅ Complete | 3 sources: closed outlines, parallel line pairs, arc pairs for curved beams |
| M5 — Grid creation | ✅ Complete | Convention naming A,B,C / 1,2,3; batch creation with duplicate avoidance |
| M6 — Column placement | ✅ Complete | Rectangular + circular; per-size type duplication + caching; rotation for landscape |
| M7 — Beam placement | ✅ Complete | Per-width type duplication; centerline placement at level elevation |
| M8 — WPF Dialog UI | ✅ Complete | AnonGee-branded theme; layer mapping; build options; sizing limits with sliders |
| M9 — JSON export | ✅ Complete | Intermediate JSON with full report; contract for external validator |
| M10 — Warning suppression | ✅ Complete | WarningSwallower via IFailuresPreprocessor; modal-free batch creation |
| M11 — Unit tests for shapes | ⬜ Planned | `shapes.py` is Revit-free and designed for unit testing |
| M12 — External validator | ⬜ Planned | CPython + ezdxf checker consuming the JSON export |
| M13 — Slab creation | ⬜ Planned | UI checkbox exists but disabled ("coming soon") |
| M14 — Curved beam placement | ⬜ Planned | Arc pairs detected + reviewed but not placed |
| M15 — Text-based grid labels | ⬜ Planned | Currently positional convention; real labels from DWG text needed |

---

## Module Completion

### Pushbutton Layer

| Component | Lines (approx) | Completion | Notes |
|-----------|---------------|------------|-------|
| `script.py` | ~250 | 95% | Main orchestration; slab pass not yet wired |
| `ui.xaml` | ~350 | 100% | Theme complete; all controls functional |
| `bundle.yaml` | ~15 | 100% | Metadata set |

### `cad2bim` Library Layer

| Module | Lines (approx) | Completion | Stability | Notes |
|--------|---------------|------------|-----------|-------|
| `__init__.py` | ~30 | 100% | Stable | Version + doc |
| `model.py` | ~70 | 100% | Stable | Data holders |
| `units.py` | ~30 | 100% | Stable | mm ↔ feet |
| `compat.py` | ~50 | 100% | Stable | Revit version shims |
| `cad_links.py` | ~50 | 100% | Stable | Link finder |
| `geometry_reader.py` | ~140 | 95% | Stable | Edge cases handled |
| `layers.py` | ~80 | 90% | Stable | Convention may need tuning per real DWG |
| `shapes.py` | ~450 | 85% | Core stable | Line-spine & circle detection tested; more edge cases likely in production |
| `report.py` | ~280 | 85% | Stable | Filtering/snapping logic works; arc-beam placement not yet wired |
| `grids.py` | ~120 | 90% | Stable | Namer works; text-reader upgrade path clear |
| `columns.py` | ~150 | 90% | Stable | Rect + circular placement; b/h param name fallbacks may need tuning |
| `beams.py` | ~100 | 90% | Stable | Width param name fallbacks; placement works |
| `transactions.py` | ~30 | 100% | Stable | Warning swallower |
| `ui.py` | ~80 | 100% | Stable | Secondary path (not used in main WPF flow) |

---

## Key Metrics (Estimated)

| Metric | Value |
|--------|-------|
| Total source files | 15 (1 pushbutton + 14 lib modules) |
| Total code (approx) | ~2,000 lines |
| Revit dependencies | `Autodesk.Revit.DB` (imported at call time, not package-import) |
| Python version target | IronPython 2.7 (pyRevit) + CPython 3.x (external validator) |
| Min Revit version | 2022 |
| Test coverage | Manual only; no automated test suite yet |

---

## Known Issues & Risks

1. **Layer convention tuning** — The default regex patterns are educated guesses. Real CAD files from different consultants may need pattern adjustments in `layers.py`.
2. **Param name fallbacks** — Column b/h and beam width parameter names vary across families. The current fallback lists may miss some conventions.
3. **Edge cases in shape decomposition** — Highly irregular column outlines (non-rectilinear, non-rectangular) are approximated with oriented bounding boxes. Review may be needed.
4. **Curved beam placement** — Detected but not placed. Concentric arc pairs are surfaced in the report review section.
5. **Slab edge creation** — `slab_edge` category is classified but no creation pass exists.
6. **No automated tests** — `shapes.py` was designed for unit testing but no test suite exists yet.
7. **Grid label text** — DWG text entities are not read by the geometry API. Labels follow positional convention (A,B,C / 1,2,3).
8. **Memory pressure** — Large DWGs with thousands of curves may impact Revit session performance during the reading pass.
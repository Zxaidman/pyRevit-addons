# Column stress-test fixture

`stress_columns.dxf` is a synthetic structural plan (mm, on a labelled 8×6 grid)
that exercises every column-detection path in the cad2bim pipeline in one file.
Link it into Revit (or read it with `dxf_reader`) and run **CAD to BIM** to
confirm columns survive. Regenerate with:

```
python3 generate_stress_columns_dxf.py      # needs ezdxf
```

## Regions and expected columns

| Grid area | What it tests | Expected column(s) |
|-----------|---------------|--------------------|
| 1–3 / A   | plain closed rectangles | 400×400, 300×900, 900×300 |
| 4 / A     | rotated rectangle (`oriented_rect`) | 600×900 @ 30° |
| 5 / A     | composite lift-core (`decompose`) | L → 1500×900 + 600×600 |
| 6 / A     | round column (arc/circle) | Ø700 |
| 1 / B     | junction-fragmented **rotated** column (oriented recovery) | 600×800 @ 25° |
| 3–5 / B   | **fused comb**: long wall + 3 legs (rectilinear assembly) | 6000×300 wall + 3× 300×2400 legs |
| 7 / E     | **clipped wall, end cap missing** (bbox-shell completion) | 4500×300 |
| 1–2 / E   | mark-only columns + schedule table | C9 → 500×500, C10 → 650×650 |

The last three rows are the regression-critical paths added while hardening
Test10 (fragmented junctions, fused wall+leg combs, and clipped walls). The
schedule block is laid out Test15-style (Mark | W | L | H, one MTEXT per cell)
so the schedule parser is exercised too.

## stress_columns_adversarial.dxf

A harder plan (regenerate with `generate_stress_columns_adversarial.py`) for the
messy real-world cases:

| Region | What it tests |
|--------|---------------|
| `S-NOTES` block | column + beam + slab schedules **stacked on one layer** with different x-layouts — each must be read as an independent table (a beam's `D` column must not be read as a column's length) |
| 12/B–D | column **outline and size/mark text on the same layer** (`S-COLS`) |
| 12/E–F | **irregular** triangle / trapezoid columns (vs. an L control) |

The schedule-isolation behaviour is locked by `test_schedule_parsing.py`.

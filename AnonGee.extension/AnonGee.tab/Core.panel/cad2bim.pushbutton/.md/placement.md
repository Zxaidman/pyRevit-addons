# Install / Replace — CAD to BIM (cad2bim v0.9.0)

This is the complete, versioned package. Replace your working copy wholesale to
avoid stale or duplicate modules.

## 1. Package contents

```
AnonGee.extension/
├── lib/
│   └── cad2bim/                      v0.9.0  (put under lib/py2/ — see step 2)
│       ├── __init__.py   (carries __version__ = "0.9.0")
│       ├── units.py  compat.py  model.py
│       ├── cad_links.py  geometry_reader.py
│       ├── shapes.py  layers.py
│       ├── ui.py  report.py
│       ├── transactions.py  grids.py  columns.py  beams.py
└── AnonGee.tab/
    └── Core.panel/
        └── CAD to BIM.pushbutton/
            ├── bundle.yaml
            ├── script.py
            ├── ui.xaml          (WPF main window, AnonGee theme)
            └── icon.README.txt   (add your icon.png here)
```

## 2. Where it goes in your repo

- `cad2bim/`  ->  `AnonGee.extension/lib/py2/cad2bim/`   (your IronPython convention)
- pushbutton files  ->  the existing `AnonGee.tab/Core.panel/CAD to BIM.pushbutton/`

`script.py` calls `path_resolver.update_paths()` first, which puts `lib/py2` on
sys.path so `import cad2bim` resolves there.

## 3. IMPORTANT — remove stale / shadowing copies first

The `AttributeError: ... has no attribute 'build_column_sections'` is caused by an
OLD `cad2bim` being imported instead of this one. Before installing:

1. DELETE any `cad2bim` folder at `lib/` root (i.e. `lib/cad2bim/`). pyRevit puts
   `lib/` on sys.path, so a copy there hijacks the import ahead of
   `lib/py2/cad2bim`. There must be exactly ONE `cad2bim`, under `lib/py2/`.
2. Delete the old `lib/py2/cad2bim/` and REPLACE it with this one (don't merge —
   replace, so no removed file lingers).
3. Delete any `*.pyc` / `__pycache__` under `cad2bim`.

## 4. Reload

pyRevit does NOT auto-reload `lib/` modules — they are cached per Revit session.
After copying, run `pyrevit reload`, or restart Revit, so the new modules load.
(Editing only `script.py` is picked up without a reload; editing any `cad2bim/*.py`
module requires a reload.)

## 5. Verify the right version loaded

On run, the output window's first line is:

    cad2bim 0.9.0 loaded from D:\...\AnonGee.extension\lib\py2\cad2bim

- If the VERSION is not `0.4.0`, an old copy is still being imported.
- If the PATH is not `...\lib\py2\cad2bim`, a shadow copy elsewhere won.

Fix the path/version before trusting the rest of the run.

## 6. Expected run (Level-1 style DWG)

1. Pick the linked DWG (if several).
2. Optionally adjust the layer mapping.
3. Output shows: per-layer/category summary, then a Column sections block
   (e.g. composite 1, line_member 2, non_rectilinear 1, rectangle 54), the
   lift-core split (2 x 300x3300), and line-drawn members (12300 mm, 3000 mm).
4. Prompt to create grids -> creates A–H x 1–8 from the 16 S-GRID lines.
5. Prompt to export JSON.

## 7. Notes
- Embedded (imported, not linked) DWGs are ignored; only links are read.
- Coordinates are read in internal feet and never rescaled.
- Grids are the only elements created in this build; columns/beams/slabs follow.
- DWG grid-label text isn't exposed by the Revit geometry API, so grid names are
  convention-based (A–H x 1–8) for now.

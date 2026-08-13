# Auto Level Manager — changelog

Versioned with [semantic versioning](https://semver.org), read from the point
of view of someone using the tool:

| Part      | Means                                                                                                                              |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **MAJOR** | The tool behaves differently on purpose — a workflow moved, a default now creates something it did not before, or what **Apply changes** writes to the model changed shape. Read the notes before upgrading. |
| **MINOR** | A new capability. Everything you already did still works the same way.                                                             |
| **PATCH** | A fix. Nothing new to learn.                                                                                                       |

The version in `anongee_autolevel/__init__.py` is the single source of truth.
`bundle.yaml`, the badge in the window header and the newest heading below are
checked against it by `tests/test_autolevel_ui.py`, so they cannot drift apart.
The version shown in the window header is the build you are actually running —
quote it when reporting anything.

---

## 1.1.1

**Fixed**

- The window would not open at all: `XamlParseException: 'Unexpected token
  after end of markup extension.'` at load. The Generate tab's template
  tooltip listed the naming tokens starting with `{n}`, and XAML reads any
  attribute value beginning with `{` as a markup extension — so it parsed
  `{n}` as one and choked on the rest of the sentence. Escaped with a leading
  `{}`. This made 1.1.0 unusable; upgrade straight past it.

**Added**

- The version now shows in the window header, so the build you are running is
  never in doubt.
- Two static checks that would have caught the above without opening Revit:
  every attribute value that starts with `{` must be a real markup extension
  or be escaped, and every `{StaticResource}` must name a key that exists.
  Both failures are invisible to an XML parser and both kill the window.

## 1.1.0

> Broken — the window does not open. Superseded by 1.1.1.

**Added**

- **Guidance throughout**, after the first round of testing reported that too
  much was going on to know where to start:
  - a tooltip on every interactive control;
  - tabs numbered `1 · Detect` … `4 · Views`, because they are a sequence;
  - a hint strip under the tabs saying what the current tab is for;
  - a line above the table saying what to do *next*, worked out from the state
    of the plan (nothing scanned / changes staged / an error in the way);
  - a **Guide** tab with the whole tool on one page.
- **Zoom and pan on the stack drawing.** Wheel zooms on the cursor, Shift+wheel
  pans, dragging empty space pans, and `–` / `+` / `Fit` sit under the canvas.
  Panning is clamped so the view cannot leave the building.
- **The drawing is now an editor.** Click a level to select it, drag it to
  change its elevation — snapped to a step you choose, Shift for none, obeying
  the push-levels-above switch — and double-click to rename it.
- Crowded stacks drop names rather than overprinting them, and the hint says
  how many were hidden and that zooming separates them.

**Changed**

- The stack drawing's camera moved to `anongee_autolevel/stackview.py`: pure
  arithmetic, no Revit and no WPF, so the property that matters (zooming leaves
  the elevation under the cursor exactly under the cursor) is under test.

## 1.0.0

First release.

**Added**

- One modeless window for level work — Revit stays interactive while it is
  open, and every model read and write is marshalled onto Revit's primary
  thread through an external-event bridge.
- **Smart text detection.** Reads level marks out of drawing text — `FFL
  +3.500`, `LVL. +3500`, `TOS -1.200`, `± 0.00`, `EL. 3.50 M`, `RL 100.500`,
  `TERRACE +14'-6"` — from the active view's text notes and spot elevations,
  the Revit selection, every text note in the model, a DXF on disk, a DXF
  already linked in, or a paste box.
  - The drawing's unit is inferred across the whole set, because a bare
    `3.500` is only decidable from the storey heights its neighbours imply.
  - Where texts carry positions, each written value is checked against where
    it sits on the sheet; one that contradicts its own position is flagged
    rather than quietly creating a level in the wrong place.
  - A detected level that lands on an existing one is matched, not duplicated.
- **Generation** that continues the model's own naming convention
  (`02 2ND FLOOR LVL.` → `03 3RD FLOOR LVL.`, including padded indices,
  ordinals, ordinal words and roman numerals), or renders a template.
- Inline editing of name and elevation, batch rename, re-spacing, and deletion
  with a count of what is hosted on each level first.
- Optional floor / ceiling / structural plan views for new levels, with a view
  template.
- Nothing reaches the model until **Apply changes**, which lands as one undo
  step.

# Adding these to `anongee_toolkit/ui/`

Five new files. None collides with `dialogs.py`, `forms.py` or `xaml.py`, and
`__init__.py` is **not** shipped — extend yours instead.

| File | What it adds |
|---|---|
| `progressbar.py` | `ProgressBar` — pyRevit-native-looking strip, CPython-safe |
| `hostwnd.py` | Revit main-window rect + DPI conversion (used for docking) |
| `pump.py` | dispatcher flush with a priority argument |
| `theme.py` | pyRevit palette lookup + the bar's control templates |
| `checklist.py` | `CheckList`, `pick_option` |

## What I removed after seeing your `ui/`

**No message boxes.** My version had `alert` and `ask_yes_no`; `forms.py`
already has `alert` and `confirm`, so mine are gone. Worth flagging: yours take
`(title, message)`, which is the **opposite order** to `pyrevit.forms.alert`.
Easy to get backwards when porting old scripts — Convert Slab wraps it in a
local `notify()` for exactly that reason.

**No `netclass` module.** It was headed for `revit/`; you asked me to leave that
package alone, so the duplicate-.NET-type guard is now inlined in the Convert
Slab script. It is engine-level rather than slab-specific, so if a second
CPython button needs it, `utils/` is the natural home.

## Add to your `ui/__init__.py`

```python
from anongee_toolkit.ui.progressbar import ProgressBar
from anongee_toolkit.ui.checklist import CheckList, pick_option
```

and extend `__all__`:

```python
    # progress + pickers
    "ProgressBar", "CheckList", "pick_option",
```

`hostwnd`, `pump` and `theme` are support modules — no need to re-export unless
you want them.

## Two overlaps you may want to collapse

**`WpfDialogBase.flush_ui()`** does the same job as `pump()`, hardcoded to
`Background` priority. That choice matters: `Render` sits *above* `Input` in the
dispatcher queue, so pumping at `Render` repaints but never dispatches a click —
a Cancel button pumped at `Render` looks alive and does nothing. `Background`
sits below `Input` so clicks land, at the cost of letting clicks through to
Revit as well. If you want one implementation:

```python
from anongee_toolkit.ui.pump import pump

    def flush_ui(self):
        pump(DispatcherPriority.Background)
```

**`xaml.load_xaml()`** parses XAML from a *file*; `theme.bar_resources()` parses
it from a *string* (the templates are embedded, not shipped as a .xaml). If you
would rather keep all XamlReader use in one place, a `load_xaml_string()` in
`xaml.py` would let `theme.py` drop its own parsing block.

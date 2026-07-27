# -*- coding: utf-8 -*-
"""Unjoin selected elements from joined elements of chosen categories."""

__title__ = "Unjoin by\nCategory"
__author__ = "AnonGee"
__doc__ = """Unjoins the selected elements from everything they are joined to
in the categories you pick.

1. Select one or more elements (or run the tool and pick on screen).
2. Tick one or more categories in the dialog (e.g. Floors).
3. Every join between a selected element and an element of a ticked
   category is removed. All other joins stay untouched."""

import time
from collections import defaultdict

from pyrevit import revit, DB, forms, script

from System.Windows.Input import Key

doc = revit.doc

NO_CAT_KEY = -1
PROGRESS_MIN = 50   # show the progress window only for bigger runs

RESULT_XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Unjoin by Category"
        SizeToContent="WidthAndHeight"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize"
        ShowInTaskbar="False">
    <StackPanel Margin="20" MaxWidth="460">
        <TextBlock x:Name="status_text" TextWrapping="Wrap" FontSize="13"/>
        <Button x:Name="close_btn" Content="Close"
                Width="90" Height="26" Margin="0,16,0,0"
                HorizontalAlignment="Center"
                IsDefault="True" IsCancel="True"/>
    </StackPanel>
</Window>
"""


class ResultDialog(forms.WPFWindow):
    """Result popup that closes on Enter, Space, Esc or the Close button.

    PreviewKeyDown is hooked on the WINDOW, so the keys work no matter
    which control currently has focus."""

    def __init__(self, message):
        forms.WPFWindow.__init__(self, RESULT_XAML, literal_string=True)
        self.status_text.Text = message
        self.close_btn.Click += self._on_close
        self.PreviewKeyDown += self._on_key

    def _on_close(self, sender, args):
        self.Close()

    def _on_key(self, sender, args):
        if args.Key in (Key.Enter, Key.Space, Key.Escape):
            args.Handled = True
            self.Close()


class _NoProgress(object):
    """Stand-in for forms.ProgressBar on small runs (no window shown)."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def update_progress(self, cur, total):
        pass


# ------------------------------------------------------------- get selection
elements = list(revit.get_selection().elements)
if not elements:
    elements = revit.pick_elements("Select elements to unjoin") or []
if not elements:
    script.exit()

# --------------------------------------------------- scan joins per category
# Joins are symmetric, so each pair is keyed once: frozenset({id_a, id_b}).
# That way a pair is never unjoined twice, even if both sides are selected.
# Each joined element is fetched and categorized ONCE (elem_cache), no matter
# how many selected elements it is joined to.
t0 = time.time()

cat_pairs = defaultdict(set)   # category key -> set of pair keys
cat_names = {}                 # category key -> display name
pair_elems = {}                # pair key -> (selected element, joined element)
elem_cache = {}                # element id int -> (element, cat key) or False

for el in elements:
    try:
        joined_ids = DB.JoinGeometryUtils.GetJoinedElements(doc, el)
    except Exception:
        continue   # element can't participate in joins at all
    el_id = el.Id.IntegerValue
    for jid in joined_ids:
        jid_int = jid.IntegerValue
        cached = elem_cache.get(jid_int)
        if cached is None:
            other = doc.GetElement(jid)
            if other is None:
                elem_cache[jid_int] = False
                continue
            cat = other.Category
            if cat is not None:
                cat_key = cat.Id.IntegerValue
                if cat_key not in cat_names:
                    cat_names[cat_key] = cat.Name
            else:
                cat_key = NO_CAT_KEY
                cat_names[cat_key] = "(No category)"
            cached = (other, cat_key)
            elem_cache[jid_int] = cached
        elif cached is False:
            continue
        other, cat_key = cached
        pair_key = frozenset((el_id, jid_int))
        cat_pairs[cat_key].add(pair_key)
        pair_elems[pair_key] = (el, other)

scan_secs = time.time() - t0

if not cat_pairs:
    forms.alert("Nothing in the selection is joined to anything.",
                exitscript=True)

# ---------------------------------------------------------- category dialog
labels = []
label_to_key = {}
for key in sorted(cat_pairs, key=lambda k: cat_names[k].lower()):
    count = len(cat_pairs[key])
    label = "{} ({} join{})".format(
        cat_names[key], count, "s" if count != 1 else "")
    labels.append(label)
    label_to_key[label] = key

chosen = forms.SelectFromList.show(
    labels,
    title="Unjoin From Categories",
    multiselect=True,
    button_name="Unjoin",
)
if not chosen:
    script.exit()

target_pairs = set()
chosen_names = []
for label in chosen:
    key = label_to_key[label]
    chosen_names.append(cat_names[key])
    target_pairs.update(cat_pairs[key])

# ------------------------------------------------------------------- unjoin
# No AreElementsJoined re-check: every pair comes from the scan above in the
# same session, so it is joined by definition -- re-checking would double the
# API calls in this loop. try/except still catches anything unexpected.
done = 0
failed = []
total = len(target_pairs)
step = max(1, total // 100)
t1 = time.time()

if total >= PROGRESS_MIN:
    progress = forms.ProgressBar(title="Unjoining... ({value} of {max_value})")
else:
    progress = _NoProgress()

# swallow_errors resolves Revit warning popups automatically, so the commit
# runs straight through instead of stalling on each warning dialog.
with progress as pb:
    with revit.Transaction("Unjoin by Category", swallow_errors=True):
        for n, pair_key in enumerate(target_pairs, 1):
            el_a, el_b = pair_elems[pair_key]
            try:
                DB.JoinGeometryUtils.UnjoinGeometry(doc, el_a, el_b)
                done += 1
            except Exception as err:
                failed.append((el_a, el_b, "{}".format(err)))
            if n % step == 0 or n == total:
                pb.update_progress(n, total)

unjoin_secs = time.time() - t1

# ----------------------------------------------------------- result dialog
lines = [
    "Unjoined {} of {} join(s)".format(done, total),
    "Categories: {}".format(", ".join(chosen_names)),
    "Scan {:.1f}s   |   Unjoin {:.1f}s".format(scan_secs, unjoin_secs),
]
if failed:
    lines.append("")
    lines.append("Could not unjoin {} pair(s):".format(len(failed)))
    for el_a, el_b, err in failed[:10]:
        lines.append("   {} <-> {}   ({})".format(
            el_a.Id.IntegerValue, el_b.Id.IntegerValue, err))
    if len(failed) > 10:
        lines.append("   ... and {} more".format(len(failed) - 10))

ResultDialog("\n".join(lines)).ShowDialog()

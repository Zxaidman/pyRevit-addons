# -*- coding: utf-8 -*-
"""Enforce a category-based join order priority on selected elements."""

__title__ = "Join\nPriority"
__author__ = "AnonGee"
__doc__ = """Reorders joins so higher-priority categories cut lower-priority
ones. Highest category in the list cuts everything; lowest only gets cut.

1. Select elements (or run the tool and pick on screen).
2. Reorder the category list (top = cuts everything). Order is remembered.
3. Optional: auto-join model elements that overlap the selection but
   aren't joined yet. Their categories join the list while the box is
   checked.

Same-category joins are left untouched in this version."""

import time

from pyrevit import revit, DB, forms, script

from System import String
from System.Collections.Generic import List
from System.Collections.ObjectModel import ObservableCollection
from System.Windows.Input import Cursors, Key

doc = revit.doc
config = script.get_config()

PROGRESS_MIN = 50    # show the progress window only for bigger runs
MAX_FAIL_LINES = 10  # max failed pairs listed in the result dialog

timings = {'detect': 0.0}

PRIORITY_XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Join Priority"
        SizeToContent="WidthAndHeight"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize"
        ShowInTaskbar="False">
    <StackPanel Margin="16" Width="340">
        <TextBlock Text="Top cuts everything below it:"
                   FontWeight="Bold" Margin="0,0,0,8"/>
        <DockPanel>
            <StackPanel DockPanel.Dock="Right" Margin="8,0,0,0">
                <Button x:Name="up_btn" Content="Up"
                        Width="60" Height="26" Margin="0,0,0,6"/>
                <Button x:Name="down_btn" Content="Down"
                        Width="60" Height="26"/>
            </StackPanel>
            <ListBox x:Name="cat_list" Height="220"/>
        </DockPanel>
        <CheckBox x:Name="autojoin_cb" Margin="0,12,0,0"
                  Content="Auto-join elements overlapping the selection"/>
        <StackPanel Orientation="Horizontal" HorizontalAlignment="Right"
                    Margin="0,14,0,0">
            <Button x:Name="apply_btn" Content="Apply" IsDefault="True"
                    Width="80" Height="26" Margin="0,0,8,0"/>
            <Button x:Name="cancel_btn" Content="Cancel" IsCancel="True"
                    Width="80" Height="26"/>
        </StackPanel>
    </StackPanel>
</Window>
"""

RESULT_XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Join Priority"
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


class PriorityDialog(forms.WPFWindow):
    """Reorderable category list + auto-join checkbox.

    Checking the box runs overlap detection (once, cached) and appends
    the overlapping elements' categories to the list; unchecking removes
    the ones that only came from overlaps."""

    def __init__(self, ordered_names, autojoin_default, detect_func):
        forms.WPFWindow.__init__(self, PRIORITY_XAML, literal_string=True)
        self._detect_func = detect_func
        self._detect_cache = None    # (candidates, overlap cat names)
        self._overlap_added = []     # names added by the checkbox
        self.result = None
        self.items = ObservableCollection[String]()
        for name in ordered_names:
            self.items.Add(name)
        self.cat_list.ItemsSource = self.items
        self.cat_list.SelectedIndex = 0
        self.up_btn.Click += self._move_up
        self.down_btn.Click += self._move_down
        self.apply_btn.Click += self._apply
        self.cancel_btn.Click += self._cancel
        self.autojoin_cb.Checked += self._on_check
        self.autojoin_cb.Unchecked += self._on_uncheck
        # set LAST so the Checked handler fires and pulls overlap cats in
        self.autojoin_cb.IsChecked = autojoin_default

    def _move_up(self, sender, args):
        idx = self.cat_list.SelectedIndex
        if idx > 0:
            self.items.Move(idx, idx - 1)
            self.cat_list.SelectedIndex = idx - 1

    def _move_down(self, sender, args):
        idx = self.cat_list.SelectedIndex
        if 0 <= idx < self.items.Count - 1:
            self.items.Move(idx, idx + 1)
            self.cat_list.SelectedIndex = idx + 1

    def _on_check(self, sender, args):
        if self._detect_cache is None:
            self.Cursor = Cursors.Wait
            try:
                self._detect_cache = self._detect_func()
            finally:
                self.Cursor = None
        overlap_cats = self._detect_cache[1]
        current = set(self.items)
        self._overlap_added = []
        for name in sorted(overlap_cats):
            if name not in current:
                self.items.Add(name)   # appended at the bottom
                self._overlap_added.append(name)

    def _on_uncheck(self, sender, args):
        for name in self._overlap_added:
            self.items.Remove(name)
        self._overlap_added = []

    def _apply(self, sender, args):
        checked = self.autojoin_cb.IsChecked == True
        if checked and self._detect_cache:
            candidates = self._detect_cache[0]
        else:
            candidates = []
        self.result = ([name for name in self.items], checked, candidates)
        self.Close()

    def _cancel(self, sender, args):
        self.Close()


class ResultDialog(forms.WPFWindow):
    """Result popup that closes on Enter, Space, Esc or the Close button."""

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
    elements = revit.pick_elements("Select elements for join priority") or []
if not elements:
    script.exit()

# ------------------------------------------- scan joined pairs and categories
t0 = time.time()

cat_of = {}       # element id int -> category name or None (cached once)
pair_elems = {}   # frozenset(id_a, id_b) -> (element_a, element_b)
present_cats = set()


def _cat_name(elem):
    eid = elem.Id.IntegerValue
    if eid not in cat_of:
        cat = elem.Category
        cat_of[eid] = cat.Name if cat is not None else None
    return cat_of[eid]


for el in elements:
    name = _cat_name(el)
    if name:
        present_cats.add(name)

for el in elements:
    try:
        joined_ids = DB.JoinGeometryUtils.GetJoinedElements(doc, el)
    except Exception:
        continue   # element can't participate in joins at all
    el_id = el.Id.IntegerValue
    for jid in joined_ids:
        key = frozenset((el_id, jid.IntegerValue))
        if key in pair_elems:
            continue
        other = doc.GetElement(jid)
        if other is None:
            continue
        name = _cat_name(other)
        if name:
            present_cats.add(name)
        pair_elems[key] = (el, other)

scan_secs = time.time() - t0

if not present_cats:
    forms.alert("No categorized elements in the selection.", exitscript=True)


# ------------------------- overlap detection (runs lazily from the dialog)
def _detect_overlaps():
    """Selected element(s) vs the WHOLE model: unjoined overlapping pairs.

    Works with a single selected element. Returns (candidates, cat names)
    where candidates is a list of (selected element, other element)."""
    t = time.time()
    existing = set(pair_elems)
    seen = set()
    candidates = []
    cats = set()
    for el in elements:
        if not _cat_name(el):
            continue
        bb = el.get_BoundingBox(None)
        if bb is None:
            continue
        try:
            hits = DB.FilteredElementCollector(doc)\
                     .WhereElementIsNotElementType()\
                     .WherePasses(DB.BoundingBoxIntersectsFilter(
                         DB.Outline(bb.Min, bb.Max)))\
                     .WherePasses(DB.ElementIntersectsElementFilter(el))\
                     .ToElements()
        except Exception:
            continue
        el_id = el.Id.IntegerValue
        for other in hits:
            oid = other.Id.IntegerValue
            if oid == el_id:
                continue
            cat = other.Category
            if cat is None or cat.CategoryType != DB.CategoryType.Model:
                continue
            key = frozenset((el_id, oid))
            if key in existing or key in seen:
                continue
            seen.add(key)
            cat_of[oid] = cat.Name   # prime cache for the apply phase
            cats.add(cat.Name)
            candidates.append((el, other))
    timings['detect'] = time.time() - t
    return candidates, cats


# --------------------------------- priority dialog (saved order remembered)
saved_order = config.get_option('cat_order', [])
if not isinstance(saved_order, list):
    saved_order = []
ordered = [n for n in saved_order if n in present_cats]
for n in sorted(present_cats):
    if n not in ordered:
        ordered.append(n)   # never-seen categories land at the bottom
autojoin_default = config.get_option('autojoin', False) == True

dlg = PriorityDialog(ordered, autojoin_default, _detect_overlaps)
dlg.ShowDialog()
if dlg.result is None:
    script.exit()
order, do_autojoin, join_candidates = dlg.result

config.cat_order = order
config.autojoin = do_autojoin
script.save_config()

rank = {}
for i, name in enumerate(order):
    rank[name] = i

# ------------------------------------------- build the reorder work list
order_pairs = []
same_cat = 0
unranked = 0
for key in pair_elems:
    a, b = pair_elems[key]
    na, nb = _cat_name(a), _cat_name(b)
    if not na or not nb:
        unranked += 1
    elif na == nb:
        same_cat += 1
    else:
        order_pairs.append((a, b))

# ------------------------------------------------------- apply in one txn
joined_new = 0
switched = 0
correct = 0
join_failed = []
switch_failed = []

# worst case: every new join also needs its order checked
total_ops = len(join_candidates) * 2 + len(order_pairs)
step = max(1, total_ops // 100)
if total_ops >= PROGRESS_MIN:
    progress = forms.ProgressBar(
        title="Applying join priority... ({value} of {max_value})")
else:
    progress = _NoProgress()

n = 0
t2 = time.time()
# swallow_errors resolves Revit warning popups (e.g. "joined but do not
# intersect") so the commit runs straight through.
with progress as pb:
    with revit.Transaction("Join Priority", swallow_errors=True):
        for a, b in join_candidates:
            n += 1
            try:
                DB.JoinGeometryUtils.JoinGeometry(doc, a, b)
                joined_new += 1
                if _cat_name(a) != _cat_name(b):
                    order_pairs.append((a, b))
                else:
                    same_cat += 1
            except Exception as err:
                join_failed.append((a, b, "{}".format(err)))
            if n % step == 0:
                pb.update_progress(n, total_ops)

        for a, b in order_pairs:
            n += 1
            try:
                if rank[_cat_name(a)] < rank[_cat_name(b)]:
                    cutter, cut = a, b
                else:
                    cutter, cut = b, a
                if DB.JoinGeometryUtils.IsCuttingElementInJoin(
                        doc, cutter, cut):
                    correct += 1
                else:
                    DB.JoinGeometryUtils.SwitchJoinOrder(doc, cutter, cut)
                    switched += 1
            except Exception as err:
                switch_failed.append((a, b, "{}".format(err)))
            if n % step == 0:
                pb.update_progress(n, total_ops)

        pb.update_progress(total_ops, total_ops)

apply_secs = time.time() - t2

# ----------------------------------------------------------- result dialog
lines = [
    "Join order -- switched: {}   already correct: {}".format(
        switched, correct),
]
if same_cat:
    lines.append("Same-category joins skipped: {}".format(same_cat))
if unranked:
    lines.append("Pairs without category skipped: {}".format(unranked))
if do_autojoin:
    lines.append("Auto-joined: {} of {} overlapping pair(s)".format(
        joined_new, len(join_candidates)))
    lines.append(
        "Scan {:.1f}s   |   Detect {:.1f}s   |   Apply {:.1f}s".format(
            scan_secs, timings['detect'], apply_secs))
else:
    lines.append("Scan {:.1f}s   |   Apply {:.1f}s".format(
        scan_secs, apply_secs))

failures = join_failed + switch_failed
if failures:
    lines.append("")
    lines.append("Failed on {} pair(s):".format(len(failures)))
    for a, b, err in failures[:MAX_FAIL_LINES]:
        lines.append("   {} <-> {}   ({})".format(
            a.Id.IntegerValue, b.Id.IntegerValue, err))
    if len(failures) > MAX_FAIL_LINES:
        lines.append("   ... and {} more".format(
            len(failures) - MAX_FAIL_LINES))

ResultDialog("\n".join(lines)).ShowDialog()

# -*- coding: utf-8 -*-
"""Enforce a category-based join order priority on selected elements."""

__title__ = "Join\nPriority"
__author__ = "AnonGee"
__version__ = "1.2.0"
__doc__ = """Reorders joins so higher-priority categories cut lower-priority
ones. Highest category in the list cuts everything; lowest only gets cut.

1. Select elements (or run the tool and pick on screen).
2. Reorder the category list (top = cuts everything). Order is remembered.
3. Optional: auto-join model elements that overlap the selection but
   aren't joined yet. Their categories join the list while the box is
   checked.
4. Optional: refresh edge-to-edge joins (unjoin + rejoin) so the dashed
   joined-edge linework displays again on stale joins.

Same-category joins are left untouched in this version.

v1.2.0 -- edge-met join refresh | v1.1.0 -- whole-model auto-join,
dynamic category list | v1.0.0 -- category priority + in-selection
auto-join"""

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

timings = {'detect': 0.0, 'edge': 0.0}

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
        <CheckBox x:Name="refresh_cb" Margin="0,8,0,0"
                  Content="Refresh edge-to-edge joins (unjoin + rejoin)"/>
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
    """Reorderable category list + auto-join / refresh checkboxes.

    Checking auto-join runs overlap detection (once, cached) and appends
    the overlapping elements' categories to the list; unchecking removes
    the ones that only came from overlaps."""

    def __init__(self, ordered_names, autojoin_default, refresh_default,
                 detect_func):
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
        self.refresh_cb.IsChecked = refresh_default
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
        self.result = ([name for name in self.items],
                       checked,
                       candidates,
                       self.refresh_cb.IsChecked == True)
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


def _pair_overlaps(elem_a, elem_b):
    """True if the two solids actually intersect (not just edge-touch)."""
    ids = List[DB.ElementId]()
    ids.Add(elem_b.Id)
    try:
        count = DB.FilteredElementCollector(doc, ids)\
                  .WherePasses(DB.ElementIntersectsElementFilter(elem_a))\
                  .GetElementCount()
        return count > 0
    except Exception:
        return True   # can't test -> treat as overlapping, don't refresh


# --------------------------------- priority dialog (saved order remembered)
saved_order = config.get_option('cat_order', [])
if not isinstance(saved_order, list):
    saved_order = []
ordered = [n for n in saved_order if n in present_cats]
for n in sorted(present_cats):
    if n not in ordered:
        ordered.append(n)   # never-seen categories land at the bottom
autojoin_default = config.get_option('autojoin', False) == True
refresh_default = config.get_option('refresh_edges', False) == True

dlg = PriorityDialog(ordered, autojoin_default, refresh_default,
                     _detect_overlaps)
dlg.ShowDialog()
if dlg.result is None:
    script.exit()
order, do_autojoin, join_candidates, do_refresh = dlg.result

config.cat_order = order
config.autojoin = do_autojoin
config.refresh_edges = do_refresh
script.save_config()

rank = {}
for i, name in enumerate(order):
    rank[name] = i

# ---------------------- find edge-met joined pairs to refresh (if requested)
refresh_pairs = []
if do_refresh:
    t1 = time.time()
    for key in pair_elems:
        a, b = pair_elems[key]
        if not _pair_overlaps(a, b):
            refresh_pairs.append((a, b))
    timings['edge'] = time.time() - t1

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

# --------------------------------------- apply (one undo entry via a group)
joined_new = 0
refreshed = 0
switched = 0
correct = 0
refresh_failed = []
join_failed = []
switch_failed = []
lost = set()   # pair keys whose refresh rejoin failed -> skip ordering

total_ops = (len(refresh_pairs) * 2 + len(join_candidates) * 2
             + len(order_pairs))
step = max(1, total_ops // 100)
if total_ops >= PROGRESS_MIN:
    progress = forms.ProgressBar(
        title="Applying join priority... ({value} of {max_value})")
else:
    progress = _NoProgress()

n = 0
t2 = time.time()
# The refresh needs a real regeneration BETWEEN unjoin and rejoin (that is
# what fixes the stale dashed linework), so the unjoin runs in its own
# transaction whose commit regenerates, then the rejoin + priority pass runs
# in a second one. The TransactionGroup assimilates both into ONE undo entry.
tgroup = DB.TransactionGroup(doc, "Join Priority")
tgroup.Start()
try:
    with progress as pb:
        to_rejoin = []
        if refresh_pairs:
            with revit.Transaction("Unjoin (refresh)", swallow_errors=True):
                for a, b in refresh_pairs:
                    n += 1
                    try:
                        DB.JoinGeometryUtils.UnjoinGeometry(doc, a, b)
                        to_rejoin.append((a, b))
                    except Exception as err:
                        refresh_failed.append(
                            (a, b, "refresh unjoin failed: {}".format(err)))
                    if n % step == 0:
                        pb.update_progress(n, total_ops)

        # swallow_errors resolves Revit warning popups (e.g. "joined but do
        # not intersect") so the commit runs straight through.
        with revit.Transaction("Join Priority", swallow_errors=True):
            for a, b in to_rejoin:
                n += 1
                try:
                    DB.JoinGeometryUtils.JoinGeometry(doc, a, b)
                    refreshed += 1
                except Exception as err:
                    lost.add(frozenset((a.Id.IntegerValue,
                                        b.Id.IntegerValue)))
                    refresh_failed.append(
                        (a, b, "REJOIN FAILED, join lost: {}".format(err)))
                if n % step == 0:
                    pb.update_progress(n, total_ops)

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
                if lost and frozenset((a.Id.IntegerValue,
                                       b.Id.IntegerValue)) in lost:
                    continue
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
    tgroup.Assimilate()
except Exception:
    if tgroup.GetStatus() == DB.TransactionStatus.Started:
        tgroup.RollBack()
    raise
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
if do_refresh:
    lines.append("Refreshed (unjoin+rejoin): {} of {} edge-met join(s)".format(
        refreshed, len(refresh_pairs)))

segments = ["Scan {:.1f}s".format(scan_secs)]
if do_autojoin:
    segments.append("Detect {:.1f}s".format(timings['detect']))
if do_refresh:
    segments.append("Check {:.1f}s".format(timings['edge']))
segments.append("Apply {:.1f}s".format(apply_secs))
lines.append("   |   ".join(segments))

failures = refresh_failed + join_failed + switch_failed
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
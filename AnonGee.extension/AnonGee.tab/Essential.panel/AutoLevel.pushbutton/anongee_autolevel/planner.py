# -*- coding: utf-8 -*-
"""The level plan — what the model has, what the user wants, what changes.

Everything the dialog shows comes out of :class:`LevelPlan`. It holds one row
per level (existing or proposed), tracks what was edited against the model's
own values, validates the result, and finally hands the Revit thread a plain
dict of operations. No Revit types cross this file, so the whole thing runs —
and is tested — without Revit (§12.8.7.2).
"""

from . import naming
from . import textparse

STATE_EXISTING = "existing"
STATE_NEW = "new"
STATE_RENAME = "rename"
STATE_MOVE = "move"
STATE_EDIT = "edit"
STATE_DELETE = "delete"

STATE_LABELS = {
    STATE_EXISTING: "In model",
    STATE_NEW: "New",
    STATE_RENAME: "Rename",
    STATE_MOVE: "Move",
    STATE_EDIT: "Rename + move",
    STATE_DELETE: "Delete",
}

# Two levels closer together than this are almost certainly a mistake —
# a duplicated annotation, or millimetres typed where metres were meant.
MIN_SEPARATION_MM = 100.0
DEFAULT_MATCH_TOLERANCE_MM = 25.0
DEFAULT_STOREY_MM = 3000.0


def _confidence_band(confidence):
    """Bucket a confidence into the four looks the grid draws.

    A band string drives the cell's DataTriggers. Strings bind reliably where
    a Python bool does not (§12.7.J/Q), so the visual state is carried as one.
    """
    if confidence is None:
        return "none"
    if confidence >= 75:
        return "high"
    if confidence >= 45:
        return "mid"
    return "low"


class LevelRow(object):
    """One row of the levels grid.

    ``__slots__`` with no ``INotifyPropertyChanged`` is mandatory here — see
    §12.7.G. Every slot whose name appears in a XAML binding path must match
    that path exactly; the rest are internal and never bound.
    """

    __slots__ = [
        # bound to the grid
        "Name", "ElevText", "ProjectText", "DeltaText", "StateText",
        "SourceText", "ConfText", "ConfBand", "ViewsText", "CountText",
        "NoteText",
        # mirrored from DataGrid.SelectedItems (§12.7.Q) — not bound
        "IsSelected",
        # internal
        "IdInt", "ElevMm", "OrigName", "OrigElevMm", "State", "Confidence",
        "Reasons", "Raw", "Plans", "Elements", "Source", "Locked",
    ]

    def __init__(self, name="", elevation_mm=0.0, id_int=None, source="Model"):
        self.Name = name
        self.ElevMm = float(elevation_mm)
        self.IdInt = id_int
        self.OrigName = name if id_int is not None else None
        self.OrigElevMm = float(elevation_mm) if id_int is not None else None
        self.State = STATE_EXISTING if id_int is not None else STATE_NEW
        self.Confidence = None
        self.Reasons = []
        self.Raw = ""
        self.Plans = []
        self.Elements = 0
        self.Source = source
        self.Locked = False          # true for the level Revit refuses to lose
        self.IsSelected = False
        self.ElevText = ""
        self.ProjectText = ""
        self.DeltaText = ""
        self.StateText = ""
        self.SourceText = source
        self.ConfText = ""
        self.ConfBand = "none"
        self.ViewsText = ""
        self.CountText = ""
        self.NoteText = ""

    # ── derived state ─────────────────────────────────────────────────
    @property
    def is_new(self):
        return self.IdInt is None

    @property
    def renamed(self):
        return (not self.is_new and self.State != STATE_DELETE
                and self.OrigName is not None and self.Name != self.OrigName)

    @property
    def moved(self):
        return (not self.is_new and self.State != STATE_DELETE
                and self.OrigElevMm is not None
                and abs(self.ElevMm - self.OrigElevMm) > 0.5)

    def refresh_state(self):
        if self.State == STATE_DELETE:
            return
        if self.is_new:
            self.State = STATE_NEW
            return
        if self.renamed and self.moved:
            self.State = STATE_EDIT
        elif self.renamed:
            self.State = STATE_RENAME
        elif self.moved:
            self.State = STATE_MOVE
        else:
            self.State = STATE_EXISTING

    def __repr__(self):                                       # pragma: no cover
        return "LevelRow({0!r}, {1:.0f}mm, {2})".format(
            self.Name, self.ElevMm, self.State)


class LevelPlan(object):
    """Existing levels plus every pending change, in one ordered list."""

    def __init__(self, unit_hint="mm"):
        self.rows = []
        self.unit_hint = unit_hint
        self.project_formatter = None    # set by the Revit side: mm -> str
        self.issues = []

    # ── loading ───────────────────────────────────────────────────────
    def load_existing(self, levels):
        """Seed from the Revit snapshot. Drops every pending change."""
        self.rows = []
        for level in levels or []:
            row = LevelRow(level.get("name") or "",
                           level.get("elev_mm") or 0.0,
                           id_int=level.get("id"),
                           source="Model")
            row.Plans = list(level.get("plans") or [])
            row.Elements = int(level.get("elements") or 0)
            row.ProjectText = level.get("elev_project") or ""
            self.rows.append(row)
        self.resort()
        return self

    # ── adding ────────────────────────────────────────────────────────
    def add_candidates(self, candidates, tolerance_mm=DEFAULT_MATCH_TOLERANCE_MM,
                       adopt_names=True, source="Detected"):
        """Fold detected candidates into the plan.

        A candidate that lands on an existing level is not a new level — it is
        that level, possibly better named. Only the unmatched ones are created.
        Returns ``(created, matched, renamed)``.
        """
        created = matched = renamed = 0
        for candidate in candidates or []:
            existing = self.nearest(candidate.elevation_mm, tolerance_mm,
                                    skip_new=False)
            if existing is not None:
                matched += 1
                existing.Confidence = candidate.confidence
                existing.Reasons = list(candidate.reasons)
                existing.Raw = candidate.raw
                if adopt_names and candidate.name and candidate.name != existing.Name:
                    existing.Name = naming.unique_name(
                        candidate.name, self._names_except(existing))
                    renamed += 1
                existing.refresh_state()
                continue
            row = LevelRow(candidate.name or "", candidate.elevation_mm,
                           source=candidate.source or source)
            row.Confidence = candidate.confidence
            row.Reasons = list(candidate.reasons)
            row.Raw = candidate.raw
            if not row.Name:
                row.Name = textparse.format_metres(candidate.elevation_mm)
            row.Name = naming.unique_name(row.Name, self._names_except(row))
            self.rows.append(row)
            created += 1
        self.resort()
        return created, matched, renamed

    def generate(self, count, height_mm=DEFAULT_STOREY_MM, base_mm=None,
                 mode="follow", template="Level {n}", start_index=None,
                 label="", source="Generated"):
        """Add *count* levels above the stack.

        ``mode`` is ``follow`` (continue the model's own naming) or
        ``template`` (render the user's pattern). ``follow`` falls back to the
        template when the existing names have no pattern to continue.
        """
        count = max(0, int(count or 0))
        if not count:
            return 0, "nothing to add"
        height = float(height_mm or DEFAULT_STOREY_MM)
        rows = self.live_rows()
        if base_mm is None:
            base_mm = rows[-1].ElevMm if rows else 0.0

        names = None
        note = ""
        if mode == "follow":
            convention = naming.learn_convention([r.Name for r in rows])
            if convention is not None:
                names = convention.next_names(count, start_index)
                note = convention.describe()
            else:
                note = "no naming pattern in the model — used the template"

        if names is None:
            first = start_index
            if first is None:
                first = self._next_template_index(template, len(rows))
            names = []
            for i in range(count):
                elevation = base_mm + height * (i + 1)
                names.append(naming.render_template(template, first + i,
                                                    elevation, label))
            if not note:
                note = "named from the template"

        for i in range(count):
            elevation = base_mm + height * (i + 1)
            row = LevelRow(naming.unique_name(names[i], self._names_except(None)),
                           elevation, source=source)
            row.Confidence = None
            self.rows.append(row)
        self.resort()
        return count, note

    def _next_template_index(self, template, existing_count):
        """Start numbering after the highest index already in use, else at 1."""
        highest = None
        for row in self.live_rows():
            for token in (row.Name or "").split():
                _prefix, body, _suffix = naming._split_affixes(token)
                digits = "".join(ch for ch in body if ch in "0123456789")
                if digits and digits == body.lstrip("+-"):
                    value = int(digits)
                    highest = value if highest is None else max(highest, value)
        return 1 if highest is None else highest + 1

    # ── editing ───────────────────────────────────────────────────────
    def rename(self, row, name):
        cleaned = (name or "").strip()
        if not cleaned:
            return False, "A level needs a name."
        clash = self._find_name(cleaned, skip=row)
        if clash is not None:
            return False, "\"{0}\" is already taken.".format(cleaned)
        row.Name = cleaned
        row.refresh_state()
        return True, ""

    def set_elevation(self, row, text_or_mm, push_above=False):
        """Move one level. With *push_above*, everything higher moves with it."""
        if isinstance(text_or_mm, (int, float)):
            value = float(text_or_mm)
        else:
            value = textparse.parse_elevation_input(text_or_mm, self.unit_hint)
        if value is None:
            return False, "Couldn't read that elevation."
        delta = value - row.ElevMm
        if push_above and abs(delta) > 0.5:
            for other in self.live_rows():
                if other is not row and other.ElevMm > row.ElevMm:
                    other.ElevMm += delta
                    other.refresh_state()
        row.ElevMm = value
        row.refresh_state()
        self.resort()
        return True, ""

    def respace(self, height_mm, base_row=None):
        """Re-space the stack above *base_row* to a uniform storey height."""
        rows = self.live_rows()
        if len(rows) < 2:
            return 0
        start = 0
        if base_row is not None and base_row in rows:
            start = rows.index(base_row)
        height = float(height_mm or DEFAULT_STOREY_MM)
        changed = 0
        for i in range(start + 1, len(rows)):
            target = rows[start].ElevMm + height * (i - start)
            if abs(rows[i].ElevMm - target) > 0.5:
                rows[i].ElevMm = target
                rows[i].refresh_state()
                changed += 1
        self.resort()
        return changed

    def batch_rename(self, rows, prefix="", suffix="", find="", replace="",
                     case_mode="keep", template="", start_index=1,
                     use_template=False):
        """Rename several rows at once. Returns (changed, [collisions])."""
        targets = [row for row in (rows or []) if row.State != STATE_DELETE]
        changed = 0
        collisions = []
        for offset, row in enumerate(targets):
            if use_template and template:
                proposed = naming.render_template(
                    template, start_index + offset, row.ElevMm, row.Name)
            else:
                proposed = naming.apply_affixes(row.Name, prefix, suffix,
                                                find, replace, case_mode)
            if not proposed or proposed == row.Name:
                continue
            if self._find_name(proposed, skip=row) is not None:
                collisions.append(proposed)
                continue
            row.Name = proposed
            row.refresh_state()
            changed += 1
        return changed, collisions

    def mark_delete(self, rows, deleted=True):
        count = 0
        for row in rows or []:
            if row.is_new:
                if deleted:
                    self.rows.remove(row)
                    count += 1
                continue
            row.State = STATE_DELETE if deleted else STATE_EXISTING
            if not deleted:
                row.refresh_state()
            count += 1
        self.resort()
        return count

    def remove_proposed(self):
        """Drop everything not yet in the model and undo pending edits."""
        self.rows = [row for row in self.rows if not row.is_new]
        for row in self.rows:
            row.Name = row.OrigName
            row.ElevMm = row.OrigElevMm
            row.Confidence = None
            row.Reasons = []
            row.State = STATE_EXISTING
        self.resort()

    # ── queries ───────────────────────────────────────────────────────
    def live_rows(self):
        return [row for row in self.rows if row.State != STATE_DELETE]

    def nearest(self, elevation_mm, tolerance_mm, skip_new=True):
        best = None
        best_gap = None
        for row in self.rows:
            if row.State == STATE_DELETE:
                continue
            if skip_new and row.is_new:
                continue
            gap = abs(row.ElevMm - elevation_mm)
            if gap <= tolerance_mm and (best_gap is None or gap < best_gap):
                best, best_gap = row, gap
        return best

    def _names_except(self, row):
        return [other.Name for other in self.rows
                if other is not row and other.State != STATE_DELETE]

    def _find_name(self, name, skip=None):
        lowered = (name or "").strip().lower()
        for row in self.rows:
            if row is skip or row.State == STATE_DELETE:
                continue
            if (row.Name or "").strip().lower() == lowered:
                return row
        return None

    def resort(self):
        self.rows.sort(key=lambda row: (row.ElevMm, row.Name or ""))
        return self.rows

    # ── validation + display ──────────────────────────────────────────
    def validate(self):
        """Everything that would fail, or should give the user pause."""
        issues = []
        rows = self.live_rows()
        seen = {}
        for row in rows:
            key = (row.Name or "").strip().lower()
            if not key:
                issues.append(("error", row, "This level has no name."))
                continue
            if key in seen:
                issues.append(("error", row,
                               "Duplicate name — Revit needs unique level names."))
            seen[key] = row
        for i in range(len(rows) - 1):
            gap = rows[i + 1].ElevMm - rows[i].ElevMm
            if abs(gap) < MIN_SEPARATION_MM:
                issues.append(("warn", rows[i + 1],
                               "Only {0:.0f} mm above \"{1}\".".format(
                                   gap, rows[i].Name)))
        for row in self.rows:
            if row.State == STATE_DELETE and row.Elements:
                issues.append(("warn", row,
                               "{0} element(s) are hosted on this level.".format(
                                   row.Elements)))
        self.issues = issues
        return issues

    def refresh_display(self, formatter=None):
        """Recompute every string the grid shows. Call after any change."""
        formatter = formatter or self.project_formatter
        self.resort()
        self.validate()
        noted = {}
        for severity, row, message in self.issues:
            if row is not None and id(row) not in noted:
                noted[id(row)] = (severity, message)

        previous = None
        for row in self.rows:
            row.refresh_state()
            row.ElevText = textparse.format_mm(row.ElevMm)
            row.ProjectText = (formatter(row.ElevMm) if formatter
                               else textparse.format_metres(row.ElevMm))
            row.StateText = STATE_LABELS.get(row.State, row.State)
            row.SourceText = row.Source
            row.ConfText = ("{0}%".format(int(row.Confidence))
                            if row.Confidence is not None else "—")
            row.ConfBand = _confidence_band(row.Confidence)
            row.CountText = "{0}".format(row.Elements) if row.Elements else "—"
            row.ViewsText = "{0}".format(len(row.Plans)) if row.Plans else "—"
            if row.State == STATE_DELETE:
                row.DeltaText = "—"
            elif previous is None:
                row.DeltaText = "base"
            else:
                row.DeltaText = "+{0:.0f}".format(row.ElevMm - previous.ElevMm)
            if row.State != STATE_DELETE:
                previous = row
            severity_message = noted.get(id(row))
            if severity_message:
                row.NoteText = severity_message[1]
            elif row.Reasons:
                row.NoteText = ", ".join(row.Reasons[:2])
            elif row.State == STATE_RENAME:
                row.NoteText = "was \"{0}\"".format(row.OrigName)
            elif row.State == STATE_MOVE:
                row.NoteText = "was {0:.0f} mm".format(row.OrigElevMm)
            elif row.State == STATE_EDIT:
                row.NoteText = "was \"{0}\" at {1:.0f} mm".format(
                    row.OrigName, row.OrigElevMm)
            else:
                row.NoteText = ""
        return self.rows

    def summary(self):
        counts = {"total": 0, "new": 0, "rename": 0, "move": 0, "edit": 0,
                  "delete": 0, "existing": 0}
        for row in self.rows:
            counts["total"] += 1
            counts[row.State] = counts.get(row.State, 0) + 1
        counts["changes"] = (counts["new"] + counts["rename"] + counts["move"]
                             + counts["edit"] + counts["delete"])
        return counts

    def has_blocking_issues(self):
        return any(severity == "error" for severity, _row, _msg in self.issues)

    # ── handing work to the Revit thread ──────────────────────────────
    def to_operations(self, create_views=False, view_type_ids=None,
                      view_template_id=None):
        """A plain-data description of the change set (§12.8.7.2)."""
        creates = []
        renames = []
        moves = []
        deletes = []
        for row in self.rows:
            if row.State == STATE_DELETE:
                if row.IdInt is not None:
                    deletes.append({"id": row.IdInt, "name": row.Name})
                continue
            if row.is_new:
                creates.append({"name": row.Name, "elev_mm": row.ElevMm})
                continue
            if row.renamed:
                renames.append({"id": row.IdInt, "name": row.Name,
                                "was": row.OrigName})
            if row.moved:
                moves.append({"id": row.IdInt, "elev_mm": row.ElevMm,
                              "was_mm": row.OrigElevMm, "name": row.Name})
        return {
            "creates": creates,
            "renames": renames,
            "moves": moves,
            "deletes": deletes,
            "create_views": bool(create_views),
            "view_type_ids": list(view_type_ids or []),
            "view_template_id": view_template_id,
        }

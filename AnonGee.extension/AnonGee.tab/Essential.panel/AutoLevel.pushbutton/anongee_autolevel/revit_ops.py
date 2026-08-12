# -*- coding: utf-8 -*-
"""Everything that must happen on Revit's primary thread.

The modeless window runs WPF on its own thread; touching the Revit API from
there crashes Revit (§12.8.2). So every read and every write lives here, and
is only ever called from inside the external event handler's ``Execute()``.

Each function takes plain data and returns plain data — ints, strings, floats,
lists and dicts. No Revit object ever crosses back to the WPF thread
(§12.8.7.2).
"""

from Autodesk.Revit.DB import (ElementLevelFilter,
                               FilteredElementCollector, ImportInstance, Level,
                               ModelPathUtils, SpotDimension, TextNote,
                               Transaction, TransactionGroup,
                               ViewFamilyType, ViewPlan, ViewType, XYZ)

from . import compat

# A level tagged in a section is normally annotated once; a document-wide sweep
# can hit thousands of notes, so it stops here and says that it did.
MAX_TEXT_SCAN = 6000

PLAN_FAMILIES = ("FloorPlan", "CeilingPlan", "StructuralPlan", "AreaPlan")


# ── reading the model ──────────────────────────────────────────────────────

def _plans_by_level(doc):
    """{level id int: [view name]} for every non-template plan view."""
    plans = {}
    for view in FilteredElementCollector(doc).OfClass(ViewPlan).ToElements():
        try:
            if view.IsTemplate:
                continue
            level = view.GenLevel
            if level is None:
                continue
            key = compat.id_value(level.Id)
        except Exception:
            continue
        plans.setdefault(key, []).append(compat.element_name(view))
    return plans


def _hosted_count(doc, level_id):
    """How many model elements sit on this level. Cheap enough per level."""
    try:
        return (FilteredElementCollector(doc)
                .WhereElementIsNotElementType()
                .WherePasses(ElementLevelFilter(level_id))
                .GetElementCount())
    except Exception:
        return 0


def snapshot(doc, with_counts=True):
    """The model's levels, plus what the dialog needs to describe them."""
    plans = _plans_by_level(doc)
    levels = []
    for level in FilteredElementCollector(doc).OfClass(Level) \
            .WhereElementIsNotElementType().ToElements():
        try:
            key = compat.id_value(level.Id)
            elevation_mm = compat.feet_to_mm(level.Elevation)
            levels.append({
                "id": key,
                "name": compat.element_name(level),
                "elev_mm": elevation_mm,
                "elev_project": compat.format_length_mm(doc, elevation_mm),
                "plans": plans.get(key, []),
                "elements": _hosted_count(doc, level.Id) if with_counts else 0,
            })
        except Exception:
            continue
    levels.sort(key=lambda item: item["elev_mm"])
    return {
        "levels": levels,
        "title": _doc_title(doc),
        "view_types": view_types(doc),
        "view_templates": plan_templates(doc),
    }


def _doc_title(doc):
    try:
        return doc.Title
    except Exception:
        return "(untitled)"


def view_types(doc):
    """Plan-view family types, so new levels can be given views."""
    found = []
    for vft in FilteredElementCollector(doc).OfClass(ViewFamilyType).ToElements():
        try:
            family = str(vft.ViewFamily)
        except Exception:
            continue
        if family not in PLAN_FAMILIES:
            continue
        found.append({"id": compat.id_value(vft.Id),
                      "name": compat.element_name(vft),
                      "family": family})
    found.sort(key=lambda item: (PLAN_FAMILIES.index(item["family"]),
                                 item["name"].lower()))
    return found


def plan_templates(doc):
    """Plan-view templates the new views can be handed."""
    found = []
    for view in FilteredElementCollector(doc).OfClass(ViewPlan).ToElements():
        try:
            if not view.IsTemplate:
                continue
        except Exception:
            continue
        found.append({"id": compat.id_value(view.Id),
                      "name": compat.element_name(view)})
    found.sort(key=lambda item: item["name"].lower())
    return found


# ── reading text out of the model ──────────────────────────────────────────

def _view_frame(view):
    """(origin, up, is_vertical) for projecting text positions onto the sheet."""
    try:
        up = view.UpDirection
        origin = view.Origin
        vertical = abs(up.Z) > 0.99
        return origin, up, vertical
    except Exception:
        return XYZ(0, 0, 0), XYZ(0, 0, 1), False


def _sheet_y_mm(coord, origin, up):
    try:
        offset = XYZ(coord.X - origin.X, coord.Y - origin.Y, coord.Z - origin.Z)
        return compat.feet_to_mm(offset.DotProduct(up))
    except Exception:
        return None


def collect_texts(doc, uidoc, scope="active_view"):
    """Pull annotation text (and exact spot elevations) out of the model.

    ``scope`` is one of ``active_view``, ``selection`` or ``document``.
    Returns ``entries`` for the text parser and ``exact`` for values Revit
    already knows precisely — a spot elevation needs no parsing at all.
    """
    result = {"entries": [], "exact": [], "view": "", "vertical": False,
              "note": "", "error": ""}
    if uidoc is None:
        result["error"] = "Open a model first."
        return result

    view = None
    try:
        view = uidoc.ActiveView
    except Exception:
        view = None

    if scope == "selection":
        ids = list(uidoc.Selection.GetElementIds())
        if not ids:
            result["error"] = ("Nothing selected — pick the level tags in Revit "
                               "and scan again. The window stays open.")
            return result
        elements = [doc.GetElement(eid) for eid in ids]
        result["view"] = "Selection ({0} element(s))".format(len(ids))
    elif scope == "document":
        elements = list(FilteredElementCollector(doc).OfClass(TextNote)
                        .WhereElementIsNotElementType().ToElements())
        elements += list(FilteredElementCollector(doc).OfClass(SpotDimension)
                         .WhereElementIsNotElementType().ToElements())
        result["view"] = "Whole model"
    else:
        if view is None:
            result["error"] = "No active view to scan."
            return result
        elements = list(FilteredElementCollector(doc, view.Id).OfClass(TextNote)
                        .WhereElementIsNotElementType().ToElements())
        elements += list(FilteredElementCollector(doc, view.Id)
                         .OfClass(SpotDimension)
                         .WhereElementIsNotElementType().ToElements())
        result["view"] = compat.element_name(view)

    origin, up, vertical = _view_frame(view) if view is not None else (
        XYZ(0, 0, 0), XYZ(0, 0, 1), False)
    result["vertical"] = bool(vertical)

    truncated = False
    for element in elements:
        if len(result["entries"]) + len(result["exact"]) >= MAX_TEXT_SCAN:
            truncated = True
            break
        if isinstance(element, TextNote):
            try:
                text = element.Text or ""
            except Exception:
                continue
            if not text.strip():
                continue
            coord = None
            try:
                coord = element.Coord
            except Exception:
                coord = None
            entry = {"text": text, "source": "Text note", "x": None, "y": None}
            if coord is not None:
                entry["y"] = _sheet_y_mm(coord, origin, up)
                entry["x"] = compat.feet_to_mm(coord.X)
                entry["z_mm"] = compat.feet_to_mm(coord.Z)
            result["entries"].append(entry)
        elif isinstance(element, SpotDimension):
            try:
                point = element.Origin
            except Exception:
                continue
            if point is None:
                continue
            result["exact"].append({
                "elev_mm": compat.feet_to_mm(point.Z),
                "source": "Spot elevation",
                "text": "spot elevation",
            })

    parts = []
    if result["entries"]:
        parts.append("{0} text note(s)".format(len(result["entries"])))
    if result["exact"]:
        parts.append("{0} spot elevation(s)".format(len(result["exact"])))
    if truncated:
        parts.append("stopped at {0}".format(MAX_TEXT_SCAN))
    result["note"] = ", ".join(parts) if parts else "nothing to read here"
    return result


def list_cad_links(doc):
    """Imported and linked CAD files, with the paths that can be re-read."""
    found = []
    for instance in FilteredElementCollector(doc).OfClass(ImportInstance) \
            .WhereElementIsNotElementType().ToElements():
        try:
            cad_type = doc.GetElement(instance.GetTypeId())
        except Exception:
            continue
        if cad_type is None:
            continue
        path = ""
        linked = False
        try:
            reference = cad_type.GetExternalFileReference()
            if reference is not None:
                linked = True
                path = ModelPathUtils.ConvertModelPathToUserVisiblePath(
                    reference.GetAbsolutePath())
        except Exception:
            path = ""
        found.append({"id": compat.id_value(instance.Id),
                      "name": compat.element_name(cad_type),
                      "path": path,
                      "linked": linked})
    found.sort(key=lambda item: item["name"].lower())
    return found


# ── writing ────────────────────────────────────────────────────────────────

def _start(doc, name, preprocessor):
    transaction = Transaction(doc, name)
    transaction.Start()
    if preprocessor is not None:
        try:
            options = transaction.GetFailureHandlingOptions()
            options.SetFailuresPreprocessor(preprocessor)
            options.SetClearAfterRollback(True)
            transaction.SetFailureHandlingOptions(options)
        except Exception:
            pass
    return transaction


def _finish(transaction):
    """Commit, or roll back if something left the transaction half-open."""
    try:
        if transaction.HasStarted() and not transaction.HasEnded():
            transaction.Commit()
    except Exception:
        try:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        except Exception:
            pass


def _taken_names(doc):
    names = set()
    for level in FilteredElementCollector(doc).OfClass(Level) \
            .WhereElementIsNotElementType().ToElements():
        names.add(compat.element_name(level).strip().lower())
    return names


def apply_operations(doc, operations, preprocessor=None):
    """Run the change set. One transaction group, one undo step for the user.

    Renames happen in two passes on purpose: swapping two level names in one
    go ("Level 2" -> "Level 3" while "Level 3" -> "Level 4") collides the
    moment the first one lands, so every renamed level is parked on a unique
    placeholder first and given its real name second.
    """
    report = {"created": 0, "renamed": 0, "moved": 0, "deleted": 0,
              "views": 0, "errors": [], "warnings": [], "new_ids": []}

    renames = operations.get("renames") or []
    moves = operations.get("moves") or []
    deletes = operations.get("deletes") or []
    creates = operations.get("creates") or []

    if not (renames or moves or deletes or creates):
        report["warnings"].append("Nothing to apply.")
        return report

    group = TransactionGroup(doc, "AnonGee · Auto Level Manager")
    group.Start()
    try:
        # Deletes go first so their names are free for the renames and creates
        # that follow — the plan allows reusing the name of a level you are
        # removing, and this is what makes that work.
        if deletes:
            _apply_deletes(doc, deletes, report, preprocessor)
        if renames:
            _apply_renames(doc, renames, report, preprocessor)
        if moves:
            _apply_moves(doc, moves, report, preprocessor)
        if creates:
            _apply_creates(doc, creates, report, preprocessor)
        if operations.get("create_views") and report["new_ids"]:
            _apply_views(doc, report, operations.get("view_type_ids") or [],
                         operations.get("view_template_id"), preprocessor)
        group.Assimilate()
    except Exception as error:
        try:
            if group.HasStarted() and not group.HasEnded():
                group.RollBack()
        except Exception:
            pass
        report["errors"].append("Rolled back: {0}".format(str(error)[:200]))
    return report


def _apply_renames(doc, renames, report, preprocessor):
    transaction = _start(doc, "Auto Level: rename", preprocessor)
    try:
        parked = []
        for index, item in enumerate(renames):
            level = doc.GetElement(compat.element_id(item["id"]))
            if level is None:
                report["errors"].append(
                    "Level {0} is no longer in the model.".format(item.get("was")))
                continue
            ok, message = compat.set_element_name(
                level, "~AutoLevel~{0}~{1}".format(index, item["id"]))
            if ok:
                parked.append((level, item))
            else:
                report["errors"].append("{0}: {1}".format(item.get("was"), message))
        for level, item in parked:
            ok, message = compat.set_element_name(level, item["name"])
            if ok:
                report["renamed"] += 1
            else:
                # Put the original name back rather than leave a placeholder.
                compat.set_element_name(level, item.get("was") or item["name"])
                report["errors"].append("{0}: {1}".format(item["name"], message))
    finally:
        _finish(transaction)


def _apply_moves(doc, moves, report, preprocessor):
    transaction = _start(doc, "Auto Level: move", preprocessor)
    try:
        for item in moves:
            level = doc.GetElement(compat.element_id(item["id"]))
            if level is None:
                report["errors"].append(
                    "Level {0} is no longer in the model.".format(item.get("name")))
                continue
            try:
                level.Elevation = compat.mm_to_feet(item["elev_mm"])
                report["moved"] += 1
            except Exception as error:
                report["errors"].append("{0}: {1}".format(
                    item.get("name"), str(error)[:140]))
    finally:
        _finish(transaction)


def _apply_deletes(doc, deletes, report, preprocessor):
    transaction = _start(doc, "Auto Level: delete", preprocessor)
    try:
        for item in deletes:
            element_id = compat.element_id(item["id"])
            if doc.GetElement(element_id) is None:
                continue
            try:
                removed = doc.Delete(element_id)
                report["deleted"] += 1
                extra = (len(removed) - 1) if removed else 0
                if extra > 0:
                    report["warnings"].append(
                        "\"{0}\" took {1} dependent element(s) with it.".format(
                            item.get("name"), extra))
            except Exception as error:
                report["errors"].append("Couldn't delete \"{0}\": {1}".format(
                    item.get("name"), str(error)[:140]))
    finally:
        _finish(transaction)


def _apply_creates(doc, creates, report, preprocessor):
    transaction = _start(doc, "Auto Level: create", preprocessor)
    try:
        taken = _taken_names(doc)
        for item in creates:
            try:
                level = Level.Create(doc, compat.mm_to_feet(item["elev_mm"]))
            except Exception as error:
                report["errors"].append("Couldn't create \"{0}\": {1}".format(
                    item.get("name"), str(error)[:140]))
                continue
            report["created"] += 1
            report["new_ids"].append(compat.id_value(level.Id))
            wanted = (item.get("name") or "").strip()
            if not wanted:
                taken.add(compat.element_name(level).strip().lower())
                continue
            name = wanted
            counter = 2
            while name.strip().lower() in taken:
                name = "{0} ({1})".format(wanted, counter)
                counter += 1
            ok, message = compat.set_element_name(level, name)
            if ok:
                taken.add(name.strip().lower())
            else:
                taken.add(compat.element_name(level).strip().lower())
                report["warnings"].append(
                    "Kept Revit's name for \"{0}\": {1}".format(wanted, message))
    finally:
        _finish(transaction)


def _apply_views(doc, report, view_type_ids, view_template_id, preprocessor):
    if not view_type_ids:
        return
    transaction = _start(doc, "Auto Level: plan views", preprocessor)
    try:
        template_id = (compat.element_id(view_template_id)
                       if view_template_id else None)
        for level_id in report["new_ids"]:
            for type_id in view_type_ids:
                try:
                    view = ViewPlan.Create(doc, compat.element_id(type_id),
                                           compat.element_id(level_id))
                    report["views"] += 1
                except Exception as error:
                    report["warnings"].append("View not created: {0}".format(
                        str(error)[:120]))
                    continue
                if template_id is not None:
                    try:
                        view.ViewTemplateId = template_id
                    except Exception:
                        report["warnings"].append(
                            "Couldn't apply the view template to \"{0}\".".format(
                                compat.element_name(view)))
    finally:
        _finish(transaction)


# ── selection and navigation ───────────────────────────────────────────────

def select_levels(uidoc, level_ids):
    """Push level ids into Revit's selection. ``List[T]`` built with Add()."""
    if uidoc is None:
        return 0
    from Autodesk.Revit.DB import ElementId
    from System.Collections.Generic import List
    ids = List[ElementId]()                     # §12.9.4 — never List[T](list)
    for value in level_ids or []:
        element_id = compat.element_id(value)
        if element_id != ElementId.InvalidElementId:
            ids.Add(element_id)
    uidoc.Selection.SetElementIds(ids)
    return ids.Count


def open_level_plan(uidoc, level_id):
    """Activate a plan view of this level — the modeless payoff.

    Returns (ok, message). Revit stays interactive while the window is open,
    so jumping from a row in the grid to the view it describes is one click.
    """
    if uidoc is None:
        return False, "Open a model first."
    doc = uidoc.Document
    target = compat.element_id(level_id)
    best = None
    for view in FilteredElementCollector(doc).OfClass(ViewPlan).ToElements():
        try:
            if view.IsTemplate:
                continue
            level = view.GenLevel
            if level is None or level.Id != target:
                continue
        except Exception:
            continue
        if best is None or view.ViewType == ViewType.FloorPlan:
            best = view
    if best is None:
        return False, "No plan view exists for that level yet."
    try:
        uidoc.RequestViewChange(best)
    except Exception:
        try:
            uidoc.ActiveView = best
        except Exception as error:
            return False, "Couldn't open the view: {0}".format(str(error)[:120])
    return True, "Opened \"{0}\".".format(compat.element_name(best))

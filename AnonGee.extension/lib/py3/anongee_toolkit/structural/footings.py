# -*- coding: utf-8 -*-
"""Create foundation pads as floors. Writes — inside a caller's transaction.

Footings are floors here rather than family instances, and that is the choice
the rest of this module follows from: a floor is a sketched outline, so a pad
that is not rectangular can be *scheduled* instead of approximated by the
nearest rectangle it fits inside. A combined footing, a cut corner, a pad worked
around a pile cap — all of them are just a different list of points.

Two things this does that are easy to leave out and expensive to discover.

**It flags every pad structural.** A floor that is not carries no
reinforcement — Revit refuses every bar — and it looks identical in every view.
That was the first thing the probe found in a real model, so it is set here
rather than hoped for.

**It duplicates a type per thickness.** A schedule with 900, 750 and 1050 mm
pads needs three types, named for their thickness, created once and reused.
Setting the thickness on a shared type instead would silently resize every
footing already using it.

No function here opens a transaction: a run creates hundreds of pads in chunks
inside one ``TransactionGroup`` the caller owns.
"""

import math

from Autodesk.Revit.DB import BuiltInCategory
from Autodesk.Revit.DB import BuiltInParameter
from Autodesk.Revit.DB import CurveLoop
from Autodesk.Revit.DB import ElementTransformUtils
from Autodesk.Revit.DB import FilteredElementCollector
from Autodesk.Revit.DB import Floor
from Autodesk.Revit.DB import FloorType
from Autodesk.Revit.DB import Line
from Autodesk.Revit.DB import XYZ
from System.Collections.Generic import List

from anongee_toolkit.revit.units import ft_to_mm
from anongee_toolkit.revit.units import mm_to_ft

__version__ = "0.1.0"

#: How a duplicated type is named. Thickness leads because that is the only
#: thing distinguishing one from another, and it sorts usefully.
TYPE_NAME = "RC Footing {0} mm"

#: Two points closer than this are the same point; a zero-length edge makes
#: Revit refuse the whole sketch rather than the duplicate.
MIN_EDGE_FT = 0.0026            # ~0.8 mm


def foundation_types(doc):
    """``[(name, ElementId, is_foundation)]`` of floor types worth offering.

    Floor types outside the Structural Foundation category are included, and
    labelled, because a project that has not loaded a foundation type can still
    place pads — Revit will simply file them under Floors — and saying so beats
    refusing to start.
    """
    foundation = []
    other = []
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        try:
            name = floor_type.Name
            category = floor_type.Category
            is_foundation = (
                category is not None
                and category.Id.IntegerValue
                == int(BuiltInCategory.OST_StructuralFoundation))
        except Exception:
            continue
        (foundation if is_foundation else other).append(
            (name, floor_type.Id, is_foundation))
    foundation.sort(key=lambda row: row[0])
    other.sort(key=lambda row: row[0])
    return foundation + other


def default_type_id(doc):
    """The foundation type a run should start from, or ``None``."""
    rows = foundation_types(doc)
    for name, element_id, is_foundation in rows:
        if is_foundation:
            return element_id
    return rows[0][1] if rows else None


def thickness_mm(floor_type):
    """A floor type's total thickness, or ``None`` if it will not say."""
    try:
        parameter = floor_type.get_Parameter(
            BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
        if parameter is not None and parameter.HasValue:
            return ft_to_mm(parameter.AsDouble())
    except Exception:
        pass
    try:
        structure = floor_type.GetCompoundStructure()
        if structure is not None:
            return ft_to_mm(structure.GetWidth())
    except Exception:
        pass
    return None


def _set_thickness(floor_type, value_mm):
    """Set a type's thickness through its core layer. True when it took."""
    try:
        structure = floor_type.GetCompoundStructure()
        if structure is None:
            return False
        structure.SetLayerWidth(structure.GetFirstCoreLayerIndex(),
                                mm_to_ft(value_mm))
        floor_type.SetCompoundStructure(structure)
        return True
    except Exception:
        return False


def resolve_type(doc, base_type_id, value_mm, cache=None):
    """``(FloorType, note)`` of this thickness, duplicated from the base once.

    Reuses a type already named for the thickness before duplicating, so a
    second run over the same schedule adds nothing. Requires a transaction when
    it has to duplicate.
    """
    cache = cache if cache is not None else {}
    base = doc.GetElement(base_type_id)
    if base is None:
        return None, "the base floor type could not be resolved"
    if not value_mm:
        return base, None

    key = int(round(value_mm))
    if key in cache:
        return cache[key], None

    existing = thickness_mm(base)
    if existing is not None and abs(existing - value_mm) < 0.5:
        cache[key] = base
        return base, None

    wanted = TYPE_NAME.format(key)
    for floor_type in FilteredElementCollector(doc).OfClass(FloorType).ToElements():
        try:
            if floor_type.Name == wanted:
                cache[key] = floor_type
                return floor_type, None
        except Exception:
            continue

    try:
        duplicated = base.Duplicate(wanted)
    except Exception as duplicate_error:
        cache[key] = base
        return base, ("could not create a {0} mm type ({1}); using '{2}' as it "
                      "is".format(key, duplicate_error, base.Name))
    if not _set_thickness(duplicated, value_mm):
        return duplicated, ("created '{0}' but could not set its thickness — "
                            "check the type's structure".format(wanted))
    cache[key] = duplicated
    return duplicated, None


def curve_loop(points_mm, origin_mm=(0.0, 0.0), rotation_deg=0.0):
    """``(CurveLoop, skipped)`` from local millimetre points.

    Rotation is applied about the pad's own origin before the offset, so a
    rotated footing turns on the spot rather than swinging away from where it
    was scheduled.
    """
    angle = math.radians(rotation_deg or 0.0)
    cos_a, sin_a = math.cos(angle), math.sin(angle)

    placed = []
    for point in points_mm:
        x, y = float(point[0]), float(point[1])
        if rotation_deg:
            x, y = x * cos_a - y * sin_a, x * sin_a + y * cos_a
        placed.append(XYZ(mm_to_ft(x + origin_mm[0]),
                          mm_to_ft(y + origin_mm[1]), 0.0))

    loop = CurveLoop()
    skipped = 0
    count = len(placed)
    for index in range(count):
        start = placed[index]
        end = placed[(index + 1) % count]
        if start.DistanceTo(end) < MIN_EDGE_FT:
            skipped += 1
            continue
        loop.Append(Line.CreateBound(start, end))
    return loop, skipped


def set_structural(floor):
    """Flag the pad structural. Without it Revit accepts no reinforcement.

    The failure this prevents is invisible: an unflagged floor looks exactly
    like a footing in every view and refuses every bar placed into it.
    """
    try:
        parameter = floor.get_Parameter(
            BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(1)
            return True
    except Exception:
        pass
    return False


def set_mark(element, mark):
    if not mark:
        return
    try:
        parameter = element.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
        if parameter is not None and not parameter.IsReadOnly:
            parameter.Set(str(mark))
    except Exception:
        pass


def sit_on_level(floor, offset_mm=0.0):
    """Put the pad's top at the level, plus whatever offset was scheduled.

    A foundation *family* hangs its depth below the level it is hosted on; a
    floor sits with its top there. The offset is stated rather than assumed so
    the two conventions cannot be confused.
    """
    for builtin in (BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM,
                    BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM):
        try:
            parameter = floor.get_Parameter(builtin)
        except Exception:
            continue
        if parameter is not None and not parameter.IsReadOnly:
            try:
                parameter.Set(mm_to_ft(offset_mm or 0.0))
                return True
            except Exception:
                continue
    return False


def create(doc, points_mm, floor_type_id, level_id, origin_mm=(0.0, 0.0),
           rotation_deg=0.0, offset_mm=0.0, mark=""):
    """Place one pad. **Requires a transaction the caller opened.**

    Returns the ``Floor``. Raises on anything that stops it being made, which
    the run above turns into a reported row rather than a stopped batch.
    """
    loop, skipped = curve_loop(points_mm, origin_mm, rotation_deg)
    if loop.NumberOfCurves() < 3:
        raise ValueError("the outline has fewer than three usable edges")

    loops = List[CurveLoop]()
    loops.Add(loop)
    floor = Floor.Create(doc, loops, floor_type_id, level_id)
    set_structural(floor)

    # A floor's rebar-cover parameters do not exist until it is structural AND
    # the document has caught up. Without this the cover is written to a
    # parameter that is not there yet, silently -- which is why cover types
    # were being created and never applied to anything.
    try:
        doc.Regenerate()
    except Exception:
        pass

    sit_on_level(floor, offset_mm)
    set_mark(floor, mark)
    return floor, skipped


def rotate(doc, element, point_mm, rotation_deg):
    """Turn a placed element about a vertical axis through *point_mm*.

    Only used where the outline could not carry the rotation itself — a
    rectangle built from Length and Width is turned when it is built, so this
    is for the cases where Revit has to do it afterwards.
    """
    if not rotation_deg:
        return False
    try:
        axis = Line.CreateUnbound(
            XYZ(mm_to_ft(point_mm[0]), mm_to_ft(point_mm[1]), 0.0), XYZ.BasisZ)
        ElementTransformUtils.RotateElement(doc, element.Id, axis,
                                            math.radians(rotation_deg))
        return True
    except Exception:
        return False

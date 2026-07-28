#! python3
# -*- coding: utf-8 -*-
"""
AnonGee · BIM Generation — core.py
Structural element creation: levels, columns, beams, floors/slabs.
"""

import clr
clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import (
    FilteredElementCollector, FamilySymbol, FloorType, BuiltInCategory,
    BuiltInParameter, XYZ, Line, Transaction, TransactionStatus, Level,
    Floor, CurveLoop, JoinGeometryUtils, MaterialFunctionAssignment
)
from Autodesk.Revit.DB.Structure import StructuralType
from System.Collections.Generic import List

from collections import OrderedDict
from parser_service import convert_metrics_distances, get_numeric_portion, get_ordinal_string

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MM_PER_FOOT = 304.8


# ─────────────────────────────────────────────────────────────────────────────
# Unit helpers
# ─────────────────────────────────────────────────────────────────────────────

def mm_to_feet(mm):
    return mm / MM_PER_FOOT

def meters_to_mm(meters):
    return int(round(meters * 1000.0))

def meters_to_feet(meters):
    return mm_to_feet(meters_to_mm(meters))


# ─────────────────────────────────────────────────────────────────────────────
# Safe parameter setter
# ─────────────────────────────────────────────────────────────────────────────

def set_parameter_if_writable(param, value):
    """Set a Revit parameter only if it exists and is not read-only."""
    if param and not param.IsReadOnly:
        param.Set(value)


# ─────────────────────────────────────────────────────────────────────────────
# Family / type queries
# ─────────────────────────────────────────────────────────────────────────────

def _collect_family_symbols(doc, category):
    """Return an OrderedDict of {display_name: FamilySymbol} sorted by name."""
    symbols = list(
        FilteredElementCollector(doc)
        .OfClass(FamilySymbol)
        .OfCategory(category)
    )
    result = OrderedDict()
    for symbol in sorted(symbols, key=lambda s: s.Name):
        family_name = doc.GetElement(symbol.Family.Id).Name
        display     = f"{family_name} - {symbol.Name}"
        result[display] = symbol
    return result


def get_structural_columns(doc):
    return _collect_family_symbols(doc, BuiltInCategory.OST_StructuralColumns)


def get_structural_framings(doc):
    return _collect_family_symbols(doc, BuiltInCategory.OST_StructuralFraming)


def get_floor_types(doc):
    """Return an OrderedDict of {name: FloorType} sorted by name."""
    floor_types = list(FilteredElementCollector(doc).OfClass(FloorType))
    result = OrderedDict()
    for ft in sorted(floor_types, key=lambda x: x.Name):
        result[ft.Name] = ft
    return result


def _activate_if_family_symbol(element):
    """
    Call Activate() only on FamilySymbol instances.
    FloorType (ElementType subclass) has no IsActive/Activate members.
    Calling those on a FloorType raises AttributeError.
    """
    if isinstance(element, FamilySymbol) and not element.IsActive:
        element.Activate()


# ─────────────────────────────────────────────────────────────────────────────
# FamilySymbol type resolution (columns / beams)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_or_duplicate_family_type(base_symbol, width_mm, depth_mm):
    """
    Return the FamilySymbol named "{width_mm} X {depth_mm}".
    Duplicates the base_symbol and sets dimension parameters if not found.
    """
    width_ft = mm_to_feet(int(round(float(width_mm))))
    depth_ft = mm_to_feet(int(round(float(depth_mm))))
    size_tag = f"{int(width_mm)} X {int(depth_mm)}"

    doc    = base_symbol.Document
    family = base_symbol.Family

    for symbol_id in family.GetFamilySymbolIds():
        existing = doc.GetElement(symbol_id)
        if existing.Name == size_tag:
            _activate_if_family_symbol(existing)
            return existing

    new_type = base_symbol.Duplicate(size_tag)
    for width_param in ("b", "Width"):
        set_parameter_if_writable(new_type.LookupParameter(width_param), width_ft)
    for depth_param in ("h", "Depth", "d"):
        set_parameter_if_writable(new_type.LookupParameter(depth_param), depth_ft)
    return new_type


# ─────────────────────────────────────────────────────────────────────────────
# FloorType resolution (slabs)
# ─────────────────────────────────────────────────────────────────────────────

def _find_structural_layer_index(compound_structure):
    """
    Return the index of the first structural (load-bearing) layer in a
    CompoundStructure, or 0 as a safe fallback.

    The structural layer carries MaterialFunctionAssignment.Structure.
    """
    for idx in range(compound_structure.LayerCount):
        func = compound_structure.GetLayerFunction(idx)
        if func == MaterialFunctionAssignment.Structure:
            return idx
    return 0


def _resolve_or_duplicate_floor_type(doc, base_floor_type, thickness_mm, floor_type_cache):
    """
    Return a FloorType whose structural layer thickness matches thickness_mm.

    Strategy:
      1. Check the cache — return immediately if already created this session.
      2. Scan existing FloorTypes for a name match ('{thickness_mm} mm').
      3. Duplicate base_floor_type, rename it, and set the structural layer width.

    FloorType thickness lives inside a CompoundStructure layer — it cannot be
    set via a simple LookupParameter like FamilySymbol dimensions can.
    """
    type_name = f"{thickness_mm} mm"

    if type_name in floor_type_cache:
        return floor_type_cache[type_name]

    # Scan existing types for an already-named match
    for ft in FilteredElementCollector(doc).OfClass(FloorType):
        if ft.Name == type_name:
            floor_type_cache[type_name] = ft
            return ft

    # No match found — duplicate and configure the structural layer thickness
    thickness_ft = mm_to_feet(thickness_mm)
    new_ft = base_floor_type.Duplicate(type_name)

    cs = new_ft.GetCompoundStructure()
    if cs is not None and cs.LayerCount > 0:
        structural_layer_idx = _find_structural_layer_index(cs)
        cs.SetLayerWidth(structural_layer_idx, thickness_ft)
        new_ft.SetCompoundStructure(cs)

    floor_type_cache[type_name] = new_ft
    return new_ft


# ─────────────────────────────────────────────────────────────────────────────
# Level management
# ─────────────────────────────────────────────────────────────────────────────

def _build_level_cache(doc):
    """Seed a {mm_elevation_int: Level} dict from all document levels."""
    cache = {}
    for level in FilteredElementCollector(doc).OfClass(Level):
        key        = meters_to_mm(level.Elevation / 3.28084)
        cache[key] = level
    return cache


def _get_or_create_level(elevation_meters, level_cache, doc):
    """Return the cached Level at this elevation, creating one if absent."""
    key = meters_to_mm(elevation_meters)
    if key not in level_cache:
        level_cache[key] = Level.Create(doc, meters_to_feet(elevation_meters))
    return level_cache[key]


# ─────────────────────────────────────────────────────────────────────────────
# Column placement
# ─────────────────────────────────────────────────────────────────────────────

def _place_column(doc, column_data, col_base_symbol, level_cache):
    """Create one structural column from a ColumnEntityContext."""
    coords = column_data.four_coordinates_profile
    pts    = [XYZ(c[0], c[1], c[2]) for c in coords]

    width_mm = convert_metrics_distances(pts[0], pts[1])
    depth_mm = convert_metrics_distances(pts[1], pts[2])
    if width_mm == 0:
        width_mm = convert_metrics_distances(pts[0], pts[3])
    if depth_mm == 0:
        depth_mm = width_mm

    centre_x = meters_to_feet(sum(c[0] for c in coords) / 4.0)
    centre_y = meters_to_feet(sum(c[1] for c in coords) / 4.0)
    base_z   = meters_to_feet(column_data.elevation_bottom_metric)

    col_type  = _resolve_or_duplicate_family_type(col_base_symbol, width_mm, depth_mm)
    base_lvl  = _get_or_create_level(column_data.elevation_bottom_metric, level_cache, doc)
    top_lvl   = _get_or_create_level(column_data.elevation_top_metric,    level_cache, doc)

    column = doc.Create.NewFamilyInstance(
        XYZ(centre_x, centre_y, base_z), col_type, base_lvl, StructuralType.Column
    )
    set_parameter_if_writable(column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM),        top_lvl.Id)
    set_parameter_if_writable(column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM), 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Beam placement
# ─────────────────────────────────────────────────────────────────────────────

def _place_beam(doc, beam_data, beam_base_symbol, level):
    """Create one structural beam from a FramingBeamContext."""
    pts   = [XYZ(p[0], p[1], p[2]) for p in beam_data.quad_bounds_sequence]
    edges = sorted(
        [(convert_metrics_distances(pts[i], pts[(i + 1) % 4]), pts[i], pts[(i + 1) % 4])
         for i in range(4)],
        key=lambda e: e[0]
    )

    width_mm = edges[0][0] or 200
    depth_mm = max(
        int(round(abs(beam_data.top_elevation_metric - beam_data.quad_bounds_sequence[0][2]) * 1000.0)),
        1
    )

    top_z = meters_to_feet(beam_data.top_elevation_metric)
    start = XYZ(
        meters_to_feet((edges[0][1].X + edges[0][2].X) / 2),
        meters_to_feet((edges[0][1].Y + edges[0][2].Y) / 2),
        top_z
    )
    end = XYZ(
        meters_to_feet((edges[1][1].X + edges[1][2].X) / 2),
        meters_to_feet((edges[1][1].Y + edges[1][2].Y) / 2),
        top_z
    )

    if start.DistanceTo(end) < 0.01:
        return

    beam_type = _resolve_or_duplicate_family_type(beam_base_symbol, width_mm, depth_mm)
    beam      = doc.Create.NewFamilyInstance(
        Line.CreateBound(start, end), beam_type, level, StructuralType.Beam
    )
    set_parameter_if_writable(
        beam.LookupParameter("Comments"),
        f"{beam_data.name} @{beam_data.top_elevation_metric:.1f}m"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Slab placement
# ─────────────────────────────────────────────────────────────────────────────

def _build_curve_loop_from_quad(quad_points_meters, profile_z_meters):
    """
    Build a closed CurveLoop from the (x, y) of four points, projected onto
    a flat plane at profile_z_meters.

    profile_z_meters MUST equal the level elevation passed to Floor.Create.

    Revit's Floor.Create convention: the profile loop is the floor's TOP
    face, sitting at the level elevation. The floor then extrudes DOWNWARD
    from there by the FloorType's total thickness. The quad's own recorded
    Z in the INP file is the slab's BOTTOM face — the expected result of
    that downward extrusion — and is used only to derive thickness in
    _place_slab, never as the profile or level Z.

    Returns None for degenerate inputs.
    """
    if len(quad_points_meters) < 3:
        return None

    profile_z_ft = meters_to_feet(profile_z_meters)
    pts_ft = [
        XYZ(meters_to_feet(p[0]), meters_to_feet(p[1]), profile_z_ft)
        for p in quad_points_meters
    ]

    curves = List[Line]()
    n = len(pts_ft)
    for i in range(n):
        start = pts_ft[i]
        end   = pts_ft[(i + 1) % n]
        if start.DistanceTo(end) < 0.001:
            return None  # degenerate edge
        curves.Add(Line.CreateBound(start, end))

    try:
        loop = CurveLoop.Create(curves)
        return None if loop.IsOpen() else loop
    except Exception:
        return None


def _place_slab(doc, slab_data, base_floor_type, level_cache, floor_type_cache):
    """
    Create one structural floor from a SlabsSurfaceContext.

    INP file encoding (confirmed from FRAME.inp analysis):
      slab_data.top_elevation_metric    = slab TOP face elevation (e.g. 4.0 m)
      slab_data.slab_depth_layer_bottom = quad Z = slab BOTTOM face (e.g. 3.8 m)
      slab_data.quad_points_collection  = 4 corners recorded at the BOTTOM face

    Revit placement model:
      level          = top_elevation_metric   (4.0)
      profile loop Z = top_elevation_metric   (4.0)  <- TOP face, same as level
      FloorType thickness = (top_elevation_metric - slab_depth_layer_bottom)
                          = 200 mm
      Floor.Create extrudes the profile DOWNWARD by that thickness, so the
      bottom face lands at 3.8 -- exactly matching the quad's recorded Z.

    Previous bug: the profile loop was projected to the QUAD's Z (3.8) while
    the level was ALSO set to 3.8. Profile and level matched each other, but
    both were 400mm below where they needed to be -- the floor's top ended up
    at 3.8, extruding down to 3.6, entirely displaced from the real slab.
    Fix: both profile and level use top_elevation_metric (4.0).
    """
    top_face_meters    = slab_data.top_elevation_metric       # 4.0 -- level AND profile Z
    bottom_face_meters = slab_data.slab_depth_layer_bottom    # 3.8 -- used only for thickness
    thickness_mm       = max(1, round((top_face_meters - bottom_face_meters) * 1000))

    curve_loop = _build_curve_loop_from_quad(slab_data.quad_points_collection, top_face_meters)
    if curve_loop is None:
        return  # degenerate geometry -- skip silently

    floor_type = _resolve_or_duplicate_floor_type(doc, base_floor_type, thickness_mm, floor_type_cache)
    level      = _get_or_create_level(top_face_meters, level_cache, doc)

    loop_list = List[CurveLoop]()
    loop_list.Add(curve_loop)

    Floor.Create(doc, loop_list, floor_type.Id, level.Id)


# ─────────────────────────────────────────────────────────────────────────────
# Geometry joining helpers
# ─────────────────────────────────────────────────────────────────────────────

def _bounding_boxes_overlap(box_a, box_b, tolerance=-0.05):
    if not box_a or not box_b:
        return False
    x = not (box_a.Max.X + tolerance < box_b.Min.X or box_a.Min.X - tolerance > box_b.Max.X)
    y = not (box_a.Max.Y + tolerance < box_b.Min.Y or box_a.Min.Y - tolerance > box_b.Max.Y)
    z = not (box_a.Max.Z + tolerance < box_b.Min.Z or box_a.Min.Z - tolerance > box_b.Max.Z)
    return x and y and z


def _try_join_geometry(doc, element_a, element_b):
    try:
        if not JoinGeometryUtils.AreElementsJoined(doc, element_a, element_b):
            JoinGeometryUtils.JoinGeometry(doc, element_a, element_b)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Main generation entry point
# ─────────────────────────────────────────────────────────────────────────────

def execute_generation_protocol(
    doc, parsed_model, col_symbol, beam_symbol, floor_type,
    level_prefix, level_start_name, level_suffix, separator
):
    """
    Create all levels, columns, beams, and slabs inside a single guarded
    Revit transaction.

    Transaction contract:
      - Any exception triggers RollBack before re-raising.
      - The transaction is always closed — pyRevit never sees an open one.
    """
    txn = Transaction(doc, "AnonGee · BIM Generation")
    txn.Start()
    try:
        _run_generation(
            doc, parsed_model, col_symbol, beam_symbol, floor_type,
            level_prefix, level_start_name, level_suffix, separator
        )
        txn.Commit()
    except Exception:
        if txn.GetStatus() == TransactionStatus.Started:
            txn.RollBack()
        raise


def _run_generation(
    doc, parsed_model, col_symbol, beam_symbol, floor_type,
    level_prefix, level_start_name, level_suffix, separator
):
    """Inner body — all Revit model writes live here."""

    # FamilySymbol activation (FloorType has no Activate — never call it)
    _activate_if_family_symbol(col_symbol)
    _activate_if_family_symbol(beam_symbol)

    # Collect all elevations that need levels
    z_elevations = set()
    for col  in parsed_model['columns']:
        z_elevations.update([col.elevation_bottom_metric, col.elevation_top_metric])
    for beam in parsed_model['framings']:
        z_elevations.add(beam.top_elevation_metric)
    for slab in parsed_model['slabs']:
        # top_elevation_metric = slab TOP face elevation = the level _place_slab uses
        z_elevations.add(slab.top_elevation_metric)

    level_cache       = _build_level_cache(doc)
    sorted_elevations = sorted(z_elevations)

    # Create / rename levels
    numeric_start  = get_numeric_portion(level_start_name)
    prefix_is_int  = level_prefix.isdigit()
    prefix_pad_len = len(level_prefix) if prefix_is_int else 0

    for index, elevation in enumerate(sorted_elevations):
        level = _get_or_create_level(elevation, level_cache, doc)
        prefix_part = (
            str(int(level_prefix) + index).zfill(prefix_pad_len)
            if prefix_is_int else level_prefix
        )
        name_parts = [p for p in [prefix_part, get_ordinal_string(numeric_start + index), level_suffix] if p]
        level_name = separator.join(name_parts).replace("  ", " ").strip()
        try:
            level.Name = level_name
        except Exception:
            pass  # name collision with existing level — skip

    # Place structural columns
    for col_data in parsed_model['columns']:
        _place_column(doc, col_data, col_symbol, level_cache)

    # Place structural beams
    for beam_data in parsed_model['framings']:
        beam_level = _get_or_create_level(beam_data.top_elevation_metric, level_cache, doc)
        _place_beam(doc, beam_data, beam_symbol, beam_level)

    # Place structural slabs — floor_type_cache persists across all slabs in this transaction
    floor_type_cache = {}
    for slab_data in parsed_model['slabs']:
        _place_slab(doc, slab_data, floor_type, level_cache, floor_type_cache)

    # Regenerate geometry before bounding-box join queries
    doc.Regenerate()

    # Join intersecting columns and beams
    columns = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_StructuralColumns)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    beams = list(
        FilteredElementCollector(doc)
        .OfCategory(BuiltInCategory.OST_StructuralFraming)
        .WhereElementIsNotElementType()
        .ToElements()
    )
    for column in columns:
        col_box = column.get_BoundingBox(None)
        for beam in beams:
            if _bounding_boxes_overlap(col_box, beam.get_BoundingBox(None)):
                _try_join_geometry(doc, column, beam)

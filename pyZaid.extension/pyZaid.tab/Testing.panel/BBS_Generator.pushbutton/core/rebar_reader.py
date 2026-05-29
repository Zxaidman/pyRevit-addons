# -*- coding: utf-8 -*-
"""
core/rebar_reader.py
Reads DB.Rebar elements from Revit and resolves them into BarRecord instances.
Pre-scans the model to ensure global parameter consistency.
"""

import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in [_ROOT, os.path.join(_ROOT, "core"), os.path.join(_ROOT, "standards")]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementId,
    BuiltInCategory, BuiltInParameter
)

from bar_record import BarRecord
from bar_mark_manager import AutoMarkGenerator, read_bar_mark, read_bar_type_name
from shape_resolver import resolve_shape, extract_dimensions

FT_TO_MM = 304.8

_HOST_CAT_MAP = {
    -2001330: "Beam", -2001320: "Column", -2000032: "Slab",
    -2001300: "Foundation", -2000011: "Wall",
}

def _get_double_param(element, param_names):
    for name in param_names:
        if not name: continue
        try:
            p = element.LookupParameter(name)
            if p and p.HasValue and p.StorageType.ToString() == "Double": return p.AsDouble()
        except Exception: continue
    return None

def _get_int_param(element, param_names):
    for name in param_names:
        if not name: continue
        try:
            p = element.LookupParameter(name)
            if p and p.HasValue:
                st = p.StorageType.ToString()
                if st == "Integer": return p.AsInteger()
                if st == "Double": return int(p.AsDouble())
        except Exception: continue
    return None

def _get_string_param(element, param_names, doc=None):
    for name in param_names:
        if not name: continue
        try:
            p = element.LookupParameter(name)
            if p and p.HasValue:
                st = p.StorageType.ToString()
                if st == "String": return p.AsString()
                elif st == "ElementId" and doc:
                    el = doc.GetElement(p.AsElementId())
                    if el: return el.Name
                elif st == "Integer": return str(p.AsInteger())
        except Exception: continue
    return None

def _host_member_type(doc, rebar_element):
    try:
        host_id = rebar_element.GetHostId()
        if host_id and host_id != ElementId.InvalidElementId:
            host = doc.GetElement(host_id)
            if host and host.Category:
                cat_id = host.Category.Id.IntegerValue
                mtype = _HOST_CAT_MAP.get(cat_id, "Unknown")
                mark_p = host.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
                name = mark_p.AsString() if mark_p and mark_p.HasValue else ""
                if not name:
                    try: name = host.Name
                    except Exception: name = f"ID{host_id.IntegerValue}"
                return host, mtype, name.strip()
    except Exception: pass
    return None, "Unknown", "Unknown"

def _floor_level_name(doc, rebar_element, param_names):
    for name in param_names:
        if not name: continue
        if name == "SCHEDULE_LEVEL_PARAM":
            try:
                p = rebar_element.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM)
                if p and p.HasValue:
                    lvl = doc.GetElement(p.AsElementId())
                    if lvl: return lvl.Name
            except Exception: pass
            continue
        try:
            p = rebar_element.LookupParameter(name)
            if p and p.HasValue:
                st = p.StorageType.ToString()
                if st == "ElementId":
                    lvl = doc.GetElement(p.AsElementId())
                    if lvl: return lvl.Name
                elif st == "String":
                    val = p.AsString()
                    if val and val.strip(): return val.strip()
        except Exception: pass
    try:
        p2 = rebar_element.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if p2 and p2.HasValue:
            lvl = doc.GetElement(p2.AsElementId())
            if lvl: return lvl.Name
    except Exception: pass
    return "Unknown Level"

def _collect_rebars(doc, uidoc, scope):
    cat = BuiltInCategory.OST_Rebar
    if scope == "whole":
        elements = FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements()
    elif scope == "view":
        elements = FilteredElementCollector(doc, doc.ActiveView.Id).OfCategory(cat).WhereElementIsNotElementType().ToElements()
    else:
        elements = [doc.GetElement(eid) for eid in uidoc.Selection.GetElementIds() if doc.GetElement(eid)]
    return [e for e in elements if e.GetType().Name == "Rebar"]

def _determine_best_param(rebars, param_names, doc, ptype="string"):
    """
    Pre-scans a SAMPLE of rebars (max 50) to find the most consistent
    parameter name. Scanning all bars is too expensive for large models.

    Returns a list containing the single best param name found.
    Falls back to the first candidate if none found in sample.
    """
    if not param_names:
        return []
    # Cap sample size — 50 bars is enough to determine consistency
    sample = rebars[:50]
    best_param = param_names[0]
    best_count = -1
    for pname in param_names:
        count = 0
        for r in sample:
            val = None
            try:
                if ptype == "string": val = _get_string_param(r, [pname], doc)
                elif ptype == "double": val = _get_double_param(r, [pname])
                elif ptype == "int":    val = _get_int_param(r, [pname])
                elif ptype == "level":  val = _floor_level_name(doc, r, [pname])
            except Exception:
                continue
            if val and val != "Unknown Level":
                count += 1
        # 100% hit on sample → use immediately, no need to check others
        if count == len(sample):
            return [pname]
        if count > best_count:
            best_count = count
            best_param = pname
    return [best_param]

def read_bars(
    doc, uidoc, standard_module, scope="whole",
    level_filter=None, member_filter=None, diameter_filter=None,
    progress_callback=None, shape_overrides=None, params_config=None
):
    params_config = params_config or {}
    raw = _collect_rebars(doc, uidoc, scope)
    total = len(raw)
    if not raw: return []

    # Global Scan: Lock in one consistent parameter across all rebars
    p_level  = _determine_best_param(raw, params_config.get("level", ["SCHEDULE_LEVEL_PARAM"]), doc, "level")
    p_length = _determine_best_param(raw, params_config.get("length", ["Length of each bar", "Cut Length"]), doc, "double")
    p_qty    = _determine_best_param(raw, params_config.get("qty", ["Quantity", "Number of Bars"]), doc, "int")
    p_shape  = _determine_best_param(raw, params_config.get("shape", ["Shape"]), doc, "string")
    p_member = _determine_best_param(raw, params_config.get("member", ["Partition", "ID_LIC"]), doc, "string")
    p_detail = _determine_best_param(raw, params_config.get("detail", ["ITEM_V"]), doc, "string")
    p_mark   = _determine_best_param(raw, params_config.get("mark", ["Mark", "Bar Mark"]), doc, "string")
    p_type   = _determine_best_param(raw, params_config.get("type", ["Bar Type", "Comments"]), doc, "string")

    auto_marker = AutoMarkGenerator()
    records = []

    for idx, rebar in enumerate(raw):
        if progress_callback: progress_callback(idx + 1, total, f"Reading bar {idx+1} of {total}…")

        try:
            level_name = _floor_level_name(doc, rebar, p_level)
            if level_filter and level_name not in level_filter: continue

            member_type_override = _get_string_param(rebar, p_member, doc)
            _, mtype_host, member_name = _host_member_type(doc, rebar)
            member_type = member_type_override if member_type_override else mtype_host
            if member_filter and member_type not in member_filter: continue
                
            bar_detail = _get_string_param(rebar, p_detail, doc) or ""

            bar_type = doc.GetElement(rebar.GetTypeId())
            dia_p = bar_type.get_Parameter(BuiltInParameter.REBAR_BAR_DIAMETER) if bar_type else None
            diameter_ft = dia_p.AsDouble() if dia_p and dia_p.HasValue else 0.0
            diameter_mm = int(round(diameter_ft * FT_TO_MM))

            if diameter_filter and diameter_mm not in diameter_filter: continue

            bar_mark = read_bar_mark(rebar, p_mark)
            if not bar_mark: bar_mark = auto_marker.get_or_create(rebar.Id.IntegerValue, member_name, diameter_mm)

            bar_type_name = read_bar_type_name(rebar, p_type, diameter_mm)

            # ── Shape resolution — GetRebarShape() first (correct Revit API) ──
            # GetRebarShape() returns the RebarShape element containing the
            # shape family name and dimension parameters A/B/C/D/E.
            # Text parameter is only used as a user display override.
            shape_elem = None
            try:
                if hasattr(rebar, "GetRebarShape"):
                    shape_elem = rebar.GetRebarShape()
            except Exception:
                pass

            # Shape name from RebarShape element; text param overrides if set
            shape_name = shape_elem.Name if shape_elem else "Unknown"
            if p_shape:
                override_val = _get_string_param(rebar, p_shape, doc)
                if override_val and override_val.strip():
                    shape_name = override_val.strip()

            shape_code, shape_desc, _ = resolve_shape(
                shape_name, standard_module, shape_overrides)

            # extract_dimensions reads RebarShape type THEN rebar instance
            dims = extract_dimensions(shape_elem, rebar, FT_TO_MM)

            cut_len_ft = _get_double_param(rebar, p_length)
            cutting_length_mm = int(round(cut_len_ft * FT_TO_MM)) if cut_len_ft else 0

            bend_ded_mm = _estimate_bend_deduction(rebar, shape_code, diameter_mm, standard_module)
            bend_dia_mm = standard_module.bend_diameter_mm(diameter_mm)

            no_bars = _get_int_param(rebar, p_qty) or 1
            try:
                arr = rebar.get_Parameter(BuiltInParameter.REBAR_ELEM_QUANTITY_OF_BARS)
                if arr and arr.HasValue: no_bars = arr.AsInteger()
            except Exception: pass

            total_length_mm = cutting_length_mm * no_bars
            unit_wt = standard_module.UNIT_WEIGHTS.get(diameter_mm, 0.0)
            total_wt = round((total_length_mm / 1000.0) * unit_wt, 3)
            formula_str = standard_module.cutting_length_formula(shape_code, dims, diameter_mm)

            record = BarRecord(
                bar_mark=bar_mark, member_name=member_name, member_type=member_type,
                floor_level=level_name, bar_type_name=bar_type_name, diameter_mm=diameter_mm,
                shape_code=shape_code, shape_description=shape_desc, dimensions=dims,
                cutting_length_mm=cutting_length_mm, bend_deduction_mm=bend_ded_mm,
                bend_diameter_mm=bend_dia_mm, no_of_bars=no_bars, total_length_mm=total_length_mm,
                unit_weight_kg_per_m=unit_wt, total_weight_kg=total_wt,
                standard=standard_module.STANDARD_SHORT, revit_element_id=rebar.Id.IntegerValue,
                formula_string=formula_str, bar_detail=bar_detail
            )
            records.append(record)

        except Exception as ex:
            if progress_callback: progress_callback(idx + 1, total, f"⚠ Skipped element {rebar.Id.IntegerValue}: {ex}")
            continue

    return records

def _estimate_bend_deduction(rebar, shape_code, diameter_mm, standard_module):
    _BEND_90_COUNT = {"00":0, "11":1, "13":2, "21":2, "51":4, "41":2, "44":2, "77":2}
    try: return _BEND_90_COUNT.get(str(shape_code), 0) * standard_module.bend_deduction_per_bend(diameter_mm, 90)
    except Exception: return 0

def get_all_levels(doc, params_config=None):
    p_level = params_config.get("level", ["SCHEDULE_LEVEL_PARAM"]) if params_config else ["SCHEDULE_LEVEL_PARAM"]
    cat = BuiltInCategory.OST_Rebar
    rebars = [r for r in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements() if r.GetType().Name == "Rebar"]
    levels = set()
    for r in rebars:
        lvl = _floor_level_name(doc, r, p_level)
        if lvl and lvl != "Unknown Level": levels.add(lvl)
    if not levels:
        model_levels = [e for e in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Levels).WhereElementIsNotElementType().ToElements() if e.GetType().Name == "Level"]
        model_levels.sort(key=lambda lv: lv.Elevation)
        return [lv.Name for lv in model_levels]
    return sorted(list(levels))

def get_all_member_types(doc, params_config=None):
    p_member = params_config.get("member", ["Partition", "ID_LIC", "ID_V"]) if params_config else ["Partition", "ID_LIC", "ID_V"]
    cat = BuiltInCategory.OST_Rebar
    rebars = [r for r in FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements() if r.GetType().Name == "Rebar"]
    mtypes = set()
    for r in rebars:
        val = _get_string_param(r, p_member, doc)
        if val: mtypes.add(val)
        else:
            _, mtype_host, _ = _host_member_type(doc, r)
            mtypes.add(mtype_host)
    if not mtypes: return ["Beam", "Column", "Slab", "Foundation", "Wall"]
    return sorted(list(mtypes))

def get_rebar_diameters(doc):
    types = [t for t in FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rebar).WhereElementIsElementType().ToElements() if t.GetType().Name == "RebarBarType"]
    dias = set()
    for t in types:
        p = t.get_Parameter(BuiltInParameter.REBAR_BAR_DIAMETER)
        if p and p.HasValue:
            d = int(round(p.AsDouble() * FT_TO_MM))
            if d > 0: dias.add(d)
    return sorted(dias)
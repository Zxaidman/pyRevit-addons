# -*- coding: utf-8 -*-
"""
core/bar_mark_manager.py
Reads bar mark from a Revit Rebar element's parameters.
Falls back to auto-generation if parameter is empty or missing.
"""

import re

def read_bar_mark(rebar_element, param_names):
    for pname in param_names:
        if not pname: continue
        try:
            p = rebar_element.LookupParameter(pname)
            if p and p.HasValue:
                st = p.StorageType.ToString()
                if st == "String":
                    val = p.AsString()
                    if val and val.strip(): return val.strip()
                elif st == "Integer":
                    return str(p.AsInteger())
        except Exception:
            continue
    return None

def read_bar_type_name(rebar_element, param_names, diameter_mm):
    for pname in param_names:
        if not pname: continue
        try:
            p = rebar_element.LookupParameter(pname)
            if p and p.HasValue:
                st = p.StorageType.ToString()
                if st == "String":
                    val = p.AsString()
                    if val and val.strip(): return val.strip()
                elif st == "Integer":
                    return str(p.AsInteger())
        except Exception:
            continue
    return f"T{diameter_mm}"

class AutoMarkGenerator:
    def __init__(self):
        self._counters = {}
        self._cache = {}

    def get_or_create(self, revit_element_id, member_name, diameter_mm):
        if revit_element_id in self._cache:
            return self._cache[revit_element_id]

        prefix = _member_prefix(member_name)
        key = (prefix, diameter_mm)
        seq = self._counters.get(key, 0) + 1
        self._counters[key] = seq

        mark = f"{prefix}-T{diameter_mm}-{seq:02d}"
        self._cache[revit_element_id] = mark
        return mark

    def reset(self):
        self._counters.clear()
        self._cache.clear()

def _member_prefix(member_name):
    """
    Extracts a short prefix from a structural member name.
    Pass 1: single letter + digits (B3, C1, S2, F1, W4)
    Pass 2: multi-char + digits  (BM-1, CB-2, SB-3, RB-4)
    Pass 3: any letters + digits anywhere in string
    Fallback: first 5 uppercase alphanumeric chars
    """
    m = re.search(r'\b([BCWSFVRbcwsfvr]\d+)\b', member_name)
    if m:
        return m.group(1).upper()
    m2 = re.search(r'\b(BM|CB|SB|WB|FB|RB|PL|RC|SC|FC)-?\s*(\d+)\b',
                   member_name, re.IGNORECASE)
    if m2:
        return (m2.group(1) + m2.group(2)).upper()
    m3 = re.search(r'([A-Za-z]{1,3})(\d{1,3})', member_name)
    if m3:
        return (m3.group(1) + m3.group(2)).upper()
    clean = re.sub(r'[^A-Za-z0-9]', '', member_name)
    return clean[:5].upper() if clean else "XX"
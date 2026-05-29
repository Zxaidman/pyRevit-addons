# -*- coding: utf-8 -*-
"""
core/revision_tracker.py
Saves and compares BBS exports for revision highlighting.

On each export a .bbs_rev JSON sidecar is written alongside the .xlsx.
On next export the previous sidecar is loaded and hashes compared.

Change states:
  "new"      — bar mark not in previous export (highlight GREEN)
  "changed"  — bar mark found but hash differs (highlight YELLOW)
  "deleted"  — bar mark was in previous, absent now (highlight RED)
  "same"     — no change
"""

import json
import os
import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import asdict


CHANGE_NEW     = "new"
CHANGE_CHANGED = "changed"
CHANGE_DELETED = "deleted"
CHANGE_SAME    = "same"


def _sidecar_path(xlsx_path: str) -> str:
    base, _ = os.path.splitext(xlsx_path)
    return base + ".bbs_rev"


def save_revision(records, xlsx_path: str, standard: str, metadata: dict = None):
    """
    Saves a JSON sidecar next to the xlsx.
    records: list of BarRecord
    """
    payload = {
        "export_date": datetime.datetime.now().isoformat(),
        "standard": standard,
        "metadata": metadata or {},
        "bars": {}
    }
    for r in records:
        # Key includes element_id to guarantee uniqueness even when
        # the same bar mark appears in multiple members on the same floor.
        key = f"{r.floor_level}|{r.member_type}|{r.member_name}|{r.bar_mark}|{r.revit_element_id}"
        payload["bars"][key] = {
            "hash":           r.revision_hash,
            "diameter_mm":    r.diameter_mm,
            "cutting_length": r.cutting_length_mm,
            "no_of_bars":     r.no_of_bars,
            "total_weight":   r.total_weight_kg,
            "shape_code":     r.shape_code,
        }
    with open(_sidecar_path(xlsx_path), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_previous_revision(prev_xlsx_path: str) -> Optional[dict]:
    """
    Loads previous revision sidecar.
    Returns None if not found.
    """
    sidecar = _sidecar_path(prev_xlsx_path)
    if not os.path.exists(sidecar):
        # Try loading the sidecar if user pointed at the xlsx but sidecar exists
        if os.path.exists(prev_xlsx_path):
            # maybe they gave us a path to the xlsx and sidecar is alongside
            pass
        return None
    try:
        with open(sidecar, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def compare_revisions(
    current_records,
    prev_data: Optional[dict]
) -> Dict[str, str]:
    """
    Compares current BarRecord list against previous JSON data.

    Returns a dict:
      { "bar_mark|member_name|floor_level": change_state, ... }

    Also returns a separate dict of deleted bars (only in previous).
    """
    if not prev_data:
        # No previous — everything is "new"
        return {
            f"{r.floor_level}|{r.member_type}|{r.member_name}|{r.bar_mark}|{r.revit_element_id}": CHANGE_NEW
            for r in current_records
        }

    prev_bars = prev_data.get("bars", {})
    current_keys = set()
    changes = {}

    for r in current_records:
        # Key includes element_id to guarantee uniqueness even when
        # the same bar mark appears in multiple members on the same floor.
        key = f"{r.floor_level}|{r.member_type}|{r.member_name}|{r.bar_mark}|{r.revit_element_id}"
        current_keys.add(key)
        if key not in prev_bars:
            changes[key] = CHANGE_NEW
        elif r.revision_hash != prev_bars[key].get("hash", ""):
            changes[key] = CHANGE_CHANGED
        else:
            changes[key] = CHANGE_SAME

    # Deleted bars
    for key in prev_bars:
        if key not in current_keys:
            changes[key] = CHANGE_DELETED

    return changes


def build_diff_summary(changes: Dict[str, str]) -> dict:
    """Returns count summary of each change type."""
    from collections import Counter
    c = Counter(changes.values())
    return {
        "new":     c.get(CHANGE_NEW, 0),
        "changed": c.get(CHANGE_CHANGED, 0),
        "deleted": c.get(CHANGE_DELETED, 0),
        "same":    c.get(CHANGE_SAME, 0),
        "total":   len(changes),
    }
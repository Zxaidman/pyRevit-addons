# -*- coding: utf-8 -*-
"""Compare Revit-link geometry against ezdxf geometry to find problem geometry.

Revit's CAD import silently clips and merges geometry at column/beam junctions
(a 600x750 column reads as 463x750; a clean beam becomes a 1064 mm blob). The raw
DXF, read with ezdxf, does not have that problem. With both sets expressed in Revit
internal feet (the ezdxf set after transform.apply), this module quantifies where
they disagree so the run can (a) report exactly which members Revit would have
mangled and (b) justify building from the cleaner ezdxf geometry instead.

Revit-free and operates on CurveRecord-like objects (.points, .kind, .layer_key,
.length_ft), so it is unit-testable outside Revit.
"""

from collections import defaultdict

_MM = 304.8
# A matched pair whose lengths differ by more than this fraction AND this absolute
# amount is flagged as clipped/merged.
_LEN_MISMATCH_FRAC = 0.10
_LEN_MISMATCH_MM = 50.0


def _midpoint(record):
    pts = record.points
    if not pts:
        return (0.0, 0.0)
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    return (sx / len(pts), sy / len(pts))


def _length_mm(record):
    if getattr(record, "length_ft", None):
        return record.length_ft * _MM
    total = 0.0
    pts = record.points
    for a, b in zip(pts, pts[1:]):
        total += ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
                  + (a[2] - b[2]) ** 2) ** 0.5
    return total * _MM


def _per_layer(records):
    table = defaultdict(lambda: {"count": 0, "length_mm": 0.0})
    for record in records:
        bucket = table[record.layer_key]
        bucket["count"] += 1
        bucket["length_mm"] += _length_mm(record)
    return table


def diff(revit_records, dxf_records, tol_ft):
    """Return a structured comparison of the two geometry sets (internal feet).

    Matches each DXF curve to the nearest Revit curve by midpoint within tol_ft.
    Reports per-layer counts/length, members present in the DXF but missing in
    Revit (dropped/merged), the reverse, and matched pairs whose length differs
    (clipped). `tol_ft` should be roughly a member half-width.
    """
    revit_mid = [_midpoint(r) for r in revit_records]
    revit_used = [False] * len(revit_records)
    tol2 = tol_ft * tol_ft

    dxf_only = 0
    clipped = []
    matched = 0
    for record in dxf_records:
        mx, my = _midpoint(record)
        best = -1
        best_d2 = tol2
        for i, (rx, ry) in enumerate(revit_mid):
            if revit_used[i]:
                continue
            d2 = (rx - mx) ** 2 + (ry - my) ** 2
            if d2 <= best_d2:
                best = i
                best_d2 = d2
        if best < 0:
            dxf_only += 1
            continue
        revit_used[best] = True
        matched += 1
        dxf_len = _length_mm(record)
        rev_len = _length_mm(revit_records[best])
        ref = max(dxf_len, rev_len, 1e-9)
        if (abs(dxf_len - rev_len) > _LEN_MISMATCH_MM
                and abs(dxf_len - rev_len) / ref > _LEN_MISMATCH_FRAC):
            clipped.append({
                "layer": record.layer_key,
                "dxf_length_mm": round(dxf_len, 1),
                "revit_length_mm": round(rev_len, 1),
            })

    revit_only = sum(1 for used in revit_used if not used)

    dxf_layers = _per_layer(dxf_records)
    revit_layers = _per_layer(revit_records)
    per_layer = {}
    for layer in sorted(set(dxf_layers.keys()) | set(revit_layers.keys())):
        per_layer[layer] = {
            "revit_count": revit_layers.get(layer, {}).get("count", 0),
            "dxf_count": dxf_layers.get(layer, {}).get("count", 0),
            "revit_length_mm": round(revit_layers.get(layer, {}).get("length_mm", 0.0), 1),
            "dxf_length_mm": round(dxf_layers.get(layer, {}).get("length_mm", 0.0), 1),
        }

    return {
        "revit_curves": len(revit_records),
        "dxf_curves": len(dxf_records),
        "matched": matched,
        "dxf_only": dxf_only,          # in DXF, dropped/merged by Revit's import
        "revit_only": revit_only,      # Revit import artifacts with no DXF source
        "clipped": clipped,            # matched but length differs (junction clipping)
        "per_layer": per_layer,
        "build_source": "dxf",         # authoritative source for element creation
    }


def format_console(comparison):
    """Short console lines summarising the comparison."""
    if not comparison:
        return []
    return [
        "compare: revit {0} vs dxf {1} curves; matched {2}".format(
            comparison["revit_curves"], comparison["dxf_curves"],
            comparison["matched"]),
        "problem geometry: {0} in DXF missing/merged in Revit, {1} clipped "
        "(building from DXF)".format(
            comparison["dxf_only"], len(comparison["clipped"])),
    ]

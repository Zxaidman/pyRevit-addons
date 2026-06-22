# -*- coding: utf-8 -*-
"""Read geometry + text from a DXF file with ezdxf (CPython3, in-process).

This is the half of the hybrid extraction that the Revit API cannot do: it reads
the TEXT the link hides, and it reads geometry the Revit import would clip/merge.
ezdxf handles BOTH ascii and binary DXF, OCS->WCS transforms, MTEXT formatting and
block INSERT/ATTRIB tag text -- far more reliable than a hand-rolled group-code
reader. Requires the pyRevit CPython3 engine (#! python3) with ezdxf on lib/py3.

Output mirrors the Revit reader: geometry becomes CurveRecords (so the existing
shapes/report/columns/beams pipeline is reused verbatim) and text becomes
TextRecords. Coordinates are in the DXF's own units until transform.apply maps them
to Revit internal feet.
"""

import math
import os

from ..model import CurveRecord, TextRecord, DxfReadResult

# ezdxf is vendored under lib/py3. Import LAZILY (not at module load): the CPython3
# engine caches sys.modules across runs, so a module-load import that failed once
# (e.g. before ezdxf was provisioned) would stay failed for the whole session. A
# lazy retry picks ezdxf up on the next run without a full Revit restart.
ezdxf = None
_ezdxf_recover = None
_EZDXF_ERROR = "ezdxf not imported yet"


def _ensure_ezdxf():
    """Import ezdxf on demand; cache the module once it succeeds. Returns bool."""
    global ezdxf, _ezdxf_recover, _EZDXF_ERROR
    if ezdxf is not None:
        return True
    try:
        import ezdxf as _ezdxf_module
        from ezdxf import recover as _recover_module
        ezdxf = _ezdxf_module
        _ezdxf_recover = _recover_module
        _EZDXF_ERROR = None
        return True
    except Exception as import_error:
        _EZDXF_ERROR = import_error
        return False


_FLATTEN_DIST = 0.5     # tessellation sag for splines/ellipses, drawing units
_CIRCLE_SAMPLES = (0.0, 120.0, 240.0)   # degrees: 3 points fix an exact circle


def ezdxf_available():
    return _ensure_ezdxf()


def read_dxf(path):
    """Read one DXF into a DxfReadResult(records, texts), in DXF coordinates.

    Fail-fast with a clear message if ezdxf is missing or the file is unreadable.
    """
    if not _ensure_ezdxf():
        raise RuntimeError(
            "ezdxf is not available. Provision it into lib/py3 "
            "(tools/auto_provision.py) and re-run. Import error: {0}".format(
                _EZDXF_ERROR))
    if not path or not os.path.exists(path):
        raise IOError("DXF file not found: {0}".format(path))

    try:
        doc = ezdxf.readfile(path)
    except Exception:
        # Binary/odd/damaged files: the recover module is more forgiving.
        doc, _auditor = _ezdxf_recover.readfile(path)

    records = []
    texts = []
    _walk(doc.modelspace(), records, texts, depth=0)
    return DxfReadResult(os.path.basename(path), records, texts)


def _walk(entities, records, texts, depth):
    """Process an entity container, recursing one level into block INSERTs."""
    for entity in entities:
        dxftype = entity.dxftype()
        try:
            if dxftype == "INSERT":
                _read_insert(entity, records, texts, depth)
            elif dxftype in ("TEXT", "ATTRIB", "ATTDEF"):
                _add_text(texts, _safe(lambda: entity.dxf.text),
                          _layer(entity), _insert_point(entity))
            elif dxftype == "MTEXT":
                _add_text(texts, _safe(entity.plain_text), _layer(entity),
                          _xyz(entity.dxf.insert))
            else:
                record = _geometry_record(entity, dxftype)
                if record is not None:
                    records.append(record)
        except Exception:
            # One malformed entity must never abort the whole read.
            continue


def _read_insert(insert, records, texts, depth):
    """Explode a block reference: nested geometry (WCS) + its ATTRIB tag text."""
    for attrib in getattr(insert, "attribs", []):
        _add_text(texts, _safe(lambda: attrib.dxf.text), _layer(attrib),
                  _insert_point(attrib))
    if depth >= 3:
        return   # bound nesting depth
    try:
        virtual = list(insert.virtual_entities())
    except Exception:
        virtual = []
    _walk(virtual, records, texts, depth + 1)


def _geometry_record(entity, dxftype):
    layer = _layer(entity)
    if dxftype == "LINE":
        pts = [_xyz(entity.dxf.start), _xyz(entity.dxf.end)]
        return CurveRecord("line", pts, layer, None)
    if dxftype == "ARC":
        return CurveRecord("arc", _arc_points(entity), layer, None)
    if dxftype == "CIRCLE":
        # 3 points (0/120/240 deg) reconstruct the exact circle downstream.
        return CurveRecord("arc", _circle_points(entity), layer, None)
    if dxftype == "LWPOLYLINE":
        return CurveRecord("polyline", _lwpolyline_points(entity), layer, None)
    if dxftype == "POLYLINE":
        return CurveRecord("polyline", _polyline_points(entity), layer, None)
    if dxftype in ("ELLIPSE", "SPLINE"):
        pts = _flatten(entity)
        if len(pts) >= 2:
            return CurveRecord(dxftype.lower(), pts, layer, None)
    return None


# --- geometry helpers -------------------------------------------------------

def _arc_points(arc):
    """[start, mid, end] of an ARC in WCS (matches the Revit reader's convention)."""
    cx, cy, cz = _xyz(arc.dxf.center)
    r = arc.dxf.radius
    sa = math.radians(arc.dxf.start_angle)
    ea = math.radians(arc.dxf.end_angle)
    if ea < sa:
        ea += 2.0 * math.pi
    ma = (sa + ea) / 2.0
    ocs = arc.ocs()
    return [_to_wcs(ocs, (cx + r * math.cos(a), cy + r * math.sin(a), cz))
            for a in (sa, ma, ea)]


def _circle_points(circle):
    cx, cy, cz = _xyz(circle.dxf.center)
    r = circle.dxf.radius
    ocs = circle.ocs()
    return [_to_wcs(ocs, (cx + r * math.cos(math.radians(a)),
                          cy + r * math.sin(math.radians(a)), cz))
            for a in _CIRCLE_SAMPLES]


def _lwpolyline_points(poly):
    elevation = poly.dxf.elevation if poly.dxf.hasattr("elevation") else 0.0
    ocs = poly.ocs()
    pts = [_to_wcs(ocs, (x, y, elevation)) for x, y in poly.get_points("xy")]
    if getattr(poly, "closed", False) and len(pts) >= 2:
        pts = pts + [pts[0]]
    return pts


def _polyline_points(poly):
    pts = []
    for vertex in poly.vertices:
        pts.append(_xyz(vertex.dxf.location))
    if getattr(poly, "is_closed", False) and len(pts) >= 2:
        pts = pts + [pts[0]]
    return pts


def _flatten(entity):
    try:
        return [_xyz(p) for p in entity.flattening(_FLATTEN_DIST)]
    except Exception:
        return []


# --- text helpers -----------------------------------------------------------

def _add_text(texts, value, layer, point):
    if value is None:
        return
    cleaned = value.strip()
    if not cleaned:
        return
    texts.append(TextRecord(cleaned, layer, point))


def _insert_point(entity):
    """Best text anchor: insertion point, falling back to alignment point."""
    point = _xyz(entity.dxf.insert)
    if point == (0.0, 0.0, 0.0) and entity.dxf.hasattr("align_point"):
        return _xyz(entity.dxf.align_point)
    return point


# --- low-level --------------------------------------------------------------

def _layer(entity):
    try:
        return entity.dxf.layer
    except Exception:
        return None


def _xyz(point):
    """Normalise an ezdxf Vec3 / tuple to a plain (x, y, z) float tuple."""
    try:
        return (float(point.x), float(point.y), float(point.z))
    except AttributeError:
        if len(point) >= 3:
            return (float(point[0]), float(point[1]), float(point[2]))
        return (float(point[0]), float(point[1]), 0.0)


def _to_wcs(ocs, point):
    return _xyz(ocs.to_wcs(point))


def _safe(getter):
    try:
        return getter()
    except Exception:
        return None

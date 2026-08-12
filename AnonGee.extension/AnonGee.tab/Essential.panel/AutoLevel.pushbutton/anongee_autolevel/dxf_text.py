# -*- coding: utf-8 -*-
"""Read TEXT / MTEXT / ATTRIB out of a DXF, with positions.

Revit does not expose the text inside a CAD link — the geometry you get back
from an ``ImportInstance`` is curves. cad2bim solves this by reading the DXF
itself with ezdxf and aligning it to the link, and this tool takes the same
route for the same reason.

ezdxf is bundled in ``lib/py3`` (CPython 3 only). Nothing here is imported
until the user actually picks a DXF, so the tool loads fine without it and
says so plainly when the file is picked.
"""

import os

MM_PER_FT = 304.8


def available():
    """True when ezdxf can be imported right now."""
    try:
        import ezdxf                                  # noqa: F401
        return True
    except Exception:
        return False


def version():
    try:
        import ezdxf
        return getattr(ezdxf, "__version__", "unknown")
    except Exception:
        return None


def _entity_text(entity):
    """The string an entity carries, or ''. Handles TEXT, MTEXT and ATTRIB."""
    dxftype = entity.dxftype()
    try:
        if dxftype == "MTEXT":
            return entity.text or ""
        if dxftype in ("TEXT", "ATTRIB", "ATTDEF"):
            return entity.dxf.text or ""
    except Exception:
        return ""
    return ""


def _entity_point(entity):
    """The entity's insertion point as (x, y), or (None, None)."""
    for attribute in ("insert", "align_point"):
        try:
            point = getattr(entity.dxf, attribute, None)
            if point is not None:
                return float(point[0]), float(point[1])
        except Exception:
            continue
    return None, None


def read_texts(path, layers=None, include_blocks=True, limit=20000):
    """Every text entity in the DXF's modelspace.

    Returns ``{"entries": [...], "layers": [...], "note": str, "error": str}``.
    Entries carry ``text``, ``x``, ``y``, ``layer`` and ``source``; the
    coordinates are the DXF's own drawing units, which is all the position
    cross-check needs (it solves for the scale itself).
    """
    result = {"entries": [], "layers": [], "note": "", "error": ""}
    if not path or not os.path.isfile(path):
        result["error"] = "File not found: {0}".format(path or "(none)")
        return result
    if os.path.splitext(path)[1].lower() != ".dxf":
        result["error"] = ("Only DXF can be read directly. Save the DWG as DXF, "
                           "or scan the model's text instead.")
        return result
    try:
        import ezdxf
    except Exception as error:
        result["error"] = ("ezdxf isn't available on this engine ({0}). "
                           "Run this tool on the CPython 3 engine, or scan the "
                           "model's text instead.".format(str(error)[:80]))
        return result

    try:
        document = ezdxf.readfile(path)
    except Exception as error:
        result["error"] = "Couldn't read the DXF: {0}".format(str(error)[:160])
        return result

    wanted = set(name.strip().lower() for name in (layers or []) if name)
    seen_layers = {}
    entries = []

    def take(entity, source):
        if len(entries) >= limit:
            return
        text = _entity_text(entity)
        if not text or not text.strip():
            return
        try:
            layer = str(entity.dxf.layer)
        except Exception:
            layer = ""
        seen_layers[layer] = seen_layers.get(layer, 0) + 1
        if wanted and layer.strip().lower() not in wanted:
            return
        x, y = _entity_point(entity)
        entries.append({"text": text, "x": x, "y": y, "layer": layer,
                        "source": source})

    try:
        modelspace = document.modelspace()
    except Exception as error:
        result["error"] = "No modelspace in this DXF: {0}".format(str(error)[:120])
        return result

    for entity in modelspace:
        dxftype = entity.dxftype()
        if dxftype in ("TEXT", "MTEXT", "ATTDEF"):
            take(entity, "DXF")
        elif dxftype == "INSERT":
            try:
                for attribute in entity.attribs:
                    take(attribute, "DXF block attribute")
            except Exception:
                pass
            if include_blocks:
                try:
                    for nested in entity.virtual_entities():
                        if nested.dxftype() in ("TEXT", "MTEXT"):
                            take(nested, "DXF block")
                except Exception:
                    pass

    result["entries"] = entries
    result["layers"] = sorted(seen_layers.keys(), key=lambda name: name.lower())
    if len(entries) >= limit:
        result["note"] = ("stopped at {0} texts — narrow it down with a layer "
                          "filter".format(limit))
    else:
        result["note"] = "{0} text entit{1} on {2} layer(s)".format(
            len(entries), "y" if len(entries) == 1 else "ies", len(seen_layers))
    return result

# -*- coding: utf-8 -*-
"""Map DXF coordinates into Revit internal feet, and validate the mapping.

The Revit link we create carries a transform (ImportInstance.GetTotalTransform())
from the DXF's coordinate space to Revit internal feet. We use that as the primary
mapping for the text points and the ezdxf geometry. But the symbol-space-vs-feet
convention is API-version-sensitive, so we cross-check it against the two geometry
extractions: transform the DXF geometry's bounding box and compare it to the Revit
link geometry's bounding box. If they disagree grossly (a wrong scale factor), we
fall back to an empirical scale+translation derived directly from the two boxes --
which is exactly the "match the Revit and DXF extraction" the design calls for.

The matrix math is plain floats (no Revit objects), so it is unit-testable.
"""

# Gross-mismatch threshold: if the transformed-DXF bbox size differs from the
# Revit bbox size by more than this fraction on either axis, the API transform is
# wrong (usually a unit-scale mismatch) and we use the empirical fit instead.
_SIZE_MISMATCH_FRAC = 0.25


class Affine(object):
    """A 3x4 affine map: p' = M * (x, y, z) + t. Plain floats; Revit-free."""

    def __init__(self, rows):
        # rows = [[a, b, c, tx], [d, e, f, ty], [g, h, i, tz]]
        self.rows = rows

    def apply(self, point):
        x, y, z = point[0], point[1], point[2]
        r = self.rows
        return (r[0][0] * x + r[0][1] * y + r[0][2] * z + r[0][3],
                r[1][0] * x + r[1][1] * y + r[1][2] * z + r[1][3],
                r[2][0] * x + r[2][1] * y + r[2][2] * z + r[2][3])

    @classmethod
    def from_basis(cls, bx, by, bz, origin):
        """Build from Revit-style basis vectors + origin (each an (x, y, z))."""
        return cls([
            [bx[0], by[0], bz[0], origin[0]],
            [bx[1], by[1], bz[1], origin[1]],
            [bx[2], by[2], bz[2], origin[2]],
        ])

    @classmethod
    def scale_translate(cls, s, tx, ty, tz):
        """Uniform scale + translation, no rotation (the empirical fallback)."""
        return cls([[s, 0.0, 0.0, tx],
                    [0.0, s, 0.0, ty],
                    [0.0, 0.0, s, tz]])


def bbox_of_records(records):
    """Axis-aligned (xmin, ymin, xmax, ymax) over every point, or None if empty."""
    xs = []
    ys = []
    for record in records:
        for p in record.points:
            xs.append(p[0])
            ys.append(p[1])
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_after(affine, bbox):
    """Transform the four corners of a 2D bbox and return the new aligned bbox."""
    corners = [(bbox[0], bbox[1], 0.0), (bbox[2], bbox[1], 0.0),
               (bbox[2], bbox[3], 0.0), (bbox[0], bbox[3], 0.0)]
    moved = [affine.apply(c) for c in corners]
    xs = [m[0] for m in moved]
    ys = [m[1] for m in moved]
    return (min(xs), min(ys), max(xs), max(ys))


def empirical_affine(dxf_bbox, revit_bbox):
    """Uniform scale+translation aligning the DXF bbox onto the Revit bbox.

    Scale is the average of the per-axis size ratios (robust to one axis being
    near-zero); translation aligns the bbox centres. No rotation (auto Center- and
    Origin-placement never rotate).
    """
    dxf_w = dxf_bbox[2] - dxf_bbox[0]
    dxf_h = dxf_bbox[3] - dxf_bbox[1]
    rev_w = revit_bbox[2] - revit_bbox[0]
    rev_h = revit_bbox[3] - revit_bbox[1]
    ratios = []
    if dxf_w > 1e-9:
        ratios.append(rev_w / dxf_w)
    if dxf_h > 1e-9:
        ratios.append(rev_h / dxf_h)
    s = sum(ratios) / len(ratios) if ratios else 1.0

    dxf_cx = (dxf_bbox[0] + dxf_bbox[2]) / 2.0
    dxf_cy = (dxf_bbox[1] + dxf_bbox[3]) / 2.0
    rev_cx = (revit_bbox[0] + revit_bbox[2]) / 2.0
    rev_cy = (revit_bbox[1] + revit_bbox[3]) / 2.0
    tx = rev_cx - s * dxf_cx
    ty = rev_cy - s * dxf_cy
    # z: keep the DXF plane flat at the Revit geometry's plane (scaled, no offset).
    return Affine.scale_translate(s, tx, ty, 0.0)


def _size_mismatch(a_bbox, b_bbox):
    """Largest per-axis fractional size difference between two bboxes (0 = same)."""
    aw, ah = a_bbox[2] - a_bbox[0], a_bbox[3] - a_bbox[1]
    bw, bh = b_bbox[2] - b_bbox[0], b_bbox[3] - b_bbox[1]
    worst = 0.0
    for a, b in ((aw, bw), (ah, bh)):
        ref = max(abs(a), abs(b), 1e-9)
        worst = max(worst, abs(a - b) / ref)
    return worst


def from_link(import_instance):
    """Exact DXF-coords -> Revit-internal-feet affine from the link's OWN transform.

    This is authoritative for mapping the DXF's text points into Revit coordinates:
    the ImportInstance's GetTotalTransform() is precisely the matrix Revit applied
    when it linked the DXF (unit scale + placement), so no bbox guessing is needed.
    """
    t = import_instance.GetTotalTransform()
    bx, by, bz, origin = t.BasisX, t.BasisY, t.BasisZ, t.Origin
    return Affine.from_basis((bx.X, bx.Y, bx.Z), (by.X, by.Y, by.Z),
                             (bz.X, bz.Y, bz.Z), (origin.X, origin.Y, origin.Z))


def build_dxf_to_internal(import_instance, dxf_records, revit_records, logger=None):
    """Return (affine, diagnostics) mapping DXF coords -> Revit internal feet.

    Primary: the link's GetTotalTransform(). Validated against the geometry bboxes;
    on a gross size mismatch, falls back to the empirical bbox fit. Retained for
    diagnostics only -- element building now uses the Revit link geometry directly,
    and text uses from_link() above.
    """
    revit_transform = import_instance.GetTotalTransform()
    bx, by, bz = revit_transform.BasisX, revit_transform.BasisY, revit_transform.BasisZ
    origin = revit_transform.Origin
    api_affine = Affine.from_basis((bx.X, bx.Y, bx.Z), (by.X, by.Y, by.Z),
                                   (bz.X, bz.Y, bz.Z), (origin.X, origin.Y, origin.Z))

    dxf_bbox = bbox_of_records(dxf_records)
    revit_bbox = bbox_of_records(revit_records)
    diagnostics = {"method": "api_transform", "size_mismatch": None}

    if dxf_bbox is None or revit_bbox is None:
        if logger:
            logger.info("transform: missing geometry on one side; using API transform")
        return api_affine, diagnostics

    mismatch = _size_mismatch(_bbox_after(api_affine, dxf_bbox), revit_bbox)
    diagnostics["size_mismatch"] = mismatch
    if mismatch > _SIZE_MISMATCH_FRAC:
        affine = empirical_affine(dxf_bbox, revit_bbox)
        diagnostics["method"] = "empirical_bbox"
        if logger:
            logger.warning("transform: API transform off by {0:.0%}; using empirical "
                           "bbox fit".format(mismatch))
        return affine, diagnostics

    if logger:
        logger.info("transform: API transform OK (bbox size delta {0:.1%})".format(mismatch))
    return api_affine, diagnostics


def apply_to_records(affine, records):
    """Rewrite every record's points through the affine (in place); return records."""
    for record in records:
        record.points = [affine.apply(p) for p in record.points]
    return records


def apply_to_texts(affine, texts):
    """Fill each text's point_internal from its DXF point; return texts."""
    for text in texts:
        if text.point is not None:
            text.point_internal = affine.apply(text.point)
    return texts

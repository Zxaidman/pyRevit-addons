# -*- coding: utf-8 -*-
"""RoundElementDist - unit precision checker / corrector.

Sorts the selection into direction groups, gives each group its own datum and
its own measurement axis, then reports every off-precision distance before
anything moves. Elements joined to each other (core walls) are detected as
rigid sets and presented as a single approve/reject decision.

Version : 1.1.0
Target  : Revit 2025
Engine  : IronPython 2.7 AND CPython 3 compatible
          - no f-strings
          - no pyrevit.forms.ProgressBar
          - no ISelectionFilter / no subclassing of .NET types
            (both trigger "Duplicate type name within an assembly" on the 2nd
             run under the CPython engine)

CHANGES since 1.0.0
  - direction grouping: each parallel family gets its own datum + axis, so
    angled walls and columns are measured along their OWN normal
  - walls are read from the compound structure core (centreline or faces),
    NOT from tessellated solids - immune to wall/column joins
  - columns prefer uncut symbol geometry over join-cut top level solids
  - joined elements are clustered (union-find over JoinGeometryUtils and
    wall end joins) and moved as one rigid body, or left alone
  - clusters spanning two directions get a combined translation vector
  - touching pairs (gap ~ 0) are reported, never "corrected"
"""

__title__ = "Round\nElem Dist"
__author__ = "AnonGee"
__doc__ = ("Check element distances against a correct datum per direction "
           "group and round them to a design value. Reports first, you "
           "approve each fix. Joined core walls move as one body.")

__version__ = "1.1.0"

import math

import clr
clr.AddReference("System")
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")

import System.Windows.Forms as swf
import System.Drawing as sd

from Autodesk.Revit.DB import (
    ElementId, XYZ, Line, Options, ViewDetailLevel, Transaction,
    ElementTransformUtils, UnitUtils, UnitTypeId, Grid, FamilyInstance,
    Solid, GeometryInstance, Reference, ReferenceArray, ViewType,
    FamilyInstanceReferenceType, Level, Wall, JoinGeometryUtils,
    BuiltInParameter
)
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, script

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()
logger = script.get_logger()


# ---------------------------------------------------------------------------
# CONFIG - safe to edit
# ---------------------------------------------------------------------------

DEFAULT_INCREMENT = 5.0        # mm - one of 1 / 2 / 5 / 10
DEFAULT_DECIMALS = 3           # decimal places for the decimal rounding mode
DEFAULT_MAX_SHIFT = 25.0       # mm - never auto-move further than this
DEFAULT_ANGLE_TOL = 0.5        # deg - direction grouping tolerance
IGNORE_BELOW = 0.05            # mm - treat as already correct
TOUCHING_BELOW = 1.0           # mm - face gap this small means "touching"
DIM_OFFSET = 1500.0            # mm - dimension line offset from the datum


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

def to_mm(value_ft):
    return UnitUtils.ConvertFromInternalUnits(value_ft, UnitTypeId.Millimeters)


def to_ft(value_mm):
    return UnitUtils.ConvertToInternalUnits(value_mm, UnitTypeId.Millimeters)


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------

def _half_up(value):
    """round() is banker's rounding on Python 3 - this is not."""
    if value >= 0:
        return math.floor(value + 0.5)
    return math.ceil(value - 0.5)


def round_target(value_mm, mode, increment, decimals):
    if mode == "multiple":
        if increment <= 0:
            return value_mm
        return _half_up(value_mm / increment) * float(increment)
    factor = math.pow(10, decimals)
    return _half_up(value_mm * factor) / factor


# ---------------------------------------------------------------------------
# Angles / directions
# ---------------------------------------------------------------------------

def angle_of(vec):
    """Direction angle folded to [0, 180) degrees."""
    a = math.degrees(math.atan2(vec.Y, vec.X)) % 180.0
    if a < 0:
        a += 180.0
    return a


def angle_delta(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def axis_from_angle(deg):
    rad = math.radians(deg)
    return XYZ(math.cos(rad), math.sin(rad), 0).Normalize()


def element_normals(element):
    """Candidate in-plan normals for an element (directions it can be
    measured ALONG). A rectangular column returns two, so it takes part in
    both of its own runs."""
    try:
        if isinstance(element, Wall):
            crv = element.Location.Curve
            vec = crv.GetEndPoint(1) - crv.GetEndPoint(0)
            flat = XYZ(vec.X, vec.Y, 0)
            if flat.GetLength() < 1e-9:
                return []
            flat = flat.Normalize()
            return [XYZ(-flat.Y, flat.X, 0)]

        if isinstance(element, Grid):
            crv = element.Curve
            vec = crv.GetEndPoint(1) - crv.GetEndPoint(0)
            flat = XYZ(vec.X, vec.Y, 0)
            if flat.GetLength() < 1e-9:
                return []
            flat = flat.Normalize()
            return [XYZ(-flat.Y, flat.X, 0)]

        if isinstance(element, FamilyInstance):
            tr = element.GetTransform()
            out = []
            for basis in (tr.BasisX, tr.BasisY):
                flat = XYZ(basis.X, basis.Y, 0)
                if flat.GetLength() > 1e-9:
                    out.append(flat.Normalize())
            return out
    except Exception as err:
        logger.debug("normals failed on {}: {}".format(element.Id, err))
    return [XYZ.BasisX, XYZ.BasisY]


def build_direction_groups(elements, tol):
    """Return [{'angle':deg, 'axis':XYZ, 'elements':[...]}] sorted by size."""
    reps = []
    for el in elements:
        for nrm in element_normals(el):
            ang = angle_of(nrm)
            hit = False
            for r in reps:
                if angle_delta(ang, r) <= tol:
                    hit = True
                    break
            if not hit:
                reps.append(ang)

    groups = []
    for rep in reps:
        members = []
        for el in elements:
            for nrm in element_normals(el):
                if angle_delta(angle_of(nrm), rep) <= tol:
                    members.append(el)
                    break
        if members:
            groups.append({"angle": rep,
                           "axis": axis_from_angle(rep),
                           "elements": members})
    groups.sort(key=lambda g: -len(g["elements"]))
    return groups


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def geom_options():
    opt = Options()
    opt.ComputeReferences = True
    opt.IncludeNonVisibleObjects = False
    opt.DetailLevel = ViewDetailLevel.Fine
    return opt


def collect_solids(element, opt):
    """Prefer instance geometry (uncut by joins) over top level solids
    (which Revit has already trimmed where the element lost a join)."""
    top_solids = []
    inst_solids = []
    try:
        geo = element.get_Geometry(opt)
    except Exception:
        return []
    if geo is None:
        return []

    for g in geo:
        if isinstance(g, Solid):
            try:
                if g.Volume > 1e-9:
                    top_solids.append(g)
            except Exception:
                pass
        elif isinstance(g, GeometryInstance):
            try:
                for sub in g.GetInstanceGeometry():
                    if isinstance(sub, Solid) and sub.Volume > 1e-9:
                        inst_solids.append(sub)
            except Exception:
                pass

    return inst_solids if inst_solids else top_solids


def wall_core_scalars(wall, axis):
    """Core faces + core centreline of a wall projected onto axis, derived
    from the compound structure - never from cut solids."""
    try:
        crv = wall.Location.Curve
    except Exception:
        return None
    pnt = crv.Evaluate(0.5, True)

    try:
        orient = wall.Orientation
        width = wall.Width
    except Exception:
        return None
    if width is None or width <= 0:
        return None

    core_start = 0.0
    core_end = width
    try:
        cs = wall.WallType.GetCompoundStructure()
        if cs is not None:
            widths = [cs.GetLayerWidth(i) for i in range(cs.LayerCount)]
            first = cs.GetFirstCoreLayerIndex()
            last = cs.GetLastCoreLayerIndex()
            core_start = sum(widths[:first])
            core_end = sum(widths[:last + 1])
    except Exception:
        pass

    core_mid = (core_start + core_end) / 2.0

    # distance from the exterior face to the location line
    offset = width / 2.0
    try:
        par = wall.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM)
        if par is not None:
            key = par.AsInteger()
            offset = {0: width / 2.0,      # wall centreline
                      1: core_mid,         # core centreline
                      2: 0.0,              # finish face exterior
                      3: width,            # finish face interior
                      4: core_start,       # core exterior
                      5: core_end}.get(key, width / 2.0)
    except Exception:
        pass

    s_ext = (pnt + orient.Multiply(offset - core_start)).DotProduct(axis)
    s_int = (pnt + orient.Multiply(offset - core_end)).DotProduct(axis)
    s_mid = (pnt + orient.Multiply(offset - core_mid)).DotProduct(axis)
    return (min(s_ext, s_int), max(s_ext, s_int), s_mid)


def element_scalars(element, axis, opt):
    """(lo, hi, centre) projections onto axis, in feet."""
    if isinstance(element, Wall):
        return wall_core_scalars(element, axis)

    if isinstance(element, Grid):
        try:
            val = element.Curve.Evaluate(0.5, True).DotProduct(axis)
            return (val, val, val)
        except Exception:
            return None

    lo = None
    hi = None
    for solid in collect_solids(element, opt):
        for edge in solid.Edges:
            try:
                pts = edge.Tessellate()
            except Exception:
                continue
            for p in pts:
                d = p.DotProduct(axis)
                if lo is None or d < lo:
                    lo = d
                if hi is None or d > hi:
                    hi = d

    centre = None
    try:
        loc = element.Location
        if hasattr(loc, "Point") and loc.Point is not None:
            centre = loc.Point.DotProduct(axis)
        elif hasattr(loc, "Curve") and loc.Curve is not None:
            centre = loc.Curve.Evaluate(0.5, True).DotProduct(axis)
    except Exception:
        centre = None

    if lo is None or hi is None:
        bb = element.get_BoundingBox(None)
        if bb is not None:
            corners = []
            for x in (bb.Min.X, bb.Max.X):
                for y in (bb.Min.Y, bb.Max.Y):
                    for z in (bb.Min.Z, bb.Max.Z):
                        corners.append(XYZ(x, y, z))
            if bb.Transform is not None:
                corners = [bb.Transform.OfPoint(c) for c in corners]
            proj = [c.DotProduct(axis) for c in corners]
            lo = min(proj)
            hi = max(proj)

    if lo is None or hi is None:
        if centre is None:
            return None
        return (centre, centre, centre)
    if centre is None:
        centre = (lo + hi) / 2.0
    return (lo, hi, centre)


def element_point(element):
    try:
        loc = element.Location
        if hasattr(loc, "Point") and loc.Point is not None:
            return loc.Point
        if hasattr(loc, "Curve") and loc.Curve is not None:
            return loc.Curve.Evaluate(0.5, True)
    except Exception:
        pass
    bb = element.get_BoundingBox(None)
    if bb is not None:
        return (bb.Min + bb.Max).Multiply(0.5)
    return XYZ(0, 0, 0)


# ---------------------------------------------------------------------------
# Joined clusters (core walls)
# ---------------------------------------------------------------------------

def joined_neighbour_ids(element):
    ids = set()
    try:
        for eid in JoinGeometryUtils.GetJoinedElements(doc, element):
            ids.add(eid.IntegerValue)
    except Exception:
        pass
    if isinstance(element, Wall):
        try:
            loc = element.Location
            for end in (0, 1):
                for other in loc.ElementsAtJoin(end):
                    ids.add(other.Id.IntegerValue)
        except Exception:
            pass
    ids.discard(element.Id.IntegerValue)
    return ids


def build_clusters(elements):
    """Union-find over joins. Returns (clusters, open_flags).

    clusters   : list of lists of element ids (ints)
    open_flags : set of cluster indices that are joined to something OUTSIDE
                 the selection - moving those will shear at that boundary
    """
    ids = [e.Id.IntegerValue for e in elements]
    index = {}
    for i, eid in enumerate(ids):
        index[eid] = i
    parent = list(range(len(ids)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    outside = set()
    for el in elements:
        me = index[el.Id.IntegerValue]
        for nid in joined_neighbour_ids(el):
            if nid in index:
                union(me, index[nid])
            else:
                outside.add(me)

    buckets = {}
    for i, eid in enumerate(ids):
        buckets.setdefault(find(i), []).append(i)

    clusters = []
    open_flags = set()
    for root in buckets:
        members = buckets[root]
        ci = len(clusters)
        clusters.append([ids[i] for i in members])
        for i in members:
            if i in outside:
                open_flags.add(ci)
                break
    return clusters, open_flags


# ---------------------------------------------------------------------------
# WinForms - nothing here subclasses a .NET type, on purpose
# ---------------------------------------------------------------------------

def _label(text, x, y, w=185):
    lbl = swf.Label()
    lbl.Text = text
    lbl.Left = x
    lbl.Top = y + 3
    lbl.Width = w
    return lbl


def _combo(items, selected_index, x, y, w=215):
    cb = swf.ComboBox()
    cb.DropDownStyle = swf.ComboBoxStyle.DropDownList
    for it in items:
        cb.Items.Add(it)
    cb.SelectedIndex = selected_index
    cb.Left = x
    cb.Top = y
    cb.Width = w
    return cb


def _textbox(value, x, y, w=215):
    tb = swf.TextBox()
    tb.Text = str(value)
    tb.Left = x
    tb.Top = y
    tb.Width = w
    return tb


def settings_dialog():
    form = swf.Form()
    form.Text = "RoundElementDist  v" + __version__
    form.Width = 455
    form.Height = 390
    form.FormBorderStyle = swf.FormBorderStyle.FixedDialog
    form.StartPosition = swf.FormStartPosition.CenterScreen
    form.MaximizeBox = False
    form.MinimizeBox = False

    row = 15
    step = 32

    datum_items = ["Pick a correct ELEMENT per group",
                   "Pick a correct POINT per group"]
    ref_items = ["Centre to centre  (walls: core centreline)",
                 "Face to face  (walls: core faces)"]
    mode_items = ["Nearest multiple", "Decimal places"]
    incr_items = ["1", "2", "5", "10"]
    dec_items = ["0", "1", "2", "3"]

    form.Controls.Add(_label("Datum:", 15, row))
    cb_datum = _combo(datum_items, 0, 205, row)
    form.Controls.Add(cb_datum)
    row += step

    form.Controls.Add(_label("Reference:", 15, row))
    cb_ref = _combo(ref_items, 0, 205, row)
    form.Controls.Add(cb_ref)
    row += step

    form.Controls.Add(_label("Rounding mode:", 15, row))
    cb_mode = _combo(mode_items, 0, 205, row)
    form.Controls.Add(cb_mode)
    row += step

    form.Controls.Add(_label("Multiple of (mm):", 15, row))
    cb_incr = _combo(incr_items, incr_items.index(str(int(DEFAULT_INCREMENT))),
                     205, row)
    form.Controls.Add(cb_incr)
    row += step

    form.Controls.Add(_label("Decimal places:", 15, row))
    cb_dec = _combo(dec_items, DEFAULT_DECIMALS, 205, row)
    form.Controls.Add(cb_dec)
    row += step

    form.Controls.Add(_label("Max shift allowed (mm):", 15, row))
    tb_shift = _textbox(DEFAULT_MAX_SHIFT, 205, row)
    form.Controls.Add(tb_shift)
    row += step

    form.Controls.Add(_label("Direction tolerance (deg):", 15, row))
    tb_angle = _textbox(DEFAULT_ANGLE_TOL, 205, row)
    form.Controls.Add(tb_angle)
    row += step

    chk_dim = swf.CheckBox()
    chk_dim.Text = "Place dimensions for corrected elements"
    chk_dim.Left = 18
    chk_dim.Top = row
    chk_dim.Width = 340
    form.Controls.Add(chk_dim)
    row += step

    btn_ok = swf.Button()
    btn_ok.Text = "Continue"
    btn_ok.Left = 215
    btn_ok.Top = row
    btn_ok.Width = 95
    btn_ok.DialogResult = swf.DialogResult.OK
    form.Controls.Add(btn_ok)

    btn_cancel = swf.Button()
    btn_cancel.Text = "Cancel"
    btn_cancel.Left = 320
    btn_cancel.Top = row
    btn_cancel.Width = 95
    btn_cancel.DialogResult = swf.DialogResult.Cancel
    form.Controls.Add(btn_cancel)

    form.AcceptButton = btn_ok
    form.CancelButton = btn_cancel

    if form.ShowDialog() != swf.DialogResult.OK:
        return None

    try:
        max_shift = abs(float(tb_shift.Text))
    except Exception:
        max_shift = DEFAULT_MAX_SHIFT
    try:
        angle_tol = abs(float(tb_angle.Text))
    except Exception:
        angle_tol = DEFAULT_ANGLE_TOL

    return {
        "datum_is_point": cb_datum.SelectedIndex == 1,
        "reference": ["centre", "face"][cb_ref.SelectedIndex],
        "mode": ["multiple", "decimals"][cb_mode.SelectedIndex],
        "increment": float(incr_items[cb_incr.SelectedIndex]),
        "decimals": int(dec_items[cb_dec.SelectedIndex]),
        "max_shift": max_shift,
        "angle_tol": angle_tol,
        "place_dims": chk_dim.Checked,
    }


def checklist_dialog(title, header, rows, width=800):
    """Generic checked-list picker. Returns checked indices, or None."""
    form = swf.Form()
    form.Text = title
    form.Width = width
    form.Height = 540
    form.StartPosition = swf.FormStartPosition.CenterScreen

    lbl = swf.Label()
    lbl.Text = header
    lbl.Left = 12
    lbl.Top = 10
    lbl.Width = width - 40
    lbl.Height = 32
    form.Controls.Add(lbl)

    clb = swf.CheckedListBox()
    clb.Left = 12
    clb.Top = 46
    clb.Width = width - 44
    clb.Height = 390
    clb.CheckOnClick = True
    clb.Font = sd.Font("Consolas", 8.5)
    clb.HorizontalScrollbar = True
    for r in rows:
        clb.Items.Add(r, True)
    form.Controls.Add(clb)

    def _set_all(state):
        for i in range(clb.Items.Count):
            clb.SetItemChecked(i, state)

    btn_all = swf.Button()
    btn_all.Text = "Check all"
    btn_all.Left = 12
    btn_all.Top = 448
    btn_all.Width = 95
    btn_all.Click += lambda s, e: _set_all(True)
    form.Controls.Add(btn_all)

    btn_none = swf.Button()
    btn_none.Text = "Uncheck all"
    btn_none.Left = 115
    btn_none.Top = 448
    btn_none.Width = 95
    btn_none.Click += lambda s, e: _set_all(False)
    form.Controls.Add(btn_none)

    btn_ok = swf.Button()
    btn_ok.Text = "OK"
    btn_ok.Left = width - 250
    btn_ok.Top = 448
    btn_ok.Width = 110
    btn_ok.DialogResult = swf.DialogResult.OK
    form.Controls.Add(btn_ok)

    btn_cancel = swf.Button()
    btn_cancel.Text = "Cancel"
    btn_cancel.Left = width - 135
    btn_cancel.Top = 448
    btn_cancel.Width = 100
    btn_cancel.DialogResult = swf.DialogResult.Cancel
    form.Controls.Add(btn_cancel)

    form.AcceptButton = btn_ok
    form.CancelButton = btn_cancel

    if form.ShowDialog() != swf.DialogResult.OK:
        return None
    return [i for i in clb.CheckedIndices]


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

def centre_reference(element, axis):
    if isinstance(element, Grid):
        return Reference(element)
    if isinstance(element, Wall):
        try:
            return Reference(element)
        except Exception:
            return None
    if isinstance(element, FamilyInstance):
        try:
            tr = element.GetTransform()
            along_x = abs(tr.BasisX.DotProduct(axis)) >= \
                abs(tr.BasisY.DotProduct(axis))
            ref_type = (FamilyInstanceReferenceType.CenterLeftRight if along_x
                        else FamilyInstanceReferenceType.CenterFrontBack)
            refs = element.GetReferences(ref_type)
            if refs and refs.Count > 0:
                return refs[0]
        except Exception:
            pass
    return None


def place_dimension(view, axis, datum_element, target_element, datum_pt):
    if datum_element is None:
        return False
    ref_a = centre_reference(datum_element, axis)
    ref_b = centre_reference(target_element, axis)
    if ref_a is None or ref_b is None:
        return False
    perp = XYZ(-axis.Y, axis.X, 0).Normalize()
    base = datum_pt + perp.Multiply(to_ft(DIM_OFFSET))
    try:
        line = Line.CreateBound(base, base + axis.Multiply(to_ft(1000.0)))
        arr = ReferenceArray()
        arr.Append(ref_a)
        arr.Append(ref_b)
        doc.Create.NewDimension(view, line, arr)
        return True
    except Exception as err:
        logger.debug("dimension failed: {}".format(err))
        return False


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

def skip_reason(element):
    try:
        if element.Document.IsLinked:
            return "in a linked model"
    except Exception:
        pass
    try:
        if element.Pinned:
            return "pinned"
    except Exception:
        pass
    try:
        if element.GroupId is not None and \
                element.GroupId != ElementId.InvalidElementId:
            return "inside a group"
    except Exception:
        pass
    if isinstance(element, Level):
        return "level (not planar)"
    if isinstance(element, Wall):
        try:
            if element.IsStackedWall or element.IsStackedWallMember:
                return "stacked wall"
        except Exception:
            pass
        try:
            if element.CurtainGrid is not None:
                return "curtain wall"
        except Exception:
            pass
    return None


def cat_name(element):
    try:
        return element.Category.Name
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cfg = settings_dialog()
    if cfg is None:
        script.exit()

    opt = geom_options()
    view = doc.ActiveView
    is_plan = view.ViewType in (ViewType.FloorPlan, ViewType.CeilingPlan,
                                ViewType.EngineeringPlan, ViewType.AreaPlan)

    # --- 1. selection -------------------------------------------------------
    pre_ids = list(uidoc.Selection.GetElementIds())
    if pre_ids:
        selection = [doc.GetElement(eid) for eid in pre_ids]
    else:
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, "Select the elements to CHECK")
            selection = [doc.GetElement(r.ElementId) for r in refs]
        except OperationCanceledException:
            script.exit()
    selection = [e for e in selection if e is not None]
    if not selection:
        swf.MessageBox.Show("Nothing selected.", "RoundElementDist")
        script.exit()

    by_id = {}
    for el in selection:
        by_id[el.Id.IntegerValue] = el

    # --- 2. clusters --------------------------------------------------------
    clusters, open_flags = build_clusters(selection)
    cluster_of = {}
    for ci, members in enumerate(clusters):
        for eid in members:
            cluster_of[eid] = ci

    # --- 3. direction groups ------------------------------------------------
    groups = build_direction_groups(selection, cfg["angle_tol"])
    if not groups:
        swf.MessageBox.Show("Could not read any direction from the selection.",
                            "RoundElementDist")
        script.exit()

    grows = []
    for g in groups:
        grows.append("{:>7.2f} deg   {:>4} elements".format(
            g["angle"], len(g["elements"])))
    picked = checklist_dialog(
        "Direction groups  -  v" + __version__,
        "Each ticked group gets its own datum and is measured along its own "
        "normal.",
        grows, width=520)
    if picked is None or not picked:
        script.exit()
    groups = [groups[i] for i in picked]

    # --- 4. datum + evaluate per group -------------------------------------
    # delta_by_element[eid] = list of (axis, delta_mm) - one per group
    results = []
    group_info = []
    for g in groups:
        axis = g["axis"]
        label = "{:.2f} deg".format(g["angle"])

        datum_element = None
        datum_pt = None
        try:
            if cfg["datum_is_point"]:
                datum_pt = uidoc.Selection.PickPoint(
                    "Group {} - pick the CORRECT point".format(label))
            else:
                ref = uidoc.Selection.PickObject(
                    ObjectType.Element,
                    "Group {} - pick the CORRECT element".format(label))
                datum_element = doc.GetElement(ref.ElementId)
        except OperationCanceledException:
            continue

        if datum_pt is not None:
            d_lo = d_hi = d_centre = datum_pt.DotProduct(axis)
        else:
            d_sc = element_scalars(datum_element, axis, opt)
            if d_sc is None:
                continue
            d_lo, d_hi, d_centre = d_sc
            datum_pt = element_point(datum_element)

        warn = ""
        if datum_element is not None:
            ok_dir = False
            for nrm in element_normals(datum_element):
                if angle_delta(angle_of(nrm), g["angle"]) <= cfg["angle_tol"]:
                    ok_dir = True
                    break
            if not ok_dir:
                warn = "  (datum is not parallel to this group)"

        group_info.append({"label": label, "axis": axis, "warn": warn,
                           "datum_element": datum_element,
                           "datum_pt": datum_pt})
        gi = len(group_info) - 1

        for el in g["elements"]:
            eid = el.Id.IntegerValue
            if datum_element is not None and eid == datum_element.Id.IntegerValue:
                continue

            rec = {"el": el, "id": el.Id, "eid": eid, "gi": gi,
                   "name": cat_name(el), "status": "", "cur": 0.0,
                   "target": 0.0, "delta": 0.0, "side": 1,
                   "cluster": cluster_of.get(eid, -1)}

            reason = skip_reason(el)
            if reason:
                rec["status"] = "SKIP - " + reason
                results.append(rec)
                continue

            sc = element_scalars(el, axis, opt)
            if sc is None:
                rec["status"] = "SKIP - no geometry"
                results.append(rec)
                continue

            t_lo, t_hi, t_centre = sc
            side = 1 if (t_centre - d_centre) >= 0 else -1
            rec["side"] = side

            if cfg["reference"] == "face":
                cur_ft = (t_lo - d_hi) if side > 0 else (t_hi - d_lo)
            else:
                cur_ft = t_centre - d_centre

            cur_mm = abs(to_mm(cur_ft))
            rec["cur"] = cur_mm

            if cfg["reference"] == "face" and cur_mm < TOUCHING_BELOW:
                rec["status"] = "TOUCHING - not corrected"
                results.append(rec)
                continue

            tgt_mm = round_target(cur_mm, cfg["mode"], cfg["increment"],
                                  cfg["decimals"])
            delta_mm = tgt_mm - cur_mm
            rec["target"] = tgt_mm
            rec["delta"] = delta_mm

            if abs(delta_mm) <= IGNORE_BELOW:
                rec["status"] = "OK"
            elif abs(delta_mm) > cfg["max_shift"]:
                rec["status"] = "REVIEW - beyond max shift"
            else:
                rec["status"] = "FIX"
            results.append(rec)

    if not results:
        output.print_md("**No groups processed.**")
        return

    # --- 5. report ----------------------------------------------------------
    output.print_md("## RoundElementDist v{}".format(__version__))
    for i, gi in enumerate(group_info):
        dtxt = ("picked point" if gi["datum_element"] is None
                else "{} (id {})".format(cat_name(gi["datum_element"]),
                                         gi["datum_element"].Id.IntegerValue))
        output.print_md("- **group {}** - datum: {}{}".format(
            gi["label"], dtxt, gi["warn"]))
    output.print_md(
        "**Reference:** {}  |  **Rounding:** {}  |  **Max shift:** {:g} mm"
        .format(cfg["reference"],
                ("multiple of {:g} mm".format(cfg["increment"])
                 if cfg["mode"] == "multiple"
                 else "{} decimals".format(cfg["decimals"])),
                cfg["max_shift"]))

    table = []
    for r in sorted(results, key=lambda x: (x["gi"], x["cur"])):
        skipped = r["status"].startswith("SKIP") or \
            r["status"].startswith("TOUCHING")
        cl = r["cluster"]
        cl_txt = "-"
        if cl >= 0 and len(clusters[cl]) > 1:
            cl_txt = "set {}{}".format(cl, "!" if cl in open_flags else "")
        table.append([
            output.linkify(r["id"]),
            r["name"],
            group_info[r["gi"]]["label"],
            cl_txt,
            "{:.3f}".format(r["cur"]),
            "-" if skipped else "{:.3f}".format(r["target"]),
            "-" if skipped else "{:+.3f}".format(r["delta"]),
            r["status"],
        ])
    output.print_table(
        table_data=table,
        title="Distances from datum",
        columns=["Id", "Category", "Group", "Joined set", "Current (mm)",
                 "Target (mm)", "Shift (mm)", "Status"])

    fixable = [r for r in results if r["status"] == "FIX"]
    if not fixable:
        output.print_md("**Nothing to correct.**")
        return

    # --- 6. build actions ---------------------------------------------------
    # a joined set moves as one rigid body: one controlling delta per group it
    # takes part in, summed into a single translation vector
    actions = []
    singles = []
    set_recs = {}
    for r in fixable:
        cl = r["cluster"]
        if cl >= 0 and len(clusters[cl]) > 1:
            set_recs.setdefault(cl, []).append(r)
        else:
            singles.append(r)

    for r in singles:
        axis = group_info[r["gi"]]["axis"]
        actions.append({
            "kind": "single",
            "members": [r["id"]],
            "vector": axis.Multiply(to_ft(r["delta"] * r["side"])),
            "row": "{:<10} {:<14} {:>9} {:>12} -> {:>12}  ({:+.3f} mm)".format(
                r["eid"], r["name"][:14], group_info[r["gi"]]["label"],
                "{:.3f}".format(r["cur"]), "{:.3f}".format(r["target"]),
                r["delta"]),
        })

    for cl in sorted(set_recs.keys()):
        recs = set_recs[cl]
        vector = XYZ(0, 0, 0)
        parts = []
        for gi in sorted(set(r["gi"] for r in recs)):
            in_group = [r for r in recs if r["gi"] == gi]
            ctrl = min(in_group, key=lambda r: r["cur"])
            deltas = [r["delta"] for r in in_group]
            axis = group_info[gi]["axis"]
            vector = vector + axis.Multiply(to_ft(ctrl["delta"] * ctrl["side"]))
            parts.append("{} {:+.3f} (spread {:.3f})".format(
                group_info[gi]["label"], ctrl["delta"],
                max(deltas) - min(deltas)))
        member_ids = [by_id[e].Id for e in clusters[cl] if e in by_id]
        actions.append({
            "kind": "set",
            "members": member_ids,
            "vector": vector,
            "row": "SET {:<3}{} {:>2} elems  rigid move:  {}".format(
                cl, "!" if cl in open_flags else " ",
                len(member_ids), "   ".join(parts)),
        })

    # --- 7. approve ---------------------------------------------------------
    header = ("Ticked rows will be moved. SET rows move every member together "
              "as one rigid body.\n"
              "A ! means the set is also joined to elements OUTSIDE your "
              "selection - moving it will shear at that boundary.")
    approved = checklist_dialog("Approve fixes  -  v" + __version__,
                                header, [a["row"] for a in actions])
    if approved is None:
        output.print_md("**Cancelled - nothing moved.**")
        return
    if not approved:
        output.print_md("**No fixes selected - nothing moved.**")
        return

    # --- 8. apply -----------------------------------------------------------
    moved = 0
    sets_moved = 0
    dims = 0
    failed = []
    trans = Transaction(doc, "RoundElementDist {}".format(__version__))
    trans.Start()
    try:
        for i in approved:
            act = actions[i]
            try:
                ids = List_of(act["members"])
                ElementTransformUtils.MoveElements(doc, ids, act["vector"])
                moved += len(act["members"])
                if act["kind"] == "set":
                    sets_moved += 1
            except Exception as err:
                failed.append((act["row"][:40], str(err)))

        if cfg["place_dims"] and is_plan:
            for i in approved:
                act = actions[i]
                if act["kind"] != "single":
                    continue
                rec = None
                for r in singles:
                    if r["id"] in act["members"]:
                        rec = r
                        break
                if rec is None:
                    continue
                gi = group_info[rec["gi"]]
                if place_dimension(view, gi["axis"], gi["datum_element"],
                                   rec["el"], gi["datum_pt"]):
                    dims += 1
        trans.Commit()
    except Exception as err:
        trans.RollBack()
        output.print_md("**Transaction rolled back:** {}".format(err))
        return

    output.print_md("### Result")
    output.print_md("- elements moved: **{}**".format(moved))
    output.print_md("- joined sets moved rigidly: **{}**".format(sets_moved))
    if cfg["place_dims"]:
        output.print_md("- dimensions placed: **{}**{}".format(
            dims, "" if is_plan else "  (active view is not a plan)"))
    if failed:
        output.print_md("- failed: **{}**".format(len(failed)))
        for row, msg in failed:
            output.print_md("  - {} : {}".format(row, msg))


def List_of(element_ids):
    """ICollection<ElementId> for MoveElements, built without importing
    generics at module level."""
    from System.Collections.Generic import List as NetList
    out = NetList[ElementId]()
    for eid in element_ids:
        out.Add(eid)
    return out


main()
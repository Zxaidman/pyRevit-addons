#! python3
# -*- coding: utf-8 -*-
"""Convert Structural Floor <-> Structural Foundation (slab).

Revit has no in-place category swap: Floors live in OST_Floors and foundation
slabs in OST_StructuralFoundation, so the element must be recreated. This tool
reads everything off the source (sketch loops + openings, level, offset, slope
arrow, slab shape edits, all writable parameters, joins, pin state), builds the
counterpart, replays it, then deletes the original -- reporting anything that
could not survive the round trip BEFORE it touches the model.

Engine : CPython 3 (pyRevit)
Revit  : 2022+ (developed against 2025)
"""

__title__ = "Convert\nSlab"
__author__ = "AnonGee"
__version__ = "1.0.0"
__min_revit_ver__ = 2022
__doc__ = ("Convert selected Structural Floors to Structural Foundation slabs "
           "and vice versa. Shows a pre-flight report and asks for confirmation "
           "before modifying anything.")

import os
import json
import traceback

from pyrevit import revit, DB, UI, forms, script

from System.Collections.Generic import List

# ---------------------------------------------------------------------------
# globals
# ---------------------------------------------------------------------------

TOOL_VERSION = "1.0.0"

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

CFG_NAME = "slab_convert_config.json"
CFG_PATH = os.path.join(os.path.dirname(__file__), CFG_NAME)

PT_TOL = 1e-6          # feet, endpoint matching for loop building
XY_TOL = 1e-4          # feet, vertex matching for shape edits
Z_NORMAL_TOL = 1e-6

DEFAULT_CFG = {
    "_readme": [
        "Config for Convert Slab v{0}.".format(TOOL_VERSION),
        "Type resolution order: 1) exact name from the convention below,",
        "2) identical compound structure, 3) same total thickness within",
        "tolerance, 4) duplicate a seed type of the target category and copy",
        "the source's compound structure (same thickness + materials)."
    ],
    "thickness_tolerance_mm": 0.5,
    "require_identical_layers": False,
    "prefer_name_match": True,
    "create_missing_types": True,
    "swallow_warnings": True,
    "select_results_after_run": True,
    "floor_to_foundation": {
        "strip_prefixes": ["FLR_", "FLR-", "FLOOR_", "SLAB_"],
        "strip_suffixes": [],
        "prefix": "FND_",
        "suffix": ""
    },
    "foundation_to_floor": {
        "strip_prefixes": ["FND_", "FND-", "FOUNDATION_", "FOOTING_"],
        "strip_suffixes": [],
        "prefix": "FLR_",
        "suffix": ""
    }
}

FLOOR = "FLOOR"
FOUNDATION = "FOUNDATION"

# ---------------------------------------------------------------------------
# tiny utils
# ---------------------------------------------------------------------------


def eid_val(eid):
    """ElementId -> int, across the 2024 Value/IntegerValue split."""
    if eid is None:
        return -1
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def bic_id(bic):
    return eid_val(DB.ElementId(bic))


CAT_FLOORS = bic_id(DB.BuiltInCategory.OST_Floors)
CAT_FND = bic_id(DB.BuiltInCategory.OST_StructuralFoundation)

CAT_REBAR = set()
for _c in ("OST_Rebar", "OST_AreaRein", "OST_PathRein",
           "OST_FabricAreas", "OST_FabricReinforcement"):
    try:
        CAT_REBAR.add(bic_id(getattr(DB.BuiltInCategory, _c)))
    except Exception:
        pass
CAT_PARTS = bic_id(DB.BuiltInCategory.OST_Parts)
CAT_EDGESLAB = bic_id(DB.BuiltInCategory.OST_EdgeSlab)

INVALID = DB.ElementId.InvalidElementId


def el_name(e):
    """Element.Name across IronPython / pythonnet quirks."""
    if e is None:
        return "?"
    try:
        n = e.Name
        if n:
            return n
    except Exception:
        pass
    try:
        return DB.Element.Name.GetValue(e)
    except Exception:
        pass
    try:
        p = e.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        return p.AsString() if p else "?"
    except Exception:
        return "?"


def mm_to_ft(v):
    try:
        return DB.UnitUtils.ConvertToInternalUnits(v, DB.UnitTypeId.Millimeters)
    except Exception:
        return v / 304.8


def ft_to_mm(v):
    try:
        return DB.UnitUtils.ConvertFromInternalUnits(v, DB.UnitTypeId.Millimeters)
    except Exception:
        return v * 304.8


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    if os.path.isfile(CFG_PATH):
        try:
            with open(CFG_PATH, "r") as fh:
                user = json.load(fh)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception:
            forms.alert("{0} is not valid JSON - using defaults.".format(CFG_NAME),
                        title="Convert Slab")
    else:
        try:
            with open(CFG_PATH, "w") as fh:
                json.dump(DEFAULT_CFG, fh, indent=2)
        except Exception:
            pass
    return cfg


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------


def slab_kind(el):
    """FLOOR / FOUNDATION / None. Only sketch-based slabs qualify."""
    if not isinstance(el, DB.Floor):
        return None
    if el.Category is None:
        return None
    c = eid_val(el.Category.Id)
    if c == CAT_FLOORS:
        return FLOOR
    if c == CAT_FND:
        return FOUNDATION
    return None


def target_kind(kind):
    return FOUNDATION if kind == FLOOR else FLOOR


def target_cat_id(kind):
    return CAT_FND if kind == FLOOR else CAT_FLOORS


def target_bic(kind):
    return (DB.BuiltInCategory.OST_StructuralFoundation if kind == FLOOR
            else DB.BuiltInCategory.OST_Floors)


class SlabSelFilter(UI.Selection.ISelectionFilter):
    __namespace__ = "SlabConvert"

    def AllowElement(self, e):
        return slab_kind(e) is not None

    def AllowReference(self, ref, pt):
        return False


def gather_selection():
    ids = list(uidoc.Selection.GetElementIds())
    if ids:
        return [doc.GetElement(i) for i in ids]
    try:
        try:
            refs = uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.Element, SlabSelFilter(),
                "Pick structural floors / foundation slabs, then Finish")
        except Exception:
            refs = uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.Element,
                "Pick structural floors / foundation slabs, then Finish")
        return [doc.GetElement(r.ElementId) for r in refs]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# geometry / sketch reading
# ---------------------------------------------------------------------------


def get_sketch(el):
    sid = getattr(el, "SketchId", None)
    if sid is not None and eid_val(sid) > 0:
        sk = doc.GetElement(sid)
        if isinstance(sk, DB.Sketch):
            return sk
    try:
        for did in el.GetDependentElements(DB.ElementClassFilter(DB.Sketch)):
            sk = doc.GetElement(did)
            if isinstance(sk, DB.Sketch):
                return sk
    except Exception:
        pass
    try:
        for did in el.GetDependentElements(None):
            sk = doc.GetElement(did)
            if isinstance(sk, DB.Sketch):
                return sk
    except Exception:
        pass
    return None


def build_loop(curves):
    """Order an unordered curve bag head-to-tail into a CurveLoop."""
    remaining = list(curves)
    if not remaining:
        return None
    cl = DB.CurveLoop()
    cur = remaining.pop(0)
    cl.Append(cur)
    end = cur.GetEndPoint(1)
    guard = len(remaining) + 1
    while remaining and guard > 0:
        guard -= 1
        picked = None
        for i, c in enumerate(remaining):
            if c.GetEndPoint(0).DistanceTo(end) < PT_TOL:
                picked = (i, c)
                break
            if c.GetEndPoint(1).DistanceTo(end) < PT_TOL:
                picked = (i, c.CreateReversed())
                break
        if picked is None:
            raise Exception("sketch loop is not closed / not orderable")
        i, c = picked
        remaining.pop(i)
        cl.Append(c)
        end = c.GetEndPoint(1)
    if remaining:
        raise Exception("sketch loop is not closed / not orderable")
    return cl


def read_profile(sketch):
    """CurveArrArray -> (loops, base_z). Slope arrow is excluded."""
    loops = []
    base_z = None
    for arr in sketch.Profile:
        curves = [c for c in arr]
        if not curves:
            continue
        if len(curves) == 1:
            c = curves[0]
            if c.GetEndPoint(0).DistanceTo(c.GetEndPoint(1)) > PT_TOL:
                # open single curve -> slope arrow leaked into the profile
                continue
        loop = build_loop(curves)
        if loop is None:
            continue
        for c in loop:
            for i in (0, 1):
                z = c.GetEndPoint(i).Z
                if base_z is None:
                    base_z = z
                elif abs(z - base_z) > 1e-5:
                    raise Exception("sketch is not horizontal")
        loops.append(loop)
    if not loops:
        raise Exception("no closed boundary found in sketch")
    return loops, (base_z or 0.0)


def find_slope_arrow(sketch):
    """The only sketch curve carrying SPECIFY_SLOPE_OR_OFFSET is the arrow."""
    try:
        eids = sketch.GetAllElements()
    except Exception:
        return None
    for eid in eids:
        el = doc.GetElement(eid)
        if not isinstance(el, DB.CurveElement):
            continue
        p = el.get_Parameter(DB.BuiltInParameter.SPECIFY_SLOPE_OR_OFFSET)
        if p is not None:
            gc = el.GeometryCurve
            if isinstance(gc, DB.Line):
                return gc
    return None


def read_shape_edits(el, base_z):
    """Capture slab shape editor state as plain data."""
    try:
        ed = el.SlabShapeEditor
    except Exception:
        return None
    if ed is None:
        return None
    try:
        if not ed.IsEnabled:
            return None
    except Exception:
        return None
    verts = []
    try:
        for v in ed.SlabShapeVertices:
            p = v.Position
            verts.append((p.X, p.Y, p.Z - base_z))
    except Exception:
        return None
    creases = []
    try:
        for c in ed.SlabShapeCreases:
            crv = c.Curve
            a = crv.GetEndPoint(0)
            b = crv.GetEndPoint(1)
            ctype = str(c.CreaseType)
            creases.append(((a.X, a.Y, a.Z - base_z),
                            (b.X, b.Y, b.Z - base_z), ctype))
    except Exception:
        pass
    if not verts:
        return None
    return {"vertices": verts, "creases": creases}


def apply_shape_edits(new_el, data, base_z):
    """Replay vertex offsets / added points onto the new slab."""
    if not data:
        return True, ""
    try:
        ed = new_el.SlabShapeEditor
        if ed is None:
            return False, "target has no slab shape editor"
        ed.Enable()
        doc.Regenerate()
    except Exception as ex:
        return False, "enable failed: {0}".format(ex)

    ok = True
    notes = []
    for (x, y, dz) in data["vertices"]:
        try:
            match = None
            for v in ed.SlabShapeVertices:
                p = v.Position
                if abs(p.X - x) < XY_TOL and abs(p.Y - y) < XY_TOL:
                    match = v
                    break
            if match is not None:
                if abs(dz) > 1e-9:
                    ed.ModifySubElement(match, dz)
            else:
                ed.DrawPoint(DB.XYZ(x, y, base_z + dz))
            doc.Regenerate()
        except Exception as ex:
            ok = False
            notes.append(str(ex))

    for (a, b, _ctype) in data.get("creases", []):
        try:
            va = vb = None
            for v in ed.SlabShapeVertices:
                p = v.Position
                if va is None and abs(p.X - a[0]) < XY_TOL and abs(p.Y - a[1]) < XY_TOL:
                    va = v
                if vb is None and abs(p.X - b[0]) < XY_TOL and abs(p.Y - b[1]) < XY_TOL:
                    vb = v
            if va is not None and vb is not None:
                ed.DrawSplitLine(va, vb)
                doc.Regenerate()
        except Exception:
            pass

    return ok, "; ".join(notes[:2])


# ---------------------------------------------------------------------------
# dependents / joins
# ---------------------------------------------------------------------------


def classify_dependents(el):
    """-> dict of lists: rebar, tags, dims, openings, hosted, parts, other"""
    res = {"rebar": [], "tags": [], "dims": [], "openings": [],
           "hosted": [], "parts": [], "slab_edges": [], "analytical": []}
    try:
        deps = list(el.GetDependentElements(None))
    except Exception:
        return res
    for did in deps:
        if eid_val(did) == eid_val(el.Id):
            continue
        d = doc.GetElement(did)
        if d is None:
            continue
        if isinstance(d, (DB.Sketch, DB.SketchPlane, DB.CurveElement)):
            continue
        cat = d.Category
        cid = eid_val(cat.Id) if cat is not None else -1

        if isinstance(d, DB.Opening):
            res["openings"].append(did)
        elif cid in CAT_REBAR:
            res["rebar"].append(did)
        elif cid == CAT_PARTS:
            res["parts"].append(did)
        elif cid == CAT_EDGESLAB:
            res["slab_edges"].append(did)
        elif isinstance(d, DB.Dimension):
            res["dims"].append(did)
        elif cat is not None and cat.CategoryType == DB.CategoryType.Annotation:
            res["tags"].append(did)
        elif isinstance(d, DB.FamilyInstance):
            res["hosted"].append(did)
        elif "Analytical" in d.GetType().Name:
            res["analytical"].append(did)
    return res


def read_joins(el):
    out = []
    try:
        for oid in DB.JoinGeometryUtils.GetJoinedElements(doc, el):
            other = doc.GetElement(oid)
            if other is None:
                continue
            cutting = DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, el, other)
            out.append((oid, cutting))
    except Exception:
        pass
    return out


def restore_joins(new_el, joins):
    restored = 0
    for oid, was_cutting in joins:
        other = doc.GetElement(oid)
        if other is None:
            continue
        try:
            if not DB.JoinGeometryUtils.AreElementsJoined(doc, new_el, other):
                DB.JoinGeometryUtils.JoinGeometry(doc, new_el, other)
            now = DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, new_el, other)
            if now != was_cutting:
                DB.JoinGeometryUtils.SwitchJoinOrder(doc, new_el, other)
            restored += 1
        except Exception:
            pass
    return restored


def read_openings(ids):
    data = []
    for oid in ids:
        op = doc.GetElement(oid)
        if not isinstance(op, DB.Opening):
            continue
        try:
            curves = op.BoundaryCurves
            if curves is None or curves.Size == 0:
                continue
            arr = DB.CurveArray()
            for c in curves:
                arr.Append(c)
            data.append(arr)
        except Exception:
            pass
    return data


# ---------------------------------------------------------------------------
# type resolution
# ---------------------------------------------------------------------------


def conventional_name(src_name, kind, cfg):
    rule = cfg["floor_to_foundation"] if kind == FLOOR else cfg["foundation_to_floor"]
    base = src_name
    for p in rule.get("strip_prefixes", []):
        if base.upper().startswith(p.upper()):
            base = base[len(p):]
            break
    for s in rule.get("strip_suffixes", []):
        if s and base.upper().endswith(s.upper()):
            base = base[:-len(s)]
            break
    return "{0}{1}{2}".format(rule.get("prefix", ""), base.strip(),
                              rule.get("suffix", ""))


def collect_types(cat_id):
    out = []
    for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType):
        if t.Category is not None and eid_val(t.Category.Id) == cat_id:
            out.append(t)
    return out


def cs_width(ftype):
    try:
        cs = ftype.GetCompoundStructure()
        if cs is not None:
            return cs.GetWidth()
    except Exception:
        pass
    p = ftype.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_DEFAULT_THICKNESS_PARAM)
    return p.AsDouble() if p else 0.0


def cs_signature(ftype):
    try:
        cs = ftype.GetCompoundStructure()
        if cs is None:
            return None
        sig = []
        for i in range(cs.LayerCount):
            sig.append((round(cs.GetLayerWidth(i), 9),
                        eid_val(cs.GetMaterialId(i)),
                        str(cs.GetLayerFunction(i))))
        return tuple(sig)
    except Exception:
        return None


def resolve_type(src_type, kind, cfg, created_cache):
    """-> (FloorType or None, note, is_new)"""
    cat_id = target_cat_id(kind)
    cands = collect_types(cat_id)
    want_name = conventional_name(el_name(src_type), kind, cfg)

    if want_name in created_cache:
        return created_cache[want_name], "reused new type", False

    if cfg.get("prefer_name_match", True):
        for t in cands:
            if el_name(t).strip().lower() == want_name.strip().lower():
                return t, "name match", False

    src_sig = cs_signature(src_type)
    if src_sig is not None:
        for t in cands:
            if cs_signature(t) == src_sig:
                return t, "identical layers", False

    if not cfg.get("require_identical_layers", False):
        tol = mm_to_ft(float(cfg.get("thickness_tolerance_mm", 0.5)))
        src_w = cs_width(src_type)
        best, best_d = None, None
        for t in cands:
            d = abs(cs_width(t) - src_w)
            if d <= tol and (best_d is None or d < best_d):
                best, best_d = t, d
        if best is not None:
            return best, "thickness match ({0:.1f} mm)".format(ft_to_mm(src_w)), False

    if not cfg.get("create_missing_types", True):
        return None, "no matching type and creation disabled", False
    if not cands:
        return None, ("no type exists in the target category - create one "
                      "Foundation Slab / Floor type first"), False

    return ("CREATE", want_name, True)


TYPE_PARAMS_TO_COPY = [
    DB.BuiltInParameter.ALL_MODEL_TYPE_COMMENTS,
    DB.BuiltInParameter.ALL_MODEL_DESCRIPTION,
    DB.BuiltInParameter.ALL_MODEL_TYPE_MARK,
    DB.BuiltInParameter.KEYNOTE_PARAM,
    DB.BuiltInParameter.UNIFORMAT_CODE,
    DB.BuiltInParameter.UNIFORMAT_DESCRIPTION,
    DB.BuiltInParameter.ALL_MODEL_MANUFACTURER,
    DB.BuiltInParameter.ALL_MODEL_MODEL,
    DB.BuiltInParameter.ALL_MODEL_COST,
    DB.BuiltInParameter.FIRE_RATING,
]


def create_target_type(src_type, kind, new_name):
    cands = collect_types(target_cat_id(kind))
    seed = cands[0]
    name = new_name
    existing = set(el_name(t).lower()
                   for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType))
    n = 2
    while name.lower() in existing:
        name = "{0} {1}".format(new_name, n)
        n += 1
    new_type = seed.Duplicate(name)
    try:
        cs = src_type.GetCompoundStructure()
        if cs is not None:
            new_type.SetCompoundStructure(cs)
    except Exception:
        pass
    for bip in TYPE_PARAMS_TO_COPY:
        try:
            sp = src_type.get_Parameter(bip)
            tp = new_type.get_Parameter(bip)
            if sp and tp and not tp.IsReadOnly and sp.HasValue:
                copy_param(sp, tp)
        except Exception:
            pass
    return new_type


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------

# Matched on enum *name* rather than int: str(enum) is reliable on both
# IronPython and pythonnet, int(enum) is not.
SKIP_BIPS = set([
    "ELEM_FAMILY_PARAM", "ELEM_TYPE_PARAM", "ELEM_FAMILY_AND_TYPE_PARAM",
    "ELEM_CATEGORY_PARAM", "ELEM_CATEGORY_PARAM_MT", "ID_PARAM",
    "LEVEL_PARAM", "SCHEDULE_LEVEL_PARAM", "SKETCH_PLANE_PARAM",
    "FLOOR_ATTR_THICKNESS_PARAM", "FLOOR_ATTR_DEFAULT_THICKNESS_PARAM",
    "HOST_AREA_COMPUTED", "HOST_VOLUME_COMPUTED", "HOST_PERIMETER_COMPUTED",
    "DESIGN_OPTION_ID", "EDITED_BY", "ELEM_TYPE_LABEL", "ROOF_SLOPE",
    "ELEMENT_LOCKED_PARAM", "STRUCTURAL_ANALYTICAL_MODEL",
])


def copy_param(sp, tp):
    st = sp.StorageType
    if st == DB.StorageType.Double:
        tp.Set(sp.AsDouble())
    elif st == DB.StorageType.Integer:
        tp.Set(sp.AsInteger())
    elif st == DB.StorageType.String:
        v = sp.AsString()
        tp.Set(v if v is not None else "")
    elif st == DB.StorageType.ElementId:
        tp.Set(sp.AsElementId())


def find_target_param(new_el, sp):
    d = sp.Definition
    try:
        if isinstance(d, DB.InternalDefinition) and \
                d.BuiltInParameter != DB.BuiltInParameter.INVALID:
            tp = new_el.get_Parameter(d.BuiltInParameter)
            if tp is not None:
                return tp
    except Exception:
        pass
    try:
        if sp.IsShared:
            tp = new_el.get_Parameter(sp.GUID)
            if tp is not None:
                return tp
    except Exception:
        pass
    try:
        return new_el.LookupParameter(d.Name)
    except Exception:
        return None


def copy_instance_params(src, new_el):
    """-> (copied, skipped_names)"""
    copied = 0
    missed = []

    # phase first: it can cascade onto other values
    for bip in (DB.BuiltInParameter.PHASE_CREATED,
                DB.BuiltInParameter.PHASE_DEMOLISHED,
                DB.BuiltInParameter.ELEM_PARTITION_PARAM):
        try:
            sp = src.get_Parameter(bip)
            tp = new_el.get_Parameter(bip)
            if sp and tp and not tp.IsReadOnly and sp.HasValue:
                copy_param(sp, tp)
                copied += 1
        except Exception:
            pass

    for sp in src.Parameters:
        try:
            if sp.IsReadOnly or not sp.HasValue:
                continue
            d = sp.Definition
            if isinstance(d, DB.InternalDefinition):
                bp = d.BuiltInParameter
                if bp != DB.BuiltInParameter.INVALID and str(bp) in SKIP_BIPS:
                    continue
            tp = find_target_param(new_el, sp)
            if tp is None:
                missed.append(d.Name)
                continue
            if tp.IsReadOnly or tp.StorageType != sp.StorageType:
                continue
            copy_param(sp, tp)
            copied += 1
        except Exception:
            try:
                missed.append(sp.Definition.Name)
            except Exception:
                pass
    return copied, missed


def measured(el):
    """(area, volume, bbox) for regression checking."""
    a = v = 0.0
    try:
        p = el.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
        a = p.AsDouble() if p else 0.0
    except Exception:
        pass
    try:
        p = el.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)
        v = p.AsDouble() if p else 0.0
    except Exception:
        pass
    bb = None
    try:
        bb = el.get_BoundingBox(None)
    except Exception:
        pass
    return a, v, bb


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------


class Plan(object):
    def __init__(self, el):
        self.el = el
        self.id = el.Id
        self.kind = slab_kind(el)
        self.src_type = doc.GetElement(el.GetTypeId())
        self.src_type_name = el_name(self.src_type)
        self.blockers = []
        self.warnings = []
        self.infos = []
        self.target_type = None
        self.target_type_name = "?"
        self.make_new_type = False
        self.data = {}

    @property
    def blocked(self):
        return bool(self.blockers)

    @property
    def name(self):
        flag = "[BLOCKED] " if self.blocked else ("[!] " if self.warnings else "[ok] ")
        return "{0}{1}  {2} '{3}'  ->  '{4}'{5}".format(
            flag, eid_val(self.id),
            "Floor" if self.kind == FLOOR else "Foundation",
            self.src_type_name, self.target_type_name,
            ("   |  " + "; ".join(self.blockers + self.warnings))
            if (self.blockers or self.warnings) else "")

    def __str__(self):
        return self.name


def build_plan(el, cfg, created_cache):
    p = Plan(el)

    if el.GroupId is not None and eid_val(el.GroupId) > 0:
        p.blockers.append("inside a model group")
    try:
        if el.AssemblyInstanceId is not None and eid_val(el.AssemblyInstanceId) > 0:
            p.blockers.append("inside an assembly")
    except Exception:
        pass

    active_opt = DB.DesignOption.GetActiveDesignOptionId(doc)
    src_opt = el.DesignOption.Id if el.DesignOption is not None else INVALID
    if eid_val(src_opt) != eid_val(active_opt):
        p.blockers.append("in design option '{0}' - activate it first".format(
            el.DesignOption.Name if el.DesignOption else "?"))

    sketch = get_sketch(el)
    if sketch is None:
        p.blockers.append("no editable sketch found")
    else:
        try:
            loops, base_z = read_profile(sketch)
            p.data["loops"] = loops
            p.data["base_z"] = base_z
            p.data["slope_arrow"] = find_slope_arrow(sketch)
            p.data["shape"] = read_shape_edits(el, base_z)
            if p.data["shape"]:
                p.infos.append("{0} shape-edit points".format(
                    len(p.data["shape"]["vertices"])))
        except Exception as ex:
            p.blockers.append(str(ex))

    res = resolve_type(p.src_type, p.kind, cfg, created_cache)
    if isinstance(res[0], str) and res[0] == "CREATE":
        p.make_new_type = True
        p.target_type_name = res[1]
        p.infos.append("will create type '{0}'".format(res[1]))
    elif res[0] is None:
        p.blockers.append(res[1])
    else:
        p.target_type = res[0]
        p.target_type_name = el_name(res[0])
        p.infos.append(res[1])

    deps = classify_dependents(el)
    p.data["deps"] = deps
    p.data["joins"] = read_joins(el)

    if deps["tags"]:
        p.warnings.append("{0} tag(s) will be lost".format(len(deps["tags"])))
    if deps["dims"]:
        p.warnings.append("{0} dimension(s) will be lost".format(len(deps["dims"])))
    if deps["hosted"]:
        p.warnings.append("{0} hosted family instance(s) will be DELETED".format(
            len(deps["hosted"])))
    if deps["parts"]:
        p.warnings.append("{0} part(s) will be lost".format(len(deps["parts"])))
    if deps["slab_edges"]:
        p.warnings.append("{0} slab edge(s) will be lost".format(len(deps["slab_edges"])))
    if deps["analytical"]:
        p.warnings.append("analytical association will be lost")
    if deps["rebar"]:
        p.infos.append("{0} reinforcement element(s) - re-host attempted".format(
            len(deps["rebar"])))
    if deps["openings"]:
        p.infos.append("{0} opening(s) recreated".format(len(deps["openings"])))
    if p.data["joins"]:
        p.infos.append("{0} join(s) restored".format(len(p.data["joins"])))

    return p


# ---------------------------------------------------------------------------
# conversion
# ---------------------------------------------------------------------------


class WarningSwallower(DB.IFailuresPreprocessor):
    __namespace__ = "SlabConvert"

    def PreprocessFailures(self, fa):
        for f in fa.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                fa.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


def apply_failure_handler(t):
    try:
        o = t.GetFailureHandlingOptions()
        o.SetFailuresPreprocessor(WarningSwallower())
        o.SetClearAfterRollback(True)
        t.SetFailureHandlingOptions(o)
    except Exception:
        pass


def create_slab(loops, type_id, level_id, structural, slope_arrow, slope):
    """-> (Floor, sloped_overload_used)"""
    net_loops = List[DB.CurveLoop]()
    for l in loops:
        net_loops.Add(l)
    if slope_arrow is not None:
        try:
            return DB.Floor.Create(doc, net_loops, type_id, level_id,
                                   structural, slope_arrow, slope), True
        except Exception:
            pass
    return DB.Floor.Create(doc, net_loops, type_id, level_id), False


def convert_one(p, cfg, created_cache):
    """Runs inside its own transaction. -> result dict."""
    src = p.el
    res = {"old": eid_val(p.id), "new": None, "status": "failed",
           "notes": [], "delta": ""}

    src_area, src_vol, src_bb = measured(src)
    was_pinned = False
    try:
        was_pinned = src.Pinned
    except Exception:
        pass

    level_id = src.LevelId if hasattr(src, "LevelId") else \
        src.get_Parameter(DB.BuiltInParameter.LEVEL_PARAM).AsElementId()
    off_p = src.get_Parameter(DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
    offset = off_p.AsDouble() if off_p else 0.0
    st_p = src.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
    structural = bool(st_p.AsInteger()) if st_p else True
    slope_p = src.get_Parameter(DB.BuiltInParameter.ROOF_SLOPE)
    slope_val = slope_p.AsDouble() if (slope_p and slope_p.HasValue) else 0.0

    opening_data = read_openings(p.data["deps"]["openings"])

    # 1. target type
    if p.make_new_type:
        if p.target_type_name in created_cache:
            ttype = created_cache[p.target_type_name]
        else:
            ttype = create_target_type(p.src_type, p.kind, p.target_type_name)
            created_cache[p.target_type_name] = ttype
            res["notes"].append("created type '{0}'".format(
                el_name(ttype)))
    else:
        ttype = p.target_type

    # 2. create
    new_el, sloped = create_slab(p.data["loops"], ttype.Id, level_id, structural,
                                 p.data["slope_arrow"], slope_val)
    if new_el is None:
        res["notes"].append("Floor.Create returned nothing")
        return res
    doc.Regenerate()

    if eid_val(new_el.Category.Id) != target_cat_id(p.kind):
        res["notes"].append("created element landed in the wrong category")
        return res

    # 3. placement + params
    try:
        np = new_el.get_Parameter(DB.BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)
        if np and not np.IsReadOnly:
            np.Set(offset)
    except Exception:
        pass
    try:
        nsp = new_el.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL)
        if nsp and not nsp.IsReadOnly:
            nsp.Set(1 if structural else 0)
    except Exception:
        pass

    copied, missed = copy_instance_params(src, new_el)
    res["notes"].append("{0} params copied".format(copied))
    if missed:
        res["notes"].append("{0} param(s) had no counterpart: {1}".format(
            len(missed), ", ".join(sorted(set(missed))[:4])))

    if p.data["slope_arrow"] is not None:
        if not sloped:
            res["notes"].append("SLOPE ARROW NOT TRANSFERRED - verify")
        try:
            nsl = new_el.get_Parameter(DB.BuiltInParameter.ROOF_SLOPE)
            if nsl and not nsl.IsReadOnly and abs(nsl.AsDouble() - slope_val) > 1e-9:
                nsl.Set(slope_val)
        except Exception:
            res["notes"].append("slope needs manual check")

    doc.Regenerate()

    # 4. shape edits
    ok, note = apply_shape_edits(new_el, p.data["shape"], p.data["base_z"])
    if not ok:
        res["notes"].append("shape edits partial: {0}".format(note))

    # 5. reinforcement re-host (must happen while the source still exists)
    rehosted = 0
    for rid in p.data["deps"]["rebar"]:
        r = doc.GetElement(rid)
        if r is None:
            continue
        try:
            if hasattr(r, "SetHostId"):
                r.SetHostId(doc, new_el.Id)
                rehosted += 1
        except Exception:
            pass
    if p.data["deps"]["rebar"]:
        res["notes"].append("{0}/{1} reinforcement re-hosted".format(
            rehosted, len(p.data["deps"]["rebar"])))

    # 6. openings
    made = 0
    for arr in opening_data:
        try:
            doc.Create.NewOpening(new_el, arr, True)
            made += 1
        except Exception:
            pass
    if opening_data:
        res["notes"].append("{0}/{1} openings recreated".format(made, len(opening_data)))

    # 7. delete source
    try:
        if was_pinned:
            src.Pinned = False
    except Exception:
        pass
    doc.Delete(src.Id)
    doc.Regenerate()

    # 8. joins + pin
    r = restore_joins(new_el, p.data["joins"])
    if p.data["joins"]:
        res["notes"].append("{0}/{1} joins restored".format(r, len(p.data["joins"])))
    try:
        if was_pinned:
            new_el.Pinned = True
    except Exception:
        pass

    # 9. verify
    doc.Regenerate()
    new_area, new_vol, new_bb = measured(new_el)
    da_m2 = abs(new_area - src_area) * (0.3048 ** 2)
    dv_m3 = abs(new_vol - src_vol) * (0.3048 ** 3)
    dz = 0.0
    if src_bb is not None and new_bb is not None:
        dz = max(abs(ft_to_mm(new_bb.Min.Z - src_bb.Min.Z)),
                 abs(ft_to_mm(new_bb.Max.Z - src_bb.Max.Z)))
    res["delta"] = "area {0:.4f} m2 / vol {1:.4f} m3 / z {2:.2f} mm".format(
        da_m2, dv_m3, dz)
    rel = (da_m2 / (src_area * 0.3048 ** 2)) if src_area > 1e-9 else 0.0
    if rel > 0.001 or dz > 0.1:
        res["notes"].append("GEOMETRY DELTA - verify manually")

    res["new"] = eid_val(new_el.Id)
    res["new_id"] = new_el.Id
    res["status"] = "ok"
    return res


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main():
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Run this in a project document.", title="Convert Slab")
        return

    cfg = load_config()

    elements = gather_selection()
    if not elements:
        forms.alert("Nothing selected.", title="Convert Slab")
        return

    slabs, rejected = [], 0
    for el in elements:
        if slab_kind(el) is not None:
            slabs.append(el)
        else:
            rejected += 1

    if not slabs:
        forms.alert("None of the {0} selected element(s) is a sketch-based "
                    "structural floor or foundation slab.\n\n"
                    "Isolated footings and wall foundations are family/host "
                    "based and are out of scope for this tool."
                    .format(len(elements)), title="Convert Slab")
        return

    created_cache = {}
    plans = []
    with forms.ProgressBar(title="Analysing {value}/{max_value}") as pb:
        for i, el in enumerate(slabs):
            try:
                plans.append(build_plan(el, cfg, created_cache))
            except Exception as ex:
                p = Plan(el)
                p.blockers.append("analysis failed: {0}".format(ex))
                plans.append(p)
            pb.update_progress(i + 1, len(slabs))

    header = "Convert Slab v{0} - {1} slab(s)".format(TOOL_VERSION, len(plans))
    if rejected:
        header += " ({0} non-slab selection(s) ignored)".format(rejected)

    picked = forms.SelectFromList.show(
        plans, title=header, name_attr="name", multiselect=True,
        button_name="Continue", width=1100, height=620)

    if not picked:
        return

    todo = [p for p in picked if not p.blocked]
    blocked = [p for p in picked if p.blocked]
    if blocked:
        forms.alert("{0} blocked element(s) were dropped from the run:\n\n{1}"
                    .format(len(blocked),
                            "\n".join(p.name for p in blocked[:10])),
                    title="Convert Slab")
    if not todo:
        return

    mode = forms.CommandSwitchWindow.show(
        ["Convert {0} slab(s)".format(len(todo)), "Report only (no changes)"],
        message="Ready.")
    if not mode:
        return
    dry_run = mode.startswith("Report")

    results = []
    new_ids = []

    if dry_run:
        output.print_md("## Convert Slab v{0} - dry run".format(TOOL_VERSION))
        rows = [[output.linkify(p.id), p.src_type_name, p.target_type_name,
                 "; ".join(p.infos) or "-", "; ".join(p.warnings) or "-"]
                for p in todo]
        output.print_table(rows, columns=["Element", "From type", "To type",
                                          "Planned", "Losses"])
        return

    tg = DB.TransactionGroup(doc, "Convert Slab v{0}".format(TOOL_VERSION))
    tg.Start()
    try:
        with forms.ProgressBar(title="Converting {value}/{max_value}",
                               cancellable=True) as pb:
            for i, p in enumerate(todo):
                if pb.cancelled:
                    break
                t = DB.Transaction(doc, "Convert {0}".format(eid_val(p.id)))
                t.Start()
                if cfg.get("swallow_warnings", True):
                    apply_failure_handler(t)
                try:
                    r = convert_one(p, cfg, created_cache)
                    if r["status"] == "ok":
                        t.Commit()
                        new_ids.append(r["new_id"])
                    else:
                        t.RollBack()
                    results.append((p, r))
                except Exception:
                    t.RollBack()
                    results.append((p, {"old": eid_val(p.id), "new": None,
                                        "status": "failed", "delta": "",
                                        "notes": [traceback.format_exc()
                                                  .strip().splitlines()[-1]]}))
                pb.update_progress(i + 1, len(todo))
        tg.Assimilate()
    except Exception:
        tg.RollBack()
        forms.alert("Run aborted and rolled back:\n\n{0}"
                    .format(traceback.format_exc()), title="Convert Slab")
        return

    ok = [r for _, r in results if r["status"] == "ok"]
    output.print_md("## Convert Slab v{0} - {1}/{2} converted"
                    .format(TOOL_VERSION, len(ok), len(results)))
    rows = []
    for p, r in results:
        rows.append([
            output.linkify(p.id) if r["status"] != "ok" else str(r["old"]),
            output.linkify(r["new_id"]) if r.get("new_id") else "-",
            p.target_type_name,
            r["status"].upper(),
            r["delta"] or "-",
            "; ".join(r["notes"]) or "-",
        ])
    output.print_table(rows, columns=["Old id", "New", "Type", "Status",
                                      "Geometry delta", "Notes"])

    lost = [(p, p.warnings) for p, r in results
            if r["status"] == "ok" and p.warnings]
    if lost:
        output.print_md("### Accepted losses")
        output.print_table([[str(eid_val(p.id)), "; ".join(w)] for p, w in lost],
                           columns=["Old id", "Lost"])

    if new_ids and cfg.get("select_results_after_run", True):
        try:
            sel = List[DB.ElementId]()
            for i in new_ids:
                sel.Add(i)
            uidoc.Selection.SetElementIds(sel)
        except Exception:
            pass


main()

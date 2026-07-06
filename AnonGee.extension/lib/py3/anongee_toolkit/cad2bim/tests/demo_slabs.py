# Demo: slab prototype against a REAL 0.30.0 export -- both outline sources.
import importlib.util, os, sys, types, json
PKG = "/home/user/pyRevit-addons/AnonGee.extension/lib/py3/anongee_toolkit/cad2bim"
for name in ("_c2b", "_c2b.geom", "_c2b.classify", "_c2b.readers"):
    m = types.ModuleType(name); m.__path__ = []; sys.modules[name] = m
def L(full, *parts):
    spec = importlib.util.spec_from_file_location(full, os.path.join(PKG, *parts))
    mod = importlib.util.module_from_spec(spec); sys.modules[full] = mod
    if "." in full:
        p, c = full.rsplit(".", 1); setattr(sys.modules[p], c, mod)
    spec.loader.exec_module(mod); return mod
config=L("_c2b.config","config.py"); model=L("_c2b.model","model.py")
L("_c2b.geom.shapes","geom","shapes.py")
layers=L("_c2b.classify.layers","classify","layers.py")
marks=L("_c2b.classify.marks","classify","marks.py")
report=L("_c2b.report","report.py")
proto=L("_c2b.slabs_proto","slabs_proto.py")
MM=config.MM_PER_FT; FT=1.0/MM

class T:
    def __init__(s, mark,x,y,b,h,layer):
        s.mark=mark; s.b_mm=b; s.h_mm=h; s.layer=layer
        s.point_internal=(x*FT,y*FT,0.0) if x is not None else None

d=json.load(open(sys.argv[1]))
recs=[]
for g in d["beams"]["raw_geometry"]:
    pts=[(p[0]*FT,p[1]*FT,0.0) for p in g["pts"]]
    r=model.CurveRecord(g["kind"],pts,g["layer"],0.0)
    r.category=layers.CATEGORY_SLAB_EDGE if g["cat"]=="slab" else layers.CATEGORY_BEAM
    recs.append(r)
bt=[T(t.get("mark"),t.get("x"),t.get("y"),t.get("b"),t.get("h"),t.get("layer"))
    for t in d.get("texts_sized",[])
    if layers.classify_text_layer(t.get("layer") or "")==layers.CATEGORY_BEAM_TEXT]
circ=[{"center":(c["x"]*FT,c["y"]*FT,0.0),"diameter_ft":c["dia"]*FT}
      for c in d["columns"].get("circles",[])]

# Source 1: slab-edge layer as drawn
loops_edges = proto.slab_loops_from_edges(recs)
areas1 = sorted(round(abs(proto._signed_area(r))*MM*MM/1e6,1) for r,_z in loops_edges)
print("source 1 (A-FLOR edges):   %d loops, areas m2: %s" % (len(loops_edges), areas1[:12]))

# Source 2: beam perimeter graph (the fallback)
bs=report.build_beam_segments(recs,circ,None,None,texts=bt,tolerances={},schedule=None)
loops_graph = proto.slab_loops_from_beam_graph(bs["segments"])
areas2 = sorted(round(abs(proto._signed_area(r))*MM*MM/1e6,1) for r,_z in loops_graph)
print("source 2 (beam graph):     %d loops from %d beams, areas m2: %s%s" % (
    len(loops_graph), len(bs["segments"]), areas2[:12], " ..." if len(areas2)>12 else ""))

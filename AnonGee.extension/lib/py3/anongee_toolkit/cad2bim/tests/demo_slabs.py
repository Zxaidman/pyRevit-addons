# Demo: slab outlines against a REAL 0.30.0 export -- both outline sources.
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                        # loads cad2bim by file, real import graph

config, model, layers, marks, report, proto = _loader.load(
    "config", "model", "classify.layers", "classify.marks", "report",
    "slab_outlines")
MM=config.MM_PER_FT; FT=1.0/MM


def storey_payload(document, wanted=None):
    """One storey's section out of an export, or the export itself.

    A multi-storey run writes ONE file with a `storeys` array instead of the
    flat payload these harnesses were written against, so every stored fixture
    now looks like the former. `wanted` picks a storey by index or by a
    fragment of its label; the lowest storey is the default.
    """
    storeys = document.get("storeys")
    if not storeys:
        return document
    if wanted is None:
        chosen = storeys[0]
    elif str(wanted).lstrip("-").isdigit():
        chosen = storeys[int(wanted)]
    else:
        matches = [s for s in storeys
                   if str(wanted).lower() in (s.get("storey") or "").lower()]
        if not matches:
            raise SystemExit("no storey matching %r; have: %s"
                             % (wanted, [s.get("storey") for s in storeys]))
        chosen = matches[0]
    print("storey: %s (%d of %d)"
          % (chosen.get("storey"), storeys.index(chosen) + 1, len(storeys)))
    return chosen



class T:
    def __init__(s, mark,x,y,b,h,layer):
        s.mark=mark; s.b_mm=b; s.h_mm=h; s.layer=layer
        s.point_internal=(x*FT,y*FT,0.0) if x is not None else None

d=storey_payload(json.load(open(sys.argv[1])), os.environ.get("STOREY"))
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
areas1 = sorted(round(abs(proto._signed_area(r))*MM*MM/1e6,1) for r,_z,_arcs in loops_edges)
print("source 1 (A-FLOR edges):   %d loops, areas m2: %s" % (len(loops_edges), areas1[:12]))

# Source 2: beam perimeter graph (the fallback)
bs=report.build_beam_segments(recs,circ,None,None,texts=bt,tolerances={},schedule=None)
loops_graph = proto.slab_loops_from_beam_graph(bs["segments"])
areas2 = sorted(round(abs(proto._signed_area(r))*MM*MM/1e6,1) for r,_z,_arcs in loops_graph)
print("source 2 (beam graph):     %d loops from %d beams, areas m2: %s%s" % (
    len(loops_graph), len(bs["segments"]), areas2[:12], " ..." if len(areas2)>12 else ""))

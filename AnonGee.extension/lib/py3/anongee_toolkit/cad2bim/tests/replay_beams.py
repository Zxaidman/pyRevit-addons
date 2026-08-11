#!/usr/bin/env python3
"""Replay beam detection from a 0.30.0+ JSON export's beams.raw_geometry, OFFLINE.

The DXF source carries beams as loose LINES (not the polylines Revit's link reader
builds), so the DXF harness places zero beams and cannot reproduce a Revit-only beam
miss. From 0.30.0 the export dumps the exact beam/slab-edge geometry (mm) the link
reader returned -- this script rebuilds CurveRecords from it and re-runs the real
build_beam_segments, so 8b-8e can be diagnosed without another Revit run.

  python3 replay_beams.py <export.json> [mark-filter]
"""
import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _loader                        # loads cad2bim by file, real import graph

config, model, layers, marks, report = _loader.load(
    "config", "model", "classify.layers", "classify.marks", "report")
MM = config.MM_PER_FT
FT = 1.0 / MM


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



class T:  # minimal TextRecord stand-in for build_beam_segments (it reads point_internal/mark/b_mm/h_mm)
    def __init__(self, mark, x, y, b, h, layer, rot=None):
        self.mark = mark; self.b_mm = b; self.h_mm = h; self.layer = layer
        self.rotation_deg = rot
        self.point_internal = (x * FT, y * FT, 0.0) if x is not None else None

def records_from_raw(raw):
    recs = []
    for g in raw:
        pts = [(p[0] * FT, p[1] * FT, 0.0) for p in g["pts"]]
        r = model.CurveRecord(g["kind"], pts, g["layer"], 0.0)
        r.category = layers.CATEGORY_SLAB_EDGE if g["cat"] == "slab" else layers.CATEGORY_BEAM
        recs.append(r)
    return recs

def main():
    d = storey_payload(json.load(open(sys.argv[1])),
                       os.environ.get("STOREY"))
    want = sys.argv[2].upper() if len(sys.argv) > 2 else None
    raw = d["beams"].get("raw_geometry")
    if not raw:
        print("export has no beams.raw_geometry -- needs a 0.30.0+ run"); return
    recs = records_from_raw(raw)
    # beam text labels (those on a beam-text layer) for sizing
    beam_texts = []
    for t in d.get("texts_sized", []):
        if layers.classify_text_layer(t.get("layer") or "") == layers.CATEGORY_BEAM_TEXT:
            beam_texts.append(T(t.get("mark"), t.get("x"), t.get("y"), t.get("b"),
                                t.get("h"), t.get("layer"), t.get("rot")))
    # circles from the columns dump (for arc-junction filtering + end snap)
    circles = []
    for c in d["columns"].get("circles", []):
        circles.append({"center": (c["x"] * FT, c["y"] * FT, 0.0), "diameter_ft": c["dia"] * FT})
    bs = report.build_beam_segments(recs, circles, None, None, texts=beam_texts,
                                    tolerances={}, schedule=None)
    print("raw geometry:", len(raw), "records  (beam/slab)")
    print("status_counts:", dict(bs["status_counts"]))
    print("segments:", len(bs["segments"]), " curved:", len(bs.get("curved", [])))
    for s in bs["segments"]:
        mk = s.get("mark")
        if want and (mk is None or want not in str(mk).upper()):
            continue
        sx, sy, ex, ey = s["start"][0]*MM, s["start"][1]*MM, s["end"][0]*MM, s["end"][1]*MM
        print("  %-6s w=%4s d=%-5s len=%6.0f (%8.0f,%8.0f)->(%8.0f,%8.0f)" % (
            mk, int(round(s["width_mm"])), s.get("depth_mm"),
            math.hypot(ex-sx, ey-sy), sx, sy, ex, ey))

if __name__ == "__main__":
    main()

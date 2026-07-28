# -*- coding: utf-8 -*-
"""The JSON export shape and the Tolerances-tab overrides.

A multi-storey run must write ONE file carrying a section per storey (the user
asked for one JSON, not one per floor), and every tunable the Tolerances tab
exposes must actually reach the geometry modules. Standalone (no Revit).
"""

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)


def _load():
    for name in ("_exp", "_exp.geom", "_exp.classify", "_exp.readers"):
        if name not in sys.modules:
            m = types.ModuleType(name)
            m.__path__ = []
            sys.modules[name] = m

    def load(full, *parts):
        spec = importlib.util.spec_from_file_location(full, os.path.join(_PKG, *parts))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        if "." in full:
            parent, child = full.rsplit(".", 1)
            setattr(sys.modules[parent], child, mod)
        spec.loader.exec_module(mod)
        return mod

    load("_exp.config", "config.py")
    load("_exp.geom.shapes", "geom", "shapes.py")
    load("_exp.geom.transform", "geom", "transform.py")
    load("_exp.classify.layers", "classify", "layers.py")
    load("_exp.classify.marks", "classify", "marks.py")
    load("_exp.model", "model.py")
    load("_exp.slab_outlines", "slab_outlines.py")
    load("_exp.stair_layout", "stair_layout.py")
    return load("_exp.report", "report.py")


report = _load()
config = sys.modules["_exp.config"]
slab_outlines = sys.modules["_exp.slab_outlines"]
stair_layout = sys.modules["_exp.stair_layout"]


class _Result(object):
    def __init__(self, name):
        self.source_name = name
        self.records = []


def _payload(label):
    return report.build_export_payload(_Result("plan.dxf"), {}, {}, None,
                                       {"columns": {"created": 3},
                                        "stairs": {"created": 1,
                                                   "storey": label}})


class StoreySections(unittest.TestCase):
    def test_one_file_holds_every_storey(self):
        storeys = [("GROUND FLOOR", _payload("GROUND FLOOR")),
                   ("FIRST FLOOR", _payload("FIRST FLOOR")),
                   ("TERRACE", _payload("TERRACE"))]
        target = os.path.join(tempfile.mkdtemp(), "multi.json")
        report.export_storeys_json(target, storeys, source_name="plan.dxf")
        with open(target) as handle:
            document = json.load(handle)
        self.assertEqual(document["storey_count"], 3)
        self.assertEqual([s["storey"] for s in document["storeys"]],
                         ["GROUND FLOOR", "FIRST FLOOR", "TERRACE"])
        # the shared header is lifted out of the sections, not repeated
        self.assertEqual(document["source"], "plan.dxf")
        self.assertIn("cad2bim_version", document)
        for section in document["storeys"]:
            self.assertNotIn("source", section)
            self.assertNotIn("cad2bim_version", section)
            self.assertIn("columns", section)      # the per-storey payload
            self.assertIn("beams", section)

    def test_single_storey_export_is_unchanged(self):
        target = os.path.join(tempfile.mkdtemp(), "one.json")
        report.export_json(target, _Result("plan.dxf"), {},
                           outcomes={"columns": {"created": 3}})
        with open(target) as handle:
            document = json.load(handle)
        self.assertEqual(document["source"], "plan.dxf")
        self.assertNotIn("storeys", document)
        self.assertIn("columns", document)


class ToleranceOverrides(unittest.TestCase):
    def tearDown(self):
        slab_outlines.apply_tolerances(
            {k: config.DEFAULTS[k] for k in
             ("slab_snap_mm", "slab_heal_mm", "slab_chain_mm",
              "slab_min_width_mm", "slab_min_step_mm")})
        stair_layout.apply_tolerances(
            {k: config.DEFAULTS[k] for k in
             ("stair_cluster_mm", "stair_tread_min_mm", "stair_tread_max_mm",
              "stair_arrival_merge_mm")})

    def test_defaults_match_the_module_constants(self):
        d = config.DEFAULTS
        self.assertEqual(d["slab_snap_mm"], slab_outlines._SNAP_MM)
        self.assertEqual(d["slab_heal_mm"], slab_outlines._EDGE_HEAL_MM)
        self.assertEqual(d["slab_chain_mm"], slab_outlines._CHAIN_TOL_MM)
        self.assertEqual(d["slab_min_width_mm"],
                         slab_outlines._MIN_PANEL_WIDTH_MM)
        self.assertEqual(d["slab_min_step_mm"], slab_outlines._MIN_STEP_MM)
        self.assertEqual(d["stair_cluster_mm"], stair_layout._CLUSTER_GAP_MM)
        self.assertEqual(d["stair_tread_min_mm"], stair_layout._TREAD_MIN_MM)
        self.assertEqual(d["stair_tread_max_mm"], stair_layout._TREAD_MAX_MM)
        self.assertEqual(d["stair_arrival_merge_mm"],
                         stair_layout._ARRIVAL_MERGE_GAP_MM)

    def test_dialog_values_reach_the_modules(self):
        slab_outlines.apply_tolerances({"slab_snap_mm": 75.0,
                                        "slab_heal_mm": 400.0,
                                        "slab_chain_mm": 200.0,
                                        "slab_min_width_mm": 600.0,
                                        "slab_min_step_mm": 30.0})
        self.assertEqual(slab_outlines._SNAP_MM, 75.0)
        self.assertEqual(slab_outlines._EDGE_HEAL_MM, 400.0)
        self.assertEqual(slab_outlines._CHAIN_TOL_MM, 200.0)
        self.assertEqual(slab_outlines._MIN_PANEL_WIDTH_MM, 600.0)
        self.assertEqual(slab_outlines._MIN_STEP_MM, 30.0)
        stair_layout.apply_tolerances({"stair_cluster_mm": 2500.0,
                                       "stair_tread_min_mm": 120.0,
                                       "stair_tread_max_mm": 600.0,
                                       "stair_arrival_merge_mm": 900.0})
        self.assertEqual(stair_layout._CLUSTER_GAP_MM, 2500.0)
        self.assertEqual(stair_layout._TREAD_MIN_MM, 120.0)
        self.assertEqual(stair_layout._TREAD_MAX_MM, 600.0)
        self.assertEqual(stair_layout._ARRIVAL_MERGE_GAP_MM, 900.0)

    def test_empty_tolerances_change_nothing(self):
        slab_outlines.apply_tolerances(None)
        stair_layout.apply_tolerances({})
        self.assertEqual(slab_outlines._SNAP_MM, config.DEFAULTS["slab_snap_mm"])
        self.assertEqual(stair_layout._TREAD_MAX_MM,
                         config.DEFAULTS["stair_tread_max_mm"])


if __name__ == "__main__":
    unittest.main()

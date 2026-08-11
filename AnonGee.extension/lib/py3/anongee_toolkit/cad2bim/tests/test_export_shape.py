# -*- coding: utf-8 -*-
"""The JSON export shape and the Tolerances-tab overrides.

A multi-storey run must write ONE file carrying a section per storey (the user
asked for one JSON, not one per floor), and every tunable the Tolerances tab
exposes must actually reach the geometry modules. Standalone (no Revit).
"""

import json
import os
import sys
import tempfile
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)


report, export, config, slab_outlines, slab_graph, stair_layout = (
    _loader.load("report", "export", "config", "slab_outlines",
                 "slab_graph", "stair_layout"))


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
        self.assertEqual(d["slab_snap_mm"], slab_graph._SNAP_MM)
        self.assertEqual(d["slab_heal_mm"], slab_graph._EDGE_HEAL_MM)
        self.assertEqual(d["slab_chain_mm"], slab_graph._CHAIN_TOL_MM)
        self.assertEqual(d["slab_min_width_mm"],
                         slab_graph._MIN_PANEL_WIDTH_MM)
        self.assertEqual(d["slab_min_step_mm"], slab_graph._MIN_STEP_MM)
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
        self.assertEqual(slab_graph._SNAP_MM, 75.0)
        self.assertEqual(slab_graph._EDGE_HEAL_MM, 400.0)
        self.assertEqual(slab_graph._CHAIN_TOL_MM, 200.0)
        self.assertEqual(slab_graph._MIN_PANEL_WIDTH_MM, 600.0)
        self.assertEqual(slab_graph._MIN_STEP_MM, 30.0)
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
        self.assertEqual(slab_graph._SNAP_MM, config.DEFAULTS["slab_snap_mm"])
        self.assertEqual(stair_layout._TREAD_MAX_MM,
                         config.DEFAULTS["stair_tread_max_mm"])


class ExportSurvivesRevitObjects(unittest.TestCase):
    """A report is a diagnostic; it must never fail a run that already built.

    v0.63.0 put live ElementIds into the outcomes for the material pass and
    json.dump raised on them AFTER the model was placed, losing the report and
    reporting a crash for a run that had worked.
    """

    class _FakeId(object):
        def __init__(self, value):
            self.IntegerValue = value

    def test_an_element_id_encodes_as_its_integer(self):
        self.assertEqual(export._jsonable(self._FakeId(42)), 42)

    def test_anything_else_encodes_as_its_text(self):
        class Opaque(object):
            def __str__(self):
                return "<a revit thing>"
        self.assertEqual(export._jsonable(Opaque()), "<a revit thing>")

    def test_dump_does_not_raise_on_an_unexpected_object(self):
        import json
        payload = {"outcomes": {"columns": {"ids": [self._FakeId(7)]}}}
        text = json.dumps(payload, default=export._jsonable)
        self.assertIn("7", text)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Saving and reloading the whole dialog, without WPF in the room."""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)


def _load():
    """settings.py on its own -- importing the package would pull in Revit."""
    spec = importlib.util.spec_from_file_location(
        "_settings_under_test", os.path.join(_PKG, "settings.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


settings = _load()


class WhatGetsSaved(unittest.TestCase):
    def test_ordinary_controls_are_saveable(self):
        for name in ("tb_slab_step", "chk_beams", "cb_floor_type",
                     "sl_beam_min", "tb_name_footing", "cb_mat_beam"):
            self.assertTrue(settings.saveable(name), name)

    def test_computed_text_and_buttons_are_not(self):
        for name in ("version_text", "source_text", "status_text",
                     "multistorey_preview", "lbl_name_floor",
                     "btn_run", "storey_rows", "layer_rows", "text_rows",
                     "hatch_rows"):
            self.assertFalse(settings.saveable(name), name)

    def test_detected_controls_are_saved_but_never_restored(self):
        # the drawing in front of the user decides these, not last week's run
        for name in ("chk_multistorey", "cb_boundary_layer", "cb_origin_layer"):
            self.assertTrue(settings.saveable(name), name)
            self.assertFalse(settings.restorable(name), name)

    def test_a_missing_name_is_neither(self):
        self.assertFalse(settings.saveable(""))
        self.assertFalse(settings.saveable(None))
        self.assertFalse(settings.restorable(None))


class MatchingASavedComboLabel(unittest.TestCase):
    ITEMS = ["(unchanged)", "Concrete - Cast In Situ", "Concrete, Precast"]

    def test_exact_match(self):
        self.assertEqual(settings.pick_index(self.ITEMS, "Concrete, Precast"), 2)

    def test_case_insensitive_match(self):
        self.assertEqual(
            settings.pick_index(self.ITEMS, "concrete - cast in situ"), 1)

    def test_a_unique_prefix_still_finds_a_renamed_duplicate(self):
        items = ["Generic 150mm (2)", "Other"]
        self.assertEqual(settings.pick_index(items, "Generic 150mm"), 0)

    def test_an_ambiguous_prefix_is_refused(self):
        items = ["Generic 150mm", "Generic 150mm (2)"]
        # exact wins outright...
        self.assertEqual(settings.pick_index(items, "Generic 150mm"), 0)
        # ...but a prefix matching two candidates picks neither
        self.assertEqual(settings.pick_index(items, "Generic 1"), -1)

    def test_a_label_this_model_does_not_have_is_left_alone(self):
        self.assertEqual(settings.pick_index(self.ITEMS, "Steel"), -1)
        self.assertEqual(settings.pick_index(self.ITEMS, None), -1)

    def test_empty_items(self):
        self.assertEqual(settings.pick_index([], "anything"), -1)


class PayloadShape(unittest.TestCase):
    def test_payload_carries_the_version_and_three_sections(self):
        data = settings.payload({"chk_beams": True}, {"S-COL": "Column"},
                                {"S-TEXT": "Column mark"}, "0.67.0")
        self.assertEqual(data["schema"], settings.SCHEMA)
        self.assertEqual(data["version"], "0.67.0")
        self.assertEqual(data["controls"], {"chk_beams": True})
        self.assertEqual(data["layers"], {"S-COL": "Column"})
        self.assertEqual(data["texts"], {"S-TEXT": "Column mark"})

    def test_payload_is_json_serialisable(self):
        data = settings.payload({"tb_slab_step": "20", "sl_beam_min": 150.0,
                                 "chk_beams": False})
        self.assertEqual(json.loads(json.dumps(data))["controls"]["sl_beam_min"],
                         150.0)

    def test_sections_of_a_good_payload(self):
        controls, layers, texts = settings.sections(
            settings.payload({"a": 1}, {"b": "c"}, {"d": "e"}))
        self.assertEqual((controls, layers, texts),
                         ({"a": 1}, {"b": "c"}, {"d": "e"}))

    def test_sections_of_rubbish_is_three_empty_dicts(self):
        for junk in (None, [], "text", {}, {"controls": "not a dict"},
                     {"controls": None}):
            self.assertEqual(settings.sections(junk), ({}, {}, {}), repr(junk))

    def test_payload_carries_the_advanced_overrides(self):
        data = settings.payload({"a": 1}, advanced={"beam_heal_mm": 400.0})
        self.assertEqual(data["advanced"], {"beam_heal_mm": 400.0})
        self.assertEqual(settings.advanced_overrides(data),
                         {"beam_heal_mm": 400.0})

    def test_a_schema_1_file_without_the_section_loads_unchanged(self):
        # the section is OPTIONAL: an old file restores everything it always
        # restored and its advanced overrides simply read as none
        old = {"schema": 1, "version": "0.67.0",
               "controls": {"chk_beams": True}, "layers": {}, "texts": {}}
        controls, layers, texts = settings.sections(old)
        self.assertEqual(controls, {"chk_beams": True})
        self.assertEqual(settings.advanced_overrides(old), {})

    def test_advanced_overrides_of_rubbish_is_an_empty_dict(self):
        for junk in (None, [], "text", {"advanced": "not a dict"},
                     {"advanced": None}, {"advanced": [1, 2]}):
            self.assertEqual(settings.advanced_overrides(junk), {}, repr(junk))

    def test_payload_carries_the_hatch_mapping_in_its_own_section(self):
        # hatches map on their own table, apart from geometry and text, so
        # the file keeps them apart too
        data = settings.payload({"a": 1}, {"S-COLS": "column"},
                                {"S-COLS-IDEN": "column text"},
                                hatches={"S-FND-FOLD": "fold"})
        self.assertEqual(data["hatches"], {"S-FND-FOLD": "fold"})
        self.assertEqual(settings.hatch_mappings(data),
                         {"S-FND-FOLD": "fold"})
        # ...and the three-tuple sections keep their shape (the advanced
        # precedent): the hatch section rides its own accessor
        self.assertEqual(settings.sections(data),
                         ({"a": 1}, {"S-COLS": "column"},
                          {"S-COLS-IDEN": "column text"}))

    def test_a_file_older_than_schema_3_loads_unchanged(self):
        # no hatches section: the mapping reads as empty, so the dialog's
        # convention guess stands, and everything else restores as it did
        old = {"schema": 2, "version": "0.73.1",
               "controls": {"chk_beams": True},
               "layers": {"S-COLS": "column"}, "texts": {},
               "advanced": {"beam_heal_mm": 400.0}}
        controls, layers, texts = settings.sections(old)
        self.assertEqual(controls, {"chk_beams": True})
        self.assertEqual(layers, {"S-COLS": "column"})
        self.assertEqual(settings.hatch_mappings(old), {})
        self.assertEqual(settings.advanced_overrides(old),
                         {"beam_heal_mm": 400.0})

    def test_hatch_mappings_of_rubbish_is_an_empty_dict(self):
        for junk in (None, [], "text", {"hatches": "not a dict"},
                     {"hatches": None}, {"hatches": [1, 2]}):
            self.assertEqual(settings.hatch_mappings(junk), {}, repr(junk))

    def test_describe_counts_both_layer_maps(self):
        text = settings.describe(settings.payload(
            {"a": 1, "b": 2}, {"L1": "Column"}, {"T1": "Beam mark"}, "0.67.0"))
        self.assertIn("2 setting(s)", text)
        self.assertIn("2 layer(s)", text)
        self.assertIn("0.67.0", text)


class TheFileOnDisk(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_a_round_trip_returns_what_went_in(self):
        path = os.path.join(self.folder, "settings.json")
        data = settings.payload({"tb_slab_step": "20", "chk_beams": True},
                                {"S-COL": "Column"}, {}, "0.67.0")
        self.assertIsNone(settings.write(path, data))
        self.assertEqual(settings.read(path), data)

    def test_a_missing_file_reads_as_nothing(self):
        self.assertEqual(settings.read(os.path.join(self.folder, "nope.json")),
                         {})

    def test_a_file_that_is_not_json_reads_as_nothing(self):
        path = os.path.join(self.folder, "broken.json")
        with open(path, "wb") as handle:
            handle.write(b"{not json at all")
        self.assertEqual(settings.read(path), {})

    def test_a_json_file_that_is_not_a_dict_reads_as_nothing(self):
        path = os.path.join(self.folder, "list.json")
        with open(path, "wb") as handle:
            handle.write(b"[1, 2, 3]")
        self.assertEqual(settings.read(path), {})

    def test_write_makes_the_folder_and_reports_a_failure_instead_of_raising(self):
        nested = os.path.join(self.folder, "a", "b", "settings.json")
        self.assertIsNone(settings.write(nested, settings.payload({})))
        self.assertTrue(os.path.isfile(nested))
        # a value json cannot encode is reported, not raised
        failure = settings.write(os.path.join(self.folder, "bad.json"),
                                 {"controls": {"x": object()}})
        self.assertTrue(failure)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""naming + prefs -- how auto-created types are named, and that it sticks.

Every builder that duplicates a type asks naming for the new type's name, so a
template the user typed on the Naming tab decides it. Covered here: the sizes
each template may use, what a malformed one does (falls back rather than failing
a build), and that templates and standard sizes survive to the next session
through the preferences file. Standalone (no Revit).
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)


def _load():
    for name in ("_nm",):
        if name not in sys.modules:
            module = types.ModuleType(name)
            module.__path__ = []
            sys.modules[name] = module

    def load(full, *parts):
        spec = importlib.util.spec_from_file_location(full, os.path.join(_PKG, *parts))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        parent, child = full.rsplit(".", 1)
        setattr(sys.modules[parent], child, mod)
        spec.loader.exec_module(mod)
        return mod

    load("_nm.prefs", "prefs.py")
    return load("_nm.naming", "naming.py"), sys.modules["_nm.prefs"]


naming, prefs = _load()


class DefaultNames(unittest.TestCase):
    def setUp(self):
        naming.apply({})

    def test_the_shipped_names_are_what_the_builders_used_to_hard_code(self):
        self.assertEqual(naming.column_type_name(400, 600), "400 X 600")
        self.assertEqual(naming.circular_column_type_name(600), "600D")
        self.assertEqual(naming.beam_type_name(300, 600), "300 X 600")
        self.assertEqual(naming.beam_type_name(300), "300")
        self.assertEqual(naming.floor_type_name(200), "200 THK")
        self.assertEqual(naming.stair_type_name(150, 300, 1500, 200),
                         "cad2bim 150R x 300T x 1500W x 200wst")
        self.assertEqual(naming.stair_waist_type_name(200), "cad2bim waist 200")
        self.assertEqual(naming.level_name(2, 3000, "First Floor"),
                         "CAD Level 2")
        self.assertEqual(naming.grid_name("A"), "A")
        self.assertEqual(naming.footing_type_name(600), "PAD 600 THK")

    def test_sizes_are_whole_millimetres(self):
        # a float size must never leak "400.0" into a type name
        self.assertEqual(naming.column_type_name(400.0, 599.6), "400 X 600")
        self.assertEqual(naming.floor_type_name(199.7), "200 THK")


class CustomTemplates(unittest.TestCase):
    def tearDown(self):
        naming.apply({})

    def test_an_office_convention_replaces_the_default(self):
        naming.apply({"column_rect": "RC-C {b}x{h}",
                      "floor": "SLAB {t}"})
        self.assertEqual(naming.column_type_name(400, 600), "RC-C 400x600")
        self.assertEqual(naming.floor_type_name(200), "SLAB 200")
        # untouched templates keep their default
        self.assertEqual(naming.beam_type_name(300, 600), "300 X 600")

    def test_a_blank_template_keeps_the_default(self):
        naming.apply({"column_rect": "   "})
        self.assertEqual(naming.column_type_name(400, 600), "400 X 600")

    def test_an_unknown_key_is_ignored(self):
        naming.apply({"not_a_type": "{x}"})
        self.assertEqual(naming.templates()["column_rect"],
                         naming.DEFAULTS["column_rect"])
        self.assertNotIn("not_a_type", naming.templates())

    def test_a_bad_template_falls_back_instead_of_failing_the_build(self):
        naming.apply({"column_rect": "C {b} {nope}"})
        self.assertEqual(naming.column_type_name(400, 600), "400 X 600")
        self.assertTrue(any("column_rect" in p for p in naming.problems()))

    def test_validate_explains_a_bad_template_before_it_is_used(self):
        self.assertIsNone(naming.validate("column_rect", "C{b}-{h}"))
        self.assertIsNotNone(naming.validate("column_rect", "C{b}-{depth}"))
        self.assertIsNotNone(naming.validate("floor", "   "))
        self.assertIsNotNone(naming.validate("no_such_key", "{b}"))

    def test_levels_and_grids_take_a_convention_too(self):
        naming.apply({"level": "{label} (L{n} @{e})", "grid": "G-{name}"})
        self.assertEqual(naming.level_name(2, 3000, "First Floor"),
                         "First Floor (L2 @3000)")
        self.assertEqual(naming.grid_name("A"), "G-A")

    def test_a_level_with_no_plan_title_still_names_cleanly(self):
        naming.apply({"level": "L{n} {label}"})
        self.assertEqual(naming.level_name(3, 6000, None), "L3")

    def test_a_grid_the_convention_did_not_name_stays_unnamed(self):
        # the builder skips an empty name and keeps Revit's own, so a grid the
        # drawing never labelled must NOT come back as the literal template
        self.assertEqual(naming.grid_name(None), "")
        naming.apply({"grid": "G-{name}"})
        self.assertEqual(naming.grid_name(""), "")
        self.assertEqual(naming.grid_name("B2"), "G-B2")

    def test_footings_take_a_convention_too(self):
        # a pad is a FLOOR, so its type carries only a thickness -- naming it
        # after a plan size would invent one type per column
        naming.apply({"footing": "PCC-{t}"})
        self.assertEqual(naming.footing_type_name(600), "PCC-600")

    def test_a_template_may_ignore_the_sizes_entirely(self):
        naming.apply({"floor": "GENERIC SLAB"})
        self.assertEqual(naming.floor_type_name(200), "GENERIC SLAB")


class LevelNames(unittest.TestCase):
    """New levels are named, not numbered "CAD Level 11" whatever was typed."""

    def setUp(self):
        naming.apply({})

    def test_the_template_decides_the_name(self):
        naming.apply({"level": "{o} Floor Level"})
        self.assertEqual(naming.level_name(3, 9000), "3rd Floor Level")
        self.assertEqual(naming.level_name(11, 33000), "11th Floor Level")

    def test_the_ordinal_field_reads_properly(self):
        for number, text in ((1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"),
                             (11, "11th"), (12, "12th"), (13, "13th"),
                             (21, "21st"), (22, "22nd"), (23, "23rd"),
                             (101, "101st"), (111, "111th")):
            self.assertEqual(naming.ordinal(number), text)


class ContinuingTheModelsOwnLevelNames(unittest.TestCase):
    """An office template arrives with its levels already named.

    "00 GROUND LVL", "01 1ST FLOOR LVL.", "02 2ND FLOOR LVL." -- a level this
    run adds should read like the next line of that list.
    """

    EXISTING = ["00 GROUND LVL", "01 1ST FLOOR LVL.", "02 2ND FLOOR LVL."]

    def test_the_next_names_continue_the_list(self):
        self.assertEqual(naming.next_level_names(self.EXISTING, 3),
                         ["03 3RD FLOOR LVL.", "04 4TH FLOOR LVL.",
                          "05 5TH FLOOR LVL."])

    def test_the_number_keeps_its_width(self):
        names = naming.next_level_names(["001 GROUND", "002 1ST FLOOR"], 1)
        self.assertEqual(names, ["003 2ND FLOOR"])

    def test_a_separator_is_kept(self):
        names = naming.next_level_names(["00 - GROUND LVL", "01 - 1ST FLOOR"], 2)
        self.assertEqual(names, ["02 - 2ND FLOOR", "03 - 3RD FLOOR"])

    def test_lower_case_names_stay_lower_case(self):
        names = naming.next_level_names(["00 ground", "01 1st floor"], 1)
        self.assertEqual(names, ["02 2nd floor"])

    def test_a_model_with_no_convention_falls_back_to_the_template(self):
        for names in (["Level 1", "Level 2"], ["Ground", "First"], [], None,
                      ["01 1ST FLOOR LVL."]):
            self.assertIsNone(naming.next_level_names(names, 2), names)

    def test_a_body_without_an_ordinal_is_carried_over_as_it_is(self):
        # "00 PODIUM" / "01 PODIUM" -- nothing to move on, so the number does
        # the work and the words stay put
        names = naming.next_level_names(["00 PODIUM", "01 PODIUM"], 2)
        self.assertEqual(names, ["02 PODIUM", "03 PODIUM"])

    def test_the_highest_level_is_what_gets_continued(self):
        # levels arrive in whatever order the collector gives them
        shuffled = ["02 2ND FLOOR LVL.", "00 GROUND LVL", "01 1ST FLOOR LVL."]
        self.assertEqual(naming.next_level_names(shuffled, 1),
                         ["03 3RD FLOOR LVL."])


class AcrossSessions(unittest.TestCase):
    """The dialog is rebuilt every run, so conventions live in a file."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        os.environ["ANONGEE_PREFS_DIR"] = self.folder

    def tearDown(self):
        os.environ.pop("ANONGEE_PREFS_DIR", None)
        shutil.rmtree(self.folder, ignore_errors=True)
        naming.apply({})

    def test_templates_come_back_next_session(self):
        naming.save({"column_rect": "RC-C {b}x{h}", "floor": "SLAB {t}"})
        self.assertEqual(naming.load()["column_rect"], "RC-C {b}x{h}")
        self.assertEqual(naming.load()["beam_sized"],
                         naming.DEFAULTS["beam_sized"])

    def test_only_the_changed_templates_are_stored(self):
        naming.save(dict(naming.DEFAULTS))
        self.assertEqual(prefs.load().get("naming"), {})

    def test_standard_sizes_ride_along_in_the_same_file(self):
        prefs.update({"standards": {"column": "230x450, 300x600",
                                    "beam_widths": "230, 300"}})
        naming.save({"floor": "SLAB {t}"})
        saved = prefs.load()
        self.assertEqual(saved["standards"]["beam_widths"], "230, 300")
        self.assertEqual(saved["naming"]["floor"], "SLAB {t}")

    def test_a_corrupt_file_reads_as_no_preferences(self):
        with open(prefs.path(), "wb") as handle:
            handle.write(b"{not json")
        self.assertEqual(prefs.load(), {})
        self.assertEqual(naming.load(), naming.DEFAULTS)

    def test_a_missing_file_reads_as_no_preferences(self):
        self.assertEqual(prefs.load(), {})

    def test_an_unwritable_location_reports_instead_of_raising(self):
        # a FILE where the folder should be: saving must report, never raise
        blocker = os.path.join(self.folder, "blocked")
        with open(blocker, "wb") as handle:
            handle.write(b"not a folder")
        os.environ["ANONGEE_PREFS_DIR"] = os.path.join(blocker, "deeper")
        self.assertFalse(prefs.save({"naming": {}}))
        self.assertIsNotNone(prefs.last_error())

    def test_unserialisable_settings_are_reported_not_raised(self):
        self.assertFalse(prefs.save({"naming": set(["a"])}))
        self.assertIsNotNone(prefs.last_error())


if __name__ == "__main__":
    unittest.main()

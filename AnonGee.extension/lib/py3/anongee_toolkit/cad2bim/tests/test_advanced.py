# -*- coding: utf-8 -*-
"""The advanced-tunables registry: live, honest about defaults, and persistent.

The registry's one promise is LIVENESS: every registered attribute exists in
its module and its consumers read it at call time, so `advanced.apply` actually
changes behaviour. Two tests hold that promise up from both ends. `effective()
== defaults()` on a fresh namespace proves existence and catches DRIFT -- a
constant changed in its module without the registry moving fails by name. And
the frozen-import scan proves no other module took a copy of a registered name
at import, which is the trap that would make an override land in slab_graph
and never reach the code that decides (slab_outlines' _COLUMN_RECT_PAD_MM is
exactly that, and is excluded from the registry for it).

Persistence follows the naming.py idiom: only overrides that differ from the
default are stored, so deleting the preferences file stays a way to get the
defaults back.
"""

import ast
import os
import shutil
import tempfile
import unittest

import _loader

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)


advanced, prefs = _loader.load("advanced", "prefs")


class TheRegistryIsLive(unittest.TestCase):
    def test_every_attribute_exists_and_holds_its_registered_default(self):
        # existence AND drift in one statement: effective() reads each module
        # attribute with getattr, so a renamed constant raises by name, and a
        # changed one fails the equality with both numbers in the message
        self.assertEqual(advanced.effective(), advanced.defaults())

    def test_every_registered_module_is_revit_free(self):
        # apply() imports these to rebind them; one Revit import at module
        # level (the builders) and the whole registry dies outside Revit
        for entry in advanced.REGISTRY:
            self.assertIn(entry.module, advanced._MODULES, entry.key)

    def test_keys_are_unique_and_every_row_reads_as_a_sentence(self):
        keys = [entry.key for entry in advanced.REGISTRY]
        self.assertEqual(len(keys), len(set(keys)))
        for entry in advanced.REGISTRY:
            self.assertTrue(entry.label, entry.key)
            self.assertTrue(entry.unit, entry.key)
            # `effect` is the newcomer's sentence: it has to say something
            self.assertGreater(len(entry.effect), 30, entry.key)

    def test_no_module_froze_a_copy_of_a_registered_name_at_import(self):
        """`from .slab_graph import _HEAL_MM` anywhere would break liveness.

        A module that imports a registered NAME holds the value from import
        time; advanced.apply rebinds the source module's attribute and the
        copy never hears. The excluded _COLUMN_RECT_PAD_MM is the standing
        example. Scanned over the whole package, builders included -- ast
        parses text, no Revit import runs.
        """
        registered = {}
        for entry in advanced.REGISTRY:
            registered.setdefault(entry.module, set()).add(entry.attribute)
        offenders = []
        for folder, _dirs, files in os.walk(_PKG):
            if "tests" in os.path.relpath(folder, _PKG).split(os.sep):
                continue
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(folder, name)
                with open(path, "rb") as handle:
                    tree = ast.parse(handle.read().decode("utf-8"))
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ImportFrom) or not node.module:
                        continue
                    module = node.module.rsplit(".", 1)[-1]
                    for alias in node.names:
                        if alias.name in registered.get(module, ()):
                            offenders.append("{0}: from .{1} import {2}".format(
                                name, module, alias.name))
        self.assertEqual(offenders, [],
                         "import-frozen copies of registered tunables: %s"
                         % offenders)


class ApplyAndReset(unittest.TestCase):
    def tearDown(self):
        advanced.reset()

    def test_an_override_rebinds_the_module_constant(self):
        fold_plan = advanced._MODULES["fold_plan"]
        advanced.apply({"fold_probe_mm": 25.0})
        self.assertEqual(fold_plan._PROBE_MM, 25.0)
        # ...and only that one moved
        expected = advanced.defaults()
        expected["fold_probe_mm"] = 25.0
        self.assertEqual(advanced.effective(), expected)

    def test_apply_is_idempotent_two_runs_never_inherit_each_other(self):
        advanced.apply({"beam_heal_mm": 400.0})
        advanced.apply({"joint_tol_mm": 5.0})
        expected = advanced.defaults()
        expected["joint_tol_mm"] = 5.0
        self.assertEqual(advanced.effective(), expected)

    def test_reset_restores_every_default(self):
        advanced.apply({"beam_heal_mm": 400.0, "plan_min_region_m2": 9.0})
        advanced.reset()
        self.assertEqual(advanced.effective(), advanced.defaults())

    def test_a_whole_number_tunable_stays_a_whole_number(self):
        advanced.apply({"arc_chords": 24.6})
        self.assertEqual(advanced._MODULES["slab_graph"]._ARC_CHORDS, 25)
        self.assertIsInstance(advanced._MODULES["slab_graph"]._ARC_CHORDS, int)

    def test_a_value_that_is_not_a_number_keeps_the_default_and_says_so(self):
        # a wrong NUMBER here fails quietly by design; a non-number must not
        advanced.apply({"beam_heal_mm": "six hundred"})
        self.assertEqual(advanced._MODULES["slab_graph"]._HEAL_MM, 600.0)
        self.assertTrue(any("beam_heal_mm" in p for p in advanced.problems()))

    def test_a_key_the_registry_does_not_know_is_ignored(self):
        advanced.apply({"not_a_tunable": 1.0})
        self.assertEqual(advanced.effective(), advanced.defaults())

    def test_a_text_number_from_a_hand_edited_file_still_lands(self):
        advanced.apply({"beam_heal_mm": "400"})
        self.assertEqual(advanced._MODULES["slab_graph"]._HEAL_MM, 400.0)


class AcrossSessions(unittest.TestCase):
    """Overrides live in the preferences file under their own "advanced" key,
    applied by the pushbutton before any planning runs."""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        os.environ["ANONGEE_PREFS_DIR"] = self.folder

    def tearDown(self):
        os.environ.pop("ANONGEE_PREFS_DIR", None)
        shutil.rmtree(self.folder, ignore_errors=True)
        advanced.reset()

    def test_overrides_come_back_next_session(self):
        advanced.save({"beam_heal_mm": 400.0, "fold_probe_mm": 25.0})
        self.assertEqual(advanced.load(),
                         {"beam_heal_mm": 400.0, "fold_probe_mm": 25.0})

    def test_only_the_changed_values_are_stored(self):
        # a file of defaults is the same as no file -- deleting it must stay
        # a way to get the defaults back, exactly as naming.save keeps only
        # the changed templates
        advanced.save(dict(advanced.defaults()))
        self.assertEqual(prefs.load().get("advanced"), {})

    def test_unknown_keys_and_rubbish_values_never_reach_the_file(self):
        advanced.save({"beam_heal_mm": "not a number", "who_knows": 3.0,
                       "joint_tol_mm": 5.0})
        self.assertEqual(prefs.load().get("advanced"), {"joint_tol_mm": 5.0})

    def test_the_round_trip_actually_changes_the_module(self):
        advanced.save({"plan_min_region_m2": 9.0})
        advanced.apply(advanced.load())
        self.assertEqual(advanced._MODULES["floor_plans"]._MIN_REGION_M2, 9.0)

    def test_a_hand_edited_file_with_a_wrong_shape_reads_as_no_overrides(self):
        prefs.update({"advanced": ["not", "a", "dict"]})
        self.assertEqual(advanced.load(), {})

    def test_naming_and_standards_ride_the_same_file_untouched(self):
        prefs.update({"naming": {"floor": "SLAB {t}"}})
        advanced.save({"joint_tol_mm": 5.0})
        saved = prefs.load()
        self.assertEqual(saved["naming"], {"floor": "SLAB {t}"})
        self.assertEqual(saved["advanced"], {"joint_tol_mm": 5.0})


if __name__ == "__main__":
    unittest.main()

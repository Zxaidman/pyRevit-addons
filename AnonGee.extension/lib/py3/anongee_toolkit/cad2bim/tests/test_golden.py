# -*- coding: utf-8 -*-
"""_golden -- the compare step the regression legs are built on.

Three regression harnesses were lost because they lived in a scratchpad and were
never committed: the stored slab fingerprints, the 17-DXF sweep and the
storey/roof replays. Without them "no regressions" is an assertion, not a
measurement. They are being rebuilt as committed code, and all three reduce to
the same move: compute numbers over a fixed corpus, compare them against a
stored baseline, and say precisely what moved.

That compare is the part with logic in it, so it is the part with tests. A
golden-file harness whose baseline is written by the same run it is checked
against proves nothing on its own -- what has to be proved is that a real change
is CAUGHT, and named well enough to act on. Standalone (no Revit).
"""

import os
import shutil
import tempfile
import unittest

# _golden lives beside the tests, not inside the package, so it is a plain
# import -- _loader is for cad2bim modules, which cannot be imported by name.
import _golden


class Differences(unittest.TestCase):
    def test_identical_numbers_report_nothing(self):
        data = {"Test1": {"rects": 61, "beams": 141}}
        self.assertEqual(_golden.differences(data, dict(data)), [])

    def test_a_moved_number_is_named_with_both_values(self):
        before = {"Test1": {"rects": 61, "beams": 141}}
        after = {"Test1": {"rects": 63, "beams": 141}}
        found = _golden.differences(before, after)
        self.assertEqual(len(found), 1)
        self.assertIn("Test1", found[0])
        self.assertIn("rects", found[0])
        self.assertIn("61", found[0])
        self.assertIn("63", found[0])

    def test_every_moved_number_is_reported_not_just_the_first(self):
        before = {"Test1": {"rects": 61, "beams": 141},
                  "Test2": {"rects": 20, "beams": 30}}
        after = {"Test1": {"rects": 62, "beams": 140},
                 "Test2": {"rects": 20, "beams": 31}}
        self.assertEqual(len(_golden.differences(before, after)), 3)

    def test_a_fixture_that_vanished_is_reported(self):
        found = _golden.differences({"Test1": {"rects": 1}}, {})
        self.assertEqual(len(found), 1)
        self.assertIn("Test1", found[0])

    def test_a_fixture_that_appeared_is_reported(self):
        found = _golden.differences({}, {"Test9": {"rects": 1}})
        self.assertEqual(len(found), 1)
        self.assertIn("Test9", found[0])

    def test_a_metric_that_vanished_is_reported(self):
        found = _golden.differences({"Test1": {"rects": 1, "beams": 2}},
                                    {"Test1": {"rects": 1}})
        self.assertEqual(len(found), 1)
        self.assertIn("beams", found[0])

    def test_the_report_is_ordered_so_two_runs_read_the_same(self):
        before = {"B": {"y": 1, "x": 1}, "A": {"x": 1}}
        after = {"B": {"y": 2, "x": 2}, "A": {"x": 2}}
        self.assertEqual(_golden.differences(before, after),
                         _golden.differences(before, after))
        self.assertTrue(_golden.differences(before, after)[0].startswith("A"))

    def test_a_float_that_only_LOOKS_different_is_not_a_change(self):
        # areas are rounded before they are stored; 9.0 read back from JSON must
        # not read as a move against 9
        self.assertEqual(_golden.differences({"T": {"area": 9.0}},
                                             {"T": {"area": 9}}), [])


class Storing(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "sample.json")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_a_missing_baseline_loads_as_nothing_rather_than_raising(self):
        self.assertIsNone(_golden.load(self.path))

    def test_what_is_saved_is_what_is_loaded(self):
        data = {"Test1": {"rects": 61, "areas": [1.5, 2.5]}}
        _golden.save(self.path, data)
        self.assertEqual(_golden.load(self.path), data)

    def test_a_saved_baseline_is_readable_by_a_human_and_stable_in_git(self):
        _golden.save(self.path, {"B": {"y": 1}, "A": {"x": 2}})
        with open(self.path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("\n", text)                    # indented, not one line
        self.assertLess(text.index('"A"'), text.index('"B"'))   # sorted keys
        self.assertTrue(text.endswith("\n"))         # no no-newline-at-EOF diffs

    def test_saving_creates_the_baselines_folder_if_it_is_not_there_yet(self):
        nested = os.path.join(self.folder, "deeper", "still", "sample.json")
        _golden.save(nested, {"A": {"x": 1}})
        self.assertEqual(_golden.load(nested), {"A": {"x": 1}})


if __name__ == "__main__":
    unittest.main()

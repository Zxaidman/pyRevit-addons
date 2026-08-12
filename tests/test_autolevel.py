# -*- coding: utf-8 -*-
"""Revit-free tests for the Auto Level Manager's thinking parts.

Run from the repository root::

    python3 -m unittest discover -s tests -v

The three modules under test (textparse, naming, planner) never import an
Autodesk namespace, which is the whole point of keeping them separate from
revit_ops: the detection heuristics can be argued with on any machine.
"""

import os
import sys
import unittest

_BUTTON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "AnonGee.extension", "AnonGee.tab", "Essential.panel", "AutoLevel.pushbutton")
if _BUTTON not in sys.path:
    sys.path.insert(0, _BUTTON)

from anongee_autolevel import naming, planner, textparse   # noqa: E402


def entry(text, y=None, source="test"):
    return {"text": text, "y": y, "source": source}


# ── the scanner ────────────────────────────────────────────────────────────

class ScannerTests(unittest.TestCase):

    def test_signed_metre_notation(self):
        got = textparse.parse_line("FFL +3.500")
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got.elevation_mm, 3.5)      # raw magnitude
        self.assertEqual(got.name, "FFL")
        self.assertTrue(got.signed)

    def test_negative_and_unicode_minus(self):
        for text in ("TOS -1.200", u"TOS −1.200"):
            got = textparse.parse_line(text)
            self.assertIsNotNone(got, text)
            self.assertAlmostEqual(got.elevation_mm, -1.2)

    def test_plus_minus_zero(self):
        got = textparse.parse_line(u"± 0.00")
        self.assertIsNotNone(got)
        self.assertEqual(got.elevation_mm, 0.0)

    def test_comma_reads_as_a_decimal_point(self):
        got = textparse.parse_line("FFL +3,500")
        self.assertAlmostEqual(got.elevation_mm, 3.5)

    def test_explicit_units(self):
        cases = {"EL. 3.50 M": 3500.0, "LVL 3500MM": 3500.0,
                 "LVL 350 cm": 3500.0}
        for text, expected in cases.items():
            got = textparse.parse_line(text)
            self.assertIsNotNone(got, text)
            self.assertTrue(got.explicit_unit, text)
            self.assertAlmostEqual(
                got.elevation_mm * textparse.UNIT_FACTORS[got.unit], expected, 3,
                msg=text)

    def test_feet_and_inches(self):
        got = textparse.parse_line("TERRACE LVL +14'-6\"")
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got.elevation_mm, 14 * 304.8 + 6 * 25.4, 3)
        self.assertEqual(got.unit, "ftin")   # already resolved to millimetres

    def test_feet_inches_with_a_fraction(self):
        got = textparse.parse_line("LVL 12'-6 1/2\"")
        self.assertAlmostEqual(got.elevation_mm, 12 * 304.8 + 6.5 * 25.4, 3)

    def test_bare_feet(self):
        got = textparse.parse_line("LVL +38'")
        self.assertAlmostEqual(got.elevation_mm, 38 * 304.8, 3)

    def test_column_marks_are_not_levels(self):
        for text in ("C1 400x400", "B2 230X450", "M20 BOLT"):
            self.assertIsNone(textparse.parse_line(text), text)

    def test_bare_number_needs_evidence(self):
        self.assertIsNone(textparse.parse_line("2400"))
        self.assertIsNotNone(textparse.parse_line("2400", require_evidence=False))

    def test_the_elevation_beats_other_numbers_on_the_line(self):
        got = textparse.parse_line("ROOM 12 FFL +7.000")
        self.assertAlmostEqual(got.elevation_mm, 7.0)

    def test_mtext_codes_are_stripped(self):
        raw = u"{\\fArial|b0|i0;FFL\\P+3.500}"
        self.assertEqual(textparse.split_lines(raw), ["FFL", "+3.500"])

    def test_confidence_rewards_evidence(self):
        strong = textparse.parse_line("SECOND FLOOR FFL +7.000")
        weak = textparse.parse_line("7.00")
        self.assertGreater(strong.confidence, 70)
        self.assertLess(weak.confidence, strong.confidence)


# ── unit inference over a set ──────────────────────────────────────────────

class UnitInferenceTests(unittest.TestCase):

    def test_metre_notation_is_read_as_metres(self):
        result = textparse.detect([entry("FFL +0.000"), entry("FFL +3.500"),
                                   entry("FFL +7.000"), entry("FFL +10.500")])
        self.assertEqual(result.unit, "m")
        self.assertEqual([round(c.elevation_mm) for c in result.candidates],
                         [0, 3500, 7000, 10500])

    def test_millimetre_notation_is_read_as_millimetres(self):
        result = textparse.detect([entry("LVL +0"), entry("LVL +3500"),
                                   entry("LVL +7000"), entry("LVL +10500")])
        self.assertEqual(result.unit, "mm")
        self.assertEqual([round(c.elevation_mm) for c in result.candidates],
                         [0, 3500, 7000, 10500])

    def test_an_explicit_unit_settles_the_whole_set(self):
        result = textparse.detect([entry("LVL 0.000 M"), entry("LVL 3.500"),
                                   entry("LVL 7.000")])
        self.assertEqual(result.unit, "m")

    def test_a_hand_set_unit_is_honoured(self):
        result = textparse.detect([entry("LVL +0"), entry("LVL +3.5"),
                                   entry("LVL +7")], unit_hint="m")
        self.assertEqual(result.unit, "m")
        self.assertAlmostEqual(result.candidates[-1].elevation_mm, 7000.0)

    def test_an_imperial_drawing_reads_its_bare_numbers_as_feet(self):
        """12'-6" resolves to mm on its own; the bare 11.5 beside it is feet."""
        result = textparse.detect([entry("LVL +14'-6\""), entry("LVL +11.5")])
        self.assertEqual(result.unit, "ft")
        values = sorted(round(c.elevation_mm, 1) for c in result.candidates)
        self.assertEqual(values, [round(11.5 * 304.8, 1),
                                  round(14 * 304.8 + 6 * 25.4, 1)])

    def test_datum_offset_rebases_a_site_level(self):
        result = textparse.detect([entry("RL 100.000"), entry("RL 103.500")],
                                  datum_offset_mm=100000.0)
        self.assertEqual([round(c.elevation_mm) for c in result.candidates],
                         [0, 3500])


# ── merging, ordering, position cross-check ────────────────────────────────

class DetectionPipelineTests(unittest.TestCase):

    def test_repeated_annotations_merge_into_one_level(self):
        result = textparse.detect([entry("FFL +3.500"), entry("FFL +3.500"),
                                   entry("FFL +3.502")])
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].merged, 3)

    def test_a_named_duplicate_wins_the_name(self):
        result = textparse.detect([entry("+3.500"),
                                   entry("SECOND FLOOR FFL +3.500")])
        self.assertEqual(len(result.candidates), 1)
        self.assertIn("SECOND FLOOR", result.candidates[0].name)

    def test_candidates_come_back_lowest_first(self):
        result = textparse.detect([entry("FFL +7.000"), entry("FFL +0.000"),
                                   entry("FFL +3.500")])
        values = [c.elevation_mm for c in result.candidates]
        self.assertEqual(values, sorted(values))

    def test_a_text_that_contradicts_its_position_is_flagged(self):
        # y climbs with the written value except for the third one, which is
        # drawn at roof height but labelled as the ground floor.
        entries = [entry("FFL +0.000", y=0.0), entry("FFL +3.500", y=35.0),
                   entry("FFL +0.100", y=70.0), entry("FFL +10.500", y=105.0)]
        result = textparse.detect(entries)
        flagged = [c for c in result.candidates
                   if any("position suggests" in r for r in c.reasons)]
        self.assertEqual(len(flagged), 1)
        self.assertAlmostEqual(flagged[0].elevation_mm, 100.0, 1)

    def test_consistent_positions_flag_nothing(self):
        entries = [entry("FFL +0.000", y=0.0), entry("FFL +3.500", y=35.0),
                   entry("FFL +7.000", y=70.0), entry("FFL +10.500", y=105.0)]
        result = textparse.detect(entries)
        for candidate in result.candidates:
            self.assertNotIn("position suggests", " ".join(candidate.reasons))

    def test_a_real_section_sheet(self):
        entries = [entry(u"TERRACE LVL. +14.000"), entry("2ND FLOOR FFL +10.500"),
                   entry("1ST FLOOR FFL +7.000"), entry("GF FFL +3.500"),
                   entry(u"PLINTH LVL ±0.00"), entry("C1 300x600"),
                   entry("SECTION A-A"), entry("SCALE 1:100")]
        result = textparse.detect(entries)
        self.assertEqual([round(c.elevation_mm) for c in result.candidates],
                         [0, 3500, 7000, 10500, 14000])


# ── inline elevation editing ───────────────────────────────────────────────

class ElevationInputTests(unittest.TestCase):

    def test_accepts_the_shapes_a_user_types(self):
        cases = {"3500": 3500.0, "3.5 m": 3500.0, "+3500": 3500.0,
                 "-1200": -1200.0, "11'-6\"": 11 * 304.8 + 6 * 25.4}
        for text, expected in cases.items():
            self.assertAlmostEqual(textparse.parse_elevation_input(text),
                                   expected, 3, msg=text)

    def test_rejects_nonsense(self):
        for text in ("", "   ", "abc", None):
            self.assertIsNone(textparse.parse_elevation_input(text))


# ── naming ─────────────────────────────────────────────────────────────────

class ConventionTests(unittest.TestCase):

    def test_plain_numbering(self):
        convention = naming.learn_convention(["Level 1", "Level 2", "Level 3"])
        self.assertIsNotNone(convention)
        self.assertEqual(convention.next_names(2), ["Level 4", "Level 5"])

    def test_zero_padded_numbering(self):
        convention = naming.learn_convention(["L01", "L02", "L03"])
        self.assertIsNotNone(convention)
        self.assertEqual(convention.next_names(2), ["L04", "L05"])

    def test_padded_index_and_ordinal_together(self):
        convention = naming.learn_convention(
            ["01 1ST FLOOR LVL.", "02 2ND FLOOR LVL.", "03 3RD FLOOR LVL."])
        self.assertIsNotNone(convention)
        self.assertEqual(convention.next_names(2),
                         ["04 4TH FLOOR LVL.", "05 5TH FLOOR LVL."])

    def test_ordinal_words(self):
        convention = naming.learn_convention(
            ["First Floor", "Second Floor", "Third Floor"])
        self.assertIsNotNone(convention)
        self.assertEqual(convention.next_names(1), ["Fourth Floor"])

    def test_roman_numerals(self):
        convention = naming.learn_convention(["Level I", "Level II", "Level III"])
        self.assertIsNotNone(convention)
        self.assertEqual(convention.next_names(2), ["Level IV", "Level V"])

    def test_a_step_of_more_than_one_is_kept(self):
        convention = naming.learn_convention(["Level 2", "Level 4", "Level 6"])
        self.assertIsNotNone(convention)
        self.assertEqual(convention.next_names(2), ["Level 8", "Level 10"])

    def test_unpatterned_names_return_nothing(self):
        self.assertIsNone(naming.learn_convention(["Ground", "Roof"]))
        self.assertIsNone(naming.learn_convention(["Level 1"]))
        self.assertIsNone(naming.learn_convention([]))

    def test_odd_names_do_not_break_the_majority_pattern(self):
        convention = naming.learn_convention(
            ["Site", "Level 1", "Level 2", "Level 3"])
        self.assertIsNotNone(convention)
        self.assertEqual(convention.next_names(1), ["Level 4"])


class TemplateTests(unittest.TestCase):

    def test_index_tokens(self):
        self.assertEqual(naming.render_template("Level {n}", 7), "Level 7")
        self.assertEqual(naming.render_template("L{nn}", 7), "L07")
        self.assertEqual(naming.render_template("L{nnn}", 7), "L007")
        self.assertEqual(naming.render_template("{ORDINAL} FLOOR", 2),
                         "2ND FLOOR")
        self.assertEqual(naming.render_template("{Word} Floor", 3),
                         "Third Floor")
        self.assertEqual(naming.render_template("Level {roman}", 4), "Level IV")

    def test_elevation_tokens(self):
        self.assertEqual(naming.render_template("FFL {elev_m}", 1, 3500.0),
                         "FFL 3.500")
        self.assertEqual(naming.render_template("FFL {elev_mm}", 1, 3500.0),
                         "FFL 3500")

    def test_eleventh_through_thirteenth_use_th(self):
        self.assertEqual(naming.render_template("{ORDINAL}", 11), "11TH")
        self.assertEqual(naming.render_template("{ORDINAL}", 12), "12TH")
        self.assertEqual(naming.render_template("{ORDINAL}", 13), "13TH")
        self.assertEqual(naming.render_template("{ORDINAL}", 21), "21ST")

    def test_unknown_tokens_survive_untouched(self):
        self.assertEqual(naming.render_template("Level {nope}", 1),
                         "Level {nope}")

    def test_unique_name_avoids_collisions(self):
        self.assertEqual(naming.unique_name("Level 1", ["Level 2"]), "Level 1")
        self.assertEqual(naming.unique_name("Level 1", ["level 1"]),
                         "Level 1 (2)")
        self.assertEqual(naming.unique_name("Level 1", ["Level 1", "Level 1 (2)"]),
                         "Level 1 (3)")

    def test_batch_rename_primitives(self):
        self.assertEqual(naming.apply_affixes("Floor", prefix="B-"), "B-Floor")
        self.assertEqual(naming.apply_affixes("Floor", suffix=" LVL"),
                         "Floor LVL")
        self.assertEqual(naming.apply_affixes("Old Floor", find="Old",
                                              replace="New"), "New Floor")
        self.assertEqual(naming.apply_affixes("floor", case_mode="upper"),
                         "FLOOR")


# ── the plan ───────────────────────────────────────────────────────────────

def sample_plan():
    plan = planner.LevelPlan()
    plan.load_existing([
        {"id": 101, "name": "Level 1", "elev_mm": 0.0, "elements": 40},
        {"id": 102, "name": "Level 2", "elev_mm": 3500.0, "elements": 12},
    ])
    return plan


class PlanTests(unittest.TestCase):

    def test_loading_sorts_and_marks_everything_existing(self):
        plan = sample_plan()
        self.assertEqual([row.Name for row in plan.rows], ["Level 1", "Level 2"])
        self.assertTrue(all(row.State == planner.STATE_EXISTING
                            for row in plan.rows))

    def test_a_detected_level_on_an_existing_one_is_a_match_not_a_duplicate(self):
        plan = sample_plan()
        result = textparse.detect([entry("SECOND FLOOR FFL +3.500")])
        created, matched, renamed = plan.add_candidates(result.candidates)
        self.assertEqual((created, matched), (0, 1))
        self.assertEqual(renamed, 1)
        self.assertEqual(len(plan.rows), 2)
        self.assertEqual(plan.rows[1].State, planner.STATE_RENAME)

    def test_a_detected_level_off_the_stack_is_created(self):
        plan = sample_plan()
        result = textparse.detect([entry("THIRD FLOOR FFL +7.000")])
        created, matched, _renamed = plan.add_candidates(result.candidates)
        self.assertEqual((created, matched), (1, 0))
        self.assertEqual(plan.rows[-1].State, planner.STATE_NEW)
        self.assertAlmostEqual(plan.rows[-1].ElevMm, 7000.0)

    def test_matching_respects_the_tolerance(self):
        plan = sample_plan()
        result = textparse.detect([entry("FFL +3.520")])   # 20 mm off
        created, matched, _ = plan.add_candidates(result.candidates,
                                                  tolerance_mm=25.0)
        self.assertEqual((created, matched), (0, 1))
        plan = sample_plan()
        created, matched, _ = plan.add_candidates(result.candidates,
                                                  tolerance_mm=5.0)
        self.assertEqual((created, matched), (1, 0))

    def test_generate_follows_the_models_own_naming(self):
        plan = sample_plan()
        count, note = plan.generate(2, height_mm=3500.0, mode="follow")
        self.assertEqual(count, 2)
        self.assertEqual([row.Name for row in plan.rows],
                         ["Level 1", "Level 2", "Level 3", "Level 4"])
        self.assertAlmostEqual(plan.rows[-1].ElevMm, 10500.0)
        self.assertIn("continues", note)

    def test_generate_falls_back_to_the_template(self):
        plan = planner.LevelPlan()
        plan.load_existing([{"id": 1, "name": "Ground", "elev_mm": 0.0}])
        count, note = plan.generate(2, height_mm=3000.0, mode="follow",
                                    template="FL {nn}")
        self.assertEqual(count, 2)
        self.assertIn("no naming pattern", note)
        self.assertEqual([row.Name for row in plan.rows[1:]], ["FL 01", "FL 02"])

    def test_generated_names_never_collide(self):
        plan = planner.LevelPlan()
        plan.load_existing([{"id": 1, "name": "FL 01", "elev_mm": 0.0}])
        plan.generate(1, mode="template", template="FL {nn}", start_index=1)
        self.assertEqual(plan.rows[-1].Name, "FL 01 (2)")

    def test_renaming_rejects_a_duplicate(self):
        plan = sample_plan()
        ok, message = plan.rename(plan.rows[0], "Level 2")
        self.assertFalse(ok)
        self.assertIn("already taken", message)
        self.assertEqual(plan.rows[0].Name, "Level 1")

    def test_renaming_rejects_an_empty_name(self):
        plan = sample_plan()
        ok, _message = plan.rename(plan.rows[0], "   ")
        self.assertFalse(ok)

    def test_moving_one_level_leaves_the_others_alone(self):
        plan = sample_plan()
        ok, _ = plan.set_elevation(plan.rows[1], "4000")
        self.assertTrue(ok)
        self.assertAlmostEqual(plan.rows[0].ElevMm, 0.0)
        self.assertEqual(plan.rows[1].State, planner.STATE_MOVE)

    def test_push_above_carries_the_stack(self):
        plan = sample_plan()
        plan.generate(1, height_mm=3500.0)                  # 0, 3500, 7000
        ok, _ = plan.set_elevation(plan.rows[1], 4000.0, push_above=True)
        self.assertTrue(ok)
        self.assertEqual([round(row.ElevMm) for row in plan.rows],
                         [0, 4000, 7500])

    def test_respace_makes_the_stack_uniform(self):
        plan = planner.LevelPlan()
        plan.load_existing([
            {"id": 1, "name": "A", "elev_mm": 0.0},
            {"id": 2, "name": "B", "elev_mm": 3300.0},
            {"id": 3, "name": "C", "elev_mm": 6100.0}])
        changed = plan.respace(3000.0)
        self.assertEqual(changed, 2)
        self.assertEqual([round(row.ElevMm) for row in plan.rows],
                         [0, 3000, 6000])

    def test_batch_rename_applies_and_reports_collisions(self):
        plan = sample_plan()
        changed, collisions = plan.batch_rename(plan.rows, prefix="B-")
        self.assertEqual(changed, 2)
        self.assertEqual(collisions, [])
        self.assertEqual([row.Name for row in plan.rows],
                         ["B-Level 1", "B-Level 2"])

    def test_batch_rename_by_template(self):
        plan = sample_plan()
        changed, _ = plan.batch_rename(plan.rows, use_template=True,
                                       template="L{nn}", start_index=1)
        self.assertEqual(changed, 2)
        self.assertEqual([row.Name for row in plan.rows], ["L01", "L02"])

    def test_batch_rename_reports_a_collision_instead_of_making_one(self):
        plan = sample_plan()
        changed, collisions = plan.batch_rename([plan.rows[0]],
                                                find="1", replace="2")
        self.assertEqual(changed, 0)
        self.assertEqual(collisions, ["Level 2"])

    def test_deleting_a_new_row_just_drops_it(self):
        plan = sample_plan()
        plan.generate(1)
        plan.mark_delete([plan.rows[-1]])
        self.assertEqual(len(plan.rows), 2)

    def test_deleting_an_existing_row_stages_it(self):
        plan = sample_plan()
        plan.mark_delete([plan.rows[1]])
        self.assertEqual(plan.rows[1].State, planner.STATE_DELETE)
        self.assertEqual(len(plan.live_rows()), 1)

    def test_undoing_a_delete_restores_the_row(self):
        plan = sample_plan()
        plan.mark_delete([plan.rows[1]])
        plan.mark_delete([plan.rows[1]], deleted=False)
        self.assertEqual(plan.rows[1].State, planner.STATE_EXISTING)

    def test_reset_drops_proposals_and_edits(self):
        plan = sample_plan()
        plan.generate(2)
        plan.rename(plan.rows[0], "Renamed")
        plan.remove_proposed()
        self.assertEqual([row.Name for row in plan.rows], ["Level 1", "Level 2"])
        self.assertTrue(all(row.State == planner.STATE_EXISTING
                            for row in plan.rows))


class ValidationTests(unittest.TestCase):

    def test_duplicate_names_are_an_error(self):
        plan = sample_plan()
        plan.rows[1].Name = "Level 1"
        issues = plan.validate()
        self.assertTrue(plan.has_blocking_issues())
        self.assertTrue(any("Duplicate" in message
                            for _s, _r, message in issues))

    def test_levels_stacked_on_top_of_each_other_are_a_warning(self):
        plan = sample_plan()
        plan.rows[1].ElevMm = 50.0
        issues = plan.validate()
        self.assertFalse(plan.has_blocking_issues())
        self.assertTrue(any(severity == "warn" for severity, _r, _m in issues))

    def test_deleting_a_populated_level_warns(self):
        plan = sample_plan()
        plan.mark_delete([plan.rows[0]])            # 40 hosted elements
        issues = plan.validate()
        self.assertTrue(any("hosted" in message for _s, _r, message in issues))

    def test_display_strings_are_filled_in(self):
        plan = sample_plan()
        plan.generate(1, height_mm=3500.0)
        plan.refresh_display()
        self.assertEqual(plan.rows[0].DeltaText, "base")
        self.assertEqual(plan.rows[1].DeltaText, "+3500")
        self.assertEqual(plan.rows[2].StateText, "New")
        self.assertEqual(plan.rows[0].CountText, "40")

    def test_display_uses_the_projects_own_formatter(self):
        plan = sample_plan()
        plan.refresh_display(formatter=lambda mm: "{0:.2f} m".format(mm / 1000.0))
        self.assertEqual(plan.rows[1].ProjectText, "3.50 m")


class OperationTests(unittest.TestCase):

    def test_a_clean_plan_asks_for_nothing(self):
        operations = sample_plan().to_operations()
        self.assertEqual(operations["creates"], [])
        self.assertEqual(operations["renames"], [])
        self.assertEqual(operations["moves"], [])
        self.assertEqual(operations["deletes"], [])

    def test_every_kind_of_change_is_carried_across(self):
        plan = sample_plan()
        plan.generate(1, height_mm=3500.0)
        plan.rename(plan.rows[0], "Ground")
        plan.set_elevation(plan.rows[1], 3600.0)
        plan.mark_delete([plan.rows[1]])
        operations = plan.to_operations(create_views=True, view_type_ids=[9])
        self.assertEqual(len(operations["creates"]), 1)
        self.assertEqual(operations["renames"][0]["name"], "Ground")
        self.assertEqual(operations["deletes"][0]["id"], 102)
        self.assertEqual(operations["moves"], [])       # deleted rows don't move
        self.assertTrue(operations["create_views"])
        self.assertEqual(operations["view_type_ids"], [9])

    def test_a_rename_and_a_move_on_one_level_produce_both(self):
        plan = sample_plan()
        plan.rename(plan.rows[1], "Upper")
        plan.set_elevation(plan.rows[1], 4000.0)
        operations = plan.to_operations()
        self.assertEqual(len(operations["renames"]), 1)
        self.assertEqual(len(operations["moves"]), 1)
        self.assertEqual(plan.rows[1].State, planner.STATE_EDIT)

    def test_the_summary_counts_pending_changes(self):
        plan = sample_plan()
        plan.generate(2)
        plan.rename(plan.rows[0], "Ground")
        counts = plan.summary()
        self.assertEqual(counts["new"], 2)
        self.assertEqual(counts["rename"], 1)
        self.assertEqual(counts["changes"], 3)


# ── end to end, still without Revit ────────────────────────────────────────

class EndToEndTests(unittest.TestCase):

    def test_a_section_sheet_becomes_a_change_set(self):
        plan = planner.LevelPlan()
        plan.load_existing([{"id": 1, "name": "Level 1", "elev_mm": 0.0}])
        result = textparse.detect([
            entry(u"PLINTH LVL ±0.00", y=0.0),
            entry("GF FFL +3.500", y=35.0),
            entry("1ST FLOOR FFL +7.000", y=70.0),
            entry("2ND FLOOR FFL +10.500", y=105.0),
            entry("C1 300x600", y=20.0),
            entry("SCALE 1:100", y=-30.0)])
        created, matched, _renamed = plan.add_candidates(result.candidates)
        self.assertEqual((created, matched), (3, 1))
        plan.refresh_display()
        operations = plan.to_operations()
        self.assertEqual(len(operations["creates"]), 3)
        self.assertEqual([round(c["elev_mm"]) for c in operations["creates"]],
                         [3500, 7000, 10500])
        self.assertFalse(plan.has_blocking_issues())


if __name__ == "__main__":                                    # pragma: no cover
    unittest.main(verbosity=2)

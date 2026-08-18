# -*- coding: utf-8 -*-
"""Foundation layers and foundation labels.

Footings have always been INVENTED: `footing_plan.pads_for` reads column
rectangles, grows them by a projection and merges the overlaps. Nothing came
from the drawing, and `builders/footings.py` discarded any footprint bigger than
a column, so a raft could not be produced at all.

The drawing has been carrying the answer the whole time. test10's foundation
level (supplied 2026-08-13):

    S-FND        12 LWPOLYLINE + 8 LINE   footing and raft outlines
    S-FND-IDEN   19 MTEXT                 F3_1500MM THK / 2000MM FOLD
    S-FND-FOLD    6 HATCH (ANSI37)        fold regions
    S-FND-SUNK    1 HATCH (ANSI37)        sunk region

and Test0 turns out to carry an `S-FNDN` layer too -- 187 entities that have
been classified as unmapped, and therefore ignored, since the day it was added.

Two things are tested here. That the four new categories pick up exactly the
layers they should and NOTHING else -- the existing corpus must classify
identically, or every regression baseline moves. And that the label parses,
including the second paragraph a stepped foundation carries after `\\P`, which
the DXF reader hands over as a newline.
"""

import unittest

import _loader


layers, foundation_labels = _loader.load("classify.layers", "foundation_labels")


class NewLayerCategories(unittest.TestCase):
    def test_a_foundation_outline_layer_is_recognised(self):
        self.assertEqual(layers.classify_layer("S-FND"),
                         layers.CATEGORY_FOUNDATION)

    def test_the_layer_Test0_has_been_ignoring_for_months_is_recognised(self):
        self.assertEqual(layers.classify_layer("S-FNDN"),
                         layers.CATEGORY_FOUNDATION)

    def test_a_fold_layer_is_a_FOLD_not_a_foundation(self):
        # "S-FND-FOLD" contains "fnd"; the step layers have to be tested first
        self.assertEqual(layers.classify_layer("S-FND-FOLD"),
                         layers.CATEGORY_FOLD)

    def test_a_sunk_layer_is_a_SUNK_not_a_foundation(self):
        self.assertEqual(layers.classify_layer("S-FND-SUNK"),
                         layers.CATEGORY_SUNK)

    def test_the_foundation_TEXT_layer_carries_no_geometry(self):
        # excluded by the "iden" rule, which is correct -- it is a text layer
        self.assertEqual(layers.classify_layer("S-FND-IDEN"),
                         layers.CATEGORY_UNMAPPED)

    def test_the_foundation_text_layer_is_routed_to_foundation_text(self):
        self.assertEqual(layers.classify_text_layer("S-FND-IDEN"),
                         layers.CATEGORY_FOUNDATION_TEXT)

    def test_the_new_categories_are_offered_to_the_override_dialog(self):
        for category in (layers.CATEGORY_FOUNDATION, layers.CATEGORY_FOLD,
                         layers.CATEGORY_SUNK):
            self.assertIn(category, layers.ALL_CATEGORIES)
        self.assertIn(layers.CATEGORY_FOUNDATION_TEXT, layers.TEXT_CATEGORIES)


class TheHatchLayersHaveTheirOwnConvention(unittest.TestCase):
    """Hatches map on their own table, apart from geometry and text.

    classify_hatch_layer routes a HATCH layer to a region meaning -- column
    fill / fold / sunk / cutout -- and nothing else. Every layer name here is
    a real one from the corpus.
    """

    def test_the_step_layers_route_as_they_do_in_geometry(self):
        # test10's convention: the tokens carry over, so the sweep's fold and
        # sunk counts must not move when regions switch to this convention
        self.assertEqual(layers.classify_hatch_layer("S-FND-FOLD"),
                         layers.CATEGORY_FOLD)
        self.assertEqual(layers.classify_hatch_layer("S-FND-SUNK"),
                         layers.CATEGORY_SUNK)

    def test_a_column_fill_layer_is_a_column_region(self):
        # test10's S-COLS carries 330 column fills, test9's PI_COLUMN HATCH
        # 106, Project1's COLUMN HATCH_ASC 218
        for name in ("S-COLS", "PI_COLUMN HATCH", "COLUMN HATCH_ASC"):
            self.assertEqual(layers.classify_hatch_layer(name),
                             layers.CATEGORY_COLUMN, name)

    def test_a_cutout_layer_routes_by_name_here_and_only_here(self):
        # the GEOMETRY convention deliberately has no cutout token (it would
        # re-route test9's shear-wall linework); the hatch convention may
        # carry one because routing a hatch layer never moves linework
        self.assertEqual(layers.classify_hatch_layer("PI_SHEAR WALL CUTOUT"),
                         layers.CATEGORY_CUTOUT)
        self.assertEqual(layers.classify_layer("PI_SHEAR WALL CUTOUT"),
                         layers.CATEGORY_STRUCT_WALL)

    def test_everything_else_is_unmapped(self):
        # geometry categories a hatch cannot be: a wall hatch, a slab hatch,
        # a plain hatch layer, the empty name
        for name in ("PI_RETAINING WALL HATCH", "PT SLAB HATCH", "PI_HATCH",
                     "SYMBOL", ".", "0", "", None):
            self.assertEqual(layers.classify_hatch_layer(name),
                             layers.CATEGORY_UNMAPPED, repr(name))

    def test_an_annotation_layer_is_excluded_first(self):
        # the exclusions run first, as in classify_layer: a hatch on an
        # -IDEN or -ANNO layer is decoration, whatever else the name says
        self.assertEqual(layers.classify_hatch_layer("S-COLS-IDEN"),
                         layers.CATEGORY_UNMAPPED)

    def test_the_hatch_category_list_is_the_dialogs_and_ends_unmapped(self):
        # _build_rows falls back to the LAST item when a default is missing
        self.assertEqual(layers.HATCH_CATEGORIES,
                         (layers.CATEGORY_COLUMN, layers.CATEGORY_FOLD,
                          layers.CATEGORY_SUNK, layers.CATEGORY_CUTOUT,
                          layers.CATEGORY_UNMAPPED))

    def test_the_default_hatch_mapping_covers_every_key(self):
        mapping = layers.build_default_hatch_mapping(
            ["S-FND-FOLD", "S-COLS", "PI_HATCH"])
        self.assertEqual(mapping,
                         {"S-FND-FOLD": layers.CATEGORY_FOLD,
                          "S-COLS": layers.CATEGORY_COLUMN,
                          "PI_HATCH": layers.CATEGORY_UNMAPPED})


class TheRestOfTheCorpusIsUntouched(unittest.TestCase):
    """Every layer name in the 17 fixtures that could plausibly collide with the
    new patterns. If one of these moves, so does every regression baseline."""

    def test_structural_layers_keep_their_categories(self):
        self.assertEqual(layers.classify_layer("S-COLS"),
                         layers.CATEGORY_COLUMN)
        self.assertEqual(layers.classify_layer("S-BEAM"),
                         layers.CATEGORY_BEAM)
        self.assertEqual(layers.classify_layer("A-FLOR"),
                         layers.CATEGORY_SLAB_EDGE)
        self.assertEqual(layers.classify_layer("S-GRID"),
                         layers.CATEGORY_GRID)

    def test_a_STEP_layer_is_still_a_stair_not_a_foundation(self):
        # Project1/Test8 draw "A-STAIR-Steps"; "foot"/"step" must not drag it in
        self.assertEqual(layers.classify_layer("A-STAIR-Steps"),
                         layers.CATEGORY_STAIR)

    def test_a_THK_wall_layer_is_still_a_wall(self):
        self.assertEqual(layers.classify_layer("JW_ 150 thk NON-STRU. WALL"),
                         layers.CATEGORY_ARCH_WALL)

    def test_a_retaining_wall_is_still_a_structural_wall(self):
        self.assertEqual(layers.classify_layer("PI_RETAINING WALL"),
                         layers.CATEGORY_STRUCT_WALL)

    def test_text_routing_is_unchanged_for_the_layers_that_had_it(self):
        self.assertEqual(layers.classify_text_layer("S-COLS-IDEN"),
                         layers.CATEGORY_COLUMN_TEXT)
        self.assertEqual(layers.classify_text_layer("S-BEAM-IDEN"),
                         layers.CATEGORY_BEAM_TEXT)
        self.assertEqual(layers.classify_text_layer("S-GRID-IDEN"),
                         layers.CATEGORY_GRID_TEXT)


class ParsingTheLabel(unittest.TestCase):
    """Every distinct label form test10 actually contains, verbatim."""

    def test_a_plain_footing_label(self):
        found = foundation_labels.parse("F1_1200MM THK")
        self.assertEqual(found["mark"], "F1")
        self.assertEqual(found["thickness_mm"], 1200.0)
        self.assertIsNone(found["step_mm"])
        self.assertIsNone(found["step_kind"])

    def test_a_folded_footing_label(self):
        found = foundation_labels.parse("F3_1500MM THK\n2000MM FOLD")
        self.assertEqual(found["mark"], "F3")
        self.assertEqual(found["thickness_mm"], 1500.0)
        self.assertEqual(found["step_mm"], 2000.0)
        self.assertEqual(found["step_kind"], "fold")

    def test_a_sunk_footing_label(self):
        found = foundation_labels.parse("F6_1000MM THK\n1000MM SUNK")
        self.assertEqual(found["mark"], "F6")
        self.assertEqual(found["thickness_mm"], 1000.0)
        self.assertEqual(found["step_mm"], 1000.0)
        self.assertEqual(found["step_kind"], "sunk")

    def test_the_raw_MTEXT_paragraph_break_reads_the_same_as_a_newline(self):
        # belt and braces: the reader converts \P, a hand-built record may not
        self.assertEqual(foundation_labels.parse("F3_1500MM THK\\P2000MM FOLD"),
                         foundation_labels.parse("F3_1500MM THK\n2000MM FOLD"))

    def test_every_thickness_the_drawing_uses(self):
        for mark, thickness in (("F1", 1200), ("F2", 1200), ("F3", 1500),
                                ("F4", 800), ("F5", 2000), ("F6", 1000)):
            text = "{0}_{1}MM THK".format(mark, thickness)
            self.assertEqual(foundation_labels.parse(text)["thickness_mm"],
                             float(thickness), text)


class ParsingIsForgiving(unittest.TestCase):
    def test_case_and_spacing_do_not_matter(self):
        found = foundation_labels.parse("  f3 _ 1500 mm thk \n 2000 mm fold ")
        self.assertEqual(found["mark"], "F3")
        self.assertEqual(found["thickness_mm"], 1500.0)
        self.assertEqual(found["step_kind"], "fold")

    def test_a_space_separator_works_like_an_underscore(self):
        self.assertEqual(foundation_labels.parse("F3 1500MM THK")["mark"], "F3")

    def test_MM_may_be_left_off(self):
        self.assertEqual(foundation_labels.parse("F3_1500 THK")["thickness_mm"],
                         1500.0)

    def test_an_unmarked_thickness_is_only_a_foundation_ON_a_foundation_layer(self):
        # "150 THK." is a SLAB note (slab_labels owns it) and "1200MM THK" on a
        # foundation layer is a raft. The text cannot tell them apart -- the
        # layer can, so the caller passes what it knows instead of us guessing.
        self.assertIsNone(foundation_labels.parse("1200MM THK"))
        found = foundation_labels.parse("1200MM THK", on_foundation_layer=True)
        self.assertIsNone(found["mark"])
        self.assertEqual(found["thickness_mm"], 1200.0)

    def test_a_slab_note_is_never_claimed_from_a_foundation_layer_either(self):
        # a marked slab note keeps its own shape; only the bare thickness is
        # ambiguous, and only that one is unlocked by the layer
        self.assertIsNone(foundation_labels.parse("S1 150 THK",
                                                  on_foundation_layer=True))

    def test_a_mark_on_its_own_names_it_without_sizing_it(self):
        found = foundation_labels.parse("F3")
        self.assertEqual(found["mark"], "F3")
        self.assertIsNone(found["thickness_mm"])

    def test_text_that_is_not_a_foundation_label_is_not_one(self):
        for text in ("C1 400x400", "150 THK.", "STAIRCASE", "DN", "", None,
                     "GROUND FLOOR LVL."):
            self.assertIsNone(foundation_labels.parse(text), repr(text))

    def test_a_beam_label_is_not_mistaken_for_a_foundation(self):
        # "B1 300x600" must not read as mark B1 -- the mark letter is F
        self.assertIsNone(foundation_labels.parse("B1 300x600"))


if __name__ == "__main__":
    unittest.main()

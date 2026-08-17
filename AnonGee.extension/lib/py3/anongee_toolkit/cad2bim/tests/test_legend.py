# -*- coding: utf-8 -*-
"""The legend: swatch pattern -> legend text -> meaning, proposed, never applied.

Every number in this file is measured off test9 (StructuralPlan-Test9.dxf),
which is the only fixture that carries the convention:

  * 14 legend rows, "HATCH INDICATE ...", across THREE tower legends plus one
    standalone cutout entry. Swatches are 807x484, 1001x601 and 1100x400
    rectangles; their texts anchor 657..947 mm from the swatch centre; rows
    stack 617..640 mm apart, so the WRONG row's swatch is 839..1020 mm away.
  * The nearest PLAN hatch to any legend text is 6622 mm out (worst 16140) --
    the measured reason meaning travels by PATTERN, never by proximity.
  * The same pattern means different things per tower: ZIGZAG is
    "T.O.S. +50MM." / "COMPENSATORY STRIP." / "TOS. +6250." across the three.
    A whole-sheet read refuses those patterns loudly instead of picking one.
  * What survives on test9: ONE proposal -- ASPHALT -> cutout on
    PI_SHEAR WALL CUTOUT (9 plan hatches, all on that one layer) -- and three
    report-only meanings (AR-CONC, ANSI32, ANSI37).

The sign question is OPEN: every step value on the drawing is "+", so fold-up
cannot be told from drop, and a step proposal goes to CATEGORY_FOLD whatever
the sign (findings.md records the question).
"""

import os
import unittest

import _loader

legend, layers, config, dxf_reader = _loader.load(
    "legend", "classify.layers", "config", "readers.dxf_reader")

_MM = 304.8
_HERE = os.path.dirname(os.path.abspath(__file__))
_TEST9 = os.path.join(_HERE, "fixtures", "cad", "StructuralPlan-Test9.dxf")


def _mm(value):
    return value / _MM


class _Region(object):
    """A hatch as the reader leaves it: outer ring in internal feet."""

    def __init__(self, x0, y0, x1, y1, pattern, layer):
        self.points = [(_mm(x0), _mm(y0), 0.0), (_mm(x1), _mm(y0), 0.0),
                       (_mm(x1), _mm(y1), 0.0), (_mm(x0), _mm(y1), 0.0)]
        self.pattern = pattern
        self.layer = layer
        self.category = None

    @property
    def layer_key(self):
        return self.layer


class _Text(object):
    def __init__(self, text, point_mm):
        self.text = text
        self.point = (_mm(point_mm[0]), _mm(point_mm[1]), 0.0)
        self.point_internal = None


def _swatch(x, y, pattern, layer="PI_HATCH", w=807, h=484):
    """A legend swatch at test9's size, centred on (x, y)."""
    return _Region(x - w / 2.0, y - h / 2.0, x + w / 2.0, y + h / 2.0,
                   pattern, layer)


def _row(x, y, pattern, meaning, layer="PI_HATCH"):
    """One legend row at the measured geometry: the text anchors 653 mm right
    and 68 mm below the swatch centre (test9's insertion-point offset)."""
    return (_swatch(x, y, pattern, layer),
            _Text(meaning, (x + 653, y - 68)))


class SwatchPairing(unittest.TestCase):
    def test_a_row_pairs_at_the_measured_geometry(self):
        swatch, text = _row(0, 0, "ZIGZAG", "HATCH INDICATE T.O.S. +50MM.")
        entries = legend.read([swatch], [text])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["pattern"], "ZIGZAG")
        self.assertEqual(entries[0]["layer"], "PI_HATCH")

    def test_a_plan_hatch_distance_never_pairs(self):
        # 6622 mm is the CLOSEST any test9 plan hatch comes to a legend text.
        swatch = _swatch(0, 0, "ZIGZAG")
        text = _Text("HATCH INDICATE T.O.S. +50MM.", (6622, 0))
        self.assertEqual(legend.read([swatch], [text]), [])

    def test_a_missing_swatch_unpairs_its_row_instead_of_stealing(self):
        # Two rows stacked 617 mm apart, the lower swatch not drawn: the lower
        # text's nearest swatch is now the upper one (901 mm, inside reach),
        # but that swatch's own text is closer -- mutual-nearest refuses the
        # theft, so the orphaned row reads as NO entry rather than the wrong
        # meaning.
        upper_swatch, upper_text = _row(0, 617, "STARS",
                                        "HATCH INDICATE T.O.S. +400MM.")
        lower_text = _Text("HATCH INDICATE NON TOWER AREA.", (653, -68))
        entries = legend.read([upper_swatch], [upper_text, lower_text])
        self.assertEqual([e["meaning"] for e in entries],
                         ["HATCH INDICATE T.O.S. +400MM."])

    def test_the_size_band_is_measured_not_guessed(self):
        # Beside a legend text, an 83x83 level marker and a 600x75 wall sliver
        # (test9's smallest non-swatches) are not swatches; the 1100x400
        # cutout swatch -- the band's widest real occupant -- is.
        text = _Text("HATCH INDICATE CUTOUT FOR DOOR ABOVE", (653, -68))
        marker = _Region(-41, -41, 42, 42, "SOLID", "PI_LEVEL")
        sliver = _Region(-300, -37, 300, 38, "ZIGZAG", "PI_HATCH")
        self.assertEqual(legend.read([marker, sliver], [text]), [])
        swatch = _swatch(0, 0, "ASPHALT", "PI_SHEAR WALL CUTOUT",
                         w=1100, h=400)
        entries = legend.read([marker, sliver, swatch], [text])
        self.assertEqual([e["pattern"] for e in entries], ["ASPHALT"])

    def test_indicate_without_hatch_is_not_a_legend_row(self):
        # test9's near-miss: "*A- INDICATE 20mm CAMBER TO BE PROVIDED IN
        # BEAM" sits on the sheet too, and it describes a beam, not a hatch.
        swatch = _swatch(0, 0, "SOLID")
        text = _Text("*A- INDICATE 20mm CAMBER TO BE PROVIDED IN BEAM",
                     (653, -68))
        self.assertEqual(legend.read([swatch], [text]), [])


class MeaningParsing(unittest.TestCase):
    """test9's five meanings, verbatim, plus the sign the drawing never uses."""

    def _kind_of(self, meaning):
        swatch, text = _row(0, 0, "ZIGZAG", meaning)
        entries = legend.read([swatch], [text])
        self.assertEqual(len(entries), 1)
        return entries[0]

    def test_tos_plus_50(self):
        entry = self._kind_of("HATCH INDICATE T.O.S. +50MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", 50.0))

    def test_tos_plus_400(self):
        entry = self._kind_of("HATCH INDICATE T.O.S. +400MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", 400.0))

    def test_tos_spelled_without_dots_and_without_mm(self):
        entry = self._kind_of("HATCH INDICATE TOS. +6250.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", 6250.0))

    def test_cutout(self):
        # The MTEXT arrives with its continuation line; whitespace collapses.
        entry = self._kind_of("HATCH INDICATE CUTOUT FOR DOOR ABOVE\n"
                              "1ST. FLOOR LVL. SLAB AS/ARCH DRAWING")
        self.assertEqual(entry["kind"], "cutout")
        self.assertIsNone(entry["value_mm"])
        self.assertEqual(entry["meaning"],
                         "HATCH INDICATE CUTOUT FOR DOOR ABOVE "
                         "1ST. FLOOR LVL. SLAB AS/ARCH DRAWING")

    def test_anything_else_is_kept_verbatim_as_report_only(self):
        entry = self._kind_of("HATCH INDICATE COLUMN/SHEAR WALL THROUGH "
                              "FOUNDATION TO TERMINATION.")
        self.assertEqual(entry["kind"], "other")
        self.assertEqual(entry["meaning"],
                         "HATCH INDICATE COLUMN/SHEAR WALL THROUGH "
                         "FOUNDATION TO TERMINATION.")

    def test_a_minus_keeps_its_sign(self):
        # No fixture draws one; the parser must still not fold it into "+".
        entry = self._kind_of("HATCH INDICATE T.O.S. -300MM.")
        self.assertEqual((entry["kind"], entry["value_mm"]), ("step", -300.0))


class AmbiguityIsRefused(unittest.TestCase):
    """Two meanings for one pattern -> no proposal, a note. test9's whole-sheet
    read is the case: three towers, three legends, one ZIGZAG."""

    def test_conflicting_meanings_kill_the_pattern_loudly(self):
        rows = [_row(0, 0, "ZIGZAG", "HATCH INDICATE T.O.S. +50MM."),
                _row(50000, 0, "ZIGZAG", "HATCH INDICATE TOS. +6250.")]
        regions = [swatch for swatch, _text in rows]
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        entries = legend.read(regions, [text for _swatch, text in rows])
        self.assertEqual(len(entries), 2)
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"], {})
        self.assertEqual(len(proposal["notes"]), 1)
        self.assertIn("ZIGZAG", proposal["notes"][0])
        self.assertIn("no proposal", proposal["notes"][0])

    def test_the_same_meaning_twice_is_agreement_not_conflict(self):
        # test9's AR-CONC writes the identical termination note in all three
        # legends; repetition across towers must not read as ambiguity.
        rows = [_row(0, 0, "ZIGZAG", "HATCH INDICATE T.O.S. +400MM."),
                _row(50000, 0, "ZIGZAG", "HATCH INDICATE T.O.S. +400MM.")]
        regions = [swatch for swatch, _text in rows]
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        entries = legend.read(regions, [text for _swatch, text in rows])
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_HATCH": layers.CATEGORY_FOLD})
        self.assertEqual(proposal["notes"], [])


class ProposalTranslation(unittest.TestCase):
    """Per-LAYER proposals: that is what the dialog maps, so every plan hatch
    of the pattern must sit on one layer or nothing is proposed."""

    def _one_row(self, meaning, pattern="ZIGZAG"):
        swatch, text = _row(0, 0, pattern, meaning)
        return [swatch], [text]

    def test_a_step_proposes_fold_on_the_one_plan_layer(self):
        regions, texts = self._one_row("HATCH INDICATE T.O.S. +50MM.")
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        entries = legend.read(regions, texts)
        proposal = legend.propose(entries, regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_HATCH": layers.CATEGORY_FOLD})
        self.assertIn("PI_HATCH", proposal["rows"])
        self.assertIn("T.O.S. +50MM", proposal["rows"]["PI_HATCH"])

    def test_a_negative_step_still_proposes_fold(self):
        # The drawing cannot prove which sign means fold-up (every test9
        # value is "+", and a plan cannot say the parent's own level), so the
        # sign changes nothing here -- the open question lives in findings.md
        # rather than in a silent guess.
        regions, texts = self._one_row("HATCH INDICATE T.O.S. -300MM.")
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_HATCH": layers.CATEGORY_FOLD})

    def test_a_cutout_proposes_the_cutout_category(self):
        regions, texts = self._one_row("HATCH INDICATE CUTOUT FOR DOOR ABOVE",
                                       pattern="ASPHALT")
        regions[0].layer = "PI_SHEAR WALL CUTOUT"
        regions.append(_Region(20000, 20000, 20900, 20400, "ASPHALT",
                               "PI_SHEAR WALL CUTOUT"))
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_SHEAR WALL CUTOUT": layers.CATEGORY_CUTOUT})

    def test_two_plan_layers_refuse_the_pattern(self):
        # test9's AR-CONC is the live case: 26 plan hatches on PI_COLUMN
        # HATCH and 8 on PI_RETAINING WALL HATCH -- a per-layer proposal
        # cannot carry one pattern to two layers, so it says so instead.
        regions, texts = self._one_row("HATCH INDICATE T.O.S. +50MM.")
        regions.append(_Region(20000, 20000, 21000, 20800, "ZIGZAG",
                               "PI_HATCH"))
        regions.append(_Region(30000, 20000, 31000, 20800, "ZIGZAG",
                               "PI_OTHER"))
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"], {})
        self.assertTrue(any("2 layers" in note for note in proposal["notes"]))

    def test_a_pattern_nobody_uses_proposes_nothing(self):
        # test9's STARS and ANSI37 exist only as their own swatches.
        regions, texts = self._one_row("HATCH INDICATE T.O.S. +400MM.",
                                       pattern="STARS")
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"], {})
        self.assertTrue(any("no plan hatch" in note
                            for note in proposal["notes"]))

    def test_report_only_meanings_never_touch_the_mapping(self):
        regions, texts = self._one_row("HATCH INDICATE STUB SHEAR WALL.",
                                       pattern="ANSI37")
        regions.append(_Region(20000, 20000, 21000, 20800, "ANSI37",
                               "PI_COLUMN HATCH"))
        proposal = legend.propose(legend.read(regions, texts), regions)
        self.assertEqual(proposal["mapping"], {})
        self.assertEqual(proposal["reports"],
                         ["pattern ANSI37 notes 'HATCH INDICATE STUB SHEAR "
                          "WALL.' (report only)"])


class StoreyValuesAreRefused(unittest.TestCase):
    """+6250 is the next floor, not a step. The SAME threshold fold_plan
    applies (config's max_step_mm, the dialog's own knob) refuses it wherever
    legend depths flow."""

    def _entries(self, *meanings):
        rows = [_row(index * 50000, 0, "ZIGZAG", meaning)
                for index, meaning in enumerate(meanings)]
        return legend.read([swatch for swatch, _t in rows],
                           [text for _s, text in rows])

    def test_a_step_inside_the_limit_flows(self):
        steps, notes = legend.legend_steps(
            self._entries("HATCH INDICATE T.O.S. +400MM."))
        self.assertEqual(steps, {"ZIGZAG": 400.0})
        self.assertEqual(notes, [])

    def test_6250_is_a_storey_and_says_so(self):
        steps, notes = legend.legend_steps(
            self._entries("HATCH INDICATE TOS. +6250."))
        self.assertEqual(steps, {})
        self.assertEqual(len(notes), 1)
        self.assertIn("6250", notes[0])
        self.assertIn("storey", notes[0])

    def test_the_dialog_knob_is_the_limit(self):
        # Same knob as fold_plan.plan_steps: the default is config's
        # max_step_mm, and an explicit value replaces it.
        self.assertEqual(config.DEFAULTS["max_step_mm"], 3000.0)
        steps, notes = legend.legend_steps(
            self._entries("HATCH INDICATE TOS. +6250."), max_step_mm=7000.0)
        self.assertEqual(steps, {"ZIGZAG": 6250.0})
        self.assertEqual(notes, [])

    def test_an_ambiguous_pattern_never_reaches_the_threshold(self):
        steps, notes = legend.legend_steps(
            self._entries("HATCH INDICATE T.O.S. +50MM.",
                          "HATCH INDICATE TOS. +6250."))
        self.assertEqual(steps, {})
        self.assertEqual(len(notes), 1)
        self.assertIn("no proposal", notes[0])


class TheTest9Legend(unittest.TestCase):
    """The fixture itself, end to end -- the numbers the sweep pins forever."""

    _cache = None

    @classmethod
    def _read(cls):
        if cls._cache is None:
            result = dxf_reader.read_dxf(_TEST9)
            scale = 1.0 / _MM
            for region in result.regions:
                region.points = [(p[0] * scale, p[1] * scale, 0.0)
                                 for p in region.points]
            for text in result.texts:
                text.point_internal = (text.point[0] * scale,
                                       text.point[1] * scale, 0.0)
            cls._cache = result
        return cls._cache

    def setUp(self):
        if not dxf_reader.ezdxf_available():
            self.skipTest("ezdxf is not importable -- `pip install ezdxf` "
                          "(the bundled lib/py3 copy is a Windows build)")

    def test_fourteen_rows_across_three_tower_legends(self):
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        self.assertEqual(len(entries), 14)
        by_pattern = {}
        for entry in entries:
            by_pattern[entry["pattern"]] = by_pattern.get(entry["pattern"],
                                                          0) + 1
        self.assertEqual(by_pattern,
                         {"SOLID": 3, "AR-CONC": 3, "ZIGZAG": 3, "STARS": 2,
                          "ANSI32": 1, "ANSI37": 1, "ASPHALT": 1})

    def test_one_proposal_survives_the_whole_sheet(self):
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        proposal = legend.propose(entries, result.regions)
        self.assertEqual(proposal["mapping"],
                         {"PI_SHEAR WALL CUTOUT": layers.CATEGORY_CUTOUT})
        # ...overriding the name-convention default, which reads "shear" and
        # says structural wall. That is exactly why it is a marked proposal
        # in the dialog and not a silent application.
        self.assertEqual(layers.classify_layer("PI_SHEAR WALL CUTOUT"),
                         layers.CATEGORY_STRUCT_WALL)
        # Three towers, three legends: ZIGZAG, STARS and SOLID all mean
        # different things per tower, and all three are refused by name.
        refused = " ".join(proposal["notes"])
        for pattern in ("ZIGZAG", "STARS", "SOLID"):
            self.assertIn(pattern, refused)
        self.assertEqual(len(proposal["reports"]), 3)

    def test_no_step_depth_leaves_the_ambiguous_sheet(self):
        # ZIGZAG carries +50 in one tower and +6250 in another; a whole-sheet
        # read must hand the step machinery NOTHING rather than either.
        result = self._read()
        entries = legend.read(result.regions, result.texts)
        steps, _notes = legend.legend_steps(entries)
        self.assertEqual(steps, {})


if __name__ == "__main__":
    unittest.main()

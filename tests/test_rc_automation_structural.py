# -*- coding: utf-8 -*-
"""Static checks on the Revit-touching half of RC Automation.

These four modules import ``Autodesk.Revit.DB``, so they cannot be imported
here and their behaviour cannot be exercised off Revit. What *can* be checked
without Revit is everything that would otherwise only fail inside it, and each
of these has a specific failure in mind:

* a function calling something the toolkit does not have — an ``AttributeError``
  four hundred bars into a run;
* a raw Python list handed to a Revit API method, which is a fatal marshalling
  fault across the pythonnet bridge, not a catchable ``TypeError`` (§12.9.4);
* a module opening its own transaction, when a run nests thousands of bars
  inside one ``TransactionGroup`` the caller owns;
* the layout rules drifting away from the ones ``models`` defines, so a
  schedule's "12 T16 @ 200" quietly becomes something else.
"""

import ast
import io
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STRUCTURAL = os.path.join(_ROOT, "AnonGee.extension", "lib", "py3",
                           "anongee_toolkit", "structural")
_MODULES = ("rebar_types", "rebar_hosts", "rebar_geometry",
            "rebar_factory", "rebar_run")

if os.path.join(_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
from _rc_loader import load as _load_rc                          # noqa: E402

_rc = _load_rc()


def _path(name):
    return os.path.join(_STRUCTURAL, name + ".py")


def _read(name):
    with io.open(_path(name), encoding="utf-8") as handle:
        return handle.read()


def _tree(name):
    return ast.parse(_read(name))


def _top_level_names(name):
    """Everything a module defines at the top level: functions and classes.

    Classes count. The first version of this collected only functions and duly
    reported ``rebar_factory.PlacementResult`` as a call into something that
    does not exist, which is a test finding its own blind spot rather than a
    bug.
    """
    return set(node.name for node in _tree(name).body
               if isinstance(node, (ast.FunctionDef, ast.ClassDef)))


def _functions(name):
    return dict((node.name, node) for node in _tree(name).body
                if isinstance(node, ast.FunctionDef))


class ModuleTests(unittest.TestCase):

    def test_every_module_compiles(self):
        for name in _MODULES:
            compile(_read(name), _path(name), "exec")

    def test_every_module_is_listed_in_the_package(self):
        init = _read("__init__")
        for name in _MODULES:
            self.assertIn('"{0}"'.format(name), init, name)

    def test_no_re_module(self):
        """The engine ships a partial stdlib and ``re`` is not in it (§12.9.3)."""
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.Import):
                    self.assertNotIn("re", [a.name for a in node.names], name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, "re", name)

    def test_no_pyrevit_imports(self):
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("pyrevit"),
                                     name)

    def test_no_star_imports(self):
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotIn("*", [a.name for a in node.names], name)


class TransactionOwnershipTests(unittest.TestCase):
    """A run places thousands of bars in chunks inside one TransactionGroup.

    A module that opened its own would either nest inside that or hand the user
    a thousand undo steps, so none of them may.
    """

    def test_nothing_opens_a_transaction(self):
        for name in _MODULES:
            source = _read(name)
            for forbidden in ("Transaction(", "TransactionGroup(",
                              "SubTransaction("):
                self.assertNotIn(forbidden, source,
                                 "{0} opens {1}".format(name, forbidden))

    def test_the_writing_module_says_it_does_not(self):
        source = _read("rebar_factory")
        self.assertIn("never opens a transaction", source.lower())

    def test_the_reading_modules_say_they_only_read(self):
        for name in ("rebar_types", "rebar_hosts"):
            self.assertIn("read", _read(name).split("\n")[2].lower()
                          + _read(name)[:1200].lower(), name)


class MarshallingTests(unittest.TestCase):
    """Raw Python lists across the bridge are a fatal fault, not an exception."""

    def test_curves_are_a_typed_list_built_with_add(self):
        source = _read("rebar_geometry")
        self.assertIn("List[Curve]()", source)
        self.assertIn("curves.Add(", source)

    def test_the_typed_list_is_imported_from_generic(self):
        self.assertIn("from System.Collections.Generic import List",
                      _read("rebar_geometry"))

    def test_no_python_list_literal_is_passed_as_curves(self):
        # `curves=[...]` would marshal as a fatal fault rather than raising.
        for name in ("rebar_factory", "rebar_geometry"):
            self.assertNotIn("curves = [", _read(name), name)


class CrossModuleApiTests(unittest.TestCase):
    """Every rc_automation attribute these modules name actually exists."""

    OWNERS = {"rebar_spec": "rebar_spec", "models": "models"}

    def test_referenced_rc_automation_attributes_exist(self):
        missing = []
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if not isinstance(node, ast.Attribute):
                    continue
                owner = node.value
                if (not isinstance(owner, ast.Name)
                        or owner.id not in self.OWNERS):
                    continue
                module = getattr(_rc, self.OWNERS[owner.id])
                if not hasattr(module, node.attr):
                    missing.append("{0}: {1}.{2}".format(
                        name, owner.id, node.attr))
        self.assertEqual(sorted(set(missing)), [])

    def test_internal_calls_resolve(self):
        """A call into a sibling module has to name a function it defines."""
        known = dict((name, _top_level_names(name)) for name in _MODULES)
        missing = []
        for name in _MODULES:
            for node in ast.walk(_tree(name)):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name)
                        and func.value.id in known
                        and func.attr not in known[func.value.id]):
                    missing.append("{0}: {1}.{2}".format(
                        name, func.value.id, func.attr))
        self.assertEqual(sorted(set(missing)), [])

    def test_every_layout_rule_models_defines_is_handled(self):
        source = _read("rebar_factory")
        models = _rc.models
        for rule in (models.LAYOUT_NUMBER_WITH_SPACING,
                     models.LAYOUT_MAXIMUM_SPACING,
                     models.LAYOUT_FIXED_NUMBER):
            constant = [n for n in dir(models)
                        if n.startswith("LAYOUT_")
                        and getattr(models, n) == rule][0]
            # FixedNumber is the else-branch, so its constant need not appear;
            # the API call for it must.
            if rule != models.LAYOUT_FIXED_NUMBER:
                self.assertIn("models." + constant, source, constant)
        for call in ("SetLayoutAsNumberWithSpacing",
                     "SetLayoutAsMaximumSpacing", "SetLayoutAsFixedNumber"):
            self.assertIn(call, source, call)

    def test_the_tie_role_drives_the_stirrup_style(self):
        # A tie placed as a Standard bar hooks and schedules like a straight
        # one, which is wrong in the model and wrong in the BBS.
        source = _read("rebar_factory")
        self.assertIn("ROLE_COLUMN_TIE", source)
        self.assertIn("RebarStyle.StirrupTie", source)
        self.assertTrue(hasattr(_rc.rebar_spec, "ROLE_COLUMN_TIE"))


class PlacementContractTests(unittest.TestCase):

    def test_the_factory_exposes_the_three_placement_shapes(self):
        functions = _functions("rebar_factory")
        for name in ("place_layer", "place_set", "place_bars", "create_bar",
                     "apply_layout"):
            self.assertIn(name, functions, name)

    def test_placement_returns_results_rather_than_raising(self):
        """One bad bar in four hundred costs that bar, not the run."""
        source = _read("rebar_factory")
        for name in ("place_layer", "place_set", "place_bars"):
            body = source.split("def " + name)[1].split("\ndef ")[0]
            self.assertIn("result.errors.append", body, name)
            self.assertIn("except Exception", body, name)

    def test_a_uniform_run_is_placed_as_one_element(self):
        # The 2,000-versus-50,000 difference at the stated scale.
        body = _read("rebar_factory").split("def place_layer")[1]\
            .split("\ndef ")[0]
        self.assertIn("plan.as_set()", body)
        self.assertIn("apply_layout", body)

    def test_placed_bars_are_stamped_so_a_rerun_can_tell_them_apart(self):
        # Phase 3 replaces only what this tool made and leaves hand-added bars
        # alone, which it can only do if they were marked when placed.
        source = _read("rebar_factory")
        self.assertIn("STAMP_TEXT", source)
        self.assertIn("_stamp(rebar)", source)
        self.assertIn("def existing_stamped_rebar", source)

    def test_host_validity_is_asked_before_anything_is_placed(self):
        source = _read("rebar_hosts")
        self.assertIn("def is_valid_host", source)
        self.assertIn("IsValidHost", source)
        # And the reason a footing usually fails it is spelled out.
        self.assertIn("FLOOR_PARAM_IS_STRUCTURAL", source)

    def test_types_are_matched_never_created(self):
        """Creating a bar type nobody loaded puts a wrong name in the BBS."""
        source = _read("rebar_types")
        for forbidden in (".Duplicate(", ".Create(", "NewFamilyInstance"):
            self.assertNotIn(forbidden, source, forbidden)


class RunContractTests(unittest.TestCase):
    """The Phase 2 pass: what it refuses to do, and why."""

    def body(self, function):
        return _read("rebar_run").split("def " + function)[1].split("\ndef ")[0]

    def test_planning_opens_no_transaction(self):
        # The plan is shown before a transaction exists, so it can be refused.
        for name in ("plan_footings", "_plan_one_footing", "resolve_bar_types"):
            self.assertNotIn("Transaction", self.body(name), name)

    def test_a_host_that_cannot_be_reinforced_is_asked_first(self):
        body = self.body("_plan_one_footing")
        self.assertIn("is_valid_host", body)
        self.assertIn("why_not_a_host", body)

    def test_a_pad_that_is_not_its_scheduled_size_is_refused(self):
        # Bars planned from the schedule and placed against a bounding box do
        # not fit a pad that was modelled differently, or rotated.
        body = self.body("_plan_one_footing")
        self.assertIn("_sized_as_scheduled", body)
        self.assertIn("STATUS_INVALID", body)

    def test_an_outline_is_threaded_through_to_the_bars(self):
        body = self.body("_plan_one_footing")
        self.assertIn("plan_footing(footing, rows, placement)", body)

    def test_existing_reinforcement_stops_a_second_run_doubling_it(self):
        body = self.body("_plan_one_footing")
        self.assertIn("_has_any_rebar", body)
        self.assertIn("STATUS_EXISTS", body)

    def test_bar_types_are_resolved_once_for_the_run(self):
        # A thousand footings of one type ask the same question a thousand
        # times otherwise.
        body = self.body("resolve_bar_types")
        self.assertIn("if key in resolved or key in missing", body)

    def test_the_size_check_uses_the_schedule_not_the_type_row(self):
        body = self.body("_plan_one_footing")
        self.assertIn("rebar_spec.scheduled_extent_mm", body)
        self.assertTrue(hasattr(_rc.rebar_spec, "scheduled_extent_mm"))


class GeometryContractTests(unittest.TestCase):

    def test_the_array_vector_is_used_as_the_plane_normal(self):
        """Revit distributes a set along the normal, so it is not a free choice.

        A footing layer running X and spaced along Y has to hand over Y, or the
        set marches off vertically instead of across the pad.
        """
        source = _read("rebar_geometry")
        self.assertIn("array_vector", source)
        self.assertIn("def normal_for", source)
        self.assertTrue(hasattr(_rc.rebar_spec.BarSetSpec, "__slots__"))
        self.assertIn("array_vector", _rc.rebar_spec.BarSetSpec.__slots__)

    def test_zero_length_segments_are_dropped_not_passed_on(self):
        # Revit rejects an entire sketch for one zero-length line, so a repeated
        # outline point would otherwise cost the whole bar.
        source = _read("rebar_geometry")
        self.assertIn("MIN_SEGMENT_FT", source)
        self.assertIn("skipped", source)

    def test_rotation_is_applied_before_the_offset(self):
        """Rotating after offsetting swings a pad's bars away from the pad."""
        body = _read("rebar_geometry").split("def to_xyz")[1].split("\ndef ")[0]
        rotate_at = body.index("math.radians")
        offset_at = body.index("origin_ft is None")
        self.assertLess(rotate_at, offset_at)


if __name__ == "__main__":
    unittest.main()

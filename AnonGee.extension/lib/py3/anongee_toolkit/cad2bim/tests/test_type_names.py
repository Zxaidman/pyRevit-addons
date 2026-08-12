# -*- coding: utf-8 -*-
"""type_names -- matching a type name the way REVIT matches it.

Every builder that duplicates a type first asks "does a type of this name exist
already?". That question was asked with a plain Python `==`, which is stricter
than the rule Revit itself applies: Revit treats two type names as the same when
they differ only in case or in surrounding/repeated whitespace.

The gap crashed the column pass. A family carrying the Revit-standard "400 x 600"
was asked for the toolkit's default "400 X 600"; `==` said "no such type", so the
builder called Duplicate, and Revit answered

    The name is already in use for this element type.
    Parameter name: name

Covered here: the normalisation, the lookup built on it, and the resolve step
that reuses rather than duplicates -- plus what happens when a name really is
taken by something that cannot be reused. Standalone (no Revit).
"""

import ast
import os
import unittest

import _loader


type_names = _loader.load("type_names")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
# type_names.py owns the one guarded Duplicate; every other module must go
# through it. The tests themselves fake a Duplicate, which is the point of them.
_DUPLICATE_IS_ALLOWED_IN = ("type_names.py",)


def _package_sources():
    """(relative path, parsed tree) for every cad2bim module outside tests/."""
    for folder, folders, files in os.walk(_PKG):
        folders[:] = [name for name in folders
                      if name not in ("tests", "__pycache__")]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                source = handle.read().decode("utf-8")
            yield os.path.relpath(path, _PKG), ast.parse(source)


class _FakeType(object):
    """Enough of a Revit ElementType to drive resolve_type: a name and a
    Duplicate that enforces REVIT's uniqueness rule, not Python's."""

    def __init__(self, name, family):
        self.name = name
        self.family = family          # the list this type's siblings live in
        family.append(self)

    def Duplicate(self, name):
        for sibling in self.family:
            if sibling.name.strip().lower() == name.strip().lower():
                raise ValueError("The name is already in use for this element "
                                 "type.\nParameter name: name")
        return _FakeType(name, self.family)


def _scan(family):
    return lambda: [(sibling.name, sibling) for sibling in family]


class Normalising(unittest.TestCase):
    def test_case_alone_is_not_a_different_name(self):
        # the exact shape of the reported crash: Revit ships "400 x 600",
        # the default template renders "400 X 600"
        self.assertEqual(type_names.key("400 x 600"),
                         type_names.key("400 X 600"))

    def test_surrounding_whitespace_is_not_a_different_name(self):
        self.assertEqual(type_names.key("  200 THK "), type_names.key("200 THK"))

    def test_repeated_inner_whitespace_is_not_a_different_name(self):
        self.assertEqual(type_names.key("400  X\t600"),
                         type_names.key("400 X 600"))

    def test_genuinely_different_names_stay_different(self):
        self.assertNotEqual(type_names.key("400 X 600"),
                            type_names.key("400 X 900"))

    def test_a_missing_name_normalises_instead_of_raising(self):
        self.assertEqual(type_names.key(None), "")
        self.assertEqual(type_names.key(""), "")


class Finding(unittest.TestCase):
    def test_it_finds_the_type_revit_would_call_the_same(self):
        rows = [("300 x 450", "a"), ("400 x 600", "b")]
        self.assertEqual(type_names.find(rows, "400 X 600"), "b")

    def test_it_returns_none_when_the_name_is_really_absent(self):
        rows = [("300 x 450", "a")]
        self.assertIsNone(type_names.find(rows, "400 X 600"))

    def test_an_unnamed_candidate_never_matches(self):
        rows = [(None, "a")]
        self.assertIsNone(type_names.find(rows, "400 X 600"))


class Resolving(unittest.TestCase):
    def setUp(self):
        self.family = []
        self.base = _FakeType("300 x 450", self.family)

    def test_a_name_revit_already_holds_is_REUSED_not_duplicated(self):
        stock = _FakeType("400 x 600", self.family)
        found, created, note = type_names.resolve_type(self.base, "400 X 600",
                                                       _scan(self.family))
        self.assertIs(found, stock)
        self.assertIsNone(note)
        self.assertEqual(len(self.family), 2)   # nothing was created

    def test_a_reused_type_is_flagged_so_its_SIZE_is_left_alone(self):
        # the model's own "400 x 600" must not be resized under the user; only a
        # type this run created may have its dimensions written
        _FakeType("400 x 600", self.family)
        _found, created, _note = type_names.resolve_type(self.base, "400 X 600",
                                                         _scan(self.family))
        self.assertFalse(created)

    def test_a_genuinely_new_name_is_duplicated_and_flagged_for_sizing(self):
        found, created, note = type_names.resolve_type(self.base, "500 X 500",
                                                       _scan(self.family))
        self.assertEqual(found.name, "500 X 500")
        self.assertTrue(created)
        self.assertIsNone(note)
        self.assertEqual(len(self.family), 2)

    def test_a_clash_the_scan_could_not_see_is_reused_and_reported(self):
        # the scan is scoped narrower than Revit's own uniqueness rule, so the
        # pre-check misses and Duplicate throws -- the type still comes back
        hidden = _FakeType("400 x 600", self.family)
        found, created, note = type_names.resolve_type(
            self.base, "400 X 600", scan=lambda: [], rescan=_scan(self.family))
        self.assertIs(found, hidden)
        self.assertFalse(created)
        self.assertIn("400 X 600", note)

    def test_an_unresolvable_clash_returns_a_sentence_not_a_stack_trace(self):
        def explode(name):
            raise ValueError("The name is already in use for this element type.")
        self.base.Duplicate = explode
        found, created, note = type_names.resolve_type(self.base, "400 X 600",
                                                       scan=lambda: [])
        self.assertIsNone(found)
        self.assertFalse(created)
        self.assertIn("400 X 600", note)
        self.assertNotIn("Traceback", note)


class Recording(unittest.TestCase):
    """A note has to reach the console once, not once per element -- a whole
    storey of 400x600 columns shares one type and therefore one note."""

    def test_a_note_lands_in_the_result(self):
        result = {"created": [], "skipped": [], "errors": [], "notes": []}
        type_names.record(result, "type name '400 X 600' already existed")
        self.assertEqual(result["notes"],
                         ["type name '400 X 600' already existed"])

    def test_the_same_note_is_not_repeated(self):
        result = {"notes": []}
        type_names.record(result, "same")
        type_names.record(result, "same")
        self.assertEqual(result["notes"], ["same"])

    def test_nothing_to_say_records_nothing(self):
        result = {"notes": []}
        type_names.record(result, None)
        type_names.record(result, "")
        self.assertEqual(result["notes"], [])


class NoBuilderMayAskThePlainQuestion(unittest.TestCase):
    """The static half: the crash came back the moment ONE call site was left
    comparing names with `==`, so the rule is enforced over the whole package
    rather than trusted to the reviewer of the next builder."""

    def test_every_duplication_goes_through_the_guarded_helper(self):
        offenders = []
        for relative, tree in _package_sources():
            if os.path.basename(relative) in _DUPLICATE_IS_ALLOWED_IN:
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "Duplicate"):
                    offenders.append("{0}:{1}".format(relative, node.lineno))
        self.assertEqual(offenders, [],
                         "duplicate a type through type_names.resolve_type, "
                         "which reuses a clashing name instead of losing the "
                         "element: " + ", ".join(offenders))

    def test_no_element_name_is_compared_with_a_plain_equals(self):
        offenders = []
        for relative, tree in _package_sources():
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                if not any(isinstance(op, (ast.Eq, ast.NotEq))
                           for op in node.ops):
                    continue
                if _is_a_name_lookup(node.left):
                    offenders.append("{0}:{1}".format(relative, node.lineno))
        self.assertEqual(offenders, [],
                         "compare element names with type_names.key(), which "
                         "matches them the way Revit does: "
                         + ", ".join(offenders))


def _is_a_name_lookup(node):
    """True for the two shapes that read an element's name: get_element_name(x)
    and x.get_Parameter(...).AsString()."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name) and node.func.id == "get_element_name":
        return True
    return isinstance(node.func, ast.Attribute) and node.func.attr == "AsString"


if __name__ == "__main__":
    unittest.main()

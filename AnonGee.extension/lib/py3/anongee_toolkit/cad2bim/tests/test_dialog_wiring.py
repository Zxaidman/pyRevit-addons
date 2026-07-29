# -*- coding: utf-8 -*-
"""The pushbutton dialog and its XAML must agree on every named control.

A control added to ui.xaml but never bound in script.py (or bound but missing
from the XAML) only fails when the user opens the dialog in Revit -- exactly how
v0.59.0's `tb_slab_step` got out. Both files are plain text here, so the check
is a static one: no Revit, no WPF, no XamlReader.
"""

import ast
import os
import re
import unittest
import xml.etree.ElementTree as ET

_HERE = os.path.dirname(os.path.abspath(__file__))
_BUTTON = os.path.normpath(os.path.join(
    _HERE, "..", "..", "..", "..", "..",
    "AnonGee.tab", "Core.panel", "CAD to BIM.pushbutton"))
_SCRIPT = os.path.join(_BUTTON, "script.py")
_XAML = os.path.join(_BUTTON, "ui.xaml")
_LINK_XAML = os.path.join(_BUTTON, "link_options.xaml")

_FIND = re.compile(r'\bfind\(\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*\)')


def _xaml_names(*paths):
    """Every x:Name in the given .xaml files (both dialogs by default)."""
    key = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"
    names = set()
    for path in (paths or (_XAML, _LINK_XAML)):
        names.update(el.get(key) for el in ET.parse(path).iter() if el.get(key))
    return names


def _script_source():
    with open(_SCRIPT, "rb") as handle:
        return handle.read().decode("utf-8")


class DialogControlNames(unittest.TestCase):
    def test_every_bound_control_exists_in_the_xaml(self):
        missing = sorted(set(_FIND.findall(_script_source())) - _xaml_names())
        self.assertEqual(missing, [], "bound but absent from ui.xaml: %s" % missing)

    def test_every_control_the_dialog_uses_is_bound(self):
        """self.tb_x / self.cb_x / self.chk_x must come from a find(...) call.

        Catches the reverse slip: a new textbox read by _init_tolerances or
        _read_tolerances that nobody ever assigned.
        """
        source = _script_source()
        bound = set(_FIND.findall(source))
        prefixes = ("tb_", "cb_", "chk_", "rb_", "btn_", "lbl_")
        assigned = set()
        used = set()
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Name) or node.value.id != "self":
                continue
            if not node.attr.startswith(prefixes):
                continue
            if isinstance(node.ctx, ast.Store):
                assigned.add(node.attr)
            else:
                used.add(node.attr)
        unbound = sorted(name for name in used
                         if name not in bound and name not in assigned)
        self.assertEqual(unbound, [],
                         "used but never bound to a control: %s" % unbound)


class SlabToleranceRow(unittest.TestCase):
    """Every slab tolerance on the Tolerances tab reaches slab_outlines."""

    def test_slab_tolerance_boxes_are_all_present(self):
        names = _xaml_names(_XAML)
        for control in ("tb_slab_snap", "tb_slab_heal", "tb_slab_chain",
                        "tb_slab_width", "tb_slab_step"):
            self.assertIn(control, names)


if __name__ == "__main__":
    unittest.main()

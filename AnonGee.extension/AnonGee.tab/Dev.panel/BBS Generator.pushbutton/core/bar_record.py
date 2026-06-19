# -*- coding: utf-8 -*-
"""
core/bar_record.py
Central data model — plain class, IronPython 2 + CPython 3 compatible.
"""
import hashlib
import json

class BarRecord(object):
    __slots__ = [
        "bar_mark", "member_name", "member_type", "floor_level", "bar_type_name",
        "diameter_mm", "shape_code", "shape_description", "dimensions",
        "cutting_length_mm", "bend_deduction_mm", "bend_diameter_mm",
        "no_of_bars", "total_length_mm",
        "unit_weight_kg_per_m", "total_weight_kg",
        "standard", "revit_element_id", "formula_string",
        "revision_hash", "bar_detail"
    ]

    def __init__(self,
                 bar_mark, member_name, member_type, floor_level, bar_type_name,
                 diameter_mm, shape_code, shape_description, dimensions,
                 cutting_length_mm, bend_deduction_mm, bend_diameter_mm,
                 no_of_bars, total_length_mm,
                 unit_weight_kg_per_m, total_weight_kg,
                 standard, revit_element_id, formula_string, bar_detail=""):

        self.bar_mark              = bar_mark
        self.member_name           = member_name
        self.member_type           = member_type
        self.floor_level           = floor_level
        self.bar_type_name         = bar_type_name
        self.diameter_mm           = diameter_mm
        self.shape_code            = shape_code
        self.shape_description     = shape_description
        self.dimensions            = dimensions
        self.cutting_length_mm     = cutting_length_mm
        self.bend_deduction_mm     = bend_deduction_mm
        self.bend_diameter_mm      = bend_diameter_mm
        self.no_of_bars            = no_of_bars
        self.total_length_mm       = total_length_mm
        self.unit_weight_kg_per_m  = unit_weight_kg_per_m
        self.total_weight_kg       = total_weight_kg
        self.standard              = standard
        self.revit_element_id      = revit_element_id
        self.formula_string        = formula_string
        self.bar_detail            = bar_detail
        self.revision_hash         = self._compute_hash()

    def _compute_hash(self):
        payload = json.dumps({
            "bar_mark":       self.bar_mark,
            "member_name":    self.member_name,
            "diameter_mm":    self.diameter_mm,
            "shape_code":     self.shape_code,
            "dimensions":     self.dimensions,
            "cutting_length": self.cutting_length_mm,
            "no_of_bars":     self.no_of_bars,
            "bar_detail":     self.bar_detail,
        }, sort_keys=True)
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    @property
    def total_length_m(self):
        return self.total_length_mm / 1000.0

    @property
    def cutting_length_m(self):
        return self.cutting_length_mm / 1000.0

    @property
    def diameter_label(self):
        return "T{0}".format(self.diameter_mm)

    def to_dict(self):
        return {s: getattr(self, s) for s in self.__slots__}
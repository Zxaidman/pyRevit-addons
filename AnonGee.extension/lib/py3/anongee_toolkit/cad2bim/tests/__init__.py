# -*- coding: utf-8 -*-
"""Standalone unit tests for the pure-geometry cad2bim modules.

These import shapes.py / config.py by file path into a synthetic package so they
run on a bare CPython (no numpy, no Revit), matching the modules' design promise
of being statically inspectable and unit-testable outside Revit.
"""

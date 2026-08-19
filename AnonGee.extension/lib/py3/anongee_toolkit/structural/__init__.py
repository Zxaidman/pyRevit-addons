# -*- coding: utf-8 -*-
"""
anongee_toolkit.structural
~~~~~~~~~~~~~~~~~~~~~~~~~~
Domain helpers for structural Revit elements.

Everything here touches the Revit API, so none of it imports off Revit. The
decisions these modules act on -- what a bar is, where it goes, whether a run
can be one element -- are made in :mod:`anongee_toolkit.rc_automation`, which
imports nothing and is unit-tested on any machine.

``rebar_types``      resolve the bar, hook and cover TYPE elements a schedule names
``rebar_hosts``      find the elements a row is about, and say when one cannot host
``rebar_geometry``   millimetres local to a host, into world-feet curves
``rebar_factory``    place the bars — the only module that writes
"""
from anongee_toolkit.structural.rebars import get_rebars

__all__ = ["get_rebars", "rebar_types", "rebar_hosts", "rebar_geometry",
           "rebar_factory"]

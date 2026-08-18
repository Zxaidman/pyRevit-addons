# -*- coding: utf-8 -*-
"""
anongee_toolkit.rc_automation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The thinking half of RC Automation: reading an Excel schedule, deciding whether
it makes sense, and turning it into objects.

Nothing in this package imports Revit, WPF or pyRevit, and only
:func:`excel_engine.read_grid` imports openpyxl. That is on purpose -- every
rule the tool applies to a workbook can then be exercised by
``python -m unittest discover -s tests`` on a machine with no Revit on it, which
is where the rules get argued with.

The half that writes to a model lives in :mod:`anongee_toolkit.structural`, and
the window lives in the pushbutton.
"""

__version__ = "0.1.0"

from anongee_toolkit.rc_automation import models          # noqa: F401
from anongee_toolkit.rc_automation import standards       # noqa: F401
from anongee_toolkit.rc_automation import excel_engine    # noqa: F401
from anongee_toolkit.rc_automation import validation      # noqa: F401
from anongee_toolkit.rc_automation import reconcile       # noqa: F401
from anongee_toolkit.rc_automation import rebar_spec      # noqa: F401

__all__ = ["models", "standards", "excel_engine", "validation",
           "reconcile", "rebar_spec"]

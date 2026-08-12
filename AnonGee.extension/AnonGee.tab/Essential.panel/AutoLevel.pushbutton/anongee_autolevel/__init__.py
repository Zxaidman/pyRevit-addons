# -*- coding: utf-8 -*-
"""Auto Level Manager — the tool's own package.

Split so the thinking parts run without Revit:

  ``textparse``  detect elevations in drawing text (no ``re``, §12.9.3)
  ``naming``     learn the model's level-naming convention, or render one
  ``planner``    the level plan: rows, edits, validation, the change set
  ``dxf_text``   pull TEXT/MTEXT out of a DXF through ezdxf (optional)
  ``compat``     the Revit API version differences this tool touches
  ``revit_ops``  everything that must run on Revit's primary thread

Only ``compat`` and ``revit_ops`` import Autodesk namespaces; the other four
are plain Python and are covered by ``tests/test_autolevel.py``.
"""

VERSION = "1.0.0"

__all__ = ["textparse", "naming", "planner", "dxf_text", "compat", "revit_ops"]

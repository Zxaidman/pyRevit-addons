# -*- coding: utf-8 -*-
"""Auto Level Manager — the tool's own package.

Split so the thinking parts run without Revit:

  ``textparse``  detect elevations in drawing text (no ``re``, §12.9.3)
  ``naming``     learn the model's level-naming convention, or render one
  ``planner``    the level plan: rows, edits, validation, the change set
  ``stackview``  the stack drawing's camera: zoom, pan, elevation <-> pixels
  ``settings``   the dialog's options, remembered between Revit sessions
  ``dxf_text``   pull TEXT/MTEXT out of a DXF through ezdxf (optional)
  ``compat``     the Revit API version differences this tool touches
  ``revit_ops``  everything that must run on Revit's primary thread

Only ``compat`` and ``revit_ops`` import Autodesk namespaces; the rest are
plain Python and are covered by ``tests/test_autolevel.py``.
"""

# The one place this tool's version is written. bundle.yaml's "Version:" line,
# the badge in the window header and CHANGELOG.md's newest heading are all
# checked against it by tests/test_autolevel_ui.py, so they cannot drift.
#
# Semantic versioning, read as "what does this mean for someone using it":
#   MAJOR  the tool behaves differently on purpose — a workflow moved, a
#          default now creates something it did not create before, or what
#          Apply writes to the model changed shape.
#   MINOR  a new capability, everything you already did still works.
#   PATCH  a fix. No new capability, nothing to relearn.
VERSION = "1.2.0"

__all__ = ["textparse", "naming", "planner", "stackview", "settings",
           "dxf_text", "compat", "revit_ops"]

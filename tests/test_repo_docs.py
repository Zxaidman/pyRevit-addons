# -*- coding: utf-8 -*-
"""The repository's own documentation, checked against the repository.

The README drifted once: nine tools were shipping on the ribbon and none of
them were written down, because nothing connected the folder you add to the
prose you are supposed to update. This connects them.

The root changelog and ``extension.json`` are held to each other for the same
reason the per-tool versions are — a version nobody can trust is worse than
no version at all.
"""

import json
import os
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TAB = os.path.join(_ROOT, "AnonGee.extension", "AnonGee.tab")
_README = os.path.join(_ROOT, "README.md")
_CHANGELOG = os.path.join(_ROOT, "CHANGELOG.md")
_EXTENSION_JSON = os.path.join(_ROOT, "extension.json")


def _read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _squash(text):
    """Lowercase, punctuation-free, single-spaced — for loose name matching."""
    kept = [ch.lower() if (ch.isalnum() or ch.isspace()) else " " for ch in text]
    return " ".join("".join(kept).split())


def bundle_title(folder):
    """The name a tool shows on the ribbon: bundle.yaml, else __title__.

    Both may carry a newline to split the ribbon label over two lines, and
    either may be absent, in which case pyRevit falls back to the folder name.
    """
    bundle = os.path.join(folder, "bundle.yaml")
    if os.path.isfile(bundle):
        for line in _read(bundle).splitlines():
            if line.startswith("title:"):
                value = line.split(":", 1)[1].strip().strip("'\"")
                if value:
                    return value.replace("\\n", " ")
    script = os.path.join(folder, "script.py")
    if os.path.isfile(script):
        for line in _read(script).splitlines():
            if line.strip().startswith("__title__"):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value:
                    return value.replace("\\n", " ")
    return ""


def pushbuttons():
    """Every leaf tool bundle on the ribbon, as (folder, ribbon title)."""
    found = []
    for root, dirs, _files in os.walk(_TAB):
        for name in dirs:
            if name.endswith(".pushbutton"):
                folder = os.path.join(root, name)
                found.append((folder, bundle_title(folder)))
    return sorted(found)


class RibbonDocumentationTests(unittest.TestCase):

    def test_there_are_tools_to_check(self):
        self.assertGreater(len(pushbuttons()), 20)

    def test_every_shipped_tool_appears_in_the_readme(self):
        """A button on the ribbon that the README does not mention is drift."""
        readme = _squash(_read(_README))
        missing = []
        for folder, title in pushbuttons():
            basename = os.path.basename(folder)[:-len(".pushbutton")]
            # Accept the ribbon title or the folder name, with or without the
            # spaces a CamelCase folder leaves out ("AutoLevel" / "Auto Level").
            candidates = [title, basename, _spaced(basename)]
            if not any(_squash(name) and _squash(name) in readme
                       for name in candidates if name):
                missing.append("{0} (ribbon title: {1!r})".format(basename, title))
        self.assertEqual(missing, [],
                         "not documented in README.md: " + "; ".join(missing))

    def test_every_panel_appears_in_the_readme(self):
        readme = _squash(_read(_README))
        for name in sorted(os.listdir(_TAB)):
            if name.endswith(".panel"):
                panel = name[:-len(".panel")]
                self.assertIn(_squash(panel), readme,
                              "{0} panel is not in the README".format(panel))

    def test_the_readme_links_the_root_changelog(self):
        self.assertIn("(CHANGELOG.md)", _read(_README))


def _spaced(name):
    """``AutoLevel`` -> ``Auto Level``, so CamelCase folders still match."""
    out = []
    for index, ch in enumerate(name):
        if index and ch.isupper() and not name[index - 1].isupper():
            out.append(" ")
        out.append(ch)
    return "".join(out)


class ExtensionVersionTests(unittest.TestCase):

    def extension_version(self):
        return json.loads(_read(_EXTENSION_JSON))["version"]

    def test_the_extension_version_is_semantic(self):
        parts = self.extension_version().split(".")
        self.assertEqual(len(parts), 3, self.extension_version())
        for part in parts:
            self.assertTrue(part.isdigit(), self.extension_version())

    def test_the_root_changelog_leads_with_it(self):
        headings = [line[3:].strip() for line in _read(_CHANGELOG).splitlines()
                    if line.startswith("## ")]
        versions = [heading for heading in headings
                    if heading.replace(".", "").isdigit()]
        self.assertTrue(versions, "no version headings in CHANGELOG.md")
        self.assertEqual(versions[0], self.extension_version(),
                         "CHANGELOG.md leads with {0}, extension.json says {1}"
                         .format(versions[0], self.extension_version()))

    def test_the_root_changelog_is_newest_first(self):
        headings = [line[3:].strip() for line in _read(_CHANGELOG).splitlines()
                    if line.startswith("## ")]
        versions = [heading for heading in headings
                    if heading.replace(".", "").isdigit()]
        self.assertEqual(versions, sorted(
            versions, key=lambda v: [int(p) for p in v.split(".")], reverse=True))

    def test_the_panels_extension_json_declares_all_exist(self):
        declared = json.loads(_read(_EXTENSION_JSON))["bundles"][0]["folders"]
        for folder in declared:
            path = os.path.join(_ROOT, "AnonGee.extension", folder)
            self.assertTrue(os.path.isdir(path), folder)

    def test_every_panel_on_disk_is_declared(self):
        declared = set(json.loads(_read(_EXTENSION_JSON))["bundles"][0]["folders"])
        for name in sorted(os.listdir(_TAB)):
            if name.endswith(".panel"):
                self.assertIn("AnonGee.tab/{0}".format(name), declared,
                              "{0} is on disk but not in extension.json".format(name))


if __name__ == "__main__":                                    # pragma: no cover
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""Regenerate the sample schedule in every format the tool has to cope with.

    python tests/fixtures/rc_automation/build_fixtures.py

The CSVs are the source of truth -- they are what a schema change gets reviewed
in -- and everything else is built from them, so a format cannot quietly drift
away from the others. ``test_rc_automation.py`` asserts they all parse to the
same objects.

What gets written, and why each earns its place:

``sample_schedule.xlsx``
    The normal case, plus the INFO cover sheet that keeps project and units off
    the data sheets.
``sample_schedule.xlsm``
    Macro-enabled, which is what a firm's real template usually is. Same bytes
    as far as openpyxl cares; the point is that the *extension* is accepted.
``sample_schedule.xls``
    Not a real .xls -- deliberately. It exists so the legacy-format refusal is
    tested against a file that is actually there, since "not found" and "cannot
    read this format" are different messages and the user needs the second one.
``txt_sheets/``
    One tab-separated file per sheet. Revit's own schedule export writes this,
    and a folder of them is a first-class input.

Needs openpyxl. The extension vendors a Windows build, so on Linux or macOS::

    pip install openpyxl
"""

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SHEETS = ("FOOTING_TYPES", "FOOTING_PLACEMENT", "FOOTING_REBAR",
          "COLUMN_TYPES", "COLUMN_PLACEMENT", "COLUMN_REBAR")

#: The cover sheet the CSVs cannot carry -- they are one table each by design.
INFO_ROWS = [
    ["PROJECT", "Riverside Tower"],
    ["UNITS", "mm"],
    ["STANDARD", "BS 8666:2020"],
    ["REVISION", "C"],
    ["", ""],
    ["Note", "Lengths in millimetres. One row per type; placement is separate."],
]


def read_csv_rows(path):
    """Rows from a CSV, quote-aware, without the ``csv`` module.

    The same hand-rolled split the toolkit uses, for the same reason: the
    Outline column is one cell full of commas.
    """
    with io.open(path, encoding="utf-8") as handle:
        text = handle.read()
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
        "AnonGee.extension", "lib", "py3"))
    rows = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if not line.strip():
            continue
        cells, current, quoted, index = [], [], False, 0
        while index < len(line):
            char = line[index]
            if char == '"':
                if quoted and index + 1 < len(line) and line[index + 1] == '"':
                    current.append('"')
                    index += 1
                else:
                    quoted = not quoted
            elif char == "," and not quoted:
                cells.append("".join(current))
                current = []
            else:
                current.append(char)
            index += 1
        cells.append("".join(current))
        rows.append(cells)
    return rows


def strip_title_block(rows):
    """Drop the FOOTING_TYPES title block -- the INFO sheet replaces it."""
    for index, row in enumerate(rows):
        if row and row[0].strip() == "TypeMark":
            return rows[index:]
    return rows


def build_workbook(path, keep_macros=False):
    from openpyxl import Workbook
    book = Workbook()
    book.remove(book.active)

    info = book.create_sheet(title="INFO")
    for row in INFO_ROWS:
        info.append(row)

    for name in SHEETS:
        rows = read_csv_rows(os.path.join(HERE, name + ".csv"))
        if name == "FOOTING_TYPES":
            rows = strip_title_block(rows)
        sheet = book.create_sheet(title=name)
        for row in rows:
            sheet.append(row)

    book.save(path)
    return path


def build_text_sheets(folder):
    if not os.path.isdir(folder):
        os.makedirs(folder)
    written = []
    rows_by_sheet = [("INFO", INFO_ROWS)]
    for name in SHEETS:
        rows = read_csv_rows(os.path.join(HERE, name + ".csv"))
        if name == "FOOTING_TYPES":
            rows = strip_title_block(rows)
        rows_by_sheet.append((name, rows))

    for name, rows in rows_by_sheet:
        target = os.path.join(folder, name + ".txt")
        with io.open(target, "w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                # Tab-separated, so the Outline cell needs no quoting at all --
                # it has no tabs in it.
                handle.write(u"\t".join(str(cell) for cell in row) + u"\n")
        written.append(target)
    return written


def build_fake_legacy(path):
    """A file with a .xls name that is not one, for the refusal path."""
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(u"This is not a real BIFF workbook.\n"
                     u"It exists so the '.xls cannot be read' message is "
                     u"tested against a file that is present.\n")
    return path


def main():
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("openpyxl is needed. pip install openpyxl")
        return 1

    made = [
        build_workbook(os.path.join(HERE, "sample_schedule.xlsx")),
        build_workbook(os.path.join(HERE, "sample_schedule.xlsm")),
        build_fake_legacy(os.path.join(HERE, "sample_schedule.xls")),
    ]
    made.extend(build_text_sheets(os.path.join(HERE, "txt_sheets")))
    for path in made:
        print("wrote", os.path.relpath(path, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())

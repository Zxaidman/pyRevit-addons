# -*- coding: utf-8 -*-
"""
General-purpose utility functions.

These helpers solve recurring low-level problems that appear across multiple
modules: building .NET arrays for COM calls, parsing TSV exports from Revit
schedules, and extracting numbers from mixed text strings.
"""
import System


def create_com_array(*items):
    """
    Build a ``System.Object[]`` from Python arguments.

    Fixes the ``'type expected'`` error that CPython3/pythonnet raises when
    passing a variable number of arguments to COM ``InvokeMember`` calls.

    Args:
        *items: Values to pack into the array.

    Returns:
        System.Array[System.Object]
    """
    arr = System.Array.CreateInstance(System.Object, len(items))
    for i, item in enumerate(items):
        arr[i] = item
    return arr


def parse_tsv_row(line):
    """
    Parse one tab-delimited row, honouring RFC-4180-style double-quoted fields.

    Args:
        line (str): A single line from a TSV file (trailing newline already stripped).

    Returns:
        list[str]: Field values.
    """
    fields, buf, in_quotes = [], [], False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            if in_quotes and i + 1 < len(line) and line[i + 1] == '"':
                buf.append('"')
                i += 2
                continue
            in_quotes = not in_quotes
        elif ch == '\t' and not in_quotes:
            fields.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    fields.append(''.join(buf))
    return fields


def read_tsv(path):
    """
    Read a TSV file, trying multiple encodings for robustness.

    Revit schedule exports can be UTF-8 BOM, CP-1252, or Latin-1 depending
    on the Windows locale.  This function tries each in order.

    Args:
        path (str): Absolute path to the TSV file.

    Returns:
        list[list[str]]: Parsed rows, or an empty list on failure.
    """
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            rows = []
            with open(path, "r", encoding=encoding) as fh:
                for line in fh:
                    rows.append(parse_tsv_row(line.rstrip("\r\n")))
            return rows
        except (UnicodeDecodeError, Exception):
            continue
    return []


def extract_numeric(text):
    """
    Extract the first valid floating-point number from a mixed string.

    Handles European comma-as-decimal-separator notation.  Regex-free so it
    works under both IronPython 2 and CPython 3 without the ``re`` module.

    Args:
        text (str | any): Input value.  Non-strings are cast with ``str()``.

    Returns:
        float | None: First number found, or ``None`` if none.
    """
    if not text:
        return None

    s = str(text).replace(" ", "")
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_comma > last_dot:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")

    n, j = len(s), 0
    while j < n:
        c = s[j]
        if c.isdigit() or (c == "-" and j + 1 < n and s[j + 1].isdigit()):
            digits, k = [], j
            if s[k] == "-":
                digits.append("-")
                k += 1
            while k < n and s[k].isdigit():
                digits.append(s[k])
                k += 1
            if k < n and s[k] == ".":
                frac, m = [], k + 1
                while m < n and s[m].isdigit():
                    frac.append(s[m])
                    m += 1
                if frac:
                    digits.append(".")
                    digits.extend(frac)
            try:
                return float("".join(digits))
            except ValueError:
                pass
        j += 1
    return None


def extract_bracket_int(text):
    """
    Parse a leading ``[<int>]`` prefix and return the integer.

    Used to unpack the ``"[<id>] <name>"`` format that
    :func:`~anongee_toolkit.revit.parameters.get_parameter_value` emits for
    ElementId parameters.

    Args:
        text (str): Input string, e.g. ``"[123456] Concrete - 30MPa"``.

    Returns:
        int | None: The bracketed integer, or ``None`` if not present.
    """
    if not text or not text.startswith("["):
        return None
    end = text.find("]")
    if end < 1:
        return None
    try:
        return int(text[1:end].strip())
    except ValueError:
        return None

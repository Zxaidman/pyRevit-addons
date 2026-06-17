# -*- coding: utf-8 -*-
import System

def create_com_array(*items):
    """
    Builds a .NET Object[] reliably. 
    Fixes the 'type expected' error in CPython3/pythonnet when passing arguments to COM objects.
    """
    arr = System.Array.CreateInstance(System.Object, len(items))
    for i, item in enumerate(items):
        arr[i] = item
    return arr

def parse_tsv_row(line):
    """Parses one tab-delimited line, honouring double-quoted fields."""
    fields, buf, in_q = [], [], False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '"':
            if in_q and i + 1 < len(line) and line[i + 1] == '"':
                buf.append('"'); i += 2; continue
            in_q = not in_q
        elif ch == '\t' and not in_q:
            fields.append(''.join(buf)); buf = []
        else:
            buf.append(ch)
        i += 1
    fields.append(''.join(buf))
    return fields

def read_tsv(path):
    """
    Reads a TSV file robustly, handling multiple text encodings.
    Often used to parse native Revit Schedule exports.
    """
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            rows = []
            with open(path, 'r', encoding=enc) as fh:
                for line in fh:
                    rows.append(parse_tsv_row(line.rstrip('\r\n')))
            return rows
        except (UnicodeDecodeError, Exception):
            continue
    return []

def extract_numeric(text):
    """Extracts the first valid floating-point number from a string. Regex-free."""
    if not text:
        return None
    s = str(text).replace(" ", "")
    last_dot, last_comma = s.rfind('.'), s.rfind(',')
    if last_comma > last_dot:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '')
    n, j = len(s), 0
    while j < n:
        c = s[j]
        if c.isdigit() or (c == '-' and j + 1 < n and s[j + 1].isdigit()):
            digits, k = [], j
            if s[k] == '-':
                digits.append('-'); k += 1
            while k < n and s[k].isdigit():
                digits.append(s[k]); k += 1
            if k < n and s[k] == '.':
                frac, m = [], k + 1
                while m < n and s[m].isdigit():
                    frac.append(s[m]); m += 1
                if frac:
                    digits.append('.'); digits.extend(frac)
            try: return float(''.join(digits))
            except ValueError: pass
        j += 1
    return None

def extract_bracket_int(text):
    """Parses a leading '[<int>]' prefix to an integer."""
    if not text or not text.startswith('['): return None
    end = text.find(']')
    if end < 1: return None
    try: return int(text[1:end].strip())
    except ValueError: return None
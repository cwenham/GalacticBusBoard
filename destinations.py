"""
destinations.py
─────────────────────────────────────────────────────────────────────────────
Loads a CSV lookup table of curated short names for bus destinations, so
common but awkwardly-abbreviating names (e.g. "Shooting Field" trimming
down to just "Shoot") can be given a sensible fixed short form instead of
relying purely on character-by-character pixel-width trimming.

CSV format (header row optional, columns in this order):
    ID (integer), Stop Name, Short Name

e.g.
    id,stop_name,short_name
    1,Shooting Field,Shoot Fld
    2,Churchill Square,Churchill Sq
    3,Portslade Old Village,Portslade OV

This is intentionally a flat file rather than a database: the columns and
the ID column in particular are there so this file can later be exported
from (or imported into) a proper database table without changing shape.
─────────────────────────────────────────────────────────────────────────────
"""

import config


def parse_csv_line(line):
    """
    Minimal CSV field splitter supporting double-quoted fields (with ""
    as an escaped quote inside a quoted field). Deliberately hand-rolled
    rather than depending on a `csv` module, since one isn't guaranteed to
    be present in MicroPython builds.
    """
    fields = []
    field  = ""
    in_quotes = False
    i = 0
    n = len(line)

    while i < n:
        ch = line[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < n and line[i + 1] == '"':
                    field += '"'
                    i += 1
                else:
                    in_quotes = False
            else:
                field += ch
        else:
            if ch == '"':
                in_quotes = True
            elif ch == ',':
                fields.append(field)
                field = ""
            else:
                field += ch
        i += 1

    fields.append(field)
    return fields


def load_overrides(path=None):
    """
    Load the destination short-name overrides CSV into a dict keyed by a
    normalised (lowercased, trimmed) stop name, so lookups are tolerant of
    minor case/whitespace differences between this table and whatever
    TransportAPI happens to return. Each value is
    {"id": int_or_str, "stop_name": str, "short_name": str}.

    Missing file, unreadable rows, or a malformed line are all handled by
    skipping and logging rather than crashing — this feature is additive,
    so a bad CSV should degrade to "no overrides", not take the board down.
    """
    path = path or config.DESTINATION_OVERRIDES_CSV
    overrides = {}

    try:
        f = open(path, "r")
    except OSError as exc:
        print("Destination overrides: could not open '{}' ({}) - continuing without overrides".format(path, exc))
        return overrides

    try:
        first_line = True
        line_no = 0
        for raw_line in f:
            line_no += 1
            line = raw_line.strip()
            if not line:
                continue

            fields = parse_csv_line(line)

            if first_line:
                first_line = False
                # A header row's first field won't parse as an integer
                # ("id" / "ID" / etc.) - skip it if so.
                try:
                    int(fields[0].strip())
                except ValueError:
                    continue

            if len(fields) < 3:
                print("Destination overrides: skipping malformed row {}: {!r}".format(line_no, line))
                continue

            raw_id, stop_name, short_name = fields[0].strip(), fields[1].strip(), fields[2].strip()
            if not stop_name or not short_name:
                print("Destination overrides: skipping row {} with empty name(s)".format(line_no))
                continue

            try:
                row_id = int(raw_id)
            except ValueError:
                print("Destination overrides: row {} has non-integer ID {!r}, keeping as text".format(line_no, raw_id))
                row_id = raw_id

            key = stop_name.lower()
            overrides[key] = {"id": row_id, "stop_name": stop_name, "short_name": short_name}
    finally:
        f.close()

    print("Destination overrides: loaded {} entries from '{}'".format(len(overrides), path))
    return overrides


def get_short_name(overrides, raw_name):
    """
    Look up raw_name in the overrides table (case-insensitive, whitespace-
    trimmed). Returns the configured short name if there's a match,
    otherwise returns raw_name unchanged so the caller's normal pixel-fit
    trimming can still apply.
    """
    if not raw_name:
        return raw_name
    entry = overrides.get(raw_name.strip().lower())
    return entry["short_name"] if entry else raw_name

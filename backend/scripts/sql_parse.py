"""One quote-aware parser for the SQL seed files.

Used by scripts.build_all_in_one and tests/test_migrations_sql.py so the
build, the docs and the tests can never disagree about what the migrations
contain.
"""
from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

SEED_FILES = ("003_seed_3pl.sql", "004_broaden_beyond_ecommerce.sql")

# (label, insert marker, number of fields that form the unique constraint)
SEEDED = {
    "signals": ("insert into service_signals", 1),
    "keywords": ("insert into service_keywords", 2),
    "queries": ("insert into discovery_queries", 2),
    "roles": ("insert into service_roles", 1),
}


def strip_comments(sql: str) -> str:
    """Remove -- comments, leaving comment markers inside string literals."""
    out = []
    for line in sql.splitlines():
        in_str, i = False, 0
        while i < len(line):
            if line[i] == "'":
                in_str = not in_str
            elif not in_str and line[i:i + 2] == "--":
                line = line[:i]
                break
            i += 1
        out.append(line)
    return "\n".join(out)


def split_fields(row: str) -> list[str]:
    """Split one VALUES row on commas outside quotes.

    A naive regex cannot do this: `'a','b'` has no unquoted context between
    the fields, so lookahead-based splitting silently merges them.
    """
    fields, buf, in_str, i = [], [], False, 0
    while i < len(row):
        c = row[i]
        if c == "'":
            if in_str and i + 1 < len(row) and row[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_str = not in_str
            buf.append(c)
        elif c == "," and not in_str:
            fields.append("".join(buf).strip())
            buf = []
        else:
            buf.append(c)
        i += 1
    fields.append("".join(buf).strip())
    return fields


def values_block(sql: str, marker: str) -> str:
    """Extract the `(values ... )` list belonging to one INSERT."""
    start = sql.index("(values", sql.index(marker))
    depth, i = 1, start + len("(values")
    while depth:
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
        i += 1
    return sql[start:i]


def values_rows(sql: str, marker: str) -> list[list[str]]:
    """All rows of one INSERT's VALUES list, comments stripped."""
    sql = strip_comments(sql)
    try:
        block = values_block(sql, marker)
    except ValueError:
        return []
    return [split_fields(r) for r in re.findall(r"\(([^()]*)\)", block)]


def unquote(value: str):
    """SQL literal -> Python value."""
    value = value.strip()
    if value.lower() == "null":
        return None
    if value.startswith("'"):
        return value.strip("'").replace("''", "'")
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def collect(label: str, files: tuple[str, ...] = SEED_FILES) -> list[list[str]]:
    """Deduplicated rows for one seeded table, across all seed files.

    Dedup mirrors the database's unique constraint, so the count matches what
    actually lands in Postgres after the migration runs.
    """
    marker, key_len = SEEDED[label]
    out, seen = [], set()
    for name in files:
        sql = (MIGRATIONS / name).read_text()
        for row in values_rows(sql, marker):
            if len(row) < key_len:
                continue
            key = tuple(unquote(f) for f in row[:key_len])
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out


def expected_counts() -> dict[str, int]:
    return {label: len(collect(label)) for label in SEEDED}

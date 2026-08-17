"""Static validation of the SQL migration files.

These exist because the SQL path and the Python seed path are separate code,
and only the Python one is exercised by the rest of the suite. A duplicate row
inside a single INSERT ... ON CONFLICT DO UPDATE fails at runtime with
"ON CONFLICT DO UPDATE command cannot affect row a second time" - which is
exactly the kind of thing that should be caught here, not in production.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from scripts.sql_parse import (
    SEED_FILES, collect, split_fields, unquote, values_rows,
)

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
SEED_SQL = MIGRATIONS / "003_seed_3pl.sql"
BROADEN_SQL = MIGRATIONS / "004_broaden_beyond_ecommerce.sql"
INIT_SQL = MIGRATIONS / "001_init.sql"
RLS_SQL = MIGRATIONS / "002_rls.sql"
ALL_IN_ONE = MIGRATIONS / "ALL_IN_ONE.sql"

# (table, insert marker, indexes forming the unique constraint)
UNIQUE_CONSTRAINTS = [
    ("service_signals", "insert into service_signals", (0,)),
    ("service_keywords", "insert into service_keywords", (0, 1)),
    ("service_roles", "insert into service_roles", (0,)),
    ("discovery_queries", "insert into discovery_queries", (0, 1)),
]


def _values_block(sql: str, marker: str) -> str:
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


def _rows(block: str) -> list[list[str]]:
    return [[f.strip().strip("'") for f in split_fields(row)]
            for row in re.findall(r"\(([^()]*)\)", block)]


@pytest.mark.parametrize("seed_file", SEED_FILES)
@pytest.mark.parametrize("table,marker,key_idx", UNIQUE_CONSTRAINTS)
def test_no_duplicate_constrained_values(table: str, marker: str,
                                         key_idx: tuple[int, ...],
                                         seed_file: str):
    """A single INSERT must not propose the same constrained values twice.

    Checked per file: each migration is its own statement, so duplicates
    only matter within one file.
    """
    sql = (MIGRATIONS / seed_file).read_text(encoding="utf-8")
    rows = values_rows(sql, marker)
    keys = [tuple(r[i].strip("'") for i in key_idx)
            for r in rows if len(r) > max(key_idx)]
    duplicates = {k: c for k, c in Counter(keys).items() if c > 1}
    assert not duplicates, (
        f"{seed_file}: {table} has duplicate rows within one INSERT: "
        f"{duplicates}. Postgres will raise 'ON CONFLICT DO UPDATE command "
        f"cannot affect row a second time'.")


@pytest.mark.parametrize("seed_file", SEED_FILES)
def test_every_insert_is_idempotent(seed_file: str):
    """Re-running the seed must not duplicate rows or error."""
    sql = (MIGRATIONS / seed_file).read_text(encoding="utf-8")
    for match in re.finditer(r"insert into (\w+)", sql):
        nxt = sql.find("insert into", match.end())
        segment = sql[match.start(): nxt if nxt > 0 else len(sql)]
        assert "on conflict" in segment or "not exists" in segment, (
            f"insert into {match.group(1)} has no idempotency guard")


def test_rls_only_targets_tables_that_exist():
    created = set(re.findall(r"create table if not exists (\w+)",
                             INIT_SQL.read_text(encoding="utf-8")))
    secured = set(re.findall(r"alter table (\w+)\s+enable row level security",
                             RLS_SQL.read_text(encoding="utf-8")))
    assert secured <= created, f"RLS on non-existent tables: {secured - created}"


def test_foreign_keys_target_tables_that_exist():
    sql = INIT_SQL.read_text(encoding="utf-8")
    created = set(re.findall(r"create table if not exists (\w+)", sql))
    referenced = set(re.findall(r"references (\w+)\(", sql))
    assert referenced <= created, f"FK to missing tables: {referenced - created}"


def test_dollar_quotes_and_parens_are_balanced():
    for path in (INIT_SQL, RLS_SQL, SEED_SQL, BROADEN_SQL, ALL_IN_ONE):
        code = "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                         if not l.strip().startswith("--"))
        assert len(re.findall(r"\$\$", code)) % 2 == 0, f"{path.name}: unbalanced $$"
        assert code.count("(") == code.count(")"), f"{path.name}: unbalanced parens"


def test_all_in_one_is_current():
    """ALL_IN_ONE.sql must contain the current contents of its three sources."""
    combined = ALL_IN_ONE.read_text(encoding="utf-8")
    for path in (INIT_SQL, RLS_SQL, SEED_SQL, BROADEN_SQL):
        body = path.read_text(encoding="utf-8").strip()
        assert body in combined, (
            f"ALL_IN_ONE.sql is stale relative to {path.name}. "
            f"Regenerate it with: python -m scripts.build_all_in_one")


def test_seed_script_keywords_have_no_duplicates():
    """The Python seed path has the same constraint."""
    from scripts.seed import KEYWORDS, QUERIES, ROLES, SIGNALS

    for label, items, key in [
        ("SIGNALS", SIGNALS, lambda r: r[0]),
        ("KEYWORDS", KEYWORDS, lambda r: (r[0], r[1])),
        ("ROLES", ROLES, lambda r: r[0]),
        ("QUERIES", QUERIES, lambda r: (r[0], r[1])),
    ]:
        counts = Counter(key(row) for row in items)
        duplicates = {k: c for k, c in counts.items() if c > 1}
        assert not duplicates, f"scripts.seed.{label} has duplicates: {duplicates}"


def _declared_unique_constraints() -> dict[str, set[tuple[str, ...]]]:
    init = INIT_SQL.read_text(encoding="utf-8")
    out: dict[str, set[tuple[str, ...]]] = {}
    for match in re.finditer(r"create table if not exists (\w+) \((.*?)\n\);",
                             init, re.S):
        table, body = match.group(1), match.group(2)
        constraints: set[tuple[str, ...]] = set()
        for unique in re.findall(r"unique \(([^)]+)\)", body):
            constraints.add(tuple(c.strip() for c in unique.split(",")))
        for line in body.splitlines():
            line = line.strip()
            if " unique" in line and not line.startswith("unique"):
                constraints.add((line.split()[0],))
            if "primary key" in line:
                constraints.add((line.split()[0],))
        out[table] = constraints
    return out


def _insert_segments(sql: str):
    starts = [m.start() for m in re.finditer(r"^insert into ", sql, re.M)]
    starts.append(len(sql))
    for i in range(len(starts) - 1):
        segment = sql[starts[i]:starts[i + 1]]
        yield re.match(r"insert into (\w+)", segment).group(1), segment


def test_on_conflict_targets_match_a_real_constraint():
    """An ON CONFLICT target with no matching unique index raises 42P10:
    'there is no unique or exclusion constraint matching the ON CONFLICT
    specification'."""
    declared = _declared_unique_constraints()
    problems = []
    segments = [seg for name in SEED_FILES
                for seg in _insert_segments((MIGRATIONS / name).read_text(encoding="utf-8"))]
    for table, segment in segments:
        match = re.search(r"on conflict \(([^)]+)\)", segment)
        if not match:
            continue
        target = tuple(c.strip() for c in match.group(1).split(","))
        if target not in declared.get(table, set()):
            problems.append(f"{table} ON CONFLICT {target} "
                            f"(declared: {sorted(declared.get(table, set()))})")
    assert not problems, f"ON CONFLICT targets with no matching constraint: {problems}"


def test_every_insert_segment_is_guarded():
    """Checked per-statement, so an unguarded INSERT can't hide behind the
    next statement's guard."""
    unguarded = [
        f"{name}:{table}" for name in SEED_FILES
        for table, segment in _insert_segments((MIGRATIONS / name).read_text(encoding="utf-8"))
        if "on conflict" not in segment and "not exists" not in segment
    ]
    assert not unguarded, f"INSERTs with no idempotency guard: {unguarded}"


def test_python_seed_does_not_contradict_the_sql_seed():
    """The SQL migration is the authoritative seed (84 keywords vs 51); the
    Python list is a smaller set for local development. They may differ in
    size, but must never disagree about what a keyword means - a keyword
    mapped to different signal_types in the two paths would score the same
    company differently depending on how it was seeded.
    """
    from scripts.seed import KEYWORDS, ROLES, SIGNALS

    sql_keywords = {
        (unquote(r[0]), unquote(r[1])): unquote(r[2])
        for r in collect("keywords") if len(r) > 2
    }
    sql_signals = {
        unquote(r[0]): unquote(r[3])
        for r in collect("signals") if len(r) > 3
    }
    sql_roles = {
        unquote(r[0]): unquote(r[1])
        for r in collect("roles") if len(r) > 1
    }

    conflicts = []
    for keyword, category, signal_type, _weight in KEYWORDS:
        if (keyword, category) not in sql_keywords:
            continue
        sql_signal = sql_keywords[(keyword, category)]
        if sql_signal != signal_type:
            conflicts.append(
                f"keyword {keyword!r}: python={signal_type!r} sql={sql_signal!r}")

    for signal_type, _name, _desc, weight, _decay, _occ in SIGNALS:
        sql_weight = sql_signals.get(signal_type)
        if sql_weight is not None and float(sql_weight) != float(weight):
            conflicts.append(
                f"signal {signal_type!r}: python weight={weight} sql={sql_weight}")

    for pattern, priority in ROLES:
        sql_priority = sql_roles.get(pattern)
        if sql_priority is not None and int(sql_priority) != int(priority):
            conflicts.append(
                f"role {pattern!r}: python={priority} sql={sql_priority}")

    assert not conflicts, (
        "The two seed paths disagree, so a company would score differently "
        f"depending on how the database was seeded:\n  "
        + "\n  ".join(conflicts))


# --------------------------------------------------------------------------
# Encoding
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", [
    "001_init.sql", "002_rls.sql", "003_seed_3pl.sql",
    "004_broaden_beyond_ecommerce.sql", "005_query_library.sql",
    "006_linkedin_url.sql", "ALL_IN_ONE.sql",
])
def test_migrations_are_pure_ascii(name: str):
    """SQL files get opened in editors that re-save as cp1252, which turns an
    em-dash into byte 0x97 and makes the file undecodable as UTF-8. Staying
    ASCII removes the failure mode."""
    raw = (MIGRATIONS / name).read_bytes()
    try:
        raw.decode("ascii")
    except UnicodeDecodeError as exc:
        context = raw[max(0, exc.start - 40):exc.start + 40]
        pytest.fail(
            f"{name} is not ASCII at byte {exc.start}: "
            f"{raw[exc.start:exc.start + 2]!r}\n"
            f"  context: {context.decode('latin-1')!r}\n"
            f"  Fix: python -m scripts.build_all_in_one "
            f"(or replace the character by hand)")


@pytest.mark.parametrize("name", [
    "001_init.sql", "002_rls.sql", "003_seed_3pl.sql",
    "004_broaden_beyond_ecommerce.sql", "005_query_library.sql",
    "006_linkedin_url.sql", "ALL_IN_ONE.sql",
])
def test_migrations_use_lf_line_endings(name: str):
    assert b"\r\n" not in (MIGRATIONS / name).read_bytes(), (
        f"{name} has CRLF line endings; an editor re-saved it")


def test_query_library_sql_is_current():
    from scripts.query_library import build_library
    sql = (MIGRATIONS / "005_query_library.sql").read_text(encoding="utf-8")
    rows = re.findall(r"^ \('(.*?)', (?:null|'[A-Z]{2}'), \d\)", sql, re.M)
    assert len(rows) == len(build_library()), (
        "005_query_library.sql is stale. "
        "Rebuild: python -m scripts.build_query_library")

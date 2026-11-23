"""Regenerate migrations/ALL_IN_ONE.sql from the source migrations.

Run after editing any of them:
    python -m scripts.build_all_in_one

tests/test_migrations_sql.py::test_all_in_one_is_current fails if you forget.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

PARTS = [
    ("001_init.sql", "SCHEMA - tables, indexes, triggers"),
    ("002_rls.sql", "ROW LEVEL SECURITY - policies"),
    ("003_seed_3pl.sql", "SEED - the 3PL service configuration"),
    ("004_broaden_beyond_ecommerce.sql",
     "BROADEN - legacy 3PL wholesale, manufacturing, retail segments"),
    ("006_linkedin_url.sql", "SCHEMA - company LinkedIn URL columns"),
    ("007_powersports_aftermarket_sourcing.sql",
     "SEED - Powersports Aftermarket Product Sourcing (default service)"),
]

HEADER = """-- =====================================================================
--  ALL-IN-ONE MIGRATION
--  Configurable B2B Intent Intelligence Platform
--  Default service: powersports_aftermarket_sourcing
--  Legacy service retained (inactive): 3pl
--
--  Paste this entire file into the Supabase SQL Editor and press Run.
--  Requires no local database connection, no drivers, no DNS.
--
--  Safe to re-run: every statement is idempotent
--  (create ... if not exists / on conflict / not exists guards).
--
--  GENERATED FILE - do not edit directly.
--  Source: 001_init.sql + 002_rls.sql + 003_seed_3pl.sql
--          + 004_broaden_beyond_ecommerce.sql + 006_linkedin_url.sql
--          + 007_powersports_aftermarket_sourcing.sql
--  (005_query_library.sql - the 8k-query legacy 3PL library - is optional
--   and run separately.)
--  Rebuild: python -m scripts.build_all_in_one
--  Generated {stamp}
-- =====================================================================

"""

FOOTER = """

-- =====================================================================
--  DONE. Verify with:
-- =====================================================================
select
  (select count(*) from services)          as services,
  (select count(*) from service_signals)   as signals,
  (select count(*) from service_keywords)  as keywords,
  (select count(*) from discovery_queries) as queries,
  (select count(*) from service_roles)     as roles;
-- Expect: {expected}
"""


def expected_counts() -> str:
    """Derived from the SQL itself, deduplicated the same way Postgres will
    dedupe it, so this comment can never drift out of date."""
    from scripts.sql_parse import SERVICE_SEED_GROUPS
    from scripts.sql_parse import expected_counts as counts

    c = counts(SERVICE_SEED_GROUPS)
    return (f"{c['services']} services, {c['signals']} signals, "
            f"{c['keywords']} keywords, {c['queries']} queries, "
            f"{c['roles']} roles")


def _assert_ascii(text: str, label: str) -> str:
    """Generated SQL must be pure ASCII.

    These files get opened in editors that re-save as cp1252, which turns an
    em-dash into 0x97 and makes the file undecodable as UTF-8. Staying ASCII
    removes the failure mode entirely.
    """
    bad = sorted({c for c in text if ord(c) > 127})
    if bad:
        raise ValueError(f"{label} contains non-ASCII characters: {bad}")
    return text


def build() -> Path:
    chunks = [HEADER.format(stamp=f"{datetime.now(timezone.utc):%Y-%m-%d}")]
    for name, label in PARTS:
        body = (MIGRATIONS / name).read_text()
        chunks.append(
            "\n\n-- ====================================================="
            "================\n"
            f"--  PART {name[:3]}  |  {label}\n"
            "-- ====================================================="
            "================\n\n" + body)
    chunks.append(FOOTER.format(expected=expected_counts()))

    out = MIGRATIONS / "ALL_IN_ONE.sql"
    out.write_text(_assert_ascii("".join(chunks), out.name),
                   encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    path = build()
    lines = len(path.read_text().splitlines())
    print(f"Wrote {path.relative_to(path.parent.parent)} "
          f"({lines} lines, {path.stat().st_size:,} bytes)")
    print(f"Expected after running: {expected_counts()}")

"""Regenerate migrations/ALL_IN_ONE.sql from the three source migrations.

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
    ("001_init.sql", "SCHEMA — tables, indexes, triggers"),
    ("002_rls.sql", "ROW LEVEL SECURITY — policies"),
    ("003_seed_3pl.sql", "SEED — the 3PL service configuration"),
]

HEADER = """-- =====================================================================
--  ALL-IN-ONE MIGRATION
--  Configurable B2B Intent Intelligence Platform  |  V1 service: 3PL
--
--  Paste this entire file into the Supabase SQL Editor and press Run.
--  Requires no local database connection, no drivers, no DNS.
--
--  Safe to re-run: every statement is idempotent
--  (create ... if not exists / on conflict / not exists guards).
--
--  GENERATED FILE - do not edit directly.
--  Source: 001_init.sql + 002_rls.sql + 003_seed_3pl.sql
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
    """Derive the expected row counts from the seed file itself, so the
    comment can never drift out of date."""
    import re
    from collections import Counter

    sql = (MIGRATIONS / "003_seed_3pl.sql").read_text()

    def count(marker: str) -> int:
        start = sql.index("(values", sql.index(marker))
        depth, i = 1, start + len("(values")
        while depth:
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
            i += 1
        return len(re.findall(r"\(([^()]*)\)", sql[start:i]))

    return (f"1 service, {count('insert into service_signals')} signals, "
            f"{count('insert into service_keywords')} keywords, "
            f"{count('insert into discovery_queries')} queries, "
            f"{count('insert into service_roles')} roles")


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
    out.write_text("".join(chunks))
    return out


if __name__ == "__main__":
    path = build()
    lines = len(path.read_text().splitlines())
    print(f"Wrote {path.relative_to(path.parent.parent)} "
          f"({lines} lines, {path.stat().st_size:,} bytes)")
    print(f"Expected after running: {expected_counts()}")

"""Generate migrations/005_query_library.sql from scripts.query_library.

    python -m scripts.build_query_library
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.query_library import (  # noqa: E402
    EXCLUDED_BUSINESS_TYPES, QUERY_EXCLUSION_TERMS, build_library, stats,
)

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
OUT = MIGRATIONS / "005_query_library.sql"
CHUNK = 400          # rows per INSERT; keeps statements parseable


def sql_str(value: str | None) -> str:
    if value is None:
        return "null"
    return "'" + value.replace("'", "''") + "'"


def build() -> Path:
    queries = build_library()
    info = stats(queries)

    exclusion_terms = ", ".join(sql_str(t) for t in QUERY_EXCLUSION_TERMS)
    business_types = ", ".join(sql_str(t) for t in EXCLUDED_BUSINESS_TYPES)

    parts: list[str] = [f"""-- =====================================================================
-- 005  DISCOVERY QUERY LIBRARY
--
-- {info['total']:,} Serper queries generated from
-- BUSINESS MODEL x CATEGORY x PATTERN x PLATFORM x GROWTH x GEOGRAPHY.
--
-- Tiers (stored in discovery_queries.priority):
--   1  {info['by_tier'].get(1, 0):>5}  platform + category, DTC + category   <- run these first
--   2  {info['by_tier'].get(2, 0):>5}  business model x category
--   3  {info['by_tier'].get(3, 0):>5}  growth, directories, alt terminology
--   4  {info['by_tier'].get(4, 0):>5}  geographic fan-out and broad discovery
--
-- Seeding all of them costs nothing - only EXECUTED queries cost Serper
-- credits. Discovery runs by tier, so start with tier 1.
--
-- GENERATED FILE - do not edit directly.
-- Rebuild: python -m scripts.build_query_library
-- Generated {datetime.now(timezone.utc):%Y-%m-%d}
-- =====================================================================

-- Tier selection needs this index once the table is large.
create index if not exists idx_discovery_queries_service_priority
  on discovery_queries(service_id, priority, enabled);

-- Negative operators appended to every query at search time, and the
-- business types rejected at classification. Stored in service config so
-- they are tunable without a deploy.
update services
set config = config || jsonb_build_object(
      'query_exclusion_terms', jsonb_build_array(
        {exclusion_terms}),
      'excluded_business_types', jsonb_build_array(
        {business_types}))
where slug = '3pl';
"""]

    for i in range(0, len(queries), CHUNK):
        chunk = queries[i:i + CHUNK]
        lo, hi = i + 1, i + len(chunk)
        values = ",\n ".join(
            f"({sql_str(q.text)}, {sql_str(q.country)}, {q.tier})"
            for q in chunk)
        parts.append(f"""

-- ---------------------------------------------------------------------
-- queries {lo:,}-{hi:,} of {len(queries):,}
-- ---------------------------------------------------------------------
insert into discovery_queries (service_id, query, country, priority)
select s.id, v.query, v.country, v.priority
from services s,
(values
 {values}
) as v(query, country, priority)
where s.slug = '3pl'
  and not exists (
    select 1 from discovery_queries dq
    where dq.service_id = s.id and dq.query = v.query
      and dq.country is not distinct from v.country);""")

    parts.append(f"""


-- =====================================================================
--  DONE. Verify:
-- =====================================================================
select priority as tier, count(*) as queries
from discovery_queries
group by priority order by priority;
-- Expect roughly: tier1 {info['by_tier'].get(1, 0)}, tier2 {info['by_tier'].get(2, 0)}, """
                 f"""tier3 {info['by_tier'].get(3, 0)}, tier4 {info['by_tier'].get(4, 0)}
""")

    OUT.write_text("".join(parts))
    return OUT


if __name__ == "__main__":
    path = build()
    lib = build_library()
    info = stats(lib)
    print(f"Wrote {path.relative_to(path.parent.parent)}")
    print(f"  {info['total']:,} queries, {path.stat().st_size:,} bytes, "
          f"{len(path.read_text().splitlines()):,} lines")
    print(f"  tiers: {info['by_tier']}")

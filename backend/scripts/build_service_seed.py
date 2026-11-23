"""Generate the idempotent SQL migration for a data-defined service.

    python -m scripts.build_service_seed                    # every registered service
    python -m scripts.build_service_seed powersports_aftermarket_sourcing

The Python module in scripts/services/ is the source of truth; the SQL and
the ORM seed (scripts/seed.py) are both derived from it, so the two seed
paths cannot disagree. tests/test_powersports_migration.py fails if the SQL
is stale.

Migration 007 also carries the additive, generic schema the new service
needs (company_type / size / headquarters columns, company_facts,
product_interests). Nothing is dropped or overwritten; the legacy 3PL service
is set inactive and keeps all of its rows and history.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.services import MIGRATION_FILES, SERVICE_MODULES  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

SCHEMA_SQL = """-- ---------------------------------------------------------------------
-- 1. GENERIC SCHEMA ADDITIONS (additive only - nothing dropped or renamed)
-- ---------------------------------------------------------------------
alter table companies add column if not exists company_type text;
alter table companies add column if not exists company_type_confidence double precision;
alter table companies add column if not exists company_type_evidence jsonb not null default '{}'::jsonb;
alter table companies add column if not exists employee_band text;
alter table companies add column if not exists size_confidence double precision;
alter table companies add column if not exists size_source_url text;
alter table companies add column if not exists size_observed_at timestamptz;
alter table companies add column if not exists headquarters text;
alter table companies add column if not exists headquarters_state text;
alter table companies add column if not exists linkedin_url text;
alter table companies add column if not exists linkedin_source text;
alter table companies add column if not exists linkedin_checked_at timestamptz;

create index if not exists idx_companies_company_type on companies(company_type);
create index if not exists idx_companies_employee_band on companies(employee_band);
create index if not exists idx_companies_hq_state on companies(headquarters_state);

-- Time-varying, sourced company facts. is_estimate separates verified
-- statements from inferences.
create table if not exists company_facts (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id) on delete cascade,
    fact_type    text not null,
    value        text not null,
    source_id    uuid references sources(id) on delete set null,
    source_url   text,
    evidence     text,
    confidence   double precision not null default 0.5,
    is_estimate  boolean not null default false,
    observed_at  timestamptz not null default now(),
    unique (company_id, fact_type, value)
);
create index if not exists idx_company_facts_company
  on company_facts(company_id, fact_type);

-- What a company may want to buy, with the evidence class of each claim.
create table if not exists product_interests (
    id                uuid primary key default gen_random_uuid(),
    company_id        uuid not null references companies(id) on delete cascade,
    service_id        uuid not null references services(id) on delete cascade,
    signal_id         uuid references signals(id) on delete set null,
    signal_type       text,
    interest_type     text not null check (interest_type in
                        ('EXPLICITLY_SEEKING','RECENTLY_ADDED',
                         'CURRENTLY_CARRIED','INFERRED_FIT')),
    category          text,
    subcategory       text,
    products          jsonb not null default '[]'::jsonb,
    vehicle_segments  jsonb not null default '[]'::jsonb,
    vehicle_platforms jsonb not null default '[]'::jsonb,
    brand             text,
    reason            text,
    source_id         uuid references sources(id) on delete set null,
    source_url        text,
    published_at      timestamptz,
    event_date        timestamptz,
    evidence          text,
    confidence        double precision not null default 0.5,
    created_at        timestamptz not null default now()
);
create index if not exists idx_product_interests_company_service
  on product_interests(company_id, service_id);
create index if not exists idx_product_interests_category
  on product_interests(category);

alter table company_facts     enable row level security;
alter table product_interests enable row level security;
drop policy if exists "auth_read_company_facts" on company_facts;
create policy "auth_read_company_facts" on company_facts
  for select to authenticated using (true);
drop policy if exists "auth_read_product_interests" on product_interests;
create policy "auth_read_product_interests" on product_interests
  for select to authenticated using (true);
"""


def sql_str(value) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def sql_num(value) -> str:
    if value is None:
        return "null"
    return str(int(value)) if float(value).is_integer() else str(value)


def _assert_ascii(text: str, label: str) -> str:
    bad = sorted({c for c in text if ord(c) > 127})
    if bad:
        raise ValueError(f"{label} contains non-ASCII characters: {bad}")
    return text


def _assert_no_parens(rows, label: str) -> None:
    """scripts/sql_parse.py reads VALUES rows with a paren-delimited regex,
    so seeded literals must not contain parentheses."""
    for row in rows:
        for value in row:
            if isinstance(value, str) and ("(" in value or ")" in value):
                raise ValueError(f"{label}: parenthesis in seeded value {value!r}")


def render(module) -> str:
    slug = module.SLUG
    _assert_no_parens(module.SIGNALS, "SIGNALS")
    _assert_no_parens(module.KEYWORDS, "KEYWORDS")
    _assert_no_parens(module.ROLES, "ROLES")
    library = module.build_library()
    _assert_no_parens([(q.text,) for q in library], "QUERIES")

    config_json = json.dumps(module.CONFIG, ensure_ascii=True, sort_keys=True)
    signals = ",\n ".join(
        f"({sql_str(t)},{sql_str(n)},{sql_str(d)},{sql_num(w)},{sql_num(dd)},{m})"
        for t, n, d, w, dd, m in module.SIGNALS)
    keywords = ",\n ".join(
        f"({sql_str(k)},{sql_str(c)},{sql_str(s)},{sql_num(w)})"
        for k, c, s, w in module.KEYWORDS)
    roles = ",\n ".join(f"({sql_str(p)},{r})" for p, r in module.ROLES)
    queries = ",\n ".join(
        f"({sql_str(q.text)}, {sql_str(q.country)}, {q.tier})" for q in library)
    tiers = module.stats(library)["by_tier"]

    number = MIGRATION_FILES[slug][:3]
    return f"""-- =====================================================================
-- {number}  {module.NAME.upper()}
--
-- Service slug: {slug}
-- New default service. Additive and idempotent: safe to re-run, safe on a
-- database seeded by 001-006. Deletes nothing. The legacy '3pl' service is
-- set inactive and keeps every signal, keyword, query, opportunity and
-- review it ever produced.
--
-- GENERATED FILE - do not edit directly.
-- Source: scripts/services/{slug}.py
-- Rebuild: python -m scripts.build_service_seed {slug}
-- =====================================================================

{SCHEMA_SQL}
-- ---------------------------------------------------------------------
-- 2. SERVICE
-- ---------------------------------------------------------------------
insert into services (name, slug, description, status, config)
values (
  {sql_str(module.NAME)}, {sql_str(slug)},
  {sql_str(module.DESCRIPTION)},
  'active',
  {sql_str(config_json)}::jsonb
)
on conflict (slug) do update
  set name = excluded.name, description = excluded.description,
      config = excluded.config, status = 'active';

-- Retain, do not delete, the legacy service.
update services set status = 'inactive' where slug = '3pl';

-- ---------------------------------------------------------------------
-- 3. SIGNALS + WEIGHTS  ({len(module.SIGNALS)})
-- ---------------------------------------------------------------------
insert into service_signals
  (service_id, signal_type, signal_name, description, weight, decay_days, max_occurrences)
select s.id, v.signal_type, v.signal_name, v.description, v.weight, v.decay_days, v.max_occ
from services s,
(values
 {signals}
) as v(signal_type, signal_name, description, weight, decay_days, max_occ)
where s.slug = {sql_str(slug)}
on conflict (service_id, signal_type) do update
  set weight = excluded.weight,
      decay_days = excluded.decay_days,
      signal_name = excluded.signal_name,
      description = excluded.description;

-- ---------------------------------------------------------------------
-- 4. KEYWORDS  ({len(module.KEYWORDS)})
-- ---------------------------------------------------------------------
insert into service_keywords (service_id, keyword, category, signal_type, weight)
select s.id, v.keyword, v.category, v.signal_type, v.weight
from services s,
(values
 {keywords}
) as v(keyword, category, signal_type, weight)
where s.slug = {sql_str(slug)}
on conflict (service_id, keyword, category) do update
  set weight = excluded.weight, signal_type = excluded.signal_type;

-- ---------------------------------------------------------------------
-- 5. DECISION-MAKER ROLES  ({len(module.ROLES)})
-- ---------------------------------------------------------------------
insert into service_roles (service_id, title_pattern, role_priority)
select s.id, v.pattern, v.prio
from services s,
(values
 {roles}
) as v(pattern, prio)
where s.slug = {sql_str(slug)}
on conflict (service_id, title_pattern) do update set role_priority = excluded.role_priority;

-- ---------------------------------------------------------------------
-- 6. DISCOVERY QUERIES  ({len(library)}: {tiers})
-- ---------------------------------------------------------------------
insert into discovery_queries (service_id, query, country, priority)
select s.id, v.query, v.country, v.priority
from services s,
(values
 {queries}
) as v(query, country, priority)
where s.slug = {sql_str(slug)}
  and not exists (
    select 1 from discovery_queries dq
    where dq.service_id = s.id and dq.query = v.query
      and dq.country is not distinct from v.country);

-- Verify:
-- select slug, status from services;
-- select priority as tier, count(*) from discovery_queries dq
--   join services s on s.id = dq.service_id
--   where s.slug = {sql_str(slug)} group by priority order by priority;
"""


def build(slug: str) -> Path:
    module = SERVICE_MODULES[slug]
    out = MIGRATIONS / MIGRATION_FILES[slug]
    out.write_text(_assert_ascii(render(module), out.name),
                   encoding="utf-8", newline="\n")
    return out


if __name__ == "__main__":
    slugs = sys.argv[1:] or list(SERVICE_MODULES)
    for slug in slugs:
        path = build(slug)
        print(f"Wrote {path.relative_to(path.parent.parent)} "
              f"({len(path.read_text().splitlines())} lines)")

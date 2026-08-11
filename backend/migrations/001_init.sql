-- =====================================================================
-- Configurable B2B Intent Intelligence Platform - Core Schema
-- Service-agnostic. Nothing in this file knows what "3PL" is.
-- Run in Supabase SQL Editor, or: psql "$DATABASE_MIGRATION_URL" -f 001_init.sql
-- =====================================================================

create extension if not exists "pgcrypto";
create extension if not exists "pg_trgm";

-- ---------------------------------------------------------------------
-- SERVICE CONFIGURATION (§11, §12, §13, §14)
-- ---------------------------------------------------------------------
create table if not exists services (
    id           uuid primary key default gen_random_uuid(),
    name         text not null,
    slug         text not null unique,
    description  text,
    status       text not null default 'active'
                 check (status in ('active','inactive','draft')),
    config       jsonb not null default '{}'::jsonb,  -- weights, thresholds, prompts
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

create table if not exists service_signals (
    id           uuid primary key default gen_random_uuid(),
    service_id   uuid not null references services(id) on delete cascade,
    signal_type  text not null,
    signal_name  text not null,
    description  text,
    weight       numeric(6,2) not null default 0,
    decay_days   integer,          -- null = never decays
    max_occurrences integer not null default 1,
    enabled      boolean not null default true,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),
    unique (service_id, signal_type)
);

create table if not exists service_keywords (
    id           uuid primary key default gen_random_uuid(),
    service_id   uuid not null references services(id) on delete cascade,
    keyword      text not null,
    category     text,             -- ecommerce | logistics | hiring | funding | ...
    signal_type  text,             -- which signal this keyword contributes to
    weight       numeric(6,2) not null default 1,
    enabled      boolean not null default true,
    created_at   timestamptz not null default now(),
    unique (service_id, keyword, category)
);

create table if not exists discovery_queries (
    id           uuid primary key default gen_random_uuid(),
    service_id   uuid not null references services(id) on delete cascade,
    query        text not null,
    country      text,
    priority     integer not null default 5,
    enabled      boolean not null default true,
    last_run_at  timestamptz,
    results_count integer not null default 0,
    created_at   timestamptz not null default now()
);

create table if not exists service_roles (
    id            uuid primary key default gen_random_uuid(),
    service_id    uuid not null references services(id) on delete cascade,
    title_pattern text not null,          -- matched case-insensitively
    role_priority integer not null default 50,   -- 1 = most desirable
    enabled       boolean not null default true,
    unique (service_id, title_pattern)
);

-- ---------------------------------------------------------------------
-- GENERIC COMPANY INTELLIGENCE (§15) - shared across all services
-- ---------------------------------------------------------------------
create table if not exists companies (
    id                  uuid primary key default gen_random_uuid(),
    name                text,
    domain              text not null unique,     -- normalized, no www, lowercase
    website             text,
    country             text,                     -- ISO-3166 alpha-2
    country_confidence  numeric(4,3),
    industry            text,
    description         text,
    is_ecommerce        boolean,
    is_physical_product boolean,
    platform            text,                     -- shopify | woocommerce | ...
    employee_count      integer,
    founded_year        integer,
    currencies          jsonb not null default '[]'::jsonb,
    languages           jsonb not null default '[]'::jsonb,
    status              text not null default 'discovered'
                        check (status in ('discovered','queued','crawling','crawled',
                                          'classified','rejected','error')),
    rejection_reason    text,                     -- §32: never reprocess blindly
    discovered_via      text,
    last_crawled_at     timestamptz,
    last_classified_at  timestamptz,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);
create index if not exists idx_companies_status  on companies(status);
create index if not exists idx_companies_country on companies(country);
create index if not exists idx_companies_name_trgm on companies using gin (name gin_trgm_ops);

-- ---------------------------------------------------------------------
-- EVIDENCE (§16, §29)
-- ---------------------------------------------------------------------
create table if not exists sources (
    id            uuid primary key default gen_random_uuid(),
    company_id    uuid not null references companies(id) on delete cascade,
    source_type   text not null
                  check (source_type in ('website','about','shipping','returns',
                        'careers','job','news','funding','crowdfunding',
                        'press_release','social','directory','registry','other')),
    url           text not null,
    title         text,
    content       text,
    excerpt       text,
    published_at  timestamptz,
    discovered_at timestamptz not null default now(),
    content_hash  text,
    http_status   integer,
    unique (company_id, url)
);
create index if not exists idx_sources_company on sources(company_id);
create index if not exists idx_sources_hash    on sources(content_hash);

create table if not exists crawl_jobs (
    id            uuid primary key default gen_random_uuid(),
    company_id    uuid not null references companies(id) on delete cascade,
    url           text not null,
    page_type     text,
    status        text not null default 'pending'
                  check (status in ('pending','processing','completed','failed','skipped')),
    http_status   integer,
    error         text,
    attempt_count integer not null default 0,
    started_at    timestamptz,
    completed_at  timestamptz,
    created_at    timestamptz not null default now()
);
create index if not exists idx_crawl_jobs_status on crawl_jobs(status);
create index if not exists idx_crawl_jobs_company on crawl_jobs(company_id);

-- ---------------------------------------------------------------------
-- SIGNALS (§18, §25) - service-scoped
-- ---------------------------------------------------------------------
create table if not exists signals (
    id           uuid primary key default gen_random_uuid(),
    company_id   uuid not null references companies(id) on delete cascade,
    service_id   uuid not null references services(id) on delete cascade,
    signal_type  text not null,
    strength     numeric(4,3) not null default 1.0,   -- 0..1 multiplier on weight
    description  text,
    evidence     text,                                 -- the quoted snippet
    source_id    uuid references sources(id) on delete set null,
    confidence   numeric(4,3) not null default 0.5,
    detected_at  timestamptz not null default now(),
    expires_at   timestamptz,
    created_at   timestamptz not null default now()
);
create index if not exists idx_signals_company_service on signals(company_id, service_id);
create index if not exists idx_signals_type on signals(signal_type);

-- ---------------------------------------------------------------------
-- OPPORTUNITIES (§19)
-- ---------------------------------------------------------------------
create table if not exists service_opportunities (
    id              uuid primary key default gen_random_uuid(),
    company_id      uuid not null references companies(id) on delete cascade,
    service_id      uuid not null references services(id) on delete cascade,
    score           numeric(5,2) not null default 0,
    raw_score       numeric(6,2) not null default 0,
    deterministic_score numeric(5,2) not null default 0,
    ai_score        numeric(5,2),
    evidence_score  numeric(5,2) not null default 0,
    score_breakdown jsonb not null default '[]'::jsonb,  -- §39 traceability
    intent_level    text not null default 'LOW'
                    check (intent_level in ('LOW','POSSIBLE','GOOD','STRONG','HOT')),
    urgency         text check (urgency in ('low','medium','high')),
    likely_need     jsonb not null default '[]'::jsonb,
    target_country  jsonb not null default '[]'::jsonb,
    reasoning       text,
    confidence      numeric(4,3),
    ai_analysis     jsonb,
    last_analyzed   timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),
    unique (company_id, service_id)                      -- §19, §51
);
create index if not exists idx_opps_score  on service_opportunities(score desc);
create index if not exists idx_opps_intent on service_opportunities(intent_level);

-- ---------------------------------------------------------------------
-- DECISION MAKERS (§20) - NO EMAIL FIELDS, BY DESIGN (§5, §35)
-- ---------------------------------------------------------------------
create table if not exists decision_makers (
    id            uuid primary key default gen_random_uuid(),
    company_id    uuid not null references companies(id) on delete cascade,
    name          text not null,
    job_title     text,
    profile_url   text,
    source        text,
    source_id     uuid references sources(id) on delete set null,
    confidence    numeric(4,3) not null default 0.5,
    confidence_label text check (confidence_label in ('confirmed','likely','possible')),
    role_priority integer not null default 50,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    unique (company_id, name, job_title)
);
create index if not exists idx_dm_company on decision_makers(company_id);

-- Right-to-object / erasure support (GDPR). Checked before any DM insert.
create table if not exists suppressions (
    id         uuid primary key default gen_random_uuid(),
    kind       text not null check (kind in ('domain','person')),
    value      text not null,
    reason     text,
    created_at timestamptz not null default now(),
    unique (kind, value)
);

-- ---------------------------------------------------------------------
-- OPS: caching, runs, metrics (§49, §56)
-- ---------------------------------------------------------------------
create table if not exists search_cache (
    id         uuid primary key default gen_random_uuid(),
    query_hash text not null unique,
    query      text not null,
    provider   text not null,
    results    jsonb not null,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null
);

create table if not exists pipeline_runs (
    id            uuid primary key default gen_random_uuid(),
    service_id    uuid references services(id) on delete set null,
    run_type      text not null,
    status        text not null default 'running',
    stats         jsonb not null default '{}'::jsonb,
    error         text,
    started_at    timestamptz not null default now(),
    completed_at  timestamptz
);

create table if not exists api_usage (
    id           uuid primary key default gen_random_uuid(),
    provider     text not null,
    operation    text not null,
    model        text,
    tokens_in    integer default 0,
    tokens_out   integer default 0,
    cost_usd     numeric(10,6) default 0,
    success      boolean not null default true,
    company_id   uuid references companies(id) on delete set null,
    created_at   timestamptz not null default now()
);
create index if not exists idx_api_usage_created on api_usage(created_at);

-- Human labels for §66 validation
create table if not exists lead_reviews (
    id             uuid primary key default gen_random_uuid(),
    opportunity_id uuid not null references service_opportunities(id) on delete cascade,
    label          text not null check (label in ('excellent','good','maybe','bad')),
    notes          text,
    reviewer       text,
    created_at     timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------
create or replace function set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end;
$$ language plpgsql;

do $$
declare t text;
begin
  foreach t in array array['services','service_signals','companies',
                           'service_opportunities','decision_makers']
  loop
    execute format(
      'drop trigger if exists trg_%1$s_updated on %1$s;
       create trigger trg_%1$s_updated before update on %1$s
       for each row execute function set_updated_at();', t);
  end loop;
end $$;

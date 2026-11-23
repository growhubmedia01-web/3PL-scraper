-- =====================================================================
--  ALL-IN-ONE MIGRATION
--  Configurable B2B Intent Intelligence Platform
--  Default service: pet_specialty_food_treats_supplements
--  Also seeded (active): powersports_aftermarket_sourcing
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
--          + 007_powersports_aftermarket_sourcing.sql + 008_source_types.sql
--          + 009_product_interest_attributes.sql
--          + 010_pet_specialty_food_treats_supplements.sql
--  (005_query_library.sql - the 8k-query legacy 3PL library - is optional
--   and run separately.)
--  Rebuild: python -m scripts.build_all_in_one
--  Generated 2026-11-23
-- =====================================================================



-- =====================================================================
--  PART 001  |  SCHEMA - tables, indexes, triggers
-- =====================================================================

-- =====================================================================
-- Configurable B2B Intent Intelligence Platform - Core Schema
-- Service-agnostic. Nothing in this file knows what "3PL" is.
-- Run in Supabase SQL Editor, or: psql "$DATABASE_MIGRATION_URL" -f 001_init.sql
-- =====================================================================

create extension if not exists "pgcrypto";
create extension if not exists "pg_trgm";

-- ---------------------------------------------------------------------
-- SERVICE CONFIGURATION (section 11, section 12, section 13, section 14)
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
-- GENERIC COMPANY INTELLIGENCE (section 15) - shared across all services
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
    rejection_reason    text,                     -- section 32: never reprocess blindly
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
-- EVIDENCE (section 16, section 29)
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
-- SIGNALS (section 18, section 25) - service-scoped
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
-- OPPORTUNITIES (section 19)
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
    score_breakdown jsonb not null default '[]'::jsonb,  -- section 39 traceability
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
    unique (company_id, service_id)                      -- section 19, section 51
);
create index if not exists idx_opps_score  on service_opportunities(score desc);
create index if not exists idx_opps_intent on service_opportunities(intent_level);

-- ---------------------------------------------------------------------
-- DECISION MAKERS (section 20) - NO EMAIL FIELDS, BY DESIGN (section 5, section 35)
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
-- OPS: caching, runs, metrics (section 49, section 56)
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

-- Human labels for section 66 validation
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


-- =====================================================================
--  PART 002  |  ROW LEVEL SECURITY - policies
-- =====================================================================

-- =====================================================================
-- Row Level Security (section 53)
-- Backend uses the service_role key and bypasses RLS.
-- The frontend uses the publishable/anon key and gets read-only access
-- to non-personal tables only. Decision makers stay server-side.
-- =====================================================================

alter table services              enable row level security;
alter table service_signals       enable row level security;
alter table service_keywords      enable row level security;
alter table discovery_queries     enable row level security;
alter table service_roles         enable row level security;
alter table companies             enable row level security;
alter table sources               enable row level security;
alter table crawl_jobs            enable row level security;
alter table signals               enable row level security;
alter table service_opportunities enable row level security;
alter table decision_makers       enable row level security;
alter table suppressions          enable row level security;
alter table search_cache          enable row level security;
alter table pipeline_runs         enable row level security;
alter table api_usage             enable row level security;
alter table lead_reviews          enable row level security;

-- Authenticated users may read the lead-facing tables.
do $$
declare t text;
begin
  foreach t in array array['services','service_signals','service_keywords',
                           'companies','sources','signals',
                           'service_opportunities','pipeline_runs']
  loop
    execute format(
      'drop policy if exists "auth_read_%1$s" on %1$s;
       create policy "auth_read_%1$s" on %1$s
       for select to authenticated using (true);', t);
  end loop;
end $$;

-- Decision makers contain personal data: read requires an authenticated
-- session, and rows for suppressed people/domains are filtered out.
drop policy if exists "auth_read_decision_makers" on decision_makers;
create policy "auth_read_decision_makers" on decision_makers
for select to authenticated
using (
  not exists (
    select 1 from suppressions s
    where (s.kind = 'person' and lower(s.value) = lower(decision_makers.name))
       or (s.kind = 'domain' and exists (
             select 1 from companies c
             where c.id = decision_makers.company_id
               and lower(c.domain) = lower(s.value)))
  )
);

-- Human review: authenticated users may label leads.
drop policy if exists "auth_write_lead_reviews" on lead_reviews;
create policy "auth_write_lead_reviews" on lead_reviews
for all to authenticated using (true) with check (true);

-- Everything else (crawl_jobs, api_usage, search_cache, suppressions,
-- discovery_queries, service_roles) has NO policy => service_role only.

-- Anonymous access is granted nowhere. Never expose the service_role key
-- to the browser.


-- =====================================================================
--  PART 003  |  SEED - the 3PL service configuration
-- =====================================================================

-- =====================================================================
-- 3PL SERVICE CONFIGURATION (section 21, section 24, section 26)
-- This is the ONLY file in the system that knows what 3PL is.
-- Adding a second service = adding another file like this one.
-- =====================================================================

insert into services (name, slug, description, status, config)
values (
  'Third Party Logistics', '3pl',
  'Find ecommerce and physical-product brands likely to need warehousing, order fulfillment and returns management.',
  'active',
  jsonb_build_object(
    'score_weights', jsonb_build_object(
        'deterministic', 0.5, 'ai', 0.3, 'evidence', 0.2),
    'intent_thresholds', jsonb_build_object(
        'LOW', 0, 'POSSIBLE', 31, 'GOOD', 51, 'STRONG', 71, 'HOT', 86),
    'normalization_ceiling', 100,
    'decision_maker_threshold', 80,
    'decision_maker_optional_threshold', 60,
    'ai_analysis_min_raw_score', 25,
    'required_signals', jsonb_build_array('physical_products'),
    'signal_page_affinity', jsonb_build_object(
        'existing_3pl', jsonb_build_array('shipping','returns','about','website','careers')),
    'query_exclusion_terms', jsonb_build_array(
        '3pl', 'fulfillment provider', 'fulfilment provider',
        'logistics provider', 'fulfillment company', 'warehousing company',
        'fulfillment service', 'agency', 'consultant'),
    'refresh_days', jsonb_build_object(
        'HOT', 3, 'STRONG', 7, 'GOOD', 30, 'POSSIBLE', 60, 'LOW', 180),
    'ai_system_prompt',
      'You are a B2B logistics analyst. Assess whether a company is likely to need third-party logistics (3PL) services: warehousing, order fulfillment, pick and pack, and returns management. Base every conclusion strictly on the supplied evidence. If the evidence does not support a conclusion, say so and lower your confidence. Never invent facts, names, or figures.'
  )
)
on conflict (slug) do update
  set config = excluded.config, description = excluded.description;

-- ---------------------------------------------------------------------
-- SIGNALS + WEIGHTS (section 24, section 26)
-- ---------------------------------------------------------------------
insert into service_signals
  (service_id, signal_type, signal_name, description, weight, decay_days, max_occurrences)
select s.id, v.signal_type, v.signal_name, v.description, v.weight, v.decay_days, v.max_occ
from services s,
(values
 ('ecommerce','Ecommerce','Sells online via a storefront platform or cart/checkout flow',8,null,1),
 ('physical_products','Physical Products','Ships tangible goods with SKUs, inventory and returns',10,null,1),
 ('new_store','New Store','Recently launched online store',10,365,1),
 ('international_shipping','International Shipping','States it ships beyond its home market',8,null,1),
 ('international_expansion','International Expansion','Announced entry into a new geographic market',15,270,2),
 ('recent_funding','Recent Funding','Raised capital recently; growth pressure on operations',12,540,2),
 ('product_launch','Product Launch','New product line, major launch or pre-orders',10,180,3),
 ('operations_hiring','Operations Hiring','Hiring ops/supply chain/logistics roles',15,120,3),
 ('fulfillment_hiring','Fulfillment Hiring','Hiring fulfillment/warehouse/distribution roles',20,120,3),
 ('crowdfunding','Crowdfunding','Running or recently funded a crowdfunding campaign',15,365,1),
 ('rapid_growth','Rapid Growth','Public evidence of fast growth in orders/headcount/revenue',10,270,1),
 ('existing_3pl','Existing 3PL','Already works with a fulfillment provider',-20,null,1)
) as v(signal_type, signal_name, description, weight, decay_days, max_occ)
where s.slug = '3pl'
on conflict (service_id, signal_type) do update
  set weight = excluded.weight,
      decay_days = excluded.decay_days,
      signal_name = excluded.signal_name,
      description = excluded.description;

-- ---------------------------------------------------------------------
-- KEYWORDS (section 13). A keyword alone must never qualify a company.
-- ---------------------------------------------------------------------
insert into service_keywords (service_id, keyword, category, signal_type, weight)
select s.id, v.keyword, v.category, v.signal_type, v.weight
from services s,
(values
 -- logistics vocabulary
 ('3pl','logistics','existing_3pl',1.0),
 ('third party logistics','logistics','existing_3pl',1.0),
 ('fulfillment partner','logistics','existing_3pl',1.0),
 ('fulfilment partner','logistics','existing_3pl',1.0),
 ('warehouse partner','logistics','existing_3pl',1.0),
 ('fulfilled by','logistics','existing_3pl',0.8),
 ('shipbob','logistics','existing_3pl',1.0),
 ('shipmonk','logistics','existing_3pl',1.0),
 ('deliverr','logistics','existing_3pl',1.0),
 ('huboo','logistics','existing_3pl',1.0),
 ('fulfillment by amazon','logistics','existing_3pl',0.9),
 ('fulfillment','logistics',null,0.6),
 ('warehouse','logistics',null,0.6),
 ('warehousing','logistics',null,0.6),
 ('distribution center','logistics',null,0.7),
 ('distribution centre','logistics',null,0.7),
 ('fulfillment center','logistics',null,0.7),
 ('pick and pack','logistics',null,0.8),
 ('order fulfillment','logistics',null,0.8),
 ('reverse logistics','logistics',null,0.8),
 ('inventory','logistics',null,0.4),
 -- physical product / ops
 ('sku','physical','physical_products',0.8),
 ('in stock','physical','physical_products',0.6),
 ('out of stock','physical','physical_products',0.7),
 ('free shipping','physical','physical_products',0.7),
 ('shipping policy','physical','physical_products',0.8),
 ('delivery times','physical','physical_products',0.6),
 ('return policy','physical','physical_products',0.7),
 ('returns','physical','physical_products',0.5),
 ('dispatch','physical','physical_products',0.6),
 ('tracking number','physical','physical_products',0.7),
 -- ecommerce
 ('add to cart','ecommerce','ecommerce',1.0),
 ('add to bag','ecommerce','ecommerce',1.0),
 ('checkout','ecommerce','ecommerce',0.8),
 ('shopping cart','ecommerce','ecommerce',0.9),
 ('shop now','ecommerce','ecommerce',0.6),
 ('my account','ecommerce','ecommerce',0.4),
 -- international
 ('ships worldwide','international','international_shipping',1.0),
 ('ship worldwide','international','international_shipping',1.0),
 ('we ship worldwide','international','international_shipping',1.0),
 ('ship internationally','international','international_shipping',1.0),
 ('shipping worldwide','international','international_shipping',1.0),
 ('worldwide shipping','international','international_shipping',1.0),
 ('international shipping','international','international_shipping',1.0),
 ('we ship internationally','international','international_shipping',1.0),
 ('ships to usa','international','international_shipping',0.9),
 ('ships to europe','international','international_shipping',0.9),
 ('global shipping','international','international_shipping',0.9),
 ('customs and duties','international','international_shipping',0.8),
 ('launching in the us','international','international_expansion',1.0),
 ('now available in the us','international','international_expansion',1.0),
 ('expanding into','international','international_expansion',1.0),
 ('entering the us market','international','international_expansion',1.0),
 ('opening our first us','international','international_expansion',1.0),
 ('new market','international','international_expansion',0.6),
 -- hiring
 ('operations manager','hiring','operations_hiring',1.0),
 ('head of operations','hiring','operations_hiring',1.0),
 ('supply chain manager','hiring','operations_hiring',1.0),
 ('logistics manager','hiring','operations_hiring',1.0),
 ('logistics coordinator','hiring','operations_hiring',0.8),
 ('inventory manager','hiring','operations_hiring',0.9),
 ('vp operations','hiring','operations_hiring',1.0),
 ('fulfillment manager','hiring','fulfillment_hiring',1.0),
 ('warehouse manager','hiring','fulfillment_hiring',1.0),
 ('warehouse associate','hiring','fulfillment_hiring',0.8),
 ('fulfillment operations','hiring','fulfillment_hiring',1.0),
 ('distribution manager','hiring','fulfillment_hiring',1.0),
 ('warehouse operative','hiring','fulfillment_hiring',0.8),
 -- funding / growth
 ('raised','funding','recent_funding',0.6),
 ('seed round','funding','recent_funding',1.0),
 ('series a','funding','recent_funding',1.0),
 ('series b','funding','recent_funding',1.0),
 ('pre-seed','funding','recent_funding',0.9),
 ('funding round','funding','recent_funding',1.0),
 ('secures investment','funding','recent_funding',0.9),
 ('kickstarter','crowdfunding','crowdfunding',1.0),
 ('indiegogo','crowdfunding','crowdfunding',1.0),
 ('backers','crowdfunding','crowdfunding',0.8),
 ('crowdfunding campaign','crowdfunding','crowdfunding',1.0),
 ('pre-order','launch','product_launch',0.8),
 ('preorder','launch','product_launch',0.8),
 ('new collection','launch','product_launch',0.7),
 ('now launching','launch','product_launch',0.7),
 ('introducing our new','launch','product_launch',0.7)
) as v(keyword, category, signal_type, weight)
where s.slug = '3pl'
on conflict (service_id, keyword, category) do update set weight = excluded.weight;

-- ---------------------------------------------------------------------
-- DISCOVERY QUERIES (section 14)
-- ---------------------------------------------------------------------
insert into discovery_queries (service_id, query, country, priority)
select s.id, v.query, v.country, v.priority
from services s,
(values
 ('new Shopify brand', null, 1),
 ('new ecommerce brand', null, 1),
 ('new DTC brand', null, 1),
 ('new consumer brand launch', null, 2),
 ('new physical product brand', null, 2),
 ('new online store launch', null, 3),
 ('ecommerce brand expanding internationally', null, 1),
 ('ecommerce company hiring operations manager', null, 1),
 ('DTC brand hiring fulfillment manager', null, 1),
 ('ecommerce brand raises seed funding', null, 2),
 ('DTC brand launching in the US', 'US', 1),
 ('UK ecommerce brand expanding to USA', 'GB', 1),
 ('Kickstarter product shipping to backers', null, 2),
 ('new Shopify store United Kingdom', 'GB', 3),
 ('new Shopify store Australia', 'AU', 3),
 -- broader physical product brands (non-ecommerce)
 ('new food and beverage brand launch', null, 1),
 ('new FMCG brand', null, 1),
 ('new consumer goods brand', null, 1),
 ('new CPG brand launch', null, 1),
 ('new beverage brand', null, 2),
 ('new snack brand launch', null, 2),
 ('new beauty brand launch', null, 2),
 ('new skincare brand launch', null, 2),
 ('new supplement brand', null, 2),
 ('new pet food brand', null, 2),
 ('new homeware brand launch', null, 2),
 ('new clothing brand launch', null, 2),
 ('new apparel brand', null, 2),
 ('physical product brand raising seed funding', null, 1),
 ('consumer goods company hiring operations manager', null, 1),
 ('wholesale brand expanding internationally', null, 2),
 ('new hardware product launch', null, 2),
 ('new electronics brand', null, 2)
) as v(query, country, priority)
where s.slug = '3pl'
  and not exists (                       -- idempotent: safe to re-run
    select 1 from discovery_queries dq
    where dq.service_id = s.id and dq.query = v.query);

-- ---------------------------------------------------------------------
-- DECISION MAKER ROLE PRIORITY (section 21)
-- ---------------------------------------------------------------------
insert into service_roles (service_id, title_pattern, role_priority)
select s.id, v.pattern, v.prio
from services s,
(values
 ('head of operations',1),('vp operations',1),('vp of operations',1),
 ('coo',2),('chief operating officer',2),
 ('operations director',3),('director of operations',3),
 ('operations manager',4),
 ('supply chain manager',5),('head of supply chain',5),('supply chain director',5),
 ('logistics manager',6),('head of logistics',6),
 ('fulfillment manager',7),('fulfilment manager',7),
 ('inventory manager',8),
 ('ecommerce director',9),('head of ecommerce',9),('director of ecommerce',9),
 ('founder',10),('co-founder',10),('cofounder',10),
 ('ceo',11),('chief executive officer',11),
 ('managing director',12),
 ('general manager',15)
) as v(pattern, prio)
where s.slug = '3pl'
on conflict (service_id, title_pattern) do update set role_priority = excluded.role_priority;


-- =====================================================================
--  PART 004  |  BROADEN - legacy 3PL wholesale, manufacturing, retail segments
-- =====================================================================

-- =====================================================================
-- 004  BROADEN BEYOND ECOMMERCE
--
-- 3PL customers are not only DTC brands. Wholesalers, manufacturers,
-- importers, retail/omnichannel brands and subscription businesses all
-- hold inventory and ship goods - often at higher volume than DTC.
--
-- Three changes:
--   1. required_signals drops 'ecommerce'. Physical goods is the gate;
--      selling online becomes a scoring bonus, not an entry requirement.
--   2. companies.business_model records what kind of company it is.
--   3. New signals, keywords and discovery queries for the new segments.
--
-- Idempotent. Safe to run on a database already seeded by 003.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. New column: what kind of business is this?
-- ---------------------------------------------------------------------
alter table companies
  add column if not exists business_model text;

alter table companies
  add column if not exists sales_channels jsonb not null default '[]'::jsonb;

create index if not exists idx_companies_business_model
  on companies(business_model);

-- ---------------------------------------------------------------------
-- 2. Requalify: physical products is the gate, not ecommerce
-- ---------------------------------------------------------------------
update services
set config = config
  || jsonb_build_object(
       'required_signals', jsonb_build_array('physical_products'),
       'normalization_ceiling', 110,
       'ai_system_prompt',
         'You are a B2B logistics analyst. Assess whether a company is likely '
         || 'to need third-party logistics (3PL) services: warehousing, order '
         || 'fulfillment, pick and pack, and returns management. Consider ALL '
         || 'companies that move physical goods - direct-to-consumer brands, '
         || 'wholesalers, distributors, importers, manufacturers, retail and '
         || 'omnichannel brands, marketplace sellers, and subscription '
         || 'businesses. A company does not need an online store to need a '
         || '3PL. Base every conclusion strictly on the supplied evidence. If '
         || 'the evidence does not support a conclusion, say so and lower your '
         || 'confidence. Never invent facts, names, or figures.',
       'signal_page_affinity', jsonb_build_object(
          'existing_3pl',      jsonb_build_array('shipping','returns','about','website','careers'),
          'wholesale_b2b',     jsonb_build_array('website','about','other','shipping'),
          'marketplace_seller',jsonb_build_array('website','about','other','shipping'),
          'retail_distribution', jsonb_build_array('website','about','other'),
          'subscription_model',jsonb_build_array('website','shipping','other'),
          'manufacturer',      jsonb_build_array('website','about'),
          'importer_exporter', jsonb_build_array('website','about','shipping'),
          'capacity_strain',   jsonb_build_array('news','website','about','shipping','careers'),
          'seeking_3pl',       jsonb_build_array('news','website','about','careers'),
          'warehouse_move',    jsonb_build_array('news','about','website','press_release'),
          'peak_season',       jsonb_build_array('news','website','careers')))
where slug = '3pl';

-- ---------------------------------------------------------------------
-- 3. New signals
-- ---------------------------------------------------------------------
insert into service_signals
  (service_id, signal_type, signal_name, description, weight, decay_days, max_occurrences)
select s.id, v.signal_type, v.signal_name, v.description, v.weight, v.decay_days, v.max_occ
from services s,
(values
 ('seeking_3pl','Actively Seeking 3PL','Publicly looking for a fulfillment partner - the strongest possible signal',25,180,1),
 ('capacity_strain','Capacity Strain','Outgrowing current space, backorders, or shipping delays',20,180,2),
 ('subscription_model','Subscription Model','Recurring shipments - predictable, high-volume fulfillment',15,null,1),
 ('warehouse_move','Warehouse Move','Relocating to or opening a larger facility',15,270,1),
 ('wholesale_b2b','Wholesale / B2B','Sells wholesale or trade with minimum order quantities',12,null,1),
 ('marketplace_seller','Marketplace Seller','Sells on Amazon, eBay, Etsy or similar - multi-channel fulfillment',12,null,1),
 ('retail_distribution','Retail Distribution','Stocked by physical retailers; needs retail-compliant fulfillment',12,null,1),
 ('importer_exporter','Importer / Exporter','Imports goods; container handling and customs needs',12,null,1),
 ('multi_channel','Multi-Channel','Sells through three or more channels',10,null,1),
 ('peak_season','Peak Season Pressure','Seasonal volume spikes needing flexible capacity',10,150,1),
 ('manufacturer','Manufacturer','Produces its own goods and holds finished inventory',8,null,1)
) as v(signal_type, signal_name, description, weight, decay_days, max_occ)
where s.slug = '3pl'
on conflict (service_id, signal_type) do update
  set weight = excluded.weight,
      decay_days = excluded.decay_days,
      signal_name = excluded.signal_name,
      description = excluded.description;

-- Ecommerce is now a bonus rather than a gate; nudge its weight down a
-- little so it does not dominate the non-DTC segments.
update service_signals set weight = 8
where signal_type = 'ecommerce'
  and service_id = (select id from services where slug = '3pl');

-- ---------------------------------------------------------------------
-- 4. Keywords for the new segments
-- ---------------------------------------------------------------------
insert into service_keywords (service_id, keyword, category, signal_type, weight)
select s.id, v.keyword, v.category, v.signal_type, v.weight
from services s,
(values
 -- ---- actively seeking a 3PL (highest intent) ----
 ('looking for a 3pl','intent','seeking_3pl',1.0),
 ('looking for a fulfillment partner','intent','seeking_3pl',1.0),
 ('seeking fulfillment partner','intent','seeking_3pl',1.0),
 ('request for quote fulfillment','intent','seeking_3pl',1.0),
 ('fulfillment rfp','intent','seeking_3pl',1.0),
 ('outsourcing our fulfillment','intent','seeking_3pl',1.0),
 ('outsource fulfilment','intent','seeking_3pl',1.0),
 ('third party logistics provider','intent','seeking_3pl',0.9),
 -- ---- capacity strain ----
 ('outgrowing our warehouse','capacity','capacity_strain',1.0),
 ('running out of warehouse space','capacity','capacity_strain',1.0),
 ('outgrown our current space','capacity','capacity_strain',1.0),
 ('at capacity','capacity','capacity_strain',0.7),
 ('shipping delays','capacity','capacity_strain',0.8),
 ('dispatch delays','capacity','capacity_strain',0.8),
 ('on backorder','capacity','capacity_strain',0.8),
 ('back in stock soon','capacity','capacity_strain',0.6),
 ('order backlog','capacity','capacity_strain',0.9),
 ('longer than usual','capacity','capacity_strain',0.6),
 -- ---- warehouse move ----
 ('new warehouse','facility','warehouse_move',0.9),
 ('moving to a larger facility','facility','warehouse_move',1.0),
 ('new distribution centre','facility','warehouse_move',1.0),
 ('new distribution center','facility','warehouse_move',1.0),
 ('opening a new facility','facility','warehouse_move',0.9),
 ('relocating our operations','facility','warehouse_move',0.9),
 -- ---- wholesale / B2B ----
 ('wholesale','wholesale','wholesale_b2b',0.8),
 ('wholesale enquiries','wholesale','wholesale_b2b',1.0),
 ('wholesale inquiries','wholesale','wholesale_b2b',1.0),
 ('trade account','wholesale','wholesale_b2b',1.0),
 ('trade customers','wholesale','wholesale_b2b',1.0),
 ('become a stockist','wholesale','wholesale_b2b',1.0),
 ('become a retailer','wholesale','wholesale_b2b',0.9),
 ('minimum order quantity','wholesale','wholesale_b2b',1.0),
 ('moq','wholesale','wholesale_b2b',0.9),
 ('bulk orders','wholesale','wholesale_b2b',0.9),
 ('trade pricing','wholesale','wholesale_b2b',1.0),
 ('wholesale price list','wholesale','wholesale_b2b',1.0),
 ('b2b portal','wholesale','wholesale_b2b',0.9),
 -- ---- marketplace ----
 ('available on amazon','marketplace','marketplace_seller',1.0),
 ('shop on amazon','marketplace','marketplace_seller',0.9),
 ('amazon store','marketplace','marketplace_seller',0.9),
 ('our ebay shop','marketplace','marketplace_seller',1.0),
 ('etsy shop','marketplace','marketplace_seller',0.9),
 ('walmart marketplace','marketplace','marketplace_seller',1.0),
 ('seller central','marketplace','marketplace_seller',0.9),
 ('fba','marketplace','marketplace_seller',0.7),
 -- ---- retail distribution ----
 ('stockists','retail','retail_distribution',1.0),
 ('find a stockist','retail','retail_distribution',1.0),
 ('where to buy','retail','retail_distribution',0.9),
 ('available in store','retail','retail_distribution',0.9),
 ('our retail partners','retail','retail_distribution',1.0),
 ('now in selfridges','retail','retail_distribution',0.8),
 ('stocked in','retail','retail_distribution',0.7),
 ('retail partners','retail','retail_distribution',0.9),
 -- ---- subscription ----
 ('subscription box','subscription','subscription_model',1.0),
 ('monthly subscription','subscription','subscription_model',0.9),
 ('subscribe and save','subscription','subscription_model',0.9),
 ('recurring delivery','subscription','subscription_model',1.0),
 ('meal kit','subscription','subscription_model',1.0),
 ('delivered monthly','subscription','subscription_model',0.9),
 ('cancel anytime','subscription','subscription_model',0.6),
 -- ---- manufacturing ----
 ('our factory','manufacturing','manufacturer',1.0),
 ('manufactured in','manufacturing','manufacturer',0.8),
 ('we manufacture','manufacturing','manufacturer',1.0),
 ('our production facility','manufacturing','manufacturer',1.0),
 ('private label','manufacturing','manufacturer',0.9),
 ('white label','manufacturing','manufacturer',0.8),
 ('contract manufacturing','manufacturing','manufacturer',1.0),
 ('made in our workshop','manufacturing','manufacturer',0.9),
 -- ---- import / export ----
 ('imported from','import','importer_exporter',0.8),
 ('we import','import','importer_exporter',1.0),
 ('customs clearance','import','importer_exporter',0.9),
 ('container shipments','import','importer_exporter',1.0),
 ('freight forwarding','import','importer_exporter',0.8),
 ('incoterms','import','importer_exporter',0.9),
 ('duty paid','import','importer_exporter',0.7),
 -- ---- peak season ----
 ('black friday','seasonal','peak_season',0.7),
 ('holiday shipping deadline','seasonal','peak_season',0.9),
 ('christmas delivery cut off','seasonal','peak_season',0.9),
 ('peak season','seasonal','peak_season',0.8),
 ('seasonal demand','seasonal','peak_season',0.8)
) as v(keyword, category, signal_type, weight)
where s.slug = '3pl'
on conflict (service_id, keyword, category) do update set weight = excluded.weight;

-- ---------------------------------------------------------------------
-- 5. Discovery queries for the new segments
-- ---------------------------------------------------------------------
insert into discovery_queries (service_id, query, country, priority)
select s.id, v.query, v.country, v.priority
from services s,
(values
 -- highest intent: they are already shopping for this
 ('"looking for a 3PL" brand', null, 1),
 ('"looking for a fulfillment partner"', null, 1),
 ('brand "outgrowing our warehouse"', null, 1),
 ('ecommerce brand "outsourcing fulfillment"', null, 1),
 -- wholesale / distribution
 ('wholesale supplier "trade accounts" new brand', null, 2),
 ('"become a stockist" new brand', null, 2),
 ('"minimum order quantity" wholesale brand launch', null, 3),
 ('B2B wholesale brand expanding distribution', null, 2),
 ('distributor "now distributing" consumer products', null, 3),
 ('importer "we import" consumer goods company', null, 3),
 -- manufacturing / CPG
 ('CPG brand launch new product line', null, 2),
 ('food and beverage brand national rollout', null, 2),
 ('cosmetics brand "our factory" expanding', null, 3),
 ('private label manufacturer consumer goods', null, 3),
 ('drinks brand expanding production', null, 3),
 ('supplement brand scaling production', null, 3),
 -- retail / omnichannel
 ('brand "now available in" retailer nationwide', null, 2),
 ('brand launches in Target OR Walmart OR Whole Foods', 'US', 2),
 ('brand "now in" Selfridges OR John Lewis OR Boots', 'GB', 2),
 ('"find a stockist" brand new retail partners', null, 3),
 ('omnichannel brand expanding retail distribution', null, 2),
 ('Amazon seller brand scaling operations', null, 2),
 ('marketplace seller expanding to new channels', null, 3),
 -- subscription
 ('subscription box company launch', null, 2),
 ('meal kit company expanding delivery area', null, 2),
 ('subscription brand raises funding', null, 2),
 ('"subscribe and save" brand growth', null, 3),
 -- capacity / operations pressure
 ('brand "new distribution centre" opening', null, 2),
 ('brand "moving to a larger facility"', null, 2),
 ('company hiring warehouse manager new facility', null, 1),
 ('brand "shipping delays" apology growth', null, 3),
 -- crowdfunding fulfilment waves
 ('Kickstarter project shipping rewards to backers', null, 2),
 ('Indiegogo campaign fulfilment update', null, 3)
) as v(query, country, priority)
where s.slug = '3pl'
  and not exists (
    select 1 from discovery_queries dq
    where dq.service_id = s.id and dq.query = v.query);


-- =====================================================================
--  PART 006  |  SCHEMA - company LinkedIn URL columns
-- =====================================================================

-- =====================================================================
-- 006  COMPANY LINKEDIN URL RESOLUTION
--
-- Two-tier resolution, no LinkedIn scraping involved:
--   tier 1 - free: schema.org sameAs links and on-page external links
--            already captured during the normal site crawl.
--   tier 2 - fallback: one cached search-engine query via the existing
--            SearchProvider abstraction, only when tier 1 finds nothing.
--
-- linkedin_checked_at doubles as the "tier 2 already attempted" marker so
-- re-processing a company never repeats a search call.
--
-- Idempotent. Safe to run on a database already seeded by 001-005.
-- =====================================================================

alter table companies
  add column if not exists linkedin_url text;

alter table companies
  add column if not exists linkedin_source text;

alter table companies
  add column if not exists linkedin_checked_at timestamptz;


-- =====================================================================
--  PART 007  |  SEED - Powersports Aftermarket Product Sourcing (default service)
-- =====================================================================

-- =====================================================================
-- 007  POWERSPORTS AFTERMARKET PRODUCT SOURCING
--
-- Service slug: powersports_aftermarket_sourcing
-- New default service. Additive and idempotent: safe to re-run, safe on a
-- database seeded by 001-006. Deletes nothing. The legacy '3pl' service is
-- set inactive and keeps every signal, keyword, query, opportunity and
-- review it ever produced.
--
-- GENERATED FILE - do not edit directly.
-- Source: scripts/services/powersports_aftermarket_sourcing.py
-- Rebuild: python -m scripts.build_service_seed powersports_aftermarket_sourcing
-- =====================================================================

-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- 2. SERVICE
-- ---------------------------------------------------------------------
insert into services (name, slug, description, status, config)
values (
  'Powersports Aftermarket Product Sourcing', 'powersports_aftermarket_sourcing',
  'Find mid-market US wholesale distributors of aftermarket powersports parts and accessories that show public, evidenced intent to source new products, onboard new brands or expand categories - and which products they may be looking to buy.',
  'active',
  '{"adjacent_categories": {"ATV/UTV/Side-by-Side Accessories": ["Tires and Wheels", "Electrical and Performance"], "Electrical and Performance": ["Maintenance and Consumables"], "Maintenance and Consumables": ["Electrical and Performance"], "Motorcycle Aftermarket Accessories": ["Riding Gear and Protection", "Electrical and Performance"], "Riding Gear and Protection": ["Motorcycle Aftermarket Accessories"], "Tires and Wheels": ["ATV/UTV/Side-by-Side Accessories", "Maintenance and Consumables"]}, "ai_analysis_min_raw_score": 20, "ai_extra_fields": {"company_size_qualification": "\"mid_market\" | \"small\" | \"micro\" | \"large\" | \"unknown\" - never guess", "distribution_partnerships": "[string] - brands named in the evidence", "distributor_qualification": "\"qualified\" | \"possible\" | \"not_qualified\" | \"unknown\"", "distributor_qualification_reason": "string citing evidence", "likely_decision_roles": "[string] - job titles, never personal contact data", "product_categories": "[string] - only categories named in the evidence", "products_mentioned": "[string] - only products named in the evidence", "recent_expansion_activity": "[string]", "strongest_buying_signals": "[string]", "supplier_onboarding_evidence": "[string]"}, "ai_grounded_fields": ["likely_services", "product_categories", "products_mentioned", "distribution_partnerships"], "ai_probability_field": "buying_intent_probability", "ai_system_prompt": "You are a B2B supply-chain analyst for manufacturers that want to sell aftermarket powersports products through US distributors. You assess whether a company is a suitable US powersports aftermarket wholesale distributor and what public evidence shows it is currently seeking, purchasing, onboarding or expanding aftermarket product categories and supplier relationships. Commercial direction matters: a distributor recruiting dealers is selling, not buying; a manufacturer seeking a distributor is the opposite direction and is not a buyer. Base every conclusion strictly on the supplied evidence. Never invent products, brands, purchasing requirements, employee counts or revenue. A general growth announcement is not a specific purchasing requirement.", "ai_task": "Is this company a suitable US powersports aftermarket distributor, and what public evidence indicates that it is currently seeking, purchasing, onboarding or expanding aftermarket product categories and supplier relationships? Put the probability that it is actively expanding its supplier or product portfolio in service_probability. Put only product categories named in the evidence in likely_services. If no specific product requirement is identifiable, say exactly: Specific product demand not publicly disclosed.", "brand_patterns": ["distribution (?:agreement|partnership|deal) with ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:exclusive|official|authorized|master) (?:US |U\\.S\\. |North American |national )?distributor (?:of|for) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:now|will) (?:distribute|distributing|carry|carrying|stock|stocking) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:added|adds|adding|welcomes|welcomed) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3}) (?:to (?:its|our|the) (?:lineup|line card|brand portfolio|portfolio|catalog|offering))", "partner(?:ed|ship)? with ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})"], "carried_page_types": ["brands", "website", "about", "other"], "company_type_markers": {"brand_owner": ["find a dealer", "dealer locator", "where to buy", "become a distributor", "distributor inquiries", "our products are sold through", "distributors wanted", "looking for distributors"], "dealer_retailer": ["visit our showroom", "new and used", "pre-owned inventory", "schedule a test ride", "showroom hours", "browse our inventory", "used inventory", "value your trade", "financing available", "new inventory", "in-stock units", "our dealership"], "importer": ["we import", "importer of", "exclusive importer", "import and distribute", "importer and distributor", "direct importer"], "manufacturer": ["we manufacture", "our factory", "manufactured in", "designed and manufactured", "engineered and manufactured", "our manufacturing facility", "manufacturing facility", "made in usa", "made in the usa", "in-house manufacturing", "we design and build"], "service_provider": ["schedule service", "service appointment", "repair shop", "our service department", "we repair", "service specials", "our technicians", "marketing agency", "digital agency"], "wholesale_distributor": ["wholesale distributor", "wholesale distribution", "distributor of", "we distribute", "master distributor", "dealer network", "authorized dealers", "independent dealers", "dealer portal", "dealer login", "dealer pricing", "serving dealers", "dealer support", "line card", "linecard", "brands we carry", "brands we distribute", "distribution centers", "distribution center", "wholesale only", "dealers only", "trade only", "become a dealer", "dealer application", "b2b", "distribution partner"]}, "crawl_link_first_page_types": ["supplier", "brands", "news", "careers", "dealer", "about"], "crawl_max_pages": 16, "crawl_priority_paths": [["/", "website"], ["/about", "about"], ["/about-us", "about"], ["/brands", "brands"], ["/our-brands", "brands"], ["/line-card", "brands"], ["/vendors", "supplier"], ["/suppliers", "supplier"], ["/vendor-application", "supplier"], ["/become-a-vendor", "supplier"], ["/news", "news"], ["/press", "news"], ["/careers", "careers"], ["/dealers", "dealer"], ["/become-a-dealer", "dealer"], ["/contact", "other"]], "decision_maker_optional_threshold": 30, "decision_maker_threshold": 40, "dimension_caps": {"intent": 40}, "discovery_blocked_domains": ["powersportsbusiness.com", "aimexpousa.com", "mic.org", "dealernews.com", "motorcycle.com", "cycleworld.com", "atv.com", "utvdriver.com", "utvactionmag.com", "dirtrider.com", "motorcyclistonline.com", "thomasnet.com", "zoominfo.com", "dnb.com", "manta.com", "bbb.org", "yellowpages.com", "mapquest.com", "rocketreach.co", "apollo.io", "craigslist.org", "cycletrader.com", "atvtrader.com", "revzilla.com", "rockymountainatvmc.com", "partzilla.com", "denniskirk.com", "cyclegear.com", "motosport.com", "jdpower.com", "kbb.com", "nadaguides.com", "facebook.com", "linkedin.com", "youtube.com"], "exclude_logistics_providers": false, "excluded_business_types": ["marketing agency", "seo agency", "web development agency", "digital agency", "software company", "saas platform", "consulting firm", "law firm", "recruitment agency", "staffing agency", "insurance agency", "trade publication"], "external_fetchers": ["ats"], "external_query_templates": [["press_release", "\"{name}\" \"distribution agreement\" OR \"now distributing\" OR \"exclusive distributor\" OR \"partnership\"", "news"], ["press_release", "\"{name}\" \"new brands\" OR \"new product lines\" OR \"product line expansion\" OR \"adds\"", "news"], ["news", "\"{name}\" powersports site:powersportsbusiness.com OR site:aimexpousa.com OR site:dealernews.com", "web"], ["supplier", "\"{name}\" \"vendor application\" OR \"supplier application\" OR \"new vendor\" OR \"submit your products\"", "web"], ["job", "\"{name}\" \"purchasing manager\" OR \"category manager\" OR \"buyer\" OR \"procurement\"", "web"], ["press_release", "\"{name}\" \"distribution center\" OR warehouse OR acquires OR acquisition", "news"]], "fetch_external_articles": 3, "fit_multipliers": {"company_type": {"default": 0.5, "hybrid_distributor_dealer": 0.85, "hybrid_distributor_manufacturer": 0.95, "importer": 0.9, "unknown": 0.75, "wholesale_distributor": 1.0}, "employee_band": {"large": 0.7, "micro": 0.55, "mid_market": 1.0, "small": 0.85, "unknown": 0.8}}, "hybrid_company_types": {"hybrid_distributor_dealer": ["wholesale_distributor", "dealer_retailer"], "hybrid_distributor_manufacturer": ["wholesale_distributor", "manufacturer"]}, "industry_keywords": {"powersports": ["powersports", "power sports", "atv", "utv", "side-by-side", "side by side", "sxs", "motorcycle", "motorcycles", "dirt bike", "motocross", "snowmobile", "v-twin", "off-road vehicle", "aftermarket parts", "dual sport", "adventure touring", "sled", "personal watercraft", "pwc", "jet ski", "harley-davidson", "dirtbike", "quad bike", "can-am", "polaris", "sea-doo", "ski-doo", "arctic cat"]}, "intent_thresholds": {"GOOD": 51, "HOT": 86, "LOW": 0, "POSSIBLE": 31, "STRONG": 71}, "interest_type_by_signal": {"active_product_rfq": "EXPLICITLY_SEEKING", "catalog_or_linecard_expansion": "RECENTLY_ADDED", "explicit_supplier_search": "EXPLICITLY_SEEKING", "new_brand_added": "RECENTLY_ADDED", "new_distribution_partnership": "RECENTLY_ADDED", "new_product_line_launch": "RECENTLY_ADDED", "product_category_expansion": "RECENTLY_ADDED", "supplier_application_open": "EXPLICITLY_SEEKING"}, "no_product_demand_message": "Specific product demand not publicly disclosed.", "normalization_ceiling": 90, "product_taxonomy": {"ATV/UTV/Side-by-Side Accessories": {"Bumpers": ["front bumper", "rear bumper", "bumper"], "Cab Enclosures": ["cab enclosure", "cab enclosures", "cab heater", "rear window"], "Cargo Racks": ["cargo rack", "cargo box", "rack extender"], "Doors and Door Panels": ["utv door", "door panel", "upper door", "lower door", "suicide door"], "Grilles": ["grille", "grill guard", "brush guard"], "Lighting Systems": ["light bar", "whip light", "rock light", "pod light", "utv lighting"], "Mirrors": ["side mirror", "rear view mirror", "rearview mirror", "utv mirror"], "Recovery Accessories": ["recovery strap", "recovery kit", "tow strap", "traction board", "snatch block"], "Rock Sliders": ["rock slider", "rock sliders", "nerf bar"], "Roof Racks": ["roof rack"], "Roof Systems": ["roof system", "utv roof", "hard top", "soft top"], "Skid Plates": ["skid plate", "skid plates", "belly pan"], "Storage Systems": ["storage bag", "storage system", "under-seat storage", "dash storage"], "Tire Carriers": ["tire carrier", "spare tire carrier", "spare tire mount"], "Winches": ["winch", "winches", "winch mount", "synthetic rope"], "Windshield Wipers": ["windshield wiper", "wiper kit"], "Windshields": ["windshield", "windscreen", "half windshield", "full windshield"]}, "Electrical and Performance": {"Batteries": ["battery", "batteries", "lithium battery", "agm battery"], "Brake Components": ["brake pad", "brake rotor", "brake line", "brake caliper"], "Charging Systems": ["battery charger", "battery tender", "charging system", "stator"], "EFI Components": ["efi", "fuel injector", "throttle body"], "Electrical Accessories": ["electrical accessories", "usb charger", "power outlet", "switch panel"], "Engine Upgrades": ["big bore kit", "engine upgrade", "cam kit", "turbo kit", "clutch kit"], "Exhaust Systems": ["exhaust system", "slip-on exhaust", "full exhaust", "muffler"], "LED Lighting": ["led lighting", "led headlight", "led light"], "Performance Tuners": ["fuel programmer", "performance tuner", "ecu flash", "fuel controller"], "Suspension Components": ["suspension", "shock absorber", "shocks", "lift kit", "a-arm", "fork spring"], "Tire Balancing Products": ["tire balancing", "balance beads", "wheel weight"], "Wiring Harnesses": ["wiring harness", "wire harness"]}, "Maintenance and Consumables": {"Chains": ["drive chain", "motorcycle chain", "o-ring chain", "x-ring chain"], "Chemicals": ["chemicals", "fuel stabilizer", "coolant", "brake fluid"], "Cleaning Products": ["cleaning products", "bike wash", "degreaser", "detailing"], "Engine Oils": ["engine oil", "motor oil", "4-stroke oil", "2-stroke oil"], "Filters": ["oil filter", "air filter", "fuel filter"], "Lubricants": ["lubricant", "lubricants", "chain lube", "grease"], "Maintenance Kits": ["maintenance kit", "service kit", "tune-up kit"], "Sprockets": ["sprocket", "sprockets"], "Workshop Consumables": ["shop supplies", "workshop consumables", "zip ties", "shop towels"]}, "Motorcycle Aftermarket Accessories": {"Adventure Touring Products": ["adventure touring", "adv accessories", "adventure bike"], "Crash Bars": ["crash bar"], "Crash Protection": ["crash protection", "engine guard", "highway bar"], "Frame Sliders": ["frame slider", "crash slider", "axle slider"], "Handguards": ["handguard", "hand guard"], "Motorcycle Racks": ["luggage rack", "motorcycle rack", "sissy bar"], "Panniers": ["pannier"], "Saddlebags": ["saddlebag", "saddle bag"], "Styling Accessories": ["motorcycle styling", "chrome accessories", "custom grips", "foot pegs", "billet accessories"], "Top Cases": ["top case", "top box"], "Touring Luggage": ["touring luggage", "motorcycle luggage", "tail bag", "tank bag"], "Windscreens": ["motorcycle windscreen", "fairing", "wind deflector"]}, "Riding Gear and Protection": {"Body Armour": ["body armor", "body armour", "chest protector", "roost guard"], "Boots": ["riding boots", "motorcycle boots", "mx boots", "motocross boots"], "Casual Riding Apparel": ["casual apparel", "riding apparel", "moto apparel", "lifestyle apparel"], "Gloves": ["riding gloves", "motorcycle gloves", "mx gloves"], "Goggles": ["goggle", "goggles"], "Helmets": ["helmet", "helmets"], "Jackets": ["riding jacket", "motorcycle jacket"], "Jerseys": ["jersey", "jerseys"], "Knee Protection": ["knee brace", "knee guard", "knee protection"], "Motocross Apparel": ["motocross apparel", "mx apparel", "mx gear", "motocross gear"], "Neck Protection": ["neck brace", "neck protection"], "Riding Pants": ["riding pants", "mx pants", "motocross pants"], "Snowmobile Apparel": ["snowmobile apparel", "snowmobile jacket", "snowmobile bib", "monosuit"]}, "Tires and Wheels": {"ATV Tires": ["atv tire"], "Motorcycle Tires": ["motorcycle tire", "dirt bike tire", "street tire", "dual sport tire"], "Off-Road Tires": ["off-road tire", "mud tire", "all-terrain tire"], "Performance Wheels": ["performance wheel", "forged wheel", "cast wheel", "spoked wheel"], "Specialty Wheels": ["beadlock wheel", "specialty wheel", "atv wheel", "utv wheel"], "Tire and Wheel Systems": ["tire and wheel kit", "wheel and tire package", "mounted tire", "tire and wheel package"], "UTV Tires": ["utv tire", "side-by-side tire", "sxs tire"]}}, "qualification": {"allow_unverified_location_tlds": ["com", "net", "us", "org", "biz"], "allowed_countries": ["US"], "company_type_min_markers": 2, "eligible_company_types": ["wholesale_distributor", "importer", "hybrid_distributor_manufacturer", "hybrid_distributor_dealer"], "excluded_employee_bands": ["large", "small", "micro"], "industry_implies_physical": true, "min_country_confidence": 0.6, "min_industry_markers": 1, "reject_company_types": ["dealer_retailer", "service_provider", "manufacturer", "brand_owner"], "require_country_evidence": true, "required_industry": "powersports", "unknown_company_type": "allow"}, "query_exclusion_terms": ["for sale", "rental", "rentals"], "refresh_days": {"GOOD": 30, "HOT": 7, "LOW": 120, "POSSIBLE": 60, "STRONG": 14}, "required_signals": ["powersports_participation"], "score_weights": {"ai": 0.3, "deterministic": 0.5, "evidence": 0.2}, "signal_dimensions": {"b2b_dealer_distribution": "fit", "manufacturer_seeking_distribution": "negative", "powersports_participation": "fit", "retail_only_operation": "negative", "service_repair_operation": "negative"}, "signal_page_affinity": {"acquisition_or_distribution_expansion": ["news", "press_release", "about"], "active_product_rfq": ["supplier", "news", "press_release", "website", "other"], "catalog_or_linecard_expansion": ["brands", "website", "news", "press_release"], "category_buyer_hiring": ["careers", "job"], "dealer_network_expansion": ["news", "press_release", "about", "website", "dealer"], "distribution_center_expansion": ["news", "press_release", "about", "website"], "explicit_supplier_search": ["supplier", "news", "press_release", "website", "about", "other"], "new_brand_added": ["news", "press_release", "brands", "website"], "new_distribution_partnership": ["news", "press_release", "website", "brands", "about"], "new_product_line_launch": ["news", "press_release", "website", "brands"], "procurement_hiring": ["careers", "job"], "product_category_expansion": ["news", "press_release", "website", "brands"], "supplier_application_open": ["supplier", "website", "other", "about"]}, "signal_rules": {"acquisition_or_distribution_expansion": {"require_context_phrases": ["distributor", "distribution", "distributing", "aftermarket", "powersports", "parts", "accessories"]}, "active_product_rfq": {"exclude_page_types": ["dealer"], "require_context_phrases": ["supplier", "suppliers", "manufacturer", "manufacturers", "vendor", "vendors", "factory", "factories", "source", "sourcing", "brands"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "seeking a us distributor", "looking for a us distributor", "distributors wanted", "become a dealer", "become an authorized dealer", "dealer application", "dealer account", "open a dealer account", "wholesale account application", "apply for a dealer", "get a quote", "your quote", "your order", "our customers", "for dealers", "dealer quote"]}, "catalog_or_linecard_expansion": {"require_context_phrases": ["new", "added", "adds", "expanded", "expands", "expansion", "now includes", "additional"]}, "category_buyer_hiring": {"require_page_types": ["careers", "job"]}, "explicit_supplier_search": {"exclude_page_types": ["dealer"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "seeking a us distributor", "looking for a us distributor", "distributors wanted", "become a dealer", "become an authorized dealer", "dealer application", "dealer account", "open a dealer account", "wholesale account application", "apply for a dealer"]}, "new_brand_added": {"exclude_page_types": ["dealer"], "suppress_phrases": ["looking for", "seeking", "submit", "interested in", "our new brand identity", "looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "seeking a us distributor", "looking for a us distributor", "distributors wanted"]}, "new_distribution_partnership": {"require_context_phrases": ["distribute", "distribution", "distributor", "distributing", "brand", "brands", "product line", "products", "dealers", "aftermarket", "accessories", "parts"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "seeking a us distributor", "looking for a us distributor", "distributors wanted"]}, "new_product_line_launch": {"require_context_phrases": ["powersports", "power sports", "atv", "utv", "side-by-side", "side by side", "sxs", "motorcycle", "motorcycles", "dirt bike", "motocross", "snowmobile", "off-road", "offroad", "aftermarket", "v-twin", "moto"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "seeking a us distributor", "looking for a us distributor", "distributors wanted"]}, "procurement_hiring": {"require_page_types": ["careers", "job"]}, "product_category_expansion": {"require_context_phrases": ["powersports", "power sports", "atv", "utv", "side-by-side", "side by side", "sxs", "motorcycle", "motorcycles", "dirt bike", "motocross", "snowmobile", "off-road", "offroad", "aftermarket", "v-twin", "moto"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "seeking a us distributor", "looking for a us distributor", "distributors wanted"]}, "supplier_application_open": {"exclude_page_types": ["dealer"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "seeking a us distributor", "looking for a us distributor", "distributors wanted", "become a dealer", "become an authorized dealer", "dealer application", "dealer account", "open a dealer account", "wholesale account application", "apply for a dealer"]}}, "size_bands": [{"band": "micro", "max": 10, "min": 1}, {"band": "small", "max": 49, "min": 11}, {"band": "mid_market", "max": 500, "min": 50}, {"band": "large", "max": null, "min": 501}], "undated_confidence_factor": 0.75, "vehicle_platforms": ["Polaris", "Can-Am", "CFMOTO", "Kawasaki", "Yamaha", "Honda", "Suzuki", "KTM", "Harley-Davidson", "Arctic Cat", "Ski-Doo", "BRP", "Textron", "Segway Powersports", "Husqvarna", "GasGas", "Ducati", "BMW Motorrad", "Triumph", "Indian Motorcycle", "Hisun", "Kymco", "Massimo", "RZR", "Ranger", "Maverick", "Defender", "Talon", "Pioneer", "Teryx", "Wolverine"], "vehicle_segments": {"ATV": ["atv", "atvs", "quad", "four wheeler"], "Motorcycle - Adventure": ["adventure bike", "adventure touring", "dual sport"], "Motorcycle - Off-Road/Motocross": ["motocross", "dirt bike", "mx", "enduro", "off-road motorcycle"], "Motorcycle - Street/Touring": ["touring", "cruiser", "street bike", "sportbike", "bagger"], "Snowmobile": ["snowmobile", "snowmobiles", "sled", "sleds"], "UTV/Side-by-Side": ["utv", "utvs", "side-by-side", "side by side", "sxs"]}}'::jsonb
)
on conflict (slug) do update
  set name = excluded.name, description = excluded.description,
      config = excluded.config, status = 'active';

-- Retain, do not delete, the legacy service.
update services set status = 'inactive' where slug = '3pl';

-- ---------------------------------------------------------------------
-- 3. SIGNALS + WEIGHTS  (18)
-- ---------------------------------------------------------------------
insert into service_signals
  (service_id, signal_type, signal_name, description, weight, decay_days, max_occurrences)
select s.id, v.signal_type, v.signal_name, v.description, v.weight, v.decay_days, v.max_occ
from services s,
(values
 ('active_product_rfq','Active Product RFQ','Public request for quotes or a specific product requirement directed at suppliers',35,90,1),
 ('explicit_supplier_search','Explicit Supplier Search','Distributor explicitly asks for new suppliers, manufacturers, products or brands',30,120,1),
 ('supplier_application_open','Supplier Application Open','A genuine supplier or vendor submission process exists. Proves openness to proposals, not an active sourcing project. Revalidated every 180 days by re-crawl',22,180,1),
 ('new_distribution_partnership','New Distribution Partnership','Newly signed distribution agreement with a manufacturer or brand',27,180,1),
 ('new_brand_added','New Brand Added','A new aftermarket brand was added to the distributor portfolio',25,180,1),
 ('product_category_expansion','Product Category Expansion','Expansion into a new product category or a material range increase',23,180,1),
 ('new_product_line_launch','New Product Line Launch','Upcoming or recently launched product lines',18,150,1),
 ('catalog_or_linecard_expansion','Catalog or Line Card Expansion','Material category or brand expansion in the current catalog or line card',15,180,1),
 ('category_buyer_hiring','Category Buyer Hiring','Hiring category managers, buyers or merchandise managers who own assortment',17,120,1),
 ('procurement_hiring','Procurement Hiring','Hiring purchasing, sourcing or procurement professionals',15,120,1),
 ('distribution_center_expansion','Distribution Center Expansion','New warehouse, distribution centre or major inventory-capacity expansion',13,270,1),
 ('dealer_network_expansion','Dealer Network Expansion','Entering new territories or materially expanding B2B dealer coverage',12,180,1),
 ('acquisition_or_distribution_expansion','Acquisition or Distribution Expansion','Acquired a distributor, added regional distribution or materially expanded operations',12,270,1),
 ('powersports_participation','Powersports Participation','Verifiable participation in the powersports aftermarket',5,null,1),
 ('b2b_dealer_distribution','B2B Dealer Distribution','Supplies dealers or resellers - the distributor-to-dealer direction. Fit, not buying intent',6,null,1),
 ('manufacturer_seeking_distribution','Manufacturer Seeking Distribution','The company is looking for distributors for its own products - the opposite direction',-25,null,1),
 ('retail_only_operation','Retail-Only Operation','Consumer showroom or unit-sales language with no wholesale operation',-15,null,1),
 ('service_repair_operation','Service or Repair Operation','Repair or service business rather than a distributor',-12,null,1)
) as v(signal_type, signal_name, description, weight, decay_days, max_occ)
where s.slug = 'powersports_aftermarket_sourcing'
on conflict (service_id, signal_type) do update
  set weight = excluded.weight,
      decay_days = excluded.decay_days,
      signal_name = excluded.signal_name,
      description = excluded.description;

-- ---------------------------------------------------------------------
-- 4. KEYWORDS  (219)
-- ---------------------------------------------------------------------
insert into service_keywords (service_id, keyword, category, signal_type, weight)
select s.id, v.keyword, v.category, v.signal_type, v.weight
from services s,
(values
 ('request for quote','intent','active_product_rfq',1),
 ('request for quotation','intent','active_product_rfq',1),
 ('rfq','intent','active_product_rfq',1),
 ('request for proposal','intent','active_product_rfq',1),
 ('seeking quotes','intent','active_product_rfq',1),
 ('looking to source','intent','active_product_rfq',1),
 ('now sourcing','intent','active_product_rfq',1),
 ('we are sourcing','intent','active_product_rfq',1),
 ('sourcing request','intent','active_product_rfq',1),
 ('quotes from manufacturers','intent','active_product_rfq',1),
 ('quotes from suppliers','intent','active_product_rfq',1),
 ('looking for new suppliers','intent','explicit_supplier_search',1),
 ('seeking new suppliers','intent','explicit_supplier_search',1),
 ('looking for suppliers','intent','explicit_supplier_search',1),
 ('seeking suppliers','intent','explicit_supplier_search',1),
 ('new supplier opportunities','intent','explicit_supplier_search',1),
 ('looking for new products','intent','explicit_supplier_search',1),
 ('seeking new products','intent','explicit_supplier_search',1),
 ('looking for new brands','intent','explicit_supplier_search',1),
 ('seeking new brands','intent','explicit_supplier_search',1),
 ('submit your product','intent','explicit_supplier_search',1),
 ('submit your products','intent','explicit_supplier_search',1),
 ('submit your catalog','intent','explicit_supplier_search',1),
 ('submit your product catalog','intent','explicit_supplier_search',1),
 ('product catalog for consideration','intent','explicit_supplier_search',1),
 ('products for consideration','intent','explicit_supplier_search',1),
 ('accepting new vendors','intent','explicit_supplier_search',1),
 ('accepting new suppliers','intent','explicit_supplier_search',1),
 ('accepting new brands','intent','explicit_supplier_search',1),
 ('looking for manufacturers','intent','explicit_supplier_search',1),
 ('seeking manufacturers','intent','explicit_supplier_search',1),
 ('new vendor partners','intent','explicit_supplier_search',1),
 ('interested in becoming a supplier','intent','explicit_supplier_search',1),
 ('interested in becoming a vendor','intent','explicit_supplier_search',1),
 ('supplier application','intent','supplier_application_open',1),
 ('vendor application','intent','supplier_application_open',1),
 ('new vendor application','intent','supplier_application_open',1),
 ('vendor inquiry form','intent','supplier_application_open',1),
 ('supplier inquiry','intent','supplier_application_open',1),
 ('become a supplier','intent','supplier_application_open',1),
 ('become a vendor','intent','supplier_application_open',1),
 ('vendor submission','intent','supplier_application_open',1),
 ('supplier submission','intent','supplier_application_open',1),
 ('vendor onboarding','intent','supplier_application_open',1),
 ('new vendor setup','intent','supplier_application_open',1),
 ('vendor information form','intent','supplier_application_open',1),
 ('supplier registration','intent','supplier_application_open',1),
 ('vendor registration','intent','supplier_application_open',1),
 ('prospective vendors','intent','supplier_application_open',1),
 ('prospective suppliers','intent','supplier_application_open',1),
 ('product submission form','intent','supplier_application_open',1),
 ('new brand submission','intent','supplier_application_open',1),
 ('distribution agreement','expansion','new_distribution_partnership',1),
 ('distribution partnership','expansion','new_distribution_partnership',1),
 ('exclusive distribution','expansion','new_distribution_partnership',1),
 ('exclusive distributor for','expansion','new_distribution_partnership',1),
 ('exclusive distribution rights','expansion','new_distribution_partnership',1),
 ('agreement to distribute','expansion','new_distribution_partnership',1),
 ('will now distribute','expansion','new_distribution_partnership',1),
 ('now distributing','expansion','new_distribution_partnership',1),
 ('now distributes','expansion','new_distribution_partnership',1),
 ('named exclusive distributor','expansion','new_distribution_partnership',1),
 ('appointed as distributor','expansion','new_distribution_partnership',1),
 ('distribution deal','expansion','new_distribution_partnership',1),
 ('master distributor for','expansion','new_distribution_partnership',1),
 ('partnered with','expansion','new_distribution_partnership',0.6),
 ('new partnership with','expansion','new_distribution_partnership',0.6),
 ('announces partnership','expansion','new_distribution_partnership',0.6),
 ('added to our lineup','expansion','new_brand_added',1),
 ('added to its lineup','expansion','new_brand_added',1),
 ('adds brand','expansion','new_brand_added',1),
 ('joins our brand portfolio','expansion','new_brand_added',1),
 ('joins our lineup','expansion','new_brand_added',1),
 ('now carrying','expansion','new_brand_added',1),
 ('now carries','expansion','new_brand_added',1),
 ('now stocking','expansion','new_brand_added',1),
 ('newest brand','expansion','new_brand_added',1),
 ('new to our line','expansion','new_brand_added',1),
 ('added to our line card','expansion','new_brand_added',1),
 ('adds new brands','expansion','new_brand_added',1),
 ('expands brand portfolio','expansion','new_brand_added',1),
 ('expanded brand portfolio','expansion','new_brand_added',1),
 ('new brand','expansion','new_brand_added',0.7),
 ('new brands','expansion','new_brand_added',0.7),
 ('expands its product','expansion','product_category_expansion',1),
 ('expanded product offering','expansion','product_category_expansion',1),
 ('expanding our product','expansion','product_category_expansion',1),
 ('new product category','expansion','product_category_expansion',1),
 ('new product categories','expansion','product_category_expansion',1),
 ('expanded its catalog','expansion','product_category_expansion',1),
 ('expands catalog','expansion','product_category_expansion',1),
 ('expanded assortment','expansion','product_category_expansion',1),
 ('expands assortment','expansion','product_category_expansion',1),
 ('expansion into','expansion','product_category_expansion',1),
 ('expanding into','expansion','product_category_expansion',1),
 ('broadens its product','expansion','product_category_expansion',1),
 ('new product line','expansion','new_product_line_launch',0.8),
 ('new product lines','expansion','new_product_line_launch',0.8),
 ('launches new','expansion','new_product_line_launch',0.8),
 ('introduces new','expansion','new_product_line_launch',0.8),
 ('new for 2026','expansion','new_product_line_launch',0.8),
 ('new for 2027','expansion','new_product_line_launch',0.8),
 ('product launch','expansion','new_product_line_launch',0.8),
 ('new products for','expansion','new_product_line_launch',0.8),
 ('line card','expansion','catalog_or_linecard_expansion',0.8),
 ('linecard','expansion','catalog_or_linecard_expansion',0.8),
 ('new catalog','expansion','catalog_or_linecard_expansion',0.8),
 ('2026 catalog','expansion','catalog_or_linecard_expansion',0.8),
 ('2027 catalog','expansion','catalog_or_linecard_expansion',0.8),
 ('catalog expansion','expansion','catalog_or_linecard_expansion',0.8),
 ('new skus','expansion','catalog_or_linecard_expansion',0.8),
 ('new part numbers','expansion','catalog_or_linecard_expansion',0.8),
 ('thousands of new parts','expansion','catalog_or_linecard_expansion',0.8),
 ('category manager','hiring','category_buyer_hiring',1),
 ('product buyer','hiring','category_buyer_hiring',1),
 ('buyer','hiring','category_buyer_hiring',1),
 ('senior buyer','hiring','category_buyer_hiring',1),
 ('associate buyer','hiring','category_buyer_hiring',1),
 ('category buyer','hiring','category_buyer_hiring',1),
 ('merchandise manager','hiring','category_buyer_hiring',1),
 ('merchandising manager','hiring','category_buyer_hiring',1),
 ('assortment manager','hiring','category_buyer_hiring',1),
 ('product line manager','hiring','category_buyer_hiring',1),
 ('merchandise planner','hiring','category_buyer_hiring',1),
 ('purchasing manager','hiring','procurement_hiring',1),
 ('purchasing agent','hiring','procurement_hiring',1),
 ('purchasing director','hiring','procurement_hiring',1),
 ('director of purchasing','hiring','procurement_hiring',1),
 ('procurement manager','hiring','procurement_hiring',1),
 ('procurement specialist','hiring','procurement_hiring',1),
 ('sourcing manager','hiring','procurement_hiring',1),
 ('sourcing specialist','hiring','procurement_hiring',1),
 ('strategic sourcing','hiring','procurement_hiring',1),
 ('vendor manager','hiring','procurement_hiring',1),
 ('vendor relations','hiring','procurement_hiring',1),
 ('purchasing coordinator','hiring','procurement_hiring',1),
 ('inventory buyer','hiring','procurement_hiring',1),
 ('purchasing analyst','hiring','procurement_hiring',1),
 ('new distribution center','capacity','distribution_center_expansion',1),
 ('new distribution centre','capacity','distribution_center_expansion',1),
 ('new warehouse','capacity','distribution_center_expansion',1),
 ('opens distribution center','capacity','distribution_center_expansion',1),
 ('opened a new distribution','capacity','distribution_center_expansion',1),
 ('warehouse expansion','capacity','distribution_center_expansion',1),
 ('expanded warehouse','capacity','distribution_center_expansion',1),
 ('expands distribution center','capacity','distribution_center_expansion',1),
 ('additional distribution center','capacity','distribution_center_expansion',1),
 ('square-foot distribution','capacity','distribution_center_expansion',1),
 ('square foot distribution','capacity','distribution_center_expansion',1),
 ('square-foot warehouse','capacity','distribution_center_expansion',1),
 ('square foot warehouse','capacity','distribution_center_expansion',1),
 ('new facility','capacity','distribution_center_expansion',0.6),
 ('breaks ground','capacity','distribution_center_expansion',0.6),
 ('expands dealer network','capacity','dealer_network_expansion',1),
 ('expanding our dealer network','capacity','dealer_network_expansion',1),
 ('expanded its dealer network','capacity','dealer_network_expansion',1),
 ('growing dealer network','capacity','dealer_network_expansion',1),
 ('new sales territory','capacity','dealer_network_expansion',1),
 ('new territories','capacity','dealer_network_expansion',1),
 ('expanded coverage','capacity','dealer_network_expansion',1),
 ('new dealer accounts','capacity','dealer_network_expansion',1),
 ('has acquired','capacity','acquisition_or_distribution_expansion',1),
 ('completed the acquisition','capacity','acquisition_or_distribution_expansion',1),
 ('acquisition of','capacity','acquisition_or_distribution_expansion',1),
 ('acquires','capacity','acquisition_or_distribution_expansion',1),
 ('merges with','capacity','acquisition_or_distribution_expansion',1),
 ('regional distribution capabilities','capacity','acquisition_or_distribution_expansion',1),
 ('adds distribution','capacity','acquisition_or_distribution_expansion',1),
 ('powersports','fit','powersports_participation',0.9),
 ('power sports','fit','powersports_participation',0.9),
 ('atv','fit','powersports_participation',0.9),
 ('utv','fit','powersports_participation',0.9),
 ('side-by-side','fit','powersports_participation',0.9),
 ('sxs','fit','powersports_participation',0.9),
 ('motorcycle','fit','powersports_participation',0.9),
 ('dirt bike','fit','powersports_participation',0.9),
 ('motocross','fit','powersports_participation',0.9),
 ('snowmobile','fit','powersports_participation',0.9),
 ('v-twin','fit','powersports_participation',0.9),
 ('become a dealer','fit','b2b_dealer_distribution',0.9),
 ('dealer application','fit','b2b_dealer_distribution',0.9),
 ('authorized dealers','fit','b2b_dealer_distribution',0.9),
 ('dealer network','fit','b2b_dealer_distribution',0.9),
 ('dealer portal','fit','b2b_dealer_distribution',0.9),
 ('dealer login','fit','b2b_dealer_distribution',0.9),
 ('wholesale distributor','fit','b2b_dealer_distribution',0.9),
 ('dealer pricing','fit','b2b_dealer_distribution',0.9),
 ('independent dealers','fit','b2b_dealer_distribution',0.9),
 ('serving dealers','fit','b2b_dealer_distribution',0.9),
 ('dealer support','fit','b2b_dealer_distribution',0.9),
 ('wholesale only','fit','b2b_dealer_distribution',0.9),
 ('dealers only','fit','b2b_dealer_distribution',0.9),
 ('trade only','fit','b2b_dealer_distribution',0.9),
 ('looking for distributors','negative','manufacturer_seeking_distribution',1),
 ('looking for a distributor','negative','manufacturer_seeking_distribution',1),
 ('seeking distributors','negative','manufacturer_seeking_distribution',1),
 ('seeking a distributor','negative','manufacturer_seeking_distribution',1),
 ('become a distributor','negative','manufacturer_seeking_distribution',1),
 ('distributor inquiries','negative','manufacturer_seeking_distribution',1),
 ('distributor opportunities','negative','manufacturer_seeking_distribution',1),
 ('distributors wanted','negative','manufacturer_seeking_distribution',1),
 ('seeking a us distributor','negative','manufacturer_seeking_distribution',1),
 ('looking for a us distributor','negative','manufacturer_seeking_distribution',1),
 ('distribute our products','negative','manufacturer_seeking_distribution',1),
 ('interested in distributing our products','negative','manufacturer_seeking_distribution',1),
 ('visit our showroom','negative','retail_only_operation',0.9),
 ('new and used','negative','retail_only_operation',0.9),
 ('pre-owned inventory','negative','retail_only_operation',0.9),
 ('schedule a test ride','negative','retail_only_operation',0.9),
 ('showroom hours','negative','retail_only_operation',0.9),
 ('browse our inventory','negative','retail_only_operation',0.9),
 ('used inventory','negative','retail_only_operation',0.9),
 ('value your trade','negative','retail_only_operation',0.9),
 ('schedule service','negative','service_repair_operation',0.9),
 ('service appointment','negative','service_repair_operation',0.9),
 ('repair shop','negative','service_repair_operation',0.9),
 ('our service department','negative','service_repair_operation',0.9),
 ('we repair','negative','service_repair_operation',0.9),
 ('service specials','negative','service_repair_operation',0.9)
) as v(keyword, category, signal_type, weight)
where s.slug = 'powersports_aftermarket_sourcing'
on conflict (service_id, keyword, category) do update
  set weight = excluded.weight, signal_type = excluded.signal_type;

-- ---------------------------------------------------------------------
-- 5. DECISION-MAKER ROLES  (46)
-- ---------------------------------------------------------------------
insert into service_roles (service_id, title_pattern, role_priority)
select s.id, v.pattern, v.prio
from services s,
(values
 ('vp of purchasing',1),
 ('vice president of purchasing',1),
 ('vp purchasing',1),
 ('vice president, purchasing',1),
 ('director of purchasing',1),
 ('purchasing director',1),
 ('head of purchasing',1),
 ('chief purchasing officer',1),
 ('director of procurement',1),
 ('vp of procurement',1),
 ('head of procurement',1),
 ('purchasing manager',2),
 ('category manager',2),
 ('senior category manager',2),
 ('director of category management',2),
 ('merchandising director',2),
 ('director of merchandising',2),
 ('vp of merchandising',2),
 ('vp of product',3),
 ('vice president of product',3),
 ('director of product',3),
 ('product line manager',3),
 ('head of product',3),
 ('product manager',4),
 ('procurement manager',4),
 ('sourcing manager',4),
 ('director of sourcing',4),
 ('vendor relations manager',4),
 ('vendor manager',4),
 ('senior buyer',4),
 ('buyer',5),
 ('purchasing agent',5),
 ('owner',6),
 ('co-owner',6),
 ('president',6),
 ('ceo',6),
 ('chief executive officer',6),
 ('founder',7),
 ('co-founder',7),
 ('coo',8),
 ('chief operating officer',8),
 ('general manager',9),
 ('director of business development',10),
 ('vp of business development',10),
 ('business development manager',11),
 ('vice president',12)
) as v(pattern, prio)
where s.slug = 'powersports_aftermarket_sourcing'
on conflict (service_id, title_pattern) do update set role_priority = excluded.role_priority;

-- ---------------------------------------------------------------------
-- 6. DISCOVERY QUERIES  (631: {1: 162, 2: 247, 3: 212, 4: 10})
-- ---------------------------------------------------------------------
insert into discovery_queries (service_id, query, country, priority)
select s.id, v.query, v.country, v.priority
from services s,
(values
 ('powersports distributor seeking new suppliers', 'US', 1),
 ('powersports distributor supplier application', 'US', 1),
 ('aftermarket parts distributor new brand submissions', 'US', 1),
 ('powersports wholesaler looking for manufacturers', 'US', 1),
 ('distributor sourcing new ATV accessories', 'US', 1),
 ('powersports distributor vendor application', 'US', 1),
 ('motorcycle parts distributor become a vendor', 'US', 1),
 ('powersports distributor submit your products', 'US', 1),
 ('UTV accessories distributor new vendor application', 'US', 1),
 ('powersports distributor accepting new brands', 'US', 1),
 ('motorcycle aftermarket distributor product submission', 'US', 1),
 ('powersports distributor RFQ aftermarket products', 'US', 1),
 ('"powersports distributor" "vendor application"', 'US', 1),
 ('"powersports distributor" "new suppliers"', 'US', 1),
 ('"powersports wholesale distributor" "vendor application"', 'US', 1),
 ('"powersports wholesale distributor" "new suppliers"', 'US', 1),
 ('"motorcycle parts distributor" "vendor application"', 'US', 1),
 ('"motorcycle parts distributor" "new suppliers"', 'US', 1),
 ('"ATV UTV aftermarket distributor" "vendor application"', 'US', 1),
 ('"ATV UTV aftermarket distributor" "new suppliers"', 'US', 1),
 ('"aftermarket parts distributor" "vendor application"', 'US', 1),
 ('"aftermarket parts distributor" "new suppliers"', 'US', 1),
 ('motorcycle parts distributor new product lines', 'US', 2),
 ('distributor adding new UTV product categories', 'US', 2),
 ('powersports distributor distribution agreement', 'US', 2),
 ('motorcycle aftermarket distributor expanding product portfolio', 'US', 2),
 ('UTV accessories distributor partnership announcement', 'US', 2),
 ('powersports distributor adds new brands', 'US', 2),
 ('powersports distributor exclusive distribution rights', 'US', 2),
 ('powersports distributor new brand partnership 2026', 'US', 2),
 ('UTV accessories distribution agreement powersports distributor', 'US', 2),
 ('distributor adds UTV accessories brand', 'US', 2),
 ('motorcycle crash protection distribution agreement powersports distributor', 'US', 2),
 ('distributor adds motorcycle crash protection brand', 'US', 2),
 ('ATV tires distribution agreement powersports distributor', 'US', 2),
 ('distributor adds ATV tires brand', 'US', 2),
 ('UTV tires distribution agreement powersports distributor', 'US', 2),
 ('distributor adds UTV tires brand', 'US', 2),
 ('powersports batteries distribution agreement powersports distributor', 'US', 2),
 ('distributor adds powersports batteries brand', 'US', 2),
 ('UTV windshields distribution agreement powersports distributor', 'US', 2),
 ('distributor adds UTV windshields brand', 'US', 2),
 ('motorcycle apparel distribution agreement powersports distributor', 'US', 2),
 ('distributor adds motorcycle apparel brand', 'US', 2),
 ('off-road performance parts distribution agreement powersports distributor', 'US', 2),
 ('distributor adds off-road performance parts brand', 'US', 2),
 ('motorcycle luggage distribution agreement powersports distributor', 'US', 2),
 ('distributor adds motorcycle luggage brand', 'US', 2),
 ('UTV lighting distribution agreement powersports distributor', 'US', 2),
 ('distributor adds UTV lighting brand', 'US', 2),
 ('motorcycle helmets distribution agreement powersports distributor', 'US', 2),
 ('distributor adds motorcycle helmets brand', 'US', 2),
 ('powersports lubricants distribution agreement powersports distributor', 'US', 2),
 ('distributor adds powersports lubricants brand', 'US', 2),
 ('UTV cab enclosures distribution agreement powersports distributor', 'US', 2),
 ('distributor adds UTV cab enclosures brand', 'US', 2),
 ('winches distribution agreement powersports distributor', 'US', 2),
 ('distributor adds winches brand', 'US', 2),
 ('powersports aftermarket parts distributors USA', 'US', 3),
 ('powersports wholesale distributors', 'US', 3),
 ('motorcycle parts wholesale distributors', 'US', 3),
 ('ATV UTV aftermarket distributors', 'US', 3),
 ('side by side accessories wholesale distributors', 'US', 3),
 ('motorcycle apparel wholesale distributors', 'US', 3),
 ('motocross parts distributors', 'US', 3),
 ('snowmobile parts wholesalers', 'US', 3),
 ('regional powersports parts distributors', 'US', 3),
 ('powersports dealer wholesale suppliers', 'US', 3),
 ('aftermarket accessories distribution companies', 'US', 3),
 ('independent motorcycle dealer distributors', 'US', 3),
 ('V-twin parts wholesale distributor', 'US', 3),
 ('off-road parts wholesale distributor', 'US', 3),
 ('UTV accessories wholesale distributor dealers only', 'US', 3),
 ('powersports tire wholesale distributor', 'US', 3),
 ('motorcycle riding gear distributor dealers', 'US', 3),
 ('powersports parts distributor dealer network', 'US', 3),
 ('powersports parts distributor Texas', 'US', 3),
 ('powersports parts distributor California', 'US', 3),
 ('powersports parts distributor Minnesota', 'US', 3),
 ('powersports parts distributor Wisconsin', 'US', 3),
 ('powersports parts distributor Pennsylvania', 'US', 3),
 ('powersports parts distributor Georgia', 'US', 3),
 ('powersports parts distributor Ohio', 'US', 3),
 ('powersports parts distributor Florida', 'US', 3),
 ('powersports parts distributor Michigan', 'US', 3),
 ('powersports parts distributor Utah', 'US', 3),
 ('powersports distributor line card brands we carry', 'US', 3),
 ('motorcycle parts distributor dealer portal login', 'US', 3),
 ('powersports product category manager hiring', 'US', 4),
 ('powersports distributor purchasing manager jobs', 'US', 4),
 ('aftermarket distributor procurement hiring', 'US', 4),
 ('powersports distributor buyer job', 'US', 4),
 ('motorcycle parts distributor category manager job', 'US', 4),
 ('powersports distributor new warehouse expansion', 'US', 4),
 ('powersports distributor new distribution center', 'US', 4),
 ('powersports distributor acquires distributor', 'US', 4),
 ('motorcycle parts distributor acquisition', 'US', 4),
 ('powersports distributor expands dealer network', 'US', 4),
 ('powersports parts distributor vendor application', 'US', 1),
 ('powersports parts distributor new vendor setup', 'US', 1),
 ('powersports wholesale distributor seeking new product lines', 'US', 1),
 ('powersports distributor become a supplier', 'US', 1),
 ('powersports aftermarket distributor new supplier inquiry', 'US', 1),
 ('powersports parts wholesaler manufacturers wanted', 'US', 1),
 ('powersports distributor submit a new product', 'US', 1),
 ('powersports wholesale distributor dealers only', 'US', 1),
 ('powersports parts distributor brands we carry', 'US', 1),
 ('powersports accessories wholesale distributor', 'US', 1),
 ('motorcycle parts distributor vendor application', 'US', 1),
 ('motorcycle parts distributor new vendor setup', 'US', 1),
 ('motorcycle wholesale distributor seeking new product lines', 'US', 1),
 ('motorcycle distributor become a supplier', 'US', 1),
 ('motorcycle aftermarket distributor new supplier inquiry', 'US', 1),
 ('motorcycle parts wholesaler manufacturers wanted', 'US', 1),
 ('motorcycle distributor submit a new product', 'US', 1),
 ('motorcycle wholesale distributor dealers only', 'US', 1),
 ('motorcycle parts distributor brands we carry', 'US', 1),
 ('motorcycle accessories wholesale distributor', 'US', 1),
 ('ATV parts distributor vendor application', 'US', 1),
 ('ATV parts distributor new vendor setup', 'US', 1),
 ('ATV wholesale distributor seeking new product lines', 'US', 1),
 ('ATV distributor become a supplier', 'US', 1),
 ('ATV aftermarket distributor new supplier inquiry', 'US', 1),
 ('ATV parts wholesaler manufacturers wanted', 'US', 1),
 ('ATV distributor submit a new product', 'US', 1),
 ('ATV wholesale distributor dealers only', 'US', 1),
 ('ATV parts distributor brands we carry', 'US', 1),
 ('ATV accessories wholesale distributor', 'US', 1),
 ('UTV parts distributor vendor application', 'US', 1),
 ('UTV parts distributor new vendor setup', 'US', 1),
 ('UTV wholesale distributor seeking new product lines', 'US', 1),
 ('UTV distributor become a supplier', 'US', 1),
 ('UTV aftermarket distributor new supplier inquiry', 'US', 1),
 ('UTV parts wholesaler manufacturers wanted', 'US', 1),
 ('UTV distributor submit a new product', 'US', 1),
 ('UTV wholesale distributor dealers only', 'US', 1),
 ('UTV parts distributor brands we carry', 'US', 1),
 ('UTV accessories wholesale distributor', 'US', 1),
 ('side by side parts distributor vendor application', 'US', 1),
 ('side by side parts distributor new vendor setup', 'US', 1),
 ('side by side wholesale distributor seeking new product lines', 'US', 1),
 ('side by side distributor become a supplier', 'US', 1),
 ('side by side aftermarket distributor new supplier inquiry', 'US', 1),
 ('side by side parts wholesaler manufacturers wanted', 'US', 1),
 ('side by side distributor submit a new product', 'US', 1),
 ('side by side wholesale distributor dealers only', 'US', 1),
 ('side by side parts distributor brands we carry', 'US', 1),
 ('side by side accessories wholesale distributor', 'US', 1),
 ('snowmobile parts distributor vendor application', 'US', 1),
 ('snowmobile parts distributor new vendor setup', 'US', 1),
 ('snowmobile wholesale distributor seeking new product lines', 'US', 1),
 ('snowmobile distributor become a supplier', 'US', 1),
 ('snowmobile aftermarket distributor new supplier inquiry', 'US', 1),
 ('snowmobile parts wholesaler manufacturers wanted', 'US', 1),
 ('snowmobile distributor submit a new product', 'US', 1),
 ('snowmobile wholesale distributor dealers only', 'US', 1),
 ('snowmobile parts distributor brands we carry', 'US', 1),
 ('snowmobile accessories wholesale distributor', 'US', 1),
 ('dirt bike parts distributor vendor application', 'US', 1),
 ('dirt bike parts distributor new vendor setup', 'US', 1),
 ('dirt bike wholesale distributor seeking new product lines', 'US', 1),
 ('dirt bike distributor become a supplier', 'US', 1),
 ('dirt bike aftermarket distributor new supplier inquiry', 'US', 1),
 ('dirt bike parts wholesaler manufacturers wanted', 'US', 1),
 ('dirt bike distributor submit a new product', 'US', 1),
 ('dirt bike wholesale distributor dealers only', 'US', 1),
 ('dirt bike parts distributor brands we carry', 'US', 1),
 ('dirt bike accessories wholesale distributor', 'US', 1),
 ('motocross parts distributor vendor application', 'US', 1),
 ('motocross parts distributor new vendor setup', 'US', 1),
 ('motocross wholesale distributor seeking new product lines', 'US', 1),
 ('motocross distributor become a supplier', 'US', 1),
 ('motocross aftermarket distributor new supplier inquiry', 'US', 1),
 ('motocross parts wholesaler manufacturers wanted', 'US', 1),
 ('motocross distributor submit a new product', 'US', 1),
 ('motocross wholesale distributor dealers only', 'US', 1),
 ('motocross parts distributor brands we carry', 'US', 1),
 ('motocross accessories wholesale distributor', 'US', 1),
 ('V-twin parts distributor vendor application', 'US', 1),
 ('V-twin parts distributor new vendor setup', 'US', 1),
 ('V-twin wholesale distributor seeking new product lines', 'US', 1),
 ('V-twin distributor become a supplier', 'US', 1),
 ('V-twin aftermarket distributor new supplier inquiry', 'US', 1),
 ('V-twin parts wholesaler manufacturers wanted', 'US', 1),
 ('V-twin distributor submit a new product', 'US', 1),
 ('V-twin wholesale distributor dealers only', 'US', 1),
 ('V-twin parts distributor brands we carry', 'US', 1),
 ('V-twin accessories wholesale distributor', 'US', 1),
 ('off-road parts distributor vendor application', 'US', 1),
 ('off-road parts distributor new vendor setup', 'US', 1),
 ('off-road wholesale distributor seeking new product lines', 'US', 1),
 ('off-road distributor become a supplier', 'US', 1),
 ('off-road aftermarket distributor new supplier inquiry', 'US', 1),
 ('off-road parts wholesaler manufacturers wanted', 'US', 1),
 ('off-road distributor submit a new product', 'US', 1),
 ('off-road wholesale distributor dealers only', 'US', 1),
 ('off-road parts distributor brands we carry', 'US', 1),
 ('off-road accessories wholesale distributor', 'US', 1),
 ('personal watercraft parts distributor vendor application', 'US', 1),
 ('personal watercraft parts distributor new vendor setup', 'US', 1),
 ('personal watercraft wholesale distributor seeking new product lines', 'US', 1),
 ('personal watercraft distributor become a supplier', 'US', 1),
 ('personal watercraft aftermarket distributor new supplier inquiry', 'US', 1),
 ('personal watercraft parts wholesaler manufacturers wanted', 'US', 1),
 ('personal watercraft distributor submit a new product', 'US', 1),
 ('personal watercraft wholesale distributor dealers only', 'US', 1),
 ('personal watercraft parts distributor brands we carry', 'US', 1),
 ('personal watercraft accessories wholesale distributor', 'US', 1),
 ('metric cruiser parts distributor vendor application', 'US', 1),
 ('metric cruiser parts distributor new vendor setup', 'US', 1),
 ('metric cruiser wholesale distributor seeking new product lines', 'US', 1),
 ('metric cruiser distributor become a supplier', 'US', 1),
 ('metric cruiser aftermarket distributor new supplier inquiry', 'US', 1),
 ('metric cruiser parts wholesaler manufacturers wanted', 'US', 1),
 ('metric cruiser distributor submit a new product', 'US', 1),
 ('metric cruiser wholesale distributor dealers only', 'US', 1),
 ('metric cruiser parts distributor brands we carry', 'US', 1),
 ('metric cruiser accessories wholesale distributor', 'US', 1),
 ('adventure motorcycle parts distributor vendor application', 'US', 1),
 ('adventure motorcycle parts distributor new vendor setup', 'US', 1),
 ('adventure motorcycle wholesale distributor seeking new product lines', 'US', 1),
 ('adventure motorcycle distributor become a supplier', 'US', 1),
 ('adventure motorcycle aftermarket distributor new supplier inquiry', 'US', 1),
 ('adventure motorcycle parts wholesaler manufacturers wanted', 'US', 1),
 ('adventure motorcycle distributor submit a new product', 'US', 1),
 ('adventure motorcycle wholesale distributor dealers only', 'US', 1),
 ('adventure motorcycle parts distributor brands we carry', 'US', 1),
 ('adventure motorcycle accessories wholesale distributor', 'US', 1),
 ('golf cart and UTV parts distributor vendor application', 'US', 1),
 ('golf cart and UTV parts distributor new vendor setup', 'US', 1),
 ('golf cart and UTV wholesale distributor seeking new product lines', 'US', 1),
 ('golf cart and UTV distributor become a supplier', 'US', 1),
 ('golf cart and UTV aftermarket distributor new supplier inquiry', 'US', 1),
 ('golf cart and UTV parts wholesaler manufacturers wanted', 'US', 1),
 ('golf cart and UTV distributor submit a new product', 'US', 1),
 ('golf cart and UTV wholesale distributor dealers only', 'US', 1),
 ('golf cart and UTV parts distributor brands we carry', 'US', 1),
 ('golf cart and UTV accessories wholesale distributor', 'US', 1),
 ('UTV accessories wholesale distributor for dealers', 'US', 2),
 ('UTV accessories distributor vendor application', 'US', 2),
 ('UTV accessories wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle crash protection wholesale distributor for dealers', 'US', 2),
 ('motorcycle crash protection distributor vendor application', 'US', 2),
 ('motorcycle crash protection wholesale supplier to powersports dealers', 'US', 2),
 ('ATV tires wholesale distributor for dealers', 'US', 2),
 ('ATV tires distributor vendor application', 'US', 2),
 ('ATV tires wholesale supplier to powersports dealers', 'US', 2),
 ('UTV tires wholesale distributor for dealers', 'US', 2),
 ('UTV tires distributor vendor application', 'US', 2),
 ('UTV tires wholesale supplier to powersports dealers', 'US', 2),
 ('powersports batteries wholesale distributor for dealers', 'US', 2),
 ('powersports batteries distributor vendor application', 'US', 2),
 ('powersports batteries wholesale supplier to powersports dealers', 'US', 2),
 ('UTV windshields wholesale distributor for dealers', 'US', 2),
 ('UTV windshields distributor vendor application', 'US', 2),
 ('UTV windshields wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle apparel wholesale distributor for dealers', 'US', 2),
 ('motorcycle apparel distributor vendor application', 'US', 2),
 ('motorcycle apparel wholesale supplier to powersports dealers', 'US', 2),
 ('off-road performance parts wholesale distributor for dealers', 'US', 2),
 ('off-road performance parts distributor vendor application', 'US', 2),
 ('off-road performance parts wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle luggage wholesale distributor for dealers', 'US', 2),
 ('motorcycle luggage distributor vendor application', 'US', 2),
 ('motorcycle luggage wholesale supplier to powersports dealers', 'US', 2),
 ('UTV lighting wholesale distributor for dealers', 'US', 2),
 ('UTV lighting distributor vendor application', 'US', 2),
 ('UTV lighting wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle helmets wholesale distributor for dealers', 'US', 2),
 ('motorcycle helmets distributor vendor application', 'US', 2),
 ('motorcycle helmets wholesale supplier to powersports dealers', 'US', 2),
 ('powersports lubricants wholesale distributor for dealers', 'US', 2),
 ('powersports lubricants distributor vendor application', 'US', 2),
 ('powersports lubricants wholesale supplier to powersports dealers', 'US', 2),
 ('UTV cab enclosures wholesale distributor for dealers', 'US', 2),
 ('UTV cab enclosures distributor vendor application', 'US', 2),
 ('UTV cab enclosures wholesale supplier to powersports dealers', 'US', 2),
 ('winches wholesale distributor for dealers', 'US', 2),
 ('winches distributor vendor application', 'US', 2),
 ('winches wholesale supplier to powersports dealers', 'US', 2),
 ('UTV roofs wholesale distributor for dealers', 'US', 2),
 ('UTV roofs distributor vendor application', 'US', 2),
 ('UTV roofs wholesale supplier to powersports dealers', 'US', 2),
 ('UTV doors wholesale distributor for dealers', 'US', 2),
 ('UTV doors distributor vendor application', 'US', 2),
 ('UTV doors wholesale supplier to powersports dealers', 'US', 2),
 ('UTV bumpers wholesale distributor for dealers', 'US', 2),
 ('UTV bumpers distributor vendor application', 'US', 2),
 ('UTV bumpers wholesale supplier to powersports dealers', 'US', 2),
 ('UTV audio wholesale distributor for dealers', 'US', 2),
 ('UTV audio distributor vendor application', 'US', 2),
 ('UTV audio wholesale supplier to powersports dealers', 'US', 2),
 ('UTV mirrors wholesale distributor for dealers', 'US', 2),
 ('UTV mirrors distributor vendor application', 'US', 2),
 ('UTV mirrors wholesale supplier to powersports dealers', 'US', 2),
 ('UTV seats wholesale distributor for dealers', 'US', 2),
 ('UTV seats distributor vendor application', 'US', 2),
 ('UTV seats wholesale supplier to powersports dealers', 'US', 2),
 ('ATV plows wholesale distributor for dealers', 'US', 2),
 ('ATV plows distributor vendor application', 'US', 2),
 ('ATV plows wholesale supplier to powersports dealers', 'US', 2),
 ('snowmobile parts wholesale distributor for dealers', 'US', 2),
 ('snowmobile parts wholesale supplier to powersports dealers', 'US', 2),
 ('snowmobile apparel wholesale distributor for dealers', 'US', 2),
 ('snowmobile apparel distributor vendor application', 'US', 2),
 ('snowmobile apparel wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle exhaust wholesale distributor for dealers', 'US', 2),
 ('motorcycle exhaust distributor vendor application', 'US', 2),
 ('motorcycle exhaust wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle tires wholesale distributor for dealers', 'US', 2),
 ('motorcycle tires distributor vendor application', 'US', 2),
 ('motorcycle tires wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle batteries wholesale distributor for dealers', 'US', 2),
 ('motorcycle batteries distributor vendor application', 'US', 2),
 ('motorcycle batteries wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle brakes wholesale distributor for dealers', 'US', 2),
 ('motorcycle brakes distributor vendor application', 'US', 2),
 ('motorcycle brakes wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle lighting wholesale distributor for dealers', 'US', 2),
 ('motorcycle lighting distributor vendor application', 'US', 2),
 ('motorcycle lighting wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle seats wholesale distributor for dealers', 'US', 2),
 ('motorcycle seats distributor vendor application', 'US', 2),
 ('motorcycle seats wholesale supplier to powersports dealers', 'US', 2),
 ('motocross graphics wholesale distributor for dealers', 'US', 2),
 ('motocross graphics distributor vendor application', 'US', 2),
 ('motocross graphics wholesale supplier to powersports dealers', 'US', 2),
 ('dirt bike plastics wholesale distributor for dealers', 'US', 2),
 ('dirt bike plastics distributor vendor application', 'US', 2),
 ('dirt bike plastics wholesale supplier to powersports dealers', 'US', 2),
 ('off-road gear wholesale distributor for dealers', 'US', 2),
 ('off-road gear distributor vendor application', 'US', 2),
 ('off-road gear wholesale supplier to powersports dealers', 'US', 2),
 ('powersports chemicals wholesale distributor for dealers', 'US', 2),
 ('powersports chemicals distributor vendor application', 'US', 2),
 ('powersports chemicals wholesale supplier to powersports dealers', 'US', 2),
 ('powersports drive belts wholesale distributor for dealers', 'US', 2),
 ('powersports drive belts distributor vendor application', 'US', 2),
 ('powersports drive belts wholesale supplier to powersports dealers', 'US', 2),
 ('powersports clutch kits wholesale distributor for dealers', 'US', 2),
 ('powersports clutch kits distributor vendor application', 'US', 2),
 ('powersports clutch kits wholesale supplier to powersports dealers', 'US', 2),
 ('lift kits UTV wholesale distributor for dealers', 'US', 2),
 ('lift kits UTV distributor vendor application', 'US', 2),
 ('lift kits UTV wholesale supplier to powersports dealers', 'US', 2),
 ('UTV wheels wholesale distributor for dealers', 'US', 2),
 ('UTV wheels distributor vendor application', 'US', 2),
 ('UTV wheels wholesale supplier to powersports dealers', 'US', 2),
 ('ATV accessories wholesale distributor for dealers', 'US', 2),
 ('ATV accessories distributor vendor application', 'US', 2),
 ('ATV accessories wholesale supplier to powersports dealers', 'US', 2),
 ('powersports trailers wholesale distributor for dealers', 'US', 2),
 ('powersports trailers distributor vendor application', 'US', 2),
 ('powersports trailers wholesale supplier to powersports dealers', 'US', 2),
 ('motorcycle tools wholesale distributor for dealers', 'US', 2),
 ('motorcycle tools distributor vendor application', 'US', 2),
 ('motorcycle tools wholesale supplier to powersports dealers', 'US', 2),
 ('powersports covers wholesale distributor for dealers', 'US', 2),
 ('powersports covers distributor vendor application', 'US', 2),
 ('powersports covers wholesale supplier to powersports dealers', 'US', 2),
 ('tie-downs and ramps wholesale distributor for dealers', 'US', 2),
 ('tie-downs and ramps distributor vendor application', 'US', 2),
 ('tie-downs and ramps wholesale supplier to powersports dealers', 'US', 2),
 ('Kolpin authorized distributor powersports dealers', 'US', 2),
 ('Kolpin wholesale distributor USA', 'US', 2),
 ('Warn winch authorized distributor powersports dealers', 'US', 2),
 ('Warn winch wholesale distributor USA', 'US', 2),
 ('SuperATV authorized distributor powersports dealers', 'US', 2),
 ('SuperATV wholesale distributor USA', 'US', 2),
 ('EBC brakes authorized distributor powersports dealers', 'US', 2),
 ('EBC brakes wholesale distributor USA', 'US', 2),
 ('K&N authorized distributor powersports dealers', 'US', 2),
 ('K&N wholesale distributor USA', 'US', 2),
 ('Yuasa authorized distributor powersports dealers', 'US', 2),
 ('Yuasa wholesale distributor USA', 'US', 2),
 ('Maxima oil authorized distributor powersports dealers', 'US', 2),
 ('Maxima oil wholesale distributor USA', 'US', 2),
 ('Kenda tires authorized distributor powersports dealers', 'US', 2),
 ('Kenda tires wholesale distributor USA', 'US', 2),
 ('ITP tires authorized distributor powersports dealers', 'US', 2),
 ('ITP tires wholesale distributor USA', 'US', 2),
 ('Dunlop motorcycle tires authorized distributor powersports dealers', 'US', 2),
 ('Dunlop motorcycle tires wholesale distributor USA', 'US', 2),
 ('Shinko tires authorized distributor powersports dealers', 'US', 2),
 ('Shinko tires wholesale distributor USA', 'US', 2),
 ('Kemimoto authorized distributor powersports dealers', 'US', 2),
 ('Kemimoto wholesale distributor USA', 'US', 2),
 ('Rugged Radios authorized distributor powersports dealers', 'US', 2),
 ('Rugged Radios wholesale distributor USA', 'US', 2),
 ('Rigid lighting authorized distributor powersports dealers', 'US', 2),
 ('Rigid lighting wholesale distributor USA', 'US', 2),
 ('Baja Designs authorized distributor powersports dealers', 'US', 2),
 ('Baja Designs wholesale distributor USA', 'US', 2),
 ('Seizmik authorized distributor powersports dealers', 'US', 2),
 ('Seizmik wholesale distributor USA', 'US', 2),
 ('Moose Utility authorized distributor powersports dealers', 'US', 2),
 ('Moose Utility wholesale distributor USA', 'US', 2),
 ('Pro Armor authorized distributor powersports dealers', 'US', 2),
 ('Pro Armor wholesale distributor USA', 'US', 2),
 ('Bell helmets authorized distributor powersports dealers', 'US', 2),
 ('Bell helmets wholesale distributor USA', 'US', 2),
 ('Fly Racing authorized distributor powersports dealers', 'US', 2),
 ('Fly Racing wholesale distributor USA', 'US', 2),
 ('Alpinestars authorized distributor powersports dealers', 'US', 2),
 ('Alpinestars wholesale distributor USA', 'US', 2),
 ('Klim authorized distributor powersports dealers', 'US', 2),
 ('Klim wholesale distributor USA', 'US', 2),
 ('Icon motorcycle gear authorized distributor powersports dealers', 'US', 2),
 ('Icon motorcycle gear wholesale distributor USA', 'US', 2),
 ('Kuryakyn authorized distributor powersports dealers', 'US', 2),
 ('Kuryakyn wholesale distributor USA', 'US', 2),
 ('Vance & Hines authorized distributor powersports dealers', 'US', 2),
 ('Vance & Hines wholesale distributor USA', 'US', 2),
 ('Cobra exhaust authorized distributor powersports dealers', 'US', 2),
 ('Cobra exhaust wholesale distributor USA', 'US', 2),
 ('Antigravity batteries authorized distributor powersports dealers', 'US', 2),
 ('Antigravity batteries wholesale distributor USA', 'US', 2),
 ('Motobatt authorized distributor powersports dealers', 'US', 2),
 ('Motobatt wholesale distributor USA', 'US', 2),
 ('Hiflofiltro authorized distributor powersports dealers', 'US', 2),
 ('Hiflofiltro wholesale distributor USA', 'US', 2),
 ('DID chain authorized distributor powersports dealers', 'US', 2),
 ('DID chain wholesale distributor USA', 'US', 2),
 ('RK chain authorized distributor powersports dealers', 'US', 2),
 ('RK chain wholesale distributor USA', 'US', 2),
 ('EBC clutch authorized distributor powersports dealers', 'US', 2),
 ('EBC clutch wholesale distributor USA', 'US', 2),
 ('Gates belts authorized distributor powersports dealers', 'US', 2),
 ('Gates belts wholesale distributor USA', 'US', 2),
 ('Dayco belts authorized distributor powersports dealers', 'US', 2),
 ('Dayco belts wholesale distributor USA', 'US', 2),
 ('Polaris accessories aftermarket authorized distributor powersports dealers', 'US', 2),
 ('Polaris accessories aftermarket wholesale distributor USA', 'US', 2),
 ('Can-Am accessories aftermarket authorized distributor powersports dealers', 'US', 2),
 ('Can-Am accessories aftermarket wholesale distributor USA', 'US', 2),
 ('Tusk authorized distributor powersports dealers', 'US', 2),
 ('Tusk wholesale distributor USA', 'US', 2),
 ('Quadboss authorized distributor powersports dealers', 'US', 2),
 ('Quadboss wholesale distributor USA', 'US', 2),
 ('Dragonfire Racing authorized distributor powersports dealers', 'US', 2),
 ('Dragonfire Racing wholesale distributor USA', 'US', 2),
 ('Interior Color authorized distributor powersports dealers', 'US', 2),
 ('Interior Color wholesale distributor USA', 'US', 2),
 ('Bad Dog authorized distributor powersports dealers', 'US', 2),
 ('Bad Dog wholesale distributor USA', 'US', 2),
 ('Cycle Country authorized distributor powersports dealers', 'US', 2),
 ('Cycle Country wholesale distributor USA', 'US', 2),
 ('Denali lighting authorized distributor powersports dealers', 'US', 2),
 ('Denali lighting wholesale distributor USA', 'US', 2),
 ('powersports parts distributor Alabama', 'US', 3),
 ('motorcycle parts wholesale distributor Alabama', 'US', 3),
 ('ATV UTV parts wholesale distributor Alabama', 'US', 3),
 ('powersports accessories wholesaler Alabama', 'US', 3),
 ('powersports parts distributor Alaska', 'US', 3),
 ('motorcycle parts wholesale distributor Alaska', 'US', 3),
 ('ATV UTV parts wholesale distributor Alaska', 'US', 3),
 ('powersports accessories wholesaler Alaska', 'US', 3),
 ('powersports parts distributor Arizona', 'US', 3),
 ('motorcycle parts wholesale distributor Arizona', 'US', 3),
 ('ATV UTV parts wholesale distributor Arizona', 'US', 3),
 ('powersports accessories wholesaler Arizona', 'US', 3),
 ('powersports parts distributor Arkansas', 'US', 3),
 ('motorcycle parts wholesale distributor Arkansas', 'US', 3),
 ('ATV UTV parts wholesale distributor Arkansas', 'US', 3),
 ('powersports accessories wholesaler Arkansas', 'US', 3),
 ('motorcycle parts wholesale distributor California', 'US', 3),
 ('ATV UTV parts wholesale distributor California', 'US', 3),
 ('powersports accessories wholesaler California', 'US', 3),
 ('powersports parts distributor Colorado', 'US', 3),
 ('motorcycle parts wholesale distributor Colorado', 'US', 3),
 ('ATV UTV parts wholesale distributor Colorado', 'US', 3),
 ('powersports accessories wholesaler Colorado', 'US', 3),
 ('powersports parts distributor Connecticut', 'US', 3),
 ('motorcycle parts wholesale distributor Connecticut', 'US', 3),
 ('ATV UTV parts wholesale distributor Connecticut', 'US', 3),
 ('powersports accessories wholesaler Connecticut', 'US', 3),
 ('powersports parts distributor Delaware', 'US', 3),
 ('motorcycle parts wholesale distributor Delaware', 'US', 3),
 ('ATV UTV parts wholesale distributor Delaware', 'US', 3),
 ('powersports accessories wholesaler Delaware', 'US', 3),
 ('motorcycle parts wholesale distributor Florida', 'US', 3),
 ('ATV UTV parts wholesale distributor Florida', 'US', 3),
 ('powersports accessories wholesaler Florida', 'US', 3),
 ('motorcycle parts wholesale distributor Georgia', 'US', 3),
 ('ATV UTV parts wholesale distributor Georgia', 'US', 3),
 ('powersports accessories wholesaler Georgia', 'US', 3),
 ('powersports parts distributor Idaho', 'US', 3),
 ('motorcycle parts wholesale distributor Idaho', 'US', 3),
 ('ATV UTV parts wholesale distributor Idaho', 'US', 3),
 ('powersports accessories wholesaler Idaho', 'US', 3),
 ('powersports parts distributor Illinois', 'US', 3),
 ('motorcycle parts wholesale distributor Illinois', 'US', 3),
 ('ATV UTV parts wholesale distributor Illinois', 'US', 3),
 ('powersports accessories wholesaler Illinois', 'US', 3),
 ('powersports parts distributor Indiana', 'US', 3),
 ('motorcycle parts wholesale distributor Indiana', 'US', 3),
 ('ATV UTV parts wholesale distributor Indiana', 'US', 3),
 ('powersports accessories wholesaler Indiana', 'US', 3),
 ('powersports parts distributor Iowa', 'US', 3),
 ('motorcycle parts wholesale distributor Iowa', 'US', 3),
 ('ATV UTV parts wholesale distributor Iowa', 'US', 3),
 ('powersports accessories wholesaler Iowa', 'US', 3),
 ('powersports parts distributor Kansas', 'US', 3),
 ('motorcycle parts wholesale distributor Kansas', 'US', 3),
 ('ATV UTV parts wholesale distributor Kansas', 'US', 3),
 ('powersports accessories wholesaler Kansas', 'US', 3),
 ('powersports parts distributor Kentucky', 'US', 3),
 ('motorcycle parts wholesale distributor Kentucky', 'US', 3),
 ('ATV UTV parts wholesale distributor Kentucky', 'US', 3),
 ('powersports accessories wholesaler Kentucky', 'US', 3),
 ('powersports parts distributor Louisiana', 'US', 3),
 ('motorcycle parts wholesale distributor Louisiana', 'US', 3),
 ('ATV UTV parts wholesale distributor Louisiana', 'US', 3),
 ('powersports accessories wholesaler Louisiana', 'US', 3),
 ('powersports parts distributor Maine', 'US', 3),
 ('motorcycle parts wholesale distributor Maine', 'US', 3),
 ('ATV UTV parts wholesale distributor Maine', 'US', 3),
 ('powersports accessories wholesaler Maine', 'US', 3),
 ('powersports parts distributor Maryland', 'US', 3),
 ('motorcycle parts wholesale distributor Maryland', 'US', 3),
 ('ATV UTV parts wholesale distributor Maryland', 'US', 3),
 ('powersports accessories wholesaler Maryland', 'US', 3),
 ('powersports parts distributor Massachusetts', 'US', 3),
 ('motorcycle parts wholesale distributor Massachusetts', 'US', 3),
 ('ATV UTV parts wholesale distributor Massachusetts', 'US', 3),
 ('powersports accessories wholesaler Massachusetts', 'US', 3),
 ('motorcycle parts wholesale distributor Michigan', 'US', 3),
 ('ATV UTV parts wholesale distributor Michigan', 'US', 3),
 ('powersports accessories wholesaler Michigan', 'US', 3),
 ('motorcycle parts wholesale distributor Minnesota', 'US', 3),
 ('ATV UTV parts wholesale distributor Minnesota', 'US', 3),
 ('powersports accessories wholesaler Minnesota', 'US', 3),
 ('powersports parts distributor Mississippi', 'US', 3),
 ('motorcycle parts wholesale distributor Mississippi', 'US', 3),
 ('ATV UTV parts wholesale distributor Mississippi', 'US', 3),
 ('powersports accessories wholesaler Mississippi', 'US', 3),
 ('powersports parts distributor Missouri', 'US', 3),
 ('motorcycle parts wholesale distributor Missouri', 'US', 3),
 ('ATV UTV parts wholesale distributor Missouri', 'US', 3),
 ('powersports accessories wholesaler Missouri', 'US', 3),
 ('powersports parts distributor Montana', 'US', 3),
 ('motorcycle parts wholesale distributor Montana', 'US', 3),
 ('ATV UTV parts wholesale distributor Montana', 'US', 3),
 ('powersports accessories wholesaler Montana', 'US', 3),
 ('powersports parts distributor Nebraska', 'US', 3),
 ('motorcycle parts wholesale distributor Nebraska', 'US', 3),
 ('ATV UTV parts wholesale distributor Nebraska', 'US', 3),
 ('powersports accessories wholesaler Nebraska', 'US', 3),
 ('powersports parts distributor Nevada', 'US', 3),
 ('motorcycle parts wholesale distributor Nevada', 'US', 3),
 ('ATV UTV parts wholesale distributor Nevada', 'US', 3),
 ('powersports accessories wholesaler Nevada', 'US', 3),
 ('powersports parts distributor New Hampshire', 'US', 3),
 ('motorcycle parts wholesale distributor New Hampshire', 'US', 3),
 ('ATV UTV parts wholesale distributor New Hampshire', 'US', 3),
 ('powersports accessories wholesaler New Hampshire', 'US', 3),
 ('powersports parts distributor New Jersey', 'US', 3),
 ('motorcycle parts wholesale distributor New Jersey', 'US', 3),
 ('ATV UTV parts wholesale distributor New Jersey', 'US', 3),
 ('powersports accessories wholesaler New Jersey', 'US', 3),
 ('powersports parts distributor New Mexico', 'US', 3),
 ('motorcycle parts wholesale distributor New Mexico', 'US', 3),
 ('ATV UTV parts wholesale distributor New Mexico', 'US', 3),
 ('powersports accessories wholesaler New Mexico', 'US', 3),
 ('powersports parts distributor New York', 'US', 3),
 ('motorcycle parts wholesale distributor New York', 'US', 3),
 ('ATV UTV parts wholesale distributor New York', 'US', 3),
 ('powersports accessories wholesaler New York', 'US', 3),
 ('powersports parts distributor North Carolina', 'US', 3),
 ('motorcycle parts wholesale distributor North Carolina', 'US', 3),
 ('ATV UTV parts wholesale distributor North Carolina', 'US', 3),
 ('powersports accessories wholesaler North Carolina', 'US', 3),
 ('powersports parts distributor North Dakota', 'US', 3),
 ('motorcycle parts wholesale distributor North Dakota', 'US', 3),
 ('ATV UTV parts wholesale distributor North Dakota', 'US', 3),
 ('powersports accessories wholesaler North Dakota', 'US', 3),
 ('motorcycle parts wholesale distributor Ohio', 'US', 3),
 ('ATV UTV parts wholesale distributor Ohio', 'US', 3),
 ('powersports accessories wholesaler Ohio', 'US', 3),
 ('powersports parts distributor Oklahoma', 'US', 3),
 ('motorcycle parts wholesale distributor Oklahoma', 'US', 3),
 ('ATV UTV parts wholesale distributor Oklahoma', 'US', 3),
 ('powersports accessories wholesaler Oklahoma', 'US', 3),
 ('powersports parts distributor Oregon', 'US', 3),
 ('motorcycle parts wholesale distributor Oregon', 'US', 3),
 ('ATV UTV parts wholesale distributor Oregon', 'US', 3),
 ('powersports accessories wholesaler Oregon', 'US', 3),
 ('motorcycle parts wholesale distributor Pennsylvania', 'US', 3),
 ('ATV UTV parts wholesale distributor Pennsylvania', 'US', 3),
 ('powersports accessories wholesaler Pennsylvania', 'US', 3),
 ('powersports parts distributor South Carolina', 'US', 3),
 ('motorcycle parts wholesale distributor South Carolina', 'US', 3),
 ('ATV UTV parts wholesale distributor South Carolina', 'US', 3),
 ('powersports accessories wholesaler South Carolina', 'US', 3),
 ('powersports parts distributor South Dakota', 'US', 3),
 ('motorcycle parts wholesale distributor South Dakota', 'US', 3),
 ('ATV UTV parts wholesale distributor South Dakota', 'US', 3),
 ('powersports accessories wholesaler South Dakota', 'US', 3),
 ('powersports parts distributor Tennessee', 'US', 3),
 ('motorcycle parts wholesale distributor Tennessee', 'US', 3),
 ('ATV UTV parts wholesale distributor Tennessee', 'US', 3),
 ('powersports accessories wholesaler Tennessee', 'US', 3),
 ('motorcycle parts wholesale distributor Texas', 'US', 3),
 ('ATV UTV parts wholesale distributor Texas', 'US', 3),
 ('powersports accessories wholesaler Texas', 'US', 3),
 ('motorcycle parts wholesale distributor Utah', 'US', 3),
 ('ATV UTV parts wholesale distributor Utah', 'US', 3),
 ('powersports accessories wholesaler Utah', 'US', 3),
 ('powersports parts distributor Vermont', 'US', 3),
 ('motorcycle parts wholesale distributor Vermont', 'US', 3),
 ('ATV UTV parts wholesale distributor Vermont', 'US', 3),
 ('powersports accessories wholesaler Vermont', 'US', 3),
 ('powersports parts distributor Virginia', 'US', 3),
 ('motorcycle parts wholesale distributor Virginia', 'US', 3),
 ('ATV UTV parts wholesale distributor Virginia', 'US', 3),
 ('powersports accessories wholesaler Virginia', 'US', 3),
 ('powersports parts distributor Washington', 'US', 3),
 ('motorcycle parts wholesale distributor Washington', 'US', 3),
 ('ATV UTV parts wholesale distributor Washington', 'US', 3),
 ('powersports accessories wholesaler Washington', 'US', 3),
 ('powersports parts distributor West Virginia', 'US', 3),
 ('motorcycle parts wholesale distributor West Virginia', 'US', 3),
 ('ATV UTV parts wholesale distributor West Virginia', 'US', 3),
 ('powersports accessories wholesaler West Virginia', 'US', 3),
 ('motorcycle parts wholesale distributor Wisconsin', 'US', 3),
 ('ATV UTV parts wholesale distributor Wisconsin', 'US', 3),
 ('powersports accessories wholesaler Wisconsin', 'US', 3),
 ('powersports parts distributor Wyoming', 'US', 3),
 ('motorcycle parts wholesale distributor Wyoming', 'US', 3),
 ('ATV UTV parts wholesale distributor Wyoming', 'US', 3),
 ('powersports accessories wholesaler Wyoming', 'US', 3)
) as v(query, country, priority)
where s.slug = 'powersports_aftermarket_sourcing'
  and not exists (
    select 1 from discovery_queries dq
    where dq.service_id = s.id and dq.query = v.query
      and dq.country is not distinct from v.country);

-- Verify:
-- select slug, status from services;
-- select priority as tier, count(*) from discovery_queries dq
--   join services s on s.id = dq.service_id
--   where s.slug = 'powersports_aftermarket_sourcing' group by priority order by priority;


-- =====================================================================
--  PART 008  |  SCHEMA - brand, supplier and dealer page source types
-- =====================================================================

-- =====================================================================
-- 008  SOURCE TYPES FOR THE POWERSPORTS CRAWLER
--
-- The powersports service crawls brand, supplier and dealer pages, and
-- saves them as sources with source_type 'brands', 'supplier' and
-- 'dealer'. 001 limited source_type to the original 3PL page types, so on
-- Postgres every crawl that reached such a page failed the CHECK and rolled
-- back the whole company. SQLite has no CHECK here, so it only showed up
-- on Supabase.
--
-- Widens the allowed set only: no rows are changed or deleted. Safe to
-- re-run.
-- =====================================================================

alter table sources drop constraint if exists sources_source_type_check;
alter table sources add constraint sources_source_type_check
    check (source_type in ('website','about','shipping','returns',
          'careers','job','news','funding','crowdfunding',
          'press_release','social','directory','registry','other',
          'brands','supplier','dealer'));


-- =====================================================================
--  PART 009  |  SCHEMA - product-interest attributes: format, claims, species detail
-- =====================================================================

-- =====================================================================
-- 009  PRODUCT-INTEREST ATTRIBUTES
--
-- Adds product_interests.attributes: service-defined attributes read from
-- the evidence text of each product-interest record - for example product
-- format, protein source, life stage and the company's own stated claims.
-- Generic: a service defines the vocabulary in config.product_attributes.
--
-- Additive only. No existing row is changed. Safe to re-run.
-- =====================================================================

alter table product_interests
    add column if not exists attributes jsonb not null default '{}'::jsonb;


-- =====================================================================
--  PART 010  |  SEED - Pet Specialty Food, Treats & Supplements
-- =====================================================================

-- =====================================================================
-- 010  PET SPECIALTY FOOD, TREATS & SUPPLEMENTS
--
-- Service slug: pet_specialty_food_treats_supplements
-- New default service. Additive and idempotent: safe to re-run, safe on a
-- database seeded by 001-006. Deletes nothing. The legacy '3pl' service is
-- set inactive and keeps every signal, keyword, query, opportunity and
-- review it ever produced.
--
-- GENERATED FILE - do not edit directly.
-- Source: scripts/services/pet_specialty_food_treats_supplements.py
-- Rebuild: python -m scripts.build_service_seed pet_specialty_food_treats_supplements
-- =====================================================================

-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- 2. SERVICE
-- ---------------------------------------------------------------------
insert into services (name, slug, description, status, config)
values (
  'Pet Specialty Food, Treats & Supplements', 'pet_specialty_food_treats_supplements',
  'Find mid-market US pet specialty distributors and wholesalers that show public, evidenced intent to source, onboard or expand pet food, treats, chews and supplements - and which products they may be looking to buy.',
  'active',
  '{"adjacent_categories": {"Chews": ["Dog and Cat Treats"], "Dog and Cat Treats": ["Chews"], "Pet Supplements": ["Dog and Cat Treats"], "Specialty Cat Food": ["Dog and Cat Treats"], "Specialty Dog Food": ["Dog and Cat Treats", "Pet Supplements"]}, "ai_analysis_min_raw_score": 20, "ai_extra_fields": {"company_size_qualification": "\"mid_market\" | \"small\" | \"micro\" | \"large\" | \"unknown\" - never guess", "distribution_partnerships": "[string] - brands named in the evidence", "distributor_qualification": "\"qualified\" | \"possible\" | \"not_qualified\" | \"unknown\"", "distributor_qualification_reason": "string citing evidence", "evidence_gaps": "[string] - what is unknown or uncertain", "likely_decision_roles": "[string] - job titles, never personal contact data", "product_categories": "[string] - only categories named in the evidence", "products_mentioned": "[string] - only products named in the evidence", "purchasing_hiring": "[string]", "recent_expansion_activity": "[string]", "recently_added_brands": "[string] - brands named in the evidence", "species_and_formats": "[string] - only as stated in the evidence", "supplier_onboarding_evidence": "[string]", "wholesale_distribution_model": "string - only what the evidence shows"}, "ai_grounded_fields": ["likely_services", "product_categories", "products_mentioned", "distribution_partnerships", "recently_added_brands"], "ai_probability_field": "buying_intent_probability", "ai_system_prompt": "You are a B2B supply-chain analyst for pet food, treat and supplement manufacturers that want to sell through US pet specialty distributors. Analyze whether this company is a genuine US pet specialty distributor or wholesaler and determine what public evidence indicates that it is purchasing, onboarding or expanding its portfolio of pet food, treats, chews and supplements. Commercial direction matters: a distributor inviting retailers to open wholesale accounts is selling, not buying; a brand looking for distributors is the opposite direction and is not a buyer; a pet store buying from wholesalers is retail purchasing. Distinguish seeking suppliers, accepting supplier submissions, recently onboarding a supplier, currently carrying a product and a possible category fit - these are different claims. Use only the supplied evidence. Never invent products, brands, ingredients, purchasing requirements, employee counts or revenue. A general growth announcement is not a specific purchasing requirement. Product health or quality statements are the company''s own marketing claims: never describe them as proven, veterinary or FDA-approved, and never turn ''supports joint health'' into a disease treatment claim.", "ai_task": "Analyze whether this company is a genuine US pet specialty distributor or wholesaler and determine what public evidence indicates that it is purchasing, onboarding or expanding its portfolio of pet food, treats, chews and supplements. Put the probability that it is actively expanding its supplier or product portfolio in service_probability. Put only product categories named in the evidence in likely_services. If no specific product requirement is identifiable, say exactly: Specific product demand not publicly disclosed.", "brand_patterns": ["distribution (?:agreement|partnership|deal) with ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:exclusive|official|authorized|master) (?:US |U\\.S\\. |North American |national )?distributor (?:of|for) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:now|will) (?:distribute|distributing|carry|carrying|stock|stocking) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:added|adds|adding|welcomes|welcomed) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3}) (?:to (?:its|our|the) (?:lineup|line card|brand portfolio|portfolio|catalog|offering|assortment))", "([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3}) (?:is |are )?now available (?:through|via|from) ", "([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3}) expands (?:its )?distribution (?:with|through) ", "partner(?:ed|ship)? with ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})"], "carried_page_types": ["brands", "website", "about", "other"], "company_type_markers": {"b2b_marketplace": ["verified suppliers", "b2b sourcing platform", "sourcing platform", "all suppliers", "low moq", "post a buying request", "live requests", "supplier directory", "find suppliers", "list your products", "trade assurance", "become a supplier"], "brand_owner": ["find a retailer", "store locator", "where to buy", "looking for distributors", "become a distributor", "distributor inquiries", "subscribe and save", "shop now", "our products are sold", "available at fine pet retailers", "add to cart", "free shipping on orders", "orders ship within", "shop all", "shop the collection", "our story", "new arrivals", "join our pack", "learn more about these products", "carry our products", "our recipes", "veterinarian formulated"], "manufacturer": ["we manufacture", "our kitchen", "our manufacturing facility", "manufacturing facility", "manufactured in", "co-packer", "co-manufacturing", "our production facility", "we make our", "made in our own"], "pet_retailer": ["visit our store", "store hours", "in-store pickup", "curbside pickup", "shop our store", "pet boutique", "frequent buyer program", "self-serve dog wash", "our store", "locally owned pet store"], "pet_service_provider": ["dog grooming", "grooming appointment", "boarding and daycare", "doggy daycare", "pet sitting", "dog walking", "dog training classes"], "pet_specialty_distributor": ["wholesale distributor", "wholesale distribution", "we distribute", "pet specialty distributor", "pet food distributor", "brands we carry", "brands we distribute", "brands we represent", "line card", "linecard", "distribution center", "distribution centers", "master distributor", "delivery routes", "sales territory", "b2b distribution", "brand application", "partner with brands", "we partner with brands", "brand partners", "responsible distributor", "products we carry", "lines we carry", "territory footprint", "independent pet specialty", "pet specialty segment", "pet speciality segment", "independent pet retailers", "pet specialty retailers"], "software_or_service_vendor": ["book a demo", "request a demo", "free trial", "start your free trial", "go to dashboard", "pricing plans", "per month", "saas", "software platform", "find the buyers", "find retailers for your", "sign up free", "api access"], "veterinary_clinic": ["veterinary clinic", "animal hospital", "schedule an appointment", "our veterinarians", "wellness exams", "spay and neuter"], "veterinary_supplier": ["veterinary distributor", "veterinary practices", "animal health distributor", "veterinary clinics nationwide", "serving veterinarians"]}, "crawl_link_first_page_types": ["supplier", "brands", "news", "careers", "about"], "crawl_max_pages": 16, "crawl_priority_paths": [["/", "website"], ["/about", "about"], ["/about-us", "about"], ["/brands", "brands"], ["/our-brands", "brands"], ["/line-card", "brands"], ["/vendors", "supplier"], ["/become-a-vendor", "supplier"], ["/info/become-a-vendor", "supplier"], ["/vendor-application", "supplier"], ["/suppliers", "supplier"], ["/new-vendors", "supplier"], ["/news", "news"], ["/press", "news"], ["/careers", "careers"], ["/retailers", "dealer"], ["/wholesale-account", "dealer"], ["/contact", "other"]], "decision_maker_optional_threshold": 30, "decision_maker_threshold": 40, "dimension_caps": {"intent": 40}, "discovery_blocked_domains": ["petfoodprocessing.net", "petfoodindustry.com", "petbusiness.com", "petage.com", "globalpetexpo.org", "superzoo.org", "petfoodforum.com", "petproductnews.com", "americanpetproducts.org", "appa.org", "fda.gov", "aafco.org", "nasc.cc", "chewy.com", "petco.com", "petsmart.com", "amazon.com", "walmart.com", "target.com", "tractorsupply.com", "petsupermarket.com", "petvalu.com", "thomasnet.com", "zoominfo.com", "dnb.com", "manta.com", "bbb.org", "yellowpages.com", "yelp.com", "mapquest.com", "rocketreach.co", "apollo.io", "faire.com", "rangeme.com", "facebook.com", "linkedin.com", "instagram.com", "youtube.com", "reddit.com", "indeed.com", "glassdoor.com"], "exclude_logistics_providers": false, "excluded_business_types": ["marketing agency", "seo agency", "web development agency", "digital agency", "software company", "saas platform", "consulting firm", "law firm", "recruitment agency", "staffing agency", "insurance agency", "trade publication", "animal shelter", "rescue organization"], "external_fetchers": ["ats"], "external_query_templates": [["press_release", "\"{name}\" \"now available through\" OR \"distribution partnership\" OR \"distribution agreement\" OR \"adds\"", "news"], ["news", "\"{name}\" site:petfoodprocessing.net OR site:petfoodindustry.com OR site:petbusiness.com OR site:petage.com", "web"], ["supplier", "\"{name}\" \"vendor application\" OR \"become a vendor\" OR \"submit your product\" OR \"new brands\"", "web"], ["job", "\"{name}\" \"category manager\" OR \"purchasing manager\" OR \"buyer\" OR \"procurement\"", "web"], ["press_release", "\"{name}\" \"distribution center\" OR warehouse OR acquires OR acquisition", "news"]], "fetch_external_articles": 3, "fit_multipliers": {"company_type": {"default": 0.5, "hybrid_distributor_manufacturer": 0.9, "hybrid_distributor_retailer": 0.8, "pet_specialty_distributor": 1.0, "unknown": 0.75, "veterinary_supplier": 0.6}, "employee_band": {"large": 0.6, "micro": 0.55, "mid_market": 1.0, "small": 0.85, "unknown": 0.8}}, "hybrid_company_types": {"hybrid_distributor_manufacturer": ["pet_specialty_distributor", "manufacturer"], "hybrid_distributor_retailer": ["pet_specialty_distributor", "pet_retailer"]}, "industry_keywords": {"pet": ["pet food", "pet specialty", "pet supplies", "pet products", "dog food", "cat food", "dog treats", "cat treats", "pet treats", "pet supplements", "dog chews", "pet nutrition", "independent pet", "pet retailers", "pet stores", "pet industry", "companion animal", "bully sticks", "dog supplements", "cat supplements"]}, "intent_thresholds": {"GOOD": 51, "HOT": 86, "LOW": 0, "POSSIBLE": 31, "STRONG": 71}, "interest_type_by_signal": {"active_product_category_request": "EXPLICITLY_SEEKING", "active_product_rfq": "EXPLICITLY_SEEKING", "active_supplier_request": "EXPLICITLY_SEEKING", "catalog_linecard_expansion": "RECENTLY_ADDED", "food_category_expansion": "RECENTLY_ADDED", "new_brand_added": "RECENTLY_ADDED", "new_supplier_partnership": "RECENTLY_ADDED", "premium_natural_portfolio_expansion": "RECENTLY_ADDED", "product_line_launch": "RECENTLY_ADDED", "supplement_category_expansion": "RECENTLY_ADDED", "treats_category_expansion": "RECENTLY_ADDED"}, "no_product_demand_message": "Specific product demand not publicly disclosed.", "normalization_ceiling": 90, "product_attributes": {"format": {"Air-dried": ["air-dried", "air dried"], "Canned": ["canned"], "Capsule": ["capsule"], "Dehydrated": ["dehydrated"], "Freeze-dried": ["freeze-dried", "freeze dried"], "Fresh": ["fresh"], "Frozen": ["frozen"], "Hard chews": ["hard chew"], "Kibble": ["kibble"], "Liquid": ["liquid"], "Oil": ["oil"], "Paste": ["paste"], "Powder": ["powder"], "Raw": ["raw"], "Soft chews": ["soft chew"], "Tablet": ["tablet"], "Topper": ["topper"]}, "life_stage": {"All life stages": ["all life stages"], "Kitten": ["kitten"], "Puppy": ["puppy", "puppies"], "Senior": ["senior"]}, "positioning": {"Grain-free": ["grain-free", "grain free"], "High protein": ["high-protein", "high protein"], "Limited ingredient": ["limited ingredient", "limited-ingredient"], "Novel protein": ["novel protein", "novel-protein"], "Single ingredient": ["single-ingredient", "single ingredient"]}, "protein_source": {"Beef": ["beef"], "Bison": ["bison"], "Chicken": ["chicken"], "Duck": ["duck"], "Insect": ["insect protein"], "Lamb": ["lamb"], "Pork": ["pork"], "Rabbit": ["rabbit"], "Salmon": ["salmon"], "Turkey": ["turkey"], "Venison": ["venison"], "Whitefish": ["whitefish"]}, "stated_certifications_and_claims": {"Human-grade - stated": ["human-grade", "human grade"], "Made in USA - stated": ["made in usa", "made in the usa", "made in the u.s.a"], "NASC Quality Seal - stated": ["nasc quality seal", "nasc seal"], "Natural - stated": ["all-natural", "all natural", "natural"], "Organic - stated": ["organic"], "Sourced in USA - stated": ["sourced in the usa", "us-sourced"]}, "stated_health_claims": {"Supports calm behavior - company claim": ["supports calm", "promotes calm", "calming support"], "Supports dental health - company claim": ["supports dental health", "fresh breath", "reduces tartar"], "Supports digestion - company claim": ["supports digestion", "digestive support", "supports gut health"], "Supports immune health - company claim": ["supports immune", "immune support"], "Supports joint health - company claim": ["supports joint health", "joint support", "supports hip and joint"], "Supports skin and coat - company claim": ["supports skin and coat", "healthy skin and coat"]}}, "product_taxonomy": {"Chews": {"Bully Sticks": ["bully stick"], "Dental Chews": ["dental chew"], "Long-Lasting Chews": ["long-lasting chew", "long lasting chew"], "Natural Chews": ["natural chew", "beef chew", "lamb chew", "yak chew", "himalayan chew", "antler chew"], "Rawhide Alternatives": ["rawhide alternative", "rawhide-free chew", "rawhide free chew"]}, "Dog and Cat Treats": {"Baked Biscuits": ["baked biscuit", "dog biscuit", "baked dog treat"], "Cat Treats": ["cat treat"], "Dehydrated Treats": ["dehydrated treat"], "Dental Treats": ["dental treat", "dental chew"], "Dog Treats": ["dog treat"], "Freeze-Dried Treats": ["freeze-dried treat", "freeze dried treat", "freeze-dried raw treat", "freeze-dried dog treat", "freeze-dried cat treat", "freeze dried dog treat", "freeze dried cat treat"], "Functional Treats": ["functional treat"], "Grain-Free Treats": ["grain-free treat", "grain free treat"], "Jerky Treats": ["jerky treat", "dog jerky", "jerky"], "Limited-Ingredient Treats": ["limited ingredient treat", "limited-ingredient treat"], "Meat-Based Treats": ["meat treat", "meat-based treat"], "Natural Treats": ["natural dog treat", "natural cat treat", "natural pet treat", "natural treat"], "Novel-Protein Treats": ["novel protein treat", "novel-protein treat"], "Organic Treats": ["organic treat"], "Single-Ingredient Treats": ["single-ingredient treat", "single ingredient treat"], "Soft Treats": ["soft treat", "soft and chewy treat"], "Training Treats": ["training treat"]}, "Pet Supplements": {"Anxiety Support": ["anxiety support", "stress relief supplement"], "Calming and Relaxation": ["calming chew", "calming supplement", "calming treat", "relaxation supplement"], "Digestive Health Supplements": ["digestive supplement", "digestive health supplement", "digestive chew", "gut health supplement"], "Functional Supplement Chews": ["supplement chew", "functional soft chew", "soft chew supplement"], "Glucosamine and Chondroitin": ["glucosamine", "chondroitin"], "Hip and Joint Supplements": ["hip and joint", "joint supplement", "joint support supplement", "joint chew"], "Immune Support": ["immune support supplement", "immune chew"], "Liquid Supplements": ["liquid supplement"], "Mobility Supplements": ["mobility supplement", "mobility chew"], "Multivitamins": ["multivitamin"], "Nutritional Powders": ["supplement powder", "nutritional powder"], "Omega-3 and Fish Oil": ["omega-3", "fish oil", "salmon oil", "krill oil"], "Pet Supplements - General": ["pet supplement", "dog supplement", "cat supplement"], "Prebiotics": ["prebiotic"], "Probiotics": ["probiotic"], "Senior Pet Supplements": ["senior supplement", "senior pet supplement"], "Skin and Coat Supplements": ["skin and coat supplement", "skin and coat chew"]}, "Specialty Cat Food": {"Cat Broths and Food Enhancers": ["cat broth", "bone broth for cats"], "Cat Meal Toppers and Mixers": ["cat food topper", "meal topper for cats"], "Dehydrated Cat Food": ["dehydrated cat food"], "Freeze-Dried Cat Food": ["freeze-dried cat food", "freeze dried cat food"], "Fresh and Frozen Cat Food": ["fresh cat food", "frozen cat food"], "Functional Cat Nutrition": ["functional cat food", "functional nutrition for cats"], "Grain-Free Cat Food": ["grain-free cat food", "grain free cat food"], "High-Protein Cat Food": ["high-protein cat food", "high protein cat food"], "Kitten Food": ["kitten food", "kitten formula"], "Limited-Ingredient Cat Food": ["limited ingredient cat food", "limited-ingredient cat food"], "Premium Dry Cat Food": ["premium dry cat food", "dry cat food", "cat kibble", "premium cat food"], "Raw Cat Food": ["raw cat food"], "Senior Cat Food": ["senior cat food"], "Wet Cat Food": ["wet cat food", "canned cat food"]}, "Specialty Dog Food": {"Air-Dried Dog Food": ["air-dried dog food", "air dried dog food"], "Breed-Specific Formulations": ["breed-specific formula", "breed specific nutrition"], "Dehydrated Dog Food": ["dehydrated dog food"], "Dog Broths and Food Enhancers": ["bone broth for dogs", "dog broth", "dog food enhancer"], "Dog Meal Toppers and Mixers": ["dog food topper", "meal topper for dogs", "dog food mixer", "dog meal mixer"], "Freeze-Dried Dog Food": ["freeze-dried dog food", "freeze dried dog food", "freeze-dried raw dog food"], "Fresh Dog Food": ["fresh dog food", "gently cooked dog food"], "Frozen Dog Food": ["frozen dog food", "frozen raw dog food"], "Functional Dog Nutrition": ["functional dog food", "functional nutrition for dogs"], "Grain-Free Dog Food": ["grain-free dog food", "grain free dog food"], "High-Protein Dog Food": ["high-protein dog food", "high protein dog food"], "Large-Breed Food": ["large breed dog food", "large-breed dog food", "large breed formula"], "Limited-Ingredient Dog Food": ["limited ingredient dog food", "limited-ingredient dog food"], "Novel-Protein Dog Food": ["novel protein dog food", "novel-protein dog food"], "Premium Dry Dog Food": ["premium dry dog food", "dry dog food", "dog kibble", "premium dog food"], "Puppy Food": ["puppy food", "puppy formula"], "Raw Dog Food": ["raw dog food", "raw diet for dogs"], "Senior Dog Food": ["senior dog food"], "Small-Breed Food": ["small breed dog food", "small-breed dog food", "small breed formula"], "Wet Dog Food": ["wet dog food", "canned dog food"]}}, "qualification": {"allow_unverified_location_tlds": ["com", "net", "us", "org", "biz"], "allowed_countries": ["US"], "company_type_min_markers": 2, "eligible_company_types": ["pet_specialty_distributor", "hybrid_distributor_manufacturer", "hybrid_distributor_retailer", "veterinary_supplier"], "excluded_employee_bands": ["large", "small", "micro"], "industry_implies_physical": true, "min_country_confidence": 0.6, "min_industry_markers": 1, "reject_company_types": ["pet_retailer", "veterinary_clinic", "pet_service_provider", "manufacturer", "brand_owner", "software_or_service_vendor", "b2b_marketplace"], "require_country_evidence": true, "required_industry": "pet", "unknown_company_type": "reject"}, "query_exclusion_terms": ["for sale", "adoption", "puppies for sale", "near me"], "refresh_days": {"GOOD": 30, "HOT": 7, "LOW": 120, "POSSIBLE": 60, "STRONG": 14}, "required_signals": ["pet_specialty_participation"], "score_weights": {"ai": 0.3, "deterministic": 0.5, "evidence": 0.2}, "signal_dimensions": {"b2b_retailer_distribution": "fit", "brand_seeking_distribution": "negative", "pet_service_or_clinic": "negative", "pet_specialty_participation": "fit", "retail_only_pet_store": "negative"}, "signal_page_affinity": {"acquisition_expansion": ["news", "press_release", "about"], "active_product_category_request": ["supplier", "news", "press_release", "website", "other"], "active_product_rfq": ["supplier", "news", "press_release", "website", "other"], "active_supplier_request": ["supplier", "news", "press_release", "website", "about", "other"], "catalog_linecard_expansion": ["brands", "website", "news", "press_release"], "category_manager_hiring": ["careers", "job"], "distribution_center_expansion": ["news", "press_release", "about", "website"], "food_category_expansion": ["news", "press_release", "website", "brands"], "merchandising_hiring": ["careers", "job"], "new_brand_added": ["news", "press_release", "brands", "website"], "new_supplier_partnership": ["news", "press_release", "website", "brands", "about"], "premium_natural_portfolio_expansion": ["news", "press_release", "website", "brands"], "private_label_expansion": ["news", "press_release", "brands", "website"], "procurement_hiring": ["careers", "job"], "product_line_launch": ["news", "press_release", "website", "brands"], "purchasing_manager_hiring": ["careers", "job"], "regional_distribution_expansion": ["news", "press_release", "about", "website"], "retail_network_expansion": ["news", "press_release", "about", "website", "dealer"], "supplement_category_expansion": ["news", "press_release", "website", "brands"], "supplier_application_open": ["supplier", "website", "other", "about"], "treats_category_expansion": ["news", "press_release", "website", "brands"], "vendor_relations_expansion": ["careers", "job"]}, "signal_rules": {"acquisition_expansion": {"require_context_phrases": ["distributor", "distribution", "distributing", "pet", "wholesale"]}, "active_product_category_request": {"exclude_page_types": ["dealer", "careers", "job"], "require_context_phrases": ["food", "treat", "treats", "chew", "chews", "supplement", "supplements", "brands", "products", "lines", "suppliers", "manufacturers"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution", "wholesale account application", "open a wholesale account", "apply for a wholesale account", "retailer application", "become a retailer", "become a stockist", "retailer sign up", "retailer signup", "for retailers", "new retailer", "retail account", "dealer application", "become a dealer", "get a quote", "your quote", "your order", "our customers", "request a catalog", "request pricing"]}, "active_product_rfq": {"exclude_page_types": ["dealer"], "require_context_phrases": ["supplier", "suppliers", "manufacturer", "manufacturers", "vendor", "vendors", "source", "sourcing", "brands"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution", "wholesale account application", "open a wholesale account", "apply for a wholesale account", "retailer application", "become a retailer", "become a stockist", "retailer sign up", "retailer signup", "for retailers", "new retailer", "retail account", "dealer application", "become a dealer", "get a quote", "your quote", "your order", "our customers", "request a catalog", "request pricing"]}, "active_supplier_request": {"exclude_page_types": ["dealer"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution", "wholesale account application", "open a wholesale account", "apply for a wholesale account", "retailer application", "become a retailer", "become a stockist", "retailer sign up", "retailer signup", "for retailers", "new retailer", "retail account", "dealer application", "become a dealer"]}, "catalog_linecard_expansion": {"require_context_phrases": ["new", "added", "adds", "expanded", "expands", "expansion", "now includes", "additional"]}, "category_manager_hiring": {"require_page_types": ["careers", "job"]}, "food_category_expansion": {"require_context_phrases": ["dog food", "cat food", "pet food", "kibble", "wet food", "raw food", "freeze-dried", "fresh food", "frozen food", "diet", "diets", "formula", "formulas", "topper", "toppers"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "merchandising_hiring": {"require_page_types": ["careers", "job"]}, "new_brand_added": {"exclude_page_types": ["dealer"], "require_context_phrases": ["pet", "pets", "dog", "dogs", "cat", "cats", "canine", "feline", "puppy", "kitten", "treat", "treats", "chew", "chews", "pet food", "supplement", "supplements", "nutrition"], "suppress_phrases": ["looking for", "seeking", "submit", "interested in", "our new brand identity", "welcomes you", "looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "new_supplier_partnership": {"require_context_phrases": ["distribute", "distribution", "distributor", "distributing", "brand", "brands", "retailers", "pet specialty"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "premium_natural_portfolio_expansion": {"require_context_phrases": ["premium", "natural", "holistic", "limited ingredient", "limited-ingredient", "organic", "grain-free", "grain free", "human-grade", "specialty nutrition"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "private_label_expansion": {"require_context_phrases": ["expand", "expands", "expanded", "expanding", "launch", "launches", "new", "adds", "added"]}, "procurement_hiring": {"require_page_types": ["careers", "job"]}, "product_line_launch": {"require_context_phrases": ["pet", "pets", "dog", "dogs", "cat", "cats", "canine", "feline", "puppy", "kitten", "treat", "treats", "chew", "chews", "pet food", "supplement", "supplements", "nutrition"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "purchasing_manager_hiring": {"require_page_types": ["careers", "job"]}, "regional_distribution_expansion": {"require_context_phrases": ["distribution", "distributor", "wholesale", "retailers", "stores", "delivery"]}, "supplement_category_expansion": {"require_context_phrases": ["supplement", "supplements", "probiotic", "probiotics", "omega-3", "fish oil", "glucosamine", "joint", "calming", "multivitamin", "wellness", "functional nutrition"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "supplier_application_open": {"exclude_page_types": ["dealer"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution", "wholesale account application", "open a wholesale account", "apply for a wholesale account", "retailer application", "become a retailer", "become a stockist", "retailer sign up", "retailer signup", "for retailers", "new retailer", "retail account", "dealer application", "become a dealer"]}, "treats_category_expansion": {"require_context_phrases": ["treat", "treats", "chew", "chews", "bully stick", "bully sticks", "jerky", "biscuit", "biscuits", "dental"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "vendor_relations_expansion": {"require_page_types": ["careers", "job"]}}, "size_bands": [{"band": "micro", "max": 10, "min": 1}, {"band": "small", "max": 49, "min": 11}, {"band": "mid_market", "max": 500, "min": 50}, {"band": "large", "max": null, "min": 501}], "ui_labels": {"interest_types": {"CURRENTLY_CARRIED": "Currently carried", "EXPLICITLY_SEEKING": "Explicitly seeking", "INFERRED_FIT": "Inferred category fit", "RECENTLY_ADDED": "Recently onboarded"}, "segment": "Species", "title": "Pet Specialty Buying Intelligence \u00b7 US"}, "undated_confidence_factor": 0.75, "vehicle_platforms": [], "vehicle_segments": {"Cat": ["cat", "cats", "feline", "kitten", "kittens"], "Dog": ["dog", "dogs", "canine", "puppy", "puppies"], "Other": ["small animal", "small animals", "bird", "birds", "equine", "horse", "reptile", "ferret"]}}'::jsonb
)
on conflict (slug) do update
  set name = excluded.name, description = excluded.description,
      config = excluded.config, status = 'active';

-- Retain, do not delete, the legacy service.
update services set status = 'inactive' where slug = '3pl';

-- ---------------------------------------------------------------------
-- 3. SIGNALS + WEIGHTS  (27)
-- ---------------------------------------------------------------------
insert into service_signals
  (service_id, signal_type, signal_name, description, weight, decay_days, max_occurrences)
select s.id, v.signal_type, v.signal_name, v.description, v.weight, v.decay_days, v.max_occ
from services s,
(values
 ('active_supplier_request','Active Supplier Request','Distributor publicly asks for new suppliers, product proposals, vendor submissions or manufacturer partnerships',35,90,1),
 ('active_product_category_request','Active Product Category Request','Distributor explicitly requests products in a named pet food, treat, chew or supplement category',35,90,1),
 ('active_product_rfq','Active Product RFQ','Public request for quotation, product sourcing or a specific procurement opportunity',35,90,1),
 ('supplier_application_open','Supplier Application Open','An official supplier or vendor submission process invites brands to submit products. Evergreen openness to new brands, not an active purchasing requirement. Revalidated every 180 days by re-crawl',20,180,1),
 ('new_supplier_partnership','New Supplier Partnership','Distributor announces a new supplier or manufacturer partnership',27,180,1),
 ('new_brand_added','New Brand Added','Distributor adds a new pet food, treat or supplement brand',25,180,1),
 ('food_category_expansion','Food Category Expansion','Expansion into a new pet food category or a substantial addition to one',23,180,1),
 ('treats_category_expansion','Treats Category Expansion','Addition of new treat, chew or dental-product categories',23,180,1),
 ('supplement_category_expansion','Supplement Category Expansion','Addition of new functional pet supplements or wellness brands',25,180,1),
 ('premium_natural_portfolio_expansion','Premium or Natural Portfolio Expansion','Expansion into premium, natural, holistic, limited-ingredient or specialty nutrition',20,180,1),
 ('product_line_launch','Product Line Launch','Distributor announces a new product line or a material assortment launch',18,150,1),
 ('catalog_linecard_expansion','Catalog or Line Card Expansion','Material change to an official distributor catalog or line card',15,180,1),
 ('category_manager_hiring','Category Manager Hiring','Hiring people who manage pet food, treat, supplement or nutrition categories',17,120,1),
 ('purchasing_manager_hiring','Purchasing Manager Hiring','Hiring buyers or purchasing managers',17,120,1),
 ('procurement_hiring','Procurement Hiring','Hiring procurement, vendor management or sourcing professionals',15,120,1),
 ('merchandising_hiring','Merchandising Hiring','Hiring merchandising or assortment management roles',13,120,1),
 ('vendor_relations_expansion','Vendor Relations Expansion','Hiring or creating teams responsible for supplier and vendor relationships',15,150,1),
 ('distribution_center_expansion','Distribution Center Expansion','New warehouse, distribution facility or materially expanded distribution capacity',13,270,1),
 ('regional_distribution_expansion','Regional Distribution Expansion','New state or regional wholesale coverage',15,180,1),
 ('retail_network_expansion','Retail Network Expansion','Significant expansion in independent pet retailer coverage',12,180,1),
 ('private_label_expansion','Private Label Expansion','Expansion of the distributor private-label food, treat or supplement program',16,180,1),
 ('acquisition_expansion','Acquisition Expansion','Acquired another pet distributor or materially expanded distribution operations',12,270,1),
 ('pet_specialty_participation','Pet Specialty Participation','Verifiable participation in pet food, treats, chews or supplements',5,null,1),
 ('b2b_retailer_distribution','B2B Retailer Distribution','Supplies independent pet retailers or other B2B accounts - the distributor-to-retailer direction. Fit, not buying intent',6,null,1),
 ('brand_seeking_distribution','Brand Seeking Distribution','The company looks for distributors for its own products - the opposite direction',-25,null,1),
 ('retail_only_pet_store','Retail-Only Pet Store','Consumer store or boutique language with no wholesale operation',-15,null,1),
 ('pet_service_or_clinic','Pet Service or Clinic','Veterinary clinic, grooming, boarding, daycare or other pet service business',-15,null,1)
) as v(signal_type, signal_name, description, weight, decay_days, max_occ)
where s.slug = 'pet_specialty_food_treats_supplements'
on conflict (service_id, signal_type) do update
  set weight = excluded.weight,
      decay_days = excluded.decay_days,
      signal_name = excluded.signal_name,
      description = excluded.description;

-- ---------------------------------------------------------------------
-- 4. KEYWORDS  (308)
-- ---------------------------------------------------------------------
insert into service_keywords (service_id, keyword, category, signal_type, weight)
select s.id, v.keyword, v.category, v.signal_type, v.weight
from services s,
(values
 ('looking for new suppliers','intent','active_supplier_request',1),
 ('seeking new suppliers','intent','active_supplier_request',1),
 ('looking for suppliers','intent','active_supplier_request',1),
 ('seeking suppliers','intent','active_supplier_request',1),
 ('seeking new vendors','intent','active_supplier_request',1),
 ('looking for new vendors','intent','active_supplier_request',1),
 ('looking for new brands','intent','active_supplier_request',1),
 ('seeking new brands','intent','active_supplier_request',1),
 ('looking for manufacturers','intent','active_supplier_request',1),
 ('seeking manufacturers','intent','active_supplier_request',1),
 ('new supplier opportunities','intent','active_supplier_request',1),
 ('product proposals','intent','active_supplier_request',1),
 ('actively seeking new','intent','active_supplier_request',1),
 ('currently seeking new','intent','active_supplier_request',1),
 ('seeking manufacturer partners','intent','active_supplier_request',1),
 ('looking for new manufacturer partners','intent','active_supplier_request',1),
 ('seeking premium','category_request','active_product_category_request',1),
 ('looking for premium','category_request','active_product_category_request',1),
 ('seeking freeze-dried','category_request','active_product_category_request',1),
 ('looking for freeze-dried','category_request','active_product_category_request',1),
 ('seeking natural','category_request','active_product_category_request',1),
 ('looking for natural','category_request','active_product_category_request',1),
 ('seeking brands in','category_request','active_product_category_request',1),
 ('looking for brands in','category_request','active_product_category_request',1),
 ('seeking products in','category_request','active_product_category_request',1),
 ('looking for products in','category_request','active_product_category_request',1),
 ('currently seeking','category_request','active_product_category_request',1),
 ('actively seeking','category_request','active_product_category_request',1),
 ('now accepting submissions for','category_request','active_product_category_request',1),
 ('seeking new lines of','category_request','active_product_category_request',1),
 ('looking to add','category_request','active_product_category_request',1),
 ('seeking to add','category_request','active_product_category_request',1),
 ('request for quote','intent','active_product_rfq',1),
 ('request for quotation','intent','active_product_rfq',1),
 ('rfq','intent','active_product_rfq',1),
 ('request for proposal','intent','active_product_rfq',1),
 ('seeking quotes','intent','active_product_rfq',1),
 ('looking to source','intent','active_product_rfq',1),
 ('now sourcing','intent','active_product_rfq',1),
 ('we are sourcing','intent','active_product_rfq',1),
 ('sourcing request','intent','active_product_rfq',1),
 ('quotes from manufacturers','intent','active_product_rfq',1),
 ('quotes from suppliers','intent','active_product_rfq',1),
 ('supplier application','intent','supplier_application_open',1),
 ('vendor application','intent','supplier_application_open',1),
 ('new vendor application','intent','supplier_application_open',1),
 ('vendor inquiry form','intent','supplier_application_open',1),
 ('supplier inquiry','intent','supplier_application_open',1),
 ('become a supplier','intent','supplier_application_open',1),
 ('become a vendor','intent','supplier_application_open',1),
 ('vendor submission','intent','supplier_application_open',1),
 ('supplier submission','intent','supplier_application_open',1),
 ('vendor onboarding','intent','supplier_application_open',1),
 ('new vendor setup','intent','supplier_application_open',1),
 ('vendor information form','intent','supplier_application_open',1),
 ('supplier registration','intent','supplier_application_open',1),
 ('vendor registration','intent','supplier_application_open',1),
 ('prospective vendors','intent','supplier_application_open',1),
 ('prospective suppliers','intent','supplier_application_open',1),
 ('product submission form','intent','supplier_application_open',1),
 ('new brand submission','intent','supplier_application_open',1),
 ('brand submission','intent','supplier_application_open',1),
 ('submit your product','intent','supplier_application_open',1),
 ('submit your products','intent','supplier_application_open',1),
 ('submit your brand','intent','supplier_application_open',1),
 ('accepting new brands','intent','supplier_application_open',1),
 ('accepting new vendors','intent','supplier_application_open',1),
 ('brand application','intent','supplier_application_open',1),
 ('new brand application','intent','supplier_application_open',1),
 ('interested in becoming a vendor','intent','supplier_application_open',1),
 ('interested in becoming a supplier','intent','supplier_application_open',1),
 ('distribution agreement','expansion','new_supplier_partnership',1),
 ('distribution partnership','expansion','new_supplier_partnership',1),
 ('exclusive distribution','expansion','new_supplier_partnership',1),
 ('exclusive distributor for','expansion','new_supplier_partnership',1),
 ('agreement to distribute','expansion','new_supplier_partnership',1),
 ('will now distribute','expansion','new_supplier_partnership',1),
 ('now distributing','expansion','new_supplier_partnership',1),
 ('now distributes','expansion','new_supplier_partnership',1),
 ('named exclusive distributor','expansion','new_supplier_partnership',1),
 ('appointed as distributor','expansion','new_supplier_partnership',1),
 ('distribution deal','expansion','new_supplier_partnership',1),
 ('expands distribution with','expansion','new_supplier_partnership',1),
 ('now available through','expansion','new_supplier_partnership',1),
 ('partnered with','expansion','new_supplier_partnership',0.6),
 ('new partnership with','expansion','new_supplier_partnership',0.6),
 ('announces partnership','expansion','new_supplier_partnership',0.6),
 ('partners with','expansion','new_supplier_partnership',0.6),
 ('added to our lineup','expansion','new_brand_added',1),
 ('added to its lineup','expansion','new_brand_added',1),
 ('adds brand','expansion','new_brand_added',1),
 ('joins our brand portfolio','expansion','new_brand_added',1),
 ('joins our lineup','expansion','new_brand_added',1),
 ('now carrying','expansion','new_brand_added',1),
 ('now carries','expansion','new_brand_added',1),
 ('now stocking','expansion','new_brand_added',1),
 ('newest brand','expansion','new_brand_added',1),
 ('new to our line','expansion','new_brand_added',1),
 ('added to our line card','expansion','new_brand_added',1),
 ('adds new brands','expansion','new_brand_added',1),
 ('welcomes','expansion','new_brand_added',1),
 ('expands brand portfolio','expansion','new_brand_added',1),
 ('expanded brand portfolio','expansion','new_brand_added',1),
 ('new brand','expansion','new_brand_added',0.7),
 ('new brands','expansion','new_brand_added',0.7),
 ('expands its','food_expansion','food_category_expansion',1),
 ('expanded its','food_expansion','food_category_expansion',1),
 ('expanding its','food_expansion','food_category_expansion',1),
 ('expands our','food_expansion','food_category_expansion',1),
 ('expanding our','food_expansion','food_category_expansion',1),
 ('expansion into','food_expansion','food_category_expansion',1),
 ('expanding into','food_expansion','food_category_expansion',1),
 ('new category','food_expansion','food_category_expansion',1),
 ('new categories','food_expansion','food_category_expansion',1),
 ('adds new','food_expansion','food_category_expansion',1),
 ('added new','food_expansion','food_category_expansion',1),
 ('broadens its','food_expansion','food_category_expansion',1),
 ('now offers','food_expansion','food_category_expansion',1),
 ('now offering','food_expansion','food_category_expansion',1),
 ('expands its','treat_expansion','treats_category_expansion',1),
 ('expanded its','treat_expansion','treats_category_expansion',1),
 ('expanding its','treat_expansion','treats_category_expansion',1),
 ('expands our','treat_expansion','treats_category_expansion',1),
 ('expanding our','treat_expansion','treats_category_expansion',1),
 ('expansion into','treat_expansion','treats_category_expansion',1),
 ('expanding into','treat_expansion','treats_category_expansion',1),
 ('new category','treat_expansion','treats_category_expansion',1),
 ('new categories','treat_expansion','treats_category_expansion',1),
 ('adds new','treat_expansion','treats_category_expansion',1),
 ('added new','treat_expansion','treats_category_expansion',1),
 ('broadens its','treat_expansion','treats_category_expansion',1),
 ('now offers','treat_expansion','treats_category_expansion',1),
 ('now offering','treat_expansion','treats_category_expansion',1),
 ('expands its','supplement_expansion','supplement_category_expansion',1),
 ('expanded its','supplement_expansion','supplement_category_expansion',1),
 ('expanding its','supplement_expansion','supplement_category_expansion',1),
 ('expands our','supplement_expansion','supplement_category_expansion',1),
 ('expanding our','supplement_expansion','supplement_category_expansion',1),
 ('expansion into','supplement_expansion','supplement_category_expansion',1),
 ('expanding into','supplement_expansion','supplement_category_expansion',1),
 ('new category','supplement_expansion','supplement_category_expansion',1),
 ('new categories','supplement_expansion','supplement_category_expansion',1),
 ('adds new','supplement_expansion','supplement_category_expansion',1),
 ('added new','supplement_expansion','supplement_category_expansion',1),
 ('broadens its','supplement_expansion','supplement_category_expansion',1),
 ('now offers','supplement_expansion','supplement_category_expansion',1),
 ('now offering','supplement_expansion','supplement_category_expansion',1),
 ('expands its','premium_expansion','premium_natural_portfolio_expansion',1),
 ('expanded its','premium_expansion','premium_natural_portfolio_expansion',1),
 ('expanding its','premium_expansion','premium_natural_portfolio_expansion',1),
 ('expands our','premium_expansion','premium_natural_portfolio_expansion',1),
 ('expanding our','premium_expansion','premium_natural_portfolio_expansion',1),
 ('expansion into','premium_expansion','premium_natural_portfolio_expansion',1),
 ('expanding into','premium_expansion','premium_natural_portfolio_expansion',1),
 ('new category','premium_expansion','premium_natural_portfolio_expansion',1),
 ('new categories','premium_expansion','premium_natural_portfolio_expansion',1),
 ('adds new','premium_expansion','premium_natural_portfolio_expansion',1),
 ('added new','premium_expansion','premium_natural_portfolio_expansion',1),
 ('broadens its','premium_expansion','premium_natural_portfolio_expansion',1),
 ('now offers','premium_expansion','premium_natural_portfolio_expansion',1),
 ('now offering','premium_expansion','premium_natural_portfolio_expansion',1),
 ('new product line','expansion','product_line_launch',0.8),
 ('new product lines','expansion','product_line_launch',0.8),
 ('launches new','expansion','product_line_launch',0.8),
 ('introduces new','expansion','product_line_launch',0.8),
 ('new for 2026','expansion','product_line_launch',0.8),
 ('new for 2027','expansion','product_line_launch',0.8),
 ('product launch','expansion','product_line_launch',0.8),
 ('new products for','expansion','product_line_launch',0.8),
 ('line card','expansion','catalog_linecard_expansion',0.8),
 ('linecard','expansion','catalog_linecard_expansion',0.8),
 ('new catalog','expansion','catalog_linecard_expansion',0.8),
 ('2026 catalog','expansion','catalog_linecard_expansion',0.8),
 ('2027 catalog','expansion','catalog_linecard_expansion',0.8),
 ('catalog expansion','expansion','catalog_linecard_expansion',0.8),
 ('new skus','expansion','catalog_linecard_expansion',0.8),
 ('new items added','expansion','catalog_linecard_expansion',0.8),
 ('category manager','hiring','category_manager_hiring',1),
 ('category director','hiring','category_manager_hiring',1),
 ('category specialist','hiring','category_manager_hiring',1),
 ('director of category management','hiring','category_manager_hiring',1),
 ('senior category manager','hiring','category_manager_hiring',1),
 ('purchasing manager','hiring','purchasing_manager_hiring',1),
 ('purchasing director','hiring','purchasing_manager_hiring',1),
 ('director of purchasing','hiring','purchasing_manager_hiring',1),
 ('buyer','hiring','purchasing_manager_hiring',1),
 ('senior buyer','hiring','purchasing_manager_hiring',1),
 ('associate buyer','hiring','purchasing_manager_hiring',1),
 ('product buyer','hiring','purchasing_manager_hiring',1),
 ('purchasing agent','hiring','purchasing_manager_hiring',1),
 ('inventory buyer','hiring','purchasing_manager_hiring',1),
 ('procurement manager','hiring','procurement_hiring',1),
 ('procurement specialist','hiring','procurement_hiring',1),
 ('sourcing manager','hiring','procurement_hiring',1),
 ('sourcing specialist','hiring','procurement_hiring',1),
 ('strategic sourcing','hiring','procurement_hiring',1),
 ('purchasing coordinator','hiring','procurement_hiring',1),
 ('purchasing analyst','hiring','procurement_hiring',1),
 ('merchandising manager','hiring','merchandising_hiring',1),
 ('merchandise manager','hiring','merchandising_hiring',1),
 ('assortment manager','hiring','merchandising_hiring',1),
 ('director of merchandising','hiring','merchandising_hiring',1),
 ('merchandise planner','hiring','merchandising_hiring',1),
 ('vendor relations','hiring','vendor_relations_expansion',1),
 ('supplier relations','hiring','vendor_relations_expansion',1),
 ('vendor manager','hiring','vendor_relations_expansion',1),
 ('vendor management','hiring','vendor_relations_expansion',1),
 ('brand partnerships manager','hiring','vendor_relations_expansion',1),
 ('new distribution center','capacity','distribution_center_expansion',1),
 ('new distribution centre','capacity','distribution_center_expansion',1),
 ('new warehouse','capacity','distribution_center_expansion',1),
 ('opens distribution center','capacity','distribution_center_expansion',1),
 ('opened a new distribution','capacity','distribution_center_expansion',1),
 ('warehouse expansion','capacity','distribution_center_expansion',1),
 ('expanded warehouse','capacity','distribution_center_expansion',1),
 ('expands distribution center','capacity','distribution_center_expansion',1),
 ('additional distribution center','capacity','distribution_center_expansion',1),
 ('square-foot distribution','capacity','distribution_center_expansion',1),
 ('square foot distribution','capacity','distribution_center_expansion',1),
 ('square-foot warehouse','capacity','distribution_center_expansion',1),
 ('square foot warehouse','capacity','distribution_center_expansion',1),
 ('new facility','capacity','distribution_center_expansion',0.6),
 ('breaks ground','capacity','distribution_center_expansion',0.6),
 ('new territory','capacity','regional_distribution_expansion',1),
 ('new territories','capacity','regional_distribution_expansion',1),
 ('expands into','capacity','regional_distribution_expansion',1),
 ('now serving','capacity','regional_distribution_expansion',1),
 ('expanded coverage','capacity','regional_distribution_expansion',1),
 ('new region','capacity','regional_distribution_expansion',1),
 ('regional expansion','capacity','regional_distribution_expansion',1),
 ('new delivery routes','capacity','regional_distribution_expansion',1),
 ('expands its footprint','capacity','regional_distribution_expansion',1),
 ('new retail accounts','capacity','retail_network_expansion',1),
 ('more independent retailers','capacity','retail_network_expansion',1),
 ('expands retailer network','capacity','retail_network_expansion',1),
 ('growing retailer network','capacity','retail_network_expansion',1),
 ('independent retailers across','capacity','retail_network_expansion',1),
 ('retail partners across','capacity','retail_network_expansion',1),
 ('now supplying','capacity','retail_network_expansion',1),
 ('new retailer accounts','capacity','retail_network_expansion',1),
 ('private label','capacity','private_label_expansion',1),
 ('private-label','capacity','private_label_expansion',1),
 ('our own brand','capacity','private_label_expansion',1),
 ('exclusive brand','capacity','private_label_expansion',1),
 ('house brand','capacity','private_label_expansion',1),
 ('has acquired','capacity','acquisition_expansion',1),
 ('completed the acquisition','capacity','acquisition_expansion',1),
 ('acquisition of','capacity','acquisition_expansion',1),
 ('acquires','capacity','acquisition_expansion',1),
 ('merges with','capacity','acquisition_expansion',1),
 ('adds distribution','capacity','acquisition_expansion',1),
 ('pet food','fit','pet_specialty_participation',0.9),
 ('pet specialty','fit','pet_specialty_participation',0.9),
 ('dog food','fit','pet_specialty_participation',0.9),
 ('cat food','fit','pet_specialty_participation',0.9),
 ('pet treats','fit','pet_specialty_participation',0.9),
 ('dog treats','fit','pet_specialty_participation',0.9),
 ('cat treats','fit','pet_specialty_participation',0.9),
 ('dog chews','fit','pet_specialty_participation',0.9),
 ('pet supplements','fit','pet_specialty_participation',0.9),
 ('pet nutrition','fit','pet_specialty_participation',0.9),
 ('bully sticks','fit','pet_specialty_participation',0.9),
 ('pet products','fit','pet_specialty_participation',0.9),
 ('independent pet retailers','fit','b2b_retailer_distribution',0.9),
 ('independent pet stores','fit','b2b_retailer_distribution',0.9),
 ('independent retailers','fit','b2b_retailer_distribution',0.9),
 ('pet specialty retailers','fit','b2b_retailer_distribution',0.9),
 ('wholesale account','fit','b2b_retailer_distribution',0.9),
 ('retailer accounts','fit','b2b_retailer_distribution',0.9),
 ('serving retailers','fit','b2b_retailer_distribution',0.9),
 ('wholesale only','fit','b2b_retailer_distribution',0.9),
 ('trade only','fit','b2b_retailer_distribution',0.9),
 ('become a retailer','fit','b2b_retailer_distribution',0.9),
 ('retailer application','fit','b2b_retailer_distribution',0.9),
 ('wholesale distributor','fit','b2b_retailer_distribution',0.9),
 ('pet specialty distributor','fit','b2b_retailer_distribution',0.9),
 ('retail partners','fit','b2b_retailer_distribution',0.9),
 ('looking for distributors','negative','brand_seeking_distribution',1),
 ('looking for a distributor','negative','brand_seeking_distribution',1),
 ('seeking distributors','negative','brand_seeking_distribution',1),
 ('seeking a distributor','negative','brand_seeking_distribution',1),
 ('become a distributor','negative','brand_seeking_distribution',1),
 ('distributor inquiries','negative','brand_seeking_distribution',1),
 ('distributor opportunities','negative','brand_seeking_distribution',1),
 ('distributors wanted','negative','brand_seeking_distribution',1),
 ('seeking nationwide distribution','negative','brand_seeking_distribution',1),
 ('looking for distribution','negative','brand_seeking_distribution',1),
 ('distribute our products','negative','brand_seeking_distribution',1),
 ('interested in distributing our products','negative','brand_seeking_distribution',1),
 ('wholesale inquiries for our brand','negative','brand_seeking_distribution',1),
 ('visit our store','negative','retail_only_pet_store',0.9),
 ('store hours','negative','retail_only_pet_store',0.9),
 ('in-store pickup','negative','retail_only_pet_store',0.9),
 ('curbside pickup','negative','retail_only_pet_store',0.9),
 ('shop our store','negative','retail_only_pet_store',0.9),
 ('pet boutique','negative','retail_only_pet_store',0.9),
 ('frequent buyer program','negative','retail_only_pet_store',0.9),
 ('self-serve dog wash','negative','retail_only_pet_store',0.9),
 ('veterinary clinic','negative','pet_service_or_clinic',0.9),
 ('animal hospital','negative','pet_service_or_clinic',0.9),
 ('schedule an appointment','negative','pet_service_or_clinic',0.9),
 ('grooming appointment','negative','pet_service_or_clinic',0.9),
 ('dog grooming','negative','pet_service_or_clinic',0.9),
 ('boarding and daycare','negative','pet_service_or_clinic',0.9),
 ('doggy daycare','negative','pet_service_or_clinic',0.9),
 ('pet sitting','negative','pet_service_or_clinic',0.9),
 ('dog walking','negative','pet_service_or_clinic',0.9),
 ('wellness exams','negative','pet_service_or_clinic',0.9)
) as v(keyword, category, signal_type, weight)
where s.slug = 'pet_specialty_food_treats_supplements'
on conflict (service_id, keyword, category) do update
  set weight = excluded.weight, signal_type = excluded.signal_type;

-- ---------------------------------------------------------------------
-- 5. DECISION-MAKER ROLES  (34)
-- ---------------------------------------------------------------------
insert into service_roles (service_id, title_pattern, role_priority)
select s.id, v.pattern, v.prio
from services s,
(values
 ('vp of purchasing',1),
 ('vice president of purchasing',1),
 ('vp purchasing',1),
 ('vice president, purchasing',1),
 ('director of purchasing',2),
 ('purchasing director',2),
 ('head of purchasing',2),
 ('purchasing manager',3),
 ('category director',4),
 ('director of category management',4),
 ('category manager',5),
 ('senior category manager',5),
 ('director of merchandising',6),
 ('merchandising director',6),
 ('product line manager',7),
 ('product manager',8),
 ('procurement manager',9),
 ('sourcing manager',10),
 ('vendor relations manager',11),
 ('supplier relations manager',11),
 ('senior buyer',9),
 ('buyer',10),
 ('owner',3),
 ('co-owner',3),
 ('founder',4),
 ('co-founder',4),
 ('president',4),
 ('ceo',4),
 ('chief executive officer',4),
 ('coo',6),
 ('chief operating officer',6),
 ('director of business development',12),
 ('vp of business development',12),
 ('vice president',13)
) as v(pattern, prio)
where s.slug = 'pet_specialty_food_treats_supplements'
on conflict (service_id, title_pattern) do update set role_priority = excluded.role_priority;

-- ---------------------------------------------------------------------
-- 6. DISCOVERY QUERIES  (84: {1: 14, 2: 29, 3: 33, 4: 8})
-- ---------------------------------------------------------------------
insert into discovery_queries (service_id, query, country, priority)
select s.id, v.query, v.country, v.priority
from services s,
(values
 ('pet food distributor accepting new brands', 'US', 1),
 ('pet specialty distributor become a vendor', 'US', 1),
 ('pet food distributor supplier application', 'US', 1),
 ('pet distributor submit your product', 'US', 1),
 ('pet food wholesale vendor application', 'US', 1),
 ('distributor looking for new pet food brands', 'US', 1),
 ('pet specialty distributor seeking new suppliers', 'US', 1),
 ('pet treats distributor brand submission', 'US', 1),
 ('pet supplement distributor supplier opportunities', 'US', 1),
 ('wholesale pet product sourcing new suppliers', 'US', 1),
 ('new pet food supplier partnerships distributor', 'US', 1),
 ('pet nutrition distributor new product submissions', 'US', 1),
 ('pet distributor new vendor setup', 'US', 1),
 ('pet specialty wholesaler vendor onboarding', 'US', 1),
 ('pet food distributor new brand partnership', 'US', 2),
 ('pet specialty distributor expanding portfolio', 'US', 2),
 ('pet food distributor adds new treats brand', 'US', 2),
 ('dog supplement distribution partnership', 'US', 2),
 ('cat food distributor new product line', 'US', 2),
 ('premium pet food wholesale expansion', 'US', 2),
 ('natural pet treats distribution agreement', 'US', 2),
 ('pet distributor expands supplement portfolio', 'US', 2),
 ('functional pet nutrition new distribution agreement', 'US', 2),
 ('pet food distributor adds new manufacturer', 'US', 2),
 ('pet distributor expanding category assortment', 'US', 2),
 ('now available through pet specialty distributor', 'US', 2),
 ('expands distribution with pet specialty distributor', 'US', 2),
 ('premium dog food distributor adds new brand', 'US', 2),
 ('premium dog food wholesale distributor for pet retailers', 'US', 3),
 ('premium cat food distributor adds new brand', 'US', 2),
 ('premium cat food wholesale distributor for pet retailers', 'US', 3),
 ('fresh and frozen pet food distributor adds new brand', 'US', 2),
 ('fresh and frozen pet food wholesale distributor for pet retailers', 'US', 3),
 ('freeze-dried raw pet food distributor adds new brand', 'US', 2),
 ('freeze-dried raw pet food wholesale distributor for pet retailers', 'US', 3),
 ('natural dog treats distributor adds new brand', 'US', 2),
 ('natural dog treats wholesale distributor for pet retailers', 'US', 3),
 ('functional dog treats distributor adds new brand', 'US', 2),
 ('functional dog treats wholesale distributor for pet retailers', 'US', 3),
 ('dental chews distributor adds new brand', 'US', 2),
 ('dental chews wholesale distributor for pet retailers', 'US', 3),
 ('single-ingredient dog treats distributor adds new brand', 'US', 2),
 ('single-ingredient dog treats wholesale distributor for pet retailers', 'US', 3),
 ('bully sticks and natural chews distributor adds new brand', 'US', 2),
 ('bully sticks and natural chews wholesale distributor for pet retailers', 'US', 3),
 ('dog joint supplements distributor adds new brand', 'US', 2),
 ('dog joint supplements wholesale distributor for pet retailers', 'US', 3),
 ('pet probiotics distributor adds new brand', 'US', 2),
 ('pet probiotics wholesale distributor for pet retailers', 'US', 3),
 ('dog calming chews distributor adds new brand', 'US', 2),
 ('dog calming chews wholesale distributor for pet retailers', 'US', 3),
 ('pet omega-3 fish oil distributor adds new brand', 'US', 2),
 ('pet omega-3 fish oil wholesale distributor for pet retailers', 'US', 3),
 ('skin and coat supplements for dogs distributor adds new brand', 'US', 2),
 ('skin and coat supplements for dogs wholesale distributor for pet retailers', 'US', 3),
 ('senior pet nutrition distributor adds new brand', 'US', 2),
 ('senior pet nutrition wholesale distributor for pet retailers', 'US', 3),
 ('functional pet wellness supplements distributor adds new brand', 'US', 2),
 ('functional pet wellness supplements wholesale distributor for pet retailers', 'US', 3),
 ('pet food distributors USA', 'US', 3),
 ('pet specialty food wholesalers', 'US', 3),
 ('independent pet store wholesale distributors', 'US', 3),
 ('natural pet food distributors', 'US', 3),
 ('premium pet food wholesale suppliers', 'US', 3),
 ('dog food wholesale distributors', 'US', 3),
 ('cat food wholesale distributors', 'US', 3),
 ('pet treat distributors USA', 'US', 3),
 ('dog chews wholesale distributors', 'US', 3),
 ('pet supplement wholesale distributors', 'US', 3),
 ('functional pet nutrition distributors', 'US', 3),
 ('specialty pet product distribution companies', 'US', 3),
 ('regional pet food wholesalers', 'US', 3),
 ('pet specialty distributors supplying independent retailers', 'US', 3),
 ('frozen raw pet food distributors', 'US', 3),
 ('pet health and wellness product wholesalers', 'US', 3),
 ('pet food distribution companies supplying retail stores', 'US', 3),
 ('pet food distributor purchasing manager hiring', 'US', 4),
 ('pet distributor category manager jobs', 'US', 4),
 ('pet food wholesaler procurement hiring', 'US', 4),
 ('pet specialty distributor warehouse expansion', 'US', 4),
 ('pet food distributor new distribution center', 'US', 4),
 ('pet distributor expanding retailer network', 'US', 4),
 ('pet product distributor acquisition', 'US', 4),
 ('pet food wholesaler new regional operations', 'US', 4)
) as v(query, country, priority)
where s.slug = 'pet_specialty_food_treats_supplements'
  and not exists (
    select 1 from discovery_queries dq
    where dq.service_id = s.id and dq.query = v.query
      and dq.country is not distinct from v.country);

-- Verify:
-- select slug, status from services;
-- select priority as tier, count(*) from discovery_queries dq
--   join services s on s.id = dq.service_id
--   where s.slug = 'pet_specialty_food_treats_supplements' group by priority order by priority;


-- =====================================================================
--  DONE. Verify with:
-- =====================================================================
select
  (select count(*) from services)          as services,
  (select count(*) from service_signals)   as signals,
  (select count(*) from service_keywords)  as keywords,
  (select count(*) from discovery_queries) as queries,
  (select count(*) from service_roles)     as roles;
-- Expect: 3 services, 68 signals, 691 keywords, 781 queries, 106 roles

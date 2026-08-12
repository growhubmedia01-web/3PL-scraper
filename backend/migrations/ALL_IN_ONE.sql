-- =====================================================================
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
--          + 004_broaden_beyond_ecommerce.sql
--  Rebuild: python -m scripts.build_all_in_one
--  Generated 2026-08-12
-- =====================================================================



-- =====================================================================
--  PART 001  |  SCHEMA � tables, indexes, triggers
-- =====================================================================

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


-- =====================================================================
--  PART 002  |  ROW LEVEL SECURITY � policies
-- =====================================================================

-- =====================================================================
-- Row Level Security (§53)
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
--  PART 003  |  SEED � the 3PL service configuration
-- =====================================================================

-- =====================================================================
-- 3PL SERVICE CONFIGURATION (§21, §24, §26)
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
-- SIGNALS + WEIGHTS (§24, §26)
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
-- KEYWORDS (§13). A keyword alone must never qualify a company.
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
-- DISCOVERY QUERIES (§14)
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
-- DECISION MAKER ROLE PRIORITY (§21)
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
--  PART 004  |  BROADEN � wholesale, manufacturing, retail, subscription segments
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
--  DONE. Verify with:
-- =====================================================================
select
  (select count(*) from services)          as services,
  (select count(*) from service_signals)   as signals,
  (select count(*) from service_keywords)  as keywords,
  (select count(*) from discovery_queries) as queries,
  (select count(*) from service_roles)     as roles;
-- Expect: 1 service, 23 signals, 164 keywords, 66 queries, 26 roles

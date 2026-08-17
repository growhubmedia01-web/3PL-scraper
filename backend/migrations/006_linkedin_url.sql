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

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

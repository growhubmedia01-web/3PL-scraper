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

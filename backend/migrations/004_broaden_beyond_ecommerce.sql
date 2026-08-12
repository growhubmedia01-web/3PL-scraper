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

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

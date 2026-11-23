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
  '{"adjacent_categories": {"Chews": ["Dog and Cat Treats"], "Dog and Cat Treats": ["Chews"], "Pet Supplements": ["Dog and Cat Treats"], "Specialty Cat Food": ["Dog and Cat Treats"], "Specialty Dog Food": ["Dog and Cat Treats", "Pet Supplements"]}, "ai_analysis_min_raw_score": 20, "ai_extra_fields": {"company_size_qualification": "\"mid_market\" | \"small\" | \"micro\" | \"large\" | \"unknown\" - never guess", "distribution_partnerships": "[string] - brands named in the evidence", "distributor_qualification": "\"qualified\" | \"possible\" | \"not_qualified\" | \"unknown\"", "distributor_qualification_reason": "string citing evidence", "evidence_gaps": "[string] - what is unknown or uncertain", "likely_decision_roles": "[string] - job titles, never personal contact data", "product_categories": "[string] - only categories named in the evidence", "products_mentioned": "[string] - only products named in the evidence", "purchasing_hiring": "[string]", "recent_expansion_activity": "[string]", "recently_added_brands": "[string] - brands named in the evidence", "species_and_formats": "[string] - only as stated in the evidence", "supplier_onboarding_evidence": "[string]", "wholesale_distribution_model": "string - only what the evidence shows"}, "ai_grounded_fields": ["likely_services", "product_categories", "products_mentioned", "distribution_partnerships", "recently_added_brands"], "ai_probability_field": "buying_intent_probability", "ai_system_prompt": "You are a B2B supply-chain analyst for pet food, treat and supplement manufacturers that want to sell through US pet specialty distributors. Analyze whether this company is a genuine US pet specialty distributor or wholesaler and determine what public evidence indicates that it is purchasing, onboarding or expanding its portfolio of pet food, treats, chews and supplements. Commercial direction matters: a distributor inviting retailers to open wholesale accounts is selling, not buying; a brand looking for distributors is the opposite direction and is not a buyer; a pet store buying from wholesalers is retail purchasing. Distinguish seeking suppliers, accepting supplier submissions, recently onboarding a supplier, currently carrying a product and a possible category fit - these are different claims. Use only the supplied evidence. Never invent products, brands, ingredients, purchasing requirements, employee counts or revenue. A general growth announcement is not a specific purchasing requirement. Product health or quality statements are the company''s own marketing claims: never describe them as proven, veterinary or FDA-approved, and never turn ''supports joint health'' into a disease treatment claim.", "ai_task": "Analyze whether this company is a genuine US pet specialty distributor or wholesaler and determine what public evidence indicates that it is purchasing, onboarding or expanding its portfolio of pet food, treats, chews and supplements. Put the probability that it is actively expanding its supplier or product portfolio in service_probability. Put only product categories named in the evidence in likely_services. If no specific product requirement is identifiable, say exactly: Specific product demand not publicly disclosed.", "brand_patterns": ["distribution (?:agreement|partnership|deal) with ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:exclusive|official|authorized|master) (?:US |U\\.S\\. |North American |national )?distributor (?:of|for) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:now|will) (?:distribute|distributing|carry|carrying|stock|stocking) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})", "(?:added|adds|adding|welcomes|welcomed) ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3}) (?:to (?:its|our|the) (?:lineup|line card|brand portfolio|portfolio|catalog|offering|assortment))", "([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3}) (?:is |are )?now available (?:through|via|from) ", "([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3}) expands (?:its )?distribution (?:with|through) ", "partner(?:ed|ship)? with ([A-Z][A-Za-z0-9&''\\-]+(?:\\s+[A-Z][A-Za-z0-9&''\\-]+){0,3})"], "carried_page_types": ["brands", "website", "about", "other"], "company_type_markers": {"b2b_marketplace": ["verified suppliers", "b2b sourcing platform", "sourcing platform", "all suppliers", "low moq", "post a buying request", "live requests", "supplier directory", "find suppliers", "list your products", "trade assurance", "become a supplier"], "brand_owner": ["find a retailer", "store locator", "where to buy", "looking for distributors", "become a distributor", "distributor inquiries", "subscribe and save", "shop now", "our products are sold", "available at fine pet retailers", "add to cart", "free shipping on orders", "orders ship within", "shop all", "shop the collection", "our story", "new arrivals", "join our pack", "learn more about these products"], "manufacturer": ["we manufacture", "our kitchen", "our manufacturing facility", "manufacturing facility", "manufactured in", "co-packer", "co-manufacturing", "our production facility", "we make our", "made in our own"], "pet_retailer": ["visit our store", "store hours", "in-store pickup", "curbside pickup", "shop our store", "pet boutique", "frequent buyer program", "self-serve dog wash", "our store", "locally owned pet store"], "pet_service_provider": ["dog grooming", "grooming appointment", "boarding and daycare", "doggy daycare", "pet sitting", "dog walking", "dog training classes"], "pet_specialty_distributor": ["wholesale distributor", "wholesale distribution", "distributor of", "we distribute", "pet specialty distributor", "pet food distributor", "independent pet retailers", "independent pet stores", "independent retailers", "pet specialty retailers", "retail partners", "wholesale account", "retailer accounts", "serving retailers", "brands we carry", "brands we distribute", "line card", "linecard", "distribution center", "distribution centers", "wholesale only", "trade only", "become a retailer", "retailer application", "b2b", "delivery routes", "sales territory", "master distributor"], "software_or_service_vendor": ["book a demo", "request a demo", "free trial", "start your free trial", "go to dashboard", "pricing plans", "per month", "saas", "software platform", "find the buyers", "find retailers for your", "sign up free", "api access"], "veterinary_clinic": ["veterinary clinic", "animal hospital", "schedule an appointment", "our veterinarians", "wellness exams", "spay and neuter"], "veterinary_supplier": ["veterinary distributor", "veterinary practices", "animal health distributor", "veterinary clinics nationwide", "serving veterinarians"]}, "crawl_link_first_page_types": ["supplier", "brands", "news", "careers", "about"], "crawl_max_pages": 16, "crawl_priority_paths": [["/", "website"], ["/about", "about"], ["/about-us", "about"], ["/brands", "brands"], ["/our-brands", "brands"], ["/line-card", "brands"], ["/vendors", "supplier"], ["/become-a-vendor", "supplier"], ["/info/become-a-vendor", "supplier"], ["/vendor-application", "supplier"], ["/suppliers", "supplier"], ["/new-vendors", "supplier"], ["/news", "news"], ["/press", "news"], ["/careers", "careers"], ["/retailers", "dealer"], ["/wholesale-account", "dealer"], ["/contact", "other"]], "decision_maker_optional_threshold": 30, "decision_maker_threshold": 40, "dimension_caps": {"intent": 40}, "discovery_blocked_domains": ["petfoodprocessing.net", "petfoodindustry.com", "petbusiness.com", "petage.com", "globalpetexpo.org", "superzoo.org", "petfoodforum.com", "petproductnews.com", "americanpetproducts.org", "appa.org", "fda.gov", "aafco.org", "nasc.cc", "chewy.com", "petco.com", "petsmart.com", "amazon.com", "walmart.com", "target.com", "tractorsupply.com", "petsupermarket.com", "petvalu.com", "thomasnet.com", "zoominfo.com", "dnb.com", "manta.com", "bbb.org", "yellowpages.com", "yelp.com", "mapquest.com", "rocketreach.co", "apollo.io", "faire.com", "rangeme.com", "facebook.com", "linkedin.com", "instagram.com", "youtube.com", "reddit.com", "indeed.com", "glassdoor.com"], "exclude_logistics_providers": false, "excluded_business_types": ["marketing agency", "seo agency", "web development agency", "digital agency", "software company", "saas platform", "consulting firm", "law firm", "recruitment agency", "staffing agency", "insurance agency", "trade publication", "animal shelter", "rescue organization"], "external_fetchers": ["ats"], "external_query_templates": [["press_release", "\"{name}\" \"now available through\" OR \"distribution partnership\" OR \"distribution agreement\" OR \"adds\"", "news"], ["news", "\"{name}\" site:petfoodprocessing.net OR site:petfoodindustry.com OR site:petbusiness.com OR site:petage.com", "web"], ["supplier", "\"{name}\" \"vendor application\" OR \"become a vendor\" OR \"submit your product\" OR \"new brands\"", "web"], ["job", "\"{name}\" \"category manager\" OR \"purchasing manager\" OR \"buyer\" OR \"procurement\"", "web"], ["press_release", "\"{name}\" \"distribution center\" OR warehouse OR acquires OR acquisition", "news"]], "fetch_external_articles": 3, "fit_multipliers": {"company_type": {"default": 0.5, "hybrid_distributor_manufacturer": 0.9, "hybrid_distributor_retailer": 0.8, "pet_specialty_distributor": 1.0, "unknown": 0.75, "veterinary_supplier": 0.6}, "employee_band": {"large": 0.6, "micro": 0.55, "mid_market": 1.0, "small": 0.85, "unknown": 0.8}}, "hybrid_company_types": {"hybrid_distributor_manufacturer": ["pet_specialty_distributor", "manufacturer"], "hybrid_distributor_retailer": ["pet_specialty_distributor", "pet_retailer"]}, "industry_keywords": {"pet": ["pet food", "pet specialty", "pet supplies", "pet products", "dog food", "cat food", "dog treats", "cat treats", "pet treats", "pet supplements", "dog chews", "pet nutrition", "independent pet", "pet retailers", "pet stores", "pet industry", "companion animal", "bully sticks", "dog supplements", "cat supplements"]}, "intent_thresholds": {"GOOD": 51, "HOT": 86, "LOW": 0, "POSSIBLE": 31, "STRONG": 71}, "interest_type_by_signal": {"active_product_category_request": "EXPLICITLY_SEEKING", "active_product_rfq": "EXPLICITLY_SEEKING", "active_supplier_request": "EXPLICITLY_SEEKING", "catalog_linecard_expansion": "RECENTLY_ADDED", "food_category_expansion": "RECENTLY_ADDED", "new_brand_added": "RECENTLY_ADDED", "new_supplier_partnership": "RECENTLY_ADDED", "premium_natural_portfolio_expansion": "RECENTLY_ADDED", "product_line_launch": "RECENTLY_ADDED", "supplement_category_expansion": "RECENTLY_ADDED", "treats_category_expansion": "RECENTLY_ADDED"}, "no_product_demand_message": "Specific product demand not publicly disclosed.", "normalization_ceiling": 90, "product_attributes": {"format": {"Air-dried": ["air-dried", "air dried"], "Canned": ["canned"], "Capsule": ["capsule"], "Dehydrated": ["dehydrated"], "Freeze-dried": ["freeze-dried", "freeze dried"], "Fresh": ["fresh"], "Frozen": ["frozen"], "Hard chews": ["hard chew"], "Kibble": ["kibble"], "Liquid": ["liquid"], "Oil": ["oil"], "Paste": ["paste"], "Powder": ["powder"], "Raw": ["raw"], "Soft chews": ["soft chew"], "Tablet": ["tablet"], "Topper": ["topper"]}, "life_stage": {"All life stages": ["all life stages"], "Kitten": ["kitten"], "Puppy": ["puppy", "puppies"], "Senior": ["senior"]}, "positioning": {"Grain-free": ["grain-free", "grain free"], "High protein": ["high-protein", "high protein"], "Limited ingredient": ["limited ingredient", "limited-ingredient"], "Novel protein": ["novel protein", "novel-protein"], "Single ingredient": ["single-ingredient", "single ingredient"]}, "protein_source": {"Beef": ["beef"], "Bison": ["bison"], "Chicken": ["chicken"], "Duck": ["duck"], "Insect": ["insect protein"], "Lamb": ["lamb"], "Pork": ["pork"], "Rabbit": ["rabbit"], "Salmon": ["salmon"], "Turkey": ["turkey"], "Venison": ["venison"], "Whitefish": ["whitefish"]}, "stated_certifications_and_claims": {"Human-grade - stated": ["human-grade", "human grade"], "Made in USA - stated": ["made in usa", "made in the usa", "made in the u.s.a"], "NASC Quality Seal - stated": ["nasc quality seal", "nasc seal"], "Natural - stated": ["all-natural", "all natural", "natural"], "Organic - stated": ["organic"], "Sourced in USA - stated": ["sourced in the usa", "us-sourced"]}, "stated_health_claims": {"Supports calm behavior - company claim": ["supports calm", "promotes calm", "calming support"], "Supports dental health - company claim": ["supports dental health", "fresh breath", "reduces tartar"], "Supports digestion - company claim": ["supports digestion", "digestive support", "supports gut health"], "Supports immune health - company claim": ["supports immune", "immune support"], "Supports joint health - company claim": ["supports joint health", "joint support", "supports hip and joint"], "Supports skin and coat - company claim": ["supports skin and coat", "healthy skin and coat"]}}, "product_taxonomy": {"Chews": {"Bully Sticks": ["bully stick"], "Dental Chews": ["dental chew"], "Long-Lasting Chews": ["long-lasting chew", "long lasting chew"], "Natural Chews": ["natural chew", "beef chew", "lamb chew", "yak chew", "himalayan chew", "antler chew"], "Rawhide Alternatives": ["rawhide alternative", "rawhide-free chew", "rawhide free chew"]}, "Dog and Cat Treats": {"Baked Biscuits": ["baked biscuit", "dog biscuit", "baked dog treat"], "Cat Treats": ["cat treat"], "Dehydrated Treats": ["dehydrated treat"], "Dental Treats": ["dental treat", "dental chew"], "Dog Treats": ["dog treat"], "Freeze-Dried Treats": ["freeze-dried treat", "freeze dried treat", "freeze-dried raw treat", "freeze-dried dog treat", "freeze-dried cat treat", "freeze dried dog treat", "freeze dried cat treat"], "Functional Treats": ["functional treat"], "Grain-Free Treats": ["grain-free treat", "grain free treat"], "Jerky Treats": ["jerky treat", "dog jerky", "jerky"], "Limited-Ingredient Treats": ["limited ingredient treat", "limited-ingredient treat"], "Meat-Based Treats": ["meat treat", "meat-based treat"], "Natural Treats": ["natural dog treat", "natural cat treat", "natural pet treat", "natural treat"], "Novel-Protein Treats": ["novel protein treat", "novel-protein treat"], "Organic Treats": ["organic treat"], "Single-Ingredient Treats": ["single-ingredient treat", "single ingredient treat"], "Soft Treats": ["soft treat", "soft and chewy treat"], "Training Treats": ["training treat"]}, "Pet Supplements": {"Anxiety Support": ["anxiety support", "stress relief supplement"], "Calming and Relaxation": ["calming chew", "calming supplement", "calming treat", "relaxation supplement"], "Digestive Health Supplements": ["digestive supplement", "digestive health supplement", "digestive chew", "gut health supplement"], "Functional Supplement Chews": ["supplement chew", "functional soft chew", "soft chew supplement"], "Glucosamine and Chondroitin": ["glucosamine", "chondroitin"], "Hip and Joint Supplements": ["hip and joint", "joint supplement", "joint support supplement", "joint chew"], "Immune Support": ["immune support supplement", "immune chew"], "Liquid Supplements": ["liquid supplement"], "Mobility Supplements": ["mobility supplement", "mobility chew"], "Multivitamins": ["multivitamin"], "Nutritional Powders": ["supplement powder", "nutritional powder"], "Omega-3 and Fish Oil": ["omega-3", "fish oil", "salmon oil", "krill oil"], "Pet Supplements - General": ["pet supplement", "dog supplement", "cat supplement"], "Prebiotics": ["prebiotic"], "Probiotics": ["probiotic"], "Senior Pet Supplements": ["senior supplement", "senior pet supplement"], "Skin and Coat Supplements": ["skin and coat supplement", "skin and coat chew"]}, "Specialty Cat Food": {"Cat Broths and Food Enhancers": ["cat broth", "bone broth for cats"], "Cat Meal Toppers and Mixers": ["cat food topper", "meal topper for cats"], "Dehydrated Cat Food": ["dehydrated cat food"], "Freeze-Dried Cat Food": ["freeze-dried cat food", "freeze dried cat food"], "Fresh and Frozen Cat Food": ["fresh cat food", "frozen cat food"], "Functional Cat Nutrition": ["functional cat food", "functional nutrition for cats"], "Grain-Free Cat Food": ["grain-free cat food", "grain free cat food"], "High-Protein Cat Food": ["high-protein cat food", "high protein cat food"], "Kitten Food": ["kitten food", "kitten formula"], "Limited-Ingredient Cat Food": ["limited ingredient cat food", "limited-ingredient cat food"], "Premium Dry Cat Food": ["premium dry cat food", "dry cat food", "cat kibble", "premium cat food"], "Raw Cat Food": ["raw cat food"], "Senior Cat Food": ["senior cat food"], "Wet Cat Food": ["wet cat food", "canned cat food"]}, "Specialty Dog Food": {"Air-Dried Dog Food": ["air-dried dog food", "air dried dog food"], "Breed-Specific Formulations": ["breed-specific formula", "breed specific nutrition"], "Dehydrated Dog Food": ["dehydrated dog food"], "Dog Broths and Food Enhancers": ["bone broth for dogs", "dog broth", "dog food enhancer"], "Dog Meal Toppers and Mixers": ["dog food topper", "meal topper for dogs", "dog food mixer", "dog meal mixer"], "Freeze-Dried Dog Food": ["freeze-dried dog food", "freeze dried dog food", "freeze-dried raw dog food"], "Fresh Dog Food": ["fresh dog food", "gently cooked dog food"], "Frozen Dog Food": ["frozen dog food", "frozen raw dog food"], "Functional Dog Nutrition": ["functional dog food", "functional nutrition for dogs"], "Grain-Free Dog Food": ["grain-free dog food", "grain free dog food"], "High-Protein Dog Food": ["high-protein dog food", "high protein dog food"], "Large-Breed Food": ["large breed dog food", "large-breed dog food", "large breed formula"], "Limited-Ingredient Dog Food": ["limited ingredient dog food", "limited-ingredient dog food"], "Novel-Protein Dog Food": ["novel protein dog food", "novel-protein dog food"], "Premium Dry Dog Food": ["premium dry dog food", "dry dog food", "dog kibble", "premium dog food"], "Puppy Food": ["puppy food", "puppy formula"], "Raw Dog Food": ["raw dog food", "raw diet for dogs"], "Senior Dog Food": ["senior dog food"], "Small-Breed Food": ["small breed dog food", "small-breed dog food", "small breed formula"], "Wet Dog Food": ["wet dog food", "canned dog food"]}}, "qualification": {"allow_unverified_location_tlds": ["com", "net", "us", "org", "biz"], "allowed_countries": ["US"], "company_type_min_markers": 2, "eligible_company_types": ["pet_specialty_distributor", "hybrid_distributor_manufacturer", "hybrid_distributor_retailer", "veterinary_supplier"], "excluded_employee_bands": ["large", "small", "micro"], "industry_implies_physical": true, "min_country_confidence": 0.6, "min_industry_markers": 1, "reject_company_types": ["pet_retailer", "veterinary_clinic", "pet_service_provider", "manufacturer", "brand_owner", "software_or_service_vendor", "b2b_marketplace"], "require_country_evidence": true, "required_industry": "pet", "unknown_company_type": "allow"}, "query_exclusion_terms": ["for sale", "adoption", "puppies for sale", "near me"], "refresh_days": {"GOOD": 30, "HOT": 7, "LOW": 120, "POSSIBLE": 60, "STRONG": 14}, "required_signals": ["pet_specialty_participation"], "score_weights": {"ai": 0.3, "deterministic": 0.5, "evidence": 0.2}, "signal_dimensions": {"b2b_retailer_distribution": "fit", "brand_seeking_distribution": "negative", "pet_service_or_clinic": "negative", "pet_specialty_participation": "fit", "retail_only_pet_store": "negative"}, "signal_page_affinity": {"acquisition_expansion": ["news", "press_release", "about"], "active_product_category_request": ["supplier", "news", "press_release", "website", "other"], "active_product_rfq": ["supplier", "news", "press_release", "website", "other"], "active_supplier_request": ["supplier", "news", "press_release", "website", "about", "other"], "catalog_linecard_expansion": ["brands", "website", "news", "press_release"], "category_manager_hiring": ["careers", "job"], "distribution_center_expansion": ["news", "press_release", "about", "website"], "food_category_expansion": ["news", "press_release", "website", "brands"], "merchandising_hiring": ["careers", "job"], "new_brand_added": ["news", "press_release", "brands", "website"], "new_supplier_partnership": ["news", "press_release", "website", "brands", "about"], "premium_natural_portfolio_expansion": ["news", "press_release", "website", "brands"], "private_label_expansion": ["news", "press_release", "brands", "website"], "procurement_hiring": ["careers", "job"], "product_line_launch": ["news", "press_release", "website", "brands"], "purchasing_manager_hiring": ["careers", "job"], "regional_distribution_expansion": ["news", "press_release", "about", "website"], "retail_network_expansion": ["news", "press_release", "about", "website", "dealer"], "supplement_category_expansion": ["news", "press_release", "website", "brands"], "supplier_application_open": ["supplier", "website", "other", "about"], "treats_category_expansion": ["news", "press_release", "website", "brands"], "vendor_relations_expansion": ["careers", "job"]}, "signal_rules": {"acquisition_expansion": {"require_context_phrases": ["distributor", "distribution", "distributing", "pet", "wholesale"]}, "active_product_category_request": {"exclude_page_types": ["dealer", "careers", "job"], "require_context_phrases": ["food", "treat", "treats", "chew", "chews", "supplement", "supplements", "brands", "products", "lines", "suppliers", "manufacturers"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution", "wholesale account application", "open a wholesale account", "apply for a wholesale account", "retailer application", "become a retailer", "become a stockist", "retailer sign up", "retailer signup", "for retailers", "new retailer", "retail account", "dealer application", "become a dealer", "get a quote", "your quote", "your order", "our customers", "request a catalog", "request pricing"]}, "active_product_rfq": {"exclude_page_types": ["dealer"], "require_context_phrases": ["supplier", "suppliers", "manufacturer", "manufacturers", "vendor", "vendors", "source", "sourcing", "brands"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution", "wholesale account application", "open a wholesale account", "apply for a wholesale account", "retailer application", "become a retailer", "become a stockist", "retailer sign up", "retailer signup", "for retailers", "new retailer", "retail account", "dealer application", "become a dealer", "get a quote", "your quote", "your order", "our customers", "request a catalog", "request pricing"]}, "active_supplier_request": {"exclude_page_types": ["dealer"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution", "wholesale account application", "open a wholesale account", "apply for a wholesale account", "retailer application", "become a retailer", "become a stockist", "retailer sign up", "retailer signup", "for retailers", "new retailer", "retail account", "dealer application", "become a dealer"]}, "catalog_linecard_expansion": {"require_context_phrases": ["new", "added", "adds", "expanded", "expands", "expansion", "now includes", "additional"]}, "category_manager_hiring": {"require_page_types": ["careers", "job"]}, "food_category_expansion": {"require_context_phrases": ["dog food", "cat food", "pet food", "kibble", "wet food", "raw food", "freeze-dried", "fresh food", "frozen food", "diet", "diets", "formula", "formulas", "topper", "toppers"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "merchandising_hiring": {"require_page_types": ["careers", "job"]}, "new_brand_added": {"exclude_page_types": ["dealer"], "require_context_phrases": ["pet", "pets", "dog", "dogs", "cat", "cats", "canine", "feline", "puppy", "kitten", "treat", "treats", "chew", "chews", "pet food", "supplement", "supplements", "nutrition"], "suppress_phrases": ["looking for", "seeking", "submit", "interested in", "our new brand identity", "welcomes you", "looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "new_supplier_partnership": {"require_context_phrases": ["distribute", "distribution", "distributor", "distributing", "brand", "brands", "retailers", "pet specialty"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "premium_natural_portfolio_expansion": {"require_context_phrases": ["premium", "natural", "holistic", "limited ingredient", "limited-ingredient", "organic", "grain-free", "grain free", "human-grade", "specialty nutrition"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "private_label_expansion": {"require_context_phrases": ["expand", "expands", "expanded", "expanding", "launch", "launches", "new", "adds", "added"]}, "procurement_hiring": {"require_page_types": ["careers", "job"]}, "product_line_launch": {"require_context_phrases": ["pet", "pets", "dog", "dogs", "cat", "cats", "canine", "feline", "puppy", "kitten", "treat", "treats", "chew", "chews", "pet food", "supplement", "supplements", "nutrition"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "purchasing_manager_hiring": {"require_page_types": ["careers", "job"]}, "regional_distribution_expansion": {"require_context_phrases": ["distribution", "distributor", "wholesale", "retailers", "stores", "delivery"]}, "supplement_category_expansion": {"require_context_phrases": ["supplement", "supplements", "probiotic", "probiotics", "omega-3", "fish oil", "glucosamine", "joint", "calming", "multivitamin", "wellness", "functional nutrition"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "supplier_application_open": {"exclude_page_types": ["dealer"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution", "wholesale account application", "open a wholesale account", "apply for a wholesale account", "retailer application", "become a retailer", "become a stockist", "retailer sign up", "retailer signup", "for retailers", "new retailer", "retail account", "dealer application", "become a dealer"]}, "treats_category_expansion": {"require_context_phrases": ["treat", "treats", "chew", "chews", "bully stick", "bully sticks", "jerky", "biscuit", "biscuits", "dental"], "suppress_phrases": ["looking for a distributor", "looking for distributors", "seeking a distributor", "seeking distributors", "become a distributor", "distributor inquiries", "distributors wanted", "seeking nationwide distribution", "looking for distribution"]}, "vendor_relations_expansion": {"require_page_types": ["careers", "job"]}}, "size_bands": [{"band": "micro", "max": 10, "min": 1}, {"band": "small", "max": 49, "min": 11}, {"band": "mid_market", "max": 500, "min": 50}, {"band": "large", "max": null, "min": 501}], "ui_labels": {"interest_types": {"CURRENTLY_CARRIED": "Currently carried", "EXPLICITLY_SEEKING": "Explicitly seeking", "INFERRED_FIT": "Inferred category fit", "RECENTLY_ADDED": "Recently onboarded"}, "segment": "Species", "title": "Pet Specialty Buying Intelligence \u00b7 US"}, "undated_confidence_factor": 0.75, "vehicle_platforms": [], "vehicle_segments": {"Cat": ["cat", "cats", "feline", "kitten", "kittens"], "Dog": ["dog", "dogs", "canine", "puppy", "puppies"], "Other": ["small animal", "small animals", "bird", "birds", "equine", "horse", "reptile", "ferret"]}}'::jsonb
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
-- 4. KEYWORDS  (306)
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

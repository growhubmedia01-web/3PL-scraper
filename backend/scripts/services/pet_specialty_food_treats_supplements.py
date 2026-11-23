"""Service definition: Pet Specialty Food, Treats & Supplements.

The ONLY place in the system that knows what a bully stick, a joint-support
soft chew or a pet distributor's vendor application is. Everything here is
data consumed by the generic engine through ServiceConfig:

    migrations/010_pet_specialty_food_treats_supplements.sql   (generated)
    scripts/seed.py                                            (ORM path)

Rebuild the SQL after editing:
    python -m scripts.build_service_seed pet_specialty_food_treats_supplements

Target: the BUYER - a US mid-market pet specialty distributor or wholesaler
that supplies independent pet retailers.

Commercial direction this service scores (the part that is easy to get
wrong):
    A. distributor -> brand/manufacturer   buying      POSITIVE intent
    B. brand -> distributor                seeking us  NEGATIVE
    C. retailer -> distributor             retail buying, NOT our target;
       and a distributor's retailer/wholesale-account application is the
       distributor SELLING - never a supplier-onboarding signal.

Weights are starting configuration, not validated probabilities. Recalibrate
against lead reviews.

Regulatory safeguard: product claims ("supports joint health", "NASC Quality
Seal", "human-grade") are recorded only as the company's own STATED claims,
with provenance. Nothing here treats a claim as verified, medical or
FDA-approved. Prescription diets, flea/tick and other drugs are deliberately
absent from the taxonomy.
"""
from __future__ import annotations

from dataclasses import dataclass

SLUG = "pet_specialty_food_treats_supplements"
NAME = "Pet Specialty Food, Treats & Supplements"
DESCRIPTION = (
    "Find mid-market US pet specialty distributors and wholesalers that show "
    "public, evidenced intent to source, onboard or expand pet food, treats, "
    "chews and supplements - and which products they may be looking to buy.")

# =====================================================================
# PRODUCT TAXONOMY  {category: {subcategory: [terms]}}
# Terms are matched as whole phrases, singular/plural tolerant. Species-
# ambiguous terms are deliberately avoided; species is recorded separately.
# =====================================================================
PRODUCT_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "Specialty Dog Food": {
        "Premium Dry Dog Food": ["premium dry dog food", "dry dog food",
                                 "dog kibble", "premium dog food"],
        "Wet Dog Food": ["wet dog food", "canned dog food"],
        "Fresh Dog Food": ["fresh dog food", "gently cooked dog food"],
        "Frozen Dog Food": ["frozen dog food", "frozen raw dog food"],
        "Raw Dog Food": ["raw dog food", "raw diet for dogs"],
        "Freeze-Dried Dog Food": ["freeze-dried dog food",
                                  "freeze dried dog food",
                                  "freeze-dried raw dog food"],
        "Dehydrated Dog Food": ["dehydrated dog food"],
        "Air-Dried Dog Food": ["air-dried dog food", "air dried dog food"],
        "Limited-Ingredient Dog Food": ["limited ingredient dog food",
                                        "limited-ingredient dog food"],
        "Grain-Free Dog Food": ["grain-free dog food", "grain free dog food"],
        "Novel-Protein Dog Food": ["novel protein dog food",
                                   "novel-protein dog food"],
        "High-Protein Dog Food": ["high-protein dog food",
                                  "high protein dog food"],
        "Small-Breed Food": ["small breed dog food", "small-breed dog food",
                             "small breed formula"],
        "Large-Breed Food": ["large breed dog food", "large-breed dog food",
                             "large breed formula"],
        "Puppy Food": ["puppy food", "puppy formula"],
        "Senior Dog Food": ["senior dog food"],
        "Breed-Specific Formulations": ["breed-specific formula",
                                        "breed specific nutrition"],
        "Functional Dog Nutrition": ["functional dog food",
                                     "functional nutrition for dogs"],
        "Dog Meal Toppers and Mixers": ["dog food topper", "meal topper for dogs",
                                        "dog food mixer", "dog meal mixer"],
        "Dog Broths and Food Enhancers": ["bone broth for dogs", "dog broth",
                                          "dog food enhancer"],
    },
    "Specialty Cat Food": {
        "Premium Dry Cat Food": ["premium dry cat food", "dry cat food",
                                 "cat kibble", "premium cat food"],
        "Wet Cat Food": ["wet cat food", "canned cat food"],
        "Fresh and Frozen Cat Food": ["fresh cat food", "frozen cat food"],
        "Raw Cat Food": ["raw cat food"],
        "Freeze-Dried Cat Food": ["freeze-dried cat food",
                                  "freeze dried cat food"],
        "Dehydrated Cat Food": ["dehydrated cat food"],
        "Grain-Free Cat Food": ["grain-free cat food", "grain free cat food"],
        "Limited-Ingredient Cat Food": ["limited ingredient cat food",
                                        "limited-ingredient cat food"],
        "Kitten Food": ["kitten food", "kitten formula"],
        "Senior Cat Food": ["senior cat food"],
        "High-Protein Cat Food": ["high-protein cat food",
                                  "high protein cat food"],
        "Functional Cat Nutrition": ["functional cat food",
                                     "functional nutrition for cats"],
        "Cat Meal Toppers and Mixers": ["cat food topper", "meal topper for cats"],
        "Cat Broths and Food Enhancers": ["cat broth", "bone broth for cats"],
    },
    "Dog and Cat Treats": {
        "Natural Treats": ["natural dog treat", "natural cat treat",
                           "natural pet treat", "natural treat"],
        "Single-Ingredient Treats": ["single-ingredient treat",
                                     "single ingredient treat"],
        "Freeze-Dried Treats": ["freeze-dried treat", "freeze dried treat",
                                "freeze-dried raw treat", "freeze-dried dog treat",
                                "freeze-dried cat treat", "freeze dried dog treat",
                                "freeze dried cat treat"],
        "Dehydrated Treats": ["dehydrated treat"],
        "Meat-Based Treats": ["meat treat", "meat-based treat"],
        "Jerky Treats": ["jerky treat", "dog jerky", "jerky"],
        "Training Treats": ["training treat"],
        "Dental Treats": ["dental treat", "dental chew"],
        "Functional Treats": ["functional treat"],
        "Organic Treats": ["organic treat"],
        "Limited-Ingredient Treats": ["limited ingredient treat",
                                      "limited-ingredient treat"],
        "Grain-Free Treats": ["grain-free treat", "grain free treat"],
        "Novel-Protein Treats": ["novel protein treat", "novel-protein treat"],
        "Soft Treats": ["soft treat", "soft and chewy treat"],
        "Baked Biscuits": ["baked biscuit", "dog biscuit", "baked dog treat"],
        "Cat Treats": ["cat treat"],
        "Dog Treats": ["dog treat"],
    },
    "Chews": {
        "Bully Sticks": ["bully stick"],
        "Natural Chews": ["natural chew", "beef chew", "lamb chew",
                          "yak chew", "himalayan chew", "antler chew"],
        "Rawhide Alternatives": ["rawhide alternative", "rawhide-free chew",
                                 "rawhide free chew"],
        "Long-Lasting Chews": ["long-lasting chew", "long lasting chew"],
        "Dental Chews": ["dental chew"],
    },
    "Pet Supplements": {
        "Hip and Joint Supplements": ["hip and joint", "joint supplement",
                                      "joint support supplement", "joint chew"],
        "Mobility Supplements": ["mobility supplement", "mobility chew"],
        "Glucosamine and Chondroitin": ["glucosamine", "chondroitin"],
        "Probiotics": ["probiotic"],
        "Prebiotics": ["prebiotic"],
        "Digestive Health Supplements": ["digestive supplement",
                                         "digestive health supplement",
                                         "digestive chew", "gut health supplement"],
        "Omega-3 and Fish Oil": ["omega-3", "fish oil", "salmon oil", "krill oil"],
        "Skin and Coat Supplements": ["skin and coat supplement",
                                      "skin and coat chew"],
        "Multivitamins": ["multivitamin"],
        "Calming and Relaxation": ["calming chew", "calming supplement",
                                   "calming treat", "relaxation supplement"],
        "Anxiety Support": ["anxiety support", "stress relief supplement"],
        "Immune Support": ["immune support supplement", "immune chew"],
        "Senior Pet Supplements": ["senior supplement", "senior pet supplement"],
        "Nutritional Powders": ["supplement powder", "nutritional powder"],
        "Liquid Supplements": ["liquid supplement"],
        "Functional Supplement Chews": ["supplement chew", "functional soft chew",
                                        "soft chew supplement"],
        "Pet Supplements - General": ["pet supplement", "dog supplement",
                                      "cat supplement"],
    },
}

# Adjacency used ONLY for INFERRED_FIT ("inferred category fit") records,
# which are never presented as buying demand.
ADJACENT_CATEGORIES: dict[str, list[str]] = {
    "Specialty Dog Food": ["Dog and Cat Treats", "Pet Supplements"],
    "Specialty Cat Food": ["Dog and Cat Treats"],
    "Dog and Cat Treats": ["Chews"],
    "Chews": ["Dog and Cat Treats"],
    "Pet Supplements": ["Dog and Cat Treats"],
}

# Species. Stored in the generic "segments" field of product interests.
SPECIES: dict[str, list[str]] = {
    "Dog": ["dog", "dogs", "canine", "puppy", "puppies"],
    "Cat": ["cat", "cats", "feline", "kitten", "kittens"],
    "Other": ["small animal", "small animals", "bird", "birds", "equine",
              "horse", "reptile", "ferret"],
}

# Attributes read from the evidence text of each product-interest record.
# Claims are the company's OWN stated wording - never verified efficacy.
PRODUCT_ATTRIBUTES: dict[str, dict[str, list[str]]] = {
    "format": {
        "Soft chews": ["soft chew"], "Hard chews": ["hard chew"],
        "Powder": ["powder"], "Liquid": ["liquid"], "Tablet": ["tablet"],
        "Capsule": ["capsule"], "Oil": ["oil"], "Paste": ["paste"],
        "Topper": ["topper"], "Freeze-dried": ["freeze-dried", "freeze dried"],
        "Dehydrated": ["dehydrated"], "Air-dried": ["air-dried", "air dried"],
        "Frozen": ["frozen"], "Fresh": ["fresh"], "Raw": ["raw"],
        "Kibble": ["kibble"], "Canned": ["canned"],
    },
    "protein_source": {
        "Chicken": ["chicken"], "Beef": ["beef"], "Salmon": ["salmon"],
        "Lamb": ["lamb"], "Turkey": ["turkey"], "Duck": ["duck"],
        "Bison": ["bison"], "Venison": ["venison"], "Rabbit": ["rabbit"],
        "Pork": ["pork"], "Whitefish": ["whitefish"], "Insect": ["insect protein"],
    },
    "life_stage": {
        "Puppy": ["puppy", "puppies"], "Kitten": ["kitten"],
        "Senior": ["senior"], "All life stages": ["all life stages"],
    },
    "positioning": {
        "Grain-free": ["grain-free", "grain free"],
        "Limited ingredient": ["limited ingredient", "limited-ingredient"],
        "Novel protein": ["novel protein", "novel-protein"],
        "High protein": ["high-protein", "high protein"],
        "Single ingredient": ["single-ingredient", "single ingredient"],
    },
    # Stated by the company. Never independently certified by this system.
    "stated_certifications_and_claims": {
        "NASC Quality Seal - stated": ["nasc quality seal", "nasc seal"],
        "Organic - stated": ["organic"],
        "Human-grade - stated": ["human-grade", "human grade"],
        "Natural - stated": ["all-natural", "all natural", "natural"],
        "Made in USA - stated": ["made in usa", "made in the usa",
                                 "made in the u.s.a"],
        "Sourced in USA - stated": ["sourced in the usa", "us-sourced"],
    },
    # Marketing language preserved as marketing language.
    "stated_health_claims": {
        "Supports joint health - company claim": ["supports joint health",
                                                  "joint support",
                                                  "supports hip and joint"],
        "Supports digestion - company claim": ["supports digestion",
                                               "digestive support",
                                               "supports gut health"],
        "Supports skin and coat - company claim": ["supports skin and coat",
                                                   "healthy skin and coat"],
        "Supports calm behavior - company claim": ["supports calm",
                                                   "promotes calm", "calming support"],
        "Supports immune health - company claim": ["supports immune",
                                                   "immune support"],
        "Supports dental health - company claim": ["supports dental health",
                                                    "fresh breath", "reduces tartar"],
    },
}

_B = r"([A-Z][A-Za-z0-9&'\-]+(?:\s+[A-Z][A-Za-z0-9&'\-]+){0,3})"
BRAND_PATTERNS: list[str] = [
    r"distribution (?:agreement|partnership|deal) with " + _B,
    r"(?:exclusive|official|authorized|master) (?:US |U\.S\. |North American |"
    r"national )?distributor (?:of|for) " + _B,
    r"(?:now|will) (?:distribute|distributing|carry|carrying|stock|stocking) " + _B,
    r"(?:added|adds|adding|welcomes|welcomed) " + _B + r" (?:to (?:its|our|the) "
    r"(?:lineup|line card|brand portfolio|portfolio|catalog|offering|assortment))",
    _B + r" (?:is |are )?now available (?:through|via|from) ",
    _B + r" expands (?:its )?distribution (?:with|through) ",
    r"partner(?:ed|ship)? with " + _B,
]

PET_CONTEXT = [
    "pet", "pets", "dog", "dogs", "cat", "cats", "canine", "feline", "puppy",
    "kitten", "treat", "treats", "chew", "chews", "pet food", "supplement",
    "supplements", "nutrition",
]
FOOD_CONTEXT = ["dog food", "cat food", "pet food", "kibble", "wet food",
                "raw food", "freeze-dried", "fresh food", "frozen food", "diet",
                "diets", "formula", "formulas", "topper", "toppers"]
TREAT_CONTEXT = ["treat", "treats", "chew", "chews", "bully stick",
                 "bully sticks", "jerky", "biscuit", "biscuits", "dental"]
SUPPLEMENT_CONTEXT = ["supplement", "supplements", "probiotic", "probiotics",
                      "omega-3", "fish oil", "glucosamine", "joint", "calming",
                      "multivitamin", "wellness", "functional nutrition"]
PREMIUM_CONTEXT = ["premium", "natural", "holistic", "limited ingredient",
                   "limited-ingredient", "organic", "grain-free", "grain free",
                   "human-grade", "specialty nutrition"]

# =====================================================================
# SIGNALS  (signal_type, name, description, weight, decay_days, max_occ)
# Descriptions must not contain parentheses - the SQL row parser forbids it.
# =====================================================================
SIGNALS: list[tuple[str, str, str, float, int | None, int]] = [
    # ---- Tier 1: direct supplier and product demand ----
    ("active_supplier_request", "Active Supplier Request",
     "Distributor publicly asks for new suppliers, product proposals, vendor submissions "
     "or manufacturer partnerships", 35, 90, 1),
    ("active_product_category_request", "Active Product Category Request",
     "Distributor explicitly requests products in a named pet food, treat, chew or "
     "supplement category", 35, 90, 1),
    ("active_product_rfq", "Active Product RFQ",
     "Public request for quotation, product sourcing or a specific procurement opportunity",
     35, 90, 1),
    ("supplier_application_open", "Supplier Application Open",
     "An official supplier or vendor submission process invites brands to submit products. "
     "Evergreen openness to new brands, not an active purchasing requirement. "
     "Revalidated every 180 days by re-crawl", 20, 180, 1),
    # ---- Tier 2: brand and portfolio expansion ----
    ("new_supplier_partnership", "New Supplier Partnership",
     "Distributor announces a new supplier or manufacturer partnership", 27, 180, 1),
    ("new_brand_added", "New Brand Added",
     "Distributor adds a new pet food, treat or supplement brand", 25, 180, 1),
    ("food_category_expansion", "Food Category Expansion",
     "Expansion into a new pet food category or a substantial addition to one", 23, 180, 1),
    ("treats_category_expansion", "Treats Category Expansion",
     "Addition of new treat, chew or dental-product categories", 23, 180, 1),
    ("supplement_category_expansion", "Supplement Category Expansion",
     "Addition of new functional pet supplements or wellness brands", 25, 180, 1),
    ("premium_natural_portfolio_expansion", "Premium or Natural Portfolio Expansion",
     "Expansion into premium, natural, holistic, limited-ingredient or specialty nutrition",
     20, 180, 1),
    ("product_line_launch", "Product Line Launch",
     "Distributor announces a new product line or a material assortment launch", 18, 150, 1),
    ("catalog_linecard_expansion", "Catalog or Line Card Expansion",
     "Material change to an official distributor catalog or line card", 15, 180, 1),
    # ---- Tier 3: purchasing capability ----
    ("category_manager_hiring", "Category Manager Hiring",
     "Hiring people who manage pet food, treat, supplement or nutrition categories",
     17, 120, 1),
    ("purchasing_manager_hiring", "Purchasing Manager Hiring",
     "Hiring buyers or purchasing managers", 17, 120, 1),
    ("procurement_hiring", "Procurement Hiring",
     "Hiring procurement, vendor management or sourcing professionals", 15, 120, 1),
    ("merchandising_hiring", "Merchandising Hiring",
     "Hiring merchandising or assortment management roles", 13, 120, 1),
    ("vendor_relations_expansion", "Vendor Relations Expansion",
     "Hiring or creating teams responsible for supplier and vendor relationships",
     15, 150, 1),
    # ---- Tier 4: business expansion ----
    ("distribution_center_expansion", "Distribution Center Expansion",
     "New warehouse, distribution facility or materially expanded distribution capacity",
     13, 270, 1),
    ("regional_distribution_expansion", "Regional Distribution Expansion",
     "New state or regional wholesale coverage", 15, 180, 1),
    ("retail_network_expansion", "Retail Network Expansion",
     "Significant expansion in independent pet retailer coverage", 12, 180, 1),
    ("private_label_expansion", "Private Label Expansion",
     "Expansion of the distributor private-label food, treat or supplement program",
     16, 180, 1),
    ("acquisition_expansion", "Acquisition Expansion",
     "Acquired another pet distributor or materially expanded distribution operations",
     12, 270, 1),
    # ---- Distributor fit: evidence of WHAT the company is, never of buying ----
    ("pet_specialty_participation", "Pet Specialty Participation",
     "Verifiable participation in pet food, treats, chews or supplements", 5, None, 1),
    ("b2b_retailer_distribution", "B2B Retailer Distribution",
     "Supplies independent pet retailers or other B2B accounts - the distributor-to-retailer "
     "direction. Fit, not buying intent", 6, None, 1),
    # ---- Negative polarity: wrong commercial direction or wrong business ----
    ("brand_seeking_distribution", "Brand Seeking Distribution",
     "The company looks for distributors for its own products - the opposite direction",
     -25, None, 1),
    ("retail_only_pet_store", "Retail-Only Pet Store",
     "Consumer store or boutique language with no wholesale operation", -15, None, 1),
    ("pet_service_or_clinic", "Pet Service or Clinic",
     "Veterinary clinic, grooming, boarding, daycare or other pet service business",
     -15, None, 1),
]

SIGNAL_DIMENSIONS = {
    "pet_specialty_participation": "fit",
    "b2b_retailer_distribution": "fit",
    "brand_seeking_distribution": "negative",
    "retail_only_pet_store": "negative",
    "pet_service_or_clinic": "negative",
}


# =====================================================================
# KEYWORDS  (keyword, category, signal_type, weight)
# category 'hiring' marks the signals that get the structured job boost.
# A phrase may feed several signals only under different categories.
# =====================================================================
def _kw(signal: str, category: str, weight: float, *phrases: str):
    return [(p, category, signal, weight) for p in phrases]


_EXPANSION_PHRASES = (
    "expands its", "expanded its", "expanding its", "expands our",
    "expanding our", "expansion into", "expanding into", "new category",
    "new categories", "adds new", "added new", "broadens its", "now offers",
    "now offering")

KEYWORDS: list[tuple[str, str, str, float]] = (
    _kw("active_supplier_request", "intent", 1.0,
        "looking for new suppliers", "seeking new suppliers",
        "looking for suppliers", "seeking suppliers", "seeking new vendors",
        "looking for new vendors", "looking for new brands",
        "seeking new brands", "looking for manufacturers",
        "seeking manufacturers", "new supplier opportunities",
        "product proposals", "actively seeking new", "currently seeking new",
        "seeking manufacturer partners", "looking for new manufacturer partners")
    + _kw("active_product_category_request", "category_request", 1.0,
          "seeking premium", "looking for premium", "seeking freeze-dried",
          "looking for freeze-dried", "seeking natural", "looking for natural",
          "seeking brands in", "looking for brands in", "seeking products in",
          "looking for products in", "currently seeking", "actively seeking",
          "now accepting submissions for", "seeking new lines of",
          "looking to add", "seeking to add")
    + _kw("active_product_rfq", "intent", 1.0,
          "request for quote", "request for quotation", "rfq",
          "request for proposal", "seeking quotes", "looking to source",
          "now sourcing", "we are sourcing", "sourcing request",
          "quotes from manufacturers", "quotes from suppliers")
    + _kw("supplier_application_open", "intent", 1.0,
          "supplier application", "vendor application",
          "new vendor application", "vendor inquiry form", "supplier inquiry",
          "become a supplier", "become a vendor", "vendor submission",
          "supplier submission", "vendor onboarding", "new vendor setup",
          "vendor information form", "supplier registration",
          "vendor registration", "prospective vendors",
          "prospective suppliers", "product submission form",
          "new brand submission", "brand submission", "submit your product",
          "submit your products", "submit your brand",
          "accepting new brands", "accepting new vendors", "brand application",
          "new brand application",
          "interested in becoming a vendor", "interested in becoming a supplier")
    + _kw("new_supplier_partnership", "expansion", 1.0,
          "distribution agreement", "distribution partnership",
          "exclusive distribution", "exclusive distributor for",
          "agreement to distribute", "will now distribute", "now distributing",
          "now distributes", "named exclusive distributor",
          "appointed as distributor", "distribution deal",
          "expands distribution with", "now available through")
    + _kw("new_supplier_partnership", "expansion", 0.6,
          "partnered with", "new partnership with", "announces partnership",
          "partners with")
    + _kw("new_brand_added", "expansion", 1.0,
          "added to our lineup", "added to its lineup", "adds brand",
          "joins our brand portfolio", "joins our lineup", "now carrying",
          "now carries", "now stocking", "newest brand", "new to our line",
          "added to our line card", "adds new brands", "welcomes",
          "expands brand portfolio", "expanded brand portfolio")
    + _kw("new_brand_added", "expansion", 0.7, "new brand", "new brands")
    + _kw("food_category_expansion", "food_expansion", 1.0, *_EXPANSION_PHRASES)
    + _kw("treats_category_expansion", "treat_expansion", 1.0, *_EXPANSION_PHRASES)
    + _kw("supplement_category_expansion", "supplement_expansion", 1.0,
          *_EXPANSION_PHRASES)
    + _kw("premium_natural_portfolio_expansion", "premium_expansion", 1.0,
          *_EXPANSION_PHRASES)
    + _kw("product_line_launch", "expansion", 0.8,
          "new product line", "new product lines", "launches new",
          "introduces new", "new for 2026", "new for 2027", "product launch",
          "new products for")
    + _kw("catalog_linecard_expansion", "expansion", 0.8,
          "line card", "linecard", "new catalog", "2026 catalog",
          "2027 catalog", "catalog expansion", "new skus", "new items added")
    + _kw("category_manager_hiring", "hiring", 1.0,
          "category manager", "category director", "category specialist",
          "director of category management", "senior category manager")
    + _kw("purchasing_manager_hiring", "hiring", 1.0,
          "purchasing manager", "purchasing director", "director of purchasing",
          "buyer", "senior buyer", "associate buyer", "product buyer",
          "purchasing agent", "inventory buyer")
    + _kw("procurement_hiring", "hiring", 1.0,
          "procurement manager", "procurement specialist", "sourcing manager",
          "sourcing specialist", "strategic sourcing", "purchasing coordinator",
          "purchasing analyst")
    + _kw("merchandising_hiring", "hiring", 1.0,
          "merchandising manager", "merchandise manager", "assortment manager",
          "director of merchandising", "merchandise planner")
    + _kw("vendor_relations_expansion", "hiring", 1.0,
          "vendor relations", "supplier relations", "vendor manager",
          "vendor management", "brand partnerships manager")
    + _kw("distribution_center_expansion", "capacity", 1.0,
          "new distribution center", "new distribution centre",
          "new warehouse", "opens distribution center",
          "opened a new distribution", "warehouse expansion",
          "expanded warehouse", "expands distribution center",
          "additional distribution center", "square-foot distribution",
          "square foot distribution", "square-foot warehouse",
          "square foot warehouse")
    + _kw("distribution_center_expansion", "capacity", 0.6,
          "new facility", "breaks ground")
    + _kw("regional_distribution_expansion", "capacity", 1.0,
          "new territory", "new territories", "expands into", "now serving",
          "expanded coverage", "new region", "regional expansion",
          "new delivery routes", "expands its footprint")
    + _kw("retail_network_expansion", "capacity", 1.0,
          "new retail accounts", "more independent retailers",
          "expands retailer network", "growing retailer network",
          "independent retailers across", "retail partners across",
          "now supplying", "new retailer accounts")
    + _kw("private_label_expansion", "capacity", 1.0,
          "private label", "private-label", "our own brand", "exclusive brand",
          "house brand")
    + _kw("acquisition_expansion", "capacity", 1.0,
          "has acquired", "completed the acquisition", "acquisition of",
          "acquires", "merges with", "adds distribution")
    + _kw("pet_specialty_participation", "fit", 0.9,
          "pet food", "pet specialty", "dog food", "cat food", "pet treats",
          "dog treats", "cat treats", "dog chews", "pet supplements",
          "pet nutrition", "bully sticks", "pet products")
    + _kw("b2b_retailer_distribution", "fit", 0.9,
          "independent pet retailers", "independent pet stores",
          "independent retailers", "pet specialty retailers",
          "wholesale account", "retailer accounts", "serving retailers",
          "wholesale only", "trade only", "become a retailer",
          "retailer application", "wholesale distributor",
          "pet specialty distributor", "retail partners")
    + _kw("brand_seeking_distribution", "negative", 1.0,
          "looking for distributors", "looking for a distributor",
          "seeking distributors", "seeking a distributor",
          "become a distributor", "distributor inquiries",
          "distributor opportunities", "distributors wanted",
          "seeking nationwide distribution", "looking for distribution",
          "distribute our products", "interested in distributing our products",
          "wholesale inquiries for our brand")
    + _kw("retail_only_pet_store", "negative", 0.9,
          "visit our store", "store hours", "in-store pickup",
          "curbside pickup", "shop our store", "pet boutique",
          "frequent buyer program", "self-serve dog wash")
    + _kw("pet_service_or_clinic", "negative", 0.9,
          "veterinary clinic", "animal hospital", "schedule an appointment",
          "grooming appointment", "dog grooming", "boarding and daycare",
          "doggy daycare", "pet sitting", "dog walking", "wellness exams")
)

_REVERSE = ["looking for a distributor", "looking for distributors",
            "seeking a distributor", "seeking distributors",
            "become a distributor", "distributor inquiries",
            "distributors wanted", "seeking nationwide distribution",
            "looking for distribution"]
# The distributor SELLING to retailers - never supplier onboarding.
_RETAILER_SIDE = ["wholesale account application", "open a wholesale account",
                  "apply for a wholesale account", "retailer application",
                  "become a retailer", "become a stockist", "retailer sign up",
                  "retailer signup", "for retailers", "new retailer",
                  "retail account", "dealer application", "become a dealer"]
_CUSTOMER_SIDE = ["get a quote", "your quote", "your order", "our customers",
                  "request a catalog", "request pricing"]

SIGNAL_RULES: dict[str, dict] = {
    "active_supplier_request": {
        "exclude_page_types": ["dealer"],
        "suppress_phrases": _REVERSE + _RETAILER_SIDE,
    },
    "active_product_category_request": {
        "exclude_page_types": ["dealer", "careers", "job"],
        "suppress_phrases": _REVERSE + _RETAILER_SIDE + _CUSTOMER_SIDE,
        "require_context_phrases": [
            "food", "treat", "treats", "chew", "chews", "supplement",
            "supplements", "brands", "products", "lines", "suppliers",
            "manufacturers"],
    },
    "active_product_rfq": {
        "exclude_page_types": ["dealer"],
        "suppress_phrases": _REVERSE + _RETAILER_SIDE + _CUSTOMER_SIDE,
        "require_context_phrases": [
            "supplier", "suppliers", "manufacturer", "manufacturers", "vendor",
            "vendors", "source", "sourcing", "brands"],
    },
    "supplier_application_open": {
        "exclude_page_types": ["dealer"],
        "suppress_phrases": _REVERSE + _RETAILER_SIDE,
    },
    "new_supplier_partnership": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": [
            "distribute", "distribution", "distributor", "distributing",
            "brand", "brands", "retailers", "pet specialty"],
    },
    "new_brand_added": {
        "exclude_page_types": ["dealer"],
        "suppress_phrases": ["looking for", "seeking", "submit", "interested in",
                             "our new brand identity", "welcomes you"] + _REVERSE,
        "require_context_phrases": PET_CONTEXT,
    },
    "food_category_expansion": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": FOOD_CONTEXT,
    },
    "treats_category_expansion": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": TREAT_CONTEXT,
    },
    "supplement_category_expansion": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": SUPPLEMENT_CONTEXT,
    },
    "premium_natural_portfolio_expansion": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": PREMIUM_CONTEXT,
    },
    "product_line_launch": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": PET_CONTEXT,
    },
    "catalog_linecard_expansion": {
        "require_context_phrases": ["new", "added", "adds", "expanded",
                                    "expands", "expansion", "now includes",
                                    "additional"],
    },
    "category_manager_hiring": {"require_page_types": ["careers", "job"]},
    "purchasing_manager_hiring": {"require_page_types": ["careers", "job"]},
    "procurement_hiring": {"require_page_types": ["careers", "job"]},
    "merchandising_hiring": {"require_page_types": ["careers", "job"]},
    "vendor_relations_expansion": {"require_page_types": ["careers", "job"]},
    "private_label_expansion": {
        "require_context_phrases": ["expand", "expands", "expanded", "expanding",
                                    "launch", "launches", "new", "adds", "added"],
    },
    "acquisition_expansion": {
        "require_context_phrases": ["distributor", "distribution",
                                    "distributing", "pet", "wholesale"],
    },
    "regional_distribution_expansion": {
        "require_context_phrases": ["distribution", "distributor", "wholesale",
                                    "retailers", "stores", "delivery"],
    },
}

SIGNAL_PAGE_AFFINITY: dict[str, list[str]] = {
    "active_supplier_request": ["supplier", "news", "press_release", "website",
                                "about", "other"],
    "active_product_category_request": ["supplier", "news", "press_release",
                                        "website", "other"],
    "active_product_rfq": ["supplier", "news", "press_release", "website", "other"],
    "supplier_application_open": ["supplier", "website", "other", "about"],
    "new_supplier_partnership": ["news", "press_release", "website", "brands",
                                 "about"],
    "new_brand_added": ["news", "press_release", "brands", "website"],
    "food_category_expansion": ["news", "press_release", "website", "brands"],
    "treats_category_expansion": ["news", "press_release", "website", "brands"],
    "supplement_category_expansion": ["news", "press_release", "website", "brands"],
    "premium_natural_portfolio_expansion": ["news", "press_release", "website",
                                            "brands"],
    "product_line_launch": ["news", "press_release", "website", "brands"],
    "catalog_linecard_expansion": ["brands", "website", "news", "press_release"],
    "category_manager_hiring": ["careers", "job"],
    "purchasing_manager_hiring": ["careers", "job"],
    "procurement_hiring": ["careers", "job"],
    "merchandising_hiring": ["careers", "job"],
    "vendor_relations_expansion": ["careers", "job"],
    "distribution_center_expansion": ["news", "press_release", "about", "website"],
    "regional_distribution_expansion": ["news", "press_release", "about", "website"],
    "retail_network_expansion": ["news", "press_release", "about", "website",
                                 "dealer"],
    "private_label_expansion": ["news", "press_release", "brands", "website"],
    "acquisition_expansion": ["news", "press_release", "about"],
}

# Four product-interest states. Stored codes are the platform's generic ones;
# the dashboard shows this service's names via ui_labels.interest_types.
# supplier_application_open is deliberately NOT mapped: an evergreen vendor
# program is openness to brands, not demand for a product.
# Warehouse/territory/hiring signals are never mapped to products either.
INTEREST_TYPE_BY_SIGNAL = {
    "active_supplier_request": "EXPLICITLY_SEEKING",
    "active_product_category_request": "EXPLICITLY_SEEKING",
    "active_product_rfq": "EXPLICITLY_SEEKING",
    "new_supplier_partnership": "RECENTLY_ADDED",
    "new_brand_added": "RECENTLY_ADDED",
    "food_category_expansion": "RECENTLY_ADDED",
    "treats_category_expansion": "RECENTLY_ADDED",
    "supplement_category_expansion": "RECENTLY_ADDED",
    "premium_natural_portfolio_expansion": "RECENTLY_ADDED",
    "product_line_launch": "RECENTLY_ADDED",
    "catalog_linecard_expansion": "RECENTLY_ADDED",
}

COMPANY_TYPE_MARKERS: dict[str, list[str]] = {
    # Distribution evidence only. Wording a brand also uses about its own
    # wholesale program ("b2b", "retail partners", "wholesale account",
    # "become a retailer") is deliberately absent: it cannot tell a pet
    # distributor from a pet brand selling to stores.
    "pet_specialty_distributor": [
        "wholesale distributor", "wholesale distribution", "we distribute",
        "pet specialty distributor", "pet food distributor",
        "brands we carry", "brands we distribute", "brands we represent",
        "line card", "linecard", "distribution center", "distribution centers",
        "master distributor", "delivery routes", "sales territory",
        "b2b distribution", "brand application", "partner with brands",
        "we partner with brands", "brand partners", "responsible distributor",
        "products we carry", "lines we carry", "territory footprint",
        "independent pet specialty", "pet specialty segment",
        "pet speciality segment",
        # how distributors describe themselves (brands do not say this)
        "pet supply distributor", "pet supplies distributor",
        "wholesale pet supply distributor", "full-line distributor",
        "full line distributor", "regional distributor",
        "regional pet supply distributor", "serving independent retailers",
        "distributing independent brands", "proudly distributing",
        "distributing quality pet", "pet products to stores",
        "supplying pet retailers", "supplying independent pet",
        # a distributor's split navigation: retailers buy, brands apply
        "own a store", "have a product",
        # who they sell to - two distinct phrases at most
        "independent pet retailers", "pet specialty retailers"],
    "manufacturer": [
        "we manufacture", "our kitchen", "our manufacturing facility",
        "manufacturing facility", "manufactured in", "co-packer",
        "co-manufacturing", "our production facility", "we make our",
        "made in our own"],
    "brand_owner": [
        "find a retailer", "store locator", "where to buy",
        "looking for distributors", "become a distributor",
        "distributor inquiries", "subscribe and save", "shop now",
        "our products are sold", "available at fine pet retailers",
        # direct-to-consumer storefront language
        "add to cart", "free shipping on orders", "orders ship within",
        "shop all", "shop the collection", "our story", "new arrivals",
        "join our pack", "learn more about these products",
        "carry our products", "our recipes", "veterinarian formulated"],
    # software sold to pet brands or retailers - never a buyer of product
    "software_or_service_vendor": [
        "book a demo", "request a demo", "free trial", "start your free trial",
        "go to dashboard", "pricing plans", "per month", "saas",
        "software platform", "find the buyers", "find retailers for your",
        "sign up free", "api access"],
    # B2B sourcing marketplaces and directories list suppliers; they do not buy
    "b2b_marketplace": [
        "verified suppliers", "b2b sourcing platform", "sourcing platform",
        "all suppliers", "low moq", "post a buying request", "live requests",
        "supplier directory", "find suppliers", "list your products",
        "trade assurance", "become a supplier"],
    "pet_retailer": [
        "visit our store", "store hours", "in-store pickup", "curbside pickup",
        "shop our store", "pet boutique", "frequent buyer program",
        "self-serve dog wash", "our store", "locally owned pet store"],
    "veterinary_clinic": [
        "veterinary clinic", "animal hospital", "schedule an appointment",
        "our veterinarians", "wellness exams", "spay and neuter"],
    "pet_service_provider": [
        "dog grooming", "grooming appointment", "boarding and daycare",
        "doggy daycare", "pet sitting", "dog walking", "dog training classes"],
    "veterinary_supplier": [
        "veterinary distributor", "veterinary practices", "animal health distributor",
        "veterinary clinics nationwide", "serving veterinarians"],
}

HYBRID_COMPANY_TYPES = {
    "hybrid_distributor_manufacturer": ["pet_specialty_distributor", "manufacturer"],
    "hybrid_distributor_retailer": ["pet_specialty_distributor", "pet_retailer"],
}

INDUSTRY_KEYWORDS = {
    "pet": [
        "pet food", "pet specialty", "pet supplies", "pet products", "dog food",
        "cat food", "dog treats", "cat treats", "pet treats", "pet supplements",
        "dog chews", "pet nutrition", "independent pet", "pet retailers",
        "pet stores", "pet industry", "companion animal", "bully sticks",
        "dog supplements", "cat supplements"],
}

ROLES: list[tuple[str, int]] = [
    # purchasing / supplier onboarding owners first
    ("vp of purchasing", 1), ("vice president of purchasing", 1),
    ("vp purchasing", 1), ("vice president, purchasing", 1),
    ("director of purchasing", 2), ("purchasing director", 2),
    ("head of purchasing", 2), ("purchasing manager", 3),
    ("category director", 4), ("director of category management", 4),
    ("category manager", 5), ("senior category manager", 5),
    ("director of merchandising", 6), ("merchandising director", 6),
    ("product line manager", 7), ("product manager", 8),
    ("procurement manager", 9), ("sourcing manager", 10),
    ("vendor relations manager", 11), ("supplier relations manager", 11),
    ("senior buyer", 9), ("buyer", 10),
    # at mid-sized distributors the owner or president often buys
    ("owner", 3), ("co-owner", 3), ("founder", 4), ("co-founder", 4),
    ("president", 4), ("ceo", 4), ("chief executive officer", 4),
    ("coo", 6), ("chief operating officer", 6),
    ("director of business development", 12),
    ("vp of business development", 12),
    # a longer pattern than 'president' so 'Vice President of Sales' is not
    # mistaken for the President
    ("vice president", 13),
]

CRAWL_PRIORITY_PATHS = [
    ["/", "website"], ["/about", "about"], ["/about-us", "about"],
    ["/brands", "brands"], ["/our-brands", "brands"], ["/line-card", "brands"],
    ["/vendors", "supplier"], ["/become-a-vendor", "supplier"],
    ["/info/become-a-vendor", "supplier"], ["/vendor-application", "supplier"],
    ["/suppliers", "supplier"], ["/new-vendors", "supplier"],
    ["/news", "news"], ["/press", "news"], ["/careers", "careers"],
    ["/retailers", "dealer"], ["/wholesale-account", "dealer"],
    ["/contact", "other"],
]

EXTERNAL_QUERY_TEMPLATES = [
    ["press_release", '"{name}" "now available through" OR "distribution partnership" '
                      'OR "distribution agreement" OR "adds"', "news"],
    ["news", '"{name}" site:petfoodprocessing.net OR site:petfoodindustry.com '
             'OR site:petbusiness.com OR site:petage.com', "web"],
    ["supplier", '"{name}" "vendor application" OR "become a vendor" OR '
                 '"submit your product" OR "new brands"', "web"],
    ["job", '"{name}" "category manager" OR "purchasing manager" OR "buyer" '
            'OR "procurement"', "web"],
    ["press_release", '"{name}" "distribution center" OR warehouse OR '
                      'acquires OR acquisition', "news"],
]

# Trade publications, marketplaces, big-box retail and regulators are
# evidence sources, never distributor prospects.
DISCOVERY_BLOCKED_DOMAINS = [
    "petfoodprocessing.net", "petfoodindustry.com", "petbusiness.com",
    "petage.com", "globalpetexpo.org", "superzoo.org", "petfoodforum.com",
    "petproductnews.com", "americanpetproducts.org", "appa.org",
    "fda.gov", "aafco.org", "nasc.cc", "chewy.com", "petco.com",
    "petsmart.com", "amazon.com", "walmart.com", "target.com",
    "tractorsupply.com", "petsupermarket.com", "petvalu.com",
    "thomasnet.com", "zoominfo.com", "dnb.com", "manta.com", "bbb.org",
    "yellowpages.com", "yelp.com", "mapquest.com", "rocketreach.co",
    "apollo.io", "faire.com", "rangeme.com", "facebook.com", "linkedin.com",
    "instagram.com", "youtube.com", "reddit.com", "indeed.com",
    "glassdoor.com",
]

AI_SYSTEM_PROMPT = (
    "You are a B2B supply-chain analyst for pet food, treat and supplement "
    "manufacturers that want to sell through US pet specialty distributors. "
    "Analyze whether this company is a genuine US pet specialty distributor "
    "or wholesaler and determine what public evidence indicates that it is "
    "purchasing, onboarding or expanding its portfolio of pet food, treats, "
    "chews and supplements. Commercial direction matters: a distributor "
    "inviting retailers to open wholesale accounts is selling, not buying; a "
    "brand looking for distributors is the opposite direction and is not a "
    "buyer; a pet store buying from wholesalers is retail purchasing. "
    "Distinguish seeking suppliers, accepting supplier submissions, recently "
    "onboarding a supplier, currently carrying a product and a possible "
    "category fit - these are different claims. Use only the supplied "
    "evidence. Never invent products, brands, ingredients, purchasing "
    "requirements, employee counts or revenue. A general growth announcement "
    "is not a specific purchasing requirement. Product health or quality "
    "statements are the company's own marketing claims: never describe them "
    "as proven, veterinary or FDA-approved, and never turn 'supports joint "
    "health' into a disease treatment claim.")

AI_TASK = (
    "Analyze whether this company is a genuine US pet specialty distributor "
    "or wholesaler and determine what public evidence indicates that it is "
    "purchasing, onboarding or expanding its portfolio of pet food, treats, "
    "chews and supplements. Put the probability that it is actively expanding "
    "its supplier or product portfolio in service_probability. Put only "
    "product categories named in the evidence in likely_services. If no "
    "specific product requirement is identifiable, say exactly: Specific "
    "product demand not publicly disclosed.")

AI_EXTRA_FIELDS = {
    "distributor_qualification": '"qualified" | "possible" | "not_qualified" | "unknown"',
    "distributor_qualification_reason": "string citing evidence",
    "company_size_qualification": '"mid_market" | "small" | "micro" | "large" | "unknown" - never guess',
    "wholesale_distribution_model": "string - only what the evidence shows",
    "supplier_onboarding_evidence": "[string]",
    "distribution_partnerships": "[string] - brands named in the evidence",
    "recently_added_brands": "[string] - brands named in the evidence",
    "product_categories": "[string] - only categories named in the evidence",
    "products_mentioned": "[string] - only products named in the evidence",
    "species_and_formats": "[string] - only as stated in the evidence",
    "purchasing_hiring": "[string]",
    "recent_expansion_activity": "[string]",
    "likely_decision_roles": "[string] - job titles, never personal contact data",
    "evidence_gaps": "[string] - what is unknown or uncertain",
}

CONFIG: dict = {
    "score_weights": {"deterministic": 0.5, "ai": 0.3, "evidence": 0.2},
    "intent_thresholds": {"LOW": 0, "POSSIBLE": 31, "GOOD": 51,
                          "STRONG": 71, "HOT": 86},
    "normalization_ceiling": 90,
    "decision_maker_threshold": 40,
    "decision_maker_optional_threshold": 30,
    "ai_analysis_min_raw_score": 20,
    "required_signals": ["pet_specialty_participation"],
    "signal_dimensions": SIGNAL_DIMENSIONS,
    # Intent is capped so an evergreen vendor page plus a few expansion hits
    # cannot reach HOT without a current, specific request.
    "dimension_caps": {"intent": 40},
    "signal_rules": SIGNAL_RULES,
    "signal_page_affinity": SIGNAL_PAGE_AFFINITY,
    "undated_confidence_factor": 0.75,
    "refresh_days": {"HOT": 7, "STRONG": 14, "GOOD": 30, "POSSIBLE": 60,
                     "LOW": 120},
    "exclude_logistics_providers": False,
    "excluded_business_types": [
        "marketing agency", "seo agency", "web development agency",
        "digital agency", "software company", "saas platform",
        "consulting firm", "law firm", "recruitment agency", "staffing agency",
        "insurance agency", "trade publication", "animal shelter",
        "rescue organization"],
    "query_exclusion_terms": ["for sale", "adoption", "puppies for sale",
                              "near me"],
    "qualification": {
        "eligible_company_types": ["pet_specialty_distributor",
                                   "hybrid_distributor_manufacturer",
                                   "hybrid_distributor_retailer",
                                   "veterinary_supplier"],
        "reject_company_types": ["pet_retailer", "veterinary_clinic",
                                 "pet_service_provider", "manufacturer",
                                 "brand_owner", "software_or_service_vendor",
                                 "b2b_marketplace"],
        # Pet brands vastly outnumber pet distributors and many have a
        # "wholesale" page, so a company must show distributor evidence. A
        # real distributor with a weak BUYING signal still qualifies.
        "unknown_company_type": "reject",
        "company_type_min_markers": 2,
        "allowed_countries": ["US"],
        "min_country_confidence": 0.6,
        "require_country_evidence": True,
        "allow_unverified_location_tlds": ["com", "net", "us", "org", "biz"],
        # Mid-market focus. A company that STATES a size outside 50-500 is
        # rejected and kept with that reason, so large national distributors
        # sit in their own rejected-by-size group instead of dominating the
        # lead list. Unknown size is never rejected.
        "excluded_employee_bands": ["large", "small", "micro"],
        "required_industry": "pet",
        "min_industry_markers": 1,
        "industry_implies_physical": True,
    },
    "company_type_markers": COMPANY_TYPE_MARKERS,
    "hybrid_company_types": HYBRID_COMPANY_TYPES,
    "industry_keywords": INDUSTRY_KEYWORDS,
    "size_bands": [
        {"band": "micro", "min": 1, "max": 10},
        {"band": "small", "min": 11, "max": 49},
        {"band": "mid_market", "min": 50, "max": 500},
        {"band": "large", "min": 501, "max": None},
    ],
    "fit_multipliers": {
        "employee_band": {"mid_market": 1.0, "small": 0.85, "unknown": 0.8,
                          "large": 0.6, "micro": 0.55},
        "company_type": {"pet_specialty_distributor": 1.0,
                         "hybrid_distributor_manufacturer": 0.9,
                         "hybrid_distributor_retailer": 0.8,
                         "veterinary_supplier": 0.6,
                         "unknown": 0.75, "default": 0.5},
    },
    "product_taxonomy": PRODUCT_TAXONOMY,
    "adjacent_categories": ADJACENT_CATEGORIES,
    "vehicle_segments": SPECIES,          # generic "segments" = species here
    "vehicle_platforms": [],
    "product_attributes": PRODUCT_ATTRIBUTES,
    "brand_patterns": BRAND_PATTERNS,
    "interest_type_by_signal": INTEREST_TYPE_BY_SIGNAL,
    "carried_page_types": ["brands", "website", "about", "other"],
    "no_product_demand_message": "Specific product demand not publicly disclosed.",
    "ui_labels": {
        "title": "Pet Specialty Buying Intelligence · US",
        "segment": "Species",
        "interest_types": {
            "EXPLICITLY_SEEKING": "Explicitly seeking",
            "RECENTLY_ADDED": "Recently onboarded",
            "CURRENTLY_CARRIED": "Currently carried",
            "INFERRED_FIT": "Inferred category fit",
        },
    },
    "crawl_priority_paths": CRAWL_PRIORITY_PATHS,
    "crawl_max_pages": 16,
    "crawl_link_first_page_types": ["supplier", "brands", "news", "careers",
                                    "about"],
    "external_query_templates": EXTERNAL_QUERY_TEMPLATES,
    "external_fetchers": ["ats"],
    "fetch_external_articles": 3,
    "discovery_blocked_domains": DISCOVERY_BLOCKED_DOMAINS,
    "ai_system_prompt": AI_SYSTEM_PROMPT,
    "ai_task": AI_TASK,
    "ai_extra_fields": AI_EXTRA_FIELDS,
    "ai_grounded_fields": ["likely_services", "product_categories",
                           "products_mentioned", "distribution_partnerships",
                           "recently_added_brands"],
    "ai_probability_field": "buying_intent_probability",
}


# =====================================================================
# DISCOVERY QUERY LIBRARY - deliberately small for the first controlled
# runs. Measure qualification and intent precision before scaling.
#   1  explicit supplier requests, vendor applications, RFQs
#   2  new brands, partnerships, category expansions
#   3  target distributor discovery and qualification
#   4  purchasing hiring and business expansion
# No parentheses: the SQL row parser forbids them.
# =====================================================================
@dataclass(frozen=True)
class Query:
    text: str
    tier: int
    country: str | None = "US"
    group: str = ""


_SUPPLIER_INTENT = [
    "pet food distributor accepting new brands",
    "pet specialty distributor become a vendor",
    "pet food distributor supplier application",
    "pet distributor submit your product",
    "pet food wholesale vendor application",
    "distributor looking for new pet food brands",
    "pet specialty distributor seeking new suppliers",
    "pet treats distributor brand submission",
    "pet supplement distributor supplier opportunities",
    "wholesale pet product sourcing new suppliers",
    "new pet food supplier partnerships distributor",
    "pet nutrition distributor new product submissions",
    "pet distributor new vendor setup",
    "pet specialty wholesaler vendor onboarding",
]
_PORTFOLIO_EXPANSION = [
    "pet food distributor new brand partnership",
    "pet specialty distributor expanding portfolio",
    "pet food distributor adds new treats brand",
    "dog supplement distribution partnership",
    "cat food distributor new product line",
    "premium pet food wholesale expansion",
    "natural pet treats distribution agreement",
    "pet distributor expands supplement portfolio",
    "functional pet nutrition new distribution agreement",
    "pet food distributor adds new manufacturer",
    "pet distributor expanding category assortment",
    "now available through pet specialty distributor",
    "expands distribution with pet specialty distributor",
]
_CATEGORIES = [
    "premium dog food", "premium cat food", "fresh and frozen pet food",
    "freeze-dried raw pet food", "natural dog treats", "functional dog treats",
    "dental chews", "single-ingredient dog treats", "bully sticks and natural chews",
    "dog joint supplements", "pet probiotics", "dog calming chews",
    "pet omega-3 fish oil", "skin and coat supplements for dogs",
    "senior pet nutrition", "functional pet wellness supplements",
]
_DISTRIBUTOR_DISCOVERY = [
    "pet food distributors USA",
    "pet specialty food wholesalers",
    "independent pet store wholesale distributors",
    "natural pet food distributors",
    "premium pet food wholesale suppliers",
    "dog food wholesale distributors",
    "cat food wholesale distributors",
    "pet treat distributors USA",
    "dog chews wholesale distributors",
    "pet supplement wholesale distributors",
    "functional pet nutrition distributors",
    "specialty pet product distribution companies",
    "regional pet food wholesalers",
    "pet specialty distributors supplying independent retailers",
    "frozen raw pet food distributors",
    "pet health and wellness product wholesalers",
    "pet food distribution companies supplying retail stores",
]
_HIRING_EXPANSION = [
    "pet food distributor purchasing manager hiring",
    "pet distributor category manager jobs",
    "pet food wholesaler procurement hiring",
    "pet specialty distributor warehouse expansion",
    "pet food distributor new distribution center",
    "pet distributor expanding retailer network",
    "pet product distributor acquisition",
    "pet food wholesaler new regional operations",
]


# State-by-state distributor discovery. The first live run showed that
# searches naming the distributor directly yield real distributors, while
# category and expansion searches mostly surface brands and trade press.
_STATES = [
    "Alabama", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts",
    "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska",
    "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
]
_STATE_DISTRIBUTOR_TYPES = [
    "pet food distributor",
    "wholesale pet supplies distributor",
    "pet supply distributor for independent pet stores",
]


def build_library() -> list[Query]:
    out: list[Query] = []

    def add(text: str, tier: int, group: str) -> None:
        out.append(Query(text=text, tier=tier, group=group))

    for text in _SUPPLIER_INTENT:
        add(text, 1, "supplier_intent")
    for text in _PORTFOLIO_EXPANSION:
        add(text, 2, "portfolio_expansion")
    for category in _CATEGORIES:
        add(f"{category} distributor adds new brand", 2, "category_expansion")
        add(f"{category} wholesale distributor for pet retailers", 3,
            "category_distributors")
    for text in _DISTRIBUTOR_DISCOVERY:
        add(text, 3, "distributor_discovery")
    for text in _HIRING_EXPANSION:
        add(text, 4, "hiring_expansion")
    for kind in _STATE_DISTRIBUTOR_TYPES:
        for state in _STATES:
            add(f"{kind} {state}", 3, "state_distributors")

    seen: set[tuple[str, str | None]] = set()
    unique: list[Query] = []
    for q in out:
        key = (q.text.lower(), q.country)
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
    return unique


def stats(library: list[Query] | None = None) -> dict:
    library = library if library is not None else build_library()
    by_tier: dict[int, int] = {}
    for q in library:
        by_tier[q.tier] = by_tier.get(q.tier, 0) + 1
    return {"total": len(library), "by_tier": dict(sorted(by_tier.items()))}

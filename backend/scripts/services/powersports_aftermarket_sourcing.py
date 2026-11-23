"""Service definition: Powersports Aftermarket Product Sourcing.

The ONLY place in the system that knows what powersports, a UTV bumper or a
supplier application is. Everything here is data consumed by the generic
engine through ServiceConfig:

    migrations/007_powersports_aftermarket_sourcing.sql   (generated)
    scripts/seed.py                                        (ORM path)

Rebuild the SQL after editing:
    python -m scripts.build_service_seed powersports_aftermarket_sourcing

Commercial direction this service scores (the part that is easy to get
wrong):
    distributor -> manufacturer/supplier   buying       POSITIVE intent
    distributor -> dealer                  selling      fit only, NO intent
    manufacturer -> distributor            seeking us   NEGATIVE
Weights are starting configuration, not validated probabilities. Recalibrate
against lead reviews.
"""
from __future__ import annotations

from dataclasses import dataclass

SLUG = "powersports_aftermarket_sourcing"
NAME = "Powersports Aftermarket Product Sourcing"
DESCRIPTION = (
    "Find mid-market US wholesale distributors of aftermarket powersports "
    "parts and accessories that show public, evidenced intent to source new "
    "products, onboard new brands or expand categories - and which products "
    "they may be looking to buy.")

# =====================================================================
# PRODUCT TAXONOMY  {category: {subcategory: [terms]}}
# Terms are matched as whole phrases, singular/plural tolerant.
# =====================================================================
PRODUCT_TAXONOMY: dict[str, dict[str, list[str]]] = {
    "ATV/UTV/Side-by-Side Accessories": {
        "Bumpers": ["front bumper", "rear bumper", "bumper"],
        "Rock Sliders": ["rock slider", "rock sliders", "nerf bar"],
        "Skid Plates": ["skid plate", "skid plates", "belly pan"],
        "Roof Systems": ["roof system", "utv roof", "hard top", "soft top"],
        "Windshields": ["windshield", "windscreen", "half windshield",
                        "full windshield"],
        "Windshield Wipers": ["windshield wiper", "wiper kit"],
        "Cab Enclosures": ["cab enclosure", "cab enclosures", "cab heater",
                           "rear window"],
        "Doors and Door Panels": ["utv door", "door panel", "upper door",
                                  "lower door", "suicide door"],
        "Roof Racks": ["roof rack"],
        "Cargo Racks": ["cargo rack", "cargo box", "rack extender"],
        "Storage Systems": ["storage bag", "storage system", "under-seat storage",
                            "dash storage"],
        "Tire Carriers": ["tire carrier", "spare tire carrier", "spare tire mount"],
        "Grilles": ["grille", "grill guard", "brush guard"],
        "Mirrors": ["side mirror", "rear view mirror", "rearview mirror",
                    "utv mirror"],
        "Winches": ["winch", "winches", "winch mount", "synthetic rope"],
        "Recovery Accessories": ["recovery strap", "recovery kit", "tow strap",
                                 "traction board", "snatch block"],
        "Lighting Systems": ["light bar", "whip light", "rock light",
                             "pod light", "utv lighting"],
    },
    "Tires and Wheels": {
        "ATV Tires": ["atv tire"],
        "UTV Tires": ["utv tire", "side-by-side tire", "sxs tire"],
        "Motorcycle Tires": ["motorcycle tire", "dirt bike tire",
                             "street tire", "dual sport tire"],
        "Off-Road Tires": ["off-road tire", "mud tire", "all-terrain tire"],
        "Specialty Wheels": ["beadlock wheel", "specialty wheel", "atv wheel",
                             "utv wheel"],
        "Performance Wheels": ["performance wheel", "forged wheel",
                               "cast wheel", "spoked wheel"],
        "Tire and Wheel Systems": ["tire and wheel kit", "wheel and tire package",
                                   "mounted tire", "tire and wheel package"],
    },
    "Motorcycle Aftermarket Accessories": {
        "Crash Protection": ["crash protection", "engine guard", "highway bar"],
        "Crash Bars": ["crash bar"],
        "Frame Sliders": ["frame slider", "crash slider", "axle slider"],
        "Touring Luggage": ["touring luggage", "motorcycle luggage",
                            "tail bag", "tank bag"],
        "Saddlebags": ["saddlebag", "saddle bag"],
        "Panniers": ["pannier"],
        "Top Cases": ["top case", "top box"],
        "Motorcycle Racks": ["luggage rack", "motorcycle rack", "sissy bar"],
        "Windscreens": ["motorcycle windscreen", "fairing", "wind deflector"],
        "Handguards": ["handguard", "hand guard"],
        "Styling Accessories": ["motorcycle styling", "chrome accessories",
                                "custom grips", "foot pegs", "billet accessories"],
        "Adventure Touring Products": ["adventure touring", "adv accessories",
                                      "adventure bike"],
    },
    "Riding Gear and Protection": {
        "Helmets": ["helmet", "helmets"],
        "Gloves": ["riding gloves", "motorcycle gloves", "mx gloves"],
        "Boots": ["riding boots", "motorcycle boots", "mx boots",
                  "motocross boots"],
        "Jerseys": ["jersey", "jerseys"],
        "Riding Pants": ["riding pants", "mx pants", "motocross pants"],
        "Jackets": ["riding jacket", "motorcycle jacket"],
        "Goggles": ["goggle", "goggles"],
        "Body Armour": ["body armor", "body armour", "chest protector",
                        "roost guard"],
        "Knee Protection": ["knee brace", "knee guard", "knee protection"],
        "Neck Protection": ["neck brace", "neck protection"],
        "Snowmobile Apparel": ["snowmobile apparel", "snowmobile jacket",
                               "snowmobile bib", "monosuit"],
        "Motocross Apparel": ["motocross apparel", "mx apparel", "mx gear",
                              "motocross gear"],
        "Casual Riding Apparel": ["casual apparel", "riding apparel",
                                  "moto apparel", "lifestyle apparel"],
    },
    "Electrical and Performance": {
        "Batteries": ["battery", "batteries", "lithium battery", "agm battery"],
        "Charging Systems": ["battery charger", "battery tender",
                             "charging system", "stator"],
        "LED Lighting": ["led lighting", "led headlight", "led light"],
        "Electrical Accessories": ["electrical accessories", "usb charger",
                                   "power outlet", "switch panel"],
        "Wiring Harnesses": ["wiring harness", "wire harness"],
        "Exhaust Systems": ["exhaust system", "slip-on exhaust", "full exhaust",
                            "muffler"],
        "Engine Upgrades": ["big bore kit", "engine upgrade", "cam kit",
                            "turbo kit", "clutch kit"],
        "Performance Tuners": ["fuel programmer", "performance tuner",
                               "ecu flash", "fuel controller"],
        "EFI Components": ["efi", "fuel injector", "throttle body"],
        "Suspension Components": ["suspension", "shock absorber", "shocks",
                                  "lift kit", "a-arm", "fork spring"],
        "Brake Components": ["brake pad", "brake rotor", "brake line",
                             "brake caliper"],
        "Tire Balancing Products": ["tire balancing", "balance beads",
                                    "wheel weight"],
    },
    "Maintenance and Consumables": {
        "Lubricants": ["lubricant", "lubricants", "chain lube", "grease"],
        "Engine Oils": ["engine oil", "motor oil", "4-stroke oil",
                        "2-stroke oil"],
        "Filters": ["oil filter", "air filter", "fuel filter"],
        "Chains": ["drive chain", "motorcycle chain", "o-ring chain",
                   "x-ring chain"],
        "Sprockets": ["sprocket", "sprockets"],
        "Maintenance Kits": ["maintenance kit", "service kit", "tune-up kit"],
        "Cleaning Products": ["cleaning products", "bike wash", "degreaser",
                              "detailing"],
        "Chemicals": ["chemicals", "fuel stabilizer", "coolant",
                      "brake fluid"],
        "Workshop Consumables": ["shop supplies", "workshop consumables",
                                 "zip ties", "shop towels"],
    },
}

# Adjacency used ONLY for INFERRED_FIT records, which are never presented as
# buying intent.
ADJACENT_CATEGORIES: dict[str, list[str]] = {
    "ATV/UTV/Side-by-Side Accessories": ["Tires and Wheels",
                                         "Electrical and Performance"],
    "Tires and Wheels": ["ATV/UTV/Side-by-Side Accessories",
                         "Maintenance and Consumables"],
    "Motorcycle Aftermarket Accessories": ["Riding Gear and Protection",
                                           "Electrical and Performance"],
    "Riding Gear and Protection": ["Motorcycle Aftermarket Accessories"],
    "Electrical and Performance": ["Maintenance and Consumables"],
    "Maintenance and Consumables": ["Electrical and Performance"],
}

VEHICLE_SEGMENTS: dict[str, list[str]] = {
    "ATV": ["atv", "atvs", "quad", "four wheeler"],
    "UTV/Side-by-Side": ["utv", "utvs", "side-by-side", "side by side", "sxs"],
    "Motorcycle - Street/Touring": ["touring", "cruiser", "street bike",
                                    "sportbike", "bagger"],
    "Motorcycle - Off-Road/Motocross": ["motocross", "dirt bike", "mx",
                                        "enduro", "off-road motorcycle"],
    "Motorcycle - Adventure": ["adventure bike", "adventure touring",
                               "dual sport"],
    "Snowmobile": ["snowmobile", "snowmobiles", "sled", "sleds"],
}

# Vehicle OEMs: fitment / platform context, never treated as a supplier.
VEHICLE_PLATFORMS: list[str] = [
    "Polaris", "Can-Am", "CFMOTO", "Kawasaki", "Yamaha", "Honda", "Suzuki",
    "KTM", "Harley-Davidson", "Arctic Cat", "Ski-Doo", "BRP", "Textron",
    "Segway Powersports", "Husqvarna", "GasGas", "Ducati", "BMW Motorrad",
    "Triumph", "Indian Motorcycle", "Hisun", "Kymco", "Massimo", "RZR",
    "Ranger", "Maverick", "Defender", "Talon", "Pioneer", "Teryx", "Wolverine",
]

_B = r"([A-Z][A-Za-z0-9&'\-]+(?:\s+[A-Z][A-Za-z0-9&'\-]+){0,3})"
BRAND_PATTERNS: list[str] = [
    r"distribution (?:agreement|partnership|deal) with " + _B,
    r"(?:exclusive|official|authorized|master) (?:US |U\.S\. |North American |"
    r"national )?distributor (?:of|for) " + _B,
    r"(?:now|will) (?:distribute|distributing|carry|carrying|stock|stocking) " + _B,
    r"(?:added|adds|adding|welcomes|welcomed) " + _B + r" (?:to (?:its|our|the) "
    r"(?:lineup|line card|brand portfolio|portfolio|catalog|offering))",
    r"partner(?:ed|ship)? with " + _B,
]

POWERSPORTS_CONTEXT = [
    "powersports", "power sports", "atv", "utv", "side-by-side", "side by side",
    "sxs", "motorcycle", "motorcycles", "dirt bike", "motocross", "snowmobile",
    "off-road", "offroad", "aftermarket", "v-twin", "moto",
]

# =====================================================================
# SIGNALS  (signal_type, name, description, weight, decay_days, max_occ)
# Descriptions must not contain parentheses - the SQL row parser forbids it.
# =====================================================================
SIGNALS: list[tuple[str, str, str, float, int | None, int]] = [
    # ---- Tier 1: direct buying intent ----
    ("active_product_rfq", "Active Product RFQ",
     "Public request for quotes or a specific product requirement directed at suppliers",
     35, 90, 1),
    ("explicit_supplier_search", "Explicit Supplier Search",
     "Distributor explicitly asks for new suppliers, manufacturers, products or brands",
     30, 120, 1),
    ("supplier_application_open", "Supplier Application Open",
     "A genuine supplier or vendor submission process exists. Proves openness to proposals, "
     "not an active sourcing project. Revalidated every 180 days by re-crawl",
     22, 180, 1),
    # ---- Tier 2: recent purchasing and product expansion ----
    ("new_distribution_partnership", "New Distribution Partnership",
     "Newly signed distribution agreement with a manufacturer or brand", 27, 180, 1),
    ("new_brand_added", "New Brand Added",
     "A new aftermarket brand was added to the distributor portfolio", 25, 180, 1),
    ("product_category_expansion", "Product Category Expansion",
     "Expansion into a new product category or a material range increase", 23, 180, 1),
    ("new_product_line_launch", "New Product Line Launch",
     "Upcoming or recently launched product lines", 18, 150, 1),
    ("catalog_or_linecard_expansion", "Catalog or Line Card Expansion",
     "Material category or brand expansion in the current catalog or line card", 15, 180, 1),
    # ---- Tier 3: purchasing capacity and expansion ----
    ("category_buyer_hiring", "Category Buyer Hiring",
     "Hiring category managers, buyers or merchandise managers who own assortment", 17, 120, 1),
    ("procurement_hiring", "Procurement Hiring",
     "Hiring purchasing, sourcing or procurement professionals", 15, 120, 1),
    ("distribution_center_expansion", "Distribution Center Expansion",
     "New warehouse, distribution centre or major inventory-capacity expansion", 13, 270, 1),
    ("dealer_network_expansion", "Dealer Network Expansion",
     "Entering new territories or materially expanding B2B dealer coverage", 12, 180, 1),
    ("acquisition_or_distribution_expansion", "Acquisition or Distribution Expansion",
     "Acquired a distributor, added regional distribution or materially expanded operations",
     12, 270, 1),
    # ---- Business fit: evidence of WHAT the company is, never of buying ----
    ("powersports_participation", "Powersports Participation",
     "Verifiable participation in the powersports aftermarket", 5, None, 1),
    ("b2b_dealer_distribution", "B2B Dealer Distribution",
     "Supplies dealers or resellers - the distributor-to-dealer direction. Fit, not buying intent",
     6, None, 1),
    # ---- Negative polarity: wrong commercial direction or wrong business ----
    ("manufacturer_seeking_distribution", "Manufacturer Seeking Distribution",
     "The company is looking for distributors for its own products - the opposite direction",
     -25, None, 1),
    ("retail_only_operation", "Retail-Only Operation",
     "Consumer showroom or unit-sales language with no wholesale operation", -15, None, 1),
    ("service_repair_operation", "Service or Repair Operation",
     "Repair or service business rather than a distributor", -12, None, 1),
]

SIGNAL_DIMENSIONS = {
    "powersports_participation": "fit",
    "b2b_dealer_distribution": "fit",
    "manufacturer_seeking_distribution": "negative",
    "retail_only_operation": "negative",
    "service_repair_operation": "negative",
}

# =====================================================================
# KEYWORDS  (keyword, category, signal_type, weight)
# category 'hiring' marks the signals that get the structured job boost.
# =====================================================================
def _kw(signal: str, category: str, weight: float, *phrases: str):
    return [(p, category, signal, weight) for p in phrases]


KEYWORDS: list[tuple[str, str, str, float]] = (
    _kw("active_product_rfq", "intent", 1.0,
        "request for quote", "request for quotation", "rfq",
        "request for proposal", "seeking quotes", "looking to source",
        "now sourcing", "we are sourcing", "sourcing request",
        "quotes from manufacturers", "quotes from suppliers")
    + _kw("explicit_supplier_search", "intent", 1.0,
          "looking for new suppliers", "seeking new suppliers",
          "looking for suppliers", "seeking suppliers",
          "new supplier opportunities", "looking for new products",
          "seeking new products", "looking for new brands",
          "seeking new brands", "submit your product", "submit your products",
          "submit your catalog", "submit your product catalog",
          "product catalog for consideration", "products for consideration",
          "accepting new vendors", "accepting new suppliers",
          "accepting new brands", "looking for manufacturers",
          "seeking manufacturers", "new vendor partners",
          "interested in becoming a supplier", "interested in becoming a vendor")
    + _kw("supplier_application_open", "intent", 1.0,
          "supplier application", "vendor application",
          "new vendor application", "vendor inquiry form", "supplier inquiry",
          "become a supplier", "become a vendor", "vendor submission",
          "supplier submission", "vendor onboarding", "new vendor setup",
          "vendor information form", "supplier registration",
          "vendor registration", "prospective vendors",
          "prospective suppliers", "product submission form",
          "new brand submission")
    + _kw("new_distribution_partnership", "expansion", 1.0,
          "distribution agreement", "distribution partnership",
          "exclusive distribution", "exclusive distributor for",
          "exclusive distribution rights", "agreement to distribute",
          "will now distribute", "now distributing", "now distributes",
          "named exclusive distributor", "appointed as distributor",
          "distribution deal", "master distributor for")
    + _kw("new_distribution_partnership", "expansion", 0.6,
          "partnered with", "new partnership with", "announces partnership")
    + _kw("new_brand_added", "expansion", 1.0,
          "added to our lineup", "added to its lineup", "adds brand",
          "joins our brand portfolio", "joins our lineup", "now carrying",
          "now carries", "now stocking", "newest brand", "new to our line",
          "added to our line card", "adds new brands",
          "expands brand portfolio", "expanded brand portfolio")
    + _kw("new_brand_added", "expansion", 0.7, "new brand", "new brands")
    + _kw("product_category_expansion", "expansion", 1.0,
          "expands its product", "expanded product offering",
          "expanding our product", "new product category",
          "new product categories", "expanded its catalog", "expands catalog",
          "expanded assortment", "expands assortment", "expansion into",
          "expanding into", "broadens its product")
    + _kw("new_product_line_launch", "expansion", 0.8,
          "new product line", "new product lines", "launches new",
          "introduces new", "new for 2026", "new for 2027", "product launch",
          "new products for")
    + _kw("catalog_or_linecard_expansion", "expansion", 0.8,
          "line card", "linecard", "new catalog", "2026 catalog",
          "2027 catalog", "catalog expansion", "new skus", "new part numbers",
          "thousands of new parts")
    + _kw("category_buyer_hiring", "hiring", 1.0,
          "category manager", "product buyer", "buyer", "senior buyer",
          "associate buyer", "category buyer", "merchandise manager",
          "merchandising manager", "assortment manager",
          "product line manager", "merchandise planner")
    + _kw("procurement_hiring", "hiring", 1.0,
          "purchasing manager", "purchasing agent", "purchasing director",
          "director of purchasing", "procurement manager",
          "procurement specialist", "sourcing manager", "sourcing specialist",
          "strategic sourcing", "vendor manager", "vendor relations",
          "purchasing coordinator", "inventory buyer", "purchasing analyst")
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
    + _kw("dealer_network_expansion", "capacity", 1.0,
          "expands dealer network", "expanding our dealer network",
          "expanded its dealer network", "growing dealer network",
          "new sales territory", "new territories", "expanded coverage",
          "new dealer accounts")
    + _kw("acquisition_or_distribution_expansion", "capacity", 1.0,
          "has acquired", "completed the acquisition", "acquisition of",
          "acquires", "merges with", "regional distribution capabilities",
          "adds distribution")
    + _kw("powersports_participation", "fit", 0.9,
          "powersports", "power sports", "atv", "utv", "side-by-side", "sxs",
          "motorcycle", "dirt bike", "motocross", "snowmobile", "v-twin")
    + _kw("b2b_dealer_distribution", "fit", 0.9,
          "become a dealer", "dealer application", "authorized dealers",
          "dealer network", "dealer portal", "dealer login",
          "wholesale distributor", "dealer pricing", "independent dealers",
          "serving dealers", "dealer support", "wholesale only",
          "dealers only", "trade only")
    + _kw("manufacturer_seeking_distribution", "negative", 1.0,
          "looking for distributors", "looking for a distributor",
          "seeking distributors", "seeking a distributor",
          "become a distributor", "distributor inquiries",
          "distributor opportunities", "distributors wanted",
          "seeking a us distributor", "looking for a us distributor",
          "distribute our products", "interested in distributing our products")
    + _kw("retail_only_operation", "negative", 0.9,
          "visit our showroom", "new and used", "pre-owned inventory",
          "schedule a test ride", "showroom hours", "browse our inventory",
          "used inventory", "value your trade")
    + _kw("service_repair_operation", "negative", 0.9,
          "schedule service", "service appointment", "repair shop",
          "our service department", "we repair", "service specials")
)

_REVERSE = ["looking for a distributor", "looking for distributors",
            "seeking a distributor", "seeking distributors",
            "become a distributor", "distributor inquiries",
            "seeking a us distributor", "looking for a us distributor",
            "distributors wanted"]
_DEALER_SIDE = ["become a dealer", "become an authorized dealer",
                "dealer application", "dealer account", "open a dealer account",
                "wholesale account application", "apply for a dealer"]
_CUSTOMER_SIDE = ["get a quote", "your quote", "your order", "our customers",
                  "for dealers", "dealer quote"]

SIGNAL_RULES: dict[str, dict] = {
    "active_product_rfq": {
        "exclude_page_types": ["dealer"],
        "suppress_phrases": _REVERSE + _DEALER_SIDE + _CUSTOMER_SIDE,
        "require_context_phrases": [
            "supplier", "suppliers", "manufacturer", "manufacturers", "vendor",
            "vendors", "factory", "factories", "source", "sourcing", "brands"],
    },
    "explicit_supplier_search": {
        "exclude_page_types": ["dealer"],
        "suppress_phrases": _REVERSE + _DEALER_SIDE,
    },
    "supplier_application_open": {
        "exclude_page_types": ["dealer"],
        "suppress_phrases": _REVERSE + _DEALER_SIDE,
    },
    "new_distribution_partnership": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": [
            "distribute", "distribution", "distributor", "distributing",
            "brand", "brands", "product line", "products", "dealers",
            "aftermarket", "accessories", "parts"],
    },
    "new_brand_added": {
        "exclude_page_types": ["dealer"],
        "suppress_phrases": ["looking for", "seeking", "submit", "interested in",
                             "our new brand identity"] + _REVERSE,
    },
    "product_category_expansion": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": POWERSPORTS_CONTEXT,
    },
    "new_product_line_launch": {
        "suppress_phrases": _REVERSE,
        "require_context_phrases": POWERSPORTS_CONTEXT,
    },
    "catalog_or_linecard_expansion": {
        "require_context_phrases": ["new", "added", "adds", "expanded",
                                    "expands", "expansion", "now includes",
                                    "additional"],
    },
    "category_buyer_hiring": {"require_page_types": ["careers", "job"]},
    "procurement_hiring": {"require_page_types": ["careers", "job"]},
    "acquisition_or_distribution_expansion": {
        "require_context_phrases": ["distributor", "distribution",
                                    "distributing", "aftermarket",
                                    "powersports", "parts", "accessories"],
    },
}

SIGNAL_PAGE_AFFINITY: dict[str, list[str]] = {
    "active_product_rfq": ["supplier", "news", "press_release", "website", "other"],
    "explicit_supplier_search": ["supplier", "news", "press_release", "website",
                                 "about", "other"],
    "supplier_application_open": ["supplier", "website", "other", "about"],
    "new_distribution_partnership": ["news", "press_release", "website", "brands",
                                     "about"],
    "new_brand_added": ["news", "press_release", "brands", "website"],
    "product_category_expansion": ["news", "press_release", "website", "brands"],
    "new_product_line_launch": ["news", "press_release", "website", "brands"],
    "catalog_or_linecard_expansion": ["brands", "website", "news", "press_release"],
    "category_buyer_hiring": ["careers", "job"],
    "procurement_hiring": ["careers", "job"],
    "distribution_center_expansion": ["news", "press_release", "about", "website"],
    "dealer_network_expansion": ["news", "press_release", "about", "website",
                                 "dealer"],
    "acquisition_or_distribution_expansion": ["news", "press_release", "about"],
}

INTEREST_TYPE_BY_SIGNAL = {
    "active_product_rfq": "EXPLICITLY_SEEKING",
    "explicit_supplier_search": "EXPLICITLY_SEEKING",
    "supplier_application_open": "EXPLICITLY_SEEKING",
    "new_distribution_partnership": "RECENTLY_ADDED",
    "new_brand_added": "RECENTLY_ADDED",
    "product_category_expansion": "RECENTLY_ADDED",
    "new_product_line_launch": "RECENTLY_ADDED",
    "catalog_or_linecard_expansion": "RECENTLY_ADDED",
}

COMPANY_TYPE_MARKERS: dict[str, list[str]] = {
    "wholesale_distributor": [
        "wholesale distributor", "wholesale distribution", "distributor of",
        "we distribute", "master distributor", "dealer network",
        "authorized dealers", "independent dealers", "dealer portal",
        "dealer login", "dealer pricing", "serving dealers", "dealer support",
        "line card", "linecard", "brands we carry", "brands we distribute",
        "distribution centers", "distribution center", "wholesale only",
        "dealers only", "trade only", "become a dealer", "dealer application",
        "b2b", "distribution partner"],
    "importer": [
        "we import", "importer of", "exclusive importer", "import and distribute",
        "importer and distributor", "direct importer"],
    "manufacturer": [
        "we manufacture", "our factory", "manufactured in", "designed and manufactured",
        "engineered and manufactured", "our manufacturing facility",
        "manufacturing facility", "made in usa", "made in the usa",
        "in-house manufacturing", "we design and build"],
    "brand_owner": [
        "find a dealer", "dealer locator", "where to buy", "become a distributor",
        "distributor inquiries", "our products are sold through",
        "distributors wanted", "looking for distributors"],
    "dealer_retailer": [
        "visit our showroom", "new and used", "pre-owned inventory",
        "schedule a test ride", "showroom hours", "browse our inventory",
        "used inventory", "value your trade", "financing available",
        "new inventory", "in-stock units", "our dealership"],
    "service_provider": [
        "schedule service", "service appointment", "repair shop",
        "our service department", "we repair", "service specials",
        "our technicians", "marketing agency", "digital agency"],
}

HYBRID_COMPANY_TYPES = {
    "hybrid_distributor_manufacturer": ["wholesale_distributor", "manufacturer"],
    "hybrid_distributor_dealer": ["wholesale_distributor", "dealer_retailer"],
}

INDUSTRY_KEYWORDS = {
    "powersports": [
        "powersports", "power sports", "atv", "utv", "side-by-side",
        "side by side", "sxs", "motorcycle", "motorcycles", "dirt bike",
        "motocross", "snowmobile", "v-twin", "off-road vehicle",
        "aftermarket parts", "dual sport", "adventure touring", "sled",
        "personal watercraft", "pwc", "jet ski", "harley-davidson",
        "dirtbike", "quad bike", "can-am", "polaris", "sea-doo", "ski-doo",
        "arctic cat"],
}

ROLES: list[tuple[str, int]] = [
    # purchasing / supplier onboarding owners first
    ("vp of purchasing", 1), ("vice president of purchasing", 1),
    ("vp purchasing", 1), ("vice president, purchasing", 1),
    ("director of purchasing", 1), ("purchasing director", 1),
    ("head of purchasing", 1), ("chief purchasing officer", 1),
    ("director of procurement", 1), ("vp of procurement", 1),
    ("head of procurement", 1),
    ("purchasing manager", 2), ("category manager", 2),
    ("senior category manager", 2), ("director of category management", 2),
    ("merchandising director", 2), ("director of merchandising", 2),
    ("vp of merchandising", 2),
    ("vp of product", 3), ("vice president of product", 3),
    ("director of product", 3), ("product line manager", 3),
    ("head of product", 3), ("product manager", 4),
    ("procurement manager", 4), ("sourcing manager", 4),
    ("director of sourcing", 4), ("vendor relations manager", 4),
    ("vendor manager", 4), ("senior buyer", 4), ("buyer", 5),
    ("purchasing agent", 5),
    # at smaller distributors the owner or president often buys
    ("owner", 6), ("co-owner", 6), ("president", 6), ("ceo", 6),
    ("chief executive officer", 6), ("founder", 7), ("co-founder", 7),
    ("coo", 8), ("chief operating officer", 8), ("general manager", 9),
    ("director of business development", 10),
    ("vp of business development", 10), ("business development manager", 11),
    # a longer pattern than 'president' so 'Vice President of Sales' is not
    # mistaken for the President
    ("vice president", 12),
]

CRAWL_PRIORITY_PATHS = [
    ["/", "website"], ["/about", "about"], ["/about-us", "about"],
    ["/brands", "brands"], ["/our-brands", "brands"], ["/line-card", "brands"],
    ["/vendors", "supplier"], ["/suppliers", "supplier"],
    ["/vendor-application", "supplier"], ["/become-a-vendor", "supplier"],
    ["/news", "news"], ["/press", "news"], ["/careers", "careers"],
    ["/dealers", "dealer"], ["/become-a-dealer", "dealer"],
    ["/contact", "other"],
]

EXTERNAL_QUERY_TEMPLATES = [
    ["press_release", '"{name}" "distribution agreement" OR "now distributing" '
                      'OR "exclusive distributor" OR "partnership"', "news"],
    ["press_release", '"{name}" "new brands" OR "new product lines" OR '
                      '"product line expansion" OR "adds"', "news"],
    ["news", '"{name}" powersports site:powersportsbusiness.com OR '
             'site:aimexpousa.com OR site:dealernews.com', "web"],
    ["supplier", '"{name}" "vendor application" OR "supplier application" OR '
                 '"new vendor" OR "submit your products"', "web"],
    ["job", '"{name}" "purchasing manager" OR "category manager" OR "buyer" '
            'OR "procurement"', "web"],
    ["press_release", '"{name}" "distribution center" OR warehouse OR '
                      'acquires OR acquisition', "news"],
]

DISCOVERY_BLOCKED_DOMAINS = [
    "powersportsbusiness.com", "aimexpousa.com", "mic.org", "dealernews.com",
    "motorcycle.com", "cycleworld.com", "atv.com", "utvdriver.com",
    "utvactionmag.com", "dirtrider.com", "motorcyclistonline.com",
    "thomasnet.com", "zoominfo.com", "dnb.com", "manta.com", "bbb.org",
    "yellowpages.com", "mapquest.com", "rocketreach.co", "apollo.io",
    "craigslist.org", "cycletrader.com", "atvtrader.com", "revzilla.com",
    "rockymountainatvmc.com", "partzilla.com", "denniskirk.com",
    "cyclegear.com", "motosport.com", "jdpower.com", "kbb.com",
    "nadaguides.com", "facebook.com", "linkedin.com", "youtube.com",
]

AI_SYSTEM_PROMPT = (
    "You are a B2B supply-chain analyst for manufacturers that want to sell "
    "aftermarket powersports products through US distributors. You assess "
    "whether a company is a suitable US powersports aftermarket wholesale "
    "distributor and what public evidence shows it is currently seeking, "
    "purchasing, onboarding or expanding aftermarket product categories and "
    "supplier relationships. Commercial direction matters: a distributor "
    "recruiting dealers is selling, not buying; a manufacturer seeking a "
    "distributor is the opposite direction and is not a buyer. Base every "
    "conclusion strictly on the supplied evidence. Never invent products, "
    "brands, purchasing requirements, employee counts or revenue. A general "
    "growth announcement is not a specific purchasing requirement.")

AI_TASK = (
    "Is this company a suitable US powersports aftermarket distributor, and "
    "what public evidence indicates that it is currently seeking, purchasing, "
    "onboarding or expanding aftermarket product categories and supplier "
    "relationships? Put the probability that it is actively expanding its "
    "supplier or product portfolio in service_probability. Put only product "
    "categories named in the evidence in likely_services. If no specific "
    "product requirement is identifiable, say exactly: Specific product "
    "demand not publicly disclosed.")

AI_EXTRA_FIELDS = {
    "distributor_qualification": '"qualified" | "possible" | "not_qualified" | "unknown"',
    "distributor_qualification_reason": "string citing evidence",
    "company_size_qualification": '"mid_market" | "small" | "micro" | "large" | "unknown" - never guess',
    "strongest_buying_signals": "[string]",
    "product_categories": "[string] - only categories named in the evidence",
    "products_mentioned": "[string] - only products named in the evidence",
    "supplier_onboarding_evidence": "[string]",
    "distribution_partnerships": "[string] - brands named in the evidence",
    "recent_expansion_activity": "[string]",
    "likely_decision_roles": "[string] - job titles, never personal contact data",
}

CONFIG: dict = {
    "score_weights": {"deterministic": 0.5, "ai": 0.3, "evidence": 0.2},
    "intent_thresholds": {"LOW": 0, "POSSIBLE": 31, "GOOD": 51,
                          "STRONG": 71, "HOT": 86},
    # ~ RFQ 35 + new brand 25 + buyer hiring 17 + fit 11 -> 100
    "normalization_ceiling": 90,
    "decision_maker_threshold": 40,
    "decision_maker_optional_threshold": 30,
    "ai_analysis_min_raw_score": 20,
    "required_signals": ["powersports_participation"],
    "signal_dimensions": SIGNAL_DIMENSIONS,
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
        "insurance agency", "trade publication"],
    "query_exclusion_terms": ["for sale", "rental", "rentals"],
    "qualification": {
        "eligible_company_types": ["wholesale_distributor", "importer",
                                   "hybrid_distributor_manufacturer",
                                   "hybrid_distributor_dealer"],
        "reject_company_types": ["dealer_retailer", "service_provider",
                                 "manufacturer", "brand_owner"],
        "unknown_company_type": "allow",
        "company_type_min_markers": 2,
        "allowed_countries": ["US"],
        "min_country_confidence": 0.6,
        # US only: a company must be positively located in the US
        "require_country_evidence": True,
        # ...except: a generic-TLD site with NO address and no foreign
        # evidence becomes a lead flagged "location unverified" (its
        # country_confidence stays below min_country_confidence).
        "allow_unverified_location_tlds": ["com", "net", "us", "org", "biz"],
        "required_industry": "powersports",
        # One powersports marker is enough: the lead list should include
        # weak-signal distributors, ranked LOW, rather than drop them.
        "min_industry_markers": 1,
        # Powersports parts are goods, so powersports evidence counts as
        # physical-product evidence (no cart or shipping page required).
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
                          "large": 0.7, "micro": 0.55},
        "company_type": {"wholesale_distributor": 1.0,
                         "hybrid_distributor_manufacturer": 0.95,
                         "importer": 0.9, "hybrid_distributor_dealer": 0.85,
                         "unknown": 0.75, "default": 0.5},
    },
    "product_taxonomy": PRODUCT_TAXONOMY,
    "adjacent_categories": ADJACENT_CATEGORIES,
    "vehicle_segments": VEHICLE_SEGMENTS,
    "vehicle_platforms": VEHICLE_PLATFORMS,
    "brand_patterns": BRAND_PATTERNS,
    "interest_type_by_signal": INTEREST_TYPE_BY_SIGNAL,
    "carried_page_types": ["brands", "website", "about", "other"],
    "no_product_demand_message": "Specific product demand not publicly disclosed.",
    "crawl_priority_paths": CRAWL_PRIORITY_PATHS,
    "crawl_max_pages": 16,
    "crawl_link_first_page_types": ["supplier", "brands", "news", "careers",
                                    "dealer", "about"],
    "external_query_templates": EXTERNAL_QUERY_TEMPLATES,
    "external_fetchers": ["ats"],
    "fetch_external_articles": 3,
    "discovery_blocked_domains": DISCOVERY_BLOCKED_DOMAINS,
    "ai_system_prompt": AI_SYSTEM_PROMPT,
    "ai_task": AI_TASK,
    "ai_extra_fields": AI_EXTRA_FIELDS,
    "ai_grounded_fields": ["likely_services", "product_categories",
                           "products_mentioned", "distribution_partnerships"],
    "ai_probability_field": "buying_intent_probability",
}


# =====================================================================
# DISCOVERY QUERY LIBRARY - ~630 queries. Tier = priority; discovery runs
#   never-run queries first, so each run only pays for new searches.
#   1  direct purchasing intent and supplier onboarding
#   2  recent product-category and brand expansion
#   3  target distributor discovery and qualification
#   4  hiring, warehouse expansion, acquisitions
# No parentheses: the SQL row parser forbids them.
# =====================================================================
@dataclass(frozen=True)
class Query:
    text: str
    tier: int
    country: str | None = "US"
    group: str = ""


_DISTRIBUTOR_TYPES = [
    "powersports distributor", "powersports wholesale distributor",
    "motorcycle parts distributor", "ATV UTV aftermarket distributor",
    "aftermarket parts distributor",
]
_SEGMENT_DISTRIBUTORS = [
    "powersports aftermarket parts distributors USA",
    "powersports wholesale distributors",
    "motorcycle parts wholesale distributors",
    "ATV UTV aftermarket distributors",
    "side by side accessories wholesale distributors",
    "motorcycle apparel wholesale distributors",
    "motocross parts distributors",
    "snowmobile parts wholesalers",
    "regional powersports parts distributors",
    "powersports dealer wholesale suppliers",
    "aftermarket accessories distribution companies",
    "independent motorcycle dealer distributors",
    "V-twin parts wholesale distributor",
    "off-road parts wholesale distributor",
    "UTV accessories wholesale distributor dealers only",
    "powersports tire wholesale distributor",
    "motorcycle riding gear distributor dealers",
    "powersports parts distributor dealer network",
]
_PRODUCT_LINES = [
    "UTV accessories", "motorcycle crash protection", "ATV tires",
    "UTV tires", "powersports batteries", "UTV windshields",
    "motorcycle apparel", "off-road performance parts", "motorcycle luggage",
    "UTV lighting", "motorcycle helmets", "powersports lubricants",
    "UTV cab enclosures", "winches",
]
_STATES = ["Texas", "California", "Minnesota", "Wisconsin", "Pennsylvania",
           "Georgia", "Ohio", "Florida", "Michigan", "Utah"]

# ---- expansion library -------------------------------------------------
# Measured locally (first ~330 companies): supplier-sourcing phrasing turned
# ~25% of discovered companies into leads vs ~9% overall, so the expansion
# leans on sourcing phrasing x vehicle segment x product line, then brand
# carried, then every US state.
_SEGMENTS = [
    "powersports", "motorcycle", "ATV", "UTV", "side by side", "snowmobile",
    "dirt bike", "motocross", "V-twin", "off-road", "personal watercraft",
    "metric cruiser", "adventure motorcycle", "golf cart and UTV",
]
_SOURCING_PHRASES = [
    "parts distributor vendor application",
    "parts distributor new vendor setup",
    "wholesale distributor seeking new product lines",
    "distributor become a supplier",
    "aftermarket distributor new supplier inquiry",
    "parts wholesaler manufacturers wanted",
    "distributor submit a new product",
    "wholesale distributor dealers only",
    "parts distributor brands we carry",
    "accessories wholesale distributor",
]
_MORE_PRODUCT_LINES = [
    "UTV roofs", "UTV doors", "UTV bumpers", "UTV audio", "UTV mirrors",
    "UTV seats", "ATV plows", "snowmobile parts", "snowmobile apparel",
    "motorcycle exhaust", "motorcycle tires", "motorcycle batteries",
    "motorcycle brakes", "motorcycle lighting", "motorcycle seats",
    "motocross graphics", "dirt bike plastics", "off-road gear",
    "powersports chemicals", "powersports drive belts", "powersports clutch kits",
    "lift kits UTV", "UTV wheels", "ATV accessories", "powersports trailers",
    "motorcycle tools", "powersports covers", "tie-downs and ramps",
]
_LINE_PHRASES = [
    "wholesale distributor for dealers",
    "distributor vendor application",
    "wholesale supplier to powersports dealers",
]
_BRANDS_CARRIED = [
    "Kolpin", "Warn winch", "SuperATV", "EBC brakes", "K&N", "Yuasa",
    "Maxima oil", "Kenda tires", "ITP tires", "Dunlop motorcycle tires",
    "Shinko tires", "Kemimoto", "Rugged Radios", "Rigid lighting",
    "Baja Designs", "Seizmik", "Moose Utility", "Pro Armor", "Bell helmets",
    "Fly Racing", "Alpinestars", "Klim", "Icon motorcycle gear",
    "Kuryakyn", "Vance & Hines", "Cobra exhaust", "Antigravity batteries",
    "Motobatt", "Hiflofiltro", "DID chain", "RK chain", "EBC clutch",
    "Gates belts", "Dayco belts", "Polaris accessories aftermarket",
    "Can-Am accessories aftermarket", "Tusk", "Quadboss", "Dragonfire Racing",
    "Interior Color", "Bad Dog", "Cycle Country", "Denali lighting",
]
_ALL_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Idaho", "Illinois",
    "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
    "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri",
    "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
]
_GEO_TYPES = [
    "powersports parts distributor", "motorcycle parts wholesale distributor",
    "ATV UTV parts wholesale distributor", "powersports accessories wholesaler",
]


def build_library() -> list[Query]:
    out: list[Query] = []

    def add(text: str, tier: int, group: str) -> None:
        out.append(Query(text=text, tier=tier, group=group))

    # ---- tier 1: purchasing intent / supplier onboarding ----
    for text in [
        "powersports distributor seeking new suppliers",
        "powersports distributor supplier application",
        "aftermarket parts distributor new brand submissions",
        "powersports wholesaler looking for manufacturers",
        "distributor sourcing new ATV accessories",
        "powersports distributor vendor application",
        "motorcycle parts distributor become a vendor",
        "powersports distributor submit your products",
        "UTV accessories distributor new vendor application",
        "powersports distributor accepting new brands",
        "motorcycle aftermarket distributor product submission",
        "powersports distributor RFQ aftermarket products",
    ]:
        add(text, 1, "supplier_sourcing")
    for dist in _DISTRIBUTOR_TYPES:
        add(f'"{dist}" "vendor application"', 1, "supplier_sourcing")
        add(f'"{dist}" "new suppliers"', 1, "supplier_sourcing")

    # ---- tier 2: recent category / brand expansion ----
    for text in [
        "motorcycle parts distributor new product lines",
        "distributor adding new UTV product categories",
        "powersports distributor distribution agreement",
        "motorcycle aftermarket distributor expanding product portfolio",
        "UTV accessories distributor partnership announcement",
        "powersports distributor adds new brands",
        "powersports distributor exclusive distribution rights",
        "powersports distributor new brand partnership 2026",
    ]:
        add(text, 2, "expansion")
    for line in _PRODUCT_LINES:
        add(f"{line} distribution agreement powersports distributor", 2,
            "product_expansion")
        add(f"distributor adds {line} brand", 2, "product_expansion")

    # ---- tier 3: target distributor discovery ----
    for text in _SEGMENT_DISTRIBUTORS:
        add(text, 3, "distributor_discovery")
    for state in _STATES:
        add(f"powersports parts distributor {state}", 3, "distributor_geo")
    add("powersports distributor line card brands we carry", 3,
        "distributor_discovery")
    add("motorcycle parts distributor dealer portal login", 3,
        "distributor_discovery")

    # ---- tier 4: hiring / warehouse / acquisitions ----
    for text in [
        "powersports product category manager hiring",
        "powersports distributor purchasing manager jobs",
        "aftermarket distributor procurement hiring",
        "powersports distributor buyer job",
        "motorcycle parts distributor category manager job",
        "powersports distributor new warehouse expansion",
        "powersports distributor new distribution center",
        "powersports distributor acquires distributor",
        "motorcycle parts distributor acquisition",
        "powersports distributor expands dealer network",
    ]:
        add(text, 4, "supporting_signals")

    # ---- expansion: sourcing phrasing per vehicle segment ----
    for seg in _SEGMENTS:
        for phrase in _SOURCING_PHRASES:
            add(f"{seg} {phrase}", 1, "supplier_sourcing")
    # ---- expansion: product line wholesale distributors ----
    for line in _PRODUCT_LINES + _MORE_PRODUCT_LINES:
        for phrase in _LINE_PHRASES:
            add(f"{line} {phrase}", 2, "product_distributors")
    # ---- expansion: distributors carrying established aftermarket brands ----
    for brand in _BRANDS_CARRIED:
        add(f"{brand} authorized distributor powersports dealers", 2,
            "brand_distributors")
        add(f"{brand} wholesale distributor USA", 2, "brand_distributors")
    # ---- expansion: every US state ----
    for state in _ALL_STATES:
        for kind in _GEO_TYPES:
            add(f"{kind} {state}", 3, "distributor_geo")

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

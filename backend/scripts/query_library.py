"""Combinatorial discovery-query library for Serper.

Generates BUSINESS MODEL x CATEGORY x PATTERN x PLATFORM x GROWTH x GEOGRAPHY
combinations, deduplicated and ranked into four tiers.

Why generated rather than a static list: the vocabulary changes (new
categories, new platforms, new geographies), and a 3,000-line SQL literal is
unreviewable. Regenerate with:

    python -m scripts.build_query_library
"""
from __future__ import annotations

from dataclasses import dataclass

# =====================================================================
# VOCABULARY
# =====================================================================

BUSINESS_MODELS = [
    "ecommerce brand", "ecommerce company", "ecommerce business",
    "DTC brand", "DTC company", "direct-to-consumer brand",
    "direct to consumer company", "online retailer", "online retail brand",
    "online store", "online shop", "consumer brand",
    "consumer products company", "consumer goods company", "CPG brand",
    "product brand", "product company", "retail brand",
    "online product company", "subscription brand", "subscription box company",
]

# Short forms used as query prefixes: "DTC skincare brands"
MODEL_PREFIXES = [
    "DTC", "ecommerce", "direct to consumer", "online", "consumer",
    "subscription",
]

PLATFORMS = ["Shopify", "WooCommerce", "BigCommerce", "Magento"]

PLATFORM_FOOTPRINTS = [
    '"Powered by Shopify"',
    '"powered by WooCommerce"',
    '"powered by BigCommerce"',
]

# Used as discovery signals, never as requirements.
FULFILLMENT_SIGNALS = [
    "fulfillment", "order fulfillment", "ecommerce fulfillment",
    "warehouse", "warehousing", "inventory", "shipping", "order shipping",
    "distribution", "distribution center", "pick and pack", "pick pack ship",
    "inventory management", "order processing", "direct shipping",
    "nationwide shipping", "international shipping", "DTC fulfillment",
    "retail fulfillment", "omnichannel",
]

COMPANY_TERMS = [
    "manufacturer", "retailer", "online retailer", "ecommerce company",
    "consumer goods company", "consumer products company", "product company",
    "product manufacturer", "retail company", "online shop", "online store",
    "merchandise company",
]

GROWTH_SIGNALS = [
    "growing", "fastest growing", "emerging", "funded", "high-growth",
    "rapidly growing", "new", "up and coming",
]

DIRECTORY_PATTERNS = [
    "top {cat} DTC brands",
    "best {cat} DTC brands",
    "top {cat} ecommerce brands",
    "best Shopify {cat} brands",
    "{cat} ecommerce brands directory",
    "{cat} consumer brands directory",
    "{cat} brands directory",
    "list of {cat} brands",
    "fastest growing {cat} brands",
    "emerging {cat} brands",
    "best {cat} online stores",
    "successful {cat} Shopify stores",
]

STANDALONE_DIRECTORY = [
    "top DTC brands", "best DTC brands", "fastest growing DTC brands",
    "ecommerce brands directory", "consumer brands directory",
    "Shopify brands directory", "Shopify stores directory",
    "best Shopify stores", "successful Shopify stores",
    "emerging ecommerce brands", "growing ecommerce brands",
    "consumer product startups", "DTC startups", "ecommerce startups",
    "online retailers directory", "product brands directory",
    "funded ecommerce startups", "funded DTC brands",
    "fastest growing ecommerce companies", "high-growth consumer brands",
    "rapidly growing Shopify brands", "ecommerce companies hiring",
    "DTC companies hiring", "new consumer brands launched",
    "independent brands directory", "small batch brands directory",
]

GEOGRAPHIES = [
    ("USA", "US"), ("United States", "US"), ("Canada", "CA"),
    ("UK", "GB"), ("United Kingdom", "GB"), ("Australia", "AU"),
    ("Germany", "DE"), ("France", "FR"), ("Netherlands", "NL"),
    ("Spain", "ES"), ("Italy", "IT"), ("UAE", "AE"),
    ("Singapore", "SG"), ("India", "IN"),
]

# =====================================================================
# CATEGORIES
# =====================================================================
CATEGORIES: dict[str, list[str]] = {
    "Fashion": [
        "apparel", "clothing", "fashion", "streetwear", "activewear",
        "sportswear", "footwear", "shoes", "sneakers", "bags", "handbags",
        "accessories", "jewelry", "watches", "leather goods",
    ],
    "Beauty": [
        "beauty", "cosmetics", "skincare", "haircare", "makeup",
        "personal care", "grooming", "fragrance", "perfume", "body care",
        "hair products",
    ],
    "Health & Wellness": [
        "supplements", "vitamins", "nutrition", "wellness", "health products",
        "protein", "sports nutrition", "fitness products", "health food",
        "nutritional products",
    ],
    "Food & Beverage": [
        "food", "snack", "beverage", "coffee", "tea", "chocolate", "candy",
        "packaged food", "organic food", "healthy food", "meal kits",
        "specialty food",
    ],
    "Pet": [
        "pet products", "pet supplies", "pet food", "dog products",
        "cat products", "pet accessories", "animal products",
    ],
    "Home": [
        "home decor", "home goods", "furniture", "kitchen products",
        "cookware", "bedding", "mattresses", "home organization", "lighting",
        "garden products", "household products",
    ],
    "Baby & Kids": [
        "baby products", "baby clothing", "baby accessories", "toys",
        "children's products", "kids products", "educational toys",
        "baby care",
    ],
    "Sports & Outdoor": [
        "sports equipment", "fitness equipment", "gym equipment",
        "running products", "cycling products", "outdoor gear", "camping gear",
        "hiking gear", "fishing products", "sporting goods",
    ],
    "Electronics": [
        "consumer electronics", "electronics accessories", "phone accessories",
        "computer accessories", "gaming accessories", "smart home products",
        "audio products", "wearable technology",
    ],
    "Other Physical Products": [
        "stationery", "office products", "craft products", "hobby products",
        "musical instruments", "automotive accessories", "car accessories",
        "tools", "hardware", "gifts", "lifestyle products", "luxury goods",
        "collectibles",
    ],
}

ALL_CATEGORIES = [c for terms in CATEGORIES.values() for c in terms]

# Categories worth the extra geographic fan-out (highest DTC density).
GEO_PRIORITY_CATEGORIES = [
    "apparel", "clothing", "footwear", "jewelry", "accessories",
    "skincare", "cosmetics", "beauty", "haircare",
    "supplements", "vitamins", "nutrition",
    "coffee", "snack", "food", "beverage",
    "pet products", "pet food",
    "home decor", "furniture", "kitchen products",
    "baby products", "toys",
    "fitness equipment", "outdoor gear",
    "consumer electronics", "phone accessories",
]

# =====================================================================
# EXCLUSIONS
# =====================================================================
# Appended to queries as Google negative operators. Kept short: every
# negative term costs recall, so only the ones that actually pollute
# results are included.
QUERY_EXCLUSION_TERMS = [
    "3PL", "logistics", "freight", "courier", "fulfilment services",
    "fulfillment services", "jobs", "salary", "hiring agency",
]

# Domains that are aggregators or marketplaces: useful as discovery sources
# to read, never as company records themselves. The discovery engine already
# blocks these via utils/urls.BLOCKED_DOMAINS.
EXCLUDED_RESULT_DOMAINS = [
    "amazon.com", "ebay.com", "etsy.com", "walmart.com", "alibaba.com",
    "aliexpress.com", "wish.com", "temu.com", "shein.com",
]

# Business types that must be rejected at classification even if they slip
# through the search filters.
EXCLUDED_BUSINESS_TYPES = [
    "3pl provider", "third party logistics provider", "logistics company",
    "freight forwarder", "freight broker", "courier service",
    "shipping company", "transportation company", "warehousing company",
    "fulfillment provider", "fulfillment agency",
    "marketing agency", "seo agency", "web development agency",
    "digital agency", "software company", "saas platform",
    "consulting firm", "restaurant", "hotel", "real estate agency",
    "financial services", "law firm", "healthcare provider",
    "recruitment agency", "staffing agency",
]


@dataclass(frozen=True)
class Query:
    text: str
    tier: int
    country: str | None = None
    group: str = "General"

    def key(self) -> tuple[str, str | None]:
        return (self.text.lower().strip(), self.country)


# =====================================================================
# GENERATION
# =====================================================================
def _tier1() -> list[Query]:
    """Platform + category, and DTC/ecommerce + category.

    Highest yield per Serper credit: a platform footprint plus a product
    category almost always returns real brand domains rather than listicles
    or service businesses.
    """
    out: list[Query] = []
    for group, cats in CATEGORIES.items():
        for cat in cats:
            out += [
                Query(f"Shopify {cat} brands", 1, None, group),
                Query(f"Shopify {cat} stores", 1, None, group),
                Query(f"DTC {cat} brands", 1, None, group),
                Query(f"{cat} ecommerce brands", 1, None, group),
                Query(f"{cat} direct to consumer brands", 1, None, group),
                Query(f"{cat} online stores", 1, None, group),
            ]
    return out


def _tier2() -> list[Query]:
    """Business model x category across the remaining patterns."""
    out: list[Query] = []
    patterns = [
        "{model} {cat}",
        "{model} {cat} brands",
        "{model} {cat} companies",
        "{model} {cat} startups",
    ]
    for group, cats in CATEGORIES.items():
        for cat in cats:
            for model in MODEL_PREFIXES:
                for pattern in patterns:
                    out.append(Query(
                        pattern.format(model=model, cat=cat), 2, None, group))
            out += [
                Query(f"{cat} consumer brands", 2, None, group),
                Query(f"{cat} product companies", 2, None, group),
                Query(f"{cat} online retailers", 2, None, group),
                Query(f"{cat} ecommerce companies", 2, None, group),
            ]
    return out


def _tier3() -> list[Query]:
    """Growth signals, directories, alternative company terminology, and
    the other ecommerce platforms."""
    out: list[Query] = [Query(q, 3, None, "Directory / List")
                        for q in STANDALONE_DIRECTORY]

    for group, cats in CATEGORIES.items():
        for cat in cats:
            for pattern in DIRECTORY_PATTERNS:
                out.append(Query(pattern.format(cat=cat), 3, None, group))
            for growth in ("growing", "fastest growing", "emerging", "funded"):
                out.append(Query(f"{growth} {cat} DTC brands", 3, None, group))
            for term in ("consumer products company", "online retailer",
                         "product manufacturer", "ecommerce company"):
                out.append(Query(f"{term} {cat}", 3, None, group))

    for platform in PLATFORMS[1:]:                    # Woo, BigCommerce, Magento
        for cat in GEO_PRIORITY_CATEGORIES:
            out.append(Query(f"{platform} {cat} brands", 3, None,
                             "Platform footprint"))
    for footprint in PLATFORM_FOOTPRINTS:
        for cat in GEO_PRIORITY_CATEGORIES:
            out.append(Query(f"{footprint} {cat}", 3, None,
                             "Platform footprint"))
    return out


def _tier4() -> list[Query]:
    """Geographic fan-out and broad category discovery."""
    out: list[Query] = []
    for cat in GEO_PRIORITY_CATEGORIES:
        for name, code in GEOGRAPHIES:
            out.append(Query(f"{cat} brands {name}", 4, code, "Geographic"))
            out.append(Query(f"DTC {cat} brands {name}", 4, code, "Geographic"))

    for name, code in GEOGRAPHIES:
        out += [
            Query(f"Shopify brands {name}", 4, code, "Geographic"),
            Query(f"ecommerce brands {name}", 4, code, "Geographic"),
            Query(f"DTC brands {name}", 4, code, "Geographic"),
            Query(f"consumer brands {name}", 4, code, "Geographic"),
            Query(f"online retailers {name}", 4, code, "Geographic"),
        ]

    for cat in ALL_CATEGORIES:
        out.append(Query(f"{cat} brands", 4, None, "Broad"))
        out.append(Query(f"{cat} companies", 4, None, "Broad"))

    for model in BUSINESS_MODELS:
        out.append(Query(model, 4, None, "Business Model"))
    for signal in FULFILLMENT_SIGNALS:
        out.append(Query(f"ecommerce brand {signal}", 4, None,
                         "Fulfillment signal"))
    for term in COMPANY_TERMS:
        out.append(Query(f"{term} consumer products", 4, None,
                         "Company terminology"))
    return out


def build_library() -> list[Query]:
    """All tiers, deduplicated keeping the best (lowest) tier."""
    seen: dict[tuple[str, str | None], Query] = {}
    for query in _tier1() + _tier2() + _tier3() + _tier4():
        text = " ".join(query.text.split())
        if not text or len(text) > 180:
            continue
        normalized = Query(text, query.tier, query.country, query.group)
        existing = seen.get(normalized.key())
        if existing is None or normalized.tier < existing.tier:
            seen[normalized.key()] = normalized
    return sorted(seen.values(), key=lambda q: (q.tier, q.group, q.text))


def stats(queries: list[Query]) -> dict:
    from collections import Counter
    return {
        "total": len(queries),
        "by_tier": dict(sorted(Counter(q.tier for q in queries).items())),
        "by_group": dict(Counter(q.group for q in queries).most_common()),
        "with_country": sum(1 for q in queries if q.country),
    }


if __name__ == "__main__":
    import json
    lib = build_library()
    print(json.dumps(stats(lib), indent=2))
    print("\nSamples:")
    for tier in (1, 2, 3, 4):
        sample = [q for q in lib if q.tier == tier][:4]
        for q in sample:
            print(f"  T{q.tier} [{q.country or '--'}] {q.text}")

"""Generic company classification (§32, Phase 3).

Deliberately service-agnostic: it answers "what IS this company?", never
"is this a good lead?". The 3PL judgement happens later, in the signal and
scoring engines, driven by service config.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.engine.extractor import ExtractedPage
from app.models import Company
from app.utils.text import contains_phrase

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Ecommerce platform fingerprints
# ---------------------------------------------------------------------
PLATFORM_FINGERPRINTS: dict[str, list[str]] = {
    "shopify": ["cdn.shopify.com", "shopify.com/s/files", "myshopify.com",
                "shopify-features", "/cart.js", "window.Shopify",
                "shopify-section", "x-shopid"],
    "woocommerce": ["woocommerce", "wp-content/plugins/woocommerce",
                    "wc-ajax", "wc_add_to_cart_params"],
    "bigcommerce": ["cdn11.bigcommerce.com", "bigcommerce.com/s-",
                    "stencil-utils"],
    "magento": ["mage/cookies", "magento", "static/version", "/checkout/cart/"],
    "squarespace": ["squarespace.com", "static1.squarespace.com",
                    "squarespace-cdn"],
    "wix": ["wix.com", "wixstatic.com", "wixsite.com", "_wixCssStates"],
    "prestashop": ["prestashop", "/modules/ps_"],
    "salesforce_commerce": ["demandware.static", "demandware.edgesuite"],
    "shopware": ["shopware", "/widgets/checkout/"],
    "webflow": ["webflow.com", "assets.website-files.com", "wf-"],
    "custom": [],
}

ECOMMERCE_MARKERS = [
    "add to cart", "add to bag", "add to basket", "shopping cart",
    "proceed to checkout", "view cart", "my cart", "shop now",
    "buy now", "sold out", "in stock", "out of stock",
]

PHYSICAL_PRODUCT_MARKERS = [
    "free shipping", "shipping policy", "delivery times", "dispatch",
    "tracking number", "returns policy", "return policy", "sku",
    "in stock", "out of stock", "size guide", "dimensions",
    "ships within", "estimated delivery", "warehouse", "restock",
]

# Signals that the company sells software/services, not goods.
NON_PHYSICAL_MARKERS = [
    "saas", "software as a service", "book a demo", "start free trial",
    "api documentation", "pricing per seat", "per user per month",
    "consulting services", "our agency", "case studies", "download the app",
]

# ---------------------------------------------------------------------
# Country detection
# ---------------------------------------------------------------------
TLD_COUNTRY = {
    "uk": "GB", "co.uk": "GB", "de": "DE", "fr": "FR", "es": "ES", "it": "IT",
    "nl": "NL", "be": "BE", "se": "SE", "no": "NO", "dk": "DK", "fi": "FI",
    "pl": "PL", "ie": "IE", "pt": "PT", "at": "AT", "ch": "CH", "cz": "CZ",
    "ca": "CA", "au": "AU", "nz": "NZ", "in": "IN", "sg": "SG", "jp": "JP",
    "us": "US", "mx": "MX", "br": "BR", "za": "ZA", "ae": "AE", "hk": "HK",
}

CURRENCY_COUNTRY = {"GBP": "GB", "USD": "US", "CAD": "CA", "AUD": "AU",
                    "INR": "IN", "JPY": "JP"}

COUNTRY_PHRASES: list[tuple[str, str]] = [
    (r"\bunited kingdom\b|\bengland\b|\bscotland\b|\bwales\b|\blondon\b", "GB"),
    (r"\bunited states\b|\bu\.s\.a\.?\b|\bnew york\b|\blos angeles\b|\bcalifornia\b", "US"),
    (r"\bcanada\b|\btoronto\b|\bvancouver\b", "CA"),
    (r"\baustralia\b|\bsydney\b|\bmelbourne\b", "AU"),
    (r"\bgermany\b|\bdeutschland\b|\bberlin\b|\bmunich\b", "DE"),
    (r"\bfrance\b|\bparis\b", "FR"),
    (r"\bnetherlands\b|\bamsterdam\b", "NL"),
    (r"\bireland\b|\bdublin\b", "IE"),
    (r"\bindia\b|\bmumbai\b|\bbengaluru\b|\bbangalore\b|\bdelhi\b", "IN"),
    (r"\bsingapore\b", "SG"),
    (r"\bnew zealand\b|\bauckland\b", "NZ"),
    (r"\bspain\b|\bmadrid\b|\bbarcelona\b", "ES"),
    (r"\bitaly\b|\bmilan\b|\brome\b", "IT"),
    (r"\bsweden\b|\bstockholm\b", "SE"),
]

POSTCODE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("GB", re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b")),
    ("US", re.compile(r"\b\d{5}(?:-\d{4})?\b(?=[^\d]|$)")),
    ("CA", re.compile(r"\b[A-Z]\d[A-Z]\s?\d[A-Z]\d\b")),
]

INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "apparel": ["clothing", "apparel", "fashion", "t-shirt", "hoodie", "dress",
                "menswear", "womenswear", "activewear", "swimwear"],
    "beauty": ["skincare", "cosmetics", "beauty", "serum", "moisturiser",
               "moisturizer", "fragrance", "haircare"],
    "food_beverage": ["coffee", "tea", "snack", "chocolate", "brewery", "wine",
                      "spirits", "granola", "supplement", "protein"],
    "home_furniture": ["furniture", "homeware", "bedding", "mattress", "decor",
                       "kitchenware", "candle"],
    "electronics": ["headphones", "speaker", "charger", "gadget", "smart home",
                    "wearable", "drone"],
    "health_wellness": ["vitamin", "supplement", "wellness", "nutrition",
                        "fitness equipment"],
    "pet": ["pet", "dog", "cat", "puppy", "pet food"],
    "toys_baby": ["toys", "baby", "stroller", "nursery", "kids"],
    "sports_outdoor": ["cycling", "running", "outdoor", "camping", "hiking",
                       "surf", "yoga"],
    "jewellery": ["jewellery", "jewelry", "necklace", "bracelet", "earrings",
                  "watches"],
}


@dataclass
class Classification:
    is_ecommerce: bool | None = None
    is_physical_product: bool | None = None
    platform: str | None = None
    country: str | None = None
    country_confidence: float = 0.0
    industry: str | None = None
    name: str | None = None
    description: str | None = None
    currencies: list[str] = field(default_factory=list)
    relevant: bool = True
    rejection_reason: str | None = None
    evidence: dict[str, list[str]] = field(default_factory=dict)


def _detect_platform(pages: list[ExtractedPage]) -> tuple[str | None, list[str]]:
    haystack = " ".join(
        (p.html or "") + " " + " ".join(p.scripts) + " " + " ".join(p.generators)
        for p in pages
    ).lower()
    if not haystack.strip():
        return None, []
    scores: dict[str, int] = {}
    hits: dict[str, list[str]] = {}
    for platform, markers in PLATFORM_FINGERPRINTS.items():
        for marker in markers:
            if marker.lower() in haystack:
                scores[platform] = scores.get(platform, 0) + 1
                hits.setdefault(platform, []).append(marker)
    if not scores:
        return None, []
    best = max(scores, key=lambda k: scores[k])
    return best, hits.get(best, [])


def _detect_ecommerce(pages: list[ExtractedPage],
                      platform: str | None) -> tuple[bool, list[str]]:
    evidence: list[str] = []
    if platform in {"shopify", "woocommerce", "bigcommerce", "magento",
                    "prestashop", "salesforce_commerce", "shopware"}:
        evidence.append(f"platform:{platform}")

    text = " ".join(p.searchable for p in pages)
    for marker in ECOMMERCE_MARKERS:
        if contains_phrase(text, marker):
            evidence.append(marker)

    for page in pages:
        for block in page.json_ld:
            types = block.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(t in ("Product", "Offer", "AggregateOffer") for t in types if t):
                evidence.append("schema.org:Product")
                break

    if any("/cart" in l or "/checkout" in l or "/products/" in l
           for p in pages for l in p.internal_links):
        evidence.append("cart/checkout/product URLs")

    return len(evidence) >= 2, evidence[:8]


def _detect_physical(pages: list[ExtractedPage],
                     is_ecommerce: bool) -> tuple[bool, list[str]]:
    text = " ".join(p.searchable for p in pages)
    positive = [m for m in PHYSICAL_PRODUCT_MARKERS if contains_phrase(text, m)]
    negative = [m for m in NON_PHYSICAL_MARKERS if contains_phrase(text, m)]

    has_shipping_page = any(p.page_type == "shipping" for p in pages)
    has_returns_page = any(p.page_type == "returns" for p in pages)
    if has_shipping_page:
        positive.append("shipping policy page")
    if has_returns_page:
        positive.append("returns policy page")

    # 1 physical signal is enough — many brands sell through retailers
    # (wholesale, FMCG, food & beverage, cosmetics) without a direct store
    # but still ship physical goods and need 3PL.
    physical = len(positive) >= 1 and len(positive) > len(negative)
    if is_ecommerce and (has_shipping_page or has_returns_page):
        physical = True
    return physical, positive[:8]


def _detect_country(domain: str, pages: list[ExtractedPage]
                    ) -> tuple[str | None, float, list[str]]:
    """Weighted vote across TLD, address text, phrases, currency."""
    votes: dict[str, float] = {}
    evidence: list[str] = []

    for suffix, code in TLD_COUNTRY.items():
        if domain.endswith("." + suffix):
            votes[code] = votes.get(code, 0) + 3.0
            evidence.append(f"TLD .{suffix}")
            break

    text = " ".join(p.searchable for p in pages)[:60_000]
    for pattern, code in COUNTRY_PHRASES:
        if re.search(pattern, text, re.I):
            votes[code] = votes.get(code, 0) + 1.5
            evidence.append(f"text mentions {code}")

    contact_text = " ".join(
        p.text for p in pages if p.page_type in ("other", "about"))[:20_000]
    for code, pattern in POSTCODE_PATTERNS:
        if pattern.search(contact_text):
            votes[code] = votes.get(code, 0) + 1.0
            evidence.append(f"{code} postcode format on contact/about page")

    currencies = sorted({c for p in pages for c in p.currencies})
    for currency in currencies:
        code = CURRENCY_COUNTRY.get(currency)
        if code:
            votes[code] = votes.get(code, 0) + 0.75
            evidence.append(f"prices in {currency}")

    if not votes:
        return None, 0.0, evidence

    best = max(votes, key=lambda k: votes[k])
    total = sum(votes.values())
    return best, round(votes[best] / total, 3), evidence[:6]


def _detect_industry(pages: list[ExtractedPage]) -> str | None:
    text = " ".join(p.searchable for p in pages)[:60_000]
    scores = {
        industry: sum(1 for kw in keywords if contains_phrase(text, kw))
        for industry, keywords in INDUSTRY_KEYWORDS.items()
    }
    best = max(scores, key=lambda k: scores[k]) if scores else None
    return best if best and scores[best] >= 2 else None


def _company_name(pages: list[ExtractedPage], domain: str) -> str | None:
    for page in pages:
        if page.page_type != "website":
            continue
        for block in page.json_ld:
            if block.get("@type") in ("Organization", "Corporation") and block.get("name"):
                return str(block["name"])[:200]
        if page.title:
            # "Brand Name | Tagline" -> "Brand Name"
            candidate = re.split(r"\s[|\-–—]\s", page.title)[0].strip()
            if 2 <= len(candidate) <= 80:
                return candidate
    return domain.split(".")[0].replace("-", " ").title()


def classify(company: Company, pages: list[ExtractedPage]) -> Classification:
    result = Classification()
    if not pages:
        result.relevant = False
        result.rejection_reason = "no pages crawled"
        return result

    platform, platform_ev = _detect_platform(pages)
    is_ecom, ecom_ev = _detect_ecommerce(pages, platform)
    is_physical, physical_ev = _detect_physical(pages, is_ecom)
    country, country_conf, country_ev = _detect_country(company.domain, pages)

    result.platform = platform
    result.is_ecommerce = is_ecom
    result.is_physical_product = is_physical
    result.country = country
    result.country_confidence = country_conf
    result.industry = _detect_industry(pages)
    result.name = _company_name(pages, company.domain)
    result.currencies = sorted({c for p in pages for c in p.currencies})

    home = next((p for p in pages if p.page_type == "website"), pages[0])
    result.description = (home.meta_description or home.text[:400]) or None

    result.evidence = {
        "platform": platform_ev, "ecommerce": ecom_ev,
        "physical_products": physical_ev, "country": country_ev,
    }

    # §32: reject early, and always record why so we never reprocess blindly.
    # Any brand that ships physical goods qualifies — ecommerce stores, brands
    # that sell through retailers, wholesale, FMCG, food & beverage, cosmetics,
    # sporting goods, etc. They all need 3PL services.
    if not is_physical:
        result.relevant = False
        result.rejection_reason = (
            "no physical-product evidence found — likely a SaaS or service business")
    return result


def apply_classification(db: Session, company: Company,
                         result: Classification) -> Company:
    company.platform = result.platform
    company.is_ecommerce = result.is_ecommerce
    company.is_physical_product = result.is_physical_product
    company.country = result.country
    company.country_confidence = result.country_confidence
    company.industry = result.industry
    company.currencies = result.currencies
    if result.name and not company.name:
        company.name = result.name
    if result.description and not company.description:
        company.description = result.description[:2000]

    company.last_classified_at = datetime.now(timezone.utc)
    if result.relevant:
        company.status = "classified"
        company.rejection_reason = None
    else:
        company.status = "rejected"
        company.rejection_reason = result.rejection_reason
    db.flush()
    return company

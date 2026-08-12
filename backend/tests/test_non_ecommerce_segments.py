"""3PL customers are not only DTC brands.

Before migration 004 the qualification gate required BOTH `ecommerce` and
`physical_products`, so a wholesaler or manufacturer with no online store was
capped at 45/100 no matter how strong its other signals were. These tests
pin the broadened behaviour.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.engine import scoring
from app.engine.classifier import classify
from app.engine.extractor import ExtractedPage
from app.engine.signals import detect_signals, persist_signals
from app.models import Signal


def page(url: str, text: str, page_type: str = "website") -> ExtractedPage:
    p = ExtractedPage(url=url, text=text)
    p.page_type = page_type
    return p


# --------------------------------------------------------------------------
# Fixtures: real-shaped sites with no cart
# --------------------------------------------------------------------------
WHOLESALER = [
    page("https://example.com",
         "Trade supplier of homeware since 1998. Wholesale enquiries welcome. "
         "Trade pricing available to approved accounts."),
    page("https://example.com/wholesale",
         "Minimum order quantity is 24 units per style. Download our wholesale "
         "price list. Bulk orders dispatched on pallets within 5 working days. "
         "Become a stockist today.", "other"),
    page("https://example.com/shipping",
         "Delivery times are 3-5 working days. Orders ship from our warehouse. "
         "A tracking number is issued on dispatch.", "shipping"),
]

MANUFACTURER = [
    page("https://example.com",
         "We manufacture premium skincare in small batches. Our factory in "
         "Yorkshire produces over 40 SKUs."),
    page("https://example.com/about",
         "Our production facility handles contract manufacturing and private "
         "label for other brands. Raw materials are sourced in the UK. We hold "
         "stock levels of finished goods ready for dispatch.", "about"),
]

RETAIL_BRAND = [
    page("https://example.com",
         "Award-winning snacks. Find a stockist near you."),
    page("https://example.com/stockists",
         "Available in store at over 400 retail partners nationwide. Our "
         "retail partners include major supermarkets. Where to buy: see the "
         "list below.", "other"),
    page("https://example.com/shipping",
         "Case pack quantities ship on pallets. Lead time 7 days.", "shipping"),
]

SUBSCRIPTION = [
    page("https://example.com",
         "The coffee subscription box delivered monthly. Subscribe and save "
         "20%. Cancel anytime."),
    page("https://example.com/shipping",
         "Your recurring delivery ships on the 1st of each month. Free "
         "shipping on all subscriptions. Tracking number provided.", "shipping"),
]

SAAS = [
    page("https://example.com",
         "DataFlow is a SaaS analytics platform. Book a demo. Start free "
         "trial. Pricing per seat, per user per month. Read our API "
         "documentation."),
]


# --------------------------------------------------------------------------
# Classification: physical goods without a cart
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name,pages,expected_model", [
    ("wholesaler", WHOLESALER, "wholesale"),
    ("manufacturer", MANUFACTURER, "manufacturer"),
    ("retail brand", RETAIL_BRAND, "retail"),
    ("subscription", SUBSCRIPTION, "subscription"),
])
def test_non_ecommerce_companies_are_classified_as_physical(
        db, company, name, pages, expected_model):
    result = classify(company, pages)
    assert result.is_physical_product is True, (
        f"{name} moves physical goods but was not detected as such")
    assert result.relevant is True, f"{name} was wrongly rejected"
    assert result.business_model == expected_model, (
        f"{name} classified as {result.business_model!r}")


def test_saas_is_still_rejected(db, company):
    """Broadening the gate must not let software companies through."""
    result = classify(company, SAAS)
    assert result.relevant is False
    assert result.rejection_reason


def test_a_company_selling_everywhere_is_multi_channel(db, company):
    pages = WHOLESALER + RETAIL_BRAND + [
        page("https://example.com/shop", "Available on Amazon. Our eBay shop "
             "stocks clearance lines. Add to cart.")]
    result = classify(company, pages)
    assert result.business_model == "multi_channel"
    assert len(result.sales_channels) >= 3


# --------------------------------------------------------------------------
# Scoring: the 45-point cap must no longer apply
# --------------------------------------------------------------------------
def _persist_sources(db, company, pages):
    """Mimic what the crawler stores, so evidence quality can be scored."""
    from app.models import Source
    from app.utils.text import content_hash, truncate
    for pg in pages:
        db.add(Source(company_id=company.id, source_type=pg.page_type,
                      url=pg.url, title=pg.title or "", content=pg.text,
                      excerpt=truncate(pg.text, 500),
                      content_hash=content_hash(pg.text)))
    db.flush()


def _score(db, company, config, pages):
    from app.engine.classifier import apply_classification
    apply_classification(db, company, classify(company, pages))
    _persist_sources(db, company, pages)
    detected = detect_signals(db, company, pages, config)
    stored = persist_signals(db, company, config, detected)
    return scoring.calculate(db, company, stored, config), stored


# Extra pages that turn a bare listing into a company worth calling.
def growth_pages(prefix: str) -> list[ExtractedPage]:
    return [
        page(f"https://example.com/careers",
             "We're hiring a Warehouse Manager and an Operations Manager to "
             "run our new facility.", "careers"),
        page(f"https://example.com/news",
             f"{prefix} is moving to a larger facility this autumn after "
             "raising a seed round. We now ship worldwide and are outgrowing "
             "our warehouse.", "news"),
    ]


@pytest.mark.parametrize("name,pages", [
    ("wholesaler", WHOLESALER),
    ("manufacturer", MANUFACTURER),
    ("retail brand", RETAIL_BRAND),
    ("subscription", SUBSCRIPTION),
])
def test_non_ecommerce_companies_are_no_longer_gated(db, company, config,
                                                     name, pages):
    """The point of migration 004: these companies can now be scored on their
    merits instead of being capped at 45 for having no online store."""
    result, _ = _score(db, company, config, pages)
    assert not result.missing_required, (
        f"{name} is still failing the qualification gate: "
        f"{result.missing_required}")


@pytest.mark.parametrize("name,pages", [
    ("wholesaler", WHOLESALER),
    ("manufacturer", MANUFACTURER),
    ("retail brand", RETAIL_BRAND),
    ("subscription", SUBSCRIPTION),
])
def test_a_well_signalled_non_ecommerce_company_scores_well(
        db, company, config, name, pages):
    """With hiring, expansion and capacity signals - the things a salesperson
    would actually care about - a company with no online store must be able
    to reach GOOD or better."""
    result, signals = _score(db, company, config,
                             pages + growth_pages(name))
    types = {s.signal_type for s in signals}
    assert "physical_products" in types
    assert result.score > 45, (
        f"{name} scored {result.score} with signals {sorted(types)}")


def test_a_bare_listing_still_scores_low(db, company, config):
    """Removing the cap must not mean everything scores high. A company with
    only two weak signals is a weak lead and should look like one."""
    result, _ = _score(db, company, config, WHOLESALER)
    assert result.score < 45
    assert result.intent_level in ("LOW", "POSSIBLE")


def test_physical_products_is_the_only_required_signal(config):
    assert config.required_signals == ["physical_products"], (
        "Migration 004 sets the gate to physical goods only")


def test_a_company_with_no_physical_goods_is_still_capped(db, company, config):
    """The gate still exists - it's just a different gate."""
    signals = [Signal(company_id=company.id, service_id=config.id,
                      signal_type=t, strength=1.0, confidence=1.0,
                      detected_at=datetime.now(timezone.utc))
               for t in ("ecommerce", "recent_funding", "operations_hiring")]
    result = scoring.calculate(db, company, signals, config)
    assert result.missing_required == ["physical_products"]
    assert result.score <= 45


# --------------------------------------------------------------------------
# The new high-intent signals
# --------------------------------------------------------------------------
def test_seeking_a_3pl_is_the_strongest_signal(config):
    weights = {t: config.weight_for(t) for t in config.signals}
    assert weights["seeking_3pl"] == max(weights.values()), (
        "A company publicly looking for a fulfillment partner should outweigh "
        "every other signal")


def test_capacity_strain_is_detected_with_evidence(db, company, config):
    news = page("https://example.com/news",
                "We are outgrowing our warehouse and orders are on backorder "
                "while we scale.", "news")
    found = {s.signal_type: s for s in detect_signals(db, company, [news], config)}
    assert "capacity_strain" in found
    assert "outgrowing our warehouse" in found["capacity_strain"].evidence.lower()


def test_wholesale_signal_fires_on_a_trade_page(db, company, config):
    found = {s.signal_type: s for s in detect_signals(db, company, WHOLESALER, config)}
    assert "wholesale_b2b" in found
    assert found["wholesale_b2b"].evidence

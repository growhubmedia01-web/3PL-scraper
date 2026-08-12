"""Service businesses must never appear as prospects.

The hard case is that a 3PL provider's own website is *full* of fulfillment
vocabulary - warehouse, pick and pack, inventory, shipping - and would
otherwise score higher than a real brand. But a brand that merely mentions
using a fulfillment partner is a strong customer signal and must survive.
"""
from __future__ import annotations

import pytest

from app.engine.classifier import classify
from app.engine.extractor import ExtractedPage


def page(url: str, text: str, page_type: str = "website") -> ExtractedPage:
    p = ExtractedPage(url=url, text=text)
    p.page_type = page_type
    return p


# --------------------------------------------------------------------------
# Must be rejected
# --------------------------------------------------------------------------
A_3PL_PROVIDER = [
    page("https://example.com",
         "We are a 3PL serving ecommerce brands. Our fulfillment services "
         "include pick and pack services, warehousing and returns. We store "
         "your products and ship them nationwide."),
    page("https://example.com/about",
         "Third party logistics provider with 4 distribution centres. "
         "We handle your inventory so you can focus on growth.", "about"),
]

A_FREIGHT_COMPANY = [
    page("https://example.com",
         "Freight forwarding services worldwide. We are a freight forwarder "
         "with customs brokerage services and container shipments."),
]

AN_AGENCY = [
    page("https://example.com",
         "We are a marketing agency for DTC brands. Our SEO agency team "
         "builds Shopify stores. We build websites that convert."),
]

A_SAAS = [
    page("https://example.com",
         "Our SaaS platform manages inventory for ecommerce brands. "
         "Request a demo of our platform. Pricing per seat, per user "
         "per month."),
]

A_RESTAURANT = [
    page("https://example.com",
         "Our restaurant serves seasonal food. Book a table online. "
         "Free shipping on gift vouchers."),
]


@pytest.mark.parametrize("name,pages", [
    ("3PL provider", A_3PL_PROVIDER),
    ("freight forwarder", A_FREIGHT_COMPANY),
    ("marketing agency", AN_AGENCY),
    ("SaaS platform", A_SAAS),
    ("restaurant", A_RESTAURANT),
])
def test_service_businesses_are_rejected(db, company, name, pages):
    result = classify(company, pages)
    assert result.relevant is False, f"{name} was NOT rejected"
    assert "service business" in (result.rejection_reason or "").lower()


def test_the_rejection_reason_names_the_evidence(db, company):
    result = classify(company, A_3PL_PROVIDER)
    assert result.rejection_reason
    assert len(result.rejection_reason) > 30, (
        "the reason must be specific enough to audit a false positive")


# --------------------------------------------------------------------------
# Must survive
# --------------------------------------------------------------------------
BRAND_USING_A_3PL = [
    page("https://example.com",
         "Handmade candles. Add to cart. Free shipping over £40."),
    page("https://example.com/shipping",
         "Orders are dispatched by our fulfillment partner within 2 working "
         "days. A tracking number is issued on dispatch. We ship worldwide.",
         "shipping"),
]

BRAND_WITH_OWN_WAREHOUSE = [
    page("https://example.com",
         "Outdoor gear built to last. Add to cart."),
    page("https://example.com/about",
         "We ship everything from our own warehouse in Leeds. Our inventory "
         "is managed in house.", "about"),
]

WHOLESALER_MENTIONING_FREIGHT = [
    page("https://example.com",
         "Wholesale homeware. Trade accounts available."),
    page("https://example.com/wholesale",
         "Minimum order quantity 24 units. Bulk orders ship on pallets. "
         "Freight charged at cost for container shipments.", "other"),
]


@pytest.mark.parametrize("name,pages", [
    ("brand that uses a 3PL", BRAND_USING_A_3PL),
    ("brand with its own warehouse", BRAND_WITH_OWN_WAREHOUSE),
    ("wholesaler mentioning freight", WHOLESALER_MENTIONING_FREIGHT),
])
def test_real_brands_are_not_mistaken_for_service_businesses(
        db, company, name, pages):
    result = classify(company, pages)
    assert result.relevant is True, (
        f"{name} was wrongly rejected: {result.rejection_reason}")
    assert result.is_physical_product is True


def test_using_a_fulfillment_partner_is_a_customer_signal_not_a_disqualifier(
        db, company, config):
    """This is the distinction the whole exclusion list turns on."""
    from app.engine.signals import detect_signals

    result = classify(company, BRAND_USING_A_3PL)
    assert result.relevant is True

    from app.engine.classifier import apply_classification
    apply_classification(db, company, result)
    found = {s.signal_type for s in
             detect_signals(db, company, BRAND_USING_A_3PL, config)}
    assert "existing_3pl" in found, (
        "an incumbent provider should be detected as a (negative) signal, "
        "not cause rejection")


# --------------------------------------------------------------------------
# Config-driven extra types
# --------------------------------------------------------------------------
def test_extra_excluded_types_from_config_are_applied(db, company):
    pages = [page("https://example.com",
                  "We are a recruitment agency placing candidates in retail. "
                  "Add to cart for our merchandise.")]
    assert classify(company, pages, ["recruitment agency"]).relevant is False


def test_config_types_only_match_self_description_pages(db, company):
    """A blog post mentioning "law firm" must not disqualify a brand."""
    pages = [
        page("https://example.com", "Leather bags. Add to cart. Free shipping. "
             "Shipping policy applies."),
        page("https://example.com/blog/post",
             "We supplied bags to a law firm for their staff gifts.", "news"),
    ]
    assert classify(company, pages, ["law firm"]).relevant is True

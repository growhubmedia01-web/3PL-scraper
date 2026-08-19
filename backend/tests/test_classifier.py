from __future__ import annotations

from app.engine.classifier import classify
from app.engine.extractor import ExtractedPage, extract

SHOPIFY_HTML = """
<html><head><title>Nordic Wool | Merino Basics</title>
<meta name="description" content="Sustainable merino wool basics, made in Britain.">
<script src="https://cdn.shopify.com/s/files/1/assets/theme.js"></script></head>
<body><h1>Nordic Wool</h1>
<button>Add to cart</button>
<p>Free shipping on UK orders over £50. We ship worldwide.</p>
<p>Contact us at 12 High Street, London, SW1A 1AA</p>
<span>£45.00</span>
</body></html>
"""

SAAS_HTML = """
<html><head><title>DataFlow - Analytics Platform</title></head>
<body><h1>DataFlow</h1><a href="/demo">Book a demo</a>
<p>Start free trial. Pricing per seat, per user per month.</p>
<p>Read our API documentation.</p></body></html>
"""


def test_extract_pulls_title_meta_and_text():
    page = extract(SHOPIFY_HTML, "https://nordicwool.co.uk")
    assert "Nordic Wool" in page.title
    assert "merino" in page.meta_description.lower()
    assert "add to cart" in page.searchable


def test_classifier_detects_shopify_ecommerce(db, company):
    page = extract(SHOPIFY_HTML, "https://nordicwool.co.uk")
    shipping = ExtractedPage(url="https://nordicwool.co.uk/shipping",
                             text="We ship worldwide. Dispatch within 2 days.",
                             page_type="shipping")
    result = classify(company, [page, shipping])

    assert result.platform == "shopify"
    assert result.is_ecommerce is True
    assert result.is_physical_product is True
    assert result.relevant is True


def test_classifier_detects_country_from_tld_and_address(db, company):
    company.domain = "nordicwool.co.uk"
    page = extract(SHOPIFY_HTML, "https://nordicwool.co.uk")
    result = classify(company, [page])
    assert result.country == "GB"
    assert result.country_confidence > 0


def test_classifier_rejects_saas_with_a_reason(db, company):
    page = extract(SAAS_HTML, "https://dataflow.io")
    result = classify(company, [page])
    assert result.relevant is False
    assert result.rejection_reason


def test_classifier_rejects_when_nothing_was_crawled(db, company):
    result = classify(company, [])
    assert result.relevant is False
    assert result.rejection_reason == "no pages crawled"


def test_classifier_rejects_trade_magazine_reporting_on_other_brands(db, company):
    """Real production bug: a fashion-industry magazine's homepage reads
    'Premier reporting for intimate apparel' and its articles are full of
    other brands' shipping/returns/retail-distribution vocabulary - it
    scored STRONG as if it were a goods company itself."""
    company.domain = "underlinesmagazine.com"
    page = ExtractedPage(
        url="https://underlinesmagazine.com",
        title="Underlines Magazine - Premier reporting for intimate apparel",
        text="Premier reporting for intimate apparel. New Designers Bringing "
             "Fresh Perspectives to Scoop.")
    result = classify(company, [page])
    assert result.relevant is False
    assert "service business" in result.rejection_reason


def test_classifier_rejects_news_site_via_domain_keyword_alone(db, company):
    """The domain-keyword check must catch a publisher even when the page
    copy doesn't happen to match any fixed self-description phrase."""
    company.domain = "widgetindustrymagazine.com"
    page = ExtractedPage(
        url="https://widgetindustrymagazine.com",
        title="Widget Industry Magazine",
        text="Add to cart. Free shipping worldwide. Ships within 2 days.")
    result = classify(company, [page])
    assert result.relevant is False


def test_classifier_rejects_real_estate_news_site(db, company):
    """Real production bug: bisnow.com ('Commercial Real Estate News -
    Bisnow') scored STRONG the same way."""
    company.domain = "bisnow.com"
    page = ExtractedPage(
        url="https://bisnow.com",
        title="Commercial Real Estate News - Bisnow",
        text="Commercial Real Estate News - Bisnow. Cities Atlanta Austin "
             "Boston Chicago Dallas.")
    result = classify(company, [page])
    assert result.relevant is False

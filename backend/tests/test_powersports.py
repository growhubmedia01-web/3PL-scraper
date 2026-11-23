"""Powersports Aftermarket Product Sourcing - required behaviour (spec s.16).

All page content is synthetic. It follows real-world *patterns* (a
distributor's supplier-application page vs. its dealer-application page, a
brand-partnership announcement, a UTV-accessories expansion) and never
hardcodes a production lead.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.engine import product_interest, profile, scoring
from app.engine.ai_analysis import AIAnalysis, _build_prompt, ground_analysis
from app.engine.classifier import apply_classification, classify
from app.engine.extractor import ExtractedPage, classify_page_type
from app.engine.service_config import build_config
from app.engine.signals import detect_signals, persist_signals
from app.models import (
    Company, CompanyFact, DiscoveryQuery, ProductInterest, ServiceOpportunity, Signal, Source,
)
from scripts.services import powersports_aftermarket_sourcing as ps

NOW = datetime.now(timezone.utc)
RECENT = (NOW - timedelta(days=10)).isoformat()
NO_DEMAND = "Specific product demand not publicly disclosed."

DISTRIBUTOR_HOME = (
    "Ridgeline Powersports Supply is a wholesale distributor of aftermarket "
    "powersports parts and accessories serving independent dealers across the "
    "United States. We distribute more than 120 brands of ATV, UTV and "
    "motorcycle parts from distribution centers in Texas and Minnesota. "
    "Dealers only. Become a dealer to access dealer pricing through our "
    "dealer portal.")
DISTRIBUTOR_ABOUT = (
    "Founded in 1994, Ridgeline is headquartered in Dallas, Texas. Our team "
    "of 180 employees supports more than 4,000 authorized dealers in 48 "
    "states. We are a wholesale distributor of aftermarket parts for "
    "side-by-side, ATV, motorcycle and snowmobile riders.")


# ---------------------------------------------------------------------
# fixtures and helpers
# ---------------------------------------------------------------------
@pytest.fixture
def ps_service(db):
    from scripts.seed import seed_service_module
    svc = seed_service_module(db, ps, with_library=True)
    db.flush()
    return svc


@pytest.fixture
def ps_config(db, ps_service):
    return build_config(db, ps_service)


def page(url: str, text: str, title: str = "", published_at: str | None = None,
         page_type: str | None = None) -> ExtractedPage:
    p = ExtractedPage(url=url, title=title, text=text, published_at=published_at)
    p.page_type = page_type or classify_page_type(url)
    return p


def make_company(db, domain: str, name: str | None = None) -> Company:
    row = Company(name=name, domain=domain, website=f"https://{domain}",
                  status="discovered")
    db.add(row)
    db.flush()
    return row


def store_sources(db, company: Company, pages: list[ExtractedPage]) -> None:
    for p in pages:
        db.add(Source(company_id=company.id,
                      source_type=p.page_type if p.page_type != "website" else "website",
                      url=p.url, title=p.title, content=p.text,
                      published_at=datetime.fromisoformat(p.published_at)
                      if p.published_at else None))
    db.flush()


def analyse(db, config, company: Company, pages: list[ExtractedPage]):
    """The deterministic half of the pipeline, in pipeline order."""
    store_sources(db, company, pages)
    result = classify(company, pages, config.excluded_business_types, config=config)
    apply_classification(db, company, result)
    profile.apply_profile(db, company, pages, config.size_bands)
    signals = persist_signals(db, company, config,
                              detect_signals(db, company, pages, config))
    interests = product_interest.run(db, company, signals, pages, config)
    score = scoring.calculate(db, company, signals, config)
    return result, {s.signal_type: s for s in signals}, interests, score


def distributor_pages(domain: str = "ridgelinesupply.com") -> list[ExtractedPage]:
    return [
        page(f"https://{domain}", DISTRIBUTOR_HOME,
             "Ridgeline Powersports Supply | Wholesale Distributor"),
        page(f"https://{domain}/about-us", DISTRIBUTOR_ABOUT, "About Ridgeline"),
    ]


# ---------------------------------------------------------------------
# TEST 1 - positive distributor classification
# ---------------------------------------------------------------------
def test_01_us_wholesale_powersports_distributor_qualifies(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    result, signals, _, _ = analyse(db, ps_config, company, distributor_pages())

    assert result.relevant, result.rejection_reason
    assert result.company_type == "wholesale_distributor"
    assert result.country == "US"
    assert result.industry == "powersports"
    assert company.status == "classified"
    assert company.company_type == "wholesale_distributor"
    # fit signals, not buying signals
    assert "powersports_participation" in signals
    assert "b2b_dealer_distribution" in signals


# ---------------------------------------------------------------------
# TEST 2 - direct supplier sourcing (supplier page asks for catalogs)
# ---------------------------------------------------------------------
def test_02_supplier_catalog_request_is_a_strong_sourcing_signal(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    pages = distributor_pages() + [page(
        "https://ridgelinesupply.com/vendors",
        "Interested in becoming a vendor? Ridgeline is always looking for new "
        "products and new brands for our dealers. Submit your product catalog "
        "for consideration by our purchasing team using the vendor application "
        "below.", "Vendor Application", published_at=RECENT)]
    _, signals, _, score = analyse(db, ps_config, company, pages)

    assert "explicit_supplier_search" in signals
    assert "supplier_application_open" in signals
    sig = signals["explicit_supplier_search"]
    assert sig.strength == 1.0                      # supplier page = on-topic
    assert sig.confidence >= 0.8
    assert "catalog" in sig.evidence.lower() or "new products" in sig.evidence.lower()
    line = next(l for l in score.breakdown if l.signal_type == "explicit_supplier_search")
    assert line.points >= 0.8 * 30 * 0.95           # near full weight of 30


# ---------------------------------------------------------------------
# TEST 3 - product-specific RFQ keeps category and source
# ---------------------------------------------------------------------
def test_03_utv_accessory_rfq_extracts_category_and_source(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    rfq_url = "https://ridgelinesupply.com/news/2026-utv-sourcing"
    pages = distributor_pages() + [page(
        rfq_url,
        "Ridgeline is seeking quotes from manufacturers for UTV accessories, "
        "including front bumpers, roof racks and windshields for the Polaris "
        "RZR and Can-Am Maverick.", "UTV accessory sourcing request",
        published_at=RECENT)]
    _, signals, interests, _ = analyse(db, ps_config, company, pages)

    assert "active_product_rfq" in signals
    seeking = [i for i in interests if i.interest_type == "EXPLICITLY_SEEKING"]
    assert seeking, "an explicit RFQ must produce an EXPLICITLY_SEEKING record"
    assert {i.category for i in seeking} == {"ATV/UTV/Side-by-Side Accessories"}
    subs = {i.subcategory for i in seeking}
    assert {"Bumpers", "Roof Racks", "Windshields"} <= subs
    for record in seeking:
        assert record.source_url == rfq_url
        assert record.source_id is not None
        assert "UTV/Side-by-Side" in record.vehicle_segments
        assert {"Polaris", "Can-Am"} <= set(record.vehicle_platforms)


# ---------------------------------------------------------------------
# TEST 4 - new distribution partnership
# ---------------------------------------------------------------------
def test_04_brand_partnership_gets_weighted_expansion_signal(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    pages = distributor_pages() + [page(
        "https://ridgelinesupply.com/news/trailcraft-partnership",
        "Ridgeline Powersports Supply has signed an exclusive distribution "
        "agreement with Trailcraft Racing to distribute its riding gear, "
        "helmets and gloves to dealers nationwide.",
        "Ridgeline adds Trailcraft Racing", published_at=RECENT)]
    _, signals, interests, score = analyse(db, ps_config, company, pages)

    assert "new_distribution_partnership" in signals
    weight = ps_config.signals["new_distribution_partnership"].weight
    line = next(l for l in score.breakdown
                if l.signal_type == "new_distribution_partnership")
    assert line.weight == weight == 27
    assert 0.8 * weight <= line.points <= weight
    added = [i for i in interests if i.interest_type == "RECENTLY_ADDED"]
    assert any(i.category == "Riding Gear and Protection" for i in added)


# ---------------------------------------------------------------------
# TEST 5 - product-category extraction
# ---------------------------------------------------------------------
def test_05_product_terms_are_extracted_to_their_subcategories(ps_config):
    text = ("The new catalog adds bumpers, rock sliders, windshields and roof "
            "racks for the 2026 model year.")
    found = product_interest.match_products(text, ps_config.product_taxonomy)
    subs = {sub for (_, sub) in found}
    assert {"Bumpers", "Rock Sliders", "Windshields", "Roof Racks"} <= subs
    # nothing outside the text is invented
    assert "Winches" not in subs
    assert "Tires" not in " ".join(subs)


# ---------------------------------------------------------------------
# TEST 6 - reverse commercial direction
# ---------------------------------------------------------------------
def test_06_manufacturer_seeking_us_distributor_is_not_a_buyer(db, ps_config):
    company = make_company(db, "trailforgeoffroad.com")
    pages = [
        page("https://trailforgeoffroad.com",
             "Trailforge Offroad designs and manufactures UTV bumpers and rock "
             "sliders in our factory. We manufacture every part in-house for "
             "Polaris and Can-Am side-by-side owners. Find a dealer near you.",
             "Trailforge Offroad"),
        page("https://trailforgeoffroad.com/news/expansion",
             "We are looking for a US distributor and are seeking distributors "
             "for our UTV accessories. Distributor inquiries welcome. We are "
             "looking for new products partners who can distribute our products.",
             "Distributors wanted", published_at=RECENT),
    ]
    result, signals, interests, score = analyse(db, ps_config, company, pages)

    assert result.company_type in {"manufacturer", "brand_owner"}
    assert not result.relevant
    assert "manufacturer_seeking_distribution" in signals
    for positive in ("active_product_rfq", "explicit_supplier_search",
                     "supplier_application_open"):
        assert positive not in signals
    assert not [i for i in interests if i.interest_type == "EXPLICITLY_SEEKING"]
    neg = next(l for l in score.breakdown
               if l.signal_type == "manufacturer_seeking_distribution")
    assert neg.points < 0


# ---------------------------------------------------------------------
# TEST 7 - dealer application is the selling direction
# ---------------------------------------------------------------------
def test_07_become_a_dealer_page_is_not_supplier_sourcing(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    dealer = page(
        "https://ridgelinesupply.com/become-a-dealer",
        "Become a dealer. Complete our dealer application to open a dealer "
        "account. We are looking for new dealers and accepting new dealer "
        "accounts. Get a quote on dealer pricing for our full line of products "
        "and submit your application today.", "Become a Dealer",
        published_at=RECENT)
    assert dealer.page_type == "dealer"
    _, signals, interests, _ = analyse(db, ps_config, company,
                                       distributor_pages() + [dealer])

    for positive in ("active_product_rfq", "explicit_supplier_search",
                     "supplier_application_open"):
        assert positive not in signals, positive
    assert not [i for i in interests if i.interest_type == "EXPLICITLY_SEEKING"]


def test_07b_supplier_and_dealer_pages_are_told_apart(db, ps_config):
    """Distributor with both a supplier application and a dealer application:
    only the supplier page may create a buying signal."""
    company = make_company(db, "ridgelinesupply.com")
    supplier = page("https://ridgelinesupply.com/supplier-application",
                    "New vendor application for manufacturers who want "
                    "Ridgeline to carry their products.", "Supplier Application")
    dealer = page("https://ridgelinesupply.com/dealer-application",
                  "Dealer application. Become a dealer and open a dealer "
                  "account.", "Dealer Application")
    _, signals, _, _ = analyse(db, ps_config, company,
                               distributor_pages() + [supplier, dealer])
    sources = {s.id: s for s in db.execute(select(Source)).scalars()}
    assert "supplier_application_open" in signals
    assert sources[signals["supplier_application_open"].source_id].url == supplier.url


# ---------------------------------------------------------------------
# TEST 8 - business-type exclusions
# ---------------------------------------------------------------------
@pytest.mark.parametrize("domain,text,expected_type", [
    ("lakesidepowersports.com",
     "Visit our showroom for new and used ATVs, UTVs and motorcycles. Browse "
     "our inventory, schedule a test ride and value your trade. Showroom hours "
     "Monday to Saturday. Financing available at our dealership.",
     "dealer_retailer"),
    ("twowheelrepair.com",
     "Our technicians repair motorcycles, dirt bikes and ATVs. Schedule service "
     "online or book a service appointment. Our service department offers "
     "service specials every month. We repair all makes.",
     "service_provider"),
    ("summitmotorworks.com",
     "We design and build motorcycle exhausts. Every part is engineered and "
     "manufactured in our manufacturing facility. Made in the USA for "
     "motorcycle and dirt bike riders. Find a dealer near you.",
     "manufacturer"),
])
def test_08_retailer_repair_shop_and_manufacturer_do_not_qualify(
        db, ps_config, domain, text, expected_type):
    company = make_company(db, domain)
    result, _, _, _ = analyse(db, ps_config, company,
                              [page(f"https://{domain}", text)])
    assert not result.relevant
    assert result.rejection_reason
    assert company.status == "rejected"
    if result.company_type is not None:
        assert result.company_type == expected_type
        assert result.company_type not in ps.CONFIG["qualification"][
            "eligible_company_types"]


# ---------------------------------------------------------------------
# TEST 8b - US only: a company must be positively located in the US
# ---------------------------------------------------------------------
_CORE = ("We are a wholesale distributor of aftermarket powersports parts for "
         "ATV, UTV and motorcycle dealers. Dealers only. Become a dealer for "
         "dealer pricing through our dealer portal. ")


@pytest.mark.parametrize("domain,home,contact,expected_country,qualifies", [
    # US, recognised from a state + ZIP or "City, ST" alone
    ("acme.com", _CORE, "100 Main St, Dallas, TX 75201", "US", True),
    ("acme.com", _CORE, "Visit us in Elkhart, IN.", "US", True),
    ("acme.com", _CORE + "Family owned in Fargo, North Dakota.", "Call us.", "US", True),
    ("acme.com", _CORE, "Albuquerque, NM 87102", "US", True),
    # US distributors that SELL into Canada/Mexico stay US
    ("acme.com", _CORE + "Serving dealers in the US and Canada.",
     "Dallas, TX 75201", "US", True),
    ("acme.com", _CORE + "We ship to dealers in Canada and Mexico.",
     "Dallas, TX 75201", "US", True),
    # no location evidence on a generic TLD -> kept, flagged UNVERIFIED (08g)
    ("acme.com", _CORE, "Call us or email the sales team.", "US", True),
    # ...on a country TLD -> rejected
    ("acme.de", _CORE, "Call us or email the sales team.", "DE", False),
    # a bare 5-digit postcode is not a US ZIP: nothing proves Germany either,
    # so on .com this is an unverified lead for a human to check
    ("acme.com", _CORE, "Hauptstrasse 5, 80331 Muenchen", "US", True),
    ("acme.com", _CORE + "Distribuidor en Monterrey, Mexico.",
     "Monterrey, N.L. 64000", "MX", False),
    # non-US companies, including ones that say they serve the US
    ("acme.ca", _CORE + "Serving dealers across Canada.", "Toronto, ON M5V 2T6", "CA", False),
    ("acme.com", _CORE + "Canadian owned, serving the United States.",
     "Barrie, Ontario L4N 6B5", "CA", False),
    ("acme.com", _CORE + "Based in Quebec.", "1200 Rue Principale, Laval, QC H7S 1Z4",
     "CA", False),
    ("acme.com", _CORE, "Unit 4, Birmingham B12 0XS, England", "GB", False),
    ("acme.com.au", _CORE + "Australia's leading distributor.", "Sydney NSW 2000", "AU", False),
])
def test_08b_only_companies_located_in_the_us_qualify(
        db, ps_config, domain, home, contact, expected_country, qualifies):
    company = make_company(db, domain)
    pages = [page(f"https://{domain}", home, "Acme Distribution"),
             page(f"https://{domain}/contact", contact)]
    result = classify(company, pages, ps_config.excluded_business_types,
                      config=ps_config)
    assert result.country == expected_country
    assert result.relevant is qualifies, result.rejection_reason
    if not qualifies:
        assert "geography (US)" in result.rejection_reason


def test_08g_no_address_on_generic_tld_is_a_flagged_lead(db, ps_config):
    company = make_company(db, "acme.com")
    result = classify(company, [
        page("https://acme.com", _CORE, "Acme Distribution"),
        page("https://acme.com/contact", "Call us or email the sales team."),
    ], ps_config.excluded_business_types, config=ps_config)
    assert result.relevant and result.country == "US"
    assert result.country_confidence < ps.CONFIG["qualification"]["min_country_confidence"]
    assert any(e.startswith("UNVERIFIED") for e in result.evidence["country"])


def test_08h_unverified_location_is_opt_in():
    from app.engine.classifier import _apply_qualification, Classification
    strict = {"allowed_countries": ["US"], "require_country_evidence": True}
    result = Classification(country=None)
    _apply_qualification(result, strict, "acme.com")
    assert not result.relevant
    result = Classification(country=None)
    _apply_qualification(result, {**strict, "allow_unverified_location_tlds": ["com"]},
                         "acme.com")
    assert result.relevant and result.country == "US"
    # positive foreign evidence is never overridden
    result = Classification(country="CA", country_confidence=0.9)
    _apply_qualification(result, {**strict, "allow_unverified_location_tlds": ["com"]},
                         "acme.com")
    assert not result.relevant


def test_08c_lenient_country_gate_is_unchanged_for_other_services(db, ps_config):
    """require_country_evidence is opt-in: without it, unknown location
    still passes, exactly as before."""
    from app.engine.classifier import _apply_qualification, Classification
    result = Classification(country=None, country_confidence=0.0)
    _apply_qualification(result, {"allowed_countries": ["US"]})
    assert result.relevant
    _apply_qualification(result, {"allowed_countries": ["US"],
                                  "require_country_evidence": True})
    assert not result.relevant


def test_08d_weak_signal_us_powersports_distributor_still_qualifies(db, ps_config):
    """No cart, no shipping page, no 'dealers only' wording and a single
    powersports marker: still a lead (ranked low), not a rejection."""
    company = make_company(db, "trailpartsco.com")
    pages = [page("https://trailpartsco.com",
                  "Trail Parts Co supplies parts and accessories for UTV "
                  "owners. New brands added every season.", "Trail Parts Co"),
             page("https://trailpartsco.com/contact", "400 Oak St, Boise, ID 83702")]
    result = classify(company, pages, ps_config.excluded_business_types,
                      config=ps_config)
    assert result.relevant, result.rejection_reason
    assert result.is_physical_product
    assert result.industry == "powersports"


def test_08e_non_powersports_and_non_us_are_still_rejected(db, ps_config):
    saas = make_company(db, "cloudbooks.com")
    result = classify(saas, [
        page("https://cloudbooks.com", "Cloud accounting software for small "
             "businesses. Start your free trial.", "CloudBooks"),
        page("https://cloudbooks.com/contact", "1 Market St, San Francisco, CA 94105"),
    ], ps_config.excluded_business_types, config=ps_config)
    assert not result.relevant
    foreign = make_company(db, "quadparts.ca")
    result = classify(foreign, [
        page("https://quadparts.ca", "ATV and UTV parts for riders.", "Quad Parts"),
        page("https://quadparts.ca/contact", "Toronto, ON M5V 2T6"),
    ], ps_config.excluded_business_types, config=ps_config)
    assert not result.relevant
    assert "geography (US)" in result.rejection_reason


def test_08f_industry_implies_physical_is_opt_in(db, ps_service):
    """Without the flag, the physical-product gate behaves exactly as before."""
    import copy
    raw = copy.deepcopy(ps.CONFIG)
    raw["qualification"].pop("industry_implies_physical")
    ps_service.config = raw
    config = build_config(db, ps_service)
    company = make_company(db, "trailpartsco.com")
    result = classify(company, [
        page("https://trailpartsco.com", "Parts and accessories for UTV owners.",
             "Trail Parts Co"),
        page("https://trailpartsco.com/contact", "400 Oak St, Boise, ID 83702"),
    ], config.excluded_business_types, config=config)
    assert not result.relevant
    assert "physical-product" in result.rejection_reason


# ---------------------------------------------------------------------
# TEST 9 - freshness
# ---------------------------------------------------------------------
def test_09_recent_sourcing_announcement_outscores_an_old_one(db, ps_config):
    def score_for(age_days: int) -> float:
        company = make_company(db, f"dist{age_days}.com")
        signal = Signal(company_id=company.id, service_id=ps_config.id,
                        signal_type="explicit_supplier_search", strength=1.0,
                        confidence=0.85, evidence="We are seeking new suppliers.",
                        detected_at=NOW - timedelta(days=age_days))
        raw, _, _ = scoring.deterministic_score([signal], ps_config, NOW)
        return raw

    fresh, old, expired = score_for(5), score_for(100), score_for(200)
    assert fresh > old > 0
    assert expired == 0                     # 120-day decay window has passed


def test_09b_published_date_drives_freshness(db, ps_config):
    """Same text, different publication dates -> the recent one wins."""
    text = ("Ridgeline is looking for new suppliers of UTV accessories and "
            "invites manufacturers to submit your product catalog.")
    results = {}
    for label, published in (("recent", RECENT),
                             ("old", (NOW - timedelta(days=110)).isoformat())):
        company = make_company(db, f"{label}supply.com")
        pages = [page(f"https://{label}supply.com", DISTRIBUTOR_HOME),
                 page(f"https://{label}supply.com/news/suppliers", text,
                      published_at=published)]
        _, _, _, score = analyse(db, ps_config, company, pages)
        results[label] = score.raw_score
    assert results["recent"] > results["old"]


# ---------------------------------------------------------------------
# TEST 10 - AI hallucination prevention
# ---------------------------------------------------------------------
def test_10_general_growth_never_becomes_product_demand(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    growth = page("https://ridgelinesupply.com/news/record-year",
                  "Ridgeline had a record year, grew revenue and hired 30 new "
                  "team members across the business.", published_at=RECENT)
    _, _, interests, _ = analyse(db, ps_config, company,
                                 distributor_pages() + [growth])
    assert not [i for i in interests
                if i.interest_type in ("EXPLICITLY_SEEKING", "RECENTLY_ADDED")]
    assert product_interest.demand_summary(interests, ps_config) == NO_DEMAND


def test_10b_ungrounded_ai_product_claims_are_removed(ps_config):
    corpus = ("ridgeline had a record year, grew revenue and hired 30 new team "
              "members. wholesale distributor of atv parts.")
    analysis = AIAnalysis(
        likely_services=["UTV winches"],
        extra={"products_mentioned": ["LED light bars", "UTV winches"],
               "product_categories": ["Electrical and Performance"],
               "distribution_partnerships": ["Acme Lighting"]})
    grounded = ground_analysis(analysis, ps_config, corpus)
    assert grounded.likely_services == []
    assert grounded.extra["products_mentioned"] == []
    assert grounded.extra["product_categories"] == []
    assert grounded.extra["distribution_partnerships"] == []
    assert any("ungrounded" in gap for gap in grounded.evidence_gaps)


def test_10c_prompt_forbids_invented_products(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    prompt = _build_prompt(company, [], [], ps_config, [])
    assert NO_DEMAND in prompt or NO_DEMAND in ps_config.ai_system_prompt
    assert "products_mentioned" in prompt


# ---------------------------------------------------------------------
# TEST 11 - size verification
# ---------------------------------------------------------------------
def test_11_unknown_employee_count_is_not_fabricated(db, ps_config):
    company = make_company(db, "quietsupply.com")
    pages = [page("https://quietsupply.com", DISTRIBUTOR_HOME)]
    store_sources(db, company, pages)
    facts = profile.apply_profile(db, company, pages, ps_config.size_bands)
    assert company.employee_band is None
    assert company.size_confidence in (None, 0, 0.0)
    assert not [f for f in facts if f.fact_type == "employee_count"]


def test_11b_stated_size_keeps_confidence_and_source(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    pages = distributor_pages()
    store_sources(db, company, pages)
    profile.apply_profile(db, company, pages, ps_config.size_bands)
    assert company.employee_band == "mid_market"
    assert company.size_source_url == "https://ridgelinesupply.com/about-us"
    assert 0 < company.size_confidence <= 1
    fact = db.execute(select(CompanyFact).where(
        CompanyFact.company_id == company.id,
        CompanyFact.fact_type == "employee_count")).scalar_one()
    assert fact.value == "180"
    assert fact.source_url == company.size_source_url
    assert "180 employees" in fact.evidence


def test_11c_third_party_headcount_is_ignored(db, ps_config):
    company = make_company(db, "quietsupply.com")
    pages = [page("https://quietsupply.com", DISTRIBUTOR_HOME),
             page("https://someblog.example/news/quiet",
                  "Quiet Supply employs 300 people, sources say.",
                  page_type="news")]
    store_sources(db, company, pages)
    profile.apply_profile(db, company, pages, ps_config.size_bands)
    assert company.employee_band is None


# ---------------------------------------------------------------------
# TEST 12 - data provenance
# ---------------------------------------------------------------------
def test_12_every_signal_and_interest_has_a_valid_source(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    pages = distributor_pages() + [
        page("https://ridgelinesupply.com/news/utv",
             "Ridgeline is seeking quotes from manufacturers for UTV bumpers "
             "and roof racks.", published_at=RECENT),
        page("https://ridgelinesupply.com/brands",
             "Brands we carry: Trailcraft Racing helmets, Summit tires and "
             "LED light bars for ATV and UTV riders.")]
    analyse(db, ps_config, company, pages)

    sources = {s.id: s for s in db.execute(
        select(Source).where(Source.company_id == company.id)).scalars()}
    keyword_signals = db.execute(select(Signal).where(
        Signal.company_id == company.id)).scalars().all()
    assert keyword_signals
    for signal in keyword_signals:
        assert signal.source_id in sources, signal.signal_type
        assert signal.evidence
    rows = db.execute(select(ProductInterest).where(
        ProductInterest.company_id == company.id)).scalars().all()
    assert rows
    for row in rows:
        assert row.source_url and row.source_url.startswith("https://")
        assert row.source_id in sources
        assert sources[row.source_id].url == row.source_url
        assert row.interest_type in {"EXPLICITLY_SEEKING", "RECENTLY_ADDED",
                                     "CURRENTLY_CARRIED", "INFERRED_FIT"}


def test_12b_records_without_provenance_are_dropped(db, ps_config):
    company = make_company(db, "ridgelinesupply.com")
    record = product_interest.InterestRecord(
        interest_type="EXPLICITLY_SEEKING", category="Tires and Wheels",
        subcategory="Tires", products=["tires"], evidence="tires")
    saved = product_interest.persist_interests(db, company, ps_config, [record])
    assert saved == []


# ---------------------------------------------------------------------
# TEST 13 - no-email policy
# ---------------------------------------------------------------------
def test_13_no_email_anywhere_in_the_new_service(db, ps_config):
    from app.api.export import CSV_COLUMNS
    for column in CSV_COLUMNS:
        assert "mail" not in column.lower()
    for model in (CompanyFact, ProductInterest, Company):
        for column in model.__table__.columns:
            assert "mail" not in column.name.lower(), column.name
    assert "email" not in ps.CONFIG
    for name in ps.AI_EXTRA_FIELDS:
        assert "mail" not in name
    assert "never personal contact data" in ps.AI_EXTRA_FIELDS["likely_decision_roles"]


# ---------------------------------------------------------------------
# TEST 14 - configuration isolation
# ---------------------------------------------------------------------
def test_14_legacy_3pl_config_is_untouched(db, service, config, ps_service):
    from scripts.seed import SIGNALS as LEGACY_SIGNALS
    legacy = build_config(db, service)
    assert set(legacy.signals) == {s[0] for s in LEGACY_SIGNALS}
    assert not set(legacy.signals) & {s[0] for s in ps.SIGNALS}
    assert legacy.qualification == {}
    assert legacy.product_taxonomy == {}
    assert legacy.signal_dimensions == {}
    assert legacy.id != ps_service.id
    # the legacy hiring boost still finds its 3PL hiring signals
    assert "fulfillment_hiring" in legacy.hiring_signal_types


def test_14b_generic_engine_has_no_powersports_or_new_3pl_vocab():
    engine = Path(__file__).resolve().parent.parent / "app" / "engine"
    for name in ("product_interest.py", "profile.py", "scoring.py",
                 "ai_analysis.py", "service_config.py", "pipeline.py"):
        text = (engine / name).read_text(encoding="utf-8").lower()
        for term in ("powersports", "utv", "snowmobile", "polaris"):
            assert term not in text, f"{term!r} hardcoded in {name}"
    # modules added for this retarget carry no 3PL assumptions either
    for name in ("product_interest.py", "profile.py"):
        assert "3pl" not in (engine / name).read_text(encoding="utf-8").lower()


def test_14c_seeding_is_idempotent_and_keeps_3pl(db, service, ps_service):
    from scripts.seed import seed_service_module
    from app.models import ServiceKeyword
    before = db.query(ServiceKeyword).filter_by(service_id=ps_service.id).count()
    seed_service_module(db, ps, with_library=True)
    db.flush()
    after = db.query(ServiceKeyword).filter_by(service_id=ps_service.id).count()
    assert before == after
    db.refresh(service)
    assert service.status == "inactive"       # retained, not deleted
    assert db.query(ServiceKeyword).filter_by(service_id=service.id).count() > 0


# ---------------------------------------------------------------------
# TEST 15 - dashboard API and CSV
# ---------------------------------------------------------------------
@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    from app.db import get_db
    from app.main import app

    def _db():
        yield db
    app.dependency_overrides[get_db] = _db
    yield TestClient(app)        # no `with`: skip the startup schema check
    app.dependency_overrides.clear()


def _scored_lead(db, ps_config) -> Company:
    company = make_company(db, "ridgelinesupply.com", "Ridgeline Powersports Supply")
    pages = distributor_pages() + [page(
        "https://ridgelinesupply.com/news/utv",
        "Ridgeline is seeking quotes from manufacturers for UTV bumpers and "
        "roof racks for the Polaris RZR.", published_at=RECENT)]
    _, _, interests, score = analyse(db, ps_config, company, pages)
    scoring.upsert_opportunity(db, company, ps_config, score,
                               evidenced_needs=product_interest.buying_categories(interests))
    db.commit()
    return company


def test_15_api_returns_product_interest_fields(db, ps_config, client):
    company = _scored_lead(db, ps_config)
    listing = client.get(f"/api/services/{ps.SLUG}/opportunities").json()
    assert listing["total"] == 1
    lead = listing["items"][0]
    assert lead["company_type"] == "wholesale_distributor"
    assert lead["employee_band"] == "mid_market"
    assert lead["headquarters_state"] == "TX"
    assert "ATV/UTV/Side-by-Side Accessories" in lead["product_categories"]
    assert lead["product_demand_summary"] and lead["product_demand_summary"] != NO_DEMAND
    assert lead["latest_signal_type"]

    filtered = client.get(f"/api/services/{ps.SLUG}/opportunities",
                          params={"product_category": "Tires and Wheels"}).json()
    assert filtered["total"] == 0
    by_type = client.get(f"/api/services/{ps.SLUG}/opportunities",
                         params={"interest_type": "EXPLICITLY_SEEKING",
                                 "state": "TX"}).json()
    assert by_type["total"] == 1

    detail = client.get(f"/api/services/{ps.SLUG}/opportunities/{lead['id']}").json()
    types = {i["interest_type"] for i in detail["product_interests"]}
    assert "EXPLICITLY_SEEKING" in types
    assert all(i["source_url"] for i in detail["product_interests"])
    assert {f["fact_type"] for f in detail["company_facts"]} >= {"employee_count"}
    assert detail["signal_dimensions"].get("active_product_rfq", "intent") == "intent"
    assert detail["signal_dimensions"]["manufacturer_seeking_distribution"] == "negative"
    assert detail["company"]["id"] == company.id

    taxonomy = client.get(f"/api/services/{ps.SLUG}/taxonomy").json()
    assert "ATV/UTV/Side-by-Side Accessories" in taxonomy["product_taxonomy"]
    assert "wholesale_distributor" in taxonomy["company_types"]


def test_15b_csv_exports_product_interest_without_email(db, ps_config, client):
    _scored_lead(db, ps_config)
    response = client.get("/api/export", params={"service": ps.SLUG})
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    row = rows[0]
    assert not [h for h in row if "mail" in h.lower()]
    assert "ATV/UTV/Side-by-Side Accessories" in row["Explicitly Seeking"]
    assert row["Company Type"] == "wholesale_distributor"
    assert row["Employee Band"] == "mid_market"
    assert row["HQ State"] == "TX"
    assert "ridgelinesupply.com/news/utv" in row["Product Evidence URLs"]
    assert row["Product Demand Summary"]


def test_15c_dashboard_counts_only_this_services_companies(db, ps_config, client):
    """Companies are shared across services; the dashboard's company cards
    must not count legacy 3PL history."""
    _scored_lead(db, ps_config)                          # a powersports lead
    legacy = make_company(db, "old3plbrand.com")         # 3PL-era company
    legacy.discovered_via = "search:shopify skincare brands"
    legacy.status = "rejected"
    found = make_company(db, "newpartsdist.com")         # found by a ps query
    query = db.execute(select(DiscoveryQuery).where(
        DiscoveryQuery.service_id == ps_config.id)).scalars().first()
    found.discovered_via = f"search:{query.query}"
    db.commit()

    stats = client.get("/api/stats", params={"service": ps.SLUG}).json()
    assert stats["total_companies"] == 2
    assert stats["companies_rejected"] == 0
    assert stats["total_opportunities"] == 1


@pytest.mark.parametrize("headcount,qualifies", [
    ("180 employees", True),            # mid-market
    ("1,200 employees", False),         # large
    ("12 employees", False),            # small
])
def test_11d_only_mid_market_size_qualifies(db, ps_config, headcount, qualifies):
    from app.engine.pipeline import process_company
    company = make_company(db, "ridgelinesupply.com")
    pages = [page(p.url, p.text.replace("180 employees", headcount), p.title,
                  page_type=p.page_type) for p in distributor_pages()]
    store_sources(db, company, pages)
    company.status, company.last_crawled_at = "classified", datetime.now(timezone.utc)
    result = process_company(db, company, ps_config, skip_external=True,
                             allow_ai=False)
    assert result.rejected is not qualifies, result.reason
    if not qualifies:
        assert company.status == "rejected"
        assert "size" in company.rejection_reason


def test_11e_unknown_size_still_qualifies(db, ps_config):
    from app.engine.pipeline import process_company
    company = make_company(db, "ridgelinesupply.com")
    pages = [page(p.url, p.text.replace("of 180 employees ", ""), p.title,
                  page_type=p.page_type) for p in distributor_pages()]
    store_sources(db, company, pages)
    company.status, company.last_crawled_at = "classified", datetime.now(timezone.utc)
    result = process_company(db, company, ps_config, skip_external=True,
                             allow_ai=False)
    assert not result.rejected, result.reason
    assert company.employee_band in (None, "unknown")

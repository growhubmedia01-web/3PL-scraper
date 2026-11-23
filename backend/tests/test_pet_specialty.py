"""Pet Specialty Food, Treats & Supplements - required behaviour.

All page content is synthetic. It follows public real-world PATTERNS (a pet
distributor's become-a-vendor page; a distributor announcing it now carries
a bully-stick brand or a joint-support soft-chew brand; a supplement maker
naming a distribution partner; regulator and trade-publication pages) and
never hardcodes a production lead.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from app.engine import product_interest, profile, scoring
from app.engine.ai_analysis import _build_prompt
from app.engine.classifier import apply_classification, classify
from app.engine.extractor import ExtractedPage, classify_page_type
from app.engine.service_config import build_config
from app.engine.signals import detect_signals, persist_signals
from app.models import Company, Service, Source
from scripts.services import pet_specialty_food_treats_supplements as pet
from scripts.services import powersports_aftermarket_sourcing as ps

NOW = datetime.now(timezone.utc)
RECENT = (NOW - timedelta(days=10)).isoformat()
NO_DEMAND = "Specific product demand not publicly disclosed."
DOMAIN = "harborpetsupply.com"

DISTRIBUTOR_HOME = (
    "Harbor Pet Supply is a wholesale distributor of pet food, treats and "
    "pet supplements serving independent pet retailers across the United "
    "States. We distribute more than 300 brands of dog food, cat food, dog "
    "treats and natural chews from distribution centers in Ohio and Georgia. "
    "Trade only. Retailers can open a wholesale account online.")
DISTRIBUTOR_ABOUT = (
    "Founded in 1988, Harbor Pet Supply is headquartered in Columbus, Ohio. "
    "Our team of 220 employees supports more than 3,500 independent pet "
    "stores in 30 states. We are a pet specialty distributor focused on "
    "premium and natural pet nutrition.")


# ---------------------------------------------------------------------
# fixtures and helpers
# ---------------------------------------------------------------------
@pytest.fixture
def pet_service(db):
    from scripts.seed import seed_service_module
    svc = seed_service_module(db, pet, with_library=True)
    db.flush()
    return svc


@pytest.fixture
def pet_config(db, pet_service):
    return build_config(db, pet_service)


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
        db.add(Source(company_id=company.id, source_type=p.page_type,
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


def distributor_pages(domain: str = DOMAIN) -> list[ExtractedPage]:
    return [
        page(f"https://{domain}", DISTRIBUTOR_HOME,
             "Harbor Pet Supply | Pet Specialty Distributor"),
        page(f"https://{domain}/about-us", DISTRIBUTOR_ABOUT, "About Harbor"),
    ]


def by_type(interests, kind):
    return [i for i in interests if i.interest_type == kind]


# ---------------------------------------------------------------------
# TEST 1 - a US pet specialty distributor qualifies
# ---------------------------------------------------------------------
def test_01_us_pet_specialty_distributor_qualifies(db, pet_config):
    company = make_company(db, DOMAIN)
    result, signals, _, _ = analyse(db, pet_config, company, distributor_pages())

    assert result.relevant, result.rejection_reason
    assert result.company_type == "pet_specialty_distributor"
    assert result.country == "US"
    assert result.industry == "pet"
    assert company.employee_band == "mid_market"
    # fit, not buying intent
    assert "pet_specialty_participation" in signals
    assert "b2b_retailer_distribution" in signals


# ---------------------------------------------------------------------
# TEST 2 - become-a-vendor page (pattern: a regional pet distributor's
# vendor-onboarding page) is evergreen openness, not product demand
# ---------------------------------------------------------------------
def test_02_vendor_application_is_onboarding_not_demand(db, pet_config):
    company = make_company(db, DOMAIN)
    vendor = page(
        f"https://{DOMAIN}/info/become-a-vendor",
        "Become a vendor. Brands interested in becoming a vendor can complete "
        "our new vendor application. Prospective vendors should submit your "
        "product information and our purchasing team will review it.",
        "Become a Vendor")
    assert vendor.page_type == "supplier"
    _, signals, interests, score = analyse(
        db, pet_config, company, distributor_pages() + [vendor])

    assert "supplier_application_open" in signals
    assert not by_type(interests, "EXPLICITLY_SEEKING")
    assert pet_config.signals["supplier_application_open"].weight == 20
    assert score.intent_level != "HOT"


# ---------------------------------------------------------------------
# TEST 3 - an explicit category request becomes EXPLICITLY_SEEKING
# ---------------------------------------------------------------------
def test_03_explicit_category_request_extracts_products(db, pet_config):
    company = make_company(db, DOMAIN)
    url = f"https://{DOMAIN}/news/2026-sourcing"
    pages = distributor_pages() + [page(
        url,
        "Harbor Pet Supply is currently seeking new suppliers of freeze-dried "
        "dog treats, bully sticks and dog joint supplement soft chews for our "
        "independent retailers.", "We are looking for new brands",
        published_at=RECENT)]
    _, signals, interests, _ = analyse(db, pet_config, company, pages)

    assert {"active_supplier_request", "active_product_category_request"} & set(signals)
    seeking = by_type(interests, "EXPLICITLY_SEEKING")
    assert seeking
    subs = {i.subcategory for i in seeking}
    assert {"Freeze-Dried Treats", "Bully Sticks"} <= subs
    for record in seeking:
        assert record.source_url == url and record.source_id is not None
        assert "Dog" in record.vehicle_segments            # species


# ---------------------------------------------------------------------
# TEST 4 - distributor now carries a bully-stick brand (pattern: a pet
# distributor announcing a natural-chew brand)
# ---------------------------------------------------------------------
def test_04_new_chew_brand_is_recently_onboarded(db, pet_config):
    company = make_company(db, DOMAIN)
    pages = distributor_pages() + [page(
        f"https://{DOMAIN}/news/stixwell",
        "Harbor Pet Supply has signed an exclusive distribution agreement with "
        "Stixwell Chews to distribute its bully sticks and natural chews to "
        "independent pet retailers.", "Harbor adds Stixwell Chews",
        published_at=RECENT)]
    _, signals, interests, score = analyse(db, pet_config, company, pages)

    assert "new_supplier_partnership" in signals
    line = next(l for l in score.breakdown
                if l.signal_type == "new_supplier_partnership")
    assert line.weight == 27
    added = by_type(interests, "RECENTLY_ADDED")
    assert any(i.subcategory == "Bully Sticks" for i in added)
    assert any(i.brand and "Stixwell" in i.brand for i in added)


# ---------------------------------------------------------------------
# TEST 5 - supplement brand onboarded (pattern: a joint-support soft-chew
# brand "now available through" a distributor); format and claims recorded
# as STATED, never as verified
# ---------------------------------------------------------------------
def test_05_supplement_expansion_records_format_and_stated_claims(db, pet_config):
    company = make_company(db, DOMAIN)
    pages = distributor_pages() + [page(
        f"https://{DOMAIN}/news/supplements",
        "Harbor Pet Supply expands its supplement portfolio: Joynt Labs hip and "
        "joint soft chews for dogs, which the brand says supports joint "
        "health, are now available through Harbor to independent retailers.",
        "Harbor expands supplements", published_at=RECENT)]
    _, signals, interests, _ = analyse(db, pet_config, company, pages)

    assert "supplement_category_expansion" in signals
    added = by_type(interests, "RECENTLY_ADDED")
    joint = [i for i in added if i.subcategory == "Hip and Joint Supplements"]
    assert joint
    attrs = joint[0].attributes
    assert "Soft chews" in attrs.get("format", [])
    claims = attrs.get("stated_health_claims", [])
    assert claims and all("company claim" in c for c in claims)
    for c in claims:
        assert "fda" not in c.lower() and "treat" not in c.lower()


# ---------------------------------------------------------------------
# TEST 6 - category expansions route to the right category signal
# ---------------------------------------------------------------------
def test_06_treat_expansion_is_not_a_food_expansion(db, pet_config):
    company = make_company(db, DOMAIN)
    pages = distributor_pages() + [page(
        f"https://{DOMAIN}/news/treats",
        "Harbor expanded its treats and chews assortment with single-ingredient "
        "jerky and dental chews.", "Treat expansion", published_at=RECENT)]
    _, signals, _, _ = analyse(db, pet_config, company, pages)
    assert "treats_category_expansion" in signals
    assert "supplement_category_expansion" not in signals


# ---------------------------------------------------------------------
# TEST 7 - a retailer wholesale-account application is the distributor
# SELLING, never supplier onboarding
# ---------------------------------------------------------------------
def test_07_retailer_wholesale_account_page_is_not_supplier_onboarding(db, pet_config):
    company = make_company(db, DOMAIN)
    retail = page(
        f"https://{DOMAIN}/wholesale-account",
        "Open a wholesale account. Independent pet retailers can apply for a "
        "wholesale account and submit your application today. We are accepting "
        "new retailer accounts and looking for new retailers.",
        "Retailer Application", published_at=RECENT)
    assert retail.page_type == "dealer"
    _, signals, interests, _ = analyse(db, pet_config, company,
                                       distributor_pages() + [retail])
    for positive in ("supplier_application_open", "active_supplier_request",
                     "active_product_category_request", "active_product_rfq"):
        assert positive not in signals, positive
    assert not by_type(interests, "EXPLICITLY_SEEKING")


# ---------------------------------------------------------------------
# TEST 8 - a brand seeking distributors is the opposite direction (pattern:
# a supplement maker announcing it wants distribution partners)
# ---------------------------------------------------------------------
def test_08_brand_seeking_distribution_is_not_a_buyer(db, pet_config):
    company = make_company(db, "vitapawlabs.com")
    pages = [
        page("https://vitapawlabs.com",
             "VitaPaw Labs makes dog supplements and calming chews in our "
             "manufacturing facility. We manufacture every chew in-house. Find a "
             "retailer near you or shop now.", "VitaPaw Labs"),
        page("https://vitapawlabs.com/news/distribution",
             "We are looking for distributors and seeking a distributor for our "
             "pet supplements. Distributor inquiries welcome.",
             "Distributors wanted", published_at=RECENT),
    ]
    result, signals, interests, score = analyse(db, pet_config, company, pages)

    assert not result.relevant
    assert result.company_type in {"manufacturer", "brand_owner"}
    assert "brand_seeking_distribution" in signals
    for positive in ("active_supplier_request", "supplier_application_open",
                     "active_product_rfq"):
        assert positive not in signals
    assert not by_type(interests, "EXPLICITLY_SEEKING")
    neg = next(l for l in score.breakdown
               if l.signal_type == "brand_seeking_distribution")
    assert neg.points < 0


# ---------------------------------------------------------------------
# TEST 9 - retail stores, vet clinics and pet services are not targets
# ---------------------------------------------------------------------
@pytest.mark.parametrize("domain,text", [
    ("happytailspets.com", "Happy Tails is a locally owned pet store and pet "
     "boutique. Visit our store for dog food and cat treats. Store hours 9-6, "
     "curbside pickup and a self-serve dog wash."),
    ("oakvet.com", "Oak Veterinary Clinic is a full-service animal hospital. "
     "Schedule an appointment for wellness exams; our veterinarians also "
     "stock pet food and supplements."),
    ("pawspa.com", "Paw Spa offers dog grooming, boarding and daycare, and "
     "doggy daycare. Book a grooming appointment. We also sell dog treats."),
])
def test_09_retail_clinic_and_service_businesses_are_rejected(db, pet_config, domain, text):
    company = make_company(db, domain)
    result = classify(company, [
        page(f"https://{domain}", text, domain),
        page(f"https://{domain}/contact", "12 Main St, Austin, TX 78701"),
    ], pet_config.excluded_business_types, config=pet_config)
    assert not result.relevant, (result.company_type, result.rejection_reason)


# ---------------------------------------------------------------------
# TEST 10 - geography: US only; no address on a .com is a flagged lead
# ---------------------------------------------------------------------
def test_10_us_only_and_unverified_location_is_flagged(db, pet_config):
    foreign = make_company(db, "petwholesale.ca")
    result = classify(foreign, [
        page("https://petwholesale.ca", DISTRIBUTOR_HOME.replace(
            "United States", "Canada"), "Pet Wholesale"),
        page("https://petwholesale.ca/contact", "Toronto, ON M5V 2T6"),
    ], pet_config.excluded_business_types, config=pet_config)
    assert not result.relevant
    assert "geography (US)" in result.rejection_reason

    unknown = make_company(db, "petlinewholesale.com")
    home = DISTRIBUTOR_HOME.replace(" across the United States", "").replace(
        " in Ohio and Georgia", "")
    result = classify(unknown, [
        page("https://petlinewholesale.com", home, "Petline Wholesale"),
        page("https://petlinewholesale.com/contact", "Call our sales team."),
    ], pet_config.excluded_business_types, config=pet_config)
    assert result.relevant, result.rejection_reason
    assert any(e.startswith("UNVERIFIED") for e in result.evidence["country"])


# ---------------------------------------------------------------------
# TEST 11 - mid-market only; size never makes a lead HOT
# ---------------------------------------------------------------------
@pytest.mark.parametrize("headcount,qualifies", [
    ("220 employees", True),
    ("2,400 employees", False),
    ("14 employees", False),
])
def test_11_only_mid_market_size_qualifies(db, pet_config, headcount, qualifies):
    from app.engine.pipeline import process_company
    company = make_company(db, DOMAIN)
    pages = [page(p.url, p.text.replace("220 employees", headcount), p.title,
                  page_type=p.page_type) for p in distributor_pages()]
    store_sources(db, company, pages)
    company.status, company.last_crawled_at = "classified", NOW
    result = process_company(db, company, pet_config, skip_external=True,
                             allow_ai=False)
    assert result.rejected is not qualifies, result.reason
    if not qualifies:
        assert "size" in company.rejection_reason


def test_11b_fit_alone_never_reaches_hot(db, pet_config):
    company = make_company(db, DOMAIN)
    _, _, _, score = analyse(db, pet_config, company, distributor_pages())
    assert score.intent_level in {"LOW", "POSSIBLE"}


# ---------------------------------------------------------------------
# TEST 12 - purchasing hiring is a capability signal, never product demand
# ---------------------------------------------------------------------
def test_12_category_manager_hiring_counts_only_on_careers_pages(db, pet_config):
    company = make_company(db, DOMAIN)
    pages = distributor_pages() + [page(
        f"https://{DOMAIN}/careers",
        "We are hiring a Category Manager for pet supplements and a Senior "
        "Buyer for dog treats.", "Careers", published_at=RECENT)]
    _, signals, interests, _ = analyse(db, pet_config, company, pages)
    assert "category_manager_hiring" in signals
    assert "purchasing_manager_hiring" in signals
    assert not by_type(interests, "EXPLICITLY_SEEKING")


# ---------------------------------------------------------------------
# TEST 13 - general growth is never turned into product demand
# ---------------------------------------------------------------------
def test_13_growth_without_products_shows_no_demand_message(db, pet_config):
    company = make_company(db, DOMAIN)
    pages = distributor_pages() + [page(
        f"https://{DOMAIN}/news/dc",
        "Harbor Pet Supply opened a new distribution center in Tennessee to "
        "serve more pet retailers.", "New DC", published_at=RECENT)]
    _, signals, interests, _ = analyse(db, pet_config, company, pages)
    assert "distribution_center_expansion" in signals
    assert not by_type(interests, "EXPLICITLY_SEEKING")
    assert not by_type(interests, "RECENTLY_ADDED")
    assert pet_config.raw_config["no_product_demand_message"] == NO_DEMAND


# ---------------------------------------------------------------------
# TEST 14 - regulatory safeguards: no drugs in the taxonomy, claims are
# stated, the AI is told never to upgrade marketing into medicine
# ---------------------------------------------------------------------
def test_14_taxonomy_and_prompt_keep_regulatory_safeguards(db, pet_config):
    terms = " ".join(t for subs in pet.PRODUCT_TAXONOMY.values()
                     for ts in subs.values() for t in ts).lower()
    for banned in ("flea", "tick", "prescription", "rx", "heartworm", "dewormer"):
        assert banned not in terms.split() and f" {banned} " not in f" {terms} "
    for group in ("stated_certifications_and_claims", "stated_health_claims"):
        for label in pet.PRODUCT_ATTRIBUTES[group]:
            assert "stated" in label or "company claim" in label
    system = pet_config.ai_system_prompt.lower()       # sent as the system prompt
    assert "fda-approved" in system and "marketing claims" in system
    assert "commercial direction" in system
    company = make_company(db, DOMAIN)
    task = str(_build_prompt(company, [], [], pet_config))
    assert NO_DEMAND in task


# ---------------------------------------------------------------------
# TEST 15 - regulators, trade publications and marketplaces are evidence
# sources, never prospects
# ---------------------------------------------------------------------
def test_15_regulators_and_trade_press_are_never_prospects(pet_config):
    blocked = set(pet.DISCOVERY_BLOCKED_DOMAINS)
    assert {"fda.gov", "aafco.org", "petfoodprocessing.net",
            "petfoodindustry.com", "petbusiness.com", "petage.com",
            "globalpetexpo.org", "superzoo.org", "petfoodforum.com",
            "chewy.com", "amazon.com"} <= blocked
    assert "linkedin.com" in blocked


# ---------------------------------------------------------------------
# TEST 16 - the query library is small, tiered and parser-safe
# ---------------------------------------------------------------------
def test_16_query_library_is_small_and_tiered():
    library = pet.build_library()
    stats = pet.stats(library)
    assert 150 <= stats["total"] <= 300
    assert set(stats["by_tier"]) == {1, 2, 3, 4}
    assert all("(" not in q.text and ")" not in q.text for q in library)
    assert all(q.country == "US" for q in library)
    assert len({q.text.lower() for q in library}) == len(library)


# ---------------------------------------------------------------------
# TEST 17 - powersports and 3PL are preserved
# ---------------------------------------------------------------------
def test_17_seeding_pet_keeps_powersports_and_3pl(db, service, pet_service):
    from scripts.seed import seed_service_module
    ps_svc = seed_service_module(db, ps, with_library=False)
    db.flush()
    seed_service_module(db, pet, with_library=False)     # idempotent re-run
    db.flush()
    db.refresh(ps_svc)
    db.refresh(service)
    assert ps_svc.status == "active"
    assert ps_svc.config["qualification"]["required_industry"] == "powersports"
    assert service.status == "inactive"                    # retained
    assert not set(build_config(db, ps_svc).signals) & {
        "active_supplier_request", "pet_specialty_participation"}
    assert db.query(Service).filter_by(slug=pet.SLUG).count() == 1


# ---------------------------------------------------------------------
# TEST 18 - dashboard labels and CSV: species, attributes, no email
# ---------------------------------------------------------------------
@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient
    from app.db import get_db
    from app.main import app

    def _db():
        yield db
    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_18_api_labels_and_csv_export(db, pet_config, client):
    company = make_company(db, DOMAIN, "Harbor Pet Supply")
    pages = distributor_pages() + [page(
        f"https://{DOMAIN}/news/supplements",
        "Harbor Pet Supply expands its supplement portfolio: Joynt Labs hip and "
        "joint soft chews for dogs are now available through Harbor.",
        published_at=RECENT)]
    _, _, interests, score = analyse(db, pet_config, company, pages)
    scoring.upsert_opportunity(db, company, pet_config, score,
                               evidenced_needs=product_interest.buying_categories(interests))
    db.commit()

    taxonomy = client.get(f"/api/services/{pet.SLUG}/taxonomy").json()
    labels = taxonomy["ui_labels"]
    assert labels["segment"] == "Species"
    assert labels["interest_types"]["RECENTLY_ADDED"] == "Recently onboarded"
    assert labels["interest_types"]["INFERRED_FIT"] == "Inferred category fit"
    assert "Dog" in taxonomy["vehicle_segments"]
    assert "Pet Supplements" in taxonomy["product_taxonomy"]

    listing = client.get(f"/api/services/{pet.SLUG}/opportunities").json()
    lead = listing["items"][0]
    detail = client.get(f"/api/services/{pet.SLUG}/opportunities/{lead['id']}").json()
    assert any(i.get("attributes") for i in detail["product_interests"])

    response = client.get("/api/export", params={"service": pet.SLUG})
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    row = rows[0]
    assert not [h for h in row if "mail" in h.lower()]
    assert "Dog" in row["Vehicle Segments"]
    assert "Soft chews" in row["Product Attributes"]
    assert "Pet Supplements" in row["Recently Added"]


# ---------------------------------------------------------------------
# TEST 19 - the shared crawl queue hands each company to the service whose
# query found it, so one service never judges another's companies
# ---------------------------------------------------------------------
def test_19_queue_is_scoped_to_the_discovering_service(db, pet_service):
    from scripts.seed import seed_service_module
    from app.engine.discovery import queued_companies
    from app.models import DiscoveryQuery
    ps_svc = seed_service_module(db, ps, with_library=True)
    db.flush()

    def query_of(svc):
        return db.query(DiscoveryQuery).filter_by(service_id=svc.id).first().query

    pet_co = make_company(db, "petco-found.com")
    pet_co.discovered_via = f"search:{query_of(pet_service)}"
    ps_co = make_company(db, "ps-found.com")
    ps_co.discovered_via = f"search:{query_of(ps_svc)}"
    manual = make_company(db, "manual-add.com")
    manual.discovered_via = "manual"
    for c in (pet_co, ps_co, manual):
        c.status = "queued"
    db.flush()

    pet_q = {c.domain for c in queued_companies(db, 50, service_id=pet_service.id)}
    ps_q = {c.domain for c in queued_companies(db, 50, service_id=ps_svc.id)}
    assert pet_q == {"petco-found.com", "manual-add.com"}
    assert ps_q == {"ps-found.com", "manual-add.com"}
    assert len(queued_companies(db, 50)) == 3          # unscoped: unchanged


# ---------------------------------------------------------------------
# TEST 20 - lookalikes seen in the first live run: software for brands,
# direct-to-consumer brands and a UK brand on a .com are not distributors
# ---------------------------------------------------------------------
@pytest.mark.parametrize("domain,home,contact,expected_type", [
    ("wholesalefinder.com",
     "Find the buyers who will stock your product. Reach independent pet "
     "retailers and wholesale distributors. Book a demo or start your free "
     "trial, then go to dashboard.", "Email our team.", "software_or_service_vendor"),
    ("purrlitter.com",
     "Premium natural pet supplies and cat food. Orders ship within 1 business "
     "day. Free shipping on orders over $50. Shop all. Add to cart. Our story.",
     "Questions? Email us.", "brand_owner"),
])
def test_20_software_and_dtc_brands_are_not_distributors(
        db, pet_config, domain, home, contact, expected_type):
    company = make_company(db, domain)
    result = classify(company, [page(f"https://{domain}", home, domain),
                                page(f"https://{domain}/contact", contact)],
                      pet_config.excluded_business_types, config=pet_config)
    assert result.company_type == expected_type
    assert not result.relevant


def test_20b_uk_region_is_foreign_evidence(db, pet_config):
    company = make_company(db, "moorlandrawfood.com")
    result = classify(company, [page(
        "https://moorlandrawfood.com",
        "Premium raw dog food, made in Yorkshire. Pet food for dogs and cats.",
        "Moorland Raw")], pet_config.excluded_business_types, config=pet_config)
    assert result.country == "GB"
    assert not result.relevant


# ---------------------------------------------------------------------
# TEST 21 - a lead whose company is later re-analysed and rejected leaves
# the lead list, the stats and the CSV (the row itself is kept)
# ---------------------------------------------------------------------
def test_21_later_rejected_company_is_not_listed(db, pet_config, client):
    from app.models import ServiceOpportunity
    company = make_company(db, DOMAIN, "Harbor Pet Supply")
    _, _, interests, score = analyse(db, pet_config, company, distributor_pages())
    scoring.upsert_opportunity(db, company, pet_config, score,
                               evidenced_needs=product_interest.buying_categories(interests))
    db.commit()
    assert client.get(f"/api/services/{pet.SLUG}/opportunities").json()["total"] == 1

    company.status, company.rejection_reason = "rejected", "brand, not a distributor"
    db.commit()
    assert client.get(f"/api/services/{pet.SLUG}/opportunities").json()["total"] == 0
    assert client.get("/api/stats", params={"service": pet.SLUG}).json()["total_opportunities"] == 0
    rows = list(csv.DictReader(io.StringIO(
        client.get("/api/export", params={"service": pet.SLUG}).text)))
    assert rows == []
    assert db.query(ServiceOpportunity).filter_by(company_id=company.id).count() == 1


def test_20c_b2b_sourcing_marketplace_is_not_a_distributor(db, pet_config):
    company = make_company(db, "sourcevn.com")
    result = classify(company, [page(
        "https://sourcevn.com",
        "Verified suppliers and B2B sourcing platform. Pet treats, dog chews "
        "and pet products from all suppliers. Low MOQ. Live requests. Become a "
        "supplier.", "Source VN")], pet_config.excluded_business_types,
        config=pet_config)
    assert result.company_type == "b2b_marketplace"
    assert not result.relevant


# ---------------------------------------------------------------------
# TEST 22 - external search never stores social-network results such as
# personal LinkedIn profiles
# ---------------------------------------------------------------------
def test_22_external_search_skips_social_profiles(db, monkeypatch):
    from types import SimpleNamespace
    from app.engine import evidence
    company = make_company(db, DOMAIN, "Harbor Pet Supply")

    class FakeSearch:
        has_provider = True

        def search(self, *a, **k):
            return [
                SimpleNamespace(url="https://www.linkedin.com/in/jane-doe",
                                title="Harbor Pet Supply - Jane Doe",
                                snippet="Harbor Pet Supply buyer", published_at=None),
                SimpleNamespace(url="https://petbiznews.com/harbor-adds-brand",
                                title="Harbor Pet Supply adds brand",
                                snippet="Harbor Pet Supply now distributes", published_at=None),
            ]
    monkeypatch.setattr(evidence, "SearchService", lambda *a, **k: FakeSearch())
    found = evidence.search_external_signals(db, company)
    urls = {e.url for e in found}
    assert "https://petbiznews.com/harbor-adds-brand" in urls
    assert not [u for u in urls if "linkedin.com" in u]
    assert evidence.is_social_network_url("https://uk.linkedin.com/in/x")
    assert not evidence.is_social_network_url("https://harborpetsupply.com")


# ---------------------------------------------------------------------
# TEST 23 - a pet brand's own wholesale page is not distributor evidence;
# a distributor's brand application is (patterns from the live run)
# ---------------------------------------------------------------------
def test_23_brand_wholesale_page_does_not_make_a_distributor(db, pet_config):
    company = make_company(db, "happysnoutchews.com")
    result = classify(company, [
        page("https://happysnoutchews.com",
             "Happy Snout makes single-ingredient dog chews. Shop all chews.",
             "Happy Snout"),
        page("https://happysnoutchews.com/wholesale",
             "Wholesale program for independent pet retailers and retail "
             "partners. B2B ordering. Become a retailer and open a wholesale "
             "account today.", "Wholesale"),
        page("https://happysnoutchews.com/contact", "500 Pine St, Denver, CO 80202"),
    ], pet_config.excluded_business_types, config=pet_config)
    assert result.company_type != "pet_specialty_distributor"
    assert not result.relevant


def test_23b_distributor_with_brand_application_qualifies(db, pet_config):
    company = make_company(db, "naturalpetdist.com")
    pages = [
        page("https://naturalpetdist.com",
             "Natural Pet Distribution has four outside sales representatives, "
             "each covering an area of our territory footprint, well educated on "
             "the natural products we carry.", "Natural Pet Distribution"),
        page("https://naturalpetdist.com/about-us",
             "Founded in 1981, we service independent pet retailers and only "
             "the independent pet specialty segment. Columbus, OH 43215.", "About"),
        page("https://naturalpetdist.com/brand-application",
             "Brand Application. Brands interested in distribution can complete "
             "our new brand application for our purchasing team.",
             "Brand Application", page_type="supplier"),
    ]
    result, signals, interests, _ = analyse(db, pet_config, company, pages)
    assert result.relevant, result.rejection_reason
    assert result.company_type == "pet_specialty_distributor"
    assert "supplier_application_open" in signals
    assert not by_type(interests, "EXPLICITLY_SEEKING")


def test_23c_distributor_self_description_qualifies(db, pet_config):
    """Patterns from the live run: a regional and a full-line distributor
    that describe themselves without any line-card or brand wording."""
    company = make_company(db, "lakesidepetsupply.com")
    result = classify(company, [
        page("https://lakesidepetsupply.com",
             "We are a family-owned regional pet supply distributor and a "
             "full-line wholesale pet supply distributor serving independent "
             "retailers with pet food and treats.", "Lakeside Pet Supply"),
        page("https://lakesidepetsupply.com/contact", "12 Lake Rd, Erie, PA 16501"),
    ], pet_config.excluded_business_types, config=pet_config)
    assert result.company_type == "pet_specialty_distributor"
    assert result.relevant, result.rejection_reason

"""Seed the database from the SQL migration files.

Usage (from backend/):
    python -m scripts.seed              # create schema + seed 3PL
    python -m scripts.seed --local      # use the local SQLite fallback
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal, engine, init_local_schema  # noqa: E402
from app.models import (  # noqa: E402
    DiscoveryQuery, Service, ServiceKeyword, ServiceRole, ServiceSignal,
)
from scripts.query_library import (  # noqa: E402
    EXCLUDED_BUSINESS_TYPES, QUERY_EXCLUSION_TERMS, build_library,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("seed")

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

# Mirrors 003_seed_3pl.sql. Kept here so SQLite/dev seeding works without psql.
SIGNALS = [
    ("ecommerce", "Ecommerce", "Sells online via a storefront platform or cart/checkout flow", 8, None, 1),
    ("physical_products", "Physical Products", "Ships tangible goods with SKUs, inventory and returns", 10, None, 1),
    ("new_store", "New Store", "Recently launched online store", 10, 365, 1),
    ("international_shipping", "International Shipping", "States it ships beyond its home market", 8, None, 1),
    ("international_expansion", "International Expansion", "Announced entry into a new geographic market", 15, 270, 2),
    ("recent_funding", "Recent Funding", "Raised capital recently; growth pressure on operations", 12, 540, 2),
    ("product_launch", "Product Launch", "New product line, major launch or pre-orders", 10, 180, 3),
    ("operations_hiring", "Operations Hiring", "Hiring ops/supply chain/logistics roles", 15, 120, 3),
    ("fulfillment_hiring", "Fulfillment Hiring", "Hiring fulfillment/warehouse/distribution roles", 20, 120, 3),
    ("crowdfunding", "Crowdfunding", "Running or recently funded a crowdfunding campaign", 15, 365, 1),
    ("rapid_growth", "Rapid Growth", "Public evidence of fast growth in orders/headcount/revenue", 10, 270, 1),
    ("existing_3pl", "Existing 3PL", "Already works with a fulfillment provider", -20, None, 1),
    ("seeking_3pl", "Actively Seeking 3PL", "Publicly looking for a fulfillment partner - the strongest possible signal", 25, 180, 1),
    ("capacity_strain", "Capacity Strain", "Outgrowing current space, backorders, or shipping delays", 20, 180, 2),
    ("subscription_model", "Subscription Model", "Recurring shipments - predictable, high-volume fulfillment", 15, None, 1),
    ("warehouse_move", "Warehouse Move", "Relocating to or opening a larger facility", 15, 270, 1),
    ("wholesale_b2b", "Wholesale / B2B", "Sells wholesale or trade with minimum order quantities", 12, None, 1),
    ("marketplace_seller", "Marketplace Seller", "Sells on Amazon, eBay, Etsy or similar - multi-channel fulfillment", 12, None, 1),
    ("retail_distribution", "Retail Distribution", "Stocked by physical retailers; needs retail-compliant fulfillment", 12, None, 1),
    ("importer_exporter", "Importer / Exporter", "Imports goods; container handling and customs needs", 12, None, 1),
    ("multi_channel", "Multi-Channel", "Sells through three or more channels", 10, None, 1),
    ("peak_season", "Peak Season Pressure", "Seasonal volume spikes needing flexible capacity", 10, 150, 1),
    ("manufacturer", "Manufacturer", "Produces its own goods and holds finished inventory", 8, None, 1),
]

KEYWORDS = [
    ("3pl", "logistics", "existing_3pl", 1.0),
    ("third party logistics", "logistics", "existing_3pl", 1.0),
    ("fulfillment partner", "logistics", "existing_3pl", 1.0),
    ("fulfilment partner", "logistics", "existing_3pl", 1.0),
    ("warehouse partner", "logistics", "existing_3pl", 1.0),
    ("fulfilled by", "logistics", "existing_3pl", 0.8),
    ("shipbob", "logistics", "existing_3pl", 1.0),
    ("shipmonk", "logistics", "existing_3pl", 1.0),
    ("deliverr", "logistics", "existing_3pl", 1.0),
    ("huboo", "logistics", "existing_3pl", 1.0),
    ("fulfillment by amazon", "logistics", "existing_3pl", 0.9),
    ("fulfillment", "logistics", None, 0.6),
    ("warehouse", "logistics", None, 0.6),
    ("warehousing", "logistics", None, 0.6),
    ("distribution center", "logistics", None, 0.7),
    ("distribution centre", "logistics", None, 0.7),
    ("fulfillment center", "logistics", None, 0.7),
    ("pick and pack", "logistics", None, 0.8),
    ("order fulfillment", "logistics", None, 0.8),
    ("reverse logistics", "logistics", None, 0.8),
    ("inventory", "logistics", None, 0.4),
    ("sku", "physical", "physical_products", 0.8),
    ("in stock", "physical", "physical_products", 0.6),
    ("out of stock", "physical", "physical_products", 0.7),
    ("free shipping", "physical", "physical_products", 0.7),
    ("shipping policy", "physical", "physical_products", 0.8),
    ("delivery times", "physical", "physical_products", 0.6),
    ("return policy", "physical", "physical_products", 0.7),
    ("returns", "physical", "physical_products", 0.5),
    ("dispatch", "physical", "physical_products", 0.6),
    ("tracking number", "physical", "physical_products", 0.7),
    ("add to cart", "ecommerce", "ecommerce", 1.0),
    ("add to bag", "ecommerce", "ecommerce", 1.0),
    ("checkout", "ecommerce", "ecommerce", 0.8),
    ("shopping cart", "ecommerce", "ecommerce", 0.9),
    ("shop now", "ecommerce", "ecommerce", 0.6),
    ("my account", "ecommerce", "ecommerce", 0.4),
    ("ships worldwide", "international", "international_shipping", 1.0),
    ("ship worldwide", "international", "international_shipping", 1.0),
    ("we ship worldwide", "international", "international_shipping", 1.0),
    ("ship internationally", "international", "international_shipping", 1.0),
    ("shipping worldwide", "international", "international_shipping", 1.0),
    ("worldwide shipping", "international", "international_shipping", 1.0),
    ("international shipping", "international", "international_shipping", 1.0),
    ("we ship internationally", "international", "international_shipping", 1.0),
    ("ships to usa", "international", "international_shipping", 0.9),
    ("ships to europe", "international", "international_shipping", 0.9),
    ("global shipping", "international", "international_shipping", 0.9),
    ("customs and duties", "international", "international_shipping", 0.8),
    ("launching in the us", "international", "international_expansion", 1.0),
    ("now available in the us", "international", "international_expansion", 1.0),
    ("expanding into", "international", "international_expansion", 1.0),
    ("entering the us market", "international", "international_expansion", 1.0),
    ("opening our first us", "international", "international_expansion", 1.0),
    ("new market", "international", "international_expansion", 0.6),
    ("operations manager", "hiring", "operations_hiring", 1.0),
    ("head of operations", "hiring", "operations_hiring", 1.0),
    ("supply chain manager", "hiring", "operations_hiring", 1.0),
    ("logistics manager", "hiring", "operations_hiring", 1.0),
    ("logistics coordinator", "hiring", "operations_hiring", 0.8),
    ("inventory manager", "hiring", "operations_hiring", 0.9),
    ("vp operations", "hiring", "operations_hiring", 1.0),
    ("fulfillment manager", "hiring", "fulfillment_hiring", 1.0),
    ("warehouse manager", "hiring", "fulfillment_hiring", 1.0),
    ("warehouse associate", "hiring", "fulfillment_hiring", 0.8),
    ("fulfillment operations", "hiring", "fulfillment_hiring", 1.0),
    ("distribution manager", "hiring", "fulfillment_hiring", 1.0),
    ("warehouse operative", "hiring", "fulfillment_hiring", 0.8),
    ("raised", "funding", "recent_funding", 0.6),
    ("seed round", "funding", "recent_funding", 1.0),
    ("series a", "funding", "recent_funding", 1.0),
    ("series b", "funding", "recent_funding", 1.0),
    ("pre-seed", "funding", "recent_funding", 0.9),
    ("funding round", "funding", "recent_funding", 1.0),
    ("secures investment", "funding", "recent_funding", 0.9),
    ("kickstarter", "crowdfunding", "crowdfunding", 1.0),
    ("indiegogo", "crowdfunding", "crowdfunding", 1.0),
    ("backers", "crowdfunding", "crowdfunding", 0.8),
    ("crowdfunding campaign", "crowdfunding", "crowdfunding", 1.0),
    ("pre-order", "launch", "product_launch", 0.8),
    ("preorder", "launch", "product_launch", 0.8),
    ("new collection", "launch", "product_launch", 0.7),
    ("now launching", "launch", "product_launch", 0.7),
    ("introducing our new", "launch", "product_launch", 0.7),
    ("looking for a 3pl", "intent", "seeking_3pl", 1.0),
    ("looking for a fulfillment partner", "intent", "seeking_3pl", 1.0),
    ("seeking fulfillment partner", "intent", "seeking_3pl", 1.0),
    ("request for quote fulfillment", "intent", "seeking_3pl", 1.0),
    ("fulfillment rfp", "intent", "seeking_3pl", 1.0),
    ("outsourcing our fulfillment", "intent", "seeking_3pl", 1.0),
    ("outsource fulfilment", "intent", "seeking_3pl", 1.0),
    ("third party logistics provider", "intent", "seeking_3pl", 0.9),
    ("outgrowing our warehouse", "capacity", "capacity_strain", 1.0),
    ("running out of warehouse space", "capacity", "capacity_strain", 1.0),
    ("outgrown our current space", "capacity", "capacity_strain", 1.0),
    ("at capacity", "capacity", "capacity_strain", 0.7),
    ("shipping delays", "capacity", "capacity_strain", 0.8),
    ("dispatch delays", "capacity", "capacity_strain", 0.8),
    ("on backorder", "capacity", "capacity_strain", 0.8),
    ("back in stock soon", "capacity", "capacity_strain", 0.6),
    ("order backlog", "capacity", "capacity_strain", 0.9),
    ("longer than usual", "capacity", "capacity_strain", 0.6),
    ("new warehouse", "facility", "warehouse_move", 0.9),
    ("moving to a larger facility", "facility", "warehouse_move", 1.0),
    ("new distribution centre", "facility", "warehouse_move", 1.0),
    ("new distribution center", "facility", "warehouse_move", 1.0),
    ("opening a new facility", "facility", "warehouse_move", 0.9),
    ("relocating our operations", "facility", "warehouse_move", 0.9),
    ("wholesale", "wholesale", "wholesale_b2b", 0.8),
    ("wholesale enquiries", "wholesale", "wholesale_b2b", 1.0),
    ("wholesale inquiries", "wholesale", "wholesale_b2b", 1.0),
    ("trade account", "wholesale", "wholesale_b2b", 1.0),
    ("trade customers", "wholesale", "wholesale_b2b", 1.0),
    ("become a stockist", "wholesale", "wholesale_b2b", 1.0),
    ("become a retailer", "wholesale", "wholesale_b2b", 0.9),
    ("minimum order quantity", "wholesale", "wholesale_b2b", 1.0),
    ("moq", "wholesale", "wholesale_b2b", 0.9),
    ("bulk orders", "wholesale", "wholesale_b2b", 0.9),
    ("trade pricing", "wholesale", "wholesale_b2b", 1.0),
    ("wholesale price list", "wholesale", "wholesale_b2b", 1.0),
    ("b2b portal", "wholesale", "wholesale_b2b", 0.9),
    ("available on amazon", "marketplace", "marketplace_seller", 1.0),
    ("shop on amazon", "marketplace", "marketplace_seller", 0.9),
    ("amazon store", "marketplace", "marketplace_seller", 0.9),
    ("our ebay shop", "marketplace", "marketplace_seller", 1.0),
    ("etsy shop", "marketplace", "marketplace_seller", 0.9),
    ("walmart marketplace", "marketplace", "marketplace_seller", 1.0),
    ("seller central", "marketplace", "marketplace_seller", 0.9),
    ("fba", "marketplace", "marketplace_seller", 0.7),
    ("stockists", "retail", "retail_distribution", 1.0),
    ("find a stockist", "retail", "retail_distribution", 1.0),
    ("where to buy", "retail", "retail_distribution", 0.9),
    ("available in store", "retail", "retail_distribution", 0.9),
    ("our retail partners", "retail", "retail_distribution", 1.0),
    ("now in selfridges", "retail", "retail_distribution", 0.8),
    ("stocked in", "retail", "retail_distribution", 0.7),
    ("retail partners", "retail", "retail_distribution", 0.9),
    ("subscription box", "subscription", "subscription_model", 1.0),
    ("monthly subscription", "subscription", "subscription_model", 0.9),
    ("subscribe and save", "subscription", "subscription_model", 0.9),
    ("recurring delivery", "subscription", "subscription_model", 1.0),
    ("meal kit", "subscription", "subscription_model", 1.0),
    ("delivered monthly", "subscription", "subscription_model", 0.9),
    ("cancel anytime", "subscription", "subscription_model", 0.6),
    ("our factory", "manufacturing", "manufacturer", 1.0),
    ("manufactured in", "manufacturing", "manufacturer", 0.8),
    ("we manufacture", "manufacturing", "manufacturer", 1.0),
    ("our production facility", "manufacturing", "manufacturer", 1.0),
    ("private label", "manufacturing", "manufacturer", 0.9),
    ("white label", "manufacturing", "manufacturer", 0.8),
    ("contract manufacturing", "manufacturing", "manufacturer", 1.0),
    ("made in our workshop", "manufacturing", "manufacturer", 0.9),
    ("imported from", "import", "importer_exporter", 0.8),
    ("we import", "import", "importer_exporter", 1.0),
    ("customs clearance", "import", "importer_exporter", 0.9),
    ("container shipments", "import", "importer_exporter", 1.0),
    ("freight forwarding", "import", "importer_exporter", 0.8),
    ("incoterms", "import", "importer_exporter", 0.9),
    ("duty paid", "import", "importer_exporter", 0.7),
    ("black friday", "seasonal", "peak_season", 0.7),
    ("holiday shipping deadline", "seasonal", "peak_season", 0.9),
    ("christmas delivery cut off", "seasonal", "peak_season", 0.9),
    ("peak season", "seasonal", "peak_season", 0.8),
    ("seasonal demand", "seasonal", "peak_season", 0.8),
]

QUERIES = [
    ("new Shopify brand", None, 1),
    ("new ecommerce brand", None, 1),
    ("new DTC brand", None, 1),
    ("new consumer brand launch", None, 2),
    ("new physical product brand", None, 2),
    ("new online store launch", None, 3),
    ("ecommerce brand expanding internationally", None, 1),
    ("ecommerce company hiring operations manager", None, 1),
    ("DTC brand hiring fulfillment manager", None, 1),
    ("ecommerce brand raises seed funding", None, 2),
    ("DTC brand launching in the US", "US", 1),
    ("UK ecommerce brand expanding to USA", "GB", 1),
    ("Kickstarter product shipping to backers", None, 2),
    ("new Shopify store United Kingdom", "GB", 3),
    ("new Shopify store Australia", "AU", 3),
    ("new food and beverage brand launch", None, 1),
    ("new FMCG brand", None, 1),
    ("new consumer goods brand", None, 1),
    ("new CPG brand launch", None, 1),
    ("new beverage brand", None, 2),
    ("new snack brand launch", None, 2),
    ("new beauty brand launch", None, 2),
    ("new skincare brand launch", None, 2),
    ("new supplement brand", None, 2),
    ("new pet food brand", None, 2),
    ("new homeware brand launch", None, 2),
    ("new clothing brand launch", None, 2),
    ("new apparel brand", None, 2),
    ("physical product brand raising seed funding", None, 1),
    ("consumer goods company hiring operations manager", None, 1),
    ("wholesale brand expanding internationally", None, 2),
    ("new hardware product launch", None, 2),
    ("new electronics brand", None, 2),
    ("\"looking for a 3PL\" brand", None, 1),
    ("\"looking for a fulfillment partner\"", None, 1),
    ("brand \"outgrowing our warehouse\"", None, 1),
    ("ecommerce brand \"outsourcing fulfillment\"", None, 1),
    ("wholesale supplier \"trade accounts\" new brand", None, 2),
    ("\"become a stockist\" new brand", None, 2),
    ("\"minimum order quantity\" wholesale brand launch", None, 3),
    ("B2B wholesale brand expanding distribution", None, 2),
    ("distributor \"now distributing\" consumer products", None, 3),
    ("importer \"we import\" consumer goods company", None, 3),
    ("CPG brand launch new product line", None, 2),
    ("food and beverage brand national rollout", None, 2),
    ("cosmetics brand \"our factory\" expanding", None, 3),
    ("private label manufacturer consumer goods", None, 3),
    ("drinks brand expanding production", None, 3),
    ("supplement brand scaling production", None, 3),
    ("brand \"now available in\" retailer nationwide", None, 2),
    ("brand launches in Target OR Walmart OR Whole Foods", "US", 2),
    ("brand \"now in\" Selfridges OR John Lewis OR Boots", "GB", 2),
    ("\"find a stockist\" brand new retail partners", None, 3),
    ("omnichannel brand expanding retail distribution", None, 2),
    ("Amazon seller brand scaling operations", None, 2),
    ("marketplace seller expanding to new channels", None, 3),
    ("subscription box company launch", None, 2),
    ("meal kit company expanding delivery area", None, 2),
    ("subscription brand raises funding", None, 2),
    ("\"subscribe and save\" brand growth", None, 3),
    ("brand \"new distribution centre\" opening", None, 2),
    ("brand \"moving to a larger facility\"", None, 2),
    ("company hiring warehouse manager new facility", None, 1),
    ("brand \"shipping delays\" apology growth", None, 3),
    ("Kickstarter project shipping rewards to backers", None, 2),
    ("Indiegogo campaign fulfilment update", None, 3),
]

ROLES = [
    ("head of operations", 1),
    ("vp operations", 1),
    ("vp of operations", 1),
    ("coo", 2),
    ("chief operating officer", 2),
    ("operations director", 3),
    ("director of operations", 3),
    ("operations manager", 4),
    ("supply chain manager", 5),
    ("head of supply chain", 5),
    ("supply chain director", 5),
    ("logistics manager", 6),
    ("head of logistics", 6),
    ("fulfillment manager", 7),
    ("fulfilment manager", 7),
    ("inventory manager", 8),
    ("ecommerce director", 9),
    ("head of ecommerce", 9),
    ("director of ecommerce", 9),
    ("founder", 10),
    ("co-founder", 10),
    ("cofounder", 10),
    ("ceo", 11),
    ("chief executive officer", 11),
    ("managing director", 12),
    ("general manager", 15),
]

SERVICE_CONFIG = {
    "score_weights": {"deterministic": 0.5, "ai": 0.3, "evidence": 0.2},
    "intent_thresholds": {"LOW": 0, "POSSIBLE": 31, "GOOD": 51,
                          "STRONG": 71, "HOT": 86},
    "normalization_ceiling": 110,
    "decision_maker_threshold": 80,
    "decision_maker_optional_threshold": 60,
    "ai_analysis_min_raw_score": 25,
    # Physical goods is the gate. A wholesaler, manufacturer, importer or
    # retail brand with no online store still needs warehousing, so
    # ecommerce is a scoring bonus rather than an entry requirement.
    "required_signals": ["physical_products"],
    "refresh_days": {"HOT": 3, "STRONG": 7, "GOOD": 30,
                     "POSSIBLE": 60, "LOW": 180},
    "signal_page_affinity": {
        "existing_3pl": ["shipping", "returns", "about", "website", "careers"],
        "wholesale_b2b": ["website", "about", "other", "shipping"],
        "marketplace_seller": ["website", "about", "other", "shipping"],
        "retail_distribution": ["website", "about", "other"],
        "subscription_model": ["website", "shipping", "other"],
        "manufacturer": ["website", "about"],
        "importer_exporter": ["website", "about", "shipping"],
        "capacity_strain": ["news", "website", "about", "shipping", "careers"],
        "seeking_3pl": ["news", "website", "about", "careers"],
        "warehouse_move": ["news", "about", "website", "press_release"],
        "peak_season": ["news", "website", "careers"],
    },
    # Negative operators appended to every discovery query at search time.
    "query_exclusion_terms": list(QUERY_EXCLUSION_TERMS),
    # Business types rejected at classification even if they reach the crawler.
    "excluded_business_types": list(EXCLUDED_BUSINESS_TYPES),
    "ai_system_prompt": (
        "You are a B2B logistics analyst. Assess whether a company is likely "
        "to need third-party logistics (3PL) services: warehousing, order "
        "fulfillment, pick and pack, and returns management. Consider ALL "
        "companies that move physical goods - direct-to-consumer brands, "
        "wholesalers, distributors, importers, manufacturers, retail and "
        "omnichannel brands, marketplace sellers, and subscription "
        "businesses. A company does not need an online store to need a 3PL. "
        "Base every conclusion strictly on the supplied evidence. If the "
        "evidence does not support a conclusion, say so and lower your "
        "confidence. Never invent facts, names, or figures."
    ),
}


def run_sql_migrations() -> None:
    """Postgres path: execute the .sql files in order."""
    with engine.begin() as conn:
        for name in ("001_init.sql", "002_rls.sql", "003_seed_3pl.sql"):
            path = MIGRATIONS / name
            log.info("Applying %s", name)
            conn.execute(text(path.read_text()))


def seed_orm(with_library: bool = True) -> None:
    """Portable path: seed via the ORM (works on SQLite and Postgres)."""
    db = SessionLocal()
    try:
        service = db.execute(
            select(Service).where(Service.slug == "3pl")).scalar_one_or_none()
        if service is None:
            service = Service(
                name="Third Party Logistics", slug="3pl", status="active",
                description=("Find ecommerce and physical-product brands likely "
                             "to need warehousing, order fulfillment and "
                             "returns management."),
                config=SERVICE_CONFIG)
            db.add(service)
            db.flush()
            log.info("Created service '3pl'")
        else:
            service.config = SERVICE_CONFIG
            log.info("Service '3pl' already exists - config refreshed")

        existing = {r.signal_type for r in db.execute(
            select(ServiceSignal).where(ServiceSignal.service_id == service.id)
        ).scalars()}
        for stype, sname, desc, weight, decay, max_occ in SIGNALS:
            if stype in existing:
                continue
            db.add(ServiceSignal(service_id=service.id, signal_type=stype,
                                 signal_name=sname, description=desc,
                                 weight=weight, decay_days=decay,
                                 max_occurrences=max_occ))
        log.info("Signals seeded (%d definitions)", len(SIGNALS))

        existing_kw = {(r.keyword, r.category) for r in db.execute(
            select(ServiceKeyword).where(ServiceKeyword.service_id == service.id)
        ).scalars()}
        for keyword, category, signal_type, weight in KEYWORDS:
            if (keyword, category) in existing_kw:
                continue
            db.add(ServiceKeyword(service_id=service.id, keyword=keyword,
                                  category=category, signal_type=signal_type,
                                  weight=weight))
        log.info("Keywords seeded (%d)", len(KEYWORDS))

        existing_queries = {
            (row.query, row.country) for row in db.execute(
                select(DiscoveryQuery).where(
                    DiscoveryQuery.service_id == service.id)).scalars()
        }
        added = 0
        for query, country, priority in QUERIES:
            if (query, country) in existing_queries:
                continue
            existing_queries.add((query, country))
            db.add(DiscoveryQuery(service_id=service.id, query=query,
                                  country=country, priority=priority))
            added += 1

        if with_library:
            # The generated combinatorial library. Seeding it costs nothing -
            # only executed queries cost Serper credits, and discovery runs
            # by tier.
            for item in build_library():
                if (item.text, item.country) in existing_queries:
                    continue
                existing_queries.add((item.text, item.country))
                db.add(DiscoveryQuery(service_id=service.id, query=item.text,
                                      country=item.country,
                                      priority=item.tier))
                added += 1
        log.info("Discovery queries seeded (%d new, %d total)",
                 added, len(existing_queries))

        existing_roles = {r.title_pattern for r in db.execute(
            select(ServiceRole).where(ServiceRole.service_id == service.id)
        ).scalars()}
        for pattern, priority in ROLES:
            if pattern in existing_roles:
                continue
            db.add(ServiceRole(service_id=service.id, title_pattern=pattern,
                               role_priority=priority))
        log.info("Decision-maker roles seeded (%d)", len(ROLES))

        db.commit()
        log.info("Seed complete.")
    finally:
        db.close()


def guard_database_configured() -> None:
    """Fail with an actionable message rather than a psycopg traceback."""
    if settings.db_configured:
        return
    log.error(
        "\n"
        "  DATABASE_URL is not configured.\n"
        "  It still contains the YOUR_DB_PASSWORD placeholder, so nothing\n"
        "  can be written to the database.\n\n"
        "  Fix it one of two ways:\n\n"
        "  A) Use Supabase - put your database password in backend/.env:\n"
        "     Supabase -> Project Settings -> Database -> Connection string\n\n"
        "  B) Run locally first, no setup required:\n"
        '     DATABASE_URL="sqlite+pysqlite:///./local.db" \\\n'
        "       python -m scripts.seed --local\n")
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", action="store_true",
                        help="Run the raw .sql migrations (Postgres only)")
    parser.add_argument("--local", action="store_true",
                        help="Create schema via ORM metadata first")
    parser.add_argument("--no-library", action="store_true",
                        help="Skip the generated combinatorial query library")
    args = parser.parse_args()

    guard_database_configured()
    log.info("Database: %s", settings.database_url.split("@")[-1])

    if args.sql:
        run_sql_migrations()
    elif args.local or settings.database_url.startswith("sqlite"):
        init_local_schema()

    seed_orm(with_library=not args.no_library)


if __name__ == "__main__":
    main()

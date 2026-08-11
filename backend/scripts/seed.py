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

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("seed")

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"

# Mirrors 003_seed_3pl.sql. Kept here so SQLite/dev seeding works without psql.
SIGNALS = [
    ("ecommerce", "Ecommerce", "Sells online via a storefront platform or cart/checkout flow", 10, None, 1),
    ("physical_products", "Physical Products", "Ships tangible goods with SKUs, inventory and returns", 10, None, 1),
    ("new_store", "New Store", "Recently launched online store", 10, 365, 1),
    ("international_shipping", "International Shipping", "States it ships beyond its home market", 8, None, 1),
    ("international_expansion", "International Expansion", "Announced entry into a new geographic market", 15, 270, 2),
    ("recent_funding", "Recent Funding", "Raised capital recently; growth pressure on operations", 12, 540, 2),
    ("product_launch", "Product Launch", "New product line, major launch or pre-orders", 10, 180, 3),
    ("operations_hiring", "Operations Hiring", "Hiring ops/supply chain/logistics roles", 15, 120, 3),
    ("fulfillment_hiring", "Fulfillment Hiring", "Hiring fulfillment/warehouse/distribution roles", 20, 120, 3),
    ("crowdfunding", "Crowdfunding", "Running or recently funded a crowdfunding campaign", 15, 365, 1),
    ("rapid_growth", "Rapid Growth", "Public evidence of fast growth", 10, 270, 1),
    ("existing_3pl", "Existing 3PL", "Already works with a fulfillment provider", -20, None, 1),
]

KEYWORDS = [
    ("3pl", "logistics", "existing_3pl", 1.0),
    ("third party logistics", "logistics", "existing_3pl", 1.0),
    ("fulfillment partner", "logistics", "existing_3pl", 1.0),
    ("fulfilment partner", "logistics", "existing_3pl", 1.0),
    ("warehouse partner", "logistics", "existing_3pl", 1.0),
    ("shipbob", "logistics", "existing_3pl", 1.0),
    ("shipmonk", "logistics", "existing_3pl", 1.0),
    ("huboo", "logistics", "existing_3pl", 1.0),
    ("fulfillment by amazon", "logistics", "existing_3pl", 0.9),
    ("sku", "physical", "physical_products", 0.8),
    ("free shipping", "physical", "physical_products", 0.7),
    ("shipping policy", "physical", "physical_products", 0.8),
    ("return policy", "physical", "physical_products", 0.7),
    ("tracking number", "physical", "physical_products", 0.7),
    ("dispatch", "physical", "physical_products", 0.6),
    ("add to cart", "ecommerce", "ecommerce", 1.0),
    ("add to bag", "ecommerce", "ecommerce", 1.0),
    ("shopping cart", "ecommerce", "ecommerce", 0.9),
    ("checkout", "ecommerce", "ecommerce", 0.8),
    ("ships worldwide", "international", "international_shipping", 1.0),
    ("ship worldwide", "international", "international_shipping", 1.0),
    ("we ship worldwide", "international", "international_shipping", 1.0),
    ("ship internationally", "international", "international_shipping", 1.0),
    ("shipping worldwide", "international", "international_shipping", 1.0),
    ("global shipping", "international", "international_shipping", 0.9),
    ("ships to europe", "international", "international_shipping", 0.9),
    ("worldwide shipping", "international", "international_shipping", 1.0),
    ("international shipping", "international", "international_shipping", 1.0),
    ("ships to usa", "international", "international_shipping", 0.9),
    ("customs and duties", "international", "international_shipping", 0.8),
    ("launching in the us", "international", "international_expansion", 1.0),
    ("expanding into", "international", "international_expansion", 1.0),
    ("entering the us market", "international", "international_expansion", 1.0),
    ("now available in the us", "international", "international_expansion", 1.0),
    ("operations manager", "hiring", "operations_hiring", 1.0),
    ("head of operations", "hiring", "operations_hiring", 1.0),
    ("supply chain manager", "hiring", "operations_hiring", 1.0),
    ("logistics manager", "hiring", "operations_hiring", 1.0),
    ("inventory manager", "hiring", "operations_hiring", 0.9),
    ("fulfillment manager", "hiring", "fulfillment_hiring", 1.0),
    ("warehouse manager", "hiring", "fulfillment_hiring", 1.0),
    ("fulfillment operations", "hiring", "fulfillment_hiring", 1.0),
    ("distribution manager", "hiring", "fulfillment_hiring", 1.0),
    ("seed round", "funding", "recent_funding", 1.0),
    ("series a", "funding", "recent_funding", 1.0),
    ("funding round", "funding", "recent_funding", 1.0),
    ("kickstarter", "crowdfunding", "crowdfunding", 1.0),
    ("indiegogo", "crowdfunding", "crowdfunding", 1.0),
    ("backers", "crowdfunding", "crowdfunding", 0.8),
    ("pre-order", "launch", "product_launch", 0.8),
    ("new collection", "launch", "product_launch", 0.7),
]

QUERIES = [
    ("new Shopify brand", None, 1),
    ("new ecommerce brand", None, 1),
    ("new DTC brand", None, 1),
    ("new consumer brand launch", None, 2),
    ("ecommerce brand expanding internationally", None, 1),
    ("ecommerce company hiring operations manager", None, 1),
    ("DTC brand hiring fulfillment manager", None, 1),
    ("ecommerce brand raises seed funding", None, 2),
    ("DTC brand launching in the US", "US", 1),
    ("UK ecommerce brand expanding to USA", "GB", 1),
    ("Kickstarter product shipping to backers", None, 2),
]

ROLES = [
    ("head of operations", 1), ("vp operations", 1), ("vp of operations", 1),
    ("coo", 2), ("chief operating officer", 2),
    ("operations director", 3), ("director of operations", 3),
    ("operations manager", 4),
    ("supply chain manager", 5), ("head of supply chain", 5),
    ("logistics manager", 6), ("head of logistics", 6),
    ("fulfillment manager", 7), ("fulfilment manager", 7),
    ("inventory manager", 8),
    ("ecommerce director", 9), ("head of ecommerce", 9),
    ("founder", 10), ("co-founder", 10), ("cofounder", 10),
    ("ceo", 11), ("chief executive officer", 11),
    ("managing director", 12), ("general manager", 15),
]

SERVICE_CONFIG = {
    "score_weights": {"deterministic": 0.5, "ai": 0.3, "evidence": 0.2},
    "intent_thresholds": {"LOW": 0, "POSSIBLE": 31, "GOOD": 51,
                          "STRONG": 71, "HOT": 86},
    "normalization_ceiling": 100,
    "decision_maker_threshold": 80,
    "decision_maker_optional_threshold": 60,
    "ai_analysis_min_raw_score": 25,
    "required_signals": ["ecommerce", "physical_products"],
    "signal_page_affinity": {
        "existing_3pl": ["shipping", "returns", "about", "website", "careers"],
    },
    "refresh_days": {"HOT": 3, "STRONG": 7, "GOOD": 30,
                     "POSSIBLE": 60, "LOW": 180},
    "ai_system_prompt": (
        "You are a B2B logistics analyst. Assess whether a company is likely "
        "to need third-party logistics (3PL) services: warehousing, order "
        "fulfillment, pick and pack, and returns management. Base every "
        "conclusion strictly on the supplied evidence. If the evidence does "
        "not support a conclusion, say so and lower your confidence. Never "
        "invent facts, names, or figures."
    ),
}


def run_sql_migrations() -> None:
    """Postgres path: execute the .sql files in order."""
    with engine.begin() as conn:
        for name in ("001_init.sql", "002_rls.sql", "003_seed_3pl.sql"):
            path = MIGRATIONS / name
            log.info("Applying %s", name)
            conn.execute(text(path.read_text()))


def seed_orm() -> None:
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

        if not db.execute(select(DiscoveryQuery).where(
                DiscoveryQuery.service_id == service.id)).scalars().first():
            for query, country, priority in QUERIES:
                db.add(DiscoveryQuery(service_id=service.id, query=query,
                                      country=country, priority=priority))
            log.info("Discovery queries seeded (%d)", len(QUERIES))

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
    args = parser.parse_args()

    guard_database_configured()
    log.info("Database: %s", settings.database_url.split("@")[-1])

    if args.sql:
        run_sql_migrations()
    elif args.local or settings.database_url.startswith("sqlite"):
        init_local_schema()

    seed_orm()


if __name__ == "__main__":
    main()

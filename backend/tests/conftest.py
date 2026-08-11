from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import (  # noqa: E402
    Base, Company, DiscoveryQuery, Service, ServiceKeyword, ServiceRole,
    ServiceSignal, Source,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def service(db):
    from scripts.seed import KEYWORDS, ROLES, SERVICE_CONFIG, SIGNALS

    svc = Service(name="Third Party Logistics", slug="3pl", status="active",
                  config=SERVICE_CONFIG)
    db.add(svc)
    db.flush()
    for stype, sname, desc, weight, decay, max_occ in SIGNALS:
        db.add(ServiceSignal(service_id=svc.id, signal_type=stype,
                             signal_name=sname, description=desc, weight=weight,
                             decay_days=decay, max_occurrences=max_occ))
    for keyword, category, signal_type, weight in KEYWORDS:
        db.add(ServiceKeyword(service_id=svc.id, keyword=keyword,
                              category=category, signal_type=signal_type,
                              weight=weight))
    for pattern, priority in ROLES:
        db.add(ServiceRole(service_id=svc.id, title_pattern=pattern,
                           role_priority=priority))
    db.add(DiscoveryQuery(service_id=svc.id, query="new DTC brand", priority=1))
    db.flush()
    return svc


@pytest.fixture
def config(db, service):
    from app.engine.service_config import build_config
    return build_config(db, service)


@pytest.fixture
def company(db):
    row = Company(name="Example Brand", domain="examplebrand.com",
                  website="https://examplebrand.com", country="GB",
                  is_ecommerce=True, is_physical_product=True,
                  platform="shopify", status="classified")
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def source(db, company):
    row = Source(company_id=company.id, source_type="website",
                 url="https://examplebrand.com", title="Example Brand",
                 content="Add to cart. Free shipping worldwide.")
    db.add(row)
    db.flush()
    return row

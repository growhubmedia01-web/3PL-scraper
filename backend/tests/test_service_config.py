"""The architecture requirement (§10, §67, §70): a second service must need
no code changes."""
from __future__ import annotations

from app.engine.service_config import build_config
from app.models import Service, ServiceRole, ServiceSignal


def test_config_loads_weights_from_the_database(config):
    assert config.weight_for("fulfillment_hiring") == 20
    assert config.weight_for("existing_3pl") == -20
    assert config.weight_for("nonexistent_signal") == 0


def test_role_priority_prefers_the_most_specific_match(config):
    assert config.role_priority_for("Head of Operations") == 1
    assert config.role_priority_for("COO") == 2
    assert config.role_priority_for("Chief Bottle Washer") is None


def test_changing_a_weight_changes_scoring_without_code_changes(db, company,
                                                                service, config):
    from datetime import datetime, timezone

    from app.engine import scoring
    from app.models import Signal

    signals = [Signal(company_id=company.id, service_id=service.id,
                      signal_type=t, strength=1.0, confidence=1.0,
                      detected_at=datetime.now(timezone.utc))
               for t in ("ecommerce", "physical_products", "operations_hiring")]
    before = scoring.calculate(db, company, signals, config).score

    row = db.query(ServiceSignal).filter_by(
        service_id=service.id, signal_type="operations_hiring").one()
    row.weight = 40
    db.flush()

    after = scoring.calculate(db, company, signals, build_config(db, service)).score
    assert after > before


def test_a_second_service_needs_only_new_rows(db):
    """Create a 'packaging' service with its own signals and roles - no code."""
    packaging = Service(name="Packaging", slug="packaging", status="active",
                        config={"required_signals": ["physical_products"]})
    db.add(packaging)
    db.flush()
    db.add(ServiceSignal(service_id=packaging.id, signal_type="physical_products",
                         signal_name="Physical Products", weight=25))
    db.add(ServiceSignal(service_id=packaging.id, signal_type="product_launch",
                         signal_name="Product Launch", weight=30, decay_days=180))
    db.add(ServiceRole(service_id=packaging.id, title_pattern="head of design",
                       role_priority=1))
    db.flush()

    config = build_config(db, packaging)
    assert config.slug == "packaging"
    assert config.weight_for("product_launch") == 30
    assert config.role_priority_for("Head of Design") == 1
    assert config.required_signals == ["physical_products"]

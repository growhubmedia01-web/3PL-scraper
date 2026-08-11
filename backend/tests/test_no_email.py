"""The no-email constraint is a product requirement (§5, §20, §35, §40).

These tests fail loudly if anyone reintroduces email handling.
"""
from __future__ import annotations

import pathlib

from app.api.export import CSV_COLUMNS
from app.models import DecisionMaker

BACKEND = pathlib.Path(__file__).resolve().parent.parent

FORBIDDEN_IDENTIFIERS = [
    "zerobounce", "hunter.io", "neverbounce", "emailhippo",
    "verify_email", "find_email", "email_finder", "smtp",
]


def test_decision_maker_model_has_no_email_column():
    columns = {c.name.lower() for c in DecisionMaker.__table__.columns}
    assert not any("email" in c or "mail" in c for c in columns), \
        f"DecisionMaker must not store email addresses. Found: {columns}"


def test_csv_export_has_no_email_columns():
    for column in CSV_COLUMNS:
        assert "email" not in column.lower()
        assert "mail" not in column.lower()


def test_no_email_provider_integrations_in_source():
    offenders = []
    for path in (BACKEND / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for token in FORBIDDEN_IDENTIFIERS:
            if token in text:
                offenders.append((path.name, token))
    assert not offenders, f"Email-provider integrations found: {offenders}"


def test_all_orm_tables_are_email_free():
    from app.models import Base
    offenders = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            name = column.name.lower()
            if "email" in name:
                offenders.append(f"{table.name}.{column.name}")
    assert not offenders, f"Email columns present in schema: {offenders}"

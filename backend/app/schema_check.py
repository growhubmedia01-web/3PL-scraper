"""Detect schema drift between the ORM and the live database.

Running the app against a database that is one migration behind produces
errors like:

    psycopg.errors.UndefinedColumn: column companies.business_model does not
    exist

thrown from wherever the column is first selected - usually deep inside a
background task, long after startup. This turns that into a named list of
missing columns and the migration that adds them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Columns added after the initial schema, and the migration that adds them.
# Keep in step with migrations/.
COLUMN_ORIGINS: dict[tuple[str, str], str] = {
    ("companies", "business_model"): "004_broaden_beyond_ecommerce.sql",
    ("companies", "sales_channels"): "004_broaden_beyond_ecommerce.sql",
}


@dataclass
class SchemaReport:
    missing_tables: list[str] = field(default_factory=list)
    missing_columns: list[tuple[str, str]] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return not (self.missing_tables or self.missing_columns or self.error)

    def required_migrations(self) -> list[str]:
        found = {COLUMN_ORIGINS.get(col) for col in self.missing_columns}
        migrations = sorted(m for m in found if m)
        if self.missing_tables and not migrations:
            return ["ALL_IN_ONE.sql"]
        return migrations or (["ALL_IN_ONE.sql"] if self.missing_tables else [])

    def summary(self) -> str:
        if self.error:
            return f"Could not inspect the database: {self.error}"
        if self.ok:
            return "Database schema matches the application."

        lines: list[str] = ["Database schema is out of date."]
        if self.missing_tables:
            lines.append(f"  Missing tables : {', '.join(self.missing_tables)}")
        if self.missing_columns:
            grouped: dict[str, list[str]] = {}
            for table, column in self.missing_columns:
                grouped.setdefault(table, []).append(column)
            for table, columns in sorted(grouped.items()):
                lines.append(f"  Missing columns: {table}.{{{', '.join(sorted(columns))}}}")
        migrations = self.required_migrations()
        if migrations:
            lines.append("")
            lines.append("  Run this in the Supabase SQL Editor:")
            for migration in migrations:
                lines.append(f"    backend/migrations/{migration}")
        return "\n".join(lines)


def check_schema(engine: Engine) -> SchemaReport:
    from app.models import Base

    report = SchemaReport()
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
    except Exception as exc:
        report.error = f"{type(exc).__name__}: {exc}"
        return report

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            report.missing_tables.append(table.name)
            continue
        try:
            actual = {c["name"] for c in inspector.get_columns(table.name)}
        except Exception as exc:
            report.error = f"{type(exc).__name__}: {exc}"
            return report
        for column in table.columns:
            if column.name not in actual:
                report.missing_columns.append((table.name, column.name))

    report.missing_tables.sort()
    report.missing_columns.sort()
    return report

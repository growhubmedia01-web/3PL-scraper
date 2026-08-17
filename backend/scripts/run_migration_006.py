"""Apply migration 006 (LinkedIn URL columns) via SQLAlchemy."""
from __future__ import annotations
import logging
import sys
from pathlib import Path

# Add backend directory to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text, inspect
from app.db import engine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

sqls = [
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_url text",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_source text",
    "ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_checked_at timestamptz",
]

def run():
    log.info("Connecting to database...")
    try:
        # Check what is currently missing using dialect-agnostic inspect
        log.info("Verifying existing columns in 'companies' table...")
        inspector = inspect(engine)
        existing_cols = {c["name"] for c in inspector.get_columns("companies")}
        
        log.info("Found existing columns in companies: %s", existing_cols)
        
        target_cols = {"linkedin_url", "linkedin_source", "linkedin_checked_at"}
        missing_cols = target_cols - existing_cols
        
        if not missing_cols:
            log.info("All LinkedIn columns already exist! No migration needed.")
            return

        log.info("Applying migration for columns: %s", missing_cols)
        with engine.begin() as conn:
            for sql in sqls:
                # We can just run ALTER TABLE with IF NOT EXISTS which is safe in PG/SQLite (if modern SQLite)
                # Or run them conditionally based on missing_cols
                col_name = sql.split("ADD COLUMN IF NOT EXISTS")[1].strip().split()[0]
                if col_name in missing_cols:
                    # SQLite doesn't support ADD COLUMN IF NOT EXISTS, so construct safe sql
                    if engine.dialect.name == "sqlite":
                        col_type = sql.split()[-1]
                        # timestamptz isn't native to SQLite but works as text/timestamp
                        safe_sql = f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}"
                        log.info("Executing (SQLite): %s", safe_sql)
                        conn.execute(text(safe_sql))
                    else:
                        log.info("Executing (PostgreSQL): %s", sql)
                        conn.execute(text(sql))
                        
        log.info("Migration 006 applied successfully.")
    except Exception as exc:
        log.error("Migration failed: %s", exc)
        sys.exit(1)

if __name__ == "__main__":
    run()

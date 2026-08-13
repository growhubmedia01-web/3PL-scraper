"""SQLAlchemy engine/session. Works against Supabase Postgres or local SQLite."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

log = logging.getLogger(__name__)

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    **({\
        "connect_args": {"check_same_thread": False, "timeout": 30}
    } if _is_sqlite else {
        # prepare_threshold=None fully disables server-side prepared statements.
        # Required for Supabase's PgBouncer transaction pooler — it does not
        # persist prepared statements across connections.
        #
        # IMPORTANT: 0 means "prepare on first use" (wrong — makes it worse!).
        #            None means "never prepare" (correct for PgBouncer).
        "connect_args": {"prepare_threshold": None},
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,
    }),
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
else:
    @event.listens_for(engine, "connect")
    def _pg_no_prepared_stmts(dbapi_conn, _):
        """Belt-and-suspenders: disable prepared statements on every connection.

        Supabase's PgBouncer transaction pooler does not persist prepared
        statements across connections. None = never use prepared statements.
        0 would mean "prepare on first use" which is wrong for PgBouncer.
        """
        dbapi_conn.prepare_threshold = None


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False,
                           class_=Session, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """For workers and scripts: commit on success, roll back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_local_schema() -> None:
    """Create tables from the ORM metadata. Dev/SQLite convenience only -
    against Supabase, run the SQL files in backend/migrations/ instead."""
    from app import models  # noqa: F401
    models.Base.metadata.create_all(engine)
    log.info("Local schema created at %s", settings.database_url)

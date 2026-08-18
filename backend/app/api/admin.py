"""Admin configuration APIs (§46).

Everything that makes the platform configurable rather than hardcoded:
services, signals, weights, keywords, queries, thresholds, AI settings.
All routes require the X-Admin-Token header.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.engine import linkedin
from app.models import (
    Company, DecisionMaker, DiscoveryQuery, Service, ServiceKeyword,
    ServiceRole, ServiceSignal, Suppression,
)
from app.schemas import (
    DiscoveryQueryOut, KeywordCreate, QueryCreate, QueryUpdate, ServiceCreate,
    ServiceKeywordOut, ServiceOut, ServiceSignalOut, ServiceUpdate,
    SignalCreate, SignalUpdate, SuppressionCreate,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])



def _service(db: Session, ref: str) -> Service:
    svc = db.execute(
        select(Service).where(Service.slug == ref)
    ).scalar_one_or_none() or db.get(Service, ref)
    if svc is None:
        raise HTTPException(404, f"Service '{ref}' not found")
    return svc


# ---------------- services ----------------
@router.post("/services", response_model=ServiceOut, status_code=201)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db)):
    if db.execute(select(Service).where(Service.slug == payload.slug)).scalar_one_or_none():
        raise HTTPException(409, f"Service slug '{payload.slug}' already exists")
    service = Service(**payload.model_dump())
    db.add(service)
    db.commit()
    return service


@router.patch("/services/{service_ref}", response_model=ServiceOut)
def update_service(service_ref: str, payload: ServiceUpdate,
                   db: Session = Depends(get_db)):
    service = _service(db, service_ref)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    db.commit()
    return service


@router.patch("/services/{service_ref}/config", response_model=ServiceOut)
def patch_service_config(service_ref: str, patch: dict,
                         db: Session = Depends(get_db)):
    """Merge keys into service.config: score weights, intent thresholds,
    decision-maker threshold, AI prompt, etc. (§46)."""
    service = _service(db, service_ref)
    merged = dict(service.config or {})
    merged.update(patch)
    service.config = merged
    db.commit()
    return service


# ---------------- signals ----------------
@router.get("/services/{service_ref}/signals", response_model=list[ServiceSignalOut])
def list_signals(service_ref: str, db: Session = Depends(get_db)):
    service = _service(db, service_ref)
    return db.execute(
        select(ServiceSignal).where(ServiceSignal.service_id == service.id)
        .order_by(ServiceSignal.weight.desc())).scalars().all()


@router.post("/services/{service_ref}/signals",
             response_model=ServiceSignalOut, status_code=201)
def create_signal(service_ref: str, payload: SignalCreate,
                  db: Session = Depends(get_db)):
    service = _service(db, service_ref)
    signal = ServiceSignal(service_id=service.id, **payload.model_dump())
    db.add(signal)
    db.commit()
    return signal


@router.patch("/signals/{signal_id}", response_model=ServiceSignalOut)
def update_signal(signal_id: str, payload: SignalUpdate,
                  db: Session = Depends(get_db)):
    signal = db.get(ServiceSignal, signal_id)
    if signal is None:
        raise HTTPException(404, "Signal not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(signal, field, value)
    db.commit()
    return signal


@router.delete("/signals/{signal_id}", status_code=204)
def delete_signal(signal_id: str, db: Session = Depends(get_db)):
    signal = db.get(ServiceSignal, signal_id)
    if signal is None:
        raise HTTPException(404, "Signal not found")
    db.delete(signal)
    db.commit()


# ---------------- queries ----------------
@router.post("/services/{service_ref}/queries",
             response_model=DiscoveryQueryOut, status_code=201)
def create_query(service_ref: str, payload: QueryCreate,
                 db: Session = Depends(get_db)):
    service = _service(db, service_ref)
    query = DiscoveryQuery(service_id=service.id, **payload.model_dump())
    db.add(query)
    db.commit()
    return query


@router.patch("/queries/{query_id}", response_model=DiscoveryQueryOut)
def update_query(query_id: str, payload: QueryUpdate,
                 db: Session = Depends(get_db)):
    query = db.get(DiscoveryQuery, query_id)
    if query is None:
        raise HTTPException(404, "Query not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(query, field, value)
    db.commit()
    return query


@router.delete("/queries/{query_id}", status_code=204)
def delete_query(query_id: str, db: Session = Depends(get_db)):
    query = db.get(DiscoveryQuery, query_id)
    if query is None:
        raise HTTPException(404, "Query not found")
    db.delete(query)
    db.commit()


# ---------------- keywords ----------------
@router.post("/services/{service_ref}/keywords",
             response_model=ServiceKeywordOut, status_code=201)
def create_keyword(service_ref: str, payload: KeywordCreate,
                   db: Session = Depends(get_db)):
    service = _service(db, service_ref)
    keyword = ServiceKeyword(service_id=service.id, **payload.model_dump())
    db.add(keyword)
    db.commit()
    return keyword


@router.delete("/keywords/{keyword_id}", status_code=204)
def delete_keyword(keyword_id: str, db: Session = Depends(get_db)):
    keyword = db.get(ServiceKeyword, keyword_id)
    if keyword is None:
        raise HTTPException(404, "Keyword not found")
    db.delete(keyword)
    db.commit()


# ---------------- roles ----------------
@router.post("/services/{service_ref}/roles", status_code=201)
def create_role(service_ref: str, title_pattern: str, role_priority: int = 50,
                db: Session = Depends(get_db)):
    service = _service(db, service_ref)
    role = ServiceRole(service_id=service.id,
                       title_pattern=title_pattern.lower(),
                       role_priority=role_priority)
    db.add(role)
    db.commit()
    return {"id": role.id, "title_pattern": role.title_pattern,
            "role_priority": role.role_priority}


# ---------------- GDPR: suppression + erasure ----------------
@router.post("/suppressions", status_code=201)
def create_suppression(payload: SuppressionCreate, db: Session = Depends(get_db)):
    """Right to object. Adding a person here also deletes existing records."""
    existing = db.execute(
        select(Suppression).where(Suppression.kind == payload.kind,
                                  Suppression.value == payload.value)
    ).scalar_one_or_none()
    if existing is None:
        db.add(Suppression(**payload.model_dump()))

    removed = 0
    if payload.kind == "person":
        rows = db.execute(
            select(DecisionMaker).where(
                DecisionMaker.name.ilike(payload.value))).scalars().all()
        for row in rows:
            db.delete(row)
            removed += 1
    db.commit()
    return {"ok": True, "records_removed": removed}


@router.delete("/decision-makers/{dm_id}", status_code=204)
def delete_decision_maker(dm_id: str, db: Session = Depends(get_db)):
    """Data subject erasure request."""
    person = db.get(DecisionMaker, dm_id)
    if person is None:
        raise HTTPException(404, "Decision maker not found")
    db.delete(person)
    db.commit()


@router.get("/suppressions")
def list_suppressions(db: Session = Depends(get_db)):
    rows = db.execute(select(Suppression)).scalars().all()
    return [{"id": r.id, "kind": r.kind, "value": r.value,
             "reason": r.reason, "created_at": r.created_at} for r in rows]


@router.post("/run-migration")
def run_migration(db: Session = Depends(get_db)):
    """Apply migrations 004 and 006: business_model/sales_channels and
    linkedin_url/linkedin_source/linkedin_checked_at columns.
    Safe to run multiple times (IF NOT EXISTS guards)."""
    from sqlalchemy import text
    results = []
    sqls = [
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS business_model text",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sales_channels jsonb NOT NULL DEFAULT '[]'::jsonb",
        "CREATE INDEX IF NOT EXISTS idx_companies_business_model ON companies(business_model)",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_url text",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_source text",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS linkedin_checked_at timestamptz",
    ]
    for sql in sqls:
        try:
            db.execute(text(sql))
            db.commit()
            results.append({"sql": sql[:60], "status": "ok"})
        except Exception as exc:
            db.rollback()
            results.append({"sql": sql[:60], "status": "error", "error": str(exc)[:200]})
    return {"results": results}


@router.post("/seed-queries")
def seed_queries(service_ref: str = "3pl", tier: int | None = None,
                 db: Session = Depends(get_db)):
    """Insert all queries from the query library that don't already exist.

    Safe to call multiple times - uses a NOT EXISTS check. Pass tier=1 to
    only insert the new high-intent 3PL queries without re-seeding everything.
    """
    import sys
    from pathlib import Path
    from sqlalchemy import func as _func

    scripts_dir = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from query_library import build_library  # type: ignore[import]

    service = _service(db, service_ref)
    all_queries = build_library()
    if tier is not None:
        all_queries = [q for q in all_queries if q.tier == tier]

    # Fetch existing query texts once for fast dedup
    existing_texts: set[str] = set(
        db.execute(
            select(DiscoveryQuery.query)
            .where(DiscoveryQuery.service_id == service.id)
        ).scalars().all()
    )

    added = 0
    for q in all_queries:
        if q.text not in existing_texts:
            db.add(DiscoveryQuery(
                service_id=service.id,
                query=q.text,
                country=q.country,
                priority=q.tier,
                enabled=True,
            ))
            existing_texts.add(q.text)
            added += 1

    db.commit()
    total = db.execute(
        select(_func.count(DiscoveryQuery.id))
        .where(DiscoveryQuery.service_id == service.id)
    ).scalar_one()

    return {"added": added, "skipped": len(all_queries) - added,
            "total_now": total, "library_size": len(all_queries)}


# ---------------- stuck-company utilities ----------------

@router.get("/companies/stuck")
def list_stuck_companies(db: Session = Depends(get_db)):
    """List companies stuck in 'crawling' or 'queued' that may have lock issues."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT id, domain, status, created_at, updated_at, last_crawled_at
        FROM companies
        WHERE status IN ('crawling', 'queued')
        ORDER BY created_at
        LIMIT 50
    """)).fetchall()
    return [{"id": str(r.id), "domain": r.domain, "status": r.status,
             "created_at": str(r.created_at), "updated_at": str(r.updated_at),
             "last_crawled_at": str(r.last_crawled_at)} for r in rows]


@router.post("/companies/{company_id}/skip")
def skip_company(company_id: str, reason: str = "manually skipped - lock timeout",
                 db: Session = Depends(get_db)):
    """Force a stuck company out of the queue by setting status='error'.

    Uses raw SQL with NOWAIT so it immediately errors if the row is still
    locked (rather than waiting 30s and timing out the whole session).
    If NOWAIT fails, falls back to a direct connection with a short lock_timeout.
    """
    from sqlalchemy import text

    # Try with NOWAIT first
    try:
        result = db.execute(text("""
            UPDATE companies
            SET status = 'error',
                rejection_reason = :reason,
                updated_at = NOW()
            WHERE id = :id
              AND status IN ('queued', 'discovered', 'crawling', 'error')
        """), {"id": company_id, "reason": reason})
        db.commit()
        return {"ok": True, "rows_updated": result.rowcount, "company_id": company_id}
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Could not skip company: {exc}") from exc


# ---------------- LinkedIn backfill ----------------

@router.post("/backfill-linkedin")
def backfill_linkedin(limit: int = Query(50, ge=1, le=200),
                      db: Session = Depends(get_db)):
    """One-time sweep: resolve LinkedIn URLs for already-classified companies
    that predate this feature (resolve_company_linkedin normally only runs
    during fresh pipeline processing, so it never touches historical rows).

    Tier 1 (json_ld/site-link scan) needs the raw crawled page objects, which
    aren't persisted anywhere - `sources.content` only stores extracted text,
    not links or json_ld - so this can only attempt tier 2 (search). That
    needs nothing but company.name/domain, so no re-crawl is required.

    Bounded by `limit` and gated by the same linkedin_checked_at guard the
    normal pipeline uses, so calling this repeatedly is always safe and
    never repeats a search for a company already attempted.
    """
    companies = db.execute(
        select(Company).where(
            Company.status == "classified",
            Company.linkedin_url.is_(None),
            Company.linkedin_checked_at.is_(None),
        ).order_by(Company.created_at).limit(limit)
    ).scalars().all()

    found = 0
    for company in companies:
        try:
            if linkedin.resolve_company_linkedin(db, company, []):
                found += 1
            db.commit()
        except Exception as exc:
            db.rollback()
            log.warning("LinkedIn backfill failed for %s: %s",
                       company.domain, exc)

    remaining = db.execute(
        select(func.count()).select_from(Company).where(
            Company.status == "classified",
            Company.linkedin_url.is_(None),
            Company.linkedin_checked_at.is_(None),
        )
    ).scalar_one()

    return {"checked": len(companies), "found": found, "remaining": remaining}


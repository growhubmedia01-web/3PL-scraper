"""Admin configuration APIs (§46).

Everything that makes the platform configurable rather than hardcoded:
services, signals, weights, keywords, queries, thresholds, AI settings.
All routes require the X-Admin-Token header.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import (
    DecisionMaker, DiscoveryQuery, Service, ServiceKeyword, ServiceRole,
    ServiceSignal, Suppression,
)
from app.schemas import (
    DiscoveryQueryOut, KeywordCreate, QueryCreate, QueryUpdate, ServiceCreate,
    ServiceKeywordOut, ServiceOut, ServiceSignalOut, ServiceUpdate,
    SignalCreate, SignalUpdate, SuppressionCreate,
)

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

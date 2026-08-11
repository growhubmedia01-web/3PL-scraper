"""Service catalogue endpoints (§45)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.service_config import build_config
from app.models import (
    DiscoveryQuery, Service, ServiceKeyword, ServiceRole, ServiceSignal,
)
from app.schemas import (
    DiscoveryQueryOut, ServiceKeywordOut, ServiceOut, ServiceRoleOut,
    ServiceSignalOut,
)

router = APIRouter(prefix="/api/services", tags=["services"])


def _resolve(db: Session, service_ref: str) -> Service:
    service = db.execute(
        select(Service).where(Service.slug == service_ref)
    ).scalar_one_or_none() or db.get(Service, service_ref)
    if service is None:
        raise HTTPException(404, f"Service '{service_ref}' not found")
    return service


@router.get("", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.execute(select(Service).order_by(Service.name)).scalars().all()


@router.get("/{service_ref}", response_model=ServiceOut)
def get_service(service_ref: str, db: Session = Depends(get_db)):
    return _resolve(db, service_ref)


@router.get("/{service_ref}/signals", response_model=list[ServiceSignalOut])
def get_service_signals(service_ref: str, db: Session = Depends(get_db)):
    service = _resolve(db, service_ref)
    return db.execute(
        select(ServiceSignal)
        .where(ServiceSignal.service_id == service.id)
        .order_by(ServiceSignal.weight.desc())
    ).scalars().all()


@router.get("/{service_ref}/keywords", response_model=list[ServiceKeywordOut])
def get_service_keywords(service_ref: str, db: Session = Depends(get_db)):
    service = _resolve(db, service_ref)
    return db.execute(
        select(ServiceKeyword)
        .where(ServiceKeyword.service_id == service.id)
        .order_by(ServiceKeyword.category, ServiceKeyword.keyword)
    ).scalars().all()


@router.get("/{service_ref}/queries", response_model=list[DiscoveryQueryOut])
def get_service_queries(service_ref: str, db: Session = Depends(get_db)):
    service = _resolve(db, service_ref)
    return db.execute(
        select(DiscoveryQuery)
        .where(DiscoveryQuery.service_id == service.id)
        .order_by(DiscoveryQuery.priority)
    ).scalars().all()


@router.get("/{service_ref}/roles", response_model=list[ServiceRoleOut])
def get_service_roles(service_ref: str, db: Session = Depends(get_db)):
    service = _resolve(db, service_ref)
    return db.execute(
        select(ServiceRole)
        .where(ServiceRole.service_id == service.id)
        .order_by(ServiceRole.role_priority)
    ).scalars().all()


@router.get("/{service_ref}/config")
def get_effective_config(service_ref: str, db: Session = Depends(get_db)):
    """The resolved config the engine actually uses - useful for debugging
    why a lead scored the way it did."""
    service = _resolve(db, service_ref)
    config = build_config(db, service)
    return {
        "slug": config.slug,
        "name": config.name,
        "score_weights": config.score_weights,
        "intent_thresholds": config.intent_thresholds,
        "normalization_ceiling": config.normalization_ceiling,
        "required_signals": config.required_signals,
        "decision_maker_threshold": config.dm_threshold,
        "ai_min_raw_score": config.ai_min_raw_score,
        "refresh_days": config.refresh_days,
        "signal_count": len(config.signals),
        "keyword_count": len(config.keywords),
        "query_count": len(config.queries),
        "role_count": len(config.roles),
    }

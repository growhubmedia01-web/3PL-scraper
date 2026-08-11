"""Company + evidence endpoints (§45)."""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company, DecisionMaker, Signal, Source
from app.schemas import (
    CompanyOut, DecisionMakerOut, PaginatedCompanies, SignalOut, SourceOut,
)

router = APIRouter(prefix="/api/companies", tags=["companies"])


@router.get("", response_model=PaginatedCompanies)
def list_companies(
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Search name or domain"),
    status: str | None = None,
    country: str | None = None,
    platform: str | None = None,
    is_ecommerce: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    stmt = select(Company)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Company.name).like(like),
                              func.lower(Company.domain).like(like)))
    if status:
        stmt = stmt.where(Company.status == status)
    if country:
        stmt = stmt.where(Company.country == country.upper())
    if platform:
        stmt = stmt.where(Company.platform == platform)
    if is_ecommerce is not None:
        stmt = stmt.where(Company.is_ecommerce.is_(is_ecommerce))

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(
        stmt.order_by(Company.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    return PaginatedCompanies(
        items=[CompanyOut.model_validate(r) for r in rows], total=total,
        page=page, page_size=page_size,
        pages=max(1, math.ceil(total / page_size)))


def _get_company(db: Session, company_id: str) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    return company


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: str, db: Session = Depends(get_db)):
    return _get_company(db, company_id)


@router.get("/{company_id}/signals", response_model=list[SignalOut])
def get_company_signals(company_id: str, service_id: str | None = None,
                        db: Session = Depends(get_db)):
    _get_company(db, company_id)
    stmt = select(Signal, Source.url).outerjoin(
        Source, Source.id == Signal.source_id
    ).where(Signal.company_id == company_id)
    if service_id:
        stmt = stmt.where(Signal.service_id == service_id)

    out = []
    for signal, source_url in db.execute(stmt.order_by(Signal.detected_at.desc())).all():
        item = SignalOut.model_validate(signal)
        item.source_url = source_url
        out.append(item)
    return out


@router.get("/{company_id}/sources", response_model=list[SourceOut])
def get_company_sources(company_id: str, db: Session = Depends(get_db)):
    _get_company(db, company_id)
    return db.execute(
        select(Source).where(Source.company_id == company_id)
        .order_by(Source.discovered_at.desc())
    ).scalars().all()


@router.get("/{company_id}/decision-makers", response_model=list[DecisionMakerOut])
def get_company_decision_makers(company_id: str, db: Session = Depends(get_db)):
    _get_company(db, company_id)
    return db.execute(
        select(DecisionMaker).where(DecisionMaker.company_id == company_id)
        .order_by(DecisionMaker.role_priority, DecisionMaker.confidence.desc())
    ).scalars().all()

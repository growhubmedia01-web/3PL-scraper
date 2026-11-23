"""Lead list + lead detail (§37, §38, §39)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.engine.service_config import build_config
from app.models import (
    Company, CompanyFact, DecisionMaker, LeadReview, ProductInterest, Service,
    ServiceOpportunity, Signal, Source,
)
from app.schemas import (
    CompanyFactOut, CompanyOut, DecisionMakerOut, LeadReviewCreate,
    OpportunityDetail, OpportunityListItem, OpportunityOut,
    PaginatedOpportunities, ProductInterestOut, ScoreLineOut, SignalOut,
    SourceOut,
)

BUYING_INTEREST_TYPES = ("EXPLICITLY_SEEKING", "RECENTLY_ADDED")
DEFAULT_NO_DEMAND = "Specific product demand not publicly disclosed."

router = APIRouter(prefix="/api/services/{service_ref}/opportunities",
                   tags=["opportunities"])

SORT_OPTIONS = {
    "score": ServiceOpportunity.score.desc(),
    "newest": ServiceOpportunity.created_at.desc(),
    "urgency": ServiceOpportunity.urgency.desc(),
    "updated": ServiceOpportunity.last_analyzed.desc(),
}


def _resolve_service(db: Session, service_ref: str) -> Service:
    service = db.execute(
        select(Service).where(Service.slug == service_ref)
    ).scalar_one_or_none() or db.get(Service, service_ref)
    if service is None:
        raise HTTPException(404, f"Service '{service_ref}' not found")
    return service


def _signal_map(db: Session, service_id: str,
                company_ids: list[str]) -> dict[str, list[str]]:
    if not company_ids:
        return {}
    rows = db.execute(
        select(Signal.company_id, Signal.signal_type)
        .where(Signal.service_id == service_id,
               Signal.company_id.in_(company_ids))
    ).all()
    out: dict[str, list[str]] = {}
    for company_id, signal_type in rows:
        out.setdefault(company_id, []).append(signal_type)
    return out


def _dm_map(db: Session, company_ids: list[str]) -> dict[str, DecisionMaker]:
    if not company_ids:
        return {}
    rows = db.execute(
        select(DecisionMaker).where(DecisionMaker.company_id.in_(company_ids))
        .order_by(DecisionMaker.role_priority, DecisionMaker.confidence.desc())
    ).scalars().all()
    out: dict[str, DecisionMaker] = {}
    for row in rows:
        out.setdefault(row.company_id, row)
    return out


def latest_signal_map(db: Session, service_id: str, company_ids: list[str],
                      signal_dimensions: dict[str, str]
                      ) -> dict[str, tuple[str, datetime]]:
    """Most recent buying (intent-dimension) signal per company."""
    if not company_ids:
        return {}
    rows = db.execute(
        select(Signal.company_id, Signal.signal_type, Signal.detected_at)
        .where(Signal.service_id == service_id,
               Signal.company_id.in_(company_ids))
    ).all()
    out: dict[str, tuple[str, datetime]] = {}
    for company_id, signal_type, detected_at in rows:
        if signal_dimensions.get(signal_type, "intent") != "intent":
            continue
        prior = out.get(company_id)
        if prior is None or _aware(detected_at) > _aware(prior[1]):
            out[company_id] = (signal_type, detected_at)
    return out


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def interest_map(db: Session, service_id: str, company_ids: list[str]
                 ) -> dict[str, list[ProductInterest]]:
    if not company_ids:
        return {}
    rows = db.execute(
        select(ProductInterest)
        .where(ProductInterest.service_id == service_id,
               ProductInterest.company_id.in_(company_ids))
        .order_by(ProductInterest.confidence.desc())
    ).scalars().all()
    out: dict[str, list[ProductInterest]] = {}
    for row in rows:
        out.setdefault(row.company_id, []).append(row)
    return out


def demand_summary(rows: list[ProductInterest], message: str) -> str:
    buying = [r for r in rows
              if r.interest_type in BUYING_INTEREST_TYPES and r.category]
    if not buying:
        return message
    parts = []
    for r in buying[:4]:
        parts.append(f"{r.subcategory or r.category} "
                     f"({r.interest_type.lower().replace('_', ' ')})")
    return "; ".join(dict.fromkeys(parts))


def buying_categories(rows: list[ProductInterest]) -> list[str]:
    return list(dict.fromkeys(
        r.category for r in rows
        if r.interest_type in BUYING_INTEREST_TYPES and r.category))


def _evidence_counts(db: Session, company_ids: list[str]) -> dict[str, int]:
    if not company_ids:
        return {}
    rows = db.execute(
        select(Source.company_id, func.count(Source.id))
        .where(Source.company_id.in_(company_ids))
        .group_by(Source.company_id)
    ).all()
    return {cid: count for cid, count in rows}


@router.get("", response_model=PaginatedOpportunities)
def list_opportunities(
    service_ref: str,
    db: Session = Depends(get_db),
    q: str | None = Query(None, description="Search company name or domain"),
    country: str | None = None,
    intent: str | None = Query(None, description="LOW|POSSIBLE|GOOD|STRONG|HOT"),
    urgency: str | None = None,
    industry: str | None = None,
    platform: str | None = None,
    business_model: str | None = Query(
        None, description="dtc|wholesale|manufacturer|retail|marketplace|"
                          "subscription|importer|multi_channel"),
    signal: str | None = Query(None, description="Filter by signal_type"),
    min_score: float | None = Query(None, ge=0, le=100),
    max_score: float | None = Query(None, ge=0, le=100),
    has_decision_maker: bool | None = None,
    discovered_after: datetime | None = None,
    discovered_within_days: int | None = Query(None, ge=1, le=365),
    state: str | None = Query(None, description="US state of headquarters, e.g. TX"),
    employee_band: str | None = Query(
        None, description="micro|small|mid_market|large|unknown"),
    company_type: str | None = None,
    product_category: str | None = Query(
        None, description="Category with EXPLICITLY_SEEKING/RECENTLY_ADDED evidence"),
    interest_type: str | None = Query(
        None, description="EXPLICITLY_SEEKING|RECENTLY_ADDED|CURRENTLY_CARRIED|INFERRED_FIT"),
    vehicle_segment: str | None = None,
    signal_within_days: int | None = Query(
        None, ge=1, le=730, description="Signal freshness: detected within N days"),
    sort: str = Query("score", description="score|newest|urgency|updated|evidence"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    service = _resolve_service(db, service_ref)

    stmt = (select(ServiceOpportunity, Company)
            .join(Company, Company.id == ServiceOpportunity.company_id)
            .where(ServiceOpportunity.service_id == service.id,
                   Company.status != "rejected"))   # re-analysed and rejected

    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Company.name).like(like),
                              func.lower(Company.domain).like(like)))
    if country:
        stmt = stmt.where(Company.country == country.upper())
    if intent:
        stmt = stmt.where(ServiceOpportunity.intent_level == intent.upper())
    if urgency:
        stmt = stmt.where(ServiceOpportunity.urgency == urgency.lower())
    if industry:
        stmt = stmt.where(Company.industry == industry)
    if platform:
        stmt = stmt.where(Company.platform == platform)
    if business_model:
        stmt = stmt.where(Company.business_model == business_model)
    if min_score is not None:
        stmt = stmt.where(ServiceOpportunity.score >= min_score)
    if max_score is not None:
        stmt = stmt.where(ServiceOpportunity.score <= max_score)
    if discovered_after:
        stmt = stmt.where(Company.created_at >= discovered_after)
    if discovered_within_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=discovered_within_days)
        stmt = stmt.where(Company.created_at >= cutoff)
    if signal:
        sub = select(Signal.company_id).where(
            Signal.service_id == service.id, Signal.signal_type == signal)
        stmt = stmt.where(ServiceOpportunity.company_id.in_(sub))
    if has_decision_maker is not None:
        sub = select(DecisionMaker.company_id)
        stmt = stmt.where(ServiceOpportunity.company_id.in_(sub)
                          if has_decision_maker
                          else ServiceOpportunity.company_id.not_in(sub))
    if state:
        stmt = stmt.where(Company.headquarters_state == state.upper())
    if employee_band:
        stmt = stmt.where(Company.employee_band.is_(None)
                          if employee_band == "unknown"
                          else Company.employee_band == employee_band)
    if company_type:
        stmt = stmt.where(Company.company_type.is_(None)
                          if company_type == "unknown"
                          else Company.company_type == company_type)
    if product_category or interest_type:
        sub = select(ProductInterest.company_id).where(
            ProductInterest.service_id == service.id)
        if product_category:
            sub = sub.where(ProductInterest.category == product_category)
            if not interest_type:
                sub = sub.where(ProductInterest.interest_type.in_(
                    BUYING_INTEREST_TYPES))
        if interest_type:
            sub = sub.where(ProductInterest.interest_type == interest_type.upper())
        stmt = stmt.where(ServiceOpportunity.company_id.in_(sub))
    if vehicle_segment:
        # JSON containment differs across dialects; a text match on the
        # serialized list is portable and exact enough for a filter.
        sub = select(ProductInterest.company_id).where(
            ProductInterest.service_id == service.id,
            func.cast(ProductInterest.vehicle_segments, String).like(
                f'%"{vehicle_segment}"%'))
        stmt = stmt.where(ServiceOpportunity.company_id.in_(sub))
    if signal_within_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=signal_within_days)
        sub = select(Signal.company_id).where(
            Signal.service_id == service.id, Signal.detected_at >= cutoff)
        if signal:
            sub = sub.where(Signal.signal_type == signal)
        stmt = stmt.where(ServiceOpportunity.company_id.in_(sub))

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())).scalar_one()

    order = SORT_OPTIONS.get(sort, ServiceOpportunity.score.desc())
    rows = db.execute(
        stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)
    ).all()

    company_ids = [c.id for _, c in rows]
    signals = _signal_map(db, service.id, company_ids)
    dms = _dm_map(db, company_ids)
    evidence = _evidence_counts(db, company_ids)
    cfg = service.config or {}
    dimensions = cfg.get("signal_dimensions") or {}
    latest = latest_signal_map(db, service.id, company_ids, dimensions)
    interests = interest_map(db, service.id, company_ids) \
        if cfg.get("product_taxonomy") else {}
    no_demand = cfg.get("no_product_demand_message") or DEFAULT_NO_DEMAND
    qual = cfg.get("qualification") or {}
    verify_location = bool(qual.get("require_country_evidence"))
    min_country_conf = float(qual.get("min_country_confidence", 0.5))

    items = []
    for opportunity, company in rows:
        dm = dms.get(company.id)
        items.append(OpportunityListItem(
            id=opportunity.id, company_id=company.id, company_name=company.name,
            domain=company.domain, website=company.website,
            country=company.country, industry=company.industry,
            location_unverified=verify_location and float(
                company.country_confidence or 0) < min_country_conf,
            platform=company.platform,
            business_model=company.business_model,
            score=float(opportunity.score),
            intent_level=opportunity.intent_level, urgency=opportunity.urgency,
            likely_need=opportunity.likely_need or [],
            signal_types=sorted(signals.get(company.id, [])),
            signal_count=len(signals.get(company.id, [])),
            evidence_count=evidence.get(company.id, 0),
            decision_maker_name=dm.name if dm else None,
            decision_maker_title=dm.job_title if dm else None,
            decision_maker_confidence=float(dm.confidence) if dm else None,
            has_decision_maker=dm is not None,
            last_analyzed=opportunity.last_analyzed,
            created_at=opportunity.created_at,
            headquarters=company.headquarters,
            headquarters_state=company.headquarters_state,
            employee_band=company.employee_band,
            company_type=company.company_type,
            latest_signal_type=latest.get(company.id, (None, None))[0],
            latest_signal_at=latest.get(company.id, (None, None))[1],
            product_categories=buying_categories(interests.get(company.id, [])),
            product_demand_summary=(
                demand_summary(interests.get(company.id, []), no_demand)
                if cfg.get("product_taxonomy") else None),
            confidence=opportunity.confidence))

    if sort == "evidence":
        items.sort(key=lambda i: i.evidence_count, reverse=True)

    return PaginatedOpportunities(
        items=items, total=total, page=page, page_size=page_size,
        pages=max(1, math.ceil(total / page_size)))


@router.get("/{opportunity_id}", response_model=OpportunityDetail)
def get_opportunity(service_ref: str, opportunity_id: str,
                    db: Session = Depends(get_db)):
    service = _resolve_service(db, service_ref)
    opportunity = db.get(ServiceOpportunity, opportunity_id)
    if opportunity is None or opportunity.service_id != service.id:
        raise HTTPException(404, "Opportunity not found")

    company = db.get(Company, opportunity.company_id)

    signal_rows = db.execute(
        select(Signal, Source.url)
        .outerjoin(Source, Source.id == Signal.source_id)
        .where(Signal.company_id == company.id, Signal.service_id == service.id)
        .order_by(Signal.confidence.desc())
    ).all()
    signals = []
    for signal, source_url in signal_rows:
        item = SignalOut.model_validate(signal)
        item.source_url = source_url
        signals.append(item)

    sources = db.execute(
        select(Source).where(Source.company_id == company.id)
        .order_by(Source.source_type)
    ).scalars().all()

    people = db.execute(
        select(DecisionMaker).where(DecisionMaker.company_id == company.id)
        .order_by(DecisionMaker.role_priority, DecisionMaker.confidence.desc())
    ).scalars().all()

    interest_rows = db.execute(
        select(ProductInterest)
        .where(ProductInterest.company_id == company.id,
               ProductInterest.service_id == service.id)
        .order_by(ProductInterest.confidence.desc())
    ).scalars().all()
    facts = db.execute(
        select(CompanyFact).where(CompanyFact.company_id == company.id)
        .order_by(CompanyFact.fact_type, CompanyFact.confidence.desc())
    ).scalars().all()
    cfg = service.config or {}
    qual = cfg.get("qualification") or {}

    return OpportunityDetail(
        location_unverified=bool(qual.get("require_country_evidence")) and float(
            company.country_confidence or 0) < float(
                qual.get("min_country_confidence", 0.5)),
        product_interests=[ProductInterestOut.model_validate(r)
                           for r in interest_rows],
        company_facts=[CompanyFactOut.model_validate(f) for f in facts],
        product_demand_summary=(
            demand_summary(list(interest_rows),
                           cfg.get("no_product_demand_message") or DEFAULT_NO_DEMAND)
            if cfg.get("product_taxonomy") else None),
        signal_dimensions=dict(cfg.get("signal_dimensions") or {}),
        opportunity=OpportunityOut.model_validate(opportunity),
        company=CompanyOut.model_validate(company),
        signals=signals,
        sources=[SourceOut.model_validate(s) for s in sources],
        decision_makers=[DecisionMakerOut.model_validate(p) for p in people],
        score_breakdown=[ScoreLineOut(**line)
                         for line in (opportunity.score_breakdown or [])],
        ai_analysis=opportunity.ai_analysis)


@router.post("/{opportunity_id}/review")
def review_lead(service_ref: str, opportunity_id: str,
                payload: LeadReviewCreate, db: Session = Depends(get_db)):
    """Human labelling for Phase 9 validation (§66)."""
    _resolve_service(db, service_ref)
    if db.get(ServiceOpportunity, opportunity_id) is None:
        raise HTTPException(404, "Opportunity not found")
    review = LeadReview(opportunity_id=opportunity_id, label=payload.label,
                        notes=payload.notes, reviewer=payload.reviewer)
    db.add(review)
    db.commit()
    return {"ok": True, "id": review.id}

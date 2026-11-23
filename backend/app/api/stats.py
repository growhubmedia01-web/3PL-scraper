"""Dashboard metrics (§36, §56)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import (
    ApiUsage, Company, CrawlJob, DecisionMaker, ProductInterest, Service,
    ServiceOpportunity, Signal,
)
from app.schemas import DashboardStats

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=DashboardStats)
def dashboard(service: str = Query(settings.default_service_slug),
              db: Session = Depends(get_db)):
    svc = db.execute(
        select(Service).where(Service.slug == service)).scalar_one_or_none()
    if svc is None:
        raise HTTPException(404, f"Service '{service}' not found")

    stats = DashboardStats()
    stats.total_companies = db.execute(
        select(func.count(Company.id))).scalar_one()
    stats.companies_crawled = db.execute(
        select(func.count(Company.id)).where(
            Company.last_crawled_at.is_not(None))).scalar_one()
    stats.companies_rejected = db.execute(
        select(func.count(Company.id)).where(
            Company.status == "rejected")).scalar_one()

    opp_where = ServiceOpportunity.service_id == svc.id
    stats.total_opportunities = db.execute(
        select(func.count(ServiceOpportunity.id)).where(opp_where)).scalar_one()

    intent_rows = db.execute(
        select(ServiceOpportunity.intent_level, func.count(ServiceOpportunity.id))
        .where(opp_where).group_by(ServiceOpportunity.intent_level)
    ).all()
    intent_counts = {level: count for level, count in intent_rows}
    stats.hot_leads = intent_counts.get("HOT", 0)
    stats.strong_leads = intent_counts.get("STRONG", 0)
    stats.good_leads = intent_counts.get("GOOD", 0)
    stats.by_intent = [{"intent_level": level, "count": count}
                       for level, count in sorted(
                           intent_rows, key=lambda r: r[1], reverse=True)]

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    stats.new_leads_7d = db.execute(
        select(func.count(ServiceOpportunity.id))
        .where(opp_where, ServiceOpportunity.created_at >= cutoff)).scalar_one()

    avg = db.execute(
        select(func.avg(ServiceOpportunity.score)).where(opp_where)).scalar_one()
    stats.average_score = round(float(avg), 2) if avg else 0.0

    country_rows = db.execute(
        select(Company.country, func.count(Company.id))
        .where(Company.country.is_not(None))
        .group_by(Company.country).order_by(func.count(Company.id).desc())
    ).all()
    stats.countries = len(country_rows)
    stats.by_country = [{"country": c, "count": n} for c, n in country_rows[:20]]

    signal_rows = db.execute(
        select(Signal.signal_type, func.count(Signal.id))
        .where(Signal.service_id == svc.id)
        .group_by(Signal.signal_type).order_by(func.count(Signal.id).desc())
    ).all()
    stats.signals_detected = sum(n for _, n in signal_rows)
    stats.by_signal = [{"signal_type": s, "count": n} for s, n in signal_rows]

    try:
        model_rows = db.execute(
            select(Company.business_model, func.count(Company.id))
            .where(Company.business_model.is_not(None))
            .group_by(Company.business_model)
            .order_by(func.count(Company.id).desc())
        ).all()
        stats.by_business_model = [{"business_model": m, "count": n}
                                   for m, n in model_rows]
    except Exception:
        db.rollback()
        stats.by_business_model = []

    # 007: supplier-opportunity breakdowns, scoped to this service's leads.
    try:
        opp_companies = select(ServiceOpportunity.company_id).where(opp_where)
        for attr, key in (("company_type", "by_company_type"),
                          ("employee_band", "by_employee_band")):
            column = getattr(Company, attr)
            rows = db.execute(
                select(column, func.count(Company.id))
                .where(Company.id.in_(opp_companies))
                .group_by(column).order_by(func.count(Company.id).desc())
            ).all()
            setattr(stats, key, [{attr: (v or "unknown"), "count": n}
                                 for v, n in rows])
        rows = db.execute(
            select(ProductInterest.category,
                   func.count(func.distinct(ProductInterest.company_id)))
            .where(ProductInterest.service_id == svc.id,
                   ProductInterest.category.is_not(None),
                   ProductInterest.interest_type.in_(
                       ("EXPLICITLY_SEEKING", "RECENTLY_ADDED")))
            .group_by(ProductInterest.category)
            .order_by(func.count(func.distinct(ProductInterest.company_id)).desc())
        ).all()
        stats.by_product_category = [{"category": c, "count": n} for c, n in rows]
        rows = db.execute(
            select(ProductInterest.interest_type, func.count(ProductInterest.id))
            .where(ProductInterest.service_id == svc.id)
            .group_by(ProductInterest.interest_type)
        ).all()
        stats.by_interest_type = [{"interest_type": t, "count": n} for t, n in rows]
    except Exception:
        db.rollback()

    stats.decision_makers_identified = db.execute(
        select(func.count(DecisionMaker.id))).scalar_one()

    completed = db.execute(
        select(func.count(CrawlJob.id)).where(
            CrawlJob.status == "completed")).scalar_one()
    attempted = db.execute(
        select(func.count(CrawlJob.id)).where(
            CrawlJob.status.in_(("completed", "failed")))).scalar_one()
    stats.crawl_success_rate = round(completed / attempted * 100, 1) if attempted else 0.0

    ai_rows = db.execute(
        select(ApiUsage.success, func.count(ApiUsage.id))
        .where(ApiUsage.operation.like("analyze%")).group_by(ApiUsage.success)
    ).all()
    for success, count in ai_rows:
        if success:
            stats.ai_calls += count
        else:
            stats.ai_failures += count

    cost = db.execute(select(func.sum(ApiUsage.cost_usd))).scalar_one()
    stats.estimated_cost_usd = round(float(cost), 4) if cost else 0.0
    return stats


@router.get("/health")
def health(db: Session = Depends(get_db)):
    """Readiness detail the dashboard shows as a setup checklist."""
    from app.providers.llm.factory import LLMService
    from app.providers.search.factory import SearchService
    from app.providers.search.serper import _build_key_pool as serper_pool
    from app.providers.search.exa import _build_key_pool as exa_pool

    try:
        db.execute(select(func.count(Service.id))).scalar_one()
        db_ok, db_error = True, None
    except Exception as exc:
        db_ok, db_error = False, str(exc)[:300]

    from app.db import engine
    from app.schema_check import check_schema
    report = check_schema(engine)

    search = SearchService(db)
    llm = LLMService(db)
    return {
        "database": {"ok": db_ok, "error": db_error,
                     "url_configured": settings.db_configured},
        "schema": {
            "ok": report.ok,
            "missing_tables": report.missing_tables,
            "missing_columns": [f"{t}.{c}" for t, c in report.missing_columns],
            "run_migrations": report.required_migrations(),
        },
        "search": {
            "ok": search.has_provider,
            "providers": [p.name for p in search.chain],
            "serper_keys_count": len(serper_pool()),
            "exa_keys_count": len(exa_pool()),
        },
        "llm": {"ok": llm.available, "providers": [p.name for p in llm.chain]},
        "environment": settings.environment,
    }

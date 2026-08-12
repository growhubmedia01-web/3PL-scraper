"""CSV export (§40).

Column set is fixed by the PRD and contains NO email columns. The test suite
asserts this - see tests/test_export_has_no_email_columns.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import (
    Company, DecisionMaker, Service, ServiceOpportunity, Signal, Source,
)

router = APIRouter(prefix="/api/export", tags=["export"])

CSV_COLUMNS = [
    "Company", "Website", "Country", "Industry", "Business Model",
    "Sales Channels", "Platform",
    "Score", "Intent Level", "Urgency", "Signals", "Likely Services",
    "Target Country", "Decision Maker", "Job Title", "Public Profile URL",
    "Decision Maker Confidence", "Evidence URLs", "Last Updated",
]

FORBIDDEN_SUBSTRINGS = ("email", "e-mail", "mail")


def _assert_no_email_columns() -> None:
    for column in CSV_COLUMNS:
        lowered = column.lower()
        if any(token in lowered for token in FORBIDDEN_SUBSTRINGS):
            raise RuntimeError(
                f"Export column '{column}' violates the no-email constraint (§40)")


@router.get("")
def export_csv(
    service: str = Query(settings.default_service_slug),
    intent: str | None = None,
    country: str | None = None,
    business_model: str | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    has_decision_maker: bool | None = None,
    limit: int = Query(5000, ge=1, le=50000),
    db: Session = Depends(get_db),
):
    _assert_no_email_columns()

    svc = db.execute(
        select(Service).where(Service.slug == service)).scalar_one_or_none()
    if svc is None:
        raise HTTPException(404, f"Service '{service}' not found")

    stmt = (select(ServiceOpportunity, Company)
            .join(Company, Company.id == ServiceOpportunity.company_id)
            .where(ServiceOpportunity.service_id == svc.id))
    if intent:
        stmt = stmt.where(ServiceOpportunity.intent_level == intent.upper())
    if country:
        stmt = stmt.where(Company.country == country.upper())
    if business_model:
        stmt = stmt.where(Company.business_model == business_model)
    if min_score is not None:
        stmt = stmt.where(ServiceOpportunity.score >= min_score)
    if has_decision_maker is not None:
        sub = select(DecisionMaker.company_id)
        stmt = stmt.where(ServiceOpportunity.company_id.in_(sub)
                          if has_decision_maker
                          else ServiceOpportunity.company_id.not_in(sub))

    rows = db.execute(
        stmt.order_by(ServiceOpportunity.score.desc()).limit(limit)).all()
    company_ids = [c.id for _, c in rows]

    signals: dict[str, list[str]] = {}
    if company_ids:
        for company_id, signal_type in db.execute(
            select(Signal.company_id, Signal.signal_type)
            .where(Signal.service_id == svc.id,
                   Signal.company_id.in_(company_ids))
        ).all():
            signals.setdefault(company_id, []).append(signal_type)

    people: dict[str, DecisionMaker] = {}
    evidence: dict[str, list[str]] = {}
    if company_ids:
        for person in db.execute(
            select(DecisionMaker).where(DecisionMaker.company_id.in_(company_ids))
            .order_by(DecisionMaker.role_priority, DecisionMaker.confidence.desc())
        ).scalars().all():
            people.setdefault(person.company_id, person)
        for source in db.execute(
            select(Source).where(Source.company_id.in_(company_ids))
        ).scalars().all():
            evidence.setdefault(source.company_id, []).append(source.url)

    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)

    for opportunity, company in rows:
        person = people.get(company.id)
        writer.writerow([
            company.name or company.domain,
            company.website or f"https://{company.domain}",
            company.country or "",
            company.industry or "",
            company.business_model or "",
            "; ".join(company.sales_channels or []),
            company.platform or "",
            f"{float(opportunity.score):.1f}",
            opportunity.intent_level,
            opportunity.urgency or "",
            "; ".join(sorted(signals.get(company.id, []))),
            "; ".join(opportunity.likely_need or []),
            "; ".join(opportunity.target_country or []),
            person.name if person else "",
            person.job_title if person else "",
            person.profile_url if person else "",
            f"{float(person.confidence):.2f}" if person else "",
            " | ".join(evidence.get(company.id, [])[:10]),
            opportunity.last_analyzed.isoformat() if opportunity.last_analyzed else "",
        ])

    buffer.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"{service}-leads-{stamp}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

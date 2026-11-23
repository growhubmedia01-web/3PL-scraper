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
from app.api.opportunities import (
    DEFAULT_NO_DEMAND, demand_summary, interest_map, latest_signal_map,
)
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
    # 007 - distributor / product-interest intelligence (appended so the
    # legacy column order is unchanged)
    "Headquarters", "HQ State", "Company Type", "Employee Band",
    "Size Source URL", "Size Confidence",
    "Latest Buying Signal", "Latest Signal Date",
    "Product Demand Summary", "Explicitly Seeking", "Recently Added",
    "Currently Carried", "Inferred Fit", "Vehicle Segments",
    "Brands Involved", "Product Evidence URLs", "AI Confidence",
    # 009 - product attributes as STATED in the evidence (format, protein,
    # life stage, the company's own claims). "Vehicle Segments" above holds
    # the service's segments - species for the pet service.
    "Product Attributes",
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
            .where(ServiceOpportunity.service_id == svc.id,
                   Company.status != "rejected"))   # re-analysed and rejected
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
        # Only company_id/url are ever used below (and only the first 10 per
        # company at that) - select(Source) was pulling every column,
        # including content/excerpt text blobs, across 50k+ rows for a
        # full-size export. That alone was ~15s of an ~18s request that hit
        # Render's timeout; two columns instead of the whole row cuts it to
        # under 2s for the same row count.
        for company_id, url in db.execute(
            select(Source.company_id, Source.url)
            .where(Source.company_id.in_(company_ids))
        ).all():
            evidence.setdefault(company_id, []).append(url)

    cfg = svc.config or {}
    latest = latest_signal_map(db, svc.id, company_ids,
                               cfg.get("signal_dimensions") or {})
    interests = interest_map(db, svc.id, company_ids)
    no_demand = cfg.get("no_product_demand_message") or DEFAULT_NO_DEMAND

    def _labels(rows_, kind):
        return "; ".join(dict.fromkeys(
            f"{r.category} > {r.subcategory}" if r.subcategory else r.category
            for r in rows_ if r.interest_type == kind and r.category))

    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)

    for opportunity, company in rows:
        person = people.get(company.id)
        pi = interests.get(company.id, [])
        sig_type, sig_at = latest.get(company.id, (None, None))
        segments = list(dict.fromkeys(seg for r in pi for seg in (r.vehicle_segments or [])))
        brands = list(dict.fromkeys(r.brand for r in pi if r.brand))
        pi_urls = list(dict.fromkeys(r.source_url for r in pi if r.source_url))
        attrs: dict[str, list[str]] = {}
        for r in pi:
            for name, values in (getattr(r, "attributes", None) or {}).items():
                attrs.setdefault(name, [])
                attrs[name] += [v for v in values if v not in attrs[name]]
        attr_text = "; ".join(f"{name.replace('_', ' ')}: {', '.join(values)}"
                              for name, values in sorted(attrs.items()) if values)
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
            company.headquarters or "",
            company.headquarters_state or "",
            company.company_type or "",
            company.employee_band or "unknown",
            company.size_source_url or "",
            f"{company.size_confidence:.2f}" if company.size_confidence else "",
            sig_type or "",
            sig_at.isoformat() if sig_at else "",
            demand_summary(pi, no_demand) if cfg.get("product_taxonomy") else "",
            _labels(pi, "EXPLICITLY_SEEKING"),
            _labels(pi, "RECENTLY_ADDED"),
            _labels(pi, "CURRENTLY_CARRIED"),
            _labels(pi, "INFERRED_FIT"),
            "; ".join(segments),
            "; ".join(brands),
            " | ".join(pi_urls[:10]),
            f"{opportunity.confidence:.2f}" if opportunity.confidence is not None else "",
            attr_text,
        ])

    buffer.seek(0)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    filename = f"{service}-leads-{stamp}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

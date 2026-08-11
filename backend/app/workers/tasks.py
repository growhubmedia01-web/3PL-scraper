"""Celery tasks (§41).

Each task owns its own DB session and never lets one company's failure abort
the batch (§55).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select

from app.config import settings
from app.db import session_scope
from app.engine import pipeline as pipeline_engine
from app.engine import scoring
from app.engine.discovery import queued_companies, run_discovery
from app.engine.service_config import load_service_config
from app.engine.signals import load_signals
from app.models import (
    Company, DecisionMaker, SearchCache, ServiceOpportunity,
)
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.discover_companies", bind=True,
                 max_retries=2)
def discover_companies(self, service_slug: str | None = None,
                       limit: int | None = None,
                       country: str | None = None) -> dict:
    service_slug = service_slug or settings.default_service_slug
    try:
        with session_scope() as db:
            config = load_service_config(db, service_slug)
            stats = run_discovery(db, config, limit=limit, country=country)
            return stats.as_dict()
    except Exception as exc:
        log.exception("discover_companies failed")
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="app.workers.tasks.process_company_task", bind=True,
                 max_retries=2)
def process_company_task(self, company_id: str, service_slug: str | None = None,
                         force_crawl: bool = False, skip_external: bool = False,
                         allow_ai: bool = True) -> dict:
    try:
        with session_scope() as db:
            config = load_service_config(db, service_slug)
            company = db.get(Company, company_id)
            if company is None:
                return {"error": "company not found", "company_id": company_id}
            result = pipeline_engine.process_company(
                db, company, config, force_crawl=force_crawl,
                skip_external=skip_external, allow_ai=allow_ai)
            return {
                "domain": result.domain, "ok": result.ok,
                "rejected": result.rejected, "reason": result.reason,
                "score": result.score, "intent_level": result.intent_level,
                "signals": result.signals_found,
                "decision_makers": result.decision_makers_found,
                "error": result.error,
            }
    except Exception as exc:
        log.exception("process_company_task failed for %s", company_id)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="app.workers.tasks.process_queue_task")
def process_queue_task(service_slug: str | None = None, limit: int = 25) -> dict:
    """Fan out queued companies as individual tasks so one slow site does not
    hold the whole batch."""
    with session_scope() as db:
        companies = queued_companies(db, limit=limit)
        ids = [c.id for c in companies]
    for company_id in ids:
        process_company_task.delay(company_id, service_slug, False, False, True)
    return {"dispatched": len(ids)}


@celery_app.task(name="app.workers.tasks.refresh_stale_task")
def refresh_stale_task(service_slug: str | None = None, limit: int = 50) -> dict:
    """§52: re-crawl and re-analyze on a cadence driven by intent level."""
    with session_scope() as db:
        config = load_service_config(db, service_slug)
        companies = pipeline_engine.stale_opportunities(db, config, limit=limit)
        ids = [c.id for c in companies]
    for company_id in ids:
        process_company_task.delay(company_id, service_slug, True, False, True)
    return {"refreshed": len(ids)}


@celery_app.task(name="app.workers.tasks.recalculate_scores_task")
def recalculate_scores_task(service_slug: str | None = None) -> dict:
    """Re-score from stored signals without re-crawling.

    This is what makes freshness decay real: a funding signal detected 200 days
    ago must be worth less today even if nothing about the company changed.
    """
    updated = 0
    with session_scope() as db:
        config = load_service_config(db, service_slug)
        opportunities = db.execute(
            select(ServiceOpportunity)
            .where(ServiceOpportunity.service_id == config.id)
        ).scalars().all()

        for opportunity in opportunities:
            company = db.get(Company, opportunity.company_id)
            if company is None:
                continue
            signals = load_signals(db, company.id, config.id)
            probability = None
            if opportunity.ai_analysis:
                probability = opportunity.ai_analysis.get("service_probability")
            result = scoring.calculate(db, company, signals, config,
                                       ai_probability=probability)
            scoring.upsert_opportunity(db, company, config, result,
                                       opportunity.ai_analysis)
            updated += 1
    log.info("Recalculated %d opportunities", updated)
    return {"updated": updated}


@celery_app.task(name="app.workers.tasks.prune_cache_task")
def prune_cache_task() -> dict:
    with session_scope() as db:
        result = db.execute(
            delete(SearchCache).where(
                SearchCache.expires_at < datetime.now(timezone.utc)))
        return {"pruned": result.rowcount or 0}


@celery_app.task(name="app.workers.tasks.enforce_retention_task")
def enforce_retention_task(max_age_days: int = 365) -> dict:
    """GDPR data minimisation: delete decision-maker records attached to
    companies that have not been re-analyzed within the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    removed = 0
    with session_scope() as db:
        stale_company_ids = [
            row[0] for row in db.execute(
                select(Company.id).where(
                    Company.last_crawled_at.is_not(None),
                    Company.last_crawled_at < cutoff)
            ).all()
        ]
        if stale_company_ids:
            rows = db.execute(
                select(DecisionMaker).where(
                    DecisionMaker.company_id.in_(stale_company_ids))
            ).scalars().all()
            for row in rows:
                db.delete(row)
                removed += 1
    log.info("Retention sweep removed %d decision-maker records", removed)
    return {"removed": removed}


@celery_app.task(name="app.workers.tasks.notify_hot_lead")
def notify_hot_lead(opportunity_id: str, webhook_url: str | None = None) -> dict:
    """§43: optional n8n / Slack notification. The platform works without it."""
    url = webhook_url
    if not url:
        return {"skipped": "no webhook configured"}
    with session_scope() as db:
        opportunity = db.get(ServiceOpportunity, opportunity_id)
        if opportunity is None:
            return {"error": "not found"}
        company = db.get(Company, opportunity.company_id)
        person = db.execute(
            select(DecisionMaker)
            .where(DecisionMaker.company_id == company.id)
            .order_by(DecisionMaker.role_priority)
        ).scalars().first()
        payload = {
            "company": company.name or company.domain,
            "website": company.website,
            "country": company.country,
            "score": float(opportunity.score),
            "intent": opportunity.intent_level,
            "urgency": opportunity.urgency,
            "likely_need": opportunity.likely_need,
            "decision_maker": person.name if person else None,
            "job_title": person.job_title if person else None,
            "profile_url": person.profile_url if person else None,
        }
    try:
        httpx.post(url, json=payload, timeout=10)
        return {"sent": True}
    except Exception as exc:
        log.warning("Webhook failed: %s", exc)
        return {"sent": False, "error": str(exc)}

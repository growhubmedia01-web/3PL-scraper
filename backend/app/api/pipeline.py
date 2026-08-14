"""Pipeline trigger endpoints (§45).

Long operations are dispatched to Celery when a broker is reachable; otherwise
they run in a FastAPI BackgroundTask so the product works without Redis (§41).
The request never blocks on crawling or LLM calls either way.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, session_scope
from app.engine import pipeline as pipeline_engine
from app.engine.discovery import add_company_manually, queued_companies, run_discovery
from app.engine.service_config import load_service_config
from app.models import Company, DiscoveryQuery, PipelineRun
from app.schemas import (
    AnalyzeRequest, DiscoveryRunRequest, ManualCompanyRequest,
    QueryLibraryStats, TaskAccepted,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["pipeline"])


def _dispatch(task_name: str, background: BackgroundTasks,
              celery_fn, local_fn, *args) -> str | None:
    """Prefer Celery; fall back to an in-process background task."""
    try:
        from app.workers.celery_app import celery_app
        if celery_app.control.inspect(timeout=0.5).ping():
            result = celery_fn.delay(*args)
            log.info("Dispatched %s to Celery (%s)", task_name, result.id)
            return result.id
    except Exception as exc:
        log.info("Celery unavailable (%s); running %s in-process", exc, task_name)
    background.add_task(local_fn, *args)
    return None


# ---------------------------------------------------------------------
# local runners (used when Celery is not available)
# ---------------------------------------------------------------------
def _local_discovery(service_slug: str, limit: int | None,
                     country: str | None, tier: int | None = None,
                     max_queries: int | None = None) -> None:
    with session_scope() as db:
        config = load_service_config(db, service_slug)
        run_discovery(db, config, limit=limit, country=country,
                      tier=tier, max_queries=max_queries)


def _local_process_company(company_id: str, service_slug: str,
                           force_crawl: bool, skip_external: bool,
                           allow_ai: bool) -> None:
    with session_scope() as db:
        config = load_service_config(db, service_slug)
        company = db.get(Company, company_id)
        if company:
            pipeline_engine.process_company(
                db, company, config, force_crawl=force_crawl,
                skip_external=skip_external, allow_ai=allow_ai)


def _local_process_queue(service_slug: str, limit: int,
                         max_seconds: float | None = None) -> dict:
    """Drain part of the queue and record the outcome.

    Every invocation writes a `pipeline_runs` row. Without that there is no
    way to tell whether an external scheduler is actually calling this - the
    only evidence would be the crawled count creeping up, which says nothing
    about when or how often.
    """
    from datetime import datetime, timezone

    from app.models import PipelineRun

    with session_scope() as db:
        config = load_service_config(db, service_slug)
        run = PipelineRun(service_id=config.id, run_type="process_queue",
                          status="running")
        db.add(run)
        db.flush()

        companies = queued_companies(db, limit=limit)
        try:
            batch = pipeline_engine.process_batch(
                db, companies, config, max_seconds=max_seconds)
            stats = batch.as_dict()
            stats["queued_at_start"] = len(companies)
            status = "completed"
            error = None
        except Exception as exc:
            stats = {"queued_at_start": len(companies)}
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            log.exception("process_queue failed")
            # The DB cancelled our statement (lock timeout, etc.), which puts
            # the session into a rolled-back state. We must explicitly rollback
            # before issuing any further SQL, or SQLAlchemy will raise
            # PendingRollbackError on the db.merge() below.
            db.rollback()

        # process_batch commits per company, so re-attach the run row.
        run = db.merge(run)
        run.status = status
        run.error = error
        run.stats = stats
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        return stats


# ---------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------
@router.post("/discovery/run", response_model=TaskAccepted)
def trigger_discovery(payload: DiscoveryRunRequest,
                      background: BackgroundTasks,
                      db: Session = Depends(get_db)):
    slug = payload.service_slug or settings.default_service_slug
    try:
        config = load_service_config(db, slug)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc

    if not payload.run_async:
        stats = run_discovery(db, config, limit=payload.limit,
                              country=payload.country, tier=payload.tier,
                              max_queries=payload.max_queries)
        db.commit()
        return TaskAccepted(message="Discovery complete", result=stats.as_dict())

    from app.workers import tasks
    task_id = _dispatch("discovery", background, tasks.discover_companies,
                        _local_discovery, slug, payload.limit,
                        payload.country, payload.tier, payload.max_queries)
    tier_note = f" tier {payload.tier}" if payload.tier else ""
    return TaskAccepted(
        task_id=task_id,
        message=f"Discovery started for '{slug}'{tier_note} "
                f"({payload.max_queries or settings.max_queries_per_discovery_run} "
                f"queries max)")


@router.get("/discovery/queries", response_model=QueryLibraryStats)
def query_library_stats(service: str | None = None,
                        db: Session = Depends(get_db)):
    """How big is the query library, and what would a full pass cost?"""
    from sqlalchemy import func

    from app.models import Service
    slug = service or settings.default_service_slug
    svc = db.execute(
        select(Service).where(Service.slug == slug)).scalar_one_or_none()
    if svc is None:
        raise HTTPException(404, f"Service '{slug}' not found")

    rows = db.execute(
        select(DiscoveryQuery.priority, func.count(DiscoveryQuery.id),
               func.count(DiscoveryQuery.last_run_at))
        .where(DiscoveryQuery.service_id == svc.id)
        .group_by(DiscoveryQuery.priority)
        .order_by(DiscoveryQuery.priority)
    ).all()

    total = sum(n for _, n, _ in rows)
    never_run = sum(n - run for _, n, run in rows)
    enabled = db.execute(
        select(func.count(DiscoveryQuery.id))
        .where(DiscoveryQuery.service_id == svc.id,
               DiscoveryQuery.enabled.is_(True))).scalar_one()

    return QueryLibraryStats(
        total=total, enabled=enabled, never_run=never_run,
        by_tier=[{"tier": t, "queries": n, "run": r, "never_run": n - r}
                 for t, n, r in rows],
        estimated_serper_credits_full_pass=total)


@router.post("/crawl/{company_id}", response_model=TaskAccepted)
def trigger_crawl(company_id: str, payload: AnalyzeRequest,
                  background: BackgroundTasks, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    slug = payload.service_slug or settings.default_service_slug

    from app.workers import tasks
    task_id = _dispatch("crawl", background, tasks.process_company_task,
                        _local_process_company, company_id, slug, True,
                        payload.skip_external, payload.allow_ai)
    return TaskAccepted(task_id=task_id,
                        message=f"Crawl started for {company.domain}")


@router.post("/analyze/{company_id}", response_model=TaskAccepted)
def trigger_analysis(company_id: str, payload: AnalyzeRequest,
                     background: BackgroundTasks, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "Company not found")
    slug = payload.service_slug or settings.default_service_slug

    if not payload.run_async:
        config = load_service_config(db, slug)
        result = pipeline_engine.process_company(
            db, company, config, force_crawl=payload.force_crawl,
            skip_external=payload.skip_external, allow_ai=payload.allow_ai)
        db.commit()
        return TaskAccepted(message="Analysis complete", result=result.__dict__)

    from app.workers import tasks
    task_id = _dispatch("analyze", background, tasks.process_company_task,
                        _local_process_company, company_id, slug,
                        payload.force_crawl, payload.skip_external,
                        payload.allow_ai)
    return TaskAccepted(task_id=task_id,
                        message=f"Analysis started for {company.domain}")


@router.post("/pipeline/process-queue", response_model=TaskAccepted)
def process_queue(payload: AnalyzeRequest,
                  limit: int = Query(8, ge=1, le=100,
                                     description="Max companies this call"),
                  max_seconds: float = Query(
                      240, ge=10, le=1800,
                      description="Wall-clock budget; the call returns when "
                                  "this is reached even if the queue is not "
                                  "empty"),
                  db: Session = Depends(get_db)):
    """Crawl + classify + score part of the queue.

    Runs **synchronously** on purpose: on free-tier hosts a FastAPI
    BackgroundTask is killed the moment the response is flushed, so the queue
    never drains.

    That makes the time budget the important parameter, not `limit`. One
    company takes anywhere from ~15 seconds to a few minutes, so a count alone
    cannot bound the request - `limit=50` is 30+ minutes of blocking even in
    the good case. Call this often with a small budget rather than once with
    a large one.
    """
    slug = payload.service_slug or settings.default_service_slug
    # Use a plain COUNT (no row lock) so we don't accidentally hold
    # FOR UPDATE locks that would block _local_process_queue's own
    # SKIP LOCKED query in a separate session.
    pending = db.scalar(
        select(func.count()).select_from(Company)
        .where(Company.status.in_(("queued", "discovered")))
    ) or 0
    if pending == 0:
        return TaskAccepted(accepted=False, message="No companies queued",
                            result={"queued": 0})

    stats = _local_process_queue(slug, limit, max_seconds)

    still_pending = db.scalar(
        select(func.count()).select_from(Company)
        .where(Company.status.in_(("queued", "discovered")))
    ) or 0
    processed = stats.get("processed", pending - still_pending)
    stats["queued_remaining"] = still_pending

    note = ""
    if stats.get("stopped_reason") == "time_budget_reached":
        note = " (stopped on the time budget - call again to continue)"
    return TaskAccepted(
        task_id=None,
        message=(f"Processed {processed} companies in "
                 f"{stats.get('elapsed_seconds', 0)}s. "
                 f"{still_pending} still queued.{note}"),
        result=stats)


@router.post("/companies/add", response_model=TaskAccepted)
def add_company(payload: ManualCompanyRequest, background: BackgroundTasks,
                db: Session = Depends(get_db)):
    """Seed a specific company by URL - the fastest way to test the pipeline."""
    company = add_company_manually(db, payload.url, payload.name)
    if company is None:
        raise HTTPException(
            400, "Could not extract a valid company domain from that URL "
                 "(it may be a marketplace, social or news domain).")
    db.commit()

    task_id = None
    if payload.analyze_now:
        from app.workers import tasks
        task_id = _dispatch("analyze", background, tasks.process_company_task,
                            _local_process_company, company.id,
                            settings.default_service_slug,
                            True, False, True)
    return TaskAccepted(task_id=task_id, message=f"Added {company.domain}",
                        result={"company_id": company.id,
                                "domain": company.domain})


@router.get("/pipeline/status")
def pipeline_status(db: Session = Depends(get_db)):
    """Is the scheduler actually firing, and is the queue draining?

    Answers the question "did cron call me?" directly, rather than leaving you
    to infer it from a slowly rising crawled count.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    from app.models import Company, PipelineRun, ServiceOpportunity

    now = datetime.now(timezone.utc)

    def last_run(run_type: str) -> dict:
        row = db.execute(
            select(PipelineRun).where(PipelineRun.run_type == run_type)
            .order_by(PipelineRun.started_at.desc()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            return {"ever_run": False, "last_run_at": None,
                    "minutes_ago": None, "status": None, "stats": None}
        started = row.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return {
            "ever_run": True,
            "last_run_at": started.isoformat(),
            "minutes_ago": round((now - started).total_seconds() / 60, 1),
            "status": row.status,
            "error": row.error,
            "stats": row.stats,
        }

    def runs_since(run_type: str, hours: int) -> int:
        return db.execute(
            select(func.count(PipelineRun.id)).where(
                PipelineRun.run_type == run_type,
                PipelineRun.started_at >= now - timedelta(hours=hours))
        ).scalar_one()

    status_counts = dict(db.execute(
        select(Company.status, func.count(Company.id))
        .group_by(Company.status)).all())

    queued = status_counts.get("queued", 0) + status_counts.get("discovered", 0)
    crawled = db.execute(
        select(func.count(Company.id))
        .where(Company.last_crawled_at.is_not(None))).scalar_one()

    return {
        "queue": {
            "queued": queued,
            "crawled": crawled,
            "rejected": status_counts.get("rejected", 0),
            "error": status_counts.get("error", 0),
            "total_companies": sum(status_counts.values()),
            "opportunities": db.execute(
                select(func.count(ServiceOpportunity.id))).scalar_one(),
            "by_status": status_counts,
        },
        "scheduler": {
            "process_queue": {**last_run("process_queue"),
                              "runs_last_24h": runs_since("process_queue", 24)},
            "discovery": {**last_run("discovery"),
                          "runs_last_24h": runs_since("discovery", 24)},
        },
        "checked_at": now.isoformat(),
    }


@router.get("/pipeline/runs")
def list_runs(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.execute(
        select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
    ).scalars().all()
    return [{
        "id": r.id, "run_type": r.run_type, "status": r.status,
        "stats": r.stats, "error": r.error,
        "started_at": r.started_at, "completed_at": r.completed_at,
    } for r in rows]

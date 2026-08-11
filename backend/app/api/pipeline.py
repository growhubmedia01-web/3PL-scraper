"""Pipeline trigger endpoints (§45).

Long operations are dispatched to Celery when a broker is reachable; otherwise
they run in a FastAPI BackgroundTask so the product works without Redis (§41).
The request never blocks on crawling or LLM calls either way.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db, session_scope
from app.engine import pipeline as pipeline_engine
from app.engine.discovery import add_company_manually, queued_companies, run_discovery
from app.engine.service_config import load_service_config
from app.models import Company, PipelineRun
from app.schemas import (
    AnalyzeRequest, DiscoveryRunRequest, ManualCompanyRequest, TaskAccepted,
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
                     country: str | None) -> None:
    with session_scope() as db:
        config = load_service_config(db, service_slug)
        run_discovery(db, config, limit=limit, country=country)


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


def _local_process_queue(service_slug: str, limit: int) -> None:
    with session_scope() as db:
        config = load_service_config(db, service_slug)
        companies = queued_companies(db, limit=limit)
        pipeline_engine.process_batch(db, companies, config)


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
                              country=payload.country)
        db.commit()
        return TaskAccepted(message="Discovery complete", result=stats.as_dict())

    from app.workers import tasks
    task_id = _dispatch("discovery", background, tasks.discover_companies,
                        _local_discovery, slug, payload.limit, payload.country)
    return TaskAccepted(task_id=task_id,
                        message=f"Discovery started for service '{slug}'")


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
def process_queue(payload: AnalyzeRequest, background: BackgroundTasks,
                  limit: int = 25, db: Session = Depends(get_db)):
    """Crawl + classify + score everything sitting in the queue."""
    slug = payload.service_slug or settings.default_service_slug
    pending = len(queued_companies(db, limit=1000))
    if pending == 0:
        return TaskAccepted(accepted=False, message="No companies queued")

    from app.workers import tasks
    task_id = _dispatch("process_queue", background, tasks.process_queue_task,
                        _local_process_queue, slug, limit)
    return TaskAccepted(task_id=task_id,
                        message=f"Processing up to {limit} of {pending} queued companies")


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

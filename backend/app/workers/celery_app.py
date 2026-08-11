"""Celery application + beat schedule (§41, §42)."""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

SLUG = settings.default_service_slug

celery_app = Celery(
    "intent_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    worker_max_tasks_per_child=50,      # Playwright/lxml leak; recycle workers
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
)

# §42 scheduling
celery_app.conf.beat_schedule = {
    "discover-new-companies-daily": {
        "task": "app.workers.tasks.discover_companies",
        "schedule": crontab(hour=2, minute=0),
        "args": (SLUG, None, None),
    },
    "process-queue-hourly": {
        "task": "app.workers.tasks.process_queue_task",
        "schedule": crontab(minute=15),
        "args": (SLUG, 40),
    },
    "refresh-stale-opportunities-daily": {
        "task": "app.workers.tasks.refresh_stale_task",
        "schedule": crontab(hour=4, minute=30),
        "args": (SLUG, 50),
    },
    "recalculate-scores-nightly": {
        # Cheap: re-scores from stored signals so freshness decay is applied
        # even when nothing new was crawled (§25, §42).
        "task": "app.workers.tasks.recalculate_scores_task",
        "schedule": crontab(hour=3, minute=0),
        "args": (SLUG,),
    },
    "prune-expired-cache-daily": {
        "task": "app.workers.tasks.prune_cache_task",
        "schedule": crontab(hour=5, minute=0),
    },
    "enforce-data-retention-weekly": {
        # GDPR: drop decision-maker records for companies that went cold.
        "task": "app.workers.tasks.enforce_retention_task",
        "schedule": crontab(day_of_week=0, hour=6, minute=0),
        "args": (365,),
    },
}

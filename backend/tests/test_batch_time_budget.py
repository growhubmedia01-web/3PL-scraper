"""Batch processing must be bounded by wall-clock time, not just a count.

This runs inside a synchronous HTTP request on free-tier hosts (background
tasks get killed once the response is flushed). One company can take anywhere
from ~15 seconds to several minutes, so a count limit alone cannot bound the
request: limit=50 is 30+ minutes of blocking even when every site is fast.
"""
from __future__ import annotations

import time

import pytest

from app.engine import pipeline as pipeline_engine
from app.engine.crawler import CrawlResult
from app.models import Company


@pytest.fixture
def queued_companies(db):
    companies = []
    for i in range(10):
        c = Company(name=f"Brand {i}", domain=f"brand{i}.example",
                    website=f"https://brand{i}.example", status="queued")
        db.add(c)
        companies.append(c)
    db.flush()
    return companies


def _slow_crawl(seconds: float):
    """Stub crawler that mirrors what the real one does on an unreachable
    site: takes time, marks the company, and returns no pages."""
    def crawl(db, company, max_pages=None, max_seconds=None):
        time.sleep(seconds)
        res = CrawlResult(company_id=company.id, domain=company.domain)
        res.error = "stub: no pages"
        company.status = "error"
        company.rejection_reason = res.error
        db.flush()
        return res
    return crawl


def test_batch_stops_at_the_time_budget(db, config, queued_companies,
                                        monkeypatch):
    monkeypatch.setattr(pipeline_engine, "crawl_company", _slow_crawl(0.15))

    started = time.monotonic()
    batch = pipeline_engine.process_batch(
        db, queued_companies, config, max_seconds=0.45,
        skip_external=True, allow_ai=False)
    elapsed = time.monotonic() - started

    assert batch.stopped_reason == "time_budget_reached"
    assert batch.processed < len(queued_companies), "should not have finished"
    # budget + at most one more company
    assert elapsed < 0.45 + 0.30, f"overran the budget: {elapsed:.2f}s"


def test_batch_completes_when_it_fits_in_the_budget(db, config,
                                                    queued_companies,
                                                    monkeypatch):
    monkeypatch.setattr(pipeline_engine, "crawl_company", _slow_crawl(0.01))

    batch = pipeline_engine.process_batch(
        db, queued_companies, config, max_seconds=30,
        skip_external=True, allow_ai=False)

    assert batch.stopped_reason == "completed"
    assert batch.processed == len(queued_companies)


def test_no_budget_means_process_everything(db, config, queued_companies,
                                            monkeypatch):
    monkeypatch.setattr(pipeline_engine, "crawl_company", _slow_crawl(0.01))
    batch = pipeline_engine.process_batch(
        db, queued_companies, config, skip_external=True, allow_ai=False)
    assert batch.processed == len(queued_companies)


def test_work_done_before_the_deadline_is_committed(db, config,
                                                    queued_companies,
                                                    monkeypatch):
    """A batch cut short must not lose what it already did."""
    monkeypatch.setattr(pipeline_engine, "crawl_company", _slow_crawl(0.12))

    batch = pipeline_engine.process_batch(
        db, queued_companies, config, max_seconds=0.4,
        skip_external=True, allow_ai=False)

    assert batch.processed >= 1
    # Companies the batch touched are no longer 'queued'.
    from sqlalchemy import select
    statuses = db.execute(select(Company.status)).scalars().all()
    assert any(s != "queued" for s in statuses), (
        "processed companies were not persisted")


def test_elapsed_time_is_reported(db, config, queued_companies, monkeypatch):
    monkeypatch.setattr(pipeline_engine, "crawl_company", _slow_crawl(0.02))
    batch = pipeline_engine.process_batch(
        db, queued_companies, config, max_seconds=30,
        skip_external=True, allow_ai=False)
    assert batch.elapsed_seconds > 0
    assert "elapsed_seconds" in batch.as_dict()
    assert "stopped_reason" in batch.as_dict()


def test_crawler_respects_its_own_per_company_budget(db, company):
    """One slow site must not consume the whole batch budget."""
    from app.engine import crawler

    # A budget of 0 means: fetch the homepage, then stop.
    result = crawler.crawl_company(db, company, max_seconds=0.0001)
    assert result.fetched <= 1

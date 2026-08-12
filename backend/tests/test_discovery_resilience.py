"""Discovery must survive a broken database mid-run.

Postgres aborts the entire transaction on any failed statement. Every
subsequent write then fails with InFailedSqlTransaction - including the write
that records what went wrong. The original error gets masked by a second one
from the error handler, and the caller sees an opaque 500.

That is exactly what a missing column (schema drift) triggered in production.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.engine.discovery import run_discovery
from app.models import Company, PipelineRun
from app.providers.search import factory
from app.providers.search.base import SearchProvider, SearchResult


class StubProvider(SearchProvider):
    name = "stub"

    @property
    def configured(self) -> bool:
        return True

    def search(self, query, *, country=None, num=20, page=1):
        return [SearchResult(url=f"https://brand-{i}.com",
                             title=f"Brand {i} | Official Store",
                             snippet="Shop") for i in range(3)]


@pytest.fixture
def stub_search(monkeypatch):
    monkeypatch.setattr(factory, "_REGISTRY", {"stub": StubProvider})
    return StubProvider


def test_discovery_records_a_failed_run_instead_of_raising(
        db, config, stub_search, monkeypatch):
    """A hard failure mid-run must be recorded, not propagated as a 500."""
    from app.engine import discovery

    def explode(*_args, **_kwargs):
        raise RuntimeError("column companies.business_model does not exist")

    monkeypatch.setattr(discovery, "_existing_domains", explode)

    stats = run_discovery(db, config, max_queries=2)

    assert stats.companies_created == 0
    runs = db.execute(select(PipelineRun)).scalars().all()
    assert runs, "the failed run must still be recorded"
    assert runs[-1].status == "failed"
    assert "business_model" in (runs[-1].error or "")


def test_the_run_outcome_survives_a_poisoned_transaction(
        db, config, stub_search, monkeypatch):
    """If the transaction is already aborted, the finalizer must roll back
    and record the outcome on a clean one."""
    from app.engine import discovery

    calls = {"n": 0}
    real_flush = db.flush

    def flaky_flush(*args, **kwargs):
        calls["n"] += 1
        # fail the first finalize attempt, mimicking InFailedSqlTransaction
        if calls["n"] > 3:
            raise RuntimeError("current transaction is aborted")
        return real_flush(*args, **kwargs)

    run = PipelineRun(service_id=config.id, run_type="discovery",
                      status="running")
    db.add(run)
    db.flush()

    monkeypatch.setattr(db, "flush", flaky_flush)
    discovery._finalize_run(db, run, config, discovery.DiscoveryStats(),
                            status="failed", error="boom")
    monkeypatch.undo()

    runs = db.execute(select(PipelineRun)).scalars().all()
    assert any(r.status == "failed" and r.error == "boom" for r in runs), (
        "the outcome must be recorded even after the transaction broke")


def test_a_duplicate_domain_does_not_discard_earlier_companies(
        db, config, stub_search, monkeypatch):
    """A unique-constraint collision must roll back one insert, not the run.

    The original code called db.rollback() here, silently throwing away every
    company found earlier in the same run.
    """
    from app.engine import discovery

    # Pre-create one of the domains the stub will return.
    db.add(Company(name="Existing", domain="brand-1.com",
                   website="https://brand-1.com", status="queued"))
    db.flush()

    stats = run_discovery(db, config, max_queries=1)
    db.commit()

    domains = {c.domain for c in db.execute(select(Company)).scalars().all()}
    assert "brand-0.com" in domains, "earlier companies were discarded"
    assert "brand-2.com" in domains, "later companies were discarded"
    assert stats.companies_created >= 2


def test_discovery_returns_stats_even_with_no_search_provider(db, config,
                                                              monkeypatch):
    monkeypatch.setattr(factory, "_REGISTRY", {})
    stats = run_discovery(db, config)
    assert stats.companies_created == 0
    runs = db.execute(select(PipelineRun)).scalars().all()
    assert runs[-1].status == "failed"
    assert "search provider" in (runs[-1].error or "").lower()

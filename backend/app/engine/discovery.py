"""Company discovery (§30, Phase 1).

Search -> URLs -> normalized domains -> dedupe -> company rows -> crawl queue.
Vendor-agnostic: it only talks to SearchService.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.engine.service_config import ServiceConfig
from app.models import Company, DiscoveryQuery, PipelineRun
from app.providers.search.factory import SearchService
from app.utils.dedupe import name_similarity
from app.utils.urls import normalize_domain, root_url

log = logging.getLogger(__name__)


@dataclass
class DiscoveryStats:
    queries_run: int = 0
    results_seen: int = 0
    domains_extracted: int = 0
    duplicates_skipped: int = 0
    blocked_skipped: int = 0
    companies_created: int = 0
    created_domains: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "queries_run": self.queries_run,
            "results_seen": self.results_seen,
            "domains_extracted": self.domains_extracted,
            "duplicates_skipped": self.duplicates_skipped,
            "blocked_skipped": self.blocked_skipped,
            "companies_created": self.companies_created,
        }


def _existing_domains(db: Session) -> set[str]:
    return {row[0] for row in db.execute(select(Company.domain)).all()}


def _fuzzy_duplicate(db: Session, name: str | None) -> Company | None:
    """Secondary dedupe by company name (§51). Domain equality is handled by
    the unique constraint; this catches 'Acme Ltd' vs 'Acme Limited' on
    different TLDs."""
    if not name or len(name) < 4:
        return None
    candidates = db.execute(
        select(Company).where(func.lower(Company.name).like(f"{name[:4].lower()}%"))
        .limit(25)
    ).scalars().all()
    for candidate in candidates:
        if name_similarity(name, candidate.name) >= 0.94:
            return candidate
    return None


def run_discovery(db: Session, config: ServiceConfig,
                  limit: int | None = None,
                  query_ids: list[str] | None = None,
                  country: str | None = None) -> DiscoveryStats:
    limit = limit or settings.max_companies_per_discovery_run
    stats = DiscoveryStats()
    search = SearchService(db)

    run = PipelineRun(service_id=config.id, run_type="discovery", status="running")
    db.add(run)
    db.flush()

    if not search.has_provider:
        run.status = "failed"
        run.error = ("No search provider configured. Set SERPER_API_KEY, "
                     "SERPAPI_KEY or BRAVE_SEARCH_API_KEY in backend/.env")
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        log.error(run.error)
        return stats

    queries = [q for q in config.queries
               if (not query_ids or q.id in query_ids)
               and (not country or q.country in (None, country))]
    if not queries:
        log.warning("No enabled discovery queries for service '%s'", config.slug)

    known = _existing_domains(db)

    try:
        for query in queries:
            if stats.companies_created >= limit:
                log.info("Discovery limit reached (%d companies)", limit)
                break

            target_country = country or query.country
            results = search.search(query.query, country=target_country,
                                    num=settings.search_max_results)
            stats.queries_run += 1
            stats.results_seen += len(results)

            query.last_run_at = datetime.now(timezone.utc)
            query.results_count = (query.results_count or 0) + len(results)

            for result in results:
                if stats.companies_created >= limit:
                    break
                domain = normalize_domain(result.url)
                if domain is None:
                    stats.blocked_skipped += 1
                    continue
                stats.domains_extracted += 1

                if domain in known:
                    stats.duplicates_skipped += 1
                    continue

                candidate_name = (result.title or "").split("|")[0].split("-")[0].strip()
                if _fuzzy_duplicate(db, candidate_name):
                    stats.duplicates_skipped += 1
                    known.add(domain)
                    continue

                company = Company(
                    name=candidate_name[:200] or None,
                    domain=domain,
                    website=root_url(domain),
                    status="queued",
                    discovered_via=f"search:{query.query}",
                )
                db.add(company)
                try:
                    db.flush()
                except Exception:      # concurrent insert on the unique domain
                    db.rollback()
                    stats.duplicates_skipped += 1
                    known.add(domain)
                    continue

                known.add(domain)
                stats.companies_created += 1
                stats.created_domains.append(domain)

        run.status = "completed"
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        log.exception("Discovery run failed")
    finally:
        run.stats = stats.as_dict()
        run.completed_at = datetime.now(timezone.utc)
        db.flush()

    log.info("Discovery complete: %s", stats.as_dict())
    return stats


def add_company_manually(db: Session, url_or_domain: str,
                         name: str | None = None) -> Company | None:
    """Seed a specific company - useful for testing and for user-supplied lists."""
    domain = normalize_domain(url_or_domain)
    if domain is None:
        return None
    existing = db.execute(
        select(Company).where(Company.domain == domain)
    ).scalar_one_or_none()
    if existing:
        return existing
    company = Company(name=name, domain=domain, website=root_url(domain),
                      status="queued", discovered_via="manual")
    db.add(company)
    db.flush()
    return company


def queued_companies(db: Session, limit: int = 50) -> list[Company]:
    return list(db.execute(
        select(Company)
        .where(Company.status.in_(("queued", "discovered")))
        .order_by(Company.created_at)
        .limit(limit)
    ).scalars().all())

"""Company discovery (§30, Phase 1).

Search -> URLs -> normalized domains -> dedupe -> company rows -> crawl queue.
Vendor-agnostic: it only talks to SearchService.
"""
from __future__ import annotations

import logging
import re
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


# Separators used between a brand name and its tagline in a page title.
# A bare hyphen is deliberately excluded: "Well-Kept | Skincare" must not
# become "Well".
_TITLE_SEPARATOR = re.compile(
    r"\s+[|\u2013\u2014\u00b7]\s+|\s+-\s+|:\s+")

_TITLE_NOISE = re.compile(
    r"^(shop|welcome to|official site of|buy)\s+|"
    r"\s+(official (site|store|website)|online (store|shop))$", re.I)

# Segments that carry no company name at all.
_TITLE_STOPWORDS = {
    "home", "homepage", "shop", "store", "welcome", "official site",
    "official store", "products", "index", "main", "landing page",
}


def _name_from_title(title: str | None) -> str | None:
    """Extract a company name from a search-result title.

    Titles are messy: "Home | Acme Ltd", "Shop Nordic Wool - Merino",
    "Well-Kept | Skincare". Splitting on a bare hyphen would turn
    "Well-Kept" into "Well", so only spaced separators count, and segments
    that are pure boilerplate are skipped rather than returned.
    """
    if not title:
        return None
    for segment in _TITLE_SEPARATOR.split(title.strip()):
        cleaned = _TITLE_NOISE.sub("", segment).strip(
            " -|\u2013\u2014:\u00b7")
        if cleaned and cleaned.lower() not in _TITLE_STOPWORDS:
            return cleaned[:200]
    return None


def apply_exclusions(query: str, terms: list[str]) -> str:
    """Append Google negative operators, skipping any term already present.

    Excluding "logistics" from a query that is itself about logistics would
    return nothing, so terms already in the query are left alone.
    """
    if not terms:
        return query
    lowered = query.lower()
    negatives = [
        f'-"{t}"' if " " in t else f"-{t}"
        for t in terms if t.lower() not in lowered
    ]
    return " ".join([query, *negatives]) if negatives else query


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
                  country: str | None = None,
                  tier: int | None = None,
                  max_queries: int | None = None) -> DiscoveryStats:
    """Discover companies for one service.

    `tier` selects a slice of the query library (1 = highest yield). With
    thousands of queries seeded, tier and `max_queries` are the two levers
    that control Serper spend - only executed queries cost anything.
    """
    limit = limit or settings.max_companies_per_discovery_run
    max_queries = max_queries or settings.max_queries_per_discovery_run
    stats = DiscoveryStats()
    search = SearchService(db)

    run = PipelineRun(service_id=config.id, run_type="discovery", status="running")
    db.add(run)
    db.flush()

    if not search.has_provider:
        error = ("No search provider configured. Set SERPER_API_KEY, "
                 "SERPAPI_KEY or BRAVE_SEARCH_API_KEY in backend/.env")
        log.error(error)
        _finalize_run(db, run, config, stats, status="failed", error=error)
        return stats

    queries = [q for q in config.queries
               if (not query_ids or q.id in query_ids)
               and (not country or q.country in (None, country))
               and (tier is None or q.priority == tier)]

    # Least-recently-run first, so repeated runs work through the library
    # instead of re-executing the same queries and paying twice.
    queries.sort(key=lambda q: (q.last_run_at is not None,
                                q.last_run_at or datetime.min.replace(
                                    tzinfo=timezone.utc),
                                q.priority))
    queries = queries[:max_queries]

    if not queries:
        log.warning("No enabled discovery queries for service '%s'"
                    "%s", config.slug, f" at tier {tier}" if tier else "")

    try:
        # Inside the try: a schema-drift error here (missing column) must be
        # recorded as a failed run, not raised to the caller as a 500.
        known = _existing_domains(db)

        for query in queries:
            if stats.companies_created >= limit:
                log.info("Discovery limit reached (%d companies)", limit)
                break

            target_country = country or query.country
            search_text = apply_exclusions(query.query,
                                           config.query_exclusion_terms)
            results = search.search(search_text, country=target_country,
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

                candidate_name = _name_from_title(result.title)
                if _fuzzy_duplicate(db, candidate_name):
                    stats.duplicates_skipped += 1
                    known.add(domain)
                    continue

                company = Company(
                    name=candidate_name[:200] if candidate_name else None,
                    domain=domain,
                    website=root_url(domain),
                    status="queued",
                    discovered_via=f"search:{query.query}",
                )
                # SAVEPOINT, not a bare flush: a unique-domain collision must
                # roll back this one insert, never the whole run. A plain
                # db.rollback() here would discard every company found so far.
                try:
                    with db.begin_nested():
                        db.add(company)
                        db.flush()
                except Exception:      # concurrent insert on the unique domain
                    stats.duplicates_skipped += 1
                    known.add(domain)
                    continue

                known.add(domain)
                stats.companies_created += 1
                stats.created_domains.append(domain)

        run.status = "completed"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        log.exception("Discovery run failed")
        _finalize_run(db, run, config, stats, status="failed", error=error)
        return stats

    _finalize_run(db, run, config, stats, status="completed")
    log.info("Discovery complete: %s", stats.as_dict())
    return stats


def _finalize_run(db: Session, run: PipelineRun, config: ServiceConfig,
                  stats: DiscoveryStats, status: str,
                  error: str | None = None) -> None:
    """Record the run outcome, even when the transaction is already broken.

    Postgres aborts the whole transaction on any failed statement, so once
    something goes wrong every subsequent write - including the one that
    records what went wrong - fails with InFailedSqlTransaction. Writing the
    outcome then requires a rollback and a fresh transaction first.
    """
    payload = dict(
        service_id=config.id, run_type="discovery", status=status,
        stats=stats.as_dict(), error=error,
        completed_at=datetime.now(timezone.utc),
    )
    try:
        run.status = status
        run.error = error
        run.stats = payload["stats"]
        run.completed_at = payload["completed_at"]
        db.flush()
        return
    except Exception:
        log.warning("Could not update the pipeline run in the current "
                    "transaction; retrying on a clean one.")

    try:
        db.rollback()                       # clear the aborted transaction
        db.add(PipelineRun(**payload))
        db.commit()
    except Exception:
        log.exception("Failed to record the discovery run outcome")


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

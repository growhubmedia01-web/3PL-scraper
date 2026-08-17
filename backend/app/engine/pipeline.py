"""Pipeline orchestration (§7, §41, §49).

Implements the funnel that keeps costs sane:

    discovered domains
        -> crawl + classify           (cheap, no paid API)
        -> reject irrelevant early    (records a reason, never reprocessed)
        -> resolve LinkedIn URL       (free from crawl data, one SERP call at most)
        -> detect signals             (cheap, keyword/config driven)
        -> external evidence          (SERP calls - only for classified cos)
        -> AI analysis                (only above ai_min_raw_score)
        -> score
        -> decision makers            (only above dm_threshold)

One company failing never aborts the batch (§55).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine import ai_analysis as ai
from app.engine import decision_makers as dm
from app.engine import linkedin
from app.engine import scoring, signals as signal_engine
from app.engine.classifier import apply_classification, classify
from app.engine.crawler import crawl_company, load_pages_from_sources
from app.engine.evidence import collect_external_evidence
from app.engine.service_config import ServiceConfig
from app.models import Company, ServiceOpportunity, Source

log = logging.getLogger(__name__)


@dataclass
class CompanyResult:
    domain: str
    stage: str = "start"
    ok: bool = False
    rejected: bool = False
    reason: str | None = None
    score: float | None = None
    intent_level: str | None = None
    signals_found: int = 0
    decision_makers_found: int = 0
    ai_used: bool = False
    error: str | None = None


@dataclass
class BatchResult:
    processed: int = 0
    qualified: int = 0
    rejected: int = 0
    errors: int = 0
    ai_calls: int = 0
    stopped_reason: str = "completed"
    elapsed_seconds: float = 0.0
    results: list[CompanyResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"processed": self.processed, "qualified": self.qualified,
                "rejected": self.rejected, "errors": self.errors,
                "ai_calls": self.ai_calls,
                "stopped_reason": self.stopped_reason,
                "elapsed_seconds": round(self.elapsed_seconds, 1)}


def process_company(db: Session, company: Company, config: ServiceConfig, *,
                    force_crawl: bool = False,
                    skip_external: bool = False,
                    allow_ai: bool = True) -> CompanyResult:
    """Run the full pipeline for one company. Commits nothing - the caller owns
    the transaction."""
    result = CompanyResult(domain=company.domain)

    try:
        # ---- 1. Crawl (or reuse stored sources) ------------------------
        result.stage = "crawl"
        needs_crawl = force_crawl or company.last_crawled_at is None or \
            company.status in ("queued", "discovered", "error")
        if needs_crawl:
            crawl = crawl_company(db, company)
            pages = crawl.pages
            if not crawl.ok:
                result.reason = crawl.error or "site unreachable"
                result.rejected = True
                return result
        else:
            pages = load_pages_from_sources(db, company)
            if not pages:
                crawl = crawl_company(db, company)
                pages = crawl.pages
                if not crawl.ok:
                    result.reason = crawl.error or "site unreachable"
                    result.rejected = True
                    return result

        # ---- 2. Classify + early reject (§32, §49) ---------------------
        result.stage = "classify"
        classification = classify(company, pages,
                                  config.excluded_business_types)
        apply_classification(db, company, classification)
        if not classification.relevant:
            result.rejected = True
            result.reason = classification.rejection_reason
            log.info("Rejected %s: %s", company.domain, result.reason)
            return result

        # ---- 2b. LinkedIn URL resolution (identity, not score-gated) ----
        result.stage = "linkedin"
        try:
            linkedin.resolve_company_linkedin(
                db, company, pages, skip_external=skip_external)
        except Exception as exc:
            log.warning("LinkedIn resolution failed for %s: %s",
                        company.domain, exc)

        # ---- 3. External evidence (§33) --------------------------------
        result.stage = "evidence"
        external_pages = []
        if not skip_external:
            external_pages = collect_external_evidence(db, company)

        # ---- 4. Signals (§18) ------------------------------------------
        result.stage = "signals"
        detected = signal_engine.detect_signals(
            db, company, pages, config, external_pages)
        stored_signals = signal_engine.persist_signals(
            db, company, config, detected)
        result.signals_found = len(stored_signals)

        # ---- 5. Provisional score, to decide whether AI is worth it ----
        result.stage = "score"
        provisional = scoring.calculate(db, company, stored_signals, config)

        analysis_dict = None
        probability = None
        if allow_ai and provisional.raw_score >= config.ai_min_raw_score:
            result.stage = "ai"
            sources = db.execute(
                select(Source).where(Source.company_id == company.id)
            ).scalars().all()
            analysis = ai.analyze(db, company, stored_signals, list(sources), config)
            if analysis is not None:
                analysis_dict = ai.to_dict(analysis)
                probability = analysis.service_probability
                result.ai_used = True
        else:
            log.debug("Skipping AI for %s (raw %.1f < %.1f)", company.domain,
                      provisional.raw_score, config.ai_min_raw_score)

        # ---- 6. Final score (§28) --------------------------------------
        result.stage = "final_score"
        final = scoring.calculate(db, company, stored_signals, config,
                                  ai_probability=probability)
        opportunity = scoring.upsert_opportunity(
            db, company, config, final, analysis_dict)
        result.score = final.score
        result.intent_level = final.intent_level

        # ---- 7. Decision makers, gated on score (§50) ------------------
        result.stage = "decision_makers"
        if dm.should_research(final.score, config):
            people = dm.find_decision_makers(
                db, company, pages + external_pages, config)
            result.decision_makers_found = len(people)

        result.ok = True
        result.stage = "done"
        return result

    except Exception as exc:
        log.exception("Pipeline failed for %s at stage %s",
                      company.domain, result.stage)
        result.error = f"{type(exc).__name__}: {exc}"
        return result


def process_batch(db: Session, companies: list[Company], config: ServiceConfig,
                  max_seconds: float | None = None, **kwargs) -> BatchResult:
    """Process companies until the list is exhausted or the time budget runs out.

    A count limit alone is not enough to bound this. One company can take
    anywhere from ~30 seconds to several minutes depending on how many pages
    it has, how slow it responds, and whether external lookups time out. When
    this runs inside a synchronous HTTP request - which it must on hosts that
    kill background tasks once the response is flushed - an unbounded batch
    means the request eventually times out and the caller learns nothing about
    what was done.

    The deadline is checked between companies, so the real worst case is
    `max_seconds` plus however long the last company takes.
    """
    batch = BatchResult()
    started = time.monotonic()
    deadline = started + max_seconds if max_seconds else None

    for company in companies:
        if deadline and time.monotonic() >= deadline:
            batch.stopped_reason = "time_budget_reached"
            log.info("Batch stopped after %.0fs (%d processed, %d left)",
                     time.monotonic() - started, batch.processed,
                     len(companies) - batch.processed)
            break

        outcome = process_company(db, company, config, **kwargs)
        batch.results.append(outcome)
        batch.processed += 1
        if outcome.ai_used:
            batch.ai_calls += 1
        if outcome.error:
            batch.errors += 1
        elif outcome.rejected:
            batch.rejected += 1
        elif outcome.ok:
            batch.qualified += 1

        # Commit per company so one failure can't lose the whole batch, and
        # so a timeout mid-batch still leaves everything already done saved.
        try:
            db.commit()
        except Exception as commit_exc:
            db.rollback()
            batch.errors += 1
            log.warning("Commit failed for %s (%s) - marking error and continuing",
                        company.domain, type(commit_exc).__name__)
            # Try to mark this company as error in a fresh transaction so it
            # leaves the queue and doesn't block future runs.
            try:
                from sqlalchemy import text as _text
                db.execute(_text(
                    "UPDATE companies SET status='error', "
                    "rejection_reason='commit failed - possible lock timeout', "
                    "updated_at=NOW() WHERE id=:id"
                ), {"id": str(company.id)})
                db.commit()
                log.info("Marked %s as error after commit failure", company.domain)
            except Exception as mark_exc:
                db.rollback()
                log.warning("Could not mark %s as error: %s", company.domain,
                            mark_exc)


    batch.elapsed_seconds = time.monotonic() - started
    return batch


def stale_opportunities(db: Session, config: ServiceConfig,
                        limit: int = 50) -> list[Company]:
    """§52: refresh cadence driven by intent level."""
    now = datetime.now(timezone.utc)
    refresh = config.refresh_days
    stale: list[Company] = []

    rows = db.execute(
        select(ServiceOpportunity, Company)
        .join(Company, Company.id == ServiceOpportunity.company_id)
        .where(ServiceOpportunity.service_id == config.id)
        .order_by(ServiceOpportunity.score.desc())
    ).all()

    for opportunity, company in rows:
        if len(stale) >= limit:
            break
        days = refresh.get(opportunity.intent_level, 30)
        last = opportunity.last_analyzed
        if last is None:
            stale.append(company)
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last > timedelta(days=days):
            stale.append(company)
    return stale

"""Polite website crawler (§31, §54, §55).

Guarantees:
  * robots.txt is honoured (skipped jobs are recorded, not silently dropped)
  * per-host crawl delay, bounded retries, bounded pages per company
  * every fetched page is persisted as a `sources` row with its URL and hash
  * one failing site never stops the pipeline
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.engine.extractor import ExtractedPage, candidate_urls, extract
from app.models import Company, CrawlJob, Source
from app.utils.robots import can_fetch, crawl_delay_for
from app.utils.text import truncate
from app.utils.urls import normalize_url, root_url

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class CrawlResult:
    company_id: str
    domain: str
    pages: list[ExtractedPage] = field(default_factory=list)
    fetched: int = 0
    skipped_robots: int = 0
    failed: int = 0
    stopped_early: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.fetched > 0

    def page_by_type(self, page_type: str) -> list[ExtractedPage]:
        return [p for p in self.pages if p.page_type == page_type]

    @property
    def combined_text(self) -> str:
        return " \n ".join(p.searchable for p in self.pages)


def _headers() -> dict:
    return {
        "User-Agent": settings.crawler_user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _fetch(client: httpx.Client, url: str) -> tuple[str, int]:
    resp = client.get(url, follow_redirects=True)
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        return "", resp.status_code
    return resp.text, resp.status_code


def _render_with_playwright(url: str) -> tuple[str, int]:
    """JS-heavy fallback (§31). Opt-in via PLAYWRIGHT_ENABLED."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("PLAYWRIGHT_ENABLED=true but playwright is not installed "
                    "(pip install -r requirements-optional.txt)")
        return "", 0
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=settings.crawler_user_agent)
            page.goto(url, timeout=settings.crawl_timeout_seconds * 1000,
                      wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            html = page.content()
            browser.close()
            return html, 200
    except Exception as exc:
        log.warning("Playwright render failed for %s: %s", url, exc)
        return "", 0


def _persist_source(db: Session, company: Company, page: ExtractedPage) -> Source:
    """Upsert on (company_id, url). Skips rewriting unchanged content."""
    existing = db.execute(
        select(Source).where(Source.company_id == company.id,
                             Source.url == page.url)
    ).scalar_one_or_none()

    if existing:
        if existing.content_hash != page.hash:
            existing.content = page.text
            existing.excerpt = truncate(page.text, 500)
            existing.title = page.title
            existing.content_hash = page.hash
            existing.http_status = page.http_status
            existing.discovered_at = datetime.now(timezone.utc)
        return existing

    source = Source(
        company_id=company.id,
        source_type=page.page_type if page.page_type != "website" else "website",
        url=page.url, title=page.title, content=page.text,
        excerpt=truncate(page.text, 500), content_hash=page.hash,
        http_status=page.http_status,
    )
    db.add(source)
    db.flush()
    return source


def crawl_company(db: Session, company: Company,
                  max_pages: int | None = None,
                  max_seconds: float | None = None) -> CrawlResult:
    """Crawl one company's website. Never raises for site-level problems.

    `max_seconds` bounds the whole company. Without it a slow or flaky site
    can take minutes: 12 pages x (crawl delay + a 20s timeout + retries with
    exponential backoff). That is fine in a worker, but inside a synchronous
    HTTP request it blows the caller's timeout and the batch reports nothing.
    The homepage is always attempted; the budget only limits the extra pages.
    """
    max_pages = max_pages or settings.crawl_max_pages_per_company
    max_seconds = max_seconds or settings.crawl_max_seconds_per_company
    deadline = time.monotonic() + max_seconds if max_seconds else None
    result = CrawlResult(company_id=company.id, domain=company.domain)
    base = company.website or root_url(company.domain)

    company.status = "crawling"
    try:
        with db.begin_nested():  # SAVEPOINT - a lock error here must not
            db.flush()           # poison the outer transaction.
    except Exception as exc:
        log.warning("Could not lock %s for crawling (%s) - skipping",
                    company.domain, exc)
        result.error = f"lock conflict: {exc}"
        return result

    timeout = httpx.Timeout(settings.crawl_timeout_seconds)
    try:
        with httpx.Client(headers=_headers(), timeout=timeout,
                          follow_redirects=True) as client:
            # 1. Homepage first - its links steer the rest of the crawl.
            home_url = normalize_url(base) or base
            home = _crawl_one(db, client, company, home_url, "website", result)
            if home is None:
                company.status = "error"
                company.rejection_reason = result.error or "homepage unreachable"
                db.flush()
                return result

            # 2. Priority + discovered pages.
            targets = candidate_urls(base, home.internal_links, limit=max_pages)
            for url, page_type in targets:
                if result.fetched >= max_pages:
                    break
                if deadline and time.monotonic() >= deadline:
                    result.stopped_early = True
                    log.info("Crawl budget reached for %s after %d pages",
                             company.domain, result.fetched)
                    break
                if normalize_url(url) == home_url:
                    continue
                _crawl_one(db, client, company, url, page_type, result)
    except Exception as exc:  # pragma: no cover - defensive
        result.error = str(exc)
        log.exception("Crawl aborted for %s", company.domain)

    company.last_crawled_at = datetime.now(timezone.utc)
    company.status = "crawled" if result.ok else "error"
    if not result.ok and not company.rejection_reason:
        company.rejection_reason = result.error or "no pages fetched"
    db.flush()
    return result


def _crawl_one(db: Session, client: httpx.Client, company: Company, url: str,
               page_type: str, result: CrawlResult) -> ExtractedPage | None:
    job = CrawlJob(company_id=company.id, url=url, page_type=page_type,
                   status="processing", started_at=datetime.now(timezone.utc))
    db.add(job)
    db.flush()

    if not can_fetch(url):
        job.status = "skipped"
        job.error = "disallowed by robots.txt"
        job.completed_at = datetime.now(timezone.utc)
        result.skipped_robots += 1
        db.flush()
        return None

    delay = crawl_delay_for(url)
    html, status = "", 0
    last_error = None

    for attempt in range(1, settings.crawl_max_retries + 1):
        job.attempt_count = attempt
        try:
            time.sleep(delay)
            html, status = _fetch(client, url)
            job.http_status = status
            if status == 404:
                last_error = "404"
                break                      # a missing /careers page is normal
            if status in RETRYABLE_STATUS:
                last_error = f"HTTP {status}"
                delay = min(delay * 2, 30)
                continue
            if status >= 400:
                last_error = f"HTTP {status}"
                break
            break
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            delay = min(delay * 2, 30)
        except Exception as exc:
            last_error = str(exc)
            break

    # JS-rendered pages return near-empty HTML: try Playwright once.
    if settings.playwright_enabled and len(html) < 1000 and status in (0, 200):
        rendered, rstatus = _render_with_playwright(url)
        if rendered:
            html, status = rendered, rstatus or 200
            job.http_status = status

    if not html:
        job.status = "failed"
        job.error = last_error or "empty response"
        job.completed_at = datetime.now(timezone.utc)
        result.failed += 1
        if page_type == "website":
            result.error = job.error
        db.flush()
        return None

    page = extract(html, url, http_status=status)
    page.page_type = page_type
    _persist_source(db, company, page)

    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    result.pages.append(page)
    result.fetched += 1
    db.flush()
    return page


def load_pages_from_sources(db: Session, company: Company) -> list[ExtractedPage]:
    """Rebuild page objects from stored sources - lets re-analysis run without
    re-crawling (§52 freshness, §49 cost control)."""
    rows = db.execute(
        select(Source).where(Source.company_id == company.id)
    ).scalars().all()
    pages = []
    for row in rows:
        page = ExtractedPage(url=row.url, title=row.title or "",
                             text=row.content or "", page_type=row.source_type,
                             http_status=row.http_status)
        pages.append(page)
    return pages

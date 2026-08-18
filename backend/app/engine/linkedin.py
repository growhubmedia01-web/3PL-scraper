"""Company LinkedIn URL resolution.

Two tiers, cheapest first:
  tier 1 (free)  - schema.org `sameAs` links and on-page external links,
                   both already captured during the normal site crawl.
  tier 2 (SERP)  - one search-engine query via SearchService, only if
                   tier 1 found nothing and external calls are allowed.
                   Reuses SearchService's own caching, and is gated to
                   run at most once per company (see resolve_company_linkedin).

Never fetches linkedin.com directly - this only ever reads a company's own
crawled pages or a search engine's result snippets, consistent with the
public-source-only, no-scraping posture used elsewhere in this codebase
(robots.txt honored as a hard gate, no email discovery, ATS job boards used
via their documented public JSON endpoints rather than scraped).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from sqlalchemy.orm import Session

from app.engine.extractor import ExtractedPage
from app.models import Company
from app.providers.search.factory import SearchService
from app.utils.urls import domain_root, normalize_url

log = logging.getLogger(__name__)


def _is_linkedin_company_url(url: str | None) -> bool:
    """True only for a public company page - '/company/<slug>'. Explicitly
    excludes '/in/<person>' (a personal profile - must never be surfaced
    here, same constraint as DecisionMaker.profile_url never pointing to
    LinkedIn), '/school/', '/jobs/', '/posts/', and '/admin' (a private
    management URL - one leaked into a crawled page's HTML once, pointing
    a lead at a login wall instead of a usable page)."""
    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host != "linkedin.com":
        return False
    path = parsed.path.lower()
    if not path.startswith("/company/"):
        return False
    return "/admin" not in path


def _clean_linkedin_url(url: str) -> str:
    """Drop query params and fragment. LinkedIn's own tracking params
    (trk, viewAsMember, originalSubdomain, ...) carry no meaning for a
    reference link, and normalize_url()'s generic tracking-param list
    (utm_, fbclid, ...) doesn't know about LinkedIn-specific ones."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def extract_company_linkedin_url(
        pages: list[ExtractedPage]) -> tuple[str, str] | None:
    """Tier 1: free. Scans json_ld `sameAs` first (structured, higher
    trust - the company explicitly published it about themselves), then
    falls back to any /company/ link found on the page. Returns
    (url, source) where source is 'json_ld' or 'site_link'."""
    for page in pages:
        for block in page.json_ld:
            if block.get("@type") not in ("Organization", "Corporation"):
                continue
            same_as = block.get("sameAs") or []
            if isinstance(same_as, str):
                same_as = [same_as]
            for candidate in same_as:
                if _is_linkedin_company_url(candidate):
                    norm = normalize_url(candidate)
                    if norm:
                        return _clean_linkedin_url(norm), "json_ld"

    for page in pages:
        for link in page.links:
            if _is_linkedin_company_url(link):
                norm = normalize_url(link) or link
                return _clean_linkedin_url(norm), "site_link"

    return None


def search_company_linkedin_url(db: Session,
                                company: Company) -> tuple[str, str] | None:
    """Tier 2: fallback. One SERP query, reuses SearchService's existing
    caching. Returns (url, 'search') or None."""
    search = SearchService(db)
    if not search.has_provider:
        log.info("No search provider configured; skipping LinkedIn search "
                 "for %s.", company.domain)
        return None

    name = company.name or company.domain
    query = f'site:linkedin.com/company "{name}"'
    try:
        results = search.search(query, country=company.country, num=5,
                                mode="web")
    except Exception as exc:
        log.warning("LinkedIn search failed for %s: %s", company.domain, exc)
        return None

    # The domain is authoritative (it was actually crawled); company.name is
    # a scraped guess that can be short or generic - e.g. a mis-extracted
    # name of just "Today" let a search match land on linkedin.com/company/
    # usa-today, a completely unrelated company, because "today" trivially
    # appears in "USA Today | LinkedIn". Requiring the domain's own brand
    # root (which a genuine match's snippet or URL slug should contain) is
    # a much stronger identity check than the name alone.
    #
    # Compared with spaces/hyphens stripped from both sides: a real name
    # like "Example Brand" (domain root "examplebrand") legitimately shows
    # up as "Example Brand" in a snippet or "example-brand" in a URL slug -
    # neither contains the literal, unbroken substring "examplebrand".
    root = domain_root(company.domain).lower()

    for result in results:
        if not _is_linkedin_company_url(result.url):
            continue
        blob = f"{result.title} {result.snippet}".lower()
        if name.lower()[:12] not in blob:
            continue
        if len(root) >= 4:
            blob_compact = re.sub(r"[\s\-]", "", blob)
            url_compact = re.sub(r"[\s\-]", "", result.url.lower())
            if root not in blob_compact and root not in url_compact:
                continue
        norm = normalize_url(result.url) or result.url
        return _clean_linkedin_url(norm), "search"
    return None


def resolve_company_linkedin(db: Session, company: Company,
                             pages: list[ExtractedPage], *,
                             skip_external: bool = False) -> str | None:
    """Mutates company.linkedin_url / linkedin_source / linkedin_checked_at
    in place and flushes. Returns the resolved URL (or None). Safe to call
    on every pipeline run for a company - tier 1 is cheap enough to re-scan
    every time, tier 2 fires at most once ever per company regardless of
    whether it found anything, so re-processing never repeats the spend."""
    if company.linkedin_url:
        return company.linkedin_url

    found = extract_company_linkedin_url(pages)
    if found:
        company.linkedin_url, company.linkedin_source = found
        company.linkedin_checked_at = datetime.now(timezone.utc)
        db.flush()
        return company.linkedin_url

    if skip_external or company.linkedin_checked_at is not None:
        # External calls disabled for this run, or tier 2 was already
        # tried before and came up empty - don't repeat the spend.
        return None

    company.linkedin_checked_at = datetime.now(timezone.utc)
    result = search_company_linkedin_url(db, company)
    if result:
        company.linkedin_url, company.linkedin_source = result
    db.flush()
    return company.linkedin_url

"""External evidence discovery (§33).

Looks beyond the company's own website for funding, news, expansion and
hiring evidence - using sources that are free, public and unauthenticated:

  * SERP + news search (via the SearchProvider abstraction)
  * ATS public job boards (Greenhouse / Lever / Ashby / Workable / Recruitee)
  * SEC EDGAR full-text search (US Form D = private funding round)

Everything discovered is persisted as a `sources` row so the signal engine can
cite it and the UI can link to it.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.engine.extractor import ExtractedPage
from app.models import Company, Source
from app.providers.search.factory import SearchService
from app.utils.text import clean_text, content_hash, truncate
from app.utils.urls import normalize_domain

log = logging.getLogger(__name__)

ATS_ENDPOINTS: list[tuple[str, str]] = [
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"),
    ("lever", "https://api.lever.co/v0/postings/{slug}?mode=json"),
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ("workable", "https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"),
    ("recruitee", "https://{slug}.recruitee.com/api/offers/"),
]

# Legacy (3PL) defaults. A service overrides these with
# config['external_query_templates'] = [[source_type, template, mode], ...].
EXTERNAL_QUERY_TEMPLATES: list[tuple[str, str]] = [
    ("funding", '"{name}" (raises OR raised OR "funding round" OR "seed round" OR "Series A")'),
    ("news", '"{name}" ({domain}) news'),
    ("press_release", '"{name}" (launches OR expands OR "new market" OR "US expansion")'),
    ("crowdfunding", '"{name}" (Kickstarter OR Indiegogo)'),
]


@dataclass
class ExternalEvidence:
    url: str
    title: str
    text: str
    source_type: str
    published_at: datetime | None = None

    def to_page(self) -> ExtractedPage:
        page = ExtractedPage(url=self.url, title=self.title, text=self.text)
        page.page_type = self.source_type
        if self.published_at:
            page.published_at = self.published_at.isoformat()
        return page


# Probing 3 slugs x 5 vendors at a 15s timeout is up to 225 seconds for a
# single company, almost all of it spent waiting on 404s and dead hosts.
# Inside a synchronous request that alone can blow the whole time budget.
ATS_TIMEOUT_SECONDS = 4.0
ATS_MAX_SLUG_CANDIDATES = 2


def _ats_slug_candidates(company: Company) -> list[str]:
    base = (company.name or company.domain.split(".")[0]).lower()
    base = re.sub(r"[^a-z0-9 ]+", "", base).strip()
    compact = base.replace(" ", "")
    hyphen = base.replace(" ", "-")
    root = company.domain.split(".")[0].lower()
    unique = list(dict.fromkeys([c for c in (root, compact, hyphen) if c]))
    return unique[:ATS_MAX_SLUG_CANDIDATES]


def fetch_ats_jobs(company: Company, max_jobs: int = 25) -> list[ExternalEvidence]:
    """Public ATS job boards. No API key, no scraping - these are documented
    public JSON endpoints intended for embedding."""
    out: list[ExternalEvidence] = []
    headers = {"User-Agent": settings.crawler_user_agent}
    budget = time.monotonic() + ATS_TIMEOUT_SECONDS * 6   # hard ceiling

    with httpx.Client(timeout=ATS_TIMEOUT_SECONDS, headers=headers,
                      follow_redirects=True) as client:
        for slug in _ats_slug_candidates(company):
            for vendor, template in ATS_ENDPOINTS:
                if time.monotonic() > budget:
                    log.debug("ATS probing budget exhausted for %s",
                              company.domain)
                    return out
                url = template.format(slug=slug)
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                except Exception:
                    continue

                jobs = _normalize_ats_payload(vendor, data)
                if not jobs:
                    continue
                log.info("Found %d public jobs for %s via %s",
                         len(jobs), company.domain, vendor)
                for job in jobs[:max_jobs]:
                    out.append(ExternalEvidence(
                        url=job["url"], title=job["title"],
                        text=clean_text(f"{job['title']}. {job.get('description','')}")[:8000],
                        source_type="job",
                        published_at=job.get("published_at"),
                    ))
                if out:
                    return out
    return out


def _normalize_ats_payload(vendor: str, data) -> list[dict]:
    jobs: list[dict] = []
    try:
        if vendor == "greenhouse":
            for j in data.get("jobs", []):
                jobs.append({"title": j.get("title", ""),
                             "url": j.get("absolute_url", ""),
                             "description": _strip_html(j.get("content", ""))})
        elif vendor == "lever":
            for j in data if isinstance(data, list) else []:
                jobs.append({"title": j.get("text", ""),
                             "url": j.get("hostedUrl", ""),
                             "description": _strip_html(
                                 j.get("descriptionPlain") or j.get("description", ""))})
        elif vendor == "ashby":
            for j in data.get("jobs", []):
                jobs.append({"title": j.get("title", ""),
                             "url": j.get("jobUrl", ""),
                             "description": _strip_html(j.get("descriptionHtml", ""))})
        elif vendor == "workable":
            for j in data.get("jobs", []):
                jobs.append({"title": j.get("title", ""),
                             "url": j.get("url", ""),
                             "description": _strip_html(j.get("description", ""))})
        elif vendor == "recruitee":
            for j in data.get("offers", []):
                jobs.append({"title": j.get("title", ""),
                             "url": j.get("careers_url", ""),
                             "description": _strip_html(j.get("description", ""))})
    except (AttributeError, TypeError) as exc:
        log.debug("ATS payload parse failed for %s: %s", vendor, exc)
    return [j for j in jobs if j.get("title") and j.get("url")]


def _strip_html(value: str) -> str:
    if not value:
        return ""
    import html as html_mod
    text = re.sub(r"<[^>]+>", " ", value)
    return clean_text(html_mod.unescape(text))


def fetch_sec_form_d(company: Company, max_results: int = 3) -> list[ExternalEvidence]:
    """SEC EDGAR full-text search. Free, authoritative, no API key.
    A Form D filing is a US private securities offering - i.e. a funding round."""
    if not company.name:
        return []
    ua = settings.sec_edgar_user_agent or settings.crawler_user_agent
    try:
        with httpx.Client(timeout=20, headers={"User-Agent": ua}) as client:
            resp = client.get(
                "https://efts.sec.gov/LATEST/search-index",
                params={"q": f'"{company.name}"', "forms": "D"})
            if resp.status_code != 200:
                return []
            data = resp.json()
    except Exception as exc:
        log.debug("EDGAR lookup failed for %s: %s", company.name, exc)
        return []

    out = []
    for hit in (data.get("hits", {}).get("hits", []) or [])[:max_results]:
        src = hit.get("_source", {})
        adsh = src.get("adsh", "")
        cik = (src.get("ciks") or [""])[0]
        filed = src.get("file_date")
        published = None
        if filed:
            try:
                published = datetime.fromisoformat(filed).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        out.append(ExternalEvidence(
            url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-','')}/",
            title=f"SEC Form D filing ({filed})",
            text=f"{company.name} filed a Form D notice of exempt offering with the "
                 f"SEC on {filed}. Form D indicates a private securities offering "
                 f"(funding round).",
            source_type="funding", published_at=published))
    return out


def search_external_signals(db: Session, company: Company,
                            max_per_query: int = 5,
                            templates: list[tuple] | None = None
                            ) -> list[ExternalEvidence]:
    """SERP/news lookups. Templates come from service config when given,
    otherwise the legacy funding/expansion/launch/crowdfunding set."""
    search = SearchService(db)
    if not search.has_provider:
        log.info("No search provider configured; skipping external evidence.")
        return []

    name = company.name or company.domain
    out: list[ExternalEvidence] = []
    seen: set[str] = set()

    rows = templates or [
        (t, q, "news" if t in ("news", "funding", "press_release") else "web")
        for t, q in EXTERNAL_QUERY_TEMPLATES]
    for row in rows:
        source_type, template = row[0], row[1]
        mode = row[2] if len(row) > 2 else "web"
        query = template.format(name=name, domain=company.domain)
        try:
            results = search.search(query, country=company.country,
                                    num=max_per_query, mode=mode)
        except Exception as exc:
            log.warning("External search failed (%s) for %s: %s",
                        source_type, company.domain, exc)
            continue

        for result in results:
            if result.url in seen:
                continue
            # Skip results that are just the company's own site.
            if normalize_domain(result.url) == company.domain:
                continue
            # Never store social-network results: they are mostly personal
            # profiles (linkedin.com/in/...), which this platform must not
            # collect, and are not company evidence.
            if is_social_network_url(result.url):
                continue
            # Require the company name to actually appear, or it's noise.
            blob = f"{result.title} {result.snippet}".lower()
            if name.lower()[:12] not in blob:
                continue
            seen.add(result.url)
            out.append(ExternalEvidence(
                url=result.url, title=result.title,
                text=clean_text(f"{result.title}. {result.snippet}"),
                source_type=source_type,
                published_at=_parse_relative_date(result.published_at)))
    return out


_REL_DATE = re.compile(r"(\d+)\s+(hour|day|week|month|year)s?\s+ago", re.I)


def _parse_relative_date(value: str | None) -> datetime | None:
    if not value:
        return None
    now = datetime.now(timezone.utc)
    match = _REL_DATE.search(value)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        days = {"hour": 1 / 24, "day": 1, "week": 7,
                "month": 30, "year": 365}[unit] * amount
        from datetime import timedelta
        return now - timedelta(days=days)
    try:
        from dateutil import parser
        parsed = parser.parse(value, fuzzy=True)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except Exception:
        return None


ARTICLE_TIMEOUT_SECONDS = 8.0


SOCIAL_NETWORK_HOSTS = ("linkedin.com", "facebook.com", "instagram.com",
                        "twitter.com", "x.com", "tiktok.com", "threads.net",
                        "pinterest.com", "reddit.com", "youtube.com")


def is_social_network_url(url: str | None) -> bool:
    from urllib.parse import urlparse
    host = (urlparse(url or "").hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in SOCIAL_NETWORK_HOSTS)


def fetch_article(item: ExternalEvidence) -> ExternalEvidence:
    """Replace a search snippet with the article it points at, when robots.txt
    allows it. The article - not the snippet - is the evidence. Any failure
    keeps the snippet, so this can only add information."""
    from app.engine.crawler import parse_date
    from app.engine.extractor import extract
    from app.utils.robots import can_fetch

    try:
        if not can_fetch(item.url):
            return item
        with httpx.Client(timeout=ARTICLE_TIMEOUT_SECONDS, follow_redirects=True,
                          headers={"User-Agent": settings.crawler_user_agent}) as client:
            resp = client.get(item.url)
        if resp.status_code != 200 or "html" not in resp.headers.get(
                "content-type", ""):
            return item
        page = extract(resp.text, item.url, resp.status_code)
    except Exception as exc:
        log.debug("Article fetch failed for %s: %s", item.url, exc)
        return item
    if len(page.text or "") < 200:
        return item
    item.text = clean_text(page.text)[:20_000]
    item.title = page.title or item.title
    item.published_at = parse_date(page.published_at) or item.published_at
    return item


FETCHERS = {"ats": fetch_ats_jobs, "sec_form_d": fetch_sec_form_d}


def collect_external_evidence(db: Session, company: Company, config=None
                              ) -> list[ExtractedPage]:
    """Run every external source, persist results, return them as pages the
    signal engine can consume. `config` (ServiceConfig) selects fetchers,
    query templates and article fetching; without it, legacy behaviour."""
    evidence: list[ExternalEvidence] = []
    fetcher_names = (config.external_fetchers if config is not None
                     and config.external_fetchers is not None
                     else list(FETCHERS))
    for fetcher_name in fetcher_names:
        fetcher = FETCHERS.get(fetcher_name)
        if fetcher is None:
            log.warning("Unknown external fetcher '%s' in config", fetcher_name)
            continue
        try:
            evidence.extend(fetcher(company))
        except Exception as exc:
            log.warning("%s failed for %s: %s", fetcher.__name__,
                        company.domain, exc)
    try:
        searched = search_external_signals(
            db, company,
            templates=config.external_query_templates if config is not None else None)
        article_budget = config.fetch_external_articles if config is not None else 0
        for item in searched:
            if article_budget > 0 and item.source_type in ("news", "press_release"):
                item = fetch_article(item)
                article_budget -= 1
            evidence.append(item)
    except Exception as exc:
        log.warning("External search failed for %s: %s", company.domain, exc)

    pages: list[ExtractedPage] = []
    for item in evidence:
        if not item.url:
            continue
        existing = db.execute(
            select(Source).where(Source.company_id == company.id,
                                 Source.url == item.url)
        ).scalar_one_or_none()
        if existing is None:
            db.add(Source(
                company_id=company.id, source_type=item.source_type,
                url=item.url, title=truncate(item.title, 300),
                content=item.text, excerpt=truncate(item.text, 500),
                published_at=item.published_at,
                content_hash=content_hash(item.text)))
            db.flush()
        pages.append(item.to_page())

    log.info("Collected %d external evidence items for %s",
             len(pages), company.domain)
    return pages

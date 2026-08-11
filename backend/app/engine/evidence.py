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
        return page


def _ats_slug_candidates(company: Company) -> list[str]:
    base = (company.name or company.domain.split(".")[0]).lower()
    base = re.sub(r"[^a-z0-9 ]+", "", base).strip()
    compact = base.replace(" ", "")
    hyphen = base.replace(" ", "-")
    root = company.domain.split(".")[0].lower()
    return list(dict.fromkeys([c for c in (root, compact, hyphen) if c]))


def fetch_ats_jobs(company: Company, max_jobs: int = 25) -> list[ExternalEvidence]:
    """Public ATS job boards. No API key, no scraping - these are documented
    public JSON endpoints intended for embedding."""
    out: list[ExternalEvidence] = []
    headers = {"User-Agent": settings.crawler_user_agent}

    with httpx.Client(timeout=15, headers=headers, follow_redirects=True) as client:
        for slug in _ats_slug_candidates(company):
            for vendor, template in ATS_ENDPOINTS:
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
                            max_per_query: int = 5) -> list[ExternalEvidence]:
    """SERP/news lookups for funding, expansion, launches, crowdfunding."""
    search = SearchService(db)
    if not search.has_provider:
        log.info("No search provider configured; skipping external evidence.")
        return []

    name = company.name or company.domain
    out: list[ExternalEvidence] = []
    seen: set[str] = set()

    for source_type, template in EXTERNAL_QUERY_TEMPLATES:
        query = template.format(name=name, domain=company.domain)
        mode = "news" if source_type in ("news", "funding", "press_release") else "web"
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


def collect_external_evidence(db: Session, company: Company
                              ) -> list[ExtractedPage]:
    """Run every external source, persist results, return them as pages the
    signal engine can consume."""
    evidence: list[ExternalEvidence] = []
    for fetcher in (fetch_ats_jobs, fetch_sec_form_d):
        try:
            evidence.extend(fetcher(company))
        except Exception as exc:
            log.warning("%s failed for %s: %s", fetcher.__name__,
                        company.domain, exc)
    try:
        evidence.extend(search_external_signals(db, company))
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

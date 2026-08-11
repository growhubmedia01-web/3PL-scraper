"""Decision-maker identification (§20, §22, §34, Phase 6).

Hard constraints, enforced here rather than by convention:
  * NO email discovery, extraction, verification or storage (§5, §35).
  * Only publicly published sources: the company's own team/leadership/about
    pages, its press releases, and its public job posts.
  * Every record carries a source URL and a confidence label.
  * Suppressed names/domains are never written (GDPR right to object).

Cost control (§50): callers gate this on the opportunity score.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.extractor import ExtractedPage
from app.engine.service_config import ServiceConfig
from app.models import Company, DecisionMaker, Source, Suppression
from app.utils.text import clean_text

log = logging.getLogger(__name__)

# "Jane Smith, COO" / "Jane Smith - Head of Operations" / "Jane Smith | Founder"
NAME_THEN_TITLE = re.compile(
    r"\b([A-Z][a-z'’-]{1,19}(?:\s+[A-Z][a-z'’-]{1,19}){1,2})\s*[,\-–—|]\s*"
    r"((?:[A-Z][A-Za-z&/\. ]{2,48})?(?:Founder|Co-?Founder|CEO|COO|CTO|CFO|"
    r"Chief [A-Z][a-z]+ Officer|President|Managing Director|Director|"
    r"Head of [A-Z][A-Za-z ]{2,30}|VP [A-Z][A-Za-z ]{2,30}|"
    r"Vice President[A-Za-z ]{0,30}|[A-Z][A-Za-z ]{2,30}? Manager))\b")

# "COO, Jane Smith" / "Head of Operations: Jane Smith"
TITLE_THEN_NAME = re.compile(
    r"\b((?:Founder|Co-?Founder|CEO|COO|CTO|CFO|President|Managing Director|"
    r"Head of [A-Z][A-Za-z ]{2,30}|VP [A-Z][A-Za-z ]{2,30}|"
    r"[A-Z][A-Za-z ]{2,30}? Manager))\s*[,:\-–—]\s*"
    r"([A-Z][a-z'’-]{1,19}(?:\s+[A-Z][a-z'’-]{1,19}){1,2})\b")

# "said Jane Smith, COO of Example Brand"
QUOTE_ATTRIBUTION = re.compile(
    r"\b(?:said|says|according to|commented|added)\s+"
    r"([A-Z][a-z'’-]{1,19}(?:\s+[A-Z][a-z'’-]{1,19}){1,2}),?\s+"
    r"(?:the\s+)?((?:Founder|Co-?Founder|CEO|COO|CTO|CFO|President|"
    r"Managing Director|Head of [A-Z][A-Za-z ]{2,30}|"
    r"[A-Z][A-Za-z ]{2,30}? Manager))")

# Words that look like names but aren't people.
NAME_STOPWORDS = {
    "our team", "the team", "contact us", "about us", "read more",
    "privacy policy", "terms conditions", "united states", "united kingdom",
    "new york", "los angeles", "customer service", "free shipping",
    "learn more", "shop now", "sign up", "follow us", "all rights",
    "cookie policy", "size guide", "gift card", "black friday",
}

PERSON_PAGE_TYPES = {"about", "website", "news", "press_release", "job",
                     "careers"}
LEADERSHIP_URL_HINT = re.compile(
    r"/(about|team|leadership|our-story|people|founders|management|who-we-are)",
    re.I)


@dataclass
class DecisionMakerCandidate:
    name: str
    job_title: str
    source_url: str
    source_id: str | None
    source_type: str
    role_priority: int
    confidence: float
    confidence_label: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.name.lower(), (self.job_title or "").lower())


def _plausible_name(name: str) -> bool:
    name = name.strip()
    if len(name) < 4 or len(name) > 60:
        return False
    if name.lower() in NAME_STOPWORDS:
        return False
    parts = name.split()
    if not 2 <= len(parts) <= 3:
        return False
    if not all(p[0].isupper() for p in parts if p):
        return False
    if any(ch.isdigit() for ch in name):
        return False
    return True


def _confidence_for(page_type: str, url: str, pattern: str) -> tuple[float, str]:
    """Confirmed = stated on the company's own leadership/team page.
    Likely = company-owned page or a press release quote.
    Possible = inferred from looser context."""
    on_leadership_page = bool(LEADERSHIP_URL_HINT.search(url))
    if page_type in ("about",) and on_leadership_page:
        return 0.92, "confirmed"
    if page_type in ("about", "website"):
        return 0.78, "likely"
    if page_type in ("press_release", "news") and pattern == "quote":
        return 0.72, "likely"
    if page_type in ("job", "careers"):
        return 0.55, "possible"
    return 0.5, "possible"


def _is_suppressed(db: Session, company: Company, name: str) -> bool:
    rows = db.execute(select(Suppression)).scalars().all()
    for row in rows:
        if row.kind == "person" and row.value.lower() == name.lower():
            return True
        if row.kind == "domain" and row.value.lower() == company.domain.lower():
            return True
    return False


def extract_candidates(pages: list[ExtractedPage], config: ServiceConfig,
                       source_map: dict[str, Source]) -> list[DecisionMakerCandidate]:
    candidates: dict[tuple[str, str], DecisionMakerCandidate] = {}

    for page in pages:
        if page.page_type not in PERSON_PAGE_TYPES:
            continue
        text = clean_text(page.text or "")
        if not text:
            continue
        source = source_map.get(page.url)

        matches: list[tuple[str, str, str]] = []
        for match in NAME_THEN_TITLE.finditer(text):
            matches.append((match.group(1), match.group(2), "name_title"))
        for match in TITLE_THEN_NAME.finditer(text):
            matches.append((match.group(2), match.group(1), "title_name"))
        for match in QUOTE_ATTRIBUTION.finditer(text):
            matches.append((match.group(1), match.group(2), "quote"))

        for name, title, pattern in matches:
            name = clean_text(name)
            title = clean_text(title)
            if not _plausible_name(name):
                continue

            # §21: only roles this service cares about.
            priority = config.role_priority_for(title)
            if priority is None:
                continue

            confidence, label = _confidence_for(page.page_type, page.url, pattern)
            candidate = DecisionMakerCandidate(
                name=name, job_title=title, source_url=page.url,
                source_id=source.id if source else None,
                source_type=page.page_type, role_priority=priority,
                confidence=confidence, confidence_label=label)

            existing = candidates.get(candidate.key)
            if existing is None or candidate.confidence > existing.confidence:
                candidates[candidate.key] = candidate

    ranked = sorted(candidates.values(),
                    key=lambda c: (c.role_priority, -c.confidence))
    return ranked


def find_decision_makers(db: Session, company: Company,
                         pages: list[ExtractedPage], config: ServiceConfig,
                         limit: int = 5) -> list[DecisionMaker]:
    sources = {
        s.url: s for s in db.execute(
            select(Source).where(Source.company_id == company.id)
        ).scalars().all()
    }
    candidates = extract_candidates(pages, config, sources)
    if not candidates:
        log.info("No decision-maker candidates found for %s", company.domain)
        return []

    stored: list[DecisionMaker] = []
    for candidate in candidates[:limit]:
        if _is_suppressed(db, company, candidate.name):
            log.info("Skipping suppressed person for %s", company.domain)
            continue

        existing = db.execute(
            select(DecisionMaker).where(
                DecisionMaker.company_id == company.id,
                DecisionMaker.name == candidate.name,
                DecisionMaker.job_title == candidate.job_title)
        ).scalar_one_or_none()

        if existing:
            if candidate.confidence > existing.confidence:
                existing.confidence = candidate.confidence
                existing.confidence_label = candidate.confidence_label
                existing.profile_url = candidate.source_url
                existing.source = candidate.source_type
                existing.source_id = candidate.source_id
                existing.updated_at = datetime.now(timezone.utc)
            stored.append(existing)
            continue

        row = DecisionMaker(
            company_id=company.id, name=candidate.name,
            job_title=candidate.job_title,
            profile_url=candidate.source_url,      # the page that names them
            source=candidate.source_type, source_id=candidate.source_id,
            confidence=candidate.confidence,
            confidence_label=candidate.confidence_label,
            role_priority=candidate.role_priority)
        db.add(row)
        stored.append(row)

    db.flush()
    log.info("Stored %d decision makers for %s", len(stored), company.domain)
    return stored


def should_research(score: float, config: ServiceConfig) -> bool:
    """§50 cost control: only research decision makers above the threshold."""
    return score >= config.dm_threshold


def primary_decision_maker(db: Session, company_id: str) -> DecisionMaker | None:
    return db.execute(
        select(DecisionMaker)
        .where(DecisionMaker.company_id == company_id)
        .order_by(DecisionMaker.role_priority, DecisionMaker.confidence.desc())
    ).scalars().first()

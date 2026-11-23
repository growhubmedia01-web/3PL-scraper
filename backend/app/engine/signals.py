"""Signal engine (§18, §24, §25, Phase 4).

Fully config-driven: which signals exist, what they're called, what they weigh
and how fast they decay all come from `service_signals` / `service_keywords`.
This file contains no service-specific knowledge.

Every signal produced here carries verbatim evidence and a source id (§29).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.extractor import ExtractedPage
from app.engine.service_config import ServiceConfig
from app.models import Company, Signal, Source
from app.utils.text import best_sentence, contains_phrase

log = logging.getLogger(__name__)

# Legacy (3PL) defaults, kept for backwards compatibility. Services declare
# their own via config['signal_page_affinity'].
# Page types that make a keyword hit meaningful. A "warehouse manager" phrase
# on a careers page is a hiring signal; the same phrase in a blog post is not.
DEFAULT_PAGE_AFFINITY: dict[str, set[str]] = {
    "operations_hiring": {"careers", "job"},
    "fulfillment_hiring": {"careers", "job"},
    "international_shipping": {"shipping", "returns", "website", "other"},
    "international_expansion": {"news", "website", "about", "press_release"},
    "recent_funding": {"news", "funding", "press_release", "about"},
    "product_launch": {"news", "website", "press_release"},
    "crowdfunding": {"news", "crowdfunding", "website", "about"},
}

# Affinity bonus/penalty applied to signal strength.
ON_TOPIC_STRENGTH = 1.0
OFF_TOPIC_STRENGTH = 0.5

DATE_PATTERNS = [
    re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b"),
    re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|"
               r"August|September|October|November|December)\s+(20\d{2})\b", re.I),
    re.compile(r"\b(January|February|March|April|May|June|July|August|"
               r"September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b", re.I),
]


@dataclass
class DetectedSignal:
    signal_type: str
    evidence: str
    description: str
    confidence: float
    source_id: str | None
    detected_at: datetime
    strength: float = 1.0


def _page_source_map(db: Session, company: Company) -> dict[str, Source]:
    rows = db.execute(
        select(Source).where(Source.company_id == company.id)
    ).scalars().all()
    return {r.url: r for r in rows}


def _published_date(page: ExtractedPage, source: Source | None) -> datetime | None:
    if source and source.published_at:
        value = source.published_at
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if getattr(page, "published_at", None):
        from app.engine.crawler import parse_date
        parsed = parse_date(page.published_at)
        if parsed:
            return parsed
    head = (page.text or "")[:2000]
    for pattern in DATE_PATTERNS:
        match = pattern.search(head)
        if match:
            try:
                from dateutil import parser
                parsed = parser.parse(match.group(0), fuzzy=True)
                return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None \
                    else parsed
            except Exception:
                continue
    return None


def _affinity_strength(signal_type: str, page_type: str,
                       config: ServiceConfig) -> float:
    """A keyword hit counts fully only on a page type where it means something.
    Services may override the mapping via config['signal_page_affinity']."""
    affinity = config.page_affinity.get(signal_type)
    if affinity is None:
        return ON_TOPIC_STRENGTH
    return ON_TOPIC_STRENGTH if page_type in affinity else OFF_TOPIC_STRENGTH


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\s+[•|]\s+")


def sentences_with(text: str, phrase: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "")
            if contains_phrase(s, phrase)]


def rule_allows(signal_type: str, page: ExtractedPage, sentence: str,
                config: ServiceConfig) -> bool:
    """Apply a service's polarity rules to one keyword hit.

    Keyword matching alone cannot tell "become a supplier" from "become a
    dealer", or "we are seeking new suppliers" from "we are seeking a US
    distributor". The rules (all optional, all from config):
      exclude_page_types       hit ignored on these page types
      require_page_types       hit only counts on these page types
      suppress_phrases         hit ignored if the sentence or page title
                               contains any of these
      require_context_phrases  sentence must also contain one of these
    """
    rule = config.signal_rules.get(signal_type)
    if not rule:
        return True
    if page.page_type in set(rule.get("exclude_page_types") or []):
        return False
    required_types = rule.get("require_page_types")
    if required_types and page.page_type not in set(required_types):
        return False
    scope = f"{sentence} {page.title or ''}".lower()
    if any(contains_phrase(scope, p) for p in rule.get("suppress_phrases") or []):
        return False
    context = rule.get("require_context_phrases")
    if context and not any(contains_phrase(sentence.lower(), p) for p in context):
        return False
    return True


def detect_signals(db: Session, company: Company, pages: list[ExtractedPage],
                   config: ServiceConfig,
                   external_pages: list[ExtractedPage] | None = None
                   ) -> list[DetectedSignal]:
    """Keyword/evidence-driven detection across crawled + external pages."""
    all_pages = list(pages) + list(external_pages or [])
    sources = _page_source_map(db, company)
    found: dict[str, DetectedSignal] = {}
    undated_factor = config.undated_confidence_factor

    def record(signal_type: str, evidence: str, description: str,
               confidence: float, source_id: str | None,
               detected_at: datetime, strength: float) -> None:
        prior = found.get(signal_type)
        if prior is None or confidence * strength > prior.confidence * prior.strength:
            found[signal_type] = DetectedSignal(
                signal_type=signal_type, evidence=evidence[:1000],
                description=description, confidence=round(confidence, 3),
                source_id=source_id, detected_at=detected_at,
                strength=round(strength, 3))

    # ---- 1. Structural signals derived from classification -------------
    now = datetime.now(timezone.utc)
    home_source = next(
        (s for s in sources.values() if s.source_type == "website"), None)

    if company.is_ecommerce and "ecommerce" in config.signals:
        record("ecommerce",
               f"Detected ecommerce storefront"
               + (f" on {company.platform}" if company.platform else ""),
               "Company sells online", 0.95,
               home_source.id if home_source else None, now, 1.0)

    if company.is_physical_product and "physical_products" in config.signals:
        record("physical_products",
               "Ships tangible goods: shipping and returns policies present",
               "Company ships physical products", 0.9,
               home_source.id if home_source else None, now, 1.0)

    # ---- 2. Keyword-driven signals -------------------------------------
    for page in all_pages:
        source = sources.get(page.url)
        source_id = source.id if source else None
        dated = _published_date(page, source)
        page_date = dated or now
        haystack = page.searchable
        if not haystack:
            continue

        for keyword in config.keywords:
            if not keyword.signal_type:
                continue
            if keyword.signal_type not in config.signals:
                continue
            if not contains_phrase(haystack, keyword.keyword):
                continue

            candidates = sentences_with(page.text or "", keyword.keyword)
            if not candidates and contains_phrase(
                    f"{page.title} {page.meta_description}".lower(),
                    keyword.keyword):
                candidates = [page.title or page.meta_description]
            if not candidates:
                candidates = [best_sentence(page.text or page.title,
                                            keyword.keyword)
                              or f'Matched "{keyword.keyword}" on {page.url}']
            evidence = next(
                (c for c in candidates
                 if rule_allows(keyword.signal_type, page, c, config)), None)
            if evidence is None:
                continue          # every occurrence was suppressed by a rule
            evidence = evidence[:300]

            strength = _affinity_strength(keyword.signal_type,
                                          page.page_type, config)
            confidence = min(0.95, 0.45 + keyword.weight * 0.4)
            if dated is None and config.dimension_of(keyword.signal_type) == "intent":
                confidence *= undated_factor
            signal_def = config.signals[keyword.signal_type]

            record(keyword.signal_type, evidence, signal_def.signal_name,
                   confidence, source_id, page_date, strength)

    # ---- 3. Structured job-posting boost -------------------------------
    # A careers page that lists a matching role is much stronger evidence than
    # the same phrase appearing in prose. Which signals count as hiring comes
    # from config (keywords in the "hiring" category), never from code.
    hiring_types = config.hiring_signal_types
    for page in all_pages:
        if page.page_type not in ("careers", "job"):
            continue
        source = sources.get(page.url)
        for signal_type in hiring_types:
            if signal_type not in config.signals:
                continue
            for keyword in config.keywords_for(signal_type):
                if not contains_phrase(page.searchable, keyword.keyword):
                    continue
                sentence = (best_sentence(page.text, keyword.keyword)
                            or page.title or "")
                if not rule_allows(signal_type, page, sentence, config):
                    continue
                evidence = sentence or f'Open role matching "{keyword.keyword}"'
                record(signal_type, evidence,
                       config.signals[signal_type].signal_name,
                       0.92, source.id if source else None,
                       _published_date(page, source) or now, 1.0)
                break

    return list(found.values())


def persist_signals(db: Session, company: Company, config: ServiceConfig,
                    detected: list[DetectedSignal]) -> list[Signal]:
    """Replace this service's signals for this company. Sets expires_at from
    the service's configured decay window (§25)."""
    db.query(Signal).filter(
        Signal.company_id == company.id,
        Signal.service_id == config.id,
    ).delete(synchronize_session=False)

    rows: list[Signal] = []
    for item in detected:
        signal_def = config.signals.get(item.signal_type)
        if signal_def is None:
            continue
        detected_at = item.detected_at
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=timezone.utc)
        expires_at = (detected_at + timedelta(days=signal_def.decay_days)
                      if signal_def.decay_days else None)
        row = Signal(
            company_id=company.id, service_id=config.id,
            signal_type=item.signal_type, strength=item.strength,
            description=item.description, evidence=item.evidence,
            source_id=item.source_id, confidence=item.confidence,
            detected_at=detected_at, expires_at=expires_at,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def effective_strength(signal: Signal, signal_def, now: datetime | None = None
                       ) -> float:
    """Time decay (§25).

    Linear decay from full strength at detection to zero at expiry. A signal
    with no decay_days never decays. Expired signals contribute nothing.
    """
    now = now or datetime.now(timezone.utc)
    detected_at = signal.detected_at
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=timezone.utc)

    base = float(signal.strength) * float(signal.confidence)
    if signal_def is None or not signal_def.decay_days:
        return base

    age_days = max((now - detected_at).total_seconds() / 86400.0, 0.0)
    if age_days >= signal_def.decay_days:
        return 0.0
    decay = 1.0 - (age_days / signal_def.decay_days)
    return base * decay


def load_signals(db: Session, company_id: str, service_id: str) -> list[Signal]:
    return list(db.execute(
        select(Signal).where(Signal.company_id == company_id,
                             Signal.service_id == service_id)
    ).scalars().all())

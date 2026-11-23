"""Product-interest intelligence (007).

Answers "WHAT might this company want to buy?" - and, as importantly, how
strong the evidence for each answer is. Driven entirely by service config:

  product_taxonomy         {category: {subcategory: [terms]}}
  vehicle_segments         {segment: [terms]}         (optional)
  vehicle_platforms        [names]  - fitment, never treated as suppliers
  interest_type_by_signal  {signal_type: EXPLICITLY_SEEKING | RECENTLY_ADDED}
  adjacent_categories      {category: [adjacent categories]}
  brand_patterns           [regex with one capture group for the brand]
  carried_page_types       page types read for CURRENTLY_CARRIED
  product_attributes       {attribute: {value: [terms]}}  (optional) - e.g.
                           format, protein, life stage, stated claims. Only
                           values whose terms appear in the evidence text
                           are recorded; claims are stored as the company's
                           own wording, never as verified facts.

Hard rules, enforced here:
  * Every record points at the source it was read from. No source, no record.
  * Products are only ever extracted from text - never generated.
  * CURRENTLY_CARRIED and INFERRED_FIT are recorded as exactly that, never
    promoted to buying intent.
  * When no specific product is identifiable, a category-less record says so
    rather than guessing.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.extractor import ExtractedPage
from app.engine.service_config import ServiceConfig
from app.models import Company, ProductInterest, Signal, Source
from app.utils.text import clean_text, contains_phrase

log = logging.getLogger(__name__)

EXPLICITLY_SEEKING = "EXPLICITLY_SEEKING"
RECENTLY_ADDED = "RECENTLY_ADDED"
CURRENTLY_CARRIED = "CURRENTLY_CARRIED"
INFERRED_FIT = "INFERRED_FIT"
BUYING_TYPES = (EXPLICITLY_SEEKING, RECENTLY_ADDED)

ARTICLE_PAGE_TYPES = {"news", "press_release", "job"}
DEFAULT_CARRIED_PAGE_TYPES = {"brands", "website", "about", "other"}
_SPLIT = re.compile(r"(?<=[.!?])\s+")
_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+(\d{1,2}),?\s+(20\d{2})\b")


@dataclass
class InterestRecord:
    interest_type: str
    category: str | None
    subcategory: str | None
    products: list[str] = field(default_factory=list)
    vehicle_segments: list[str] = field(default_factory=list)
    vehicle_platforms: list[str] = field(default_factory=list)
    brand: str | None = None
    attributes: dict[str, list[str]] = field(default_factory=dict)
    reason: str = ""
    signal_type: str | None = None
    signal_id: str | None = None
    source_id: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    event_date: datetime | None = None
    evidence: str = ""
    confidence: float = 0.5

    @property
    def key(self) -> tuple:
        return (self.interest_type, self.category, self.subcategory, self.brand)


def _variants(term: str) -> list[str]:
    term = term.lower().strip()
    out = {term}
    if term.endswith("ies"):
        out.add(term[:-3] + "y")
    elif term.endswith("es") and term[:-2].endswith(("sh", "ch", "x")):
        out.add(term[:-2])
    elif term.endswith("s") and not term.endswith("ss"):
        out.add(term[:-1])
    else:
        out.add(term + "s")
    return sorted(out, key=len, reverse=True)


def match_products(text: str, taxonomy: dict[str, dict[str, list[str]]]
                   ) -> dict[tuple[str, str], list[str]]:
    """{(category, subcategory): [matched product terms]} found in text."""
    low = (text or "").lower()
    found: dict[tuple[str, str], list[str]] = {}
    for category, subs in taxonomy.items():
        for subcategory, terms in subs.items():
            for term in terms:
                if any(contains_phrase(low, v) for v in _variants(term)):
                    found.setdefault((category, subcategory), [])
                    if term not in found[(category, subcategory)]:
                        found[(category, subcategory)].append(term)
    return found


def match_segments(text: str, segments: dict[str, list[str]]) -> list[str]:
    low = (text or "").lower()
    return [seg for seg, terms in segments.items()
            if any(contains_phrase(low, t) for t in terms)]


def match_attributes(text: str, vocab: dict[str, dict[str, list[str]]]
                     ) -> dict[str, list[str]]:
    """{attribute: [values]} whose terms appear in text. Empty attributes
    are omitted, so nothing is ever recorded without textual evidence."""
    low = (text or "").lower()
    out: dict[str, list[str]] = {}
    for attribute, values in (vocab or {}).items():
        hits = [value for value, terms in values.items()
                if any(contains_phrase(low, v) for t in terms for v in _variants(t))]
        if hits:
            out[attribute] = hits
    return out


def match_platforms(text: str, platforms: list[str]) -> list[str]:
    low = (text or "").lower()
    return [p for p in platforms if contains_phrase(low, p.lower())]


def extract_brands(text: str, config: ServiceConfig,
                   exclude: set[str]) -> list[str]:
    """Brand/manufacturer names from config regexes. Vehicle platforms and
    the company itself are excluded - a vehicle fitment is not a supplier."""
    out: list[str] = []
    platforms = {p.lower() for p in config.vehicle_platforms}
    for pattern in config.brand_patterns:
        try:
            regex = re.compile(pattern)
        except re.error:
            log.warning("Invalid brand pattern in config: %s", pattern)
            continue
        for m in regex.finditer(text or ""):
            name = clean_text(m.group(1)).strip(" ,.'\"")
            if not name or len(name) < 2 or len(name) > 60:
                continue
            low = name.lower()
            if low in platforms or low in exclude:
                continue
            if any(low == e or low.startswith(e + " ") for e in exclude):
                continue
            if name not in out:
                out.append(name)
    return out[:5]


def evidence_window(page: ExtractedPage, anchor: str | None,
                    radius: int = 2) -> tuple[str, bool]:
    """Text that a claim may be read from. For a news article or job post the
    whole document is about the event; for a company's own page only the
    sentences around the triggering evidence are. Returns (text, is_local)."""
    text = clean_text(page.text or "")
    if page.page_type in ARTICLE_PAGE_TYPES:
        return text[:8000], False
    sentences = _SPLIT.split(text)
    if anchor:
        needle = anchor.strip()[:80].lower()
        for i, sentence in enumerate(sentences):
            if needle and needle in sentence.lower():
                lo, hi = max(0, i - radius), min(len(sentences), i + radius + 1)
                return " ".join(sentences[lo:hi]), True
    return text[:1500], False


def _event_date(text: str) -> datetime | None:
    m = _DATE.search(text or "")
    if not m:
        return None
    try:
        from dateutil import parser
        return parser.parse(m.group(0)).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def build_interests(company: Company, signals: list[Signal],
                    pages: list[ExtractedPage], sources: dict[str, Source],
                    config: ServiceConfig) -> list[InterestRecord]:
    taxonomy = config.product_taxonomy
    if not taxonomy:
        return []
    by_source_id = {s.id: s for s in sources.values()}
    by_url = {p.url: p for p in pages}
    exclude = {(company.name or "").lower(), company.domain.split(".")[0].lower()}
    exclude.discard("")
    records: dict[tuple, InterestRecord] = {}
    attribute_vocab = config.raw_config.get("product_attributes") or {}

    def add(record: InterestRecord) -> None:
        if not (record.source_id or record.source_url):
            return                       # provenance is mandatory
        prior = records.get(record.key)
        if prior is None or record.confidence > prior.confidence:
            records[record.key] = record

    # ---- 1. Buying-intent records anchored on detected signals ----------
    mapping = config.interest_type_by_signal
    for signal in signals:
        interest_type = mapping.get(signal.signal_type)
        if interest_type not in BUYING_TYPES or not signal.source_id:
            continue
        source = by_source_id.get(signal.source_id)
        if source is None:
            continue
        page = by_url.get(source.url) or ExtractedPage(
            url=source.url, title=source.title or "",
            text=source.content or source.excerpt or "",
            page_type=source.source_type)
        window, local = evidence_window(page, signal.evidence)
        products = match_products(window, taxonomy)
        segments = match_segments(window, config.vehicle_segments)
        platforms = match_platforms(window, config.vehicle_platforms)
        brands = extract_brands(window, config, exclude)
        brand = brands[0] if brands else None
        attributes = match_attributes(window, attribute_vocab)
        signal_name = config.signals.get(signal.signal_type)
        label = signal_name.signal_name if signal_name else signal.signal_type
        event = _event_date(window)
        published = source.published_at
        base_conf = float(signal.confidence) * (0.9 if local else 0.75)

        if products:
            for (category, subcategory), terms in products.items():
                add(InterestRecord(
                    interest_type=interest_type, category=category,
                    subcategory=subcategory, products=terms,
                    vehicle_segments=segments, vehicle_platforms=platforms,
                    brand=brand, attributes=attributes,
                    reason=f"{label}: products named in the evidence",
                    signal_type=signal.signal_type, signal_id=signal.id,
                    source_id=source.id, source_url=source.url,
                    published_at=published,
                    event_date=event if event and event != published else None,
                    evidence=(signal.evidence or window)[:500],
                    confidence=round(min(base_conf, 0.95), 3)))
        else:
            add(InterestRecord(
                interest_type=interest_type, category=None, subcategory=None,
                vehicle_segments=segments, vehicle_platforms=platforms,
                brand=brand, attributes=attributes,
                reason=f"{label}. {config.no_product_demand_message}",
                signal_type=signal.signal_type, signal_id=signal.id,
                source_id=source.id, source_url=source.url,
                published_at=published, event_date=event,
                evidence=(signal.evidence or window)[:500],
                confidence=round(min(base_conf * 0.8, 0.9), 3)))

    buying_subcats = {(r.category, r.subcategory) for r in records.values()
                      if r.category}

    # ---- 2. CURRENTLY_CARRIED: present in the assortment, NOT intent ------
    carried_types = set(config.raw_config.get("carried_page_types")
                        or DEFAULT_CARRIED_PAGE_TYPES)
    for page in pages:
        if page.page_type not in carried_types:
            continue
        if company.domain not in (page.url or "").lower():
            continue                     # only the company's own pages
        source = sources.get(page.url)
        found = match_products(page.text or "", taxonomy)
        for (category, subcategory), terms in found.items():
            if (category, subcategory) in buying_subcats:
                continue
            sentence = next((s for s in _SPLIT.split(page.text or "")
                             if any(contains_phrase(s.lower(), v)
                                    for t in terms for v in _variants(t))), "")
            add(InterestRecord(
                interest_type=CURRENTLY_CARRIED, category=category,
                subcategory=subcategory, products=terms,
                vehicle_segments=match_segments(sentence, config.vehicle_segments),
                attributes=match_attributes(sentence, attribute_vocab),
                reason="Present in the current assortment; this does not "
                       "establish new buying intent",
                source_id=source.id if source else None, source_url=page.url,
                published_at=source.published_at if source else None,
                evidence=clean_text(sentence)[:300],
                confidence=0.6 if page.page_type == "brands" else 0.45))

    # ---- 3. INFERRED_FIT: adjacent to evidenced demand, NOT intent -------
    evidenced_categories = {r.category for r in records.values() if r.category}
    anchors = [r for r in records.values()
               if r.interest_type in BUYING_TYPES and r.category]
    for anchor in anchors:
        for adjacent in config.adjacent_categories.get(anchor.category, []):
            if adjacent in evidenced_categories or adjacent not in taxonomy:
                continue
            add(InterestRecord(
                interest_type=INFERRED_FIT, category=adjacent, subcategory=None,
                reason=(f"Inferred: adjacent to {anchor.category} "
                        f"({anchor.interest_type.lower().replace('_', ' ')}). "
                        f"No direct purchasing evidence for this category."),
                signal_type=anchor.signal_type, signal_id=anchor.signal_id,
                source_id=anchor.source_id, source_url=anchor.source_url,
                published_at=anchor.published_at,
                evidence=anchor.evidence[:300], confidence=0.25))
            evidenced_categories.add(adjacent)

    order = {EXPLICITLY_SEEKING: 0, RECENTLY_ADDED: 1, CURRENTLY_CARRIED: 2,
             INFERRED_FIT: 3}
    return sorted(records.values(),
                  key=lambda r: (order[r.interest_type], -r.confidence))


def persist_interests(db: Session, company: Company, config: ServiceConfig,
                      records: list[InterestRecord]) -> list[ProductInterest]:
    db.query(ProductInterest).filter(
        ProductInterest.company_id == company.id,
        ProductInterest.service_id == config.id,
    ).delete(synchronize_session=False)
    rows = []
    for r in records:
        if not (r.source_id or r.source_url):
            continue                     # provenance is mandatory, here too
        row = ProductInterest(
            company_id=company.id, service_id=config.id, signal_id=r.signal_id,
            signal_type=r.signal_type, interest_type=r.interest_type,
            category=r.category, subcategory=r.subcategory,
            products=r.products, vehicle_segments=r.vehicle_segments,
            vehicle_platforms=r.vehicle_platforms, brand=r.brand,
            attributes=r.attributes, reason=r.reason, source_id=r.source_id, source_url=r.source_url,
            published_at=r.published_at, event_date=r.event_date,
            evidence=r.evidence, confidence=r.confidence)
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def demand_summary(records, config: ServiceConfig) -> str:
    """One line for the lead list / CSV. Only buying-intent records with a
    named category count as demand."""
    buying = [r for r in records
              if r.interest_type in BUYING_TYPES and r.category]
    if not buying:
        return config.no_product_demand_message
    parts = []
    for r in buying[:4]:
        what = r.subcategory or r.category
        parts.append(f"{what} ({r.interest_type.lower().replace('_', ' ')})")
    return "; ".join(parts)


def buying_categories(records) -> list[str]:
    out: list[str] = []
    for r in records:
        if r.interest_type in BUYING_TYPES and r.category and r.category not in out:
            out.append(r.category)
    return out


def run(db: Session, company: Company, signals: list[Signal],
        pages: list[ExtractedPage], config: ServiceConfig
        ) -> list[ProductInterest]:
    sources = {s.url: s for s in db.execute(
        select(Source).where(Source.company_id == company.id)).scalars()}
    records = build_interests(company, signals, pages, sources, config)
    return persist_interests(db, company, config, records)

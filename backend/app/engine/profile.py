"""Company profile facts with provenance (007).

Service-agnostic. Reads ONLY what a company publishes about itself (or what
a supplied external page states) and records where and when it was read:

  * employee count -> employee band   (never estimated; unknown stays unknown)
  * headquarters + US state
  * dealer / reseller count, states served, facility locations
  * stated revenue figures
  * supplier / vendor intake page URL

Every fact is a `company_facts` row with source_id, source_url, evidence,
confidence and observed_at. Nothing here invents a number.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.extractor import ExtractedPage
from app.models import Company, CompanyFact, Source
from app.utils.text import clean_text

log = logging.getLogger(__name__)

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
STATE_CODES = set(US_STATES.values())

_NUM = r"(\d{1,3}(?:,\d{3})+|\d{1,6})"
_QUAL = r"(?:over |more than |nearly |almost |about |approximately |around |some )?"

EMPLOYEE_PATTERNS = [
    re.compile(_QUAL + _NUM + r"\+?\s+(?:full[- ]time\s+)?(?:employees|team members|"
               r"staff members|associates|employee-owners|people on our team)\b", re.I),
    re.compile(r"\b(?:team|staff|workforce) of " + _QUAL + _NUM + r"\b", re.I),
    re.compile(r"\bemploys " + _QUAL + _NUM + r"\b", re.I),
]
DEALER_COUNT = re.compile(
    _QUAL + _NUM + r"\+?\s+(?:independent |authorized |active )?"
    r"(?:dealers|dealer locations|dealerships|retailers|resellers|retail partners)\b",
    re.I)
STATES_SERVED = re.compile(
    r"\bserv(?:es|ing|e)\b[^.]{0,60}?\b(all 50|\d{1,2})\s+states\b", re.I)
FACILITY = re.compile(
    r"\b(?:distribution|warehouse|fulfillment) (?:centers?|centres?|facilit(?:y|ies)|"
    r"locations?|hubs?)\s+(?:located\s+)?in\s+([A-Z][A-Za-z .,&]{2,90}?)(?:[.;]|$| and serv)",
    re.M)
HQ_PATTERNS = [
    re.compile(r"\b(?:headquartered|based|located) in ([A-Z][A-Za-z .]{2,30}),\s*"
               r"([A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?)\b"),
    re.compile(r"\bheadquarters (?:is |are )?(?:located )?in ([A-Z][A-Za-z .]{2,30}),\s*"
               r"([A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?)\b"),
]
REVENUE = re.compile(
    r"\$\s?(\d+(?:\.\d+)?)\s*(million|billion|m|bn)\b[^.]{0,30}?\b(?:in )?"
    r"(?:annual )?(?:sales|revenue)", re.I)

OWN_PAGE_TYPES = {"website", "about", "other", "careers", "brands", "supplier",
                  "dealer", "news", "shipping", "returns"}


@dataclass
class Fact:
    fact_type: str
    value: str
    source_url: str
    evidence: str
    confidence: float
    is_estimate: bool = False


def _sentence(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start) + 1, 0)
    right = text.find(".", end)
    right = len(text) if right == -1 else right + 1
    return clean_text(text[left:right])[:300]


def _to_int(value: str) -> int | None:
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return None


def band_for(count: int | None, bands: list[dict]) -> str | None:
    if count is None:
        return None
    for band in bands:
        lo = band.get("min") or 0
        hi = band.get("max")
        if count >= lo and (hi is None or count <= hi):
            return band["band"]
    return None


def _state_code(value: str) -> str | None:
    value = value.strip()
    if value.upper() in STATE_CODES and len(value) == 2:
        return value.upper()
    return US_STATES.get(value.lower())


def extract_facts(company: Company, pages: list[ExtractedPage]) -> list[Fact]:
    facts: list[Fact] = []
    own_host = company.domain.lower()
    for page in pages:
        text = page.text or ""
        if not text:
            continue
        own = own_host in (page.url or "").lower()
        if not own and page.page_type not in ("news", "press_release"):
            continue
        base_conf = 0.8 if own and page.page_type == "about" else (
            0.7 if own else 0.55)

        if own:
            for pattern in EMPLOYEE_PATTERNS:
                for m in pattern.finditer(text):
                    count = _to_int(m.group(1))
                    if count is None or count < 2 or count > 500_000:
                        continue
                    facts.append(Fact("employee_count", str(count), page.url,
                                      _sentence(text, m.start(), m.end()),
                                      base_conf))
                    break

        for m in DEALER_COUNT.finditer(text):
            count = _to_int(m.group(1))
            if count and count >= 5:
                facts.append(Fact("dealer_count", str(count), page.url,
                                  _sentence(text, m.start(), m.end()), base_conf))
                break
        for m in STATES_SERVED.finditer(text):
            facts.append(Fact("states_served", m.group(1), page.url,
                              _sentence(text, m.start(), m.end()), base_conf))
            break
        for m in FACILITY.finditer(text):
            facts.append(Fact("facility_location", clean_text(m.group(1))[:90],
                              page.url, _sentence(text, m.start(), m.end()),
                              base_conf))
        for pattern in HQ_PATTERNS:
            m = pattern.search(text)
            if m and _state_code(m.group(2)):
                facts.append(Fact(
                    "headquarters",
                    f"{clean_text(m.group(1))}, {_state_code(m.group(2))}",
                    page.url, _sentence(text, m.start(), m.end()),
                    base_conf if own else 0.5))
                break
        for m in REVENUE.finditer(text):
            if own or page.page_type in ("news", "press_release"):
                facts.append(Fact("revenue_stated",
                                  f"${m.group(1)} {m.group(2)}", page.url,
                                  _sentence(text, m.start(), m.end()), base_conf))
                break
        if own and page.page_type == "supplier":
            facts.append(Fact("supplier_intake_url", page.url, page.url,
                              clean_text(page.title or text[:200])[:200], 0.85))

    # JSON-LD Organization blocks: structured, company-published.
    for page in pages:
        for block in page.json_ld or []:
            if block.get("@type") not in ("Organization", "Corporation",
                                          "LocalBusiness", "WholesaleStore"):
                continue
            employees = block.get("numberOfEmployees")
            if isinstance(employees, dict):
                employees = employees.get("value") or employees.get("minValue")
            if employees and _to_int(str(employees)):
                facts.append(Fact("employee_count", str(_to_int(str(employees))),
                                  page.url, "schema.org numberOfEmployees", 0.8))
            address = block.get("address")
            if isinstance(address, dict) and address.get("addressRegion"):
                code = _state_code(str(address["addressRegion"]))
                if code:
                    city = address.get("addressLocality") or ""
                    facts.append(Fact("headquarters",
                                      f"{city}, {code}".strip(", "),
                                      page.url, "schema.org address", 0.85))
    return facts


def apply_profile(db: Session, company: Company, pages: list[ExtractedPage],
                  size_bands: list[dict]) -> list[CompanyFact]:
    """Persist facts and update the company's summary columns.

    Employee band comes from the highest-confidence company-published count.
    With no such count the band stays NULL ('unknown') - deliberately.
    """
    facts = extract_facts(company, pages)
    sources = {s.url: s for s in db.execute(
        select(Source).where(Source.company_id == company.id)).scalars()}
    existing = {(f.fact_type, f.value): f for f in db.execute(
        select(CompanyFact).where(CompanyFact.company_id == company.id)).scalars()}
    now = datetime.now(timezone.utc)
    rows: list[CompanyFact] = []
    for fact in facts:
        key = (fact.fact_type, fact.value)
        source = sources.get(fact.source_url)
        row = existing.get(key)
        if row is None:
            row = CompanyFact(company_id=company.id, fact_type=fact.fact_type,
                              value=fact.value)
            db.add(row)
            existing[key] = row
        row.source_id = source.id if source else None
        row.source_url = fact.source_url
        row.evidence = fact.evidence
        row.confidence = max(fact.confidence, row.confidence or 0)
        row.is_estimate = fact.is_estimate
        row.observed_at = now
        rows.append(row)

    counts = sorted((f for f in facts if f.fact_type == "employee_count"),
                    key=lambda f: f.confidence, reverse=True)
    if counts:
        best = counts[0]
        company.employee_count = int(best.value)
        company.employee_band = band_for(int(best.value), size_bands)
        company.size_confidence = best.confidence
        company.size_source_url = best.source_url
        company.size_observed_at = now
    hq = sorted((f for f in facts if f.fact_type == "headquarters"),
                key=lambda f: f.confidence, reverse=True)
    if hq:
        company.headquarters = hq[0].value
        company.headquarters_state = hq[0].value.rsplit(", ", 1)[-1][:2]
        if not company.country and company.headquarters_state in STATE_CODES:
            company.country = "US"
    db.flush()
    return rows

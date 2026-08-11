"""HTML -> clean text + structured page facts (§31 storage, §60 detection input).

Service-agnostic: this module extracts *facts*, never opinions about a service.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from app.utils.text import clean_text, content_hash
from app.utils.urls import normalize_url

log = logging.getLogger(__name__)

try:
    import trafilatura
    _HAS_TRAFILATURA = True
except Exception:  # pragma: no cover
    _HAS_TRAFILATURA = False

# Page-type routing (§31 priority pages)
PAGE_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("shipping", re.compile(r"/(shipping|delivery|shipping-policy|delivery-information)", re.I)),
    ("returns", re.compile(r"/(returns?|return-policy|refunds?|exchanges)", re.I)),
    ("careers", re.compile(r"/(careers?|jobs?|join-us|work-with-us|were-hiring|hiring|vacancies)", re.I)),
    ("about", re.compile(r"/(about|about-us|our-story|who-we-are|team|leadership|people|founders)", re.I)),
    ("news", re.compile(r"/(news|press|blog|journal|updates|media)", re.I)),
    ("other", re.compile(r"/(contact|faq|help|stockists|wholesale)", re.I)),
]

PRIORITY_PATHS: list[tuple[str, str]] = [
    ("/", "website"),
    ("/about", "about"), ("/about-us", "about"), ("/our-story", "about"),
    ("/pages/about", "about"), ("/pages/about-us", "about"),
    ("/team", "about"), ("/leadership", "about"), ("/pages/our-team", "about"),
    ("/contact", "other"), ("/pages/contact", "other"),
    ("/shipping", "shipping"), ("/shipping-policy", "shipping"),
    ("/pages/shipping", "shipping"), ("/pages/shipping-policy", "shipping"),
    ("/policies/shipping-policy", "shipping"), ("/delivery", "shipping"),
    ("/returns", "returns"), ("/return-policy", "returns"),
    ("/pages/returns", "returns"), ("/policies/refund-policy", "returns"),
    ("/careers", "careers"), ("/jobs", "careers"), ("/pages/careers", "careers"),
    ("/blog", "news"), ("/news", "news"), ("/press", "news"),
    ("/pages/press", "news"),
]


@dataclass
class ExtractedPage:
    url: str
    title: str = ""
    text: str = ""
    html: str = ""
    page_type: str = "website"
    meta_description: str = ""
    links: list[str] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    generators: list[str] = field(default_factory=list)
    json_ld: list[dict] = field(default_factory=list)
    currencies: list[str] = field(default_factory=list)
    http_status: int | None = None

    @property
    def hash(self) -> str:
        return content_hash(self.text)

    @property
    def searchable(self) -> str:
        """Everything a keyword detector should look at, lowercased."""
        return " ".join([self.title, self.meta_description, self.text]).lower()


def classify_page_type(url: str) -> str:
    for page_type, pattern in PAGE_TYPE_PATTERNS:
        if pattern.search(url):
            return page_type
    return "website"


_CURRENCY_TOKENS = {
    "USD": [r"\$\s?\d", r"\bUSD\b"],
    "GBP": [r"£\s?\d", r"\bGBP\b"],
    "EUR": [r"€\s?\d", r"\bEUR\b"],
    "CAD": [r"\bCAD\b", r"\bCA\$"],
    "AUD": [r"\bAUD\b", r"\bA\$"],
    "INR": [r"₹\s?\d", r"\bINR\b"],
    "JPY": [r"¥\s?\d", r"\bJPY\b"],
}


def _detect_currencies(html: str) -> list[str]:
    found = []
    for code, patterns in _CURRENCY_TOKENS.items():
        if any(re.search(p, html) for p in patterns):
            found.append(code)
    return found


def _extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    import json
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (ValueError, TypeError):
            continue
        if isinstance(data, list):
            out.extend(d for d in data if isinstance(d, dict))
        elif isinstance(data, dict):
            out.append(data)
    return out


def extract(html: str, url: str, http_status: int | None = None) -> ExtractedPage:
    """Parse a page once; everything downstream reads this object."""
    page = ExtractedPage(url=url, html=html, http_status=http_status,
                         page_type=classify_page_type(url))
    if not html:
        return page

    soup = BeautifulSoup(html, "lxml")

    if soup.title and soup.title.string:
        page.title = clean_text(soup.title.string)[:300]

    meta = soup.find("meta", attrs={"name": "description"}) or \
        soup.find("meta", attrs={"property": "og:description"})
    if meta and meta.get("content"):
        page.meta_description = clean_text(meta["content"])[:500]

    for tag in soup.find_all("meta", attrs={"name": "generator"}):
        if tag.get("content"):
            page.generators.append(tag["content"])

    # Main body text: trafilatura gives cleaner output on article-like pages,
    # but drops nav/policy text we need, so fall back to full-page text.
    body_text = ""
    if _HAS_TRAFILATURA:
        try:
            body_text = trafilatura.extract(
                html, include_comments=False, include_tables=True,
                favor_recall=True, url=url) or ""
        except Exception as exc:
            log.debug("trafilatura failed on %s: %s", url, exc)
    if len(body_text) < 200:
        for junk in soup(["script", "style", "noscript", "svg"]):
            junk.decompose()
        body_text = soup.get_text(" ", strip=True)
    page.text = clean_text(body_text)[:120_000]

    for script in soup.find_all("script"):
        src = script.get("src")
        if src:
            page.scripts.append(src)

    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        link = normalize_url(anchor["href"], base=url)
        if not link or link in seen:
            continue
        seen.add(link)
        page.links.append(link)

    from urllib.parse import urlparse
    host = urlparse(url).netloc.lower().removeprefix("www.")
    page.internal_links = [
        l for l in page.links
        if urlparse(l).netloc.lower().removeprefix("www.") == host]

    page.json_ld = _extract_json_ld(soup)
    page.currencies = _detect_currencies(html[:200_000])
    return page


def candidate_urls(base_url: str, discovered_links: list[str] | None = None,
                   limit: int = 12) -> list[tuple[str, str]]:
    """Priority pages first, then anything the homepage linked to that looks
    like a priority page. Returns [(url, page_type)]."""
    from urllib.parse import urlparse
    base = base_url.rstrip("/")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for path, page_type in PRIORITY_PATHS:
        url = base if path == "/" else f"{base}{path}"
        norm = normalize_url(url)
        if norm and norm not in seen:
            seen.add(norm)
            out.append((norm, page_type))

    for link in discovered_links or []:
        norm = normalize_url(link)
        if not norm or norm in seen:
            continue
        page_type = classify_page_type(norm)
        if page_type == "website":
            continue
        depth = len([p for p in urlparse(norm).path.split("/") if p])
        if depth > 3:
            continue
        seen.add(norm)
        out.append((norm, page_type))

    return out[:limit]

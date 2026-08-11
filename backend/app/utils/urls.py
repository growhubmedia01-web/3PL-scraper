"""URL and domain normalization (§15, §51)."""
from __future__ import annotations

import re
from urllib.parse import urlparse, urlunparse

import tldextract

_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())  # offline snapshot

# Aggregators, marketplaces, social, news - never treated as company domains.
BLOCKED_DOMAINS: set[str] = {
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "tiktok.com", "pinterest.com", "reddit.com", "medium.com",
    "wikipedia.org", "amazon.com", "amazon.co.uk", "ebay.com", "etsy.com",
    "walmart.com", "alibaba.com", "aliexpress.com", "shopify.com",
    "wordpress.com", "wix.com", "squarespace.com", "google.com", "bing.com",
    "myshopify.com", "bigcartel.com", "storenvy.com", "ecwid.com",
    "shopifypreview.com", "webflow.io", "wixsite.com", "weebly.com",
    "yahoo.com", "apple.com", "microsoft.com", "github.com", "crunchbase.com",
    "bloomberg.com", "forbes.com", "techcrunch.com", "businesswire.com",
    "prnewswire.com", "kickstarter.com", "indiegogo.com", "glassdoor.com",
    "indeed.com", "greenhouse.io", "lever.co", "workable.com", "ashbyhq.com",
    "yelp.com", "trustpilot.com", "producthunt.com", "substack.com",
    "notion.site", "gov.uk", "sec.gov", "companieshouse.gov.uk",
}

TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid|gclid|msclkid|mc_cid|mc_eid|ref|source|_ga)", re.I)


def normalize_domain(value: str | None) -> str | None:
    """'https://WWW.Example.co.uk/path?x=1' -> 'example.co.uk'.

    Returns None for blocked, malformed, or non-registrable domains.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    if "://" not in value:
        value = "http://" + value
    try:
        host = urlparse(value).netloc.split("@")[-1].split(":")[0].lower()
    except ValueError:
        return None
    if not host:
        return None

    ext = _EXTRACT(host)
    if not ext.domain or not ext.suffix:
        return None
    registrable = f"{ext.domain}.{ext.suffix}".lower()

    # Check both the registrable domain and the full host: PSL private
    # suffixes (e.g. myshopify.com) are not always resolved to a registrable
    # domain, so "mystore.myshopify.com" must be caught by the host check.
    for candidate in (registrable, host):
        if candidate in BLOCKED_DOMAINS:
            return None
        if any(candidate.endswith("." + blocked) for blocked in BLOCKED_DOMAINS):
            return None
    return registrable


def normalize_url(url: str, base: str | None = None) -> str | None:
    """Canonicalize: drop fragment, tracking params, trailing slash, default port."""
    if not url:
        return None
    url = url.strip()
    if base and url.startswith("/"):
        parsed_base = urlparse(base)
        url = f"{parsed_base.scheme}://{parsed_base.netloc}{url}"
    if "://" not in url:
        return None
    try:
        p = urlparse(url)
    except ValueError:
        return None
    if p.scheme not in ("http", "https"):
        return None

    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    netloc = netloc.replace(":80", "").replace(":443", "")

    query = "&".join(
        part for part in p.query.split("&")
        if part and not TRACKING_PARAMS.match(part.split("=")[0])
    )
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme, netloc, path, "", query, ""))


def root_url(domain: str, https: bool = True) -> str:
    return f"{'https' if https else 'http'}://{domain}"


def same_registrable_domain(a: str, b: str) -> bool:
    na, nb = normalize_domain(a), normalize_domain(b)
    return bool(na and nb and na == nb)


def is_probably_company_site(url: str) -> bool:
    return normalize_domain(url) is not None

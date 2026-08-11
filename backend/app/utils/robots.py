"""robots.txt compliance (§31, §54).

This is a hard gate, not a suggestion: if robots.txt disallows a path for our
user-agent we do not fetch it, and the crawl job is recorded as 'skipped'.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[RobotFileParser | None, float, float | None]] = {}
_TTL_SECONDS = 60 * 60 * 12


def _fetch(origin: str) -> tuple[RobotFileParser | None, float | None]:
    parser = RobotFileParser()
    parser.set_url(f"{origin}/robots.txt")
    try:
        resp = httpx.get(
            f"{origin}/robots.txt",
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": settings.crawler_user_agent},
        )
        if resp.status_code >= 400:
            # No robots.txt (or server error) => crawling is permitted.
            parser.parse([])
            return parser, None
        parser.parse(resp.text.splitlines())
        delay = parser.crawl_delay(settings.crawler_user_agent)
        return parser, float(delay) if delay else None
    except Exception as exc:  # network failure => be conservative but not blocked
        log.debug("robots.txt fetch failed for %s: %s", origin, exc)
        return None, None


def _get(origin: str) -> tuple[RobotFileParser | None, float | None]:
    cached = _CACHE.get(origin)
    now = time.time()
    if cached and now - cached[1] < _TTL_SECONDS:
        return cached[0], cached[2]
    parser, delay = _fetch(origin)
    _CACHE[origin] = (parser, now, delay)
    return parser, delay


def can_fetch(url: str) -> bool:
    if not settings.respect_robots_txt:
        return True
    try:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
    except ValueError:
        return False
    parser, _ = _get(origin)
    if parser is None:
        return True  # couldn't read robots.txt; default-allow, rate-limited
    try:
        return parser.can_fetch(settings.crawler_user_agent, url)
    except Exception:
        return True


def crawl_delay_for(url: str) -> float:
    """Honour Crawl-delay when the site declares one, else our configured floor."""
    try:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
    except ValueError:
        return settings.crawl_delay_seconds
    _, delay = _get(origin)
    return max(delay or 0.0, settings.crawl_delay_seconds)


def sitemaps_for(url: str) -> list[str]:
    try:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
    except ValueError:
        return []
    parser, _ = _get(origin)
    if parser is None:
        return []
    return list(getattr(parser, "site_maps", lambda: [])() or [])

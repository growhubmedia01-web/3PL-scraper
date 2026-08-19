"""Serper.dev provider (https://serper.dev).

Supports multiple API keys via SERPER_API_KEYS (comma-separated) for key
rotation. When one key hits the rate limit (429) or is exhausted, the provider
automatically moves to the next key in the list. This lets you pool multiple
free-tier keys to multiply your effective credit quota.

Configuration:
    Single key:   SERPER_API_KEY=abc123
    Multi-key:    SERPER_API_KEYS=abc123,def456,ghi789   (takes priority)
"""
from __future__ import annotations

import itertools
import logging
import threading

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.providers.search.base import SearchProvider, SearchProviderError, SearchResult

log = logging.getLogger(__name__)

_ENDPOINT = "https://google.serper.dev"

# Thread-safe round-robin key rotator shared across all provider instances.
_lock = threading.Lock()
_key_cycle: itertools.cycle | None = None
_all_keys: list[str] = []


def _build_key_pool() -> list[str]:
    """Collect all configured Serper keys (deduped, non-empty)."""
    keys: list[str] = []
    # Multi-key env var takes priority
    multi = getattr(settings, "serper_api_keys", "") or ""
    for k in multi.split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)
    # Fall back to single key
    single = settings.serper_api_key or ""
    if single and single not in keys:
        keys.append(single)
    return keys


def _get_next_key() -> str | None:
    """Return the next key in the round-robin rotation."""
    global _key_cycle, _all_keys
    with _lock:
        if _key_cycle is None:
            _all_keys = _build_key_pool()
            if not _all_keys:
                return None
            _key_cycle = itertools.cycle(_all_keys)
        return next(_key_cycle)


class SerperProvider(SearchProvider):
    name = "serper"

    def __init__(self, api_key: str | None = None):
        # If explicitly passed an api_key, use it (e.g. in tests).
        # Otherwise pull from the rotating pool.
        self._fixed_key = api_key

    def _current_key(self) -> str | None:
        if self._fixed_key:
            return self._fixed_key
        return _get_next_key()

    @property
    def configured(self) -> bool:
        pool = _build_key_pool()
        return bool(pool or self._fixed_key)

    def _headers(self, key: str) -> dict:
        return {"X-API-KEY": key, "Content-Type": "application/json"}

    def _post(self, path: str, payload: dict) -> dict:
        """Try every key in the pool until one works or all fail."""
        pool = _build_key_pool() if not self._fixed_key else [self._fixed_key]
        if not pool:
            raise SearchProviderError("No SERPER_API_KEY configured")

        last_error: Exception | None = None
        tried: set[str] = set()

        # Try keys in round-robin order, but try each key at most once.
        for _ in range(len(pool)):
            key = _get_next_key() if not self._fixed_key else self._fixed_key
            if key in tried:
                continue
            tried.add(key)
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.post(f"{_ENDPOINT}{path}", json=payload,
                                       headers=self._headers(key))
                if resp.status_code == 401:
                    log.warning("Serper key ...%s rejected (401), trying next key", key[-6:])
                    last_error = SearchProviderError(f"Key ...{key[-6:]} rejected (401)")
                    continue
                if resp.status_code == 429:
                    log.warning("Serper key ...%s rate-limited (429), trying next key", key[-6:])
                    last_error = httpx.HTTPError(f"Key ...{key[-6:]} rate limited (429)")
                    continue
                if resp.status_code == 400:
                    # Serper returns 400 (not 402/429) for an exhausted key -
                    # {"message": "Not enough credits", "statusCode": 400} -
                    # a per-key/account condition exactly like 401/429, not a
                    # malformed-request error. Without this, one dead key in
                    # the pool broke every call regardless of how many other
                    # working keys were configured, since raise_for_status()
                    # below would abort the whole rotation on the first key
                    # tried instead of moving to the next one.
                    log.warning("Serper key ...%s returned 400 (%s), trying next key",
                               key[-6:], resp.text[:120])
                    last_error = SearchProviderError(f"Key ...{key[-6:]} returned 400: {resp.text[:200]}")
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.HTTPError, SearchProviderError):
                raise
            except Exception as exc:
                last_error = exc
                log.warning("Serper key ...%s error: %s", key[-6:], exc)
                continue

        raise SearchProviderError(
            f"All {len(pool)} Serper key(s) failed. Last error: {last_error}"
        )

    @staticmethod
    def _parse(data: dict, key: str = "organic") -> list[SearchResult]:
        out: list[SearchResult] = []
        for i, item in enumerate(data.get(key, []) or []):
            link = item.get("link") or item.get("url")
            if not link:
                continue
            out.append(SearchResult(
                url=link,
                title=item.get("title", ""),
                snippet=item.get("snippet", "") or item.get("description", ""),
                position=item.get("position", i + 1),
                published_at=item.get("date"),
            ))
        return out

    def search(self, query: str, *, country: str | None = None,
               num: int = 20, page: int = 1) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("No SERPER_API_KEY configured")
        payload: dict = {"q": query, "num": min(num, 100), "page": page}
        if country:
            payload["gl"] = country.lower()
        return self._parse(self._post("/search", payload), "organic")

    def news(self, query: str, *, country: str | None = None,
             num: int = 10) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("No SERPER_API_KEY configured")
        payload: dict = {"q": query, "num": min(num, 100)}
        if country:
            payload["gl"] = country.lower()
        return self._parse(self._post("/news", payload), "news")

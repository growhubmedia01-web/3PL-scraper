"""Search provider factory + cached, fallback-aware facade (§30, §48, §49)."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApiUsage, SearchCache
from app.providers.search.base import SearchProvider, SearchProviderError, SearchResult
from app.providers.search.brave import BraveProvider
from app.providers.search.exa import ExaProvider
from app.providers.search.serpapi import SerpApiProvider
from app.providers.search.serper import SerperProvider

log = logging.getLogger(__name__)

_REGISTRY: dict[str, type[SearchProvider]] = {
    "serper": SerperProvider,
    "serpapi": SerpApiProvider,
    "brave": BraveProvider,
    "exa": ExaProvider,
}


def register_provider(name: str, cls: type[SearchProvider]) -> None:
    """Add a new vendor without touching the discovery engine."""
    _REGISTRY[name.lower()] = cls


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def get_search_provider(name: str | None = None) -> SearchProvider:
    key = (name or settings.search_provider or "serper").lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        raise SearchProviderError(
            f"Unknown search provider '{key}'. Available: {available_providers()}")
    return cls()


def _configured_chain(preferred: str | None = None) -> list[SearchProvider]:
    order = [preferred or settings.search_provider] + [
        p for p in _REGISTRY if p != (preferred or settings.search_provider)]
    chain = []
    for name in order:
        try:
            provider = get_search_provider(name)
        except SearchProviderError:
            continue
        if provider.configured:
            chain.append(provider)
    return chain


class SearchService:
    """What the discovery engine actually uses.

    Adds: DB-backed result caching (cost control), automatic fallback to the
    next configured vendor, and API usage accounting.
    """

    def __init__(self, db: Session, provider: str | None = None):
        self.db = db
        self.chain = _configured_chain(provider)

    @property
    def has_provider(self) -> bool:
        return bool(self.chain)

    @staticmethod
    def _hash(query: str, country: str | None, num: int, mode: str) -> str:
        raw = json.dumps([query.lower().strip(), country, num, mode], sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cached(self, key: str) -> list[SearchResult] | None:
        row = self.db.execute(
            select(SearchCache).where(SearchCache.query_hash == key)
        ).scalar_one_or_none()
        if not row:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            self.db.delete(row)
            self.db.flush()
            return None
        return [SearchResult(**r) for r in row.results]

    def _store(self, key: str, query: str, provider: str,
               results: list[SearchResult]) -> None:
        self.db.merge(SearchCache(
            query_hash=key, query=query, provider=provider,
            results=[r.to_dict() for r in results],
            expires_at=datetime.now(timezone.utc)
            + timedelta(hours=settings.search_cache_ttl_hours),
        ))
        self.db.flush()

    def _record_usage(self, provider: str, operation: str, success: bool) -> None:
        self.db.add(ApiUsage(provider=provider, operation=operation, success=success))
        self.db.flush()

    def search(self, query: str, *, country: str | None = None,
               num: int | None = None, mode: str = "web",
               use_cache: bool = True) -> list[SearchResult]:
        num = num or settings.search_max_results
        key = self._hash(query, country, num, mode)

        if use_cache:
            hit = self._cached(key)
            if hit is not None:
                log.debug("search cache hit: %s", query)
                return hit

        if not self.chain:
            log.warning("No search provider configured; returning no results.")
            return []

        last_error: Exception | None = None
        for provider in self.chain:
            try:
                fn = provider.news if mode == "news" else provider.search
                results = fn(query, country=country, num=num)
                self._record_usage(provider.name, f"search.{mode}", True)
                if use_cache:
                    self._store(key, query, provider.name, results)
                return results
            except Exception as exc:  # try the next vendor (§55)
                last_error = exc
                self._record_usage(provider.name, f"search.{mode}", False)
                log.warning("Search provider %s failed for %r: %s",
                            provider.name, query, exc)
                continue

        log.error("All search providers failed for %r: %s", query, last_error)
        return []

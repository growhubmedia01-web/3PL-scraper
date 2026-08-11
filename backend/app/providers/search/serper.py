"""Serper.dev provider (https://serper.dev)."""
from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.providers.search.base import SearchProvider, SearchProviderError, SearchResult

log = logging.getLogger(__name__)

_ENDPOINT = "https://google.serper.dev"


class SerperProvider(SearchProvider):
    name = "serper"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.serper_api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"X-API-KEY": self.api_key, "Content-Type": "application/json"}

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=2, max=15),
           retry=retry_if_exception_type(httpx.HTTPError),
           reraise=True)
    def _post(self, path: str, payload: dict) -> dict:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{_ENDPOINT}{path}", json=payload,
                               headers=self._headers())
            if resp.status_code == 401:
                raise SearchProviderError(
                    "Serper rejected the API key (401). Check SERPER_API_KEY - "
                    "serper.dev keys are 40-char hex strings. A key with a "
                    "'live_' prefix belongs to a different vendor."
                )
            if resp.status_code == 429:
                raise httpx.HTTPError("Serper rate limit (429)")
            resp.raise_for_status()
            return resp.json()

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
            raise SearchProviderError("SERPER_API_KEY is not set")
        payload: dict = {"q": query, "num": min(num, 100), "page": page}
        if country:
            payload["gl"] = country.lower()
        return self._parse(self._post("/search", payload), "organic")

    def news(self, query: str, *, country: str | None = None,
             num: int = 10) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("SERPER_API_KEY is not set")
        payload: dict = {"q": query, "num": min(num, 100)}
        if country:
            payload["gl"] = country.lower()
        return self._parse(self._post("/news", payload), "news")

"""SerpAPI provider (https://serpapi.com)."""
from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.providers.search.base import SearchProvider, SearchProviderError, SearchResult

_ENDPOINT = "https://serpapi.com/search.json"


class SerpApiProvider(SearchProvider):
    name = "serpapi"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.serpapi_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=2, max=15),
           retry=retry_if_exception_type(httpx.HTTPError), reraise=True)
    def _get(self, params: dict) -> dict:
        with httpx.Client(timeout=45) as client:
            resp = client.get(_ENDPOINT, params=params)
            resp.raise_for_status()
            return resp.json()

    def search(self, query: str, *, country: str | None = None,
               num: int = 20, page: int = 1) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("SERPAPI_KEY is not set")
        params = {"q": query, "api_key": self.api_key, "engine": "google",
                  "num": min(num, 100), "start": (page - 1) * num}
        if country:
            params["gl"] = country.lower()
        data = self._get(params)
        return [
            SearchResult(url=r.get("link", ""), title=r.get("title", ""),
                         snippet=r.get("snippet", ""), position=r.get("position", i + 1),
                         published_at=r.get("date"))
            for i, r in enumerate(data.get("organic_results", []) or [])
            if r.get("link")
        ]

    def news(self, query: str, *, country: str | None = None,
             num: int = 10) -> list[SearchResult]:
        params = {"q": query, "api_key": self.api_key, "engine": "google_news",
                  "num": min(num, 100)}
        if country:
            params["gl"] = country.lower()
        data = self._get(params)
        return [
            SearchResult(url=r.get("link", ""), title=r.get("title", ""),
                         snippet=r.get("snippet", ""), position=i + 1,
                         published_at=r.get("date"))
            for i, r in enumerate(data.get("news_results", []) or [])
            if r.get("link")
        ]

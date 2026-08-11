"""Brave Search API provider - independent index, useful as a fallback."""
from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.providers.search.base import SearchProvider, SearchProviderError, SearchResult

_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveProvider(SearchProvider):
    name = "brave"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.brave_search_api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=1, min=2, max=15),
           retry=retry_if_exception_type(httpx.HTTPError), reraise=True)
    def search(self, query: str, *, country: str | None = None,
               num: int = 20, page: int = 1) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("BRAVE_SEARCH_API_KEY is not set")
        params = {"q": query, "count": min(num, 20), "offset": page - 1}
        if country:
            params["country"] = country.upper()
        with httpx.Client(timeout=30) as client:
            resp = client.get(_ENDPOINT, params=params, headers={
                "X-Subscription-Token": self.api_key,
                "Accept": "application/json",
            })
            resp.raise_for_status()
            data = resp.json()
        return [
            SearchResult(url=r.get("url", ""), title=r.get("title", ""),
                         snippet=r.get("description", ""), position=i + 1,
                         published_at=r.get("age"))
            for i, r in enumerate((data.get("web") or {}).get("results", []) or [])
            if r.get("url")
        ]

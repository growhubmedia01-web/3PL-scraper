"""Exa (exa.ai) search provider — neural/AI-powered web search.

Exa is distinct from keyword-search APIs: it uses embedding-based retrieval,
which finds semantically relevant pages rather than just keyword matches.
This is particularly effective for discovering new brands.

Docs: https://docs.exa.ai/reference/search
"""
from __future__ import annotations

import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.providers.search.base import SearchProvider, SearchProviderError, SearchResult

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.exa.ai"


class ExaProvider(SearchProvider):
    name = "exa"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.exa_api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

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
                    "Exa rejected the API key (401). Check EXA_API_KEY in .env."
                )
            if resp.status_code == 429:
                raise httpx.HTTPError("Exa rate limit (429)")
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _parse(data: dict) -> list[SearchResult]:
        out: list[SearchResult] = []
        for i, item in enumerate(data.get("results", []) or []):
            url = item.get("url")
            if not url:
                continue
            out.append(SearchResult(
                url=url,
                title=item.get("title", ""),
                snippet=item.get("text", "") or item.get("summary", "") or item.get("highlight", ""),
                position=i + 1,
                published_at=item.get("publishedDate"),
            ))
        return out

    def search(self, query: str, *, country: str | None = None,
               num: int = 20, page: int = 1) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("EXA_API_KEY is not set")
        payload: dict = {
            "query": query,
            "numResults": min(num, 100),
            "type": "auto",          # Exa picks neural vs keyword automatically
            "contents": {
                "text": {"maxCharacters": 500},  # short snippet for each result
            },
        }
        return self._parse(self._post("/search", payload))

    def news(self, query: str, *, country: str | None = None,
             num: int = 10) -> list[SearchResult]:
        """Exa doesn't have a separate news endpoint — use a recency filter."""
        if not self.configured:
            raise SearchProviderError("EXA_API_KEY is not set")
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload: dict = {
            "query": query,
            "numResults": min(num, 100),
            "type": "auto",
            "startPublishedDate": cutoff,
            "contents": {
                "text": {"maxCharacters": 500},
            },
        }
        return self._parse(self._post("/search", payload))

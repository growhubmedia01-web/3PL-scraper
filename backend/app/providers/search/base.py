"""Search provider abstraction (§30, §48).

The discovery engine depends on this interface only - never on a vendor.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

from app.utils.text import clean_text


@dataclass
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""
    position: int = 0
    published_at: str | None = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Vendors occasionally return raw control characters (e.g. a literal
        # NUL byte) from garbled source pages - sanitize once here so no
        # downstream consumer (search_cache, discovery's title extraction,
        # evidence text) has to remember to.
        self.title = clean_text(self.title)
        self.snippet = clean_text(self.snippet)

    def to_dict(self) -> dict:
        return {
            "url": self.url, "title": self.title, "snippet": self.snippet,
            "position": self.position, "published_at": self.published_at,
        }


class SearchProviderError(RuntimeError):
    pass


class SearchProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def search(self, query: str, *, country: str | None = None,
               num: int = 20, page: int = 1) -> list[SearchResult]:
        """Web search."""

    def news(self, query: str, *, country: str | None = None,
             num: int = 10) -> list[SearchResult]:
        """News search. Defaults to web search if the vendor has no news mode."""
        return self.search(query, country=country, num=num)

    @property
    def configured(self) -> bool:
        return True

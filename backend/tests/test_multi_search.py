"""Tests for aggregated search results across multiple providers."""
from __future__ import annotations

import pytest
from app.providers.search import factory
from app.providers.search.base import SearchProvider, SearchResult
from app.providers.search.factory import SearchService


class ProviderOne(SearchProvider):
    name = "provider_one"

    @property
    def configured(self) -> bool:
        return True

    def search(self, query, *, country=None, num=20, page=1):
        return [
            SearchResult(url="https://common.com", title="Common Brand", snippet="Snippet common"),
            SearchResult(url="https://only-one.com", title="One Brand", snippet="Snippet one"),
        ]


class ProviderTwo(SearchProvider):
    name = "provider_two"

    @property
    def configured(self) -> bool:
        return True

    def search(self, query, *, country=None, num=20, page=1):
        return [
            SearchResult(url="https://common.com", title="Common Brand", snippet="Snippet common"),
            SearchResult(url="https://only-two.com", title="Two Brand", snippet="Snippet two"),
        ]


@pytest.fixture
def mock_providers(monkeypatch):
    monkeypatch.setattr(factory, "_REGISTRY", {
        "provider_one": ProviderOne,
        "provider_two": ProviderTwo,
    })


def test_multiple_search_providers_merge_and_deduplicate(db, mock_providers, monkeypatch):
    # Mock settings to return both providers as search_provider
    from app.config import settings
    monkeypatch.setattr(settings, "search_provider", "provider_one,provider_two")

    service = SearchService(db)
    assert len(service.chain) == 2

    # Query the aggregated search service
    results = service.search("test query", use_cache=False)

    # Should contain unique URLs only, merged from both
    urls = [r.url for r in results]
    assert len(urls) == 3
    assert "https://common.com" in urls
    assert "https://only-one.com" in urls
    assert "https://only-two.com" in urls

    # Check that duplicates were removed (only one instance of common.com)
    assert urls.count("https://common.com") == 1

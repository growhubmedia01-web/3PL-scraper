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


def test_serper_key_rotation(monkeypatch):
    from app.config import settings
    from app.providers.search.serper import _build_key_pool, _get_next_key
    import app.providers.search.serper as serper_mod

    # Reset module state
    monkeypatch.setattr(serper_mod, "_key_cycle", None)
    monkeypatch.setattr(serper_mod, "_all_keys", [])

    monkeypatch.setattr(settings, "serper_api_keys", "key_a,key_b,key_c")
    monkeypatch.setattr(settings, "serper_api_key", "")
    
    assert _build_key_pool() == ["key_a", "key_b", "key_c"]

    # Verify rotation works
    assert _get_next_key() == "key_a"
    assert _get_next_key() == "key_b"
    assert _get_next_key() == "key_c"
    assert _get_next_key() == "key_a"


def test_serper_key_rotation_falls_back_on_error(monkeypatch):
    from app.config import settings
    from app.providers.search.serper import SerperProvider
    import app.providers.search.serper as serper_mod
    import httpx

    # Reset module state
    monkeypatch.setattr(serper_mod, "_key_cycle", None)
    monkeypatch.setattr(serper_mod, "_all_keys", [])
    monkeypatch.setattr(settings, "serper_api_keys", "key1,key2")
    monkeypatch.setattr(settings, "serper_api_key", "")

    calls = []
    def mock_post(self, url, json=None, headers=None, **kwargs):
        key = headers.get("X-API-KEY")
        calls.append(key)
        if key == "key1":
            return httpx.Response(429, request=httpx.Request("POST", url))
        else:
            return httpx.Response(200, json={"organic": [{"link": "https://ok.com"}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = SerperProvider()
    results = provider.search("test")

    # Should have tried key1 first, failed, then successfully tried key2
    assert "key1" in calls
    assert "key2" in calls
    assert len(results) == 1
    assert results[0].url == "https://ok.com"


def test_serper_400_credits_exhausted_falls_back_to_next_key(monkeypatch):
    """Serper signals an out-of-credit key with 400, not 402/429 - a real
    production incident where all 4 pooled keys had run out and the 400
    path wasn't rotating past a dead key to reach a working one."""
    from app.config import settings
    from app.providers.search.serper import SerperProvider
    import app.providers.search.serper as serper_mod
    import httpx

    monkeypatch.setattr(serper_mod, "_key_cycle", None)
    monkeypatch.setattr(serper_mod, "_all_keys", [])
    monkeypatch.setattr(settings, "serper_api_keys", "dead_key,live_key")
    monkeypatch.setattr(settings, "serper_api_key", "")

    calls = []
    def mock_post(self, url, json=None, headers=None, **kwargs):
        key = headers.get("X-API-KEY")
        calls.append(key)
        if key == "dead_key":
            return httpx.Response(400, json={"message": "Not enough credits",
                                              "statusCode": 400},
                                  request=httpx.Request("POST", url))
        return httpx.Response(200, json={"organic": [{"link": "https://ok.com"}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    results = SerperProvider().search("test")

    assert "dead_key" in calls
    assert "live_key" in calls
    assert len(results) == 1
    assert results[0].url == "https://ok.com"


def test_exa_key_rotation(monkeypatch):
    from app.config import settings
    from app.providers.search.exa import _build_key_pool, _get_next_key
    import app.providers.search.exa as exa_mod

    # Reset module state
    monkeypatch.setattr(exa_mod, "_key_cycle", None)
    monkeypatch.setattr(exa_mod, "_all_keys", [])

    monkeypatch.setattr(settings, "exa_api_keys", "key_a,key_b,key_c")
    monkeypatch.setattr(settings, "exa_api_key", "")
    
    assert _build_key_pool() == ["key_a", "key_b", "key_c"]

    # Verify rotation works
    assert _get_next_key() == "key_a"
    assert _get_next_key() == "key_b"
    assert _get_next_key() == "key_c"
    assert _get_next_key() == "key_a"


def test_exa_key_rotation_falls_back_on_error(monkeypatch):
    from app.config import settings
    from app.providers.search.exa import ExaProvider
    import app.providers.search.exa as exa_mod
    import httpx

    # Reset module state
    monkeypatch.setattr(exa_mod, "_key_cycle", None)
    monkeypatch.setattr(exa_mod, "_all_keys", [])
    monkeypatch.setattr(settings, "exa_api_keys", "key1,key2")
    monkeypatch.setattr(settings, "exa_api_key", "")

    calls = []
    def mock_post(self, url, json=None, headers=None, **kwargs):
        key = headers.get("x-api-key")
        calls.append(key)
        if key == "key1":
            return httpx.Response(429, request=httpx.Request("POST", url))
        else:
            return httpx.Response(200, json={"results": [{"url": "https://ok.com"}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    provider = ExaProvider()
    results = provider.search("test")

    # Should have tried key1 first, failed, then successfully tried key2
    assert "key1" in calls
    assert "key2" in calls
    assert len(results) == 1
    assert results[0].url == "https://ok.com"


def test_exa_400_falls_back_to_next_key(monkeypatch):
    """Mirrors the Serper fix - a vendor can signal a per-key/account
    problem with a 400 instead of 401/429."""
    from app.config import settings
    from app.providers.search.exa import ExaProvider
    import app.providers.search.exa as exa_mod
    import httpx

    monkeypatch.setattr(exa_mod, "_key_cycle", None)
    monkeypatch.setattr(exa_mod, "_all_keys", [])
    monkeypatch.setattr(settings, "exa_api_keys", "dead_key,live_key")
    monkeypatch.setattr(settings, "exa_api_key", "")

    calls = []
    def mock_post(self, url, json=None, headers=None, **kwargs):
        key = headers.get("x-api-key")
        calls.append(key)
        if key == "dead_key":
            return httpx.Response(400, json={"error": "Insufficient balance"},
                                  request=httpx.Request("POST", url))
        return httpx.Response(200, json={"results": [{"url": "https://ok.com"}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    results = ExaProvider().search("test")

    assert "dead_key" in calls
    assert "live_key" in calls
    assert len(results) == 1
    assert results[0].url == "https://ok.com"

from __future__ import annotations

import pytest

from app.engine.extractor import ExtractedPage
from app.engine.linkedin import (
    extract_company_linkedin_url, resolve_company_linkedin,
    search_company_linkedin_url,
)
from app.models import Company
from app.providers.search import factory
from app.providers.search.base import SearchProvider, SearchResult


def page(url="https://examplebrand.com", links=None, json_ld=None):
    p = ExtractedPage(url=url, text="Example Brand sells things.")
    p.links = links or []
    p.json_ld = json_ld or []
    return p


def test_json_ld_sameas_is_preferred_over_site_link():
    p = page(
        links=["https://linkedin.com/company/wrong-one"],
        json_ld=[{"@type": "Organization",
                 "sameAs": ["https://linkedin.com/company/example-brand"]}])
    result = extract_company_linkedin_url([p])
    assert result == ("https://linkedin.com/company/example-brand", "json_ld")


def test_site_link_fallback_when_no_json_ld():
    p = page(links=["https://linkedin.com/company/example-brand"])
    result = extract_company_linkedin_url([p])
    assert result == ("https://linkedin.com/company/example-brand", "site_link")


def test_personal_profile_links_are_ignored():
    p = page(links=["https://linkedin.com/in/janedoe"])
    assert extract_company_linkedin_url([p]) is None


def test_other_linkedin_paths_are_ignored():
    p = page(links=["https://linkedin.com/jobs/view/12345",
                    "https://linkedin.com/school/some-university",
                    "https://linkedin.com/posts/someone_activity-123"])
    assert extract_company_linkedin_url([p]) is None


def test_no_match_returns_none():
    p = page(links=["https://twitter.com/examplebrand"])
    assert extract_company_linkedin_url([p]) is None


def test_admin_urls_are_ignored():
    p = page(links=["https://linkedin.com/company/104532730/admin/dashboard"])
    assert extract_company_linkedin_url([p]) is None


def test_tracking_params_are_stripped_from_site_link():
    p = page(links=["https://linkedin.com/company/example-brand?trk=company_logo"])
    result = extract_company_linkedin_url([p])
    assert result == ("https://linkedin.com/company/example-brand", "site_link")


def test_tracking_params_are_stripped_from_json_ld():
    p = page(json_ld=[{"@type": "Organization",
                       "sameAs": ["https://linkedin.com/company/example-brand"
                                  "?originalSubdomain=uk"]}])
    result = extract_company_linkedin_url([p])
    assert result == ("https://linkedin.com/company/example-brand", "json_ld")


class FakeLinkedInProvider(SearchProvider):
    name = "fake"
    calls = 0

    @property
    def configured(self) -> bool:
        return True

    def search(self, query, *, country=None, num=20, page=1):
        FakeLinkedInProvider.calls += 1
        return [
            SearchResult(url="https://linkedin.com/company/example-brand",
                        title="Example Brand | LinkedIn",
                        snippet="Example Brand is a company on LinkedIn."),
            SearchResult(url="https://unrelated.com", title="Unrelated",
                        snippet="Nothing to do with it."),
        ]


class FakeNoiseProvider(SearchProvider):
    name = "fake_noise"

    @property
    def configured(self) -> bool:
        return True

    def search(self, query, *, country=None, num=20, page=1):
        return [SearchResult(url="https://linkedin.com/company/totally-different",
                             title="Totally Different Co", snippet="No match here.")]


@pytest.fixture
def mock_linkedin_provider(monkeypatch):
    FakeLinkedInProvider.calls = 0
    monkeypatch.setattr(factory, "_REGISTRY", {"fake": FakeLinkedInProvider})
    from app.config import settings
    monkeypatch.setattr(settings, "search_provider", "fake")


@pytest.fixture
def mock_noise_provider(monkeypatch):
    monkeypatch.setattr(factory, "_REGISTRY", {"fake_noise": FakeNoiseProvider})
    from app.config import settings
    monkeypatch.setattr(settings, "search_provider", "fake_noise")


def test_tier2_search_finds_company_page(db, company, mock_linkedin_provider):
    result = search_company_linkedin_url(db, company)
    assert result == ("https://linkedin.com/company/example-brand", "search")


def test_tier2_search_filters_noise(db, company, mock_noise_provider):
    assert search_company_linkedin_url(db, company) is None


class FakeWrongCompanyProvider(SearchProvider):
    """Reproduces the real bug: a generic/short scraped name ('Today')
    weakly matches an unrelated company's LinkedIn page via a substring
    coincidence, even though the domains have nothing in common."""
    name = "fake_wrong"

    @property
    def configured(self) -> bool:
        return True

    def search(self, query, *, country=None, num=20, page=1):
        return [SearchResult(url="https://linkedin.com/company/usa-today",
                             title="USA Today | LinkedIn",
                             snippet="USA Today is a news organization.")]


@pytest.fixture
def mock_wrong_company_provider(monkeypatch):
    monkeypatch.setattr(factory, "_REGISTRY", {"fake_wrong": FakeWrongCompanyProvider})
    from app.config import settings
    monkeypatch.setattr(settings, "search_provider", "fake_wrong")


def test_tier2_rejects_match_missing_domain_root(db, mock_wrong_company_provider):
    company = Company(name="Today", domain="abellemon.com.au",
                      website="https://abellemon.com.au", status="classified")
    db.add(company)
    db.flush()
    assert search_company_linkedin_url(db, company) is None, \
        "'today' matching inside 'USA Today' must not be enough - the " \
        "domain root 'abellemon' appears nowhere in the result"


def test_resolve_skips_tier2_when_tier1_succeeds(db, company, mock_linkedin_provider):
    p = page(json_ld=[{"@type": "Organization",
                       "sameAs": ["https://linkedin.com/company/example-brand"]}])
    url = resolve_company_linkedin(db, company, [p])
    assert url == "https://linkedin.com/company/example-brand"
    assert company.linkedin_source == "json_ld"
    assert FakeLinkedInProvider.calls == 0


def test_resolve_only_calls_search_once_across_reprocessing(db, company, mock_linkedin_provider):
    empty_page = page()  # no links, no json_ld -> tier 1 finds nothing both times

    first = resolve_company_linkedin(db, company, [empty_page])
    assert first == "https://linkedin.com/company/example-brand"
    assert FakeLinkedInProvider.calls == 1
    checked_at = company.linkedin_checked_at
    assert checked_at is not None

    # Re-processing: linkedin_url is already set, so it short-circuits before
    # even reaching tier 2 again.
    second = resolve_company_linkedin(db, company, [empty_page])
    assert second == "https://linkedin.com/company/example-brand"
    assert FakeLinkedInProvider.calls == 1
    assert company.linkedin_checked_at == checked_at


def test_resolve_never_repeats_search_when_nothing_found(db, company, mock_noise_provider):
    empty_page = page()

    first = resolve_company_linkedin(db, company, [empty_page])
    assert first is None
    assert company.linkedin_checked_at is not None
    checked_at = company.linkedin_checked_at

    second = resolve_company_linkedin(db, company, [empty_page])
    assert second is None
    assert company.linkedin_checked_at == checked_at, \
        "tier 2 must not fire again once already attempted, even with no result"


def test_resolve_respects_skip_external(db, company, mock_linkedin_provider):
    empty_page = page()
    result = resolve_company_linkedin(db, company, [empty_page], skip_external=True)
    assert result is None
    assert company.linkedin_checked_at is None, \
        "skip_external must not mark tier 2 as attempted, so a later real run can still try it"
    assert FakeLinkedInProvider.calls == 0

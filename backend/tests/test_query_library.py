"""The discovery query library.

Recall is the goal, but a library this size is a spend multiplier: every
executed query costs a Serper credit, and every result costs a crawl. These
tests pin the properties that keep it useful rather than merely large.
"""
from __future__ import annotations

import re
from collections import Counter

import pytest

from app.engine.discovery import apply_exclusions
from scripts.query_library import (
    ALL_CATEGORIES, CATEGORIES, EXCLUDED_BUSINESS_TYPES,
    QUERY_EXCLUSION_TERMS, build_library, stats,
)

LIB = build_library()


def test_library_is_large_enough_to_be_worth_generating():
    assert len(LIB) > 2000


def test_no_duplicate_queries():
    keys = [q.key() for q in LIB]
    duplicates = {k: c for k, c in Counter(keys).items() if c > 1}
    assert not duplicates, f"duplicate queries waste credits: {duplicates}"


def test_every_tier_is_populated():
    by_tier = stats(LIB)["by_tier"]
    assert set(by_tier) == {1, 2, 3, 4}
    for tier, count in by_tier.items():
        assert count > 50, f"tier {tier} has only {count} queries"


def test_tier1_is_small_enough_to_run_cheaply():
    """Tier 1 is the 'just run it' set. It must stay affordable."""
    tier1 = [q for q in LIB if q.tier == 1]
    assert len(tier1) < 1200, (
        f"tier 1 has {len(tier1)} queries - too expensive as a default run")


def test_tier1_targets_platforms_and_categories():
    tier1 = " | ".join(q.text.lower() for q in LIB if q.tier == 1)
    for token in ("shopify", "dtc", "ecommerce brands", "online stores"):
        assert token in tier1


def test_every_category_is_covered():
    corpus = " | ".join(q.text.lower() for q in LIB)
    missing = [c for c in ALL_CATEGORIES if c.lower() not in corpus]
    assert not missing, f"categories with no queries: {missing}"


def test_every_category_group_is_covered():
    groups = {q.group for q in LIB}
    for group in CATEGORIES:
        assert group in groups, f"no queries for group {group}"


def test_queries_do_not_contain_excluded_business_terms():
    """The library must not go looking for 3PLs, freight firms or agencies -
    those are competitors and service businesses, not prospects."""
    banned = ["3pl", "freight forward", "courier company", "logistics company",
              "marketing agency", "seo agency", "saas"]
    offenders = [q.text for q in LIB
                 if any(b in q.text.lower() for b in banned)]
    assert not offenders, f"queries target excluded business types: {offenders[:5]}"


def test_queries_never_target_marketplaces():
    banned = ["amazon", "ebay", "etsy", "walmart", "alibaba", "aliexpress"]
    offenders = [q.text for q in LIB
                 if any(b in q.text.lower() for b in banned)]
    assert not offenders, f"marketplace queries: {offenders[:5]}"


def test_geographic_queries_carry_a_country_code():
    geo = [q for q in LIB if q.group == "Geographic"]
    assert geo
    assert all(q.country and len(q.country) == 2 for q in geo)


def test_country_codes_are_valid_iso_alpha2():
    for q in LIB:
        if q.country:
            assert re.fullmatch(r"[A-Z]{2}", q.country), q


def test_no_query_is_absurdly_long():
    for q in LIB:
        assert len(q.text) <= 180, q.text


def test_no_empty_or_whitespace_queries():
    for q in LIB:
        assert q.text.strip()
        assert "  " not in q.text, f"double space in {q.text!r}"


# --------------------------------------------------------------------------
# Exclusion operators
# --------------------------------------------------------------------------
def test_exclusions_are_appended_as_negative_operators():
    got = apply_exclusions("Shopify skincare brands", QUERY_EXCLUSION_TERMS)
    assert got.startswith("Shopify skincare brands")
    assert "-3PL" in got
    assert '-"fulfillment services"' in got


def test_multiword_exclusions_are_quoted():
    got = apply_exclusions("test", ["hiring agency"])
    assert got == 'test -"hiring agency"'


def test_a_term_already_in_the_query_is_not_excluded():
    """Excluding a word the query is about would return nothing."""
    got = apply_exclusions("logistics brands", QUERY_EXCLUSION_TERMS)
    assert "-logistics" not in got


def test_exclusions_are_a_no_op_when_unconfigured():
    assert apply_exclusions("plain query", []) == "plain query"


def test_excluded_business_types_are_defined():
    assert len(EXCLUDED_BUSINESS_TYPES) > 20
    for expected in ("logistics company", "freight forwarder",
                     "marketing agency", "software company"):
        assert expected in EXCLUDED_BUSINESS_TYPES


# --------------------------------------------------------------------------
# Generated SQL
# --------------------------------------------------------------------------
def test_generated_sql_matches_the_library():
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent
           / "migrations" / "005_query_library.sql")
    assert sql.exists(), "run: python -m scripts.build_query_library"
    text = sql.read_text()
    rows = re.findall(r"^ \('(.*?)', (?:null|'[A-Z]{2}'), \d\)", text, re.M)
    assert len(rows) == len(LIB), (
        f"005_query_library.sql has {len(rows)} rows but the library has "
        f"{len(LIB)}. Rebuild: python -m scripts.build_query_library")


def test_generated_sql_escapes_apostrophes():
    """"children's products" must become 'children''s products' in SQL, or the
    statement terminates early and the migration fails to parse."""
    from pathlib import Path
    sql = (Path(__file__).resolve().parent.parent
           / "migrations" / "005_query_library.sql").read_text()

    with_apostrophes = [q for q in LIB if "'" in q.text]
    assert with_apostrophes, "expected some queries to contain apostrophes"

    for query in with_apostrophes:
        escaped = query.text.replace("'", "''")
        assert f"('{escaped}'" in sql, (
            f"apostrophe not escaped for {query.text!r}")
        # and the raw form must not appear as a literal opener
        assert f"('{query.text}'," not in sql


# --------------------------------------------------------------------------
# Company name extraction from search-result titles
# --------------------------------------------------------------------------
@pytest.mark.parametrize("title,expected", [
    ("Well-Kept | Skincare & Body", "Well-Kept"),        # hyphenated name
    ("Allbirds - Wool Runners", "Allbirds"),             # spaced hyphen
    ("Aesop | Skin, Hair & Body Care", "Aesop"),
    ("Shop Nordic Wool — Merino Basics", "Nordic Wool"),
    ("Home | Northgate Trade Supplies", "Northgate Trade Supplies"),
    ("Homepage - Acme Ltd", "Acme Ltd"),
    ("Store | Bear & Bramble", "Bear & Bramble"),
    ("BatchMade Cosmetics Official Store", "BatchMade Cosmetics"),
    ("Buy Oatly Online Store", "Oatly"),
    ("Coca-Cola: Refresh", "Coca-Cola"),
    ("Ben & Jerry's", "Ben & Jerry's"),
    ("", None),
    (None, None),
])
def test_company_name_extraction(title, expected):
    from app.engine.discovery import _name_from_title
    assert _name_from_title(title) == expected


def test_hyphenated_brand_names_survive():
    """Splitting on a bare hyphen would truncate half the brands on the web."""
    from app.engine.discovery import _name_from_title
    for name in ("Well-Kept", "Coca-Cola", "Rag-and-Bone", "Dr-Bronner"):
        assert _name_from_title(f"{name} | Shop") == name

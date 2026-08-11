"""Connection-string handling.

Supabase passwords routinely contain '@', ':' or '/'. Pasted raw into a URI
they mis-parse silently and produce a DNS error instead of an auth error,
which is a genuinely confusing failure mode.
"""
from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from app.config import _fix_unencoded_password


def parsed(url: str):
    return make_url(_fix_unencoded_password(url))


def test_unencoded_at_sign_in_password_is_fixed():
    url = parsed("postgresql+psycopg://postgres:Shaik@HB1234@db.abc.supabase.co:5432/postgres")
    assert url.password == "Shaik@HB1234"
    assert url.host == "db.abc.supabase.co"
    assert url.port == 5432
    assert url.database == "postgres"


def test_raw_paste_would_have_mis_parsed_without_the_fix():
    """Documents the bug being prevented."""
    broken = make_url(
        "postgresql+psycopg://postgres:Shaik@HB1234@db.abc.supabase.co:5432/postgres")
    assert broken.password == "Shaik"
    assert broken.host == "HB1234@db.abc.supabase.co"


def test_already_encoded_password_is_left_alone():
    original = "postgresql+psycopg://postgres:Shaik%40HB1234@db.abc.supabase.co:5432/postgres"
    assert _fix_unencoded_password(original) == original
    assert parsed(original).password == "Shaik@HB1234"


def test_simple_password_is_untouched():
    original = "postgresql+psycopg://postgres:simplepass@db.abc.supabase.co:5432/postgres"
    assert _fix_unencoded_password(original) == original


def test_sqlite_urls_are_untouched():
    for url in ("sqlite+pysqlite:///./local.db", "sqlite+pysqlite:///:memory:"):
        assert _fix_unencoded_password(url) == url


def test_pooler_style_username_survives():
    url = parsed(
        "postgresql+psycopg://postgres.abcdefghijklmnopqrst:p@ss@"
        "aws-0-eu-west-2.pooler.supabase.com:6543/postgres")
    assert url.username == "postgres.abcdefghijklmnopqrst"
    assert url.password == "p@ss"
    assert url.host == "aws-0-eu-west-2.pooler.supabase.com"
    assert url.port == 6543


@pytest.mark.parametrize("password,expected", [
    ("has:colon", "has:colon"),
    ("has/slash", "has/slash"),
    ("has#hash", "has#hash"),
    ("has@at:and/all#of#them", "has@at:and/all#of#them"),
])
def test_other_reserved_characters(password: str, expected: str):
    url = parsed(f"postgresql+psycopg://postgres:{password}@db.abc.supabase.co:5432/postgres")
    assert url.password == expected
    assert url.host == "db.abc.supabase.co"

from app.utils.urls import normalize_domain, normalize_url


def test_normalize_domain_strips_scheme_www_and_path():
    assert normalize_domain("https://WWW.Example.co.uk/shop?utm_source=x") == "example.co.uk"
    assert normalize_domain("example.com") == "example.com"
    assert normalize_domain("http://shop.example.com/a/b") == "example.com"


def test_normalize_domain_blocks_marketplaces_and_social():
    for blocked in ("https://www.amazon.com/dp/B01", "https://linkedin.com/in/x",
                    "https://mystore.myshopify.com", "https://facebook.com/brand"):
        assert normalize_domain(blocked) is None


def test_normalize_domain_rejects_garbage():
    assert normalize_domain("") is None
    assert normalize_domain("not a url") is None
    assert normalize_domain("http://localhost:3000") is None


def test_normalize_url_removes_tracking_and_fragment():
    got = normalize_url("https://www.Example.com/page/?utm_source=x&id=7#top")
    assert got == "https://example.com/page?id=7"

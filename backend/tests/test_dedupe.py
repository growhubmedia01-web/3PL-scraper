from app.utils.dedupe import canonical_name, is_duplicate, name_similarity


def test_canonical_name_strips_legal_suffixes():
    assert canonical_name("Acme Widgets Ltd.") == "acme widgets"
    assert canonical_name("ACME WIDGETS LIMITED") == "acme widgets"


def test_name_similarity_matches_variants():
    assert name_similarity("Acme Widgets Ltd", "Acme Widgets Limited") > 0.9
    assert name_similarity("Acme Widgets", "Totally Different Co") < 0.5


def test_domain_equality_is_authoritative():
    assert is_duplicate("A", "example.com", "B", "example.com")
    assert not is_duplicate("Acme", "acme.com", "Zenith", "zenith.com")

from __future__ import annotations

from app.engine.extractor import ExtractedPage
from app.engine.signals import detect_signals, persist_signals


def page(url, text, page_type):
    p = ExtractedPage(url=url, text=text)
    p.page_type = page_type
    return p


def test_structural_signals_come_from_classification(db, company, config, source):
    found = detect_signals(db, company, [], config)
    types = {s.signal_type for s in found}
    assert "ecommerce" in types
    assert "physical_products" in types


def test_hiring_keyword_on_careers_page_is_strong(db, company, config):
    careers = page("https://examplebrand.com/careers",
                   "We are hiring a Fulfillment Manager to run our new warehouse.",
                   "careers")
    found = {s.signal_type: s for s in detect_signals(db, company, [careers], config)}
    assert "fulfillment_hiring" in found
    assert found["fulfillment_hiring"].strength == 1.0
    assert "Fulfillment Manager" in found["fulfillment_hiring"].evidence


def test_same_keyword_off_topic_page_is_weaker(db, company, config):
    blog = page("https://examplebrand.com/blog/post",
                "Our fulfillment manager wrote this blog about packaging.",
                "news")
    found = {s.signal_type: s for s in detect_signals(db, company, [blog], config)}
    assert found["fulfillment_hiring"].strength < 1.0


def test_signal_evidence_is_verbatim_from_the_source(db, company, config):
    shipping = page("https://examplebrand.com/shipping",
                    "We ship worldwide from our UK studio. Customs and duties "
                    "are the responsibility of the buyer.", "shipping")
    found = {s.signal_type: s for s in detect_signals(db, company, [shipping], config)}
    evidence = found["international_shipping"].evidence
    assert "ship worldwide" in evidence.lower()


def test_persist_signals_sets_expiry_from_config(db, company, config):
    careers = page("https://examplebrand.com/careers",
                   "Hiring an Operations Manager.", "careers")
    detected = detect_signals(db, company, [careers], config)
    rows = persist_signals(db, company, config, detected)

    by_type = {r.signal_type: r for r in rows}
    assert by_type["operations_hiring"].expires_at is not None   # decay_days=120
    assert by_type["ecommerce"].expires_at is None               # never decays


def test_persist_signals_replaces_rather_than_duplicates(db, company, config):
    careers = page("https://examplebrand.com/careers",
                   "Hiring an Operations Manager.", "careers")
    detected = detect_signals(db, company, [careers], config)
    persist_signals(db, company, config, detected)
    second = persist_signals(db, company, config, detected)

    from app.engine.signals import load_signals
    assert len(load_signals(db, company.id, config.id)) == len(second)

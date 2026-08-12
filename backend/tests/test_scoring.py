"""Scoring engine tests - the part most worth getting right."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.engine import scoring
from app.engine.signals import effective_strength
from app.models import Signal


def make_signal(company, service, signal_type, *, days_ago=0, confidence=0.9,
                strength=1.0):
    return Signal(
        company_id=company.id, service_id=service.id, signal_type=signal_type,
        strength=strength, confidence=confidence,
        evidence=f"evidence for {signal_type}",
        detected_at=datetime.now(timezone.utc) - timedelta(days=days_ago))


def test_intent_levels_map_to_configured_thresholds(config):
    assert scoring.intent_level_for(10, config) == "LOW"
    assert scoring.intent_level_for(40, config) == "POSSIBLE"
    assert scoring.intent_level_for(60, config) == "GOOD"
    assert scoring.intent_level_for(75, config) == "STRONG"
    assert scoring.intent_level_for(90, config) == "HOT"


def test_fresh_signal_scores_higher_than_stale_one(db, company, service, config):
    fresh = make_signal(company, service, "recent_funding", days_ago=1)
    stale = make_signal(company, service, "recent_funding", days_ago=500)
    signal_def = config.signals["recent_funding"]

    assert effective_strength(fresh, signal_def) > effective_strength(stale, signal_def)


def test_expired_signal_contributes_nothing(db, company, service, config):
    expired = make_signal(company, service, "operations_hiring", days_ago=200)
    signal_def = config.signals["operations_hiring"]  # decay_days = 120
    assert effective_strength(expired, signal_def) == 0.0


def test_signal_without_decay_never_decays(db, company, service, config):
    old = make_signal(company, service, "ecommerce", days_ago=5000)
    signal_def = config.signals["ecommerce"]  # decay_days = None
    assert effective_strength(old, signal_def) == pytest.approx(0.9, abs=0.01)


def test_more_signals_produce_a_higher_score(db, company, service, config):
    few = [make_signal(company, service, "ecommerce"),
           make_signal(company, service, "physical_products")]
    many = few + [
        make_signal(company, service, "fulfillment_hiring"),
        make_signal(company, service, "international_expansion"),
        make_signal(company, service, "recent_funding"),
    ]
    low = scoring.calculate(db, company, few, config)
    high = scoring.calculate(db, company, many, config)
    assert high.score > low.score


def test_existing_3pl_reduces_but_does_not_reject(db, company, service, config):
    base = [make_signal(company, service, "ecommerce"),
            make_signal(company, service, "physical_products"),
            make_signal(company, service, "fulfillment_hiring")]
    with_incumbent = base + [make_signal(company, service, "existing_3pl")]

    without = scoring.calculate(db, company, base, config)
    with_ = scoring.calculate(db, company, with_incumbent, config)

    assert with_.score < without.score
    assert with_.score > 0, "an incumbent provider must not zero the lead out"


def test_missing_required_signals_caps_the_score(db, company, service, config):
    """fulfillment_hiring alone is a big weight, but with no evidence the
    company handles physical goods the lead must not be presented as HOT.

    Since migration 004 the gate is `physical_products` only - ecommerce is a
    scoring bonus, because wholesalers and manufacturers need 3PL too.
    """
    signals = [make_signal(company, service, "fulfillment_hiring"),
               make_signal(company, service, "international_expansion"),
               make_signal(company, service, "recent_funding")]
    result = scoring.calculate(db, company, signals, config)
    assert result.score <= 45
    assert set(result.missing_required) == {"physical_products"}


def test_ecommerce_is_no_longer_required(db, company, service, config):
    """A wholesaler or manufacturer with no online store must not be capped."""
    signals = [make_signal(company, service, "physical_products"),
               make_signal(company, service, "wholesale_b2b"),
               make_signal(company, service, "fulfillment_hiring")]
    result = scoring.calculate(db, company, signals, config)
    assert result.missing_required == []


def test_ai_probability_cannot_solely_determine_the_score(db, company, service,
                                                          config):
    """§28: the model's opinion is an input, not the verdict."""
    signals = [make_signal(company, service, "ecommerce"),
               make_signal(company, service, "physical_products")]
    sober = scoring.calculate(db, company, signals, config, ai_probability=0.0)
    hyped = scoring.calculate(db, company, signals, config, ai_probability=1.0)

    # AI carries 30% weight, so a maximally confident model moves the score by
    # at most ~30 points - it cannot manufacture a HOT lead on its own.
    assert hyped.score - sober.score <= 31
    assert hyped.intent_level != "HOT"


def test_score_breakdown_is_traceable(db, company, service, config):
    signals = [make_signal(company, service, "ecommerce"),
               make_signal(company, service, "physical_products"),
               make_signal(company, service, "operations_hiring")]
    result = scoring.calculate(db, company, signals, config)
    labels = [line.label for line in result.breakdown]

    assert "Ecommerce" in labels
    assert "Operations Hiring" in labels
    assert "Evidence quality" in labels
    assert any("Deterministic signal subtotal" in l for l in labels)
    for line in result.breakdown:
        assert isinstance(line.points, float)


def test_score_is_always_within_bounds(db, company, service, config):
    every_signal = [make_signal(company, service, stype)
                    for stype in config.signals]
    result = scoring.calculate(db, company, every_signal, config,
                               ai_probability=1.0)
    assert 0.0 <= result.score <= 100.0


def test_weights_renormalize_when_ai_is_unavailable(db, company, service, config):
    """A missing LLM key must not silently cap every lead's score."""
    signals = [make_signal(company, service, stype, confidence=1.0)
               for stype in ("ecommerce", "physical_products",
                             "fulfillment_hiring", "international_expansion",
                             "recent_funding", "operations_hiring",
                             "crowdfunding", "product_launch")]
    result = scoring.calculate(db, company, signals, config, ai_probability=None)
    assert result.ai_score is None
    # 105 raw of a 110 ceiling = 95.5 deterministic. With the AI weight
    # redistributed this carries ~68 on its own; the remaining gap is the
    # evidence component, which is zero here because this unit test creates
    # no Source rows. Without renormalization the same signals would score
    # roughly 30% lower.
    assert result.deterministic_score > 90
    assert result.score > 65, "deterministic-only runs must still score well"

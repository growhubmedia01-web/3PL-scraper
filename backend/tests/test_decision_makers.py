from __future__ import annotations

from app.engine.decision_makers import extract_candidates, find_decision_makers
from app.engine.extractor import ExtractedPage
from app.models import Suppression


def page(url, text, page_type="about"):
    p = ExtractedPage(url=url, text=text)
    p.page_type = page_type
    return p


TEAM_PAGE = page(
    "https://examplebrand.com/about/team",
    "Meet the team. Jane Smith, COO. Marcus Webb - Head of Operations. "
    "Priya Nair, Fulfillment Manager. Tom Blake, Junior Designer.")


def test_extracts_names_with_relevant_titles_only(config):
    candidates = extract_candidates([TEAM_PAGE], config, {})
    names = {c.name for c in candidates}
    assert "Jane Smith" in names
    assert "Marcus Webb" in names
    assert "Tom Blake" not in names, "irrelevant roles must be filtered out"


def test_candidates_are_ranked_by_configured_role_priority(config):
    candidates = extract_candidates([TEAM_PAGE], config, {})
    # head of operations (1) outranks coo (2) outranks fulfillment manager (7)
    assert candidates[0].job_title.lower().startswith("head of operations")


def test_leadership_page_yields_confirmed_confidence(config):
    candidates = extract_candidates([TEAM_PAGE], config, {})
    assert candidates[0].confidence_label == "confirmed"
    assert candidates[0].confidence >= 0.9


def test_press_quote_attribution_is_detected(config):
    quote = page("https://news.example.com/story",
                 'The move doubles our capacity, said Jane Smith, COO of the brand.',
                 "press_release")
    candidates = extract_candidates([quote], config, {})
    assert any(c.name == "Jane Smith" for c in candidates)


def test_no_decision_maker_record_contains_an_email(db, company, config):
    people = find_decision_makers(db, company, [TEAM_PAGE], config)
    assert people
    for person in people:
        for value in vars(person).values():
            assert "@" not in str(value), "no email may ever be stored"


def test_suppressed_person_is_never_stored(db, company, config):
    db.add(Suppression(kind="person", value="Jane Smith"))
    db.flush()
    people = find_decision_makers(db, company, [TEAM_PAGE], config)
    assert all(p.name != "Jane Smith" for p in people)


def test_stored_record_always_has_a_source_url(db, company, config):
    people = find_decision_makers(db, company, [TEAM_PAGE], config)
    for person in people:
        assert person.profile_url
        assert person.source
        assert person.confidence_label in ("confirmed", "likely", "possible")


def test_gating_threshold_respects_config(config):
    from app.engine.decision_makers import should_research
    assert should_research(95, config) is True
    assert should_research(40, config) is False

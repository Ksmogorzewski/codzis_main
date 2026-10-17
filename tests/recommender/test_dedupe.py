"""Title normalisation + duplicate collapsing (recommender/retriever/dedupe.py)."""

from __future__ import annotations

import pytest

from recommender.retriever.dedupe import dedupe_events, normalize_title


@pytest.mark.parametrize("a,b", [
    # case / whitespace / punctuation
    ("Koncert Jazzowy", "  koncert jazzowy  "),
    ("Koncert jazzowy", "Koncert jazzowy!"),
    # HTML entities and the Polish "&" == "i" convention
    ("Koncert &amp; taniec", "Koncert i taniec"),
    ("Koncert & taniec", "Koncert i taniec"),
    # zero-width characters
    ("Konc\u200bert jazzowy", "Koncert jazzowy"),
    # Polish ł is NOT decomposed by NFKD - must not vanish or split the token
    ("Pływanie dla dorosłych", "Plywanie dla doroslych"),
    # inflection: plural / case variants
    ("Koncerty jazzowe", "Koncert jazzowy"),
    ("Biegi przełajowe", "Bieg przełajowy"),
    # group / round markers (the docstring's motivating case)
    ("Zajęcia pływania - grupa 1", "Zajęcia pływania - grupa 2"),
    ("Joga dla seniorów - grupa A", "Joga dla seniorów - grupa B"),
    ("Spektakl - dzień 1", "Spektakl - dzień 3"),
    ("Warsztaty ceramiki (edycja II)", "Warsztaty ceramiki"),
    ("Warsztaty ceramiki (2)", "Warsztaty ceramiki"),
    ("Warsztaty ceramiki (nr 3)", "Warsztaty ceramiki"),
    ("Warsztaty ceramiki [4]", "Warsztaty ceramiki"),
])
def test_titles_that_must_group(a, b):
    assert normalize_title(a) == normalize_title(b)


@pytest.mark.parametrize("a,b", [
    ("Koncert jazzowy", "Koncert rockowy"),
    ("Wykład o fizyce", "Wykład o chemii"),
    ("Warsztaty ceramiki", "Warsztaty ceramiczne"),
    ("Zajęcia taneczne", "Zajęcia techniczne"),
    ("Kino plenerowe", "Kino studyjne"),
    ("Wystawa malarstwa", "Wystawa rzeźby"),
    # numbers that carry meaning, not group numbering
    ("Bieg 5 km", "Bieg 10 km"),
    # nominative -a/-o deliberately not stemmed
    ("Kino", "Kina"),
])
def test_titles_that_must_not_group(a, b):
    assert normalize_title(a) != normalize_title(b)


def test_stem_false_keeps_old_behaviour():
    assert normalize_title("Koncerty jazzowe", stem=False) == "koncerty jazzowe"
    assert normalize_title("Koncert Jazzowy", stem=False) == "koncert jazzowy"


def test_polish_letters_survive_folding():
    assert "ł" not in normalize_title("Pływanie")
    # the word must stay one token, not become "p ywania"
    assert normalize_title("Pływanie") == "plywan"
    assert len(normalize_title("Pływanie").split()) == 1


def test_empty_title_never_groups():
    events = [
        {"id": "a", "title": "🎉", "occurrences": [{"start": "2026-10-01T10:00"}]},
        {"id": "b", "title": "***", "occurrences": [{"start": "2026-10-02T10:00"}]},
        {"id": "c", "title": "", "occurrences": [{"start": "2026-10-03T10:00"}]},
    ]
    out = dedupe_events(events)
    assert [e["id"] for e in out] == ["a", "b", "c"]


def test_best_scored_member_kept_and_all_dates_attached():
    events = [
        {"id": "s1", "title": "Zajęcia pływania - grupa 1",
         "occurrences": [{"start": "2026-10-20T17:00"}]},
        {"id": "s2", "title": "Zajęcia pływania - grupa 2",
         "occurrences": [{"start": "2026-10-21T17:00"}]},
    ]
    out = dedupe_events(events, {"s1": 0.2, "s2": 0.9})
    assert len(out) == 1
    assert out[0]["id"] == "s2"                                  # highest score wins
    assert out[0]["all_dates"] == ["2026-10-20T17:00", "2026-10-21T17:00"]


def test_lowest_score_falls_back_to_earliest_date():
    events = [
        {"id": "s2", "title": "Joga - grupa 2", "occurrences": [{"start": "2026-10-21T17:00"}]},
        {"id": "s1", "title": "Joga - grupa 1", "occurrences": [{"start": "2026-10-20T17:00"}]},
    ]
    out = dedupe_events(events)  # no scores -> earliest start
    assert out[0]["id"] == "s1"


def test_group_order_is_first_appearance():
    events = [
        {"id": "1", "title": "B"},
        {"id": "2", "title": "A"},
        {"id": "3", "title": "B"},
    ]
    assert [e["id"] for e in dedupe_events(events)] == ["1", "2"]


def test_original_events_not_mutated():
    events = [{"id": "1", "title": "Joga", "occurrences": [{"start": "2026-10-20T17:00"}]}]
    dedupe_events(events, {"1": 1.0})
    assert "all_dates" not in events[0]

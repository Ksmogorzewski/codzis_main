"""Soft-preference boosts/penalties and diversification (retriever/scoring.py)."""

from __future__ import annotations

import pytest

from recommender.retriever import Candidate
from recommender.retriever.scoring import BOOSTS, PENALTIES, diversify, preference_boost


def slot(hour: int, day: str = "2026-10-20") -> dict:
    s = f"{day}T{hour:02d}:00:00+02:00"
    return {"start": s, "end": s.replace(f"T{hour:02d}", f"T{hour + 1:02d}"), "allDay": False}


def ev(**tags) -> dict:
    return {"id": "e", "title": "X", "tags": tags}


# ------------------------------------------------------------ time of day
def test_matching_time_of_day_boosts():
    boost, matched = preference_boost(ev(), {"time_of_day": ["wieczór"]}, slot(20))
    assert matched["time_of_day"] == ["wieczór"]
    assert boost == pytest.approx(BOOSTS["time_of_day"])


def test_contradicting_time_of_day_penalises():
    """14:00 for somebody who asked for 'wieczór' must be demoted, not merely unboosted."""
    boost, matched = preference_boost(ev(), {"time_of_day": ["wieczór"]}, slot(14))
    assert boost == pytest.approx(-PENALTIES["time_of_day_mismatch"])
    assert "time_of_day" not in matched


def test_unknown_time_is_neither_boosted_nor_penalised():
    all_day = {"start": "2026-10-20T00:00:00+02:00", "allDay": True}
    boost, _ = preference_boost(ev(), {"time_of_day": ["wieczór"]}, all_day)
    assert boost == 0.0

    no_slot = preference_boost(ev(), {"time_of_day": ["wieczór"]}, None)[0]
    assert no_slot == 0.0


def test_multi_day_slot_is_not_penalised_for_time_of_day():
    """A month-long exhibition has no meaningful hour: asking for 'wieczór' must not
    demote it. (It does still take the separate long-span penalty - isolated here by
    comparing the same event with and without the time request.)"""
    multi = {"start": "2026-10-01T10:00:00+02:00", "end": "2026-11-30T18:00:00+02:00"}
    baseline = preference_boost(ev(format=["Wystawa"]), {}, multi)[0]
    asked = preference_boost(ev(format=["Wystawa"]), {"time_of_day": ["wieczór"]}, multi)[0]
    assert asked == baseline == 0.0


def test_long_span_penalty_is_independent_of_time_of_day():
    multi = {"start": "2026-10-01T10:00:00+02:00", "end": "2026-11-30T18:00:00+02:00"}
    boost, _ = preference_boost(ev(), {}, multi)
    assert boost < 0          # programme/service spanning weeks, not a one-off


# -------------------------------------------------------------- audience
def test_untagged_audience_is_penalised():
    boost, _ = preference_boost(ev(), {"audience": "Dzieci (7-12)"}, slot(11))
    assert boost == pytest.approx(-PENALTIES["audience_untagged"])


def test_family_tag_is_not_penalised():
    boost, _ = preference_boost(
        ev(audience=["Rodziny / wszystkie grupy"]), {"audience": "Dzieci (7-12)"}, slot(11))
    assert boost == 0.0


def test_no_audience_request_means_no_penalty():
    assert preference_boost(ev(), {}, slot(11))[0] == 0.0


# ------------------------------------------------------------------ mode
def test_online_is_penalised_when_not_requested():
    boost, _ = preference_boost(ev(mode="Online"), {"query": "koncert"}, slot(19))
    assert boost == pytest.approx(-PENALTIES["online_unrequested"])


def test_online_event_flag_also_counts():
    event = {"id": "e", "title": "X", "online": True, "tags": {}}
    assert preference_boost(event, {}, slot(19))[0] == pytest.approx(
        -PENALTIES["online_unrequested"])


def test_online_is_not_penalised_when_requested():
    boost, _ = preference_boost(ev(mode="Online"), {"mode": "Online"}, slot(19))
    assert boost == 0.0


def test_in_person_event_is_not_penalised():
    boost, _ = preference_boost(ev(mode="Stacjonarne"), {}, slot(19))
    assert boost == 0.0


# ------------------------------------------------------- combined signal
def test_contradiction_outweighs_a_weak_taxonomy_match():
    """A wrong-time, untagged-online event must not profit from a theme hit."""
    boost, matched = preference_boost(
        ev(theme=["Nauka"], mode="Online"),
        {"themes": ["Nauka"], "time_of_day": ["wieczór"], "audience": "Dorośli (18-64)"},
        slot(11),
    )
    assert matched["themes"] == ["Nauka"]
    assert boost == pytest.approx(
        BOOSTS["themes"] - PENALTIES["time_of_day_mismatch"]
        - PENALTIES["audience_untagged"] - PENALTIES["online_unrequested"])


# ------------------------------------------------------------ diversify
def cand(score: float, venue: str, theme: str, eid: str | None = None) -> Candidate:
    return Candidate(
        event={"id": eid or f"{venue}-{theme}-{score}", "venue": {"name": venue},
               "tags": {"theme": [theme]}},
        score=score,
    )


def test_diversify_keeps_clear_score_order():
    """Small variety penalties must not reorder events that are genuinely better."""
    a = cand(0.60, "V1", "T1")
    b = cand(0.59, "V2", "T2")
    c = cand(0.58, "V1", "T1")
    assert [x.event["id"] for x in diversify([a, b, c], 3)] == [
        a.event["id"], b.event["id"], c.event["id"]]


def test_diversify_still_spreads_repeated_venue():
    a = cand(0.600, "V1", "T1")
    b = cand(0.600, "V1", "T2")
    c = cand(0.585, "V2", "T3")
    out = [x.event["id"] for x in diversify([a, b, c], 3)]
    assert out[0] == a.event["id"]
    assert out[1] == c.event["id"]        # different venue wins over the repeat
    assert out[2] == b.event["id"]


def test_diversify_respects_top_k():
    pool = [cand(0.5 - i * 0.01, f"V{i}", f"T{i}") for i in range(8)]
    assert len(diversify(pool, 3)) == 3


def test_diversify_penalties_are_smaller_than_boosts():
    """Guard the invariant that variety never outvotes a stated preference."""
    from inspect import signature
    defaults = signature(diversify).parameters
    assert defaults["venue_penalty"].default <= min(BOOSTS.values())
    assert defaults["theme_penalty"].default <= min(BOOSTS.values())

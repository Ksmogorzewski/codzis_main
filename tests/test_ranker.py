"""LLM re-rank payloads + JSON parsing (recommender/ranker.py)."""

from __future__ import annotations

from recommender.ranker import _candidate_payload, _parse_json, _prefs_payload
from recommender.retriever import Candidate


def _cand(eid, **meta):
    event = {
        "id": eid,
        "title": "Kino plenerowe",
        "lead": "<p>Seans pod gwiazdami.</p>",
        "district": [{"name": "Śródmieście"}],
        "venue": {"name": "Bulwary Wiślane"},
        "tags": {"theme": ["Film"], "occasion": ["Na randkę"], "cost": "Bezpłatne",
                 "unused_dimension": ["x"]},
    }
    return Candidate(event=event, score=0.51, metadata=dict(meta))


def test_payload_includes_matched_preferences():
    payload = _candidate_payload([_cand("e1", matched={"occasion": ["Na randkę"]}, slot=None)])
    assert payload[0]["matched"] == {"occasion": ["Na randkę"]}


def test_payload_matched_is_none_when_no_preference_hit():
    payload = _candidate_payload([_cand("e1", matched={})])
    assert payload[0]["matched"] is None


def test_payload_strips_html_and_keeps_tags():
    item = _candidate_payload([_cand("e1", matched={})])[0]
    assert item["lead"] == "Seans pod gwiazdami."
    assert item["district"] == "Śródmieście"
    assert item["venue"] == "Bulwary Wiślane"
    assert set(item["tags"]) == {"theme", "occasion", "cost"}   # only known dimensions
    assert item["score"] == 0.51


def test_payload_rank_seed_is_sequential():
    payload = _candidate_payload([_cand("a", matched={}), _cand("b", matched={})])
    assert [p["rank_seed"] for p in payload] == [1, 2]


def test_prefs_payload_drops_empty_values():
    assert _prefs_payload({"query": "x", "interests": [], "district": None,
                           "profile": ""}) == {"query": "x"}


def test_parse_json_plain():
    assert _parse_json('{"ranking": [], "notes": "ok"}') == {"ranking": [], "notes": "ok"}


def test_parse_json_strips_markdown_fence():
    assert _parse_json('```json\n{"ranking": []}\n```') == {"ranking": []}
    assert _parse_json('```\n{"ranking": []}\n```') == {"ranking": []}


def test_parse_json_garbage_does_not_raise():
    out = _parse_json("I cannot help with that.")
    assert out["ranking"] == []
    assert out["notes"] == "LLM returned non-JSON"
    assert out["raw"] == "I cannot help with that."

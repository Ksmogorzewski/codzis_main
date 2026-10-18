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


def test_rerank_is_deterministic_by_default():
    """Ranking temperature must be 0 so the same input yields the same order."""
    import inspect

    from recommender.ranker import rank_candidates

    assert inspect.signature(rank_candidates).parameters["temperature"].default == 0.0


def _capturing_client(captured: list):
    class Client:
        def chat(self, messages, **kwargs):
            captured.extend(messages)

            class M:
                content = '{"ranking": [], "notes": ""}'

            class C:
                message = M()

            class R:
                choices = [C()]
                usage = None

            return R()

    return Client()


def test_query_dominates_profile_in_prompt():
    """Z wpisaną frazą ranking LLM ma traktować ją jako nadrzędną wobec profilu."""
    from recommender.ranker import rank_candidates

    captured: list = []
    rank_candidates(_capturing_client(captured), {"query": "jazz", "themes": ["Sport"]},
                    [_cand("e1", matched={})])
    assert "outranks every profile preference" in captured[0]["content"]


def test_prompt_bez_frazy_zostaje_profilowy():
    from recommender.ranker import rank_candidates

    captured: list = []
    rank_candidates(_capturing_client(captured), {"themes": ["Sport"]}, [_cand("e1", matched={})])
    assert "outranks every profile preference" not in captured[0]["content"]


def test_expansion_stays_creative():
    """Expansion deliberately keeps a non-zero temperature (unlike ranking)."""
    from recommender.expand import EXPANSION_TEMPERATURE

    assert EXPANSION_TEMPERATURE > 0.0


def test_expansion_temperature_is_sent_to_the_llm():
    from recommender.expand import EXPANSION_TEMPERATURE, expand_query

    seen = {}

    class Client:
        def chat(self, messages, **kwargs):
            seen.update(kwargs)
            class M:
                content = "jazz, koncert"
            class C:
                message = M()
            class R:
                choices = [C()]
            return R()

    expand_query(Client(), {"query": "coś"})
    assert seen["temperature"] == EXPANSION_TEMPERATURE

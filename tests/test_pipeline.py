"""Chunker, vector index, retriever pipeline and Recommender wiring.

Uses the FakeEmbeddingModel fixture (conftest.py): real pipeline code, no torch.
"""

from __future__ import annotations

import numpy as np
import pytest

from recommender import Recommender
from recommender.chunker import build_event_text, chunk_events, plain_text
from recommender.embedder import build_index
from recommender.embedder.index import VectorIndex
from recommender.retriever import Retriever


# ------------------------------------------------------------------ chunker
def test_plain_text_strips_html_and_zero_width():
    assert plain_text("<p>Koncert\u200b jazzowy</p>") == "Koncert jazzowy"


def test_build_event_text_shape():
    text = build_event_text({
        "title": "Koncert jazzowy",
        "category": [{"name": "Muzyka"}],
        "lead": "Wieczór improwizacji.",
        "tags": {"theme": ["Jazz"], "format": ["Koncert"]},
    })
    assert text == "Koncert jazzowy. Muzyka. Jazz, Koncert. Wieczór improwizacji."


def test_build_event_text_skips_meaningless_tags():
    text = build_event_text({"title": "X", "tags": {"theme": ["Inne"], "format": ["Nieznane"]}})
    assert text == "X"


def test_chunk_events_one_chunk_per_event(events):
    chunks = chunk_events(events)
    assert len(chunks) == len(events)
    assert all(c.total_chunks == 1 for c in chunks)


def test_chunk_events_splits_pathological_length():
    long_event = {"id": "l", "title": "X", "lead": " ".join(["Zdanie."] * 900)}
    chunks = chunk_events([long_event], max_chars=200)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)


# -------------------------------------------------------------------- index
def test_index_returns_top_k_sorted(fake_model):
    chunks = chunk_events([
        {"id": "a", "title": "jazz koncert"},
        {"id": "b", "title": "rock koncert"},
        {"id": "c", "title": "pływanie basen"},
    ])
    index = VectorIndex()
    index.add(chunks, fake_model.encode([c.text for c in chunks]))

    hits = index.query(fake_model.encode(["jazz"])[0], k=3)
    assert hits[0][0].event_id == "a"
    assert len(hits) == 3
    assert [s for _, s in hits] == sorted([s for _, s in hits], reverse=True)


def test_index_allow_filters_rows(fake_model):
    chunks = chunk_events([{"id": "a", "title": "jazz"}, {"id": "b", "title": "jazz"}])
    index = VectorIndex()
    index.add(chunks, fake_model.encode([c.text for c in chunks]))
    hits = index.query(fake_model.encode(["jazz"])[0], k=10, allow={"b"})
    assert {h[0].event_id for h in hits} == {"b"}


def test_index_empty_query(fake_model):
    chunks = chunk_events([{"id": "a", "title": "jazz"}])
    index = VectorIndex()
    index.add(chunks, fake_model.encode([c.text for c in chunks]))
    assert index.query(np.zeros(fake_model.dim), k=5) == []


def test_build_index_dim_and_len(events, fake_model):
    index, model = build_index(events, model=fake_model)
    assert model is fake_model
    assert len(index) == len(events)
    assert index.dim == fake_model.dim


# ---------------------------------------------------------------- retriever
def test_retriever_ranks_semantically(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    top = retriever.retrieve({"query": "koncert jazzowy"}, top_k=3)
    assert top[0].event_id == "jazz"
    assert "cosine" in top[0].metadata and "slot" in top[0].metadata


def test_retriever_uses_passage_prompt_for_events_and_query_for_user(events, fake_model):
    fake_model.prompt_calls.clear()
    retriever = Retriever(events, model=fake_model)
    fake_model.prompt_calls.clear()
    retriever.retrieve({"query": "jazz"}, top_k=1)
    assert "query" in fake_model.prompt_calls      # user side
    assert "passage" not in fake_model.prompt_calls  # index already built


def test_hard_filter_cost(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    ids = [c.event_id for c in retriever.retrieve({"query": "koncert", "cost": "Bezpłatne"}, top_k=10)]
    assert "jazz" in ids and "rock" not in ids


def test_hard_filter_district(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    assert [c.event_id for c in retriever.retrieve(
        {"query": "koncert", "district": "Praga-Południe"}, top_k=10)] == ["rock"]


def test_audience_filter_ranks_tagged_match_first(events, fake_model):
    """Untagged events are NOT excluded (documented no-op), but the tagged match wins."""
    retriever = Retriever(events, model=fake_model)
    ids = [c.event_id for c in retriever.retrieve(
        {"query": "warsztaty dla dzieci", "audience": "Dzieci (7-12)"}, top_k=10)]
    assert ids[0] == "kids"
    assert "jazz" in ids          # no audience tag -> passes the filter
    assert "rock" in ids


@pytest.mark.parametrize("event_audience,wanted,expected", [
    (["Dzieci (7-12)"], "Dzieci (7-12)", True),
    (["Dzieci (7-12)"], "Dorośli (18-64)", False),
    (None, "Dorośli (18-64)", True),                       # untagged -> no-op
    ([], "Dorośli (18-64)", True),
    (["Rodziny / wszystkie grupy"], "Dorośli (18-64)", True),   # family events always pass
    (["Dorośli (18-64)"], "Seniorzy (65+)", True),         # seniors welcome at adult events
    (["Seniorzy (65+)"], "Dorośli (18-64)", False),
])
def test_audience_matches_rule(event_audience, wanted, expected):
    from recommender.retriever.filters import audience_matches
    assert audience_matches(event_audience, wanted) is expected


def test_hard_filter_date_window(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    ids = [c.event_id for c in retriever.retrieve(
        {"query": "zajęcia", "date_from": "2026-10-23", "date_to": "2026-10-23"}, top_k=10)]
    assert ids == ["pool2"]


def test_no_matches_returns_empty(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    assert retriever.retrieve({"query": "x", "district": "Nieistniejąca"}, top_k=5) == []


def test_min_score_floor(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    all_hits = retriever.retrieve({"query": "koncert jazzowy"}, top_k=10)
    kept = retriever.retrieve({"query": "koncert jazzowy"}, top_k=10, min_score=0.99)
    assert len(kept) <= len(all_hits)


def test_soft_preference_boost_is_recorded(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    cands = retriever.retrieve({"query": "muzyka", "themes": ["Jazz"]}, top_k=10)
    jazz = next(c for c in cands if c.event_id == "jazz")
    assert jazz.metadata["matched"]["themes"] == ["Jazz"]
    assert jazz.metadata["boost"] > 0


def test_recency_prefers_closer_district(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    cands = retriever.retrieve({"query": "koncert", "home_district": "Śródmieście"}, top_k=10)
    assert next(c for c in cands if c.event_id == "jazz").metadata["matched"]["district"] == ["home"]


def test_duplicate_titles_collapse_in_retrieval(events, fake_model):
    retriever = Retriever(events, model=fake_model)
    ids = [c.event_id for c in retriever.retrieve({"query": "zajęcia pływania"}, top_k=10)]
    assert len([i for i in ids if i.startswith("pool")]) == 1


# --------------------------------------------------------------- Recommender
def test_recommender_returns_top_k(events, fake_model):
    rec = Recommender(events, model=fake_model, api_key=None)
    out = rec.recommend({"query": "koncert jazzowy"}, top_k=2, explain=False)
    assert len(out) == 2
    assert rec.last_ranking == "cosine"
    assert rec.client is None


def test_recommender_pool_does_not_change_top_k(events, fake_model):
    rec = Recommender(events, model=fake_model, api_key=None)
    assert len(rec.recommend({"query": "koncert"}, top_k=2, pool=5, explain=False)) == 2


def test_recommender_without_events(fake_model):
    rec = Recommender([], model=fake_model, api_key=None)
    assert rec.recommend({"query": "cokolwiek"}, top_k=5, explain=False) == []


def test_recommender_explain_without_key_falls_back(events, fake_model):
    rec = Recommender(events, model=fake_model, api_key=None)
    out = rec.recommend({"query": "koncert"}, top_k=2, explain=True)
    assert rec.last_ranking == "cosine"
    assert len(out) == 2


def test_rerank_llm_error_keeps_cosine_order(events, fake_model):
    rec = Recommender(events, model=fake_model, api_key=None)

    class Broken:
        def chat(self, *a, **k):
            raise RuntimeError("llm down")

    rec.client = Broken()
    out = rec.recommend({"query": "koncert"}, top_k=2, explain=True)
    assert rec.last_ranking == "cosine"
    assert rec.last_error is not None
    assert len(out) == 2


def test_rerank_orders_by_llm_and_adds_reasons(events, fake_model):
    rec = Recommender(events, model=fake_model, api_key=None)
    cands = rec.retriever.retrieve({"query": "koncert"}, top_k=3)
    second = cands[1].event_id

    class Client:
        def chat(self, messages, **kwargs):
            class M:
                content = '{"ranking": [{"id": "%s", "reason": "Bo pasuje"}], "notes": "n"}' % second
            class C:
                message = M()
            class R:
                choices = [C()]
                usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 2,
                                       "total_tokens": 3})()
            return R()

    rec.client = Client()
    ranked = rec.rerank({"query": "koncert"}, cands)
    assert ranked[0].event_id == second
    assert ranked[0].metadata["reason"] == "Bo pasuje"
    assert len(ranked) == len(cands)          # nothing dropped
    assert rec.last_usage["total_tokens"] == 3
    assert rec.last_ranking == "llm"

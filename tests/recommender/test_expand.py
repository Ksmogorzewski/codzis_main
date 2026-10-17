"""LLM query expansion (recommender/expand.py) and its Recommender wiring."""

from __future__ import annotations

import json

import pytest

from recommender import Recommender
from recommender.expand import MAX_EXPANSION_CHARS, expand_query


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class StubClient:
    """Records calls; returns a canned expansion."""

    def __init__(self, content="koncert, muzyka na żywo, jazz, improwizacja", exc=None):
        self.content, self.exc, self.calls, self.payloads = content, exc, 0, []

    def chat(self, messages, **kwargs):
        self.calls += 1
        self.payloads.append(json.loads(messages[-1]["content"]))
        if self.exc:
            raise self.exc
        return _Resp(self.content)


# ---------------------------------------------------------------- expand_query
def test_expands_a_query():
    client = StubClient()
    assert expand_query(client, {"query": "coś na wieczór"}) == client.content
    assert client.calls == 1


def test_no_query_means_no_llm_call():
    client = StubClient()
    assert expand_query(client, {}) is None
    assert expand_query(client, {"query": "   "}) is None
    assert client.calls == 0


def test_interests_are_sent_to_the_llm():
    client = StubClient()
    expand_query(client, {"query": "coś", "interests": ["Muzyka", "Sport"]})
    assert client.payloads[0] == {"query": "coś", "interests": ["Muzyka", "Sport"]}


def test_llm_failure_returns_none():
    assert expand_query(StubClient(exc=ConnectionError("boom")), {"query": "x"}) is None


def test_unhelpful_expansion_is_ignored():
    # echo of the query, or empty output -> no expansion
    assert expand_query(StubClient("coś na wieczór"), {"query": "coś na wieczór"}) is None
    assert expand_query(StubClient("   "), {"query": "coś na wieczór"}) is None


def test_expansion_is_length_capped():
    out = expand_query(StubClient("y" * 5000), {"query": "x"})
    assert out is not None and len(out) == MAX_EXPANSION_CHARS


def test_quotes_are_stripped():
    assert expand_query(StubClient('"jazz, koncert"'), {"query": "x"}) == "jazz, koncert"


# --------------------------------------------------- Recommender._maybe_expand
class _FakeRecommender:
    """Bypasses __init__ so these tests need no embedding model."""

    _maybe_expand = Recommender._maybe_expand

    def __init__(self, client):
        self.client = client
        self.last_expansion = None
        self._expansion_cache = {}


def test_maybe_expand_appends_to_raw_query():
    rec = _FakeRecommender(StubClient("jazz, koncert"))
    out = rec._maybe_expand({"query": "coś na wieczór", "district": "Śródmieście"}, True)
    assert out["query"] == "coś na wieczór. jazz, koncert"
    assert out["district"] == "Śródmieście"          # untouched
    assert rec.last_expansion == "jazz, koncert"


def test_maybe_expand_does_not_mutate_input():
    rec = _FakeRecommender(StubClient("jazz"))
    user = {"query": "coś"}
    rec._maybe_expand(user, True)
    assert user == {"query": "coś"}


def test_maybe_expand_is_cached_per_query_and_interests():
    client = StubClient("jazz")
    rec = _FakeRecommender(client)
    rec._maybe_expand({"query": "a"}, True)
    rec._maybe_expand({"query": "a"}, True)
    assert client.calls == 1
    rec._maybe_expand({"query": "a", "interests": ["Muzyka"]}, True)
    assert client.calls == 2                       # different interests -> new key


def test_maybe_expand_disabled():
    rec = _FakeRecommender(StubClient("jazz"))
    user = {"query": "coś"}
    assert rec._maybe_expand(user, False) is user
    assert rec.last_expansion is None


def test_maybe_expand_without_client():
    rec = _FakeRecommender(None)
    user = {"query": "coś"}
    assert rec._maybe_expand(user, True) is user


def test_maybe_expand_without_query():
    client = StubClient("jazz")
    rec = _FakeRecommender(client)
    assert rec._maybe_expand({"district": "Praga"}, True) == {"district": "Praga"}
    assert client.calls == 0


def test_maybe_expand_falls_back_when_llm_fails():
    rec = _FakeRecommender(StubClient(exc=TimeoutError("slow")))
    out = rec._maybe_expand({"query": "coś"}, True)
    assert out == {"query": "coś"}
    assert rec.last_expansion is None

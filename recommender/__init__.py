"""Warsaw event recommender — RAG (cosine retrieval + optional LLM re-rank).

This is an importable component for a larger system: load events once, then call
`recommend(user_context)` per request to get ranked event suggestions.

Typical usage (build once, serve many — the AWS pattern):

    from recommender import Recommender

    rec = Recommender(events)                 # loads embedding model + builds index
    results = rec.recommend(user_context, top_k=10)

`user_context` is a flexible dict. Any of these fields are optional:

    query: str                 # natural-language request
    interests: list[str]       # declared interests / categories
    liked_event_ids: list[str] # past taste (ids of liked events)
    # hard filters (a string or a list of any-of values):
    district: str | list       # e.g. "Śródmieście" (online events pass)
    cost: str | list           # "Bezpłatne" / "Płatne" / "Nieznane"
    mode: str | list           # "Stacjonarne" / "Online" / "Hybrydowe"
    audience: str | list       # e.g. "Dorośli (18-64)"
    max_price: float           # PLN, for events with a declared price
    date_from: str             # ISO date, e.g. "2026-10-17"
    date_to: str               # ISO date
    now: str                   # ISO datetime: skip what is already over
    # soft preferences (reorder only, see retriever/scoring.py):
    themes, formats, occasion, activity_level, setting, registration, accessibility,
    time_of_day, home_district, near_districts
    profile: str               # free-text profile passed to the LLM ranker

No DeepSeek key is required: without one, results are pure cosine ranking. With a
key (env `DEEPSEEK_API_KEY` or a local `.env`), DeepSeek re-ranks the top candidates
and adds a one-line reason to each result.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .chunker import EventChunk, chunk_events, build_event_text, event_district, plain_text, MAX_CHUNK_CHARS
from .embedder import EmbeddingModel, VectorIndex, build_index, DEFAULT_MODEL
from .retriever import Retriever, Candidate, QueryEncoder, DEFAULT_TASTE_WEIGHT, DEFAULT_MIN_SCORE, BOOSTS, PENALTIES
from .llm import DeepSeekClient, load_env_value, DEEPSEEK_MODEL
from .ranker import MAX_RERANK_CANDIDATES, rank_candidates
from .expand import expand_query

__version__ = "0.1.0"

__all__ = [
    "Recommender",
    "recommend",
    "Retriever",
    "Candidate",
    "EmbeddingModel",
    "VectorIndex",
    "EventChunk",
    "QueryEncoder",
    "DeepSeekClient",
    "build_index",
    "chunk_events",
    "build_event_text",
    "event_district",
    "plain_text",
    "rank_candidates",
    "expand_query",
    "DEFAULT_MODEL",
    "DEFAULT_TASTE_WEIGHT",
    "DEFAULT_MIN_SCORE",
    "MAX_RERANK_CANDIDATES",
    "BOOSTS",
    "PENALTIES",
    "__version__",
]


# Rozwijanie frazy pomaga przy krótkich/niejasnych zapytaniach ("coś na randkę"). Konkretna,
# kilkuwyrazowa fraza ("koncert jazzowy w piątek") już nazywa, czego szuka użytkownik, więc
# pomijamy tę rundę LLM (o jedno wywołanie szybciej) i rankujemy surową frazę.
_SPECIFIC_MIN_WORDS = 3
_VAGUE_MARKERS = ("coś", "co", "jakieś", "jakaś", "jakiś", "cokolwiek", "ciekawe", "ciekawego",
                  "pomysł", "propozycje", "wydarzenia", "fajne", "fajnego")


def _query_is_specific(query: str) -> bool:
    words = query.split()
    if len(words) < _SPECIFIC_MIN_WORDS:
        return False
    head = [w.lower() for w in words[:2]]
    return not any(w.startswith(m) for m in _VAGUE_MARKERS for w in head)


class Recommender:
    """Build once, then recommend per request.

    Holds the embedding model + vector index + query encoder in memory. Passing a
    DeepSeek `api_key` (or leaving it None and letting the client resolve the env var)
    enables LLM re-ranking + explanations; otherwise results are cosine-ranked.

    index: optional prebuilt VectorIndex over chunk_events(events) (e.g. loaded from
    storage) - skips embedding every event at startup.
    llm_timeout: seconds for one DeepSeek call, without retries (for request/response
    serving); None keeps the client defaults.
    """

    def __init__(
        self,
        events: list[dict],
        model: EmbeddingModel | None = None,
        taste_weight: float = DEFAULT_TASTE_WEIGHT,
        api_key: str | None = None,
        index: VectorIndex | None = None,
        llm_timeout: float | None = None,
    ):
        self.events = events
        self.retriever = Retriever(events, model=model, taste_weight=taste_weight, index=index)
        # Resolve key explicitly so `explain` knows whether LLM ranking is possible.
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or load_env_value("DEEPSEEK_API_KEY")
        limits = {} if llm_timeout is None else {"timeout": llm_timeout, "max_retries": 0}
        self.client: DeepSeekClient | None = (
            DeepSeekClient(api_key=self.api_key, model=DEEPSEEK_MODEL, **limits) if self.api_key else None
        )
        self.last_usage: dict | None = None
        self.last_notes: str | None = None
        self.last_ranking: str | None = None   # "llm" | "cosine"
        self.last_error: str | None = None     # why the LLM re-rank was skipped
        self.last_expansion: str | None = None # the LLM-expanded query text actually embedded
        self.last_dropped: int = 0             # candidates removed by the min_score floor
        self._expansion_cache: dict[str, str | None] = {}

    # ------------------------------------------------------------------ #
    def recommend(
        self,
        user_context: dict,
        top_k: int = 10,
        min_score: float | None = DEFAULT_MIN_SCORE,
        explain: bool = True,
        pool: int | None = None,
        expand: bool = True,
        query_vector: object | None = None,
    ) -> list[Candidate]:
        """Rank events for a user context.

        explain=True (default) uses DeepSeek to re-rank + explain when a key is
        available; otherwise (or when the call fails) falls back to cosine ranking.
        Set explain=False to always use pure cosine ranking.
        pool: how many retrieved candidates the LLM re-ranks (top_k of them are returned).
        expand=True (default) asks DeepSeek to expand a short/vague query into a richer
        search text before embedding (cached per query; no-op without a key or a query).
        min_score: cosine floor (default DEFAULT_MIN_SCORE) - weak candidates are dropped
        rather than padding the list, so fewer than top_k results can come back. Pass
        None to disable. See `last_dropped` for how many were cut.
        query_vector: a precomputed query vector (see Retriever.retrieve). Ignored when
        `expand` rewrites the query, because then the text - and vector - change.
        """
        original = user_context
        user_context = self._maybe_expand(user_context, expand)
        if query_vector is not None and user_context is not original:
            query_vector = None  # expansion changed the text; the precomputed vector is stale
        candidates = self.retriever.retrieve(user_context, top_k=max(top_k, pool or 0),
                                             min_score=min_score, query_vector=query_vector)
        self.last_dropped = self.retriever.last_dropped
        self.last_usage = None
        self.last_notes = None
        self.last_ranking = "cosine"
        self.last_error = None
        if not candidates:
            return []
        if explain:
            ranked = self.rerank(user_context, candidates)
            if ranked is not None:
                candidates = ranked
        return candidates[:top_k]

    # ------------------------------------------------------------------ #
    def expand(self, user_context: dict) -> dict:
        """The user context with its query expanded by the LLM (see `_maybe_expand`).

        For callers that retrieve in two passes: a fast one without the LLM, then this
        expansion + `retriever.retrieve` + `rerank` in the background.
        """
        return self._maybe_expand(user_context, True)

    # ------------------------------------------------------------------ #
    def _maybe_expand(self, user_context: dict, expand: bool) -> dict:
        """Append the LLM expansion to the query (cached per query+interests).

        Returns the original context unchanged when expansion is disabled, impossible
        (no key / no query) or fails. The raw query is kept in front so the user's own
        words stay anchored; the expansion only adds topical signal.
        """
        self.last_expansion = None
        query = (user_context.get("query") or "").strip()
        if not expand or self.client is None or not query:
            return user_context
        if _query_is_specific(query):
            return user_context  # konkretna fraza: rozwijanie niewiele dodaje, oszczędzamy rundę LLM
        key = json.dumps([query, user_context.get("interests") or []],
                         ensure_ascii=False, sort_keys=True)
        if key not in self._expansion_cache:
            self._expansion_cache[key] = expand_query(self.client, user_context)
        extra = self._expansion_cache[key]
        self.last_expansion = extra
        if not extra:
            return user_context
        ctx = dict(user_context)
        ctx["query"] = f"{query}. {extra}"
        return ctx

    # ------------------------------------------------------------------ #
    def rerank(self, user_context: dict, candidates: list[Candidate]) -> list[Candidate] | None:
        """DeepSeek re-rank + one-line reasons for already retrieved candidates.

        Returns None when the LLM is unavailable or fails (the caller keeps the cosine
        order). Lets a caller show cosine results first and ask the LLM afterwards
        without retrieving again.
        """
        if self.client is None or not candidates:
            return None
        # Mniej kandydatów = mniejszy prompt = szybsze wywołanie LLM; odrzuceni zostają w kolejności cosinus.
        pool = candidates[:MAX_RERANK_CANDIDATES]
        try:
            result = rank_candidates(self.client, user_context, pool)
        except Exception as exc:  # the LLM is optional: keep the cosine order
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        self.last_ranking = "llm"
        self.last_usage = result["usage"]
        self.last_notes = result["data"].get("notes")
        ranking = result["data"].get("ranking") or []
        reasons = {r.get("id"): r.get("reason", "") for r in ranking if isinstance(r, dict)}
        by_id = {c.event_id: c for c in candidates}
        ordered: list[Candidate] = []
        seen: set[str] = set()
        for r in ranking:
            cid = r.get("id") if isinstance(r, dict) else None
            c = by_id.get(cid)
            if c and cid not in seen:
                c.metadata["reason"] = reasons.get(cid, "")
                ordered.append(c)
                seen.add(cid)
        # Append any candidate the LLM dropped, preserving cosine order.
        for c in candidates:
            if c.event_id not in seen:
                ordered.append(c)
        return ordered


# --------------------------------------------------------------------------- #
def recommend(
    user_context: dict,
    events: list[dict],
    top_k: int = 10,
    min_score: float | None = DEFAULT_MIN_SCORE,
    explain: bool = True,
    api_key: str | None = None,
    model: EmbeddingModel | None = None,
) -> list[Candidate]:
    """One-shot convenience: build a Recommender and rank for one user context.

    NOTE: this rebuilds the index on every call (model load + embed all events), so it
    is fine for demos/tests. For repeated serving, instantiate `Recommender` once.
    """
    rec = Recommender(events, model=model, api_key=api_key)
    return rec.recommend(user_context, top_k=top_k, min_score=min_score, explain=explain)

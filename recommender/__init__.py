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
    district: str              # hard filter, e.g. "Śródmieście"
    cost: str                  # hard filter: "Bezpłatne" / "Płatne" / "Nieznane"
    mode: str                  # hard filter: "Stacjonarne" / "Online" / "Hybrydowe"
    audience: str              # hard filter, e.g. "Dorośli (18-64)"
    date_from: str             # ISO date, e.g. "2026-10-17"
    date_to: str               # ISO date

No DeepSeek key is required: without one, results are pure cosine ranking. With a
key (env `DEEPSEEK_API_KEY` or a local `.env`), DeepSeek re-ranks the top candidates
and adds a one-line reason to each result.
"""

from __future__ import annotations

import os
from typing import Any

from .chunker import EventChunk, chunk_events, build_event_text, MAX_CHUNK_CHARS
from .embedder import EmbeddingModel, VectorIndex, build_index, DEFAULT_MODEL
from .retriever import Retriever, Candidate, QueryEncoder, DEFAULT_TASTE_WEIGHT
from .llm import DeepSeekClient, load_env_value, DEEPSEEK_MODEL
from .ranker import rank_candidates

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
    "rank_candidates",
    "DEFAULT_MODEL",
    "DEFAULT_TASTE_WEIGHT",
    "__version__",
]


class Recommender:
    """Build once, then recommend per request.

    Holds the embedding model + vector index + query encoder in memory. Passing a
    DeepSeek `api_key` (or leaving it None and letting the client resolve the env var)
    enables LLM re-ranking + explanations; otherwise results are cosine-ranked.
    """

    def __init__(
        self,
        events: list[dict],
        model: EmbeddingModel | None = None,
        taste_weight: float = DEFAULT_TASTE_WEIGHT,
        api_key: str | None = None,
    ):
        self.events = events
        self.retriever = Retriever(events, model=model, taste_weight=taste_weight)
        # Resolve key explicitly so `explain` knows whether LLM ranking is possible.
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or load_env_value("DEEPSEEK_API_KEY")
        self.client: DeepSeekClient | None = (
            DeepSeekClient(api_key=self.api_key, model=DEEPSEEK_MODEL) if self.api_key else None
        )
        self.last_usage: dict | None = None
        self.last_notes: str | None = None

    # ------------------------------------------------------------------ #
    def recommend(
        self,
        user_context: dict,
        top_k: int = 10,
        min_score: float | None = None,
        explain: bool = True,
    ) -> list[Candidate]:
        """Rank events for a user context.

        explain=True (default) uses DeepSeek to re-rank + explain when a key is
        available; otherwise falls back to cosine ranking. Set explain=False to
        always use pure cosine ranking.
        """
        candidates = self.retriever.retrieve(user_context, top_k=top_k, min_score=min_score)
        self.last_usage = None
        self.last_notes = None
        if not candidates:
            return []

        if explain and self.client is not None:
            result = rank_candidates(self.client, user_context, candidates)
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
            candidates = ordered

        return candidates


# --------------------------------------------------------------------------- #
def recommend(
    user_context: dict,
    events: list[dict],
    top_k: int = 10,
    min_score: float | None = None,
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

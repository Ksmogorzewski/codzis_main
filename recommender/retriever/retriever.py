"""Retriever: flexible UserContext -> ranked, filtered candidate events.

Pipeline (strict AND pre-filter, no fallback):
    1. hard-filter events by district / cost / mode / audience / price / date  (filters.py)
    2. encode the user context -> single query vector                        (QueryEncoder)
    3. cosine over the prebuilt index, restricted to the filtered events     (no re-embedding)
    4. best chunk per event + small soft-preference boosts                   (scoring.py)
    5. collapse same-title duplicates among the survivors                    (dedupe.py)
    6. varied top-k: not one venue / one theme over and over                 (scoring.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..chunker import build_event_text
from ..embedder import EmbeddingModel, VectorIndex

from .dedupe import dedupe_events
from .filters import make_event_filter, next_slot
from .query_encoder import QueryEncoder, DEFAULT_TASTE_WEIGHT
from .scoring import diversify, preference_boost


@dataclass
class Candidate:
    """A retrieved event plus its relevance signal."""

    event: dict
    score: float                        # cosine of the best chunk + preference boosts
    matched_chunk_text: str = ""        # the chunk that scored highest (for debugging)
    metadata: dict[str, Any] = field(default_factory=dict)  # cosine, boost, matched, slot, reason

    @property
    def event_id(self) -> str:
        return self.event.get("id", "")


class Retriever:
    """Owns the index, model, and query encoder; serves retrieval requests.

    Build once, then call retrieve() per request. Pass `index` (a VectorIndex over
    chunk_events(events), e.g. loaded from storage) to skip embedding the events here.
    """

    def __init__(
        self,
        events: list[dict],
        model: EmbeddingModel | None = None,
        taste_weight: float = DEFAULT_TASTE_WEIGHT,
        index: VectorIndex | None = None,
    ):
        from ..embedder import build_index  # local import to avoid a cycle

        self.model = model or EmbeddingModel()
        self.events: list[dict] = list(events)
        if index is None:
            self.index, self.model = build_index(self.events, model=self.model)
        else:
            self.index = index
        self._by_id: dict[str, dict] = {e.get("id", ""): e for e in self.events}

        # Query encoder needs id->text to resolve liked_event_ids.
        self.encoder = QueryEncoder(self.model, taste_weight=taste_weight)
        self.encoder.set_event_texts({e.get("id", ""): build_event_text(e) for e in self.events})

    # ------------------------------------------------------------------ #
    def retrieve(self, user: dict, top_k: int = 10, min_score: float | None = None) -> list[Candidate]:
        """Return up to top_k filtered, relevance-ranked candidate events.

        min_score: optional cosine-similarity floor (0..1). Results scoring strictly
        below this are dropped. Useful to surface only high-confidence matches.
        """
        predicate = make_event_filter(user)
        allowed = {e.get("id", "") for e in self.events if predicate(e)}
        if not allowed:
            return []

        # Every chunk of the filtered events, best first (the index holds all events).
        qv = self.encoder.encode(user)
        hits = self.index.query(qv, k=len(self.index), allow=allowed)

        # Dedupe chunks -> best score per event, preserve best-first order.
        best: dict[str, Candidate] = {}
        for chunk, score in hits:
            e = self._by_id.get(chunk.event_id)
            if e is None:
                continue
            cur = best.get(chunk.event_id)
            if cur is None or score > cur.score:
                best[chunk.event_id] = Candidate(
                    event=e, score=score, matched_chunk_text=chunk.text
                )

        for c in best.values():
            slot = next_slot(c.event, user.get("date_from"), user.get("date_to"), user.get("now"))
            boost, matched = preference_boost(c.event, user, slot)
            c.metadata.update(cosine=c.score, boost=boost, matched=matched, slot=slot)
            c.score += boost

        candidates = sorted(best.values(), key=lambda c: c.score, reverse=True)
        if min_score is not None:
            candidates = [c for c in candidates if c.metadata["cosine"] >= min_score]
        return diversify(_dedupe(candidates), top_k)


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    """Same-title events -> the best-scoring one (with the group's dates in all_dates)."""
    by_id = {c.event_id: c for c in candidates}
    kept = dedupe_events([c.event for c in candidates], {c.event_id: c.score for c in candidates})
    out: list[Candidate] = []
    for event in kept:
        c = by_id[event.get("id", "")]
        c.event = event
        out.append(c)
    return out

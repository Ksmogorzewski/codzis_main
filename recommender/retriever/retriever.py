"""Retriever: flexible UserContext -> ranked, filtered candidate events.

Pipeline (strict AND pre-filter, no fallback):
    1. hard-filter events by district / cost / mode / audience / date  (structured prefs)
    2. encode the user context -> single query vector                     (QueryEncoder)
    3. vector top-k over the chunks of the *filtered* events
    4. dedupe chunks -> one best-scoring result per event
    5. return candidates sorted by relevance score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..chunker import build_event_text
from ..embedder import EmbeddingModel, VectorIndex

from .dedupe import dedupe_events
from .filters import make_event_filter
from .query_encoder import QueryEncoder, DEFAULT_TASTE_WEIGHT


@dataclass
class Candidate:
    """A retrieved event plus its relevance signal."""

    event: dict
    score: float                        # best cosine score across its chunks
    matched_chunk_text: str = ""        # the chunk that scored highest (for debugging)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_id(self) -> str:
        return self.event.get("id", "")


class Retriever:
    """Owns the index, model, and query encoder; serves retrieval requests.

    Build once (loads model + indexes events), then call retrieve() per request.
    """

    def __init__(
        self,
        events: list[dict],
        model: EmbeddingModel | None = None,
        taste_weight: float = DEFAULT_TASTE_WEIGHT,
    ):
        from ..embedder import build_index  # local import to avoid a cycle

        self.model = model or EmbeddingModel()
        # Collapse recurring events (same title, multiple dates) into one entry so
        # they don't crowd out diverse results.
        self.events: list[dict] = dedupe_events(list(events))
        self.index, self.model = build_index(self.events, model=self.model)
        self._by_id: dict[str, dict] = {e.get("id", ""): e for e in self.events}

        # Query encoder needs id->text to resolve liked_event_ids.
        self.encoder = QueryEncoder(self.model, taste_weight=taste_weight)
        self.encoder.set_event_texts({e.get("id", ""): build_event_text(e) for e in self.events})

    # ------------------------------------------------------------------ #
    def _chunks_for_events(self, events: list[dict]) -> VectorIndex:
        """Build a temporary index over only the filtered events (keeps scores meaningful)."""
        from ..chunker import chunk_events

        chunks = chunk_events(events)
        sub = VectorIndex()
        if chunks:
            vecs = self.model.encode([c.embedding_input() for c in chunks])
            sub.add(chunks, vecs)
        return sub

    # ------------------------------------------------------------------ #
    def retrieve(self, user: dict, top_k: int = 10, min_score: float | None = None) -> list[Candidate]:
        """Return up to top_k filtered, relevance-ranked candidate events.

        min_score: optional cosine-similarity floor (0..1). Results scoring strictly
        below this are dropped. Useful to surface only high-confidence matches.
        """
        predicate = make_event_filter(user)
        filtered = [e for e in self.events if predicate(e)]

        # Vector retrieval over the filtered subset.
        qv = self.encoder.encode(user)
        if not filtered:
            return []
        sub = self._chunks_for_events(filtered)
        hits = sub.query(qv, k=max(top_k * 3, 20))  # over-fetch to survive dedupe

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

        candidates = sorted(best.values(), key=lambda c: c.score, reverse=True)
        if min_score is not None:
            candidates = [c for c in candidates if c.score >= min_score]
        return candidates[:top_k]

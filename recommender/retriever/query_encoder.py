"""Encode a flexible UserContext into a single query embedding.

Combines the explicit natural-language query, declared interests, and the user's
past taste (liked/attended events) into ONE query vector via a weighted average:

    query_vec = normalize( (1 - taste_weight) * text_vec  +  taste_weight * taste_vec )

- text_vec  : embedding of the concatenated query + interests text
- taste_vec : mean embedding of the liked events' texts (empty -> ignored)

Structured filters (district, cost, mode, date) are NOT embedded — they are handled
as hard filters by the retriever downstream.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from ..chunker import build_event_text
from ..embedder import EmbeddingModel

# Default blend: explicit query+interests dominate, past taste is a moderate nudge.
DEFAULT_TASTE_WEIGHT = 0.35


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def build_query_text(user: dict) -> str:
    """Concatenate the explicit signals (query + interests) into one string."""
    parts: list[str] = []
    q = _clean(user.get("query"))
    if q:
        parts.append(q)
    interests = [i for i in (user.get("interests") or []) if i and str(i).strip()]
    if interests:
        parts.append(", ".join(str(i).strip() for i in interests))
    return ". ".join(parts)


class QueryEncoder:
    """Turns a UserContext dict into a single L2-normalized query vector."""

    def __init__(
        self,
        model: EmbeddingModel,
        taste_weight: float = DEFAULT_TASTE_WEIGHT,
    ):
        if not 0.0 <= taste_weight <= 1.0:
            raise ValueError("taste_weight must be in [0, 1]")
        self.model = model
        self.taste_weight = taste_weight
        # event_id -> text lookup for resolving liked_event_ids (set by retriever).
        self._event_text_by_id: dict[str, str] = {}

    def set_event_texts(self, id_to_text: dict[str, str]) -> None:
        """Provide event_id -> embedding text so liked_event_ids can be resolved."""
        self._event_text_by_id = dict(id_to_text or {})

    # ------------------------------------------------------------------ #
    def _taste_vector(self, user: dict) -> np.ndarray | None:
        liked_ids = [i for i in (user.get("liked_event_ids") or []) if i]
        texts = [
            self._event_text_by_id[i]
            for i in liked_ids
            if i in self._event_text_by_id
        ]
        if not texts:
            return None
        vecs = self.model.encode(texts)          # (m, dim), normalized
        return np.mean(vecs, axis=0).astype(np.float32)

    # ------------------------------------------------------------------ #
    def encode(self, user: dict) -> np.ndarray:
        """Return a single L2-normalized query vector for the user context."""
        text_vec = self.model.encode([build_query_text(user)])[0]

        taste_vec = self._taste_vector(user)
        if taste_vec is None or self.taste_weight == 0.0:
            return text_vec  # already normalized by encode()

        w = self.taste_weight
        combined = (1.0 - w) * text_vec + w * taste_vec
        n = np.linalg.norm(combined)
        if n == 0:
            return text_vec
        return (combined / n).astype(np.float32)

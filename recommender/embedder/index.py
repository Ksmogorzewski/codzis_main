"""In-process vector index over event chunks (numpy, no external DB).

Brute-force cosine top-k via normalized dot product. At this scale (<= a few thousand
events, 384-dim) this is sub-millisecond and far simpler than FAISS. Swappable for
FAISS later if the corpus grows large.

Stores one row per chunk; multiple chunks of the same event share an event_id and the
retriever de-duplicates downstream.
"""

from __future__ import annotations

import numpy as np

from ..chunker import EventChunk


class VectorIndex:
    """A minimal, reusable top-k cosine index.

    Usage:
        index = VectorIndex()
        index.add(chunks, vectors)      # chunks: list[EventChunk], vectors: (n, dim)
        hits = index.query(vec, k=10)   # list[(chunk, score)] sorted by score desc
    """

    def __init__(self) -> None:
        self._chunks: list[EventChunk] = []
        self._matrix: np.ndarray | None = None  # (n, dim) L2-normalized

    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def dim(self) -> int | None:
        return None if self._matrix is None else int(self._matrix.shape[1])

    # ------------------------------------------------------------------ #
    def add(self, chunks: list[EventChunk], vectors: np.ndarray) -> None:
        """Append chunks and their (already L2-normalized) vectors."""
        vectors = np.asarray(vectors, dtype=np.float32)
        if len(chunks) != vectors.shape[0]:
            raise ValueError(
                f"chunks/vectors length mismatch: {len(chunks)} vs {vectors.shape[0]}"
            )
        # Ensure normalized (defensive; encode() already normalizes).
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = vectors / norms
        self._chunks.extend(chunks)
        self._matrix = (
            vectors
            if self._matrix is None
            else np.vstack([self._matrix, vectors])
        )

    # ------------------------------------------------------------------ #
    def query(self, vector: np.ndarray, k: int = 10) -> list[tuple[EventChunk, float]]:
        """Return the k most similar chunks as (chunk, cosine_score), best first."""
        if self._matrix is None or not self._chunks:
            return []
        v = np.asarray(vector, dtype=np.float32).reshape(-1)
        n = np.linalg.norm(v)
        if n == 0:
            return []
        v = v / n
        sims = self._matrix @ v                      # (n,) cosine similarities
        k = min(k, len(self._chunks))
        # argpartition for the top-k indices, then sort those by score desc.
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        return [(self._chunks[i], float(sims[i])) for i in top]

    # ------------------------------------------------------------------ #
    def rebuild(self, chunks: list[EventChunk], vectors: np.ndarray) -> None:
        """Replace the entire index (convenience for a full refresh)."""
        self._chunks = []
        self._matrix = None
        self.add(chunks, vectors)

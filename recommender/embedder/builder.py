"""Convenience builder: raw events -> chunked + embedded + indexed."""

from __future__ import annotations

from typing import Any, Iterable

from ..chunker import chunk_events
from .index import VectorIndex
from .model import EmbeddingModel


def build_index(
    events: Iterable[dict],
    model: EmbeddingModel | None = None,
) -> tuple[VectorIndex, EmbeddingModel]:
    """Chunk, embed, and index a collection of event records.

    Returns (index, model). Pass an existing `model` to reuse a loaded model;
    a new one is created (and loaded) if omitted.

    Typical startup flow (AWS): load model once, embed all events, keep index in memory.
    """
    model = model or EmbeddingModel()
    chunks = chunk_events(list(events))
    if not chunks:
        return VectorIndex(), model
    vectors = model.encode([c.embedding_input() for c in chunks])
    index = VectorIndex()
    index.add(chunks, vectors)
    return index, model

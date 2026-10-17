"""Data types for the event embedding chunker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EventChunk:
    """One embeddable text chunk derived from an event.

    `chunk_index` / `total_chunks` let a caller reconstruct or de-duplicate when an
    event is long enough to be split into several chunks (rare — see chunk_events).
    """

    event_id: str
    event_url: str
    text: str                 # the exact string that should be embedded
    title: str = ""
    district: str | None = None
    categories: list[str] = field(default_factory=list)
    chunk_index: int = 0
    total_chunks: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def embedding_input(self) -> str:
        """Return the text to feed to the embedding model.

        sentence-transformers models take a single string; we keep the pre-built
        `text` (title + categories + lead) as the canonical embedding surface.
        """
        return self.text

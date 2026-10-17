"""Event embedding chunker.

Public API:
    chunk_events(events, max_chars=...) -> list[EventChunk]
    chunk_event(event, max_chars=...)   -> list[EventChunk]
    build_event_text(event)             -> str
    EventChunk                          # dataclass
"""

from .types import EventChunk
from .event_chunker import (
    MAX_CHUNK_CHARS,
    build_event_text,
    chunk_event,
    chunk_events,
)

__all__ = [
    "EventChunk",
    "MAX_CHUNK_CHARS",
    "build_event_text",
    "chunk_event",
    "chunk_events",
]

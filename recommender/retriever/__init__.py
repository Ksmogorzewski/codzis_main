"""Retrieval: encode user context and fetch candidate events.

Public API:
    Retriever(events, model=None, taste_weight=...)  # build once, retrieve per request
    Candidate                                        # event + score + matched chunk
    QueryEncoder(model, taste_weight=...)            # UserContext -> query vector
    build_query_text(user)                           # query + interests as one string
    make_event_filter(user)                          # structured AND pre-filter
    DEFAULT_TASTE_WEIGHT
"""

from .retriever import Retriever, Candidate
from .query_encoder import QueryEncoder, build_query_text, DEFAULT_TASTE_WEIGHT
from .filters import make_event_filter, event_date_range
from .dedupe import dedupe_events, normalize_title

__all__ = [
    "Retriever",
    "Candidate",
    "QueryEncoder",
    "build_query_text",
    "make_event_filter",
    "event_date_range",
    "dedupe_events",
    "normalize_title",
    "DEFAULT_TASTE_WEIGHT",
]

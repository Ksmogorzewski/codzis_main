"""Retrieval: encode user context and fetch candidate events.

Public API:
    Retriever(events, model=None, taste_weight=...)  # build once, retrieve per request
    Candidate                                        # event + score + matched chunk
    QueryEncoder(model, taste_weight=...)            # UserContext -> query vector
    build_query_text(user)                           # query + interests as one string
    make_event_filter(user)                          # structured AND pre-filter
    next_slot(event, date_from, date_to, now)        # when the user could go (or None)
    preference_boost(event, user, slot)              # soft-preference bonus/penalty + what matched
    DEFAULT_TASTE_WEIGHT
    DEFAULT_MIN_SCORE                                # default cosine floor
"""

from .retriever import Retriever, Candidate, DEFAULT_MIN_SCORE
from .query_encoder import QueryEncoder, build_query_text, DEFAULT_TASTE_WEIGHT
from .filters import make_event_filter, event_date_range, event_price, next_slot
from .dedupe import dedupe_events, normalize_title
from .scoring import diversify, preference_boost, BOOSTS, PENALTIES

__all__ = [
    "Retriever",
    "Candidate",
    "QueryEncoder",
    "build_query_text",
    "make_event_filter",
    "event_date_range",
    "event_price",
    "next_slot",
    "dedupe_events",
    "normalize_title",
    "diversify",
    "preference_boost",
    "BOOSTS",
    "PENALTIES",
    "DEFAULT_TASTE_WEIGHT",
    "DEFAULT_MIN_SCORE",
]

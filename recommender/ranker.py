"""Optional DeepSeek re-ranking + explanation of retrieved candidates.

This is the "generation" half of RAG. It re-ranks the cosine-retrieved candidates
semantically and produces a one-line reason per event. It is OPTIONAL: if no API key
is available, the recommender falls back to cosine ranking (see Recommender.recommend).
"""

from __future__ import annotations

import json
from typing import Any

from .llm import DeepSeekClient


def _candidate_payload(candidates: list) -> list[dict]:
    items = []
    for i, c in enumerate(candidates):
        loc = None
        if c.event.get("localization"):
            loc = c.event["localization"][0].get("name")
        items.append({
            "rank_seed": i + 1,
            "id": c.event_id,
            "title": c.event.get("title", ""),
            "lead": (c.event.get("lead") or "")[:300],
            "cosine": round(c.score, 4),
            "district": loc,
        })
    return items


def _prefs_payload(user: dict) -> dict:
    keys = ("query", "interests", "audience", "district", "cost", "mode",
            "date_from", "date_to")
    return {k: user.get(k) for k in keys if user.get(k) not in (None, "", [])}


def _parse_json(text: str) -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"ranking": [], "notes": "LLM returned non-JSON", "raw": text}


def rank_candidates(
    client: DeepSeekClient,
    user: dict,
    candidates: list,
    temperature: float = 0.2,
) -> dict:
    """Re-rank candidates with DeepSeek. Returns {"data": {...}, "usage": {...}}."""
    system = (
        "You are an event recommendation engine for Warsaw. Given a user's preferences "
        "and a list of candidate events (each with a cosine similarity to the user's query), "
        "re-rank them by how well they fit the user and give each a one-line reason. "
        "Output ONLY a JSON object of the form "
        '{"ranking": [{"id": str, "reason": str}], "notes": str}. '
        "Order `ranking` from best to worst. Keep reasons under 20 words, in the same "
        "language as the user's query. Do not omit any candidate."
    )
    user_msg = (
        "User preferences:\n" + json.dumps(_prefs_payload(user), ensure_ascii=False)
        + "\n\nCandidate events:\n" + json.dumps(_candidate_payload(candidates), ensure_ascii=False)
    )
    resp = client.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        json_mode=True,
        temperature=temperature,
    )
    data = _parse_json(resp.choices[0].message.content)
    usage = getattr(resp, "usage", None)
    return {
        "data": data,
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
            "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
            "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
        },
    }

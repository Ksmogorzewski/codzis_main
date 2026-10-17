"""Kandydat z rekomendera -> karta wydarzenia dla frontendu (+ uzasadnienie bez LLM)."""

from recommender import plain_text

# Wymiary taggera pokazywane na karcie
CARD_TAGS = ["theme", "format", "cost", "mode", "setting", "registration", "audience", "activity_level"]
MAX_REASON = 160

_TIME_OF_DAY = {"rano": "rano", "popołudnie": "po południu", "wieczór": "wieczorem"}
_OCCASION = {  # "Samodzielnie" pomijamy - pasuje prawie do wszystkiego
    "Z dziećmi": "dla rodzin z dziećmi", "Ze znajomymi": "ze znajomymi", "Na randkę": "na randkę",
    "Poznawanie nowych ludzi": "okazja, by poznać ludzi",
}


def card(candidate, query: str | None) -> dict:
    e = candidate.event
    meta = candidate.metadata
    tags = e.get("tags") or {}
    attributes = e.get("attributes") or {}
    llm_reason = str(meta.get("reason") or "").strip()[:MAX_REASON]
    return {
        "id": e["id"],
        "title": plain_text(e.get("title")),
        "lead": plain_text(e.get("lead")),
        "url": e.get("url"),
        "ticketUrl": attributes.get("ticketUrl"),
        "imageUrl": e.get("imageUrl"),
        "origin": e.get("origin"),
        "source": e.get("source"),
        "kind": e.get("kind"),
        "partnerName": e.get("partnerName"),
        "district": e.get("district"),
        "venue": e.get("venue"),
        "location": e.get("location"),
        "online": bool(e.get("online")),
        "slot": meta.get("slot"),
        "schedule": e.get("schedule") or [],
        "price": attributes.get("price"),
        "tags": {k: tags[k] for k in CARD_TAGS if tags.get(k)},
        "reason": llm_reason or rule_reason(e, meta.get("matched") or {}, query),
        "reasonSource": "llm" if llm_reason else "rules",
        "score": round(candidate.score, 4),
    }


def rule_reason(event: dict, matched: dict, query: str | None) -> str:
    """Np. "Muzyka, koncert · bezpłatne · w Twojej dzielnicy · wieczorem"."""
    parts = []
    topic = matched.get("themes", [])[:1] + [f.lower() for f in matched.get("formats", [])[:1]]
    if topic:
        parts.append(", ".join(topic))
    if (event.get("tags") or {}).get("cost") == "Bezpłatne":
        parts.append("bezpłatne")
    if matched.get("district") == ["home"]:
        parts.append("w Twojej dzielnicy")
    elif matched.get("district") == ["near"] and event.get("district"):
        parts.append(f"niedaleko – {event['district']}")
    if matched.get("time_of_day"):
        parts.append(_TIME_OF_DAY.get(matched["time_of_day"][0], matched["time_of_day"][0]))
    occasion = next((_OCCASION[o] for o in matched.get("occasion", []) if o in _OCCASION), None)
    if occasion:
        parts.append(occasion)
    if "Wstęp wolny" in matched.get("registration", []):
        parts.append("bez zapisów")
    if matched.get("accessibility"):
        parts.append("dostępność: " + matched["accessibility"][0].lower())
    if not parts:
        return f"Pasuje do wyszukiwania „{query}”" if query else "Podobne do Twoich zainteresowań"
    text = " · ".join(parts[:4])
    return text[0].upper() + text[1:]

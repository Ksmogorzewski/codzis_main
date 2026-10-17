#!/usr/bin/env python3
"""
Prompt builder — turns a chunk + dimensions into messages for DeepSeekClient.

The taxonomy is multi-dimensional: each event gets values across several
dimensions (theme, age bracket, format, cost, mode). Swap DIMENSIONS below for
the final category list from the team.

    from tagger import build_messages
    messages = build_messages(chunk)
"""

import json

# --------------------------------------------------------------------------- #
# TAXONOMY — multi-dimensional. Each dimension:
#   single  : True => exactly one value (parser collapses it to a string)
#   max     : max values allowed (multi-value dimensions)
#   options : the closed list of allowed values
# --------------------------------------------------------------------------- #
DIMENSIONS = {
    "theme": {
        "single": False,
        "max": 2,
        "options": [
            "Teatr i performans",
            "Muzyka",
            "Film i kino",
            "Sztuki wizualne i wystawy",
            "Literatura",
            "Muzea i dziedzictwo",
            "Sport",
            "Rekreacja i fitness",
            "Edukacja i warsztaty",
            "Nauka i technologia",
            "Biznes i kariera",
            "Zdrowie i wellness",
            "Kulinaria",
            "Moda i design",
            "Społeczność i wolontariat",
            "Sprawy miejskie i polityka lokalna",
            "Bezpieczeństwo",
            "Ekologia i środowisko",
            "Historia",
            "Turystyka i spacery",
            "Architektura i urbanistyka",
            "Święta i festiwale",
            "Inne",
        ],
    },
    "audience": {
        "single": True,
        "max": 1,
        "options": [
            "Dzieci (0-12)",
            "Młodzież (13-17)",
            "Dorośli (18-64)",
            "Seniorzy (65+)",
            "Rodziny / wszystkie grupy",
        ],
    },
    "format": {
        "single": False,
        "max": 2,
        "options": [
            "Warsztat",
            "Kurs / szkolenie",
            "Wykład / prelekcja",
            "Koncert",
            "Spektakl",
            "Wystawa",
            "Pokaz filmowy",
            "Spotkanie / dyskusja",
            "Festyn / festiwal / jarmark",
            "Spacer / wycieczka",
            "Zawody / turniej",
            "Trening / zajęcia ruchowe",
            "Konferencja",
            "Targi",
            "Zabawa / potańcówka",
        ],
    },
    "cost": {
        "single": True,
        "max": 1,
        "options": ["Bezpłatne", "Płatne", "Nieznane"],
    },
    "mode": {
        "single": True,
        "max": 1,
        "options": ["Stacjonarne", "Online", "Hybrydowe"],
    },
}

DIMENSION_LABELS = {
    "theme": "temat (what the event is about)",
    "audience": "grupa wiekowa (age bracket)",
    "format": "format (how the event is delivered)",
    "cost": "koszt (cost)",
    "mode": "tryb (in-person / online)",
}


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #

def _dimension_block(key: str, spec: dict) -> str:
    howmany = "exactly 1" if spec["single"] else f"1-{spec['max']}"
    options = "\n".join(f"  - {o}" for o in spec["options"])
    label = DIMENSION_LABELS.get(key, key)
    return f"{key} — {label} (choose {howmany}):\n{options}"


def build_system_prompt(dimensions: dict | None = None) -> str:
    dimensions = dimensions or DIMENSIONS
    blocks = "\n\n".join(_dimension_block(k, s) for k, s in dimensions.items())
    keys = ", ".join(dimensions)
    example_in = ('[{"id": "abc123", "title": "Koncert jazzowy w parku", "lead": "", '
                  '"description": "Wieczorny koncert na świeżym powietrzu, wstęp wolny.", '
                  '"categories": ["Kultura"]}]')
    example_out = ('{"abc123": {"theme": ["Muzyka"], "audience": ["Dorośli (18-64)"], '
                   '"format": ["Koncert"], "cost": ["Bezpłatne"], "mode": ["Stacjonarne"]}}')
    return f"""You are an event tagging assistant. For each Warsaw city event, assign values across the dimensions below. Use ONLY the allowed values listed for each dimension.

{blocks}

Output rules:
1. Output ONLY a valid JSON object. No markdown fences, no prose, no explanations.
2. Use each event's "id" as the key in the output object.
3. Each value is an object with keys: {keys}.
4. Every dimension value is an array of strings, sized as specified per dimension.
5. The input "categories" field holds the event's existing tags — treat them as hints only.
6. Do not omit any event. Every input event id must appear in the output.

Example:
Input:
{example_in}
Output:
{example_out}"""


def build_user_message(chunk: list[dict]) -> str:
    """Serialize a chunk of event records as compact JSON."""
    return json.dumps(chunk, ensure_ascii=False)


def build_messages(chunk: list[dict], dimensions: dict | None = None) -> list[dict]:
    """Return the full messages list for one chunk."""
    return [
        {"role": "system", "content": build_system_prompt(dimensions)},
        {"role": "user", "content": build_user_message(chunk)},
    ]

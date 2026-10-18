"""Mapa kategorii Sport / Kultura / Rekreacja: src/client_api/events.py i src/frontend/client/lib/categories.ts.

Obie strony dzielą wydarzenia po tagach taggera (tagger/prompt.py). Literówka albo zmiana nazwy tagu
w taksonomii po cichu przerzuciłaby wydarzenia do „Rekreacji” - te testy to wyłapują.
"""

import re

import pytest

from tests.support import CLIENT_API_DIR, REPO, load_lambda, taxonomy

FRONT_CATEGORIES = REPO / "src" / "frontend" / "client" / "lib" / "categories.ts"

# nazwa listy -> wymiar taksonomii, z którego pochodzą jej wartości
LISTS = {"SPORT_THEMES": "theme", "SPORT_FORMATS": "format", "CULTURE_THEMES": "theme"}


@pytest.fixture(scope="module")
def ev():
    return load_lambda(CLIENT_API_DIR, "events")


def front_list(name: str) -> set[str]:
    """`const NAME = ["a", "b", ...];` z categories.ts -> {"a", "b", ...}."""
    source = FRONT_CATEGORIES.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = \[(.*?)\];", source, re.DOTALL)
    assert match, f"Brak listy {name} w {FRONT_CATEGORIES.name}"
    return set(re.findall(r'"([^"]*)"', match.group(1)))


@pytest.mark.parametrize(("name", "dimension"), LISTS.items())
def test_backend_categories_exist_in_taxonomy(ev, name, dimension):
    options = set(taxonomy()[dimension])
    assert getattr(ev, name) <= options, f"{name}: spoza taksonomii {getattr(ev, name) - options}"


@pytest.mark.parametrize("name", LISTS)
def test_front_categories_match_backend(ev, name):
    assert front_list(name) == getattr(ev, name)

"""Kontekst rekomendacji z profilu onboardingu (src/recommender_api/user_context.py).

Bez frazy zestaw układa profil (twarde filtry z onboardingu obowiązują); z frazą
szukamy w całej Warszawie, a preferencje zostają tylko miękkimi podbiciami.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "recommender_api"))

from user_context import AREAS, build_context  # noqa: E402

WARSAW = ZoneInfo("Europe/Warsaw")
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=WARSAW)
SPAN = (date(2026, 10, 19), date(2026, 10, 19))

PREFS = {
    "district": "Mokotów",
    "travelRange": "local",
    "cost": "Bezpłatne",
    "mode": "Stacjonarne",
    "audience": ["Dorośli (18-64)"],
    "maxPrice": 50,
    "themes": ["Muzyka"],
    "formats": ["Koncert"],
    "interests": ["jazz"],
    "occasion": ["Na randkę"],
    "timeOfDay": ["wieczór"],
}


def test_bez_frazy_twarde_filtry_z_profilu_obowiazuja():
    ctx = build_context(PREFS, "profil", SPAN, "", NOW, "local")
    assert ctx["query"] is None
    assert ctx["district"] == ["Mokotów"]
    assert ctx["cost"] == "Bezpłatne"
    assert ctx["mode"] == "Stacjonarne"
    assert ctx["audience"] == ["Dorośli (18-64)"]
    assert ctx["max_price"] == 50.0
    assert ctx["interests"] == ["Muzyka", "Koncert", "jazz"]
    assert ctx["themes"] == ["Muzyka"]


@pytest.mark.parametrize("area", AREAS)
def test_fraza_szuka_w_calej_warszawie_bez_twardych_filtrow(area):
    ctx = build_context(PREFS, None, SPAN, "koncert jazzowy", NOW, area)
    assert ctx["query"] == "koncert jazzowy"
    assert ctx["district"] is None
    assert ctx["cost"] is None
    assert ctx["mode"] is None
    assert ctx["audience"] is None
    assert ctx["max_price"] is None


def test_fraza_zachowuje_okno_czasowe_i_miekkie_preferencje():
    ctx = build_context(PREFS, None, SPAN, "jazz", NOW, "local")
    # okno czasowe to jawny wybór użytkownika, nie ustawienie z onboardingu
    assert ctx["date_from"] == "2026-10-19"
    assert ctx["date_to"] == "2026-10-19"
    # miękkie preferencje zostają jako remisowe podbicia, ale tematy nie przebijają frazy
    assert ctx["occasion"] == ["Na randkę"]
    assert ctx["time_of_day"] == ["wieczór"]
    assert ctx["home_district"] == "Mokotów"
    assert ctx["interests"] == []
    assert ctx["themes"] == []
    assert ctx["formats"] == []

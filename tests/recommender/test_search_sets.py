"""Wspólne zestawy frazy (src/recommender_api/handler.py): wyszukiwanie liczy się raz na dzielnicę.

Prawdziwy handler rekomendera na atrapie DynamoDB (moto) i atrapie modelu (FakeEmbeddingModel) - bez torcha
i bez wywołań DeepSeek (klient LLM wyłączony albo podmieniony).
"""

from __future__ import annotations

import importlib.util
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import boto3
import pytest
from moto import mock_aws

import tests.support  # noqa: F401  (fałszywe dane AWS - testy nie mogą trafić do prawdziwego konta)
from tests.recommender.conftest import FakeEmbeddingModel, make_event

API_DIR = Path(__file__).resolve().parents[2] / "src" / "recommender_api"
WARSAW = ZoneInfo("Europe/Warsaw")
QUERY = "koncert jazzowy"

ALA = {"district": "Mokotów", "travelRange": "local", "accessibility": ["Tłumaczenie na PJM"],
       "occasion": ["Na randkę"], "themes": ["Muzyka"]}
OLA = {"district": "Mokotów", "travelRange": "city", "timeOfDay": ["rano"], "cost": ["Bezpłatne"]}
EWA = {"district": "Wola", "travelRange": "nearby"}


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("USERS_TABLE", "test-users")
    monkeypatch.setenv("RESULTS_TABLE", "test-recommendations")
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "index.npz"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")  # nie sięgamy po prawdziwy klucz z .env
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.syspath_prepend(str(API_DIR))
    with mock_aws():
        dynamodb = boto3.resource("dynamodb")
        dynamodb.create_table(
            TableName="test-users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamodb.create_table(
            TableName="test-recommendations",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}, {"AttributeName": "setKey", "KeyType": "RANGE"}],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "setKey", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        users = dynamodb.Table("test-users")
        for user_id, prefs in (("u-ala", ALA), ("u-ola", OLA), ("u-ewa", EWA)):
            users.put_item(Item={"userId": user_id, "preferences": prefs, "ragProfile": f"profil {user_id} | jazz"})

        spec = importlib.util.spec_from_file_location("recommender_api_handler", API_DIR / "handler.py")
        handler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(handler)

        tomorrow = (datetime.now(WARSAW) + timedelta(days=1)).date().isoformat()
        at = {"start": f"{tomorrow}T18:00:00", "end": f"{tomorrow}T20:00:00"}
        events = [
            make_event("jazz-mok", "Koncert jazzowy", lead="Jazz na żywo.", district="Mokotów", **at,
                       tags={"theme": ["Jazz"], "format": ["Koncert"], "cost": "Bezpłatne"}),
            # ten sam tekst, inna dzielnica: kolejność rozstrzyga podbicie „blisko domu” (dzielnica w kluczu zestawu)
            make_event("jazz-wola", "Koncert jazzowy", lead="Jazz na żywo.", district="Wola", **at,
                       tags={"theme": ["Jazz"], "format": ["Koncert"], "cost": "Bezpłatne"}),
            make_event("rock", "Koncert rockowy", lead="Głośny koncert.", district="Praga-Południe", **at,
                       tags={"theme": ["Rock"], "format": ["Koncert"], "cost": "Płatne"}),
            make_event("kino", "Kino plenerowe", lead="Film pod gwiazdami.", district="Śródmieście", **at,
                       tags={"theme": ["Film i kino"], "format": ["Pokaz filmowy"], "cost": "Bezpłatne"}),
        ]
        engine = handler.Recommender(events, model=FakeEmbeddingModel())
        engine.client = None  # bez LLM, o ile test go nie podmieni
        monkeypatch.setattr(handler, "_engine", engine)
        monkeypatch.setattr(handler, "_checked_at", time.monotonic())
        # liczenie „w tle” od razu, z tym samym payloadem co asynchroniczne wywołanie Lambdy (bez wyścigu z asercjami)
        monkeypatch.setattr(
            handler,
            "_start_compute",
            lambda owner, key, fingerprint, job: handler.handler({"action": "compute", "userId": owner, **job}, None),
        )

        computed = []
        real_compute = handler.compute

        def counting_compute(engine, prefs, rag_profile, *args):
            computed.append((prefs, rag_profile))
            return real_compute(engine, prefs, rag_profile, *args)

        monkeypatch.setattr(handler, "compute", counting_compute)
        yield handler, computed, dynamodb.Table("test-recommendations")
    sys.modules.pop("recommender_api_handler", None)


def search(handler, user_id, query=QUERY, when="tomorrow"):
    return handler.get_recommendations(user_id, {"when": when, "q": query})


def owners(table):
    return sorted({item["userId"] for item in table.scan()["Items"]})


def test_phrase_is_computed_once_per_district(api):
    handler, computed, table = api
    ala = search(handler, "u-ala")
    assert ala and ala["items"]
    assert ala["items"][0]["id"] == "jazz-mok"  # fraza + dzielnica: jazz blisko domu pierwszy
    n = len(computed)

    ola = search(handler, "u-ola", "Koncert  JAZZOWY")  # inna osoba z Mokotowa, fraza wpisana inaczej

    assert len(computed) == n  # bez liczenia: gotowy wspólny zestaw
    assert ola["cached"] is True
    assert [c["id"] for c in ola["items"]] == [c["id"] for c in ala["items"]]
    assert ola["query"] == "Koncert JAZZOWY"  # „dla „…”” pokazuje frazę tej osoby
    assert owners(table) == ["search#Mokotów"]


def test_other_district_has_own_shared_set(api):
    handler, computed, table = api
    search(handler, "u-ala")
    n = len(computed)

    ewa = search(handler, "u-ewa")

    assert len(computed) > n
    assert ewa["items"][0]["id"] == "jazz-wola"
    assert owners(table) == ["search#Mokotów", "search#Wola"]


def test_sets_without_phrase_stay_personal(api):
    handler, computed, table = api
    handler.get_recommendations("u-ala", {"when": "tomorrow"})
    handler.get_recommendations("u-ola", {"when": "tomorrow"})
    assert owners(table) == ["u-ala", "u-ola"]
    assert {rag for _, rag in computed} == {"profil u-ala | jazz", "profil u-ola | jazz"}


def test_shared_set_uses_no_profile_data(api):
    handler, computed, _ = api
    search(handler, "u-ala")
    assert computed and all(prefs == {"district": "Mokotów"} and rag is None for prefs, rag in computed)


def test_ai_phase_of_shared_set_gets_no_profile(api, monkeypatch):
    handler, _, table = api
    seen = []
    engine = handler._engine
    monkeypatch.setattr(handler, "LLM_ENABLED", True)
    engine.client = object()  # „jest LLM” - same wywołania podmienione niżej
    monkeypatch.setattr(engine, "expand", lambda context: seen.append(("expand", context)) or context)
    monkeypatch.setattr(engine, "rerank", lambda context, pool: seen.append(("rerank", context)) or pool)

    search(handler, "u-ala")

    assert [step for step, _ in seen] == ["expand", "rerank"]
    for _, context in seen:
        assert context["query"] == QUERY
        assert context["profile"] is None
        assert context["home_district"] == "Mokotów"
        assert context["accessibility"] == [] and context["occasion"] == [] and context["themes"] == []
    stored = [i for i in table.scan()["Items"] if i["userId"] == "search#Mokotów"]
    assert len(stored) == 1 and '"refining": false' in stored[0]["body"]


def test_background_compute_of_shared_set_needs_no_user_record(api):
    handler, computed, table = api
    tomorrow = (datetime.now(WARSAW) + timedelta(days=1)).date().isoformat()
    owner = "search#Mokotów"
    key = handler.set_key("tomorrow", (datetime.fromisoformat(tomorrow).date(),) * 2, QUERY, 16)
    fingerprint = handler.prefs_hash({"district": "Mokotów"}, None)
    assert handler.results.claim(owner, key, fingerprint, datetime.now(WARSAW))

    done = handler.compute_set({"action": "compute", "userId": owner, "shared": True, "district": "Mokotów",
                                "when": "tomorrow", "from": tomorrow, "to": tomorrow, "q": QUERY, "limit": 16})

    assert done == {"computed": 1}
    assert computed == [({"district": "Mokotów"}, None)]
    assert owners(table) == [owner]


def test_log_key_hides_phrase(api):
    handler, _, _ = api
    assert handler._log_key("date#2026-10-30#2026-10-30#16#koncert #jazz") == "date#2026-10-30#2026-10-30#16#<fraza>"
    assert handler._log_key("today#2026-10-17#2026-10-17#16#") == "today#2026-10-17#2026-10-17#16#"

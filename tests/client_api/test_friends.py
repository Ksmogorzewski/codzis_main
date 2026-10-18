"""Model znajomych (src/client_api/friends.py) na atrapie DynamoDB: kod, zaproszenia, akceptacja, limity."""

import re

import pytest
from boto3.dynamodb.conditions import Key

from codzis_common.http import ApiError

NOW = 1_792_300_000  # 2026-10-18, sekundy epoki
ALA, OLA, KUBA = "user-ala", "user-ola", "user-kuba"
NAMES = {ALA: "Ala", OLA: "Ola", KUBA: "Kuba"}
UNKNOWN = "WAW-222222"  # poprawny format, nikt go nie ma


def code_of(friends, user_id):
    return friends.get_or_create_code(user_id, NAMES[user_id])


def invite(friends, user_id, code, now=NOW):
    return friends.invite(user_id, NAMES[user_id], code, now)


def befriend(friends, a, b):
    invite(friends, a, code_of(friends, b))
    friends.accept(b, NAMES[b], a, NOW)


def sort_keys(table, user_id):
    items = table.query(KeyConditionExpression=Key("userId").eq(user_id))["Items"]
    return sorted(item["sk"] for item in items)


def error(fn, *args):
    with pytest.raises(ApiError) as caught:
        fn(*args)
    return caught.value


def test_normalize_code_variants(friends):
    for raw in ["waw 7k2p9x", "7K2P9X", " WAW-7K2P9X ", "waw-7k2-p9x"]:
        assert friends.normalize_code(raw) == "WAW-7K2P9X"
    for raw in ["WAW-7K2", "WAW-0OIL00", "", "WAW-7K2P9XY"]:
        assert friends.normalize_code(raw) is None


def test_code_is_stable_and_regenerates(friends):
    first = code_of(friends, ALA)
    assert re.fullmatch(r"WAW-[23456789ABCDEFGHJKLMNPQRSTUVWXYZ]{6}", first)
    assert code_of(friends, ALA) == first
    assert friends.preview(OLA, first, NOW) == {"userId": ALA, "name": "Ala"}

    second = friends.regenerate_code(ALA, "Ala")
    assert second != first
    assert code_of(friends, ALA) == second
    assert error(friends.preview, OLA, first, NOW).status == 404
    assert friends.preview(OLA, second.lower(), NOW) == {"userId": ALA, "name": "Ala"}
    assert friends.overview(ALA, NOW)["code"] == second


def test_code_collision_retries(friends, monkeypatch):
    taken = code_of(friends, ALA)
    drawn = iter([taken, "WAW-333333"])
    monkeypatch.setattr(friends, "_random_code", lambda: next(drawn))

    assert code_of(friends, OLA) == "WAW-333333"
    assert friends.preview(KUBA, taken, NOW)["userId"] == ALA  # cudzy kod nienaruszony


def test_invite_then_accept_is_mutual(friends):
    assert invite(friends, OLA, code_of(friends, ALA)) == {"status": "pending", "userId": ALA, "name": "Ala"}
    assert friends.overview(ALA, NOW)["incoming"] == [{"userId": OLA, "name": "Ola", "createdAt": ANY_ISO}]
    assert friends.overview(OLA, NOW)["outgoing"] == [{"userId": ALA, "name": "Ala", "createdAt": ANY_ISO}]
    assert friends.friend_ids(ALA) == {}  # bez akceptacji nic nie widać

    assert friends.accept(ALA, "Ala", OLA, NOW) == {"status": "friends"}

    ala, ola = friends.overview(ALA, NOW), friends.overview(OLA, NOW)
    assert ala["friends"] == [{"userId": OLA, "name": "Ola", "since": ANY_ISO}]
    assert ola["friends"] == [{"userId": ALA, "name": "Ala", "since": ANY_ISO}]
    assert ala["incoming"] == ala["outgoing"] == ola["incoming"] == ola["outgoing"] == []
    assert friends.friend_ids(ALA) == {OLA: "Ola"}
    assert friends.friend_ids(OLA) == {ALA: "Ala"}


def test_invite_existing_states(friends, friends_table):
    # już znajomi -> "friends", bez nowych rekordów
    befriend(friends, ALA, OLA)
    before = (sort_keys(friends_table, ALA), sort_keys(friends_table, OLA))
    assert invite(friends, ALA, code_of(friends, OLA)) == {"status": "friends", "userId": OLA, "name": "Ola"}
    assert (sort_keys(friends_table, ALA), sort_keys(friends_table, OLA)) == before

    # drugie zaproszenie -> nadal jedna para out/in
    kuba_code = code_of(friends, KUBA)
    invite(friends, ALA, kuba_code)
    assert invite(friends, ALA, kuba_code)["status"] == "pending"
    assert [sk for sk in sort_keys(friends_table, ALA) if sk.startswith("out#")] == [f"out#{KUBA}"]
    assert [sk for sk in sort_keys(friends_table, KUBA) if sk.startswith("in#")] == [f"in#{ALA}"]

    # Kuba wpisuje kod Ali, która już go zaprosiła -> od razu znajomi, zaproszenia znikają
    assert invite(friends, KUBA, code_of(friends, ALA)) == {"status": "friends", "userId": ALA, "name": "Ala"}
    assert f"out#{KUBA}" not in sort_keys(friends_table, ALA)
    assert f"in#{ALA}" not in sort_keys(friends_table, KUBA)
    assert friends.friend_ids(ALA) == {OLA: "Ola", KUBA: "Kuba"}
    assert friends.friend_ids(KUBA) == {ALA: "Ala"}


def test_invite_self_400(friends):
    code = code_of(friends, ALA)
    assert error(invite, friends, ALA, code).status == 400
    assert error(friends.preview, ALA, code, NOW).body == {"error": "Nie możesz dodać siebie"}
    assert friends.overview(ALA, NOW)["outgoing"] == []


def test_decline_is_silent(friends):
    invite(friends, OLA, code_of(friends, ALA))
    friends.decline(ALA, OLA)

    assert friends.overview(ALA, NOW)["incoming"] == []
    assert [r["userId"] for r in friends.overview(OLA, NOW)["outgoing"]] == [ALA]  # zapraszający nie wie
    assert error(friends.accept, ALA, "Ala", OLA, NOW).status == 404
    assert friends.friend_ids(OLA) == {}


def test_remove_both_sides(friends):
    befriend(friends, ALA, OLA)
    friends.remove(OLA, ALA)

    assert friends.friend_ids(ALA) == friends.friend_ids(OLA) == {}
    assert friends.overview(ALA, NOW)["friends"] == []
    friends.remove(OLA, ALA)  # ponownie: bez błędu
    # ponowne zaproszenie po usunięciu jest dozwolone
    assert invite(friends, OLA, code_of(friends, ALA))["status"] == "pending"


def fill_friends(friends_table, user_id, count=50):
    for i in range(count):
        friends_table.put_item(Item={"userId": user_id, "sk": f"friend#seed-{i}", "name": f"Osoba {i}", "since": "x"})


def test_friend_limit(friends, friends_table):
    fill_friends(friends_table, ALA)

    # akceptacja zaproszenia
    invite(friends, OLA, code_of(friends, ALA))
    err = error(friends.accept, ALA, "Ala", OLA, NOW)
    assert (err.status, err.body) == (409, {"error": "Masz już 50 znajomych", "code": "friend_limit"})
    assert OLA not in friends.friend_ids(ALA)
    assert [r["userId"] for r in friends.overview(ALA, NOW)["incoming"]] == [OLA]  # bez częściowego zapisu

    # automatyczna akceptacja (Kuba zaprosił Alę, Ala wpisuje kod Kuby)
    invite(friends, KUBA, code_of(friends, ALA))
    err = error(invite, friends, ALA, code_of(friends, KUBA))
    assert (err.status, err.body["code"]) == (409, "friend_limit")
    assert friends.friend_ids(KUBA) == {}

    # limit drugiej strony: Kuba akceptuje zaproszenie od Ali, która ma już 50
    friends_table.put_item(
        Item={"userId": KUBA, "sk": f"in#{ALA}", "name": "Ala", "createdAt": "x", "expiresAt": NOW + 60}
    )
    assert error(friends.accept, KUBA, "Kuba", ALA, NOW).body["code"] == "friend_limit"


def test_rate_limit_wrong_codes(friends):
    ola_code = code_of(friends, OLA)
    for _ in range(5):
        assert error(friends.preview, ALA, UNKNOWN, NOW).status == 404
    assert friends.preview(ALA, ola_code, NOW)["userId"] == OLA  # dobre kody nie liczą się
    for _ in range(4):
        assert error(invite, friends, ALA, UNKNOWN).status == 404
    assert error(invite, friends, ALA, "zły kod").status == 404  # 10. zła próba

    err = error(friends.preview, ALA, UNKNOWN, NOW + 1)
    assert (err.status, err.body["error"]) == (429, "Za dużo prób. Spróbuj za godzinę.")
    assert error(invite, friends, ALA, ola_code, NOW + 2).status == 429  # zablokowane także dobre
    assert error(friends.preview, KUBA, UNKNOWN, NOW).status == 404  # inni użytkownicy bez zmian

    # po godzinie licznik od nowa
    assert error(friends.preview, ALA, UNKNOWN, NOW + 3601).status == 404
    assert friends.preview(ALA, ola_code, NOW + 3602)["userId"] == OLA


def test_pending_survive_regeneration(friends):
    invite(friends, OLA, code_of(friends, ALA))
    friends.regenerate_code(ALA, "Ala")

    assert [r["userId"] for r in friends.overview(ALA, NOW)["incoming"]] == [OLA]
    assert friends.accept(ALA, "Ala", OLA, NOW) == {"status": "friends"}
    assert friends.friend_ids(OLA) == {ALA: "Ala"}


def test_expired_invites_are_hidden(friends):
    invite(friends, OLA, code_of(friends, ALA))
    later = NOW + 31 * 24 * 3600
    assert friends.overview(ALA, later)["incoming"] == []
    assert friends.overview(OLA, later)["outgoing"] == []
    assert error(friends.accept, ALA, "Ala", OLA, later).status == 404


class _AnyIso:
    """Dowolny znacznik czasu ISO 8601 (UTC)."""

    def __eq__(self, other):
        return isinstance(other, str) and other.endswith("+00:00")

    def __repr__(self):
        return "<ISO>"


ANY_ISO = _AnyIso()

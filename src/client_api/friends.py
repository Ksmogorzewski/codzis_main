"""Znajomi: kod do podyktowania / QR, zaproszenia z akceptacją, obustronna znajomość (DynamoDB).

Tabela codzis-friends (infra/community.tf), jedyny zapisujący: client-api. PK `userId`, SK `sk`,
TTL `expiresAt` (sekundy epoki). TTL usuwa rekordy z opóźnieniem, więc wygasłe zaproszenia
i okna limitu pomijamy też przy odczycie.

    userId            sk              pola
    <sub>             code            code                                  mój aktualny kod
    code#WAW-XXXXXX   owner           owner (sub), ownerName                kod -> właściciel (get po kluczu)
    <sub>             friend#<other>  name (imię drugiej osoby), since      znajomość (zawsze para rekordów)
    <sub>             in#<from>       name, createdAt, expiresAt (+30 dni)  zaproszenie do mnie
    <sub>             out#<to>        name, createdAt, expiresAt (+30 dni)  moje zaproszenie (para do in#)
    <sub>             limit           attempts (ADD), expiresAt (+1 h)      licznik złych kodów w oknie

Imiona (`name`, `ownerName`) to kopie imienia z chwili akcji - imienia się nie zmienia, więc się nie
starzeją; zapisuje je tylko ten moduł. Rekordy wielu osób zmieniamy jedną transakcją
(TransactWriteItems): zaproszenie = out + in, akceptacja = usuń in/out + dwa friend#,
usunięcie = dwa friend#, nowy kod = usuń stary code# + dodaj nowy (warunek: kod wolny).

Zasady: bez akceptacji nikt nic nie widzi (friend_ids czyta tylko friend#); odrzucenie jest ciche
(usuwa tylko moje in#, zapraszający widzi "oczekuje" do wygaśnięcia); nowy kod nie rusza
oczekujących zaproszeń ani znajomych (są po sub, nie po kodzie). Czasy: `now` w sekundach epoki,
`createdAt`/`since` jako ISO 8601 UTC.
"""

import os
import re
import secrets
from datetime import UTC, datetime
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from codzis_common.http import ApiError

FRIENDS_TABLE = os.environ["FRIENDS_TABLE"]

PREFIX = "WAW"
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # bez 0/O/1/I - łatwe do podyktowania
CODE_LENGTH = 6
CODE_RETRIES = 5
MAX_FRIENDS = 50
MAX_WRONG_CODES = 10
LIMIT_WINDOW_S = 3600
PENDING_TTL_S = 30 * 24 * 3600

table = boto3.resource("dynamodb").Table(FRIENDS_TABLE)
ddb = table.meta.client  # klient zasobu: transakcje przyjmują zwykłe typy Pythona

_CODE_BODY = re.compile(f"[{ALPHABET}]{{{CODE_LENGTH}}}")


# --------------------------------------------------------------------------- kod


def normalize_code(raw: str) -> str | None:
    """Kod wpisany "byle jak" (`waw 7k2p9x`, `7K2P9X`, ` WAW-7K2P9X `) -> `WAW-7K2P9X`; zły format -> None."""
    body = re.sub(r"[\s-]", "", str(raw or "")).upper().removeprefix(PREFIX)
    return f"{PREFIX}-{body}" if _CODE_BODY.fullmatch(body) else None


def get_or_create_code(user_id: str, name: str) -> str:
    """Mój kod; pierwszy raz losuje nowy (`name` = moje imię, pokazywane temu, kto wpisze kod)."""
    return _current_code(user_id) or _set_code(user_id, name, None)


def regenerate_code(user_id: str, name: str) -> str:
    """Nowy kod; stary przestaje działać, oczekujące zaproszenia i znajomi zostają."""
    return _set_code(user_id, name, _current_code(user_id))


def _current_code(user_id: str) -> str | None:
    item = _get(user_id, "code")
    return item["code"] if item else None


def _random_code() -> str:
    while True:
        body = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        if not body.startswith(PREFIX):  # "WAW..." bez myślnika dałoby się pomylić z prefiksem
            return f"{PREFIX}-{body}"


def _set_code(user_id: str, name: str, old: str | None) -> str:
    """Zapisuje nowy kod (kolizja z cudzym kodem -> losuje ponownie)."""
    for _ in range(CODE_RETRIES):
        code = _random_code()
        mine: dict[str, Any] = {"TableName": FRIENDS_TABLE, "Item": {"userId": user_id, "sk": "code", "code": code}}
        if old:
            mine |= {"ConditionExpression": "code = :old", "ExpressionAttributeValues": {":old": old}}
        else:
            mine["ConditionExpression"] = "attribute_not_exists(userId)"
        items = [
            _put({"userId": f"code#{code}", "sk": "owner", "owner": user_id, "ownerName": name}, unique=True),
            {"Put": mine},
        ]
        if old:
            items.append({"Delete": {"TableName": FRIENDS_TABLE, "Key": _key(f"code#{old}", "owner")}})
        failed = _transact(items)
        if not failed:
            return code
        if failed[1]:  # mój kod zmienił się równolegle (drugie żądanie) - oddajemy aktualny
            return _current_code(user_id) or code
    raise ApiError(503, "Nie udało się utworzyć kodu, spróbuj ponownie")


# --------------------------------------------------------------------------- zaproszenia


def preview(user_id: str, code: str, now: int) -> dict:
    """Do kogo należy kod: {"userId", "name"} (zły kod liczy się do limitu prób)."""
    return _resolve(user_id, code, now)


def invite(user_id: str, name: str, code: str, now: int) -> dict:
    """Zaproszenie po kodzie -> {"status": "pending" | "friends", "userId", "name"}.

    Już znajomi -> "friends" bez zmian; ta osoba już mnie zaprosiła -> automatyczna akceptacja;
    ponowne zaproszenie nadpisuje parę out/in (bez duplikatów)."""
    other = _resolve(user_id, code, now)
    other_id = other["userId"]
    if _get(user_id, f"friend#{other_id}"):
        return {"status": "friends", **other}
    if _active(_get(user_id, f"in#{other_id}"), now):
        accept(user_id, name, other_id, now)
        return {"status": "friends", **other}
    _ensure_room(user_id, f"Masz już {MAX_FRIENDS} znajomych")
    pending = {"createdAt": _iso(now), "expiresAt": now + PENDING_TTL_S}
    _transact_or_fail(
        [
            _put({"userId": user_id, "sk": f"out#{other_id}", "name": other["name"]} | pending),
            _put({"userId": other_id, "sk": f"in#{user_id}", "name": name} | pending),
        ]
    )
    return {"status": "pending", **other}


def accept(user_id: str, name: str, from_id: str, now: int) -> dict:
    """Akceptacja zaproszenia od `from_id` -> {"status": "friends"} (obustronnie, jedną transakcją)."""
    request = _get(user_id, f"in#{from_id}")
    if request is None or not _active(request, now):
        if _get(user_id, f"friend#{from_id}"):
            return {"status": "friends"}  # już zaakceptowane (np. podwójne kliknięcie)
        raise ApiError(404, "Nie ma takiego zaproszenia")
    # Limit sprawdzamy przed transakcją: dwie równoczesne akceptacje mogą dać 51 (akceptowalne w MVP)
    _ensure_room(user_id, f"Masz już {MAX_FRIENDS} znajomych")
    _ensure_room(from_id, f"Ta osoba ma już {MAX_FRIENDS} znajomych")
    since = _iso(now)
    _transact_or_fail(
        [
            {
                "Delete": {
                    "TableName": FRIENDS_TABLE,
                    "Key": _key(user_id, f"in#{from_id}"),
                    "ConditionExpression": "attribute_exists(userId)",
                }
            },
            {"Delete": {"TableName": FRIENDS_TABLE, "Key": _key(from_id, f"out#{user_id}")}},
            _put({"userId": user_id, "sk": f"friend#{from_id}", "name": request.get("name") or "", "since": since}),
            _put({"userId": from_id, "sk": f"friend#{user_id}", "name": name, "since": since}),
        ]
    )
    return {"status": "friends"}


def decline(user_id: str, from_id: str) -> None:
    """Ciche odrzucenie: znika tylko u mnie (zapraszający widzi "oczekuje" do wygaśnięcia)."""
    table.delete_item(Key=_key(user_id, f"in#{from_id}"))


def remove(user_id: str, friend_id: str) -> None:
    """Usunięcie znajomości u obu stron (ponowne nic nie zmienia)."""
    if friend_id == user_id:  # ten sam klucz dwa razy w transakcji = błąd DynamoDB
        raise ApiError(400, "Nie możesz usunąć siebie")
    _transact_or_fail(
        [
            {"Delete": {"TableName": FRIENDS_TABLE, "Key": _key(user_id, f"friend#{friend_id}")}},
            {"Delete": {"TableName": FRIENDS_TABLE, "Key": _key(friend_id, f"friend#{user_id}")}},
        ]
    )


# --------------------------------------------------------------------------- odczyt


def overview(user_id: str, now: int) -> dict:
    """{"code", "friends": [{userId, name, since}], "incoming"/"outgoing": [{userId, name, createdAt}]}.

    Znajomi alfabetycznie, zaproszenia najnowsze najpierw, wygasłe pominięte."""
    result: dict[str, Any] = {"code": None, "friends": [], "incoming": [], "outgoing": []}
    for row in _rows(user_id):
        kind, _, other = row["sk"].partition("#")
        if row["sk"] == "code":
            result["code"] = row["code"]
        elif kind == "friend":
            result["friends"].append({"userId": other, "name": row.get("name") or "", "since": row.get("since")})
        elif kind in ("in", "out") and _active(row, now):
            pending = {"userId": other, "name": row.get("name") or "", "createdAt": row.get("createdAt")}
            result["incoming" if kind == "in" else "outgoing"].append(pending)
    result["friends"].sort(key=lambda f: (f["name"].casefold(), f["userId"]))
    for key in ("incoming", "outgoing"):
        result[key].sort(key=lambda r: str(r["createdAt"] or ""), reverse=True)
    return result


def friend_ids(user_id: str) -> dict[str, str]:
    """Moi znajomi (tylko zaakceptowani): id -> imię."""
    return {row["sk"].removeprefix("friend#"): row.get("name") or "" for row in _rows(user_id, "friend#")}


# --------------------------------------------------------------------------- limity


def _resolve(user_id: str, raw: str, now: int) -> dict:
    """Kod -> {"userId", "name"} właściciela. Zły kod -> 404 i +1 do limitu; za dużo złych -> 429."""
    _check_attempts(user_id, now)
    code = normalize_code(raw)
    item = _get(f"code#{code}", "owner") if code else None
    if not item:
        _count_wrong(user_id, now)
        raise ApiError(404, "Nie ma takiego kodu")
    if item["owner"] == user_id:
        raise ApiError(400, "Nie możesz dodać siebie")
    return {"userId": item["owner"], "name": item.get("ownerName") or ""}


def _check_attempts(user_id: str, now: int) -> None:
    item = _get(user_id, "limit") or {}
    if _active(item, now) and int(item.get("attempts", 0)) >= MAX_WRONG_CODES:
        raise ApiError(429, "Za dużo prób. Spróbuj za godzinę.", code="too_many_attempts")


def _count_wrong(user_id: str, now: int) -> None:
    """+1 w bieżącym oknie (ADD); brak okna albo wygasło -> nowe okno na godzinę."""
    try:
        table.update_item(
            Key=_key(user_id, "limit"),
            UpdateExpression="ADD attempts :one",
            ConditionExpression="expiresAt > :now",
            ExpressionAttributeValues={":one": 1, ":now": now},
        )
    except ddb.exceptions.ConditionalCheckFailedException:
        table.put_item(Item={"userId": user_id, "sk": "limit", "attempts": 1, "expiresAt": now + LIMIT_WINDOW_S})


def _ensure_room(user_id: str, message: str) -> None:
    count = table.query(
        KeyConditionExpression=Key("userId").eq(user_id) & Key("sk").begins_with("friend#"),
        Select="COUNT",
        ConsistentRead=True,
    )["Count"]
    if count >= MAX_FRIENDS:
        raise ApiError(409, message, code="friend_limit")


# --------------------------------------------------------------------------- DynamoDB


def _key(user_id: str, sk: str) -> dict:
    return {"userId": user_id, "sk": sk}


def _get(user_id: str, sk: str) -> dict | None:
    return table.get_item(Key=_key(user_id, sk), ConsistentRead=True).get("Item")


def _rows(user_id: str, prefix: str = "") -> list[dict]:
    condition = Key("userId").eq(user_id)
    if prefix:
        condition = condition & Key("sk").begins_with(prefix)
    params: dict[str, Any] = {"KeyConditionExpression": condition, "ConsistentRead": True}
    rows: list[dict] = []
    while True:
        page = table.query(**params)
        rows.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            return rows
        params["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def _put(item: dict, unique: bool = False) -> dict:
    put: dict[str, Any] = {"TableName": FRIENDS_TABLE, "Item": item}
    if unique:
        put["ConditionExpression"] = "attribute_not_exists(userId)"
    return {"Put": put}


def _transact(items: list[dict]) -> list[bool]:
    """[] = zapisano; inaczej lista "warunek niespełniony?" dla każdej pozycji. Inny konflikt -> 409."""
    try:
        ddb.transact_write_items(TransactItems=items)
        return []
    except ddb.exceptions.TransactionCanceledException as e:
        failed = [r.get("Code") == "ConditionalCheckFailed" for r in e.response.get("CancellationReasons", [])]
        if any(failed):
            return failed
        raise ApiError(409, "Konflikt zapisu, spróbuj ponownie", code="conflict") from e


def _transact_or_fail(items: list[dict]) -> None:
    if _transact(items):
        raise ApiError(409, "Stan zaproszenia zmienił się, odśwież listę", code="conflict")


def _active(item: dict | None, now: int) -> bool:
    return bool(item) and int((item or {}).get("expiresAt", 0)) > now


def _iso(now: int) -> str:
    return datetime.fromtimestamp(now, UTC).isoformat()

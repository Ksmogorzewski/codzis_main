"""Ekipy na wydarzenia i ich czaty (DynamoDB): zapisani łączą się w ekipy do 4 osób, każda ma własny czat.

Tabela codzis-crews (infra/community.tf), jedyny zapisujący: client-api. PK `eventId`, SK `sk`,
TTL `expiresAt` (sekundy epoki).

    eventId  sk                        pola
    <id>     crew#<nr>                 members {userId: {name, joinedAt}}, size, messages (licznik), last
                                       (ostatnia wiadomość do podglądu), closed?, createdAt, expiresAt
    <id>     member#<userId>           userId, crew (<nr>), joinedAt, read (ile wiadomości ekipy przeczytałem),
                                       lastSentAt (moja ostatnia wiadomość), expiresAt
    <id>     msg#<nr>#<sentAt>#<los>   kind, userId?, name?, text?, sentAt, expiresAt

<nr> = 001, 002…; sentAt = ISO 8601 UTC z milisekundami („…T18:00:00.123Z”), więc SK sortuje się po czasie.

Zapytania (po kluczu, bez scan):
  - moja ekipa: get member#<ja> + get crew#<nr>,
  - czat: query begins_with msg#<nr># (najnowsze), nowe od chwili X: BETWEEN msg#<nr>#<X> AND msg#<nr>#~,
  - dołączanie: query begins_with crew# (ekip na wydarzenie jest kilka),
  - plakietki: moje zapisy (attendance, GSI byUser) + BatchGet member#<ja> i crew#<nr>.

Dołączenie (pierwsze wejście na czat), wiadomość i wyjście (wypisanie z wydarzenia) to transakcje
z warunkami: równoczesne dołączenia nie przepełnią ekipy, a licznik `messages` zgadza się z wiadomościami.
Nieprzeczytane = crew.messages - member.read; moja wiadomość podbija oba liczniki, otwarty czat ustawia
read = messages. Pusta ekipa (wszyscy wyszli) jest zamknięta - nowi trafiają do innej albo nowej.

Wiadomości: kind "user" (tekst osoby) albo komunikaty Wodzireja z danych, bez LLM: "welcome" (nowa
ekipa), "joined" / "left" (kto), "full" (komplet). Tekst komunikatów oraz punkt i godzinę zbiórki składa
front z danych wydarzenia. Imiona (`name`) to kopie display_name („Ola K.”) z chwili akcji - imienia się
nie zmienia. Nowa osoba widzi całą dotychczasową rozmowę ekipy. Treści wiadomości nie logujemy.
TTL: 30 dni po końcu wydarzenia (expiresAt z taggera), a dla wydarzeń bez końca i minionych - 30 dni
od ostatniego zapisu.
"""

import os
import re
import secrets
import time
import unicodedata
import zlib
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from boto3.dynamodb.conditions import Key

from codzis_common.aws import AWS_CONFIG
from codzis_common.http import ApiError

CREWS_TABLE = os.environ["CREWS_TABLE"]

CREW_SIZE = 4
MAX_MESSAGE = 500  # znaków po oczyszczeniu
PREVIEW = 140  # znaków ostatniej wiadomości w podglądzie (zakładka „Twoje”)
PAGE = 200  # maks. wiadomości w jednej odpowiedzi
OVERLAP = timedelta(seconds=15)  # zapas przy ?after=: transakcja mogła się zapisać później niż jej sentAt
MIN_GAP = timedelta(seconds=1)  # najkrócej między moimi wiadomościami
RETENTION_S = 30 * 24 * 3600
JOIN_RETRIES = 5
BATCH_GET_MAX = 100  # limit BatchGetItem
ANONYMOUS = "Ktoś"

# Lodołamacz ekipy (stały dla ekipy, różne ekipy różne): pierwsza wiadomość osoby odblokowuje jej czat
ICEBREAKERS = [
    "Jaka jest Twoja ulubiona ulica lub budynek w Warszawie?",
    "Gdzie w Warszawie warto zabrać kogoś, kto jest tu pierwszy raz?",
    "Jakie wydarzenie w mieście najbardziej zapadło Ci w pamięć?",
    "Co najbardziej lubisz robić w Warszawie po pracy albo zajęciach?",
]

# Słowa zastrzeżone DynamoDB (size, last, read…) w wyrażeniach tylko przez nazwy zastępcze
RESERVED = ("members", "size", "messages", "last", "read", "closed")
# Znaki zmieniające kierunek tekstu - w czacie posłużyłyby do podszywania się pod inną treść
_BIDI = set("‪‫‬‭‮⁦⁧⁨⁩")

table = boto3.resource("dynamodb", config=AWS_CONFIG).Table(CREWS_TABLE)
ddb = table.meta.client  # klient zasobu: transakcje i batch przyjmują zwykłe typy Pythona


# --------------------------------------------------------------------------- czat


def open_chat(event_id: str, event: dict, user_id: str, name: str, after: datetime | None, now: datetime) -> dict:
    """Wejście na czat: moja ekipa (za pierwszym razem dołączam), wiadomości (najnowsze albo od `after`),
    wszystko przeczytane -> crew, capacity, members, messageCount, icebreaker, answered, messages, cursor."""
    ttl = expires_at(event, now)
    crew, member = _my_crew(event_id, user_id, name, now, ttl)
    nr = _nr(crew)
    rows = _messages(event_id, nr, after)
    count = _int(crew.get("messages"))
    if _int(member.get("read")) < count:
        _mark_read(event_id, user_id, count, ttl)
    seen = [rows[-1]["sentAt"]] if rows else []
    return _crew_view(crew, user_id) | {
        "icebreaker": icebreaker(event_id, nr),
        "answered": "lastSentAt" in member,
        "messages": [_message_view(row, user_id) for row in rows],
        # do następnego ?after= (z zapasem OVERLAP odpowiedź może zawierać też starsze, front odrzuca powtórki)
        "cursor": max([*seen, *([iso(after)] if after else [])], default=None),
    }


def send(event_id: str, event: dict, user_id: str, name: str, raw: object, now: datetime) -> dict:
    """Wiadomość do mojej ekipy -> {"message"}. Za szybko po poprzedniej (MIN_GAP) -> 429."""
    text = clean_message(raw)
    if not text or len(text) > MAX_MESSAGE:
        raise ApiError(400, f"Wiadomość musi mieć od 1 do {MAX_MESSAGE} znaków", fields=["text"])
    ttl = expires_at(event, now)
    crew, _ = _my_crew(event_id, user_id, name, now, ttl)
    nr = _nr(crew)
    message = _message(event_id, nr, "user", now, ttl, userId=user_id, name=name, text=text)
    failed = _transact(
        [
            _put(message),
            _update(
                event_id,
                f"crew#{nr}",
                "SET #last = :last, expiresAt = :ttl ADD #messages :one",
                "attribute_exists(#members.#me)",
                {":last": _preview(message), ":ttl": ttl, ":one": 1},
                {"#me": user_id},
            ),
            # moja wiadomość jest od razu przeczytana (read +1 razem z messages +1)
            _update(
                event_id,
                f"member#{user_id}",
                "SET lastSentAt = :now, expiresAt = :ttl ADD #read :one",
                "attribute_exists(sk) AND (attribute_not_exists(lastSentAt) OR lastSentAt < :gap)",
                {":now": message["sentAt"], ":ttl": ttl, ":one": 1, ":gap": iso(now - MIN_GAP)},
            ),
        ]
    )
    if failed:
        if failed[2] == "ConditionalCheckFailed" and _get(event_id, f"member#{user_id}"):
            raise ApiError(429, "Wysyłasz za szybko. Chwilę poczekaj.", code="too_fast")
        raise ApiError(409, "Skład ekipy właśnie się zmienił. Odśwież czat.", code="conflict")
    return {"message": _message_view(message, user_id)}


def leave(event_id: str, user_id: str, now: datetime) -> None:
    """Wypisanie z wydarzenia = wyjście z ekipy (moje wiadomości zostają w czacie); pusta ekipa się zamyka.

    Ponowne wywołanie nic nie zmienia."""
    member = _get(event_id, f"member#{user_id}")
    if not member:
        return
    nr = member["crew"]
    crew = _get(event_id, f"crew#{nr}") or {}
    me = (crew.get("members") or {}).get(user_id)
    if not me:
        table.delete_item(Key=_key(event_id, f"member#{user_id}"))
        return
    ttl = _int(crew.get("expiresAt")) or int(now.timestamp()) + RETENTION_S
    note = _message(event_id, nr, "left", now, ttl, userId=user_id, name=me.get("name"))
    values: dict[str, Any] = {":last": _preview(note), ":minus": -1, ":one": 1}
    close = ""
    if _int(crew.get("size")) <= 1:
        close, values[":true"] = ", #closed = :true", True
    _transact(
        [
            {"Delete": {"TableName": CREWS_TABLE, "Key": _key(event_id, f"member#{user_id}")}},
            _update(
                event_id,
                f"crew#{nr}",
                f"SET #last = :last{close} REMOVE #members.#me ADD #size :minus, #messages :one",
                "attribute_exists(#members.#me)",
                values,
                {"#me": user_id},
            ),
            _put(note),
        ]
    )  # warunek niespełniony = równoległe wyjście (druga karta) - nie ma już czego robić


def summaries(user_id: str, event_ids: list[str]) -> dict[str, dict]:
    """Moje ekipy na wydarzenia z listy: {eventId: crew, capacity, members, messageCount, unread, last}.

    Wydarzenia, na których czat jeszcze nie wszedłem (bez ekipy), pomijamy."""
    mine = _batch_get([_key(e, f"member#{user_id}") for e in dict.fromkeys(event_ids)])
    keys = [_key(m["eventId"], f"crew#{m['crew']}") for m in mine]
    crews = {(c["eventId"], c["sk"]): c for c in _batch_get(keys)}
    found: dict[str, dict] = {}
    for member in mine:
        crew = crews.get((member["eventId"], f"crew#{member['crew']}"))
        if not crew or user_id not in (crew.get("members") or {}):
            continue
        view = _crew_view(crew, user_id)
        unread = max(view["messageCount"] - _int(member.get("read")), 0)
        found[member["eventId"]] = view | {"unread": unread, "last": _last_view(crew.get("last"), user_id)}
    return found


# --------------------------------------------------------------------------- czyste funkcje


def clean_message(raw: object) -> str:
    """Tekst wiadomości: bez znaków sterujących i zmiany kierunku tekstu, bez zbędnych spacji; nowe linie
    zostają (najwyżej jedna pusta z rzędu)."""
    if not isinstance(raw, str):
        return ""
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept = ["".join(" " if unicodedata.category(c) == "Cc" else c for c in line if c not in _BIDI) for line in lines]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(" ".join(line.split()) for line in kept)).strip()


def icebreaker(event_id: str, nr: str) -> str:
    """Pytanie na start ekipy: stałe dla ekipy, różne ekipy dostają różne."""
    return ICEBREAKERS[zlib.crc32(f"{event_id}#{nr}".encode()) % len(ICEBREAKERS)]


def expires_at(event: dict, now: datetime) -> int:
    """TTL rekordów czatu: 30 dni po końcu wydarzenia; bez końca albo już po nim - 30 dni od teraz."""
    return max(_int(event.get("expiresAt")), int(now.timestamp())) + RETENTION_S


def iso(moment: datetime) -> str:
    """Czas w kluczach i odpowiedziach: ISO 8601 UTC z milisekundami, np. 2026-10-18T16:00:00.123Z."""
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# --------------------------------------------------------------------------- ekipa


def _my_crew(event_id: str, user_id: str, name: str, now: datetime, ttl: int) -> tuple[dict, dict]:
    """(ekipa, mój rekord member#); bez ekipy - dołączam do ekipy z wolnym miejscem albo zakładam nową."""
    member = _get(event_id, f"member#{user_id}")
    if member:
        crew = _get(event_id, f"crew#{member['crew']}")
        if crew and user_id in (crew.get("members") or {}):
            return crew, member
        table.delete_item(Key=_key(event_id, f"member#{user_id}"))  # ekipa wygasła albo mnie w niej nie ma
    return _join(event_id, user_id, name, now, ttl)


def _join(event_id: str, user_id: str, name: str, now: datetime, ttl: int) -> tuple[dict, dict]:
    """Pierwsza ekipa wydarzenia z wolnym miejscem (warunek: liczba osób się nie zmieniła) albo nowa ekipa.

    Konflikt z równoległym dołączeniem -> próbujemy jeszcze raz na świeżym stanie."""
    for _ in range(JOIN_RETRIES):
        crews = _rows(event_id, "crew#")
        found = next((c for c in crews if user_id in (c.get("members") or {})), None)
        if found:  # jestem w ekipie, ale bez rekordu member# (np. wygasł) - odtwarzamy go
            member = _member(event_id, user_id, _nr(found), now, ttl, _int(found.get("messages")))
            table.put_item(Item=member)
            return found, member

        joined = {"name": name, "joinedAt": iso(now)}
        target = next((c for c in crews if not c.get("closed") and _int(c.get("size")) < CREW_SIZE), None)
        if target:
            nr, size = _nr(target), _int(target.get("size"))
            notes = [_message(event_id, nr, "joined", now, ttl, userId=user_id, name=name)]
            if size + 1 == CREW_SIZE:
                notes.append(_message(event_id, nr, "full", now + timedelta(milliseconds=1), ttl))
            crew = target | {
                "members": (target.get("members") or {}) | {user_id: joined},
                "size": size + 1,
                "messages": _int(target.get("messages")) + len(notes),
                "last": _preview(notes[-1]),
            }
            write = _update(
                event_id,
                f"crew#{nr}",
                "SET #members.#me = :joined, #last = :last, expiresAt = :ttl ADD #size :one, #messages :notes",
                "#size = :size AND attribute_not_exists(#members.#me) AND attribute_not_exists(#closed)",
                {":joined": joined, ":last": crew["last"], ":ttl": ttl, ":one": 1, ":notes": len(notes), ":size": size},
                {"#me": user_id},
            )
        else:
            nr = f"{max((int(_nr(c)) for c in crews), default=0) + 1:03d}"
            notes = [_message(event_id, nr, "welcome", now, ttl, userId=user_id, name=name)]
            crew = {
                "eventId": event_id,
                "sk": f"crew#{nr}",
                "members": {user_id: joined},
                "size": 1,
                "messages": 1,
                "last": _preview(notes[0]),
                "createdAt": iso(now),
                "expiresAt": ttl,
            }
            write = _put(crew)
        member = _member(event_id, user_id, nr, now, ttl, _int(crew["messages"]))
        failed = _transact([_put(member), write, *(_put(note) for note in notes)])
        if not failed:
            return crew, member
        if failed[0] == "ConditionalCheckFailed":  # równoległe wejście z drugiej karty - ekipę już mam
            existing = _get(event_id, f"member#{user_id}")
            current = _get(event_id, f"crew#{existing['crew']}") if existing else None
            if existing and current:
                return current, existing
    raise ApiError(503, "Nie udało się dołączyć do ekipy, spróbuj ponownie")


def _member(event_id: str, user_id: str, nr: str, now: datetime, ttl: int, read: int) -> dict:
    """Mój rekord w ekipie; read = wiadomości, które już są (całą rozmowę widzę od razu po wejściu)."""
    return {
        "eventId": event_id,
        "sk": f"member#{user_id}",
        "userId": user_id,
        "crew": nr,
        "joinedAt": iso(now),
        "read": read,
        "expiresAt": ttl,
    }


def _crew_view(crew: dict, user_id: str) -> dict:
    """Ekipa w odpowiedzi: członkowie w kolejności dołączania (userId = tożsamość, dwie „Ole” to dwie osoby)."""
    members = sorted((crew.get("members") or {}).items(), key=lambda kv: (str(kv[1].get("joinedAt") or ""), kv[0]))
    return {
        "crew": _nr(crew),
        "capacity": CREW_SIZE,
        "members": [{"userId": uid, "name": m.get("name") or ANONYMOUS, "isMe": uid == user_id} for uid, m in members],
        "messageCount": _int(crew.get("messages")),
    }


# --------------------------------------------------------------------------- wiadomości


def _messages(event_id: str, nr: str, after: datetime | None) -> list[dict]:
    """Wiadomości ekipy od najstarszej: bez `after` najnowsze PAGE, z `after` - od after - OVERLAP."""
    prefix = f"msg#{nr}#"
    if after is None:
        rows = table.query(
            KeyConditionExpression=Key("eventId").eq(event_id) & Key("sk").begins_with(prefix),
            ScanIndexForward=False,
            Limit=PAGE,
            ConsistentRead=True,
        )["Items"]
        return rows[::-1]
    since = prefix + iso(after - OVERLAP)
    return table.query(
        KeyConditionExpression=Key("eventId").eq(event_id) & Key("sk").between(since, prefix + "~"),
        Limit=PAGE,
        ConsistentRead=True,
    )["Items"]


def _mark_read(event_id: str, user_id: str, count: int, ttl: int) -> None:
    """read = messages (bez cofania, gdy równoległe żądanie zapisało już więcej)."""
    try:
        table.update_item(
            Key=_key(event_id, f"member#{user_id}"),
            UpdateExpression="SET #read = :count, expiresAt = :ttl",
            ConditionExpression="attribute_exists(sk) AND (attribute_not_exists(#read) OR #read < :count)",
            ExpressionAttributeNames={"#read": "read"},
            ExpressionAttributeValues={":count": count, ":ttl": ttl},
        )
    except ddb.exceptions.ConditionalCheckFailedException:
        pass


def _message(event_id: str, nr: str, kind: str, at: datetime, ttl: int, **fields: Any) -> dict:
    sent_at = iso(at)
    item = {
        "eventId": event_id,
        "sk": f"msg#{nr}#{sent_at}#{secrets.token_hex(3)}",
        "kind": kind,
        "sentAt": sent_at,
        "expiresAt": ttl,
    }
    return item | {k: v for k, v in fields.items() if v}


def _message_view(item: dict, user_id: str) -> dict:
    return {
        "id": item["sk"].removeprefix("msg#"),
        "kind": item.get("kind") or "user",
        "userId": item.get("userId"),
        "name": item.get("name"),
        "text": item.get("text"),
        "sentAt": item["sentAt"],
        "isMe": item.get("userId") == user_id,
    }


def _preview(message: dict) -> dict:
    """Ostatnia wiadomość w rekordzie ekipy (podgląd na „Twoje”): tekst w jednej linii, skrócony."""
    preview = {k: message[k] for k in ("kind", "userId", "name", "sentAt") if message.get(k)}
    if message.get("text"):
        line = " ".join(message["text"].split())
        preview["text"] = line if len(line) <= PREVIEW else line[: PREVIEW - 1].rstrip() + "…"
    return preview


def _last_view(last: dict | None, user_id: str) -> dict | None:
    if not last:
        return None
    return {k: last.get(k) for k in ("kind", "userId", "name", "text", "sentAt")} | {
        "isMe": last.get("userId") == user_id
    }


# --------------------------------------------------------------------------- DynamoDB


def _key(event_id: str, sk: str) -> dict:
    return {"eventId": event_id, "sk": sk}


def _nr(crew: dict) -> str:
    return str(crew["sk"]).removeprefix("crew#")


def _int(value: Any) -> int:
    return int(value or 0)


def _get(event_id: str, sk: str) -> dict | None:
    return table.get_item(Key=_key(event_id, sk), ConsistentRead=True).get("Item")


def _rows(event_id: str, prefix: str) -> list[dict]:
    params: dict[str, Any] = {
        "KeyConditionExpression": Key("eventId").eq(event_id) & Key("sk").begins_with(prefix),
        "ConsistentRead": True,
    }
    rows: list[dict] = []
    while True:
        page = table.query(**params)
        rows.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            return rows
        params["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def _batch_get(keys: list[dict]) -> list[dict]:
    """BatchGetItem po 100 kluczy, z ponowieniem nieprzetworzonych (jak store.saves_for)."""
    found: list[dict] = []
    for i in range(0, len(keys), BATCH_GET_MAX):
        request: dict[str, Any] = {CREWS_TABLE: {"Keys": keys[i : i + BATCH_GET_MAX]}}
        for attempt in range(5):
            result = ddb.batch_get_item(RequestItems=request)
            found.extend(result.get("Responses", {}).get(CREWS_TABLE, []))
            request = result.get("UnprocessedKeys") or {}
            if not request:
                break
            time.sleep(0.05 * 2**attempt)
    return found


def _put(item: dict) -> dict:
    """Put do transakcji: tylko nowy rekord (istniejący = warunek niespełniony)."""
    return {"Put": {"TableName": CREWS_TABLE, "Item": item, "ConditionExpression": "attribute_not_exists(sk)"}}


def _update(event_id: str, sk: str, update: str, condition: str, values: dict, names: dict | None = None) -> dict:
    """Update do transakcji. Nazwy zastępcze: #<pole> dla słów zastrzeżonych (RESERVED) + własne (#me = userId)."""
    used = set(re.findall(r"#\w+", f"{update} {condition}"))
    known = {f"#{a}": a for a in RESERVED} | (names or {})
    return {
        "Update": {
            "TableName": CREWS_TABLE,
            "Key": _key(event_id, sk),
            "UpdateExpression": update,
            "ConditionExpression": condition,
            "ExpressionAttributeNames": {k: v for k, v in known.items() if k in used},
            "ExpressionAttributeValues": values,
        }
    }


def _transact(items: list[dict]) -> list[str | None]:
    """[] = zapisano; inaczej kod powodu dla każdej pozycji (np. "ConditionalCheckFailed", None = bez błędu)."""
    try:
        ddb.transact_write_items(TransactItems=items)
        return []
    except ddb.exceptions.TransactionCanceledException as e:
        reasons = [r.get("Code") for r in e.response.get("CancellationReasons", [])]
        return [None if code in (None, "None") else code for code in reasons] or ["TransactionCanceled"]

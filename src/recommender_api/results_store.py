"""Zapisane rekomendacje (tabela recommendations): gotowe zestawy kart per użytkownik.

Klucz: userId + setKey = rodzaj okna, daty, limit i wpisana fraza, np.
"today#2026-10-17#2026-10-17#12#" albo "date#2026-10-30#2026-10-30#12#jazz".

status "ready"   zestaw kart (body); ważny, dopóki profil się nie zmienił (prefsHash), nie minął
                 max_age i zostało w nim dość niezakończonych wydarzeń (handler._reusable)
status "pending" ktoś właśnie liczy ten zestaw (claim) - inni czekają, zamiast liczyć drugi raz;
                 po PENDING_SECONDS uznajemy, że liczenie padło, i można je przejąć
Stare zestawy usuwa TTL (expiresAt = dzień po końcu okna).

Bez tabeli (lokalnie) zestawy trzymane są w pamięci procesu.
"""

import hashlib
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from botocore.exceptions import ClientError

WARSAW = ZoneInfo("Europe/Warsaw")
# Zmiana logiki rankingu lub formatu kart -> podbij, żeby zapisane zestawy policzyły się od nowa
RESULTS_VERSION = 1
PENDING_SECONDS = 120


def set_key(when: str, span: tuple[date, date], query: str, limit: int) -> str:
    return f"{when}#{span[0].isoformat()}#{span[1].isoformat()}#{limit}#{query.lower()}"


def prefs_hash(prefs: dict, rag_profile: str | None) -> str:
    payload = json.dumps([RESULTS_VERSION, prefs, rag_profile], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def expires_at(span: tuple[date, date]) -> int:
    return int(datetime.combine(span[1] + timedelta(days=1), time(), tzinfo=WARSAW).timestamp())


class ResultsStore:
    def __init__(self, table=None):
        self.table = table
        self._memory: dict[tuple[str, str], dict] = {}

    def get(self, user_id: str, key: str) -> dict | None:
        if self.table is None:
            return self._memory.get((user_id, key))
        # Spójny odczyt: "pending" -> "ready" ma być widać od razu
        return self.table.get_item(Key={"userId": user_id, "setKey": key}, ConsistentRead=True).get("Item")

    def claim(self, user_id: str, key: str, fingerprint: str, now: datetime) -> bool:
        """Oznacza zestaw jako liczony. False, gdy ktoś inny właśnie liczy go dla tych samych preferencji."""
        claimed_at = int(now.timestamp())
        item = {"userId": user_id, "setKey": key, "status": "pending", "prefsHash": fingerprint,
                "claimedAt": claimed_at, "expiresAt": claimed_at + 86400}
        if self.table is None:
            current = self._memory.get((user_id, key))
            busy = (current and current.get("status") == "pending" and current.get("prefsHash") == fingerprint
                    and current["claimedAt"] >= claimed_at - PENDING_SECONDS)
            if busy:
                return False
            self._memory[(user_id, key)] = item
            return True
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(setKey) OR prefsHash <> :h OR #s <> :pending OR claimedAt < :cutoff",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":h": fingerprint, ":pending": "pending", ":cutoff": claimed_at - PENDING_SECONDS},
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def put(self, user_id: str, key: str, fingerprint: str, body: dict, expires: int) -> None:
        """Zapisuje gotowy zestaw - chyba że w międzyczasie profil się zmienił i ktoś liczy już nowy."""
        item = {
            "userId": user_id,
            "setKey": key,
            "status": "ready",
            "prefsHash": fingerprint,
            "generatedAt": body["generatedAt"],
            # JSON jako tekst: bez konwersji liczb na Decimal i z powrotem
            "body": json.dumps(body, ensure_ascii=False, default=str),
            "expiresAt": expires,
        }
        if self.table is None:
            current = self._memory.get((user_id, key))
            if not current or current.get("prefsHash") == fingerprint:
                self._memory[(user_id, key)] = item
            return
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(setKey) OR prefsHash = :h",
                                ExpressionAttributeValues={":h": fingerprint})
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    def release(self, user_id: str, key: str, fingerprint: str) -> None:
        """Zwalnia "pending" po nieudanym liczeniu, żeby inni nie czekali do końca PENDING_SECONDS."""
        if self.table is None:
            current = self._memory.get((user_id, key))
            if current and current.get("status") == "pending" and current.get("prefsHash") == fingerprint:
                del self._memory[(user_id, key)]
            return
        try:
            self.table.delete_item(
                Key={"userId": user_id, "setKey": key},
                ConditionExpression="#s = :pending AND prefsHash = :h",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":pending": "pending", ":h": fingerprint},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
